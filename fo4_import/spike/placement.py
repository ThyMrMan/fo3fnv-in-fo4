"""FNV reference subrecords FO4 keeps, read from FalloutNV.esm: bounds, primitive, portal rooms, ragdoll, parents,
ownership.

The export writes a reference's XPRM but not XMBO (a room marker's bound
half extents), XPOD (a portal's origin and destination rooms) or XRGD (the
bone pose of a ragdolled object, such as a lying skeleton). Fallout 4 has
all four in FNV's layout, so they are copied from the plugin itself, read
once per build; a portal's rooms are renumbered as every reference is.
A portal keeps no XMBO, as none of Fallout4.esm's 1,725 portals has one.
An owner (XOWN, FNV's 4 bytes in FO4's 12) is its converted faction or NPC;
an owner not converted is dropped with its faction rank (XRNK).

See: docs/fork/fo4_pipeline.md#rooms
"""

import functools
import struct

from fo4_import.base.install import source_esm
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The subrecords copied, in FO4's REFR order.
KEPT = (b'XMBO', b'XPRM', b'XPOD', b'XRGD', b'XRDS', b'XAPD', b'XAPR', b'XOWN', b'XRNK', b'XESP', b'XPRD', b'XMRK', b'FNAM', b'FULL', b'TNAM')
#: Patrol data after XPRD as all 7,684 vanilla points write it: flag, no idle, no topic (no PDTO crashes FO4).
PATROL_REST = pack_subrecord('XPPA', b'') + pack_subrecord('INAM', bytes(4)) + pack_subrecord('PDTO', bytes(8))
#: A map marker's fields, kept only on a reference with XMRK (FNV uses TNAM and XRDS elsewhere too).
MARKER = (b'XRDS', b'FNAM', b'FULL', b'TNAM')
#: FNV map marker type -> FO4's of the same kind (FNV's None, unused, as Natural Landmark).
MARKER_TYPES = {1: 1, 2: 13, 3: 3, 4: 8, 5: 0, 6: 4, 7: 5, 8: 7, 9: 9, 10: 10, 11: 11, 12: 14, 13: 6, 14: 15}
#: Subrecords that start with a reference: dropped when it is not built (an activate parent may repeat).
REFERRING = (b'XAPR', b'XESP')
#: Ownership subrecords: kept only with an owner that converts.
OWNERSHIP = (b'XOWN', b'XRNK')
#: FormIDs below this are engine forms both games share (the player, 0x14).
ENGINE_FORMS = 0x800


@functools.cache
def fields() -> dict:
    """{FNV reference FormID: [(tag, data)]} of FalloutNV.esm's references and actors holding any KEPT subrecord."""
    out = {}
    for rec, _ in walk(source_esm(), b'REFR', b'ACHR', b'ACRE'):
        found = [(tag, data) for tag, data in subrecords(rec.body) if tag in KEPT]
        if found:
            out[rec.form_id] = found
    return out


def owned(found: list, owners: dict) -> 'bytes | None':
    """FO4 XOWN data of the owner in `found` through `owners`; None if none."""
    fnv = next((struct.unpack_from('<I', d)[0] for t, d in found if t == b'XOWN'), None)
    return struct.pack('<I', owners[fnv]) + bytes(8) if fnv in owners else None


def _renumbered(ref: int, ids: dict) -> int:
    """FO4 FormID of FNV reference `ref` through `ids` {FNV hex: FO4}; engine forms as they are, 0 if not built."""
    return ref if ref < ENGINE_FORMS else ids.get(f'{ref:08X}', 0)


def _field(tag: bytes, data: bytes, ids: dict, owner: 'bytes | None') -> 'bytes | None':
    """FO4 data of one KEPT field: rooms renumbered, owner `owner`; None when its reference or owner is not built."""
    if tag == b'XOWN' or tag in OWNERSHIP and owner is None:
        return owner
    if tag == b'TNAM':
        return bytes([MARKER_TYPES.get(data[0], MARKER_TYPES[4])]) + data[1:2]
    if tag == b'XPOD':
        return struct.pack('<2I', *(ids.get(f'{room:08X}', 0) for room in struct.unpack('<2I', data)))
    if tag in REFERRING:
        parent = _renumbered(struct.unpack_from('<I', data)[0], ids)
        return struct.pack('<I', parent) + data[4:] if parent else None
    return data


def placement(fnv_fid: int, ids: dict, owners: dict = None) -> bytes:
    """FO4 subrecords of FNV reference `fnv_fid`'s KEPT fields, references through `ids` {FNV hex: FO4}.

    A portal's rooms are renumbered; an enable or activate parent that is not built is dropped; an owner maps
    through `owners` {FNV FormID: FO4}, and without one so is its rank; a map marker keeps its flags, name,
    type (MARKER_TYPES) and discovery radius.
    See: docs/fork/fo4_pipeline.md#parents
    """
    found = fields().get(fnv_fid, [])
    owner, portal = owned(found, owners or {}), any(t == b'XPOD' for t, _ in found)
    marker, out = any(t == b'XMRK' for t, _ in found), b''
    for tag, data in sorted(found, key=lambda f: KEPT.index(f[0])):
        skip = tag == b'XMBO' and portal or tag in MARKER and not marker
        kept = None if skip else _field(tag, data, ids, owner)
        out += pack_subrecord(tag.decode(), kept) if kept is not None else b''
        out += PATROL_REST if tag == b'XPRD' else b''
    return out


def map_markers(ids: dict) -> dict:
    """{map marker name: FO4 reference} of the built markers (through `ids` {FNV hex: FO4}), first by FormID."""
    out = {}
    for fnv, found in sorted(fields().items()):
        tags = dict(found)
        if b'XMRK' in tags and b'FULL' in tags and f'{fnv:08X}' in ids:
            out.setdefault(tags[b'FULL'].rstrip(b'\0').decode('cp1252'), ids[f'{fnv:08X}'])
    return out


def place(rec: dict, prefix: str = '') -> tuple:
    """(position, rotation) of an exported reference; 'XTEL.' for its teleport."""
    return (tuple(float(rec[prefix + k]) for k in ('PosX', 'PosY', 'PosZ')),
            tuple(float(rec[prefix + k]) for k in ('RotX', 'RotY', 'RotZ')))
