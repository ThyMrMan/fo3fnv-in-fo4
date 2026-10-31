"""FNV region weather and sounds as Fallout 4's: the regions of the built cells, and each cell's region list.

FO4 reads a REGN as FNV writes it: colour (RCLR), worldspace (WNAM), areas
(RPLI edge falloff, RPLD points), then per data entry an 8-byte RDAT (type,
flags, priority) and its data. A weather entry (type 3) is RDWT, 12 bytes
each (weather, chance, global). A sound entry (type 7) is FNV's RDSD (sound,
weather flags, chance x 10,000 as a percentage) and FO4's RDSA (sound
descriptor, the same flags, chance as a fraction). A region keeps FNV's
areas, flags and priority; its worldspace, weathers and sounds become the
converted ones (weathers, sounds), and a global the build lacks reads 0
(none); its music and other entries are left out. A cell lists (XCLR) the
regions FNV's cell lists that carry either. The region is hashed apart from
the emittance's daylight copy of the same FNV region. Regions and cell lists
are read from FalloutNV.esm (the export has neither).

See: docs/fork/fo4_pipeline.md#region-weather
"""

import functools
import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.weathers import fnv_weather
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: FNV/FO4 region data types: a weather list, a sound list; FNV's imposter list (RDID: references).
WEATHER, SOUND, IMPOSTER = 3, 7, 8
#: FNV region sound chance: a percentage x 10,000; FO4's is a fraction.
CHANCE_SCALE = 1_000_000
#: ledger site of a converted region (key: the FNV REGN); named before regions carried sounds.
REGION_SITE = 'FNV weather region'
#: A region area's subrecords, kept in FNV's order (RPLI then RPLD per area).
AREAS = (b'RPLI', b'RPLD')
#: Each converted entry type's FNV data subrecord.
DATA = {WEATHER: b'RDWT', SOUND: b'RDSD'}


@functools.cache
def imposters() -> frozenset:
    """FNV FormIDs of the references a region shows as imposters (its RDAT type IMPOSTER entry's RDID list).
    See: docs/fork/fo4_pipeline.md#imposters
    """
    out, kind = set(), None
    for rec, _ in source_walk(b'REGN'):
        for tag, data in subrecords(rec.body):
            kind = struct.unpack_from('<I', data)[0] if tag == b'RDAT' else kind
            out.update(struct.unpack_from(f'<{len(data) // 4}I', data) if tag == b'RDID' and kind == IMPOSTER else ())
    return frozenset(out)


def regions_of(builder) -> 'Regions':
    """`builder`'s Regions, made on first use (exteriors and interiors share them)."""
    builder.weather_regions = builder.weather_regions or Regions(builder)
    return builder.weather_regions


class Regions:
    """FO4 regions for FNV's weather and sound regions, written once each, and the region lists of FNV cells."""

    def __init__(self, builder):
        """Read FalloutNV.esm's regions that carry weather or sounds and the region lists of its cells."""
        self.builder, self.made = builder, {}
        self.fnv = {}
        for rec, _ in source_walk(b'REGN'):
            subs = list(subrecords(rec.body))
            if any(tag in DATA.values() for tag, _ in subs):
                self.fnv[rec.form_id] = subs
        self.lists = {}
        for rec, _ in source_walk(b'CELL'):
            xclr = dict(subrecords(rec.body)).get(b'XCLR')
            if xclr:
                self.lists[rec.form_id] = [r for (r,) in struct.iter_unpack('<I', xclr) if r in self.fnv]

    def xclr(self, fnv_cell: int, extra: tuple = ()) -> bytes:
        """FNV cell `fnv_cell`'s XCLR: its regions, then `extra` FO4 ones (b'': none)."""
        regions = [r for r in (self.region(f) for f in self.lists.get(fnv_cell, ())) if r] + list(extra)
        return pack_subrecord('XCLR', struct.pack(f'<{len(regions)}I', *regions)) if regions else b''

    def region(self, fnv: int) -> int:
        """FNV region `fnv`'s FO4 REGN, written once (0: nothing converts)."""
        if fnv not in self.made:
            self.made[fnv] = self._make(fnv)
        return self.made[fnv]

    def _make(self, fnv: int) -> int:
        """Write FNV region `fnv` as an FO4 REGN (module docstring); its FormID, 0 without an entry."""
        subs = self.fnv[fnv]
        found, data = dict(subs), self._data(subs)
        if not data:
            return 0
        fid = self.builder.writer.derive_formid(REGION_SITE, f'{fnv:08X}')
        world = self.builder.fnv_id(struct.unpack('<I', found[b'WNAM'])[0]) if b'WNAM' in found else 0
        body = pack_subrecord('EDID', b'FNV_' + found[b'EDID']) + pack_subrecord('RCLR', found[b'RCLR'])
        body += pack_subrecord('WNAM', struct.pack('<I', world)) if world else b''
        body += b''.join(pack_subrecord(tag.decode(), value) for tag, value in subs if tag in AREAS) + data
        self.builder.writer.add_record('REGN', pack_fo4_record('REGN', fid, 0, body))
        self.builder.counts['regions'] += 1
        return fid

    def _data(self, subs: list) -> bytes:
        """The weather and sound entries of FNV region subrecords `subs` as FO4's; b'' when none converts."""
        out, entry = b'', None
        for tag, value in subs:
            if tag == b'RDAT':
                entry = value if DATA.get(struct.unpack_from('<I', value)[0]) else None
            elif entry is not None and tag == DATA[struct.unpack_from('<I', entry)[0]]:
                out += self._weathers(entry, value) if tag == b'RDWT' else self._sounds(entry, value)
        return out

    def _weathers(self, rdat: bytes, rdwt: bytes) -> bytes:
        """RDAT `rdat` and FNV weather list `rdwt` as FO4's, its weathers and globals converted; b'' if none is."""
        entries = []
        for weather, chance, glob in struct.iter_unpack('<IiI', rdwt):
            made = fnv_weather(self.builder, weather)
            if made:
                entries.append(struct.pack('<IiI', made, chance, self.builder.globals.get(glob, 0) if glob else 0))
        return pack_subrecord('RDAT', rdat) + pack_subrecord('RDWT', b''.join(entries)) if entries else b''

    def _sounds(self, rdat: bytes, rdsd: bytes) -> bytes:
        """RDAT `rdat` and FNV sound list `rdsd` as FO4's RDSA, its sounds as descriptors; b'' if none converts."""
        entries = []
        for sound, flags, chance in struct.iter_unpack('<III', rdsd):
            made = self.builder.sounds.descriptor(sound)
            if made:
                entries.append(struct.pack('<IIf', made, flags, chance / CHANCE_SCALE))
        self.builder.counts['region sounds'] += len(entries)
        return pack_subrecord('RDAT', rdat) + pack_subrecord('RDSA', b''.join(entries)) if entries else b''
