"""Converted FNV scripts attached to the cell spike's records, their properties filled from the cell.

A record's FNV script (its SCRI) becomes its conversion (`papyrus_script_name`)
by VMAD. A property is filled when the spike has the form: a reference,
actor or quest of the cell named as the property (FNV EditorIDs), the
player, a helper quest or global (TES4Helpers.esl), the FNV item it names
through the cell's item converter (its conversion or FO4 stand-in), else a
Fallout4.esm misc item or potion of the same name, or the FNV message it
names (converted once), or a dialogue global it sets (an AddTopic unlock or a
Follow Up mark, made once, its FormID hashed from its name). Same-named
Fallout4.esm forms are not used otherwise.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from pathlib import Path

from fo4_import.base.support_records import pack_global, pack_mesg
from fo4_import.base.vmad import object_scripts
from fo4_import.helpers_plugin import helper_forms
from fo4_import.spike.script import declared_properties, fill, fo4_forms
from fo4_import.pipeline.export_index import export_records
from script_convert.constants import (FALLOUT4_POSE_PREFIX, FALLOUT4_SWAP_PREFIX, FALLOUT4_TALK_PREFIX,
                                      papyrus_script_name)

SCRIPT_PREFIX = 'FALLOUTNV_'
#: The player reference, which converted scripts name `Player`.
PLAYER = ('Player', 0x14)
#: MESG DNAM Message Box, the one flag FNV and FO4 share (FNV bit 1 is Auto Display, FO4's Delay Initial Display).
MESSAGE_BOX = 0x1
#: Name prefixes of the dialogue globals converted lines set: AddTopic unlocks and Follow Up marks.
DIALOGUE_GLOBALS = ('TES4Unlock_', 'TES4FollowUpFrom_', 'TES4FollowUpSaid_')
#: derive_formid site of the dialogue globals (key: the global's name).
GLOBAL_SITE = 'FNV dialogue GLOB'
#: Papyrus types of the item properties the cell's item converter fills by FNV name.
ITEM_TYPES = frozenset({'Potion', 'MiscObject', 'LeveledItem', 'Weapon', 'Armor', 'Ammo', 'Book', 'Key'})


class ObjectScripts:
    """Converted scripts for the cell's records; `used` lists those attached, `named` the cell's forms by FNV name."""

    def __init__(self, builder, export_dir: Path, scripts_dir: 'Path | None', helper_index: int):
        """Scripts from the converted `scripts_dir` (None: none attached); helpers at master `helper_index`."""
        self.builder, self.dir, self.helper_index, self.used = builder, scripts_dir, helper_index, []
        self.names = {int(r['FormID'], 16): r['EditorID'] for r in export_records(export_dir, 'SCPT')}
        self.messages = {r.get('EditorID'): r for r in export_records(export_dir, 'MESG')}
        self.forms, self.made_messages, self.globals = {**fo4_forms(), **helper_forms(helper_index)}, {}, {}
        self.named, self.talks = dict([PLAYER]), {}

    def name(self, scpt: int) -> 'str | None':
        """The converted script of FNV script `scpt`; None when it was not converted."""
        name = papyrus_script_name(self.names.get(scpt, ''), SCRIPT_PREFIX)
        return name if self.dir and (self.dir / f'{name}.psc').exists() else None

    def properties(self, script: str) -> dict:
        """{property: FormID} of converted `script`'s properties the spike can fill.

        A `TES4Talk_<topic>` scene gets its FormID here, kept in `talks` for the conversation builder;
        material swaps, imagespace modifiers and poses are made on demand (_made).
        """
        declared = declared_properties((self.dir / f'{script}.psc').read_text(encoding='utf-8'))
        messages = {prop: self.message(prop) for kind, prop in declared if kind == 'Message' and prop in self.messages}
        props = fill(declared, {**self.forms, 'Message': messages}, self.helper_index)
        talks = {prop: self.talk(prop) for kind, prop in declared if kind == 'Scene' and prop.startswith(FALLOUT4_TALK_PREFIX)}
        made = {prop: self._made(kind, prop) for kind, prop in declared}
        return {**props, **talks, **{p: f for p, f in made.items() if f},
                **{prop: self.named[prop] for _, prop in declared if prop in self.named}}

    def _made(self, kind: str, prop: str) -> 'int | None':
        """A property's form the spike converts on demand: material swaps, imagespace modifiers, poses, items."""
        if kind == 'MatSwap' and prop.startswith(FALLOUT4_SWAP_PREFIX):
            return self.builder.swaps.swap(prop)
        if kind == 'ImageSpaceModifier':
            return self.builder.imods.modifier(prop)
        if kind == 'GlobalVariable' and prop.startswith(DIALOGUE_GLOBALS):
            return self.global_(prop)
        if kind == 'ObjectReference' and prop.startswith(FALLOUT4_POSE_PREFIX):
            return self.builder.poses.pose(prop)
        return self.builder.items.by_name(prop) if kind in ITEM_TYPES else None

    def global_(self, name: str) -> int:
        """The dialogue global `name`, written once; its FormID hashed from the name."""
        if name not in self.globals:
            self.globals[name] = fid = self.builder.writer.derive_formid(GLOBAL_SITE, name)
            self.builder.writer.add_record('GLOB', pack_global(fid, name))
            self.builder.counts['dialogue GLOB'] += 1
        return self.globals[name]

    def talk(self, prop: str) -> int:
        """The FormID of the scene a `TES4Talk_<topic>` property starts, reserved once."""
        if prop not in self.talks:
            self.talks[prop] = self.builder.new_id(f'SCEN {prop}')
        return self.talks[prop]

    def vmad(self, scpt: int) -> bytes:
        """The VMAD attaching FNV script `scpt`'s conversion, filled; b'' when it is not converted."""
        name = self.name(scpt)
        if name is None:
            self.builder.counts['script not attached'] += 1
            return b''
        self.used.append(name)
        return object_scripts([(name, self.properties(name), {})])

    def message(self, edid: str) -> int:
        """The FO4 MESG for FNV message `edid`, made once; with no text it shows its title (FO4 shows only DESC)."""
        if edid not in self.made_messages:
            rec = self.messages[edid]
            fid = self.builder.fnv_id(rec['FormID'])
            buttons, i = [], 0
            while f'Button[{i}].Text' in rec:
                buttons.append(rec[f'Button[{i}].Text'])
                i += 1
            self.builder.writer.add_record('MESG', pack_mesg(
                fid, f'FNV_{edid}', rec.get('FULL', ''), rec.get('DESC') or rec.get('FULL', ''),
                int(rec.get('DNAM', 0)) & MESSAGE_BOX, buttons))
            self.builder.counts['MESG'] += 1
            self.made_messages[edid] = fid
        return self.made_messages[edid]
