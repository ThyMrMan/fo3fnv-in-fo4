"""RGBA images as BC1, BC3 or BC5 DDS bytes, with or without a full mip chain: the converter's own encoder.

BC1 takes each 4x4 block's endpoints on its colours' principal axis, inset, then refits them by least squares on the
indices it chose, keeping whichever fit is closer: native/src/bc1 (f3_bc1), built by tools.generators.gen_native_c.
BC3 puts a BC4 alpha block before that; BC5 is BC4 red, then BC4 green (dds_codec.encode_bc4_channel). Each mip
filters every channel apart, so colour is not weighted by alpha.

See: docs/fork/fo4_facegen_plan.md#own-dds-encoder
"""

import ctypes
import functools
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.texture.dds_codec import dds_header, encode_bc4_channel

BC1, BC3, BC5 = 71, 77, 83
#: Legacy four-CC of each format, as the CK's texconv wrote them.
FOURCC = {BC1: b'DXT1', BC3: b'DXT5', BC5: b'BC5U'}
#: Bytes per 4x4 block.
BLOCK_BYTES = {BC1: 8, BC3: 16, BC5: 16}
#: The BC1 encoder library (native/src/bc1); its version, bumped with every change to its output.
LIBRARY = Path(__file__).resolve().parents[2] / 'native' / 'dist' / {
    'win32': 'f3_bc1.dll', 'darwin': 'libf3_bc1.dylib'}.get(sys.platform, 'libf3_bc1.so')
BC1_VERSION = 1


@functools.cache
def library() -> ctypes.CDLL:
    """The BC1 encoder library, loaded once; RuntimeError when it is not built or is not BC1_VERSION."""
    build = 'build it with python -m tools.generators.gen_native_c f3_bc1'
    if not LIBRARY.is_file():
        raise RuntimeError(f'{LIBRARY} is missing: {build}')
    lib = ctypes.CDLL(str(LIBRARY))
    lib.f3_bc1_blocks.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p)
    lib.f3_bc1_blocks.restype = None
    if lib.f3_bc1_version() != BC1_VERSION:
        raise RuntimeError(f'{LIBRARY} is version {lib.f3_bc1_version()}, not {BC1_VERSION}: {build}')
    return lib


def bc1_blocks(rgb: np.ndarray) -> np.ndarray:
    """BC1 blocks (N, 8) uint8 of `rgb` (h, w, 3), h and w multiples of 4, in row-major block order."""
    height, width = rgb.shape[:2]
    out = ctypes.create_string_buffer(height * width // 2)
    library().f3_bc1_blocks(np.ascontiguousarray(rgb, np.uint8).tobytes(), height, width, out)
    return np.frombuffer(out.raw, np.uint8).reshape(-1, 8)


def _level(rgba: np.ndarray, fmt: int) -> bytes:
    """One mip of `rgba` (h, w, 4) in `fmt`, padded to whole blocks with its edge texels."""
    h, w = rgba.shape[:2]
    padded = np.pad(rgba, ((0, -h % 4), (0, -w % 4), (0, 0)), mode='edge')
    if fmt == BC5:
        red, green = encode_bc4_channel(padded[..., 0]), encode_bc4_channel(padded[..., 1])
        return np.concatenate([red, green], 1).tobytes()
    colour = bc1_blocks(padded[..., :3])
    return (colour if fmt == BC1 else np.concatenate([encode_bc4_channel(padded[..., 3]), colour], 1)).tobytes()


def resized(rgba: np.ndarray, size: tuple) -> np.ndarray:
    """`rgba` at `size` (width, height), each channel filtered apart: a box filter shrinking, bilinear growing."""
    if (rgba.shape[1], rgba.shape[0]) == tuple(size):
        return rgba
    filt = Image.BOX if size[0] <= rgba.shape[1] and size[1] <= rgba.shape[0] else Image.BILINEAR
    channels = [np.asarray(Image.fromarray(np.ascontiguousarray(rgba[..., c])).resize(size, filt)) for c in range(4)]
    return np.stack(channels, 2)


def encode(rgba: np.ndarray, fmt: int, size: tuple = None, mips: bool = True) -> bytes:
    """`rgba` (h, w, 4 uint8) as DDS bytes in `fmt` (BC1, BC3 or BC5) at `size` (width, height; its own by default),
    with a full mip chain or the top level only."""
    if fmt not in FOURCC:
        raise ValueError(f'no encoder for DXGI format {fmt}')
    level = resized(np.asarray(rgba, np.uint8), size or (rgba.shape[1], rgba.shape[0]))
    height, width = level.shape[:2]
    data = [_level(level, fmt)]
    while mips and level.shape[:2] != (1, 1):
        level = resized(level, (max(1, level.shape[1] // 2), max(1, level.shape[0] // 2)))
        data.append(_level(level, fmt))
    return dds_header(height, len(data[0]), FOURCC[fmt], len(data), width) + b''.join(data)
