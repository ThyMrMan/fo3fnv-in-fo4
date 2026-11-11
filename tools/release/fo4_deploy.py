"""Copy the FO4 build folder into its MO2 mod folder and list the files there that the build no longer makes.

    py -3.14 -m tools.release.fo4_deploy [--build DIR] [--mod DIR] [--plugin X.esm] [--dry-run] [--show N]
                                         [--delete-stale]

Copies each build file whose size or time differs (like robocopy /E), then lists the mod folder's stale files:
files the build folder does not have (case-insensitive paths). They are deleted only with --delete-stale, which
also removes the folders that leaves empty; MO2's meta.ini is never touched. Refuses while Fallout 4 runs, and when
the build's stamp (<plugin>.build.json) says running or failed; deleting also needs a finished stamp. With
--plugin (a DLC build in its own folder), a file under the folders its list covers (stale_files.roots) counts as
built only when <plugin>.files.txt names it, so a file an earlier build left there is neither copied nor kept.
A loose build file that an archive at the top of the build folder holds (the meshes and materials in
`<plugin> - Main.ba2`) is not copied, and the mod folder's copy is deleted on every run: loose wins over archived.
A deploy also clears the F3NV - Hotfix mod's scripts (fo4_hotfix) of each plugin whose build began after them, and
deletes the XDI-era dialogue hub plugin and links from the mods beside the mod folder.

See: docs/reference/python_tools.md#fo4-deploy
"""

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from fo4_import.base.ba2 import Archive
from fo4_import import dialogue_menu as menu_links
from fo4_import.pipeline import stale_files
from fo4_import.pipeline.build_inputs import RECORD_SUFFIX, SUFFIX
from fo4_import.pipeline.build_steps import STAMP_SUFFIX

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'temp' / 'profile_data'
MOD = Path(r'C:\Modlists\fo3fnv-in-fo4\mods\F3NV - Fallout New Vegas')
#: Mod-folder files no build makes but that belong there (lowercase, relative).
KEEP = frozenset({'meta.ini'})
#: The MO2 mod fo4_hotfix ships changed scripts into, ahead of a build; it must sit last in MO2's order.
HOTFIX_MOD = MOD.with_name('F3NV - Hotfix')
#: The hotfix mod's record of its files: {plugin: {'shipped': epoch seconds, 'files': [relative paths]}}.
HOTFIX_MANIFEST = 'F3NV_Hotfix.json'


def read_manifest(mod: Path) -> dict:
    """The hotfix mod's manifest (HOTFIX_MANIFEST); empty without one."""
    path = mod / HOTFIX_MANIFEST
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def _forget(mod: Path, manifest: dict, plugin: str) -> int:
    """Delete `plugin`'s hotfix files and its manifest entry; how many files."""
    files = manifest.pop(plugin, {}).get('files', [])
    for rel in files:
        (mod / rel).unlink(missing_ok=True)
    return len(files)


def install_hotfix(mod: Path, plugin: str, pex: list, shipped: float) -> int:
    """`plugin`'s hotfix: its earlier files deleted, compiled scripts `pex` copied into `mod`/Scripts and listed,
    dated `shipped` (when the hotfix began); how many."""
    manifest = read_manifest(mod)
    _forget(mod, manifest, plugin)
    (mod / 'Scripts').mkdir(parents=True, exist_ok=True)
    for path in pex:
        shutil.copyfile(path, mod / 'Scripts' / path.name)
    manifest[plugin] = {'shipped': shipped, 'files': sorted(f'Scripts/{p.name}' for p in pex)}
    (mod / HOTFIX_MANIFEST).write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    return len(pex)


def clear_hotfix(mod: Path, plugin: str, build_started: float) -> int:
    """Delete `plugin`'s hotfix files when its build began after the hotfix (the build holds those scripts); how
    many. A hotfix newer than the build stays, as the build lacks it.
    See: docs/fork/fo4_hotfix.md#clearing
    """
    manifest = read_manifest(mod)
    entry = manifest.get(plugin)
    if not entry or entry['shipped'] > build_started:
        return 0
    gone = _forget(mod, manifest, plugin)
    (mod / HOTFIX_MANIFEST).write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    return gone


def tree(folder: Path) -> dict:
    """{lowercase relative path: (path, size, mtime)} of every file under `folder`."""
    files = {}
    for top, _dirs, names in os.walk(folder):
        for name in names:
            path = Path(top, name)
            st = path.stat()
            files[path.relative_to(folder).as_posix().lower()] = (path, st.st_size, st.st_mtime)
    return files


def shipped(files: dict) -> dict:
    """`files` (tree()) less the build's input records, <plugin>.inputs.json and <plugin>.record/ (build_inputs)."""
    def record(key: str) -> bool:
        """Whether relative path `key` is part of a build's input record."""
        top = key.split('/', 1)[0]
        return top.endswith(RECORD_SUFFIX) and top != key or top == key and key.endswith(SUFFIX)
    return {key: entry for key, entry in files.items() if not record(key)}


def archived(build_dir: Path) -> set:
    """The lowercase '/'-separated paths the archives at the top of `build_dir` hold."""
    return {name.replace(chr(92), '/') for path in build_dir.glob('*.ba2') for name in Archive(path).entries}


def remove_shadowing(args: argparse.Namespace, mod: dict, packed: set) -> None:
    """Delete (unless --dry-run) the mod folder's loose copies of `packed` files: a loose file wins over an
    archive, so an old one would hide the archived file. They leave `mod`.
    See: docs/fork/fo4_pipeline.md#main-archive
    """
    shadowing = sorted(key for key in mod if key in packed)
    print(f'{len(shadowing)} loose files in the mod folder that the archives hold'
          f'{": would delete" if args.dry_run else ": deleting"} ({sum(mod[k][1] for k in shadowing) / 1e6:.1f} MB)')
    for key in shadowing:
        if not args.dry_run:
            mod[key][0].unlink()
        del mod[key]
    if shadowing and not args.dry_run:
        print(f'removed {remove_empty_dirs(args.mod)} empty folders')


def listed_only(build_dir: Path, build: dict, plugin: str) -> tuple:
    """(`build` less the files under DLC plugin `plugin`'s listed folders its file list does not name, how many
    were left out).
    See: docs/fork/fo4_pipeline.md#stale-files
    """
    roots = tuple(root.lower() + '/' for root in stale_files.roots(Path(plugin).stem, dlc=True))
    names = {rel.lower() for rel in stale_files.listed(build_dir / plugin)}
    kept = {key: entry for key, entry in build.items() if key in names or not key.startswith(roots)}
    return kept, len(build) - len(kept)


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
    parser.add_argument('--plugin', help="a DLC build's plugin (X.esm): deploy only the files its list names")
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
    if args.plugin and not stale_files.listed(args.build / args.plugin):
        return f'{args.plugin} has no file list ({stale_files.LIST_SUFFIX}) in {args.build}'
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
    """Check, copy what changed (loose files the build's archives hold stay behind), delete the mod folder's loose
    copies of those, then list (and with --delete-stale delete) the stale files."""
    args = parse(argv)
    why = refusal(args)
    if why:
        sys.exit(why)
    build, mod = shipped(tree(args.build)), tree(args.mod)
    if args.plugin:
        build, unlisted = listed_only(args.build, build, args.plugin)
        print(f'{unlisted} build files under its listed folders that {args.plugin}.files.txt does not name: left out')
    packed = archived(args.build)
    build = {key: entry for key, entry in build.items() if key not in packed}
    copy = plan(build, mod)[0]
    print(f'{len(build)} build files, {len(mod)} in the mod folder; {"would copy" if args.dry_run else "copying"} '
          f'{len(copy)} ({sum(build[k][1] for k in copy) / 1e6:.1f} MB)')
    if not args.dry_run:
        copy_files(args, build, mod, copy)
        clear_built_hotfixes(args)
    remove_shadowing(args, mod, packed)
    retire_hub(args)
    report_stale(args, mod, plan(build, mod)[1])
    return 0


def retire_hub(args: argparse.Namespace) -> None:
    """Delete (unless --dry-run) the XDI-era hub files (dialogue_menu.LEGACY) in the MO2 mods beside --mod:
    each build now writes its own plugin's links.
    See: docs/fork/fo4_dialogue_menu_plan.md#converter
    """
    found = [mod / rel for mod in sorted(args.mod.parent.iterdir()) if mod.is_dir()
             for rel in menu_links.LEGACY if (mod / rel).is_file()]
    for path in found:
        print(f'XDI-era hub file {path}: {"would delete" if args.dry_run else "deleting"}')
        if not args.dry_run:
            path.unlink()


def clear_built_hotfixes(args: argparse.Namespace) -> None:
    """After a deploy, clear_hotfix (the hotfix mod beside --mod) for each deployed plugin: --plugin, else every
    stamped plugin of the build."""
    stamps = [args.build / (args.plugin + STAMP_SUFFIX)] if args.plugin else sorted(args.build.glob('*' + STAMP_SUFFIX))
    for stamp in stamps:
        plugin = stamp.name[:-len(STAMP_SUFFIX)]
        started = time.mktime(time.strptime(json.loads(stamp.read_text(encoding='utf-8'))['started'],
                                            '%Y-%m-%d %H:%M:%S'))
        gone = clear_hotfix(args.mod.with_name(HOTFIX_MOD.name), plugin, started)
        if gone:
            print(f'{gone} hotfix scripts of {plugin} cleared from {HOTFIX_MOD.name}: the build holds them')


if __name__ == '__main__':
    sys.exit(main())
