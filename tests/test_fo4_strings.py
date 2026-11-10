"""Fallout4.esm string IDs written as text in a plugin that is not localized.

See: docs/fork/fo4_thrown_weapons.md#names
"""

import struct

from fo4_import.base import strings
from fo4_import.spike.void_actors import copy_record
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


class _Record:
    """A Fallout4.esm record as walk() yields it."""

    def __init__(self, sig: bytes, body: bytes):
        self.sig, self.body, self.flags = sig, body, 0


def _fake_strings(monkeypatch):
    """Fallout4.esm's strings as two entries."""
    monkeypatch.setattr(strings, 'fallout4', lambda: {7: b'Mole Rat', 9: b'A skin'})


def test_a_name_or_description_id_becomes_its_text(monkeypatch):
    """FULL and DESC string IDs read as their text; other fields stay as they are."""
    _fake_strings(monkeypatch)
    assert strings.as_text(b'FULL', struct.pack('<I', 7)) == b'Mole Rat\0'
    assert strings.as_text(b'DESC', struct.pack('<I', 9)) == b'A skin\0'
    assert strings.as_text(b'RNAM', struct.pack('<I', 7)) == struct.pack('<I', 7)


def test_a_copied_record_carries_text_and_keeps_replaced_values(monkeypatch):
    """copy_record writes the template's name as text, but a value it is given as is."""
    _fake_strings(monkeypatch)
    body = (pack_subrecord('EDID', b'MoleratRace\0') + pack_subrecord('FULL', struct.pack('<I', 7))
            + pack_subrecord('DESC', struct.pack('<I', 9)))
    made = dict(subrecords(copy_record(_Record(b'RACE', body), 0x800, 'FNV_VoidRace', {b'DESC': b'Ant\0'})[24:]))
    assert made[b'FULL'] == b'Mole Rat\0' and made[b'DESC'] == b'Ant\0'
