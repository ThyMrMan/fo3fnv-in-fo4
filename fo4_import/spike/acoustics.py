"""FNV interior acoustic spaces (ASPC, a cell's XCAS) as Fallout 4's: a looping sound, region sounds, reverb.

FNV's ASPC holds four loops by time of day (SNAM: dawn or default,
afternoon, dusk, night), a walla sound, the region whose sounds play inside
(RDAT) and an environment type (ANAM, an EAX preset); FO4's holds one loop
(SNAM, a sound descriptor), the region (RDAT), a reverb record (BNAM), the
interior flag (XTRI) and weather attenuation (WNAM). A space takes FNV's
dawn or default loop, its region (regions, without a worldspace when FNV
gives none) and the vanilla reverb REVERBS names for its environment type.
FO4 gives acoustic spaces only to interiors (282 of Fallout4.esm's cells, no
exterior), so only an interior's XCAS converts. Spaces and cell XCAS are read
from FalloutNV.esm (the export has neither).

See: docs/fork/fo4_pipeline.md#acoustic-spaces
"""

import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.records import pack_u32
from fo4_import.spike.regions import regions_of
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV environment type (xEdit's ASPC ANAM enum) -> the Fallout4.esm REVB nearest it; outdoor types have none.
REVERBS = {
    1: 'DefaultReverb', 2: 'IntGenericAReverb', 3: 'IntFakeWoodSmall', 4: 'IntRoomWoodMediumReverb',
    5: 'IntRoomStoneMediumReverb', 6: 'IntRoomWoodRoomsReverb', 7: 'IntRoomStoneMediumReverb',
    8: 'IntRoomStoneLargeReverb', 9: 'IntRoomStoneLargeExtraReverb', 10: 'IntCaveAReverb', 11: 'IntCaveLargeReverb',
    12: 'IntIndustrialLargeExtraReverb', 13: 'IntFakeWoodMedium', 14: 'IntGenericBReverb', 15: 'IntRoomStoneNarrow',
    23: 'IntCaveSewerPipeReverb', 24: 'Underwater', 25: 'IntVaultGenericRoomSmallReverb',
    26: 'IntVaultGenericRoomMediumReverb', 27: 'IntVaultGenericRoomLargeReverb', 28: 'IntIndustrialMediumReverb',
    29: 'IntIndustrialLargeReverb', 30: 'IntFakeMetalMedium',
}


class AcousticSpaces:
    """FO4 ASPCs for FNV's, written once each, and the XCAS of FNV interiors."""

    def __init__(self, builder):
        """Read FalloutNV.esm's acoustic spaces and its interiors' XCAS, and Fallout4.esm's reverbs."""
        self.builder, self.made = builder, {}
        self.fnv = {rec.form_id: list(subrecords(rec.body)) for rec, _ in source_walk(b'ASPC')}
        self.cells = {}
        for rec, _ in source_walk(b'CELL'):
            subs = dict(subrecords(rec.body))
            if b'XCAS' in subs and b'XCLC' not in subs:
                self.cells[rec.form_id] = struct.unpack('<I', subs[b'XCAS'])[0]
        self.reverbs = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                        for r, _ in walk(builder.fo4, b'REVB')}

    def xcas(self, fnv_cell: int) -> bytes:
        """FNV interior `fnv_cell`'s XCAS as FO4's (b'': none)."""
        space = self.space(self.cells[fnv_cell]) if fnv_cell in self.cells else 0
        return pack_u32('XCAS', space) if space else b''

    def space(self, fnv: int) -> int:
        """FNV ASPC `fnv`'s FO4 ASPC, written once (0: not in FalloutNV.esm)."""
        if fnv not in self.made:
            self.made[fnv] = self._make(fnv) if fnv in self.fnv else 0
        return self.made[fnv]

    def _make(self, fnv: int) -> int:
        """Write FNV ASPC `fnv` as FO4's (module docstring); its FormID."""
        subs = self.fnv[fnv]
        found = dict(subs)
        loops = [struct.unpack('<I', v)[0] for t, v in subs if t == b'SNAM']
        loop = self.builder.sounds.descriptor(loops[0]) if loops and loops[0] else 0
        region = struct.unpack('<I', found[b'RDAT'])[0] if b'RDAT' in found else 0
        region = regions_of(self.builder).region(region) if region in regions_of(self.builder).fnv else 0
        reverb = self.reverbs.get(REVERBS.get(struct.unpack('<I', found[b'ANAM'])[0] if b'ANAM' in found else 0, ''))
        body = pack_subrecord('EDID', b'FNV_' + found[b'EDID']) + pack_subrecord('OBND', found[b'OBND'])
        body += (pack_u32('SNAM', loop) if loop else b'') + (pack_u32('RDAT', region) if region else b'')
        body += (pack_u32('BNAM', reverb) if reverb else b'') + pack_subrecord('XTRI', b'\x01')
        body += pack_subrecord('WNAM', struct.pack('<H', 0))
        fid = self.builder.fnv_id(fnv)
        self.builder.writer.add_record('ASPC', pack_fo4_record('ASPC', fid, 0, body))
        self.builder.counts['acoustic spaces'] += 1
        return fid
