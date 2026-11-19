"""Display text in a written FO4 plugin is UTF-8: cp1252 ’ (0x92) and the like re-encoded, binary data left alone.

See: docs/fork/fo4_pipeline.md#text-encoding
"""

import struct

from fo4_import.base.text_encoding import TEXT, encode_group, utf8
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_group, pack_subrecord

WOULDNT = '"But doctor, wouldn’t that cause a parabolic destabilization?"'


def _mesg(button: bytes, dnam: bytes = struct.pack('<I', 1), flags: int = 0) -> bytes:
    """A MESG top group: one message whose DNAM and button text are given, its record flags `flags`."""
    subs = (pack_subrecord('EDID', b'CG03GoatQuestion01\0') + pack_subrecord('DNAM', dnam)
            + pack_subrecord('ITXT', button))
    group = bytearray(pack_group(0, b'MESG', pack_fo4_record('MESG', 0x38ADF, 0, subs)))
    struct.pack_into('<I', group, 32, flags)
    return bytes(group)


def _subs(group: bytes) -> dict:
    """{signature: data} of the first record in `group`."""
    record = next(r for r, _ in walk(group, span=(0, len(group))))
    return dict(subrecords(record.body))


def test_utf8_converts_cp1252_and_keeps_utf8_and_ascii():
    """’ … “ ” é become UTF-8; ASCII and UTF-8 already are unchanged; cp1252's undefined 0x81 keeps U+0081."""
    assert utf8(WOULDNT.encode('cp1252')) == WOULDNT.encode('utf-8')
    assert utf8('…“é”'.encode('cp1252')) == '…“é”'.encode('utf-8')
    assert utf8(b"wouldn't\0") == b"wouldn't\0"
    assert utf8(WOULDNT.encode('utf-8')) == WOULDNT.encode('utf-8')
    assert utf8(b'\x81\x92') == '\x81’'.encode('utf-8')


def test_button_text_is_utf8_and_binary_and_group_sizes_hold():
    """The G.O.A.T. button's ITXT is re-encoded; a DNAM holding 0x92 is not text and keeps it; sizes are rewritten."""
    out = encode_group(_mesg(WOULDNT.encode('cp1252') + b'\0', dnam=b'\x92\0\0\0'))
    subs = _subs(out)
    assert subs[b'ITXT'] == WOULDNT.encode('utf-8') + b'\0' and subs[b'DNAM'] == b'\x92\0\0\0'
    assert struct.unpack_from('<I', out, 4)[0] == len(out)
    assert struct.unpack_from('<I', out, 28)[0] == len(out) - 48


def test_unchanged_groups_pass_through():
    """ASCII text, UTF-8 text and a compressed record pass through."""
    for blob in (_mesg(b"wouldn't\0"), _mesg(WOULDNT.encode('utf-8') + b'\0'),
                 _mesg(WOULDNT.encode('cp1252') + b'\0', flags=0x40000)):
        assert encode_group(blob) is blob


def test_table_names_every_text_kind_the_intro_shows():
    """xEdit's FO4 text subrecords: subtitles, menu choices, message boxes, terminals, books, objectives."""
    for rec, sub in ((b'INFO', b'NAM1'), (b'INFO', b'RNAM'), (b'MESG', b'ITXT'), (b'MESG', b'DESC'),
                     (b'TERM', b'UNAM'), (b'TERM', b'BTXT'), (b'BOOK', b'DESC'), (b'QUST', b'NNAM')):
        assert sub in TEXT[rec], (rec, sub)
    assert b'DNAM' not in TEXT[b'MESG'] and b'EDID' not in TEXT[b'MESG']


def test_plugin_writer_stores_text_as_utf8(tmp_path):
    """FO4PluginWriter writes the button UTF-8 into the file."""
    writer = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False)
    writer.add_record('MESG', pack_fo4_record('MESG', 0x800, 0, pack_subrecord('ITXT', WOULDNT.encode('cp1252') + b'\0')))
    path = tmp_path / 'Text.esp'
    writer.write(str(path))
    data = path.read_bytes()
    assert WOULDNT.encode('utf-8') in data and b'\x92' not in data
