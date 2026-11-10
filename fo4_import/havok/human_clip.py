"""FNV human .kf clips as Fallout 4 .hkx animations on FO4's human skeleton.

A clip is decoded (kf_decode), retargeted from FNV's Bip01 skeleton onto FO4's
skeleton.hkx (clip_retarget: each mapped FO4 bone repeats its FNV bone's world
rotation change from a pose of FNV's skeleton matching FO4's rest pose; COM
takes the pelvis's translation change) and written as a Havok 2014
spline-compressed clip with one track per FO4 bone (anim_fo4). The matching
pose turns each FNV limb, spine and finger part onto the direction of the FO4
part it maps to (PART_ENDS); a bone without a part takes its leader's turn.
`seated` says whether a clip starts seated, which no FO4 route plays yet.

See: docs/fork/fo4_idles.md#clips
"""

from pathlib import Path

import numpy as np

from asset_convert.havok.clip_retarget import (Skeleton, compose, quat_wxyz_to_mat, retarget_clip, rotation_between,
                                               world_positions)
from asset_convert.havok.hkx_anim import clip_to_animation_data
from external.pynifly_hkx.anim_fo4 import parse_fo4_skeleton, write_fo4_animation
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.kf_cache import decoded

FO4_SKELETON = 'meshes\\actors\\character\\characterassets\\skeleton.hkx'
FNV_SKELETON = 'characters\\_male\\skeleton.nif'
#: FO4 bone carrying the body's height and facing, which takes the FNV pelvis's translation.
COM = 'COM'
#: Engine events vanilla's dynamic idles carry at their start and end (Hancock_PlayingKnife.hkx).
HEAD_TRACKING = ('HeadTrackingOff', 'HeadTrackingOn')
#: Every track's scale: vanilla clips carry none (skeleton.hkx's are off 1 by up to 4e-5, which would write a channel).
UNIT_SCALE = 1.0
#: The kind of FNV text key (`Sound: <EditorID>`, lower case) a furniture pose plays as a sound event.
SOUND_KEY = 'sound'
#: Every annotation track's name: vanilla leaves them blank (all 1,500 clips surveyed in fo4_idles.md#encoder-test).
TRACK_NAME = ''
#: A seated first frame: each thigh's drop over its length below [0], the pelvis below [1] of its rest height.
SEATED = (0.5, 0.75)
#: FNV finger chain (Bip01 <side> ...) -> FO4 finger number, thumb first.
FINGERS = {'Thumb1': 1, 'Finger1': 2, 'Finger2': 3, 'Finger3': 4, 'Finger4': 5}


def _side_bones(side: str) -> dict:
    """FNV -> FO4 bones of one side's leg, arm and fingers."""
    fnv, fo4 = f'Bip01 {side} ', side
    out = {fnv + 'Thigh': fo4 + 'Leg_Thigh', fnv + 'Calf': fo4 + 'Leg_Calf', fnv + 'Foot': fo4 + 'Leg_Foot',
           fnv + 'Toe0': fo4 + 'Leg_Toe1', fnv + 'Clavicle': fo4 + 'Arm_Collarbone',
           fnv + 'UpperArm': fo4 + 'Arm_UpperArm', fnv + 'Forearm': fo4 + 'Arm_ForeArm1', fnv + 'Hand': fo4 + 'Arm_Hand'}
    for chain, n in FINGERS.items():
        for joint in range(3):
            out[fnv + chain + ('', '1', '2')[joint]] = f'{fo4}Arm_Finger{n}{joint + 1}'
    return out


def _side_parts(side: str) -> tuple:
    """({FNV bone: the FNV bone its part runs to}, {FNV bone: the bone whose turn it takes}) of one side."""
    fnv = f'Bip01 {side} '
    chain = ['Thigh', 'Calf', 'Foot', 'Toe0']
    arm = ['Clavicle', 'UpperArm', 'Forearm', 'Hand', 'Finger2']
    ends = {fnv + a: fnv + b for limb in (chain, arm) for a, b in zip(limb, limb[1:])}
    follow = {fnv + 'Toe0': fnv + 'Foot'}
    for finger in FINGERS:
        ends.update({fnv + finger: fnv + finger + '1', fnv + finger + '1': fnv + finger + '2'})
        follow[fnv + finger + '2'] = fnv + finger + '1'
    return ends, follow


#: FNV bone -> FO4 skeleton.hkx bone. FNV's pelvis turns the whole body, as FO4's COM does.
BONES = {'Bip01 Pelvis': COM, 'Bip01 Spine': 'Spine1', 'Bip01 Spine1': 'Spine2', 'Bip01 Spine2': 'Chest',
         'Bip01 Neck': 'Neck', 'Bip01 Head': 'Head', **_side_bones('L'), **_side_bones('R')}
#: FNV bone -> the FNV bone its part runs to; FNV bone -> the bone whose turn it takes.
PART_ENDS = {'Bip01 Spine': 'Bip01 Spine1', 'Bip01 Spine1': 'Bip01 Spine2', 'Bip01 Spine2': 'Bip01 Neck',
             'Bip01 Neck': 'Bip01 Head', **_side_parts('L')[0], **_side_parts('R')[0]}
FOLLOW = {'Bip01 Head': 'Bip01 Neck', **_side_parts('L')[1], **_side_parts('R')[1]}


class HumanClips:
    """Converts FNV human clips under an export's meshes; FO4's skeleton is read once."""

    def __init__(self, export_meshes: Path):
        """Clips read from `export_meshes` (the export's meshes folder)."""
        self.meshes = export_meshes
        fo4 = parse_fo4_skeleton(Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Animations.ba2').read(FO4_SKELETON))
        self.pose = {b: (tuple(p.translation), (p.rotation[3], *p.rotation[:3]), UNIT_SCALE)
                     for b, p in zip(fo4.bones, fo4.reference_pose)}
        self.fo4 = Skeleton(fo4.bones, fo4.parents, [compose(t, quat_wxyz_to_mat(q), s) for t, q, s in self.pose.values()])
        self.fnv = Skeleton.from_nif(str(export_meshes / FNV_SKELETON))
        self.deltas = matching_pose(self.fnv, self.fo4)

    def write(self, kf: str, out: Path, props=()) -> None:
        """Convert the FNV clip at `kf` (relative to the meshes folder) to `out`, showing `props` (anim_props.Prop
        or fnv_props.ConvertedProp)."""
        clip = decoded(str(self.meshes / kf))[0]
        moved = retarget_clip(clip, self.fnv, self.fo4, BONES, self.deltas, translated=(COM,))
        events = [(0.0, HEAD_TRACKING[0]), (float(clip.duration), HEAD_TRACKING[1])]
        for prop in props:
            events += prop.events(clip.text_keys, float(clip.duration))
            moved.tracks.append(prop.track(clip, self.fnv))
        self._save(moved, list(dict.fromkeys(events)), out)

    def write_pose(self, kf: str, out: Path, sound) -> None:
        """Convert FNV furniture clip `kf` to `out` as a furniture pose in FNV's marker frame (the marker is FNV's),
        no head tracking (vanilla's furniture clips carry no events), each `Sound: <EditorID>` key played by
        `sound(EditorID)` (an event or None).
        See: docs/fork/fo4_pipeline.md#crucifix
        """
        clip = decoded(str(self.meshes / kf))[0]
        moved = retarget_clip(clip, self.fnv, self.fo4, BONES, self.deltas, translated=(COM,))
        keys = [(float(t), key.partition(':')) for t, key in clip.text_keys]
        events = [(t, sound(name.strip())) for t, (kind, _, name) in keys if kind.strip().lower() == SOUND_KEY]
        self._save(moved, [e for e in events if e[1]], out)

    def _save(self, moved, events: list, out: Path) -> None:
        """Write retargeted clip `moved` with `events` [(time, text)] to `out`, its tracks unnamed."""
        anim = clip_to_animation_data(moved, self.fo4.names, self.pose, events)
        anim.bone_names = [TRACK_NAME] * anim.num_tracks
        out.parent.mkdir(parents=True, exist_ok=True)
        write_fo4_animation(str(out), anim)

    def seated(self, kf: str) -> bool:
        """Whether the FNV clip at `kf` starts seated: both thighs near level and the pelvis low (SEATED).

        See: docs/fork/fo4_idles.md#furniture
        """
        world, rest = world_positions(decoded(str(self.meshes / kf))[0], self.fnv, 0), self.fnv.world
        pelvis = self.fnv.index['Bip01 Pelvis']
        drops = []
        for side in 'LR':
            hip, knee = (world[self.fnv.index[f'Bip01 {side} {b}']][3, :3] for b in ('Thigh', 'Calf'))
            drops.append((hip[2] - knee[2]) / np.linalg.norm(knee - hip))
        return max(drops) < SEATED[0] and world[pelvis][3, 2] < SEATED[1] * rest[pelvis][3, 2]


def matching_pose(fnv: Skeleton, fo4: Skeleton) -> dict:
    """{FNV bone: 4x4 world delta} turning each FNV part about its joint onto its FO4 part's rest direction."""
    turns = {}
    for bone, end in PART_ENDS.items():
        span = fnv.world[fnv.index[end]][3, :3] - fnv.world[fnv.index[bone]][3, :3]
        fo4_span = fo4.world[fo4.index[BONES[end]]][3, :3] - fo4.world[fo4.index[BONES[bone]]][3, :3]
        turns[bone] = rotation_between(span, fo4_span, np.array([0.0, 0.0, 1.0]))
    turns.update({bone: turns[leader] for bone, leader in FOLLOW.items()})
    deltas = {}
    for bone, turn in turns.items():
        at = fnv.world[fnv.index[bone]][3, :3]
        deltas[bone] = compose(at - at @ turn, turn)
    return deltas
