"""Display text in a written Fallout 4 plugin stored as UTF-8, the encoding Fallout 4's menus read it in.

Every converter writes text as cp1252, the encoding of FO3/FNV, Skyrim and Fallout4.esm's own English strings. FO4
passes a plugin's text bytes to its menus as UTF-8, so a lone byte above 0x7F (cp1252's ’ is 0x92) draws as a box.
The writer re-encodes each display-text subrecord as it writes the file (FO4PluginWriter._finish_groups), the one
place every record passes. Which subrecords are text comes from xEdit's FO4 definitions: data/fo4_text_subrecords.json,
made by tools/generators/gen_fnv_subrecord_formids.py --text.

See: docs/fork/fo4_pipeline.md#text-encoding
"""

import json
import re
from pathlib import Path

from fo4_import.base.group_walk import HEADER, records, replace_bodies
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: {record signature: display-text subrecord signatures}.
TEXT = {rec.encode(): frozenset(sub.encode() for sub in subs) for rec, subs in json.loads(
    (Path(__file__).resolve().parents[1] / 'data' / 'fo4_text_subrecords.json').read_text(encoding='utf-8')).items()}
#: The record flag Compressed: such a body is zlib data, not subrecords.
FLAG_COMPRESSED = 0x40000
#: A byte outside ASCII.
HIGH = re.compile(rb'[\x80-\xff]')
#: cp1252's 0x80-0x9F; the 5 bytes it leaves undefined keep their Latin-1 code point, as Windows converts them.
CP1252 = {b: bytes([b]).decode('cp1252') for b in range(0x80, 0xA0) if b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)}


def utf8(data: bytes) -> bytes:
    """cp1252 text `data` as UTF-8; UTF-8 (or ASCII) already is returned unchanged."""
    try:
        data.decode('utf-8')
        return data
    except UnicodeDecodeError:
        return data.decode('latin-1').translate(CP1252).encode('utf-8')


def _body(sig: bytes, body: bytes) -> 'bytes | None':
    """Record `sig`'s `body` with its display text as UTF-8; None when nothing changes."""
    wanted = TEXT[sig]
    if not any(tag in body for tag in wanted):
        return None
    subs = subrecords(body)
    out = [(tag, utf8(data) if tag in wanted and HIGH.search(data) else data) for tag, data in subs]
    if all(new is old for (_, new), (_, old) in zip(out, subs)):
        return None
    return b''.join(pack_subrecord(tag.decode('latin-1'), data) for tag, data in out)


def encode_group(blob: bytes) -> bytes:
    """Top-level group `blob` with every display-text subrecord as UTF-8 (unchanged when none needs it)."""
    bodies = {}
    for pos, sig, size, flags in records(blob):
        if sig in TEXT and not flags & FLAG_COMPRESSED:
            body = _body(sig, blob[pos + HEADER:pos + HEADER + size])
            if body is not None:
                bodies[pos] = body
    return replace_bodies(blob, bodies)
