"""
FNV challenges (CHAL): a pure dump of the name, description, icon, reward
script, DATA and the two type-dependent form links.

DATA (24 bytes, JIP's TESChallenge::ChallengeData): type, threshold, flags,
interval, then two u16 and a u32 whose meaning depends on the type; SNAM and
XNAM are form links whose meaning also depends on it.

See: docs/commentary/tes4_export_falloutnv.md#challenges
"""

import struct

from ..tes4_reader import Record, get_subrecord
from .common import emit_formid, emit_script, emit_string

#: DATA's fields in order (struct '<IIIIHHI').
_DATA = ("Type", "Threshold", "Flags", "Interval", "Value1", "Value2", "Value3")


def export_CHALLENGE(rec: Record) -> list:
    """A CHAL: FULL, DESC, ICON, SCRI, DATA's seven fields, SNAM and XNAM."""
    lines = []
    for sig in ("FULL", "DESC", "ICON"):
        emit_string(lines, sig, get_subrecord(rec, sig))
    emit_script(lines, rec)
    data = get_subrecord(rec, "DATA")
    if data and len(data.data) >= 24:
        lines += [f"DATA.{k}={v}" for k, v in zip(_DATA, struct.unpack_from("<IIIIHHI", data.data))]
    for sig in ("SNAM", "XNAM"):
        emit_formid(lines, sig, get_subrecord(rec, sig))
    return lines


CHALLENGE_EXPORTERS = {"CHAL": export_CHALLENGE}
