"""A master plugin file's bytes in its dependent's FormID numbering (master_space's map), read by install's stack.

Every record's FormID, every group labelled by a FormID (a world's, cell's or topic's children) and every subrecord
FormID data/<game>_subrecord_formids.json places (from xEdit's definitions, tools/generators/
gen_fnv_subrecord_formids.py) is renumbered, a union's by its selector field; conditions by xEdit's parameter
types, alternate texture lists by their entries, ownership by owner_data, script data (VMAD) by dangling_scripts'
walker. A compressed record is written inflated. Any other subrecord the table calls complex or does not name, and
script data the walker cannot follow, is left as is and counted in master_space.UNCLASSIFIED.

See: docs/fork/fo4_plugin_layout.md#multi-master
"""

import functools
import json
import struct
from pathlib import Path

from fo4_import.base.dangling_scripts import Unreadable, object_offsets
from fo4_import.pipeline.master_space import UNCLASSIFIED, condition_bytes, renumber
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, decompress, header_end

DATA = Path(__file__).resolve().parents[1] / 'data'
#: A record or group header's size.
HEADER = 24
#: GRUP types whose label is a FormID: world, cell and topic children, a cell's persistent, temporary, distant.
FORMID_LABELS = frozenset({1, 6, 7, 8, 9, 10})
#: Subrecord header: signature, u16 size; XXXX carries the next one's u32 size.
SUB = struct.Struct('<4sH')


@functools.cache
def layouts(game: str) -> dict:
    """{record sig: {subrecord sig: layout}} for `game` (fnv, fo3), sigs as bytes."""
    raw = json.loads((DATA / f'{game}_subrecord_formids.json').read_text(encoding='utf-8'))
    return {rec.encode('latin1'): {sub.encode('latin1'): v for sub, v in subs.items()} for rec, subs in raw.items()}


def renumbered(raw: bytes, mapping: tuple, game: str) -> bytes:
    """Plugin bytes `raw` with every FormID through `mapping`."""
    start = header_end(raw)
    return raw[:start] + Renumbering(mapping, game).span(raw, start, len(raw))


class Renumbering:
    """One master's records rewritten through one FormID map."""

    def __init__(self, mapping: tuple, game: str):
        """`mapping`: master index -> dependent's; `game`: fnv or fo3."""
        self.mapping, self.game, self.table = mapping, game, layouts(game)

    def span(self, raw: bytes, pos: int, end: int) -> bytes:
        """The records and groups in raw[pos:end], renumbered."""
        out = bytearray()
        while pos < end:
            size = struct.unpack_from('<I', raw, pos + 4)[0]
            if raw[pos:pos + 4] == b'GRUP':
                label, kind = struct.unpack_from('<II', raw, pos + 8)
                inner = self.span(raw, pos + HEADER, pos + size)
                head = bytearray(raw[pos:pos + HEADER])
                struct.pack_into('<I', head, 4, HEADER + len(inner))
                if kind in FORMID_LABELS:
                    struct.pack_into('<I', head, 8, renumber(label, self.mapping))
                out += head + inner
                pos += size
            else:
                out += self.record(raw, pos, size)
                pos += HEADER + size
        return bytes(out)

    def record(self, raw: bytes, pos: int, size: int) -> bytes:
        """One record renumbered, inflated if it was compressed."""
        sig = raw[pos:pos + 4]
        flags, fid = struct.unpack_from('<II', raw, pos + 8)
        body = self.subrecords(sig, decompress(raw[pos + HEADER:pos + HEADER + size], flags))
        head = bytearray(raw[pos:pos + HEADER])
        struct.pack_into('<III', head, 4, len(body), flags & ~FLAG_COMPRESSED, renumber(fid, self.mapping))
        return bytes(head) + body

    def subrecords(self, sig: bytes, body: bytes) -> bytes:
        """Record `sig`'s body with each subrecord's FormIDs renumbered by its layout."""
        subs, out, pos, big, seen = self.table.get(sig, {}), bytearray(), 0, None, {}
        while pos + SUB.size <= len(body):
            tag, length = SUB.unpack_from(body, pos)
            pos += SUB.size
            if tag == b'XXXX':
                big = struct.unpack_from('<I', body, pos)[0]
                pos += length
                continue
            length, big = (length if big is None else big), None
            data = self.data(sig, tag, body[pos:pos + length], subs.get(tag), seen)
            seen[tag] = body[pos:pos + length]
            big_head = SUB.pack(b'XXXX', 4) + struct.pack('<I', len(data)) + SUB.pack(tag, 0)
            out += (big_head if len(data) > 0xFFFF else SUB.pack(tag, len(data))) + data
            pos += length
        return bytes(out)

    def data(self, sig: bytes, tag: bytes, data: bytes, layout, seen: dict) -> bytes:
        """One subrecord's data renumbered by `layout` (`seen`: the record's earlier subrecords by tag); a complex
        or unnamed one counted and kept."""
        if layout == 'none' or not data:
            return data
        if isinstance(layout, dict):
            return placed(data, self.mapping, {**layout, 'at': offsets(layout, data, seen)})
        if layout == 'owner_data':
            return self.owner_data(sig, data)
        if layout == 'condition':
            return condition_bytes(data, self.mapping, self.game)
        if layout == 'alt_textures':
            return alt_textures(data, self.mapping)
        if layout == 'complex' and tag == b'VMAD':
            return self.vmad(sig, data)
        UNCLASSIFIED[f'{sig.decode("latin1")}.{tag.decode("latin1")} ({layout or "not in the table"})'] += 1
        return data

    def vmad(self, sig: bytes, data: bytes) -> bytes:
        """Script data with every object's FormID renumbered (dangling_scripts' walker); one it cannot walk
        counted and kept.
        See: docs/fork/fo4_plugin_layout.md#multi-master-scripts
        """
        try:
            return placed(data, self.mapping, {'at': object_offsets(sig, data)})
        except (Unreadable, struct.error, IndexError):
            UNCLASSIFIED[f'{sig.decode("latin1")}.VMAD (script data not walked)'] += 1
            return data

    def owner_data(self, sig: bytes, data: bytes) -> bytes:
        """COED: owner at 0; at 4 a global (NPC owner) or a rank (faction), renumbered when the map keeps index 0.
        See: docs/fork/fo4_plugin_layout.md#multi-master
        """
        if self.mapping[:1] == (0,):
            return placed(data, self.mapping, {'at': [0, 4]})
        UNCLASSIFIED[f'{sig.decode("latin1")}.COED (global or rank, map moves index 0)'] += 1
        return placed(data, self.mapping, {'at': [0]})


def placed(data: bytes, mapping: tuple, layout: dict) -> bytes:
    """`data` with a FormID at each of `layout`'s offsets (in every `stride`-byte entry after `start`)."""
    out = bytearray(data)
    stride, start = layout.get('stride', 0), layout.get('start', 0)
    bases = range(start, len(out) - stride + 1, stride) if stride else (0,)
    for base in bases:
        for at in layout['at']:
            if base + at + 4 <= len(out):
                struct.pack_into('<I', out, base + at, renumber(struct.unpack_from('<I', out, base + at)[0], mapping))
    return bytes(out)


def offsets(layout: dict, data: bytes, seen: dict) -> list:
    """`layout`'s FormID offsets: its own, and each case's whose values hold its selector (`data`'s bytes, or an
    earlier subrecord's in `seen`); none while the selector subrecord has not been seen."""
    select = layout.get('select')
    if select is None:
        return layout['at']
    source = seen.get(select['sub'].encode('latin1'), b'') if 'sub' in select else data
    raw = source[select['at']:select['at'] + select['size']]
    value = int.from_bytes(raw, 'little') if len(raw) == select['size'] else None
    return [*layout['at'], *(at for case in layout['cases'] if value in case['in'] for at in case['at'])]


def alt_textures(data: bytes, mapping: tuple) -> bytes:
    """An alternate texture list (u32 count; each: u32 name length, name, texture set FormID, s32 index) renumbered."""
    out, pos = bytearray(data), 4
    for _ in range(struct.unpack_from('<I', data)[0] if len(data) >= 4 else 0):
        pos += 4 + struct.unpack_from('<I', data, pos)[0]
        struct.pack_into('<I', out, pos, renumber(struct.unpack_from('<I', data, pos)[0], mapping))
        pos += 8
    return bytes(out)
