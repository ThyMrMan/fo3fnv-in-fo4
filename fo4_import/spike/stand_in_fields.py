"""Every field a creature's Fallout 4 stand-in carries, marked by what the converter does with it.

A converted creature is a copy of a Fallout 4 NPC (its stand-in, or the male body for a template actor) with
FNV's data written over it; a field nothing writes keeps the stand-in's value. Each NPC_ subrecord is:

- **keep**: the stand-in's own body, look or engine data, wanted as is (race, skin, heights, face);
- **fnv**: written from FNV; the stand-in's value surviving is a leftover;
- **drop**: the stand-in's own ties (its scripts, crime faction), never wanted;
- **open**: known to survive, its decision not made yet (abilities, perks, class).

`leftovers` raises on a field with no mark, so a stand-in with something new stops the build until someone
decides. A field whose template slot the copy takes from its template is skipped: the template's value wins.

See: docs/fork/fo4_creature_audit.md#leftover-check
"""

import struct

from fo4_import.spike.actor_data import ACBS_TEMPLATE
from tes5_import.base.tes5_reader import subrecords

KEEP, FNV, DROP, OPEN = 'keep', 'fnv', 'drop', 'open'
#: FO4 ACBS template flags, one per TPTA slot.
TRAITS, STATS, FACTIONS, SPELLS, AI_DATA, PACKAGES = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20
INVENTORY, SCRIPT, DEF_PACKS, ATTACKS, KEYWORDS = 0x100, 0x200, 0x400, 0x800, 0x1000
#: {NPC_ subrecord: (mark, template slots any of which supply it)}; each mark's reason is in the doc.
FIELDS = {
    b'EDID': (KEEP, 0), b'FULL': (KEEP, 0), b'ACBS': (KEEP, 0),
    b'AIDT': (FNV, AI_DATA), b'SNAM': (FNV, FACTIONS), b'PKID': (FNV, PACKAGES), b'ZNAM': (FNV, TRAITS | AI_DATA),
    b'INAM': (FNV, TRAITS), b'CNTO': (FNV, INVENTORY), b'COCT': (FNV, INVENTORY), b'PRPS': (FNV, STATS),
    b'TPLT': (KEEP, 0), b'TPTA': (KEEP, 0),
    b'VTCK': (KEEP, TRAITS), b'CSCR': (KEEP, TRAITS), b'DOFT': (KEEP, INVENTORY), b'SOFT': (KEEP, INVENTORY),
    b'OBND': (KEEP, 0), b'RNAM': (KEEP, TRAITS), b'WNAM': (KEEP, TRAITS), b'ANAM': (KEEP, TRAITS),
    b'ATKR': (KEEP, ATTACKS), b'ATKD': (KEEP, ATTACKS), b'ATKE': (KEEP, ATTACKS), b'ATKW': (KEEP, ATTACKS),
    b'ATKS': (KEEP, ATTACKS), b'ATKT': (KEEP, ATTACKS),
    b'APPR': (KEEP, 0), b'OBTE': (KEEP, 0), b'OBTF': (KEEP, 0), b'OBTS': (KEEP, 0), b'STOP': (KEEP, 0),
    b'DATA': (KEEP, 0), b'DNAM': (KEEP, STATS), b'MWGT': (KEEP, TRAITS), b'NAM4': (KEEP, TRAITS),
    b'NAM5': (KEEP, TRAITS), b'NAM6': (KEEP, TRAITS), b'NAM8': (KEEP, TRAITS), b'QNAM': (KEEP, TRAITS),
    b'FTST': (KEEP, TRAITS), b'HCLF': (KEEP, TRAITS), b'BCLF': (KEEP, TRAITS), b'PNAM': (KEEP, TRAITS),
    b'MSDK': (KEEP, TRAITS), b'MSDV': (KEEP, TRAITS), b'MRSV': (KEEP, TRAITS), b'FMRI': (KEEP, TRAITS),
    b'FMRS': (KEEP, TRAITS), b'TETI': (KEEP, TRAITS), b'TEND': (KEEP, TRAITS), b'NTRM': (KEEP, TRAITS),
    b'DPLT': (KEEP, DEF_PACKS), b'ECOR': (KEEP, PACKAGES),
    b'KSIZ': (KEEP, KEYWORDS), b'KWDA': (KEEP, KEYWORDS),
    b'VMAD': (DROP, SCRIPT), b'CRIF': (DROP, FACTIONS), b'SHRT': (DROP, TRAITS),
    b'SPCT': (OPEN, SPELLS), b'SPLO': (OPEN, SPELLS), b'PRKZ': (OPEN, SPELLS), b'PRKR': (OPEN, SPELLS), b'CNAM': (OPEN, STATS),
}


def _values(subs: bytes) -> dict:
    """{tag: [each value, in order]} of subrecords `subs`."""
    found = {}
    for tag, data in subrecords(subs):
        found.setdefault(tag, []).append(data)
    return found


def leftovers(stand_in: bytes, built: bytes, name: str = '') -> list:
    """The marks and tags (`'open PRKR'`) of stand-in body `stand_in`'s fields that copy `built` (its
    subrecords) still carries where its own template slots do not supply them: an `fnv` or `open` field kept
    whole, a `drop` field any of whose values survived. Raises ValueError naming `name` on a field with no mark."""
    theirs, ours = _values(stand_in), _values(built)
    unmarked = sorted(tag.decode() for tag in theirs if tag not in FIELDS)
    if unmarked:
        raise ValueError(f'{name}: stand-in fields with no mark in stand_in_fields.FIELDS: {unmarked}')
    acbs = ours.get(b'ACBS', [b''])[0]
    templated = struct.unpack_from('<H', acbs, ACBS_TEMPLATE)[0] if len(acbs) >= ACBS_TEMPLATE + 2 else 0
    found = []
    for tag, values in theirs.items():
        mark, slots = FIELDS[tag]
        if mark == KEEP or slots & templated:
            continue
        kept = any(v in values for v in ours.get(tag, ())) if mark == DROP else ours.get(tag) == values
        found += [f'{mark} {tag.decode()}'] if kept else []
    return sorted(found)


def checked(counts, stand_in: bytes, name: str, edit):
    """Clone edit `edit` counting (`stand-in leftover open PRKR`) the leftovers of copy `name` of `stand_in`."""
    def run(subs: bytes) -> bytes:
        """`edit`'s subrecords, their leftovers counted."""
        built = edit(subs)
        for found in leftovers(stand_in, built, name):
            counts[f'stand-in leftover {found}'] += 1
        return built
    return run
