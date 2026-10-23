"""FNV's Pip-Boy tabs: each tab's quest carries its name, place, rows and strings; old Pip-Boy Tabs files go.

See: docs/fork/fo4_pipboy_tabs.md
"""
import struct
from types import SimpleNamespace

from fo4_import.spike import pipboy_tabs as T
from script_convert.pipeline import pack_wstring, script_entry


def _builder() -> SimpleNamespace:
    """A builder stand-in recording the records it is given."""
    records = []
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x1234, add_record=lambda sig, rec: records.append(rec))
    return SimpleNamespace(writer=writer, scripts=SimpleNamespace(used=[]), records=records)


def test_string_properties_pack_as_vmad_types_2_and_12():
    """A string property is type 2 and a wstring; a string array is type 12, a count, then each wstring."""
    entry = script_entry('S', None, {'A': ('string', 'SKILLS'), 'B': ('strings', ['x', 'yz'])})
    assert pack_wstring('A') + struct.pack('<BB', 2, 1) + pack_wstring('SKILLS') in entry
    assert pack_wstring('B') + struct.pack('<BBI', 12, 1, 2) + pack_wstring('x') + pack_wstring('yz') in entry


def test_tab_quest_carries_the_tab_and_names_its_scripts():
    """The quest's script gets the tab's name, place, rows and strings, and the tab scripts compile."""
    builder = _builder()
    assert T.tab_quest(builder, 'REPUTATION', 0x55, ('Neutral', 'Liked'), 0x66) == 0x1234
    record = builder.records[0]
    assert pack_wstring('TabName') + struct.pack('<BB', 2, 1) + pack_wstring('REPUTATION') in record
    assert pack_wstring('Order') + struct.pack('<BBi', 3, 1, T.ORDER['REPUTATION']) in record
    assert pack_wstring('Values') + struct.pack('<BBI', 12, 1, 2) in record
    assert pack_wstring('Shown') in record and pack_wstring('Rows') in record
    assert set(builder.scripts.used) == {T.TAB_SCRIPT, T.NATIVES}


def test_old_pip_boy_tabs_files_are_removed(tmp_path):
    """A rebuild deletes the Karma and Reputation files older builds wrote, and nothing else."""
    folder = tmp_path / T.LEGACY_FOLDER
    folder.mkdir()
    for name in ('Mod_Karma.ini', 'Mod_Reputation.ini', 'Other_Karma.ini'):
        (folder / name).write_text('x')
    assert len(T.remove_legacy_tabs(tmp_path, 'Mod.esp')) == 2
    assert [p.name for p in folder.iterdir()] == ['Other_Karma.ini']
