"""Own-rig creatures (fo4_import.rig): the pieces that run without the game or its tools."""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.havok import graph as G
from fo4_import.havok import packfile, packfile_write
from fo4_import.rig import assets, behavior, build, records
from fo4_import.rig import gun_mods
from fo4_import.rig.table import Rig, rigs, weapon_node
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.spike.talking_machines import bone_worlds, part_pose
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from tests.test_script_converter import conv_lines
from fo4_import.spike.ammo_mods import ADD, FORM, FORM_VALUE2, omod_data, prop
from fo4_import.spike import creatures as C
from fo4_import.spike import idles as ID
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

GECKO = 'creatures\\nvgecko'
#: The FNV export's meshes, where each rig's skeleton and clips are read.
EXPORT_MESHES = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm' / 'meshes'


def subs(*tags: str) -> bytes:
    """Subrecords with the given tags, each holding a FormID 1."""
    return b''.join(pack_subrecord(t, struct.pack('<I', 1)) for t in tags)


def test_a_parts_vats_name_is_fnvs_part_covering_its_bone():
    """A bone takes the name of FNV's part on it or its nearest ancestor; above every part, none; a template's
    localized name reads through the strings, a plain one as itself."""
    parents = {'Bip01 Head': 'Bip01 Neck1', 'Bip01 Neck1': 'Bip01 Spine1', 'Bip01 Spine1': 'Root'}
    names = {'bip01 neck1': 'Head', 'bip01 spine1': 'Torso'}
    assert records.part_name('Bip01 Head', names, parents) == 'Head'
    assert records.part_name('Bip01 Spine1', names, parents) == 'Torso'
    assert records.part_name('Root', names, parents) is None
    assert records.localized(struct.pack('<I', 7), {7: b'Head'}) == 'Head'
    assert records.localized(b'Torso\0', {}) == 'Torso'


def test_skin_goes_after_spells_and_before_the_attack_race():
    """WNAM lands where FO4's NPC_ keeps it; RNAM and ATKR name the rig's race."""
    out = list(subrecords(C._on_race(subs('EDID', 'RNAM', 'SPLO', 'ATKR', 'PRKZ'), 0x100, 0x200)))
    assert [t for t, _ in out] == [b'EDID', b'RNAM', b'SPLO', b'WNAM', b'ATKR', b'PRKZ']
    values = {t: struct.unpack('<I', d)[0] for t, d in out}
    assert values[b'RNAM'] == values[b'ATKR'] == 0x100 and values[b'WNAM'] == 0x200


def test_skin_replaces_a_template_skin():
    """A template NPC's own WNAM is replaced, not doubled."""
    out = [t for t, _ in subrecords(C._on_race(subs('RNAM', 'WNAM', 'PRKZ'), 0x100, 0x200))]
    assert out.count(b'WNAM') == 1


def test_project_file_data_lists_root_character_skeleton_and_clips():
    """The project list: 3, 0, name, count, root graph, character, skeleton, clips, 0 (CRLF)."""
    rig = rigs()[GECKO]
    lines = build.project_file_data(rig).decode().split('\r\n')
    assert lines[:3] == ['3', '0', 'FNVGeckoProject'] and lines[3] == str(3 + len(rig.clips))
    assert lines[4:7] == ['Behaviors\\FNVGeckoRootBehavior.hkx', 'Characters\\FNVGeckoCharacter.hkx',
                          'CharacterAssets\\skeleton.hkx'] and lines[-2:] == ['0', '']


def test_a_long_body_name_gets_a_short_stable_file_name():
    """A short model name is its own file; a long many-part one is its first stem and a hash, distinct per name, and
    the skin's model path names the same file."""
    parts = ['nvdlc03_brainbot', 'nvdlc03_brainbot_brain', 'nvdlc03_brainbot_eyel_m', 'nvdlc03_brainbot_eyer_sm',
             'nvdlc03_brainbot_gunlens', 'nvdlc03_brainbot_mouth_lg', 'nvdlc03_brainbot_shell_white']
    long = '+'.join(parts) + '.nif'
    other = long.replace('white', 'blue')
    assert records.model_file('a+b.nif') == 'a+b.nif'
    short = records.model_file(long)
    assert short.startswith('nvdlc03_brainbot+') and short == records.model_file(long)
    assert len(short) <= records.MODEL_NAME_MAX and short.endswith('.nif') and short != records.model_file(other)
    rig = rigs()['nvdlc03\\creatures\\brainbot']
    assert records.body_path(rig, long).endswith('\\' + short)


def test_body_name_takes_the_one_body_part_or_joins_several():
    """One NIFZ part keeps its name (extension lower case); several join their stems, read back by body_parts."""
    assert build.body_name({'NIFZCount': '1', 'NIFZ[0]': 'NVFireGecko.NIF'}) == 'NVFireGecko.nif'
    joined = build.body_name({'NIFZCount': '2', 'NIFZ[0]': 'a.NIF', 'NIFZ[1]': 'b.nif', 'EditorID': 'X'})
    assert joined == 'a+b.nif' and build.body_parts(joined) == ['a.nif', 'b.nif']
    assert build.body_parts('NVFireGecko.nif') == ['NVFireGecko.nif']
    with pytest.raises(ValueError):
        build.body_name({'NIFZCount': '0', 'EditorID': 'X'})


def test_old_speeds_become_the_new_layout():
    """A 17-float SPED gives forward walk, run, sprint (run x 1.75) and its six rotation rates twice."""
    old = [0.0] * 8 + [1.0, 2.0, 3.0, 4.0, 5.0, 6.0] + [0.0] * 3
    new = records.sped(old, 60.0, 500.0)
    assert len(new) == 28 and new[8:12] == [0.0, 60.0, 500.0, 875.0]
    assert new[16:] == [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 5.0, 5.0, 6.0, 6.0]


def test_spells_join_the_list_after_rnam():
    """SPCT counts old and new spells, after RNAM; none is doubled."""
    out = list(subrecords(C.with_spells([1, 7])(subs('EDID', 'RNAM', 'SPCT', 'SPLO', 'WNAM'))))
    assert [t for t, _ in out] == [b'EDID', b'RNAM', b'SPCT', b'SPLO', b'SPLO', b'WNAM']
    assert struct.unpack('<I', out[2][1])[0] == 2 and struct.unpack('<I', out[4][1])[0] == 7


@pytest.mark.parametrize('folder', sorted(rigs()))
def test_every_rig_names_its_own_bones_and_clips(folder):
    """Every bone a rig entry names is in its FNV skeleton and every clip it names is exported."""
    fnv = EXPORT_MESHES / folder.replace(chr(92), '/')
    if not fnv.is_dir():
        pytest.skip('no FNV export')
    rig = rigs()[folder]
    names = {b.name for b in assets.skeleton_bones(fnv / 'skeleton.nif')}
    assert {*rig.parts.values(), rig.default_part, *rig.pose_bones, *rig.fire_nodes.values()} <= names
    assert all((fnv / kf.replace(chr(92), '/')).is_file() for kf in rig.clips.values())


def test_a_clip_with_no_root_motion_has_speed_zero(monkeypatch):
    """An immobile rig's idle in a movement role moves nothing: speed 0, not an error."""
    maker = behavior.Builder.__new__(behavior.Builder)
    monkeypatch.setattr(maker, 'fnv', lambda role: type('Clip', (), {'duration': 1.0})(), raising=False)
    monkeypatch.setattr(behavior, 'split_root_motion', lambda clip: None)
    assert maker.root_speed('WalkForward') == 0.0


def ranged_builder(monkeypatch, hits, duration):
    """A Builder on a fake rig with one gun (role Gun, slot 3) whose clip has Hit keys `hits`."""
    rig = type('Rig', (), {'guns': (('Gun', 3, (), 'Fire'),), 'clips': {'Gun': 'x.kf'},
                           'project': 'Test'})()
    maker = behavior.Builder(rig, Path('.'), {}, None)
    clip = type('Clip', (), {'duration': duration, 'text_keys': [(t, 'Hit') for t in hits]})()
    monkeypatch.setattr(maker, 'fnv', lambda role: clip)
    return maker


def test_a_shot_names_its_slot_and_the_attack_ends_after_it(monkeypatch):
    """The shot is weaponFire with the gun's slot as payload (the robots' weaponFire.<slot>), no sooner than the
    blend into the attack ends; AttackEnd comes after the last shot on FNV's 0.17 s clips, 0.2 s before the end on
    longer ones."""
    short = ranged_builder(monkeypatch, [0.03], 0.17)
    assert short.fire_triggers('Gun', 3) == [(behavior.ATTACK_BLEND, (behavior.FIRE, '3'), False)]
    assert short.ranged_end('Gun')[0] > behavior.ATTACK_BLEND
    assert ranged_builder(monkeypatch, [0.03], 0.6).ranged_end('Gun')[0] == pytest.approx(0.4)


def test_a_dynamic_idle_plays_on_a_tagging_generator_and_returns_to_idle():
    """dynamicAnim and dynamicAnimLooping enter states on a DynamicAnimationTaggingGenerator over a stand-in Idle
    clip (the once one raising returnToDefault 0.2 s before its end); both go back to Idle (1); it writes and reads."""
    maker = behavior.Builder(type('Rig', (), {'project': 'Test'})(), Path('.'), {}, None)
    g = maker.g
    states, wildcard = maker.dynamic(g.blend_effect('Fx', 0.2))
    assert wildcard == [('dynamicAnim', 5), ('dynamicAnimLooping', 6)]
    once = g.get(states[0])
    tagged = g.get(once['generator'])
    clip = g.get(tagged['pDefaultGenerator'])
    assert (once['name'], clip['animationName'], clip['mode']) == ('DynamicAnim', 'Animations\\Idle.hkt', G.SINGLE)
    trigger = g.get(clip['triggers'])['triggers'][0]
    assert (trigger['localTime'], trigger['relativeToEndOfClip'], g.events[trigger['event']['id']]) == (
        -0.2, 1, 'returnToDefault')
    back = g.get(once['transitions'])['transitions']
    assert {g.events[t['eventId']] for t in back} == {'returnToDefault', *behavior.TALK_END}
    assert {t['toStateId'] for t in back} == {1}
    looped = g.get(g.get(g.get(states[1])['generator'])['pDefaultGenerator'])
    assert looped['mode'] == G.LOOPING and looped['triggers'] is None
    read = packfile.read(packfile_write.write(g.objects, once['generator']))
    assert [o['class'] for o in read.objects][:2] == ['DynamicAnimationTaggingGenerator', 'hkbClipGenerator']


def test_an_idle_in_a_rig_folder_plays_on_that_rig_with_the_creature_events():
    """A Think Tank special idle belongs to its rig and sends vanilla creatures' dynamicAnim; a human clip has no
    rig; a forever loop sends the looping event."""
    assert ID.rig_of('NVDLC03\\Creatures\\BrainBot\\idleanims\\mtspecialidle_angry.kf').project == 'FNVBrainBot'
    assert ID.rig_of('characters\\_male\\idleanims\\talk.kf') is None
    rec = {'EditorID': 'X', 'DATA.LoopMin': '255', 'DATA.LoopMax': '255'}
    subs = dict(subrecords(ID.pack_idle(1, rec, b'', ('G.hkx', 'C.hkx', ID.RIG_EVENTS), (0, 0))[24:]))
    assert subs[b'ENAM'].rstrip(b'\0') == b'dynamicAnimLooping' and subs[b'DNAM'].rstrip(b'\0') == b'G.hkx'


def test_each_gun_has_a_fire_idle_on_its_slot():
    """Per fire action: a root IDLE with no event, then one child per gun under it, chained by previous sibling,
    sending fire_start(slot) on GetActionDataByte == slot."""
    rig = type('Rig', (), {'guns': (('A', 0, (), 'FireA'), ('B', 3, (), 'FireB')), 'project': 'Test', 'folder': 'test',
                           'path': lambda self, *p: chr(92).join(p)})()
    t = type('T', (), {'actions': {a: i for i, a in enumerate(records.RANGED_ACTIONS, 1)}, 'idle_data': {}})()
    added = []
    writer = type('W', (), {'derive_formid': lambda self, site, key: hash(key) & 0xFFFFFF,
                            'add_record': lambda self, sig, rec: added.append(rec)})()
    records.fire_idles(writer, rig, t)
    subs = [dict(subrecords(rec[24:])) for rec in added[:3]]
    ids = [struct.unpack_from('<I', rec, 12)[0] for rec in added[:3]]
    assert b'ENAM' not in subs[0] and struct.unpack('<II', subs[0][b'ANAM']) == (1, 0)
    assert [s[b'ENAM'] for s in subs[1:]] == [b'rangedAttackStart0\0', b'rangedAttackStart3\0']
    assert [struct.unpack('<II', s[b'ANAM']) for s in subs[1:]] == [(ids[0], 0), (ids[0], ids[1])]
    assert [struct.unpack_from('<fH', s[b'CTDA'], 4) for s in subs[1:]] == [(0.0, 747), (3.0, 747)]


def test_the_arm_layer_covers_its_bones_subtrees(monkeypatch):
    """layer_weights is 1 on each named bone and everything under it, 0 elsewhere; every bone with none named."""
    bones = [assets.Bone(n, p, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0)
             for n, p in (('Root', -1), ('Spine', 0), ('RShoulder', 1), ('RHand', 2), ('Wheel', 0))]
    maker = ranged_builder(monkeypatch, [0.03], 0.17)
    maker.bones = bones
    assert maker.layer_weights(['RShoulder']) == [0.0, 0.0, 1.0, 1.0, 0.0]
    assert maker.layer_weights(()) == [1.0] * 5


def test_a_gun_mod_and_its_combination_match_the_bubble_turrets():
    """A gun's ForcedInventory mod DATA and the default combination including it are byte for byte vanilla's
    Bubble_Turret_Ballistic3shot (gun TurretBubbleBallistic3shot at ap_TurretWep) and EncTurretBubble03's OBTS."""
    data = omod_data(0x1BBF90, [prop(FORM, ADD, gun_mods.FORCED_INVENTORY, struct.pack('<I', 0x1BBF99),
                                     struct.pack('<I', FORM_VALUE2))], b'NPC_')
    assert data == bytes.fromhex('000000000100000000004e50435f000090bf1b000000000000000000040000000200000001000000'
                                 '99bf1b00b801000000000000')
    assert gun_mods.obts([0x1BBF97]) == bytes.fromhex('010000000000000000000000ffff0100000097bf1b00000001')


def test_forced_guns_replace_an_npcs_object_template_before_its_class():
    """with_forced() drops the clone's own attach points and object template and puts its own before CNAM, the
    NPC's name (a FULL outside the template) kept; slot 0's gun hangs on WEAPON, another slot's on WEAPON<slot>."""
    subs = b''.join(pack_subrecord(t, d) for t, d in (
        ('EDID', b'X\0'), ('APPR', bytes(4)), ('OBTE', bytes(4)), ('OBTF', b''), ('FULL', b'Old\0'),
        ('OBTS', bytes(18)), ('STOP', b''), ('CNAM', bytes(4)), ('FULL', b'Name\0')))
    out = [(t, d) for t, d in subrecords(gun_mods.with_forced([7, 8], [5, 6])(subs))]
    assert [t for t, _ in out] == [b'EDID', b'APPR', b'OBTE', b'OBTF', b'FULL', b'OBTS', b'STOP', b'CNAM', b'FULL']
    assert dict(out)[b'APPR'] == struct.pack('<2I', 7, 8) and out[-1] == (b'FULL', b'Name\0')
    assert gun_mods.with_forced([], []) is None
    assert (weapon_node(0), weapon_node(3)) == ('WEAPON', 'WEAPON3')


def test_a_gun_slot_the_template_race_lacks_is_added_after_its_own():
    """with_slots turns each gun's EQUP EditorID into its index in the race's slots, the template race's first and
    a missing one (MiddleHand on the mole rat's) after them; equip_slots writes them, each gun's naming its node."""
    eqp = {'RightHand': 0x13F42, 'LeftHand': 0x13F43, 'MiddleHand': 0x1A02F}
    race = [(b'QNAM', struct.pack('<I', eqp['RightHand'])), (b'QNAM', struct.pack('<I', eqp['LeftHand']))]
    get = {(b'RACE', 'R'): (None, race), **{(b'EQUP', k): (type('E', (), {'form_id': v})(), []) for k, v in eqp.items()}}
    t = type('T', (), {'get': lambda self, sig, name: get[(sig, name)]})()
    rig = Rig('f', 'P', {'race': 'R'}, {}, {}, {}, '', (), guns=(('Spit', 'MiddleHand', (), 'Head'),
                                                              ('Fire', 'RightHand', (), 'Head')))
    resolved = records.with_slots(rig, t)
    assert [g[1] for g in resolved.guns] == [2, 0] and resolved.slots == (eqp['MiddleHand'],)
    written = [(tag, d) for tag, d in subrecords(records.equip_slots(resolved, race))]
    assert [(tag, d if tag == b'ZNAM' else struct.unpack('<I', d)[0]) for tag, d in written] == [
        (b'QNAM', eqp['RightHand']), (b'ZNAM', b'WEAPON\0'), (b'QNAM', eqp['LeftHand']),
        (b'QNAM', eqp['MiddleHand']), (b'ZNAM', b'WEAPON2\0')]


def test_a_gun_node_aims_level_ahead_at_the_shot():
    """aim_turn undoes the fire node's model-space turn in the clip's pose (the root unmoved), so the gun node's
    axes are the model's: +Y ahead, +Z up; a flame's Fire key counts as a shot."""
    half = 2 ** -0.5
    bones = [assets.Bone('Root', -1, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), 1.0),
             assets.Bone('Head', 0, (0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0)]
    clip = type('Clip', (), {'times': [0.0, 0.5], 'tracks': [type('Track', (), {
        'bone': 'Head', 'rotations': [(1.0, 0.0, 0.0, 0.0), (half, half, 0.0, 0.0)]})()]})()
    turn = assets.aim_turn(bones, clip, 'Head', 0.5)
    head = assets.skeleton_frames([assets.Bone('Root', -1, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0),
                                   assets.Bone('Head', 0, (0.0, 1.0, 0.0), (half, 0.0, 0.0, half), 1.0)])['Head'][0]
    assert head @ np.array(turn).reshape(3, 3) == pytest.approx(np.eye(3))
    assert behavior.shot_times([(0.367, 'Fire'), (0.733, 'Loop'), (1.0, 'Hit')]) == [0.367, 1.0]


def test_a_weapon_nodes_children_stay_in_place_when_it_moves_onto_one():
    """The Think Tank's WEAPON (turned 90° about Z, 7 up) holds its fire node 1 along its X: the fire node is lifted
    onto WEAPON's parent at (0, 1, 7), in the animation skeleton and the skeleton.nif alike, and WEAPON hangs on it."""
    half = 2 ** -0.5
    bones = [assets.Bone('Root', -1, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0),
             assets.Bone('WEAPON', 0, (0.0, 0.0, 7.0), (0.0, 0.0, half, half), 1.0),
             assets.Bone('Fire', 1, (1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0)]
    moved = assets.move_weapon(bones, 'Fire', (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    world = assets.skeleton_frames(moved)
    assert [(b.name, moved[b.parent].name) for b in moved[1:]] == [('Fire', 'Root'), ('WEAPON', 'Fire')]
    assert world['Fire'][1] == pytest.approx((0.0, 1.0, 7.0))
    assert world['Fire'][0] == pytest.approx(assets.skeleton_frames(bones)['Fire'][0])
    nif = type('Nif', (), {'blocks': [
        ('NiNode', {'translation': (0.0, 0.0, 7.0), 'rotation': (0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
                    'scale': 1.0, 'children': [1]}),
        ('NiNode', {'translation': (1.0, 0.0, 0.0), 'rotation': (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
                    'scale': 1.0, 'children': []})]})()
    assert assets.lift_nif_children(nif, 0) == [1] and nif.blocks[0][1]['children'] == []
    assert nif.blocks[1][1]['translation'] == pytest.approx((0.0, 1.0, 7.0))
    assert nif.blocks[1][1]['rotation'] == pytest.approx((0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0))


SECURITRON = EXPORT_MESHES / 'creatures' / 'nvsecuritron'


@pytest.mark.skipif(not SECURITRON.exists(), reason='needs the FalloutNV.esm export')
def test_a_rigid_part_rides_its_prn_bone_where_fnv_attaches_it(tmp_path):
    """Victor's face screen (no skin, `Prn` Bip01 Screen10) is skinned fully to that bone, its vertices where the
    posed static conversion puts them, its shader keeping its free-running controllers."""
    part, skeleton = SECURITRON / 'nvsecuritronvictorscreen01.nif', SECURITRON / 'skeleton.nif'
    _, summary = assets.write_body([part], skeleton, assets.skeleton_bones(skeleton), tmp_path / 'body.nif',
                                   EXPORT_MESHES.parent)
    assert summary['Screen01:0']['bones'] == 1
    nif = assets.F.read((tmp_path / 'body.nif').read_bytes())
    shapes = {nif.strings[s['name']]: s for s in (read_tri_shape(Reader(b)) for k, b in nif.blocks
                                                  if k == 'BSSubIndexTriShape')}
    screen = shapes['Screen01:0']
    skin = nif.blocks[screen['skin']][1]
    bone = struct.unpack_from('<i', skin, 12)[0]
    assert nif.strings[nif.blocks[bone][1]['name']] == 'Bip01 Screen10'
    posed = assets.CS.convert(str(part), pose=part_pose(part, bone_worlds(skeleton))).nif
    want = next(b for k, b in posed.blocks if k == 'BSTriShape' and posed.strings[b['name']] == 'Screen01:0')
    mean = np.mean([v['position'] for v in screen['vertices']], axis=0)
    assert mean == pytest.approx(np.mean([v['position'] for v in want['vertices']], axis=0), abs=0.01)
    shader = nif.blocks[screen['shader']][1]
    assert nif.blocks[shader['controller']][0].startswith('BSEffectShaderProperty')
    assert shader['name'] == -1


@pytest.mark.skipif(not SECURITRON.exists(), reason='needs the FalloutNV.esm export')
def test_the_idle_clips_screen_channels_loop_on_the_body(tmp_path):
    """mtidle.kf's screen channels become loops over its 13.33 s on the screen's shader: four UV channels and its
    B-spline emissive colour, sampled and shown as FNV does (colour x30 emittance, clipped to 1)."""
    part, skeleton = SECURITRON / 'nvsecuritronvictorscreen01.nif', SECURITRON / 'skeleton.nif'
    assets.write_body([part], skeleton, assets.skeleton_bones(skeleton), tmp_path / 'body.nif', EXPORT_MESHES.parent,
                      (SECURITRON / 'mtidle.kf',))
    nif = assets.F.read((tmp_path / 'body.nif').read_bytes())
    screen = next(s for s in (read_tri_shape(Reader(b)) for k, b in nif.blocks if k == 'BSSubIndexTriShape')
                  if nif.strings[s['name']] == 'Screen01:0')
    loops, at = {}, nif.blocks[screen['shader']][1]['controller']
    while at >= 0:
        kind, block = nif.blocks[at]
        keys = nif.blocks[nif.blocks[block['interpolator']][1]['data']][1]['keys']['keys']
        loops[(kind[-15:], block['variable'])] = (block['flags'], round(block['stop'], 2), keys)
        at = block['next']
    assert set(loops) == {('ColorController', 0)} | {('FloatController', v) for v in (6, 7, 8, 9)}
    assert {flags for flags, _, _ in loops.values()} == {0x48} and {s for _, s, _ in loops.values()} == {13.33}
    colors = [k[1] for k in loops[('ColorController', 0)][2]]
    assert len(colors) == 401 and 0.6 < min(colors) and max(colors) == 1.0


BRAINBOT = EXPORT_MESHES.parents[1] / 'OldWorldBlues.esm' / 'meshes' / 'nvdlc03' / 'creatures' / 'brainbot'


@pytest.mark.skipif(not BRAINBOT.exists(), reason='needs the OldWorldBlues.esm export')
def test_an_idle_clips_float_spline_channels_loop_as_sampled_keys(tmp_path):
    """mtidle.kf drives Think Tank shader floats with compressed float splines; each becomes a looping float
    controller whose key data was sampled from the spline."""
    parts = [BRAINBOT / f'nvdlc03_brainbot_{p}.nif' for p in ('eyel_m', 'eyer_m', 'mouth_m', 'gunlens', 'brain')]
    skeleton = BRAINBOT / 'skeleton.nif'
    assets.write_body(parts, skeleton, assets.skeleton_bones(skeleton), tmp_path / 'body.nif', EXPORT_MESHES.parent,
                      (BRAINBOT / 'mtidle.kf',))
    nif = assets.F.read((tmp_path / 'body.nif').read_bytes())
    floats = [b for k, b in nif.blocks if k.endswith('FloatController')]
    assert floats
    keys = [nif.blocks[nif.blocks[b['interpolator']][1]['data']][1]['keys']['keys'] for b in floats]
    assert max(len(k) for k in keys) > 2


@pytest.mark.skipif(not SECURITRON.exists(), reason='needs the FalloutNV.esm export')
def test_an_expression_screen_is_the_face_screen_showing_its_face_texture(tmp_path):
    """screen_part picks the part holding Screen01:0; retexturing it shows `<face>_<expression>.dds` as
    SetSecuritronExpression does."""
    parts = [SECURITRON / p for p in ('nvsecuritron.nif', 'nvsecuritronvoicebox.nif', 'nvsecuritronvictorscreen01.nif')]
    screen = assets.screen_part(parts)
    assert screen == parts[2]
    texture = assets.SCREEN_TEXTURE.format('infantry', 'neutral')
    skeleton = SECURITRON / 'skeleton.nif'
    statics, _ = assets.write_body([screen], skeleton, assets.skeleton_bones(skeleton), tmp_path / 's.nif',
                                   EXPORT_MESHES.parent, (None, {assets.SCREEN_SHAPE: texture}))
    nif = assets.F.read((tmp_path / 's.nif').read_bytes())
    shape = next(s for s in (read_tri_shape(Reader(b)) for k, b in nif.blocks if k == 'BSSubIndexTriShape')
                 if nif.strings[s['name']] == assets.SCREEN_SHAPE)
    assert nif.blocks[shape['shader']][1]['source_texture'].lower().endswith('securitron\\infantry_neutral.dds')
    assert texture in statics[0].textures


class _Templates:
    """A stand-in for records.Templates holding a template skin and addon as Fallout4.esm lays them out."""

    def get(self, sig: bytes, edid: str) -> tuple:
        """(record with flags, subrecords) of the stand-in skin or addon."""
        if sig == b'ARMO':
            return type('Rec', (), {'flags': 4})(), [
                (b'EDID', b'Skin\0'), (b'BOD2', struct.pack('<I', 8)), (b'RNAM', bytes(4)), (b'INDX', bytes(2)),
                (b'MODL', bytes(4)), (b'DATA', bytes(12))]
        return type('Rec', (), {'flags': 0})(), [
            (b'EDID', b'AA\0'), (b'BOD2', struct.pack('<I', 8)), (b'RNAM', bytes(4)), (b'MOD2', b'm\0'),
            (b'MO2T', b'x'), (b'MOD3', b'm\0'), (b'SNDD', bytes(4))]


def _subs(record: bytes) -> list:
    """A packed record's subrecords (its 24-byte header skipped)."""
    return subrecords(record[24:])


def test_a_skin_with_a_face_screen_lists_both_addons_and_covers_both_slots():
    """Without a screen the skin keeps one addon on the template's slot (33); with one, a second addon on the Eyes
    slot (47) shows it and the skin covers both, listed as INDX/MODL pairs as vanilla's SkinNaked."""
    rig = Rig(folder='creatures\\x', project='FNVX', template={'skin': 'S', 'addon': 'A'}, clips={}, attacks={},
              parts={}, default_part='', pose_bones=())
    armo, armas = records.skin((1, 2), 9, rig, _Templates(), 'body.nif')
    assert len(armas) == 1 and [t for t, _ in _subs(armo)] == [b'EDID', b'BOD2', b'RNAM', b'INDX', b'MODL', b'DATA']
    armo, armas = records.skin((1, 2, 3), 9, rig, _Templates(), 'body.nif', screen='screen.nif')
    subs = _subs(armo)
    assert struct.unpack('<I', dict(subs)[b'BOD2'])[0] == 8 | 1 << (records.SCREEN_SLOT - records.FIRST_SLOT)
    assert [struct.unpack('<I', d)[0] for t, d in subs if t == b'MODL'] == [2, 3]
    screen = dict(_subs(armas[1]))
    assert screen[b'MOD2'].rstrip(b'\0').endswith(b'screen.nif') and b'SNDD' not in screen


def test_set_securitron_expression_equips_that_faces_screen_armor(monkeypatch):
    """`SetSecuritronExpression <ref> <face> <expression>` equips the armor property its face and expression name."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'fallout4')
    xref = CrossRefGraph()
    xref._is_fallout = True
    out = conv_lines(ScriptConverter(xref), 'SetSecuritronExpression rSelf Infantry Neutral', 'ObjectReference')
    assert out == '(rSelf as Actor).EquipItem(TES4Screen_Infantry_Neutral, true, true)'


RAT = EXPORT_MESHES / 'creatures' / 'nvgiantrat' / 'skeleton.nif'


@pytest.mark.skipif(not RAT.exists() or not assets.elric.ELRIC.exists(), reason='needs the FalloutNV.esm export and Elric')
@pytest.mark.parametrize('folder', ['nvgiantrat', 'centaur', 'nvcazadores'])
def test_an_elric_skeleton_comes_out_byte_identical_its_ragdoll_in_node_order(tmp_path, folder):
    """Elric numbers ragdoll bodies differently each run; in_node_order makes two runs' skeleton.nif identical,
    bodies in node order: capsules (rat), a sphere shape (centaur), constraints sharing one motor through fixed
    arrays (cazador)."""
    skeleton = EXPORT_MESHES / 'creatures' / folder / 'skeleton.nif'
    first = assets.write_skeleton_nif(skeleton, tmp_path / 'a' / 'skeleton.nif')
    second = assets.write_skeleton_nif(skeleton, tmp_path / 'b' / 'skeleton.nif')
    assert (tmp_path / 'a' / 'skeleton.nif').read_bytes() == (tmp_path / 'b' / 'skeleton.nif').read_bytes()
    assert first == second
    nif = assets.F.read((tmp_path / 'a' / 'skeleton.nif').read_bytes())
    system = next(i for i, (k, _) in enumerate(nif.blocks) if k == 'bhkRagdollSystem')
    bodies = [struct.unpack_from('<iHiI', nif.blocks[b['collision']][1])[3] for k, b in nif.blocks
              if k == 'NiNode' and b['collision'] >= 0
              and struct.unpack_from('<iHiI', nif.blocks[b['collision']][1])[2] == system]
    assert bodies == list(range(len(bodies)))


def test_a_dlc_build_leaves_a_rig_its_master_ships_to_the_master(tmp_path):
    """A master folder holding the rig's skeleton.nif keeps its rig files (Rigs.shipped), and one holding a body
    keeps that body (Rigs.model writes nothing); a body the master lacks (Honest Hearts' green gecko) is the DLC's."""
    rig = rigs()[GECKO]
    shipped, other, own = tmp_path / 'game', tmp_path / 'other', tmp_path / 'dlc'
    path = shipped / 'Meshes' / rig.actor_dir / 'CharacterAssets' / 'skeleton.nif'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'nif')
    made = build.Rigs.__new__(build.Rigs)
    made.data_dir, made.masters = own, [other, shipped]
    assert made.shipped(rig) == path
    body = path.with_name('NVGecko.nif')
    body.write_bytes(b'nif')
    assert made.shipped(rig, 'NVGecko.nif') == body and made.shipped(rig, 'NVDLC02GreenGecko.nif') is None
    made.builder = type('B', (), {'counts': __import__('collections').Counter()})()
    made.model(rig, [], 'NVGecko.nif')
    assert made.builder.counts["own-rig bodies left to the master's folder"] == 1
    made.masters = [other]
    assert made.shipped(rig) is None
