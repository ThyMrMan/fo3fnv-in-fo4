"""Moving an FNV skinned mesh from FNV's skeleton onto a Fallout 4 one with other proportions.

A `Rig` maps FNV bones to FO4 ones. A bone that spans a part (`ends`: a
limb or spine part, its FNV end bone) is turned so its direction matches
FO4's and stretched along itself to FO4's length; the rest move with the
bone they follow (`follow`) or, unlisted, their nearest moved ancestor.
Each vertex moves by its FNV weights. Used for outfits (FO4's body) and
creatures (an FO4 creature's skeleton).

See: docs/fork/fo4_spikes.md#spike-4-outfits
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Rig:
    """FNV bone -> FO4 bone (`bones`); FNV bone -> the FNV bone its part runs to (`ends`); FNV bone -> the bone
    whose move it takes (`follow`); the FNV root bone, moved by translation only (`root`)."""
    bones: dict
    ends: dict
    follow: dict
    root: str


def _turn(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest rotation taking unit vector `a` onto unit vector `b`."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def part_move(joint, end, fo4_joint, fo4_end) -> tuple:
    """(L, c) with x' = L x + c: the part `joint`->`end` turned onto `fo4_joint`->`fo4_end` and stretched along
    itself to its length."""
    span, fo4_span = np.subtract(end, joint), np.subtract(fo4_end, fo4_joint)
    d = span / np.linalg.norm(span)
    k = np.linalg.norm(fo4_span) / np.linalg.norm(span)
    move = _turn(d, fo4_span / np.linalg.norm(fo4_span)) @ (np.eye(3) + (k - 1.0) * np.outer(d, d))
    return move, np.asarray(fo4_joint) - move @ joint


def bone_moves(rig: Rig, fnv_joints: dict, fnv_parents: dict, fo4_joints: dict) -> dict:
    """{FNV bone: (L, c)} for every FNV skeleton bone (the module notes)."""
    moves = {rig.root: (np.eye(3), np.asarray(fo4_joints[rig.bones[rig.root]]) - fnv_joints[rig.root])}
    for bone, end in rig.ends.items():
        moves[bone] = part_move(fnv_joints[bone], fnv_joints[end], fo4_joints[rig.bones[bone]],
                                fo4_joints[rig.bones[end]])
    for bone, leader in rig.follow.items():
        moves[bone] = moves[leader]
    for bone in fnv_parents:
        up = bone
        while up not in moves and up in fnv_parents:
            up = fnv_parents[up]
        moves[bone] = moves.get(up, moves[rig.root])
    return moves


def retargeted(moves: dict, root: str, points: np.ndarray, normals: np.ndarray, weights: list) -> tuple:
    """(positions, unit normals) of FNV root-space points moved by their FNV bones' `moves` (`root`'s for none)."""
    out, nrm = np.zeros_like(points), np.zeros_like(points)
    for i, (p, n, w) in enumerate(zip(points, normals, weights)):
        total = sum(w.values()) or 1.0
        for bone, share in (w or {root: 1.0}).items():
            move, shift = moves.get(bone, moves[root])
            out[i] += share / total * (move @ p + shift)
            nrm[i] += share / total * (move @ n)
    return out, nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
