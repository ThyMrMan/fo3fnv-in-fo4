"""fo4_ref_check on small hand-built plugins: what resolves, what does not, and which fields are judged."""

import struct

from tools.validate import fo4_ref_check as rc

MASTER = 'RefCheckMaster.esm'
#: Condition function indices used below: GetWantBlocking (no form), GetDistance (Reference, aliasable), GetIsID.
GET_WANT_BLOCKING, GET_DISTANCE, GET_IS_ID = 0, 1, 72


def sub(tag: bytes, data: bytes) -> bytes:
    """One subrecord."""
    return tag + struct.pack('<H', len(data)) + data


def rec(sig: bytes, fid: int, *subs: bytes) -> bytes:
    """One uncompressed record."""
    body = b''.join(subs)
    return struct.pack('<4sIII4xH2x', sig, len(body), 0, fid, 131) + body


def grup(sig: bytes, *records: bytes) -> bytes:
    """A top-level GRUP of `records`."""
    body = b''.join(records)
    return struct.pack('<4sI4sI8x', b'GRUP', 24 + len(body), sig, 0) + body


def plugin(masters: list, *groups: bytes) -> bytes:
    """A TES4 header naming `masters`, then `groups`."""
    header = rec(b'TES4', 0, sub(b'HEDR', struct.pack('<fII', 1.0, 0, 0)),
                 *[sub(b'MAST', m.encode() + b'\0') + sub(b'DATA', bytes(8)) for m in masters])
    return header + b''.join(groups)


def ctda(kind: int, func: int, p1: int = 0, run_on: int = 0, ref: int = 0) -> bytes:
    """One 32-byte FO4 condition."""
    return sub(b'CTDA', struct.pack('<B3xfH2xIIIIi', kind, 1.0, func, p1, 0, run_on, ref, -1))


def vmad(fid: int) -> bytes:
    """A VMAD with one script holding one object property naming `fid`."""
    name = struct.pack('<H', 1) + b'S'
    prop = struct.pack('<H', 1) + b'P' + bytes((1, 1)) + struct.pack('<HhI', 0, -1, fid)
    return sub(b'VMAD', struct.pack('<hhH', 6, 2, 1) + name + bytes((0,)) + struct.pack('<H', 1) + prop)


def found(tmp_path) -> dict:
    """{(kind, record, field): [referenced FormIDs]} for the test plugin, its master beside it."""
    (tmp_path / MASTER).write_bytes(plugin([], grup(b'STAT', rec(b'STAT', 0x000800, sub(b'EDID', b'Box\0')))))
    own = 0x01000000
    data = plugin([MASTER], grup(b'STAT', rec(b'STAT', own | 0x900)), grup(b'INFO', rec(
        b'INFO', own | 0x901,
        vmad(own | 0x900), vmad(own | 0x999),
        ctda(0, GET_IS_ID, p1=0x000800), ctda(0, GET_IS_ID, p1=own | 0x998),
        ctda(2, GET_DISTANCE, p1=own | 0x997), ctda(0, GET_WANT_BLOCKING, p1=own | 0x996),
        ctda(0, GET_WANT_BLOCKING, run_on=2, ref=own | 0x995),
        sub(b'SNAM', struct.pack('<I', 0x05000001)))))
    (tmp_path / 'Test.esp').write_bytes(data)
    result = rc.check(tmp_path / 'Test.esp', [tmp_path])
    assert result['missing'] == [] and result['unreadable'] == 0
    return {key: [fid for _, _, fid in items] for key, items in result['unresolved'].items()}


def test_unresolved_references_are_found_and_resolving_ones_pass(tmp_path):
    """The dangling property, Parameter #1 and Reference are reported; master and own records resolve."""
    assert found(tmp_path) == {
        ('unresolved', 'INFO', 'VMAD property'): [0x01000999],
        ('unresolved', 'INFO', 'CTDA Parameter #1'): [0x01000998],
        ('unresolved', 'INFO', 'CTDA Reference'): [0x01000995],
        ('no such master', 'INFO', 'SNAM'): [0x05000001],
    }


def test_alias_and_non_form_parameters_are_not_judged():
    """An aliased Reference parameter and a function without form parameters yield no FormID."""
    assert rc.ctda_formids(ctda(2, GET_DISTANCE, p1=7)[6:]) == []
    assert rc.ctda_formids(ctda(0, GET_WANT_BLOCKING, p1=7)[6:]) == []
    assert rc.ctda_formids(ctda(4, GET_DISTANCE, p1=7)[6:]) == [('Comparison Global', 0x3F800000),
                                                                ('Parameter #1', 7)]


def test_field_layouts():
    """Struct offsets, arrays, typed unions and fields not listed."""
    tel = struct.pack('<I24sII', 0x11, bytes(24), 0, 0x22)
    assert rc.field_formids(b'REFR', b'XTEL', tel) == [0x11, 0x22]
    assert rc.field_formids(b'CELL', b'XCLR', struct.pack('<3I', 1, 2, 3)) == [1, 2, 3]
    assert rc.field_formids(b'PACK', b'PDTO', struct.pack('<II', 0, 9)) == [9]
    assert rc.field_formids(b'PACK', b'PDTO', struct.pack('<I4s', 1, b'GREE')) == []
    assert rc.field_formids(b'PACK', b'CNAM', struct.pack('<I', 9)) == []
    assert 0x14 in rc.HARDCODED and 0x2BC in rc.HARDCODED and 0x15 not in rc.HARDCODED
