"""FNV consumable effects as Fallout4.esm's, for the cell spike's consumables.

Each FNV effect becomes the Fallout4.esm effects EFFECTS names (FO4's own of the
same actor value and kind), a copy of a vanilla effect on another actor value
where FO4 has the mechanism but not the effect (RETARGETED, and every skill
boost IncreaseSkill* on its FNV skill), or nothing: drift, counted per effect.
Magnitude and duration stay FNV's, except where FNV's magnitude is a flag or
lives in a script (MAGNITUDES). An effect conditioned on a perk carries the
perk test (perks.Perks); one conditioned on Hardcore mode counts as without it
(UNCONVERTED), except Hardcore's need effects (NEEDS), which go to Survival mode
(survival_needs) and count it as on. An item left without effects
carries NO_EFFECT at magnitude 0, as vanilla's do.

See: docs/fork/fo4_pipeline.md#consumable-effects
"""

import re
import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.writer import pack_subrecord

#: Limb condition actor values (both games' names).
LIMBS = ('PerceptionCondition', 'EnduranceCondition', 'LeftAttackCondition', 'RightAttackCondition',
         'LeftMobilityCondition', 'RightMobilityCondition')
RESTORE_LIMBS = tuple('RestoreCondition' + p for p in ('Head', 'Torso', 'LeftArm', 'RightArm', 'LeftLeg', 'RightLeg'))
#: FNV magic effect EditorID -> the Fallout4.esm effects carrying it (same actor value, same kind).
EFFECTS = {
    'RestoreHealth': ('RestoreHealthFood',), 'RestoreHealthStimpak': ('RestoreHealthGeneric',),
    'DamageRadiationLevel': ('DamageRadiationChem',), 'RestoreRadiationLevel': ('RestoreRadsChem',),
    'NukaColaAddCap': ('NukaColaBottlecapAdder',), 'SunsetSarsparillaAddCap': ('NukaColaBottlecapAdder',),
    'IncreaseStrength': ('FortifyStrength',), 'IncreaseAgility': ('FortifyAgility',),
    'IncreaseCharisma': ('FortifyCharisma',), 'IncreaseActionPoints': ('FortifyActionPoints',),
    'IncreaseDamageThreshold': ('FortifyDamageResist',), 'IncreaseFireResistance': ('FortifyResistFire',),
    'IncreasePoisonResistance': ('FortifyResistPoison',), 'NVIncreaseEnergyResistance': ('FortifyResistEnergyFood',),
    'IncreaseRadiationResistance': ('FortifyResistRadsRadX',),
    'ChemIncSTAlcohol': ('FortifyStrengthAlcohol',), 'ChemIncCHAlcohol': ('FortifyCharismaAlcohol',),
    'ChemRedINAlcohol': ('ReduceIntelligenceAlcohol',), 'ChemIncPEAlcohol': ('FortifyPerception',),
    'ChemIncAGJet': ('FortifyAgility',), 'ChemIncAPJet': ('FortifyActionPointsJet',),
    'ChemIncAGTobacco': ('FortifyAgility',), 'ChemIncPETobacco': ('FortifyPerception',),
    'ChemIncSTBuffout': ('FortifyStrengthBuff',), 'ChemIncENBuffout': ('FortifyEnduranceBuff',),
    'ChemIncHealthBuffout': ('FortifyHealthBuff',), 'ChemIncINMentats': ('FortifyIntelligenceMentats',),
    'ChemIncPEMentats': ('FortifyPerceptionMentats',), 'ChemIncCHMentats': ('FortifyCharismaMentats',),
    'ReduceStrength': ('ReduceStrength',), 'ReducePerception': ('ReducePerception',),
    'ReduceEndurance': ('ReduceEndurance',), 'ReduceCharisma': ('ReduceCharisma',),
    'ReduceIntelligence': ('ReduceIntelligence',), 'ReduceAgility': ('ReduceAgility',),
    'StealthBoyInvis': ('ChameleonEffectStealthBoy',), 'TurboEffect': ('SlowTimeJet',),
    'PsychoMagicEffect': ('ExtraDamage25Psycho',), 'RestoreAllLimbs': RESTORE_LIMBS,
}
#: FNV effect -> FO4 magnitude: Turbo's is an on/off flag (FO4 Jet's time scale), Psycho's and the limb script's.
MAGNITUDES = {'TurboEffect': 0.3, 'PsychoMagicEffect': 25.0, 'RestoreAllLimbs': 100.0}
#: FNV effect -> (Fallout4.esm effect copied, the FO4 actor values its copies change); FNV's DR is FalloutDamageResist.
RETARGETED = {'NVRestoreLimbs': ('RestoreHealthFood', LIMBS),
              'IncreaseDamageResistance': ('FortifyDamageResist', ('FalloutDamageResist',)),
              'ChemIncDmgResistPsycho': ('FortifyDamageResistPsycho', ('FalloutDamageResist',)),
              'IncreaseCritChance': ('FortifyStrength', ('CritChance',))}
SKILL_EFFECT_PREFIX, SKILL_TEMPLATE = 'IncreaseSkill', 'FortifyStrength'
#: FNV engine effects the export cannot name (EFID ''): FalloutNV.esm uses only 0x14F, the addiction usage monitor.
UNNAMED = 'UMON'
#: FNV condition functions counted as false (true on NEEDS): FO4 has no Hardcore mode. HasPerk is written as FO4's.
UNCONVERTED = {'IsHardcore'}
#: FNV Hardcore need effect -> (Survival need, 1 when it lowers the need, -1 when it raises it).
NEEDS = {'RestoreStarvationLevel': ('hunger', 1), 'DamageStarvationLevel': ('hunger', -1),
         'RestoreDehydrationLevel': ('thirst', 1), 'DamageDehydrationLevel': ('thirst', -1),
         'RestoreSleepDeprivationLevel': ('sleep', 1), 'DamageSleepDeprivationLevel': ('sleep', -1)}
PERK_TEST, HAS_PERK = 'HasPerk', C.FO4.index('HasPerk')
#: A CTDA's comparison bits.
COMPARE = 0xE0
#: The effect an item with none left carries at magnitude 0, as vanilla's VRWorkshopShared_MutfruitFake.
NO_EFFECT = 'FortifyHealth'
#: DATA offset of an FO4 magic effect's actor value.
AV_AT = 0x44
#: derive_formid sites of the copies (key: the skill's name; FNV effect EditorID and actor value).
SITES = {'skill': 'FNV skill boost', 'copy': 'FNV effect copy'}
#: Every Fallout4.esm magic effect this module reads.
WANTED = {*(e for fo4 in EFFECTS.values() for e in fo4), *(t for t, _ in RETARGETED.values()),
          SKILL_TEMPLATE, NO_EFFECT}


def fnv_effects(rec: dict) -> list:
    """[(FNV effect EditorID, magnitude, area, duration, actor value index, its HasPerk tests)] FO4 can run
    (UNCONVERTED false, true on NEEDS)."""
    out = []
    for i in range(int(rec.get('EffectCount', 0))):
        key = f'Effect[{i}]'
        edid = rec[f'{key}.EFID'] or UNNAMED
        conds = [C.parse(rec[f'{key}.Condition[{j}].Raw']) for j in range(int(rec.get(f'{key}.ConditionCount', 0)))]
        if any(c['func'] in UNCONVERTED and not C.compare(c, float(edid in NEEDS)) for c in conds):
            continue
        out.append((edid, float(rec[f'{key}.Magnitude']), int(rec[f'{key}.Area']),
                    int(rec[f'{key}.Duration']), int(rec[f'{key}.ActorValue']),
                    [c for c in conds if c['func'] == PERK_TEST]))
    return out


class Effects:
    """FO4 effects for FNV consumables; copies are written once through the cell builder."""

    def __init__(self, builder, helper_index: int, vanilla: dict, needs=None):
        """`vanilla`: {EditorID: (FormID, data)}; `needs`: a SurvivalNeeds or None."""
        self.builder, self.helper_index, self.vanilla, self.needs = builder, helper_index, vanilla, needs
        self.copies = {}

    def subs(self, rec: dict) -> bytes:
        """EFID/EFIT pairs for FNV consumable `rec`; NO_EFFECT at magnitude 0 when none carries."""
        out = self.pairs(rec)
        if not out:
            self.builder.counts['ALCH with no effect (placeholder)'] += 1
            out = effect_pair(self.vanilla[NO_EFFECT][0], 0.0, 0, 0)
        return out

    def pairs(self, rec: dict) -> bytes:
        """EFID/EFIT pairs (with perk tests) of the effects of FNV `rec` (a consumable, a spell) FO4 carries; b''
        when none does."""
        out = b''
        for edid, magnitude, area, duration, av, perks in fnv_effects(rec):
            fo4 = self._targets(edid, av, magnitude)
            if not fo4:
                self.builder.counts[f'effect dropped ({edid})'] += 1
            tests = self._perk_tests(perks)
            if tests is None:
                self.builder.counts['effect dropped (perk not in the build)'] += 1
                continue
            for fid, value in fo4:
                out += effect_pair(fid, value, area, duration) + tests
        return out

    def _perk_tests(self, perks: list) -> 'bytes | None':
        """FO4 HasPerk CTDAs of an effect's FNV HasPerk tests, OR flags kept within them; a perk the build lacks
        counts as not held (its test dropped when that passes); None when the effect then never runs."""
        ids = self.builder.perks.form_map()
        if any(c['p1'] not in ids and not C.compare(c, 0.0) for c in perks):
            return None
        perks = [c for c in perks if c['p1'] in ids]
        out = b''
        for i, cond in enumerate(perks):
            joined = cond['op_flags'] & C.OR_NEXT if i < len(perks) - 1 else 0
            out += R.pack_ctda(cond['op_flags'] & COMPARE | joined, cond['value'], HAS_PERK, ids[cond['p1']])
        self.builder.counts['effect perk tests'] += len(perks)
        return out

    def _targets(self, edid: str, av: int, magnitude: float) -> list:
        """[(FO4 effect FormID, magnitude)] for FNV effect `edid`; [] when none."""
        if edid in NEEDS:
            return self.needs.effects(edid, magnitude) if self.needs else []
        return [(fid, MAGNITUDES.get(edid, magnitude)) for fid in self._fo4(edid, av)]

    def _fo4(self, edid: str, av: int) -> list:
        """FormIDs of the FO4 effects for FNV effect `edid` (on FNV actor value index `av`): a mapped, retargeted or
        skill effect, else its converted script as a script effect; [] with none."""
        if edid in EFFECTS:
            return [self.vanilla[e][0] for e in EFFECTS[edid]]
        if edid in RETARGETED:
            template, avs = RETARGETED[edid]
            return [self.copy(template, name, 'copy', f'{edid} {name}', f'FNV_{edid}_{name}') for name in avs]
        if edid.startswith(SKILL_EFFECT_PREFIX) and 0 <= av < len(C.FNV_AV_NAMES):
            skill = C.FNV_AV_NAMES[av].replace(' ', '')
            return [self.copy(SKILL_TEMPLATE, skill, 'skill', skill, f'FNV_Fortify{skill}')]
        scripted = self.builder.scripts.effects.consumed(edid)
        return [scripted] if scripted else []

    def copy(self, template: str, av: str, site: str, key: str, edid: str) -> int:
        """FormID of a copy of vanilla effect `template` changing FO4 actor value `av`; written on first use."""
        if key in self.copies:
            return self.copies[key]
        fid = self.copies[key] = self.builder.writer.derive_formid(SITES[site], key)
        subs = self.vanilla[template][1]
        data = bytearray(subs[b'DATA'])
        data[AV_AT:AV_AT + 4] = struct.pack('<I', actor_value_form(av, self.helper_index))
        name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', av)
        body = pack_subrecord('EDID', f'{edid}\0'.encode()) + pack_subrecord('FULL', f'{name}\0'.encode())
        body += pack_subrecord('DATA', bytes(data))
        body += pack_subrecord('SNDD', subs[b'SNDD']) if b'SNDD' in subs else b''
        body += pack_subrecord('DNAM', b'\0')
        self.builder.writer.add_record('MGEF', pack_fo4_record('MGEF', fid, 0, body))
        self.builder.counts[f'MGEF ({site})'] += 1
        return fid


def effect_pair(fid: int, magnitude: float, area: int, duration: int) -> bytes:
    """One EFID/EFIT pair."""
    return pack_subrecord('EFID', struct.pack('<I', fid)) + pack_subrecord('EFIT', struct.pack('<fII', magnitude,
                                                                                               area, duration))
