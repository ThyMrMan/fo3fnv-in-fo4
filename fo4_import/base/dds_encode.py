"""RGBA images as BC1, BC3 or BC5 DDS bytes, with or without a full mip chain: the converter's own encoder.

BC1 takes each 4x4 block's endpoints on its colours' principal axis, inset, then refits them by least squares on the
indices it chose, keeping whichever fit is closer. BC3 puts a BC4 alpha block before that; BC5 is BC4 red, then
BC4 green (dds_codec.encode_bc4_channel). Each mip filters every channel apart, so colour is not weighted by alpha.

See: docs/fork/fo4_facegen_plan.md#own-dds-encoder
"""

import numpy as np
from PIL import Image

from asset_convert.texture.dds_codec import blocks_4x4, c565_to_rgb_vec, dds_header, encode_bc4_channel

BC1, BC3, BC5 = 71, 77, 83
#: Legacy four-CC of each format, as the CK's texconv wrote them.
FOURCC = {BC1: b'DXT1', BC3: b'DXT5', BC5: b'BC5U'}
#: Bytes per 4x4 block.
BLOCK_BYTES = {BC1: 8, BC3: 16, BC5: 16}
#: Endpoint 0's weight in each of BC1's four palette entries (four-colour mode: endpoint 0 above endpoint 1).
WEIGHTS = np.array([1.0, 0.0, 2 / 3, 1 / 3])
#: Power-iteration steps finding a block's principal colour axis.
AXIS_STEPS = 8
#: The palette index at each third of the way from endpoint 1 (0) to endpoint 0 (3).
STEP_CODES = np.array([1, 3, 2, 0], np.uint8)


def _axis(centred: np.ndarray) -> np.ndarray:
    """Each block's principal axis of `centred` (N, 16, 3); grey's axis for a flat block."""
    cov = np.matmul(centred.transpose(0, 2, 1), centred)
    axis = (centred.max(1) - centred.min(1) + 1e-3)[..., None]
    for _ in range(AXIS_STEPS):
        axis = np.matmul(cov, axis)
        axis /= np.maximum(np.sqrt((axis * axis).sum(1, keepdims=True)), 1e-9)
    axis = axis[..., 0]
    return np.where(np.abs(axis).sum(1, keepdims=True) > 0.5, axis, np.full(3, 3 ** -0.5))


def _to_565(rgb: np.ndarray) -> np.ndarray:
    """(N, 3) colours rounded to 5:6:5 codes."""
    q = np.clip(np.rint(rgb * np.array([31, 63, 31]) / 255), 0, np.array([31, 63, 31])).astype(np.int32)
    return (q[:, 0] << 11) | (q[:, 1] << 5) | q[:, 2]


def _codes(blocks: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> tuple:
    """(palette index per texel (N, 16), squared error per block) of `blocks` on the line from `p1` to `p0`: each
    texel takes the palette entry its projection on the line rounds to."""
    line = p0 - p1
    t = np.matmul(blocks - p1[:, None], line[..., None])[..., 0] / np.maximum((line * line).sum(1), 1e-6)[:, None]
    step = np.clip(np.rint(t * 3), 0, 3).astype(np.uint8)
    drawn = p1[:, None] + (step[..., None] / np.float32(3)) * line[:, None]
    return STEP_CODES[step], ((blocks - drawn) ** 2).sum((1, 2))


def _quantised(blocks: np.ndarray, ends: tuple) -> tuple:
    """(c0, c1, codes, error) of endpoint colours `ends`, in four-colour order (c0 above c1)."""
    c0, c1 = _to_565(ends[0]), _to_565(ends[1])
    c0, c1 = np.maximum(c0, c1), np.minimum(c0, c1)
    same = c0 == c1
    c0, c1 = np.where(same & (c0 == 0), 1, c0), np.where(same & (c0 > 0), c0 - 1, c1)
    p0, p1 = c565_to_rgb_vec(c0).astype(np.float32), c565_to_rgb_vec(c1).astype(np.float32)
    codes, error = _codes(blocks, p0, p1)
    return c0, c1, codes, error


def _refit(blocks: np.ndarray, codes: np.ndarray, ends: tuple) -> tuple:
    """The endpoints minimising the squared error of `blocks` for palette indices `codes`; `ends` where singular."""
    a = WEIGHTS[codes]
    b = 1 - a
    aa, bb, ab = (a * a).sum(1), (b * b).sum(1), (a * b).sum(1)
    ax, bx = np.matmul(a[:, None], blocks)[:, 0], np.matmul(b[:, None], blocks)[:, 0]
    det = aa * bb - ab * ab
    ok = (np.abs(det) > 1e-6)[:, None]
    det = np.where(ok[:, 0], det, 1)[:, None]
    e0 = (bb[:, None] * ax - ab[:, None] * bx) / det
    e1 = (aa[:, None] * bx - ab[:, None] * ax) / det
    return np.where(ok, np.clip(e0, 0, 255), ends[0]), np.where(ok, np.clip(e1, 0, 255), ends[1])


def bc1_blocks(rgb: np.ndarray) -> np.ndarray:
    """BC1 blocks (N, 8) uint8 of `rgb` (h, w, 3), h and w multiples of 4, in row-major block order."""
    blocks = blocks_4x4(rgb).astype(np.float32)
    mean = blocks.mean(1)
    axis = _axis(blocks - mean[:, None])
    t = np.matmul(blocks - mean[:, None], axis[..., None])[..., 0]
    lo, hi = t.min(1), t.max(1)
    inset = (hi - lo) / 16
    ends = tuple(np.clip(mean + (v - sign * inset)[:, None] * axis, 0, 255) for v, sign in ((hi, 1), (lo, -1)))
    first = _quantised(blocks, ends)
    second = _quantised(blocks, _refit(blocks, first[2], ends))
    better = second[3] < first[3]
    c0, c1, codes = (np.where(better[:, None] if x.ndim > 1 else better, y, x) for x, y in zip(first[:3], second[:3]))
    out = np.empty(len(blocks), np.dtype([('c0', '<u2'), ('c1', '<u2'), ('p', '<u4')]))
    out['c0'], out['c1'] = c0, c1
    out['p'] = (codes.astype(np.uint32) << (np.arange(16, dtype=np.uint32) * 2)).sum(1, dtype=np.uint32)
    return np.frombuffer(out.tobytes(), np.uint8).reshape(-1, 8)


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
