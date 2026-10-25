"""FNV combat styles as Fallout 4 CSTY records, one per FNV style.

FNV rolls each melee decision from its style's percentages: an attack, block
and hold score shared out by one roll, a dodge roll while the target swings,
then a direction (FalloutNV.exe 0x9cc510, 0x644680, 0x644580, 0x644990,
0x644a70). Fallout 4 reads per-style multipliers that interpolate between a
Min and a Max game setting (Fallout4.exe 0x101b540: min + (max - min) * mult).
Each FNV chance is inverted onto the multiplier giving the same FO4 chance;
fields FNV has no source for keep Fallout4.esm DefaultCombatStyle's values.
An actor without a style fights with FNV's form 0x3D, converted like the rest.

See: docs/fork/fo4_pipeline.md#combat-styles
"""

import json
import struct
from itertools import product
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord
from tes5_import.character_data_falloutnv import ENGINE_SETTINGS

#: derive_formid site of a converted style (key: the FNV style's FormID).
SITE = 'FNV CSTY'
#: FNV's hard-coded DefaultCombatstyle, which an actor or creature without ZNAM fights with (FalloutNV.exe 0x505000).
FNV_DEFAULT = 0x3D
#: The Fallout4.esm style whose values fill the fields FNV has no source for.
FO4_DEFAULT = 'DefaultCombatStyle'
#: The tags vanilla's NPC ZNAM (all 1,745) comes right before.
ZNAM_BEFORE = (b'NAM5',)
#: Fallout4.exe defaults (min, max) each multiplier interpolates; Fallout4.esm overrides none of them.
ATTACK, BLOCK_THREAT, DODGE_THREAT = (0.025, 1.0), (0.0, 1.0), (0.0, 1.0)
CIRCLE, FALLBACK, COVER_SEARCH = (0.0, 0.75), (0.0, 0.5), (128.0, 4096.0)
#: fCombatOptimalRangeMult Min, Mid, Max: the three-point interpolation of 2 * CSLR Range Mult - 1 (0x101d046).
OPTIMAL_RANGE = (0.1, 1.0, 1.5)
#: FNV's weapon skill stand-in (its block score hard-codes 50) and the score FNV leaves a restricted weapon.
SKILL_FRACTION, RESTRICTED_SCORE = 0.5, 1e-4
#: FNV CSTD flag Ignore Threats; CSSD weapon restrictions Melee Only and Ranged Only.
IGNORE_THREATS, MELEE_ONLY, RANGED_ONLY = 0x10, '1', '2'
#: The smallest cover search mult that still searches (FO4 takes no cover at 0 or less).
LEAST_COVER = 1e-4
#: FO4 CSGD/CSME/CSCR/CSLR fields as (tag, float index), named as xEdit's FO4 definition names them.
FIELDS = {'offensive': (b'CSGD', 0), 'defensive': (b'CSGD', 1), 'melee': (b'CSGD', 3), 'ranged': (b'CSGD', 5),
          'unarmed': (b'CSGD', 7), 'avoid': (b'CSGD', 9), 'dodge': (b'CSGD', 10), 'evade': (b'CSGD', 11),
          'attack_staggered': (b'CSME', 0), 'power_staggered': (b'CSME', 1), 'circle': (b'CSCR', 0),
          'fallback': (b'CSCR', 1), 'range': (b'CSLR', 4)}
#: Float count each written block has (vanilla's commonest sizes) and xEdit's defaults for a short vanilla one.
SIZES = {b'CSME': (10, 1.0), b'CSLR': (5, 0.5)}


def fnv_settings(export_dir: Path) -> dict:
    """FalloutNV.exe's numeric settings with the plugin's own GMSTs over them."""
    with open(ENGINE_SETTINGS['falloutnv'], encoding='utf-8') as handle:
        out = dict(json.load(handle)['settings'])
    for rec in export_records(export_dir, 'GMST'):
        if rec.get('EditorID', '')[:1] in ('f', 'i') and 'DATA.Value' in rec:
            out[rec['EditorID']] = float(rec['DATA.Value'])
    return out


def mult(chance: float, span: tuple) -> float:
    """The multiplier that makes FO4's min + (max - min) * mult equal `chance`."""
    lo, hi = span
    return (chance - lo) / (hi - lo)


def _f(rec: dict, key: str) -> float:
    """FNV style field `key` (CSTD/CSAD/CSSD...) of `rec`, 0 when absent."""
    return float(rec.get(key, 0) or 0)


def melee_shares(rec: dict, settings: dict, under_attack: bool, staggered: bool = False) -> tuple:
    """(attack, block) shares of FNV's one roll over attack, block and hold scores (0x9cc8de), the actor's
    weapon skill at SKILL_FRACTION, its target attacking or not and recoiling (`staggered`) or not."""
    state = 'WhileUnderAttack' if under_attack else 'NotUnderAttack'
    bonus = _f(rec, 'CSTD.RecoilStaggerBonusToAttack') if staggered else 0.0
    attack = max(0.0, (_f(rec, 'CSTD.AttackChance') + bonus + _f(rec, 'CSAD.AttackSkillModifierBase')
                       + _f(rec, 'CSAD.AttackSkillModifierMult') * SKILL_FRACTION) * _f(rec, f'CSAD.Attack{state}Mult'))
    block = max(0.0, (_f(rec, 'CSTD.BlockChance') + _f(rec, 'CSAD.BlockSkillModifierBase')
                      + _f(rec, 'CSAD.BlockSkillModifierMult') * SKILL_FRACTION) * _f(rec, f'CSAD.Block{state}Mult')
                * settings['fBlockScoreNoShieldMult'] * (1.0 if under_attack else 0.25))
    hold = max(100.0 - attack - block, settings['fCombatMaxHoldScore'])
    total = int(attack + block + hold) or 100
    return attack / total, block / total


def roll_at_most(score: float) -> float:
    """The chance FNV's rand() % 100 <= `score` passes."""
    return min(100, max(0, int(score) + 1)) / 100.0 if score >= 0 else 0.0


def dodge_shares(rec: dict, settings: dict, under_attack: bool) -> tuple:
    """(back, side) chances of an FNV dodge at melee range, full fatigue, against a melee target: the dodge roll
    (0x644990), then the direction (0x644a70) over every equally likely 1-5 draw of its three scores."""
    state = 'WhileUnderAttack' if under_attack else 'NotUnderAttack'
    score = max(0.0, (_f(rec, 'CSTD.DodgeChance') + _f(rec, 'CSAD.DodgeFatigueModBase'))
                * _f(rec, f'CSAD.Dodge{state}Mult'))
    base, back_mult = settings['fAIDodgeDecisionBase'], _f(rec, f'CSAD.DodgeBack{state}Mult')
    forward_mult = _f(rec, 'CSAD.DodgeForwardNotAttackingMult')
    draws = list(product(range(1, 6), repeat=3))
    back = sum(base * back_mult * b >= base * forward_mult * f and base * back_mult * b > base * s
               for b, f, s in draws) / len(draws)
    side = (1.0 - back) * roll_at_most(_f(rec, 'CSTD.LeftRightChance'))
    dodge = roll_at_most(score)
    return dodge * back, dodge * side


def converted_values(rec: dict, settings: dict) -> dict:
    """{FIELDS name: FO4 value} for FNV style `rec`; the fields it leaves out keep FO4's default.

    Defensive is capped at Offensive for a style that attacks: FO4 reads Defensive - Offensive as a stance
    (0x101b1a0) that holds melee actors off, and FNV has none.
    """
    attack, _ = melee_shares(rec, settings, False)
    staggered, _ = melee_shares(rec, settings, False, staggered=True)
    _, block = melee_shares(rec, settings, True)
    power = _f(rec, 'CSTD.PowerAttackChance') + _f(rec, 'CSAD.PowerAttackFatigueModBase')
    offensive = max(0.0, mult(attack, ATTACK))
    out = {'offensive': offensive, 'defensive': min(offensive, block) if offensive else block,
           'attack_staggered': staggered / attack if attack else 1.0,
           'power_staggered': (power + _f(rec, 'CSTD.RecoilStaggerBonusToPowerAttack')) / power if power > 0 else 1.0}
    out.update(_maneuvers(rec, settings))
    out.update(_ranged(rec))
    return out


def _maneuvers(rec: dict, settings: dict) -> dict:
    """Dodge, circle and fall back from FNV's melee dodges (none for a Ranged Only style, whose actors FNV never
    puts in its melee procedure); avoiding and evading threats off under Ignore Threats."""
    out = {'avoid': 0.0, 'evade': 0.0} if int(_f(rec, 'CSTD.Flags')) & IGNORE_THREATS else {}
    if rec.get('CSSD.WeaponRestrictions') == RANGED_ONLY:
        return {**out, 'dodge': 0.0, 'circle': 0.0, 'fallback': 0.0}
    back, side = dodge_shares(rec, settings, True)
    calm_back, calm_side = dodge_shares(rec, settings, False)
    return {**out, 'dodge': mult(back + side, DODGE_THREAT), 'circle': mult(calm_side, CIRCLE),
            'fallback': mult(calm_back, FALLBACK)}


def _ranged(rec: dict) -> dict:
    """Range mult, cover and equipment scores from FNV's CSSD."""
    lo, mid, hi = OPTIMAL_RANGE
    wanted = min(hi, max(lo, (_f(rec, 'CSSD.RangedWeaponRangeMultMin') + _f(rec, 'CSSD.RangedWeaponRangeMultMax')) / 2))
    x = (wanted - lo) / (mid - lo) - 1.0 if wanted <= mid else (wanted - mid) / (hi - mid)
    out = {'range': (x + 1.0) / 2.0}
    restriction = rec.get('CSSD.WeaponRestrictions')
    if restriction == MELEE_ONLY:
        out['ranged'] = RESTRICTED_SCORE
    elif restriction == RANGED_ONLY:
        out.update(melee=RESTRICTED_SCORE, unarmed=RESTRICTED_SCORE)
    cover = max(LEAST_COVER, mult(_f(rec, 'CSSD.CoverSearchRadius'), COVER_SEARCH))
    return {**out, 'cover': cover if _f(rec, 'CSSD.TakeCoverChance') > 0 else 0.0}


def pack_style(fid: int, edid: str, default: bytes, values: dict) -> bytes:
    """FO4 CSTY `fid` named `edid`: FO4 default style body `default` with `values` (converted_values) set."""
    blocks = {}
    for tag, data in subrecords(default):
        floats = list(struct.unpack(f'<{len(data) // 4}f', data)) if tag in (b'CSGD', b'CSME', b'CSCR', b'CSLR') else None
        size, fill = SIZES.get(tag, (0, 0.0))
        blocks[tag] = floats + [fill] * (size - len(floats)) if floats is not None else data
    for name, value in values.items():
        if name == 'cover':
            blocks[b'CSCV'] = struct.pack('<f', value)
        else:
            tag, index = FIELDS[name]
            blocks[tag][index] = value
    subs = b''
    for tag, data in blocks.items():
        data = struct.pack(f'<{len(data)}f', *data) if isinstance(data, list) else data
        subs += pack_string_subrecord('EDID', edid) if tag == b'EDID' else pack_subrecord(tag.decode(), data)
    return pack_fo4_record('CSTY', fid, 0, subs)


def fo4_default(fo4: bytes) -> bytes:
    """Fallout4.esm's FO4_DEFAULT style body."""
    for rec, _ in walk(fo4, b'CSTY'):
        if dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode('cp1252') == FO4_DEFAULT:
            return rec.body
    raise ValueError(f'{FO4_DEFAULT} not in Fallout4.esm')


class CombatStyles:
    """FO4 styles for FNV styles, each written once when an actor first names it."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV's styles and settings and Fallout4.esm's default style."""
        self.builder = builder
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'CSTY')}
        self.settings, self.default, self.made = fnv_settings(export_dir), fo4_default(builder.fo4), {}

    def record(self, traits: dict) -> dict:
        """The FNV style record of an actor whose traits are `traits`."""
        fnv = int(traits.get('ZNAM.CombatStyle', '0') or '0', 16)
        return self.records.get(fnv) or self.records[FNV_DEFAULT]

    def of(self, fnv: int) -> int:
        """The FO4 style of FNV style `fnv` (FNV_DEFAULT when 0 or not exported), written once."""
        fnv = fnv if fnv in self.records else FNV_DEFAULT
        if fnv not in self.made:
            rec = self.records[fnv]
            fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X}')
            values = converted_values(rec, self.settings)
            self.builder.writer.add_record('CSTY', pack_style(fid, f'FNV_{rec["EditorID"]}', self.default, values))
            self.builder.counts['CSTY'] += 1
            self.made[fnv] = fid
        return self.made[fnv]

    def edit(self, traits: dict):
        """The ZNAM edit for an actor whose traits are FNV record `traits`."""
        fid = self.of(int(traits.get('ZNAM.CombatStyle', '0') or '0', 16))
        return R.with_sub(b'ZNAM', struct.pack('<I', fid), ZNAM_BEFORE)
