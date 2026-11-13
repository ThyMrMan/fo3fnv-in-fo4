"""Converted FNV scripts attached to the cell spike's records, their properties filled from the cell.

A record's FNV script (its SCRI) becomes its conversion (`papyrus_script_name`)
by VMAD. A property is filled when the spike has the form: a reference,
actor or quest of the cell named as the property (FNV EditorIDs), the
player, a helper quest or global (FalloutHelpers.esl), the FNV item it names
through the cell's item converter (its conversion or FO4 stand-in), else a
Fallout4.esm misc item or potion of the same name, or the FNV message it
names (converted once), the FNV spell of script effects it names
(script_effects.py), the FNV global it names (globals.py), or a dialogue
global it sets (an AddTopic unlock or a Follow Up mark, made once, its FormID
hashed from its name). Same-named
Fallout4.esm forms are not used otherwise.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import re
from pathlib import Path

from fo4_import.base.support_records import pack_global, pack_mesg
from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.condition_forms import condition_forms
from fo4_import.spike.controls import fo4_controls
from fo4_import.spike.quest import QVAR_SITE, objective_key
from fo4_import.spike.readables import Readables
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.say_topics import blocker, conditions_of, conditions_under, never_true, settled_by
from script_convert.quest_var_mirrors import PREFIX as QVAR_PREFIX
from fo4_import.spike.script import base_forms, declared_properties, fill, prefix
from fo4_import.spike.script_effects import ScriptEffects
from fo4_import.spike.type_tests import CREATURE_TYPE_PREFIX
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.writer import pack_string_subrecord
from tes5_import.record_types.crime_falloutnv import ENEMY_LIST_EDID
from script_convert.constants import (FALLOUT4_CHAT_PREFIX, FALLOUT4_POSE_PREFIX, FALLOUT4_SCREEN_PREFIX,
                                      FALLOUT4_SWAP_PREFIX, FALLOUT4_TALK_PREFIX, TALKING_LISTS_PROPERTY,
                                      papyrus_script_name)

#: The player reference, which converted scripts name `Player`.
PLAYER = ('Player', 0x14)
#: MESG DNAM Message Box, the one flag FNV and FO4 share (FNV bit 1 is Auto Display, FO4's Delay Initial Display).
MESSAGE_BOX = 0x1
#: A message button's test that never passes: the player is not the player's base (FO4 Player 0x7).
NEVER_SHOWN = R.pack_ctda(0, 0.0, C.FO4.index('GetIsID'), 0x7, run_on=R.RUN_REFERENCE, ref=C.PLAYER_REF)
#: Name prefixes of the dialogue globals converted lines set: AddTopic unlocks and Follow Up marks.
DIALOGUE_GLOBALS = ('TES4Unlock_', 'TES4FollowUpFrom_', 'TES4FollowUpSaid_')
#: derive_formid site of the dialogue globals (key: the global's name).
GLOBAL_SITE = 'FNV dialogue GLOB'
#: The FormList the polyfill's SetDestroyed mirrors destroyed references into (converter._destroyed_formlist).
DESTROYED_LIST = 'TES4DestroyedRefs'
#: Name prefix of an effect family keyword property (script_convert.constants.mgef_family_keyword_name).
FAMILY_PREFIX = 'TES4FX_'
#: The FormLists scripts fill at run time, written empty: destroyed references, factions the player is an enemy of.
RUNTIME_LISTS = (DESTROYED_LIST, ENEMY_LIST_EDID)
#: Mirror global name prefix of an objective state, and its parts: state, quest EditorID, objective index.
OBJECTIVE_PREFIX = 'TES4Obj'
OBJECTIVE_GLOBAL = re.compile(r'TES4Obj(Done|Shown)_(.+)_(\d+)$')
#: Papyrus types of the item properties the cell's item converter fills by FNV name.
ITEM_TYPES = frozenset({'Potion', 'MiscObject', 'LeveledItem', 'Weapon', 'Armor', 'Ammo', 'Book', 'Key'})
#: Papyrus types of placed bases a property may name by its FNV EditorID (VMS21NeroCouchScript's own couch).
BASE_TYPES = frozenset({'Form', 'Activator', 'Furniture', 'Door', 'Light', 'Static', 'MovableStatic'})
#: Papyrus type -> (builder attribute, its method) that makes or finds a property's form from the property name.
NAMED_MAKERS = {'ImageSpaceModifier': ('imods', 'modifier'), 'Package': ('packages', 'named'),
                'Idle': ('idles', 'named'), 'EffectShader': ('effect_shaders', 'of'), 'Sound': ('sounds', 'named')}

#: (Papyrus type, name prefix) -> the ObjectScripts method making such a property's form.
PREFIXED_MAKERS = {('MatSwap', FALLOUT4_SWAP_PREFIX): '_swap', ('Armor', FALLOUT4_SCREEN_PREFIX): '_screen',
                   ('ObjectReference', FALLOUT4_POSE_PREFIX): '_pose', ('Keyword', FAMILY_PREFIX): '_family',
                   ('Keyword', CREATURE_TYPE_PREFIX): '_type_keyword'}
#: Papyrus type -> the ObjectScripts method making a property of that type by its name.
TYPED_MAKERS = {'GlobalVariable': '_global_form', 'FormList': '_list_form', 'Spell': '_spell_form',
                'ActorBase': 'actor_base'}


class NameMap(dict):
    """A dict of form names that also keeps `lower`: {lower-case name: the value of the last name, in insertion
    order, spelled that way ignoring case}, kept as names are set (a rebuild per lookup cost minutes).
    See: docs/fork/fo4_plugin_layout.md#stage-times
    """

    def __init__(self, *args):
        """As dict(*args)."""
        super().__init__()
        self.spellings, self.lower = {}, {}
        self.update(*args)

    def __setitem__(self, key, value):
        """Set `key`, then its lower-case entry from the last spelling of it."""
        new = key not in self
        super().__setitem__(key, value)
        spellings = self.spellings.setdefault(key.lower(), [])
        spellings += [key] if new else []
        self.lower[key.lower()] = dict.__getitem__(self, spellings[-1])

    def update(self, *args, **kwargs):
        """Set each pair through __setitem__, in order."""
        for key, value in dict(*args, **kwargs).items():
            self[key] = value


def _kept(_cond: dict) -> None:
    """No test settled up front: each converts or blocks."""
    return None


class ObjectScripts:
    """Converted scripts for the cell's records; `used` lists those attached, `named` the cell's forms by FNV name."""

    def __init__(self, builder, export_dir: Path, scripts_dir: 'Path | None', helper_index: int):
        """Scripts from the converted `scripts_dir` (None: none attached); helpers at master `helper_index`."""
        self.builder, self.dir, self.helper_index, self.used = builder, scripts_dir, helper_index, []
        self.names = {int(r['FormID'], 16): r['EditorID'] for r in export_records(export_dir, 'SCPT')}
        self.messages = {r.get('EditorID'): r for r in export_records(export_dir, 'MESG')}
        self.global_names = {r['EditorID']: int(r['FormID'], 16) for r in export_records(export_dir, 'GLOB')
                             if r.get('EditorID')}
        self.forms, self.made_messages, self.globals = base_forms(helper_index), {}, {}
        self.gated_messages, self.gate_forms = [], None
        self.effects = ScriptEffects(builder, export_dir)
        self.named, self.talks = NameMap([PLAYER]), {}
        self.quest_ids = {r['EditorID'].lower(): r['FormID'] for r in export_records(export_dir, 'QUST')
                          if r.get('EditorID')}
        self.export_dir, self.actor_bases, self.base_names = export_dir, None, None

    def name(self, scpt: int) -> 'str | None':
        """The converted script of FNV script `scpt`; None when it was not converted."""
        name = papyrus_script_name(self.names.get(scpt, ''), prefix())
        return name if self.dir and (self.dir / f'{name}.psc').exists() else None

    def properties(self, script: str, only: 'set | None' = None) -> dict:
        """{property: FormID} of converted `script`'s properties the spike can fill (those named in `only`).

        A `TES4Talk_<topic>` scene gets its FormID here, kept in `talks` for the conversation builder;
        material swaps, imagespace modifiers and poses are made on demand (_made). A name matches the build's
        forms ignoring case, as FNV's script names do (SunnyREF is the reference SunnyRef).
        """
        declared = [(kind, prop) for kind, prop in declared_properties(
            (self.dir / f'{script}.psc').read_text(encoding='utf-8')) if only is None or prop in only]
        messages = {prop: self.message(prop) for kind, prop in declared if kind == 'Message' and prop in self.messages}
        props = fill(declared, {**self.forms, 'Message': messages}, self.helper_index)
        talks = {prop: self.talk(prop) for kind, prop in declared
                 if kind == 'Scene' and prop.startswith((FALLOUT4_TALK_PREFIX, FALLOUT4_CHAT_PREFIX))}
        made, named = {prop: self._made(kind, prop) for kind, prop in declared}, self.named_lower()
        return {**props, **talks, **{p: f for p, f in made.items() if f},
                **{prop: named[prop.lower()] for _, prop in declared if prop.lower() in named}}

    def named_lower(self) -> dict:
        """`named` keyed by lower-case name (NameMap.lower; read only)."""
        return self.named.lower

    def _made(self, kind: str, prop: str) -> 'int | None':
        """A property's form the spike converts on demand (PREFIXED_MAKERS, TYPED_MAKERS, NAMED_MAKERS); else a
        Form-typed or item property's item (a note: paper or holotape)."""
        maker = next((m for (k, prefix), m in PREFIXED_MAKERS.items() if k == kind and prop.startswith(prefix)),
                     None) or TYPED_MAKERS.get(kind)
        if maker:
            return getattr(self, maker)(prop)
        if kind in NAMED_MAKERS:
            owner, maker = NAMED_MAKERS[kind]
            return getattr(getattr(self.builder, owner), maker)(prop)
        item = self.builder.items.by_name(prop) if kind in ITEM_TYPES or kind == 'Form' else None
        return item or (self._base(prop) if kind in BASE_TYPES else None)

    def _base(self, prop: str) -> 'int | None':
        """The FO4 base of the FNV placed base whose EditorID is `prop` (any case), made if need be (CellBuilder.base).
        See: docs/fork/fo4_pipeline.md#base-properties
        """
        if self.base_names is None:
            self.base_names = {rec['EditorID'].lower(): fid for fid, (_sig, rec) in self.builder.bases.items()
                               if rec.get('EditorID')}
        fid = self.base_names.get(prop.lower())
        if fid is None:
            return None
        self.builder.counts['base made for a script property'] += fid not in self.builder.made
        return self.builder.base(fid)

    def _swap(self, prop: str) -> int:
        """A `TES4Swap_` material swap (swaps.Swaps)."""
        return self.builder.swaps.swap(prop)

    def _screen(self, prop: str) -> 'int | None':
        """A `TES4Screen_<race>_<name>` screen armor (creatures.screen_armor)."""
        return self.builder.creatures.screen_armor(*prop[len(FALLOUT4_SCREEN_PREFIX):].rsplit('_', 1))

    def _pose(self, prop: str) -> 'int | None':
        """A `TES4Pose_` player seat (poses.Poses)."""
        return self.builder.poses.pose(prop)

    def _family(self, prop: str) -> 'int | None':
        """A `TES4FX_` effect family keyword (script_effects.ScriptEffects.family_named)."""
        return self.effects.family_named(prop)

    def _type_keyword(self, prop: str) -> int:
        """An `FNV_CreatureType<type>` keyword (type_tests.TypeKeywords)."""
        return self.builder.type_keywords.keyword(prop)

    def _global_form(self, prop: str) -> 'int | None':
        """A GlobalVariable property: a dialogue global, a quest-variable or objective mirror, FNV's, else a tested
        region's watch global (region_watch)."""
        if prop.startswith(DIALOGUE_GLOBALS):
            return self.global_(prop)
        mirror = self.mirror_global(prop) if prop.startswith((QVAR_PREFIX, OBJECTIVE_PREFIX)) else None
        watch = getattr(self.builder, 'region_watch', None)
        return mirror or self.builder.globals.get(self.global_names.get(prop)) or (watch and watch.global_of(prop))

    def _list_form(self, prop: str) -> 'int | None':
        """A FormList property: an animation, item type or runtime list; an item."""
        return (self.builder.equipment.anim_list(prop) or self.builder.items.type_list(prop)
                or self.form_list(prop) or self.builder.items.by_name(prop))

    def _spell_form(self, prop: str) -> 'int | None':
        """A Spell property: script-effect spell, perk ability, else FO4 addiction."""
        consumables = getattr(self.builder, 'consumables', None)
        return (self.effects.spell(prop) or (self.builder.perks and self.builder.perks.named_ability(prop))
                or (consumables and consumables.addictions.spell(prop)))

    def actor_base(self, name: str) -> 'int | None':
        """The FO4 base of FNV NPC or creature `name` (EditorID, any case), made on demand by the people stage's
        maker (Npcs.actor_form: a template actor for a templated creature) as a placed one's (a base a script only
        names: GetDeadCount on a leveled spawn's base); None when it does not convert or names none yet.
        See: docs/fork/fo4_plugin_layout.md#dlc-script-bases
        """
        if name.lower() in self.named_lower():
            return self.named_lower()[name.lower()]
        if self.actor_bases is None:
            self.actor_bases = {r['EditorID'].lower(): r['FormID'] for sig in ('NPC_', 'CREA')
                                for r in export_records(self.export_dir, sig) if r.get('EditorID')}
        found, npcs = self.actor_bases.get(name.lower()), getattr(self.builder, 'npcs', None)
        if found and npcs is None:
            self.builder.counts['ActorBase property filled before the people stage (left None)'] += 1
        return npcs.actor_form(found) if found and npcs else None

    def mirror_global(self, name: str) -> 'int | None':
        """A quest-variable or objective mirror global (`TES4QVar_<quest>_<var>`, `TES4Obj<state>_<quest>_<n>`):
        the build's own when written, else written for a quest the build leaves out on the FormID that quest's
        own build gives it (quest_var_globals, objective_globals); None for an unknown objective quest."""
        named = self.named_lower().get(name.lower())
        if named:
            return named
        objective = OBJECTIVE_GLOBAL.match(name)
        if objective is None:
            fid = self.builder.writer.derive_formid(QVAR_SITE, name)
        elif objective[2].lower() in self.quest_ids:
            fid = self.builder.new_id(objective_key(self.quest_ids[objective[2].lower()], int(objective[3]),
                                                    objective[1]))
        else:
            return None
        self.builder.writer.add_record('GLOB', pack_global(fid, name))
        self.named[name] = fid
        self.builder.counts['mirror GLOB of a quest not built'] += 1
        return fid

    def global_(self, name: str) -> int:
        """The dialogue global `name`, written once; its FormID hashed from the name."""
        if name not in self.globals:
            self.globals[name] = fid = self.builder.writer.derive_formid(GLOBAL_SITE, name)
            self.builder.writer.add_record('GLOB', pack_global(fid, name))
            self.builder.counts['dialogue GLOB'] += 1
        return self.globals[name]

    def form_list(self, name: str) -> 'int | None':
        """The helper FormList `name` (RUNTIME_LISTS), written once and empty, or the talking-as lists'
        (talking_activators); None for other names."""
        if name == TALKING_LISTS_PROPERTY:
            return self.builder.talkers.all_lists
        if name not in RUNTIME_LISTS:
            return None
        if name not in self.globals:
            self.globals[name] = fid = self.builder.writer.derive_formid(GLOBAL_SITE, name)
            self.builder.writer.add_record('FLST', pack_fo4_record('FLST', fid, 0, pack_string_subrecord('EDID', name)))
        return self.globals[name]

    def talk(self, prop: str) -> int:
        """The FormID of the scene a `TES4Talk_<topic>` property starts, reserved once per topic in any case (FNV
        names ignore case); its first spelling keys it."""
        if prop not in self.talks:
            same = next((fid for name, fid in self.talks.items() if name.lower() == prop.lower()), None)
            self.talks[prop] = same or self.builder.new_id(f'SCEN {prop}')
        return self.talks[prop]

    def entries(self, scpt: int) -> list:
        """[(name, object properties, value properties)] attaching FNV script `scpt`'s conversion (0: none), filled."""
        name = self.name(scpt) if scpt else None
        self.builder.counts['script not attached'] += 1 if scpt and name is None else 0
        self.used += [name] if name else []
        return [(name, self.properties(name), {})] if name else []

    def vmad(self, scpt: int, extra: tuple = ()) -> bytes:
        """VMAD of script `scpt`'s filled conversion and `extra` entries; b'' if none."""
        entries = self.entries(scpt) + list(extra)
        return object_scripts(entries) if entries else b''

    def message(self, edid: str) -> int:
        """The FO4 MESG for FNV message `edid`, made once; with no text it shows its title (FO4 shows only DESC), its
        control tokens FO4's (controls)."""
        if edid not in self.made_messages:
            rec = self.messages[edid]
            self.made_messages[edid] = self.builder.fnv_id(rec['FormID'])
            if not any('.Condition[' in key for key in rec):
                self._write_message(edid, [])
            elif self.gate_forms is None:
                self.gated_messages.append(edid)
            else:
                self._write_gated(edid, *self.gate_forms)
        return self.made_messages[edid]

    def _write_message(self, edid: str, shows: list) -> None:
        """Write FNV message `edid` as made: its buttons, each shown by its CTDAs in `shows` (b'': always)."""
        rec = self.messages[edid]
        buttons, i = [], 0
        while f'Button[{i}].Text' in rec:
            buttons.append(rec[f'Button[{i}].Text'])
            i += 1
        self.builder.writer.add_record('MESG', pack_mesg(
            self.made_messages[edid], f'FNV_{edid}', rec.get('FULL', ''),
            fo4_controls(rec.get('DESC') or rec.get('FULL', '')), int(rec.get('DNAM', 0)) & MESSAGE_BOX, buttons,
            shows))
        self.builder.counts['MESG'] += 1

    def write_gated_messages(self, forms: dict, script_vars: dict) -> None:
        """Write the messages whose buttons have conditions, once the build's condition forms (`forms`, the dialogue's
        map) and `script_vars` are known; a button whose conditions cannot convert shows always, counted.
        See: docs/fork/fo4_pipeline.md#message-buttons
        """
        self.builder.readables = self.builder.readables or Readables(self.builder)
        self.gate_forms = ({**self.builder.readables.form_map(), **forms}, script_vars)
        for edid in self.gated_messages:
            self._write_gated(edid, *self.gate_forms)

    def _write_gated(self, edid: str, forms: dict, script_vars: dict) -> None:
        """Write gated message `edid`, its buttons' conditions converted against `forms` and the forms they name."""
        rec = self.messages[edid]
        count = sum(1 for key in rec if key.startswith('Button[') and key.endswith('].Text'))
        parts = [conditions_under(rec, f'Button[{i}].') for i in range(count)]
        gates = [{**part, 'ConditionCount': str(len(part))} for part in parts]
        known = {**forms, **condition_forms(self.builder, gates)}
        self._write_message(edid, [self._gate(edid, gate, known, script_vars) for gate in gates])

    def _gate(self, edid: str, gate: dict, known: dict, script_vars: dict) -> bytes:
        """One button's FO4 CTDAs: NEVER_SHOWN when its conditions never pass (a form the build lacks), b'' to show
        it always when they cannot convert (counted, with message `edid`)."""
        settled = settled_by(gate, _kept)
        if settled is None or never_true(settled, known):
            return NEVER_SHOWN
        show = conditions_of(settled, known, script_vars)
        if show is None:
            self.builder.counts[f'message button not gated: {blocker(settled, known, script_vars)} ({edid})'] += 1
        return show or b''
