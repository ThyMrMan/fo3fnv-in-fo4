"""An FNV message box button keeps the conditions that show it: exported after its text, written after FO4's ITXT.

See: docs/fork/fo4_pipeline.md#message-buttons
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.base.support_records import pack_mesg
from fo4_import.spike import conditions as C
from fo4_import.spike.attach import NEVER_SHOWN, ObjectScripts
from fo4_import.spike.say_topics import HARDCORE_KEY, conditions_under
from tes4_export.record_types.falloutnv import export_MESSAGE
from tes4_export.tes4_reader import Record, Subrecord
from tes5_import.base.tes5_reader import subrecords

#: FNV BisonElevatorMessage's Repair button condition: GetActorValue Repair (39) >= 35, as FalloutNV.esm stores it.
REPAIR_35 = bytes.fromhex('6000000000000c420e00000027000000000000000000000000000000')


def _elevator() -> Record:
    """FNV's BisonElevatorMessage: Leave It Alone, then Repair Elevator gated on Repair 35."""
    subs = [Subrecord('EDID', b'BisonElevatorMessage\0'), Subrecord('DESC', b'The elevator is broken.\0'),
            Subrecord('FULL', b'Broken Elevator\0'), Subrecord('DNAM', struct.pack('<I', 1)),
            Subrecord('ITXT', b'Leave It Alone\0'), Subrecord('ITXT', b'Repair Elevator\0'), Subrecord('CTDA', REPAIR_35)]
    return Record('MESG', 0, 0, 0x0E3EB9, subs)


def test_a_buttons_conditions_export_with_it():
    """The CTDA after the second ITXT is that button's; the first has none."""
    got = dict(line.split('=', 1) for line in export_MESSAGE(_elevator()))
    assert got['Button[1].Text'] == 'Repair Elevator'
    assert got['Button[1].Condition[0].Raw'] == REPAIR_35.hex().upper()
    assert not any(key.startswith('Button[0].Condition') for key in got)
    assert conditions_under(got, 'Button[1].') == {'Condition[0].Raw': REPAIR_35.hex().upper()}


def test_a_gated_message_waits_for_the_builds_condition_forms():
    """A message whose buttons test a quest variable is written once the build's forms are known: the variable
    reads its mirror global, which the readables' map alone lacks; a message asked for later is written at once."""
    quest_var = bytes.fromhex('000000000000803F4F0000007CFB15000E0000000000000000000000').hex().upper()
    rec = {'EditorID': 'RadioMsg', 'FormID': '0015FB7D', 'Button[0].Text': 'Listen',
           'Button[0].Condition[0].Raw': quest_var}
    written, counts = [], Counter()
    builder = SimpleNamespace(counts=counts, writer=SimpleNamespace(add_record=lambda sig, blob: written.append(blob)),
                              fnv_id=lambda fid: 0x800, readables=SimpleNamespace(form_map=lambda: {}),
                              items=SimpleNamespace(item=lambda fid: None))
    scripts = SimpleNamespace(builder=builder, messages={'RadioMsg': rec, 'Later': rec}, made_messages={},
                              gated_messages=[], gate_forms=None)
    for name in ('message', '_write_message', '_write_gated', '_gate', 'write_gated_messages'):
        setattr(scripts, name, getattr(ObjectScripts, name).__get__(scripts))
    scripts.message('RadioMsg')
    assert written == []
    scripts.write_gated_messages({('qvar', 0x15FB7C, 0x0E): 0x1234}, {})
    tags = [tag for tag, _ in subrecords(written[0][24:])]
    assert tags[-2:] == [b'ITXT', b'CTDA'] and not any('not gated' in key for key in counts)
    scripts.message('Later')
    assert len(written) == 2


def test_a_hardcore_button_reads_the_hardcore_global():
    """Dead Money's autodoc 'cure exhaustion' (IsHardcore == 1) shows while the Hardcore global is 1
    (fo4_hardcore.md#built)."""
    hardcore = '000000000000803F4A020000'.ljust(56, '0')
    scripts = SimpleNamespace(builder=SimpleNamespace(counts=Counter()))
    gate = ObjectScripts._gate.__get__(scripts)
    assert C.parse(hardcore)['func'] == 'IsHardcore'
    ctda = gate('M', {'Condition[0].Raw': hardcore}, {HARDCORE_KEY: 0x05000A00}, {})
    assert struct.unpack_from('<B3xfH2xI', ctda, 6) == (0, 1.0, C.FO4.index('GetGlobalValue'), 0x05000A00)


def test_a_button_that_never_passes_is_hidden():
    """A button testing a quest the build lacks never shows."""
    missing = '00000000000080403A00000099990000'.ljust(56, '0')
    scripts = SimpleNamespace(builder=SimpleNamespace(counts=Counter()))
    gate = ObjectScripts._gate.__get__(scripts)
    assert C.parse(missing)['func'] == 'GetStage'
    assert gate('M', {'Condition[0].Raw': missing}, {}, {}) == NEVER_SHOWN


def test_fo4_writes_each_buttons_conditions_after_its_text():
    """FO4's MESG: ITXT, then that button's CTDAs (xEdit 'Menu Button'); a button without any is its ITXT alone."""
    gate = b'CTDA' + struct.pack('<H', 4) + b'gate'
    body = pack_mesg(0x800, 'M', 'T', 'D', 1, ['Leave', 'Repair'], [b'', gate])[24:]
    tags = [tag for tag, _ in subrecords(body)]
    assert tags[-3:] == [b'ITXT', b'ITXT', b'CTDA']
