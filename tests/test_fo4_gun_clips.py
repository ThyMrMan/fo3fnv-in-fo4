"""FNV gun clips on a vanilla FO4 gun's graph: AnimTextData ids, folder order, annotation timing, the bolt cut, the hold.

See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import collections
import functools
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from asset_convert.havok.clip_retarget import Skeleton, compose, mat_to_quat_wxyz, quat_wxyz_to_mat
from asset_convert.havok.kf_decode import BoneTrack, DecodedClip
from external.pynifly_hkx.anim_fo4 import TrackData
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.havok.gun_clips import (CLIP_SITE, FNV_GRIP_FINGER, GUN_CLIPS_VERSION, IK_LEFT, ROLE_WEAPON, VIEWS,
                                        Converted, Gun, GunClips, annotations, bolt_start, carried_target, crc,
                                        file_id, fnv_stem, handle_frame, is_kept, keep, kept, left_reach, left_targets,
                                        neutral_clip, on_screen, owned, placeholder, with_folder)
from fo4_import.havok import kf_cache as KC
from fo4_import.havok.gun_clip_pool import warm
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import work_cache as WC
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.export_index import Layered, asset_root, export_records
from fo4_import.spike.gun_choice import PROP_KEYWORDS, built_in_scope, properties, traded
from fo4_import.spike.guns import Guns
from tes5_import.base.tes5_reader import first_sub, walk
from tests.fo4_versions import check

#: The FNV export the reference guns come from, and those guns: a two-handed bolt rifle and a one-handed pistol.
EXPORT = ROOT / 'export' / 'FalloutNV.esm'
REFERENCE_GUNS = ('WeapNVVarmintRifle', 'WeapNV9mmPistol')
#: A rifle's record fields (anim type 5: class 2hr) for keys over test layers.
RIFLE = {'EditorID': 'WeapX', 'DNAM.FalloutAnimType': '5', 'DNAM.AttackAnim': '68', 'DNAM.ReloadAnim': '12',
         'DNAM.Flags1': '4'}

HUNTING_RIFLE = ['Actors\\Character\\Animations\\Weapon\\HuntingRifle',
                 'Actors\\Character\\Animations\\Weapon\\Rifle\\Neutral',
                 'Actors\\Character\\Animations\\Weapon\\GripRifleStraight',
                 'Actors\\Character\\Animations\\Paired', 'Actors\\Character\\Animations']
LIGHTNING_GUN = ['Actors\\DLC01\\Character\\Animations\\LightningGun',
                 'Actors\\Character\\Animations\\Weapon\\Rifle\\Neutral',
                 'Actors\\Character\\Animations\\Paired', 'Actors\\Character\\Animations']


def test_third_persons_left_target_keeps_vanillas_offset_from_the_first_person_hand():
    """Each frame's WeaponIKTargetL sits off our first-person left hand as vanilla's sits off vanilla's (hand-local);
    a gun whose left hand writes no target (a pistol on vanilla's grip) gives none."""
    def frame(at, turn):
        """A row-vector 4x4 at `at` turned `turn` radians about z."""
        return compose(np.array(at, float), quat_wxyz_to_mat((np.cos(turn / 2), 0.0, 0.0, np.sin(turn / 2))))
    vanilla, ours, targets = frame((0, 10, 0), 0.0), frame((1, 12, -2), 0.6), [frame((-5, 15, -2), 0.1),
                                                                                frame((-4, 16, -2), 0.2)]
    track = TrackData(rotations=[list(mat_to_quat_wxyz(t[:3, :3])[1:]) + [mat_to_quat_wxyz(t[:3, :3])[0]] for t in targets],
                      translations=[list(t[3, :3]) for t in targets])
    carried_target(SimpleNamespace(tracks=[track]), 0, (vanilla, ours))
    for f, before in enumerate(targets):
        x, y, z, w = track.rotations[f]
        after = compose(np.asarray(track.translations[f]), quat_wxyz_to_mat((w, x, y, z)))
        assert np.allclose(after @ np.linalg.inv(ours), before @ np.linalg.inv(vanilla), atol=1e-5)
    moved = SimpleNamespace(tracks=[BoneTrack(bone=IK_LEFT, rotations=np.array([[1.0, 0, 0, 0]]),
                                              translations=np.array([[1.0, 2.0, 3.0]]))])
    assert np.allclose(left_targets(moved, (vanilla, {}))[1][3, :3], (1, 2, 3))
    assert left_targets(SimpleNamespace(tracks=[]), (vanilla, {})) is None


def test_a_built_in_scope_has_the_scope_flag_and_not_scope_from_mod():
    """The Bozar (Has Scope, iron-sight clips) and the Anti-Materiel Rifle are scoped; the Laser Rifle (scope from
    a mod) and the 9mm are not."""
    assert built_in_scope({'DNAM.Flags1': '6', 'DNAM.Flags2': '1032'})
    assert built_in_scope({'DNAM.Flags1': '68', 'DNAM.Flags2': '8'})
    assert not built_in_scope({'DNAM.Flags1': '68', 'DNAM.Flags2': '8200'})
    assert not built_in_scope({'DNAM.Flags1': '0'})


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


def test_a_kf_is_decoded_once_and_each_caller_gets_its_own_copy(tmp_path, monkeypatch):
    """decoded() decodes a .kf once per content: again this run from memory, a later run from the work cache;
    changing what it returned changes no later copy."""
    calls = []
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(KC, 'decode_kf', lambda path, fps: calls.append(path) or [
        DecodedClip('idle', 1.0, 0, 1.0, times=np.zeros(2), tracks=[BoneTrack('Bip01', np.zeros((2, 3)))])])
    kf = tmp_path / 'idle.kf'
    kf.write_bytes(b'kf')
    first = KC.decoded(kf)
    first[0].tracks[0].translations += 5.0
    KC._pickled.cache_clear()
    again, (clip, _) = KC.decoded(kf), KC.decoded_clip(kf, extract_motion=False)
    assert len(calls) == 1 and not again[0].tracks[0].translations.any() and clip.name == 'idle'


def _layer(root, files: dict):
    """Export layer `root` holding {path under the first-person clip folder: bytes}; `root`."""
    for name, data in files.items():
        path = root / 'meshes' / VIEWS[0].fnv.replace('\\', '/') / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def _rifle_key(tmp_path, *layers) -> tuple:
    """GunClips.key of RIFLE over export `layers` (first searched first)."""
    clips = GunClips.__new__(GunClips)
    clips.export_meshes = Layered(layers, 'meshes')
    gun_path = tmp_path / 'gun.nif'
    gun_path.write_bytes(b'gun')
    return clips.key(RIFLE, ([1, 2], {3}), gun_path, {'Weapon': np.eye(4)}, np.eye(4), ((), ()))


def test_a_master_holding_none_of_a_guns_files_leaves_its_key(tmp_path):
    """A gun's key follows each file it reads to the layer holding it: a master with other clips leaves it; a
    master replacing its aim clip, or adding the sighted aim its class lacked, changes it."""
    game = _layer(tmp_path / 'game', {'skeleton.nif': b'skeleton', '2hraim.kf': b'aim', '2hrequip.kf': b'equip'})
    key = _rifle_key(tmp_path, game)
    unrelated = _layer(tmp_path / 'unrelated', {'1hpaim.kf': b'pistol', 'locomotion/2hrrun.kf': b'run'})
    assert _rifle_key(tmp_path, unrelated, game) == key
    assert _rifle_key(tmp_path, _layer(tmp_path / 'aim', {'2hraim.kf': b'other aim'}), game) != key
    assert _rifle_key(tmp_path, _layer(tmp_path / 'sighted', {'2hraimis.kf': b'sights'}), game) != key


def test_a_kept_gun_holds_placeholders_and_one_copy_of_each_file(tmp_path, monkeypatch):
    """keep() stores each written file once by its bytes; the entry's own-keyword placeholders take any plugin's
    FormIDs (owned); a file gone from the cache makes the entry a miss."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    entry = {'target': [7, placeholder(5)], 'actor': [], 'paths': [], 'flags': bytes(4)}
    made = Converted({5: placeholder(5)}, None, {})
    keep(('a',), (made, [entry], {'x/a.hkx': b'clip', 'x/b.hkx': b'clip'}))
    keep(('b',), (made, [], {'y/a.hkx': b'clip'}))
    assert len(list((tmp_path / 'work' / 'gun_clip_files').rglob('*.ran'))) == 1 and is_kept(('a',))
    found = kept(('a',))
    assert found[2] == {'x/a.hkx': b'clip', 'x/b.hkx': b'clip'}
    assert owned(found[1][0], {5: 0x0300ABCD})['target'] == [7, 0x0300ABCD]
    for blob in (tmp_path / 'work' / 'gun_clip_files').rglob('*'):
        if blob.is_file():
            blob.unlink()
    assert kept(('a',)) is None and not is_kept(('a',))


def test_the_pool_starts_only_for_guns_not_kept(tmp_path, monkeypatch):
    """warm() makes nothing, and starts no worker, when every job's clips are kept."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    keep(('kept',), (None, [], {}))
    assert warm([(('kept',), None)], tmp_path) == 0


def _reference_gun(guns: Guns, clips: GunClips, rec: dict) -> tuple:
    """(GunClips.key, maker of GunClips.recorded) of FNV gun `rec`, chosen and built as a build does."""
    choice, subs, mesh = guns.choose(rec)
    receiver, matrix, made = guns.built(choice, mesh)
    args = guns.clip_args(rec, (subs, choice.includes), mesh[1], receiver, (made, matrix))
    return clips.key(*args), functools.partial(clips.recorded, args)


@pytest.mark.skipif(not (EXPORT / 'WEAP.txt').is_file() or not FALLOUT4_ESM.is_file(),
                    reason='needs the FNV export and Fallout 4')
def test_gun_clips_version_is_honest(tmp_path, monkeypatch):
    """REFERENCE_GUNS' clips made cold (work and mesh caches under tmp_path) match their digests recorded under
    GUN_CLIPS_VERSION (tests/fo4_versions.py)."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'meshes')
    fo4 = FALLOUT4_ESM.read_bytes()
    keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id for r, _ in walk(fo4, b'KYWD')}
    builder = SimpleNamespace(fo4=fo4, keywords=keywords, export_dir=EXPORT, data_dir=tmp_path / 'data',
                              counts=collections.Counter())
    guns, clips = Guns(builder, {}), GunClips(fo4, asset_root(EXPORT, 'meshes'), tmp_path / 'data')
    recs = {r['EditorID']: r for r in export_records(EXPORT, 'WEAP') if r['EditorID'] in REFERENCE_GUNS}
    check(CLIP_SITE, GUN_CLIPS_VERSION, {edid: _reference_gun(guns, clips, recs[edid]) for edid in REFERENCE_GUNS})
