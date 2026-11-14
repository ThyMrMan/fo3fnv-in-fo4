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
    """A menu answer left out (GetDisposition has no FO4 function) gets its count and readiness entry."""
    say = SAY.SayTopics.__new__(SAY.SayTopics)
    say.builder = SimpleNamespace(counts=collections.Counter(), readiness=Readiness())
    say.script_vars = {}
    assert say.left_out(line(raw('GetDisposition', 30.0)), {}) == b''
    assert say.builder.counts == {'line left out (condition: GetDisposition)': 1}
    assert say.builder.readiness.entries == [{'kind': LINE_LEFT_OUT, 'owner': '001164BF',
                                              'detail': '00175680 (condition: GetDisposition)'}]
