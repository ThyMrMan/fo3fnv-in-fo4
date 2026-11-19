"""The animation data stage is skipped only while everything its last live run read and wrote is unchanged.

See: docs/fork/research/anim_text_data.md#skip
"""

import os

import pytest

from fo4_import.havok import anim_text_skip as S
from fo4_import.pipeline import work_cache


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """(data folder, master folder, key, make) with a clip only the master has and one in neither."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'work')
    data, master = tmp_path / 'data', tmp_path / 'master'
    (master / 'Meshes').mkdir(parents=True)
    (master / 'Meshes' / 'a.hkx').write_bytes(b'clip a')
    data.mkdir()

    def make(logs):
        """Read both clips through the logged reader and write one file from them."""
        read = S.logged_reader(logs, data, master)
        out = data / 'Meshes' / 'AnimTextData' / 'x.txt'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((read('a.hkx') or b'') + (read('b.hkx') or b''))
        return [out], {7: 8}
    return data, master, ('key',), make


def test_an_unchanged_run_is_kept_and_its_files_touched(folders):
    """The second build finds the kept run, its template entries, and touches what it wrote."""
    data, master, key, make = folders
    S.live(key, data, make)
    out = data / 'Meshes' / 'AnimTextData' / 'x.txt'
    os.utime(out, ns=(1, 1))
    assert S.kept(key, [data, master], data) is None
    S.live(key, data, make)
    run = S.kept(key, [data, master], data)
    assert run is not None and run['templates'] == {7: 8} and out.stat().st_mtime_ns > 1
    assert S.kept(key, [data, master], data) is not None


@pytest.mark.parametrize('change', ['master edited', 'own copy added', 'missing clip added', 'output gone'])
def test_a_changed_read_or_output_runs_live(folders, change):
    """Any read finding other bytes or another place, or a written file gone, makes kept() None."""
    data, master, key, make = folders
    S.live(key, data, make)
    if change == 'master edited':
        (master / 'Meshes' / 'a.hkx').write_bytes(b'clip A')
    elif change == 'own copy added':
        (data / 'Meshes' / 'a.hkx').write_bytes(b'clip a')
    elif change == 'missing clip added':
        (master / 'Meshes' / 'b.hkx').write_bytes(b'clip b')
    else:
        (data / 'Meshes' / 'AnimTextData' / 'x.txt').unlink()
    assert S.kept(key, [data, master], data) is None
