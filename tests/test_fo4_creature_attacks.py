"""FNV creatures' attack sets on their FO4 stand-ins' attack data.

See: docs/fork/fo4_pipeline.md#creature-attacks
"""

import struct

import pytest

from fo4_import.spike import creature_attacks as CA
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: A style that power attacks in every direction and rushes.
STYLE = {'CSTD.PowerAttackChance': '50', 'CSTD.RushingAttackChance': '50', 'CSTD.FalloutFlags': '0'}
#: The deathclaw's FNV groups: left and right swipes, left, right and forward power attacks.
DEATHCLAW = frozenset({'attackleft', 'attackright', 'attackleftpower', 'attackrightpower', 'attackforwardpower'})


def _atkd(chance=1.0, flags=0, angle=0.0, damage=2.0) -> bytes:
    """An FO4 ATKD with the fields a test sets."""
    return CA.ATKD.pack(damage, chance, 0, flags, angle, 35.0, 0.0, 0.0, 0.0, 1.0, 0)


def test_a_kf_names_its_group_without_prefixes_or_variant():
    """h2hattackleft_a.kf is AttackLeft; the hand prefix and the _A/_B variant go (FalloutNV.exe 0x5f38d0)."""
    assert [CA.kf_group(n) for n in ('h2hattackleft_a.kf', 'H2HAttackForwardPower.kf', 'attackright__midbite.kf',
                                     '2hlattackspin.kf', 'mtidle.kf')] == [
        'attackleft', 'attackforwardpower', 'attackright', 'attackspin', 'mtidle']


def test_power_directions_follow_the_groups_and_the_styles_chance():
    """No power attack chance, none; Choose Attack using % Chance drops zero-weight directions."""
    assert CA.power_directions(DEATHCLAW, STYLE) == {'Left', 'Right', 'Forward'}
    assert CA.power_directions(DEATHCLAW, {**STYLE, 'CSTD.PowerAttackChance': '0'}) == frozenset()
    weighted = {**STYLE, 'CSTD.FalloutFlags': '1', 'CSTD.PowerAttackLeft': '30', 'CSTD.PowerAttackRight': '0',
                'CSTD.PowerAttackForward': '40'}
    assert CA.power_directions(DEATHCLAW, weighted) == {'Left', 'Forward'}


def test_an_attack_aimed_outside_fnvs_hit_cone_is_off():
    """FNV only hits inside 35 degrees, so a side swipe (85) is off; a 30-degree swipe stays."""
    powers = CA.power_directions(DEATHCLAW, STYLE)
    assert not CA.kept(CA.ATKD.unpack(_atkd(angle=-85.0)), DEATHCLAW, powers, STYLE)
    assert CA.kept(CA.ATKD.unpack(_atkd(angle=30.0)), DEATHCLAW, powers, STYLE)


def test_power_and_charge_attacks_need_fnvs_power_and_rushing_attacks():
    """A power attack needs a power direction; a charge needs a rushing attack chance."""
    power, charge = CA.ATKD.unpack(_atkd(flags=CA.POWER)), CA.ATKD.unpack(_atkd(flags=CA.CHARGE))
    calm = {**STYLE, 'CSTD.PowerAttackChance': '0', 'CSTD.RushingAttackChance': '0'}
    assert CA.kept(power, DEATHCLAW, CA.power_directions(DEATHCLAW, STYLE), STYLE)
    assert not CA.kept(power, DEATHCLAW, CA.power_directions(DEATHCLAW, calm), calm)
    assert CA.kept(charge, DEATHCLAW, frozenset(), STYLE) and not CA.kept(charge, DEATHCLAW, frozenset(), calm)


def test_the_list_keeps_attacks_at_damage_mult_1_and_disables_the_rest():
    """Kept: damage mult 1; off (outside the cone, or vanilla's chance 0): chance 0; events and order unchanged."""
    attacks = [(_atkd(chance=0.5), b'swipe\0', b''), (_atkd(angle=85.0), b'side\0', b''),
               (_atkd(chance=0.0), b'unused\0', b'')]
    subs, count = CA.attack_list(attacks, DEATHCLAW, STYLE)
    datas = [CA.ATKD.unpack(d) for t, d in subrecords(subs) if t == b'ATKD']
    assert count == 1 and [(d[0], d[1]) for d in datas] == [(1.0, 1.0), (2.0, 0.0), (2.0, 0.0)]
    assert [d for t, d in subrecords(subs) if t == b'ATKE'] == [b'swipe\0', b'side\0', b'unused\0']


def test_power_attacks_get_fnvs_share_of_the_weighted_pick():
    """PA% 50 + fatigue base 5 passes 56 rolls in 100; two normals and three powers: power weight w with
    3w / (3w + 2) = 0.56, the smaller weight 1 (FO4 rejects a pick when rand01() > its weight)."""
    style = {**STYLE, 'CSAD.PowerAttackFatigueModBase': '5.0'}
    assert CA.power_share(style) == 0.56
    attacks = [(_atkd(), b'l\0', b''), (_atkd(), b'r\0', b'')] + [(_atkd(flags=CA.POWER), b'p\0', b'')] * 3
    subs, _ = CA.attack_list(attacks, DEATHCLAW, style)
    chances = [CA.ATKD.unpack(d)[1] for t, d in subrecords(subs) if t == b'ATKD']
    normal, power = chances[0], chances[2]
    assert min(normal, power) == 1.0 and 3 * power / (3 * power + 2 * normal) == pytest.approx(0.56)
    assert CA.weights(4, 1, 0.1) == pytest.approx((2.25, 1.0)) and CA.weights(2, 0, 0.5) == (1.0, 1.0)
    assert CA.power_share({'CSTD.PowerAttackChance': '0'}) == 0.0 and CA.weights(2, 2, 0.0) == (1.0, 0.0)


def test_the_attack_race_and_list_replace_the_stand_ins_where_vanilla_puts_them():
    """ATKR and the list go before PRKZ, replacing any earlier ones."""
    body = (pack_subrecord('RNAM', b'\1\0\0\0') + pack_subrecord('ATKR', b'\2\0\0\0')
            + pack_subrecord('ATKD', _atkd()) + pack_subrecord('ATKE', b'old\0') + pack_subrecord('PRKZ', b'\0' * 4))
    new = pack_subrecord('ATKD', _atkd()) + pack_subrecord('ATKE', b'new\0')
    out = list(subrecords(CA.with_attacks(0x1234, new)(body)))
    assert [t for t, _ in out] == [b'RNAM', b'ATKR', b'ATKD', b'ATKE', b'PRKZ']
    assert dict(out)[b'ATKR'] == struct.pack('<I', 0x1234) and dict(out)[b'ATKE'] == b'new\0'
