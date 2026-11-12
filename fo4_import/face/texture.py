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
#: texconv's names of the DXGI formats vanilla texture sets use, and the DXGI format of a legacy four-CC DDS.
DXGI_NAMES = {28: 'R8G8B8A8_UNORM', 71: 'BC1_UNORM', 74: 'BC2_UNORM', 77: 'BC3_UNORM', 80: 'BC4_UNORM',
              83: 'BC5_UNORM', 98: 'BC7_UNORM'}
LEGACY_FORMATS = {b'DXT1': 71, b'DXT3': 74, b'DXT5': 77, b'ATI1': 80, b'BC4U': 80, b'ATI2': 83, b'BC5U': 83}
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
def texel_map(fo4: tuple, fnv_mesh: tuple, shape: tuple, frame: np.ndarray = None) -> tuple:
    """(rows, columns, FNV UVs) of the texels of a `shape` texture inside FO4's part `fo4` = (points, uvs,
    triangles), placed on FNV's mean head `fnv_mesh` = (vertices, triangles, uvs) by bake.align of the face
    points `frame` (default: the part's own); and the texels within ISLAND_PADDING outside the part with the
    part texel each copies ((rows, columns), (rows, columns)). Kept per process (memo)."""
    points, uv, tris = fo4
    mean, triangles, fnv_uvs = fnv_mesh
    fnv_surface = surface(mean, triangles)
    s, r, t = align(points if frame is None else frame, mean, fnv_surface)
    rows, cols, where = texel_points(points, uv, tris, shape[0])
    _, idx = cKDTree(fnv_surface[0]).query(s * where @ r.T + t)
    _, owner, bary = fnv_surface
    fnv_uv = (bary[idx][:, :, None] * fnv_uvs[triangles[owner[idx]]]).sum(1)
    return rows, cols, fnv_uv, island_padding(rows, cols, shape)


def island_padding(rows: np.ndarray, cols: np.ndarray, shape: tuple) -> tuple:
    """((rows, columns) within ISLAND_PADDING outside texels `rows`, `cols` of a `shape` image, (rows, columns)
    of the texel each copies)."""
    filled = np.zeros(shape, bool)
    filled[rows, cols] = True
    dist, (near_r, near_c) = distance_transform_edt(~filled, return_indices=True)
    pad = (dist > 0) & (dist <= ISLAND_PADDING)
    return np.nonzero(pad), (near_r[pad], near_c[pad])


def face_colours(fo4_image: np.ndarray, fo4: tuple, fnv: FnvHead, pieces: tuple, variant: str) -> tuple:
    """(FO4's face texture `fo4_image` (RGB or RGBA, any size) as floats with `variant`'s FNV colour on its face
    texels, the skin tone scale it needs, texel_map's padding).

    The game tints face and body by the skin tone, so the FaceGen colour's
    overall shift goes into it: the texture is scaled back per channel to
    FO4's median over the face. Both add the race's own skin after (FNV
    draws it on the face only).
    pieces = (stock skin, FaceGen offset, race skin minus stock or None).
    See: docs/fork/fo4_facegen_plan.md#race-skin
    """
    base, offset, skin = pieces
    rows, cols, fnv_uv, edge = texel_map(fo4, (fnv.mean, fnv.triangles, fnv.uvs), fo4_image.shape[:2])
    out = fo4_image.astype(float)
    fo4_median = np.median(out[rows, cols, :3], 0)
    whole = None if variant == 'T1' else base + offset
    out[rows, cols, :3] = bilinear(offset, fnv_uv) + out[rows, cols, :3] if whole is None else bilinear(whole, fnv_uv)
    tone = np.median(out[rows, cols, :3], 0) / fo4_median
    if skin is not None:
        out[rows, cols, :3] += bilinear(skin, fnv_uv)
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


def _texconv(rgba: np.ndarray, *options: str) -> bytes:
    """`rgba` as DDS bytes, through the CK's texconv with `options`."""
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / 'texture.png'
        Image.fromarray(rgba, 'RGBA').save(png)
        subprocess.run([str(TEXCONV), '-nologo', *options, '-o', tmp, str(png)], check=True, capture_output=True,
                       **POPEN_FLAGS)
        return (Path(tmp) / 'texture.dds').read_bytes()


def write_dds(rgba: np.ndarray, path: Path) -> None:
    """`rgba` as a one-level DXT5 .dds at `path`, through the CK's texconv."""
    path.write_bytes(_texconv(rgba, '-f', FACE_FORMAT, '-m', '1'))


def dds_layout(dds: bytes) -> tuple:
    """(texconv format name, width, height) of DDS bytes `dds`, DX10 header or DXT1/DXT5 four-CC."""
    four = dds[84:88]
    fmt = struct.unpack_from('<I', dds, 128)[0] if four == b'DX10' else LEGACY_FORMATS[four]
    height, width = struct.unpack_from('<II', dds, 12)
    return DXGI_NAMES[fmt], width, height


def dds_like(rgba: np.ndarray, like: bytes) -> bytes:
    """`rgba` as DDS bytes in DDS `like`'s format and size, full mips.
    See: docs/fork/fo4_facegen_plan.md#ck-face-texture-format
    """
    fmt, width, height = dds_layout(like)
    return _texconv(rgba, '-f', fmt, '-w', str(width), '-h', str(height), '-m', '0')


def dds_as(rgba: np.ndarray, like: bytes) -> bytes:
    """`rgba` as DDS bytes at its own size in DDS `like`'s format, full mips."""
    return _texconv(rgba, '-f', dds_layout(like)[0], '-m', '0')
