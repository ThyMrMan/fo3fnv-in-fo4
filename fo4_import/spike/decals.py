"""FNV placed decals (TXST references) as Fallout 4's: a decal texture set placed as a reference.

FO4 places texture sets as decals, as FNV does (24,718 in Fallout4.esm, 2 in
FalloutNV.esm). The two games' decal data (DODT) share a layout: widths,
heights, depth, shininess, parallax scale and passes, flags, two bytes,
colour. A decal keeps FNV's textures (diffuse TX00, normal TX01, staged as
any texture) and data, except: shininess is FO4's usual 1.0 (FNV's is a
specular exponent, 300 here; 132 of Fallout4.esm's 180 decals use 1.0);
flags keep alpha blending, alpha testing and no subtextures, the bits both
games read alike (FNV's bit 0 is parallax, FO4's POM shadows); the two
bytes, junk in FNV, are 0. DODT is read from FalloutNV.esm (the export
drops it).

See: docs/fork/fo4_pipeline.md#reference-fields
"""

import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif.convert_static import fo4_texture
from fo4_import.pipeline.export_index import export_file
from fo4_import.spike.statics import copy_texture
from tes5_import.base.tes5_reader import first_sub
from tes5_import.base.writer import pack_subrecord

#: DODT: FO4's shininess, the flags kept (alpha blending, alpha testing, no subtextures).
SHININESS, KEPT_FLAGS = 1.0, 0x0E
#: DODT byte offsets: shininess, flags, the two unused bytes.
AT_SHININESS, AT_FLAGS, AT_UNUSED = 20, 29, 30
#: The texture slots a decal keeps.
SLOTS = ('TX00', 'TX01')


def decal_data(dodt: bytes) -> bytes:
    """FNV decal data `dodt` as FO4's (module docstring)."""
    out = bytearray(dodt)
    struct.pack_into('<f', out, AT_SHININESS, SHININESS)
    out[AT_FLAGS] &= KEPT_FLAGS
    out[AT_UNUSED:AT_UNUSED + 2] = bytes(2)
    return bytes(out)


class Decals:
    """FO4 decal texture sets for FNV's, through a cell builder."""

    def __init__(self, builder):
        """Read FalloutNV.esm's decal data (DODT) by texture set."""
        self.builder = builder
        self.dodt = {rec.form_id: first_sub(rec.body, b'DODT') for rec, _ in source_walk(b'TXST')}

    def record(self, fid: int, rec: dict) -> int:
        """Write FNV TXST export record `rec` as an FO4 decal texture set on `fid`, its textures staged; `fid`."""
        subs = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}'.encode('cp1252') + b'\0')
        bounds = tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))
        subs += pack_subrecord('OBND', struct.pack('<6h', *bounds))
        for slot in SLOTS:
            source = 'textures\\' + rec[slot].replace('/', '\\').lower() if rec.get(slot) else None
            if source and not export_file(self.builder.export_dir, source.replace('\\', '/')).is_file():
                self.builder.counts['decal textures in no archive (left out)'] += 1
            elif source:
                copy_texture(self.builder.export_dir, self.builder.data_dir, source)
                subs += pack_subrecord(slot, (fo4_texture(source) + '\0').encode('cp1252'))
        dodt = self.dodt.get(int(rec['FormID'], 16))
        subs += pack_subrecord('DODT', decal_data(dodt)) if dodt else b''
        self.builder.writer.add_record('TXST', pack_fo4_record('TXST', fid, 0, subs + pack_subrecord('DNAM', bytes(2))))
        self.builder.counts['decals'] += 1
        return fid
