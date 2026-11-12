"""Our AnimTextData in place of the Creation Kit's: creature projects and stances, entry offsets, sync data,
pruning."""

import struct
from pathlib import Path

import numpy as np

from fo4_import.havok import anim_text as T
from fo4_import.havok.gun_anim_text import ANIM_TEXT, PERSISTENT
from tes5_import.base.writer import pack_subrecord

EVENTS = ['meleeStart_Right', 'rangedAttackStart2', 'FootLeft', 'SoundPlay.Roar', 'weaponFire', 'moveStart']
SPELLED = {'footleft': 'FootLeft', 'weaponfire': 'WeaponFire', 'attackend': 'AttackEnd'}


def _clip(ref: str, name: str, triggers: str = None, flags: int = 0) -> tuple:
    """A clip generator object."""
    return ref, {'#': ref, 'class': 'hkbClipGenerator', 'fields': {
        'name': name, 'animationName': f'Animations\\{name}.hkt', 'playbackSpeed': 1.0, 'cropStartAmountLocalTime': 0.0,
        'cropEndAmountLocalTime': 0.0, 'flags': flags, 'triggers': triggers}}


def _graph() -> dict:
    """A root machine: idle (start), melee (own transition from idle) and a ranged layer machine entered by a
    wildcard, starting in CombatIdle; a walk state no attack reaches."""
    state = lambda ref, sid, gen, trans=None: (ref, {'#': ref, 'class': 'hkbStateMachineStateInfo', 'fields': {  # noqa: E731
        'stateId': sid, 'generator': gen, 'transitions': trans}})
    trans = lambda ref, *ts: (ref, {'#': ref, 'class': T.TRANSITIONS, 'fields': {  # noqa: E731
        'transitions': [{'eventId': e, 'toStateId': s} for e, s in ts]}})
    machine = lambda ref, states, start, wild=None: (ref, {'#': ref, 'class': 'hkbStateMachine', 'fields': {  # noqa: E731
        'states': states, 'startStateId': start, 'wildcardTransitions': wild}})
    triggers = ('#t', {'#': '#t', 'class': 'hkbClipTriggerArray', 'fields': {'triggers': [
        {'event': {'id': 3}, 'localTime': 0.1, 'relativeToEndOfClip': 0},
        {'event': {'id': 2}, 'localTime': 0.2, 'relativeToEndOfClip': 0},
        {'event': {'id': 2}, 'localTime': 0.9, 'relativeToEndOfClip': 0},
        {'event': {'id': 4}, 'localTime': -0.1, 'relativeToEndOfClip': 1}]}})
    return dict([machine('#root', ['#s0', '#s1', '#s2', '#s3'], 0, '#w'), state('#s0', 0, '#idle', '#tr'),
                 state('#s1', 1, '#melee'), state('#s2', 2, '#layer'), state('#s3', 3, '#walk'),
                 trans('#tr', (0, 1), (5, 3)), trans('#w', (1, 2)),
                 machine('#layer', ['#l0', '#l1'], 0), state('#l0', 0, '#combat'), state('#l1', 1, '#shoot'),
                 _clip('#idle', 'Idle'), _clip('#melee', 'AttackRight', '#t', 4), _clip('#walk', 'Walk'),
                 _clip('#combat', 'CombatIdle'), _clip('#shoot', 'RangedAttack'), triggers])


def test_attacks_play_their_target_states_clips_entering_only_start_states():
    """An ATKE event and a gun's fire event lead to their clips (the layer's start state only); 1 marks the
    wildcard transition; movement events are not attacks."""
    objs = _graph()
    found = T.attacks(objs, EVENTS, {'meleestart_right'})
    assert [(e, w, [objs[g]['fields']['name'] for g in gens]) for e, w, gens in found] == [
        ('meleeStart_Right', False, ['AttackRight']), ('rangedAttackStart2', True, ['CombatIdle'])]
    assert T.event_info('G.hkx', found, objs) == (
        b'V2\nG.hkx\n\n2\nmeleeStart_Right\n0\n1\nAttackRight\nrangedAttackStart2\n1\n1\nCombatIdle\n')


def test_a_clip_generators_record_keeps_each_known_events_first_trigger():
    """Triggers: SoundPlay and other unknown events dropped, an event's first time kept, spelled as vanilla; the
    mirror flag becomes the first byte."""
    objs = _graph()
    data = T.generator_data('G.hkx', ['#melee'], objs, EVENTS, SPELLED)
    at = 3 + 1 + len('G.hkx') + 1 + 4
    assert data[:3] == b'V4\n' and struct.unpack_from('<I', data, at - 4)[0] == 1
    names = b'\x0cAttackRight\x00\x0cAttackRight\x00'
    assert data[at:at + len(names)] == names
    speed, start, end, mirror, dynamic, count = struct.unpack_from('<3f2BI', data, at + len(names))
    assert (speed, start, end, mirror, dynamic, count) == (1.0, 0.0, 0.0, 1, 0, 2)
    rest = data[at + len(names) + 18:]
    assert rest.startswith(b'\x09FootLeft\x00') and b'WeaponFire' in rest and b'SoundPlay' not in rest
    assert struct.unpack_from('<f', rest, 10)[0] == struct.unpack('<f', struct.pack('<f', 0.2))[0]


def _race(*subs, tag: bytes = b'RACE', form: int = 0) -> bytes:
    """A packed record of `subs` (tag, text or raw bytes)."""
    return tag + bytes(8) + struct.pack('<I', form) + bytes(8) + b''.join(
        pack_subrecord(t, x if isinstance(x, bytes) else x.encode() + b'\0') for t, x in subs)


def test_a_races_project_is_its_first_model_after_nam3():
    """The project is the first MODL after NAM3; ATKE events lower-cased; body part data; equip slots naming a
    node, by their index among all slots."""
    body = _race(('MODL', 'Actors\\Character\\Upper.egt'), ('NAM3', ''), ('MODL', 'Actors\\X\\XProject.hkx'),
                 ('MODL', 'Actors\\X\\XProject.hkx'), ('ATKE', 'meleeStart_Left'), ('SGNM', 'Actors\\X\\B.hkx'),
                 ('GNAM', struct.pack('<I', 7)), ('QNAM', bytes(4)), ('QNAM', bytes(4)), ('ZNAM', 'WEAPON2'))
    race = T.race_fields(body[24:])
    assert (race.project, race.graphs, race.attack) == ('Actors\\X\\XProject.hkx', ['Actors\\X\\B.hkx'],
                                                         {'meleestart_left'})
    assert (race.body, race.slots) == (7, [(1, 'WEAPON2')])


def test_a_race_on_a_graph_the_build_did_not_write_gets_nothing():
    """A graph read() can't find (a vanilla one) gives no files."""
    race = _race(('NAM3', ''), ('MODL', 'Actors\\Character\\CharacterProject.hkx'),
                 ('SGNM', 'Actors\\Character\\Behaviors\\RaiderRootBehavior.hkx'))
    assert T.creatures([race], lambda rel: None, T.Known(), {}) == {}


def test_body_parts_name_each_part_types_first_node():
    """{BPTD id: {part type: node}}, from each BPNN before its BPND."""
    head, torso = (bytes(T.PART_TYPE) + bytes([kind]) + bytes(10) for kind in (T.HEAD, T.TORSO))
    rec = _race(('BPNN', 'Head'), ('BPND', head), ('BPNN', 'Spine'), ('BPND', torso),
                ('BPNN', 'Neck'), ('BPND', head), tag=b'BPTD', form=9)
    assert T.body_parts([rec]) == {9: {T.HEAD: 'Head', T.TORSO: 'Spine'}}


def test_the_armed_clip_follows_the_equip_event_from_the_start_state():
    """Settling with a weapon out takes the start state's transition on weapEquip."""
    objs = {**_graph(), '#g': {'#': '#g', 'class': 'hkbBehaviorGraph', 'fields': {'rootGenerator': '#root'}}}
    assert T.armed_clip('Actors\\X', objs, EVENTS) == 'Actors\\X\\Animations\\Idle.hkx'
    assert T.armed_clip('Actors\\X', objs, EVENTS[:5] + ['weapEquip']) == 'Actors\\X\\Animations\\Walk.hkx'


def test_a_stance_poses_head_torso_and_the_first_slots_fire_record():
    """One pose (head, torso, identity DirectAt), then a fire record per slot: posed for slot 0, identity else."""
    pose = {name: np.eye(4) for name in ('Head', 'Spine', 'Weapon', 'Weapon2')}
    pose['Head'][3, :3], pose['Weapon'][3, :3] = (1, 2, 3), (4, 5, 6)
    race = T.Race(slots=[(0, 'Weapon'), (2, 'Weapon2')])
    data = T.stance(race, pose, {T.HEAD: 'Head', T.TORSO: 'Spine'})
    assert len(data) == 124 + 2 * 50 and data.startswith(b'\x17AnimationBoneTransform\x00')
    assert struct.unpack_from('<7f', data, 36) == (1, 0, 0, 0, 1, 2, 3)
    assert struct.unpack_from('<I', data, 120)[0] == 2 and data[124:128] == bytes(4)
    assert struct.unpack_from('<7f', data, 128)[4:] == (4, 5, 6) and data[174 + 3] == 2
    assert data[178:206] == T.IDENTITY and T.stance(race, pose, {T.HEAD: 'Head'}) is None


def test_file_data_names_its_clips_not_its_behavior_graphs():
    """Clips by stem (first wins), no extension; behavior graphs left out."""
    text = '3\r\n1\r\n7\r\n3\r\nActors\\C\\Behaviors\\B.hkx\r\nActors\\FNV\\C\\Walk.hkx\r\nActors\\C\\Walk.hkx\r\n0\r\n'
    assert T.file_data_names(text) == {'Walk': 'Actors\\FNV\\C\\Walk'}


def test_prune_removes_what_this_run_did_not_write(tmp_path: Path):
    """Files of the owned kinds this run didn't write go; written ones, the persistent list and file data stay."""
    root = tmp_path / ANIM_TEXT
    files = {'AnimationOffsets/1.txt': 'new', 'AnimationOffsets/2.txt': 'stale', 'AnimEventInfo/3.txt': 'stale',
             PERSISTENT.relative_to(ANIM_TEXT).as_posix(): 'list', 'AnimationFileData/2.txt': 'ours'}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    written = T.write(tmp_path, {'AnimationOffsets\\1.txt': b'new'}) + T.write(tmp_path, T.sync_data('A.esm'))
    assert T.prune(tmp_path, written) == 2
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob('*.txt')) == [
        'AnimationFileData/2.txt', 'AnimationOffsets/1.txt', PERSISTENT.relative_to(ANIM_TEXT).as_posix(),
        'SyncAnimData/ResolvedSyncAnimDataA.txt']
