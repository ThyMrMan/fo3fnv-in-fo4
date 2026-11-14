"""A plugin whose only change is code its archives part ran is replayed there, not built again.

See: docs/fork/fo4_plugin_layout.md#build-parts
"""

import json
import sys
from pathlib import Path

from fo4_import.pipeline import archive_replay as AR
from fo4_import.pipeline import build_plan as BP
from fo4_import.pipeline import ran_code as RC
from fo4_import.pipeline.build_inputs import stamp

PACKER, RECORDS_KEY = 'tests/test_fo4_archive_replay.py::_packer', 'tests/test_fo4_archive_replay.py::_records_code'


def _packer() -> None:
    """Stands for archive code."""


def _records_code() -> None:
    """Stands for record code."""


def _record(code: dict, parts: dict, made_reads: dict = None) -> dict:
    """An inputs record with nothing but `code`, `parts` and `made_reads` to check."""
    masters = {'headers': {}, 'paths': {}, 'held': {}, 'records': {}, 'ledgers': [], 'staged': {}, 'scripts': {}}
    return {'code': code, 'code_parts': parts, 'made_reads': made_reads or {}, 'files': {}, 'dirs': {},
            'programs': {}, 'natives': {}, 'asked': [], 'masters': masters,
            'environment': {'python': sys.version, 'packages': {}}}


def _plugin(tmp_path: Path, monkeypatch, rec: dict) -> Path:
    """A plugin built by pipeline.run whose inputs record is `rec`."""
    plugin = tmp_path / 'Test.esm'
    monkeypatch.setattr(BP, 'record', lambda p: rec)
    monkeypatch.setattr(BP, 'build_module', lambda p: BP.RUN)
    return plugin


def test_only_code_that_ran_in_the_archives_alone_is_replayed(tmp_path, monkeypatch):
    """A changed key that ran only in the archives part replays; one that also ran in records, or any other
    change, builds."""
    parts = {RC.ARCHIVES: [PACKER, RECORDS_KEY], RC.RECORDS: [RECORDS_KEY]}
    current = BP.identity(RECORDS_KEY)
    assert BP.replayable(_plugin(tmp_path, monkeypatch, _record({PACKER: 'old', RECORDS_KEY: current}, parts)))
    assert not BP.replayable(_plugin(tmp_path, monkeypatch, _record({PACKER: 'old', RECORDS_KEY: 'old'}, parts)))
    moved = {**_record({PACKER: 'old'}, parts), 'environment': {'python': 'other', 'packages': {}}}
    assert not BP.replayable(_plugin(tmp_path, monkeypatch, moved))
    assert not BP.replayable(_plugin(tmp_path, monkeypatch, _record({PACKER: BP.identity(PACKER)}, parts)))


def _replay(tmp_path: Path, monkeypatch, made: dict) -> tuple:
    """(exit code, inputs record file) of a replay of a plugin whose archive steps are stubbed."""
    plugin, record_file = tmp_path / 'Test.esm', tmp_path / 'Test.esm.inputs.json'
    plugin.write_bytes(b'')
    record_file.write_text('{}', encoding='utf-8')
    rec = _record({PACKER: 'old'}, {RC.ARCHIVES: [PACKER]}, made)
    monkeypatch.setattr(AR, 'record', lambda p: rec)
    monkeypatch.setattr(AR, 'replayable', lambda p: True)
    monkeypatch.setattr(AR, 'inputs_path', lambda p: record_file)
    monkeypatch.setattr(AR, 'npcs', lambda p: [])
    for name in ('restore_packed', 'pack_main', 'drop_packed'):
        monkeypatch.setattr(AR, name, lambda *a: 0)
    monkeypatch.setattr(AR, 'faces_and_textures', lambda *a: {})
    return AR.replay(plugin), record_file


def test_a_replay_takes_the_code_as_it_is_now(tmp_path, monkeypatch):
    """After the replay the inputs record holds each key's identity now, so the plan calls the plugin current."""
    made = tmp_path / 'made.nif'
    made.write_bytes(b'mesh')
    code, record_file = _replay(tmp_path, monkeypatch, {str(made): stamp(made)})
    assert code == 0
    assert json.loads(record_file.read_text(encoding='utf-8'))['code'] == {PACKER: BP.identity(PACKER)}


def test_a_made_file_the_records_read_changed_needs_a_whole_build(tmp_path, monkeypatch):
    """A file the records part read, made by the build, no longer as kept: the record is dropped and the replay
    says NEEDS_BUILD."""
    made = tmp_path / 'made.nif'
    made.write_bytes(b'mesh')
    kept = stamp(made)
    made.write_bytes(b'other')
    code, record_file = _replay(tmp_path, monkeypatch, {str(made): kept})
    assert code == BP.NEEDS_BUILD and not record_file.exists()
