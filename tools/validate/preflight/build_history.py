"""A Fallout 4 build against the build before it, and the caches its code changes invalidated.

The drift baseline moves only on --accept-build and the FormID ledger is cumulative, so neither shows a record the
latest build stopped writing. Each run keeps the build it saw (its stamp and, per record, signature, EditorID and
a CRC) and the one before; a new build is compared with the last one seen, a build seen before with the one
before it. Records gone and EditorIDs moved are review findings; added and changed records are counted.

See: docs/fork/fo4_preflight.md#previous-build
"""

import ast
import json
import subprocess
from collections import defaultdict
from pathlib import Path

from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.code_tag import ROOT, module_file, tagged_files
from core.subprocess_flags import POPEN_FLAGS
from tools.validate.preflight import build_diff
from tools.validate.preflight.findings import Finding

#: Files keeping the last build seen and the one before it (not build_last.json: the runner's key file).
LAST, PRIOR = 'build_seen.json', 'build_seen_before.json'

#: Cache calls: {function name: position of the module argument}; work_cache's and code_tag itself.
CACHE_CALLS = {'cached': 1, 'lookup': 1, 'store': 1, 'code_tag': 0}

#: The package whose caches are keyed by code tags.
PACKAGE = 'fo4_import'

_WHAT = {'removed': 'records the previous build wrote are gone', 'retyped': 'FormIDs hold another record type',
         'moved': 'EditorIDs moved to another FormID'}


def read_stamp(plugin: Path) -> dict:
    """The build stamp beside `plugin`, or {}."""
    path = stamp_path(Path(plugin))
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def _load(path: Path):
    """A kept build, or None."""
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def remember(folder: Path, build: dict):
    """The build to compare `build` ({stamp, records, contents}) with; keeps `build` as the last seen."""
    last = _load(folder / LAST)
    if last is not None and last['stamp'].get('ended') == build['stamp'].get('ended'):
        return _load(folder / PRIOR)
    if last is not None:
        (folder / LAST).replace(folder / PRIOR)
    (folder / LAST).write_text(json.dumps(build, sort_keys=True, indent=0), encoding='utf-8')
    return last


def compare(game: str, before: dict, build: dict) -> list:
    """Review findings for records gone, retyped or moved since `before`; prints added and changed counts."""
    was, now = before['records'], build['records']
    print(f'  build: against the previous build ({before["stamp"].get("ended")}): {len(was)} -> {len(now)} records')
    for what, counts in (('added', build_diff.added(was, now)),
                         ('changed', build_diff.changed(before['contents'], build['contents'], now))):
        build_diff.print_counts(what, counts, 'the previous build')
    out = []
    for kind, by_sig in build_diff.drift(was, now).items():
        for sig, rows in sorted(by_sig.items()):
            out.append(Finding('build', f'build|{game}|previous-{kind}|{sig}', 'review',
                               f'{len(rows)} {sig} {_WHAT[kind]}', build_diff.sample(rows)))
    return out


def changed_files(stamp: dict, before: 'dict | None') -> set:
    """Repo paths the build ran with changed: its stamp's uncommitted files, and the commits since `before`'s."""
    out = set(stamp.get('changed files', ()))
    old, new = (before or {}).get('commit'), stamp.get('commit')
    if old and new and old != new:
        done = subprocess.run(['git', 'diff', '--name-only', old, new], cwd=ROOT, capture_output=True, text=True,
                              **POPEN_FLAGS)
        out |= set(done.stdout.split()) | set((before or {}).get('changed files', ()))
    return out


def _module_name(path: Path) -> str:
    """The dotted module name of repo file `path`."""
    parts = path.relative_to(ROOT).with_suffix('').parts
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def imports_of(tree) -> dict:
    """{local name: module} of a file's imports: a module alias, or the module a `from` name comes from."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update({(a.asname or a.name): a.name for a in node.names})
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                full = f'{node.module}.{a.name}'
                out[a.asname or a.name] = full if module_file(full) else node.module
    return out


def resolve(arg, here: str, imports: dict) -> 'str | None':
    """The module a cache call's module argument names: a string, `__name__`, `<module>.__name__` or
    `<function>.__module__`; None for anything else."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name) and arg.id == '__name__':
        return here
    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.attr in ('__name__', '__module__'):
        return imports.get(arg.value.id)
    return None


def _named_modules(tree) -> set:
    """Repo module names a file holds as strings: what a variable can name."""
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value.startswith(PACKAGE + '.') and module_file(n.value)}


def cache_sites(package: str = PACKAGE) -> dict:
    """{module: [call site `file:line`]} of every cache keyed by a module's code tag in `package`."""
    out = defaultdict(list)
    for path in sorted((ROOT / package).rglob('*.py')):
        tree = ast.parse(path.read_bytes())
        here, imports = _module_name(path), imports_of(tree)
        for node in ast.walk(tree):
            at = CACHE_CALLS.get(getattr(node, 'func', None) and getattr(node.func, 'id', None))
            if at is None or len(node.args) <= at or path.stem == 'code_tag':
                continue
            module = resolve(node.args[at], here, imports)
            site = f'{path.relative_to(ROOT).as_posix()}:{node.lineno}'
            for name in [module] if module else sorted(_named_modules(tree)):
                out[name].append(site)
    return out


def invalidated(changed: set, sites: dict) -> dict:
    """{module: (call sites, [changed files it hashes])} of the caches `changed` (repo paths) invalidated."""
    out = {}
    for module, where in sorted(sites.items()):
        files = {p.relative_to(ROOT).as_posix() for p in tagged_files(module).values() if p.is_relative_to(ROOT)}
        hit = sorted(files & changed)
        if hit:
            out[module] = (where, hit)
    return out


def print_invalidated(stamp: dict, before: 'dict | None') -> None:
    """One line per cache the build's code changes invalidated: its module, where it is used, and the files."""
    found = invalidated(changed_files(stamp, before), cache_sites())
    print(f'  build: {len(found)} caches whose module import tree changed (an entry is remade only when a function '
          'that made it changed)')
    for module, (where, hit) in found.items():
        print(f'    {module} ({", ".join(where[:2])}): {", ".join(hit[:4])}' + (' ...' if len(hit) > 4 else ''))


def audit(game: str, folder: Path, plugin: Path, records: dict, contents: dict) -> list:
    """The previous-build findings for one Fallout 4 build (build_diff's snapshot and contents); none on the
    first build seen."""
    stamp = read_stamp(plugin)
    build = {'stamp': stamp, 'records': records, 'contents': contents}
    before = remember(Path(folder), build)
    if stamp:
        print_invalidated(stamp, before and before['stamp'])
    return compare(game, before, build) if before else []
