"""FNV GetInCell name groups as FO4 member tests (cell_families) and their exterior cells' own locations.

See: docs/fork/fo4_pipeline.md#cell-families
"""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import cell_families as CF
from fo4_import.spike import conditions as C
from fo4_import.spike import locations as LO
from fo4_import.spike import say_topics as SAY
from tes5_import.base.tes5_reader import subrecords

#: FO3's BigTown dummy interior, a BigTown interior, and a built and an unbuilt BigTown exterior.
BIG_TOWN, CLINIC, NE, SW = 0x2ADC4, 0x2ADC5, 0x2ADC6, 0x2ADC7
KEYWORD = 0x0A000100


def _cond(value: float, p1: int = BIG_TOWN, flags: int = 0, func: str = 'GetInCell') -> dict:
    """A parsed FNV test `func`(p1) == value, run on the Target, `flags` added."""
    return {'op_flags': flags, 'value': value, 'func': func, 'p1': p1, 'p2': 0, 'run_on': 1, 'ref': 0, 'global': 0}


FAMILIES = {(CF.FAMILY, BIG_TOWN): ((BIG_TOWN, CLINIC), KEYWORD)}


def test_in_the_group_is_an_or_of_its_interiors_and_its_keyword():
    """MS01MineLearn's GetInCell BigTown == 1 on the player: true in either interior or where the keyword is."""
    other = _cond(1.0, 0x14E94, func='GetQuestVariable')
    out = CF.in_families([other, _cond(1.0)], FAMILIES)
    assert out[0] == other
    assert [(c['func'], c['p1'], c['op_flags']) for c in out[1:]] == [
        ('GetInCell', BIG_TOWN, C.OR_NEXT), ('GetInCell', CLINIC, C.OR_NEXT), ('LocationHasKeyword', KEYWORD, 0)]


def test_not_in_the_group_is_an_and_distributed_over_its_or_group():
    """(A or GetInCell BigTown == 0) is (A or not in BigTown) and (A or not in the clinic) and (A or no keyword)."""
    a = _cond(1.0, 0x14E94, flags=C.OR_NEXT, func='GetQuestVariable')
    out = CF.in_families([a, _cond(0.0)], FAMILIES)
    assert len(C.groups(out)) == 3
    assert [[(c['func'], c['p1']) for c in g] for g in C.groups(out)] == [
        [('GetQuestVariable', 0x14E94), ('GetInCell', BIG_TOWN)], [('GetQuestVariable', 0x14E94), ('GetInCell', CLINIC)],
        [('GetQuestVariable', 0x14E94), ('LocationHasKeyword', KEYWORD)]]


def test_get_in_cell_param_of_a_group_tests_each_member_and_the_references_location():
    """MS02's `GetInCellParam Vault101 ButchRef != 1` (the dummy Vault101 names every Vault101 interior): Butch is
    in no member, and the keyword test reads ButchRef's location.
    See: docs/fork/fo4_pipeline.md#cell-families
    """
    butch = 0x2A4E8
    cond = {**_cond(1.0, flags=0x20, func='GetInCellParam'), 'p2': butch, 'run_on': 0}
    out = CF.in_families([cond], FAMILIES)
    assert [(c['func'], c['p1'], c['p2'], c['run_on'], c['ref']) for c in out] == [
        ('GetInCellParam', BIG_TOWN, butch, 0, 0), ('GetInCellParam', CLINIC, butch, 0, 0),
        ('LocationHasKeyword', KEYWORD, 0, C.RUN_REFERENCE, butch)]
    assert len(C.groups(out)) == 3
    rec = {'Condition[0].Raw': struct.pack('<B3xfHHIIII', 0x20, 1.0, C.FNV.index('GetInCellParam'), 0, BIG_TOWN, butch,
                                           0, 0).hex()}
    ctda = SAY.conditions_of(rec, {**FAMILIES, CLINIC: 0x0A00C5C5, butch: 0x0A0B4EA0}, {})
    funcs = [struct.unpack_from('<HxxII', d, 8) for t, d in subrecords(ctda) if t == b'CTDA']
    assert funcs == [(C.FO4.index('GetInCellParam'), 0x0A00C5C5, 0x0A0B4EA0), (C.FO4.index('LocationHasKeyword'), KEYWORD, 0)]


def test_a_cell_that_names_no_group_and_a_global_test_stay_as_they_are():
    """A GetInCell of a one-cell name, and one compared against a global, are untouched."""
    plain = [_cond(1.0, 0x1234)]
    assert CF.in_families(plain, FAMILIES) == plain
    by_global = [_cond(1.0, flags=C.USE_GLOBAL)]
    assert CF.in_families(by_global, FAMILIES) == by_global


def test_unbuilt_members_settle_and_the_line_converts():
    """The dummy BigTown is never built: its member test reads 0 and drops out of the OR, the clinic and keyword
    stay, so the converted conditions test them, not "never true"."""
    rec = {'Condition[0].Raw': struct.pack('<B3xfHHIIII', 0, 1.0, C.FNV.index('GetInCell'), 0, BIG_TOWN, 0, 0, 0).hex()}
    form_map = {**FAMILIES, CLINIC: 0x0A00C5C5}
    out = SAY.conditions_of(rec, form_map, {})
    funcs = [struct.unpack_from('<HxxI', d, 8) for t, d in subrecords(out) if t == b'CTDA']
    assert funcs == [(C.FO4.index('GetInCell'), 0x0A00C5C5), (C.FO4.index('LocationHasKeyword'), KEYWORD)]


def test_groups_are_built_from_the_named_anchors_and_the_exteriors_get_the_keyword():
    """BigTown names six cells by prefix; only the built exterior carries the keyword; a one-cell name is no group."""
    cells = [{'FormID': f'{f:08X}', 'EditorID': e, **x} for f, e, x in (
        (BIG_TOWN, 'BigTown', {}), (CLINIC, 'BigTownRedClinic', {}),
        (NE, 'BigTownNE', {'ParentWRLD': '0000003C', 'DATA.Flags': '2'}),
        (SW, 'BigTownSW', {'ParentWRLD': '0000003C', 'DATA.Flags': '2'}), (0x500, 'Megaton01', {}))]
    raw = struct.pack('<B3xfHHIIII', 0, 1.0, C.FNV.index('GetInCell'), 0, BIG_TOWN, 0, 0, 0).hex()
    one = struct.pack('<B3xfHHIIII', 0, 1.0, C.FNV.index('GetInCell'), 0, 0x500, 0, 0, 0).hex()
    records = {'CELL': cells, 'PACK': [{'Condition[0].Raw': raw, 'Condition[1].Raw': one}]}
    written = []
    builder = SimpleNamespace(cell_ids={NE: 0x0A00E6E6}, counts=Counter(), writer=SimpleNamespace(
        derive_formid=lambda site, key: KEYWORD, add_record=lambda sig, body: written.append(sig)))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(CF, 'export_records', lambda _, sig: records.get(sig, []))
        assert CF.cell_families(builder, None) == {(CF.FAMILY, BIG_TOWN): ((BIG_TOWN, CLINIC), KEYWORD)}
    assert builder.family_cells == {NE: [KEYWORD]} and written == ['KYWD']


def test_a_group_member_exterior_gets_its_own_location_with_the_keyword():
    """BigTownNE's location is a child of its region's, with that name and marker and the group keyword; any other
    exterior keeps the region's."""
    written = []
    builder = SimpleNamespace(family_cells={NE: [KEYWORD]}, counts=Counter(), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x0A000200, add_record=lambda sig, body: written.append(body)))
    locations = LO.Locations.__new__(LO.Locations)
    locations.builder, locations.root, locations.regions = builder, 0x0A000001, []
    locations.shown = {0x0A000001: ('Capital Wasteland', 0x0A000050)}
    assert locations.of_cell({'FormID': f'{NE:08X}', 'EditorID': 'BigTownNE'}, (-4, 4)) == 0x0A000200
    subs = dict(subrecords(written[0][24:]))
    assert subs[b'FULL'] == b'Capital Wasteland\0' and subs[b'KWDA'] == struct.pack('<I', KEYWORD)
    assert subs[b'PNAM'] == struct.pack('<I', 0x0A000001) and subs[b'MNAM'] == struct.pack('<I', 0x0A000050)
    assert locations.of_cell({'FormID': f'{SW:08X}'}, (-4, 3)) == 0x0A000001
