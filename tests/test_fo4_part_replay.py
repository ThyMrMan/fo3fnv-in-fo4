"""A plugin whose only change is code its meshes or archives parts ran is replayed there, not built again.

See: docs/fork/fo4_plugin_layout.md#build-parts
See: docs/fork/fo4_plugin_layout.md#meshes-replay
"""

import json
import sys
from pathlib import Path

from fo4_import.pipeline import build_plan as BP
from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import part_replay as PR
from fo4_import.pipeline import ran_code as RC
from fo4_import.pipeline.build_inputs import stamp

HERE = 'tests/test_fo4_part_replay.py::'
PACKER, FINISHER, RECORDS_KEY = HERE + '_packer', HERE + '_finisher', HERE + '_records_code'
PARTS = {RC.ARCHIVES: [PACKER, RECORDS_KEY], RC.MESHES: [FINISHER], RC.RECORDS: [RECORDS_KEY]}


def _packer() -> None:
    """Stands for archive code."""


def _finisher() -> None:
    """Stands for collision code."""


def _records_code() -> None:
    """Stands for record code."""


def _record(code: dict, made_reads: dict = None) -> dict:
    """An inputs record with PARTS, `code` and `made_reads` to check, the rest unchanged."""
    masters = {'headers': {}, 'paths': {}, 'held': {}, 'records': {}, 'ledgers': [], 'staged': {}, 'scripts': {}}
    current = {key: BP.identity(key) for key in (PACKER, FINISHER, RECORDS_KEY)}
    return {'code': {**current, **code}, 'code_parts': PARTS, 'made_reads': made_reads or {}, 'files': {},
            'dirs': {}, 'programs': {}, 'natives': {}, 'asked': [], 'masters': masters,
            'environment': {'python': sys.version, 'packages': {}}}


def _parts(monkeypatch, rec: dict, manifest: 'dict | None' = None) -> 'frozenset | None':
    """replay_parts() of a plugin built by pipeline.run with inputs record `rec` and replay `manifest`."""
    monkeypatch.setattr(BP, 'record', lambda p: rec)
    monkeypatch.setattr(BP, 'build_module', lambda p: BP.RUN)
    monkeypatch.setattr(BP.replay_manifest, 'read', lambda p: manifest)
    return BP.replay_parts(Path('Test.esm'))


def test_only_code_that_ran_in_the_replayable_parts_alone_is_replayed(monkeypatch):
    """Archive or collision code replays its parts (collision only with a manifest); code that also ran in records,
    any other change, or none, does not."""
    assert _parts(monkeypatch, _record({PACKER: 'old'})) == {RC.ARCHIVES}
    assert _parts(monkeypatch, _record({FINISHER: 'old'}), {}) == {RC.MESHES}
    assert _parts(monkeypatch, _record({FINISHER: 'old'})) is None
    assert _parts(monkeypatch, _record({RECORDS_KEY: 'old'})) is None
    moved = {**_record({PACKER: 'old'}), 'environment': {'python': 'other', 'packages': {}}}
    assert _parts(monkeypatch, moved) is None
    assert _parts(monkeypatch, _record({})) is None


def _replay(tmp_path: Path, monkeypatch, rec: dict, parts: set, manifest: dict = None) -> tuple:
    """(exit code, inputs record file, calls) of a replay of `parts` whose steps are stubbed; calls names each
    step that ran."""
    plugin, record_file, calls = tmp_path / 'Test.esm', tmp_path / 'Test.esm.inputs.json', []
    plugin.write_bytes(b'')
    record_file.write_text('{}', encoding='utf-8')
    for name, value in (('record', lambda p: rec), ('replay_parts', lambda p: frozenset(parts)),
                        ('inputs_path', lambda p: record_file), ('npcs', lambda p: [])):
        monkeypatch.setattr(PR, name, value)
    monkeypatch.setattr(PR.replay_manifest, 'read', lambda p: manifest)
    for name in ('restore_packed', 'pack_main', 'drop_packed'):
        monkeypatch.setattr(PR, name, lambda *a, name=name: calls.append(name) or 0)
    monkeypatch.setattr(PR, 'faces_and_textures', lambda *a: calls.append('textures') or {})
    monkeypatch.setattr(PR, 'finish_meshes', lambda data, paths, theirs, weapons: calls.append(('finish', paths)) or [])
    monkeypatch.setattr(PR.object_lod, 'bake_all', lambda *a: {})
    monkeypatch.setattr(PR.master_copies, 'drop_loose', lambda *a: 0)
    monkeypatch.setattr(PR.master_copies, 'write_meshes', lambda *a: calls.append('meshes record') or 0)
    monkeypatch.setattr(PR.elric_cache, 'write_mesh', lambda path, raw: calls.append(('held', raw)))
    return PR.replay(plugin), record_file, calls


def test_an_archives_replay_takes_the_code_as_it_is_now(tmp_path, monkeypatch):
    """Archives only: no mesh is finished; after it the inputs record holds each key's identity now."""
    made = tmp_path / 'made.nif'
    made.write_bytes(b'mesh')
    code, record_file, calls = _replay(tmp_path, monkeypatch, _record({PACKER: 'old'}, {str(made): stamp(made)}),
                                       {RC.ARCHIVES})
    assert code == 0 and calls == ['restore_packed', 'textures', 'pack_main', 'drop_packed']
    assert json.loads(record_file.read_text(encoding='utf-8'))['code'][PACKER] == BP.identity(PACKER)


def test_a_meshes_replay_finishes_each_mesh_from_its_kept_pre_elric_bytes(tmp_path, monkeypatch):
    """Each manifest path's pre-Elric bytes come back from the store and are finished, before the archives."""
    monkeypatch.setattr(EC, 'INPUT_STORE', tmp_path / 'store')
    key, nif = EC.keep_input(b'pre-elric'), str(tmp_path / 'Meshes' / 'a.nif')
    manifest = {'pre_elric': {nif: key}, 'theirs': {}, 'weapons': [], 'lod_worlds': [], 'finished': [nif],
                'export': str(tmp_path)}
    code, _, calls = _replay(tmp_path, monkeypatch, _record({FINISHER: 'old'}), {RC.MESHES}, manifest)
    assert code == 0
    assert calls == ['restore_packed', ('held', b'pre-elric'), ('finish', [nif]), 'textures', 'meshes record',
                     'pack_main', 'drop_packed']


def test_a_pre_elric_mesh_gone_from_the_store_needs_a_whole_build(tmp_path, monkeypatch):
    """A manifest naming a pre-Elric SHA-1 the store no longer holds: NEEDS_BUILD, the record dropped."""
    monkeypatch.setattr(EC, 'INPUT_STORE', tmp_path / 'store')
    manifest = {'pre_elric': {'a.nif': '0' * 40}, 'theirs': {}, 'weapons': [], 'lod_worlds': [], 'finished': [],
                'export': str(tmp_path)}
    code, record_file, _ = _replay(tmp_path, monkeypatch, _record({FINISHER: 'old'}), {RC.MESHES}, manifest)
    assert code == BP.NEEDS_BUILD and not record_file.exists()


def test_a_made_file_the_records_read_changed_needs_a_whole_build(tmp_path, monkeypatch):
    """A file the records part read, made by the build, no longer as kept: NEEDS_BUILD, the record dropped."""
    made = tmp_path / 'made.nif'
    made.write_bytes(b'mesh')
    kept = stamp(made)
    made.write_bytes(b'other')
    code, record_file, _ = _replay(tmp_path, monkeypatch, _record({PACKER: 'old'}, {str(made): kept}), {RC.ARCHIVES})
    assert code == BP.NEEDS_BUILD and not record_file.exists()


def test_the_pre_elric_store_keeps_each_nif_once_by_its_bytes(tmp_path, monkeypatch):
    """Two NIFs with the same bytes are one stored file; each reads back as kept; an unknown key reads None."""
    monkeypatch.setattr(EC, 'INPUT_STORE', tmp_path)
    assert EC.keep_input(b'one') == EC.keep_input(b'one') != EC.keep_input(b'two')
    assert EC.kept_input(EC.keep_input(b'one')) == b'one' and EC.kept_input('f' * 40) is None
    assert len([p for p in tmp_path.rglob('*') if p.is_file()]) == 2
