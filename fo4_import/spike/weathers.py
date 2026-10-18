"""An FNV worldspace's climate and its weathers as Fallout 4's, so the exterior lights and fogs as FNV's.

The exterior used the Commonwealth's climate: FO4's grey sun and neutral
ambient. Each FNV climate weather becomes a copy of Fallout4.esm's
CommonwealthClear with FNV's colours (sky, fog, ambient, sunlight, sun,
stars, horizon; FNV's four times of day spread over FO4's eight) and FNV's
fog distances and power (power x 2.2, as interiors'); its clouds,
imagespaces and the rest stay vanilla's, as Project Mojave's weathers do.
The climate is a copy of DefaultClimate with FNV's weather list and sun
timing. Records read from FalloutNV.esm keep FNV's FormIDs.

See: docs/fork/fo4_pipeline.md#weathers
"""

import functools
import struct

from fo4_import.base.install import source_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.imagespace import DISPLAY_GAMMA
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm DefaultClimate and CommonwealthClear: the climate and weather templates.
CLIMATE_TEMPLATE, WEATHER_TEMPLATE = 0x15F, 0x2B52A
#: Colour types in a weather's NAM0: FNV's 10, FO4's 19.
FNV_ENTRIES, FO4_ENTRIES = 10, 19
#: FNV colour type -> FO4 types it fills (fog: near, far and both high; sunlight: effect lighting too).
COLOURS = {0: (0,), 1: (1, 12, 17, 18), 3: (3,), 4: (4, 9), 5: (5,), 6: (6,), 7: (7,), 8: (8,)}
#: FO4's eight times of day as indices into FNV's first four (sunrise, day, sunset, night).
FO4_TIMES = (0, 1, 2, 3, 0, 0, 2, 2)
#: FNV fog floats: day near, day far, night near, night far, day power, night power (FO4's first six).
FOG_FLOATS, FOG_POWERS = 6, (4, 5)


def colour_table(fo4_nam0: bytes, fnv_nam0: bytes, types: dict = None) -> bytes:
    """FO4 weather colours `fo4_nam0` with the types `types` ({FNV type: FO4 types}, default COLOURS) set to FNV
    colours `fnv_nam0`'s, per FO4_TIMES."""
    per, entry = len(fnv_nam0) // FNV_ENTRIES, len(fo4_nam0) // FO4_ENTRIES
    out = bytearray(fo4_nam0)
    for fnv_type, fo4_types in (types or COLOURS).items():
        fnv = fnv_nam0[fnv_type * per:fnv_type * per + 16]
        colours = b''.join(fnv[4 * t:4 * t + 4] for t in FO4_TIMES)
        for index in fo4_types:
            out[index * entry:(index + 1) * entry] = colours
    return bytes(out)


def fog_table(fo4_fnam: bytes, fnv_fnam: bytes) -> bytes:
    """FO4 weather fog `fo4_fnam` with FNV's distances and powers (x DISPLAY_GAMMA) in its first six floats."""
    values = list(struct.unpack(f'<{FOG_FLOATS}f', fnv_fnam[:4 * FOG_FLOATS]))
    for i in FOG_POWERS:
        values[i] *= DISPLAY_GAMMA
    return struct.pack(f'<{FOG_FLOATS}f', *values) + fo4_fnam[4 * FOG_FLOATS:]


@functools.cache
def _fnv_records() -> dict:
    """{FormID: {tag: data}} of FalloutNV.esm's climates and weathers."""
    return {r.form_id: dict(subrecords(r.body)) for r, _ in walk(source_esm(), b'CLMT', b'WTHR')}


def climate(builder, fnv: int) -> int:
    """Write FNV climate `fnv` and its weathers as FO4 records; the climate's FormID (0 when FNV has none)."""
    source = _fnv_records().get(fnv)
    if source is None:
        return 0
    templates = {r.form_id: r.body for r, _ in walk(builder.fo4, b'CLMT', b'WTHR')
                 if r.form_id in (CLIMATE_TEMPLATE, WEATHER_TEMPLATE)}
    weathers = [(weather(builder, w, templates[WEATHER_TEMPLATE]), chance)
                for w, chance, _ in struct.iter_unpack('<IiI', source[b'WLST'])]
    replace = {b'EDID': b'FNV_' + source[b'EDID'], b'TNAM': source[b'TNAM'],
               b'WLST': b''.join(struct.pack('<IiI', w, chance, 0) for w, chance in weathers if w)}
    subs = b''.join(pack_subrecord(t.decode(), replace.get(t, d)) for t, d in subrecords(templates[CLIMATE_TEMPLATE]))
    fid = builder.fnv_id(fnv)
    builder.writer.add_record('CLMT', pack_fo4_record('CLMT', fid, 0, subs))
    builder.counts['climates'] += 1
    return fid


def weather(builder, fnv: int, template: bytes) -> int:
    """Write FNV weather `fnv` as a copy of `template` with FNV's colours and fog; its FormID (0 if FNV lacks it)."""
    source = _fnv_records().get(fnv)
    if source is None:
        return 0
    replace = {b'EDID': b'FNV_' + source[b'EDID']}
    subs = b''
    for tag, data in subrecords(template):
        if tag == b'NAM0':
            data = colour_table(data, source[b'NAM0'])
        elif tag == b'FNAM':
            data = fog_table(data, source[b'FNAM'])
        subs += pack_subrecord(tag.decode('latin1'), replace.get(tag, data))
    fid = builder.fnv_id(fnv)
    builder.writer.add_record('WTHR', pack_fo4_record('WTHR', fid, 0, subs))
    builder.counts['weathers'] += 1
    return fid
