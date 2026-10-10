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

from fo4_import.base.install import FALLOUTNV_ESM
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The subrecords copied, in FO4's REFR order.
KEPT = (b'XMBO', b'XPRM', b'XPOD', b'XRGD')


@functools.cache
def fields() -> dict:
    """{FNV reference FormID: {tag: data}} of FalloutNV.esm's references holding any KEPT subrecord."""
    out = {}
    for rec, _ in walk(FALLOUTNV_ESM.read_bytes(), b'REFR'):
        found = {tag: data for tag, data in subrecords(rec.body) if tag in KEPT}
        if found:
            out[rec.form_id] = found
    return out


def placement(fnv_fid: int, ids: dict) -> bytes:
    """FO4 subrecords of FNV reference `fnv_fid`'s KEPT fields; a portal's rooms through `ids` {FNV hex: FO4}."""
    found, out = fields().get(fnv_fid, {}), b''
    for tag in KEPT:
        data = found.get(tag)
        if data is None or (tag == b'XMBO' and b'XPOD' in found):
            continue
        if tag == b'XPOD':
            data = struct.pack('<2I', *(ids.get(f'{room:08X}', 0) for room in struct.unpack('<2I', data)))
        out += pack_subrecord(tag.decode(), data)
    return out
