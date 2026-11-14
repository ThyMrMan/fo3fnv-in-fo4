"""FO3/FNV weapon and armor condition on Fallout 4: the records and data its scripts run on.

Condition is the engine's own item health, set through Cleanroom UI's
CleanroomUI.dll (CRUI_Condition). Every converted weapon that wears (FNV DATA
Health, and not thrown or placed) and every armor with FNV health gets our
condition attach point and keyword (`wire`, `wire_armor`). Condition mods
by tenths carry FNV's curves: eleven for weapons (damage, value), and for
armor eleven per armor rating (DT, value). A start-game quest's player alias
runs F3NV_ConditionPlayer on data read from the source game:
- each item's FNV health;
- the wear per shot, `fDamageToWeaponValue`, and per absorbed hit,
  `fDamageToArmorPercentage` up to `fMaxArmorRating`;
- the rounds whose ammo effect multiplies wear, by the keyword their ammo mod
  adds;
- the perks multiplying it (entry point Modify Item Damage).

Repair uses a spare: the same item, or an item of its FNV repair list
(REPL). The Repair hotkey item repairs the equipped weapon, else the most
worn armor piece; in the Pip-Boy, T (or its REPAIR hint) repairs the
highlighted item, whose item card shows its condition (CND, drawn by
Cleanroom UI's Pip-Boy movie). The DLLs ship in the mod's F4SE\\Plugins.

See: docs/fork/fo4_condition.md#armor
"""

import struct
from pathlib import Path

from fo4_import.app import runtime_dll
from fo4_import.base.install import source_walk
from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_mesg, pack_script_quest
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.ammo_mods import (ADD, ATTACK_DAMAGE, CONDITION, INT, MULTIPLY_OP, members, omod_data, prop,
                                        scaled, with_point)
from fo4_import.spike.hotkey_items import hotkey_effect, hotkey_item
from fo4_import.spike.type_tests import with_keywords
from tes5_import.base.tes5_reader import first_sub
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord
from tools.validate.fo4_install_check import PLUGINS

#: derive_formid site: quest, sources, plugin rows, item, effect, keywords, tiers, messages, 'repair <FLST>'.
SITE = 'FNV condition'
SCRIPT, CALLS, NATIVES, ITEM_SCRIPT = ('F3NV_ConditionPlayer', 'F3NV_ConditionCalls', 'CRUI_Condition',
                                       'F3NV_ConditionRepairItem')
#: Each plugin's rows (the game's on its condition quest, a DLC's on a quest of its own); see Condition.write.
SOURCE_SCRIPT = 'F3NV_ConditionSource'
#: The item-card line API for other mods (natives in Cleanroom UI's CleanroomUI.dll), shipped with the Pip-Boy work.
CARD_SCRIPT = 'CRUI_ItemCard'
#: Our condition attach point (attach point keyword) and the keyword every converted item takes its mods by.
POINT_EDID, KEYWORD_EDID, ATTACH_POINT, MOD_ASSOCIATION = 'FNV_ap_Condition', 'FNV_ma_Condition', 2, 5
#: FNV weapon animation types that never wear: grenade throw, land mine, mine drop, thrown.
NO_WEAR = frozenset(range(10, 14))
#: FNV perk entry point Modify Item Damage and its Multiply Value function.
MODIFY_ITEM_DAMAGE, MULTIPLY = 68, 3
#: FNV GMSTs (name, exe default): weapon and armor wear, the most armor absorbs (percent), vendor repair's cap and price.
SETTINGS = {'WearPerShot': ('fDamageToWeaponValue', 0.2), 'ArmorWear': ('fDamageToArmorPercentage', 0.35),
            'MaxAbsorb': ('fMaxArmorRating', 85.0), 'RepairSkillBase': ('fRepairSkillBase', 4.0),
            'RepairSkillMax': ('fRepairSkillMax', 9.0), 'RepairCostMult': ('fItemRepairCostMult', 1.0)}
#: FNV entry point Has Jury Rigging; WEAP DNAM offsets of Flags 1 and the skill; non-playable bits (WEAP, ARMO BMDT).
JURY_RIGGING, FLAGS1_AT, SKILL_AT, NON_PLAYABLE_WEAPON, NON_PLAYABLE_ARMOR = 48, 12, 104, 0x80, 0x40
#: FNV WEAP DNAM offsets of Flags 2 and the jam time; Flags 2's No Jam After Reload bit.
FLAGS2_AT, JAM_TIME_AT, NO_JAM_AFTER_RELOAD = 56, 96, 0x4
#: FNV's reload jam chance GMSTs (fWeaponConditionReloadJam1..10) and FalloutNV.exe's defaults for them.
RELOAD_JAM, RELOAD_JAM_DEFAULTS = 'fWeaponConditionReloadJam', (1.0, 0.75, 0.5, 0.25, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0)
#: Fallout4.esm's jam pieces: hand-interrupt and reload idles (first, third person), and the dry-fire sound.
JAM_FORMS = {'JamInterrupt1st': 0xF2496, 'JamInterrupt3rd': 0xF249C, 'JamReload1st': 0x4D33, 'JamReload3rd': 0xBDDA6,
             'DryFire': 0x1DACD}
#: BMDT heavy and medium armor bits; group bases keeping weapons and armor apart.
HEAVY, MEDIUM, WEAPON_GROUP, ARMOR_GROUP = 0x80, 0x08, 1_000_000, 2_000_000
#: OMOD weapon property Value, armor properties Value and Rating; the tenths condition is written in.
VALUE, ARMOR_VALUE, RATING, TENTHS = 29, 5, 6, 10
#: Fallout4.esm's DamageResist actor value.
DAMAGE_RESIST = 0x2E3
#: The hotkey item's name, and the player script's messages: property, text (a %.0f takes the percent).
REPAIR_NAME = 'Repair'
MESSAGES = (('ConditionNote', 'Condition %.0f%%'), ('BrokenNote', 'This weapon is broken.'))
#: The plugin's name before 2026-10-23, deleted on rebuild: both would load and hook the Pip-Boy twice.
LEGACY_PLUGIN = 'FalloutCondition.dll'


def damage_factor(health: float) -> float:
    """FNV's weapon damage factor at `health` (0 to 1): whole from 75%, then less."""
    return 1.0 if health >= 0.75 else 1.0 - (0.75 - health) * 0.67


def armor_factor(health: float) -> float:
    """FNV's armor DT and DR factor at `health` (0 to 1): whole from 50%, half at 0."""
    return 1.0 if health >= 0.5 else 1.0 - (0.5 - health)


def value_factor(health: float) -> float:
    """FNV's item value at `health` (0 to 1): value * h^1.5."""
    return health ** 1.5


def tier_properties(tier: int) -> list:
    """The weapon OMOD properties of condition tier `tier` (tenths; TENTHS is whole and has none), at its middle."""
    if tier >= TENTHS:
        return []
    middle = (tier + 0.5) / TENTHS
    props = [scaled(VALUE, MULTIPLY_OP, value_factor(middle))]
    if damage_factor(middle) < 1.0:
        props.append(scaled(ATTACK_DAMAGE, MULTIPLY_OP, damage_factor(middle)))
    return props


def armor_cut(tier: int, rating: int) -> int:
    """The rating tier `tier` takes off armor of `rating`, at the tier's middle."""
    if tier >= TENTHS:
        return 0
    return round(rating * (1.0 - armor_factor((tier + 0.5) / TENTHS)))


def armor_tier_properties(tier: int, rating: int) -> list:
    """The armor OMOD properties of condition tier `tier` on armor of `rating`: value, and rating below 50%."""
    if tier >= TENTHS:
        return []
    props = [scaled(ARMOR_VALUE, MULTIPLY_OP, value_factor((tier + 0.5) / TENTHS))]
    if armor_cut(tier, rating):
        props.append(prop(INT, ADD, RATING, struct.pack('<i', -armor_cut(tier, rating))))
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


def jam_times() -> dict:
    """{FNV WEAP FormID: its reload jam time in seconds (DNAM), or -1 with No Jam After Reload}, read from the
    source plugin. See: docs/fork/fo4_condition.md#jams"""
    out = {}
    for rec, _ in source_walk(b'WEAP'):
        dnam = first_sub(rec.body, b'DNAM') or b''
        if len(dnam) >= JAM_TIME_AT + 4:
            exempt = struct.unpack_from('<I', dnam, FLAGS2_AT)[0] & NO_JAM_AFTER_RELOAD
            out[rec.form_id] = -1.0 if exempt else struct.unpack_from('<f', dnam, JAM_TIME_AT)[0]
    return out


def jury_groups() -> dict:
    """{FNV WEAP or ARMO FormID: its Jury Rigging group}, read from the source plugin: a weapon's animation type
    and skill, an armor's weight class and equipment type, as FalloutNV.exe compares them; non-playable items
    have none. See: docs/fork/fo4_condition.md#jury-rigging"""
    out = {}
    for rec, _ in source_walk(b'WEAP', b'ARMO'):
        if rec.sig == b'WEAP':
            dnam = first_sub(rec.body, b'DNAM') or b''
            if len(dnam) >= SKILL_AT + 4 and not dnam[FLAGS1_AT] & NON_PLAYABLE_WEAPON:
                out[rec.form_id] = WEAPON_GROUP + struct.unpack_from('<I', dnam)[0] * 1000 + struct.unpack_from(
                    '<i', dnam, SKILL_AT)[0] + 1
            continue
        bmdt, etyp = first_sub(rec.body, b'BMDT') or b'', first_sub(rec.body, b'ETYP') or b''
        if len(bmdt) >= 5 and len(etyp) >= 4 and not bmdt[4] & NON_PLAYABLE_ARMOR:
            weight = 1 if bmdt[4] & HEAVY else 2 if bmdt[4] & MEDIUM else 0
            out[rec.form_id] = ARMOR_GROUP + weight * 1000 + struct.unpack('<i', etyp)[0] + 1
    return out


def jury_rigging_perks(perks: list) -> list:
    """The FNV PERK FormIDs of export `perks` with entry point Has Jury Rigging."""
    return [int(r['FormID'], 16) for r in perks
            if any(r.get(f'Effect[{i}].EntryPoint') == str(JURY_RIGGING) for i in range(8))]


def repair_lists() -> dict:
    """{FNV WEAP or ARMO FormID: its repair list's FLST FormID} (REPL), read from the source plugin."""
    out = {}
    for rec, _ in source_walk(b'WEAP', b'ARMO'):
        repl = first_sub(rec.body, b'REPL')
        if repl:
            out[rec.form_id] = struct.unpack('<I', repl)[0]
    return out


class Condition:
    """Item condition through a cell builder: `wire` each converted weapon and armor, then `write` the rest once."""

    def __init__(self, builder):
        """No item wired yet."""
        self.builder, self.weapons, self.armors, self.made = builder, {}, {}, {}
        self.point = self.keyword = None

    def wire(self, fnv: int, fid: int, subs: list) -> list:
        """Converted weapon `subs` (FO4 `fid`, FNV WEAP `fnv`) taking condition mods; unchanged if it never wears."""
        rec = self.builder.items.records.get(fnv, (None, {}))[1]
        if float(rec.get('DATA.Health', 0) or 0) <= 0 or int(rec.get('DNAM.FalloutAnimType', -1)) in NO_WEAR:
            return subs
        self.weapons[fid] = (fnv, float(rec['DATA.Health']))
        return with_point(with_keywords(subs, [self._keyword()]), self._point())

    def wire_armor(self, fnv: int, fid: int, subs: list, fields: dict) -> list:
        """Converted armor `subs` (FO4 `fid`, FNV ARMO `fnv` with `fields` health and rating) taking condition
        mods; unchanged without FNV health."""
        if fields.get('health', 0) <= 0:
            return subs
        self.armors[fid] = (fnv, float(fields['health']), round(fields['rating']))
        return with_point(with_keywords(subs, [self._keyword()]), self._point())

    def write(self, ammo_mods, data_dir: Path, helper_index: int) -> None:
        """The condition quest, tiers, messages and Repair hotkey for the wired items, and (the game build only)
        the plugin DLL in `data_dir`; a plugin whose master holds the quest writes only its own rows' quest
        (source_quest); nothing without a wired item.
        See: docs/fork/fo4_condition.md#sources
        """
        if not self.weapons and not self.armors:
            return
        writer, repair = self.builder.writer, actor_value_form('Repair', helper_index) or 0
        quest, sources = writer.derive_formid(SITE, 'quest'), writer.derive_formid(SITE, 'sources')
        self.builder.scripts.used += [SOURCE_SCRIPT, NATIVES]
        self.builder.counts['condition weapons'], self.builder.counts['condition armor'] = (len(self.weapons),
                                                                                             len(self.armors))
        if quest >> 24 != writer.own_index:
            self._source_quest(ammo_mods, sources, repair)
            return
        writer.add_record('FLST', R.pack_flst(sources, 'FNV_ConditionSources', []))
        item, effect = (writer.derive_formid(SITE, key) for key in ('item', 'effect'))
        player = {name: self._message(name, text) for name, text in MESSAGES}
        player.update(RepairHotkey=item, DamageResist=DAMAGE_RESIST, Repair=repair, Sources=sources, **JAM_FORMS)
        jury = [self.builder.perks.first.get(f) for f in jury_rigging_perks(export_records(self.builder.export_dir,
                                                                                            'PERK'))]
        player['JuryRigging'] = next((perk for perk in jury if perk), 0)
        rows = (SOURCE_SCRIPT, {'Repair': repair, 'Sources': sources}, self._rows(ammo_mods, lambda fid: True))
        vmad = quest_fragments('', [], aliases=[(0, quest, [(SCRIPT, player, self._values())])], scripts=[rows])
        writer.add_record('QUST', R.pack_qust(quest, 'FNV_Condition', '', 0, [], 'Player', 0x14, vmad))
        hotkey_effect(self.builder, effect, 'FNV_ConditionRepairEffect', REPAIR_NAME,
                      object_scripts([(ITEM_SCRIPT, {'Hotkey': item, 'Owner': quest}, {})]))
        hotkey_item(self.builder, item, 'FNV_ConditionRepairHotkey', REPAIR_NAME, effect)
        self.builder.scripts.used += [SCRIPT, CALLS, ITEM_SCRIPT, CARD_SCRIPT]
        if self.builder.built:
            return
        runtime_dll.install(data_dir)
        (data_dir / PLUGINS / LEGACY_PLUGIN).unlink(missing_ok=True)

    def _source_quest(self, ammo_mods, sources: int, repair: int) -> None:
        """A start-game quest of this plugin holding its own wired items' rows (F3NV_ConditionSource), which adds
        itself to the master's registry `sources` as it starts."""
        writer = self.builder.writer
        fid, own = writer.derive_formid(SITE, 'plugin rows'), writer.own_index
        rows = self._rows(ammo_mods, lambda form: form >> 24 == own)
        vmad = quest_fragments('', [], scripts=[(SOURCE_SCRIPT, {'Repair': repair, 'Sources': sources}, rows)])
        writer.add_record('QUST', pack_script_quest(fid, f'FNV_Condition_{plugin_stem(self.builder.export_dir)}', vmad))

    def _values(self) -> dict:
        """F3NV_ConditionPlayer's value properties: the game's wear settings, jam chances and weapon tiers."""
        wanted = {edid for edid, _ in SETTINGS.values()} | {f'{RELOAD_JAM}{i}' for i in range(1, 11)}
        gmst = {r['EditorID']: float(r['DATA.Value']) for r in export_records(self.builder.export_dir, 'GMST')
                if r.get('EditorID') in wanted}
        out = {name: ('float', gmst.get(edid, default)) for name, (edid, default) in SETTINGS.items()}
        out['MaxAbsorb'] = ('float', out['MaxAbsorb'][1] / 100.0)
        out['JamChances'] = ('floats', [gmst.get(f'{RELOAD_JAM}{i}', chance)
                                        for i, chance in enumerate(RELOAD_JAM_DEFAULTS, start=1)])
        out['Tiers'] = ('objects', [self._tier(t) for t in range(TENTHS + 1)])
        return out

    def _rows(self, ammo_mods, kept) -> dict:
        """F3NV_ConditionSource's rows for the wired items, rounds and perks `kept(FormID)` admits."""
        perks = [(self.builder.perks.first.get(fnv), mult)
                 for fnv, mult in wear_perks(export_records(self.builder.export_dir, 'PERK'))]
        perks = [(p, m) for p, m in perks if p and kept(p)]
        rounds = [(k, m) for k, m in self._ammo_wear(ammo_mods) if kept(k)]
        weapons, armors, jams = sorted(w for w in self.weapons if kept(w)), [a for a in self.armors if kept(a)], jam_times()
        out = {'Weapons': ('objects', weapons), 'MaxHealth': ('floats', [self.weapons[w][1] for w in weapons]),
               'JamTimes': ('floats', [jams.get(self.weapons[w][0], -1.0) for w in weapons]),
               'AmmoMarks': ('objects', [k for k, _ in rounds]), 'AmmoWear': ('floats', [m for _, m in rounds]),
               'WearPerks': ('objects', [p for p, _ in perks]), 'WearPerkMults': ('floats', [m for _, m in perks]),
               **self._armor_values(armors)}
        items, groups = weapons + sorted(armors), jury_groups()
        out['RepairLists'] = ('objects', self._repair_lists(items))
        out['JuryGroups'] = ('ints', [groups.get((self.weapons.get(i) or self.armors[i])[0], 0) for i in items])
        return out

    def _armor_values(self, kept: list) -> dict:
        """F3NV_ConditionSource's armor rows for armors `kept`: each one's health and tier group, the groups' tiers."""
        armors = sorted(kept)
        ratings = sorted({self.armors[a][2] for a in armors})
        tiers = [self._armor_tier(t, r) for r in ratings for t in range(TENTHS + 1)]
        return {'Armors': ('objects', armors), 'ArmorMax': ('floats', [self.armors[a][1] for a in armors]),
                'ArmorGroup': ('ints', [ratings.index(self.armors[a][2]) for a in armors]),
                'ArmorTiers': ('objects', tiers)}

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

    def _repair_lists(self, items: list) -> list:
        """Each of `items`' repair list as our FLST of its converted items (0 without one), each written once."""
        repl, made = repair_lists(), {}
        lists = {int(r['FormID'], 16): r for r in export_records(self.builder.export_dir, 'FLST')}
        out = []
        for fid in items:
            source = repl.get((self.weapons.get(fid) or self.armors[fid])[0])
            if source in lists and source not in made:
                found = [i for i in (self.builder.items.item(m) for m in members(lists[source])) if i is not None]
                made[source] = self.builder.writer.derive_formid(SITE, f'repair {source:08X}') if found else 0
                if found:
                    self.builder.writer.add_record('FLST', R.pack_flst(
                        made[source], f'FNV_Repair_{lists[source]["EditorID"]}', found))
            out.append(made.get(source, 0))
        return out

    def _tier(self, tier: int) -> int:
        """Weapon condition mod `tier` (tenths), written once."""
        return self._omod(f'tier {tier}', f'FNV_mod_Condition{tier * 10:03d}', f'{tier * 10}% condition',
                          omod_data(self._point(), tier_properties(tier)))

    def _armor_tier(self, tier: int, rating: int) -> int:
        """Armor condition mod `tier` (tenths) for armor of `rating`, written once; one that leaves the rating is
        shared by every rating."""
        cut = armor_cut(tier, rating)
        key, edid = f'armor tier {tier}', f'FNV_mod_ArmorCondition{tier * 10:03d}'
        if cut:
            key, edid = f'{key} rating {rating}', f'{edid}_DT{rating}'
        return self._omod(key, edid, f'{tier * 10}% condition',
                          omod_data(self._point(), armor_tier_properties(tier, rating), b'ARMO'))

    def _omod(self, key: str, edid: str, name: str, data: bytes) -> int:
        """Condition mod `edid` on DATA `data`, written once per `key`."""
        if key not in self.made:
            self.made[key] = fid = self.builder.writer.derive_formid(SITE, key)
            body = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', name)
            body += pack_subrecord('DATA', data) + R.pack_u32('MNAM', self._keyword())
            self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', fid, 0, body))
        return self.made[key]

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
        """The keyword wired items carry and condition mods target; written once."""
        if self.keyword is None:
            self.keyword = self._kywd(KEYWORD_EDID, MOD_ASSOCIATION)
        return self.keyword

    def _kywd(self, edid: str, kind: int, name: str = '') -> int:
        """A keyword `edid` of type `kind`, written now."""
        fid = self.builder.writer.derive_formid(SITE, edid)
        self.builder.writer.add_record('KYWD', R.pack_kywd(fid, edid, kind, name))
        return fid
