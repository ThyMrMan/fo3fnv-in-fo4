"""FNV voice types as FO4 VTYP records, for the cell spike.

A converted NPC speaks with its FNV voice type (VTCK) in place of its vanilla
body's, so FO4 finds a line's recording under that voice type's folder
(voice.py). FNV's and FO4's VTYP are alike: an EditorID and a DNAM flag byte
(Allow Default Dialog 0x1, Female 0x2), read from FalloutNV.esm, since the
export does not decode VTYP. Each record keeps FNV's FormID.

See: docs/fork/fo4_pipeline.md#voice-types
"""

import functools
import struct

from fo4_import.base.install import fnv_esm
from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord


@functools.cache
def fnv_voice_types() -> dict:
    """{FormID: (EditorID, DNAM flags)} of FalloutNV.esm's voice types."""
    out = {}
    for rec, _ in walk(fnv_esm(), b'VTYP'):
        subs = dict(subrecords(rec.body))
        out[rec.form_id] = (subs.get(b'EDID', b'').rstrip(b'\0').decode(), subs.get(b'DNAM', b'\0')[0])
    return out


class VoiceTypes:
    """FO4 voice types for FNV ones, each written once; `made` maps each FO4 EditorID to FNV's."""

    def __init__(self, builder):
        self.builder, self.ids, self.made = builder, {}, {}

    def of(self, fnv: int) -> 'int | None':
        """The FO4 voice type for FNV voice type `fnv` (written once); None when FNV has none such."""
        if fnv not in self.ids:
            known = fnv_voice_types().get(fnv)
            self.ids[fnv] = self._write(fnv, *known) if known else None
        return self.ids[fnv]

    def _write(self, fnv: int, edid: str, flags: int) -> int:
        """Write FNV voice type `fnv` (EditorID `edid`, DNAM `flags`); its FO4 FormID."""
        fid, name = self.builder.fnv_id(f'{fnv:08X}'), f'FNV_{edid}'
        subs = pack_subrecord('EDID', name.encode() + b'\0') + pack_subrecord('DNAM', struct.pack('<B', flags))
        self.builder.writer.add_record('VTYP', pack_fo4_record('VTYP', fid, 0, subs))
        self.builder.counts['VTYP'] += 1
        self.made[name] = edid
        return fid


def with_voice(voice: 'int | None'):
    """A record edit giving an NPC FO4 voice type `voice` (VTCK); None when there is none."""
    if voice is None:
        return None

    def edit(subs: bytes) -> bytes:
        """The subrecords with VTCK replaced."""
        return b''.join(pack_subrecord(tag.decode(), struct.pack('<I', voice) if tag == b'VTCK' else data)
                        for tag, data in subrecords(subs))
    return edit
