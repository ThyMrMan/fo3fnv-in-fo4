"""FNV perks as FO4 PERK records: rank chains, entry points, vanilla effects, abilities.

See: docs/fork/fo4_perks.md#records
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
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
