"""FNV perks as FO4 PERK records: rank chains, entry points, vanilla effects, abilities.

See: docs/fork/fo4_perks.md#records
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import consumable_effects as CE
from fo4_import.spike import crafting as CR
from fo4_import.spike import perks as P
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def _perks(**extra) -> P.Perks:
    """A Perks with a stand-in builder writing into a list, no Fallout4.esm read."""
    written = []
    perks = P.Perks.__new__(P.Perks)
    perks.builder = SimpleNamespace(counts=Counter(), writer=SimpleNamespace(add_record=lambda s, r: written.append(r)),
                                    new_id=lambda owner: 0x0B100000 + sum(map(ord, owner)), fnv_id=lambda f: 0x0B000000 | int(f, 16))
    perks.forms, perks.script_vars, perks.tabs, perks.vanilla, perks.written = {}, {}, {35: 3, 123: 1}, {}, set()
    perks.written_records = written
    for k, v in extra.items():
        setattr(perks, k, v)
    return perks


def _effect(ep: int, rank: int, value: float, tabs: dict = None) -> dict:
    """An FNV export entry-point effect of rank `rank`: Multiply `value`, conditions per tab."""
    out = {'Type': 'EntryPoint', 'Rank': str(rank), 'Priority': '0', 'EntryPoint': str(ep), 'Function': '3',
           'ValueType': '1', 'Value': struct.pack('<f', value).hex()}
    for k, (tab, raws) in enumerate((tabs or {}).items()):
        out[f'Tab[{k}].RunOn'] = str(tab)
        out.update({f'Tab[{k}].Condition[{j}].Raw': raw for j, raw in enumerate(raws)})
    return out


def _rec(effects: list, ranks: int = 1) -> dict:
    """An FNV export PERK with `effects`."""
    rec = {'FormID': '0001ABCD', 'EditorID': 'SwiftLearner', 'DATA.Ranks': str(ranks), 'EffectCount': str(len(effects))}
    for i, e in enumerate(effects):
        rec.update({f'Effect[{i}].{k}': v for k, v in e.items()})
    return rec


def _parts(effects: bytes) -> list:
    """[(tag, data)] of packed perk effects."""
    return subrecords(effects)


def test_damage_effect_keeps_function_value_and_tabs_on_fo4_entry_point():
    """FNV Calculate Weapon Damage x1.25 becomes FO4 Mod Weapon Attack Damage (35), Multiply 1.25, 3 tabs."""
    perks = _perks()
    parts = _parts(perks._effects(_rec([_effect(0, 0, 1.25)]), 0, 0, 'FNV_X'))
    tags = dict(parts)
    assert tags[b'DATA'] == bytes([35, 3, 3]) and struct.unpack('<f', tags[b'EPFD'])[0] == 1.25
    assert [t for t, _ in parts] == [b'PRKE', b'DATA', b'EPFT', b'EPFB', b'EPFD', b'PRKF']


def test_earlier_rank_is_off_once_the_next_rank_is_held():
    """Rank 1 of a two-rank perk tests HasPerk(rank 2) == 0 on its owner tab; rank 2 carries no such test."""
    perks = _perks()
    rec = _rec([_effect(9, 0, 1.1), _effect(9, 1, 1.2)], ranks=2)
    first = _parts(perks._effects(rec, 0, 0x0B100099, 'FNV_X'))
    ctda = next(d for t, d in first if t == b'CTDA')
    assert struct.unpack_from('<H', ctda, 8)[0] == C.FO4.index('HasPerk') and struct.unpack_from('<I', ctda, 12)[0] == 0x0B100099
    assert dict(first)[b'PRKC'] == b'\x00'
    second = _parts(perks._effects(rec, 1, 0, 'FNV_X'))
    assert b'CTDA' not in dict(second) and dict(second)[b'EPFD'] == struct.pack('<f', 1.2)


def test_effect_testing_a_tab_fo4_lacks_is_left_out():
    """FNV To Hit Chance with a weapon-tab condition: FO4's Mod VATS Hit Chance has the owner tab only."""
    perks = _perks()
    raw = '00000000000000006d01000000000000000000000000000000000000'
    assert perks._effects(_rec([_effect(8, 0, 1.25, {1: [raw]})]), 0, 0, 'FNV_X') == b''
    assert perks.builder.counts['perk effect left out (tab FO4 lacks)'] == 1


def test_weapon_skill_on_the_weapon_tab_is_a_keyword_test():
    """IsWeaponSkillType Guns on Calculate Weapon Damage's weapon tab: HasKeyword(FNV_WeaponSkillGuns) there."""
    keywords = SimpleNamespace(keyword=lambda edid: 0x0B200001 if edid == 'FNV_WeaponSkillGuns' else 0)
    perks = _perks(forms={TYPE_KEYWORDS: keywords})
    raw = (struct.pack('<B3xfH2xI', 0, 1.0, C.FNV.index('IsWeaponSkillType'), C.FNV_AV_NAMES.index('Guns'))
           + bytes(12)).hex()
    ctda = dict(_parts(perks._effects(_rec([_effect(0, 0, 1.25, {1: [raw]})]), 0, 0, 'FNV_X')))[b'CTDA']
    assert struct.unpack_from('<HxxI', ctda, 8) == (C.FO4.index('HasKeyword'), 0x0B200001)


def test_quest_stage_effect_keeps_the_low_byte_of_fnv_stage():
    """Scrounger's stage 0xCD46 is Generic's stage 70 (low byte)."""
    perks = _perks(forms={0x38B2: 0x020038B2})
    rec = _rec([{'Type': 'QuestStage', 'Rank': '0', 'Priority': '0', 'Quest': '000038B2', 'Stage': str(0xCD46)}])
    assert dict(_parts(perks._effects(rec, 0, 0, 'FNV_X')))[b'DATA'] == struct.pack('<IH', 0x020038B2, 70)


def test_unmapped_entry_point_is_counted():
    """FNV Modify Attack Speed (43) has no FO4 counterpart."""
    perks = _perks()
    assert perks._effects(_rec([_effect(43, 0, 1.2)]), 0, 0, 'FNV_X') == b''
    assert perks.builder.counts['perk effect left out (FNV entry point 43)'] == 1


def test_vanilla_effect_blocks_parse_and_repack():
    """effect_blocks reads a vanilla entry-point effect; it repacks with its tab and a fresh EPFB."""
    ctda = pack_subrecord('CTDA', bytes(32))
    body = (pack_subrecord('DATA', bytes(5)) + pack_subrecord('PRKE', bytes([2, 0, 0])) +
            pack_subrecord('DATA', bytes([155, 10, 3])) + pack_subrecord('PRKC', b'\x00') + ctda +
            pack_subrecord('EPFT', b'\x05') + pack_subrecord('EPFB', b'\x02\x00') +
            pack_subrecord('EPFD', struct.pack('<I', 0x5240D)) + pack_subrecord('PRKF', b''))
    (data, tabs, params), = P.effect_blocks(subrecords(body))
    assert data == bytes([155, 10, 3]) and tabs == {0: ctda}
    packed = dict(_parts(P.pack_effect(P.ENTRY_POINT, data, tabs, P._with_entry_id(params, 0))))
    assert packed[b'EPFB'] == b'\x00\x00' and packed[b'EPFD'] == struct.pack('<I', 0x5240D)


def test_rank_ids_keep_fnv_formid_for_the_first_rank():
    """A three-rank perk: FNV's FormID, then two generated ids."""
    perks = _perks()
    ids = perks._rank_ids(_rec([], ranks=3))
    assert ids[0] == 0x0B01ABCD and len(set(ids)) == 3


def _has_perk(perk: int, value: float = 1.0, or_next: bool = False) -> dict:
    """A parsed FNV condition: HasPerk `perk` == `value`."""
    return {'func': 'HasPerk', 'op_flags': C.OR_NEXT if or_next else 0, 'value': value, 'p1': perk, 'p2': 0,
            'run_on': 0, 'ref': 0, 'global': 0}


def test_level_up_offers_playable_perks_by_level_not_traits_or_hidden():
    """Playable perks by level then name; a trait, a hidden and an unplayable perk are left off."""
    perks = _perks()
    perks.records = [{'FormID': '01', 'FULL': 'B', 'DATA.Playable': '1', 'DATA.MinLevel': '4'},
                     {'FormID': '02', 'FULL': 'A', 'DATA.Playable': '1', 'DATA.MinLevel': '4'},
                     {'FormID': '03', 'FULL': 'C', 'DATA.Playable': '1', 'DATA.MinLevel': '2'},
                     {'FormID': '04', 'FULL': 'T', 'DATA.Playable': '1', 'DATA.Trait': '1'},
                     {'FormID': '05', 'FULL': 'H', 'DATA.Playable': '1', 'DATA.Hidden': '1'},
                     {'FormID': '06', 'FULL': 'U', 'DATA.Playable': '0'}]
    perks.ids = {int(r['FormID'], 16): [0x0B000000 | int(r['FormID'], 16)] for r in perks.records}
    assert perks.playable() == [0x0B000003, 0x0B000002, 0x0B000001]


def test_recipe_perk_condition_is_fo4_has_perk():
    """A Vigilant Recycler recipe's HasPerk == 1 becomes FO4 HasPerk on its first-rank perk."""
    crafting = CR.Crafting.__new__(CR.Crafting)
    crafting.builder = SimpleNamespace(perks=SimpleNamespace(form_map=lambda: {0x1234: 0x0B001234}))
    ctda = crafting._condition(_has_perk(0x1234))
    assert struct.unpack_from('<fHxxI', ctda, 10) == (1.0, C.FO4.index('HasPerk'), 0x0B001234)


def test_consumable_effect_carries_its_perk_test_and_an_unknown_perk_counts_as_not_held():
    """An effect needing a known perk gets FO4 HasPerk; one needing a perk the build lacks never runs."""
    effects = CE.Effects.__new__(CE.Effects)
    effects.builder = SimpleNamespace(perks=SimpleNamespace(form_map=lambda: {0x1234: 0x0B001234}), counts=Counter())
    ctda = effects._perk_tests([_has_perk(0x1234)])
    assert struct.unpack_from('<HxxI', ctda, 14) == (C.FO4.index('HasPerk'), 0x0B001234)
    assert effects._perk_tests([_has_perk(0x9999)]) is None
    assert effects._perk_tests([_has_perk(0x9999, 0.0)]) == b''


def test_skill_gates_set_each_minigame_gate_by_its_skill_with_the_higher_tier_later():
    """Lockpick and Science each set their FO4 gate (62, 98) to 1, 2, 3 at 50, 75, 100, priority rising with tier."""
    raw = P.gate_effects(1)
    blocks = P.effect_blocks(subrecords(P.pack_subrecord('DATA', bytes(5)) + raw))
    assert [b[0] for b in blocks] == [bytes([ep, P.SET_VALUE, 1]) for ep in (62, 98) for _ in range(3)]
    values = [struct.unpack('<f', dict(b[2])[b'EPFD'])[0] for b in blocks]
    levels = [struct.unpack_from('<f', b[1][0], 10)[0] for b in blocks]
    assert values == [1.0, 2.0, 3.0] * 2 and levels == [50.0, 75.0, 100.0] * 2
    priorities = [p[2] for t, p in subrecords(raw) if t == b'PRKE']
    assert priorities == [1, 2, 3] * 2
