"""FNV gun clips on a vanilla FO4 gun's graph: AnimTextData ids, folder order, annotation timing, the bolt cut, the hold.

See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import struct
from types import SimpleNamespace

import numpy as np

from asset_convert.havok.clip_retarget import Skeleton
from asset_convert.havok.kf_decode import BoneTrack, DecodedClip
from fo4_import.havok.gun_clips import (FNV_GRIP_FINGER, ROLE_WEAPON, Gun, GunClips, annotations, bolt_start, crc,
                                        file_id, fnv_stem, handle_frame, left_reach, neutral_clip, on_screen, with_folder)
from fo4_import.spike.gun_choice import PROP_KEYWORDS, properties, traded

HUNTING_RIFLE = ['Actors\\Character\\Animations\\Weapon\\HuntingRifle',
                 'Actors\\Character\\Animations\\Weapon\\Rifle\\Neutral',
                 'Actors\\Character\\Animations\\Weapon\\GripRifleStraight',
                 'Actors\\Character\\Animations\\Paired', 'Actors\\Character\\Animations']
LIGHTNING_GUN = ['Actors\\DLC01\\Character\\Animations\\LightningGun',
                 'Actors\\Character\\Animations\\Weapon\\Rifle\\Neutral',
                 'Actors\\Character\\Animations\\Paired', 'Actors\\Character\\Animations']


def test_file_ids_match_vanilla():
    """Ids of files the game ships: the hunting rifle's (Fallout4 - Animations.ba2) and DLC01's lightning gun's."""
    assert crc('|'.join(HUNTING_RIFLE)) == 3461649414
    assert crc('Actors\\Character\\Behaviors\\WeaponBehavior.hkx') == 2796883870
    assert crc('Actors\\Character\\_1stPerson\\Behaviors\\GunBehavior.hkx') == 4210333847
    assert file_id(LIGHTNING_GUN, 'Actors\\Character\\Behaviors\\RightArmInjuredWeaponWrappingBehavior.hkx') \
        == 10448007346973008486


def test_gun_folder_goes_after_paired_folders():
    """The gun's folder is searched first, after the paired-animation folders."""
    first_person = ['Actors\\Character\\_1stPerson\\Animations\\Paired',
                    'Actors\\Character\\_1stPerson\\Animations\\HuntingRifle']
    assert with_folder(first_person, 'X') == [first_person[0], 'X', first_person[1]]
    assert with_folder(HUNTING_RIFLE, 'X')[0] == 'X'


def test_annotations_follow_fnv_keys_else_scale():
    """Vanilla events take FNV's matching keys (sounds in order), the rest scale with the clip."""
    vanilla = [(0.033, 'SoundPlay.MagOut'), (1.067, 'SoundPlay.MagIn'), (2.0, 'reloadComplete'),
               (2.6, 'EjectShellCasing'), (3.933, 'initiateStart')]
    keys = [(0.0, 'start'), (0.25, 'Sound: Pt1'), (0.55, 'Sound: Pt2'), (0.8, 'Eject'), (1.2, 'a:8')]
    assert annotations(vanilla, 4.0, keys, 2.0) == [
        (0.25, 'SoundPlay.MagOut'), (0.55, 'SoundPlay.MagIn'), (0.8, 'EjectShellCasing'),
        (1.0, 'reloadComplete'), (3.933 / 2, 'initiateStart')]


def test_bolt_starts_the_frame_before_it_moves():
    """The cut falls the frame before the bolt part first moves; no track, no cut."""
    times = np.arange(6) / 30.0
    bolt = np.zeros((6, 3))
    bolt[3:, 0] = 1.0
    clip = DecodedClip(name='a', duration=times[-1], cycle_type=0, frequency=1.0, times=times,
                       tracks=[BoneTrack(bone='##VRBolt', translations=bolt)])
    assert bolt_start(clip, '##VRBolt') == times[2]
    assert bolt_start(clip, '##Other') is None


def test_a_missing_sighted_clip_falls_back_to_the_aim_clip(tmp_path):
    """FNV aims with the aim clip where its class lacks iron-sight clips or the gun says not to use them."""
    for name in ('2hlaim.kf', '2haaim.kf', '2haaimis.kf'):
        (tmp_path / name).write_bytes(b'')
    assert fnv_stem(tmp_path, '2hlaimis') == '2hlaim'
    assert fnv_stem(tmp_path, '2haaimis') == '2haaimis'
    assert fnv_stem(tmp_path, '2hlattack3') == '2hlattack3'
    assert fnv_stem(tmp_path, '2haaimis', sights=False) == '2haaim'


def test_on_screen_needs_a_point_ahead_inside_fo4s_view():
    """Ahead in the middle is on screen; behind the eye or far below the view is not."""
    assert on_screen(np.array([[0.0, -5.0, -30.0]]))
    assert not on_screen(np.array([[0.0, 0.0, 10.0]]))
    assert not on_screen(np.array([[10.0, -40.0, -20.0], [0.0, 0.0, 5.0]]))


def test_left_reach_moves_fnvs_hand_onto_the_gun_to_vanillas_gap():
    """FNV's finger 10 above the gun's nearest vertex moves down to vanilla's 2-unit gap; one already that close
    stays."""
    skeleton = Skeleton(["Weapon", FNV_GRIP_FINGER], [-1, 0], [np.eye(4), np.eye(4)])
    skeleton.local[1][3, :3] = (0.0, 0.0, 10.0)
    skeleton.world = skeleton.fk(skeleton.local)
    clip = DecodedClip(name='aim', duration=0.0, cycle_type=0, frequency=1.0, times=np.zeros(1), tracks=[])
    gun = Gun(np.eye(4), {}, {})
    gun.surfaces = ([np.array([[0.0, 0.0, 0.0], [50.0, 0.0, 0.0]])], [])
    rig = SimpleNamespace(src=skeleton)
    assert np.allclose(left_reach(rig, gun, clip, 2.0), (0.0, 0.0, -8.0))
    assert left_reach(rig, gun, clip, 12.0) is None


def test_a_modular_guns_entry_needs_its_grip_and_its_own_keyword():
    """A laser gun's clips key on the grip mod's AnimsGripPistol plus the receiver's keyword (both from parts), the
    most specific entry it carries wins, the replaced keyword is the gun's own one, never the shared grip's."""
    grip, laser, player = 1, 2, 9

    def entry(targets, view, actor=()):
        return {'target': list(targets), 'actor': list(actor), 'flags': struct.pack('<HH', ROLE_WEAPON, view)}

    pair, shared, player_pair = entry((grip, laser), 1), entry((grip,), 1), entry((grip, laser), 1, (player,))
    owner = SimpleNamespace(entries=[shared, pair, player_pair, entry((grip, laser, 7), 1)], player=player)
    found = GunClips.template_entries(owner, [laser, grip], {grip, laser})
    assert found == {1: (pair, player_pair, laser)}
    assert GunClips.template_entries(owner, [laser], set()) == {}


def test_traded_swaps_only_the_replaced_keyword_properties():
    """An OMOD's keyword properties take the gun's own keyword; other properties and keywords are kept."""
    props = [(4, 2, PROP_KEYWORDS, 100), (4, 2, PROP_KEYWORDS, 200), (2, 0, 25, 100)]
    data = bytes(4) + struct.pack('<I', len(props)) + bytes(8) + b''.join(
        struct.pack('<B3xB3xH2xI4x4x', t, f, p, v) for t, f, p, v in props)
    swapped = [struct.unpack('<I', v)[0] for _, _, _, v in properties(traded(data, {100: 555}))]
    assert swapped == [555, 200, 100]


def test_a_neutral_layer_holds_every_bone_at_identity_for_the_layers_length():
    """An additive layer's stand-in moves nothing: identity rotation, no translation, over the vanilla length."""
    clip = neutral_clip(['RArm_Hand', 'LArm_Hand'], 0.333)
    assert clip.duration == 0.333 and list(clip.times) == [0.0, 0.333]
    assert [t.bone for t in clip.tracks] == ['RArm_Hand', 'LArm_Hand']
    for t in clip.tracks:
        assert np.allclose(t.rotations, (1.0, 0.0, 0.0, 0.0)) and np.allclose(t.translations, 0.0)


def test_a_handle_frame_follows_its_longest_direction_turned_to_the_gun_axes():
    """A vertical post's frame has its long axis up and its centre at the post's middle; too few points, none."""
    post = np.array([[0.0, 30.0, z] for z in np.linspace(-20.0, -4.0, 9)] + [[1.0, 30.0, -12.0], [0.0, 31.0, -12.0]])
    frame = handle_frame(post)
    assert np.allclose(frame[0, :3], (0.0, 0.0, 1.0), atol=1e-6)
    assert np.allclose(frame[3, :3], post.mean(0))
    assert handle_frame(post[:2]) is None
