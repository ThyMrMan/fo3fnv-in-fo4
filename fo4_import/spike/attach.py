"""Converted FNV scripts attached to the cell spike's records, their properties filled from the cell.

A record's FNV script (its SCRI) becomes its conversion (`papyrus_script_name`)
by VMAD. A property is filled when the spike has the form: a reference,
actor or quest of the cell named as the property (FNV EditorIDs), the
player, a helper quest or global (TES4Helpers.esl), the FNV item it names
through the cell's item converter (its conversion or FO4 stand-in), else a
Fallout4.esm misc item or potion of the same name, or the FNV message it
names (converted once), the FNV global it names (globals.py), or a dialogue
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
from fo4_import.spike.controls import fo4_controls
from fo4_import.spike.quest import QVAR_SITE, objective_key
from script_convert.quest_var_mirrors import PREFIX as QVAR_PREFIX
from fo4_import.spike.script import base_forms, declared_properties, fill
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.writer import pack_string_subrecord
from script_convert.constants import (FALLOUT4_CHAT_PREFIX, FALLOUT4_POSE_PREFIX, FALLOUT4_SWAP_PREFIX,
                                      FALLOUT4_TALK_PREFIX, papyrus_script_name)

SCRIPT_PREFIX = 'FALLOUTNV_'
#: The player reference, which converted scripts name `Player`.
PLAYER = ('Player', 0x14)
#: MESG DNAM Message Box, the one flag FNV and FO4 share (FNV bit 1 is Auto Display, FO4's Delay Initial Display).
MESSAGE_BOX = 0x1
#: Name prefixes of the dialogue globals converted lines set: AddTopic unlocks and Follow Up marks.
DIALOGUE_GLOBALS = ('TES4Unlock_', 'TES4FollowUpFrom_', 'TES4FollowUpSaid_')
#: derive_formid site of the dialogue globals (key: the global's name).
GLOBAL_SITE = 'FNV dialogue GLOB'
#: The FormList the polyfill's SetDestroyed mirrors destroyed references into (converter._destroyed_formlist).
DESTROYED_LIST = 'TES4DestroyedRefs'
#: Mirror global name prefix of an objective state, and its parts: state, quest EditorID, objective index.
OBJECTIVE_PREFIX = 'TES4Obj'
OBJECTIVE_GLOBAL = re.compile(r'TES4Obj(Done|Shown)_(.+)_(\d+)$')
#: Papyrus types of the item properties the cell's item converter fills by FNV name.
ITEM_TYPES = frozenset({'Potion', 'MiscObject', 'LeveledItem', 'Weapon', 'Armor', 'Ammo', 'Book', 'Key'})


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
        self.named, self.talks = dict([PLAYER]), {}
        self.quest_ids = {r['EditorID'].lower(): r['FormID'] for r in export_records(export_dir, 'QUST')
                          if r.get('EditorID')}

    def name(self, scpt: int) -> 'str | None':
        """The converted script of FNV script `scpt`; None when it was not converted."""
        name = papyrus_script_name(self.names.get(scpt, ''), SCRIPT_PREFIX)
        return name if self.dir and (self.dir / f'{name}.psc').exists() else None

    def properties(self, script: str) -> dict:
        """{property: FormID} of converted `script`'s properties the spike can fill.

        A `TES4Talk_<topic>` scene gets its FormID here, kept in `talks` for the conversation builder;
        material swaps, imagespace modifiers and poses are made on demand (_made). A name matches the build's
        forms ignoring case, as FNV's script names do (SunnyREF is the reference SunnyRef).
        """
        declared = declared_properties((self.dir / f'{script}.psc').read_text(encoding='utf-8'))
        messages = {prop: self.message(prop) for kind, prop in declared if kind == 'Message' and prop in self.messages}
        props = fill(declared, {**self.forms, 'Message': messages}, self.helper_index)
        talks = {prop: self.talk(prop) for kind, prop in declared
                 if kind == 'Scene' and prop.startswith((FALLOUT4_TALK_PREFIX, FALLOUT4_CHAT_PREFIX))}
        made, named = {prop: self._made(kind, prop) for kind, prop in declared}, self.named_lower()
        return {**props, **talks, **{p: f for p, f in made.items() if f},
                **{prop: named[prop.lower()] for _, prop in declared if prop.lower() in named}}

    def named_lower(self) -> dict:
        """`named` keyed by lower-case name."""
        return {name.lower(): fid for name, fid in self.named.items()}

    def _made(self, kind: str, prop: str) -> 'int | None':
        """A property's form the spike converts on demand: material swaps, imagespace modifiers, poses, items,
        weapon animation type lists, packages, idles; a Form-typed item (a note: paper or holotape)."""
        if kind == 'MatSwap' and prop.startswith(FALLOUT4_SWAP_PREFIX):
            return self.builder.swaps.swap(prop)
        if kind == 'ImageSpaceModifier':
            return self.builder.imods.modifier(prop)
        if kind == 'GlobalVariable':
            if prop.startswith(DIALOGUE_GLOBALS):
                return self.global_(prop)
            mirror = self.mirror_global(prop) if prop.startswith((QVAR_PREFIX, OBJECTIVE_PREFIX)) else None
            return mirror or self.builder.globals.get(self.global_names.get(prop))
        if kind == 'ObjectReference' and prop.startswith(FALLOUT4_POSE_PREFIX):
            return self.builder.poses.pose(prop)
        if kind == 'FormList':
            return self.builder.equipment.anim_list(prop) or self.form_list(prop) or self.builder.items.by_name(prop)
        if kind == 'Package':
            return self.builder.packages.named(prop)
        if kind == 'Idle':
            return self.builder.idles.named(prop)
        return self.builder.items.by_name(prop) if kind in ITEM_TYPES or kind == 'Form' else None

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
        """The helper FormList `name` (DESTROYED_LIST), written once and empty; None for other names."""
        if name != DESTROYED_LIST:
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

    def vmad(self, scpt: int, extra: tuple = ()) -> bytes:
        """The VMAD attaching FNV script `scpt`'s conversion (0: none), filled, beside `extra` (name, object
        properties, value properties) entries; b'' with neither."""
        name = self.name(scpt) if scpt else None
        self.builder.counts['script not attached'] += 1 if scpt and name is None else 0
        self.used += [name] if name else []
        entries = ([(name, self.properties(name), {})] if name else []) + list(extra)
        return object_scripts(entries) if entries else b''

    def message(self, edid: str) -> int:
        """The FO4 MESG for FNV message `edid`, made once; with no text it shows its title (FO4 shows only DESC), its
        control tokens FO4's (controls)."""
        if edid not in self.made_messages:
            rec = self.messages[edid]
            fid = self.builder.fnv_id(rec['FormID'])
            buttons, i = [], 0
            while f'Button[{i}].Text' in rec:
                buttons.append(rec[f'Button[{i}].Text'])
                i += 1
            self.builder.writer.add_record('MESG', pack_mesg(
                fid, f'FNV_{edid}', rec.get('FULL', ''), fo4_controls(rec.get('DESC') or rec.get('FULL', '')),
                int(rec.get('DNAM', 0)) & MESSAGE_BOX, buttons))
            self.builder.counts['MESG'] += 1
            self.made_messages[edid] = fid
        return self.made_messages[edid]
