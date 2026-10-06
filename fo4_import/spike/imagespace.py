"""An FNV imagespace as an FO4 one: FO4's interior HDR, FNV's colour grading baked into its LUT.

FNV grades in display space after a linear exposure (ISHDRBLENDINSHADERCIN):
with Y = dot(c, FNV_LUMA), c = lerp(Y, c, saturation), then
lerp(c, Y x tint colour, tint amount), then (c x brightness - pivot) x
contrast + pivot. IMGS DNAM's cinematic block has a flags word after the tint
(saturation 1, contrast 2, tint 4, brightness 8); an unset value is not
applied. FO4 tonemaps (Hable curve), applies its own cinematic, then looks
the gamma-encoded colour up in a 16^3 LUT (TX00, 16 slices across a 256 x 16
texture) and writes the result. The FO4 imagespace is BASE_IMAGESPACE (the
common vanilla interior one) with its cinematic left neutral and its LUT
replaced by FNV's grading over the identity.

See: docs/fork/fo4_spikes.md#spike-2-imagespace
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm DefaultImageSpaceF4LUT: the imagespace of 180 of 317 vanilla interior cells that name one.
BASE_IMAGESPACE = 0x17161E
LUT_SIZE = 16
#: FNV's cinematic luminance weights (its shader's dot product).
FNV_LUMA = np.array([0.299, 0.587, 0.114])
SATURATION, CONTRAST, TINT, BRIGHTNESS = 1, 2, 4, 8
#: Offset of the cinematic block in an FNV IMGS DNAM: 132-byte records lack the skin dimmer.
OLD_DNAM, OLD_CINEMATIC, CINEMATIC = 132, 96, 100
#: Where generated LUTs go, under Textures (TX00 is relative to Textures).
LUT_FOLDER = 'Effects\\LUTs\\FNV'


@dataclass
class Cinematic:
    """FNV's colour grading, with unflagged parts neutral."""
    saturation: float
    pivot: float
    contrast: float
    brightness: float
    tint: tuple
    tint_amount: float


def cinematic(dnam: bytes) -> Cinematic:
    """The cinematic block of an FNV IMGS DNAM."""
    offset = OLD_CINEMATIC if len(dnam) == OLD_DNAM else CINEMATIC
    sat, pivot, con, bri, r, g, b, amount, flags = struct.unpack_from('<8fI', dnam, offset)
    return Cinematic(sat if flags & SATURATION else 1.0, pivot, con if flags & CONTRAST else 1.0,
                     bri if flags & BRIGHTNESS else 1.0, (r, g, b), amount if flags & TINT else 0.0)


def grade(rgb: np.ndarray, c: Cinematic) -> np.ndarray:
    """Display colours (0..1, [..., 3]) graded as FNV's cinematic pass does, clamped."""
    y = (rgb @ FNV_LUMA)[..., None]
    out = y + c.saturation * (rgb - y)
    out = out + c.tint_amount * (y * np.asarray(c.tint) - out)
    out = (out * c.brightness - c.pivot) * c.contrast + c.pivot
    return np.clip(out, 0.0, 1.0)


def identity() -> np.ndarray:
    """The identity LUT's colours: red across a slice, green down, blue by slice."""
    steps = np.arange(LUT_SIZE) / (LUT_SIZE - 1)
    g, b, r = np.meshgrid(steps, steps, steps, indexing='ij')
    return np.stack([r, g, b], -1).reshape(LUT_SIZE, LUT_SIZE * LUT_SIZE, 3)


def lut_dds(rgb: np.ndarray) -> bytes:
    """A LUT (0..1 RGB, [16, 256, 3]) as an uncompressed 24-bit DDS, laid out like FO4's own LUTs."""
    height, width, _ = rgb.shape
    header = struct.pack('<4s7I44s', b'DDS ', 124, 0x81007, height, width, width * height * 3, 0, 0, bytes(44))
    header += struct.pack('<2I4s5I', 32, 0x40, bytes(4), 24, 0xFF0000, 0xFF00, 0xFF, 0)
    header += struct.pack('<5I', 0x1000, 0, 0, 0, 0)
    pixels = np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)[..., ::-1]
    return header + pixels.tobytes()


def write_lut(dnam: bytes, edid: str, data_dir: Path) -> str:
    """Write FNV imagespace `edid`'s grading LUT into the data folder; its TX00 path."""
    rel = f'{LUT_FOLDER}\\{edid}.dds'
    path = data_dir / 'Textures' / rel.replace(chr(92), '/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(lut_dds(grade(identity(), cinematic(dnam))))
    return rel


def pack_imgs(fid: int, edid: str, base_body: bytes, lut: str) -> bytes:
    """An FO4 IMGS: the base imagespace's subrecords under a new EditorID, cinematic neutral, LUT `lut`."""
    neutral = {b'CNAM': struct.pack('<3f', 1.0, 1.0, 1.0), b'TNAM': struct.pack('<4f', 0.0, 1.0, 1.0, 1.0)}
    subs, placed = b'', False
    for tag, data in subrecords(base_body):
        if tag == b'EDID':
            data = edid.encode() + b'\0'
        elif tag == b'TX00':
            data, placed = lut.encode() + b'\0', True
        subs += pack_subrecord(tag.decode(), neutral.get(tag, data))
    if not placed:
        subs += pack_subrecord('TX00', lut.encode() + b'\0')
    return pack_fo4_record('IMGS', fid, 0, subs)
