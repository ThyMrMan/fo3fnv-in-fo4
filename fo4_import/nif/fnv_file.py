"""An FNV NIF or KF file read with pyffi, as the game reads it: the header line's format name is found where it
stands, so stray bytes before it are skipped, and a block naming a string past the header's string table reads
an empty name (Weapons of the New Millenia's AK47, FNC and FNCSIL), where pyffi refuses the whole file.

See: docs/fork/fo4_pipeline.md#fnv-nif-header
"""

import io
from pathlib import Path

from pyffi.formats.nif import NifFormat

#: The format names a NIF header line starts with.
NAMES = (b'Gamebryo File Format', b'NetImmerse File Format')


class Strings(list):
    """A header string table whose index past its end reads an empty name."""

    def __getitem__(self, index):
        """The string at `index`; b'' for an int index past the end."""
        if isinstance(index, int) and index >= len(self):
            return b''
        return super().__getitem__(index)


class Data(NifFormat.Data):
    """pyffi's NIF data, its string table a Strings."""

    @property
    def _string_list(self):
        """The header's string table, as Strings."""
        return self.__dict__.get('_strings')

    @_string_list.setter
    def _string_list(self, value):
        """Keep `value` as Strings."""
        self.__dict__['_strings'] = None if value is None else Strings(value)


def header_start(raw: bytes) -> int:
    """Where the format name starts in `raw`'s header line (0: at the start, or none)."""
    line = raw[:raw.find(b'\n')] if b'\n' in raw else raw
    return 0 if line.startswith(NAMES) else max(0, *(line.rfind(name) for name in NAMES))


def read(path) -> NifFormat.Data:
    """The pyffi data of the FNV NIF or KF file at `path`."""
    raw = Path(path).read_bytes()
    data = Data()
    data.read(io.BytesIO(raw[header_start(raw):]))
    return data
