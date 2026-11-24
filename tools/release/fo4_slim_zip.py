"""Build the slim release zip: only what the Fallout 4 app and the stages it launches need, from tracked files.

Usage: py -3.14 -m tools.release.fo4_slim_zip [--out DIR] [--version TAG] [--list | --refs]

Traces every repo module the app and each stage module import (code_tag's tracer, every edge followed, parent
packages included), adds the tracked data files beside them, minus SKIPPED, plus EXTRA_FILES and the built files
a download cannot make (generated); writes VERSION.
--list prints the files instead; --refs prints traced lines naming the gitignored references/ folder, which a
download lacks. Build a release from a clean checkout of its tag.

See: docs/fork/fo4_plan_release.md#slim-zip
"""

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from fo4_import import cleanroom
from fo4_import.base import mxmlc, release
from fo4_import.casino import movie
from fo4_import.pipeline.code_tag import ROOT, imported, module_file

#: The app, convert.py, and the modules fo4_import.app.stages runs with -m.
ENTRIES = ('fo4_app', 'convert', 'fo4_import.helpers_plugin', 'fo4_import.spike.facegen',
           'fo4_import.pipeline.build_plan', 'fo4_import.app.runtime_dll', 'fo4_import.classic_look',
           'fo4_import.pipeline.run', 'tools.validate.fo4_ref_check', 'tools.validate.fo4_check',
           'tools.validate.fo4_install_check')
#: Tracked files every zip carries beside the traced code: launchers, docs, the F4SE plugins the output ships.
EXTRA_FILES = ('Convert to Fallout 4.cmd', 'TES Auto-Convert.cmd', 'README.md', 'LICENSE', 'requirements.txt',
               'native/src/f3_zlib/zlib/LICENSE', 'tes_runtime/dist/F3NV.dll', 'tes_runtime/dist/CleanroomUI.dll',
               'tes_runtime/dist/CleanroomDialogue.dll', 'tes_runtime/dist/cleanroom_ui.txt')
#: Folders of tracked files every zip carries (minus SKIPPED): the native extensions and zlib build.
EXTRA_FOLDERS = ('native/dist/',)
#: Path prefixes the Fallout 4 path never runs or reads: Skyrim's and Morrowind's tools, DLLs and quest text tables.
SKIPPED = ('external/hkxcmd/', 'external/hkxconv/', 'external/mopp_bridge/', 'external/papyrus-compiler/',
           'external/bsarch/', 'external/openmw/', 'native/dist/spt_engine_dump.exe', 'tes_runtime/', 'game_bridge/',
           'tes5_import/generated/objective_short_text.json', 'tes5_import/generated/morrowind_quest_names')
#: A line naming references/ as a path part.
REFS = re.compile(r"""['"/\\]references['"/\\]""")
#: Every entry's timestamp, so the same files give the same zip.
STAMP = (2026, 1, 1, 0, 0, 0)


def traced(entries: tuple = ENTRIES) -> set:
    """Repo-relative paths of every module `entries` reach by import, and every package above each."""
    seen, todo = {}, list(entries)
    while todo:
        name = todo.pop()
        path = module_file(name)
        if path is None or name in seen:
            continue
        seen[name] = path
        package = name if path.name == '__init__.py' else name.rpartition('.')[0]
        todo += [*imported(path, package), *('.'.join(name.split('.')[:i]) for i in range(1, name.count('.') + 1))]
    return {p.relative_to(ROOT).as_posix() for p in seen.values()}


def tracked() -> list:
    """This checkout's tracked and new files on disk, ignored ones left out."""
    out = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT,
                         capture_output=True, check=True).stdout
    return [p for p in out.decode('utf-8').split('\0') if p and (ROOT / p).is_file()]


def code_folder(path: str, py_dirs: set) -> str:
    """The nearest folder at or above `path`'s that holds tracked .py files ('' for the root)."""
    folder = path.rpartition('/')[0]
    while folder and folder not in py_dirs:
        folder = folder.rpartition('/')[0]
    return folder


def slim_files(files: list, modules: set) -> list:
    """The zip's files: `modules`, each data file whose code_folder holds one of them, and EXTRA_FILES."""
    py_dirs = {p.rpartition('/')[0] for p in files if p.endswith('.py')}
    module_dirs = {m.rpartition('/')[0] for m in modules}
    data = {p for p in files if not p.endswith('.py') and code_folder(p, py_dirs) in module_dirs - {''}
            or p.startswith(EXTRA_FOLDERS)}
    picked = (modules | data) - {p for p in data if p.startswith(SKIPPED)}
    return sorted(picked | (set(EXTRA_FILES) & set(files)))


def generated() -> list:
    """Built files a download cannot make without a Cleanroom UI checkout or the Flex SDK, at the paths the code reads
    them: the pinned Cleanroom UI tree, its built plugin, movies and words, our casino movie. Built here if needed;
    SystemExit when one cannot be."""
    tree, built = cleanroom.source(), cleanroom.build()
    casino = mxmlc.built_movie(movie.SOURCES, movie.DOCUMENT, movie.CACHE, movie.MOVIE)
    if tree is None or built is None or casino is None or not (built / cleanroom.BUILT_PIN).is_file():
        raise SystemExit('the release needs the Cleanroom UI checkout and the Flex SDK to build its movies')
    files = [p for folder in (tree, built) for p in folder.rglob('*') if p.is_file()] + [casino]
    return sorted(p.relative_to(ROOT).as_posix() for p in files)


def write_zip(files: list, version: str, out_dir: Path) -> Path:
    """fo3fnv-in-fo4-<version>.zip in `out_dir`, its files under one folder of that name, VERSION added."""
    top = f'fo3fnv-in-fo4-{version}'
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'{top}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.writestr(zipfile.ZipInfo(f'{top}/{rel}', STAMP), (ROOT / rel).read_bytes(), zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo(f'{top}/VERSION', STAMP), version + '\n', zipfile.ZIP_DEFLATED)
    return target


def reference_lines(modules: set) -> list:
    """'file:line:text' of each line in `modules` naming references/."""
    return [f'{m}:{n}:{line.strip()}' for m in sorted(modules)
            for n, line in enumerate((ROOT / m).read_text(encoding='utf-8', errors='replace').splitlines(), 1)
            if REFS.search(line)]


def main(argv=None) -> int:
    """Write the zip, or print its files (--list) or the traced references/ lines (--refs)."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, default=ROOT / 'output' / 'release', help='Folder to write the zip in')
    ap.add_argument('--version', default=release.current(), help='Release name for VERSION and the zip')
    ap.add_argument('--list', action='store_true', help='Print the files, do not zip')
    ap.add_argument('--refs', action='store_true', help='Print traced lines naming references/')
    args = ap.parse_args(argv)
    modules = traced()
    files = slim_files(tracked(), modules)
    if args.refs or args.list:
        print('\n'.join(reference_lines(modules) if args.refs else files))
        return 0
    if release.key(args.version) is None:
        raise SystemExit(f'{args.version!r} is not a release tag the app reads (f3nv-<major>.<minor>)')
    files += generated()
    target = write_zip(files, args.version, args.out)
    size = sum((ROOT / f).stat().st_size for f in files)
    print(f'{target}: {len(files)} files ({len(modules)} modules), {size / 2**20:.1f} MB unpacked, '
          f'{target.stat().st_size / 2**20:.1f} MB zipped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
