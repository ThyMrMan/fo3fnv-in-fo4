"""FO4 plugin writer: header layout, form version, group order and quest-children nesting."""

import collections
import struct
from types import SimpleNamespace

import pytest

from fo4_import.base.ledger import ID, Ledger, LedgerWriter, ledger_path
from fo4_import.spike.cell import MADE_SITE, CellBuilder
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


def _writer(ledger: Ledger = None) -> LedgerWriter:
    """A writer with a fixed hash window, using `ledger` when given."""
    w = LedgerWriter(masters=['Fallout4.esm'], is_esm=False)
    w.reserve_source_ids({0x01000800})
    if ledger is not None:
        w.use_ledger(ledger)
    return w


def test_ledger_round_trip_keeps_ids_in_any_order(tmp_path):
    """Ids a build gave come back from the saved ledger whatever order the next build asks in."""
    first = _writer(Ledger(ledger_path(tmp_path / 'Spike.esp')))
    given = {key: first.derive_formid('site', key) for key in ('a', 'b', ('c', 1))}
    first.stable_number('alias Q', 'T', lambda: 4)
    first.ledger.save()
    again = _writer(Ledger(ledger_path(tmp_path / 'Spike.esp')))
    assert {key: again.derive_formid('site', key) for key in (('c', 1), 'b', 'a')} == given
    assert again.stable_number('alias Q', 'T', lambda: 9) == 4
    lines = ledger_path(tmp_path / 'Spike.esp').read_text(encoding='utf-8').splitlines()
    assert lines == sorted(lines) and not (tmp_path / 'Spike.formids.tsv').exists()


def test_ledger_ids_are_reserved_for_new_keys(tmp_path):
    """A new key whose hash lands on a kept id takes another, so the kept record does not move."""
    plain = _writer().derive_formid('site', 'new')
    ledger = Ledger()
    ledger.put(ID, 'site', 'old', plain & 0xFFFFFF)
    w = _writer(ledger)
    assert w.derive_formid('site', 'old') == plain
    assert w.derive_formid('site', 'new') != plain


def test_a_replaced_key_keeps_its_old_keys_id():
    """With no ledger entry, a new key gets the id its legacy key hashes to, and is kept under the new key."""
    w = _writer(Ledger())
    fid = w.derive_formid('site', 'INFO x 1 at quest step', legacy='INFO x 1')
    assert fid == _writer().derive_formid('site', 'INFO x 1')
    assert w.ledger.get(ID, 'site', 'INFO x 1 at quest step') == fid & 0xFFFFFF


def test_a_replaced_key_takes_over_the_id_the_ledger_kept_for_its_old_key():
    """A key the ledger kept moves to its new key with its id (a re-hash would hit the kept id and move it)."""
    first = _writer(Ledger())
    old = first.derive_formid('site', 'DIAL x 1')
    again = _writer(first.ledger)
    assert again.derive_formid('site', 'DIAL x slot 1', legacy='DIAL x 1') == old
    assert again.ledger.get(ID, 'site', 'DIAL x 1') is None
    assert again.derive_formid('site', 'DIAL x 1') != old


def test_new_id_refuses_two_records_on_one_key():
    """Two generated records keyed alike would share a FormID: new_id raises instead."""
    fake = SimpleNamespace(owned=collections.Counter(), keyed=set(), counts=collections.Counter(), writer=_writer())
    CellBuilder.new_id(fake, 'INFO x 1', key='INFO x 1 at a')
    assert CellBuilder.new_id(fake, 'INFO x 1', key='INFO x 1 at b') == _writer().derive_formid(MADE_SITE, 'INFO x 1 1')
    with pytest.raises(ValueError):
        CellBuilder.new_id(fake, 'INFO x 1', key='INFO x 1 at a')
