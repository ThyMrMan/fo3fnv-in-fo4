"""An FNV headgear mesh (hat, glasses, mask) as a Fallout 4 worn one, skinned to the head.

FNV draws headgear as a rigid mesh in its head's frame: the race head mesh's
(characters\\head\\headhuman.nif), which an NPC's .egm then moves with the
face. Fallout 4 draws worn meshes skinned: a BSSubIndexTriShape on a stub of
skeleton nodes, its vertices in model space shifted to the HEAD bone
(vanilla BaseMaleHead.nif, Raider02MaskM.nif). The converted mesh is carried
across by the fit of FO4's base head onto FNV's mean head (face.bake.align),
one per sex, then shifted by how FO4's whole head (face and head rear)
differs from FNV's near it. A hat that hides hair is tipped back about its
front brim until its back brim is no higher than vanilla's highest (FO4
cuts the hair under a hat just below that), and every vertex is kept at
least as far outside FO4's head as it was outside FNV's. It is weighted
fully to HEAD, whose skin transform is its node
rotation transposed. Its segments are vanilla head items': an empty one,
then one with every triangle under the item's first FO4 slot.

See: docs/fork/fo4_spikes.md#spike-4-headgear
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from scipy.spatial import cKDTree

from fo4_import.face.bake import align, positions, surface, triangles
from fo4_import.face.fnv_head import head
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE, pack_tri_shape
from fo4_import.nif.convert_static import IDENTITY, NifFormat, vertices
from fo4_import.nif.elric import without_havok

#: Per sex: FO4's base head (in Fallout 4 - Meshes.ba2) and FNV's human head (under the export's meshes).
FO4_HEADS = {'male': 'meshes\\actors\\character\\characterassets\\basemalehead.nif',
             'female': 'meshes\\actors\\character\\characterassets\\basefemalehead.nif'}
FNV_HEADS = {'male': 'characters\\head\\headhuman.nif', 'female': 'characters\\head\\headfemale.nif'}
#: Per sex: FO4's head rear, the back and top of the skull its base head leaves out.
FO4_REARS = {sex: f'meshes\\actors\\character\\characterassets\\faceparts\\{sex}headrear.nif' for sex in FO4_HEADS}
#: FNV head vertices whose shifts a headgear vertex averages (inverse distance), and smoothing passes over them.
NEIGHBOURS, SMOOTH_PASSES = 8, 3
#: Vanilla's highest back brim (degrees off straight back round HEAD) among hats hiding hair: postwomanfhat.nif.
HAIR_SLOT, HAIR_LINE, BRIM_SECTOR = 30, 4.55, 15.0
#: The most a hat is tipped back (radians) and the bisection steps that find the angle.
MAX_TIP, TIP_STEPS = np.radians(20.0), 40
BONE = 'HEAD'
#: Vanilla Raider02MaskM.nif's vertex descriptor: half positions, UV, normal, tangent, skin (32 bytes).
DESC_SKINNED = 0x5B00050430208
#: Shader flags1 bit Skinned (lighting and effect shaders alike).
SHADER_SKINNED = 0x2
#: Vanilla head items' last segment's bone ID (Raider02MaskM.nif, FCaptainsHat.nif).
HEAD_BONE_ID = 0x86B72980
NO_PARENT = 0xFFFFFFFF
#: FNV biped bit (hair, headband, hat, eyeglasses, mask) -> FO4 slots; only FNV's hair bit hides hair (30).
SLOTS = {1: (30,), 9: (46,), 10: (46,), 11: (47,), 14: (48, 49)}


def slots(biped_flags: int) -> 'tuple | None':
    """The FO4 slots of FNV biped flags that are all headgear (SLOTS), sorted; None otherwise."""
    bits = [i for i in range(32) if biped_flags >> i & 1]
    if not bits or any(b not in SLOTS for b in bits):
        return None
    return tuple(sorted({slot for b in bits for slot in SLOTS[b]}))


def rigid(path: Path) -> bool:
    """Whether the FNV mesh at `path` has no skinned shape, as headgear drawn in the head's frame."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return not any(isinstance(b, NifFormat.NiGeometry) and b.skin_instance for b in data.blocks)


@dataclass
class HeadFit:
    """FO4 head coordinates x map onto FNV's head frame as s * R x + t; FO4's HEAD node, translation and
    rotation; FNV's head vertices in FO4's frame (`anchors`) and how far FO4's head surface is from each;
    points over each head's surface (FNV's in its own frame), for clearances."""
    s: float
    r: np.ndarray
    t: np.ndarray
    translation: tuple
    rotation: tuple
    anchors: np.ndarray
    offsets: np.ndarray
    fnv_surface: np.ndarray
    fo4_surface: np.ndarray

    def placed(self, points: np.ndarray) -> np.ndarray:
        """FNV head-frame `points` in FO4's frame: the fit's inverse, then the nearest anchors' offsets."""
        points = (points - self.t) @ self.r / self.s
        dist, near = cKDTree(self.anchors).query(points, k=NEIGHBOURS)
        weights = 1.0 / np.maximum(dist, 1e-6)
        return points + (self.offsets[near] * weights[:, :, None]).sum(1) / weights.sum(1)[:, None]

    def cleared(self, fnv_points: np.ndarray, points: np.ndarray) -> np.ndarray:
        """`points` moved out to their FNV originals' clearance (`fnv_points`)."""
        short = _clearance(fnv_points, self.fnv_surface) - _clearance(points, self.fo4_surface)
        out = points - self.fo4_surface.mean(0)
        return points + np.maximum(short, 0.0)[:, None] * out / np.linalg.norm(out, axis=1, keepdims=True)


def _clearance(points: np.ndarray, samples: np.ndarray) -> np.ndarray:
    """Each point's distance from the head's centre less its nearest head sample's."""
    center = samples.mean(0)
    nearest = samples[cKDTree(samples).query(points)[1]]
    return np.linalg.norm(points - center, axis=1) - np.linalg.norm(nearest - center, axis=1)


def head_fit(export_dir: Path, sex: str, archives: Archives = None) -> HeadFit:
    """The fit of FO4's base head of `sex` onto FNV's mean head, with FO4's HEAD node."""
    archives = archives or Archives(FALLOUT4_DIR / 'Data')
    nif = nif_file.read(archives.read(FO4_HEADS[sex]))
    face = next(b for kind, b in nif.blocks if kind == 'BSSubIndexTriShape')
    rear = next(b for kind, b in nif_file.read(archives.read(FO4_REARS[sex])).blocks if kind == 'BSSubIndexTriShape')
    fnv = head(export_dir / 'meshes', FNV_HEADS[sex], '', '')
    fnv_surface = surface(fnv.mean, fnv.triangles)
    s, r, t = align(positions(face), fnv.mean, fnv_surface)
    anchors = (fnv.mean - t) @ r / s
    whole = np.vstack([positions(face), positions(rear)])
    samples = surface(whole, np.vstack([triangles(face), triangles(rear) + len(positions(face))]))[0]
    offsets = samples[cKDTree(samples).query(anchors)[1]] - anchors
    _, near = cKDTree(anchors).query(anchors, k=NEIGHBOURS)
    for _ in range(SMOOTH_PASSES):
        offsets = offsets[near].mean(1)
    node = next(b for kind, b in nif.blocks if kind == 'NiNode' and nif.strings[b['name']] == BONE)
    return HeadFit(s, r, t, node['translation'], node['rotation'], anchors, offsets, fnv_surface[0], samples)


def _brim(points: np.ndarray, toward: float) -> float:
    """Lowest z within BRIM_SECTOR of direction `toward` (degrees); inf if none."""
    angle = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
    near = points[np.abs((angle - toward + 180) % 360 - 180) < BRIM_SECTOR]
    return float(near[:, 2].min()) if len(near) else np.inf


def _tip(points: np.ndarray, theta: float) -> tuple:
    """(`points` turned by `theta` about the X axis through the front brim's lowest point, the turn as a matrix)."""
    angle = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
    front = points[np.abs(angle - 90) < BRIM_SECTOR]
    pivot = front[front[:, 2].argmin()]
    c, s = np.cos(theta), np.sin(theta)
    turn = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
    return pivot + (points - pivot) @ turn, turn


def tipped(points: np.ndarray) -> tuple:
    """(a hat's FO4-frame `points` tipped back about its front brim until its back brim is no higher than
    HAIR_LINE, the turn as a matrix); unchanged when it already is, or has no front brim."""
    if _brim(points, -90) <= HAIR_LINE or _brim(points, 90) == np.inf:
        return points, np.eye(3)
    low, high = -MAX_TIP, 0.0
    for _ in range(TIP_STEPS):
        mid = (low + high) / 2
        low, high = (mid, high) if _brim(_tip(points, mid)[0], -90) <= HAIR_LINE else (low, mid)
    return _tip(points, low)


def _shape_arrays(shape: dict) -> tuple:
    """(positions, UVs, unit normals, triangles) of a converted shape's vertices."""
    pos = np.array([v['position'] for v in shape['vertices']], float)
    uv = np.array([v['uv'] for v in shape['vertices']], float)
    nrm = np.array([v['normal'] for v in shape['vertices']], float) / 127.5 - 1.0
    return pos, uv, nrm, np.array(shape['triangles'])


def _segments(n_tris: int, slot: int) -> bytes:
    """A head item's segment trailer: an empty segment, one with every triangle, shared data naming `slot`."""
    out = struct.pack('<3I', n_tris, 2, 3) + struct.pack('<4I', 0, 0, NO_PARENT, 0)
    out += struct.pack('<4I', 0, n_tris, NO_PARENT, 1) + struct.pack('<4I', 0, n_tris, 1, 0)
    out += struct.pack('<2I2I', 2, 3, 0, 1)
    out += struct.pack('<3I', 0, NO_PARENT, 0) + struct.pack('<3I', 1, NO_PARENT, 0)
    return out + struct.pack('<3I', slot, HEAD_BONE_ID, 0) + struct.pack('<H', 0)


def _bone_data(points: np.ndarray, fit: HeadFit) -> bytes:
    """BSSkin::BoneData for HEAD: the bounding sphere in bone space, the node rotation transposed."""
    rotation = np.array(fit.rotation).reshape(3, 3).T
    center = (points.min(0) + points.max(0)) / 2
    radius = float(np.linalg.norm(points - center, axis=1).max())
    return (struct.pack('<I', 1) + struct.pack('<4f', *(rotation @ center), radius)
            + struct.pack('<9f', *rotation.ravel()) + struct.pack('<4f', 0.0, 0.0, 0.0, 1.0))


def _skin(nif, index: int, head_node: int, fit: HeadFit, slot: int, placed: tuple) -> None:
    """Make shape `index` a skinned BSSubIndexTriShape on `head_node` at `placed` (FO4-frame positions,
    normals), weighted fully to it, its skin blocks appended."""
    shape = nif.blocks[index][1]
    points, normals = placed
    _, uv, _, tris = _shape_arrays(shape)
    verts = vertices(points, uv, normals / np.linalg.norm(normals, axis=1, keepdims=True), None, tris)
    for v in verts:
        v.update(weights=(1.0, 0.0, 0.0, 0.0), bones=(0, 0, 0, 0))
    center = (points.min(0) + points.max(0)) / 2
    skin = len(nif.blocks)
    shape.update(vertices=verts, vertex_desc=DESC_SKINNED, skin=skin, translation=(0.0, 0.0, 0.0),
                 rotation=IDENTITY, scale=1.0, collision=NONE,
                 bound=(*map(float, center), float(np.linalg.norm(points - center, axis=1).max())))
    nif.blocks.append(('BSSkin::Instance', struct.pack('<iiIiI', 0, skin + 1, 1, head_node, 0)))
    nif.blocks.append(('BSSkin::BoneData', _bone_data(points, fit)))
    nif.blocks[shape['shader']][1]['flags1'] |= SHADER_SKINNED
    nif.blocks[index] = ('BSSubIndexTriShape', pack_tri_shape(shape) + _segments(len(shape['triangles']), slot))


def worn(static_bytes: bytes, fit: HeadFit, slots: tuple) -> bytes:
    """A converted FNV headgear NIF (convert_static's, its collision dropped) as FO4's worn mesh in `slots`:
    placed by `fit`, tipped to the hair line when it hides hair (slot 30), kept clear of FO4's head."""
    nif = without_havok(nif_file.read(static_bytes))
    root = nif.blocks[0][1]
    shapes = [i for i in root['children'] if nif.blocks[i][0] == 'BSTriShape']
    arrays = [_shape_arrays(nif.blocks[i][1]) for i in shapes]
    fnv_points = np.vstack([a[0] for a in arrays])
    points, turn = tipped(fit.placed(fnv_points)) if HAIR_SLOT in slots else (fit.placed(fnv_points), np.eye(3))
    points = np.split(fit.cleared(fnv_points, points), np.cumsum([len(a[0]) for a in arrays])[:-1])
    nif.blocks.append(('NiNode', {'name': nif.string(BONE), 'extra': [], 'controller': NONE, 'flags': 0xE,
                                  'translation': fit.translation, 'rotation': fit.rotation, 'scale': 1.0,
                                  'collision': NONE, 'children': []}))
    head_node = len(nif.blocks) - 1
    root['children'] = [head_node] + root['children']
    for index, (_, _, nrm, _), placed in zip(shapes, arrays, points):
        _skin(nif, index, head_node, fit, slots[0], (placed, nrm @ fit.r @ turn))
    return nif_file.write(nif)
