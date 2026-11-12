"""FNV lights in Fallout 4's modern style: each cell's main (Key) lights cast shadows.

FNV names each light by its lighting role (Key, Fill, Amb, Kicker) and no
FNV light casts a shadow. Each Key light gets a copy that casts an
omnidirectional shadow; in each cell the SHADOW_CAP widest Key references
place the copy, and the rest, and every other role, keep FNV's shadowless
light, as vanilla's fill, bounce and ambient lights are. The copy's near
clip keeps the fixture around the light out of its shadow map.

See: docs/fork/fo4_look.md#route-lights
See: docs/fork/fo4_look.md#light-near-clip
"""
import re
import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of a Key light's shadow-casting copy (key: the FNV LIGH FormID).
SITE = 'FNV shadow light'
#: FO4 LIGH DATA flag Shadow OmniDirectional (xEdit wbDefinitionsFO4), and the flags' offset in DATA.
SHADOW_OMNI, FLAGS_AT = 0x1000, 12
#: Shadow near clip (DATA float at NEAR_CLIP_AT): vanilla's commonest on placed shadow lights, as at its fixtures.
NEAR_CLIP, NEAR_CLIP_AT = 64.0, 24
#: Shadow-casting lights per cell: Fallout4.esm's 90th percentile over its 442 lit interiors (median 1).
SHADOW_CAP = 6
#: Size of a record header before its subrecords.
HEADER = 24
WORD = re.compile(r'[A-Z][a-z]+|[a-z]+|[A-Z]+(?![a-z])')


def is_key(edid: str) -> bool:
    """Whether an FNV light EditorID names a Key light (a word 'Key', any case)."""
    return 'key' in {w.lower() for w in WORD.findall(edid)}


def shadow_copy(record: bytes, fid: int) -> bytes:
    """Packed LIGH `record` on `fid`: EditorID suffixed _Shadow, DATA casting an omni shadow from NEAR_CLIP out."""
    subs = b''
    for tag, data in subrecords(record[HEADER:]):
        if tag == b'EDID':
            data = data.rstrip(b'\0') + b'_Shadow\0'
        elif tag == b'DATA':
            data = bytearray(data)
            struct.pack_into('<I', data, FLAGS_AT, struct.unpack_from('<I', data, FLAGS_AT)[0] | SHADOW_OMNI)
            struct.pack_into('<f', data, NEAR_CLIP_AT, NEAR_CLIP)
            data = bytes(data)
        subs += pack_subrecord(tag.decode('latin1'), data)
    return pack_fo4_record('LIGH', fid, 0, subs)


class ShadowLights:
    """Key lights' shadow-casting copies and which references place them."""

    def __init__(self, builder, export_dir):
        self.builder, self.copies = builder, {}
        self.radii = {int(r['FormID'], 16): float(r['DATA.Radius']) for r in export_records(export_dir, 'LIGH')
                      if is_key(r.get('EditorID', ''))}

    def add(self, rec: dict, record: bytes) -> None:
        """Write FNV light `rec`'s shadow copy (from its packed `record`) when it is a Key light."""
        fnv = int(rec['FormID'], 16)
        if fnv in self.radii and fnv not in self.copies:
            fid = self.builder.writer.derive_formid(SITE, rec['FormID'])
            self.builder.writer.add_record('LIGH', shadow_copy(record, fid))
            self.copies[fnv] = fid

    def chosen(self, refs: list) -> set:
        """FormIDs of the SHADOW_CAP widest Key lights of a cell's `refs`."""
        keys = [r for r in refs if int(r['NAME'], 16) in self.radii]
        ranked = sorted(keys, key=lambda r: (-float(r.get('XRDS.Radius', self.radii[int(r['NAME'], 16)])), r['FormID']))
        return {r['FormID'] for r in ranked[:SHADOW_CAP]}

    def base_of(self, ref: dict, base: int, chosen: set) -> int:
        """The base `ref` places: its light's shadow copy when chosen, else `base`."""
        copy = self.copies.get(int(ref['NAME'], 16)) if ref['FormID'] in chosen else None
        self.builder.counts['key lights casting a shadow'] += copy is not None
        return copy or base
