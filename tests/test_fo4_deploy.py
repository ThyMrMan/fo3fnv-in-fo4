"""tools.release.fo4_deploy: copies what changed, lists stale mod files, deletes them only with the flag."""

import json

import pytest

from tools.release import fo4_deploy as D


@pytest.fixture(autouse=True)
def _game_closed(monkeypatch):
    """Tests run the same whether or not Fallout 4 is open."""
    monkeypatch.setattr(D, 'game_running', lambda: False)


def _folders(tmp_path, status='finished'):
    """A build folder and a mod folder with one stale file, one changed file and MO2's meta.ini."""
    build, mod = tmp_path / 'build', tmp_path / 'mod'
    (build / 'Scripts').mkdir(parents=True)
    (mod / 'Scripts').mkdir(parents=True)
    (mod / 'Old').mkdir()
    (build / 'Scripts' / 'A.pex').write_text('new')
    (mod / 'Scripts' / 'a.pex').write_text('old!')
    (mod / 'Old' / 'Gone.dds').write_text('x')
    (mod / 'meta.ini').write_text('x')
    if status:
        (build / ('FalloutNV.esm' + D.STAMP_SUFFIX)).write_text(json.dumps({'status': status}))
    return build, mod


def _run(build, mod, *flags):
    """Run the tool on the two folders."""
    return D.main(['--build', str(build), '--mod', str(mod), *flags])


def test_stale_files_are_listed_and_kept(tmp_path, capsys):
    """Without the flag the changed file is copied over and the stale one only listed."""
    build, mod = _folders(tmp_path)
    assert _run(build, mod) == 0
    assert (mod / 'Scripts' / 'a.pex').read_text() == 'new'
    assert (mod / 'Old' / 'Gone.dds').is_file() and (mod / 'meta.ini').is_file()
    out = capsys.readouterr().out
    assert '1 stale files' in out and 'Gone.dds' in out and 'meta.ini' not in out


def test_delete_stale_deletes_them_and_empty_folders(tmp_path):
    """--delete-stale removes the stale file and its now-empty folder, never meta.ini."""
    build, mod = _folders(tmp_path)
    assert _run(build, mod, '--delete-stale') == 0
    assert not (mod / 'Old').exists() and (mod / 'meta.ini').is_file() and (mod / 'Scripts' / 'a.pex').is_file()


def test_dry_run_changes_nothing(tmp_path):
    """--dry-run copies and deletes nothing, even with --delete-stale."""
    build, mod = _folders(tmp_path)
    assert _run(build, mod, '--dry-run', '--delete-stale') == 0
    assert (mod / 'Scripts' / 'a.pex').read_text() == 'old!' and (mod / 'Old' / 'Gone.dds').is_file()


@pytest.mark.parametrize('status, flags', [('running', ()), ('failed', ()), (None, ('--delete-stale',))])
def test_unfinished_builds_are_refused(tmp_path, status, flags):
    """A running or failed stamp refuses any deploy; deleting also needs a finished stamp."""
    build, mod = _folders(tmp_path, status)
    with pytest.raises(SystemExit):
        _run(build, mod, *flags)
    assert (mod / 'Old' / 'Gone.dds').is_file()
