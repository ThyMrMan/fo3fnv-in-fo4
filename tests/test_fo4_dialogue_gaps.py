"""fo4_import.spike dialogue gaps: empty form params, unmade items, races, tested classes, answers left out.

See: docs/fork/fo4_dialogue_gaps.md
"""

import collections
import struct
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.spike import condition_forms as CF
from fo4_import.spike import conditions as CD
from fo4_import.spike import npcs as N
from fo4_import.spike import replacements
from fo4_import.spike import say_topics as SAY
from fo4_import.spike import voice_types as VT
from fo4_import.spike.classes import Classes
from fo4_import.spike.readiness import LINE_LEFT_OUT, Readiness
from tes5_import.base.tes5_reader import first_sub, subrecords

#: Fallout4.esm HumanChildRace, HumanRace and Citizen (npcs.HUMAN_CLASS).
CHILD_RACE, HUMAN_RACE, CITIZEN = 0x11D83F, 0x13746, N.HUMAN_CLASS
#: FNV's VendorTraveler class and the SlaveCollar armor.
VENDOR_TRAVELER, SLAVE_COLLAR = 0x15C4D6, 0x2F563


def raw(func: str, value: float, p1: int = 0, op: int = 0, run_on: int = 0) -> str:
    """One FNV condition of `func`, as raw hex."""
    return struct.pack('<B3xfIIIII', op, value, CD.FNV.index(func), p1, 0, run_on, 0).hex()


def line(*conds: str) -> dict:
    """An FNV line record with conditions `conds` (raw hex)."""
    return {'FormID': '00175680', 'QSTI.Quest': '001164BF', 'ConditionCount': str(len(conds)),
            **{f'Condition[{i}].Raw': c for i, c in enumerate(conds)}}


def test_an_empty_actor_param_converts_as_the_other_party():
    """GetFactionRelation with no actor (FNV and FO4 read the line's other party) converts with its parameter 0,
    as Fallout4.esm writes it; it used to leave the line out."""
    ctda = SAY.conditions_of(line(raw('GetFactionRelation', 2.0, op=0x80)), {}, {})
    assert ctda is not None
    assert struct.unpack_from("<H", ctda, 14)[0] == CD.FO4.index('GetFactionRelation')
    assert struct.unpack_from("<II", ctda, 18) == (0, 0)


def test_an_item_the_build_cannot_make_is_held_by_no_one():
    """An item test of an item the build cannot make (SlaveCollar) reads 0: `== 1` never passes, `== 0` always."""
    builder = SimpleNamespace(cell_ids={}, regions={}, counts=collections.Counter(),
                              items=SimpleNamespace(item=lambda fid: None))
    form_map = CF.condition_forms(builder, [line(raw('GetItemCount', 1.0, SLAVE_COLLAR))])
    assert form_map == {(CD.UNMADE, SLAVE_COLLAR): 0}
    assert CD.without_absent([CD.parse(raw('GetItemCount', 1.0, SLAVE_COLLAR))], form_map) is None
    assert CD.without_absent([CD.parse(raw('GetItemCount', 0.0, SLAVE_COLLAR))], form_map) == []


def test_an_actor_a_line_tests_is_made_before_the_line_converts():
    """FFER11Settler is never placed (FFERepeatA's script spawns it): a line testing GetIsID of it makes its base
    now (Npcs.actor_form), so the line converts instead of reading the test as never true; a non-actor stays out.
    See: docs/fork/fo4_pipeline.md#line-actors
    """
    settler, made = 0x3DBB3, []
    npcs = SimpleNamespace(actor_form=lambda fid: made.append(fid) or (0x02BA7AF0 if fid == f'{settler:08X}' else None))
    lines = [line(raw('GetIsID', 1.0, settler, run_on=0)), line(raw('GetIsID', 1.0, settler), raw('GetIsID', 1.0, 0x14)),
             line(raw('GetIsID', 1.0, 0x1234))]
    assert CF.condition_actors(npcs, lines, {}) == {settler: 0x02BA7AF0}
    assert made == [f'{settler:08X}', '00001234']
    assert CF.condition_actors(npcs, lines, {settler: 1, 0x1234: 2}) == {}
    assert CF.condition_actors(None, lines, {}) == {}


def test_a_script_effect_test_reads_its_family_keyword_and_base_karma_the_karma_global():
    """MS13's `HasMagicEffect MS13Mezzed` becomes HasMagicEffectKeyword of the effect's family keyword (the one its
    spell's copy carries); MQ11's `GetBaseActorValue Karma >= 250` reads the karma global.
    See: docs/fork/fo4_pipeline.md#effect-tests
    """
    mezzed, family, karma = 0x3D1F9, 0x0A000300, 0x0A000400
    scripts = SimpleNamespace(effects=SimpleNamespace(family_of=lambda fnv: family if fnv == mezzed else None))
    tested = [line(raw('HasMagicEffect', 1.0, mezzed)), line(raw('HasMagicEffect', 1.0, 0x1234))]
    form_map = CF.condition_effects(scripts, tested)
    assert form_map == {(CD.EFFECT, mezzed): family}
    ctda = SAY.conditions_of(tested[0], form_map, {})
    assert struct.unpack_from('<HxxI', ctda, 14) == (CD.FO4.index('HasMagicEffectKeyword'), family)
    base = SAY.conditions_of(line(raw('GetBaseActorValue', 250.0, 23, op=0x60, run_on=1)), {SAY.KARMA_KEY: karma}, {})
    assert struct.unpack_from('<HxxI', base, 14) == (CD.FO4.index('GetGlobalValue'), karma)


def test_a_form_list_entry_that_is_an_actor_base_is_made_on_demand():
    """Chesterbrook's NPC list names an NPC only a script places: the list's entry makes it (Npcs.actor_form), so
    `IsInList` of the list is not settled as never true; a non-actor entry asks no actor."""
    from fo4_import.spike.items import Items
    asked = []
    items = Items.__new__(Items)
    items.messages, items.builder = {}, SimpleNamespace(
        fnv_types={0x2E032: 'NPC_', 0x1234: 'GLOB'}, scripts=None,
        npcs=SimpleNamespace(actor_form=lambda fid: asked.append(fid) or 0x0A02E032))
    assert items._built(0x2E032) == 0x0A02E032 and items._built(0x1234) is None and asked == ['0002E032']
    assert 'IsWeaponInList' in CF.ITEM_TESTS


def test_the_players_voice_types_are_fallout4s_own_from_the_start(monkeypatch):
    """CG02's grunt tests GetIsVoiceType PlayerVoiceMale, which no NPC uses: it reads FO4's PlayerVoiceMale01,
    written by no one, whose folder takes FO3's player recordings; another voice type is still written on use.
    See: docs/fork/fo4_pipeline.md#player-voices
    """
    monkeypatch.setattr(VT, 'fnv_voice_types', lambda: {0x2853B: ('PlayerVoiceMale', 0), 0x40D42: (
        'PlayerVoiceFemale', 2), 0x1234: ('MaleAdult01', 0)})
    written = []
    builder = SimpleNamespace(fnv_id=lambda fid: 0x02000000 | int(fid, 16), counts=collections.Counter(),
                              writer=SimpleNamespace(add_record=lambda sig, rec: written.append(sig)))
    voices = VT.VoiceTypes(builder)
    assert voices.ids == {0x2853B: 0x18DF4, 0x40D42: 0x18DF7} and not written
    assert voices.made == {'PlayerVoiceMale01': 'PlayerVoiceMale', 'PlayerVoiceFemale01': 'PlayerVoiceFemale'}
    assert voices.of(0x2853B) == 0x18DF4 and voices.of(0x1234) == 0x02001234 and written == ['VTYP']
    grunt = line(raw('GetIsVoiceType', 1.0, 0x2853B, op=CD.OR_NEXT), raw('GetIsVoiceType', 1.0, 0x40D42))
    ctda = SAY.conditions_of(grunt, voices.ids, {})
    assert [struct.unpack_from('<I', ctda, at)[0] for at in (18, 56)] == [0x18DF4, 0x18DF7]


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_a_race_test_names_the_race_its_npcs_get():
    """Lily's GetIsRace CaucasianChild (Target) becomes FO4's HumanChildRace, an adult race HumanRace."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.races, npcs.child_races = {0x19: 'Caucasian', 0x42C2: 'CaucasianChild'}, {0x42C2}
    npcs.bodies = N.bodies(FALLOUT4_ESM.read_bytes(), replacements.load().rules.body)
    npcs.classes = SimpleNamespace(form_map=dict)
    forms = npcs.trait_forms()
    assert forms == {0x42C2: CHILD_RACE, 0x19: HUMAN_RACE}
    ctda = SAY.conditions_of(line(raw('GetIsRace', 1.0, 0x42C2, run_on=1)), forms, {})
    assert struct.unpack_from("<HxxI", ctda, 14) == (CD.FO4.index('GetIsRace'), CHILD_RACE)


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_a_class_a_line_tests_is_written_once_and_given_to_its_npcs():
    """VendorTraveler, tested by a line, is written once as a copy of Citizen; another class stays Citizen; the
    NPC edit sets CNAM; the line's GetIsClass converts to it."""
    written = []
    builder = SimpleNamespace(fo4=FALLOUT4_ESM.read_bytes(), fnv_id=lambda fid: 0x800000 | fid & 0xFFFF,
                              writer=SimpleNamespace(add_record=lambda sig, rec: written.append((sig, rec))),
                              counts=collections.Counter())
    names = {VENDOR_TRAVELER: 'VendorTraveler', 0x1234: 'Other'}
    classes = Classes(builder, [line(raw('GetIsClass', 1.0, VENDOR_TRAVELER))], names, CITIZEN)
    made = classes.of(VENDOR_TRAVELER)
    assert made == classes.of(VENDOR_TRAVELER) == 0x80C4D6 and len(written) == 1
    assert classes.of(0x1234) == CITIZEN
    assert [tag for tag, _ in subrecords(written[0][1][24:])] == [b'EDID', b'PRPS', b'DATA']
    assert first_sub(N.with_class(made)(first_sub_record()), b'CNAM') == struct.pack('<I', made)
    ctda = SAY.conditions_of(line(raw('GetIsClass', 1.0, VENDOR_TRAVELER)), classes.form_map(), {})
    assert struct.unpack_from("<HxxI", ctda, 14) == (CD.FO4.index('GetIsClass'), made)


def first_sub_record() -> bytes:
    """An NPC's subrecords holding CNAM Citizen."""
    return b'CNAM' + struct.pack('<HI', 4, CITIZEN)


def test_an_answer_line_whose_condition_cannot_convert_is_counted():
    """A menu answer left out (GetDisposition, its helper value not mapped) gets its count and readiness entry, once
    however many speakers or scenes try it."""
    say = SAY.SayTopics.__new__(SAY.SayTopics)
    say.builder = SimpleNamespace(counts=collections.Counter(), readiness=Readiness())
    say.script_vars, say.left = {}, set()
    assert say.left_out(line(raw('GetDisposition', 30.0)), {}) == b''
    assert say.left_out(line(raw('GetDisposition', 30.0)), {}) == b''
    assert say.builder.counts == {'line left out (condition: GetDisposition)': 1}
    assert say.builder.readiness.entries == [{'kind': LINE_LEFT_OUT, 'owner': '001164BF',
                                              'detail': '00175680 (condition: GetDisposition)'}]
