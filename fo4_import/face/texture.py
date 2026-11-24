"""FNV's FaceGen face texture on the face texture the Creation Kit exported for an FO4 NPC.

FNV draws a face with the race's head texture plus the NPC's FaceGen colour
offset: the .egt next to the head mesh holds 50 modes, each a float scale
and signed-byte R, G, B planes (256x256, rows stored bottom-up), and the
offset is the sum of FGTS times scale times plane. It is carried onto FO4's
face texture by geometry: each FO4 face texel is a point on FO4's head (its
triangle in UV space), placed on FNV's head by bake.align, whose FNV UV
gives the FNV colour there. Variants:

- 'T1': FO4's own face texture plus the NPC's FNV colour offset;
- 'T2': FNV's face texture (race texture plus offset) in place of FO4's.

FO4's alpha is kept, and texels outside FO4's face UVs keep FO4's colour.

See: docs/fork/fo4_spikes.md#spike-2-face-texture
"""

import functools
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from fo4_import.base.dds_encode import BC1, BC3, BC5, encode
from fo4_import.face.bake import align, mean_surface, point_tree
from fo4_import.face.fnv_head import FnvHead
from fo4_import.face.memo import by_content

EGT_MAGIC, EGT_HEADER = b'FREGT003', 64
#: Vanilla FaceCustomization textures by suffix -> (DXGI format, size), all with full mips (Fallout4.esm's 3 x 1,096).
VANILLA_FACE = {'d': (BC1, 1024), 'msn': (BC1, 1024), 's': (BC5, 512)}
#: The DXGI format of a legacy four-CC DDS.
LEGACY_FORMATS = {b'DXT1': 71, b'DXT3': 74, b'DXT5': 77, b'ATI1': 80, b'BC4U': 80, b'ATI2': 83, b'BC5U': 83}
#: Texels the new colour is carried past each UV island's edge, so filtering and compression do not bleed FO4's in.
ISLAND_PADDING = 8
#: Threads texel_map's k-d tree search splits its texels over (-1: every core); the result is the same for any count.
QUERY_THREADS = -1
#: Added to FNV's colour and its stock skin before their ratio (fnv_ratios), so near-black texels can't blow it up.
RATIO_PAD = 8.0
#: Texels per_texel works on at a time: small enough to stay in cache, so pooled workers don't fight over memory.
CHUNK = 8192
#: UV layouts (mesh and texture size) texel_cover keeps per process: each sex's face and rear head (a 1024 face: 37 MB).
COVERS = 8
#: The smallest normal z an 8-bit normal map states: an edge-on or invalid texel's slopes are taken at it.
Z_FLOOR = 1 / 127.5


def egt_offset(data: bytes, fgts: np.ndarray) -> np.ndarray:
    """The FaceGen colour offset [row, column, rgb] (top row first) for FGTS coefficients `fgts`."""
    if data[:8] != EGT_MAGIC:
        raise ValueError('not a FaceGen .egt')
    width, height = struct.unpack_from('<ii', data, 8)
    n_sym = struct.unpack_from('<q', data, 16)[0]
    texels = width * height
    offset = np.zeros((3, texels))
    for i in range(min(n_sym, len(fgts))):
        pos = EGT_HEADER + i * (4 + 3 * texels)
        scale = struct.unpack_from('<f', data, pos)[0]
        offset += fgts[i] * scale * np.frombuffer(data, np.int8, 3 * texels, pos + 4).reshape(3, texels)
    return offset.reshape(3, height, width).transpose(1, 2, 0)[::-1]


def _resized(image: np.ndarray, shape: tuple) -> np.ndarray:
    """`image` (float, any range) bilinearly resized to `shape` (rows, columns)."""
    return np.stack([np.asarray(Image.fromarray(image[:, :, c].astype(np.float32)).resize(
        (shape[1], shape[0]), Image.BILINEAR)) for c in range(image.shape[2])], 2)


def rgb(path: Path, shape: tuple = None) -> np.ndarray:
    """An image as float RGB, bilinearly resized to `shape` (rows, cols) if given."""
    image = Image.open(path).convert('RGB')
    return np.asarray(image if shape is None else image.resize((shape[1], shape[0]), Image.BILINEAR), float)


def fnv_texture(base_path: Path, egt_path: Path, fgts: np.ndarray) -> tuple:
    """(race head texture, the NPC's colour offset at its size: zero for a head with no .egt), both float RGB."""
    base = rgb(base_path)
    if not egt_path.is_file():
        return base, np.zeros(base.shape)
    return base, _resized(egt_offset(egt_path.read_bytes(), fgts), base.shape[:2])


def per_texel(fn, *arrays):
    """fn(*arrays), for an fn that works row by row, run CHUNK rows at a time and joined (the same values).
    See: docs/fork/fo4_facegen_plan.md#skin-speed
    """
    parts = [fn(*(a[i:i + CHUNK] for a in arrays)) for i in range(0, max(len(arrays[0]), 1), CHUNK)]
    if isinstance(parts[0], tuple):
        return tuple(np.concatenate(p) for p in zip(*parts))
    return np.concatenate(parts)


def bilinear(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Bilinear samples of `image` at UVs (u right, v down, 0..1)."""
    return per_texel(lambda part: sampled(image, bilinear_at(image.shape[:2], part)), uv)


def bilinear_at(shape: tuple, uv: np.ndarray) -> tuple:
    """(rows above, columns left, rows below, columns right, column weights, row weights) of bilinear samples at
    UVs `uv` in an image of `shape` (rows, columns): sampled() takes them for any image of that shape."""
    h, w = shape
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1)
    y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    return y0, x0, y1, x1, (x - x0)[:, None], (y - y0)[:, None]


def sampled(image: np.ndarray, at: tuple) -> np.ndarray:
    """`image` sampled at bilinear_at()'s `at`."""
    y0, x0, y1, x1, fx, fy = at
    top = image[y0, x0] * (1 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1 - fx) + image[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def texel_points(points: np.ndarray, uv: np.ndarray, tris: np.ndarray, size: int) -> tuple:
    """(rows, columns, 3D points) of each texel centre in a UV triangle (texel_cover).
    See: docs/fork/fo4_facegen_plan.md#skin-speed
    """
    rows, cols, corners, bary = texel_cover(uv, tris, size)
    return rows, cols, per_texel(lambda b, c: np.matmul(b[:, None, :], points[c])[:, 0], bary, corners)


@functools.partial(by_content, kept=COVERS)
def texel_cover(uv: np.ndarray, tris: np.ndarray, size: int) -> tuple:
    """(texel rows, columns, corner vertices [n, 3], barycentric weights [n, 3]) of every texel centre inside a
    triangle of `tris` in UV space, in triangle order; kept per process (memo)."""
    rows, cols, vertices, weights = [], [], [], []
    for tri in tris:
        corners = uv[tri] * size - 0.5
        lo, hi = np.floor(corners.min(0)).astype(int), np.ceil(corners.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0], size - 1) + 1),
                             np.arange(max(lo[1], 0), min(hi[1], size - 1) + 1))
        p = np.stack([xs.ravel(), ys.ravel()], 1).astype(float)
        m = np.array([corners[1] - corners[0], corners[2] - corners[0]]).T
        if abs(np.linalg.det(m)) < 1e-12 or not len(p):
            continue
        b = np.linalg.solve(m, (p - corners[0]).T).T
        bary = np.column_stack([1 - b.sum(1), b])
        inside = (bary >= -1e-6).all(1)
        rows.append(ys.ravel()[inside])
        cols.append(xs.ravel()[inside])
        vertices.append(np.broadcast_to(tri, (int(inside.sum()), 3)))
        weights.append(bary[inside])
    return np.concatenate(rows), np.concatenate(cols), np.vstack(vertices), np.vstack(weights)


#: texel_points remembered per process (memo), for the work-size texels the tint fit's steps share.
shared_texel_points = by_content(texel_points)


@by_content
def texel_map(fo4: tuple, fnv_mesh: tuple, shape: tuple, frame: np.ndarray = None) -> tuple:
    """(rows, columns, FNV UVs) of the texels of a `shape` texture inside FO4's part `fo4` = (points, uvs,
    triangles), placed on FNV's mean head `fnv_mesh` = (vertices, triangles, uvs) by bake.align of the face
    points `frame` (default: the part's own); and the texels within ISLAND_PADDING outside the part with the
    part texel each copies ((rows, columns), (rows, columns)). Kept per process (memo)."""
    points, uv, tris = fo4
    rows, cols, where = shared_texel_points(points, uv, tris, shape[0])
    fnv_uv = fnv_uvs_at(where, points if frame is None else frame, fnv_mesh)
    return rows, cols, fnv_uv, padding(rows, cols, shape)


def fnv_uvs_at(where: np.ndarray, frame: np.ndarray, fnv_mesh: tuple) -> np.ndarray:
    """FNV UVs of FO4 points `where`, placed on FNV's mean head `fnv_mesh` by bake.align of the face points
    `frame`."""
    mean, triangles, fnv_uvs = fnv_mesh
    fnv_surface = mean_surface(mean, triangles)
    s, r, t = align(frame, mean, fnv_surface)
    placed = s * where @ r.T + t
    _, idx = point_tree(fnv_surface[0]).query(placed, workers=QUERY_THREADS)
    return per_texel(functools.partial(surface_uv, (mean, triangles[fnv_surface[1]], fnv_uvs)), placed, idx)


def slopes(normal: np.ndarray) -> np.ndarray:
    """Height slopes (x/z, y/z) [..., 2] of normals [..., 3], z at least Z_FLOOR."""
    return normal[..., :2] / np.maximum(normal[..., 2:], Z_FLOOR)


def tilted(slope: np.ndarray) -> np.ndarray:
    """x and y [..., 2] of the unit normal with height slopes `slope` [..., 2]."""
    return slope / np.sqrt(1.0 + (slope ** 2).sum(-1, keepdims=True))


@by_content
def fnv_turns(fo4: tuple, fnv_mesh: tuple, size: int, frame: np.ndarray = None) -> np.ndarray:
    """Per texel of texel_map(fo4, fnv_mesh, (size, size), frame), in its order: the rotation [n, 2, 2] taking a
    tangent-space normal's red and green on FNV's head to FO4's: the closest rotation to its FO4 triangle's map
    from FO4 UVs to FNV UVs, transposed; none on a folded triangle. Kept per process (memo).
    See: docs/fork/fo4_facegen_plan.md#race-relief
    """
    points, uv, tris = fo4
    at = fnv_uvs_at(points, points if frame is None else frame, fnv_mesh)
    corners = texel_cover(uv, tris, size)[2]
    edges = (uv[corners[:, 1:]] - uv[corners[:, :1]]).transpose(0, 2, 1)
    j = (at[corners[:, 1:]] - at[corners[:, :1]]).transpose(0, 2, 1) @ np.linalg.inv(edges)
    angle = np.where(np.linalg.det(j) > 0, np.arctan2(j[:, 1, 0] - j[:, 0, 1], j[:, 0, 0] + j[:, 1, 1]), 0.0)
    c, s = np.cos(angle), np.sin(angle)
    return np.stack([np.stack([c, s], 1), np.stack([-s, c], 1)], 1)


def surface_uv(mesh: tuple, placed: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """UVs of `placed` on `mesh` = (vertices, triangles, UVs) at its triangles `idx`."""
    vertices, triangles, uvs = mesh
    owner = triangles[idx]
    return (projected(placed, vertices[owner])[:, :, None] * uvs[owner]).sum(1)


def projected(points: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Barycentric weights [n, 3] of each of `points` projected onto its triangle `corners` [n, 3, 3], clamped
    inside it, so neighbouring texels sample the FNV texture continuously.
    See: docs/fork/fo4_facegen_plan.md#texel-projection
    """
    a, ab, ac = corners[:, 0], corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
    ap = points - a
    d00, d01, d11 = (ab * ab).sum(1), (ab * ac).sum(1), (ac * ac).sum(1)
    d20, d21 = (ap * ab).sum(1), (ap * ac).sum(1)
    det = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-12, 1.0, d00 * d11 - d01 * d01)
    v, w = (d11 * d20 - d01 * d21) / det, (d00 * d21 - d01 * d20) / det
    bary = np.clip(np.stack([1 - v - w, v, w], 1), 0, None)
    return bary / bary.sum(1, keepdims=True)


def island_padding(rows: np.ndarray, cols: np.ndarray, shape: tuple) -> tuple:
    """((rows, columns) within ISLAND_PADDING outside texels `rows`, `cols` of a `shape` image, (rows, columns)
    of the texel each copies)."""
    filled = np.zeros(shape, bool)
    filled[rows, cols] = True
    dist, (near_r, near_c) = distance_transform_edt(~filled, return_indices=True)
    pad = (dist > 0) & (dist <= ISLAND_PADDING)
    return np.nonzero(pad), (near_r[pad], near_c[pad])


#: island_padding remembered per process (memo): a UV layout's texels pad alike for every face.
padding = by_content(island_padding)


def fnv_ratios(pieces: tuple, fnv_uv: np.ndarray) -> tuple:
    """_ratios at FNV UVs `fnv_uv`, worked per_texel."""
    return per_texel(functools.partial(_ratios, pieces), fnv_uv)


def _ratios(pieces: tuple, fnv_uv: np.ndarray) -> tuple:
    """(FNV's colour with its FaceGen offset, and with its race skin too, each over its stock skin, all plus
    RATIO_PAD) at FNV UVs `fnv_uv`; pieces as face_colours takes them.
    See: docs/fork/fo4_look_races_plan.md#face
    """
    base, offset, skin = pieces
    at = functools.cache(lambda shape: bilinear_at(shape, fnv_uv))
    stock = sampled(base, at(base.shape[:2])) + RATIO_PAD
    shifted = np.maximum(stock + sampled(offset, at(offset.shape[:2])), 1.0)
    raced = shifted if skin is None else np.maximum(shifted + sampled(skin, at(skin.shape[:2])), 1.0)
    return shifted / stock, raced / stock


def face_colours(fo4_image: np.ndarray, fo4: tuple, fnv: FnvHead, pieces: tuple, variant: str) -> tuple:
    """(FO4's face texture `fo4_image` (RGB or RGBA, any size) as floats with `variant`'s FNV colour on its face
    texels, the skin tone scale it needs, texel_map's padding). T1 scales FO4's face by fnv_ratios, so FO4's
    features keep their hue; T2 puts FNV's colour in place. The FaceGen colour's overall shift goes into the
    tone; the race's own skin is added after (FNV draws it on the face only).
    pieces = (stock skin, FaceGen offset, race skin minus stock or None).
    See: docs/fork/fo4_facegen_plan.md#race-skin
    """
    base, offset, skin = pieces
    rows, cols, fnv_uv, edge = texel_map(fo4, (fnv.mean, fnv.triangles, fnv.uvs), fo4_image.shape[:2])
    out = fo4_image.astype(float)
    fo4_median = np.median(out[rows, cols, :3], 0)
    if variant == 'T1':
        shifted, raced = fnv_ratios(pieces, fnv_uv)
        out[rows, cols, :3] *= shifted
        tone = np.median(out[rows, cols, :3], 0) / fo4_median
        out[rows, cols, :3] *= raced / shifted
    else:
        out[rows, cols, :3] = bilinear(base + offset, fnv_uv)
        tone = np.median(out[rows, cols, :3], 0) / fo4_median
        out[rows, cols, :3] += 0 if skin is None else bilinear(skin, fnv_uv)
    out[rows, cols, :3] /= tone
    return out, tone, edge


def face_texture(fo4_rgba: np.ndarray, fo4: tuple, fnv: FnvHead, pieces: tuple, variant: str,
                 shown=1.0) -> tuple:
    """(face_colours' texture, padded past its face texels, as bytes; its tone scale). `shown`: the per-channel
    factor the game draws `fo4_rgba` at (1 for an exported FaceGen texture; more for a face set's raw diffuse,
    which the skin tone brightens), so the tone compares what is seen.
    See: docs/fork/fo4_facegen_plan.md#own-heads
    """
    scale = np.append(np.broadcast_to(np.asarray(shown, float), 3), 1.0)
    out, tone, (pad, near) = face_colours(fo4_rgba * scale, fo4, fnv, pieces, variant)
    out /= scale
    out[pad[0], pad[1], :3] = out[near[0], near[1], :3]
    return np.clip(out, 0, 255).astype(np.uint8), tone


def vanilla_dds(rgba: np.ndarray, kind: str) -> bytes:
    """`rgba` as DDS in vanilla's format and size for `kind`, full mips."""
    fmt, size = VANILLA_FACE[kind]
    return encode(rgba, fmt, (size, size))


def write_dds(rgba: np.ndarray, path: Path) -> None:
    """`rgba` as a one-level BC3 .dds at `path`."""
    path.write_bytes(encode(rgba, BC3, mips=False))


def dds_layout(dds: bytes) -> tuple:
    """(DXGI format, width, height) of DDS bytes `dds`, DX10 header or legacy four-CC."""
    four = dds[84:88]
    fmt = struct.unpack_from('<I', dds, 128)[0] if four == b'DX10' else LEGACY_FORMATS[four]
    height, width = struct.unpack_from('<II', dds, 12)
    return fmt, width, height


def dds_like(rgba: np.ndarray, like: bytes) -> bytes:
    """`rgba` as DDS bytes in DDS `like`'s format and size, full mips.
    See: docs/fork/fo4_facegen_plan.md#ck-face-texture-format
    """
    fmt, width, height = dds_layout(like)
    return encode(rgba, fmt, (width, height))


def dds_as(rgba: np.ndarray, like: bytes) -> bytes:
    """`rgba` as DDS bytes at its own size in DDS `like`'s format, full mips."""
    return encode(rgba, dds_layout(like)[0])
