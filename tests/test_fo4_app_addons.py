"""The app converts a DLC or an imported mod besides the game: found in the game's Data folder or imported from a
mod folder, built into its own output with its masters' outputs as plugin folders, scoped from its export.

See: docs/fork/fo4_gui.md#addons
"""

import struct
from pathlib import Path

import pytest

from fo4_import.app import addons
from fo4_import.app import settings as S
from fo4_import.app import stages as ST

EXPORT = Path('export')


def plugin(path: Path, *masters: str) -> Path:
    """A plugin file whose header lists `masters`."""
    body = b''.join(b'MAST' + struct.pack('<H', len(m) + 1) + m.encode() + b'\0' + b'DATA\x08\x00' + bytes(8)
                    for m in masters)
    path.write_bytes(b'TES4' + struct.pack('<III', len(body), 1, 0) + bytes(8) + body)
    return path


def _settings(tmp_path: Path, chosen: str = '') -> dict:
    """Settings over a game folder holding FalloutNV.esm and Honest Hearts, with `chosen` as the target."""
    s = S.defaults()
    data = tmp_path / 'falloutnv' / 'Data'
    data.mkdir(parents=True)
    plugin(data / 'FalloutNV.esm')
    plugin(data / 'HonestHearts.esm', 'FalloutNV.esm')
    for game in ('fallout4', 'falloutnv'):
        (tmp_path / game / 'Data').mkdir(parents=True, exist_ok=True)
        s['games'][game] = str(tmp_path / game)
    s['work_dir'] = str(tmp_path / 'work')
    addons.add(s, 'falloutnv', 'HonestHearts.esm')
    s['per_source']['falloutnv']['target'] = chosen
    return s


def test_dlc_are_found_by_their_master(tmp_path):
    """A plugin built on the game's master is a DLC; the master itself and unrelated plugins are not."""
    data = tmp_path / 'Data'
    data.mkdir()
    plugin(data / 'FalloutNV.esm')
    plugin(data / 'DeadMoney.esm', 'FalloutNV.esm')
    plugin(data / 'Other.esp', 'Fallout3.esm')
    assert addons.dlc(data, 'FalloutNV.esm') == ['DeadMoney.esm']


def test_a_dlc_builds_into_its_own_folder_on_the_game_output(tmp_path, monkeypatch):
    """The DLC's plugin goes to `F3NV - <stem>` beside the game's output; the game's output is its plugin folder."""
    s = _settings(tmp_path, 'HonestHearts.esm')
    game_out = S.output_dir(s, 'falloutnv')
    assert ST.plugin_path(s, 'falloutnv') == game_out.parent / 'F3NV - HonestHearts' / 'HonestHearts.esm'
    assert ST.master_dirs(s, 'falloutnv') == [game_out]
    assert ST.unavailable(s, 'falloutnv', 'build') == 'build its master FalloutNV.esm first'
    game_out.mkdir(parents=True)
    (game_out / 'FalloutNV.esm').write_bytes(b'')
    monkeypatch.setattr(addons, 'build_scope', lambda export, region: ['--world', 'Zion', '--whole'])
    build = ST.command(s, 'falloutnv', 'build', ST.Scope('world'), tmp_path / 'x.json')
    argv = build()
    assert argv[argv.index('--plugin-dirs') + 1] == str(game_out) and argv[-3:] == ['--world', 'Zion', '--whole']
    assert argv[argv.index('--scripts') + 1] == str(tmp_path / 'work' / 'scripts' / 'HonestHearts.esm')


def test_stages_follow_the_target(tmp_path):
    """A DLC exports with its archives from the game's Data; game-wide stages and the import are the game's."""
    s = _settings(tmp_path, 'HonestHearts.esm')
    export = ST.command(s, 'falloutnv', 'export', ST.Scope(), tmp_path / 'x.json')
    assert export[2:] == ['--export-only', '--extract-only', '--data-dir', str(tmp_path / 'falloutnv' / 'Data'),
                          '-f', 'HonestHearts.esm']
    assert ST.unavailable(s, 'falloutnv', 'helpers') == ST.unavailable(s, 'falloutnv', 'classic') != ''
    assert ST.unavailable(s, 'falloutnv', 'import') == 'only a mod folder is imported'
    s['per_source']['falloutnv']['target'] = ''
    assert ST.target(s, 'falloutnv').game and ST.unavailable(s, 'falloutnv', 'helpers') == ''


def test_a_mod_folder_is_imported_then_exported(tmp_path, monkeypatch):
    """A mod target imports its folder, exports its plugin by name, and reads its masters from the folder."""
    monkeypatch.setattr(ST, 'EXPORT_ROOT', tmp_path / 'export')
    s = _settings(tmp_path)
    mod = tmp_path / 'mods' / 'Better Brotherhood'
    mod.mkdir(parents=True)
    plugin(mod / 'Better Brotherhood.esm', 'FalloutNV.esm', 'HonestHearts.esm')
    assert [p.name for p in addons.mod_plugins(mod)] == ['Better Brotherhood.esm']
    addons.add(s, 'falloutnv', 'Better Brotherhood.esm', str(mod))
    s['per_source']['falloutnv']['target'] = 'Better Brotherhood.esm'
    assert ST.command(s, 'falloutnv', 'import', ST.Scope(), tmp_path / 'x.json')[2:] == ['--import-mod', str(mod)]
    assert ST.command(s, 'falloutnv', 'export', ST.Scope(), tmp_path / 'x.json')[2:] == [
        '--export-only', '-f', 'Better Brotherhood.esm']
    out = S.output_dir(s, 'falloutnv')
    assert ST.master_dirs(s, 'falloutnv') == [out, out.parent / 'F3NV - HonestHearts']
    built = out.parent / 'F3NV - Honest Hearts'
    built.mkdir(parents=True)
    (built / 'HonestHearts.esm.build.json').write_text('{}', encoding='utf-8')
    assert ST.master_dirs(s, 'falloutnv') == [out, built]


@pytest.mark.parametrize('name, want', [
    ('HonestHearts.esm', ['--world', 'WastelandNV', 'NVDLC02ZionCanyon', '--region', '-6', '32', '-6', '32']),
    ('GunRunnersArsenal.esm', ['NVDLC05VendorChestsCell']),
    ('CaravanPack.esm', []),
])
def test_build_scope_matches_the_hand_made_dlc_builds(name, want):
    """The derived scope is what the DLC builds were given by hand."""
    if not (EXPORT / name / '_HEADER.txt').is_file():
        pytest.skip(f'{name} is not exported here')
    assert addons.build_scope(EXPORT / name) == want
