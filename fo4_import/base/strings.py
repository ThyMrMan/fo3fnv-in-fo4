"""Fallout4.esm's localized strings, by string ID, from the game's own archives.

Fallout4.esm is localized: a FULL or DESC holds a 4-byte string ID into
`Strings\\Fallout4_<language>.STRINGS` (names), `.DLSTRINGS` and
`.ILSTRINGS` (descriptions, dialogue). A record copied into a plugin that is
not localized needs the text itself. Each file is a count, a data size, a
directory of (ID, offset), then the strings: zero-terminated in .STRINGS,
length-prefixed (and zero-terminated) in the other two.

See: docs/fork/fo4_spikes.md#spike-4-equipment
"""

import struct

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR

#: String file extensions, and whether their entries start with a length.
KINDS = (('strings', False), ('dlstrings', True), ('ilstrings', True))


def parse(raw: bytes, sized: bool) -> dict:
    """{string ID: text bytes} of one strings file."""
    count = struct.unpack_from('<I', raw)[0]
    start, out = 8 + count * 8, {}
    for sid, offset in struct.iter_unpack('<II', raw[8:start]):
        at = start + offset + (4 if sized else 0)
        out[sid] = raw[at:raw.index(b'\0', at)]
    return out


def load(plugin: str = 'fallout4', language: str = 'en') -> dict:
    """{string ID: text bytes} of a master's three strings files, read from the game's BA2s."""
    archives, out = Archives(FALLOUT4_DIR / 'Data'), {}
    for ext, sized in KINDS:
        out.update(parse(archives.read(f'strings\\{plugin}_{language}.{ext}'), sized))
    return out
