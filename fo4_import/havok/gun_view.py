"""What FO4's first-person view shows of a gun's hold: its meshes posed by a clip, and how much of the right hand is
on screen while aiming (the gun_quick_convert tool's measure, and a converted gun's check: weapon_checks).

See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import math

import numpy as np

from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.app.preview.scene import SHAPES
from fo4_import.havok.gun_clips import FO4_VIEW_FOV, VIEW_ASPECT, VIEWS, fo4_skeleton, vanilla_worlds
from fo4_import.nif import file as nif_file
from fo4_import.nif import gun
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.nif.outfit import bone_data, shape_bones

B = chr(92)
#: FO4's first-person arms, posed on its first-person skeleton.
FO4_ARMS = ('actors/character/characterassets/1stpersonmalebody.nif',
            'actors/character/characterassets/1stpersonmalehands.nif')
#: The right hand bone and the reach from it counted as hand and wrist (hand_share).
HAND, HAND_REACH = 'RArm_Hand', 9.0
#: How much wider a 16:9 screen sees than the 4:3 one FO4's first-person FOV is taken as measured on.
WIDE = (16 / 9) / (4 / 3)


def homogeneous(points: np.ndarray) -> np.ndarray:
    """Row vectors with a 1 appended."""
    return np.hstack([points, np.ones((len(points), 1))])


def shapes(nif) -> list:
    """[(name, vertices in the root's frame, triangles)] of a FO4 NIF's unskinned BSTriShapes."""
    worlds = gun.node_worlds(nif)
    return [(nif.strings[b['name']], (homogeneous(np.array([v['position'] for v in b['vertices']], float))
                                      @ worlds[i])[:, :3], b['triangles'])
            for i, (kind, b) in enumerate(nif.blocks)
            if kind == 'BSTriShape' and i in worlds and b['vertices'] and b['skin'] < 0]


def fo4_skinned(raw: bytes, worlds: dict) -> list:
    """[(name, posed vertices, triangles)] of a FO4 NIF's skinned shapes on bone frames `worlds` ({name: 4x4}), a
    vertex's weight on bones `worlds` lacks shared among its others."""
    nif = nif_file.read(raw)
    out = []
    for kind, b in nif.blocks:
        b = b if isinstance(b, dict) or kind not in SHAPES else read_tri_shape(Reader(b))
        if kind not in SHAPES or b.get('skin', -1) < 0 or not b['vertices']:
            continue
        refs, data = shape_bones(nif, b)
        names = [nif.strings[nif.blocks[r][1]['name']] for r in refs]
        binds = bone_data(nif.blocks[data][1])
        points = np.array([v['position'] for v in b['vertices']], float)
        posed, total = np.zeros_like(points), np.zeros(len(points))
        for k, name in enumerate(names):
            _, rot, t = binds[k]
            weight = np.array([sum(w for w, j in zip(v['weights'], v['bones']) if j == k) for v in b['vertices']])
            if name in worlds and weight.any():
                posed += weight[:, None] * (homogeneous(points @ rot.T + t) @ worlds[name])[:, :3]
                total += weight
        out.append((nif.strings[b['name']], posed / np.maximum(total, 1e-6)[:, None], b['triangles']))
    return out


def with_helpers(worlds: dict, skeleton_nif: bytes) -> dict:
    """`worlds` ({bone: 4x4}) plus every node of skeleton NIF `skeleton_nif` it lacks (skin helpers the animated
    skeleton leaves out), each at its rest offset from its posed parent."""
    nif = nif_file.read(skeleton_nif)
    out = dict(worlds)
    stack = [(0, np.eye(4))]
    while stack:
        index, parent = stack.pop()
        block = nif.blocks[index][1]
        if not isinstance(block, dict) or 'children' not in block:
            continue
        name = nif.strings[block['name']]
        here = out.setdefault(name, gun.node_matrix(block) @ parent) if index else parent
        stack += [(c, here) for c in block['children'] if c >= 0]
    return out


class Arms:
    """FO4's first-person skeleton and arms, read once from the game's archives (`read(path)`: bytes)."""

    def __init__(self, read):
        """The rig: the skeleton, its NIF and the arm NIFs."""
        skeleton = VIEWS[0].skeleton
        self.skeleton = fo4_skeleton(read(skeleton))[0]
        self.skeleton_nif = read(skeleton[:-len('.hkx')] + '.nif')
        self.arms = [read('meshes' + B + p.replace('/', B)) for p in FO4_ARMS]

    def hand_share(self, clip: bytes, lift: float = 0.0) -> 'float | None':
        """The share of the right hand's (and wrist's) vertices on a 16:9 screen (FO4's first-person FOV taken as
        measured on 4:3) in first-person clip `clip`'s first frame, the camera raised by `lift`; None for a clip
        the parser does not read.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        anim = parse_fo4_animation(clip)
        if anim is None:
            return None
        world = vanilla_worlds(anim, self.skeleton, 0)
        worlds = with_helpers({n: world[i] for i, n in enumerate(self.skeleton.names)}, self.skeleton_nif)
        hand = worlds[HAND][3, :3]
        verts = np.vstack([v for raw in self.arms for _, v, _ in fo4_skinned(raw, worlds)])
        near = verts[np.linalg.norm(verts - hand, axis=1) < HAND_REACH]
        seen = (homogeneous(near) @ np.linalg.inv(worlds[VIEWS[0].camera[1]]))[:, :3]
        seen[:, 1] -= lift
        ahead = -seen[:, 2]
        across = math.tan(math.radians(FO4_VIEW_FOV / 2)) * WIDE
        inside = (ahead > 0) & (np.abs(seen[:, 0]) < ahead * across) & (np.abs(seen[:, 1]) < ahead * across * VIEW_ASPECT)
        return float(inside.mean())
