"""The run archive reader (tools/validate/fo4_runs.py) and the build history the stamps keep."""

import json
import os
import time
from pathlib import Path

from fo4_import.base.build_files import BOOKS
from fo4_import.pipeline import build_steps as BS
from tools.validate import fo4_runs as R


def _ticks(seconds: float) -> int:
    """`seconds` (Unix) as FILETIME ticks."""
    return int(seconds * 1e7) + R.EPOCH_TICKS


def _run(runs: Path, name: str, files: dict) -> Path:
    """A run folder `name` listing `files` {name: (size, Unix seconds)}."""
    run = runs / name
    run.mkdir(parents=True)
    rows = [f'{n}\t{size}\t{_ticks(at)}' for n, (size, at) in files.items()]
    (run / R.DATA_FILES).write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return run


def test_finished_build_adds_a_history_line(tmp_path):
    """Each finished stamp adds one history line beside it; a running one adds none."""
    plugin = tmp_path / 'Mod' / 'A.esp'
    plugin.parent.mkdir()
    BS.write_stamp(plugin, 'running', time.time(), {'commit': 'abc'})
    BS.write_stamp(plugin, 'finished', time.time(), {'commit': 'abc', 'argv': ['x']})
    BS.write_stamp(plugin, 'finished', time.time(), {'commit': 'def'})
    lines = (plugin.parent / BOOKS / ('A.esp' + BS.HISTORY_SUFFIX)).read_text(encoding='utf-8').splitlines()
    assert [json.loads(line)['commit'] for line in lines] == ['abc', 'def']
    assert 'argv' not in json.loads(lines[0])


def test_plugin_matched_to_the_build_that_wrote_it(tmp_path):
    """A plugin takes the build started last before it was written, also after the stamp ended (faces); none
    when no build started before it."""
    lines = [{'started': '2026-11-15 10:00:00', 'ended': '2026-11-15 10:10:00', 'commit': 'aaa'},
             {'started': '2026-11-15 12:00:00', 'ended': '2026-11-15 12:10:00', 'commit': 'bbb'}]
    at = time.mktime(time.strptime('2026-11-15 12:05:00', '%Y-%m-%d %H:%M:%S'))
    assert R.built_by(lines, at)['commit'] == 'bbb'
    assert R.built_by(lines, at + 1800)['commit'] == 'bbb'
    assert R.built_by(lines, at - 3600)['commit'] == 'aaa'
    assert R.built_by(lines, at - 3 * 3600) is None


def test_runs_mark_rebuilt_and_replayed(tmp_path, capsys):
    """Against the run before, a changed plugin reads rebuilt; a changed archive alone, archives changed."""
    at = time.mktime(time.strptime('2026-11-15 12:05:00', '%Y-%m-%d %H:%M:%S'))
    history = {'A.esp': [{'started': '2026-11-15 12:00:00', 'ended': '2026-11-15 12:10:00', 'commit': 'c' * 40}],
               'B.esp': []}
    first = R.data_files(_run(tmp_path, '1', {'A.esp': (5, at), 'B.esp': (7, at), 'B - Main.ba2': (1, at)}))
    second = _run(tmp_path, '2', {'A.esp': (6, at), 'B.esp': (7, at), 'B - Main.ba2': (2, at)})
    R.show(second, first, history)
    out = capsys.readouterr().out
    assert 'A.esp: built 2026-11-15 12:10:00 at cccccccc  [rebuilt]' in out
    assert 'B.esp: build not in its history  [archives changed]' in out


def test_archive_copies_logs_written_since_launch(tmp_path):
    """--archive copies the logs newer than the newest run's launch into it, and leaves older ones."""
    runs = tmp_path / 'Fallout4' / 'F3NV' / 'Runs'
    run = _run(runs, '2026-11-15_120000', {})
    script = tmp_path / 'Fallout4' / 'Logs' / 'Script'
    script.mkdir(parents=True)
    old, new = script / 'Papyrus.1.log', script / 'Papyrus.0.log'
    old.write_text('old', encoding='utf-8')
    new.write_text('[11/15/2026 - 12:00:05PM] Papyrus log opened (PC-64)\n', encoding='utf-8')
    launched = (run / R.DATA_FILES).stat().st_mtime
    os.utime(old, (launched - 60, launched - 60))
    os.utime(new, (launched + 60, launched + 60))
    assert R.archive(runs) == 0
    assert sorted(p.name for p in run.glob('*.log')) == ['Papyrus.0.log']
    assert R.opened(run / 'Papyrus.0.log') == '11/15/2026 - 12:00:05PM'
