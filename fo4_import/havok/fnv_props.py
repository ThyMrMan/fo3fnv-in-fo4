"""FNV idle props with no vanilla stand-in: FNV's mesh on an FO4 prop bone the converted clip moves as FNV moved it.

FNV hangs a prop from a skeleton bone (its mesh's `Prn`), and an idle's clip may
move the mesh's own nodes (Doc's Reflectron, the Rorschach cards, the guitar).
FO4 hangs a prop from a prop bone the clip moves: AnimObjectR1 and L1 rest on
the hands, AnimObjectA on the root. The mesh's nodes from its root down to the
one holding all its shapes (its chain) are flattened in the converted mesh,
and the clip's prop-bone track carries their transform on every frame. Under a
hand, it is turned from FNV's hand onto FO4's as the clip retarget turns the
hand. Under any other bone, it is in the clip's root space with that bone's motion.

See: docs/fork/fo4_idles.md#converted-props
"""

from dataclasses import dataclass

import numpy as np

from asset_convert.havok.clip_retarget import compose, mat_to_quat_wxyz, posed_world, quat_wxyz_to_mat, world_positions
from asset_convert.havok.kf_decode import BoneTrack
from fo4_import.havok.anim_props import Prop

#: FNV hand -> (FO4 prop bone resting on it, FO4 hand); a prop on any other FNV bone hangs from ROOT_BONE.
HANDS = {'Bip01 R Hand': ('AnimObjectR1', 'RArm_Hand'), 'Bip01 L Hand': ('AnimObjectL1', 'LArm_Hand')}
ROOT_BONE = 'AnimObjectA'


def prop_bone(parent: str) -> str:
    """The FO4 prop bone of a prop FNV hangs from `parent`."""
    return HANDS.get(parent, (ROOT_BONE,))[0]


def hand_turns(clips) -> dict:
    """{FNV hand: 4x4} taking a point in the FNV hand's space into FO4's hand's, as `clips` (HumanClips) retarget
    the hand."""
    matched = posed_world(clips.fnv, clips.deltas)
    out = {}
    for hand, (_, fo4) in HANDS.items():
        turn = matched[clips.fnv.index[hand]][:3, :3] @ clips.fo4.world[clips.fo4.index[fo4]][:3, :3].T
        out[hand] = compose(np.zeros(3), turn)
    return out


def local_at(track, frame: int, rest: np.ndarray) -> np.ndarray:
    """A chain node's local 4x4 at `frame`: `track`'s channels (kf_decode.BoneTrack) where it has them, else `rest`'s."""
    if track is None:
        return rest
    rot = quat_wxyz_to_mat(track.rotations[frame]) if track.rotations is not None else rest[:3, :3]
    return compose(track.translations[frame] if track.translations is not None else rest[3, :3], rot)


def unscaled(m: np.ndarray) -> np.ndarray:
    """4x4 `m` with its rotation rows made unit length."""
    out = m.copy()
    out[:3, :3] /= np.linalg.norm(out[:3, :3], axis=1, keepdims=True)
    return out


@dataclass
class ConvertedProp(Prop):
    """A converted FNV prop: Prop's fields, the FNV bone it hangs from, its chain ((node, unscaled rest local 4x4),
    root first) and its hand's `turn` (hand_turns; None in root space)."""
    parent: str = ''
    chain: tuple = ()
    turn: 'np.ndarray | None' = None

    def track(self, clip, fnv) -> BoneTrack:
        """The prop bone's track over FNV `clip` (on skeleton `fnv`): the chain's transform on every frame."""
        tracks = {t.bone: t for t in clip.tracks}
        frames = [unscaled(self._at(tracks, f, clip, fnv)) for f in range(len(clip.times))]
        return BoneTrack(self.bone, np.array([m[3, :3] for m in frames]),
                         np.array([mat_to_quat_wxyz(m[:3, :3]) for m in frames]))

    def _at(self, tracks: dict, frame: int, clip, fnv) -> np.ndarray:
        """The chain's 4x4 at `frame` in its FO4 bone's parent: the hand's (turned), else the root's."""
        m = np.eye(4)
        for name, rest in reversed(self.chain):
            m = m @ local_at(tracks.get(name), frame, rest)
        if self.turn is not None:
            return m @ self.turn
        return m @ world_positions(clip, fnv, frame)[fnv.index[self.parent]]
