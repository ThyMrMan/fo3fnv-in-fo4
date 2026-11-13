"""tools/disasm/address_lib.py on Fallout 4's databases: a count and (id, rva) pairs, and the --rvas table.

See: docs/reference/address_library_formats.md#fallout-4
"""

import struct

from tools.disasm import address_lib


def _write(path, pairs):
    """An FO4 database of `pairs` ({id: rva}) at `path`."""
    flat = [value for pair in pairs.items() for value in pair]
    path.write_bytes(struct.pack(f'<Q{len(flat)}Q', len(pairs), *flat))
    return path


def test_an_fo4_database_reads_as_its_pairs(tmp_path):
    """Its size is 8 + 16 * count, so it loads as {id: rva}."""
    assert address_lib.load(_write(tmp_path / 'version-1-11-240-0.bin', {15: 0x29BD698, 37: 0x2F0D7B8})) == {
        15: 0x29BD698, 37: 0x2F0D7B8}


def test_the_table_names_each_rva_by_id_and_shows_it_in_other_builds(tmp_path, capsys):
    """An exact RVA prints its ID, one inside a function its owner plus the distance, and each ID's RVA in another
    build or - when that build lacks it; the exit is 1 because one RVA had no exact ID."""
    _write(tmp_path / 'version-1-11-240-0.bin', {7: 0x1000, 8: 0x2000})
    _write(tmp_path / 'version-1-10-984-0.bin', {7: 0x900})
    assert address_lib.table([0x1000, 0x2010], '1.11.240', ['1.10.984'], str(tmp_path)) == 1
    rows = [line.split() for line in capsys.readouterr().out.splitlines()[1:]]
    assert rows == [['0x1000', '7', '0x900'], ['0x2010', '8+0x10', '-']]
