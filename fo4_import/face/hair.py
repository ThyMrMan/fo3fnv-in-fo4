"""FNV hair, facial hair, eyes and hair colour as FO4 head parts and a hair colour form.

FO4 head parts (HDPT: PNAM type, DATA flags, MODL, HNAM extra parts) are
chosen by comparing them with what FNV draws, in the FO4 head's space (FNV
meshes moved there by the face alignment):

- Hair and facial hair: surface samples carrying their texture's opacity
  (FO4: the material's diffuse alpha, alpha-tested; FNV: alpha-blended),
  drawn from VIEWS over the head, which hides what is behind it. The part
  whose coverage, pooled to POOL-pixel blocks, differs least overall wins.
  Facial hair is compared without its hairline extra part (a stubble decal;
  FNV carries that in its face texture).
- Eyes: the mean Lab colour of the iris ring (IRIS_RING degrees off each
  fitted eyeball's forward axis), from each game's eye mesh and texture.
- Hair colour: FNV draws hair as texture x FNV_HAIR_TINT x HCLR; FO4 reads a
  colour form's gradient row (CLFM CNAM) at the texture's grey. The nearest
  mean Lab colour wins.

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

import io
import struct
from functools import cache

import numpy as np
from PIL import Image, ImageCms
from scipy.spatial import cKDTree

from fo4_import.face.bake import positions, triangles, uvs
from fo4_import.face.fnv_head import NifFormat
from fo4_import.face.texture import texel_points
from fo4_import.nif import bgsm
from fo4_import.nif import file as nif_file
from tes5_import.base.tes5_reader import subrecords, walk

#: HDPT PNAM part types, and DATA flag bits.
EYES, HAIR, FACIAL_HAIR = 2, 3, 4
PLAYABLE, MALE, FEMALE = 1, 2, 4
#: Coverage images: pixels per side, half their extent (FO4 head units), samples per unit area, pooled block.
GRID, HALF, DENSITY, POOL = 112, 14.0, 80.0, 4
#: How far (head units) a sample may sit behind the head and still show (FNV's skull differs from FO4's).
DEPTH_SLACK = 1.0
#: Views as (image right, image up, toward the viewer): signed 1-based axes of x right, y forward, z up.
VIEWS = ((1, 3, 2), (-1, 3, -2), (2, 3, 1), (-2, 3, -1), (1, 2, 3))
#: Degrees off an eyeball's forward axis that bound its iris ring, and surface samples per eye mesh.
IRIS_RING, IRIS_SAMPLES = (12.0, 28.0), 200000
#: FNV's hair pixel shader: texture x (1 + vertex green x (2 HairTint - 1)), 2 x HairTint at full green.
FNV_HAIR_TINT = 2.0
HAIR_GRADIENT = 'textures/actors/character/hair/haircolor_lgrad_d.dds'
#: Head units a face texel takes a hovering part's (a brow's) colour from: its height plus FNV's skull offset.
FACE_REACH = 0.5
#: CLFM FNAM bits of a hair colour: playable, and CNAM is a gradient remap index.
HAIR_COLOUR_FLAGS = 0x3
SHAPES = ('BSSubIndexTriShape', 'BSTriShape')
#: Offsets in a BSTriShape-like block: after the name and extra data, from controller to the shader ref.
SHADER_REF_AFTER_EXTRAS = 4 + 4 + 12 + 36 + 4 + 4 + 16 + 4


@cache
def _lab_transform():
    """PIL's sRGB to Lab transform."""
    return ImageCms.buildTransformFromOpenProfiles(ImageCms.createProfile('sRGB'), ImageCms.createProfile('LAB'),
                                                   'RGB', 'LAB')


def lab(rgb) -> np.ndarray:
    """sRGB colours (0..255, [..., 3]) as CIE Lab [n, 3]."""
    flat = np.clip(np.asarray(rgb, float), 0, 255).astype(np.uint8).reshape(1, -1, 3)
    out = np.asarray(ImageCms.applyTransform(Image.fromarray(flat, 'RGB'), _lab_transform()))[0]
    return np.column_stack([out[:, 0] * (100 / 255), out[:, 1:].view(np.int8).astype(float)])


def image(data) -> np.ndarray:
    """A texture (bytes or path) as RGBA uint8."""
    return np.asarray(Image.open(io.BytesIO(data) if isinstance(data, bytes) else data).convert('RGBA'))


def texels(img: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """The texels of `img` at UVs `uv` (wrapped, nearest)."""
    h, w = img.shape[:2]
    return img[(uv[:, 1] * h).astype(int) % h, (uv[:, 0] * w).astype(int) % w]


def samples(points: np.ndarray, tris: np.ndarray, uv: np.ndarray, count=None) -> tuple:
    """(points, UVs) spread over the triangles: about DENSITY per unit area, or `count` uniformly by triangle."""
    rng = np.random.default_rng(0)
    if count is None:
        a, b, c = (points[tris[:, i]] for i in range(3))
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        owner = np.repeat(np.arange(len(tris)), np.maximum(1, np.ceil(area * DENSITY)).astype(int))
    else:
        owner = rng.integers(0, len(tris), count)
    w = rng.dirichlet(np.ones(3), len(owner))
    t = tris[owner]
    return np.einsum('nk,nkd->nd', w, points[t]), np.einsum('nk,nkd->nd', w, uv[t])


def _project(points: np.ndarray, view: tuple) -> tuple:
    """(rows, columns, nearness, inside) of `points` in a view's image."""
    axis = [np.sign(k) * points[:, abs(k) - 1] for k in view]
    cols = ((axis[0] + HALF) / (2 * HALF) * GRID).astype(int)
    rows = ((HALF - axis[1]) / (2 * HALF) * GRID).astype(int)
    return rows, cols, axis[2], (cols >= 0) & (cols < GRID) & (rows >= 0) & (rows < GRID)


def head_depths(head_points: np.ndarray) -> list:
    """Per view, the nearness of the head surface per pixel (-inf where there is none)."""
    out = []
    for view in VIEWS:
        rows, cols, near, ok = _project(head_points, view)
        depth = np.full((GRID, GRID), -np.inf)
        np.maximum.at(depth, (rows[ok], cols[ok]), near[ok])
        out.append(depth)
    return out


def coverage(parts: list, depths: list) -> np.ndarray:
    """[view, block row, block column] opacity of `parts` [(points, opacity)], pooled to POOL blocks."""
    out = np.zeros((len(VIEWS), GRID, GRID))
    for i, view in enumerate(VIEWS):
        for points, opacity in parts:
            rows, cols, near, ok = _project(points, view)
            ok &= near >= depths[i][np.clip(rows, 0, GRID - 1), np.clip(cols, 0, GRID - 1)] - DEPTH_SLACK
            np.maximum.at(out[i], (rows[ok], cols[ok]), opacity[ok])
    return out.reshape(len(VIEWS), GRID // POOL, POOL, GRID // POOL, POOL).mean((2, 4))


def coverage_distance(a: np.ndarray, b: np.ndarray) -> float:
    """The share of the two coverages' combined opacity that differs."""
    return float(np.abs(a - b).sum() / max(np.maximum(a, b).sum(), 1e-9))


class Fo4Assets:
    """Fallout4.esm head parts, texture sets and hair colours, and the meshes and textures they name."""

    def __init__(self, esm_bytes: bytes, archives):
        """Index `esm_bytes`' HDPT, TXST and CLFM records; read assets through `archives` (ba2.Archives)."""
        self.archives, self.parts, self.texture_sets, self.colours = archives, {}, {}, {}
        for rec, _ in walk(esm_bytes, b'HDPT', b'TXST', b'CLFM'):
            subs = {}
            for tag, data in subrecords(rec.body):
                subs.setdefault(tag, []).append(data)
            target = {b'HDPT': self.parts, b'TXST': self.texture_sets, b'CLFM': self.colours}[rec.sig]
            target[rec.form_id] = subs

    def edid(self, form_id: int) -> str:
        """A head part's EditorID."""
        return self.parts[form_id][b'EDID'][0].rstrip(b'\0').decode()

    def candidates(self, kind: int, female: bool) -> list:
        """Playable head parts of `kind` for one sex."""
        sex = FEMALE if female else MALE
        return [fid for fid, s in self.parts.items() if b'MODL' in s and s.get(b'PNAM', [b''])[0] == struct.pack(
            '<I', kind) and s[b'DATA'][0][0] & (PLAYABLE | sex) == PLAYABLE | sex]

    def extras(self, form_id: int) -> list:
        """A head part's extra parts (HNAM)."""
        return [struct.unpack('<I', h)[0] for h in self.parts[form_id].get(b'HNAM', [])]

    def model(self, form_id: int) -> str:
        """A head part's mesh path under meshes/."""
        return 'meshes/' + self.parts[form_id][b'MODL'][0].rstrip(b'\0').decode()

    def shapes(self, form_id: int) -> list:
        """[(block bytes, material)] of a head part's mesh shapes."""
        nif = nif_file.read(self.archives.read(self.model(form_id)))
        out = []
        for kind, raw in nif.blocks:
            if kind in SHAPES and isinstance(raw, bytes):
                extras = struct.unpack_from('<I', raw, 4)[0]
                shader = nif.blocks[struct.unpack_from('<i', raw, 8 + 4 * extras + SHADER_REF_AFTER_EXTRAS)[0]][1]
                name = nif.strings[shader['name'] if isinstance(shader, dict) else struct.unpack_from('<i', shader, 4)[0]]
                path = name if name.lower().startswith('materials') else 'materials/' + name
                out.append((raw, bgsm.read(self.archives.read(path))))
        return out

    def texture(self, path: str) -> np.ndarray:
        """A texture under textures/ as RGBA."""
        return image(self.archives.read('textures/' + path))


def fo4_part_samples(assets: Fo4Assets, form_id: int) -> list:
    """[(points, opacity)] of a head part's shapes: diffuse alpha, alpha-tested where its material says."""
    out = []
    for raw, material in assets.shapes(form_id):
        points, uv = samples(positions(raw), triangles(raw), uvs(raw))
        alpha = texels(assets.texture(material['textures']['diffuse']), uv)[:, 3].astype(float)
        out.append((points, (alpha >= material['alpha_test_ref']).astype(float) if material['alpha_test']
                    else alpha / 255))
    return out


def best_part(assets: Fo4Assets, kind: int, female: bool, target: np.ndarray, depths: list) -> tuple:
    """(head part FormID, coverage distance) of the playable part of `kind` drawn most like `target`."""
    scored = []
    for fid in assets.candidates(kind, female):
        parts = [fid] + (assets.extras(fid) if kind == HAIR else [])
        drawn = [s for p in parts if b'MODL' in assets.parts.get(p, {}) for s in fo4_part_samples(assets, p)]
        scored.append((coverage_distance(target, coverage(drawn, depths)), fid))
    distance, fid = min(scored)
    return fid, distance


def iris_colour(points: np.ndarray, tris: np.ndarray, uv: np.ndarray, img: np.ndarray) -> np.ndarray:
    """Mean Lab colour of the iris ring of each eyeball in a mesh (eyes split by x sign, spheres fitted)."""
    spread, spread_uv = samples(points, tris, uv, IRIS_SAMPLES)
    ring = np.cos(np.radians(IRIS_RING))
    picked = []
    for side in (points[:, 0] < 0, points[:, 0] >= 0):
        if side.sum() < 4:
            continue
        v = points[side]
        centre = np.linalg.lstsq(np.c_[2 * v, np.ones(len(v))], (v ** 2).sum(1), rcond=None)[0][:3]
        near = (spread[:, 0] < 0) == (v[0, 0] < 0)
        d = spread[near] - centre
        forward = d[:, 1] / np.linalg.norm(d, axis=1)
        picked.append(texels(img, spread_uv[near][(forward < ring[0]) & (forward > ring[1])])[:, :3])
    return lab(np.vstack(picked)).mean(0)


def best_eyes(assets: Fo4Assets, female: bool, target: np.ndarray) -> int:
    """The playable eye head part whose iris colour is nearest `target` (Lab)."""
    scored = []
    for fid in assets.candidates(EYES, female):
        texture_set = assets.texture_sets[struct.unpack('<I', assets.parts[fid][b'TNAM'][0])[0]]
        raw = next(r for r, _ in assets.shapes(fid))
        img = assets.texture(texture_set[b'TX00'][0].rstrip(b'\0').decode())
        scored.append((float(np.linalg.norm(iris_colour(positions(raw), triangles(raw), uvs(raw), img) - target)), fid))
    return min(scored)[1]


def fnv_shape(path) -> tuple:
    """(points, triangles, UVs, base texture) of an FNV head part mesh's shape (the hatless one)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    shape = next(b for b in data.blocks if isinstance(b, NifFormat.NiTriBasedGeom) and b.name != b'Hat')
    texture_set = next((b for b in data.blocks if isinstance(b, NifFormat.BSShaderTextureSet)), None)
    base = texture_set.textures[0].decode() if texture_set else ''
    return (np.array([(v.x, v.y, v.z) for v in shape.data.vertices]), np.array(shape.data.get_triangles()),
            np.array([(c.u, c.v) for c in shape.data.uv_sets[0]]), base)


def fnv_hair_rgb(texture: np.ndarray, layer: np.ndarray, hclr: tuple) -> np.ndarray:
    """RGBA (float) FNV draws a hair texture in: base and _hl layer blended by its alpha, tinted by HCLR."""
    layer = np.asarray(Image.fromarray(layer).resize(texture.shape[1::-1]), float)
    base = texture[..., :3].astype(float)
    mixed = base + (layer[..., :3] - base) * layer[..., 3:] / 255
    rgb = np.clip(mixed * FNV_HAIR_TINT * np.asarray(hclr, float) / 255, 0, 255)
    return np.concatenate([rgb, texture[..., 3:].astype(float)], -1)


def fnv_hair_colour(drawn: np.ndarray) -> np.ndarray:
    """Mean Lab colour of a drawn hair texture's mostly opaque texels."""
    return lab(drawn[..., :3][drawn[..., 3] > 127]).mean(0)


def onto_face(face: tuple, size: int, points: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """[size, size, 4] RGBA per face texel of its nearest sample within FACE_REACH (`points` on the FO4 head).

    `face` is (positions, UVs, triangles); texels with no sample in reach stay clear.
    """
    rows, cols, where = texel_points(*face, size)
    distance, nearest = cKDTree(points).query(where, distance_upper_bound=FACE_REACH)
    hit = np.isfinite(distance)
    out = np.zeros((size, size, 4))
    out[rows[hit], cols[hit]] = rgba[nearest[hit]]
    return out


def best_hair_colour(assets: Fo4Assets, diffuse: np.ndarray, material: dict, target: np.ndarray) -> int:
    """The hair colour form (CLFM) whose gradient row, read at `diffuse`'s grey, is nearest `target` (Lab)."""
    gradient = image(assets.archives.read(HAIR_GRADIENT))[..., :3]
    grey = diffuse[..., 0][diffuse[..., 3] >= material['alpha_test_ref']] * material['grayscale_scale']
    cols = np.clip((grey / 255 * (gradient.shape[1] - 1)).round().astype(int), 0, gradient.shape[1] - 1)
    scored = []
    for fid, subs in assets.colours.items():
        if b'FNAM' in subs and subs[b'FNAM'][0][0] & HAIR_COLOUR_FLAGS == HAIR_COLOUR_FLAGS:
            row = min(int(struct.unpack('<f', subs[b'CNAM'][0])[0] * gradient.shape[0]), gradient.shape[0] - 1)
            scored.append((float(np.linalg.norm(lab(gradient[row, cols]).mean(0) - target)), fid))
    return min(scored)[1]
