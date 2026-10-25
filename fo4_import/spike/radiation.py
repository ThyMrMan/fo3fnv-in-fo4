"""FNV radioactive references (XRAD) as Fallout 4's: a vanilla radiation hazard placed where the reference stands.

FNV gives a reference a radiation rate (XRAD, rads a second) over its radius
(XRDS). FO4 has no such field: it places hazards (PHZD), 981 in
Fallout4.esm, nearly all its generic RadiationHazard<grade><radius> (Light,
Strong, Deadly; 256 to 2048 units). Their spells deal 1, 3 and 6 a tick
(with 10, 30 and 60 beside). A radioactive reference gets the hazard whose
grade is nearest its rate and whose radius is nearest its own (256 without
one), at its position, persistent and initially disabled as it is. XRAD and XRDS are read from
FalloutNV.esm.

See: docs/fork/fo4_pipeline.md#radiation
"""

import functools
import re
import struct

from fo4_import.base.install import source_esm
from fo4_import.spike import records as R
from fo4_import.spike.placement import place, starts_disabled
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

#: Fallout4.esm's generic hazards by name, and each grade's per-tick radiation.
HAZARD = re.compile(r'RadiationHazard(Light|Strong|Deadly)(\d+)$')
GRADES = {'Light': 1.0, 'Strong': 3.0, 'Deadly': 6.0}
#: A radioactive reference's radius when FNV gives none (the smallest hazard's).
DEFAULT_RADIUS = 256
#: ledger site of a placed hazard (key: the FNV reference).
HAZARD_SITE = 'FNV radiation hazard'


@functools.cache
def radioactive() -> dict:
    """{FNV reference FormID: (rads a second, radius or None)} of FalloutNV.esm's references with XRAD."""
    out = {}
    for rec, _ in walk(source_esm(), b'REFR'):
        subs = dict(subrecords(rec.body))
        if b'XRAD' in subs:
            radius = struct.unpack('<f', subs[b'XRDS'])[0] if b'XRDS' in subs else None
            out[rec.form_id] = (struct.unpack('<f', subs[b'XRAD'])[0], radius)
    return out


def hazards(fo4: bytes) -> dict:
    """{(grade, radius): FormID} of Fallout4.esm's generic radiation hazards."""
    out = {}
    for rec, _ in walk(fo4, b'HAZD'):
        found = HAZARD.match((first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode())
        if found:
            out[(found[1], int(found[2]))] = rec.form_id
    return out


def nearest(table: dict, rate: float, radius: 'float | None') -> int:
    """The hazard of `table` (hazards()) nearest FNV rate `rate` and radius `radius`."""
    grade = min(GRADES, key=lambda g: abs(GRADES[g] - rate))
    sizes = [r for g, r in table if g == grade]
    size = min(sizes, key=lambda r: abs(r - (radius or DEFAULT_RADIUS)))
    return table[(grade, size)]


def hazard_ref(builder, ref: dict, persistent: bool) -> bytes:
    """The PHZD placing FNV reference `ref`'s radiation, persistent as `persistent`; b'' when it has none."""
    found = radioactive().get(int(ref['FormID'], 16))
    if not found:
        return b''
    builder.hazards = builder.hazards or hazards(builder.fo4)
    fid = builder.writer.derive_formid(HAZARD_SITE, ref['FormID'])
    builder.counts['radiation hazards'] += 1
    return R.pack_refr(fid, nearest(builder.hazards, *found), *place(ref), persistent=persistent,
                       disabled=starts_disabled(ref, builder.ref_ids), sig='PHZD')
