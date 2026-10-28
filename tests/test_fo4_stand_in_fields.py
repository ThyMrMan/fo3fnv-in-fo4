"""Tests for the stand-in leftover check (fo4_import.spike.stand_in_fields).

See: docs/fork/fo4_creature_audit.md#leftover-check
"""

import struct

import pytest

from fo4_import.spike.actor_data import ACBS_TEMPLATE
from fo4_import.spike.stand_in_fields import FACTIONS, checked, leftovers
from tes5_import.base.writer import pack_subrecord


def _acbs(template_flags: int = 0) -> bytes:
    """An FO4 ACBS with template flags `template_flags`."""
    data = bytearray(0x14)
    struct.pack_into('<H', data, ACBS_TEMPLATE, template_flags)
    return pack_subrecord('ACBS', bytes(data))


def _u32(tag: str, value: int) -> bytes:
    """A one-form subrecord."""
    return pack_subrecord(tag, struct.pack('<I', value))


STAND_IN = (_acbs() + _u32('RNAM', 1) + _u32('SNAM', 2) + _u32('ZNAM', 3) + _u32('VMAD', 4) + _u32('PRKR', 5)
            + _u32('CNAM', 6))


def test_kept_fnv_drop_and_open_fields_are_leftovers():
    """Kept factions, combat style, script, perk and class are each reported."""
    assert leftovers(STAND_IN, STAND_IN) == ['drop VMAD', 'fnv SNAM', 'fnv ZNAM', 'open CNAM', 'open PRKR']


def test_replaced_fields_are_not_leftovers():
    """Replaced or removed fields are not reported."""
    built = _acbs() + _u32('RNAM', 1) + _u32('SNAM', 9) + _u32('ZNAM', 8)
    assert leftovers(STAND_IN, built) == []


def test_templated_slot_is_skipped():
    """Factions a template supplies are not reported."""
    built = _acbs(FACTIONS) + _u32('RNAM', 1) + _u32('SNAM', 2) + _u32('ZNAM', 8)
    assert leftovers(STAND_IN, built) == []


def test_unmarked_field_stops_the_build():
    """A stand-in field with no mark raises, naming the copy and the field."""
    with pytest.raises(ValueError, match='Gecko.*QQQQ'):
        leftovers(STAND_IN + _u32('QQQQ', 1), STAND_IN, 'Gecko')


def test_checked_counts_and_passes_through():
    """checked returns the edit's subrecords and counts each leftover."""
    counts = {'stand-in leftover fnv SNAM': 0, 'stand-in leftover fnv ZNAM': 0, 'stand-in leftover drop VMAD': 0,
              'stand-in leftover open PRKR': 0, 'stand-in leftover open CNAM': 0}
    assert checked(counts, STAND_IN, 'Gecko', lambda subs: subs)(STAND_IN) == STAND_IN
    assert set(counts.values()) == {1}
