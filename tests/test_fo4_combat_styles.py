"""FNV combat styles as FO4 CSTY records: FNV's per-decision chances inverted onto FO4's multipliers.

See: docs/fork/fo4_pipeline.md#combat-styles
"""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import combat_styles as CS
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: The FalloutNV.exe settings the conversion reads, at their defaults.
SETTINGS = {'fBlockScoreNoShieldMult': 0.5, 'fCombatMaxHoldScore': 30.0, 'fAIDodgeDecisionBase': 10.0}

#: An FNV style with DefaultCombatstyle's melee values.
STYLE = {'EditorID': 'CSTest', 'CSTD.AttackChance': '40', 'CSTD.BlockChance': '30', 'CSTD.DodgeChance': '75',
         'CSTD.LeftRightChance': '50', 'CSTD.PowerAttackChance': '25', 'CSTD.RecoilStaggerBonusToAttack': '5.0',
         'CSTD.RecoilStaggerBonusToPowerAttack': '5.0', 'CSTD.FalloutFlags': '449',
         'CSAD.AttackSkillModifierMult': '20.0', 'CSAD.BlockSkillModifierMult': '20.0',
         'CSAD.AttackNotUnderAttackMult': '1.0', 'CSAD.AttackWhileUnderAttackMult': '0.75',
         'CSAD.BlockNotUnderAttackMult': '1.0', 'CSAD.BlockWhileUnderAttackMult': '2.0',
         'CSAD.DodgeWhileUnderAttackMult': '1.0', 'CSAD.DodgeNotUnderAttackMult': '0.75',
         'CSAD.DodgeBackWhileUnderAttackMult': '1.0', 'CSAD.DodgeBackNotUnderAttackMult': '0.7',
         'CSAD.DodgeForwardNotAttackingMult': '0.5', 'CSAD.PowerAttackFatigueModBase': '5.0',
         'CSSD.CoverSearchRadius': '2048.0', 'CSSD.TakeCoverChance': '100.0', 'CSSD.WeaponRestrictions': '0',
         'CSSD.RangedWeaponRangeMultMin': '1.0', 'CSSD.RangedWeaponRangeMultMax': '1.0'}


def _default_body() -> bytes:
    """A short FO4 default style body: 9-float CSME, 3-float CSLR, as 46 and 33 vanilla styles have."""
    floats = lambda n, v: struct.pack(f'<{n}f', *[v] * n)
    return (pack_string_subrecord('EDID', CS.FO4_DEFAULT) + pack_subrecord('CSGD', floats(12, 0.5))
            + pack_subrecord('CSME', floats(9, 1.0)) + pack_subrecord('CSRA', floats(1, 0.75))
            + pack_subrecord('CSCR', floats(11, 0.2)) + pack_subrecord('CSLR', floats(3, 0.5))
            + pack_subrecord('CSCV', floats(1, 0.5)) + pack_subrecord('CSFL', floats(8, 0.5))
            + pack_subrecord('DATA', struct.pack('<I', 1)))


def test_attack_and_block_are_fnvs_shares_of_its_one_roll():
    """Attack 40 + 20 skill mult at skill 50 = 50, block (30 + 10) * 0.5 * 0.25 = 5, hold 45: attack 0.5, so
    Offensive (0.5 - 0.025) / 0.975. Under attack: attack 37.5, block 40, hold 30 of int(107.5): block 40/107."""
    values = CS.converted_values(STYLE, SETTINGS)
    assert values['offensive'] == pytest.approx(0.475 / 0.975)
    assert values['defensive'] == pytest.approx(40 / 107)


def test_a_counter_attacker_takes_its_under_attack_share():
    """FNV's ant worker attacks at 0.1x unless its target attacks (0.9x): Offensive is the under-attack share."""
    worker = {**STYLE, 'CSTD.AttackChance': '85', 'CSAD.AttackNotUnderAttackMult': '0.1',
              'CSAD.AttackWhileUnderAttackMult': '0.9'}
    attack, _ = CS.melee_shares(worker, SETTINGS, True)
    assert CS.converted_values(worker, SETTINGS)['offensive'] == pytest.approx(CS.mult(attack, CS.ATTACK))
    assert CS.converted_values(STYLE, SETTINGS)['offensive'] == pytest.approx(0.475 / 0.975)


def test_dodge_is_the_roll_times_the_chance_a_direction_is_taken():
    """Dodge 75 passes rand() % 100 <= 75 76 times in 100; back wins 49 of the 125 draws (back >= forward,
    back > side), the rest go to the side on a 51-in-100 left/right roll."""
    back, side = CS.dodge_shares(STYLE, SETTINGS, True)
    assert back == pytest.approx(0.76 * 49 / 125) and side == pytest.approx(0.76 * (76 / 125) * 0.51)
    assert CS.converted_values(STYLE, SETTINGS)['dodge'] == pytest.approx(back + side)


def test_defensive_is_capped_at_offensive_for_a_style_that_attacks():
    """A blocker that rarely attacks keeps Defensive at most Offensive; one that never attacks keeps its block."""
    shy = {**STYLE, 'CSTD.AttackChance': '10', 'CSAD.AttackSkillModifierMult': '0.0', 'CSTD.BlockChance': '100'}
    values = CS.converted_values(shy, SETTINGS)
    assert 0.0 < values['defensive'] == pytest.approx(values['offensive'])
    never = {**shy, 'CSTD.AttackChance': '0'}
    assert CS.converted_values(never, SETTINGS)['offensive'] == 0.0
    assert CS.converted_values(never, SETTINGS)['defensive'] > 0.0


def test_ranged_only_never_dodges_and_scores_other_weapons_down():
    """FNV's ranged procedure never dodges; Ranged Only divides a non-gun's score by 10,000, Melee Only a gun's."""
    ranged = CS.converted_values({**STYLE, 'CSSD.WeaponRestrictions': '2'}, SETTINGS)
    assert (ranged['dodge'], ranged['circle'], ranged['fallback']) == (0.0, 0.0, 0.0)
    assert ranged['melee'] == ranged['unarmed'] == CS.RESTRICTED_SCORE and 'ranged' not in ranged
    melee = CS.converted_values({**STYLE, 'CSSD.WeaponRestrictions': '1'}, SETTINGS)
    assert melee['ranged'] == CS.RESTRICTED_SCORE and melee['dodge'] > 0.0


def test_cover_follows_the_search_radius_and_is_off_with_no_cover_chance():
    """Radius 2048 is (2048 - 128) / (4096 - 128); no take-cover chance writes 0, which FO4 reads as no cover."""
    assert CS.converted_values(STYLE, SETTINGS)['cover'] == pytest.approx(1920 / 3968)
    assert CS.converted_values({**STYLE, 'CSSD.TakeCoverChance': '0.0'}, SETTINGS)['cover'] == 0.0
    assert CS.converted_values({**STYLE, 'CSSD.CoverSearchRadius': '32.0'}, SETTINGS)['cover'] == CS.LEAST_COVER


def test_range_mult_inverts_fo4s_three_point_interpolation():
    """FNV's mult 1.0 is FO4's middle (0.5); 1.5 its top; 0.1 its bottom; beyond them clamps."""
    def at(value):
        return CS.converted_values({**STYLE, 'CSSD.RangedWeaponRangeMultMin': value,
                                    'CSSD.RangedWeaponRangeMultMax': value}, SETTINGS)['range']
    assert (at('1.0'), at('1.5'), at('0.1'), at('1000')) == (pytest.approx(0.5), 1.0, 0.0, 1.0)


def test_ignore_threats_turns_off_avoiding_and_evading():
    """Flag 0x10 writes avoid and evade 0; without it they keep FO4's default."""
    assert {'avoid': 0.0, 'evade': 0.0}.items() <= CS.converted_values({**STYLE, 'CSTD.FalloutFlags': '273'},
                                                                       SETTINGS).items()
    assert 'avoid' not in CS.converted_values(STYLE, SETTINGS)


def test_a_style_is_the_default_body_with_full_blocks_and_the_values_set():
    """CSME and CSLR are padded to 10 and 5 floats; each value lands in its field; EDID is the new name."""
    record = CS.pack_style(0x0300ABCD, 'FNV_CSTest', _default_body(), {'offensive': 0.25, 'range': 0.75,
                                                                        'cover': 0.0, 'circle': 0.1})
    subs = dict(subrecords(record[24:]))
    assert subs[b'EDID'] == b'FNV_CSTest\0' and struct.unpack('<I', record[12:16])[0] == 0x0300ABCD
    assert len(subs[b'CSME']) == 40 and len(subs[b'CSLR']) == 20
    assert struct.unpack('<f', subs[b'CSGD'][:4])[0] == 0.25 and struct.unpack('<5f', subs[b'CSLR'])[4] == 0.75
    assert struct.unpack('<f', subs[b'CSCV'])[0] == 0.0 and struct.unpack('<f', subs[b'CSCR'][:4])[0] == pytest.approx(0.1)


def test_a_template_actor_takes_the_style_its_traits_chain_reaches_and_none_through_a_list():
    """A Use Traits chain ending at an NPC gives that NPC's style; one leaving for a leveled list gives no edit."""
    from fo4_import.spike import npcs as N
    npcs = N.Npcs.__new__(N.Npcs)
    named = []
    npcs.builder = SimpleNamespace(combat_styles=SimpleNamespace(edit=lambda traits: named.append(traits) or 'edit'))
    base = {'FormID': '00000B01', 'ZNAM.CombatStyle': '0003BC67'}
    npcs.records = {0xB01: base, 0xB02: {'FormID': '00000B02', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000B01'},
                    0xB03: {'FormID': '00000B03', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000C00'}}
    npcs.creatures = SimpleNamespace(records={})
    assert npcs._template_style(npcs.records[0xB02]) == 'edit' and named == [base]
    assert npcs._template_style(npcs.records[0xB03]) is None


def test_an_actor_without_a_style_gets_fnvs_default_and_each_style_is_written_once():
    """No ZNAM or a style not exported means form 0x3D; ZNAM lands before NAM5."""
    written = []
    styles = CS.CombatStyles.__new__(CS.CombatStyles)
    styles.builder = SimpleNamespace(counts=Counter(), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x03000000 | int(key, 16), add_record=lambda sig, rec: written.append(rec)))
    styles.records = {CS.FNV_DEFAULT: {**STYLE, 'EditorID': 'DefaultCombatstyle'}, 0xBC67: STYLE}
    styles.settings, styles.default, styles.made = SETTINGS, _default_body(), {}
    out = styles.edit({})(pack_subrecord('ACBS', b'\0' * 4) + pack_subrecord('NAM5', b'\0\0'))
    assert [t for t, _ in subrecords(out)] == [b'ACBS', b'ZNAM', b'NAM5']
    assert dict(subrecords(out))[b'ZNAM'] == struct.pack('<I', 0x0300003D)
    assert styles.of(0x12345) == styles.of(0) == 0x0300003D and styles.of(0xBC67) == 0x0300BC67
    assert len(written) == 2 and styles.builder.counts['CSTY'] == 2
