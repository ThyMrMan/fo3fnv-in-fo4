"""Third person for converted FNV guns: where a gun's third-person copies go, vanilla poses on the human skeleton,
the left-hand target carried onto our gun, and FNV's held aim walking on vanilla's legs.

See: docs/fork/fo4_gun_animation.md#third-person-clips
"""

import numpy as np

from asset_convert.havok.clip_retarget import Skeleton, compose, mat_to_quat_wxyz, quat_wxyz_to_mat
from asset_convert.havok.kf_decode import BoneTrack, DecodedClip

#: The human third-person skeleton, and the folder a gun's own third-person clips and copies go in.
THIRD_SKELETON = 'meshes\\actors\\character\\characterassets\\skeleton.hkx'
THIRD_FOLDER = 'Actors\\FNV\\Character\\Animations'
#: Units a third-person clip's left-hand target may stray from WPNAssemblyPose's and still be on the gun (_on_gun).
ON_GUN = 12.0
#: The vanilla third-person root its folders lie under, and the folder holding paired clips.
THIRD_ROOT, PAIRED = 'actors\\character\\animations', 'paired'
#: The human skeleton's root (root motion), its centre of mass (the upper body's parent) and the legs' parent.
ROOT, COM, PELVIS = 'Root', 'COM', 'Pelvis'
#: Samples per second of a held stride (FNV's and vanilla's rate).
STRIDE_RATE = 30.0


def mirror(ours: str, folder: str) -> str:
    """The folder under `ours` mirroring vanilla third-person `folder`."""
    parts = folder.split('\\')
    tail = parts[3:] if folder.lower().startswith(THIRD_ROOT) else parts[-2:]
    return '\\'.join((ours, *tail))


def gun_folder(edid: str, folder: str) -> str:
    """FNV gun `edid`'s own third-person folder mirroring vanilla `folder`."""
    return mirror(f'{THIRD_FOLDER}\\{edid}', folder)


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


def stride(clip, length: float) -> DecodedClip:
    """FNV `clip`'s first pose held for `length` seconds at STRIDE_RATE: a moving clip's upper body, walk_legs
    giving it vanilla's legs frame by frame."""
    count = max(int(round(length * STRIDE_RATE)) + 1, 2)
    tracks = [BoneTrack(bone=t.bone, **{k: None if getattr(t, k) is None else np.repeat(getattr(t, k)[:1], count, 0)
                                        for k in ('translations', 'rotations', 'scales')}) for t in clip.tracks]
    return DecodedClip(name=clip.name, duration=length, cycle_type=clip.cycle_type, frequency=clip.frequency,
                       times=np.linspace(0.0, length, count), tracks=tracks, text_keys=[])


def leg_bones(dst: Skeleton) -> list:
    """The indices of `dst`'s Pelvis and every bone under it."""
    out = [dst.index[PELVIS]]
    for i, p in enumerate(dst.parents):
        if p in out:
            out.append(i)
    return out


def walk_legs(moved, anim, dst: Skeleton) -> None:
    """Retargeted moving clip `moved` (on human skeleton `dst`) given vanilla clip `anim`'s Root, COM position,
    Pelvis and legs per frame, in place: the legs where vanilla's are in the world, the root motion vanilla's, the
    upper body (COM's turn and above) FNV's.
    See: docs/fork/fo4_gun_animation.md#third-person-clips
    """
    root, com, legs = dst.index[ROOT], dst.index[COM], leg_bones(dst)
    frames = max(len(t.rotations) for t in anim.tracks if t.rotations)
    tracks = {t.bone: t for t in moved.tracks}
    out = {dst.names[i]: [] for i in (root, com, *legs)}
    for f, t in enumerate(moved.times):
        k = min(frames - 1, int(round(float(t) / float(anim.duration) * (frames - 1)))) if anim.duration else 0
        world = vanilla_worlds(anim, dst, k)
        turn = quat_wxyz_to_mat(tracks[COM].rotations[f]) if COM in tracks else world[com][:3, :3]
        ours = compose((world[com] @ np.linalg.inv(world[root]))[3, :3], turn) @ world[root]
        out[ROOT].append(world[root])
        out[COM].append(ours @ np.linalg.inv(world[root]))
        out[PELVIS].append(world[legs[0]] @ np.linalg.inv(ours))
        for i in legs[1:]:
            out[dst.names[i]].append(world[i] @ np.linalg.inv(world[dst.parents[i]]))
    kept = [t for t in moved.tracks if t.bone not in out]
    moved.tracks = kept + [BoneTrack(bone=b, rotations=np.array([mat_to_quat_wxyz(m[:3, :3]) for m in mats]),
                                     translations=np.array([m[3, :3] for m in mats])) for b, mats in out.items()]
