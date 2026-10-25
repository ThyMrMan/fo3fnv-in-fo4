"""A Fallout 4 NIF as parts to draw: each shape's vertices in the model's space and what its shader names.

Shapes are BSTriShape and the types that start with its fields (BSSubIndexTriShape, BSMeshLODTriShape); a
skinned shape shows in its bind pose. Each node's transform is composed down the tree (rotations act on column
vectors, as fo4_import.nif.outfit.fo4_joints composes them). BSDynamicTriShape (heads) and particles carry no
vertices here and are left out.

See: docs/fork/fo4_gui.md#preview
"""

from dataclasses import dataclass, field

import numpy as np

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import Reader, read_tri_shape

#: Shape types whose block starts with BSTriShape's fields.
SHAPES = ('BSTriShape', 'BSSubIndexTriShape', 'BSMeshLODTriShape')
#: NiAlphaProperty flags: blending on, alpha testing on.
ALPHA_BLEND, ALPHA_TEST = 0x1, 0x200


@dataclass
class Part:
    """One shape: float32 positions, normals, UVs, uint32 triangles; its material file, texture set, alpha."""
    name: str
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    triangles: np.ndarray
    material: str = ''
    textures: list = field(default_factory=list)
    effect: bool = False
    blend: bool = False
    alpha_test: int = -1


def load(data: bytes) -> list:
    """The drawable Parts of a Fallout 4 NIF's bytes."""
    return parts_of(nif_file.read(data))


def parts_of(nif) -> list:
    """The drawable Parts of a read NIF (fo4_import.nif.file.NifFile)."""
    parts = []
    for root in nif.roots:
        _walk(nif, root, np.eye(3), np.zeros(3), parts)
    return parts


def bounds(parts: list) -> tuple:
    """(center, radius) of every part's positions; ((0, 0, 0), 1) for none."""
    if not parts:
        return np.zeros(3), 1.0
    points = np.concatenate([p.positions for p in parts])
    low, high = points.min(axis=0), points.max(axis=0)
    return (low + high) / 2, max(float(np.linalg.norm(high - low)) / 2, 1e-3)


def _walk(nif, index: int, rot: np.ndarray, pos: np.ndarray, parts: list) -> None:
    """Add the parts under block `index`, whose parent's world transform is (`rot`, `pos`)."""
    if index < 0 or index >= len(nif.blocks):
        return
    kind, block = nif.blocks[index]
    if kind in SHAPES:
        block = block if isinstance(block, dict) else read_tri_shape(Reader(block))
    if not isinstance(block, dict) or 'rotation' not in block:
        return
    own = np.array(block['rotation'], float).reshape(3, 3) * block['scale']
    rot, pos = rot @ own, rot @ np.array(block['translation'], float) + pos
    if kind in SHAPES and block['vertices'] and not block['flags'] & 1:
        parts.append(_part(nif, block, rot, pos))
    for child in block.get('children', ()):
        _walk(nif, child, rot, pos, parts)


def _part(nif, shape: dict, rot: np.ndarray, pos: np.ndarray) -> Part:
    """A Part of BSTriShape `shape` placed by world transform (`rot`, `pos`)."""
    verts = shape['vertices']
    points = np.array([v['position'] for v in verts], float) @ rot.T + pos
    uvs = np.array([v.get('uv', (0.0, 0.0)) for v in verts], float)
    tris = np.array(shape['triangles'], np.uint32).reshape(-1, 3)
    normals = (np.array([v['normal'] for v in verts], float) / 127.5 - 1.0) @ rot.T if 'normal' in verts[0] \
        else face_normals(points, tris)
    part = Part(_name(nif, shape.get('name', -1)), points.astype(np.float32), _unit(normals).astype(np.float32),
                uvs.astype(np.float32), tris)
    _shader(nif, shape, part)
    return part


def _shader(nif, shape: dict, part: Part) -> None:
    """Fill `part`'s material file, texture set and alpha from `shape`'s shader and alpha property blocks."""
    kind, shader = nif.blocks[shape['shader']] if 0 <= shape['shader'] < len(nif.blocks) else ('', None)
    if isinstance(shader, dict):
        part.material = _name(nif, shader.get('name', -1))
        part.effect = kind == 'BSEffectShaderProperty'
        if part.effect:
            part.textures = [shader['source_texture'], shader['normal']]
        elif 0 <= shader.get('texture_set', -1) < len(nif.blocks):
            part.textures = list(nif.blocks[shader['texture_set']][1].get('textures', ()))
    _, alpha = nif.blocks[shape['alpha_property']] if 0 <= shape['alpha_property'] < len(nif.blocks) else ('', None)
    if isinstance(alpha, dict):
        part.blend = bool(alpha['alpha_flags'] & ALPHA_BLEND)
        part.alpha_test = alpha['threshold'] if alpha['alpha_flags'] & ALPHA_TEST else -1


def face_normals(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Per-vertex normals summed from the faces around each vertex (a shape that stores none)."""
    normals = np.zeros_like(points)
    face = np.cross(points[tris[:, 1]] - points[tris[:, 0]], points[tris[:, 2]] - points[tris[:, 0]])
    for k in range(3):
        np.add.at(normals, tris[:, k], face)
    return normals


def _unit(vectors: np.ndarray) -> np.ndarray:
    """`vectors` scaled to length 1 (zero ones kept)."""
    length = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(length > 0, length, 1.0)


def _name(nif, index: int) -> str:
    """The header string at `index`, or ''."""
    return nif.strings[index] if 0 <= index < len(nif.strings) else ''
