"""FNV's random critical hits on Fallout 4's own critical roll.

FNV rolls every hit (FalloutNV.exe 0x9B7060, its base 0x646D80): chance % = the attacker's perks (entry point 1)
applied to CritChance / (Fire Rate, automatic weapons only) x the weapon's Crit % Mult, then the target's
enemy-critical perks, plus fVATSCriticalChanceBonus in V.A.T.S. CritChance is fAVDCritLuckBase + fAVDCritLuckMult
x Luck plus abilities (Finesse +5). FO4 rolls every hit on its perk entry point 1 (Mod Critical Chance) from 0, as
vanilla Overdrive's +25 shows.

The combat rules perk (combat_perk) carries FNV's formula. Each weapon carries a keyword for its factor (Crit % Mult
over its fire rate when automatic, type_tests stamps it); for each factor f the perk adds Luck x f x
fAVDCritLuckMult, CritChance (the helper plugin's actor value) x f and f x fAVDCritLuckBase, a weapon with no factor
keyword counting 1. Only additions, so FO4's order of perk entries never changes the result; FNV's own critical
chance multipliers (Ninja's x1.15) become additions of the same kind in their perk (folded).

See: docs/fork/fo4_pipeline.md#random-criticals
"""

import struct

from fo4_import.base.install import source_walk
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.perks import CRIT_CHANCE, FLOAT_PARAM
from fo4_import.spike.sneak_attacks import in_vats, sneaking
from fo4_import.spike.type_tests import FACTORED, crit_factor
from tes5_import.base.tes5_reader import subrecords

#: The critical chance entry point's tabs (owner, weapon, target), the owner's and the weapon's.
CRIT_TABS, OWNER_TAB, WEAPON_TAB = 3, 0, 1
#: Entry point functions Add Value, Add Actor Value Mult; EPFT of an actor value and a float.
ADD_VALUE, ADD_AV_MULT, AV_PARAM = 2, 5, 8


class Criticals:
    """FNV's random critical hits for one build: the entries and the weapon factors they test."""

    def __init__(self, builder, settings: dict, helper_index: int):
        """FNV's `settings` (combat_styles.fnv_settings); every weapon factor of the source plugin, read once."""
        self.builder = builder
        self.base, self.mult = settings.get('fAVDCritLuckBase', 0.0), settings.get('fAVDCritLuckMult', 1.0)
        self.vats = settings.get('fVATSCriticalChanceBonus', 0.0)
        self.sneak = settings.get('fCombatSneakAttackBonusMult', 1.0)
        self.luck, self.chance = actor_value_form('Luck', helper_index), actor_value_form('CritChance', helper_index)
        self.factors = sorted({found for rec, _ in source_walk(b'WEAP')
                               if (found := crit_factor(dict(subrecords(rec.body))))})

    def _buckets(self) -> list:
        """[(weapon tab condition, factor)]: unmarked (1), then each factor."""
        keyword, has = self.builder.type_keywords.keyword, C.FO4.index('HasKeyword')
        return [(R.pack_ctda(0, 0.0, has, keyword(FACTORED)), 1.0)] + [
            (R.pack_ctda(0, 1.0, has, keyword(edid)), factor) for edid, factor in self.factors]

    def adds(self, scale: float, tabs: dict) -> list:
        """[(DATA, tabs, parameters)] adding `scale` x FNV's critical chance for each weapon factor, under `tabs`."""
        out = []
        for weapon, factor in self._buckets():
            k = scale * factor
            where = {**tabs, WEAPON_TAB: weapon + tabs.get(WEAPON_TAB, b'')}
            out += [(bytes([CRIT_CHANCE, ADD_AV_MULT, CRIT_TABS]), where,
                     [(b'EPFT', bytes([AV_PARAM])), (b'EPFD', struct.pack('<If', av, k * mult))])
                    for av, mult in ((self.luck, self.mult), (self.chance, 1.0))]
            if self.base:
                out.append((bytes([CRIT_CHANCE, ADD_VALUE, CRIT_TABS]), where,
                            [(b'EPFT', bytes([FLOAT_PARAM])), (b'EPFD', struct.pack('<f', k * self.base))]))
        return out

    def entries(self) -> list:
        """The combat rules perk's critical chance entries: FNV's chance; plus fVATSCriticalChanceBonus in
        V.A.T.S.; a player's sneak attack (sneak_attacks) adding (fCombatSneakAttackBonusMult - 1) x both."""
        self.builder.counts['critical factors'] = len(self.factors)
        extra = self.sneak - 1.0
        return (self.adds(1.0, {}) + self.adds(extra, {OWNER_TAB: sneaking()})
                + [self._added(self.vats, in_vats()), self._added(extra * self.vats, in_vats() + sneaking())])

    @staticmethod
    def _added(value: float, owner: bytes) -> tuple:
        """An entry adding `value` to the chance under owner conditions `owner`."""
        return (bytes([CRIT_CHANCE, ADD_VALUE, CRIT_TABS]), {OWNER_TAB: owner},
                [(b'EPFT', bytes([FLOAT_PARAM])), (b'EPFD', struct.pack('<f', value))])

    def folded(self, tabs: dict, value: float) -> list:
        """FNV crit chance multiplier `value` (under `tabs`) as adds()."""
        self.builder.counts['critical chance multiplier folded'] += 1
        return self.adds(value - 1.0, tabs)
