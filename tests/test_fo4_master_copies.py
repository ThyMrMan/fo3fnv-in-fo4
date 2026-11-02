"""fo4_import.pipeline.master_copies: a DLC build leaves to its master what the master's build already ships.

See: docs/fork/fo4_plugin_layout.md#dlc-build
"""

import json
from types import SimpleNamespace

from fo4_import.base import ba2_pack as BP
from fo4_import.pipeline import master_copies as MC


def _write(path, data: bytes):
    """Write `data` to `path`, its folder made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_loose_copies_of_the_masters_files_are_dropped(tmp_path):
    """Same path and bytes as the master's: dropped; different bytes, own files and top-level files stay."""
    dlc, game = tmp_path / 'dlc', tmp_path / 'game'
    same = _write(dlc / 'Meshes' / 'fnv' / 'a.nif', b'mesh')
    _write(game / 'Meshes' / 'fnv' / 'a.nif', b'mesh')
    changed = _write(dlc / 'Meshes' / 'Actors' / 'clip.hkx', b'dlc pose')
    _write(game / 'Meshes' / 'Actors' / 'clip.hkx', b'game pose')
    own = _write(dlc / 'Materials' / 'fnv' / 'gun.bgsm', b'own')
    top = _write(dlc / 'notes.txt', b'x')
    _write(game / 'notes.txt', b'x')
    assert MC.drop_loose(dlc, [game]) == 1
    assert not same.exists() and changed.exists() and own.exists() and top.exists()


def test_master_dirs_leave_out_the_builds_own_folder(tmp_path):
    """A master built into the same folder is not a master folder to compare against."""
    built = [tmp_path / 'game' / 'G.esm', tmp_path / 'dlc' / 'X.esm']
    builder = SimpleNamespace(data_dir=tmp_path / 'dlc', built=built)
    assert MC.master_dirs(builder) == [tmp_path / 'game']


def test_a_texture_the_master_packed_alike_is_not_staged(tmp_path, monkeypatch):
    """Same key and signature as the master's last pack: skipped; another signature is staged."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    monkeypatch.setattr(BP, '_RUNS', {})
    dlc, game = tmp_path / 'dlc', tmp_path / 'game'
    _write(BP.staging_root(game) / BP.MANIFEST, json.dumps({'fnv/a.dds': [3, 0, 'sig a']}).encode())
    MC.share(SimpleNamespace(data_dir=dlc, built=[game / 'G.esm']))
    plan = lambda sig: lambda: (sig, lambda target: target.write_bytes(b'dds'))
    assert not BP.stage_texture(dlc, 'fnv\\a.dds', plan('sig a'))
    assert BP.stage_texture(dlc, 'fnv\\b.dds', plan('sig a')) and BP.stage_texture(dlc, 'fnv\\c.dds', plan('x'))
    assert not (dlc / 'Textures' / 'fnv' / 'a.dds').exists()


def test_a_sound_from_the_masters_export_the_master_converted_is_left_to_it(tmp_path, monkeypatch):
    """A master export's sound the master converted: no job, its old copy deleted; the DLC's own sound runs."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    dlc, game, export = tmp_path / 'dlc', tmp_path / 'game', tmp_path / 'export' / 'DLC.esm'
    rel = ('Sound', 'FX', 'FNV', 'a.xwm')
    _write(BP.sound_root(game).joinpath(*rel), b'x')
    old = _write(BP.sound_root(dlc).joinpath(*rel), b'x')
    game_job = (tmp_path / 'export' / 'Game.esm' / 'sound' / 'a.wav', old, None)
    own_job = (export / 'sound' / 'a.wav', old, None)
    assert MC.master_sound(game_job, export, dlc, [game]) and not old.exists()
    assert not MC.master_sound(own_job, export, dlc, [game]) and not MC.master_sound(game_job, export, dlc, [])


def test_a_sound_written_loose_is_not_a_master_copy(tmp_path, monkeypatch):
    """Music goes loose into the data folder, outside the sound staging: converted, not compared."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    dlc, game = tmp_path / 'dlc', tmp_path / 'game'
    music = (tmp_path / 'export' / 'Game.esm' / 'music' / 'a.mp3', dlc / 'Music' / 'FNV' / 'a.xwm', None)
    assert not MC.master_sound(music, tmp_path / 'export' / 'DLC.esm', dlc, [game])
