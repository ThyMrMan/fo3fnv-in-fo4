"""Converted FNV scripts attached to the cell spike's records, their properties filled from the cell.

A record's FNV script (its SCRI) becomes its conversion (`papyrus_script_name`)
by VMAD. A property is filled when the spike has the form: a reference,
actor or quest of the cell named as the property (FNV EditorIDs), the
player, a helper quest or global (TES4Helpers.esl), a Fallout4.esm misc
item or potion of the same name, or the FNV message it names (converted
once). Same-named Fallout4.esm forms are not used otherwise: FNV's `PipBoy`
is not FO4's Pip-Boy.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from pathlib import Path

from fo4_import.base.support_records import pack_mesg
from fo4_import.base.vmad import object_scripts
from fo4_import.helpers_plugin import helper_forms
from fo4_import.spike.script import declared_properties, fill, fo4_forms
from script_convert.constants import (FALLOUT4_POSE_PREFIX, FALLOUT4_SWAP_PREFIX, FALLOUT4_TALK_PREFIX,
                                      papyrus_script_name)
from tes5_import.base.text_reader import parse_export_file

SCRIPT_PREFIX = 'FALLOUTNV_'
#: The player reference, which converted scripts name `Player`.
PLAYER = ('Player', 0x14)
#: MESG DNAM Message Box, the one flag FNV and FO4 share (FNV bit 1 is Auto Display, FO4's Delay Initial Display).
MESSAGE_BOX = 0x1


class ObjectScripts:
    """Converted scripts for the cell's records; `used` lists those attached, `named` the cell's forms by FNV name."""

    def __init__(self, builder, export_dir: Path, scripts_dir: 'Path | None', helper_index: int):
        """Scripts from the converted `scripts_dir` (None: none attached); helpers at master `helper_index`."""
        self.builder, self.dir, self.helper_index, self.used = builder, scripts_dir, helper_index, []
        self.names = {int(r['FormID'], 16): r['EditorID'] for r in parse_export_file(str(export_dir / 'SCPT.txt'))}
        self.messages = {r.get('EditorID'): r for r in parse_export_file(str(export_dir / 'MESG.txt'))}
        self.forms, self.made_messages = {**fo4_forms(), **helper_forms(helper_index)}, {}
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
        """A property's form the spike converts on demand: material swaps, imagespace modifiers, poses."""
        if kind == 'MatSwap' and prop.startswith(FALLOUT4_SWAP_PREFIX):
            return self.builder.swaps.swap(prop)
        if kind == 'ImageSpaceModifier':
            return self.builder.imods.modifier(prop)
        if kind == 'ObjectReference' and prop.startswith(FALLOUT4_POSE_PREFIX):
            return self.builder.poses.pose(prop)
        return None

    def talk(self, prop: str) -> int:
        """The FormID of the scene a `TES4Talk_<topic>` property starts, reserved once."""
        if prop not in self.talks:
            self.talks[prop] = self.builder.new_id()
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
            rec, fid = self.messages[edid], self.builder.new_id()
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
