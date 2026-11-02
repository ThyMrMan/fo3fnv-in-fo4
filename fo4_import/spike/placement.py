"""FNV reference subrecords FO4 keeps, read from FalloutNV.esm: bounds, primitive, portal rooms, ragdoll, parents,
ownership, item count (XCNT), open by default (ONAM) and an occlusion plane's size and linked planes (XOCP,
XORD), all in FNV's layout.

The export writes a reference's XPRM but not XMBO (a room marker's bound
half extents), XPOD (a portal's origin and destination rooms) or XRGD (the
bone pose of a ragdolled object, such as a lying skeleton). Fallout 4 has
all four in FNV's layout, so they are copied from the plugin itself, read
once per build; a portal's rooms are renumbered as every reference is.
A portal keeps no XMBO, as none of Fallout4.esm's 1,725 portals has one, and
neither does a trigger box (an activator's primitive): none of its 5,335 do.
An owner (XOWN, FNV's 4 bytes in FO4's 12) is its converted faction or NPC;
an owner not converted is dropped with its faction rank (XRNK).

See: docs/fork/fo4_pipeline.md#rooms
"""

import functools
import struct

from fo4_import.base.install import source_walk
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: The subrecords copied, in FO4's REFR order.
KEPT = (b'XMBO', b'XPRM', b'XPOD', b'XORD', b'XOCP', b'XRGD', b'XRDS', b'XAPD', b'XAPR', b'XOWN', b'XRNK', b'XESP', b'XCNT', b'XPRD',
        b'ONAM', b'XMRK', b'FNAM', b'FULL', b'TNAM')
#: Patrol data after XPRD as all 7,684 vanilla points write it: flag, no idle, then a PDTO (none crashes FO4).
PATROL_REST = pack_subrecord('XPPA', b'') + pack_subrecord('INAM', bytes(4))
#: A map marker's fields, kept only on a reference with XMRK (FNV uses TNAM and XRDS elsewhere too).
MARKER = (b'XRDS', b'FNAM', b'FULL', b'TNAM')
#: FNV map marker type -> FO4's of the same kind (FNV's None, unused, as Natural Landmark).
MARKER_TYPES = {1: 1, 2: 13, 3: 3, 4: 8, 5: 0, 6: 4, 7: 5, 8: 7, 9: 9, 10: 10, 11: 11, 12: 14, 13: 6, 14: 15}
#: Subrecords that start with a reference: dropped when it is not built (an activate parent may repeat).
REFERRING = (b'XAPR', b'XESP')
#: Ownership subrecords: kept only with an owner that converts.
OWNERSHIP = (b'XOWN', b'XRNK')
#: Cell children group types (child, persistent, temporary, visible distant): a reference's cell is their label.
CELL_CHILDREN = (6, 8, 9, 10)
#: FormIDs below this are engine forms both games share (the player, 0x14).
ENGINE_FORMS = 0x800
#: A reference's record flag Initially Disabled, in both games.
INITIALLY_DISABLED = 0x800


@functools.cache
def _activators() -> frozenset:
    """FNV FormIDs of the activators (ACTI, TACT), trigger boxes' bases."""
    return frozenset(rec.form_id for rec, _ in source_walk(b'ACTI', b'TACT'))


def _room_bound(subs: list) -> bool:
    """Whether a reference's subrecords hold an XMBO not on a trigger box.
    See: docs/fork/fo4_pipeline.md#rooms
    """
    tags = dict(subs)
    return b'XMBO' in tags and (b'NAME' not in tags or struct.unpack('<I', tags[b'NAME'])[0] not in _activators())


@functools.cache
def _scan() -> tuple:
    """({FNV reference FormID: [(tag, data)]} of the references and actors holding any KEPT subrecord,
    {FormID: record flags} of all of them), read once from FalloutNV.esm; a trigger box's XMBO left out."""
    out, flags = {}, {}
    for rec, _ in source_walk(b'REFR', b'ACHR', b'ACRE'):
        flags[rec.form_id] = rec.flags
        subs = list(subrecords(rec.body))
        found = [(tag, data) for tag, data in subs if tag in KEPT and (tag != b'XMBO' or _room_bound(subs))]
        if found:
            out[rec.form_id] = found
    return out, flags


def fields() -> dict:
    """_scan()'s {FNV reference FormID: [(KEPT tag, data)]}."""
    return _scan()[0]


def _parent(fnv_fid: int) -> tuple:
    """(enable parent FormID or 0, opposite-state bit) of FNV reference `fnv_fid`."""
    data = dict(fields().get(fnv_fid, ())).get(b'XESP')
    return (struct.unpack_from('<I', data)[0], data[4] & 1) if data else (0, 0)


def _disabled_at_start(fnv_fid: int, seen: frozenset = frozenset()) -> bool:
    """Whether FNV reference `fnv_fid` starts disabled: as its enable parent starts (flipped by the opposite bit),
    else by its own flag."""
    parent, opposite = _parent(fnv_fid)
    if parent and parent not in seen:
        return _disabled_at_start(parent, seen | {fnv_fid}) != bool(opposite)
    return bool(_scan()[1].get(fnv_fid, 0) & INITIALLY_DISABLED)


def starts_disabled(ref: dict, ids: dict) -> bool:
    """Whether FNV reference `ref` is placed disabled: its own flag, or, when its enable parent is not built
    (placement() drops it), the state that parent's chain gives it at the start.
    See: docs/fork/fo4_pipeline.md#parents
    """
    fid = int(ref['FormID'], 16)
    parent = _parent(fid)[0]
    if parent and not _renumbered(parent, ids):
        return _disabled_at_start(fid)
    return bool(int(ref['RecordFlags']) & INITIALLY_DISABLED)


@functools.cache
def open_rooms() -> frozenset:
    """FNV FormIDs of the room markers and portals in cells where a portal leads to no room: left out, so FO4 draws
    the whole cell (a corpse settling outside every room stays culled with the room it left).
    See: docs/fork/fo4_pipeline.md#rooms
    """
    rooms, open_cells = {}, set()
    for rec, stack in source_walk(b'REFR'):
        listed = list(subrecords(rec.body))
        subs = dict(listed)
        cell = next((g.label for g in reversed(stack.groups) if g.type in CELL_CHILDREN), None)
        if _room_bound(listed) or b'XPOD' in subs:
            rooms.setdefault(cell, []).append(rec.form_id)
        if 0 in struct.unpack_from('<2I', subs.get(b'XPOD', b'\1' * 8)):
            open_cells.add(cell)
    return frozenset(fid for cell in open_cells for fid in rooms[cell])


def owned(found: list, owners: dict) -> 'bytes | None':
    """FO4 XOWN data of the owner in `found` through `owners`; None if none."""
    fnv = next((struct.unpack_from('<I', d)[0] for t, d in found if t == b'XOWN'), None)
    return struct.pack('<I', owners[fnv]) + bytes(8) if fnv in owners else None


def _renumbered(ref: int, ids: dict) -> int:
    """FNV reference `ref` through `ids` (engine forms kept; 0: not built)."""
    return ref if ref < ENGINE_FORMS else ids.get(f'{ref:08X}', 0)


def _field(tag: bytes, data: bytes, ids: dict, owner: 'bytes | None') -> 'bytes | None':
    """FO4 data of one KEPT field: rooms renumbered, owner `owner`; None when its reference or owner is not built."""
    if tag == b'XOWN' or tag in OWNERSHIP and owner is None:
        return owner
    if tag == b'TNAM':
        return bytes([MARKER_TYPES.get(data[0], MARKER_TYPES[4])]) + data[1:2]
    if tag in (b'XPOD', b'XORD'):
        count = len(data) // 4
        return struct.pack(f'<{count}I', *(ids.get(f'{ref:08X}', 0) for ref in struct.unpack(f'<{count}I', data)))
    if tag in REFERRING:
        parent = _renumbered(struct.unpack_from('<I', data)[0], ids)
        return struct.pack('<I', parent) + data[4:] if parent else None
    return data


def _patrol_rest(fnv_fid: int, arrivals: dict) -> bytes:
    """XPPA, INAM and a PDTO naming the point's `arrivals` topic (else 0)."""
    return PATROL_REST + pack_subrecord('PDTO', struct.pack('<II', 0, arrivals.get(fnv_fid, 0)))


def placement(fnv_fid: int, ids: dict, owners: dict = None, pose: bool = True, arrivals: dict = None) -> bytes:
    """FO4 subrecords of FNV reference `fnv_fid`'s KEPT fields, references through `ids` {FNV hex: FO4}.

    Portal rooms are renumbered; an enable or activate parent not built is dropped; an owner maps through
    `owners` {FNV FormID: FO4}, else it and its rank drop; a map marker keeps its flags, name, type and
    radius. Without `pose` XRGD drops (FNV ragdoll bones). A patrol point's PDTO is its `arrivals` topic.
    See: docs/fork/fo4_pipeline.md#parents
    See: docs/fork/fo4_pipeline.md#patrol-points
    """
    found = fields().get(fnv_fid, [])
    owner, portal = owned(found, owners or {}), any(t == b'XPOD' for t, _ in found)
    marker, out = any(t == b'XMRK' for t, _ in found), b''
    for tag, data in sorted(found, key=lambda f: KEPT.index(f[0])):
        skip = tag == b'XMBO' and portal or tag in MARKER and not marker or tag == b'XRGD' and not pose
        kept = None if skip else _field(tag, data, ids, owner)
        out += pack_subrecord(tag.decode(), kept) if kept is not None else b''
        out += _patrol_rest(fnv_fid, arrivals or {}) if tag == b'XPRD' else b''
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
