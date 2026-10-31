"""FNV gun clips under a vanilla Fallout 4 gun's clip names, so that gun's behaviour graph plays FNV's motion.

FO4 picks a gun's animations by keyword: each subgraph entry of a race
(Fallout4.esm's HumanRaceSubGraphData) names target keywords, a behaviour
graph (`WeaponBehavior.hkx`; first person `GunBehavior.hkx`) and clip
folders searched in order. A converted FNV gun keeps a vanilla gun's graph
unchanged: its record takes a keyword of its own in place of the template's
`Anims` keyword, and an additive race (SADD on HumanRaceSubGraphData, as
DLC01 adds its lightning gun) copies the template's keyword-only entry of
each view with the gun's own folder searched first. That folder holds FNV's
clips under the vanilla names they replace; a state FNV has no clip for
(sprint, power armor, bash, pitch) still finds the vanilla clip further down.

- Clips (PLAN): FNV's class clips (aim, iron-sight aim, the attack and
  reload letter DNAM names, equip, unequip) per view, retargeted onto FO4's
  human or first-person skeleton (human_clip's bone map and matching pose)
  with two-bone arm IK putting each hand where FNV's is; in first person
  everything is placed relative to the camera bone (FNV's Camera1st drives
  FO4's Camera). A bolt-action attack is cut where the bolt starts to move:
  the shot plays as WPNFireSingle*, the rest as WPNBoltCharge*.
- The gun: FNV's mesh turned to FO4's axes at FNV's size, its trigger on
  the receiver's (nif.gun.placement), so FO4's hand grips it as it
  grips the template. Each clip keeps the Weapon bone at the template's
  grip in the hand (HELD_FROM) and bends the right arm so the gun lands where
  FNV's is (hold): FNV's aim with FO4's hand on the grip; with the gun placed
  in the world instead, FO4's hand (only moved to FNV's wrist) closed beside
  the grip (played). The idle and shot variants and the moving clips take
  FNV's too, so no vanilla hold blends in. The parts FNV's clips move
  (`##VRClip`, `##VRBolt`, `##VRTrigger`) move the receiver's bones
  (nif.gun.PART_BONES), and WeaponIKTargetL holds FNV's left hand, which is
  where third person's IK puts it.
- Off screen: when FNV's aim leaves all of the gun outside FO4's view (the
  minigun pose FNV's flamer borrows), each clip instead starts where the
  template's matching vanilla clip holds its gun (off_screen, anchor_for).
- Left hand: a pistol's takes vanilla's grip and finger curl; any other
  keeps FNV's, moved onto our mesh where FNV's misses it (left_reach);
  reloads keep FNV's hand. A class without iron-sight clips aims with its
  aim clip (fnv_stem), as FNV does.
- Third person keeps the template's clips, its left hand IK'd to WeaponIKTargetL, which the gun folder's
  WPNAssemblyPose sets: each human third-person entry searches first a folder of the gun's own whose copy of
  that pose puts the target on our gun (carried_target: vanilla's hand-local offset from its first-person left
  hand, onto ours).
- Events: each clip takes the annotations of the vanilla clip it replaces
  (sounds, weaponFire, reloadComplete...), each timed from FNV's matching
  text key (KEYED; vanilla sounds in order onto FNV's `Sound:` keys), the
  rest scaled to the clip's length.
- AnimTextData: the game reads an entry's resolved clip paths from
  `AnimTextData\\AnimationFileData\\<id>.txt`, id = CRC-32 of the folder list
  joined by `|` (high half) and of the behaviour graph's path (low half), lower case,
  zero start, no final inversion. Each of the template's files for its
  folder list is copied under the new list's id, the replaced clips pointed
  at the gun's folder.

See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import collections
import functools
import hashlib
import math
import pickle
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from asset_convert.havok.clip_retarget import (Skeleton, compose, mat_to_quat_wxyz, quat_wxyz_to_mat, retarget_clip,
                                               two_bone, world_positions)
from asset_convert.havok.gun_anim_falloutnv import FIRST_PERSON_ARMS
from asset_convert.havok.gun_vocabulary_falloutnv import (ANIM_TYPE_CLASS, ATTACK_ACTIONS, ATTACK_ANIMS, FNV_AUTOMATIC,
                                                       RELOAD_LETTERS)
from asset_convert.havok.hkx_anim import clip_to_animation_data, held_to, loop_clip, slice_clip
from asset_convert.havok.kf_decode import BoneTrack, DecodedClip
from fo4_import.havok.kf_cache import decoded_clip
from external.pynifly_hkx.anim_fo4 import (fo4_animation_header, parse_fo4_animation, parse_fo4_skeleton,
                                           write_fo4_animation)
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.human_clip import BONES, COM, matching_pose
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.gun import SIGHTING, bone_for
from fo4_import.pipeline.elric_cache import write_new
from fo4_import.pipeline.export_index import Layered
from fo4_import.pipeline.work_cache import cached
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

ANIMATIONS = 'Fallout4 - Animations.ba2'
ANIM_TEXT = 'meshes\\animtextdata\\animationfiledata\\'
#: Fallout4.esm's human subgraph race, which the gun entries are added to (SADD).
HUMAN_SUBGRAPHS = 0x166729
WEAPON, HAND, LEFT_HAND, IK_LEFT = 'Weapon', 'RArm_Hand', 'LArm_Hand', 'WeaponIKTargetL'
FNV_WEAPON = 'Weapon'
#: SRAF role of a weapon subgraph entry; the actor keyword of the player's entries.
ROLE_WEAPON, PLAYER = 1, 'AnimArchetypePlayer'
#: How far (game units) a part moves from its first frame before it counts as moving.
MOVED = 0.05
#: Vanilla annotation (lower case) -> the FNV text key (lower-case prefix) it is timed from.
KEYED = {'weaponfire': 'hit', 'ejectshellcasing': 'eject'}
SOUND_EVENT, FNV_SOUND = 'soundplay.', 'sound:'
#: The DLC06 additive race's subrecords before SADD, each filled from HumanRaceSubGraphData's same-named one.
HEAD = ('EDID', 'DESC', 'BOD2', 'PRPS', 'DATA', 'MNAM', 'FNAM', *['MTNM'] * 5, 'VTCK', 'PNAM', 'UNAM', 'NAM1',
        'MNAM', 'INDX', 'FNAM', 'INDX', 'GNAM', 'NAM3', 'MNAM', 'FNAM', *['NAME'] * 32, 'RBPC', 'VNAM')
ENTRY = (b'SAKD', b'SGNM', b'SAPT', b'STKD')
#: The work cache site of a gun's converted clips, and the FNV WEAP fields the conversion reads.
CLIP_SITE = 'gun_clips'
REC_FIELDS = ('EditorID', 'DNAM.FalloutAnimType', 'DNAM.AttackAnim', 'DNAM.ReloadAnim', 'DNAM.Flags1')


@dataclass(frozen=True)
class View:
    """One perspective: FNV's clip folder, FO4's skeleton, the gun folders' root, SRAF perspective, and the
    camera bones placed together (FNV, FO4; None in third person)."""
    fnv: str
    skeleton: str
    folder: str
    perspective: int
    camera: 'tuple | None'


#: The views converted: first person (third person keeps the template's clips and over-the-shoulder camera).
VIEWS = (View('characters\\_1stperson', 'meshes\\actors\\character\\_1stperson\\characterassets\\skeleton.hkx',
              'Actors\\FNV\\Character\\_1stPerson\\Animations', 1, ('Camera1st', 'Camera')),)
#: First-person moving clips: the aim pose held for the vanilla clip's length (piece 'still'), as vanilla's hold.
MOVES = ('WalkForward', 'RunForward', 'RunLeft', 'RunRight')
#: (FO4 clip, FNV clip, piece) per view, with every variant the graph picks among (idles A-D, shots A-B).
PLAN = {1: (('WPNIdleReady', '{cls}aim', None), *((f'WPNIdleReady{v}', '{cls}aim', None) for v in 'ABCD'),
          ('WPNIdleSighted', '{cls}aimis', None), ('WPNFireSingleReady', '{cls}{attack}', 'shot'),
          *((f'WPNFireSingleReady{v}', '{cls}{attack}', 'shot') for v in 'AB'),
          ('WPNBoltChargeReady', '{cls}{attack}', 'bolt'), ('WPNFireSingleSighted', '{cls}{attack}is', 'shot'),
          ('WPNReload', '{cls}reload{letter}', None), ('WPNEquip', '{cls}equip', None),
          ('WPNUnequip', '{cls}unequip', None), ('WPNBoltChargeSighted', '{cls}{attack}is', 'bolt'),
          *((f'WPN{move}Ready', '{cls}aim', 'still') for move in MOVES), ('WPNWalkForwardSighted', '{cls}aimis', 'still'),
          *((f'WPNFireAuto{c}', '{cls}attackloop' + s, 'loop') for c, s in (('ReadyForward', ''), ('ReadyBack', ''),
                                                                                ('Sighted', 'is'))))}
#: Clips keeping FNV's left hand (it works the magazine); elsewhere a one-handed gun's holds vanilla's grip.
OWN_LEFT = ('WPNReload',)
#: The FNV class held in one hand: only its left hand takes vanilla's grip (FNV holds the others two-handed).
ONE_HANDED = '1hp'
#: Clips FNV's left hand reaches vanilla's grip over (1: by the end, -1: leaving it from the start); FNV is one-handed.
REACH = {'WPNEquip': 1, 'WPNUnequip': -1}
LEFT_ARM = ('LArm_UpperArm', 'LArm_ForeArm1', LEFT_HAND)
#: The left hand's finger bones' name prefix (thumb included): they take vanilla's curl round the grip.
LEFT_FINGER = 'LArm_Finger'
#: The left middle finger's base in each skeleton: where a left grip's distance to the gun is measured.
GRIP_FINGER, FNV_GRIP_FINGER = 'LArm_Finger21', 'Bip01 L Finger21'
#: FO4's first-person field of view (Fallout4.ini fDefault1stPersonFOV, horizontal) and the screen's height over width.
FO4_VIEW_FOV, VIEW_ASPECT = 80.0, 9 / 16
#: Havok's blend hint ADDITIVE (a clip of bone deltas) and what a converted gun writes in such a layer's place.
ADDITIVE, NEUTRAL = 2, '(neutral additive)'
#: FNV WEAP DNAM.Flags1's Don't Use 1st Person IS Anims: it aims with its unsighted clips (a scope's view).
FNV_NO_SIGHTS = 0x40
#: The first-person clip whose left hand third person's target is carried from.
HELD_POSE = 'WPNIdleReady'
#: The per-gun pose setting WeaponIKTargetL, the human third-person skeleton, the folder a gun's own copies go in.
ASSEMBLY, THIRD_SKELETON = 'WPNAssemblyPose', 'meshes\\actors\\character\\characterassets\\skeleton.hkx'
THIRD_FOLDER = 'Actors\\FNV\\Character\\Animations'
#: Two handles are held the same way when their long directions lie within 45 degrees (cosine).
SAME_WAY = math.cos(math.radians(45))
#: The suffix of FNV's iron-sight clips (2haaimis, 2haattack3is).
SIGHTED = 'is'
#: The vanilla clips (lower case, first that reads) whose Weapon bone gives the hand's grip on the gun.
HELD_FROM = ('wpnfiresingleready', 'wpnreload', 'wpnequip')
#: The right arm (upper arm, forearm, hand) the grip bends.
RIGHT_ARM = ('RArm_UpperArm', 'RArm_ForeArm1', HAND)
#: The clip a bolt-action cut is made for in each perspective (the template must have it).
BOLT_CLIP = 'WPNBoltChargeReady'


def crc(text: str) -> int:
    """AnimTextData's CRC-32: lower case, zero start, no final inversion."""
    return zlib.crc32(text.lower().encode('cp1252'), 0xFFFFFFFF) ^ 0xFFFFFFFF


def file_id(folders, graph: str) -> int:
    """The AnimTextData id of a subgraph entry's folders and behaviour graph."""
    return crc('|'.join(folders)) << 32 | crc(graph)


def with_folder(folders: list, ours: str) -> list:
    """`folders` with `ours` before the first folder that is not a paired one."""
    at = next((i for i, f in enumerate(folders) if not f.lower().endswith('\\paired')), len(folders))
    return folders[:at] + [ours] + folders[at:]


def annotations(vanilla: list, vanilla_length: float, keys: list, length: float) -> list:
    """[(time, text)]: each vanilla annotation (time, text) timed from its FNV text key (KEYED; sounds in order
    onto FNV's `Sound:` keys), else scaled from the vanilla clip's length to `length`."""
    sounds = [t for t, k in keys if k.lower().startswith(FNV_SOUND)]
    out = []
    for t, text in sorted(vanilla):
        prefix = KEYED.get(text.lower())
        at = next((float(kt) for kt, k in keys if prefix and k.lower().startswith(prefix)), None)
        if at is None and text.lower().startswith(SOUND_EVENT) and sounds:
            at = float(sounds.pop(0))
        if at is None:
            at = t * length / vanilla_length if vanilla_length else 0.0
        out.append((round(min(at, length), 4), text))
    return sorted(out)


def subgraph_entries(subs: list) -> list:
    """A race's subgraph entries: [{'actor': [FormID], 'graph', 'paths', 'target': [FormID], 'flags': SRAF}]."""
    out, cur = [], None
    for sig, body in subs:
        if sig in ENTRY and (cur is None or 'flags' in cur):
            cur = {'actor': [], 'paths': [], 'target': []}
            out.append(cur)
        if cur is not None:
            _entry_field(cur, sig, body)
    return out


def _entry_field(entry: dict, sig: bytes, body: bytes) -> None:
    """Put one subgraph subrecord into its entry."""
    if sig in (b'SAKD', b'STKD'):
        entry['actor' if sig == b'SAKD' else 'target'].append(struct.unpack('<I', body)[0])
    elif sig == b'SGNM':
        entry['graph'] = body.rstrip(b'\0').decode('cp1252')
    elif sig == b'SAPT':
        entry['paths'].append(body.rstrip(b'\0').decode('cp1252'))
    elif sig == b'SRAF':
        entry['flags'] = body


def entry_subrecords(entry: dict) -> list:
    """An entry's subrecords."""
    zstr = lambda s: s.encode('cp1252') + b'\0'
    return ([(b'SAKD', struct.pack('<I', k)) for k in entry['actor']] + [(b'SGNM', zstr(entry['graph']))]
            + [(b'SAPT', zstr(p)) for p in entry['paths']] + [(b'STKD', struct.pack('<I', k)) for k in entry['target']]
            + [(b'SRAF', entry['flags'])])


def aimed(entry: dict, old: int, new: int) -> dict:
    """`entry` with target keyword `old` traded for `new` (a gun's own Anims one)."""
    return dict(entry, target=[new if k == old else k for k in entry['target']])


def perspective(entry: dict) -> int:
    """An entry's view (SRAF's second half: 0 third person, 1 first)."""
    return struct.unpack_from('<H', entry['flags'], 2)[0]


def bolt_start(clip, part: 'str | None') -> 'float | None':
    """When FNV's bolt part (track `part`) first leaves its first frame's place; None without it or if it stays."""
    track = next((t for t in clip.tracks if t.bone == part and t.translations is not None), None)
    if track is None:
        return None
    moved = np.flatnonzero(np.linalg.norm(track.translations - track.translations[0], axis=1) > MOVED)
    return float(clip.times[moved[0] - 1]) if len(moved) and moved[0] > 0 else None


def _matrix(rotation_wxyz, translation) -> np.ndarray:
    """A row-vector 4x4 of a (w, x, y, z) rotation and a translation."""
    return compose(translation, quat_wxyz_to_mat(rotation_wxyz))


def _track(name: str, mats: list) -> BoneTrack:
    """A BoneTrack of per-frame row-vector local matrices, its quaternions kept on one hemisphere."""
    q = np.array([mat_to_quat_wxyz(m[:3, :3] / np.linalg.norm(m[0, :3])) for m in mats])
    for k in range(1, len(q)):
        if np.dot(q[k], q[k - 1]) < 0:
            q[k] = -q[k]
    return BoneTrack(bone=name, rotations=q, translations=np.array([m[3, :3] for m in mats]))


def fo4_skeleton(raw: bytes) -> tuple:
    """(Skeleton, {bone: (translation, rotation wxyz, scale)}) of a FO4 skeleton.hkx."""
    fo4 = parse_fo4_skeleton(raw)
    pose = {b: (tuple(p.translation), (p.rotation[3], *p.rotation[:3]), p.scale[0])
            for b, p in zip(fo4.bones, fo4.reference_pose)}
    return Skeleton(fo4.bones, fo4.parents, [compose(t, quat_wxyz_to_mat(q), s) for t, q, s in pose.values()]), pose


def fnv_frames(path: Path) -> dict:
    """{node name: 4x4 row-vector frame} of an FNV gun's nodes, in the gun's frame."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    root = data.roots[0]
    return {n.name.decode('cp1252'): np.array(n.get_transform(root).as_list())
            for n in root.tree() if isinstance(n, NifFormat.NiNode)}


@dataclass
class Rig:
    """One view's FNV and FO4 skeletons, FO4's rest pose, the matching pose and the bones retargeted."""
    view: View
    src: Skeleton
    dst: Skeleton
    pose: dict
    deltas: dict
    bones: dict
    shift: np.ndarray

    @classmethod
    def load(cls, view: View, export_meshes: Path, archives: Archives) -> 'Rig':
        """The rig of `view`, its FNV skeleton from the export's meshes."""
        dst, pose = fo4_skeleton(archives.read(view.skeleton))
        src = Skeleton.from_nif(str(export_meshes / view.fnv / 'skeleton.nif'))
        shift = np.zeros(3)
        bones = dict(BONES)
        if view.camera:
            bones[view.camera[0]] = view.camera[1]
            shift = dst.world[dst.index[view.camera[1]]][3, :3] - src.world[src.index[view.camera[0]]][3, :3]
        return cls(view, src, dst, pose, matching_pose(src, dst), bones, shift)

    def retarget(self, clip):
        """FNV `clip` on FO4's skeleton, the arms' hands where FNV's are."""
        return retarget_clip(clip, self.src, self.dst, self.bones, self.deltas,
                             translated=(COM,) + ((self.view.camera[1],) if self.view.camera else ()),
                             anchor=self.view.camera, ik_chains=FIRST_PERSON_ARMS)

    def camera(self, moved, frame: int) -> np.ndarray:
        """FO4's camera bone in the world at `frame` of retargeted clip `moved`."""
        return world_positions(moved, self.dst, frame)[self.dst.index[self.view.camera[1]]]

    def fnv_gun(self, clip, frame: int) -> np.ndarray:
        """FNV's gun in the world at `frame` of `clip`, camera shift added."""
        out = world_positions(clip, self.src, frame)[self.src.index[FNV_WEAPON]].copy()
        out[3, :3] += self.shift
        return out


def hold(rig: Rig, moved, f: int, hand: np.ndarray, arm: tuple = RIGHT_ARM) -> np.ndarray:
    """Frame `f` of retargeted clip `moved` (tracks changed in place) with `arm` (upper arm, forearm, hand) bent so
    its hand is at world frame `hand` (row-vector 4x4), the elbow kept on its side; the posed worlds."""
    dst = rig.dst
    world = world_positions(moved, dst, f)
    chain = [dst.index[n] for n in arm]
    fixes = two_bone(world, chain, hand[3, :3], world[chain[1]][3, :3] - world[chain[0]][3, :3])
    tracks = {t.bone: t for t in moved.tracks}
    new = world.copy()
    for di, p in enumerate(dst.parents):
        local = world[di] if p < 0 else world[di] @ np.linalg.inv(world[p])
        posed = local if p < 0 else local @ new[p]
        owner = _arm_segment(dst, chain, di)
        if dst.names[di] in tracks and owner is not None:
            rot = hand[:3, :3] if di == chain[2] else world[di][:3, :3] @ fixes[owner]
            posed = compose(posed[3, :3], rot)
            local_rot = rot @ np.linalg.inv(new[p][:3, :3])
            tracks[dst.names[di]].rotations[f] = mat_to_quat_wxyz(local_rot)
        new[di] = posed
    return new


def _roll(local: np.ndarray, rest: np.ndarray) -> float:
    """Radians `local` rolls its bone about the parent's +X from `rest`."""
    cur, ref = local[1, 1:], rest[1, 1:]
    return math.atan2(ref[0] * cur[1] - ref[1] * cur[0], float(np.dot(ref, cur)))


def share_twist(rig: Rig, moved) -> None:
    """Each hand's roll from rest shared in thirds with its forearm's two twist bones (`moved` changed in place), as
    vanilla's clips share it, the hand's world rotation unchanged; FNV's skeleton has no twist bones.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    dst, tracks = rig.dst, {t.bone: t for t in moved.tracks}
    for side in 'RL':
        hand, twists = f'{side}Arm_Hand', (f'{side}Arm_ForeArm2', f'{side}Arm_ForeArm3')
        if hand not in tracks or not all(b in dst.index for b in twists) or twists[0] in tracks:
            continue
        rest = {b: dst.local[dst.index[b]][:3, :3] for b in (hand, *twists)}
        under = rest[twists[1]] @ rest[twists[0]]
        out = {b: np.empty((len(moved.times), 4)) for b in twists}
        for f, q in enumerate(tracks[hand].rotations):
            local = quat_wxyz_to_mat(q)
            half = _roll(local, rest[hand]) / 6
            turn = quat_wxyz_to_mat((math.cos(half), math.sin(half), 0.0, 0.0))
            turned = {b: turn @ rest[b] for b in twists}
            tracks[hand].rotations[f] = mat_to_quat_wxyz(local @ under @ np.linalg.inv(turned[twists[1]] @ turned[twists[0]]))
            for b in twists:
                out[b][f] = mat_to_quat_wxyz(turned[b])
        moved.tracks += [BoneTrack(bone=b, rotations=out[b], translations=None) for b in twists]


def fill_from(moved, anim, rig: Rig) -> None:
    """Every skeleton bone `moved` has no track for (FNV has no such bone: the camera target, upper-arm twists,
    rib helpers, the gun's other bones) held at its pose in vanilla clip `anim`'s first frame, in place; vanilla's
    third-person clips place the over-the-shoulder camera so.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    if anim is None:
        return
    have, n = {t.bone for t in moved.tracks}, len(moved.times)
    for i, bone in enumerate(rig.dst.names):
        if bone in have or i >= len(anim.tracks) or not anim.tracks[i].rotations:
            continue
        x, y, z, w = anim.tracks[i].rotations[0]
        moved.tracks.append(BoneTrack(bone=bone, rotations=np.tile((w, x, y, z), (n, 1)),
                                      translations=np.tile(np.asarray(anim.tracks[i].translations[0], float), (n, 1))))


def cut_piece(clip, piece: 'str | None', length: float, cut: 'float | None'):
    """FNV `clip` cut to PLAN's `piece`: 'still' its first pose held and 'loop' it repeated for `length` (the vanilla
    clip's; a loop keeps vanilla's event times), 'shot' up to the bolt's `cut` and held to at least `length`
    (the graph leaves a shot by triggers timed back from its end), 'bolt' from the cut; None for a bolt piece
    without one.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    if piece == 'still':
        return slice_clip(clip, 0.0, length, hold=True)
    if piece == 'loop':
        return loop_clip(clip, length)
    if piece == 'shot':
        return held_to(slice_clip(clip, 0.0, cut) if cut else clip, length)
    if piece == 'bolt':
        return slice_clip(clip, cut, float(clip.times[-1])) if cut is not None else None
    return clip


def grip_weights(clip_name: str, frames: int) -> 'np.ndarray | None':
    """Per frame, how far FO4 clip `clip_name`'s left hand is on vanilla's grip: eased in or out over REACH's
    clips, fully elsewhere; None where FNV's own left hand plays (OWN_LEFT)."""
    if clip_name in OWN_LEFT:
        return None
    t = np.linspace(0.0, 1.0, frames)
    ease = t * t * (3.0 - 2.0 * t)
    return {1: ease, -1: ease[::-1]}.get(REACH.get(clip_name), np.ones(frames))


def slerp(a: np.ndarray, b: np.ndarray, w: float) -> np.ndarray:
    """Unit quaternion `w` of the way from `a` to `b` (wxyz), the short way round."""
    b = b if np.dot(a, b) >= 0 else -b
    angle = math.acos(min(1.0, float(np.dot(a, b))))
    q = a if angle < 1e-6 else (math.sin((1 - w) * angle) * a + math.sin(w * angle) * b) / math.sin(angle)
    return q / np.linalg.norm(q)


def toward(start: np.ndarray, end: np.ndarray, w: float) -> np.ndarray:
    """Row-vector frame `w` of the way from `start` to `end` (position lerped, rotation slerped)."""
    if w >= 1.0:
        return end
    q = slerp(mat_to_quat_wxyz(start[:3, :3]), mat_to_quat_wxyz(end[:3, :3]), w)
    return compose(start[3, :3] + w * (end[3, :3] - start[3, :3]), quat_wxyz_to_mat(q))


def curl_left(moved, curl: dict, weights: np.ndarray) -> None:
    """Left fingers turned `weights` (per frame) to `curl` ({bone: wxyz})."""
    for t in moved.tracks:
        if t.bone in curl and t.rotations is not None:
            t.rotations = np.array([slerp(np.asarray(q, float), curl[t.bone], w) for q, w in zip(t.rotations, weights)])


def finish(rig: Rig, gun: 'Gun', clip, moved, held: np.ndarray, vanilla, grip: tuple) -> None:
    """Retargeted `moved` (of FNV `clip`) with the gun held and the left hand on the grip (`grip`: its frame,
    grip_weights and finger curl; Gun.tracks, curl_left), the forearm twist shared, the bones FNV lacks from
    `vanilla` and every rotation track continuous, in place."""
    frame, weights, curl = grip
    moved.tracks += gun.tracks(rig, clip, moved, held, frame, weights)
    if weights is not None and frame is not None:
        curl_left(moved, curl, weights)
    share_twist(rig, moved)
    fill_from(moved, vanilla, rig)
    continuous(moved)


def vanilla_finger(anim, rig: Rig) -> np.ndarray:
    """Vanilla clip `anim`'s left middle-finger base in its Weapon frame, first frame."""
    world = vanilla_worlds(anim, rig.dst, 0)
    return (world[rig.dst.index[GRIP_FINGER]] @ np.linalg.inv(world[rig.dst.index[WEAPON]]))[3, :3]


def fnv_finger(rig: Rig, gun: 'Gun', clip) -> np.ndarray:
    """FNV `clip`'s left middle-finger base on our gun (Weapon frame), frame 0."""
    world = world_positions(clip, rig.src, 0)
    on_gun = np.linalg.inv(world[rig.src.index[FNV_WEAPON]]) @ gun.matrix
    return (world[rig.src.index[FNV_GRIP_FINGER]] @ on_gun)[3, :3]


def grip_gap(anim, rig: Rig, theirs: np.ndarray) -> 'float | None':
    """How far vanilla_finger sits from vertices `theirs`; None without both."""
    if anim is None or not len(theirs):
        return None
    return float(np.linalg.norm(theirs - vanilla_finger(anim, rig), axis=1).min())


def handle_frame(points: np.ndarray) -> 'np.ndarray | None':
    """A handle's frame (row-vector 4x4): its centre, its main directions longest first, each turned toward the
    gun axis it most follows (+X right, +Y ahead, +Z up), right-handed; None for under three points."""
    if len(points) < 3:
        return None
    centre = points.mean(0)
    axes = np.linalg.svd(points - centre, full_matrices=False)[2]
    axes = np.array([a if a[np.argmax(np.abs(a))] > 0 else -a for a in axes[:2]])
    out = np.eye(4)
    out[:3, :3] = np.vstack([axes, np.cross(axes[0], axes[1])])
    out[3, :3] = centre
    return out


def nearest_piece(pieces, point: np.ndarray) -> np.ndarray:
    """The one of vertex groups `pieces` nearest `point`."""
    return min(pieces, key=lambda p: float(np.linalg.norm(p - point, axis=1).min()))


def handle_grip(rig: Rig, gun: 'Gun', template, grip: np.ndarray, aim: Path) -> 'np.ndarray | None':
    """Vanilla's left grip `grip` (on the template's gun) carried onto our gun's handle: from the template piece
    (Gun.surfaces) nearest vanilla's left finger to ours nearest FNV's in aim clip `aim`, kept in each one's
    handle_frame; None without both or for handles held differently (long directions beyond SAME_WAY). FNV's
    `2hh` left fist grips the minigun's top handle, above every other heavy gun's (the Incinerator's post).
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    ours, theirs = gun.surfaces
    if not len(ours) or not len(theirs) or not aim.is_file():
        return None
    held = handle_frame(nearest_piece(theirs, vanilla_finger(template, rig)))
    ours_frame = handle_frame(nearest_piece(ours, fnv_finger(rig, gun, decoded_clip(str(aim))[0])))
    if held is None or ours_frame is None or abs(float(held[0, :3] @ ours_frame[0, :3])) < SAME_WAY:
        return None
    return grip @ np.linalg.inv(held) @ ours_frame


def left_reach(rig: Rig, gun: 'Gun', clip, gap: 'float | None') -> 'np.ndarray | None':
    """The Weapon-frame move putting FNV's left hand in FNV `clip` (first frame) on our gun: straight toward
    our gun's vertex (Gun.surfaces) nearest its middle finger's base, until that is `gap` from it (as vanilla
    holds its own gun); None when it already is that close or without the gap or vertices.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    ours = gun.points(0)
    if gap is None or not len(ours):
        return None
    finger = fnv_finger(rig, gun, clip)
    gaps = np.linalg.norm(ours - finger, axis=1)
    near = int(np.argmin(gaps))
    return (ours[near] - finger) * (1.0 - gap / gaps[near]) if gaps[near] > gap else None


def on_screen(points: np.ndarray) -> bool:
    """Whether any camera-space point (FO4's camera: looking down -Z, +Y up) is inside FO4's first-person view."""
    ahead = -points[:, 2]
    across = math.tan(math.radians(FO4_VIEW_FOV / 2))
    return bool(np.any((ahead > 0) & (np.abs(points[:, 0]) < ahead * across)
                       & (np.abs(points[:, 1]) < ahead * across * VIEW_ASPECT)))


def _in_camera(rig: Rig, gun: 'Gun', clip, moved) -> np.ndarray:
    """Our gun's camera-space frame at FNV `clip`'s start (`moved`: retargeted)."""
    return gun.inverse @ rig.fnv_gun(clip, 0) @ np.linalg.inv(rig.camera(moved, 0))


def off_screen(rig: Rig, gun: 'Gun', aim: Path) -> bool:
    """Whether FNV's aim clip `aim` holds all of the gun (Gun.surfaces) off FO4's screen (False without either)."""
    if not aim.is_file() or not len(gun.points(0)):
        return False
    clip = decoded_clip(str(aim))[0]
    held = _in_camera(rig, gun, clip, rig.retarget(clip))
    return not on_screen(np.hstack([gun.points(0), np.ones((len(gun.points(0)), 1))]) @ held)


def anchor_for(rig: Rig, gun: 'Gun', clip, moved, vanilla) -> np.ndarray:
    """Gun.anchor for FNV `clip` (`moved`: it retargeted): the camera-space move putting the gun where and as
    vanilla clip `vanilla` holds the template's in its first frame, FNV's motion from there kept.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    world = vanilla_worlds(vanilla, rig.dst, 0)
    theirs = world[rig.dst.index[WEAPON]] @ np.linalg.inv(world[rig.dst.index[rig.view.camera[1]]])
    return np.linalg.inv(_in_camera(rig, gun, clip, moved)) @ theirs


def neutral_clip(bones: list, length: float) -> DecodedClip:
    """A two-key clip of `length` seconds holding every one of `bones` at identity (an additive layer's no-op)."""
    times = np.array([0.0, length])
    return DecodedClip(name='neutral', duration=length, cycle_type=0, frequency=1.0, times=times,
                       tracks=[BoneTrack(bone=b, rotations=np.tile((1.0, 0.0, 0.0, 0.0), (2, 1)),
                                         translations=np.zeros((2, 3))) for b in bones])


def fnv_stem(kf_dir: Path, stem: str, sights: bool = True) -> str:
    """FNV clip `stem`, a sighted one unsighted when missing or not `sights`."""
    if stem.endswith(SIGHTED) and (not sights or not (kf_dir / f'{stem.replace(chr(92), "/")}.kf').is_file()):
        return stem[:-len(SIGHTED)]
    return stem


def vanilla_worlds(anim, dst: Skeleton, f: int) -> list:
    """Row-vector world frames of skeleton `dst` posed by vanilla clip `anim` at frame `f` (rest where untracked)."""
    out = []
    for i, p in enumerate(dst.parents):
        track = anim.tracks[i] if i < len(anim.tracks) and anim.tracks[i].rotations else None
        if track is None:
            local = dst.local[i]
        else:
            x, y, z, w = track.rotations[f]
            local = compose(np.asarray(track.translations[f], float), quat_wxyz_to_mat((w, x, y, z)))
        out.append(local if p < 0 else local @ out[p])
    return out


def left_grip(anim, rig: Rig) -> 'tuple | None':
    """Vanilla's left hand in clip `anim`'s first frame: (its frame relative to the Weapon bone, {left finger:
    local wxyz}); None without `anim`."""
    if anim is None:
        return None
    world = vanilla_worlds(anim, rig.dst, 0)
    curl = {}
    for i, bone in enumerate(rig.dst.names):
        if bone.startswith(LEFT_FINGER) and i < len(anim.tracks) and anim.tracks[i].rotations:
            x, y, z, w = anim.tracks[i].rotations[0]
            curl[bone] = np.array((w, x, y, z), float)
    return world[rig.dst.index[LEFT_HAND]] @ np.linalg.inv(world[rig.dst.index[WEAPON]]), curl


def left_targets(moved, vanilla: 'tuple | None') -> 'tuple | None':
    """(vanilla's left hand in the Weapon frame from left_grip `vanilla`, ours from retargeted `moved`'s
    WeaponIKTargetL first frame); None without either (a pistol holding vanilla's grip writes no target)."""
    track = next((t for t in moved.tracks if t.bone == IK_LEFT), None)
    if track is None or vanilla is None:
        return None
    return vanilla[0], compose(np.asarray(track.translations[0], float), quat_wxyz_to_mat(track.rotations[0]))


def carried_target(anim, index: int, left: tuple) -> None:
    """Third-person clip `anim`'s WeaponIKTargetL track (bone `index`) moved onto our gun, in place: each frame
    keeps the hand-local offset vanilla's target has from vanilla's first-person left hand (`left`: left_targets).
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    vanilla, ours = left
    move = np.linalg.inv(vanilla) @ ours
    track = anim.tracks[index]
    for f, ((x, y, z, w), at) in enumerate(zip(track.rotations, track.translations)):
        target = compose(np.asarray(at, float), quat_wxyz_to_mat((w, x, y, z))) @ move
        qw, qx, qy, qz = mat_to_quat_wxyz(target[:3, :3])
        track.rotations[f], track.translations[f] = [qx, qy, qz, qw], list(target[3, :3])


def continuous(clip) -> None:
    """Each of `clip`'s rotation tracks kept on one quaternion hemisphere, frame to frame, in place."""
    for t in clip.tracks:
        if t.rotations is not None:
            for k in range(1, len(t.rotations)):
                if np.dot(t.rotations[k], t.rotations[k - 1]) < 0:
                    t.rotations[k] = -t.rotations[k]


def _arm_segment(dst: Skeleton, chain: list, di: int) -> 'int | None':
    """0 or 1 for a bone the upper arm or forearm turns (its nearest chain ancestor), 2 for the hand itself."""
    if di == chain[2]:
        return 2
    a = di
    while a >= 0 and a not in chain:
        a = dst.parents[a]
    return chain.index(a) if a in chain[:2] else None


@dataclass
class Gun:
    """An FNV gun in FO4's Weapon frame: FNV frame -> FO4 frame (`matrix`), and per receiver bone an FNV part
    moves, (the bone's receiver rest, the part's rest frame inverted, the part's FNV name)."""
    matrix: np.ndarray
    parts: dict
    frames: dict
    inverse: np.ndarray = field(init=False)
    #: (our gun's pieces, the template gun's): nif.gun.pieces, Weapon frame (left_reach, handle_grip).
    surfaces: tuple = ((), ())
    #: The Weapon-frame move putting FNV's left hand on the gun (left_reach), else None.
    reach: 'np.ndarray | None' = None
    #: A camera-space move put after FNV's gun placement (anchor_for), else None: FNV's own placement.
    anchor: 'np.ndarray | None' = None
    #: Whether its hold is moved off FNV's for being off screen (off_screen).
    moved: bool = False
    #: The first-person left hand in the Weapon frame in WPNIdleReady: (vanilla's on the template, ours), else None.
    left: 'tuple | None' = None

    def points(self, which: int) -> np.ndarray:
        """Every vertex of our gun (0) or the template's (1), Weapon frame."""
        return np.vstack(self.surfaces[which]) if len(self.surfaces[which]) else np.zeros((0, 3))

    def __post_init__(self):
        self.inverse = np.linalg.inv(self.matrix)

    @classmethod
    def build(cls, matrix: np.ndarray, frames: dict, receiver: dict) -> 'Gun':
        """The gun of FNV node `frames` (fnv_frames) on a receiver of {bone: rest 4x4}."""
        parts = {}
        for name, frame in frames.items():
            bone = bone_for(name, receiver) if name.startswith('##') else None
            if bone and bone not in parts:
                parts[bone] = (receiver[bone], np.linalg.inv(frame), name)
        return cls(matrix, parts, frames)

    def part_local(self, clip, name: str, frame: int) -> np.ndarray:
        """FNV part `name`'s frame at `frame` of `clip` (its rest where the clip has no channel)."""
        rest = self.frames[name]
        track = next((t for t in clip.tracks if t.bone == name), None)
        if track is None:
            return rest
        rot = quat_wxyz_to_mat(track.rotations[frame]) if track.rotations is not None else rest[:3, :3]
        at = track.translations[frame] if track.translations is not None else rest[3, :3]
        return compose(at, rot)

    def tracks(self, rig: Rig, src_clip, moved, held: np.ndarray, grip: np.ndarray, weights) -> list:
        """The Weapon, part and left-hand target tracks of a retargeted clip: the gun where FNV's is (camera
        shift applied; an `anchor` moves it in camera space), held in FO4's right hand at `held` (the Weapon
        bone's local in vanilla's hand: hold() bends the arm to it), its parts where FNV's clip moves them; the
        left hand as left_hand() puts it (`weights`: grip_weights per frame), the left target on it unless the
        hand is always on `grip`."""
        left = rig.dst.index[LEFT_HAND]
        aimed = grip is None or weights is None or weights.min() < 1.0
        out = {name: [] for name in (WEAPON, *([IK_LEFT] if aimed else []), *self.parts)}
        for f in range(len(src_clip.times)):
            placed = self.inverse @ rig.fnv_gun(src_clip, f)
            on_gun = None
            if self.anchor is not None:
                camera = rig.camera(moved, f)
                on_gun = world_positions(moved, rig.dst, f)[left] @ np.linalg.inv(placed)
                placed = placed @ np.linalg.inv(camera) @ self.anchor @ camera
            world = hold(rig, moved, f, np.linalg.inv(held) @ placed)
            out[WEAPON].append(held)
            world = self.left_hand(rig, moved, f, world, (placed, on_gun, grip, held), 0.0 if weights is None else weights[f])
            if aimed:
                out[IK_LEFT].append(world[left] @ np.linalg.inv(placed))
            for bone, (rest, rest_inv, name) in self.parts.items():
                out[bone].append(rest @ self.inverse @ rest_inv @ self.part_local(src_clip, name, f) @ self.matrix)
        return [_track(name, mats) for name, mats in out.items()]

    def left_hand(self, rig: Rig, moved, f: int, world: list, hold_at: tuple, weight: float) -> list:
        """Frame `f`'s worlds with the left arm bent to its target, `world` unchanged without one: `weight` of the
        way onto vanilla's grip (hold_at: gun frame, FNV's left hand on the unmoved gun or None, grip, held), else
        FNV's hand (on_gun, on the moved gun) moved `weight` of `reach`."""
        placed, on_gun, grip, held = hold_at
        left, hand = rig.dst.index[LEFT_HAND], rig.dst.index[HAND]
        if weight > 0.0 and grip is not None:
            return hold(rig, moved, f, toward(world[left], grip @ held @ world[hand], weight), LEFT_ARM)
        reach = weight > 0.0 and self.reach is not None
        if on_gun is None and not reach:
            return world
        target = (world[left] if on_gun is None else on_gun @ placed).copy()
        if reach:
            target[3, :3] += weight * (self.reach @ placed[:3, :3])
        return hold(rig, moved, f, target, LEFT_ARM)

    def sight_lift(self, rig: Rig, src_clip, moved) -> 'float | None':
        """How far above FO4's camera FNV's eye point (##SightingNode) sits in the clip's first frame, along
        the camera's up; None without one."""
        if SIGHTING not in self.frames or not rig.view.camera:
            return None
        eye = (self.frames[SIGHTING] @ rig.fnv_gun(src_clip, 0))[3, :3]
        camera = world_positions(moved, rig.dst, 0)[rig.dst.index[rig.view.camera[1]]]
        return float(np.dot(eye - camera[3, :3], camera[1, :3]))


@dataclass
class Converted:
    """What a gun's clip conversion gives its records: {template Anims keyword: the gun's own replacing it} (one
    per view), the sights' camera lift, the clips written, and whether the hold was moved for being off screen."""
    replaces: dict
    lift: 'float | None'
    clips: dict
    moved: bool = False


class GunClips:
    """Converts FNV guns' clips onto vanilla guns' behaviour graphs; every gun's entries go in one additive race."""

    def __init__(self, fo4: bytes, export_meshes: Path, data_dir: Path):
        """Index Fallout4.esm's human subgraph entries (`fo4` the plugin's bytes) and the archives' AnimTextData;
        clips read from `export_meshes`, files written under `data_dir`."""
        self.export_meshes, self.data_dir = export_meshes, data_dir
        self.archives = Archives(FALLOUT4_DIR / 'Data', ANIMATIONS)
        race = next(list(subrecords(r.body)) for r, _ in walk(fo4, b'RACE') if r.form_id == HUMAN_SUBGRAPHS)
        self.race_subs, self.entries = race, subgraph_entries(race)
        self.player = next(r.form_id for r, _ in walk(fo4, b'KYWD') if first_sub(r.body, b'EDID') == PLAYER.encode() + b'\0')
        self.anim_text = {int(n[len(ANIM_TEXT):-4]): n for n in self.archives.names(ANIM_TEXT)
                          if n[len(ANIM_TEXT):-4].isdigit()}
        self.rigs, self.added, self.headers, self.written = {}, [], {}, []
        self.third = fo4_skeleton(self.archives.read(THIRD_SKELETON))[0]

    def rig(self, view: View) -> Rig:
        """The rig of `view`, loaded once."""
        if view not in self.rigs:
            self.rigs[view] = Rig.load(view, self.export_meshes, self.archives)
        return self.rigs[view]

    def template_entries(self, keywords: list, carried: 'set | None' = None) -> dict:
        """{perspective: (keyword-only weapon entry, the player's entry else that one, the keyword it replaces)}
        of the template: per view the most specific entry whose targets it carries in full (`carried`, with
        `keywords`, those a gun's own may replace, in order). The replaced one is its target keying the fewest
        entries: a modular gun's receiver or grip keyword, not the shared AnimsGripPistol. The player's entry
        carries the events the player hears.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        carried = set(keywords) | (carried or set())
        uses = collections.Counter(k for e in self.entries for k in e['target'])
        found = {}
        for e in self.entries:
            own = sorted((k for k in e['target'] if k in keywords), key=lambda k: (uses[k], keywords.index(k)))
            if own and set(e['target']) <= carried and e['actor'] in ([], [self.player]) and \
                    struct.unpack_from('<H', e['flags'])[0] == ROLE_WEAPON:
                found.setdefault((perspective(e), tuple(e['target'])), {})[bool(e['actor'])] = (e, own[0])
        out = {}
        ranked = sorted(found.items(), key=lambda item: (-len(item[0][1]),
                                                          keywords.index(next(iter(item[1].values()))[1])))
        for (view, targets), pair in ranked:
            if False in pair and view not in out:
                (entry, kw), heard = pair[False], pair.get(True, pair[False])[0]
                out[view] = (entry, heard, kw)
        return out

    @staticmethod
    def _clip_paths(files: list) -> dict:
        """{clip name, lower case: resolved path} of AnimTextData files."""
        return {line.rsplit('\\', 1)[-1].lower()[:-4]: line for _, lines in files for line in lines[4:]}

    def _resolved(self, entry: dict) -> list:
        """The vanilla AnimTextData files (id, lines) of an entry's folder list."""
        high = crc('|'.join(entry['paths']))
        return [(fid, self.archives.read(name).decode('cp1252').splitlines())
                for fid, name in sorted(self.anim_text.items()) if fid >> 32 == high]

    def _template_anim(self, resolved: dict):
        """The first of the template's HELD_FROM clips that reads (`resolved`: its clip paths); None without one."""
        for name in HELD_FROM:
            anim = parse_fo4_animation(self.archives.read('meshes\\' + resolved[name].lower())) \
                if name in resolved else None
            if anim:
                return anim
        return None

    @staticmethod
    def _held(anim, rig: Rig) -> np.ndarray:
        """The Weapon bone's local in the hand (row-vector 4x4) in vanilla clip `anim`, else the skeleton's rest."""
        i = rig.dst.index[WEAPON]
        if anim and i < len(anim.tracks) and anim.tracks[i].rotations:
            x, y, z, w = anim.tracks[i].rotations[0]
            return compose(np.asarray(anim.tracks[i].translations[0], float), quat_wxyz_to_mat((w, x, y, z)))
        return rig.dst.local[i]

    def _header(self, path: str):
        """A vanilla clip's fo4_animation_header (length, events, blend hint)."""
        if path not in self.headers:
            self.headers[path] = fo4_animation_header(self.archives.read('meshes\\' + path.lower()))
        return self.headers[path]

    def _neutral_layers(self, rig: Rig, resolved: dict, folder: str, written: dict) -> dict:
        """Write a clip moving nothing (its length and events kept) in `folder` for each additive layer of the
        template's (`resolved`) not `written`: its pitch, turn, sway and jiggle were authored on its own hold
        and pull a converted gun's arms about (the Varmint Rifle's into the camera), and FNV's first person has none;
        {clip name: NEUTRAL}.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        mine, out = {name.lower() for name in written}, {}
        for name, path in resolved.items():
            header = None if name in mine else self._header(path)
            if header is None or header.blend_hint != ADDITIVE:
                continue
            anim = clip_to_animation_data(neutral_clip(rig.dst.names, header.duration), rig.dst.names, rig.pose,
                                          [(a.time, a.text) for a in header.annotations])
            anim.bone_names, anim.blend_hint = [''] * len(rig.dst.names), ADDITIVE
            target = self._write_clip(folder, path, anim)
            out[target.stem] = NEUTRAL
        return out

    def _vanilla(self, path: str) -> tuple:
        """(annotations, length, clip) of a vanilla clip; ([], 0, None) if not spline."""
        anim = parse_fo4_animation(self.archives.read('meshes\\' + path.lower()))
        return ([(a.time, a.text) for a in anim.annotations], anim.duration, anim) if anim else ([], 0.0, None)

    def convert(self, rec: dict, keywords: tuple, own_keyword, gun_path: Path, receiver: dict,
                placement: np.ndarray, surfaces: tuple) -> 'Converted | None':
        """_convert(), kept in the work cache by everything it reads (_inputs) with the files it writes: a replay
        writes them again (touched when unchanged) and adds the gun's entries.
        See: docs/fork/fo4_plugin_layout.md#stage-times
        """
        args = (rec, keywords, own_keyword, gun_path, receiver, placement, surfaces)
        made, added, files = cached(CLIP_SITE, __name__, self._inputs(*args), lambda: self._recorded(args))
        for rel, data in files.items():
            write_new(self.data_dir / rel, data)
        self.added += added
        return made

    def _recorded(self, args: tuple) -> tuple:
        """(_convert(*args), the entries it adds, {data-folder path: bytes} of the files it writes); the entries
        are left for convert() to add."""
        start, self.written = len(self.added), []
        made = self._convert(*args)
        added, self.added = self.added[start:], self.added[:start]
        return made, added, {p.relative_to(self.data_dir).as_posix(): p.read_bytes() for p in dict.fromkeys(self.written)}

    def _inputs(self, rec: dict, keywords: tuple, own_keyword, gun_path: Path, *shape) -> tuple:
        """What _convert reads beyond Fallout4.esm: its cache key's parts."""
        own = tuple(own_keyword(k) for k in keywords[0])
        return (tuple(rec.get(k) for k in REC_FIELDS), tuple(keywords[0]), tuple(sorted(keywords[1] or ())), own,
                gun_path.read_bytes(), pickle.dumps(shape, protocol=5), self.fnv_digest)

    @functools.cached_property
    def fnv_digest(self) -> str:
        """A hash of every file in the views' FNV clip folders (clips and skeleton) in every export layer, read once."""
        digest, meshes = hashlib.sha1(), self.export_meshes
        roots = [Path(f).joinpath(*meshes.parts) for f in meshes.folders] if isinstance(meshes, Layered) else [meshes]
        for folder in (Path(root) / view.fnv for root in roots for view in VIEWS):
            for path in sorted(p for p in folder.rglob('*') if p.is_file()):
                digest.update(str(path)[len(str(folder)):].lower().encode() + b'\0' + path.read_bytes())
        return digest.hexdigest()

    def _convert(self, rec: dict, keywords: tuple, own_keyword, gun_path: Path, receiver: dict,
                 placement: np.ndarray, surfaces: tuple) -> 'Converted | None':
        """Write FNV gun `rec`'s clips (its NIF at `gun_path`, built on a receiver of {bone: rest 4x4}, put in its
        frame by `placement`: nif.gun.placement; `surfaces`: Gun.surfaces) under the template's clip names, given
        `keywords` (its KWDA list, every keyword its parts give it: template_entries) and `own_keyword` (a template
        keyword -> the FormID of the gun's own taking it); None when the template has no weapon entry it carries or
        FNV's class has no clips."""
        entries = self.template_entries(*keywords)
        cls = ANIM_TYPE_CLASS.get(int(rec.get('DNAM.FalloutAnimType', -1)))
        if not entries or cls is None:
            return None
        gun = Gun.build(placement, fnv_frames(gun_path), receiver)
        gun.surfaces = surfaces
        names = {'attack': ATTACK_ANIMS.get(int(rec.get('DNAM.AttackAnim', 255))) or ATTACK_ACTIONS[0],
                 'letter': RELOAD_LETTERS[int(rec.get('DNAM.ReloadAnim', 0))],
                 'auto': bool(int(rec.get('DNAM.Flags1', 0)) & FNV_AUTOMATIC),
                 'sights': not int(rec.get('DNAM.Flags1', 0)) & FNV_NO_SIGHTS}
        written, lift, replaces = {}, None, {}
        for view in VIEWS:
            if view.perspective not in entries:
                continue
            entry, heard, kw = entries[view.perspective]
            replaces[kw] = keyword = own_keyword(kw)
            folder = f'{view.folder}\\{rec["EditorID"]}'
            files = self._resolved(entry)
            events = {**self._clip_paths(files), **self._clip_paths(self._resolved(heard))}
            written[view.perspective], view_lift = self._view(view, cls, names, gun, folder, files, events)
            lift = view_lift if view_lift is not None else lift
            self._anim_text(entry, folder, files, written[view.perspective])
            self.added.append(aimed(dict(entry, paths=with_folder(entry['paths'], folder)), kw, keyword))
        self.added += [aimed(self._with_assembly(gun, rec['EditorID'], e), kw, keyword)
                       for kw, keyword in replaces.items() for e in self.entries
                       if kw in e['target'] and perspective(e) not in written]
        return Converted(replaces, lift, written, gun.moved)

    def _with_assembly(self, gun: Gun, edid: str, entry: dict) -> dict:
        """Third-person `entry` searching first a folder of FNV gun `edid`'s own holding its WPNAssemblyPose with
        the left hand's target on our gun (carried_target); `entry` unchanged without our left hand or a vanilla
        pose on the human third-person skeleton.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        files = self._resolved(entry)
        path = self._clip_paths(files).get(ASSEMBLY.lower())
        anim = parse_fo4_animation(self.archives.read('meshes\\' + path.lower())) if path and gun.left else None
        if anim is None or len(anim.tracks) != len(self.third.names):
            return entry
        carried_target(anim, self.third.index[IK_LEFT], gun.left)
        folder = '\\'.join((THIRD_FOLDER, edid, *path.split('\\')[-3:-1]))
        self._write_clip(folder, path, anim)
        self._anim_text(entry, folder, files, {ASSEMBLY: ASSEMBLY})
        return dict(entry, paths=with_folder(entry['paths'], folder))

    @staticmethod
    def _hold_rules(rig: Rig, gun: Gun, aim: Path, template, grip: tuple, one_handed: bool) -> tuple:
        """(off_screen: clips start at vanilla's hold, also on `gun`; left_reach's gap; the left grip, carried
        onto our handle for a moved gun (handle_grip); whether the left hand takes it)."""
        vanilla_left = grip[0] is not None and one_handed
        gun.moved = not vanilla_left and template is not None and off_screen(rig, gun, aim)
        if gun.moved and grip[0] is not None:
            grip = (handle_grip(rig, gun, template, grip[0], aim), grip[1])
            vanilla_left = grip[0] is not None
        gap = None if vanilla_left else grip_gap(template, rig, gun.points(1))
        return gun.moved, gap, grip, vanilla_left

    def _view(self, view: View, cls: str, names: dict, gun: Gun, folder: str, files: list, events: dict) -> tuple:
        """Write one view's clips into `folder`, each with the events of the vanilla clip `events` resolves its
        name to; ({FO4 clip: FNV stem}, the iron sights' camera lift)."""
        rig = self.rig(view)
        resolved = self._clip_paths(files)
        kf_dir = self.export_meshes / view.fnv
        bolt = next((p[2] for b, p in gun.parts.items() if b == 'WeaponBolt'), None)
        template = self._template_anim(resolved)
        out, lift, held, grip = {}, None, self._held(template, rig), left_grip(template, rig) or (None, {})
        moving, gap, grip, vanilla_left = self._hold_rules(rig, gun, kf_dir / f'{cls}aim.kf', template, grip,
                                                          cls == ONE_HANDED)
        for clip_name, action, piece in PLAN[view.perspective]:
            stem = fnv_stem(kf_dir, action.format(cls=cls, **names), names['sights'])
            kf = kf_dir / f'{stem.replace(chr(92), "/")}.kf'
            if clip_name.lower() not in resolved or not kf.is_file() or (piece == 'loop' and not names['auto']):
                continue
            clip = decoded_clip(str(kf))[0]
            vanilla, length, anim = self._vanilla(events[clip_name.lower()])
            clip = cut_piece(clip, piece, length, bolt_start(clip, bolt) if BOLT_CLIP.lower() in resolved else None)
            if clip is None:
                continue
            moved = rig.retarget(clip)
            gun.anchor = anchor_for(rig, gun, clip, moved, anim or template) if moving else None
            gun.reach = left_reach(rig, gun, clip, gap)
            weights = grip_weights(clip_name, len(clip.times)) if vanilla_left or gun.reach is not None else None
            finish(rig, gun, clip, moved, held, anim or template, (grip[0] if vanilla_left else None, weights, grip[1]))
            anim = clip_to_animation_data(moved, rig.dst.names, rig.pose,
                                          annotations(vanilla, length, clip.text_keys, float(clip.duration)))
            anim.bone_names = [''] * len(rig.dst.names)
            self._write_clip(folder, resolved[clip_name.lower()], anim)
            out[clip_name] = stem + (f' ({piece})' if piece else '')
            if clip_name == 'WPNIdleSighted':
                lift = gun.sight_lift(rig, clip, moved)
            if clip_name == HELD_POSE:
                gun.left = left_targets(moved, left_grip(template, rig))
        out.update(self._neutral_layers(rig, resolved, folder, out))
        return out, lift

    def _anim_text(self, entry: dict, folder: str, files: list, written: dict) -> None:
        """Each of the template entry's AnimTextData files again under the new folder list's id, the clips
        written pointed at `folder`."""
        mine = {name.lower() for name in written}
        high = crc('|'.join(with_folder(entry['paths'], folder)))
        out_dir = self.data_dir / 'Meshes' / 'AnimTextData' / 'AnimationFileData'
        out_dir.mkdir(parents=True, exist_ok=True)
        for fid, lines in files:
            new_id = high << 32 | fid & 0xFFFFFFFF
            body = lines[:2] + [str(new_id)] + lines[3:4] + [
                f'{folder}\\{line.rsplit(chr(92), 1)[-1]}'
                if line.rsplit('\\', 1)[-1].lower()[:-4] in mine else line for line in lines[4:]]
            (out_dir / f'{new_id}.txt').write_bytes(('\r\n'.join(body) + '\r\n').encode('cp1252'))
            self.written.append(out_dir / f'{new_id}.txt')

    def _write_clip(self, folder: str, vanilla: str, anim) -> Path:
        """Write `anim` into `folder` under vanilla clip path `vanilla`'s file name, recorded (_recorded); the path."""
        path = self.data_dir / 'Meshes' / folder / vanilla.rsplit('\\', 1)[-1]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_fo4_animation(str(path), anim)
        self.written.append(path)
        return path

    def race(self, edid: str, own=None) -> 'list | None':
        """The additive race's subrecords holding every converted gun's entries, or only those targeting a keyword
        `own` accepts (None without any): DLC06's additive head filled from HumanRaceSubGraphData, SADD on it, then
        the entries."""
        added = [e for e in self.added if own is None or any(own(k) for k in e['target'])]
        if not added:
            return None
        seen, head = {}, []
        for sig in HEAD:
            k = seen[sig] = seen.get(sig, -1) + 1
            body = [b for s, b in self.race_subs if s == sig.encode()][k] if sig != 'EDID' else (edid + '\0').encode()
            head.append((sig.encode(), body))
        out = head + [(b'SADD', struct.pack('<I', HUMAN_SUBGRAPHS))]
        for entry in added:
            out += entry_subrecords(entry)
        return out
