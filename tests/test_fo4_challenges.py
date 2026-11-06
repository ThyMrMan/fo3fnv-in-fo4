"""FNV challenges on FO4: each type's event, the records a kept challenge gets, its filters, the reward spell, the
challenge commands, and the census of FalloutNV.esm.

See: docs/fork/fo4_pipeline.md#challenges
"""

import collections
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.spike import challenges as C
from fo4_import.spike import pipboy_tabs as T
from fo4_import.spike import script_effects as SE
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.pipeline import pack_wstring
from tes5_import.base.tes5_reader import subrecords

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'


def _chal(kind: int, value1: int = 0, value2: int = 0, value3: int = 0, **extra) -> dict:
    """An exported CHAL of type `kind` with DATA values and `extra` keys."""
    return {'EditorID': f'C{kind}_{value1}_{value2}_{value3}', 'FormID': '0016BA4E', 'DATA.Type': str(kind),
            'DATA.Value1': str(value1), 'DATA.Value2': str(value2), 'DATA.Value3': str(value3),
            'DATA.Threshold': '10', 'DATA.Interval': '5', 'DATA.Flags': '0', **extra}


def _builder(written: list) -> SimpleNamespace:
    """A builder stand-in keeping (signature, record) in `written`; FormIDs from the key's length."""
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x01000000 + len(str(key)),
                             add_record=lambda sig, rec: written.append((sig, rec)), own_index=1)
    return SimpleNamespace(writer=writer, counts=collections.Counter(), fnv_id=lambda f: 0x02000000 | int(f, 16),
                           scripts=SimpleNamespace(used=[], names={0x15EAAA: 'ChallengeLowXPSCRIPT'},
                                                   effects=SimpleNamespace(script_spell=lambda s, e: 0x0300)))


@pytest.mark.parametrize('rec,expected', [
    (_chal(0, 0, 34), (C.KILL, ())),
    (_chal(2, 0, 4), (C.KILL, ())),
    (_chal(3, 0, 1, 6), (C.STAT, C.CRITICALS)),
    (_chal(4), (C.MARKER, C.DISCOVERIES)),
    (_chal(5), (C.USE, ())),
    (_chal(9), (C.USE, ())),
    (_chal(11, 4), (C.STAT, ('Locks Picked',))),
    (_chal(11, 32), (C.STAT, ('Chems Crafted', 'Food Cooked'))),
    (_chal(11, 35), (C.KILL, ())),
    (_chal(11, 30), (C.CRIPPLED, ())),
    (_chal(11, 27), (C.COMPLETED, ())),
])
def test_each_counted_type_has_its_event(rec, expected):
    """Each counted type maps to its event and FO4 stats."""
    assert C.counting(rec) == expected


@pytest.mark.parametrize('rec,reason', [
    (_chal(8), 'do damage'),
    (_chal(3, 1, 0), 'hit (damage, body part)'),
    (_chal(3, 0, 3), 'hit (cripple)'),
    (_chal(11, 37), 'misc stat Caravan Games Won'),
])
def test_types_without_an_fo4_event_are_left_out(rec, reason):
    """Types with no FO4 event are left out, with why."""
    assert C.counting(rec) == reason


def test_fnv_stats_are_the_engine_s_43():
    """FalloutNV.exe has 43 misc stats; the maps name only those."""
    assert len(C.FNV_STATS) == 43 and C.FNV_STATS[27] == 'Challenges Completed'
    assert set(C.FO4_STATS) <= set(C.FNV_STATS) and set(C.STAT_EVENTS) <= set(C.FNV_STATS)


def test_creature_types_follow_use_traits_templates(monkeypatch):
    """A creature using its template's traits takes the template's type; one that does not keeps its own."""
    recs = [{'FormID': '00000001', 'DATA.CreatureType': '6'},
            {'FormID': '00000002', 'DATA.CreatureType': '0', 'TPLT.Template': '00000001', 'ACBS.TemplateFlags': '1'},
            {'FormID': '00000003', 'DATA.CreatureType': '2', 'TPLT.Template': '00000001', 'ACBS.TemplateFlags': '2'}]
    monkeypatch.setattr(C, 'export_records', lambda path, sig: recs)
    assert C.creature_types(Path('x')) == {1: 6, 2: 6, 3: 2}


def _filters(written: list) -> C.Filters:
    """Filters over three FNV weapons (an energy pistol, a laser rifle, a power fist) the build made."""
    filters = C.Filters.__new__(C.Filters)
    made = {0x10: 0x5010, 0x11: 0x5011, 0x12: 0x5012}
    filters.builder = SimpleNamespace(**vars(_builder(written)), items=SimpleNamespace(shared={}, made=made),
                                      creatures=SimpleNamespace(made={0x20: 0x6020, 0x21: 0x6021}), npc_ids={},
                                      ref_ids={'000CDF00': 0x7000})
    filters.weapon_recs = [{'FormID': '00000010', 'DNAM.Skill': '34', 'DNAM.FalloutAnimType': '4'},
                           {'FormID': '00000011', 'DNAM.Skill': '34', 'DNAM.FalloutAnimType': '7'},
                           {'FormID': '00000012', 'DNAM.Skill': '45', 'DNAM.FalloutAnimType': '0'}]
    filters.lists, filters.types, filters.fists = {0x30: [0x11]}, {0x20: 6, 0x21: 1}, 0x9999
    return filters


def _members(record: bytes) -> list:
    """The LNAM FormIDs of a written FLST."""
    return [struct.unpack('<I', data)[0] for tag, data in subrecords(record[24:]) if tag == b'LNAM']


def test_weapon_filters_take_skill_type_list_and_fists():
    """A kill's skill and type, a critical's type and list pick the made weapons; Unarmed adds the fists."""
    written = []
    filters = _filters(written)
    filters.weapons(_chal(0, 0, 34))
    filters.weapons(_chal(3, 0, 1, 5))
    filters.weapons(_chal(3, 0, 1, 0, XNAM='00000030'))
    filters.weapons(_chal(0, 0, 45))
    assert [_members(rec) for _, rec in written] == [[0x5010, 0x5011], [0x5010], [0x5011], [0x5012, 0x9999]]
    assert filters.weapons(_chal(2, 0, 7)) == 0 and filters.weapons(_chal(11, 4)) == 0


def test_victims_items_and_markers_are_the_build_s():
    """A creature type picks the creatures made of it; a use names the made item; a marker its placed reference."""
    written = []
    filters = _filters(written)
    filters.victims(_chal(2, 0, 7))
    filters.items(_chal(5, SNAM='00000010'))
    assert [_members(rec) for _, rec in written] == [[0x6020], [0x5010]]
    assert filters.marker(_chal(4, SNAM='000CDF00')) == 0x7000 and filters.marker(_chal(4, SNAM='00000001')) == 0


def test_a_kept_challenge_gets_its_row_state_quest_and_tab(monkeypatch):
    """The row is an actor value on the CHAL's FormID; the state global reads its flags; the quest carries the arrays
    and the tab comes after KARMA."""
    written = []
    builder = _builder(written)
    monkeypatch.setattr(C, 'Filters', lambda b, e: SimpleNamespace(weapons=lambda r: 0, victims=lambda r: 0,
                                                                   items=lambda r: 0, marker=lambda r: 0))
    monkeypatch.setattr(C, 'fo4_weapon', lambda fo4, edid: 0x9999)
    builder.fo4 = b''
    shown, locked = _chal(11, 4, FULL='Locks', SCRI='0015EAAA', **{'DATA.Flags': '4'}), \
        _chal(11, 5, **{'DATA.Flags': '3', 'FormID': '00165779'})
    chal = C.Challenges.__new__(C.Challenges)
    chal.builder, chal.export_dir, chal.kept = builder, None, [(shown, C.STAT, ('Locks Picked',)),
                                                               (locked, C.STAT, ('Computers Hacked',))]
    chal.write()
    sigs = [sig for sig, _ in written]
    assert sigs.count('AVIF') == 2 and sigs.count('GLOB') == 2 and sigs.count('QUST') == 2
    assert struct.unpack_from('<I', written[0][1], 12)[0] == 0x0216BA4E
    values = [struct.unpack('<f', dict(subrecords(rec[24:]))[b'FLTV'])[0] for sig, rec in written if sig == 'GLOB']
    assert values == [1.0, -2.0]
    quest = next(rec for sig, rec in written if sig == 'QUST' and pack_wstring(C.SCRIPT) in rec)
    assert pack_wstring('Locks Picked') in quest and pack_wstring(C.PLAYER_SCRIPT) in quest
    assert T.ORDER['CHALLENGES'] > T.ORDER['KARMA'] and builder.counts['CHAL kept'] == 2


def test_a_dlc_writes_only_its_own_challenges_adding_them_to_the_games_tab(monkeypatch):
    """A plugin (load byte 2) whose master holds the counting quest: only its own challenge is kept, on its own
    quest (F3NV_ChallengeSource) naming the master's tab lists; no tab or list of its own; the stat group is the
    fixed table's number."""
    written = []
    builder = _builder(written)
    builder.writer.own_index, builder.fo4 = 2, b''
    builder.ids = SimpleNamespace(is_own=lambda fid: fid >> 24 == 1)
    monkeypatch.setattr(C, 'Filters', lambda b, e: SimpleNamespace(weapons=lambda r: 0, victims=lambda r: 0,
                                                                   items=lambda r: 0, marker=lambda r: 0))
    own, game = _chal(11, 4, FormID='01000900'), _chal(11, 5, FormID='00165779')
    chal = C.Challenges.__new__(C.Challenges)
    chal.builder, chal.export_dir = builder, Path('DeadMoney.esm')
    chal.kept = [(own, C.STAT, ('Locks Picked',)), (game, C.STAT, ('Computers Hacked',))]
    assert chal.write() is None
    quests = [rec for sig, rec in written if sig == 'QUST']
    assert builder.counts['CHAL kept'] == 1 and len(quests) == 1 and not [s for s, _ in written if s == 'FLST']
    assert pack_wstring(C.SOURCE_SCRIPT) in quests[0] and pack_wstring(C.SCRIPT) not in quests[0]
    assert b'FNV_Challenges_DeadMoney\0' in quests[0] and pack_wstring('TabRows') in quests[0]
    assert struct.pack('<I', builder.writer.derive_formid(C.SITE, 'rows')) in quests[0]
    assert struct.pack('<i', C.STAT_GROUPS.index(('Locks Picked',))) in quests[0]


def test_a_reward_script_becomes_a_self_fire_and_forget_spell():
    """The reward is one Script effect carrying the converted script, cast fire and forget on self; written once."""
    written = []
    builder = SimpleNamespace(counts=collections.Counter(), writer=_builder(written).writer,
                              scripts=SimpleNamespace(name=lambda scpt: 'X', vmad=lambda scpt: b'vmad'))
    fx = SE.ScriptEffects.__new__(SE.ScriptEffects)
    fx.builder, fx.made, fx.made_effects = builder, {}, {}
    fx.templates = ({b'DATA': bytes(152), b'ETYP': bytes(4)}, {b'ETYP': bytes(4)})
    assert fx.script_spell(0x15EAAA, 'FNV_RewardA') == fx.script_spell(0x15EAAA, 'FNV_RewardA')
    (_, mgef), (_, spel) = written
    assert dict(subrecords(mgef[24:]))[b'VMAD'] == b'vmad'
    cast, delivery = struct.unpack_from('<II', dict(subrecords(mgef[24:]))[b'DATA'], SE.CAST_AT)
    assert (cast, delivery) == (SE.FIRE_AND_FORGET, SE.DELIVERY['Self'])
    assert struct.unpack_from('<IIIfII', dict(subrecords(spel[24:]))[b'SPIT'])[4:] == (SE.FIRE_AND_FORGET, 0)


def test_challenge_commands_call_the_challenges_quest_on_fallout4(monkeypatch):
    """UnlockChallenge, RemoveRecurringFromChallenge and GetChallengeCompleted call F3NV_Challenges on the
    challenge's state global."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'fallout4')
    src = ('scn T\nbegin ScriptEffectStart\n  UnlockChallenge NVChallengeBug\n  RemoveRecurringFromChallenge NVChallengeBug\n'
           '  if GetChallengeCompleted NVChallengeBug\n    player.RewardXP 5\n  endif\nend\n')
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ActiveMagicEffect', 'T')
    assert 'F3NV_Challenges.Unlock(NVChallengeBug)' in out and 'F3NV_Challenges.StopRecurring(NVChallengeBug)' in out
    assert 'F3NV_Challenges.Completed(NVChallengeBug)' in out
    assert 'GlobalVariable Property NVChallengeBug' in out and 'TODO' not in out


@pytest.mark.skipif(not (EXPORT / 'CHAL.txt').exists(), reason='needs the FalloutNV.esm export')
def test_census_of_falloutnv():
    """FalloutNV.esm's 105 challenges: 61 counted, 44 left out (18 damage)."""
    recs = C.export_records(EXPORT, 'CHAL')
    how = [C.counting(r) for r in recs]
    assert len(recs) == 105 and sum(not isinstance(h, str) for h in how) == 61
    assert how.count('do damage') == 18
