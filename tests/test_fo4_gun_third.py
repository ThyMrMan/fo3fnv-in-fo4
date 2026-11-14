"""gun_third: a held stride walks on vanilla's legs while the upper body keeps FNV's pose; third-person entries
search the gun's own folder first."""

import math
from types import SimpleNamespace

import numpy as np

from asset_convert.havok.clip_retarget import Skeleton, compose, quat_wxyz_to_mat, world_positions
from asset_convert.havok.kf_decode import BoneTrack, DecodedClip
from fo4_import.havok import gun_clips as G
from fo4_import.havok import gun_third as T

NAMES = ['Root', 'COM', 'Pelvis', 'LLeg_Thigh', 'Spine1']
PARENTS = [-1, 0, 1, 2, 1]


def skeleton() -> Skeleton:
    """Root; COM over Pelvis (and a thigh) and Spine1; each 10 up from its parent."""
    return Skeleton(NAMES, PARENTS, [compose((0.0, 0.0, 10.0 * (i > 0)), np.eye(3)) for i in range(len(NAMES))])


def turn(angle: float) -> tuple:
    """A wxyz turn of `angle` radians about +Z."""
    return math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2)


def vanilla_walk(frames: int = 5) -> SimpleNamespace:
    """A vanilla clip (anim_fo4 form: x y z w) moving the root ahead and swinging the thigh."""
    tracks = []
    for i in range(len(NAMES)):
        w, x, y, z = turn(0.3 * i) if NAMES[i] == 'LLeg_Thigh' else (1.0, 0.0, 0.0, 0.0)
        rot = [[x, y, z, w] if NAMES[i] != 'LLeg_Thigh' else list(turn(0.1 * f)[1:]) + [turn(0.1 * f)[0]]
               for f in range(frames)]
        at = [[5.0 * f, 0.0, 0.0] if i == 0 else [0.0, 0.0, 10.0 + (i == 1) * 0.5 * f] for f in range(frames)]
        tracks.append(SimpleNamespace(rotations=rot, translations=at))
    return SimpleNamespace(tracks=tracks, duration=(frames - 1) / 30.0)


def test_stride_holds_the_first_pose_at_every_frame():
    """A stride is the clip's first pose at 30 per second for the length asked."""
    clip = DecodedClip(name='aim', duration=1.0, cycle_type=0, frequency=1.0, times=np.array([0.0, 1.0]),
                       tracks=[BoneTrack(bone='Spine1', rotations=np.array([turn(0.2), turn(0.9)]))])
    out = T.stride(clip, 0.5)
    assert len(out.times) == 16 and out.times[-1] == 0.5
    assert np.allclose(out.tracks[0].rotations, turn(0.2))


def test_walk_legs_puts_vanilla_legs_under_fnvs_upper_body():
    """Each frame's thigh lands where vanilla's is in the world, the root moves as vanilla's, and COM keeps FNV's
    turn (so the spine above it is FNV's)."""
    dst, anim = skeleton(), vanilla_walk()
    times = np.linspace(0.0, anim.duration, 5)
    moved = DecodedClip(name='m', duration=anim.duration, cycle_type=0, frequency=1.0, times=times, tracks=[
        BoneTrack(bone='COM', rotations=np.tile(turn(0.5), (5, 1)), translations=np.tile((0.0, 0.0, 30.0), (5, 1))),
        BoneTrack(bone='Spine1', rotations=np.tile(turn(0.1), (5, 1)), translations=np.tile((0, 0, 10.0), (5, 1)))])
    T.walk_legs(moved, anim, dst)
    for f in range(5):
        ours, theirs = world_positions(moved, dst, f), T.vanilla_worlds(anim, dst, f)
        assert np.allclose(ours[dst.index['LLeg_Thigh']], theirs[dst.index['LLeg_Thigh']], atol=1e-6)
        assert np.allclose(ours[0][3, :3], (5.0 * f, 0.0, 0.0))
        assert np.allclose(ours[1][:3, :3], quat_wxyz_to_mat(turn(0.5)), atol=1e-6)
        assert np.allclose(ours[1][3, 2], theirs[1][3, 2])


def test_third_person_entries_search_the_guns_folder_first():
    """A third-person entry gets the gun's own folder before every vanilla one but paired, and its file data points
    the clips we wrote there."""
    clips = G.GunClips.__new__(G.GunClips)
    clips.written, clips.data_dir = [], None
    files = [(5, ['3', '1', '5', '2', 'Actors\\Character\\Animations\\Weapon\\Grip\\WPNIdleReady.hkx',
                  'Actors\\Character\\Animations\\Weapon\\Grip\\WPNReload.hkx'])]
    clips._resolved, wrote = (lambda entry: files), {}
    clips._anim_text = lambda entry, paths, f, moved: wrote.update(paths=paths, moved=moved)
    entry = {'paths': ['Actors\\Character\\Animations\\Paired', 'Actors\\Character\\Animations\\Weapon\\Grip']}
    gun = SimpleNamespace(left=None)
    out = clips._with_targets(gun, 'WeapX', entry, {}, ('Actors\\FNV\\Character\\Animations\\WeapX', {'wpnidleready'}))
    assert out['paths'] == ['Actors\\Character\\Animations\\Paired', 'Actors\\FNV\\Character\\Animations\\WeapX',
                            'Actors\\Character\\Animations\\Weapon\\Grip']
    assert wrote['moved'] == {'wpnidleready': 'Actors\\FNV\\Character\\Animations\\WeapX'}


def test_each_entry_finds_the_stride_made_from_its_own_vanilla_walk():
    """A stride written for the player's walk is searched in the player's entry, in our mirror of the player
    folder, ahead of vanilla's; the gun's own folder is not used for it."""
    clips = G.GunClips.__new__(G.GunClips)
    walk = 'Actors\\Character\\Animations\\Weapon\\Pistol\\Player\\WPNWalkForwardReady.hkx'
    clips._resolved = lambda entry: [(5, ['3', '1', '5', '1', walk])]
    wrote = {}
    clips._anim_text = lambda entry, paths, f, moved: wrote.update(moved=moved)
    ours = T.gun_folder('WeapX', walk.rsplit('\\', 1)[0])
    entry = {'paths': ['Actors\\Character\\Animations\\Weapon\\Pistol\\Player']}
    out = clips._with_targets(SimpleNamespace(left=None), 'WeapX', entry, {walk.lower(): ours}, None)
    assert ours == 'Actors\\FNV\\Character\\Animations\\WeapX\\Weapon\\Pistol\\Player'
    assert out['paths'] == [ours, entry['paths'][0]] and wrote['moved'] == {'wpnwalkforwardready': ours}


def test_third_person_plan_strides_the_moving_clips():
    """PLAN[0] is first person's with every held moving clip a stride."""
    pieces = {clip: piece for clip, _, piece in G.PLAN[0]}
    assert pieces['WPNRunForwardReady'] == 'stride' and pieces['WPNWalkForwardSighted'] == 'stride'
    assert pieces['WPNIdleReady'] is None and len(G.PLAN[0]) == len(G.PLAN[1])
