"""An FNV NIF or KF file read as the game reads it: the header line's format name is found where it stands, so
stray bytes before it are skipped, and a block naming a string past the header's string table reads an empty name
(Weapons of the New Millenia's AK47, FNC and FNCSIL), where pyffi refuses the whole file.

read() reads with our own reader (fnv_reader), and with pyffi (read_pyffi) a file of another version or with a
block ours could not read; either's blocks pass isinstance() against NifFormat's classes.

See: docs/fork/fo4_pipeline.md#fnv-nif-header
See: docs/fork/research/fnv_nif_reader.md#integration
"""

import io
import struct
from pathlib import Path

from fo4_import.nif import fnv_reader
from fo4_import.nif.fnv_reader import header_start
from pyffi.formats.nif import NifFormat


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


def read_pyffi(path) -> NifFormat.Data:
    """The pyffi data of the FNV NIF or KF file at `path`."""
    raw = Path(path).read_bytes()
    data = Data()
    data.read(io.BytesIO(raw[header_start(raw):]))
    return data


def read(path):
    """The data of the FNV NIF or KF file at `path`: fnv_reader's, else pyffi's."""
    try:
        data = fnv_reader.read(path)
    except (ValueError, IndexError, struct.error):
        return read_pyffi(path)
    return read_pyffi(path) if data.skipped else data
