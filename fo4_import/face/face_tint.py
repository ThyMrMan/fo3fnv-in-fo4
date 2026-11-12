"""The face diffuse (_d) the Creation Kit bakes for an NPC: its tint layers, and the race's defaults for slots it
leaves empty, composited in order onto its face set's diffuse.

    py -3.14 -m fo4_import.face.face_tint --plugin <plugin> --dirs <folders> --npc <FormID> --out <png>

Scratch use: nothing in the build reads it yet.

See: docs/fork/fo4_facegen_plan.md#face-d-decode
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


@dataclass(frozen=True)
class Option:
    """One race tint option: TETI slot, first TTET texture ('' for none), TTEB blend, TTEC template colours
    {template index: (CLFM FormID data, alpha, blend)}, TTED default (0 when absent)."""

    slot: int
    texture: str
    blend: int
    colours: dict
    default: float


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
    if tag == b'TTET' and not option['texture']:
        option['texture'] = facegeom.zstr(data)
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
            current = out[index] = dict(slot=slot, texture='', blend=DEFAULT, colours={}, default=0.0)
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


def face_diffuse(src: facegeom.Sources, npc: facegeom.Rec, race: facegeom.Rec, female: bool,
                 size: int = None) -> np.ndarray:
    """The NPC's face _d as float RGB 0..1 at `size` square (default: its face set diffuse's size)."""
    owner, tag = (npc, b'FTST') if npc.first(b'FTST') else (race, facegeom.FACE_SETS[female])
    base_path = facegeom.txst_slots(src, src.get(owner, owner.first(tag)))[0]
    size = size or Image.open(io.BytesIO(src.read('textures\\' + base_path))).size[0]
    out = texture(src, base_path, size)[..., :3].copy()
    options = race_options(race, female)
    for layer in with_defaults(npc_layers(npc), options):
        option = options.get(layer.index)
        drawn = option and layer.value > 0 and (option.texture or option.slot == SKIN_TONE_SLOT)
        if drawn:
            rgba = texture(src, option.texture, size) if option.texture else None
            colour = colour_of(src, race, option, layer) if layer.kind == COLOUR_LAYER else None
            out = apply(out, option, layer, rgba, colour)
    return out


def main(argv=None) -> None:
    """Write one NPC's face _d as a PNG to --out."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--plugin', type=Path, required=True, help="the NPC's plugin (its masters are found in --dirs)")
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='folders holding masters, loose files and BA2s')
    p.add_argument('--npc', required=True, help="the NPC's FormID (hex; the plugin's own index is ignored)")
    p.add_argument('--size', type=int, help="square size (default: the face set diffuse's)")
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    src = facegeom.Sources(args.plugin, [args.plugin.parent] + args.dirs)
    npc, race, female, _ = facegeom.npc_face(src, args.plugin.name, int(args.npc, 16))
    rgb = face_diffuse(src, npc, race, female, args.size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(args.out)
    print('wrote', args.out)


if __name__ == '__main__':
    main()
