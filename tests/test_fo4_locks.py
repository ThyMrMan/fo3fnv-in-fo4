"""The FNV locks FO4's lock tiers cannot hold (fo4_import.spike.locks) and the script that holds them."""

import re
import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fo4_import.base.vmad import read_entry
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import locks as L
from fo4_import.spike import records as R
from fo4_import.spike.terminals import Terminals
from tes5_import.base.tes5_reader import subrecords

HELPER = 2
NOTE, NOTE_FO4 = 0xBEEF, 0x0300BEEF
SCRIPT = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4' / f'{L.LOCK_SCRIPT}.psc'


def _terminals(records: dict) -> Terminals:
    """Terminals over export `records` alone, without the vanilla template."""
    terminals = Terminals.__new__(Terminals)
    terminals.records = records
    return terminals


def _builder(terms: dict = None) -> SimpleNamespace:
    """A builder making only the password note, its terminals `terms`."""
    return SimpleNamespace(items=SimpleNamespace(item=lambda fid: NOTE_FO4 if fid == NOTE else None),
                           scripts=SimpleNamespace(helper_index=HELPER), counts=Counter(),
                           readables=SimpleNamespace(terminals=_terminals(terms or {})))


def _script(vmad: bytes) -> tuple:
    """(script, objects, values) of the one script a REFR given `vmad` attaches."""
    data = dict(subrecords(R.pack_refr(1, 2, (0, 0, 0), (0, 0, 0), vmad=vmad)[24:]))[b'VMAD']
    assert struct.unpack_from('<HHH', data)[2] == 1
    return read_entry(data, 6)[0]


def test_an_easy_lock_is_held_to_lockpick_and_a_tier_fo4_gates_is_left_to_the_game():
    """Level 25 (FO4's ungated Novice) runs the script on Lockpick; 0, 50, 75, 100 and key-only get none."""
    builder = _builder()
    name, objects, values = _script(L.lock_vmad(builder, {'XLOC.Level': '25'}))
    assert (name, objects, values) == (L.LOCK_SCRIPT, {'Skill': actor_value_form('Lockpick', HELPER)},
                                       {'IsTerminal': ('bool', 0)})
    assert all(L.lock_vmad(builder, {'XLOC.Level': level}) == b'' for level in ('0', '50', '75', '100', '255'))
    assert L.lock_vmad(builder, {'NAME': '00000001'}) == b'' and builder.counts['locks held by script: Easy'] == 1


def test_a_terminal_with_a_password_note_is_held_to_science_and_names_the_note():
    """A Hard terminal with a password note: Science, the note's FO4 form; an Easy one without: no password."""
    terms = {0x10: {'DNAM.Difficulty': '3', 'DNAM.Flags': '0', 'PNAM': f'{NOTE:08X}'},
             0x11: {'DNAM.Difficulty': '1', 'DNAM.Flags': '0'},
             0x12: {'DNAM.Difficulty': '1', 'DNAM.Flags': '2', 'PNAM': f'{NOTE:08X}'}}
    builder = _builder(terms)
    science = actor_value_form('Science', HELPER)
    assert _script(L.lock_vmad(builder, {'NAME': '00000010'}))[1:] == (
        {'Skill': science, 'Password': NOTE_FO4}, {'IsTerminal': ('bool', 1)})
    assert _script(L.lock_vmad(builder, {'NAME': '00000011'}))[1] == {'Skill': science}
    assert L.lock_vmad(builder, {'NAME': '00000012'}) == b''
    assert builder.counts['locks held by script: password note'] == 1


def test_a_terminals_lock_is_its_difficulty_in_fnv_steps_and_requires_key_is_255():
    """Difficulty x 25, Requires Key 255, Leveled kept, the password note's FormID; Unlocked has no lock."""
    terminals = _terminals({1: {'DNAM.Difficulty': '4', 'DNAM.Flags': '1', 'PNAM': '0000BEEF'},
                            2: {'DNAM.Difficulty': '5', 'DNAM.Flags': '0'}, 3: {'DNAM.Flags': '2'}})
    assert terminals.lock_of({'NAME': '1'}) == (100, True, NOTE)
    assert terminals.lock_of({'NAME': '2'}) == (255, False, 0)
    assert terminals.lock_of({'NAME': '3'}) is None and terminals.lock_of({'NAME': '9'}) is None


def test_a_placed_references_scripts_come_before_its_base():
    """REFR VMAD sits after EDID and before NAME, as xEdit's FO4 REFR."""
    tags = [t for t, _ in subrecords(R.pack_refr(1, 2, (0, 0, 0), (0, 0, 0), edid='X', vmad=b'v')[24:])]
    assert tags[:3] == [b'EDID', b'VMAD', b'NAME']


def test_the_lock_script_declares_every_property_the_converter_fills():
    """Each property lock_vmad fills is declared in the script with a matching type."""
    declared = dict((name, kind) for kind, name in re.findall(r'^(\w+) Property (\w+) Auto', SCRIPT.read_text(), re.M))
    assert declared == {'Skill': 'ActorValue', 'IsTerminal': 'Bool', 'Password': 'Form'}
