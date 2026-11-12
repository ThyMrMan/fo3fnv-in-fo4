"""The face textures the Creation Kit bakes for an NPC (FaceCustomization _d, _msn, _s): its tint layers, and the
race's defaults for slots it leaves empty, composited in order onto its face set's diffuse, normal and specular.

    py -3.14 -m fo4_import.face.face_tint --plugin <plugin> --dirs <folders> --npc <FormID> --out <folder>

Scratch use: nothing in the build reads it yet.

See: docs/fork/fo4_facegen_plan.md#face-d-decode
See: docs/fork/fo4_facegen_plan.md#face-maps
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
#: Per FaceCustomization texture besides _d: (face set slot it starts from, position of an option's own TTET).
MAPS = {'msn': (1, 1), 's': (7, 2)}


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


def with_defaults(layers: list, options: dict) -> list:
    """`layers`, then each option with a default value in a slot no layer fills, at that value; with no Skin Tone
    layer, the Skin Tone option's first template colour (TTEC order) at full value."""
    have = {layer.index for layer in layers}
    slots = {options[layer.index].slot for layer in layers if layer.index in options}
    out = layers + [Layer(i, 2, o.default) for i, o in options.items()
                    if o.default > 0 and i not in have and o.slot not in slots]
    tone = next((i for i, o in options.items() if o.slot == SKIN_TONE_SLOT and o.colours), None)
    if tone is not None and SKIN_TONE_SLOT not in slots:
        out.append(Layer(tone, COLOUR_LAYER, 1.0, template=next(iter(options[tone].colours))))
    return out


def soft_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Photoshop's Soft Light of `b` over `a` (0..1)."""
    return np.where(b <= 0.5, 2 * a * b + a * a * (1 - 2 * b), 2 * a * (1 - b) + np.sqrt(a) * (2 * b - 1))


def blend(op: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Layer `b` over `a` (0..1) by blend operation `op`."""
    if op == MULTIPLY:
        return a * b
    if op == OVERLAY:
        return np.where(a <= 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    if op == HARD_LIGHT:
        return np.where(b <= 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    return soft_light(a, b) if op == SOFT_LIGHT else b + 0 * a


def colour_of(src: facegeom.Sources, race: facegeom.Rec, option: Option, layer: Layer) -> tuple:
    """(RGB 0..1, alpha, blend) of a colour layer: its template's (by TTEC template index) if it names one the
    option has, else its own colour at alpha 1 with the option's blend."""
    if layer.template in option.colours:
        data, alpha, op = option.colours[layer.template]
        return np.frombuffer(src.get(race, data).first(b'CNAM')[:3], np.uint8) / np.float32(255), alpha, op
    return np.array(layer.colour, np.float32) / 255, 1.0, option.blend


@functools.lru_cache(maxsize=24)
def texture(src: facegeom.Sources, path: str, size: int) -> np.ndarray:
    """A texture under textures\\ as float RGBA 0..1 at `size` square (bilinear)."""
    img = Image.open(io.BytesIO(src.read('textures\\' + path))).convert('RGBA')
    img = img if img.size == (size, size) else img.resize((size, size), Image.BILINEAR)
    return np.asarray(img, np.float32) / 255


def apply(out: np.ndarray, option: Option, layer: Layer, rgba: np.ndarray, layer_colour=None) -> np.ndarray:
    """`out` with one layer drawn from the option's texture `rgba`: a colour layer (`layer_colour` = colour_of's)
    at value x alpha through the texture's red channel (the skin tone unmasked, by Soft Light); a value-only one
    by the texture's RGB at value x alpha, but a Default-blend detail other than brows at value x sqrt(alpha),
    twice."""
    if layer.kind == COLOUR_LAYER:
        rgb, alpha, op = layer_colour
        tone = option.slot == SKIN_TONE_SLOT
        m = (1.0 if tone else rgba[..., :1]) * layer.value * alpha
        return out * (1 - m) + m * blend(SOFT_LIGHT if tone else op, out, rgb)
    twice = option.blend == DEFAULT and option.slot != BROW_SLOT
    m = layer.value * (np.sqrt(rgba[..., 3:]) if twice else rgba[..., 3:])
    for _ in range(2 if twice else 1):
        out = out * (1 - m) + m * blend(option.blend, out, rgba[..., :3])
    return out


def apply_map(out: np.ndarray, layer: Layer, diffuse: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """`out` (map RG) lerped to `rgba` at value x sqrt(`diffuse` alpha)."""
    m = layer.value * np.sqrt(diffuse[..., 3:])
    return out * (1 - m) + m * rgba[..., :2]


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
        """[(Option, Layer)] drawn in order (with_defaults), value > 0."""
        options = race_options(self.race, self.female)
        return [(options[layer.index], layer) for layer in with_defaults(npc_layers(self.npc), options)
                if layer.index in options and layer.value > 0]

    def size(self, path: str, size: int = None) -> int:
        """`size`, else texture `path`'s width."""
        return size or Image.open(io.BytesIO(self.src.read('textures\\' + path))).size[0]


def face_diffuse(face: Face, size: int = None) -> np.ndarray:
    """The NPC's face _d as float RGB 0..1 at `size` square (default: its face set diffuse's size)."""
    base_path = face.slots()[0]
    size = face.size(base_path, size)
    out = texture(face.src, base_path, size)[..., :3].copy()
    for option, layer in face.layers():
        if option.texture or option.slot == SKIN_TONE_SLOT:
            rgba = texture(face.src, option.texture, size) if option.texture else None
            colour = colour_of(face.src, face.race, option, layer) if layer.kind == COLOUR_LAYER else None
            out = apply(out, option, layer, rgba, colour)
    return out


def face_map(face: Face, kind: str, size: int = None) -> np.ndarray:
    """The NPC's face _msn or _s (`kind`) as float RG 0..1 at `size` square (default: the face set map's size):
    the face set's map with each value-only layer's own map over it (apply_map)."""
    base_path = face.slots()[MAPS[kind][0]]
    size = face.size(base_path, size)
    out = texture(face.src, base_path, size)[..., :2].copy()
    for option, layer in face.layers():
        if layer.kind != COLOUR_LAYER and option.texture and option.map_texture(kind):
            diffuse = texture(face.src, option.texture, size)
            out = apply_map(out, layer, diffuse, texture(face.src, option.map_texture(kind), size))
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
