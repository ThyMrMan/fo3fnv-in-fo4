"""List the Fallout 4 play-test runs F3NV.dll archived, each with its logs and the build of every plugin it loaded.

    py -3.14 -m tools.validate.fo4_runs [--last N] [--archive] [--mods DIR]

While the Trace mod is on, each launch copies the previous run's logs into that run's folder (My Games\\Fallout4\\
F3NV\\Runs\\<launch time>) and lists the Data files the new run loads. A plugin's build is the one in its build
history (or current stamp) started last before the plugin file was written: its commit and the files then
changed. A run marks what changed since the run before it: a rebuilt plugin, or only its archives (a parts
replay). `--archive` copies the logs of the run just played into its folder now, as the next launch would. Pass a
run's Papyrus.0.log to fo4_trace with --log.

See: docs/fork/fo4_condition.md#run-archive
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from fo4_import.app import mo2_setup
from fo4_import.app import settings as S
from fo4_import.base.build_files import BOOKS
from fo4_import.pipeline.build_steps import HISTORY_SUFFIX, STAMP_SUFFIX
from tools.validate.fo4_trace import my_games

#: The file a run folder lists its Data files in (name, size, FILETIME ticks), written at launch.
DATA_FILES = 'data_files.tsv'
#: FILETIME ticks (100 ns since 1601) at the Unix epoch.
EPOCH_TICKS = 116444736000000000
#: The logs a run keeps: (folder under My Games, name pattern).
LOGS = (('Logs/Script', 'Papyrus.*.log'), ('F4SE', 'F3NV*.log'), ('F4SE', 'crash-*.log'))
PLUGIN_EXTS = ('.esm', '.esp', '.esl')
_OPENED = re.compile(r'^\[([^\]]+)\] Papyrus log opened')
_STAMP_TIME = '%Y-%m-%d %H:%M:%S'


def runs_dir() -> 'Path | None':
    """The run archive folder, or None without a My Games folder."""
    games = my_games()
    return games / 'F3NV' / 'Runs' if games else None


def data_files(run: Path) -> dict:
    """{name: (size, Unix write time)} of a run's DATA_FILES, {} when none."""
    listed = run / DATA_FILES
    rows = [line.split('\t') for line in listed.read_text(encoding='utf-8').splitlines()] if listed.exists() else []
    return {row[0]: (int(row[1]), (int(row[2]) - EPOCH_TICKS) / 1e7) for row in rows if len(row) == 3}


def builds(mods: Path) -> dict:
    """{plugin name: [build line]} from every mod's build history and finished stamp (started/ended as seconds)."""
    found = {}
    for books in mods.glob(f'*/{BOOKS}'):
        for history in books.glob(f'*{HISTORY_SUFFIX}'):
            lines = [json.loads(text) for text in history.read_text(encoding='utf-8').splitlines() if text]
            found.setdefault(history.name[:-len(HISTORY_SUFFIX)], []).extend(lines)
        for stamp in books.glob(f'*{STAMP_SUFFIX}'):
            body = json.loads(stamp.read_text(encoding='utf-8'))
            if body.get('status') == 'finished':
                found.setdefault(stamp.name[:-len(STAMP_SUFFIX)], []).append(body)
    return found


def built_by(lines: list, written: float) -> 'dict | None':
    """The finished build line started last before the file write time `written` (steps after a build, such as
    the faces, may write the plugin after its stamp ends); None when none started before it."""
    started = [(datetime.strptime(line['started'], _STAMP_TIME).timestamp(), i) for i, line in enumerate(lines)
               if line.get('ended')]
    before = max(((at, i) for at, i in started if at <= written), default=None)
    return lines[before[1]] if before else None


def opened(log: Path) -> str:
    """When a Papyrus log was opened (its first line), or '?'."""
    with log.open(encoding='utf-8', errors='replace') as text:
        m = _OPENED.match(text.readline())
    return m[1] if m else '?'


def describe(name: str, files: dict, before: dict, history: dict) -> str:
    """One plugin of a run: its build (commit, changed files) and what changed since the run `before`."""
    line = built_by(history.get(name, []), files[name][1])
    build = (f"built {line['ended']} at {line.get('commit', '')[:8] or '?'}"
             + (f" +{len(line['changed files'])} changed" if line.get('changed files') else '')) if line \
        else 'build not in its history'
    archives = [n for n in files if n.startswith(Path(name).stem + ' - ') and n.endswith('.ba2')]
    moved = 'rebuilt' if before.get(name) != files[name] else (
        'archives changed' if any(before.get(n) != files[n] for n in archives) else '')
    return f'    {name}: {build}' + (f'  [{moved}]' if before and moved else '')


def show(run: Path, before: dict, history: dict) -> dict:
    """Print `run`: its logs and its built plugins against the run `before`; its data files."""
    files = data_files(run)
    papyrus = sorted(run.glob('Papyrus.*.log'))
    crashes = len(list(run.glob('crash-*.log')))
    print(f'{run.name}: ' + (', '.join(f'{p.name} opened {opened(p)}' for p in papyrus) or 'no Papyrus log yet')
          + (f', {crashes} crash logs' if crashes else ''))
    for name in sorted(n for n in files if n in history and n.endswith(PLUGIN_EXTS)):
        print(describe(name, files, before, history))
    return files


def archive(runs: Path) -> int:
    """Copy the logs written since the newest run's launch into its folder (as F3NV.dll's next launch would)."""
    newest = max((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.name, default=None) \
        if runs.is_dir() else None
    if newest is None:
        print('no run archived yet (is the Trace mod on and the new F3NV.dll deployed?)')
        return 2
    since, games, copied = (newest / DATA_FILES).stat().st_mtime, runs.parents[1], 0
    for folder, pattern in LOGS:
        for log in (games / folder).glob(pattern):
            if log.stat().st_mtime > since:
                shutil.copy2(log, newest / log.name)
                copied += 1
    print(f'{copied} logs copied into {newest}')
    return 0


def main() -> int:
    """List the archived runs (or archive the last one's logs first); 2 when there is no archive."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--last', type=int, default=10, help='how many of the newest runs to list')
    ap.add_argument('--archive', action='store_true', help="copy the run just played's logs into its folder first")
    ap.add_argument('--mods', type=Path, help="the MO2 mods folder (default: the app's MO2 instance)")
    args = ap.parse_args()
    runs = runs_dir()
    if runs is None or not runs.is_dir():
        print('no run archive yet: it starts with the first launch with the Trace mod on and the new F3NV.dll')
        return 2
    if args.archive and archive(runs):
        return 2
    found = mo2_setup.instance(S.load())
    mods = args.mods or (found.mods if found else None)
    history = builds(mods) if mods else {}
    folders = sorted((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.name)
    before = data_files(folders[-args.last - 1]) if len(folders) > args.last else {}
    for run in folders[-args.last:]:
        before = show(run, before, history)
    return 0


if __name__ == '__main__':
    sys.exit(main())
