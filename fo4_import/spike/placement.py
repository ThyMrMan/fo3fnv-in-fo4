"""FNV reference subrecords FO4 keeps as they are, read from FalloutNV.esm: bounds, primitive, portal rooms, ragdoll.

The export writes a reference's XPRM but not XMBO (a room marker's bound
half extents), XPOD (a portal's origin and destination rooms) or XRGD (the
bone pose of a ragdolled object, such as a lying skeleton). Fallout 4 has
all four in FNV's layout, so they are copied from the plugin itself, read
once per build; a portal's rooms are renumbered as every reference is.
A portal keeps no XMBO, as none of Fallout4.esm's 1,725 portals has one.

See: docs/fork/fo4_pipeline.md#rooms
"""

import functools
import struct

from fo4_import.base.install import fnv_esm
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The subrecords copied, in FO4's REFR order.
KEPT = (b'XMBO', b'XPRM', b'XPOD', b'XRGD', b'XAPD', b'XAPR', b'XESP')
#: Subrecords that start with a reference: dropped when it is not built (an activate parent may repeat).
REFERRING = (b'XAPR', b'XESP')
#: FormIDs below this are engine forms both games share (the player, 0x14).
ENGINE_FORMS = 0x800


@functools.cache
def fields() -> dict:
    """{FNV reference FormID: [(tag, data)]} of FalloutNV.esm's references and actors holding any KEPT subrecord."""
    out = {}
    for rec, _ in walk(fnv_esm(), b'REFR', b'ACHR', b'ACRE'):
        found = [(tag, data) for tag, data in subrecords(rec.body) if tag in KEPT]
        if found:
            out[rec.form_id] = found
    return out


def _renumbered(ref: int, ids: dict) -> int:
    """FO4 FormID of FNV reference `ref` through `ids` {FNV hex: FO4}; engine forms as they are, 0 if not built."""
    return ref if ref < ENGINE_FORMS else ids.get(f'{ref:08X}', 0)


def placement(fnv_fid: int, ids: dict) -> bytes:
    """FO4 subrecords of FNV reference `fnv_fid`'s KEPT fields, references through `ids` {FNV hex: FO4}.

    A portal's rooms are renumbered; an enable or activate parent that is not built is dropped.
    See: docs/fork/fo4_pipeline.md#parents
    """
    found = fields().get(fnv_fid, [])
    tags, out = {tag for tag, _ in found}, b''
    for tag in KEPT:
        for data in (d for t, d in found if t == tag):
            if tag == b'XMBO' and b'XPOD' in tags:
                continue
            if tag == b'XPOD':
                data = struct.pack('<2I', *(ids.get(f'{room:08X}', 0) for room in struct.unpack('<2I', data)))
            elif tag in REFERRING:
                parent = _renumbered(struct.unpack_from('<I', data)[0], ids)
                if not parent:
                    continue
                data = struct.pack('<I', parent) + data[4:]
            out += pack_subrecord(tag.decode(), data)
    return out
