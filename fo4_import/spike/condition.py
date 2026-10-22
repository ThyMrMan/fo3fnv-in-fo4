"""FO3/FNV weapon condition on Fallout 4: the records and data its scripts run on.

Condition is the engine's own item health, set through the FalloutCondition
F4SE plugin (TES4_Condition). Every converted weapon that wears (FNV DATA
Health, and not thrown or placed) gets our condition attach point and
keyword (`wire`). Eleven condition mods carry FNV's damage and value curves
by tenths, and the player script attaches them as condition changes. A
start-game quest's player alias runs TES4_ConditionPlayer on data read from
the source game:
- each weapon's FNV health;
- the wear per shot, `fDamageToWeaponValue`;
- the rounds whose ammo effect multiplies wear, by the keyword their ammo mod
  adds;
- the perks multiplying it (entry point Modify Item Damage).

A Repair hotkey item repairs the equipped weapon from a spare: the same
weapon, or an item of its FNV repair list (WEAP REPL). The plugin DLL ships
in the mod's F4SE\\Plugins.

See: docs/fork/fo4_condition.md#plan
"""

import shutil
import struct
from pathlib import Path

from fo4_import.base.install import source_esm
from fo4_import.base.support_records import pack_mesg
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.ammo_mods import (ATTACK_DAMAGE, CONDITION, MULTIPLY_OP, members, omod_data, scaled,
                                        with_point)
from fo4_import.spike.hotkey_items import hotkey_effect, hotkey_item
from fo4_import.spike.type_tests import with_keywords
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: derive_formid site (keys: quest, item, effect, keyword EditorIDs, 'tier <t>', messages, 'repair <FNV FLST>').
SITE = 'FNV condition'
SCRIPT, CALLS, NATIVES, ITEM_SCRIPT = ('TES4_ConditionPlayer', 'TES4_ConditionCalls', 'TES4_Condition',
                                       'TES4_ConditionRepairItem')
#: Our condition attach point (attach point keyword) and the keyword every converted weapon takes its mods by.
POINT_EDID, KEYWORD_EDID, ATTACH_POINT, MOD_ASSOCIATION = 'FNV_ap_Condition', 'FNV_ma_Condition', 2, 5
#: FNV weapon animation types that never wear: grenade throw, land mine, mine drop, thrown.
NO_WEAR = frozenset(range(10, 14))
#: FNV perk entry point Modify Item Damage and its Multiply Value function; the GMST of wear per shot.
MODIFY_ITEM_DAMAGE, MULTIPLY, WEAR_SETTING = 68, 3, 'fDamageToWeaponValue'
#: OMOD weapon property Value; the tenths condition is written in.
VALUE, TENTHS = 29, 10
#: The hotkey item's name, and the player script's messages: property, text (a %.0f takes the percent).
REPAIR_NAME = 'Repair Weapon'
MESSAGES = (('ConditionNote', 'Condition %.0f%%'), ('BrokenNote', 'This weapon is broken.'),
            ('RepairedNote', 'Repaired: condition %.0f%%'),
            ('NoSpareNote', 'No spare to repair this weapon with. Condition %.0f%%'))
#: The FalloutCondition plugin as built (tes_runtime/fo4_condition) and where a mod ships F4SE plugins.
PLUGIN = Path(__file__).resolve().parents[2] / 'tes_runtime' / 'dist' / 'FalloutCondition.dll'
PLUGIN_DIR = Path('F4SE') / 'Plugins'


def damage_factor(health: float) -> float:
    """FNV's weapon damage factor at `health` (0 to 1): whole from 75%, then less."""
    return 1.0 if health >= 0.75 else 1.0 - (0.75 - health) * 0.67


def value_factor(health: float) -> float:
    """FNV's item value at `health` (0 to 1): value * h^1.5."""
    return health ** 1.5


def tier_properties(tier: int) -> list:
    """The OMOD properties of condition tier `tier` (tenths; TENTHS is whole and has none), at its middle."""
    if tier >= TENTHS:
        return []
    middle = (tier + 0.5) / TENTHS
    props = [scaled(VALUE, MULTIPLY_OP, value_factor(middle))]
    if damage_factor(middle) < 1.0:
        props.append(scaled(ATTACK_DAMAGE, MULTIPLY_OP, damage_factor(middle)))
    return props


def wear_perks(perks: list) -> list:
    """[(FNV PERK FormID, multiplier)] of export `perks` multiplying item wear (Modify Item Damage), one per perk."""
    out = []
    for rec in perks:
        i = 0
        while f'Effect[{i}].Type' in rec:
            key = f'Effect[{i}]'
            entry, function = int(rec.get(f'{key}.EntryPoint', -1)), int(rec.get(f'{key}.Function', 0))
            if entry == MODIFY_ITEM_DAMAGE and function == MULTIPLY:
                out.append((int(rec['FormID'], 16), struct.unpack('<f', bytes.fromhex(rec[f'{key}.Value']))[0]))
                break
            i += 1
    return out


def repair_lists() -> dict:
    """{FNV WEAP FormID: its repair list's FLST FormID} (WEAP REPL), read from the source plugin."""
    out = {}
    for rec, _ in walk(source_esm(), b'WEAP'):
        repl = first_sub(rec.body, b'REPL')
        if repl:
            out[rec.form_id] = struct.unpack('<I', repl)[0]
    return out


class Condition:
    """Weapon condition through a cell builder: `wire` each converted weapon, then `write` the rest once."""

    def __init__(self, builder):
        """No weapon wired yet."""
        self.builder, self.weapons, self.point, self.keyword, self.tiers = builder, {}, None, None, set()

    def wire(self, fnv: int, fid: int, subs: list) -> list:
        """Converted weapon `subs` (FO4 `fid`, FNV WEAP `fnv`) taking condition mods; unchanged if it never wears."""
        rec = self.builder.items.records.get(fnv, (None, {}))[1]
        if float(rec.get('DATA.Health', 0) or 0) <= 0 or int(rec.get('DNAM.FalloutAnimType', -1)) in NO_WEAR:
            return subs
        self.weapons[fid] = (fnv, float(rec['DATA.Health']))
        return with_point(with_keywords(subs, [self._keyword()]), self._point())

    def write(self, ammo_mods, data_dir: Path, helper_index: int) -> None:
        """The condition quest, tiers, messages and Repair hotkey for the wired weapons, and the plugin DLL in
        `data_dir`; nothing without a wired weapon."""
        if not self.weapons:
            return
        writer = self.builder.writer
        quest, item, effect = (writer.derive_formid(SITE, key) for key in ('quest', 'item', 'effect'))
        notes = {name: self._message(name, text) for name, text in MESSAGES}
        weapons = sorted(self.weapons)
        lists = self._repair_lists(weapons)
        player = {'ConditionNote': notes['ConditionNote'], 'BrokenNote': notes['BrokenNote'], 'RepairHotkey': item}
        vmad = quest_fragments('', [], aliases=[(0, quest, [(SCRIPT, player, self._values(weapons, ammo_mods))])])
        writer.add_record('QUST', R.pack_qust(quest, 'FNV_Condition', '', 0, [], 'Player', 0x14, vmad))
        repair = {'Hotkey': item, 'Repair': actor_value_form('Repair', helper_index) or 0,
                  'RepairedNote': notes['RepairedNote'], 'NoSpareNote': notes['NoSpareNote']}
        hotkey_effect(self.builder, effect, 'FNV_ConditionRepairEffect', REPAIR_NAME, object_scripts(
            [(ITEM_SCRIPT, repair, {'Weapons': ('objects', weapons), 'RepairLists': ('objects', lists)})]))
        hotkey_item(self.builder, item, 'FNV_ConditionRepairHotkey', REPAIR_NAME, effect)
        self.builder.scripts.used += [SCRIPT, CALLS, NATIVES, ITEM_SCRIPT]
        self.builder.counts['condition weapons'] = len(weapons)
        (data_dir / PLUGIN_DIR).mkdir(parents=True, exist_ok=True)
        shutil.copy2(PLUGIN, data_dir / PLUGIN_DIR / PLUGIN.name)

    def _values(self, weapons: list, ammo_mods) -> dict:
        """TES4_ConditionPlayer's value properties for `weapons` (FO4 FormIDs, sorted)."""
        export = self.builder.export_dir
        perks = [(self.builder.perks.first.get(fnv), mult) for fnv, mult in wear_perks(export_records(export, 'PERK'))]
        perks = [(p, m) for p, m in perks if p]
        rounds = self._ammo_wear(ammo_mods)
        setting = next((float(r['DATA.Value']) for r in export_records(export, 'GMST')
                        if r.get('EditorID') == WEAR_SETTING), 0.2)
        return {'Weapons': ('objects', weapons), 'MaxHealth': ('floats', [self.weapons[w][1] for w in weapons]),
                'Tiers': ('objects', [self._tier(t) for t in range(TENTHS + 1)]), 'WearPerShot': ('float', setting),
                'AmmoMarks': ('objects', [k for k, _ in rounds]), 'AmmoWear': ('floats', [m for _, m in rounds]),
                'WearPerks': ('objects', [p for p, _ in perks]), 'WearPerkMults': ('floats', [m for _, m in perks])}

    def _ammo_wear(self, ammo_mods) -> list:
        """[(the keyword an ammo mod adds, the round's wear multiplier)] of the rounds with a condition effect."""
        out = []
        for ammo, keyword in sorted(ammo_mods.marks.items()):
            rec, i = ammo_mods.ammo.get(ammo, {}), 0
            while f'RCIL[{i}]' in rec:
                effect = ammo_mods.effects.get(int(rec[f'RCIL[{i}]'], 16), {})
                kind, op = int(effect.get('DATA.Type', -1)), int(effect.get('DATA.Operation', -1))
                if kind == CONDITION and op == MULTIPLY_OP:
                    out.append((keyword, float(effect['DATA.Value'])))
                i += 1
        return out

    def _repair_lists(self, weapons: list) -> list:
        """Each of `weapons`' repair list as our FLST of its converted items (0 without one), each written once."""
        repl, made = repair_lists(), {}
        lists = {int(r['FormID'], 16): r for r in export_records(self.builder.export_dir, 'FLST')}
        out = []
        for fid in weapons:
            source = repl.get(self.weapons[fid][0])
            if source in lists and source not in made:
                items = [i for i in (self.builder.items.item(m) for m in members(lists[source])) if i is not None]
                made[source] = self.builder.writer.derive_formid(SITE, f'repair {source:08X}') if items else 0
                if items:
                    self.builder.writer.add_record('FLST', R.pack_flst(
                        made[source], f'FNV_Repair_{lists[source]["EditorID"]}', items))
            out.append(made.get(source, 0))
        return out

    def _tier(self, tier: int) -> int:
        """Condition mod `tier` (tenths), written once."""
        fid = self.builder.writer.derive_formid(SITE, f'tier {tier}')
        if tier not in self.tiers:
            self.tiers.add(tier)
            body = pack_string_subrecord('EDID', f'FNV_mod_Condition{tier * 10:03d}')
            body += pack_string_subrecord('FULL', f'{tier * 10}% condition')
            body += pack_subrecord('DATA', omod_data(self._point(), tier_properties(tier)))
            self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', fid, 0, body + R.pack_u32('MNAM',
                                                                                                    self._keyword())))
        return fid

    def _message(self, name: str, text: str) -> int:
        """A notification message `text`, written now."""
        fid = self.builder.writer.derive_formid(SITE, name)
        self.builder.writer.add_record('MESG', pack_mesg(fid, f'FNV_Condition{name}', '', text, 0, []))
        return fid

    def _point(self) -> int:
        """Our condition attach point, written once."""
        if self.point is None:
            self.point = self._kywd(POINT_EDID, ATTACH_POINT, 'Condition')
        return self.point

    def _keyword(self) -> int:
        """The keyword wired weapons carry and condition mods target; written once."""
        if self.keyword is None:
            self.keyword = self._kywd(KEYWORD_EDID, MOD_ASSOCIATION)
        return self.keyword

    def _kywd(self, edid: str, kind: int, name: str = '') -> int:
        """A keyword `edid` of type `kind`, written now."""
        fid = self.builder.writer.derive_formid(SITE, edid)
        self.builder.writer.add_record('KYWD', R.pack_kywd(fid, edid, kind, name))
        return fid
