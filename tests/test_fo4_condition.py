"""FNV weapon condition on Fallout 4: the curves, the condition mods, wear perks and which weapons are wired.

See: docs/fork/fo4_condition.md#plan
"""
import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import condition as C
from fo4_import.spike.ammo_mods import ATTACK_DAMAGE, PROPERTY


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
