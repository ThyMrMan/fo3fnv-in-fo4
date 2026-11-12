"""The face textures the Creation Kit bakes for an NPC (FaceCustomization _d, _msn, _s), as its face shader does:
the NPC's tint layers plus a default layer for every race option it doesn't list, in reverse race order, each
blended in linear light at mask^(1/2.2) x value onto its face set's diffuse, normal and specular.

    py -3.14 -m fo4_import.face.face_tint --plugin <plugin> --dirs <folders> --npc <FormID> --out <folder>

See: docs/fork/fo4_facegen_plan.md#ck-face-shader
"""

import argparse
import functools
import io
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.face import facegeom

#: xEdit's TETI slot enum: Skin Tone, Brows.
SKIN_TONE_SLOT, BROW_SLOT = 12, 23
#: Blend operations (TTEB, TTEC): Default (the layer replaces), Multiply, Overlay, Soft Light, Hard Light.
DEFAULT, MULTIPLY, OVERLAY, SOFT_LIGHT, HARD_LIGHT = range(5)
#: NPC TETI data type of a layer with a colour (the other, 2, is value-only).
COLOUR_LAYER = 1
#: TETI slots: below PALETTE_SLOT masks, then palettes (colour layers), from TEXTURE_SET_SLOT on texture sets.
PALETTE_SLOT, TEXTURE_SET_SLOT = 7, 21
#: The face shader's power for masks, Soft Light and its output.
GAMMA = 2.2
#: Per FaceCustomization texture besides _d: (face set slot it starts from, position of an option's own TTET).
MAPS = {'msn': (1, 1), 's': (7, 2)}
#: The whole image as an index: every row and column.
WHOLE = (slice(None), slice(None))
#: RGBA channel whose zeros leave the face untouched: red masks a colour layer, alpha a value-only layer.
RED, ALPHA = 0, 3


@dataclass(frozen=True)
class Option:
    """One race tint option: TETI slot, TTET textures in order (_d, _n, _s), TTEB blend, TTEC template colours
    {template index: (CLFM FormID data, alpha, blend)}, TTED default (0 when absent)."""

    slot: int
    textures: tuple
    blend: int
    colours: dict
    default: float

    @property
    def texture(self) -> str:
        """The option's diffuse texture ('' for none)."""
        return self.textures[0] if self.textures else ''

    def map_texture(self, kind: str) -> str:
        """The option's texture for FaceCustomization `kind` ('' for none)."""
        at = MAPS[kind][1]
        return self.textures[at] if len(self.textures) > at else ''

    @property
    def palette(self) -> bool:
        """True for a palette (colour) option, by its slot."""
        return PALETTE_SLOT <= self.slot < TEXTURE_SET_SLOT

    @property
    def default_entry(self) -> tuple:
        """(template index, TTEC entry) at TTED's bits as an index; (None, None)."""
        at = struct.unpack('<I', struct.pack('<f', self.default))[0]
        entries = list(self.colours.items())
        return entries[at] if at < len(entries) else (None, None)


@dataclass(frozen=True)
class Layer:
    """One NPC tint layer: race option index, data type, value 0..1, own RGB (0..255) or None, template or None."""

    index: int
    kind: int
    value: float
    colour: tuple = None
    template: int = None


def _option_fields(option: dict, tag: bytes, data: bytes) -> None:
    """Set the field subrecord `tag` gives on the option being read (a dict of Option's fields)."""
    if tag == b'TTET':
        option['textures'] += (facegeom.zstr(data),)
    elif tag == b'TTEB':
        option['blend'] = struct.unpack('<I', data)[0]
    elif tag == b'TTED':
        option['default'] = struct.unpack('<f', data)[0]
    elif tag == b'TTEC':
        entries = (struct.unpack_from('<IfHI', data, at) for at in range(0, len(data) - 13, 14))
        option['colours'] = {index: (struct.pack('<I', fid), alpha, op) for fid, alpha, index, op in entries}


def race_options(race: facegeom.Rec, female: bool) -> dict:
    """{option index: Option} of the race's tint options for one sex."""
    out, current = {}, None
    for tag, data in facegeom.sex_section(race, female):
        if tag == b'TETI':
            slot, index = struct.unpack('<HH', data)
            current = out[index] = dict(slot=slot, textures=(), blend=DEFAULT, colours={}, default=0.0)
        elif current is not None:
            _option_fields(current, tag, data)
    return {index: Option(**fields) for index, fields in out.items()}


def npc_layers(npc: facegeom.Rec) -> list:
    """The NPC's tint layers (TETI then TEND), in record order."""
    out, teti = [], None
    for tag, data in npc.subs:
        if tag == b'TETI':
            teti = struct.unpack('<HH', data)
        elif tag == b'TEND' and teti:
            colour = tuple(data[1:4]) if len(data) >= 5 else None
            template = struct.unpack_from('<h', data, 5)[0] if len(data) >= 7 else None
            out.append(Layer(teti[1], teti[0], data[0] / 100, colour, template))
            teti = None
    return out


def default_layer(index: int, option: Option):
    """The layer the CK adds for an option an NPC doesn't list: a palette's default entry at that entry's alpha, a
    texture set at TTED; None for a mask or a palette without entries."""
    if option.palette:
        template, entry = option.default_entry
        return Layer(index, COLOUR_LAYER, entry[1], template=template) if entry else None
    return Layer(index, 2, option.default) if option.slot >= TEXTURE_SET_SLOT else None


def baked_layers(layers: list, options: dict) -> list:
    """[(Option, Layer)] the CK bakes, drawn in order: the NPC's `layers` plus default_layer for each option they
    don't name (no brow default when a brow layer is above 0), value > 0, in reverse race option order.

    See: docs/fork/fo4_facegen_plan.md#ck-layer-list
    """
    have = {layer.index for layer in layers}
    brow = any(options[l.index].slot == BROW_SLOT and l.value > 0 for l in layers if l.index in options)
    added = [default_layer(i, o) for i, o in options.items() if i not in have and not (brow and o.slot == BROW_SLOT)]
    order = {index: at for at, index in enumerate(options)}
    kept = [layer for layer in layers + added if layer and layer.index in options and layer.value > 0]
    return [(options[layer.index], layer) for layer in sorted(kept, key=lambda layer: -order[layer.index])]


def linear(c: np.ndarray) -> np.ndarray:
    """sRGB 0..1 to linear light, the GPU's decode of an sRGB texture."""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def soft_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Photoshop's Soft Light of `b` over `a` (0..1)."""
    return np.where(b < 0.5, 2 * a * b + a * a * (1 - 2 * b), 2 * a * (1 - b) + np.sqrt(a) * (2 * b - 1))


def blend(op: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Layer `b` over `a` (linear 0..1) by blend operation `op`, as the face shader does (Soft Light in gamma)."""
    if op == MULTIPLY:
        return a * b
    if op == OVERLAY:
        return np.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    if op == HARD_LIGHT:
        return np.where(b < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    return soft_light(a ** (1 / GAMMA), b ** (1 / GAMMA)) ** GAMMA if op == SOFT_LIGHT else b + 0 * a


def colour_of(src: facegeom.Sources, race: facegeom.Rec, option: Option, layer: Layer) -> tuple:
    """(linear RGB, blend) of a colour layer: its template entry's colour and blend if it names one the option has,
    else its own colour with the default entry's blend; the skin tone always by Soft Light."""
    if layer.template in option.colours:
        data, _, op = option.colours[layer.template]
        rgb = np.frombuffer(src.get(race, data).first(b'CNAM')[:3], np.uint8) / np.float32(255)
    else:
        rgb, op = np.array(layer.colour, np.float32) / 255, (option.default_entry[1] or (0, 0, option.blend))[2]
    return linear(rgb), SOFT_LIGHT if option.slot == SKIN_TONE_SLOT else op


def image(src: facegeom.Sources, path: str, size: int) -> np.ndarray:
    """A texture under textures\\ as RGBA uint8 at `size` square: read texel by texel as the shader's `ld` does,
    averaged when `size` is below the texture's (the CK's own face is larger and is shrunk after)."""
    img = Image.open(io.BytesIO(src.read('textures\\' + path))).convert('RGBA')
    shrink = Image.BILINEAR if size < img.size[0] else Image.NEAREST
    img = img if img.size == (size, size) else img.resize((size, size), shrink)
    return np.asarray(img)


@functools.cache
def crop(src: facegeom.Sources, path: str, size: int, area: tuple) -> np.ndarray:
    """`area` of image(), kept for the process: only the part a layer draws is held.

    See: docs/fork/fo4_facegen_plan.md#own-stage-speed
    """
    return image(src, path, size)[area].copy()


def texture(src: facegeom.Sources, path: str, size: int, area: tuple = WHOLE) -> np.ndarray:
    """crop() as float RGBA 0..1."""
    return np.asarray(crop(src, path, size, area), np.float32) / 255


@functools.cache
def painted(src: facegeom.Sources, path: str, size: int, channel: int) -> tuple:
    """Slices of image()'s smallest box holding `channel`'s nonzeros, or None."""
    values = image(src, path, size)[..., channel]
    rows, cols = np.flatnonzero(values.any(1)), np.flatnonzero(values.any(0))
    return (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)) if len(rows) else None


def weight(mask: np.ndarray, layer: Layer) -> np.ndarray:
    """A layer's strength per texel: its mask (0..1) to the 1/GAMMA, times its value."""
    return mask ** (1 / GAMMA) * layer.value


def apply(out: np.ndarray, option: Option, layer: Layer, rgba: np.ndarray, layer_colour=None) -> np.ndarray:
    """`out` (linear RGB) with one layer drawn from the option's texture `rgba` (raw 0..1, None for none): a palette
    layer's colour (`layer_colour` = colour_of's) through the texture's red channel, a texture set's linear RGB
    through its alpha, each lerped in at weight() by its blend."""
    if option.palette:
        rgb, op = layer_colour
        mask = rgba[..., :1] if rgba is not None else np.ones((1, 1, 1), np.float32)
    else:
        rgb, op, mask = linear(rgba[..., :3]), option.blend, rgba[..., 3:]
    return out + weight(mask, layer) * (blend(op, out, rgb) - out)


def apply_map(out: np.ndarray, layer: Layer, diffuse: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """`out` (map RG, raw) lerped to `rgba` at weight() of `diffuse`'s alpha."""
    return out + weight(diffuse[..., 3:], layer) * (rgba[..., :2] - out)


@dataclass(frozen=True)
class Face:
    """What an NPC's face textures are drawn from: Sources, the NPC, its race, female."""

    src: facegeom.Sources
    npc: facegeom.Rec
    race: facegeom.Rec
    female: bool

    def slots(self) -> list:
        """Texture slots of the NPC's face set, else the race default's."""
        owner, tag = (self.npc, b'FTST') if self.npc.first(b'FTST') else (self.race, facegeom.FACE_SETS[self.female])
        return facegeom.txst_slots(self.src, self.src.get(owner, owner.first(tag)))

    def layers(self) -> list:
        """[(Option, Layer)] drawn in order (baked_layers)."""
        return baked_layers(npc_layers(self.npc), race_options(self.race, self.female))

    def size(self, path: str, size: int = None) -> int:
        """`size`, else texture `path`'s width."""
        return size or Image.open(io.BytesIO(self.src.read('textures\\' + path))).size[0]


def area(face: Face, option: Option, size: int):
    """The painted() box where a layer can change the _d; None if it draws nothing."""
    if option.palette:
        return painted(face.src, option.texture, size, RED) if option.texture else WHOLE
    return painted(face.src, option.texture, size, ALPHA) if option.slot >= TEXTURE_SET_SLOT and option.texture else None


def face_diffuse(face: Face, size: int = None) -> np.ndarray:
    """The NPC's face _d as float sRGB 0..1 at `size` square (default: its face set diffuse's size): the face set's
    diffuse in linear light, each layer applied inside its area(), back by the shader's 1/GAMMA.

    See: docs/fork/fo4_facegen_plan.md#ck-face-shader
    """
    base_path = face.slots()[0]
    size = face.size(base_path, size)
    out = linear(texture(face.src, base_path, size)[..., :3])
    for option, layer in face.layers():
        at = area(face, option, size)
        if at is not None:
            rgba = texture(face.src, option.texture, size, at) if option.texture else None
            colour = colour_of(face.src, face.race, option, layer) if option.palette else None
            out[at] = apply(out[at], option, layer, rgba, colour)
    return np.clip(out, 0, 1) ** (1 / GAMMA)


def face_map(face: Face, kind: str, size: int = None) -> np.ndarray:
    """The NPC's face _msn or _s (`kind`) as float RG 0..1 at `size` square (default: the face set map's size):
    the face set's map with each texture set's own map lerped over it (apply_map), inside its diffuse's painted
    alpha."""
    base_path = face.slots()[MAPS[kind][0]]
    size = face.size(base_path, size)
    out = texture(face.src, base_path, size)[..., :2]
    for option, layer in face.layers():
        at = area(face, option, size) if not option.palette else None
        if at is not None and option.map_texture(kind):
            diffuse = texture(face.src, option.texture, size, at)
            out[at] = apply_map(out[at], layer, diffuse, texture(face.src, option.map_texture(kind), size, at))
    return out


def as_image(values: np.ndarray) -> Image.Image:
    """Float 0..1 RGB, or RG (blue 0), as an 8-bit RGB image."""
    rgb = values if values.shape[2] == 3 else np.dstack([values, np.zeros(values.shape[:2], values.dtype)])
    return Image.fromarray(np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def main(argv=None) -> None:
    """Write one NPC's face _d, _msn and _s as PNGs to the folder --out."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--plugin', type=Path, required=True, help="the NPC's plugin (its masters are found in --dirs)")
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='folders holding masters, loose files and BA2s')
    p.add_argument('--npc', required=True, help="the NPC's FormID (hex; the plugin's own index is ignored)")
    p.add_argument('--size', type=int, help="square size (default: each face set texture's)")
    p.add_argument('--out', type=Path, required=True, help='folder for <FormID>_d.png, _msn.png, _s.png')
    args = p.parse_args(argv)
    src = facegeom.Sources(args.plugin, [args.plugin.parent] + args.dirs)
    npc, race, female, _ = facegeom.npc_face(src, args.plugin.name, int(args.npc, 16))
    face, stem = Face(src, npc, race, female), f'{int(args.npc, 16) & 0xFFFFFF:08X}'
    args.out.mkdir(parents=True, exist_ok=True)
    as_image(face_diffuse(face, args.size)).save(args.out / f'{stem}_d.png')
    for kind in MAPS:
        as_image(face_map(face, kind, args.size)).save(args.out / f'{stem}_{kind}.png')
    print('wrote', args.out / f'{stem}_*.png')


if __name__ == '__main__':
    main()
