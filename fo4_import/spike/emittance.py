"""FNV emittance (XEMI) as FO4's: a reference taking its colour from a light, or from a region's daylight.

A light emittance points at the light's FO4 LIGH. A region emittance makes,
once per FNV region, an FO4 region shaped like Fallout4.esm's
FXLightRegionSunlightWhite (one weather, no worldspace) whose weather is
FXWthrSunlightWhite with its Sunlight and Effect Lighting colours replaced
by the FNV region's first weather's Sunlight colours. FO4 has eight times
of day to FNV's four; the early and late sunrise and sunset take FNV's
sunrise and sunset. The region's weather list is read from FalloutNV.esm.

See: docs/fork/fo4_pipeline.md#emittance
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import FALLOUTNV_ESM
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm FXLightRegionSunlightWhite and its weather FXWthrSunlightWhite.
FX_REGION, FX_WEATHER = 0x1171, 0x75491
#: Weather colour entries: FO4's Sunlight and Effect Lighting; FNV's Sunlight (of 10).
FO4_SUNLIGHT, FO4_EFFECT, FNV_SUNLIGHT, FNV_ENTRIES, FO4_ENTRIES = 4, 9, 4, 10, 19
#: FO4's eight times of day as indices into FNV's four (sunrise, day, sunset, night).
FO4_TIMES = (0, 1, 2, 3, 0, 0, 2, 2)


@functools.cache
def region_weathers() -> dict:
    """{FNV region FormID: its first weather's FormID} of FalloutNV.esm's regions with a weather list."""
    out = {}
    for rec, _ in walk(FALLOUTNV_ESM.read_bytes(), b'REGN'):
        rdwt = dict(subrecords(rec.body)).get(b'RDWT')
        if rdwt:
            out[rec.form_id] = struct.unpack_from('<I', rdwt)[0]
    return out


def sunlight_table(fo4_nam0: bytes, fnv_nam0: bytes) -> bytes:
    """FO4 weather colours `fo4_nam0` with Sunlight and Effect Lighting set to FNV colours `fnv_nam0`'s Sunlight."""
    per, entry = len(fnv_nam0) // FNV_ENTRIES, len(fo4_nam0) // FO4_ENTRIES
    fnv = fnv_nam0[FNV_SUNLIGHT * per:FNV_SUNLIGHT * per + 16]
    colours = b''.join(fnv[4 * t:4 * t + 4] for t in FO4_TIMES)
    out = bytearray(fo4_nam0)
    for index in (FO4_SUNLIGHT, FO4_EFFECT):
        out[index * entry:(index + 1) * entry] = colours
    return bytes(out)


class Emittance:
    """XEMI subrecords for FNV references, each FO4 region and weather made once."""

    def __init__(self, builder, export_dir: Path):
        self.builder, self.export_dir, self.made = builder, export_dir, {}

    @functools.cached_property
    def _vanilla(self) -> dict:
        """{FormID: body} of Fallout4.esm's FX region and weather."""
        return {r.form_id: r.body for r, _ in walk(self.builder.fo4, b'REGN', b'WTHR') if r.form_id in (FX_REGION, FX_WEATHER)}

    def xemi(self, ref: dict) -> bytes:
        """The XEMI of FNV reference `ref`; b'' when it has none or its region has no weather."""
        if 'XEMI.Emittance' not in ref:
            return b''
        fnv = int(ref['XEMI.Emittance'], 16)
        if self.builder.bases.get(fnv, ('',))[0] == 'LIGH':
            target = self.builder.base(fnv)
        else:
            target = self.region(fnv)
        self.builder.counts['emittance ' + ('converted' if target else 'left out')] += 1
        return pack_subrecord('XEMI', struct.pack('<I', target)) if target else b''

    def region(self, fnv: int) -> 'int | None':
        """The FO4 region for FNV region `fnv`'s daylight, made once; None if `fnv` is no region with weather."""
        if fnv not in self.made:
            weather = region_weathers().get(fnv)
            self.made[fnv] = self._make(fnv, weather) if weather else None
        return self.made[fnv]

    def _make(self, fnv: int, weather: int) -> int:
        """Write the FO4 weather and region for FNV region `fnv` and its weather; the region's FormID."""
        fnv_weather = next(r for r in export_records(self.export_dir, 'WTHR') if int(r['FormID'], 16) == weather)
        edid = f'FNV_{fnv_weather["EditorID"]}Emittance'
        wthr_id = self.builder.new_id(f'emittance weather {weather:08X}')
        subs = b''
        for tag, data in subrecords(self._vanilla[FX_WEATHER]):
            data = {b'EDID': edid.encode() + b'\0',
                    b'NAM0': sunlight_table(data, bytes.fromhex(fnv_weather['NAM0.Data']))}.get(tag, data)
            subs += pack_subrecord(tag.decode(), data)
        self.builder.writer.add_record('WTHR', pack_fo4_record('WTHR', wthr_id, 0, subs))
        regn_id = self.builder.fnv_id(fnv)
        subs = b''
        for tag, data in subrecords(self._vanilla[FX_REGION]):
            if tag != b'WNAM':
                data = {b'EDID': edid.encode() + b'Region\0', b'RDWT': struct.pack('<3I', wthr_id, 100, 0)}.get(tag, data)
                subs += pack_subrecord(tag.decode(), data)
        self.builder.writer.add_record('REGN', pack_fo4_record('REGN', regn_id, 0, subs))
        return regn_id
