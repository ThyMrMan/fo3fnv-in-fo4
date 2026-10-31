"""FNV's weather imagespace modifiers as FO4 weather imagespaces, one per FNV time of day.

FNV grades an exterior with its worldspace's imagespace (WRLD INAM;
NVDefaultExterior for 12 of FNV's 14 worldspaces) and the weather's
modifier for the time of day (WTHR IAD 0 to 3: sunrise, day, sunset,
night). A weather's modifiers are not animatable, so each holds its first
key (the GECK: the duration is then ignored). What carries is the tint:
the modifier's and the imagespace's own (its flags aside) average by their
amounts, and the larger amount applies (the GECK's rule). That matches
FNV's measured hues: amber by day, near-neutral grey at night. The
modifiers' saturation, contrast and brightness do not carry (FNV's measured
levels fit without them). Each pair (imagespace, modifier) becomes one FO4
imagespace through imagespace.py: FNV's tone and that grading in a LUT,
exposure fixed, on the vanilla weather's own imagespace for that time
(exterior depth of field). FNV's IMGS and IMAD values are read from
FalloutNV.esm (the export keeps IMAD's sizes only).

See: docs/fork/fo4_look.md#weather-imagespace
"""

import functools
import struct
from dataclasses import replace

from fo4_import.base.install import source_walk
from fo4_import.spike.imagespace import Cinematic, base_hdr, cinematic, own_tint, pack_imgs, write_lut
from tes5_import.base.tes5_reader import subrecords, walk

#: derive_formid site of a weather imagespace (key: (FNV imagespace FormID, FNV modifier FormID)).
SITE = 'FNV weather imagespace'
#: FNV's times of day with a weather modifier (WTHR IAD 0 to 3): sunrise, day, sunset, night.
TIMES = 4

@functools.cache
def _fnv(sig: bytes) -> dict:
    """{FormID: {tag: data}} of FalloutNV.esm's `sig` records (WRLD, IMGS, IMAD)."""
    return {r.form_id: dict(subrecords(r.body)) for r, _ in source_walk(sig)}


def world_imagespace(world: int) -> int:
    """FNV worldspace `world`'s exterior imagespace (WRLD INAM); 0 for none."""
    inam = _fnv(b'WRLD').get(world, {}).get(b'INAM')
    return struct.unpack('<I', inam)[0] if inam else 0


def tinted(base: Cinematic, own: tuple, imad: dict) -> Cinematic:
    """FNV imagespace grading `base` with the tint of its own (`own`: colour, amount, from own_tint) and modifier
    `imad`'s ({tag: data}, first key) averaged by their amounts, the larger amount applied (the GECK's rule)."""
    tint = struct.unpack_from('<5f', imad[b'TNAM'])[1:] if b'TNAM' in imad else (0.0, 0.0, 0.0, 0.0)
    (colour, amount), weight = own, own[1] + tint[3]
    mixed = tuple((c * amount + m * tint[3]) / weight for c, m in zip(colour, tint[:3])) if weight else colour
    return replace(base, tint=mixed, tint_amount=max(amount, tint[3]))


def _vanilla_body(builder, fid: int) -> bytes:
    """Fallout4.esm imagespace `fid`'s record body, read once per build."""
    if fid not in builder.weather_templates:
        builder.weather_templates[fid] = next(r.body for r, _ in walk(builder.fo4, b'IMGS') if r.form_id == fid)
    return builder.weather_templates[fid]


def _imagespace(builder, base: int, imad: int, template: int) -> int:
    """The FO4 imagespace of FNV imagespace `base` under modifier `imad` (0: none), on vanilla exterior imagespace
    `template` (its depth of field, bloom and HDR), written once per build."""
    key = (base, imad)
    if key not in builder.weather_imagespaces:
        body = _vanilla_body(builder, template)
        source = _fnv(b'IMGS')[base]
        modifier = _fnv(b'IMAD').get(imad, {})
        edid = 'FNV_' + '_'.join(r[b'EDID'].rstrip(b'\0').decode() for r in (source, modifier) if r)
        grading = tinted(cinematic(source[b'DNAM']), own_tint(source[b'DNAM']), modifier)
        lut = write_lut(grading, edid, builder.data_dir, base_hdr(body))
        fid = builder.writer.derive_formid(SITE, key)
        builder.writer.add_record('IMGS', pack_imgs(fid, edid, body, lut))
        builder.weather_imagespaces[key] = fid
        builder.counts['weather imagespaces'] += 1
    return builder.weather_imagespaces[key]


def weather_imagespaces(builder, weather: dict, templates: tuple) -> 'list | None':
    """FNV weather `weather`'s ({tag: data}) FO4 imagespaces for sunrise, day, sunset and night, under the
    worldspace's FNV imagespace (`builder.world_imagespace`), each on the vanilla weather's imagespace for that
    time (`templates`, its IMSP's first four); None when the worldspace names none."""
    base = builder.world_imagespace
    if base not in _fnv(b'IMGS'):
        return None
    imads = [struct.unpack('<I', weather[bytes([t]) + b'IAD'])[0] if bytes([t]) + b'IAD' in weather else 0
             for t in range(TIMES)]
    return [_imagespace(builder, base, imad, template) for imad, template in zip(imads, templates)]
