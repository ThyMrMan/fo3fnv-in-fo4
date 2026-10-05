"""FO4 plugin writer: header layout, form version, group order and quest-children nesting."""

import struct

from fo4_import.base.writer import (
    FO4PluginWriter, FORM_VERSION_FO4, GRP_QUEST_CHILDREN, GRP_TOPIC_CHILDREN,
    pack_fo4_record, pack_quest, pack_topic,
)
from tes5_import.base.tes5_reader import walk
from tes5_import.base.writer import pack_group, pack_string_subrecord

QUST, DIAL, INFO, SCEN, DLBR, KYWD, CELL = 0x01000800, 0x01000801, 0x01000802, 0x01000803, 0x01000804, 0x01000805, 0x01000806


def _rec(sig: str, fid: int, edid: str) -> bytes:
    """A record holding only an EDID."""
    return pack_fo4_record(sig, fid, 0, pack_string_subrecord('EDID', edid))


def _plugin(tmp_path) -> bytes:
    """Write a small plugin through FO4PluginWriter and return its bytes."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False)
    topic = pack_topic(_rec('DIAL', DIAL, 'SpikeTopic'), DIAL, [_rec('INFO', INFO, '')])
    w.add_record('QUST', pack_quest(_rec('QUST', QUST, 'SpikeQuest'), QUST,
                                    [_rec('DLBR', DLBR, 'SpikeBranch')], [topic],
                                    [_rec('SCEN', SCEN, 'SpikeScene')]))
    w.add_record('KYWD', _rec('KYWD', KYWD, 'SpikeKeyword'))
    cell = _rec('CELL', CELL, 'SpikeCell')
    w.add_raw_group('CELL', pack_group(2, struct.pack('<i', 6), pack_group(3, struct.pack('<i', 0), cell)))
    path = tmp_path / 'Spike.esp'
    w.write(str(path))
    return path.read_bytes()


def _header_subs(raw: bytes) -> dict:
    """The TES4 header's subrecords as {sig: data}."""
    size = struct.unpack_from('<I', raw, 4)[0]
    subs, pos = {}, 24
    while pos < 24 + size:
        sig, n = struct.unpack_from('<4sH', raw, pos)
        subs[sig] = raw[pos + 6:pos + 6 + n]
        pos += 6 + n
    return subs


def test_header_is_fo4_layout(tmp_path):
    """Form version 131, HEDR 1.0, master, INTV and the interior cell count."""
    raw = _plugin(tmp_path)
    assert struct.unpack_from('<H', raw, 20)[0] == FORM_VERSION_FO4
    assert struct.unpack_from('<I', raw, 8)[0] == 0
    subs = _header_subs(raw)
    assert struct.unpack('<f', subs[b'HEDR'][:4])[0] == 1.0
    assert subs[b'MAST'] == b'Fallout4.esm\x00'
    assert struct.unpack('<I', subs[b'INTV'])[0] == 1
    assert struct.unpack('<I', subs[b'INCC'])[0] == 1


def test_records_and_group_order(tmp_path):
    """Every record is form version 131, and KYWD precedes CELL precedes QUST."""
    raw = _plugin(tmp_path)
    seen = [(rec.sig, rec.form_version) for rec, _ in walk(raw)]
    assert all(version == FORM_VERSION_FO4 for _, version in seen)
    order = [sig for sig, _ in seen]
    assert order.index(b'KYWD') < order.index(b'CELL') < order.index(b'QUST')


def test_dialogue_nests_under_its_quest(tmp_path):
    """DLBR, DIAL, its INFO, then SCEN, inside the quest's type-10 group."""
    raw = _plugin(tmp_path)
    nested = [(rec.sig, [(g.type, g.label_fid) for g in stack.groups[1:]])
              for rec, stack in walk(raw) if stack.top == b'QUST']
    quest_group = (GRP_QUEST_CHILDREN, QUST)
    assert nested == [
        (b'QUST', []),
        (b'DLBR', [quest_group]),
        (b'DIAL', [quest_group]),
        (b'INFO', [quest_group, (GRP_TOPIC_CHILDREN, DIAL)]),
        (b'SCEN', [quest_group]),
    ]


def test_quest_without_children_has_no_group():
    """A bare quest is just its record, as vanilla writes it."""
    rec = _rec('QUST', QUST, 'Bare')
    assert pack_quest(rec, QUST) == rec
