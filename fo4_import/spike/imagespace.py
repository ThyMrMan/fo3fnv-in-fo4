"""An FNV imagespace as an FO4 one: FO4's tone curve and bloom, FNV's colours in its LUT.

FNV's cinematic pass grades display colours: with Y = dot(c, FNV_LUMA),
c = lerp(Y, c, saturation), then lerp(c, Y x tint colour, tint amount). IMGS
DNAM's cinematic block flags which apply (saturation 1, tint 4). FO4
tonemaps (Hable curve), applies its own cinematic, then looks the
gamma-encoded colour up in a 16^3 LUT (TX00) and writes the result. The FO4
imagespace keeps its template's curve and bloom, its cinematic neutral, and
a LUT of FNV's saturation and tint over the identity. Exposure is pinned
(fixed_exposure): FNV does not brighten a dark room.

See: docs/fork/fo4_look.md#route-tone
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
#: Header size of an uncompressed DDS (magic and DDS_HEADER).
DDS_HEADER = 128
#: FNV's cinematic luminance weights (its shader's dot product).
FNV_LUMA = np.array([0.299, 0.587, 0.114])
SATURATION, TINT = 1, 4
#: Offset of the cinematic block in an FNV IMGS DNAM: 132-byte records lack the skin dimmer.
OLD_DNAM, OLD_CINEMATIC, CINEMATIC = 132, 96, 100
#: Where generated LUTs go, under Textures (TX00 is relative to Textures).
LUT_FOLDER = 'Effects\\LUTs\\FNV'
#: FO4's tonemap: Hable's curve of twice the exposed colour, normalised at this white, then gamma 1/2.2.
FO4_WHITE, DISPLAY_GAMMA = 11.2, 2.2
#: Samples of FO4's curve inverted by interpolation.
CURVE_SAMPLES = 20001


@dataclass
class Cinematic:
    """FNV's colour grading (saturation and tint), with unflagged parts neutral."""
    saturation: float
    tint: tuple
    tint_amount: float


def cinematic(dnam: bytes) -> Cinematic:
    """The saturation and tint of an FNV IMGS DNAM's cinematic block."""
    offset = OLD_CINEMATIC if len(dnam) == OLD_DNAM else CINEMATIC
    sat, _, _, _, r, g, b, amount, flags = struct.unpack_from('<8fI', dnam, offset)
    return Cinematic(sat if flags & SATURATION else 1.0, (r, g, b), amount if flags & TINT else 0.0)


def own_tint(dnam: bytes) -> tuple:
    """(colour, amount) of an FNV IMGS DNAM's tint, its flags aside."""
    offset = OLD_CINEMATIC if len(dnam) == OLD_DNAM else CINEMATIC
    r, g, b, amount = struct.unpack_from('<4f', dnam, offset + 16)
    return (r, g, b), amount


def grade(rgb: np.ndarray, c: Cinematic) -> np.ndarray:
    """Display colours (0..1, [..., 3]) graded as FNV's cinematic pass does, clamped."""
    y = (rgb @ FNV_LUMA)[..., None]
    out = y + c.saturation * (rgb - y)
    out = out + c.tint_amount * (y * np.asarray(c.tint) - out)
    return np.clip(out, 0.0, 1.0)


def hable(x: np.ndarray, e: float) -> np.ndarray:
    """Hable's filmic curve as FO4's shader has it; `e` is IMGS Tonemap E."""
    return (x * (0.15 * x + 0.05) + 0.2 * e) / (x * (0.15 * x + 0.5) + 0.06) - e / 0.3


def fo4_display(c: np.ndarray, e: float) -> np.ndarray:
    """The display colour FO4 shows for exposed linear colour `c`."""
    return np.clip(hable(2 * c, e) / hable(FO4_WHITE, e), 0.0, 1.0) ** (1 / DISPLAY_GAMMA)


def base_hdr(base_body: bytes) -> tuple:
    """(Tonemap E, Middle Gray) of an FO4 IMGS's HNAM."""
    hdr = struct.unpack('<9f', dict(subrecords(base_body))[b'HNAM'][:36])
    return hdr[1], hdr[8]


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


def read_lut(dds: bytes) -> np.ndarray:
    """A 24-bit LUT DDS (lut_dds's layout) as [green, blue, red, 3] in 0..1."""
    height, width = struct.unpack_from('<2I', dds, 12)
    pixels = np.frombuffer(dds, np.uint8, height * width * 3, DDS_HEADER).reshape(height, width, 3)[..., ::-1]
    return (pixels / 255.0).reshape(LUT_SIZE, LUT_SIZE, LUT_SIZE, 3)


def apply_lut(rgb: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Display colours `rgb` (0..1, [..., 3]) looked up in `lut` (read_lut) with trilinear filtering."""
    scaled = np.clip(rgb, 0, 1) * (LUT_SIZE - 1)
    low = np.minimum(scaled.astype(int), LUT_SIZE - 2)
    frac = scaled - low
    out = np.zeros(rgb.shape, dtype=float)
    for corner in np.ndindex(2, 2, 2):
        r, g, b = (low[..., i] + corner[i] for i in range(3))
        weight = np.prod([frac[..., i] if corner[i] else 1 - frac[..., i] for i in range(3)], axis=0)
        out += weight[..., None] * lut[g, b, r]
    return out


def write_lut(grading: Cinematic, edid: str, data_dir: Path) -> str:
    """Write imagespace `edid`'s LUT (FNV `grading` of the identity); its TX00 path."""
    rel = f'{LUT_FOLDER}\\{edid}.dds'
    path = data_dir / 'Textures' / rel.replace(chr(92), '/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(lut_dds(grade(identity(), grading)))
    return rel


def fixed_exposure(tonemap_e: float, middle_grey: float) -> float:
    """The exposure at which FO4's curve shows `middle_grey` as FNV does (^ 1/2.2).

    See: docs/fork/fo4_look.md#route-tone
    """
    scene = np.linspace(0.0, FO4_WHITE / 2, CURVE_SAMPLES)
    exposed = np.interp(middle_grey ** (1 / DISPLAY_GAMMA), fo4_display(scene, tonemap_e), scene)
    return float(exposed) / middle_grey


def pack_imgs(fid: int, edid: str, base_body: bytes, lut: str) -> bytes:
    """An FO4 IMGS: the base imagespace's subrecords under a new EditorID, cinematic neutral, LUT `lut`.

    Auto exposure is pinned to fixed_exposure (FNV's exposure does not follow the scene).
    See: docs/fork/fo4_look.md#route-tone
    """
    neutral = {b'CNAM': struct.pack('<3f', 1.0, 1.0, 1.0), b'TNAM': struct.pack('<4f', 0.0, 1.0, 1.0, 1.0)}
    subs, placed = b'', False
    for tag, data in subrecords(base_body):
        if tag == b'EDID':
            data = edid.encode() + b'\0'
        elif tag == b'HNAM':
            exposure = fixed_exposure(*base_hdr(base_body))
            data = data[:16] + struct.pack('<2f', exposure, exposure) + data[24:]
        elif tag == b'TX00':
            data, placed = lut.encode() + b'\0', True
        subs += pack_subrecord(tag.decode(), neutral.get(tag, data))
    if not placed:
        subs += pack_subrecord('TX00', lut.encode() + b'\0')
    return pack_fo4_record('IMGS', fid, 0, subs)
