"""fo4_import.app.stages and runner: command lines from settings, what can run, packaging, running."""

import sys
import zipfile
from pathlib import Path

from core import run_log
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
    assert cmd[cmd.index('--resources') + 1] == 'balanced'
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
    build = ST.command(s, 'falloutnv', 'build', ST.Scope(), tmp_path / 'x.json')
    assert build[build.index('--scripts') + 1] == str(tmp_path / 'old')


def test_the_build_converts_scripts_itself():
    """No scripts stage: the build converts --scripts itself."""
    assert 'scripts' not in dict(ST.ORDER) and 'scripts' not in ST.WINDOWS_TOOLS


def test_found_says_what_earlier_runs_left(tmp_path, monkeypatch):
    """The export is done; built plugins are named."""
    monkeypatch.setattr(ST, 'EXPORT_ROOT', tmp_path / 'export')
    s = _settings(tmp_path)
    assert [ST.found(s, 'falloutnv', k) for k, _ in ST.ORDER] == [None] * len(ST.ORDER)
    header = tmp_path / 'export' / 'FalloutNV.esm' / '_HEADER.txt'
    header.parent.mkdir(parents=True)
    header.write_text('x')
    assert ST.found(s, 'falloutnv', 'export').done
    ST.plugin_path(s, 'falloutnv').parent.mkdir(parents=True)
    ST.plugin_path(s, 'falloutnv').write_text('x')
    built = ST.found(s, 'falloutnv', 'build')
    assert built.text.startswith('FalloutNV.esm built') and not built.done


def test_export_reads_the_chosen_game_folder(tmp_path):
    """Export runs convert.py, archives too, with the game Data folder."""
    cmd = ST.command(_settings(tmp_path), 'falloutnv', 'export', ST.Scope(), tmp_path / 'x.json')
    assert cmd[2:] == ['--export-only', '--extract-only', '--data-dir', str(tmp_path / 'falloutnv' / 'Data'), '-f',
                       'FalloutNV.esm']


def test_what_cannot_run_says_why(tmp_path):
    """FO3 builds but has no Classic Look; the build runs on any OS; a missing game folder blocks its stages."""
    s = _settings(tmp_path)
    assert ST.unavailable(s, 'falloutnv', 'build', 'win32') == ST.unavailable(s, 'fallout3', 'build', 'win32') == ''
    assert 'New Vegas only' in ST.unavailable(s, 'fallout3', 'classic', 'win32')
    assert ST.unavailable(s, 'fallout3', 'export', 'win32') == ''
    assert ST.unavailable(s, 'falloutnv', 'build', 'linux') == ST.unavailable(s, 'falloutnv', 'helpers', 'linux') == ''
    s['games']['fallout4'] = str(tmp_path / 'missing')
    assert 'Fallout 4' in ST.unavailable(s, 'falloutnv', 'check', 'win32')
    assert 'Fallout 4' in ST.unavailable(s, 'falloutnv', 'fo4edit', 'win32')
    assert ST.unavailable(s, 'falloutnv', 'export', 'win32') == ''


def test_the_next_step_and_each_rows_state_follow_what_is_built(tmp_path, monkeypatch):
    """Without its master the game is not pickable; unbuilt, Convert builds it and an add-on waits on it; built, the
    next step is rebuilding or Finished."""
    s = _settings(tmp_path)
    assert ST.game_problem(s, 'falloutnv') and 'folder on the Setup screen' in ST.next_step(s, 'falloutnv')
    (tmp_path / 'falloutnv' / 'Data' / 'FalloutNV.esm').write_bytes(b'')
    assert ST.game_problem(s, 'falloutnv') == '' and ST.next_step(s, 'falloutnv').startswith('Click Convert to build')
    assert ST.row_state(s, 'falloutnv', '') == 'not built yet'
    assert ST.row_state(s, 'falloutnv', 'DeadMoney.esm') == 'convert FalloutNV.esm first'
    game = ST.plugin_path(s, 'falloutnv')
    game.parent.mkdir(parents=True)
    game.write_bytes(b'')
    monkeypatch.setattr(ST.build_plan, 'record', lambda plugin: {} if plugin == game else None)
    assert ST.row_state(s, 'falloutnv', '').startswith('built ') and 'is built' in ST.next_step(s, 'falloutnv')
    assert ST.row_state(s, 'falloutnv', 'DeadMoney.esm') == 'not built yet'


def test_check_is_the_fast_reference_check_and_fo4edit_is_optional(tmp_path):
    """Check runs fo4_ref_check on any OS; FO4Edit's full check is its own Windows-only stage, unticked by default."""
    s = _settings(tmp_path)
    check = ST.command(s, 'falloutnv', 'check', ST.Scope(), tmp_path / 'x.json')
    fo4edit = ST.command(s, 'falloutnv', 'fo4edit', ST.Scope(), tmp_path / 'x.json')
    assert check[1:3] == ['-m', 'tools.validate.fo4_ref_check'] and fo4edit[1:3] == ['-m', 'tools.validate.fo4_check']
    assert check[3] == str(ST.plugin_path(s, 'falloutnv')) and check[4] == '--plugin-dirs'
    assert ST.unavailable(s, 'falloutnv', 'check', 'linux') == ''
    assert 'Windows' in ST.unavailable(s, 'falloutnv', 'fo4edit', 'linux')
    assert ST.OPTIONAL == {'classic', 'fo4edit'} and [k for k, _ in ST.ORDER][-3:] == ['classic', 'check', 'fo4edit']


def test_rebuild_what_changed_covers_the_target_its_masters_and_the_mods_built_on_it(tmp_path, monkeypatch):
    """The game and three mods are built (C on A, A and B on the game); for target A, build_plan --run gets the
    game, A and C, not B, then D, built on C beside the output but not an add-on; it needs a recorded build of A;
    a recorded build or faces run counts as done."""
    s = _settings(tmp_path)
    for name in ('A.esp', 'B.esp', 'C.esp'):
        ST.addons.add(s, 'falloutnv', name)
    game = ST.plugin_path(s, 'falloutnv')
    mods = {n: ST.addons.default_output(s, 'falloutnv', f'{n}.esp') / f'{n}.esp' for n in 'ABC'}
    masters = {mods['A'].resolve(): [game], mods['B'].resolve(): [game], mods['C'].resolve(): [mods['A']]}
    recorded = {game.resolve(), mods['A'].resolve(), mods['B'].resolve(), mods['C'].resolve()}
    monkeypatch.setattr(ST.build_plan, 'record', lambda p: {} if Path(p).resolve() in recorded else None)
    monkeypatch.setattr(ST.build_plan, 'masters_of', lambda p: masters.get(Path(p).resolve(), []))
    monkeypatch.setattr(ST, 'faces_stamp', lambda p: {'status': 'finished', 'ended': 'then'})
    s['per_source']['falloutnv']['target'] = 'A.esp'
    assert ST.rebuilt(s, 'falloutnv') == [game, mods['A'], mods['C']]
    other = game.parent.parent / 'F3NV - D' / 'D.esp'
    other.parent.mkdir(parents=True)
    other.write_text('x')
    recorded.add(other.resolve())
    masters[other.resolve()] = [mods['C']]
    assert ST.rebuilt(s, 'falloutnv') == [game, mods['A'], mods['C'], other]
    argv = ST.command(s, 'falloutnv', 'update', ST.Scope(), tmp_path / 'x.json')()
    assert argv[1:4] == ['-m', 'fo4_import.pipeline.build_plan', '--run']
    assert argv[4:] == [str(game), str(mods['A']), str(mods['C']), str(other)]
    assert ST.unavailable(s, 'falloutnv', 'update', 'win32') == '' and ST.found(s, 'falloutnv', 'faces').done
    mods['A'].parent.mkdir(parents=True)
    mods['A'].write_text('x')
    assert ST.found(s, 'falloutnv', 'build').done
    recorded.discard(mods['A'].resolve())
    assert 'build it once' in ST.unavailable(s, 'falloutnv', 'update', 'win32')
    assert not ST.found(s, 'falloutnv', 'build').done


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


def test_runner_streams_logs_and_stops_at_a_failure(tmp_path, monkeypatch):
    """Each stage's lines arrive in order and go to one run log named for the plugin, which the stages are told of;
    a failing stage ends the run and its errors become warnings."""
    monkeypatch.setenv(run_log.LOGS_DIR_ENV_VAR, str(tmp_path))
    py = sys.executable
    plan = [('a', 'First', [py, '-c', 'import os; print("one"); print(os.environ["TESCONV_RUN_LOG"] != "")']),
            ('b', 'Second', [py, '-c', 'import sys; print("ERROR: bad"); sys.exit(3)']),
            ('c', 'Third', [py, '-c', 'print("never")'])]
    lines = []
    runner = Runner(plan, name='FalloutNV.esm')
    results = runner.run(lines.append)
    assert [(r.key, r.code) for r in results] == [('a', 0), ('b', 3)]
    assert lines[:3] == ['=== First', 'one', 'True'] and 'never' not in lines
    assert runner.warnings == ['ERROR: bad']
    log = next(tmp_path.glob('run-*-FalloutNV.esm.log')).read_text(encoding='utf-8')
    assert 'ERROR: bad' in log and '=== Second: failed (3)' in log and 'stopped or failed' in log


def test_the_estimate_reads_the_last_build_else_the_export_else_nothing(tmp_path, monkeypatch):
    """No export and no build: no line; an export: its cold and cached estimate; a finished build's stamp wins."""
    s = _settings(tmp_path)
    export = tmp_path / 'export' / 'FalloutNV.esm'
    monkeypatch.setattr(ST, 'export_dir', lambda settings, source: export)
    assert ST.estimate(s, 'falloutnv') == ''
    export.mkdir(parents=True)
    (export / 'NPC_.txt').write_text('---RECORD_BEGIN---\n' * 50)
    assert 'from its export' in ST.estimate(s, 'falloutnv') and 'cold' in ST.estimate(s, 'falloutnv')
    stamp = ST.stamp_path(ST.plugin_path(s, 'falloutnv'))
    stamp.parent.mkdir(parents=True)
    stamp.write_text('{"status": "finished", "stages": {"people": {"seconds": 1.0}}, "counts": {"NPC_": 5}}')
    assert 'from its last build' in ST.estimate(s, 'falloutnv')
