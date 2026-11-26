"""FNV consumable effects as Fallout4.esm's, for the cell spike's consumables.

Each FNV effect becomes the Fallout4.esm effects EFFECTS names (FO4's own of the
same actor value and kind), a copy of a vanilla effect on another actor value
where FO4 has the mechanism but not the effect (RETARGETED, and every skill
boost IncreaseSkill* on its FNV skill), its converted script, else, for any
other Value Modifier effect, Fallout4.esm's plain effect of its actor value and
kind (by_value), or nothing: drift, counted per effect with the reason.
Magnitude and duration stay FNV's, except where FNV's magnitude is a flag or
lives in a script (MAGNITUDES). An effect conditioned on a perk carries the
perk test (perks.Perks); one conditioned on Hardcore mode (HARDCORE) carries that test as a read of the
Hardcore global (hardcore.Hardcore.test), so both variants of an effect are kept; Hardcore's need effects
(NEEDS) go to FNV's Hardcore needs (hardcore.Hardcore.need_effects). An item left without effects
carries NO_EFFECT at magnitude 0, as vanilla's do.

See: docs/fork/fo4_pipeline.md#consumable-effects
"""

import re
import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords
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
#: FNV's Hardcore test, written as a read of the Hardcore global (hardcore.Hardcore.test). HasPerk is written as FO4's.
HARDCORE = 'IsHardcore'
#: FNV Hardcore need effect -> (need: 0 Dehydration, 1 Hunger, 2 Sleep Deprivation; 1 raises it, -1 lowers it).
NEEDS = {'RestoreDehydrationLevel': (0, -1), 'DamageDehydrationLevel': (0, 1),
         'RestoreStarvationLevel': (1, -1), 'DamageStarvationLevel': (1, 1),
         'RestoreSleepDeprivationLevel': (2, -1), 'DamageSleepDeprivationLevel': (2, 1)}
PERK_TEST, HAS_PERK = 'HasPerk', C.FO4.index('HasPerk')
#: FNV's actor value test, written as FO4's GetValue of the same-named actor value (HeadCrippleEffect's Perception).
VALUE_TEST, GET_VALUE = 'GetActorValue', C.FO4.index('GetValue')
#: A CTDA's comparison bits.
COMPARE = 0xE0
#: The effect an item with none left carries at magnitude 0, as vanilla's VRWorkshopShared_MutfruitFake.
NO_EFFECT = 'FortifyHealth'
#: DATA offset of an FO4 magic effect's actor value.
AV_AT = 0x44
#: derive_formid sites of the copies (key: the skill's name; FNV effect EditorID and actor value).
SITES = {'skill': 'FNV skill boost', 'copy': 'FNV effect copy'}
#: FNV's Value Modifier archetype, routed by actor value (by_value); FNV's and FO4's Recover and Detrimental flags.
VALUE_MODIFIER, RECOVER, DETRIMENTAL = 0, 0x2, 0x4
#: MGEF DATA offset of the archetype, the actor value after it (both games); FO4's casting type and delivery.
ARCHETYPE_AT, CAST_AT = 0x40, 0x50
#: Fallout4.esm's plain value effects: archetypes Value Modifier and Peak Value Modifier, cast as a consumable is.
FO4_VALUE_ARCHETYPES, VALUE_PREFIXES, CONSUMED = (0, 34), ('fortify', 'reduce', 'restore', 'damage'), (1, 0)
#: FO4 MGEF flags Hide in UI; the subrecords a plain value effect has none of.
HIDDEN, NOT_PLAIN = 0x8000, (b'VMAD', b'CTDA', b'KWDA')
#: The copied template by (lowers, recovers) where Fallout4.esm has no plain effect of that kind on the actor value.
VALUE_TEMPLATES = {(False, True): SKILL_TEMPLATE, (True, True): 'ReduceStrength',
                   (False, False): 'RestoreHealthFood', (True, False): 'DamageHealth'}
#: Why an effect has no FO4 effect, by FNV archetype (None: no MGEF record, as UMON); others name their number.
DROP_REASONS = {None: 'no record', 1: 'script did not convert', VALUE_MODIFIER: 'actor value FO4 lacks'}
#: Every Fallout4.esm magic effect this module reads.
WANTED = {*(e for fo4 in EFFECTS.values() for e in fo4), *(t for t, _ in RETARGETED.values()),
          *VALUE_TEMPLATES.values(), NO_EFFECT}


def fnv_effects(rec: dict) -> list:
    """[(FNV effect EditorID, magnitude, area, duration, actor value index, its HasPerk tests, its HARDCORE
    tests, its VALUE_TEST tests)]."""
    out = []
    for i in range(int(rec.get('EffectCount', 0))):
        key = f'Effect[{i}]'
        edid = rec[f'{key}.EFID'] or UNNAMED
        conds = [C.parse(rec[f'{key}.Condition[{j}].Raw']) for j in range(int(rec.get(f'{key}.ConditionCount', 0)))]
        out.append((edid, float(rec[f'{key}.Magnitude']), int(rec[f'{key}.Area']),
                    int(rec[f'{key}.Duration']), int(rec[f'{key}.ActorValue']),
                    *([c for c in conds if c['func'] == func] for func in (PERK_TEST, HARDCORE, VALUE_TEST))))
    return out


def value_key(subs: dict) -> 'tuple | None':
    """(actor value, lowers, recovers) of Fallout4.esm effect `subs` ({tag: data}) when it is a plain value effect a
    consumable casts (VALUE_PREFIXES, FO4_VALUE_ARCHETYPES, CONSUMED, shown, no NOT_PLAIN); None otherwise."""
    data = subs.get(b'DATA', b'')
    edid = subs.get(b'EDID', b'').rstrip(b'\0').decode().lower()
    if not edid.startswith(VALUE_PREFIXES) or any(t in subs for t in NOT_PLAIN) or len(data) < CAST_AT + 8:
        return None
    flags, (archetype, av) = struct.unpack_from('<I', data)[0], struct.unpack_from('<II', data, ARCHETYPE_AT)
    if archetype not in FO4_VALUE_ARCHETYPES or flags & HIDDEN or struct.unpack_from('<II', data, CAST_AT) != CONSUMED:
        return None
    return av, bool(flags & DETRIMENTAL), bool(flags & RECOVER)


def fnv_value_effects() -> dict:
    """{FNV effect EditorID: (archetype, actor value, flags)} of the source stack's MGEF DATA, the source's first
    (the export drops the archetype and actor value)."""
    out = {}
    for rec, _ in source_walk(b'MGEF'):
        subs = dict(subrecords(rec.body))
        data = subs.get(b'DATA', b'')
        if len(data) >= ARCHETYPE_AT + 8:
            kind = (*struct.unpack_from('<Ii', data, ARCHETYPE_AT), struct.unpack_from('<I', data)[0])
            out.setdefault(subs.get(b'EDID', b'').rstrip(b'\0').decode(), kind)
    return out


class Effects:
    """FO4 effects for FNV consumables; copies are written once through the cell builder."""

    def __init__(self, builder, helper_index: int, vanilla: dict, hardcore=None, values: 'dict | None' = None):
        """`vanilla`: {EditorID: (FormID, data)}; `values`: {value_key(): FormID}."""
        self.builder, self.helper_index, self.vanilla, self.hardcore = builder, helper_index, vanilla, hardcore
        self.copies, self.values, self.fnv_values = {}, values or {}, None

    def subs(self, rec: dict) -> bytes:
        """EFID/EFIT pairs for FNV consumable `rec`; NO_EFFECT at magnitude 0 when none carries."""
        out = self.pairs(rec)
        if not out:
            self.builder.counts['ALCH with no effect (placeholder)'] += 1
            out = effect_pair(self.vanilla[NO_EFFECT][0], 0.0, 0, 0)
        return out

    def pairs(self, rec: dict) -> bytes:
        """EFID/EFIT pairs (with Hardcore and perk tests) of the effects of FNV `rec` (a consumable, a spell) FO4
        carries; b'' when none does."""
        out = b''
        for edid, magnitude, area, duration, av, perks, hardcore, values in fnv_effects(rec):
            fo4 = self.targets(edid, av, magnitude)
            if not fo4:
                self.builder.counts[f'effect dropped ({edid}: {self.drop_reason(edid)})'] += 1
            tests = self._hardcore_tests(hardcore)
            perk_tests = self._perk_tests(perks)
            tests = None if tests is None or perk_tests is None else tests + perk_tests + self._value_tests(values)
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

    def _value_tests(self, conds: list) -> bytes:
        """FO4 GetValue CTDAs of an effect's FNV actor value tests, ANDed; one FO4 lacks the value of, or compared
        to a global, is dropped (counted) as the other tests this path cannot write."""
        out = b''
        for cond in conds:
            av = actor_value_form(C.fnv_av_name(cond['p1']), self.helper_index)
            if av is None or cond['op_flags'] & C.USE_GLOBAL:
                self.builder.counts[f'effect test dropped ({VALUE_TEST} {C.fnv_av_name(cond["p1"])})'] += 1
                continue
            out += R.pack_ctda(cond['op_flags'] & COMPARE, cond['value'], GET_VALUE, av)
        return out

    def _hardcore_tests(self, conds: list) -> 'bytes | None':
        """Tests of HARDCORE `conds`; with no mode, settled as off (None: fails)."""
        if self.hardcore and self.hardcore.on:
            return b''.join(self.hardcore.test(c) for c in conds)
        return None if any(not C.compare(c, 0.0) for c in conds) else b''

    def targets(self, edid: str, av: int, magnitude: float) -> list:
        """[(FO4 effect FormID, magnitude)] for FNV effect `edid`; [] when none."""
        if edid in NEEDS:
            return self.hardcore.need_effects(edid, magnitude) if self.hardcore and self.hardcore.on else []
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
        return [scripted] if scripted else self.by_value(edid, av)

    def _fnv_value(self, edid: str) -> tuple:
        """(archetype, actor value, flags) of FNV effect `edid`; (None, -1, 0) for none."""
        if self.fnv_values is None:
            self.fnv_values = fnv_value_effects()
        return self.fnv_values.get(edid, (None, -1, 0))

    def by_value(self, edid: str, av: int) -> list:
        """[FO4 effect] of FNV Value Modifier effect `edid` on its actor value (the effect item's `av`, else its own),
        of its kind (lowers, recovers): Fallout4.esm's plain one, else a VALUE_TEMPLATES copy; [] for another
        archetype or an actor value FO4 lacks.
        See: docs/fork/fo4_pipeline.md#effects-by-actor-value
        """
        archetype, own, flags = self._fnv_value(edid)
        av = av if av >= 0 else own
        name = C.fnv_av_name(av) if archetype == VALUE_MODIFIER and 0 <= av < len(C.FNV_AV_NAMES) else ''
        fo4_av = actor_value_form(name, self.helper_index) if name else None
        if fo4_av is None:
            return []
        kind = (bool(flags & DETRIMENTAL), bool(flags & RECOVER))
        if (fo4_av, *kind) in self.values:
            return [self.values[(fo4_av, *kind)]]
        template = VALUE_TEMPLATES[kind]
        return [self.copy(template, name, 'copy', f'{template} {name}', f'FNV_{template}_{name}')]

    def drop_reason(self, edid: str) -> str:
        """Why FNV effect `edid` has no FO4 effect (DROP_REASONS by its archetype)."""
        if edid in NEEDS:
            return 'Hardcore off'
        archetype = self._fnv_value(edid)[0]
        return DROP_REASONS.get(archetype, f'archetype {archetype}')

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
