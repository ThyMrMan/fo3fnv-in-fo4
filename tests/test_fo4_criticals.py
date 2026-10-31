"""FNV's random critical roll on FO4: weapon factors, the perk's additions, the folded multipliers, who holds it."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import combat_perk as CP
from fo4_import.spike import consumable_effects as CE
from fo4_import.spike import criticals as CR
from fo4_import.spike import weapon_skills as WS
from fo4_import.spike import requirement_spread as RS
from fo4_import.spike import npc_skills as NS
from fo4_import.spike import skill_tags as ST
from fo4_import.spike import sneak_attacks as SA
from fo4_import.spike import weapon_poisons as WP
from fo4_import.spike import perks as PK
from script_convert.target import fallout4_actor_values
from fo4_import.spike.type_tests import FACTORED, crit_factor, requirement_names, weapon_names
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def _weapon(mult: float, flags1: int = 0, rate: float = 8.0) -> dict:
    """Raw FNV WEAP subrecords: DNAM with Flags1 and Fire Rate, CRDT with Crit % Mult."""
    dnam = bytearray(108)
    dnam[12] = flags1
    struct.pack_into('<f', dnam, 64, rate)
    return {b'DNAM': bytes(dnam), b'CRDT': struct.pack('<HxxfB3xI', 16, mult, 0, 0)}


def test_the_factor_is_crit_mult_over_fire_rate_for_automatic_weapons_only():
    """An automatic divides by its fire rate (the assault rifle's 1/8); a semi-automatic does not; 1 gets none."""
    assert crit_factor(_weapon(1.0, 0x2, 8.0)) == ('FNV_CritFactor_1_8', 0.125)
    assert crit_factor(_weapon(2.0, 0x0, 8.0)) == ('FNV_CritFactor_2_1', 2.0)
    assert crit_factor(_weapon(1.0)) is None and crit_factor({b'DNAM': bytes(108)}) is None
    assert weapon_names(_weapon(0.0))[-2:] == (FACTORED, 'FNV_CritFactor_0_1')


def _criticals(factors: list, base: float = 0.0) -> CR.Criticals:
    """A Criticals with `factors`, Luck 0x2C8 and CritChance 0x0100081F, keywords numbered by name."""
    crit = CR.Criticals.__new__(CR.Criticals)
    names = {}
    keywords = SimpleNamespace(keyword=lambda edid: names.setdefault(edid, 0x100 + len(names)))
    crit.builder = SimpleNamespace(type_keywords=keywords, counts={'critical chance multiplier folded': 0})
    crit.base, crit.mult, crit.luck, crit.chance, crit.factors = base, 1.0, 0x2C8, 0x0100081F, factors
    return crit


def test_the_perk_adds_luck_and_crit_chance_times_each_factor():
    """Per factor (and 1 for an unmarked weapon): Luck x f x the Luck mult and CritChance x f, on entry point 1;
    the base only when it is not 0; a folded x1.15 adds 0.15 of the same, keeping its own tabs."""
    crit = _criticals([('FNV_CritFactor_1_8', 0.125)])
    adds = crit.adds(1.0, {})
    values = [struct.unpack('<If', dict(p)[b'EPFD']) for _, _, p in adds]
    assert [d for d, _, _ in adds] == [bytes([1, 5, 3])] * 4
    assert values == [(0x2C8, 1.0), (0x0100081F, 1.0), (0x2C8, 0.125), (0x0100081F, 0.125)]
    folded = crit.folded({1: b'melee'}, 1.15)
    assert abs(struct.unpack('<If', dict(folded[0][2])[b'EPFD'])[1] - 0.15) < 1e-6
    assert folded[0][1][1].endswith(b'melee') and len(_criticals([], base=2.0).adds(1.0, {})) == 3


def _npc(*subs) -> bytes:
    """An FO4 NPC_ record of `subs` (tag, data)."""
    return pack_fo4_record('NPC_', 0x1000, 0, b''.join(pack_subrecord(t, d) for t, d in subs))


def test_an_npc_gets_the_perk_in_its_perk_list_or_a_new_one_once():
    """A new PRKZ/PRKR before COCT; appended to an existing list with the count raised; never twice."""
    plain = CP.with_perk(_npc(('EDID', b'A\0'), ('RNAM', bytes(4)), ('COCT', bytes(4))), 0x0B000001)
    assert [t for t, _ in subrecords(plain[24:])] == [b'EDID', b'RNAM', b'PRKZ', b'PRKR', b'COCT']
    held = _npc(('EDID', b'A\0'), ('PRKZ', struct.pack('<I', 1)), ('PRKR', struct.pack('<IB', 5, 1)), ('AIDT', b'x'))
    got = list(subrecords(CP.with_perk(held, 0x0B000001)[24:]))
    assert got[1] == (b'PRKZ', struct.pack('<I', 2)) and got[3] == (b'PRKR', struct.pack('<IB', 0x0B000001, 1))
    assert CP.with_perk(plain, 0x0B000001) == plain
    assert struct.unpack_from('<I', plain, 4)[0] == len(plain) - 24


def test_a_weapon_skill_scales_damage_and_spread_for_an_attacker_holding_it(monkeypatch):
    """Per skill: damage x fDamageSkillBase then x (1 + skill x mult / (100 x base)), not on hand-to-hand
    weapons; spread x (1 - skill x fWobbleToSkillConversion / 100); each only when the attacker has the skill."""
    monkeypatch.setattr(WS, 'actor_value_form', lambda name, index: 0x01000819)
    names = {}
    skills = WS.WeaponSkills.__new__(WS.WeaponSkills)
    skills.builder = SimpleNamespace(type_keywords=SimpleNamespace(keyword=lambda e: names.setdefault(e, len(names))))
    skills.settings, skills.helper_index, skills.skills = {'fDamageSkillBase': 0.5, 'fDamageSkillMult': 0.5,
                                                           'fWobbleToSkillConversion': 0.5}, 1, ['Guns']
    damage, scale, spread, vats_base, vats_skill, sway_m, sway_k = skills.entries()
    assert (sway_m[0], sway_k[0]) == (bytes([102, 3, 1]), bytes([102, 14, 1]))
    assert len(spread[1][0]) == 2 * 38 and struct.unpack_from('<H', spread[1][0], 38 + 6 + 8)[0] == 136
    assert (vats_base[0], vats_skill[0]) == (bytes([123, 3, 1]), bytes([123, 14, 1]))
    assert struct.unpack('<f', dict(vats_base[2])[b'EPFD'])[0] == 0.5 and len(vats_skill[1][0]) == 38
    assert abs(struct.unpack('<If', dict(vats_skill[2])[b'EPFD'])[1] - 0.01) < 1e-9
    assert (damage[0], scale[0], spread[0]) == (bytes([35, 3, 3]), bytes([35, 14, 3]), bytes([134, 14, 2]))
    assert struct.unpack('<f', dict(damage[2])[b'EPFD'])[0] == 0.5
    av, per_point = struct.unpack('<If', dict(scale[2])[b'EPFD'])
    assert av == 0x01000819 and abs(per_point - 0.01) < 1e-9
    assert abs(struct.unpack('<If', dict(spread[2])[b'EPFD'])[1] + 0.005) < 1e-9
    assert len(damage[1][1]) == 2 * 38 and 'FNV_WeaponAnimHandToHand' in names and 'FNV_WeaponSkillGuns' in names


def test_vats_and_sneak_attacks_add_to_the_critical_chance():
    """In V.A.T.S. + the bonus; a player's sneak attack adds (mult - 1) x the base terms and the V.A.T.S. bonus."""
    crit = _criticals([])
    crit.vats, crit.sneak = 5.0, 100.0
    entries = crit.entries()
    added = [struct.unpack('<f', dict(p)[b'EPFD'])[0] for d, _, p in entries if d[1] == CR.ADD_VALUE]
    assert len(entries) == 2 + 2 + 2 and added == [5.0, 99 * 5.0]
    sneak = [t for d, t, p in entries if d[1] == CR.ADD_AV_MULT and struct.unpack('<If', dict(p)[b'EPFD'])[1] == 99]
    assert sneak and CR.OWNER_TAB in sneak[0]


def test_sneak_attack_damage_is_fnvs_melee_value_unless_the_weapon_is_ranged():
    """Mod Sneak Attack Mult set: the other value with a ranged FNV animation keyword (OR'd), else melee's."""
    names = {}
    sneak = SA.SneakAttacks.__new__(SA.SneakAttacks)
    sneak.builder = SimpleNamespace(type_keywords=SimpleNamespace(keyword=lambda e: names.setdefault(e, len(names))))
    sneak.melee, sneak.other = 5.0, 1.0
    (ranged_data, ranged, ranged_p), (_, melee, melee_p) = sneak.entries()
    assert ranged_data == bytes([18, 1, 3]) and struct.unpack('<f', dict(ranged_p)[b'EPFD'])[0] == 1.0
    assert struct.unpack('<f', dict(melee_p)[b'EPFD'])[0] == 5.0 and 'FNV_WeaponAnimMelee1Hand' not in names
    assert len(ranged[1]) == len(melee[1]) == 11 * 38


def test_a_poison_is_an_ingestible_whose_every_effect_is_hostile():
    """FNV's IsPoison: all effects carry the hostile flag; one helpful effect (or none) is not a poison."""
    poisons = WP.WeaponPoisons.__new__(WP.WeaponPoisons)
    poisons.builder = SimpleNamespace(perks=SimpleNamespace(fnv_effects={'DamageHealth': {'DATA.Flags': '4'},
                                                                        'RestoreHealth': {'DATA.Flags': '0'}}))
    rec = {'EffectCount': '2', 'Effect[0].EFID': 'DamageHealth', 'Effect[1].EFID': 'DamageHealth'}
    assert poisons.is_poison(rec) and not poisons.is_poison({**rec, 'Effect[1].EFID': 'RestoreHealth'})
    assert not poisons.is_poison({'EffectCount': '0'})


def test_fnv_damage_threshold_is_fo4_damage_resist_and_fnv_dr_the_helpers():
    """FNV DT is FO4 DamageResist; FNV DR is the helper's FalloutDamageResist."""
    values = fallout4_actor_values()
    assert values['damagethreshold'] == ('DamageResist', 'Fallout4.esm', 0x2E3)
    assert values['damageresist'][:2] == ('FalloutDamageResist', 'FalloutHelpers.esl')


def test_an_attacker_dt_perk_becomes_fo4_target_resistance_less_the_ignored_dt():
    """FNV entry 58 Set Value 15 (Piercing Strike) is FO4 entry 37 Add Value -15."""
    perks = PK.Perks.__new__(PK.Perks)
    perks.tabs, perks.forms, perks.script_vars, perks.builder = {37: 3}, {}, {}, SimpleNamespace(counts=Counter())
    rec = {'Effect[0].EntryPoint': '58', 'Effect[0].Function': '1', 'Effect[0].ValueType': '1',
           'Effect[0].Value': struct.pack('<f', 15.0).hex()}
    data, _, params = perks._entry_point(rec, 'Effect[0]')
    assert data == bytes([37, 2, 3]) and struct.unpack('<f', dict(params)[b'EPFD'])[0] == -15.0


def _stat_perks(constants: dict) -> tuple:
    """A Perks with Fallout4.esm's `constants` and a writer that keeps its records; (perks, written)."""
    perks, written = PK.Perks.__new__(PK.Perks), []
    perks.constants, perks.forms, perks.script_vars, perks.helper_index = constants, {}, {}, 1
    perks.vanilla = {PK.SPELL_TEMPLATE: (0, {b'ETYP': bytes(4), b'SPIT': bytes(36)})}
    perks.builder = SimpleNamespace(counts=Counter(), new_id=lambda key: 0x0B000100,
                                    writer=SimpleNamespace(add_record=lambda sig, data: written.append(data)))
    return perks, written


def test_a_stat_entry_point_is_an_ability_on_fo4s_own_effect_in_its_units():
    """Rapid Reload (37 Multiply 1.25) is ReloadSpeedMult +0.25 on Fallout4.esm's effect; Nerves of Steel
    (39 x1.2) ActionPointRate +1.2; with no FO4 effect for a FormID value, left out and counted."""
    perks, written = _stat_perks({(0x2D3, False, False): 0xAAA, (0x2D8, False, True): 0xBBB})
    for ep, value in (('37', 1.25), ('39', 1.2)):
        rec = {'Effect[0].EntryPoint': ep, 'Effect[0].Function': '3', 'Effect[0].Value': struct.pack('<f', value).hex()}
        assert perks._stat_ability(rec, 'Effect[0]', b'', 'PERK 1') == 0x0B000100
    pairs = [dict(subrecords(r[24:])) for r in written]
    assert struct.unpack('<I', pairs[0][b'EFID'])[0] == 0xAAA and struct.unpack('<I', pairs[1][b'EFID'])[0] == 0xBBB
    assert abs(struct.unpack_from('<f', pairs[0][b'EFIT'])[0] - 0.25) < 1e-6
    assert abs(struct.unpack_from('<f', pairs[1][b'EFIT'])[0] - 1.2) < 1e-5
    perks.constants = {}
    assert perks._stat_ability(rec, 'Effect[0]', b'', 'PERK 1') is None
    assert perks.builder.counts['perk effect left out (stat entry: no FO4 effect)'] == 1


def test_a_consumable_effect_with_no_fo4_match_falls_back_to_its_converted_script():
    """An unmapped FNV effect is its script effect when the script converted, else nothing."""
    effects = CE.Effects.__new__(CE.Effects)
    scripted = {'StealthBoyEffect': 0x0B000200}
    effects.builder = SimpleNamespace(scripts=SimpleNamespace(effects=SimpleNamespace(consumed=scripted.get)))
    assert effects._fo4('StealthBoyEffect', -1) == [0x0B000200] and effects._fo4('NothingEffect', -1) == []


def test_a_weapon_carries_its_strength_and_skill_requirement_keywords():
    """DNAM +168 Strength (above 1) and +200 skill requirement (above 0) as keywords."""
    dnam = bytearray(204)
    struct.pack_into('<I', dnam, 168, 6)
    struct.pack_into('<I', dnam, 200, 50)
    assert requirement_names(bytes(dnam)) == ('FNV_StrengthReq_6', 'FNV_SkillReq_50')
    assert requirement_names(bytes(204)) == () and requirement_names(b'') == ()


def test_a_requirement_shortfall_multiplies_the_cone_per_band(monkeypatch):
    """Strength 3: 1 and 2 short (x1.25, x1.5); skill 25: 3 started steps of 10 (x1.25 to x1.75)."""
    monkeypatch.setattr(RS, 'actor_value_form', lambda name, index: 0x2C2 if name == 'Strength' else 0x0100081A)
    req = RS.RequirementSpread.__new__(RS.RequirementSpread)
    req.builder = SimpleNamespace(type_keywords=SimpleNamespace(keyword=lambda e: 0x100))
    req.helper_index, req.step, req.strengths, req.skills = 1, 0.25, [3], [(41, 25)]
    entries = req.entries()
    values = [round(struct.unpack('<f', dict(p)[b'EPFD'])[0], 4) for _, _, p in entries]
    assert values == [1.25, 1.5, 1.25, 1.5, 1.75] and {d for d, _, _ in entries} == {bytes([134, 3, 2])}
    assert len(entries[2][1][0]) == 3 * 38 and len(entries[2][1][1]) == 2 * 38 and len(entries[0][1][0]) == 2 * 38


def test_scoped_sway_halves_from_skill_0_to_100():
    """FO4's scoped sway 1 - 0.5 x stability: SWAY_AT_ZERO at skill 0, half of it at 100."""
    first, second = WS.sway_entries(0x01000819, b'', 0.5)
    m = struct.unpack('<f', dict(first[2])[b'EPFD'])[0]
    k = struct.unpack('<If', dict(second[2])[b'EPFD'])[1]
    assert abs(1 - 0.5 * m - WS.SWAY_AT_ZERO) < 1e-6 and abs(1 - 0.5 * m * (1 + 100 * k) - WS.SWAY_AT_ZERO / 2) < 1e-6


def test_a_skill_check_tags_its_option_as_fnv_does():
    """GetActorValue Speech >= 50 on the player (Target): [Speech 50]; < 50 too; a bracketed prompt or none stays."""
    def raw(op, value, av=43, run_on=1):
        return struct.pack('<B3xfIIIII', op, value, 14, av, 0, run_on, 0).hex()
    passed, failed = {'Condition[0].Raw': raw(0x60, 50.0)}, {'Condition[0].Raw': raw(0x80, 50.0)}
    assert ST.tagged('Hand it over.', [passed, failed]) == '[Speech 50] Hand it over.'
    assert ST.tagged('Hand it over.', [failed]) == '[Speech 50] Hand it over.'
    assert ST.tagged('[Lie] Hand it over.', [passed]) == '[Lie] Hand it over.'
    assert ST.tagged('Hi.', [{'Condition[0].Raw': raw(0x60, 50.0, run_on=0)}]) == 'Hi.'
    assert ST.tagged('Lift it.', [{'Condition[0].Raw': raw(0x40, 5.0, av=5)}]) == '[Strength 6] Lift it.'


def test_a_creatures_combat_skill_is_every_combat_skill(monkeypatch):
    """Combat Skill 55 on Energy Weapons, Explosives, Melee Weapons, Guns and Unarmed; none without one."""
    monkeypatch.setattr(NS, 'creature_combat', lambda: {0x123: 55})
    monkeypatch.setattr(NS, 'actor_value_form', lambda name, index: 0x01000800 + NS.COMBAT_SKILLS.index(name))
    edit = NS.with_creature_skills(0x03000123, 1)
    prps = dict(subrecords(edit(pack_subrecord('AIDT', bytes(4)))))[b'PRPS']
    assert [struct.unpack_from('<If', prps, i) for i in range(0, len(prps), 8)] == [
        (0x01000800 + i, 55.0) for i in range(5)]
    assert NS.with_creature_skills(0x999, 1) is None
