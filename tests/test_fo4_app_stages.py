"""fo4_import.app.stages and runner: command lines from settings, what can run, packaging, running."""

import os
import sys
import zipfile
from pathlib import Path

from fo4_import.app import settings as S
from fo4_import.app import stages as ST
from fo4_import.app.runner import Runner


def _settings(tmp_path: Path) -> dict:
    """Settings with every game folder, work and output folders under `tmp_path`."""
    s = S.defaults()
    for game in s['games']:
        (tmp_path / game / 'Data').mkdir(parents=True)
        s['games'][game] = str(tmp_path / game)
    s['work_dir'] = str(tmp_path / 'work')
    s['mod_sources'] = [{'folder': str(tmp_path / 'mods'), 'kind': 'folder_of_mods'}]
    return s


def test_build_arguments_follow_the_choices(tmp_path):
    """The build writes into the output folder, reads the settings' mod sources and scopes as asked."""
    s = _settings(tmp_path)
    s['per_source']['falloutnv']['profile'] = 'look'
    s['per_source']['falloutnv']['replacements'] = {'where': 'custom', 'path': str(tmp_path / 'none.json')}
    cmd = ST.command(s, 'falloutnv', 'build', ST.Scope('region', (1, 2, 3, 4), 6), tmp_path / 'fo4_app.json')
    out = tmp_path / 'work' / 'output' / 'FalloutNV'
    assert cmd[1:3] == ['-m', 'fo4_import.pipeline.run']
    assert cmd[cmd.index('--out') + 1] == str(out / 'FalloutNV.esm') and cmd[cmd.index('--data') + 1] == str(out)
    assert cmd[cmd.index('--region') + 1:cmd.index('--region') + 5] == ['1', '2', '3', '4']
    assert cmd[cmd.index('--profile') + 1] == 'look' and cmd[cmd.index('--workers') + 1] == '6'
    assert cmd[cmd.index('--mod-sources') + 1] == str(tmp_path / 'fo4_app.json')
    assert '--replacements' not in cmd and cmd[-1] == 'GSDocMitchellHouse'
    test = ST.command(s, 'falloutnv', 'build', ST.Scope(), tmp_path / 'x.json')
    assert test[test.index('--around') + 1:test.index('--around') + 3] == ['-18', '0']
    whole = ST.command(s, 'falloutnv', 'build', ST.Scope('world'), tmp_path / 'x.json')
    assert whole[whole.index('--world') + 1:whole.index('--whole')] == ['WastelandNV', 'reached']


def test_a_chosen_scripts_folder_is_used(tmp_path):
    """Scripts go to the work folder by default, else to the chosen (an earlier run's) folder."""
    s = _settings(tmp_path)
    build = ST.command(s, 'falloutnv', 'build', ST.Scope(), tmp_path / 'x.json')
    assert build[build.index('--scripts') + 1] == str(tmp_path / 'work' / 'scripts' / 'FalloutNV.esm')
    s['per_source']['falloutnv']['scripts'] = str(tmp_path / 'old')
    assert ST.command(s, 'falloutnv', 'scripts', ST.Scope(), tmp_path / 'x.json')[-3] == str(tmp_path / 'old')


def test_found_says_what_earlier_runs_left(tmp_path, monkeypatch):
    """The export is done; scripts are done only when newer than the export; built plugins are named."""
    monkeypatch.setattr(ST, 'EXPORT_ROOT', tmp_path / 'export')
    s = _settings(tmp_path)
    assert [ST.found(s, 'falloutnv', k) for k, _ in ST.ORDER] == [None] * len(ST.ORDER)
    header = tmp_path / 'export' / 'FalloutNV.esm' / '_HEADER.txt'
    header.parent.mkdir(parents=True)
    header.write_text('x')
    scripts = S.scripts_dir(s, 'falloutnv')
    scripts.mkdir(parents=True)
    (scripts / 'A.psc').write_text('x')
    os.utime(scripts / 'A.psc', (header.stat().st_mtime - 60,) * 2)
    assert ST.found(s, 'falloutnv', 'export').done
    assert not ST.found(s, 'falloutnv', 'scripts').done and 'older' in ST.found(s, 'falloutnv', 'scripts').text
    os.utime(scripts / 'A.psc', (header.stat().st_mtime + 60,) * 2)
    assert ST.found(s, 'falloutnv', 'scripts').done
    ST.plugin_path(s, 'falloutnv').parent.mkdir(parents=True)
    ST.plugin_path(s, 'falloutnv').write_text('x')
    built = ST.found(s, 'falloutnv', 'build')
    assert built.text.startswith('FalloutNV.esm built') and not built.done


def test_export_reads_the_chosen_game_folder(tmp_path):
    """Export runs convert.py on the source master with the chosen game's Data folder."""
    cmd = ST.command(_settings(tmp_path), 'falloutnv', 'export', ST.Scope(), tmp_path / 'x.json')
    assert cmd[2:5] == ['--export-only', '-f', 'FalloutNV.esm']
    assert cmd[-1] == str(tmp_path / 'falloutnv' / 'Data')


def test_what_cannot_run_says_why(tmp_path):
    """FO3 builds nothing yet; Windows-only stages need Windows; a missing game folder blocks its stages."""
    s = _settings(tmp_path)
    assert ST.unavailable(s, 'falloutnv', 'build', 'win32') == ''
    assert 'does not support' in ST.unavailable(s, 'fallout3', 'build', 'win32')
    assert ST.unavailable(s, 'fallout3', 'export', 'win32') == ''
    assert 'Windows' in ST.unavailable(s, 'falloutnv', 'scripts', 'linux')
    assert ST.unavailable(s, 'falloutnv', 'helpers', 'linux') == ''
    s['games']['fallout4'] = str(tmp_path / 'missing')
    assert 'Fallout 4' in ST.unavailable(s, 'falloutnv', 'check', 'win32')
    assert 'Fallout 4' in ST.unavailable(s, 'falloutnv', 'fo4edit', 'win32')
    assert ST.unavailable(s, 'falloutnv', 'export', 'win32') == ''


def test_check_is_the_fast_reference_check_and_fo4edit_is_optional(tmp_path):
    """Check runs fo4_ref_check on any OS; FO4Edit's full check is its own Windows-only stage, unticked by default."""
    s = _settings(tmp_path)
    check = ST.command(s, 'falloutnv', 'check', ST.Scope(), tmp_path / 'x.json')
    fo4edit = ST.command(s, 'falloutnv', 'fo4edit', ST.Scope(), tmp_path / 'x.json')
    assert check[1:3] == ['-m', 'tools.validate.fo4_ref_check'] and fo4edit[1:3] == ['-m', 'tools.validate.fo4_check']
    assert check[3] == str(ST.plugin_path(s, 'falloutnv')) and check[4] == '--plugin-dirs'
    assert ST.unavailable(s, 'falloutnv', 'check', 'linux') == ''
    assert 'Windows' in ST.unavailable(s, 'falloutnv', 'fo4edit', 'linux')
    assert ST.OPTIONAL == {'fo4edit'} and [k for k, _ in ST.ORDER][-2:] == ['check', 'fo4edit']


def test_zip_output_is_packaged(tmp_path):
    """With zip output the folder is zipped beside itself; with folder output nothing is made."""
    s = _settings(tmp_path)
    out = S.output_dir(s, 'falloutnv')
    out.mkdir(parents=True)
    (out / 'FalloutNV.esm').write_bytes(b'x')
    assert ST.package(s, 'falloutnv') is None
    s['per_source']['falloutnv']['output']['kind'] = 'zip'
    made = ST.package(s, 'falloutnv')
    assert made == out.with_suffix('.zip') and zipfile.ZipFile(made).namelist() == ['FalloutNV.esm']


def test_runner_streams_and_stops_at_a_failure():
    """Each stage's lines arrive in order; a failing stage ends the run and its errors become warnings."""
    py = sys.executable
    plan = [('a', 'First', [py, '-c', 'print("one"); print("two")']),
            ('b', 'Second', [py, '-c', 'import sys; print("ERROR: bad"); sys.exit(3)']),
            ('c', 'Third', [py, '-c', 'print("never")'])]
    lines = []
    runner = Runner(plan)
    results = runner.run(lines.append)
    assert [(r.key, r.code) for r in results] == [('a', 0), ('b', 3)]
    assert lines[:3] == ['=== First', 'one', 'two'] and 'never' not in lines
    assert runner.warnings == ['ERROR: bad']
