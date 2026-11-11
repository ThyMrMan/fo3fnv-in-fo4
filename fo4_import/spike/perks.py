"""FNV perks as FO4 PERK records, for the cell spike.

Each FNV perk keeps its FormID, name, description, level and requirements (its
conditions). A perk of several ranks becomes FO4's chain of one record per
rank (NNAM), as vanilla's QuickHands01/02; FNV applies only the current rank's
effects (Swift Learner x1.1, x1.2, x1.3), so an earlier rank's effects are off
once the next rank is held. An entry point maps by meaning (ENTRY_POINTS),
keeping FNV's function, value and condition tabs, or carries the vanilla perk
effect doing the same (VANILLA_EFFECTS); an ability becomes an FO4 ability of
constant effects; a quest stage stays one. What cannot convert is counted.

See: docs/fork/fo4_perks.md#records
"""

import re
import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.consumable_effects import AV_AT, Effects
from fo4_import.spike.say_topics import conditions_of
from fo4_import.spike.script import QUEST, prefix
from fo4_import.spike.teammates import Teammates, companion_gate
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: FNV entry point -> the FO4 entry point of the same meaning (fo4_perks.md#census).
ENTRY_POINTS = {0: 35, 1: 1, 2: 2, 4: 3, 6: 4, 8: 123, 9: 22, 11: 5, 12: 6, 23: 11, 25: 13, 31: 15, 32: 16, 34: 134,
                36: 17, 40: 79, 58: 37, 59: 103, 72: 100}
#: FNV DT perks on the attacker (58), whose function 1 is Subtract Value; FO4 Add Value; FNV Subtract Value.
IGNORED_DT, ADD_VALUE, SUBTRACT_VALUE = 58, 2, 1
#: FNV entry point on a stat -> (FO4 actor value, name or FormID; FO4 units per 1.0 of an FNV multiplier).
STAT_ENTRIES = {37: (0x2D3, 1.0), 39: (0x2D8, 6.0), 42: ('SpeedMult', 100.0), 44: (0x2E9, -100.0),
                56: ('DamageThreshold', 1.0)}
#: FNV entry point -> (Fallout4.esm perk, its entry point) whose effect does the same in FO4.
VANILLA_EFFECTS = {20: ('Hacker04', 127), 29: ('IronFist05', 155), 33: ('ConcentratedFire01', 109),
                   35: ('GrimReaperSprint01', 107)}
#: FO4 PRKE effect types, by the FNV export's names.
QUEST_STAGE, ABILITY, ENTRY_POINT = 0, 1, 2
EFFECT_TYPES = {'QuestStage': QUEST_STAGE, 'Ability': ABILITY, 'EntryPoint': ENTRY_POINT}
#: FNV's quest stage effect: the stage is the low byte, 0xCD fill above it (Scrounger 0xCD46: Generic's stage 70).
STAGE_MASK = 0xFF
#: FNV entry point parameter types FO4 reads alike (EPFT): none, a float, two floats.
VALUE_TYPES = (0, 1, 2)
#: Condition tabs of an entry point vanilla never uses: the perk owner's, which every one has.
OWNER_TABS = 1
#: Fallout4.esm's ability lending SPIT and ETYP; constant effects copied where vanilla lacks one (TEMPLATES).
SPELL_TEMPLATE, RAISE, LOWER, RESTORE = 'AbPerkQuickHands', 'AbFortifyStrength', 'AbReduceCarryWeight', 'abRestoreHealth'
#: The copied template by (lowers, recovers): raise, lower, and restore (raise per second, without Recover).
TEMPLATES = {(False, True): RAISE, (True, True): LOWER, (False, False): RESTORE}
#: Fallout4.esm's constant value effects by EditorID prefix (any case); FNV's and FO4's Recover, Detrimental flags.
CONSTANT_PREFIXES, RECOVER, DETRIMENTAL = ('abfortify', 'abreduce', 'abrestore'), 0x2, 0x4
#: Fallout4.esm's attack spell shape and touch effects (lowers; lowers and recovers), read for attack_spells.
ATTACK_TEMPLATES = ('PoisonRadscorpion', 'crPoisonEffect', 'StingwingPoisonEffectNPC')
#: FNV effect -> Fallout4.esm constant effect of the same archetype (Chameleon: vanilla's NPC cloak ability's).
CONSTANT_EFFECTS = {'StealthBoyInvis': 'AssaultronStealthEFFECT'}
#: FNV spell type Ability.
ABILITY_TYPE = 4
#: FNV condition tab captions whose subject is an item, not an actor (xEdit wbPERKCondition).
ITEM_CAPTIONS = frozenset({'Item', 'Weapon', 'Attacker Weapon'})
#: Perk DATA: trait, level, ranks, playable, hidden.
PERK_DATA = '<5B'
#: FO4 entry points gating the minigames' tiers (Set Player Gate Lockpick, Hacking) and the FNV skill each follows.
SKILL_GATES = ((62, 'Lockpick'), (98, 'Science'))
#: Skill opening FO4's Advanced, Expert and Master tiers: FNV's lock and terminal levels 50, 75 and 100.
GATE_SKILLS = (50.0, 75.0, 100.0)
#: Entry point function Set Value, its float parameter type (EPFT), and CTDA's greater-or-equal.
SET_VALUE, FLOAT_PARAM, AT_LEAST = 1, 1, 0x60
#: The critical chance entry point (FNV's and FO4's) and the Multiply Value function (folded by spike.criticals).
CRIT_CHANCE, MULTIPLY = 1, 3
#: The skill gates perk: its EditorID and FormID key, and DATA (no trait or level, one rank, unplayable, hidden).
GATES_EDID, GATES_KEY, GATES_DATA = 'FNV_SkillGates', 'PERK skill gates', struct.pack(PERK_DATA, 0, 0, 1, 0, 1)


class Perks:
    """The build's FO4 perks: `ids` hands out each FNV perk's rank records, `write` writes them all."""

    def __init__(self, builder, export_dir: Path, helper_index: int):
        """Perks of `export_dir`'s PERK records, drawing on Fallout4.esm's abilities and perks."""
        self.builder, self.helper_index = builder, helper_index
        self.records = export_records(export_dir, 'PERK')
        self.spells = {int(r['FormID'], 16): r for r in export_records(export_dir, 'SPEL')}
        self.spell_names = {fid: r.get('EditorID', '') for fid, r in self.spells.items()}
        self.abilities = {r['EditorID'].lower(): r for r in self.spells.values()
                          if r.get('EditorID') and int(r.get('SPIT.Type', 0) or 0) == ABILITY_TYPE}
        self.fnv_effects = {r['EditorID']: r for r in export_records(export_dir, 'MGEF') if r.get('EditorID')}
        self.ids = {int(r['FormID'], 16): self._rank_ids(r) for r in self.records}
        self.first = {fnv: ids[0] for fnv, ids in self.ids.items()}
        self.constants, self.tabs, self.vanilla, self.written, self.pending = {}, {}, {}, set(), set()
        #: [(FO4 perk rank, quest, stage, fragment script)] of every converted quest stage effect, for the rules.
        self.stage_effects = []
        self.quest_names = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'QUST')}
        self._index_vanilla()
        self.effects = Effects(builder, helper_index, self.vanilla)
        self.gates = builder.new_id(GATES_KEY, key=GATES_KEY)
        self.teammates = Teammates(builder, export_dir, self.records)

    def _rank_ids(self, rec: dict) -> list:
        """FO4 FormIDs of an FNV perk's ranks: FNV's own for the first."""
        later = [self.builder.new_id(f'PERK {rec["FormID"]} rank {r + 1}') for r in range(1, _ranks(rec))]
        return [self.builder.fnv_id(rec['FormID'])] + later

    def _index_vanilla(self) -> None:
        """Fallout4.esm's constant effects by (actor value, lowers, recovers), entry points' tab counts, and
        templates."""
        perks = {p for p, _ in VANILLA_EFFECTS.values()}
        for rec, _ in walk(self.builder.fo4, b'MGEF', b'PERK', b'SPEL'):
            subs = subrecords(rec.body)
            edid = dict(subs).get(b'EDID', b'').rstrip(b'\0').decode()
            if rec.sig == b'PERK':
                for block in effect_blocks(subs):
                    self.tabs[block[0][0]] = max(self.tabs.get(block[0][0], 0), block[0][2])
                if edid in perks:
                    self.vanilla[edid] = (rec.form_id, effect_blocks(subs))
            elif edid in (SPELL_TEMPLATE, *TEMPLATES.values(), *CONSTANT_EFFECTS.values(), *ATTACK_TEMPLATES):
                self.vanilla[edid] = (rec.form_id, dict(subs))
            if rec.sig == b'MGEF' and edid.lower().startswith(CONSTANT_PREFIXES):
                data = dict(subs)[b'DATA']
                key = (struct.unpack_from('<I', data, AV_AT)[0], bool(data[0] & DETRIMENTAL), bool(data[0] & RECOVER))
                self.constants.setdefault(key, rec.form_id)

    def traits(self) -> list:
        """The FO4 perks of FNV's playable traits."""
        return [self.ids[int(r['FormID'], 16)][0] for r in self.records
                if r.get('DATA.Trait') == '1' and r.get('DATA.Playable') == '1']

    def playable(self) -> list:
        """The first-rank FO4 perks a level-up offers (FNV's playable, shown perks; not traits), by level and name."""
        offered = [r for r in self.records if r.get('DATA.Playable') == '1' and r.get('DATA.Trait') != '1'
                   and r.get('DATA.Hidden') != '1']
        offered.sort(key=lambda r: (int(r.get('DATA.MinLevel', 0) or 0), r.get('FULL', '')))
        return [self.ids[int(r['FormID'], 16)][0] for r in offered]

    def form_map(self) -> dict:
        """{FNV perk FormID: first-rank FO4 perk}, held at any rank."""
        return self.first

    def named(self) -> dict:
        """{FNV perk EditorID: first-rank FO4 perk}, for scripts' Perk properties."""
        return {r['EditorID']: self.ids[int(r['FormID'], 16)][0] for r in self.records if r.get('EditorID')}

    def write(self, form_map: dict, script_vars: dict) -> None:
        """Write every perk's rank records; their conditions see `form_map` and `script_vars` (conditions_of)."""
        self.forms, self.script_vars = form_map, script_vars
        for rec in self.records:
            ids = self.ids[int(rec['FormID'], 16)]
            needs = conditions_of(rec, form_map, script_vars)
            if needs is None:
                self.builder.counts['perk requirements not converted'] += 1
            teammates = self.teammates.perks.get(int(rec['FormID'], 16))
            for rank, fid in enumerate(ids):
                after = ids[rank + 1] if rank + 1 < len(ids) else 0
                edid = f'FNV_{rec["EditorID"]}' + (f'_Rank{rank + 1}' if rank else '')
                effects = b'' if teammates else self._effects(rec, rank, after, edid)
                if not teammates:
                    self._stages(rec, rank, fid)
                self.builder.writer.add_record('PERK', pack_perk(fid, (edid, rec.get('FULL', ''), rec.get('DESC', '')),
                                                                 needs or b'', _data(rec, len(ids), bool(teammates)),
                                                                 after, effects))
                self.builder.counts['PERK'] += 1
            if teammates:
                self._companion_perk(rec, ids[0], teammates)
        self.builder.writer.add_record('PERK', pack_perk(self.gates, (GATES_EDID, '', ''), b'', GATES_DATA, 0,
                                                         gate_effects(self.helper_index)))
        for fnv in sorted(self.pending):
            self._ability(fnv, b'', '') or self._empty(fnv)

    def _stages(self, rec: dict, rank: int, fid: int) -> None:
        """Add rank `rank` (FO4 perk `fid`) of FNV perk `rec`'s quest stage effects on a built quest to
        stage_effects.
        See: docs/fork/fo4_pipeline.md#intense-training
        """
        for i in range(int(rec.get('EffectCount', 0) or 0)):
            key = f'Effect[{i}]'
            fnv = int(rec.get(f'{key}.Quest', '0'), 16)
            quest = self.forms.get(fnv)
            if rec.get(f'{key}.Type') == 'QuestStage' and int(rec.get(f'{key}.Rank', 0)) == rank and quest:
                stage = int(rec.get(f'{key}.Stage', 0)) & STAGE_MASK
                self.stage_effects.append((fid, quest, stage, f'{prefix(QUEST)}{self.quest_names.get(fnv, '')}'))

    def ability(self, fnv: int) -> 'int | None':
        """The FO4 ability of FNV spell `fnv` (an actor's), written with the perks (its conditions need their
        form map); a script-effect ability (the glowing one's glow) is ScriptEffects'; None, counted, when no
        effect has an FO4 counterpart."""
        spell = self.spells.get(fnv)
        if spell is None or not any(self.constant_target(spell, f'Effect[{j}]')
                                    for j in range(int(spell.get('EffectCount', 0) or 0))):
            scripted = spell and self.builder.scripts.effects.spell(spell['EditorID'])
            self.builder.counts['actor ability left out' if not scripted else 'actor ability (script effect)'] += 1
            return scripted or None
        self.pending.add(fnv)
        return self.builder.fnv_id(fnv)

    def named_ability(self, edid: str) -> 'int | None':
        """ability() of FNV ability `edid` (any case); None for another spell."""
        spell = self.abilities.get(edid.lower())
        return self.ability(int(spell['FormID'], 16)) if spell else None

    def _empty(self, fnv: int) -> None:
        """Ability `fnv` with no effect, as an actor names it but none of its effects' conditions convert."""
        spell = self.spells[fnv]
        self.builder.writer.add_record('SPEL', pack_spell(self.builder.fnv_id(fnv), f'FNV_{spell["EditorID"]}',
                                                          spell.get('FULL', ''), self.vanilla[SPELL_TEMPLATE][1], b''))
        self.builder.counts['actor ability with no effect'] += 1

    def _companion_perk(self, rec: dict, player_perk: int, teammates: tuple) -> None:
        """Write teammate perk `rec`'s companion perk (`teammates`: its FormID, holders): FNV's entry points, on while
        the holder is a teammate and the player holds `player_perk`; counted, not written, when it names no NPC.
        See: docs/fork/fo4_perks.md#teammate-perks
        """
        fid, holders = teammates
        if not holders:
            self.builder.counts['teammate perk naming no companion'] += 1
            return
        edid = f'FNV_{rec["EditorID"]}_Teammates'
        effects = self._effects(rec, 0, 0, edid, companion_gate(player_perk))
        self.builder.writer.add_record('PERK', pack_perk(fid, (edid, rec.get('FULL', ''), rec.get('DESC', '')), b'',
                                                         GATES_DATA, 0, effects))
        self.builder.counts['PERK (companion)'] += 1

    def _effects(self, rec: dict, rank: int, after: int, edid: str, gate: bytes = b'') -> bytes:
        """The packed effects of rank `rank` of FNV perk `rec`; off while perk `after` (its next rank) is held.
        With `gate` (a companion perk's conditions), only entry points, each gated by it on the owner tab."""
        off = (R.pack_ctda(0, 0.0, C.FO4.index('HasPerk'), after) if after else b'') + gate
        out, entry = [], 0
        for i in range(int(rec.get('EffectCount', 0) or 0)):
            key = f'Effect[{i}]'
            if int(rec.get(f'{key}.Rank', 0)) != rank:
                continue
            kind = EFFECT_TYPES.get(rec.get(f'{key}.Type'))
            kind = ABILITY if kind == ENTRY_POINT and int(rec.get(f'{key}.EntryPoint', -1)) in STAT_ENTRIES else kind
            if gate and kind != ENTRY_POINT:
                self.builder.counts['companion perk effect left out (not an entry point)'] += 1
                continue
            made = self._effect(rec, key, kind, off, f'{edid} {i}')
            for data, tabs, params in [] if made is None else made if isinstance(made, list) else [made]:
                if kind == ENTRY_POINT:
                    tabs = {**tabs, 0: off + tabs.get(0, b'')} if off else tabs
                    params, entry = _with_entry_id(params, entry), entry + 1
                out.append((int(rec.get(f'{key}.Priority', 0)), kind, pack_effect(kind, data, tabs, params)))
        return b''.join(e for _, _, e in sorted(out, key=lambda e: e[:2]))

    def _effect(self, rec: dict, key: str, kind: int, off: bytes, owner: str) -> 'tuple | None':
        """(DATA, {tab: conditions}, parameters) of one FNV perk effect, or a list of them (a folded critical
        chance multiplier); None, counted, when it cannot convert."""
        if kind == QUEST_STAGE:
            quest = self.forms.get(int(rec.get(f'{key}.Quest', '0'), 16))
            if quest is None:
                self.builder.counts['perk effect left out (quest not built)'] += 1
                return None
            return struct.pack('<IH', quest, int(rec.get(f'{key}.Stage', 0)) & STAGE_MASK), {}, []
        if kind == ABILITY:
            spell = (self._stat_ability(rec, key, off, owner) if f'{key}.EntryPoint' in rec
                     else self._ability(int(rec.get(f'{key}.Ability', '0'), 16), off, owner))
            return None if spell is None else (struct.pack('<I', spell), {}, [])
        return self._entry_point(rec, key)

    def _stat_ability(self, rec: dict, key: str, off: bytes, owner: str) -> 'int | None':
        """An FNV entry point on one of the actor's stats (STAT_ENTRIES) as an ability: a spell of one constant
        effect on its FO4 actor value (Add Value as is, Multiply Value m as (m - 1) x its units), under the effect's
        owner conditions and `off`; None, counted, when it tests another tab or a condition cannot convert.
        See: docs/fork/fo4_perks.md#stat-abilities
        """
        name, units = STAT_ENTRIES[int(rec[f'{key}.EntryPoint'])]
        function, tabs = int(rec[f'{key}.Function']), _tabs(rec, key)
        conds = conditions_of(tabs.get(0, {}), self.forms, self.script_vars) if tabs.get(0) else b''
        if conds is None or function not in (ADD_VALUE, MULTIPLY) or any(raws for t, raws in tabs.items() if t):
            self.builder.counts['perk effect left out (stat entry: another tab or condition)'] += 1
            return None
        value = struct.unpack('<f', bytes.fromhex(rec[f'{key}.Value']))[0]
        magnitude = value if function == ADD_VALUE else units * (value - 1.0)
        effect = self._vanilla_raise(name) if isinstance(name, int) else self.raising(name)
        if not effect:
            self.builder.counts['perk effect left out (stat entry: no FO4 effect)'] += 1
            return None
        fid = self.builder.new_id(f'SPEL {owner} stat')
        pair = pack_subrecord('EFID', struct.pack('<I', effect))
        pair += pack_subrecord('EFIT', struct.pack('<fII', magnitude, 0, 0))
        self.builder.writer.add_record('SPEL', pack_spell(fid, f'FNV_{owner.split()[0]}Stat{owner.split()[-1]}', '',
                                                          self.vanilla[SPELL_TEMPLATE][1], pair + off + conds))
        self.builder.counts['SPEL (perk stat ability)'] += 1
        return fid

    def _vanilla_raise(self, fo4_av: int) -> 'int | None':
        """Fallout4.esm's effect raising AV form `fo4_av` (recovering first), or None."""
        return self.constants.get((fo4_av, False, True)) or self.constants.get((fo4_av, False, False))

    def raising(self, name: str) -> int:
        """The effect raising actor value `name`: vanilla's, else a RAISE copy."""
        return (self._vanilla_raise(actor_value_form(name, self.helper_index))
                or self.effects.copy(RAISE, name, 'copy', f'{RAISE} {name}', f'FNV_{RAISE}_{name}'))

    def _entry_point(self, rec: dict, key: str) -> 'tuple | None':
        """An FNV entry-point effect on FO4's (ENTRY_POINTS) or vanilla's (VANILLA_EFFECTS), a critical chance
        multiplier as additions (spike.criticals); None, counted, when FO4 has neither, a condition cannot convert
        or it tests a tab FO4's entry point lacks."""
        ep, value_type = int(rec[f'{key}.EntryPoint']), int(rec.get(f'{key}.ValueType', 0))
        if ep in VANILLA_EFFECTS:
            perk, fo4 = VANILLA_EFFECTS[ep]
            return next(b for b in self.vanilla[perk][1] if b[0][0] == fo4)
        if ep not in ENTRY_POINTS or value_type not in VALUE_TYPES:
            self.builder.counts[f'perk effect left out (FNV entry point {ep})'] += 1
            return None
        fo4, tabs = ENTRY_POINTS[ep], {}
        count = self.tabs.get(ENTRY_POINTS[ep], OWNER_TABS)
        items = FNV_ITEM_TABS.get(ep, frozenset())
        for tab, raws in _tabs(rec, key).items():
            conds = None if tab >= count else conditions_of(raws, self.forms, self.script_vars, item=tab in items)
            if conds is None:
                self.builder.counts['perk effect left out (' + ('condition)' if tab < count else 'tab FO4 lacks)')] += 1
                return None
            tabs[tab] = conds
        value = bytes.fromhex(rec.get(f'{key}.Value', ''))
        function = int(rec[f'{key}.Function'])
        if ep == CRIT_CHANCE and function == MULTIPLY and value_type == FLOAT_PARAM:
            return self.builder.criticals.folded(tabs, struct.unpack('<f', value)[0])
        if ep == IGNORED_DT and function == SUBTRACT_VALUE and value_type == FLOAT_PARAM:
            function, value = ADD_VALUE, struct.pack('<f', -struct.unpack('<f', value)[0])
        params = [(b'EPFT', bytes([value_type]))] + ([(b'EPFD', value)] if value_type else [])
        return bytes([fo4, function, count]), tabs, params

    def _ability(self, fnv: int, off: bytes, owner: str) -> 'int | None':
        """The FO4 ability of FNV spell `fnv`, its effects off when `off` holds (an earlier rank's); None, counted,
        when none of its effects converts."""
        spell = self.spells.get(fnv)
        if spell is None:
            self.builder.counts['perk effect left out (no ability)'] += 1
            return None
        fid = self.builder.fnv_id(fnv) if not off else self.builder.new_id(f'SPEL {owner}')
        if fid in self.written:
            return fid
        effects = b''
        for j in range(int(spell.get('EffectCount', 0) or 0)):
            made = self.constant_effect(spell, f'Effect[{j}]')
            if made is None:
                self.builder.counts[f'ability effect left out ({spell.get(f"Effect[{j}].EFID")})'] += 1
                continue
            effects += made[0] + off + made[1]
        if not effects:
            return None
        self.written.add(fid)
        template = self.vanilla[SPELL_TEMPLATE][1]
        edid = f'FNV_{spell["EditorID"]}' + ('_' + owner.split()[0] if off else '')
        self.builder.writer.add_record('SPEL', pack_spell(fid, edid, spell.get('FULL', ''), template, effects))
        self.builder.counts['SPEL (perk ability)'] += 1
        return fid

    def constant_effect(self, spell: dict, key: str) -> 'tuple | None':
        """(EFID and EFIT, conditions) of an FNV ability effect on an FO4 constant effect; None when it cannot."""
        raws = {f'Condition[{c}].Raw': spell[f'{key}.Condition[{c}].Raw']
                for c in range(int(spell.get(f'{key}.ConditionCount', 0) or 0))}
        conds = conditions_of(raws, self.forms, self.script_vars)
        effect = self.constant_target(spell, key)
        if effect is None or conds is None:
            return None
        fit = struct.pack('<fII', float(spell[f'{key}.Magnitude']), int(spell.get(f'{key}.Area', 0)),
                          int(spell.get(f'{key}.Duration', 0)))
        return pack_subrecord('EFID', struct.pack('<I', effect)) + pack_subrecord('EFIT', fit), conds

    def constant_target(self, spell: dict, key: str) -> 'int | None':
        """The FO4 constant effect of FNV ability effect `key`: vanilla's on its actor value that lowers and
        recovers as FNV's does, else a copy of that kind's template; None without either. An effect FO4 has by
        archetype, not actor value, is CONSTANT_EFFECTS'."""
        if spell[f'{key}.EFID'] in CONSTANT_EFFECTS:
            return self.vanilla[CONSTANT_EFFECTS[spell[f'{key}.EFID']]][0]
        av = int(spell.get(f'{key}.ActorValue', -1))
        name = C.fnv_av_name(av) if 0 <= av < len(C.FNV_AV_NAMES) else ''
        fo4_av = actor_value_form(name, self.helper_index) if name else None
        flags = int(self.fnv_effects.get(spell[f'{key}.EFID'], {}).get('DATA.Flags', 0))
        kind = (bool(flags & DETRIMENTAL), bool(flags & RECOVER))
        if fo4_av is None or (fo4_av, *kind) in self.constants:
            return self.constants.get((fo4_av, *kind))
        template = TEMPLATES.get(kind)
        return self.effects.copy(template, name, 'copy', f'{template} {name}',
                                 f'FNV_{template}_{name}') if template else None


def fnv_item_tabs(defs: str) -> dict:
    """{FNV entry point: its tabs whose subject is an item} from xEdit's FNV definitions `defs`."""
    kinds = re.search(r'TPERKEntryPointConditionType = \((.*?)\);', defs, re.S).group(1).replace(',', ' ').split()
    rows = re.search(r'wbPERKCondition : array.*?= \((.*?)\n  \);', defs, re.S).group(1)
    captions = [re.findall(r"Caption\d: '([^']*)'", row) for row in rows.splitlines() if 'Count:' in row]
    table = re.search(r'wbPERKEntryPoints : array.*?= \((.*?)\n  \);', defs, re.S).group(1)
    points = [m.group(1) or 'epcDefault' for m in re.finditer(r"Name: '[^']*'(?:; Condition: (epc\w+))?", table)]
    return {ep: frozenset(i for i, c in enumerate(captions[kinds.index(kind)]) if c in ITEM_CAPTIONS)
            for ep, kind in enumerate(points)}


#: {FNV entry point: tabs whose subject is an item} (fnv_item_tabs).
FNV_ITEM_TABS = fnv_item_tabs(C.FNV_DEFS.read_text(errors='replace'))


def _ranks(rec: dict) -> int:
    """How many ranks an FNV perk has (at least one)."""
    return max(1, int(rec.get('DATA.Ranks', 1) or 1))


def _data(rec: dict, ranks: int, hidden: bool = False) -> bytes:
    """FO4 perk DATA of FNV perk `rec`, its chain `ranks` long; `hidden` for a teammate perk's player switch.
    See: docs/fork/fo4_perks.md#teammate-perks
    """
    flags = (int(rec.get(f'DATA.{k}', 0) or 0) for k in ('Trait', 'MinLevel'))
    return struct.pack(PERK_DATA, *flags, ranks, int(rec.get('DATA.Playable', 0) or 0),
                       int(hidden or rec.get('DATA.Hidden', 0) or 0))


def _tabs(rec: dict, key: str) -> dict:
    """{tab: {'Condition[j].Raw': raw}} of an FNV perk effect's condition tabs."""
    out, k = {}, 0
    while f'{key}.Tab[{k}].RunOn' in rec:
        tab, j, raws = int(rec[f'{key}.Tab[{k}].RunOn']), 0, {}
        while f'{key}.Tab[{k}].Condition[{j}].Raw' in rec:
            raws[f'Condition[{j}].Raw'] = rec[f'{key}.Tab[{k}].Condition[{j}].Raw']
            j += 1
        out[tab], k = raws, k + 1
    return out


def _with_entry_id(params: list, entry: int) -> list:
    """`params` with EPFB `entry` (unique in its perk) after EPFT."""
    rest = [p for p in params if p[0] not in (b'EPFT', b'EPFB')]
    return [p for p in params if p[0] == b'EPFT'] + [(b'EPFB', struct.pack('<H', entry))] + rest


def effect_blocks(subs: list) -> list:
    """[(DATA, {tab: conditions}, [(tag, data)] parameters)] of a Fallout4.esm perk's entry-point effects."""
    out, tab, block = [], 0, None
    for tag, data in subs:
        if tag == b'PRKE':
            block = [b'', {}, []] if data[0] == ENTRY_POINT else None
            continue
        if block is None:
            continue
        if tag == b'PRKF':
            out.append(tuple(block))
            block = None
        elif tag == b'PRKC':
            tab = struct.unpack('<b', data)[0]
            block[1][tab] = b''
        else:
            _add_part(block, tab, tag, data)
    return out


def _add_part(block: list, tab: int, tag: bytes, data: bytes) -> None:
    """Add subrecord `tag` to an effect_blocks block: its DATA, a condition of tab `tab`, or a parameter."""
    if tag == b'DATA':
        block[0] = data
    elif tag in (b'CTDA', b'CIS1', b'CIS2'):
        block[1][tab] += pack_subrecord(tag.decode(), data)
    else:
        block[2].append((tag, data))


def gate_effects(helper_index: int) -> bytes:
    """The skill gates perk's effects: each gate entry point set to 1, 2 and 3 at its skill's GATE_SKILLS, the
    higher tier at a higher priority so it applies last.

    See: docs/fork/fo4_perks.md#skill-gates
    """
    gates = [(entry, skill, tier, level) for entry, skill in SKILL_GATES for tier, level in enumerate(GATE_SKILLS, 1)]
    out = b''
    for n, (entry, skill, tier, level) in enumerate(gates):
        ctda = R.pack_ctda(AT_LEAST, level, C.FO4.index('GetValue'), actor_value_form(skill, helper_index))
        params = [(b'EPFT', bytes([FLOAT_PARAM])), (b'EPFB', struct.pack('<H', n)), (b'EPFD', struct.pack('<f', tier))]
        out += pack_effect(ENTRY_POINT, bytes([entry, SET_VALUE, OWNER_TABS]), {0: ctda}, params, tier)
    return out


def pack_effect(kind: int, data: bytes, tabs: dict, params: list, priority: int = 0) -> bytes:
    """One FO4 perk effect: PRKE (rank 0, the chain holding ranks; `priority`), DATA, its tabs, parameters and end
    marker."""
    out = pack_subrecord('PRKE', bytes([kind, 0, priority])) + pack_subrecord('DATA', data)
    for tab in sorted(tabs):
        out += pack_subrecord('PRKC', struct.pack('<b', tab)) + tabs[tab]
    return out + b''.join(pack_subrecord(t.decode(), d) for t, d in params) + pack_subrecord('PRKF', b'')


def pack_perk(fid: int, text: tuple, conditions: bytes, data: bytes, next_perk: int, effects: bytes) -> bytes:
    """An FO4 perk: `text` (EditorID, name, description), requirement `conditions`, DATA, the next rank, effects."""
    edid, name, desc = text
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', name) + pack_string_subrecord('DESC', desc) + conditions
    subs += pack_subrecord('DATA', data) + (pack_subrecord('NNAM', struct.pack('<I', next_perk)) if next_perk else b'')
    return pack_fo4_record('PERK', fid, 0, subs + effects)


def pack_spell(fid: int, edid: str, name: str, template: dict, effects: bytes) -> bytes:
    """An FO4 ability of `effects`, with `template`'s equip type and SPIT."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('OBND', bytes(12)) + pack_string_subrecord('FULL', name)
    subs += pack_subrecord('ETYP', template[b'ETYP']) + pack_string_subrecord('DESC', '') + pack_subrecord('SPIT', template[b'SPIT'])
    return pack_fo4_record('SPEL', fid, 0, subs + effects)
