"""FNV's Hardcore need effects on consumables as Fallout 4 Survival's hunger, thirst and sleep.

Each FNV need effect (consumable_effects.NEEDS) becomes a Script-archetype effect
running SCRIPT, one per FNV effect and amount (the amount a script property, as on
vanilla's addiction effects), which hands Survival's own manager (MANAGER) the amount in
Survival's units: the game hours the amount covers at FNV's rate (its GMST, else
FalloutNV.exe's default, and TimeScale) times Survival's cost per hour. Lowered
Sleep Deprivation equips a hidden potion with Survival's caffeine keywords, the
extra one from EXTRA_AT hours. An item with need effects carries IGNORE_AS_FOOD,
so Survival does not also feed by its price.

See: docs/fork/fo4_pipeline.md#survival-needs
"""

from fo4_import.base.vmad import object_scripts
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.consumable_effects import NEEDS, NO_EFFECT
from fo4_import.spike.hotkey_items import hotkey_effect, hotkey_item

HUNGER, THIRST, SLEEP = 'hunger', 'thirst', 'sleep'
#: Per need: FNV's rate GMST (real seconds per point) and FalloutNV.exe's default for it.
RATES = {HUNGER: ('fHCStarvationRate', 0.39), THIRST: ('fHCDehydrationRate', 10.0),
         SLEEP: ('fHCSleepDeprivationRate', 0.26)}
#: FNV's TimeScale global; the script's Need property per need.
TIMESCALE, NEED_INDEX = 'TimeScale', {HUNGER: 0, THIRST: 1, SLEEP: 2}
#: HC_ManagerScript's FoodCostPerTick and DrinkCostPerTick per one-hour tick (Fallout4.esm keeps the defaults).
SURVIVAL_PER_HOUR = 4.0
#: HC_ManagerScript's CaffeineInducedSleepDelay and ExtraCaffeineInducedSleepDelay (hours); the extra from their middle.
CAFFEINE_HOURS = (2.333, 7.0)
EXTRA_AT = sum(CAFFEINE_HOURS) / 2
#: Survival's caffeine keywords per tier, and the keyword that hides an item from Survival's food handling.
CAFFEINE = (('ObjectTypeCaffeinated',), ('ObjectTypeCaffeinated', 'ObjectTypeExtraCaffeinated'))
IGNORE_AS_FOOD = 'HC_IgnoreAsFood'
#: Survival's rule global per need, and its manager quest.
RULES = {HUNGER: 'HC_Rule_SustenanceEffects', THIRST: 'HC_Rule_SustenanceEffects', SLEEP: 'HC_Rule_SleepEffects'}
MANAGER = 'HC_Manager'
#: Effect names per need.
NAMES = {HUNGER: 'Hunger', THIRST: 'Thirst', SLEEP: 'Caffeine'}
SCRIPT = 'F3NV_SurvivalNeed'
#: derive_formid site (key: FNV effect EditorID and FNV magnitude; potion: its caffeine keyword).
SITE = 'FNV survival need'
#: Every Fallout4.esm record this module reads.
WANTED = {IGNORE_AS_FOOD, MANAGER, *RULES.values(), *CAFFEINE[1]}


def fnv_per_hour(export_dir) -> dict:
    """{need: FNV points per game hour}: 3600 / TimeScale real seconds per hour over each RATES setting."""
    gmst = {r.get('EditorID'): r for r in export_records(export_dir, 'GMST')}
    scale = next(float(r['FLTV.Value']) for r in export_records(export_dir, 'GLOB') if r.get('EditorID') == TIMESCALE)
    return {need: 3600.0 / scale / float(gmst.get(name, {}).get('DATA.Value', default))
            for need, (name, default) in RATES.items()}


class SurvivalNeeds:
    """Survival need effects for FNV consumables; effects and caffeine potions written once through the builder."""

    def __init__(self, builder, vanilla: dict, per_hour: dict):
        """`vanilla`: {EditorID: (FormID, {tag: data})}, WANTED's and NO_EFFECT included."""
        self.builder, self.vanilla, self.per_hour, self.made = builder, vanilla, per_hour, {}

    def effects(self, edid: str, amount: float) -> list:
        """[(FO4 effect FormID, magnitude)] for FNV need effect `edid` of `amount`; [] for raised sleep."""
        need, sign = NEEDS[edid]
        hours = amount / self.per_hour[need]
        if need != SLEEP:
            points = float(max(1, round(hours * SURVIVAL_PER_HOUR)))
            return [(self._effect(edid, amount, need, {'Amount': ('float', sign * points)}), points)]
        if sign < 0:
            return []
        tier = int(hours >= EXTRA_AT)
        return [(self._effect(edid, amount, need, {}, tier), CAFFEINE_HOURS[tier])]

    def _effect(self, edid: str, amount: float, need: str, values: dict, tier: int = None) -> int:
        """FormID of the SCRIPT effect for FNV effect `edid` of `amount`, with `values` (sleep: caffeine `tier`)."""
        key = f'{edid} {amount:g}'
        if key not in self.made:
            fid = self.made[key] = self.builder.writer.derive_formid(SITE, key)
            objects = {'HC_Manager': self.vanilla[MANAGER][0], 'Rule': self.vanilla[RULES[need]][0]}
            if tier is not None:
                objects['Caffeine'] = self._potion(tier)
            values = {'Need': ('int', NEED_INDEX[need]), **values}
            hotkey_effect(self.builder, fid, f'FNV_Survival_{edid}_{amount:g}', NAMES[need],
                          object_scripts([(SCRIPT, objects, values)]))
            self.builder.scripts.used.append(SCRIPT)
            self.builder.counts['MGEF (survival need)'] += 1
        return self.made[key]

    def _potion(self, tier: int) -> int:
        """FormID of the hidden caffeine potion of `tier`: CAFFEINE's keywords, a zero NO_EFFECT."""
        key = CAFFEINE[tier][-1]
        if key not in self.made:
            fid = self.made[key] = self.builder.writer.derive_formid(SITE, key)
            hotkey_item(self.builder, fid, f'FNV_Survival_{key}', NAMES[SLEEP], self.vanilla[NO_EFFECT][0],
                        tuple(self.vanilla[k][0] for k in CAFFEINE[tier]))
        return self.made[key]
