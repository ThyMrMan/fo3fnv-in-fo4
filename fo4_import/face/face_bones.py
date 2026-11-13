"""An NPC's sculpt regions (FMRI/FMRS) moved onto its head part vertices through the race's face bones.

The race's region file lists, per region, the face bones it drives, with Maxima and Minima per axis for
position, rotation (degrees) and scale. A control value v adds |v| times the Maxima (v >= 0) or Minima to
each bone, summed over regions. A bone's node becomes local @ T(pos) @ Rzyx(-angles) @ diag(1 + scale); the
facebones skeleton carries that down its hierarchy. Each part's _faceBones twin (the part's own vertices,
skinned to the face bones) is then skinned with every bone's move taken in the bone's own frame, about the
twin's bind. Matches the CK on Doc Mitchell to 0.045 units at worst.

See: docs/fork/fo4_facegen_plan.md#sculpt-regions
"""

import json
import struct

import numpy as np

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.nif.outfit import bone_data, shape_bones

ASSETS = 'meshes\\actors\\character\\characterassets\\'
#: The race's region file and facebones skeleton, per sex (female?).
REGIONS = {False: ASSETS + 'humanracefacialboneregionsmale.txt',
           True: ASSETS + 'humanracefacialboneregionsfemale.txt'}
SKELETONS = {False: ASSETS + 'skeleton_facebones.nif', True: ASSETS + 'skeleton_female_facebones.nif'}
#: FMRS: position xyz, rotation xyz, scale (two unused floats follow).
CONTROLS = 7
#: A part mesh's twin skinned to the face bones: the model path with this before '.nif'.
TWIN = '_faceBones'
#: A region file's bone name 'bone_X' is skeleton node 'skin_bone_X'.
NODE_PREFIX = 'skin_'
SHAPES = ('BSSubIndexTriShape', 'BSTriShape')


def npc_controls(npc) -> list:
    """[(region id, 7 control values)] of an NPC record's FMRI/FMRS pairs."""
    ids = [struct.unpack('<I', d)[0] for tag, d in npc.subs if tag == b'FMRI']
    values = [struct.unpack_from(f'<{CONTROLS}f', d) for tag, d in npc.subs if tag == b'FMRS']
    return list(zip(ids, values))


def _limit(bone: dict, value: float, part: str, axis: str) -> float:
    """|value| times the bone's Maxima (value >= 0) or Minima for one part and axis."""
    return abs(value) * bone['Maxima' if value >= 0 else 'Minima'][part][axis]


def bone_controls(regions: list, controls: list) -> dict:
    """{skeleton node name (lower case): 9 floats (position, rotation degrees, scale per axis)} summed."""
    by_id = {r['ID']: r for r in regions}
    out = {}
    for rid, values in controls:
        for bone in by_id[rid]['BonesA'] if rid in by_id else ():
            d = out.setdefault((NODE_PREFIX + bone['Bone']).lower(), np.zeros(9))
            for j, axis in enumerate('xyz'):
                d[j] += _limit(bone, values[j], 'Position', axis)
                d[3 + j] += _limit(bone, values[3 + j], 'Rotation', axis)
                d[6 + j] += _limit(bone, values[6], 'Scale', axis)
    return out


def local_move(d: np.ndarray) -> np.ndarray:
    """A bone's 4x4 move in its parent's frame from its 9 summed controls."""
    x, y, z = np.radians(-d[3:6])
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = rz @ ry @ rx @ np.diag(1 + d[6:9])
    m[:3, 3] = d[:3]
    return m


class FaceSkeleton:
    """A facebones skeleton NIF's node tree: parent and local 4x4 per node, nodes by lower-case name."""

    def __init__(self, nif):
        """Every NiNode of `nif`."""
        self.parent, self.local, self.index = {}, {}, {}
        for i, (kind, b) in enumerate(nif.blocks):
            for c in b.get('children', ()) if isinstance(b, dict) else ():
                self.parent[c] = i
            if kind == 'NiNode':
                m = np.eye(4)
                m[:3, :3] = np.array(b['rotation']).reshape(3, 3) * b['scale']
                m[:3, 3] = b['translation']
                self.local[i], self.index[nif.strings[b['name']].lower()] = m, i

    def world(self, moves: dict) -> dict:
        """{lower name: world 4x4} with `moves` {node index: 4x4} applied after each node's local transform."""
        out = {}

        def place(i):
            """Node `i`'s world 4x4, its parents placed first."""
            if i not in out:
                m = self.local[i] @ moves.get(i, np.eye(4))
                up = self.parent.get(i)
                out[i] = place(up) @ m if up in self.local else m
            return out[i]
        return {name: place(i) for name, i in self.index.items()}


def bone_moves(skeleton: FaceSkeleton, controls: dict) -> dict:
    """{lower name: 4x4 move in the bone's own frame (rest^-1 @ moved)} of every bone the controls move."""
    moves = {skeleton.index[n]: local_move(d) for n, d in controls.items() if n in skeleton.index}
    if not moves:
        return {}
    rest, moved = skeleton.world({}), skeleton.world(moves)
    out = {n: np.linalg.solve(rest[n], moved[n]) for n in rest}
    return {n: m for n, m in out.items() if not np.allclose(m, np.eye(4), atol=1e-7)}


def twin_shape(nif) -> tuple:
    """(positions, weights, bone indices, bone names, bind 4x4 per bone) of a _faceBones mesh's first shape."""
    index = next(i for i, (kind, _) in enumerate(nif.blocks) if kind in SHAPES)
    block = nif.blocks[index][1]
    shape = block if isinstance(block, dict) else read_tri_shape(Reader(block))
    verts = shape['vertices']
    nodes, data = shape_bones(nif, shape)
    binds = []
    for _, rot, t in bone_data(nif.blocks[data][1]):
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = rot, t
        binds.append(m)
    return (np.array([v['position'] for v in verts], float), np.array([v['weights'] for v in verts], float),
            np.array([v['bones'] for v in verts], int), [nif.strings[nif.blocks[n][1]['name']] for n in nodes], binds)


def sculpted(twin: tuple, moves: dict) -> np.ndarray:
    """The twin's positions skinned with `moves` (bone_moves), each about its bone's bind."""
    points, weights, bones, names, binds = twin
    out = points.copy()
    for k, name in enumerate(names):
        move = moves.get(name.lower())
        w = (weights * (bones == k)).sum(1)
        if move is None or not w.any():
            continue
        m = np.linalg.solve(binds[k], move @ binds[k])
        out += w[:, None] * (points @ m[:3, :3].T + m[:3, 3] - points)
    return out


class Sculpt:
    """One NPC's face bone moves, applied to its head parts by model path."""

    def __init__(self, src, npc, female: bool):
        """The moves `npc`'s FMRI/FMRS make on the race's facebones skeleton (`src` reads game files)."""
        self.src = src
        controls = npc_controls(npc)
        self.moves = {}
        if controls:
            regions = json.loads(src.read(REGIONS[female]))
            skeleton = FaceSkeleton(nif_file.read(src.read(SKELETONS[female])))
            self.moves = bone_moves(skeleton, bone_controls(regions, controls))

    def positions(self, model: str, count: int) -> 'np.ndarray | None':
        """The sculpted positions of a part (MODL path under meshes\\) with `count` vertices, or None when nothing
        moves, it has no twin, or the twin's vertex count differs."""
        if not self.moves:
            return None
        try:
            twin = twin_shape(nif_file.read(self.src.read('meshes\\' + model[:-4] + TWIN + model[-4:])))
        except KeyError:
            return None
        return sculpted(twin, self.moves) if len(twin[0]) == count else None
