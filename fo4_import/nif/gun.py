"""An FNV gun mesh on a Fallout 4 receiver's skeleton, so FO4's gun animations move its parts.

FO4 builds a gun from parts; the receiver mesh (`TGunReceiver.nif`,
`PipeRifleBoltAction.nif`, `10MMPistol.nif`) is the root `WEAPON` with the
bones the animations move (WeaponBolt, WeaponMagazine, WeaponTrigger,
WeaponExtra1..3, their *Trans twins, optics, the left-hand IK target), the
receiver's geometry under its own node with `ProjectileNode` (the muzzle),
and the receiver's collision. The FNV gun replaces that geometry: its
parts named for a moving piece (`##Clip`, `##Trigger`, `##Lever`...) hang
from the matching bone, the rest from the receiver's node. FNV's guns lie
along +X with +Y up, FO4's along +Y with +Z up; the FNV gun is turned to
FO4's axes and moved so its trigger sits on the receiver's (the right hand
grips both), and the muzzle node moves to FNV's `ProjectileNode`. The
receiver's own shapes keep their blocks (names, shaders, the controllers
and sequences that drive them) and lose only their geometry; its
collision stays.

See: docs/fork/fo4_spikes.md#spike-4-guns
"""

import copy
import struct
from pathlib import Path

import numpy as np

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY, NifFormat, vertices
from fo4_import.nif.elric import without_havok

#: FO4 = FNV @ AXES: FNV's length (+X) is FO4's +Y, FNV's up (+Y) FO4's +Z, FNV's +Z FO4's +X.
AXES = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
#: How an FNV part's name ends (# and :N dropped) -> the FO4 receiver bone it moves with (first match wins).
PART_BONES = (('trigger', 'WeaponTrigger'), ('clip', 'WeaponMagazine'), ('magazine', 'WeaponMagazine'),
              ('bolt', 'WeaponBolt'), ('slide', 'WeaponBolt'), ('lever', 'WeaponBolt'), ('bar', 'WeaponBolt'),
              ('hammer', 'WeaponExtra2'))
TRIGGER_BONE, MUZZLE, MAGAZINE_BONE = 'WeaponTrigger', 'ProjectileNode', 'WeaponMagazine'
#: Parent connect points (BSConnectPoint::Parents) a magazine and sights attach at.
MAG_POINT, SCOPE_POINT = 'P-Mag', 'P-Scope'
#: FNV's aiming eye point on a gun.
SIGHTING = '##SightingNode'


def _matrix(block: dict) -> np.ndarray:
    """A node's local transform as a 4x4 row-vector matrix (v @ M), NiMatrix3 rows transposed."""
    m = np.eye(4)
    m[:3, :3] = np.array(block['rotation']).reshape(3, 3).T * block['scale']
    m[3, :3] = block['translation']
    return m


def _worlds(nif) -> dict:
    """{block index: world matrix} of every node reachable from the root."""
    out, stack = {}, [(0, np.eye(4))]
    while stack:
        index, parent = stack.pop()
        kind, block = nif.blocks[index]
        if not isinstance(block, dict) or 'translation' not in block:
            continue
        out[index] = _matrix(block) @ parent
        stack += [(c, out[index]) for c in block.get('children', []) if c >= 0]
    return out


def _named(nif, name: str) -> 'int | None':
    """The index of the node called `name`, or None."""
    return next((i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'
                 and nif.strings[b['name']] == name), None)


def _bone_for(part: str, bones: 'dict | None' = None) -> 'str | None':
    """The bone an FNV part moves with (one in `bones`, when given)."""
    stem = part.split(':')[0].strip('#').lower()
    return next((bone for word, bone in PART_BONES if stem.endswith(word) and (bones is None or bone in bones)),
                None)


def fnv_nodes(path: Path) -> dict:
    """{node name: world position} of an FNV gun's nodes (ProjectileNode, ##SightingNode...)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    root = data.roots[0]
    return {n.name.decode('cp1252'): np.array(n.get_transform(root).as_list())[3, :3]
            for n in root.tree() if isinstance(n, NifFormat.NiNode)}


def _trigger_top(points: np.ndarray) -> np.ndarray:
    """A part's top middle: a trigger's pivot, a magazine's mouth."""
    lo, hi = points.min(0), points.max(0)
    return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2]])


def _receiver_trigger(nif, worlds: dict) -> 'np.ndarray | None':
    """The receiver trigger's pivot in receiver space: its shapes' top, else the bone itself."""
    bone = _named(nif, TRIGGER_BONE)
    if bone is None:
        return None
    shapes = [c for c in nif.blocks[bone][1]['children'] if nif.blocks[c][0] == 'BSTriShape']
    points = [_moved(np.array([v['position'] for v in nif.blocks[c][1]['vertices']], float),
                     _matrix(nif.blocks[c][1]) @ worlds[bone]) for c in shapes]
    return _trigger_top(np.vstack(points)) if points else worlds[bone][3, :3]


def connect_points(nif, worlds: dict) -> dict:
    """{parent connect point name: receiver-space position} of a NIF's BSConnectPoint::Parents."""
    out = {}
    for kind, raw in nif.blocks:
        if kind != 'BSConnectPoint::Parents':
            continue
        at, count = 8, struct.unpack_from('<I', raw, 4)[0]
        for _ in range(count):
            names = []
            for _ in range(2):
                n = struct.unpack_from('<I', raw, at)[0]
                names.append(raw[at + 4:at + 4 + n].decode('cp1252'))
                at += 4 + n
            translation = np.array(struct.unpack_from('<3f', raw, at + 16))
            at += 32
            parent = _named(nif, names[0])
            out[names[1]] = _moved(translation[None], worlds[parent])[0] if parent in worlds else translation
    return out


def _top(nif, worlds: dict) -> float:
    """The highest vertex of the placed shapes, in receiver space (0 with none)."""
    points = [_moved(np.array([v['position'] for v in b['vertices']], float), worlds[i])
              for i, (kind, b) in enumerate(nif.blocks) if kind == 'BSTriShape' and i in worlds and b['vertices']]
    return float(np.vstack(points)[:, 2].max()) if points else 0.0


def mesh_top(raw: bytes) -> float:
    """The highest point of a NIF's placed shapes."""
    nif = nif_file.read(raw)
    return _top(nif, _worlds(nif))


def receiver_layout(raw: bytes) -> dict:
    """A FO4 receiver NIF's trigger, magazine mouth, muzzle and sights point, and its top (z), receiver space."""
    nif = nif_file.read(raw)
    worlds = _worlds(nif)
    points = connect_points(nif, worlds)
    node = {name: worlds[i][3, :3] for name in (MAGAZINE_BONE, MUZZLE) if (i := _named(nif, name)) in worlds}
    return {'trigger': _receiver_trigger(nif, worlds), 'mag': points.get(MAG_POINT, node.get(MAGAZINE_BONE)),
            'muzzle': node.get(MUZZLE), 'scope': points.get(SCOPE_POINT),
            'top': _top(nif, worlds)}


def _fnv_parts(src) -> dict:
    """{shape index: (part name, vertices in FO4's axes)} of an FNV gun."""
    return {i: (src.strings[src.blocks[i][1]['name']],
                np.array([v['position'] for v in src.blocks[i][1]['vertices']], float) @ AXES)
            for i in src.blocks[0][1]['children'] if src.blocks[i][0] == 'BSTriShape'}


def fnv_layout(static_bytes: bytes, nodes: dict) -> dict:
    """A converted FNV gun's trigger, magazine mouth, muzzle and sighting eye point (None when it has none)
    and top, FO4's axes."""
    parts = _fnv_parts(nif_file.read(static_bytes)).values()
    moving = {bone: [p for name, p in parts if _bone_for(name) == bone] for bone in (TRIGGER_BONE, MAGAZINE_BONE)}
    every = np.vstack([p for _, p in parts])
    return {'trigger': _trigger_top(np.vstack(moving[TRIGGER_BONE])) if moving[TRIGGER_BONE] else None,
            'mag': _trigger_top(np.vstack(moving[MAGAZINE_BONE])) if moving[MAGAZINE_BONE] else None,
            'muzzle': nodes[MUZZLE] @ AXES if MUZZLE in nodes else None,
            'sight': nodes[SIGHTING] @ AXES if SIGHTING in nodes else None, 'top': float(every[:, 2].max())}


def _moved(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """`points` through a 4x4 row-vector transform."""
    return (np.c_[points, np.ones(len(points))] @ matrix)[:, :3]


def _copy_block(dst, src, index: int) -> int:
    """Append a copy of `src`'s block `index` (a shader, its texture set, an alpha) to `dst`; its index."""
    kind, block = copy.deepcopy(src.blocks[index])
    for field in ('name', 'root_material'):
        if isinstance(block, dict) and block.get(field, NONE) >= 0:
            text = src.strings[block[field]]
            block[field] = dst.string(text) if text else dst.empty_string()
    if isinstance(block, dict) and block.get('texture_set', NONE) >= 0:
        block['texture_set'] = _copy_block(dst, src, block['texture_set'])
    dst.blocks.append((kind, block))
    return len(dst.blocks) - 1


def _merge_shape(dst, src, index: int, points: np.ndarray, normals: np.ndarray) -> int:
    """Copy `src`'s shape `index` (shader, texture set, alpha) into `dst`, its vertices at `points`; its index."""
    shape = copy.deepcopy(src.blocks[index][1])
    tris = np.array(shape['triangles'])
    uv = np.array([v['uv'] for v in shape['vertices']], float)
    colors = (np.array([v['color'] for v in shape['vertices']], float) / 255
              if 'color' in shape['vertices'][0] else None)
    unit = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    center = (points.min(0) + points.max(0)) / 2
    shape.update(name=dst.string(src.strings[shape['name']]), vertices=vertices(points, uv, unit, colors, tris),
                 translation=(0.0, 0.0, 0.0), rotation=IDENTITY, scale=1.0, collision=NONE, extra=[],
                 bound=(*map(float, center), float(np.linalg.norm(points - center, axis=1).max())))
    for key in ('shader', 'alpha_property'):
        if shape[key] >= 0:
            shape[key] = _copy_block(dst, src, shape[key])
    dst.blocks.append(('BSTriShape', shape))
    return len(dst.blocks) - 1


def _emptied(nif) -> None:
    """Empty every receiver shape's geometry, keeping the block its shader and controllers hang on."""
    for kind, block in nif.blocks:
        if kind == 'BSTriShape':
            block.update(vertices=[], triangles=[], bound=(0.0, 0.0, 0.0, 0.0))
            block.pop('counts', None)


def gun(static_bytes: bytes, nodes: dict, receiver_bytes: bytes) -> bytes:
    """The FO4 weapon NIF of a converted FNV gun (convert_static's, `nodes` its FNV node positions) on the
    receiver NIF `receiver_bytes`."""
    src = without_havok(nif_file.read(static_bytes))
    nif = nif_file.read(receiver_bytes)
    worlds = _worlds(nif)
    muzzle = _named(nif, MUZZLE)
    body = next((i for i, (_, b) in enumerate(nif.blocks)
                 if isinstance(b, dict) and muzzle in b.get('children', [])), 0)
    bones = {nif.strings[b['name']]: i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'}
    target = _receiver_trigger(nif, worlds)
    _emptied(nif)
    named = _fnv_parts(src)
    parts, names = {i: p for i, (_, p) in named.items()}, {i: n for i, (n, _) in named.items()}
    triggers = [p for i, p in parts.items() if _bone_for(names[i], bones) == TRIGGER_BONE]
    offset = target - _trigger_top(np.vstack(triggers)) if triggers and target is not None else np.zeros(3)
    for i, points in parts.items():
        bone = _bone_for(names[i], bones)
        parent = bones[bone] if bone else body
        inverse = np.linalg.inv(worlds[parent])
        normals = (np.array([v['normal'] for v in src.blocks[i][1]['vertices']], float) / 127.5 - 1.0) @ AXES
        merged = _merge_shape(nif, src, i, _moved(points + offset, inverse), normals @ inverse[:3, :3])
        nif.blocks[parent][1]['children'].append(merged)
    if muzzle is not None and MUZZLE in nodes:
        local = _moved((nodes[MUZZLE] @ AXES + offset)[None], np.linalg.inv(worlds[body]))[0]
        nif.blocks[muzzle][1]['translation'] = tuple(map(float, local))
    return nif_file.write(nif)
