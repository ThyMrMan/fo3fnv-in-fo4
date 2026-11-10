"""FNV's Hardcore mode on Fallout 4, in place of Survival's needs: its switch, needs, stages and rules.

FNV's engine keeps the needs (Dehydration, Hunger, Sleep Deprivation, 0 to
1000), helper plugin actor values here (NEED_AVS). The game plugin gets a
start-game quest running SCRIPT, which raises them at FNV's rates (per_hour),
lowers Sleep Deprivation on sleep and keeps limbs unmended by sleep; F3NV.dll
weighs ammo and shows the needs on the HUD while it is on. Converted scripts' SetHardcore (Doc Mitchell's choice) and an aid item
switch it. Each stage of FNV's DEHY, HUNG and SLPD records (stages) becomes a
potion of its spell's effects, conditioned on the need's range, as Survival's
stages are. Need effects on consumables become NEED_SCRIPT effects carrying
FNV's amount (need_effects); IsHardcore conditions read the Hardcore global
(test; HARDCORE_KEY for dialogue and messages). FO3 has no stage records:
nothing is made.

See: docs/fork/fo4_hardcore.md#built
"""

import struct
from pathlib import Path

from fo4_import.base.install import source_walk
from fo4_import.base.support_records import pack_global, pack_mesg, pack_script_quest
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.consumable_effects import COMPARE, LIMBS, NEEDS, effect_pair, fnv_effects
from fo4_import.spike.hotkey_items import NO_AUTO_CALC, hotkey_effect, hotkey_item
from fo4_import.spike.say_topics import HARDCORE_KEY
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: derive_formid sites: the mode's records (key: EditorID); need effects (key: FNV effect and amount; kept from before).
SITE, NEED_SITE = 'FNV hardcore', 'FNV survival need'
SCRIPT, NEED_SCRIPT, ITEM_SCRIPT = 'F3NV_Hardcore', 'F3NV_HardcoreNeed', 'F3NV_HardcoreItem'
#: The property converted scripts reach the quest through (command_rows_fallout4).
PROPERTY = 'TES4Hardcore'
#: Per need (NEEDS' index): FNV's stage record type, helper actor value, name, rate setting and FalloutNV.exe's default.
STAGE_TYPES = (b'DEHY', b'HUNG', b'SLPD')
NEED_AVS, NAMES = ('Dehydration', 'Hunger', 'SleepDeprivation'), ('Dehydration', 'Hunger', 'Sleep Deprivation')
RATES = (('fHCDehydrationRate', 10.0), ('fHCStarvationRate', 0.39), ('fHCSleepDeprivationRate', 0.26))
SLEEP_RESTORE, TIMESCALE = ('fHCSleepRestorationMod', 60.0), 'TimeScale'
#: Per need: FNV's raised and lowered messages (GMST), and FalloutNV.exe's text where FalloutNV.esm has none.
MESSAGES = (('sDehydrationIncrease', 'sDehydrationDecrease'), ('sHungerIncrease', 'sHungerDecrease'),
            ('sSleepDeprevationIncrease', 'sSleepDeprevationDecrease'))
DEFAULT_TEXT = {'sHungerIncrease': 'Your Hunger level has increased',
                'sHungerDecrease': 'Your Hunger level has decreased'}
#: Survival's effect type keyword per need, on the stage potions as on Survival's.
STAGE_KEYWORDS = ('HC_EffectType_Thirst', 'HC_EffectType_Hunger', 'HC_EffectType_Sleep')
#: Survival's manager and the rules turned off for a Hardcore character who picks Survival.
MANAGER = 'HC_Manager'
SURVIVAL_RULES = ('HC_Rule_SustenanceEffects', 'HC_Rule_SleepEffects', 'HC_Rule_DiseaseEffects', 'HC_Rule_AdrenalineOn')
#: A stage effect's duration, Survival's stage potions' (seconds).
LONG = 0x337E4680
ITEM_NAME = 'Hardcore Mode'
#: The Hardcore item's boxes: (EditorID, text, buttons); the first shows the three needs.
MENUS = (('MenuOn', 'Hardcore Mode is on.\n\nH2O %.0f   FOD %.0f   SLP %.0f\n\nTurning it off resets your needs, '
                    'and the reward for finishing the game in Hardcore Mode is lost.', ['Keep it on', 'Turn it off']),
         ('MenuOff', 'Hardcore Mode is off.', ['Turn it on', 'Keep it off']))
SURVIVAL_OFF = "Hardcore Mode replaces Survival's hunger, thirst, sleep, illness and adrenaline for this character."
GET_VALUE, GLOBAL_VALUE = C.FO4.index('GetValue'), C.FO4.index('GetGlobalValue')


def per_hour(export_dir: Path) -> list:
    """Each need's FNV points per game hour, from RATES and TimeScale."""
    scale = next(float(r['FLTV.Value']) for r in export_records(export_dir, 'GLOB') if r.get('EditorID') == TIMESCALE)
    return [3600.0 / scale / _setting(export_dir, *rate) for rate in RATES]


def _setting(export_dir: Path, name: str, default):
    """GMST `name`'s value in the export, else `default` (FalloutNV.exe's)."""
    rec = next((r for r in export_records(export_dir, 'GMST') if r.get('EditorID') == name), {})
    value = rec.get('DATA.Value', default)
    return value if isinstance(default, str) else float(value)


def stages() -> list:
    """Per need: [(threshold, FNV stage spell)] of STAGE_TYPES; [] (FO3) without."""
    out = [sorted(struct.unpack('<II', first_sub(rec.body, b'DATA')) for rec, _ in source_walk(sig))
           for sig in STAGE_TYPES]
    return out if all(out) else []


def range_tests(av: int, low: float, high: float) -> bytes:
    """CTDAs passing while actor value `av` is from `low` to under `high`."""
    return R.pack_ctda(0x60, float(low), GET_VALUE, av) + R.pack_ctda(0x80, float(high), GET_VALUE, av)


class Hardcore:
    """FNV's Hardcore mode of one build: its globals at once, need effects as asked, the rest in write()."""

    def __init__(self, builder, export_dir: Path, helper_index: int):
        """The mode's forms for `builder`'s game; none without FNV's stage records."""
        self.builder, self.export_dir, self.made = builder, export_dir, {}
        self.stages = stages()
        self.avs = [actor_value_form(name, helper_index) for name in NEED_AVS]
        self.limbs = [actor_value_form(name, helper_index) for name in LIMBS]
        self.quest = self.on = self.always = None
        if not self.stages:
            return
        derive = builder.writer.derive_formid
        self.quest, self.on, self.always = (derive(SITE, k) for k in ('FNV_Hardcore', 'F3NV_Hardcore',
                                                                      'F3NV_HardcoreAlways'))
        builder.writer.add_record('GLOB', pack_global(self.on, 'F3NV_Hardcore'))
        builder.writer.add_record('GLOB', pack_global(self.always, 'F3NV_HardcoreAlways'))

    def form_map(self) -> dict:
        """{HARDCORE_KEY: the Hardcore global} for conditions; {} without the mode."""
        return {HARDCORE_KEY: self.on} if self.on else {}

    def named(self) -> dict:
        """{PROPERTY: the quest} for converted scripts; {} without the mode."""
        return {PROPERTY: self.quest} if self.quest else {}

    def test(self, cond: dict) -> bytes:
        """FNV IsHardcore `cond` as GetGlobalValue on the Hardcore global."""
        return R.pack_ctda(cond['op_flags'] & COMPARE, cond['value'], GLOBAL_VALUE, self.on)

    def need_effects(self, edid: str, amount: float) -> list:
        """[(FO4 effect FormID, magnitude)] for FNV need effect `edid` of `amount`: NEED_SCRIPT carrying FNV's
        amount (positive raises the need), written once."""
        need, sign = NEEDS[edid]
        key = f'{edid} {amount:g}'
        if key not in self.made:
            fid = self.made[key] = self.builder.writer.derive_formid(NEED_SITE, key)
            values = {'Need': ('int', need), 'Amount': ('float', sign * float(amount))}
            hotkey_effect(self.builder, fid, f'FNV_Hardcore_{edid}_{amount:g}', NAMES[need],
                          object_scripts([(NEED_SCRIPT, {'Manager': self.quest}, values)]))
            self.builder.scripts.used.append(NEED_SCRIPT)
            self.builder.counts['MGEF (Hardcore need)'] += 1
        return [(self.made[key], float(amount))]

    def write(self, effects) -> None:
        """The stage potions (their effects through consumable Effects `effects`), messages, the Hardcore item and
        the quest; nothing without the mode or when a master holds the quest.
        See: docs/fork/fo4_hardcore.md#built
        """
        if not self.quest:
            return
        self.builder.scripts.used += [SCRIPT, ITEM_SCRIPT]
        if self.quest >> 24 != self.builder.writer.own_index:
            return
        vanilla = _vanilla(self.builder.fo4, {MANAGER, *SURVIVAL_RULES, *STAGE_KEYWORDS})
        spells = {int(r['FormID'], 16): r for r in export_records(self.export_dir, 'SPEL')}
        potions = [self._stage(need, i, spells, effects, vanilla[STAGE_KEYWORDS[need]])
                   for need in range(len(NEED_AVS)) for i in range(len(self.stages[need]) - 1)]
        raised, lowered = ([self._message(texts[side]) for texts in MESSAGES] for side in (0, 1))
        objects = {'Hardcore': self.on, 'Always': self.always, 'HC_Manager': vanilla[MANAGER], 'Hotkey': self._item(),
                   'SurvivalOff': self._message('SurvivalOff', SURVIVAL_OFF)}
        objects.update({name: self._message(name, text, buttons) for name, text, buttons in MENUS})
        values = {'Needs': ('objects', self.avs), 'Stages': ('objects', potions), 'Raised': ('objects', raised),
                  'Lowered': ('objects', lowered), 'Limbs': ('objects', self.limbs),
                  'SurvivalRules': ('objects', [vanilla[r] for r in SURVIVAL_RULES]),
                  'PerHour': ('floats', per_hour(self.export_dir)),
                  'Thresholds': ('floats', [float(t) for need in self.stages for t, _ in need]),
                  'SleepRestore': ('float', _setting(self.export_dir, *SLEEP_RESTORE))}
        vmad = quest_fragments('', [], scripts=[(SCRIPT, objects, values)])
        self.builder.writer.add_record('QUST', pack_script_quest(self.quest, 'FNV_Hardcore', vmad))
        self.builder.counts['Hardcore stages'] = len(potions)

    def _stage(self, need: int, index: int, spells: dict, effects, keyword: int) -> int:
        """The potion of need `need`'s stage `index`: its FNV spell's effects, each held to the stage's range."""
        (low, spell), (high, _) = self.stages[need][index:index + 2]
        rec = spells[spell]
        tests = range_tests(self.avs[need], low, high)
        pairs = b''.join(effect_pair(fid, value, area, LONG) + tests
                         for edid, magnitude, area, _, av, _, _ in fnv_effects(rec)
                         for fid, value in effects.targets(edid, av, magnitude))
        fid = self.builder.writer.derive_formid(SITE, rec['EditorID'])
        body = pack_string_subrecord('EDID', f'FNV_{rec["EditorID"]}') + pack_subrecord('OBND', bytes(12))
        body += pack_string_subrecord('FULL', rec.get('FULL', rec['EditorID'])) + R.pack_keywords([keyword])
        body += pack_subrecord('DATA', struct.pack('<f', 0.0))
        body += pack_subrecord('ENIT', struct.pack('<iIIfI', 0, NO_AUTO_CALC, 0, 0.0, 0)) + pairs
        self.builder.writer.add_record('ALCH', pack_fo4_record('ALCH', fid, 0, body))
        return fid

    def _message(self, name: str, text: str = None, buttons: list = ()) -> int:
        """Message `name` (a notification, a box with `buttons`), its text FNV's setting `name` unless given."""
        text = text or _setting(self.export_dir, name, DEFAULT_TEXT.get(name, name))
        fid = self.builder.writer.derive_formid(SITE, name)
        self.builder.writer.add_record('MESG', pack_mesg(fid, f'FNV_Hardcore{name[0].upper()}{name[1:]}', '', text,
                                                         int(bool(buttons)), list(buttons)))
        return fid

    def _item(self) -> int:
        """The Hardcore item and its effect (ITEM_SCRIPT gives it back and shows the switch)."""
        item, effect = (self.builder.writer.derive_formid(SITE, k) for k in ('FNV_HardcoreItem', 'item effect'))
        hotkey_effect(self.builder, effect, 'FNV_HardcoreItemEffect', ITEM_NAME,
                      object_scripts([(ITEM_SCRIPT, {'Manager': self.quest, 'Hotkey': item}, {})]))
        hotkey_item(self.builder, item, 'FNV_HardcoreItem', ITEM_NAME, effect)
        return item


def _vanilla(fo4: bytes, edids: set) -> dict:
    """{EditorID: FormID} of Fallout4.esm's quests, globals and keywords named in `edids`."""
    out = {}
    for rec, _ in walk(fo4, b'QUST', b'GLOB', b'KYWD'):
        edid = (dict(subrecords(rec.body)).get(b'EDID') or b'').rstrip(b'\0').decode()
        if edid in edids:
            out[edid] = rec.form_id
    return out
