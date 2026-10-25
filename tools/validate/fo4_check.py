"""FO4Edit's "Check for errors" on a built Fallout 4 plugin, headless: unresolved and wrong-type references, bad
sizes and values, as xEdit's record definitions see them.

    py -3.14 -m tools.validate.fo4_check <plugin.esp> [--plugin-dirs DIR ...] [--work DIR]

The plugin and its masters are hard-linked into a work folder (Fallout4.esm from the game, the others from the
plugin's folder or --plugin-dirs), FO4Edit loads them with fo4edit_check.pas, and the errors print grouped by
message. Exit 1 when there are errors.
"""

import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR
from tes5_import.base.tes5_reader import subrecords

ROOT = Path(__file__).resolve().parents[2]
FO4EDIT = ROOT / 'references' / 'FO4Edit 4.1.5f' / 'FO4Edit.exe'
SCRIPT = Path(__file__).with_name('fo4edit_check.pas')
#: Seconds FO4Edit may take to load and check, unless --timeout says otherwise.
TIMEOUT = 1200


def masters(plugin: Path) -> list:
    """The master file names in `plugin`'s header."""
    raw = plugin.read_bytes()
    size = int.from_bytes(raw[4:8], 'little')
    return [d.rstrip(b'\0').decode('cp1252') for t, d in subrecords(raw[24:24 + size]) if t == b'MAST']


def find(name: str, dirs: list) -> Path:
    """The first file `name` in `dirs`."""
    for folder in dirs:
        if (Path(folder) / name).is_file():
            return Path(folder) / name
    raise FileNotFoundError(f'{name} not found in {[str(d) for d in dirs]}')


def stage(plugin: Path, dirs: list, work: Path) -> None:
    """Hard-link `plugin` and its masters into `work` with plugins.txt and the script's target file."""
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    names = masters(plugin)
    for name in names + [plugin.name]:
        source = plugin if name == plugin.name else find(name, [FALLOUT4_DIR / 'Data', plugin.parent, *dirs])
        os.link(source, work / name)
    (work / 'plugins.txt').write_text(''.join(f'*{n}\n' for n in names[1:] + [plugin.name]), encoding='utf-8')
    (work / 'fo4_check_target.txt').write_text(plugin.name, encoding='utf-8')
    shutil.copyfile(SCRIPT, work / SCRIPT.name)


def run(work: Path, timeout: int = TIMEOUT) -> list:
    """Run FO4Edit over `work` until the script writes its result (FO4Edit stays open in script mode, so it is
    closed then); the result file's lines."""
    cmd = [str(FO4EDIT), f'-D:{work}\\', f'-P:{work / "plugins.txt"}', f'-script:{work / SCRIPT.name}',
           '-autoload', '-autoexit', '-nobuildrefs', '-IKnowWhatImDoing']
    result = work / 'fo4_check_result.txt'
    proc = subprocess.Popen(cmd, **POPEN_FLAGS)
    started = time.time()
    while not result.exists() and proc.poll() is None and time.time() - started < timeout:
        time.sleep(2)
    time.sleep(2)
    proc.kill()
    if not result.exists():
        raise RuntimeError(f'FO4Edit wrote no result ({result})')
    return result.read_text(encoding='utf-8', errors='replace').splitlines()


def summary(lines: list) -> dict:
    """{error message with numbers and FormIDs masked: [lines]}."""
    groups = collections.defaultdict(list)
    for line in lines:
        if not line.startswith('#'):
            message = line.split(' -> ', 1)[-1]
            groups[re.sub(r'\[[0-9A-F]{8}\]|[0-9A-F]{8}|\d+', '#', message)].append(line)
    return groups


def main() -> int:
    """Check the plugin; print the errors grouped; 1 when there are any."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--plugin-dirs', nargs='*', default=(), help='Folders holding masters other than Fallout4.esm')
    ap.add_argument('--work', type=Path, default=ROOT / 'temp' / 'fo4_check', help='Folder to stage the load in')
    ap.add_argument('--show', type=int, default=5, help='Examples per error kind')
    ap.add_argument('--timeout', type=int, default=TIMEOUT, help='Seconds FO4Edit may take')
    args = ap.parse_args()
    stage(args.plugin.resolve(), args.plugin_dirs, args.work.resolve())
    lines = run(args.work.resolve(), args.timeout)
    groups = summary(lines)
    print('\n'.join(line for line in lines if line.startswith('#')))
    for message, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f'{len(items):6d}  {message}')
        for item in items[:args.show]:
            print(f'        {item}')
    print(f'{sum(map(len, groups.values()))} errors in {len(groups)} kinds')
    return 1 if groups else 0


if __name__ == '__main__':
    sys.exit(main())
