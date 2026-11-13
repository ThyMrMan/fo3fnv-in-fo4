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
import functools
import struct
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from fo4_import.nif import file as nif_file
from fo4_import.nif import fnv_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY, NifFormat, vertices
from fo4_import.nif.elric import without_havok

#: FO4 = FNV @ AXES: FNV's length (+X) is FO4's +Y, FNV's up (+Y) FO4's +Z, FNV's +Z FO4's +X.
AXES = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
#: After AXES, a gun FNV builds along its +Y (launchers) has its muzzle up (+Z) or down: these turn it ahead (+Y).
TIP = {1: np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]),
       -1: np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])}
#: The quarter-turn rolls about FO4's +Y (the barrel) a tipped launcher is fitted to its receiver's shape at.
ROLLS = tuple(np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]]) for c, s in ((1, 0), (0, 1), (-1, 0), (0, -1)))
#: How an FNV part's name ends (# and :N dropped) -> the FO4 receiver bone it moves with (first match wins).
PART_BONES = (('trigger', 'WeaponTrigger'), ('clip', 'WeaponMagazine'), ('magazine', 'WeaponMagazine'),
              ('bolt', 'WeaponBolt'), ('slide', 'WeaponBolt'), ('lever', 'WeaponBolt'), ('bar', 'WeaponBolt'),
              ('hammer', 'WeaponExtra2'))
TRIGGER_BONE, MUZZLE, MAGAZINE_BONE = 'WeaponTrigger', 'ProjectileNode', 'WeaponMagazine'
#: The FNV gun node a Hide Backpack gun wears on the character's back.
BACKPACK = 'Backpack'
#: Parent connect points (BSConnectPoint::Parents) a magazine and sights attach at.
MAG_POINT, SCOPE_POINT = 'P-Mag', 'P-Scope'
#: FNV's aiming eye point on a gun.
SIGHTING = '##SightingNode'
#: How many NIFs parsed() and stripped() each keep: a gun's converted mesh, its receiver and its build, and spares.
KEPT_PARSES = 8


@functools.lru_cache(maxsize=KEPT_PARSES)
def parsed(raw: bytes):
    """nif_file.read(`raw`), shared by the readers here: never change it.
    See: docs/fork/fo4_build_speed.md#gun-parses
    """
    return nif_file.read(raw)


@functools.lru_cache(maxsize=KEPT_PARSES)
def stripped(raw: bytes):
    """without_havok() of a fresh read of `raw`, shared like parsed()."""
    return without_havok(nif_file.read(raw))


def node_matrix(block: dict) -> np.ndarray:
    """A node's local transform as a 4x4 row-vector matrix (v @ M), NiMatrix3 rows transposed."""
    m = np.eye(4)
    m[:3, :3] = np.array(block['rotation']).reshape(3, 3).T * block['scale']
    m[3, :3] = block['translation']
    return m


def node_worlds(nif) -> dict:
    """{block index: world matrix} of every node reachable from the root, the root's own transform left out (the
    game puts a weapon's root on its attach bone as is).
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    out, stack = {}, [(0, np.eye(4))]
    while stack:
        index, parent = stack.pop()
        kind, block = nif.blocks[index]
        if not isinstance(block, dict) or 'translation' not in block:
            continue
        out[index] = (node_matrix(block) if index else np.eye(4)) @ parent
        stack += [(c, out[index]) for c in block.get('children', []) if c >= 0]
    return out


def without(raw: bytes, part: str) -> bytes:
    """Converted FNV gun `raw` without FNV part `part`'s shapes (named `part`:N under the root)."""
    nif = nif_file.read(raw)
    root = nif.blocks[0][1]
    root['children'] = [c for c in root['children']
                        if nif.blocks[c][0] != 'BSTriShape' or nif.strings[nif.blocks[c][1]['name']].split(':')[0] != part]
    return nif_file.write(nif)


def _named(nif, name: str) -> 'int | None':
    """The index of the node called `name`, or None."""
    return next((i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'
                 and nif.strings[b['name']] == name), None)


def bone_for(part: str, bones: 'dict | None' = None) -> 'str | None':
    """The bone an FNV part moves with (one in `bones`, when given)."""
    stem = part.split(':')[0].strip('#').lower()
    return next((bone for word, bone in PART_BONES if stem.endswith(word) and (bones is None or bone in bones)),
                None)


def fnv_nodes(path: Path) -> dict:
    """{node name: world position} of an FNV gun's nodes (ProjectileNode, ##SightingNode...)."""
    data = fnv_file.read(path)
    root = data.roots[0]
    return {n.name.decode('cp1252'): np.array(n.get_transform(root).as_list())[3, :3]
            for n in root.tree() if isinstance(n, NifFormat.NiNode)}


def _trigger_top(points: np.ndarray) -> np.ndarray:
    """A part's top middle: a trigger's pivot, a magazine's mouth."""
    lo, hi = points.min(0), points.max(0)
    return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2]])


def _inside(point: np.ndarray, points: np.ndarray) -> bool:
    """Whether `point` lies within the box of `points` (False for none)."""
    return bool(len(points)) and bool(np.all(point >= points.min(0)) and np.all(point <= points.max(0)))


def _receiver_trigger(nif, worlds: dict, drawn: bool = False) -> 'np.ndarray | None':
    """The receiver trigger's pivot in receiver space: its shapes' top, else the bone itself; with `drawn`, None
    for a bone outside the NIF's drawn shapes (the laser's placeholder sits 23 units off the gun, its trigger
    drawn by the grip; the 10mm's bone sits in its receiver by the trigger shape).
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    bone = _named(nif, TRIGGER_BONE)
    if bone is None:
        return None
    shapes = [c for c in nif.blocks[bone][1]['children'] if nif.blocks[c][0] == 'BSTriShape']
    points = [_moved(np.array([v['position'] for v in nif.blocks[c][1]['vertices']], float),
                     node_matrix(nif.blocks[c][1]) @ worlds[bone]) for c in shapes]
    if points:
        return _trigger_top(np.vstack(points))
    at = worlds[bone][3, :3]
    return None if drawn and not _inside(at, _points(nif, worlds)) else at


def connect_points(nif, worlds: dict) -> dict:
    """{parent connect point name: receiver-space position} (connect_frames)."""
    return {name: frame[3, :3] for name, frame in connect_frames(nif, worlds).items()}


def connect_frames(nif, worlds: dict) -> dict:
    """{parent connect point name: its 4x4 row-vector transform in receiver space} of BSConnectPoint::Parents
    (rotation quaternion w x y z, translation, on the named node's world transform in `worlds`)."""
    out = {}
    for kind, raw in nif.blocks:
        if kind != 'BSConnectPoint::Parents':
            continue
        at, count = 8, struct.unpack_from('<I', raw, 4)[0]
        for _ in range(count):
            names, at = _sized_strings(raw, at, 2)
            local = np.eye(4)
            local[:3, :3] = _quaternion(struct.unpack_from('<4f', raw, at)).T
            local[3, :3] = struct.unpack_from('<3f', raw, at + 16)
            at += 32
            parent = _named(nif, names[0])
            out[names[1]] = local @ worlds[parent] if parent in worlds else local
    return out


def connect_children(nif) -> list:
    """The parent point names (C-X attaches to P-X) a part's BSConnectPoint::Children name."""
    out = []
    for kind, raw in nif.blocks:
        if kind == 'BSConnectPoint::Children':
            out += _sized_strings(raw, 9, struct.unpack_from('<I', raw, 5)[0])[0]
    return ['P-' + name[2:] if name.startswith('C-') else name for name in out]


def _sized_strings(raw: bytes, at: int, count: int) -> tuple:
    """(`count` u32-length strings read from `at`, the offset after them)."""
    out = []
    for _ in range(count):
        n = struct.unpack_from('<I', raw, at)[0]
        out.append(raw[at + 4:at + 4 + n].decode('cp1252'))
        at += 4 + n
    return out, at


def _quaternion(q: tuple) -> np.ndarray:
    """The 3x3 rotation (column vectors) of quaternion (w, x, y, z)."""
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _points(nif, worlds: dict) -> np.ndarray:
    """Every placed shape's vertices in receiver space (an empty 0x3 with none)."""
    points = [_moved(np.array([v['position'] for v in b['vertices']], float), worlds[i])
              for i, (kind, b) in enumerate(nif.blocks) if kind == 'BSTriShape' and i in worlds and b['vertices']]
    return np.vstack(points) if points else np.zeros((0, 3))


def pieces(raw: bytes) -> list:
    """A weapon NIF's placed shapes split into connected vertex groups (a handle, a barrel...), its bone's frame."""
    nif = parsed(raw)
    worlds, out = node_worlds(nif), []
    for i, (kind, b) in enumerate(nif.blocks):
        if kind != 'BSTriShape' or i not in worlds or not b['vertices'] or not b['triangles']:
            continue
        placed = _moved(np.array([v['position'] for v in b['vertices']], float), worlds[i])
        tris = np.array(b['triangles'])
        links = coo_matrix((np.ones(tris.size), (tris.ravel(), np.roll(tris, 1, 1).ravel())), shape=(len(placed),) * 2)
        _, labels = connected_components(links, directed=False)
        out += [placed[labels == k] for k in np.unique(labels[np.unique(tris)])]
    return out


def _top(nif, worlds: dict) -> float:
    """The highest vertex of the placed shapes, in receiver space (0 with none)."""
    placed = _points(nif, worlds)
    return float(placed[:, 2].max()) if len(placed) else 0.0


def mesh_top(raw: bytes) -> float:
    """The highest point of a NIF's placed shapes."""
    nif = parsed(raw)
    return _top(nif, node_worlds(nif))


def receiver_layout(raw: bytes) -> dict:
    """A FO4 receiver NIF's trigger, magazine mouth, muzzle and sights point, and its top (z), receiver space."""
    nif = parsed(raw)
    worlds = node_worlds(nif)
    points = connect_points(nif, worlds)
    node = {name: worlds[i][3, :3] for name in (MAGAZINE_BONE, MUZZLE) if (i := _named(nif, name)) in worlds}
    return {'trigger': _receiver_trigger(nif, worlds), 'mag': points.get(MAG_POINT, node.get(MAGAZINE_BONE)),
            'muzzle': node.get(MUZZLE), 'scope': points.get(SCOPE_POINT),
            'top': _top(nif, worlds)}


def _shape_parents(src) -> dict:
    """{shape index: its parent node's world matrix} of every BSTriShape reachable from the root (node_worlds)."""
    worlds = node_worlds(src)
    return {c: world for i, world in worlds.items() for c in src.blocks[i][1].get('children', [])
            if c >= 0 and src.blocks[c][0] == 'BSTriShape'}


def _fnv_parts(src, axes: np.ndarray = AXES) -> dict:
    """{shape index: (part name, vertices in the gun's frame, turned by `axes`)} of an FNV gun, nested shapes
    included."""
    return {i: (src.strings[src.blocks[i][1]['name']],
                _moved(np.array([v['position'] for v in src.blocks[i][1]['vertices']], float).reshape(-1, 3),
                       parent) @ axes)
            for i, parent in _shape_parents(src).items()}


def fnv_layout(static_bytes: bytes, nodes: dict) -> dict:
    """A converted FNV gun's trigger, magazine mouth, muzzle and sighting eye point (None when it has none)
    and top, FO4's axes; None when the mesh has no shapes."""
    parts = _fnv_parts(parsed(static_bytes)).values()
    every = np.vstack([np.empty((0, 3)), *(p for _, p in parts)])
    if not len(every):
        return None
    moving = {bone: [p for name, p in parts if bone_for(name) == bone] for bone in (TRIGGER_BONE, MAGAZINE_BONE)}
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
    at = len(dst.blocks) - 1
    if isinstance(block, dict) and 'controller' in block:
        block['controller'] = _copy_chain(dst, src, block['controller'], at)
    return at


def _copy_chain(dst, src, index: int, owner: int) -> int:
    """Append copies of `src`'s controller `index` and those after it, with their interpolators and key data,
    driving `dst` block `owner`; the first copy's index (NONE when none: a controller or interpolator this
    reader keeps as raw bytes is left out, as its links cannot be moved).
    See: docs/fork/fo4_pipeline.md#gun-controllers
    """
    if index < 0 or not isinstance(src.blocks[index][1], dict):
        return NONE
    kind, block = copy.deepcopy(src.blocks[index])
    interp = block.get('interpolator', NONE)
    if interp >= 0 and not isinstance(src.blocks[interp][1], dict):
        return _copy_chain(dst, src, block.get('next', NONE), owner)
    dst.blocks.append((kind, block))
    at = len(dst.blocks) - 1
    block['target'] = owner
    if interp >= 0:
        block['interpolator'] = _copy_keyed(dst, src, interp)
    block['next'] = _copy_chain(dst, src, block.get('next', NONE), owner)
    return at


def _copy_keyed(dst, src, index: int) -> int:
    """Append a copy of `src`'s interpolator `index`, then its key data; the interpolator's index."""
    kind, block = copy.deepcopy(src.blocks[index])
    dst.blocks.append((kind, block))
    at = len(dst.blocks) - 1
    if block.get('data', NONE) >= 0:
        dst.blocks.append(copy.deepcopy(src.blocks[block['data']]))
        block['data'] = len(dst.blocks) - 1
    return at


def _merge_shape(dst, src, index: int, points: np.ndarray, normals: np.ndarray) -> int:
    """Copy `src`'s shape `index` (shader, texture set, alpha) into `dst`, its vertices at `points`; its index."""
    source = src.blocks[index][1]
    shape = {k: None if k == 'vertices' else list(v) if k == 'triangles' else copy.deepcopy(v)
             for k, v in source.items()}
    tris = np.array(shape['triangles'])
    uv = np.array([v['uv'] for v in source['vertices']], float)
    colors = (np.array([v['color'] for v in source['vertices']], float) / 255
              if 'color' in source['vertices'][0] else None)
    unit = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    center = (points.min(0) + points.max(0)) / 2
    shape.update(name=dst.string(src.strings[shape['name']]), vertices=vertices(points, uv, unit, colors, tris),
                 translation=(0.0, 0.0, 0.0), rotation=IDENTITY, scale=1.0, collision=NONE, extra=[],
                 bound=(*map(float, center), float(np.linalg.norm(points - center, axis=1).max())))
    for key in ('shader', 'alpha_property'):
        if shape[key] >= 0:
            shape[key] = _copy_block(dst, src, shape[key])
    dst.blocks.append(('BSTriShape', shape))
    at = len(dst.blocks) - 1
    shape['controller'] = _copy_chain(dst, src, shape['controller'], at)
    return at


def _emptied(nif) -> None:
    """Empty every receiver shape's geometry, keeping the block its shader and controllers hang on."""
    for kind, block in nif.blocks:
        if kind == 'BSTriShape':
            block.update(vertices=[], triangles=[], bound=(0.0, 0.0, 0.0, 0.0))
            block.pop('counts', None)


def draws(raw: bytes) -> bool:
    """Whether a NIF has any geometry (a weapon's base model is often an empty dummy)."""
    return any(kind.endswith('TriShape') for kind, _ in parsed(raw).blocks)


def receiver_bones(raw: bytes) -> dict:
    """{bone name: receiver-space rest 4x4} of a receiver NIF's nodes."""
    nif = parsed(raw)
    worlds = node_worlds(nif)
    return {nif.strings[b['name']]: worlds[i] for i, (kind, b) in enumerate(nif.blocks)
            if kind == 'NiNode' and i in worlds}


def _box(points: np.ndarray) -> np.ndarray:
    """[min corner, max corner] of `points`."""
    return np.array([points.min(0), points.max(0)])


def axes_for(src, nodes: dict, receiver) -> np.ndarray:
    """FNV gun `src`'s turn to FO4's axes: AXES, except for one FNV builds along +Y (a launcher, its muzzle in
    `nodes` then up or down), tipped so the muzzle points ahead and rolled the quarter turn whose shape best fits
    receiver NIF `receiver`'s placed shapes."""
    if MUZZLE not in nodes:
        return AXES
    _, ahead, up = nodes[MUZZLE] @ AXES
    if abs(up) <= abs(ahead):
        return AXES
    theirs = _box(_points(receiver, node_worlds(receiver)))
    ours = np.vstack([p for _, p in _fnv_parts(src, np.eye(3)).values()])
    turns = [AXES @ TIP[1 if up > 0 else -1] @ roll for roll in ROLLS]
    return min(turns, key=lambda axes: float(np.abs(_box(ours @ axes) - theirs).sum()))


def placement(static_bytes: bytes, nodes: dict, receiver_bytes: bytes) -> np.ndarray:
    """The row-vector 4x4 putting converted FNV gun `static_bytes` (`nodes` its FNV node positions) in receiver
    NIF `receiver_bytes`'s frame: turned to FO4's axes (axes_for), then moved so its trigger's top sits on the
    receiver's drawn one; unmoved without either, as both games put a gun's origin in the hand."""
    src, nif = stripped(static_bytes), parsed(receiver_bytes)
    axes = axes_for(src, nodes, nif)
    bones = {nif.strings[b['name']]: i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'}
    target = _receiver_trigger(nif, node_worlds(nif), drawn=True)
    triggers = [p for name, p in _fnv_parts(src, axes).values() if bone_for(name, bones) == TRIGGER_BONE]
    out = np.eye(4)
    out[:3, :3] = axes
    if triggers and target is not None:
        out[3, :3] = target - _trigger_top(np.vstack(triggers))
    return out


def gun(static_bytes: bytes, nodes: dict, receiver_bytes: bytes, matrix: np.ndarray) -> bytes:
    """The FO4 weapon NIF of a converted FNV gun (convert_static's, `nodes` its FNV node positions) on the
    receiver NIF `receiver_bytes`, put in its frame by `matrix` (placement())."""
    axes, offset = matrix[:3, :3], matrix[3, :3]
    src = without_havok(nif_file.read(static_bytes))
    nif = nif_file.read(receiver_bytes)
    worlds = node_worlds(nif)
    muzzle = _named(nif, MUZZLE)
    body = next((i for i, (_, b) in enumerate(nif.blocks)
                 if isinstance(b, dict) and muzzle in b.get('children', [])), 0)
    bones = {nif.strings[b['name']]: i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'}
    _emptied(nif)
    named, frames = _fnv_parts(src, axes), _shape_parents(src)
    parts, names = {i: p for i, (_, p) in named.items()}, {i: n for i, (n, _) in named.items()}
    for i, points in parts.items():
        bone = bone_for(names[i], bones)
        parent = bones[bone] if bone else body
        inverse = np.linalg.inv(worlds[parent])
        raw = np.array([v['normal'] for v in src.blocks[i][1]['vertices']], float) / 127.5 - 1.0
        normals = raw @ frames[i][:3, :3] @ axes
        merged = _merge_shape(nif, src, i, _moved(points + offset, inverse), normals @ inverse[:3, :3])
        nif.blocks[parent][1]['children'].append(merged)
    if muzzle is not None and MUZZLE in nodes:
        local = _moved((nodes[MUZZLE] @ axes + offset)[None], np.linalg.inv(worlds[body]))[0]
        nif.blocks[muzzle][1]['translation'] = tuple(map(float, local))
    return nif_file.write(nif)
