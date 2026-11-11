"""tools.release.fo4_deploy: copies what changed, lists stale mod files, deletes them only with the flag."""

import json

import pytest

from fo4_import.base.ba2_write import write_general
from tools.release import fo4_deploy as D

#: A build stamp's start time (the deploy clears hotfixes older than it).
STARTED = '2026-11-05 00:00:00'


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
        (build / ('FalloutNV.esm' + D.STAMP_SUFFIX)).write_text(json.dumps({'status': status, 'started': STARTED}))
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


def test_the_build_input_record_is_not_shipped(tmp_path):
    """<plugin>.inputs.json and <plugin>.record/ are not copied, and a deployed copy is deleted as stale; the ledger
    beside them ships."""
    build, mod = _folders(tmp_path)
    for folder in (build, mod):
        (folder / 'FalloutNV.esm.record').mkdir()
        (folder / 'FalloutNV.esm.record' / '12.json').write_text('{}')
        (folder / 'FalloutNV.esm.inputs.json').write_text('{}')
    (build / 'FalloutNV.formids.tsv').write_text('ledger')
    assert _run(build, mod, '--delete-stale') == 0
    assert not (mod / 'FalloutNV.esm.record').exists() and not (mod / 'FalloutNV.esm.inputs.json').exists()
    assert (mod / 'FalloutNV.formids.tsv').read_text() == 'ledger'


def test_the_xdi_era_hub_is_retired_from_the_mods_beside(tmp_path):
    """The hub plugin and its links in a mod beside --mod are deleted; its other files and --dry-run's stay."""
    build, mod = _folders(tmp_path)
    hub = tmp_path / 'fo4_dialogue_menu'
    links = hub / 'F4SE' / 'Plugins' / 'F3NV_Menus'
    links.mkdir(parents=True)
    for path in (hub / 'F3NV_MenuHub.esp', links / 'F3NV_MenuHub.txt', links / 'F3NV_MenuTest.txt'):
        path.write_text('x')
    assert _run(build, mod, '--dry-run') == 0 and (hub / 'F3NV_MenuHub.esp').is_file()
    assert _run(build, mod) == 0
    assert not (hub / 'F3NV_MenuHub.esp').exists() and not (links / 'F3NV_MenuHub.txt').exists()
    assert (links / 'F3NV_MenuTest.txt').is_file()


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


def test_a_dlc_deploys_only_the_files_its_list_names_under_its_listed_folders(tmp_path, capsys):
    """--plugin: an old rig the list no longer names is neither copied nor kept in the mod; a listed rig, the
    plugin and a script (outside the listed folders) are copied."""
    build, mod = tmp_path / 'build', tmp_path / 'mod'
    names = ('DLC.esm', 'Scripts/A.pex', 'Meshes/Actors/FNVGhost/skeleton.nif', 'Meshes/Actors/FNVGecko/skeleton.nif')
    for name in names:
        (build / name).parent.mkdir(parents=True, exist_ok=True)
        (build / name).write_text('x')
    (mod / 'Meshes/Actors/FNVGecko').mkdir(parents=True)
    (mod / 'Meshes/Actors/FNVGecko/skeleton.nif').write_text('old')
    (build / ('DLC.esm' + D.STAMP_SUFFIX)).write_text(json.dumps({'status': 'finished', 'started': STARTED}))
    (build / 'DLC.esm.files.txt').write_text('Meshes/Actors/FNVGhost/skeleton.nif\n')
    assert _run(build, mod, '--plugin', 'DLC.esm') == 0
    assert all((mod / name).is_file() for name in names[:3])
    assert (mod / 'Meshes/Actors/FNVGecko/skeleton.nif').read_text() == 'old'
    out = capsys.readouterr().out
    assert '1 build files under its listed folders' in out and '1 stale files' in out and 'FNVGecko' in out


def test_loose_files_an_archive_holds_ship_only_in_it(tmp_path, capsys):
    """A build mesh the Main archive holds is not copied, and the mod folder's loose copy (which would hide the
    archived one) is deleted even without --delete-stale; the archive and a loose script ship."""
    build, mod = _folders(tmp_path)
    (build / 'Meshes' / 'fnv').mkdir(parents=True)
    (build / 'Meshes' / 'fnv' / 'Cup.nif').write_text('cup')
    write_general({'Meshes/fnv/Cup.nif': build / 'Meshes' / 'fnv' / 'Cup.nif'}, build / 'FalloutNV - Main.ba2')
    (mod / 'meshes' / 'fnv').mkdir(parents=True)
    (mod / 'meshes' / 'fnv' / 'cup.nif').write_text('old')
    assert _run(build, mod, '--dry-run') == 0 and (mod / 'meshes' / 'fnv' / 'cup.nif').is_file()
    assert _run(build, mod) == 0
    assert not (mod / 'meshes').exists() and (mod / 'FalloutNV - Main.ba2').is_file()
    assert (mod / 'Scripts' / 'a.pex').read_text() == 'new' and (mod / 'Old' / 'Gone.dds').is_file()
    assert '1 loose files in the mod folder that the archives hold' in capsys.readouterr().out


def test_a_dlc_without_a_file_list_is_refused(tmp_path):
    """--plugin needs the plugin's file list."""
    build, mod = _folders(tmp_path)
    with pytest.raises(SystemExit):
        _run(build, mod, '--plugin', 'DLC.esm')
