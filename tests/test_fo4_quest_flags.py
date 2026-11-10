"""FNV quest flags on the FO4 QUST: Allow Repeated Stages carries over.

See: docs/fork/fo4_pipeline.md#intense-training
"""

import struct
from types import SimpleNamespace

from fo4_import.spike import quest as Q
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords

#: FO4 record header size.
HEADER = 24


def _flags(record: bytes) -> int:
    """DNAM flags of a packed FO4 QUST."""
    return struct.unpack_from('<H', dict(subrecords(record[HEADER:]))[b'DNAM'])[0]


def _quest(flags: int) -> bytes:
    """quest_record of a start-enabled FNV quest with DATA flags `flags`, no scripts or objectives."""
    scripts = SimpleNamespace(dir=None, used=[], builder=SimpleNamespace(writer=None))
    rec = {'FormID': '000038B2', 'EditorID': 'Generic', 'DATA.Flags': str(flags), 'DATA.Priority': '5',
           'Stage[0].Index': '101'}
    return Q.quest_record(0x38B2, rec, scripts, {}, start=True)


def test_generic_keeps_repeated_stages():
    """FNV's Generic (flags 25) keeps Start Game Enabled and Allow Repeated Stages."""
    assert _flags(_quest(25)) == 0x0011 | R.REPEATED_STAGES


def test_without_repeated_stages():
    """A quest without FNV's flag stays without it."""
    assert _flags(_quest(1)) == 0x0011
    assert _flags(R.pack_fnv_quest(1, 'Q', '', 0, b'', [], [], [])) == 0
