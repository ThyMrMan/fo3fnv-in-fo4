"""Ship changed scripts to the game without a rebuild: compiled into the F3NV - Hotfix MO2 mod, which wins over the
built mods' archives and files once it sits last in MO2's order.

    py -3.14 -m tools.release.fo4_hotfix [--plugin temp/profile_data/FalloutNV.esm] [--dry-run]

Converts the plugin's FNV scripts as its build does (its stamp names the folders), compares each with the copy its
last build compiled (the script stage), and compiles those that differ, and helper scripts that build never had,
into the hotfix mod, replacing that plugin's earlier hotfix. The next deploy of a build that started later clears
them (fo4_deploy.clear_hotfix). Only scripts: a fix that also needs records waits for a build, and a script that
gains a property a record would fill is refused (exit 2) for one.

See: docs/fork/fo4_hotfix.md#how-it-works
"""

import argparse
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from core.heavy_lock import hold_heavy_lock
from fo4_import.base.papyrus import header_dirs
from fo4_import.base.build_files import all_moved_in
from fo4_import.pipeline.build_plan import stamp_options
from fo4_import.pipeline.build_steps import STAMP_SUFFIX, convert_scripts, stamp_path
from core.build_resources import profile_cores
from fo4_import.spike.script import converted_prefix, stage_dir
from tools.release.fo4_deploy import MOD, ROOT, game_running, hotfix_mod, install_hotfix
from tools.script.compile_papyrus import compile_fallout4

#: The base game's build, the default plugin.
BASE = ROOT / 'temp' / 'profile_data' / 'FalloutNV.esm'
#: The build options a hotfix reads from the stamp's command.
OPTIONS = ('--export', '--data', '--scripts', '--plugin-dirs')
#: Value types whose property a record never fills (the converted scripts' variables).
VALUE_TYPES = frozenset({'int', 'float', 'bool', 'string', 'var'})
#: `<type> Property <name>`, then whether an `=` default follows on the line.
PROPERTY = re.compile(r'^\s*([\w:\[\]]+)\s+Property\s+(\w+)([^\n;]*)', re.IGNORECASE | re.MULTILINE)


def build_options(plugin: Path) -> dict:
    """{option: [values]} of OPTIONS in `plugin`'s build stamp command."""
    return {flag: values for flag, values in stamp_options(plugin).items() if flag in OPTIONS}


def master_script_dirs(options: dict) -> list:
    """The converted-script folders of the built masters in the build's --plugin-dirs (each from its stamp)."""
    dirs = []
    for folder in options.get('--plugin-dirs', []):
        for stamp in all_moved_in(ROOT / folder, '*.esm' + STAMP_SUFFIX):
            dirs += [ROOT / d for d in build_options(ROOT / folder / stamp.name[:-len(STAMP_SUFFIX)])['--scripts']]
    return dirs


def changed_sources(scripts_dir: Path, stage: Path, prefix: str) -> list:
    """The .psc files of `scripts_dir` differing from their copy in `stage` (the last build's compile), and the
    helpers `stage` lacks; a converted script (`prefix`) the build never compiled is attached to nothing, so not."""
    out = []
    for path in sorted(scripts_dir.glob('*.psc')):
        staged = stage / path.name
        if staged.is_file():
            if staged.read_bytes() != path.read_bytes():
                out.append(path)
        elif not path.stem.upper().startswith(prefix):
            out.append(path)
    return out


def filled_properties(text: str) -> dict:
    """{name: type} (lower) of the object properties with no default.
    See: docs/fork/fo4_hotfix.md#needs-a-build
    """
    return {name.lower(): kind.lower() for kind, name, rest in PROPERTY.findall(text)
            if kind.lower().rstrip('[]') not in VALUE_TYPES and '=' not in rest}


def needs_build(sources: list, stage: Path) -> list:
    """Why changed `sources` need a build instead: each property a record could fill, added or retyped against
    the staged copy (the built plugin fills none of them, so the script would see None)."""
    reasons = []
    for path in sources:
        staged = stage / path.name
        if not staged.is_file():
            continue
        old = filled_properties(staged.read_text(encoding='utf-8', errors='replace'))
        new = filled_properties(path.read_text(encoding='utf-8', errors='replace'))
        reasons += [f'{path.stem}: property {name} ({kind}) {"retyped" if name in old else "added"}'
                    for name, kind in sorted(new.items()) if old.get(name) != kind]
    return reasons


def compile_changed(sources: list, imports: str) -> tuple:
    """({script: compiled .pex}, {script: errors}, the scratch folder) of `sources` compiled against `imports`;
    the caller copies the .pex, then removes the folder."""
    work = Path(tempfile.mkdtemp(prefix='fo4_hotfix_'))
    src, out = work / 'src', work / 'out'
    src.mkdir()
    out.mkdir()
    for path in sources:
        shutil.copyfile(path, src / path.name)
    compiled, own, names = compile_fallout4(SimpleNamespace(src=str(src), out=str(out), full=True, workers=profile_cores(),
                                                            headers=f'{src};{imports}'))
    pex = {n: out / f'{n}.pex' for n in names if n.lower() in compiled and (out / f'{n}.pex').is_file()}
    failed = {n: own.get(n, ['no error of its own (a script it uses failed)']) for n in names if n not in pex}
    return pex, failed, work


def parse(argv) -> argparse.Namespace:
    """The command line."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--plugin', type=Path, default=BASE, help='the built plugin (default the base game build)')
    parser.add_argument('--mod', type=Path, help="the hotfix MO2 mod folder (default the plugin's game's)")
    parser.add_argument('--dry-run', action='store_true', help='convert and list the changed scripts; ship nothing')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Convert, compare, compile and install the plugin's changed scripts; 1 when one fails to compile."""
    args = parse(argv)
    if not stamp_path(args.plugin).is_file():
        sys.exit(f'{args.plugin} has no build stamp; build it once first')
    if not args.dry_run and game_running():
        sys.exit('Fallout 4 is running; close it first')
    hold_heavy_lock('tools.release.fo4_hotfix ' + str(args.plugin))
    args.mod = args.mod or hotfix_mod(MOD.parent, args.plugin)
    started, options = time.time(), build_options(args.plugin)
    scripts_dir, data_dir = ROOT / options['--scripts'][0], ROOT / options['--data'][0]
    convert_scripts(ROOT / options['--export'][0], scripts_dir)
    sources = changed_sources(scripts_dir, stage_dir(data_dir), converted_prefix(scripts_dir))
    print(f'{len(sources)} scripts differ from the last build of {args.plugin.name}:')
    print(''.join(f'  {p.stem}\n' for p in sources), end='')
    blockers = needs_build(sources, stage_dir(data_dir))
    if blockers:
        print('needs a full build, not a hotfix:\n' + ''.join(f'  {why}\n' for why in blockers), end='')
        return 2
    if args.dry_run or not sources:
        return 0
    imports = ';'.join([header_dirs(), *map(str, master_script_dirs(options)), str(stage_dir(data_dir))])
    pex, failed, work = compile_changed(sources, imports)
    for name, errors in sorted(failed.items()):
        print(f'  {name} does not compile: {"; ".join(errors)}')
    shipped = install_hotfix(args.mod, args.plugin.name, list(pex.values()), started)
    shutil.rmtree(work, ignore_errors=True)
    print(f'{shipped} scripts in {args.mod} for {args.plugin.name} ({len(failed)} failed)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
