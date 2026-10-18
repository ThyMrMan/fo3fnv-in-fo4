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

import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face.bake import align, surface
from fo4_import.face.fnv_head import FnvHead
from fo4_import.face.memo import by_content

EGT_MAGIC, EGT_HEADER = b'FREGT003', 64
TEXCONV = FALLOUT4_DIR / 'Tools' / 'Elric' / 'texconv.exe'
#: FO4's exported face diffuse format (DXT5).
FACE_FORMAT = 'BC3_UNORM'
#: Vanilla FaceCustomization textures by suffix -> (format, size), all with full mips (Fallout4.esm's 3 x 1,096).
VANILLA_FACE = {'d': ('BC1_UNORM', 1024), 'msn': ('BC1_UNORM', 1024), 's': ('BC5_UNORM', 512)}
#: Texels the new colour is carried past each UV island's edge, so filtering and compression do not bleed FO4's in.
ISLAND_PADDING = 8


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


def fnv_texture(base_path: Path, egt_path: Path, fgts: np.ndarray) -> tuple:
    """(race head texture, the NPC's colour offset at its size), both float RGB."""
    base = np.asarray(Image.open(base_path).convert('RGB'), float)
    return base, _resized(egt_offset(egt_path.read_bytes(), fgts), base.shape[:2])


def bilinear(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Bilinear samples of `image` at UVs (u right, v down, 0..1)."""
    h, w = image.shape[:2]
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1)
    y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    top = image[y0, x0] * (1 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1 - fx) + image[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def texel_points(points: np.ndarray, uv: np.ndarray, tris: np.ndarray, size: int) -> tuple:
    """(texel rows, columns, 3D points) of every texel centre inside a triangle in UV space."""
    rows, cols, where = [], [], []
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
        where.append(bary[inside] @ points[tri])
    return np.concatenate(rows), np.concatenate(cols), np.vstack(where)


#: texel_points remembered per process (memo), for the work-size texels the tint fit's steps share.
shared_texel_points = by_content(texel_points)


@by_content
def texel_map(fo4: tuple, fnv_mesh: tuple, shape: tuple) -> tuple:
    """(rows, columns, FNV UVs) of the texels of a `shape` texture inside FO4's face `fo4` = (points, uvs,
    triangles), placed on FNV's mean head `fnv_mesh` = (vertices, triangles, uvs) by bake.align; and the texels
    within ISLAND_PADDING outside the face with the face texel each copies ((rows, columns), (rows, columns)).
    The same for every NPC of one face and FNV head, so kept per process (memo)."""
    points, uv, tris = fo4
    mean, triangles, fnv_uvs = fnv_mesh
    fnv_surface = surface(mean, triangles)
    s, r, t = align(points, mean, fnv_surface)
    rows, cols, where = texel_points(points, uv, tris, shape[0])
    _, idx = cKDTree(fnv_surface[0]).query(s * where @ r.T + t)
    _, owner, bary = fnv_surface
    fnv_uv = (bary[idx][:, :, None] * fnv_uvs[triangles[owner[idx]]]).sum(1)
    filled = np.zeros(shape, bool)
    filled[rows, cols] = True
    dist, (near_r, near_c) = distance_transform_edt(~filled, return_indices=True)
    pad = (dist > 0) & (dist <= ISLAND_PADDING)
    return rows, cols, fnv_uv, (np.nonzero(pad), (near_r[pad], near_c[pad]))


def face_texture(fo4_rgba: np.ndarray, fo4: tuple, fnv: FnvHead, pieces: tuple, variant: str) -> tuple:
    """(FO4's face texture `fo4_rgba` with `variant`'s FNV colour, the skin tone scale it needs).

    The game tints the face, like the body and hairline, by the NPC's skin
    tone at runtime (the CK's face texture does not change with it), so the
    colour's overall shift goes into the tone: the texture is scaled back,
    per channel, to FO4's median over the face, and the scale returned is
    what the tone must be multiplied by. pieces = (race texture, NPC offset).
    """
    base, offset = pieces
    source = offset if variant == 'T1' else base + offset
    rows, cols, fnv_uv, (pad, near) = texel_map(fo4, (fnv.mean, fnv.triangles, fnv.uvs), fo4_rgba.shape[:2])
    out = fo4_rgba.astype(float)
    fo4_median = np.median(out[rows, cols, :3], 0)
    out[rows, cols, :3] = bilinear(source, fnv_uv) + (out[rows, cols, :3] if variant == 'T1' else 0.0)
    tone = np.median(out[rows, cols, :3], 0) / fo4_median
    out[rows, cols, :3] /= tone
    out[pad[0], pad[1], :3] = out[near[0], near[1], :3]
    return np.clip(out, 0, 255).astype(np.uint8), tone


def vanilla_face_texture(path: Path) -> bool:
    """Re-encode the CK face texture at `path` in place as vanilla's for its suffix (VANILLA_FACE: format, size,
    full mips) through texconv; False for another suffix."""
    kind = VANILLA_FACE.get(path.stem.rpartition('_')[2].lower())
    if kind is None:
        return False
    fmt, size = kind
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([str(TEXCONV), '-nologo', '-f', fmt, '-w', str(size), '-h', str(size), '-m', '0',
                        '-o', tmp, str(path)], check=True, capture_output=True, **POPEN_FLAGS)
        path.write_bytes((Path(tmp) / f'{path.stem}.dds').read_bytes())
    return True


def write_dds(rgba: np.ndarray, path: Path) -> None:
    """`rgba` as a one-level DXT5 .dds at `path`, through the CK's texconv."""
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / f'{path.stem}.png'
        Image.fromarray(rgba, 'RGBA').save(png)
        subprocess.run([str(TEXCONV), '-nologo', '-f', FACE_FORMAT, '-m', '1', '-o', tmp, str(png)],
                       check=True, capture_output=True, **POPEN_FLAGS)
        path.write_bytes((Path(tmp) / f'{path.stem}.dds').read_bytes())
