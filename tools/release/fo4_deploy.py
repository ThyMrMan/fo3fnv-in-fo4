"""Copy the FO4 build folder into its MO2 mod folder and list the files there that the build no longer makes.

    py -3.14 -m tools.release.fo4_deploy [--build DIR] [--mod DIR] [--dry-run] [--show N] [--delete-stale]

Copies each build file whose size or time differs (like robocopy /E), then lists the mod folder's stale files:
files the build folder does not have (case-insensitive paths). They are deleted only with --delete-stale, which
also removes the folders that leaves empty; MO2's meta.ini is never touched. Refuses while Fallout 4 runs, and when
the build's stamp (<plugin>.build.json) says running or failed; deleting also needs a finished stamp.

See: docs/reference/python_tools.md#fo4-deploy
"""

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fo4_import.pipeline.build_steps import STAMP_SUFFIX

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'temp' / 'profile_data'
MOD = Path(r'C:\Modlists\fo3fnv-in-fo4\mods\F3NV - Fallout New Vegas')
#: Mod-folder files no build makes but that belong there (lowercase, relative).
KEEP = frozenset({'meta.ini'})


def tree(folder: Path) -> dict:
    """{lowercase relative path: (path, size, mtime)} of every file under `folder`."""
    files = {}
    for top, _dirs, names in os.walk(folder):
        for name in names:
            path = Path(top, name)
            st = path.stat()
            files[path.relative_to(folder).as_posix().lower()] = (path, st.st_size, st.st_mtime)
    return files


def plan(build: dict, mod: dict) -> tuple:
    """(build files to copy, mod files to delete): copies are new or differ in size or time (2 s slack, FAT/robocopy
    rounding); stale ones are mod files the build does not have, except KEEP."""
    copy = [key for key, (_p, size, mtime) in build.items()
            if key not in mod or mod[key][1] != size or abs(mod[key][2] - mtime) > 2]
    stale = [key for key in mod if key not in build and key not in KEEP]
    return sorted(copy), sorted(stale)


def stamp_status(build_dir: Path) -> 'str | None':
    """The build stamp's status (running, finished, failed), or None when the build folder has no stamp."""
    stamps = sorted(build_dir.glob('*' + STAMP_SUFFIX))
    statuses = {json.loads(p.read_text(encoding='utf-8')).get('status') for p in stamps}
    if not statuses:
        return None
    return 'finished' if statuses == {'finished'} else ('running' if 'running' in statuses else 'failed')


def game_running() -> bool:
    """Whether Fallout4.exe runs (it holds the BA2s open); False off Windows."""
    if sys.platform != 'win32':
        return False
    tasks = subprocess.run(['tasklist'], capture_output=True, text=True).stdout.lower()
    return 'fallout4.exe' in tasks


def summary(keys: list, files: dict) -> list:
    """Lines grouping `keys` by top folder and extension, biggest first."""
    groups = collections.defaultdict(lambda: [0, 0])
    for key in keys:
        top = key.split('/', 1)[0] if '/' in key else '.'
        group = groups[f'{top} *.{key.rsplit(".", 1)[-1]}' if '.' in key else top]
        group[0] += 1
        group[1] += files[key][1]
    return [f'  {n:6} files {size / 1e6:9.1f} MB  {name}'
            for name, (n, size) in sorted(groups.items(), key=lambda kv: -kv[1][1])]


def remove_empty_dirs(folder: Path) -> int:
    """Remove the empty folders under `folder` (not `folder` itself), deepest first; how many."""
    removed = 0
    for top, _dirs, _names in sorted(os.walk(folder), key=lambda t: -len(t[0])):
        path = Path(top)
        if path != folder and not any(path.iterdir()):
            path.rmdir()
            removed += 1
    return removed


def parse(argv) -> argparse.Namespace:
    """The command line."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, default=BUILD, help='the build folder (default temp/profile_data)')
    parser.add_argument('--mod', type=Path, default=MOD, help="the MO2 mod folder (default the F3NV mod's)")
    parser.add_argument('--dry-run', action='store_true', help='copy and delete nothing; say what would change')
    parser.add_argument('--show', type=int, default=20, help='stale paths to print (default 20; 0 for none)')
    parser.add_argument('--delete-stale', action='store_true',
                        help="delete the mod folder's stale files (needs a finished build stamp)")
    return parser.parse_args(argv)


def refusal(args: argparse.Namespace) -> str:
    """Why this run must not go ahead, or '' (missing folders, an unfinished build, the game running)."""
    if not args.build.is_dir() or not args.mod.is_dir():
        return f'missing folder: {args.build if not args.build.is_dir() else args.mod}'
    status = stamp_status(args.build)
    if status in ('running', 'failed'):
        return f'the build stamp in {args.build} says {status}; deploy a finished build'
    if status is None:
        print(f'warning: no {STAMP_SUFFIX} in {args.build}; cannot tell whether that build finished')
    if args.delete_stale and status != 'finished':
        return '--delete-stale needs a finished build stamp, so a partial build cannot empty the mod folder'
    if not args.dry_run and game_running():
        return 'Fallout 4 is running; close it first'
    return ''


def copy_files(args: argparse.Namespace, build: dict, mod: dict, keys: list) -> None:
    """Copy the build files `keys` over the mod folder's (keeping the mod folder's spelling of an existing path)."""
    for key in keys:
        source = build[key][0]
        target = mod[key][0] if key in mod else args.mod / source.relative_to(args.build)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def report_stale(args: argparse.Namespace, mod: dict, stale: list) -> None:
    """List the stale files grouped and the first --show of them; delete them with --delete-stale."""
    print(f'{len(stale)} stale files in the mod folder (no longer built), '
          f'{sum(mod[k][1] for k in stale) / 1e6:.1f} MB:')
    print('\n'.join(summary(stale, mod)))
    for key in stale[:args.show]:
        print(f'    {mod[key][0].relative_to(args.mod)}')
    if len(stale) > args.show > 0:
        print(f'    ... {len(stale) - args.show} more (--show N)')
    if stale and args.delete_stale and not args.dry_run:
        for key in stale:
            mod[key][0].unlink()
        print(f'deleted {len(stale)} stale files and {remove_empty_dirs(args.mod)} empty folders')
    elif stale:
        print('kept them; --delete-stale deletes them')


def main(argv=None) -> int:
    """Check, copy what changed, then list (and with --delete-stale delete) the stale files."""
    args = parse(argv)
    why = refusal(args)
    if why:
        sys.exit(why)
    build, mod = tree(args.build), tree(args.mod)
    copy, stale = plan(build, mod)
    print(f'{len(build)} build files, {len(mod)} in the mod folder; {"would copy" if args.dry_run else "copying"} '
          f'{len(copy)} ({sum(build[k][1] for k in copy) / 1e6:.1f} MB)')
    if not args.dry_run:
        copy_files(args, build, mod, copy)
    report_stale(args, mod, stale)
    return 0


if __name__ == '__main__':
    sys.exit(main())
