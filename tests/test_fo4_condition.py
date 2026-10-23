"""FNV weapon condition on Fallout 4: the curves, the condition mods, wear perks and which weapons are wired.

See: docs/fork/fo4_condition.md#plan
"""
import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import condition as C, records as R
from fo4_import.spike.ammo_mods import ATTACK_DAMAGE, PROPERTY
from fo4_import.spike.npc_skills import merged_prps
from script_convert.symbols import STATIC_SCRIPT_CLASSES
from tes5_import.base.writer import pack_subrecord
from tes5_import.base.tes5_reader import subrecords


def _props(tier: int) -> dict:
    """{property: its value 1} of condition tier `tier`."""
    out = {}
    for p in C.tier_properties(tier):
        _, _, which, value, _, _ = PROPERTY.unpack(p)
        out[which] = struct.unpack('<f', value)[0]
    return out


def test_fnv_damage_and_value_curves():
    """Damage is whole from 75% and half at 0; value is value * h^1.5."""
    assert C.damage_factor(0.8) == 1.0 and C.damage_factor(0.75) == 1.0
    assert C.damage_factor(0.0) == pytest.approx(1.0 - 0.75 * 0.67)
    assert C.value_factor(0.25) == pytest.approx(0.125)


def test_condition_tiers_scale_value_always_and_damage_below_three_quarters():
    """Tier 9 (90-100%) only lowers value; tier 2 lowers damage too; the whole tier has no effect."""
    assert set(_props(9)) == {C.VALUE}
    low = _props(2)
    assert low[ATTACK_DAMAGE] == pytest.approx(C.damage_factor(0.25) - 1.0)
    assert low[C.VALUE] == pytest.approx(C.value_factor(0.25) - 1.0)
    assert C.tier_properties(C.TENTHS) == []


def test_wear_perks_are_modify_item_damage_multipliers():
    """Only a Multiply on entry point 68 counts, one per perk."""
    def perk(fid, entry, function, value):
        """An export PERK with one effect."""
        return {'FormID': f'{fid:08X}', 'Effect[0].Type': '2', 'Effect[0].EntryPoint': str(entry),
                'Effect[0].Function': str(function), 'Effect[0].Value': struct.pack('<f', value).hex()}
    found = C.wear_perks([perk(1, 68, 3, 0.5), perk(2, 68, 1, 9.0), perk(3, 57, 3, 2.0)])
    assert found == [(1, 0.5)]


def test_only_weapons_that_wear_take_the_condition_point():
    """A gun with FNV health gets our point and keyword; a grenade or a weapon with no health is unchanged."""
    records = {1: ('WEAP', {'DATA.Health': '250', 'DNAM.FalloutAnimType': '5'}),
               2: ('WEAP', {'DATA.Health': '20', 'DNAM.FalloutAnimType': '10'}),
               3: ('WEAP', {'DATA.Health': '0', 'DNAM.FalloutAnimType': '3'})}
    written = []
    builder = SimpleNamespace(items=SimpleNamespace(records=records), counts=Counter(),
                              writer=SimpleNamespace(derive_formid=lambda site, key: hash((site, key)) & 0xFFFFFF,
                                                     add_record=lambda sig, rec: written.append(sig)))
    cond = C.Condition(builder)
    gun = [(b'EDID', b'x\0'), (b'KSIZ', struct.pack('<I', 1)), (b'KWDA', struct.pack('<I', 7)), (b'OBTE', bytes(4))]
    wired = dict(cond.wire(1, 0x100, list(gun)))
    assert cond.point in struct.unpack('<I', wired[b'APPR']) and struct.pack('<I', cond.keyword) in wired[b'KWDA']
    assert cond.wire(2, 0x200, list(gun)) == gun and cond.wire(3, 0x300, list(gun)) == gun
    assert cond.weapons == {0x100: (1, 250.0)} and Counter(written) == {'KYWD': 2}


def _armor_props(tier: int, rating: int) -> dict:
    """{property: its value 1} of armor condition tier `tier` on armor of `rating` (ints as ints)."""
    out = {}
    for p in C.armor_tier_properties(tier, rating):
        vtype, _, which, value, _, _ = PROPERTY.unpack(p)
        out[which] = struct.unpack('<i' if vtype == C.INT else '<f', value)[0]
    return out


def test_armor_tiers_cut_rating_below_half_and_always_value():
    """FNV's DT curve: whole from 50%, half at 0; tier 7 only lowers value; tier 2 of DT 20 takes 5 off."""
    assert C.armor_factor(0.5) == 1.0 and C.armor_factor(0.0) == pytest.approx(0.5)
    assert set(_armor_props(7, 20)) == {C.ARMOR_VALUE}
    low = _armor_props(2, 20)
    assert low[C.RATING] == -5 and low[C.ARMOR_VALUE] == pytest.approx(C.value_factor(0.25) - 1.0)
    assert C.armor_tier_properties(C.TENTHS, 20) == [] and C.armor_cut(2, 0) == 0


def test_only_armor_with_fnv_health_takes_the_condition_point():
    """Armor with FNV health gets our point and keyword and is kept with its health and rounded rating."""
    builder = SimpleNamespace(writer=SimpleNamespace(derive_formid=lambda site, key: hash((site, key)) & 0xFFFFFF,
                                                     add_record=lambda sig, rec: None))
    cond = C.Condition(builder)
    armor = [(b'EDID', b'x\0'), (b'KSIZ', struct.pack('<I', 1)), (b'KWDA', struct.pack('<I', 7)), (b'FNAM', bytes(8))]
    wired = dict(cond.wire_armor(1, 0x100, list(armor), {'health': 300, 'rating': 11.6}))
    assert struct.unpack('<I', wired[b'APPR'])[0] == cond.point and b'KWDA' in wired
    assert cond.wire_armor(2, 0x200, list(armor), {'health': 0, 'rating': 5.0}) == armor
    assert cond.armors == {0x100: (1, 300.0, 12)}


def test_entry_condition_is_a_coed_after_its_entry():
    """A container item or leveled entry with a condition is followed by a COED (owner 0, condition at +8)."""
    cont = R.pack_cont(0x10, 'x', '', '', (0,) * 6, [(0x20, 1, 0.4), (0x21, 2)], 0, 0.0)
    tags = [(tag, data) for tag, data in subrecords(cont[24:]) if tag in (b'CNTO', b'COED')]
    assert [t for t, _ in tags] == [b'CNTO', b'COED', b'CNTO']
    assert struct.unpack('<IIf', tags[1][1]) == (0, 0, pytest.approx(0.4))
    lvli = R.pack_leveled('LVLI', 0x11, 'y', 0, 0, [(1, 0x20, 1, 0.5), (1, 0x21, 1, None)])
    assert [t for t, _ in subrecords(lvli[24:]) if t in (b'LVLO', b'COED')] == [b'LVLO', b'COED', b'LVLO']


def test_jury_rigging_perk_is_the_one_with_entry_point_48():
    """Only a perk with an effect on entry point Has Jury Rigging (48) counts."""
    perks = [{'FormID': '00000001', 'Effect[0].EntryPoint': '48'}, {'FormID': '00000002', 'Effect[0].EntryPoint': '68'},
             {'FormID': '00000003', 'Effect[0].EntryPoint': '9', 'Effect[1].EntryPoint': '48'}]
    assert C.jury_rigging_perks(perks) == [1, 3]


def _prps(subs: bytes) -> dict:
    """{actor value: value} of `subs`' PRPS."""
    data = dict(subrecords(subs))[b'PRPS']
    return dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8))


def test_npc_skills_join_prps_or_come_before_its_successor():
    """Skills join an NPC's own PRPS values, or go in a new PRPS right before the first tag that follows it."""
    own = pack_subrecord('EDID', b'x\0') + pack_subrecord('PRPS', struct.pack('<If', 1, 5.0))
    merged = merged_prps(own + pack_subrecord('AIDT', b''), {2: 90.0, 1: 7.0})
    assert _prps(merged) == {1: 7.0, 2: 90.0}
    assert [t for t, _ in subrecords(merged)] == [b'EDID', b'PRPS', b'AIDT']
    added = merged_prps(pack_subrecord('CNTO', b'') + pack_subrecord('CNTO', b''), {2: 90.0})
    assert [t for t, _ in subrecords(added)] == [b'PRPS', b'CNTO', b'CNTO']


def test_fallout4_static_scripts_count_as_declared():
    """Fallout 4's static scripts are known, so their calls are kept."""
    assert {'f3nv_conditioncalls', 'f3nv_condition', 'tes4polyfill'} <= STATIC_SCRIPT_CLASSES
