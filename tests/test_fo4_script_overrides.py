"""A dependent plugin's changed script written onto the master records attaching it (spike.script_overrides).

See: docs/fork/fo4_plugin_layout.md#changed-scripts
"""

import collections
import struct
from pathlib import Path
from types import SimpleNamespace

from fo4_import.base import vmad as V
from fo4_import.base.dangling_scripts import script_spans
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike import script_overrides as SO
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

TRIGGER = 'FALLOUTNV_VCG01RemoveDocCarebearM_1109'
#: The master version's source: a perk and a street-light quest the dependent's version no longer declares.
MASTER_PSC = ('Scriptname X\nPerk Property CompanionSuite Auto Const\nQuest Property VStreetLighting Auto Const\n'
              'ImageSpaceModifier Property NVEyeAdjustISFX Auto Const\nInt Property bDoOnce Auto Conditional\n')
#: The dependent's: GameHour added, the perk and quest gone, the modifier spelled in another case.
OWN_PSC = ('Scriptname X\nGlobalVariable Property GameHour Auto Const\n'
           'ImageSpaceModifier Property NVEyeADJUSTISFX Auto Const\nInt Property bDoOnce Auto Conditional\n')
MASTER_PROPS = {'CompanionSuite': 0x0215C571, 'NVEyeAdjustISFX': 0x0211E6E1, 'VStreetLighting': 0x02127E9D}
GAME_HOUR = 0x38
ACTI_ID = 0x0211E65F


class Scripts:
    """ObjectScripts.properties stand-in: fills GameHour only, and records what it was asked for."""

    def __init__(self):
        """Nothing asked yet."""
        self.asked, self.used = [], []

    def properties(self, script: str, only=None) -> dict:
        """{GameHour: FO4's global} when asked for it."""
        self.asked.append((script, set(only or ())))
        return {p: GAME_HOUR for p in only or () if p == 'GameHour'}


def _builder() -> SimpleNamespace:
    """A builder with the Scripts stand-in, a writer and counts."""
    return SimpleNamespace(scripts=Scripts(), writer=FO4PluginWriter(masters=['Fallout4.esm']),
                           counts=collections.Counter())


def _acti_body(vmad: bytes) -> bytes:
    """An ACTI body: EDID, then `vmad`."""
    return pack_string_subrecord('EDID', 'VCG01RemoveDocCarebearModeTrigger') + pack_subrecord('VMAD', vmad)


def _master_vmad() -> bytes:
    """The master's VMAD: another script, then the trigger's."""
    return V.object_scripts([('F3NV_Other', {'Keep': 0x02000001}, {}), (TRIGGER, MASTER_PROPS, {})])


def test_script_spans_list_plain_fragment_and_quest_scripts():
    """Each entry's name and bounds: plain scripts, an INFO's fragment script, a quest's stage script."""
    plain = _master_vmad()
    spans = script_spans(b'ACTI', plain)
    assert [name for name, _, _ in spans] == ['F3NV_Other', TRIGGER]
    assert spans[-1][2] == len(plain)
    assert V.read_entry(plain, spans[1][1])[0] == (TRIGGER, MASTER_PROPS, {})
    info = V.info_fragments('TIF_A', {'Q': 1}, begin=None, scripts=[('F3NV_SayOnce', {}, {})])
    assert [name for name, _, _ in script_spans(b'INFO', info)] == ['F3NV_SayOnce', 'TIF_A']
    quest = V.quest_fragments('QF_A', [(10, 0, 'Fragment_0')], {'P': 2})
    assert [name for name, _, _ in script_spans(b'QUST', quest)] == ['QF_A']
    assert script_spans(b'QUST', V.quest_fragments('', [])) == []


def test_rebuilt_entry_keeps_shared_drops_stale_fills_new():
    """Shared properties keep the master's values (any case), stale ones go, only new ones are filled."""
    builder = _builder()
    entry = SO.rebuilt_entry(builder, TRIGGER, (TRIGGER, MASTER_PROPS, {}), (OWN_PSC, MASTER_PSC))
    assert V.read_entry(entry, 0)[0] == (TRIGGER, {'NVEyeAdjustISFX': 0x0211E6E1, 'GameHour': GAME_HOUR}, {})
    assert builder.scripts.asked == [(TRIGGER, {'GameHour'})]


def test_rebuilt_entry_is_none_when_nothing_changes():
    """The same property list (in any case) leaves the master's entry; nothing is filled."""
    builder = _builder()
    same = MASTER_PSC.replace('CompanionSuite', 'companionsuite')
    assert SO.rebuilt_entry(builder, TRIGGER, (TRIGGER, MASTER_PROPS, {}), (same, MASTER_PSC)) is None
    assert builder.scripts.asked == []


def test_with_entry_replaces_only_that_script():
    """The other script and subrecords stay; the named script's entry is the new one."""
    entry = V.object_scripts([(TRIGGER, {'GameHour': GAME_HOUR}, {})])[6:]
    body = SO.with_entry(b'ACTI', _acti_body(_master_vmad()), TRIGGER.upper(), entry)
    subs = dict(subrecords(body))
    assert subs[b'EDID'] == b'VCG01RemoveDocCarebearModeTrigger\x00'
    assert subs[b'VMAD'] == V.object_scripts([('F3NV_Other', {'Keep': 0x02000001}, {}),
                                              (TRIGGER, {'GameHour': GAME_HOUR}, {})])
    assert SO.with_entry(b'ACTI', _acti_body(_master_vmad()), 'FALLOUTNV_Elsewhere', entry) is None


def _planned(builder, body: bytes) -> bytes:
    """Plan the trigger's override of master ACTI `body` on `builder`; the new entry."""
    entry = V.object_scripts([(TRIGGER, {'GameHour': GAME_HOUR}, {})])[6:]
    builder.script_overrides = {ACTI_ID: (b'ACTI', 0, body, TRIGGER, entry)}
    return entry


def _compiled(tmp_path):
    """A Scripts folder holding the trigger's compiled script."""
    (tmp_path / f'{TRIGGER}.pex').write_bytes(b'')
    return tmp_path


def test_apply_leaves_a_script_that_did_not_compile():
    """No compiled .pex: the master's script still runs, so its record is not overridden."""
    builder = _builder()
    _planned(builder, _acti_body(_master_vmad()))
    SO.apply(builder, Path('nonexistent-scripts-folder'))
    assert list(builder.writer.top_records()) == []
    assert builder.counts[f'changed script left to the master (did not compile) ({TRIGGER})'] == 1


def test_apply_writes_the_master_record_with_the_entry(tmp_path):
    """A record the build does not write is added: the master's body, the new entry, the master's FormID."""
    builder = _builder()
    _planned(builder, _acti_body(_master_vmad()))
    SO.apply(builder, _compiled(tmp_path))
    (blob,) = list(builder.writer.top_records())
    assert struct.unpack_from('<I', blob, 12)[0] == ACTI_ID
    vmad = dict(subrecords(blob[24:]))[b'VMAD']
    assert V.read_entry(vmad, script_spans(b'ACTI', vmad)[1][1])[0][1] == {'GameHour': GAME_HOUR}
    assert builder.counts['master records overridden for a changed script (ACTI)'] == 1


def test_apply_patches_a_record_the_build_writes(tmp_path):
    """A written copy (a quest with its children group after it) gets the entry in place, nothing added."""
    builder = _builder()
    written = pack_fo4_record('ACTI', ACTI_ID, 0, _acti_body(_master_vmad())) + b'GRUPchildren'
    builder.writer.add_record('ACTI', written)
    _planned(builder, _acti_body(_master_vmad()))
    SO.apply(builder, _compiled(tmp_path))
    (blob,) = list(builder.writer.top_records())
    assert blob.endswith(b'GRUPchildren') and blob[:4] == b'ACTI'
    size = struct.unpack_from('<I', blob, 4)[0]
    vmad = dict(subrecords(blob[24:24 + size]))[b'VMAD']
    assert 'GameHour' in V.read_entry(vmad, script_spans(b'ACTI', vmad)[1][1])[0][1]
    assert builder.counts['changed script entry set on a written master record'] == 1


def test_attachers_find_records_in_a_built_master(tmp_path):
    """Every top-level record of a built master whose VMAD attaches a changed script, any case."""
    writer = FO4PluginWriter(masters=['Fallout4.esm'])
    writer.add_record('ACTI', pack_fo4_record('ACTI', 0x0111E65F, 0, _acti_body(_master_vmad())))
    writer.add_record('MISC', pack_fo4_record('MISC', 0x01000800, 0, _acti_body(
        V.object_scripts([('F3NV_Other', {}, {})]))))
    writer.write(str(tmp_path / 'Master.esm'))
    found = SO.attachers([tmp_path / 'Master.esm'], ['Fallout4.esm', 'Master.esm'], {TRIGGER.lower(): TRIGGER})
    assert list(found) == [0x0111E65F]
    assert found[0x0111E65F][0] == b'ACTI' and found[0x0111E65F][3] == TRIGGER
