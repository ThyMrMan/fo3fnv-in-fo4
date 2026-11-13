"""Which plugins need a build: each built plugin's record (build_inputs) checked against the code, files and its
masters' builds as they are now.

    py -3.14 -m fo4_import.pipeline.build_plan temp/profile_data/FalloutNV.esm temp/profile_data_dm/DeadMoney.esm
    py -3.14 -m fo4_import.pipeline.build_plan --run <plugins...>      # build what needs it, masters first
    py -3.14 -m fo4_import.pipeline.build_plan --verify <plugin>       # rebuild a current plugin; same bytes?

A plugin is current, needs a build (with the first changed input), or waits for a master that does.

See: docs/fork/fo4_plugin_layout.md#build-plan
"""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.ledger import ID, Ledger, ledger_path
from fo4_import.pipeline import creation_kit, mod_dirs
from fo4_import.pipeline.build_inputs import inputs_path, listing, stamp
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.code_identity import changed, rebase
from fo4_import.pipeline.code_tag import ROOT
from tes5_import.base.tes5_reader import walk

CURRENT, BUILD, AFTER = 'current', 'build', 'after'
#: fo4_import.pipeline.run's flags that take one path.
PATH_FLAGS = frozenset({'--export', '--out', '--data', '--scripts', '--mod-sources', '--replacements'})


def record(plugin: Path) -> 'dict | None':
    """`plugin`'s inputs record; None without one, or when its stamp is not a finished build."""
    path, stamp_file = inputs_path(plugin), stamp_path(plugin)
    if not path.is_file() or not stamp_file.is_file() or not plugin.is_file():
        return None
    if json.loads(stamp_file.read_text(encoding='utf-8')).get('status') != 'finished':
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def same_file(path: str, kept: list) -> bool:
    """Whether file `path` still matches its kept [size, mtime_ns, SHA-1 or None]."""
    now = stamp(Path(path))
    if now is None or now[0] != kept[0]:
        return False
    return now[1] == kept[1] or (kept[2] is not None and now[2] == kept[2])


def _files(rec: dict) -> 'str | None':
    """The first input file, folder, program or native extension no longer as the build saw it."""
    for path, kept in rec['files'].items():
        if not same_file(path, kept):
            return f'file {path}'
    for path, kept in rec['dirs'].items():
        if listing(Path(path)) != kept:
            return f'folder {path}'
    for path, kept in {**rec['programs'], **rec.get('natives', {})}.items():
        found = path if Path(path).is_absolute() else shutil.which(path)
        if kept is None or found is None or not same_file(found, kept):
            return f'program {path}'
    return None


def _asked(rec: dict) -> 'str | None':
    """The first question the build asked about its mods (build_inputs.asked) that now has another answer."""
    for kind, arg, answer in rec.get('asked', []):
        if (mod_dirs.ask(arg) if kind == mod_dirs.FOUND else creation_kit.ask(kind, arg)) != answer:
            return f'{kind} {arg}'.rstrip()
    return None


def _environment(rec: dict) -> 'str | None':
    """The Python or third-party package that changed since the build, if one."""
    env = rec['environment']
    if env['python'] != sys.version:
        return 'Python'
    for dist, version in env['packages'].items():
        try:
            if importlib.metadata.version(dist) != version:
                return f'package {dist}'
        except importlib.metadata.PackageNotFoundError:
            return f'package {dist}'
    return None


def _records(paths: list, wanted: dict) -> dict:
    """{FormID: [signature, SHA-1 of the body]} of `wanted` ({FormID: signature}) in plugins `paths`, the last
    one holding each (as master_overrides.master_records reads)."""
    out = {}
    sigs = frozenset(s.encode('latin-1') for s in wanted.values())
    for path in paths:
        for rec, _ in walk(Path(path).read_bytes(), bodies=sigs):
            if wanted.get(rec.form_id) == rec.sig.decode('latin-1'):
                out[rec.form_id] = [rec.sig.decode('latin-1'), hashlib.sha1(rec.body).hexdigest()]
    return out


def _held(paths: list) -> frozenset:
    """Every FormID in built plugins `paths`."""
    return frozenset(rec.form_id for path in paths for rec, _ in walk(Path(path).read_bytes(), bodies=()))


def _ledgers(log: dict, held: frozenset) -> 'str | None':
    """The first master ledger lookup that now answers differently."""
    ledgers = {int(k.split(':')[1]): Ledger(Path(v[0])) for k, v in log['paths'].items() if k.startswith('ledger:')}
    for site, key, answer in log['ledgers']:
        now = None
        for index, ledger in sorted(ledgers.items()):
            oid = ledger.sites.get((ID, site), {}).get(key)
            if oid is not None and index << 24 | oid in held:
                now = index << 24 | oid
                break
        if now != answer:
            return f'master ledger {site} {key}'
    return None


def _masters(log: dict) -> 'str | None':
    """The first master question that now has another answer (build_inputs.MasterLog)."""
    plugins = log['paths'].get('plugin', [])
    for path, masters in log['headers'].items():
        if not Path(path).is_file() or file_masters(Path(path)) != masters:
            return f'master header {path}'
    held = _held(plugins) if plugins else frozenset()
    moved = next((fid for fid, answer in log['held'].items() if (int(fid, 16) in held) != answer), None)
    if moved:
        return f'master holds {moved}'
    wanted = {int(fid, 16): sig for fid, (sig, _) in log['records'].items()}
    now = _records(plugins, wanted) if wanted else {}
    moved = next((fid for fid, kept in log['records'].items() if now.get(int(fid, 16), [kept[0], None]) != kept), None)
    if moved:
        return f'master record {moved}'
    return _ledgers(log, held) or _staged(log) or _scripts(log)


def _staged(log: dict) -> 'str | None':
    """The first texture whose masters' packed signatures differ now."""
    manifests = [json.loads(Path(p).read_text(encoding='utf-8')) if Path(p).is_file() else {}
                 for p in log['paths'].get('manifest', [])]
    for key, kept in log['staged'].items():
        if [(m.get(key) or [None] * 3)[2] for m in manifests] != kept:
            return f'master texture {key}'
    return None


def _scripts(log: dict) -> 'str | None':
    """The first master script compiled against that changed."""
    for path, digest in log['scripts'].items():
        now = Path(path)
        if not now.is_file() or hashlib.sha1(now.read_bytes()).hexdigest() != digest:
            return f'master script {path}'
    return None


def check(plugin: Path) -> tuple:
    """(CURRENT or BUILD, the first changed input or '') of built `plugin`, its masters taken as they are now."""
    rec = record(plugin)
    if rec is None:
        return BUILD, 'no finished build with an inputs record'
    key = changed(rec['code'])
    if key:
        return BUILD, f'code {key}'
    reason = _environment(rec) or _files(rec) or _asked(rec) or _masters(rec['masters'])
    return (BUILD, reason) if reason else (CURRENT, '')


def masters_of(plugin: Path) -> list:
    """The built master plugins `plugin`'s last build read (none without a record)."""
    rec = record(plugin)
    return [Path(p) for p in rec['masters']['paths'].get('plugin', [])] if rec else []


def ordered(plugins: list) -> list:
    """`plugins` with every one after the masters among them its last build read."""
    left, out = [Path(p) for p in plugins], []
    while left:
        names = {p.resolve() for p in left}
        ready = [p for p in left if not names & {m.resolve() for m in masters_of(p)}] or left[:1]
        out += ready
        left = [p for p in left if p not in ready]
    return out


def plan(plugins: list) -> list:
    """[(plugin, verdict, reason)] for `plugins`, masters first; a plugin whose master needs a build waits (AFTER).
    Code is read as it is now on disk, each call afresh.
    See: docs/fork/fo4_plugin_layout.md#build-plan
    """
    rebase()
    out, building = [], set()
    for plugin in ordered(plugins):
        waiting = [m for m in masters_of(plugin) if m.resolve() in building]
        verdict = (AFTER, waiting[0].name) if waiting else check(plugin)
        if verdict[0] != CURRENT:
            building.add(plugin.resolve())
        out.append((plugin, *verdict))
    return out


def _exists(path: str) -> bool:
    """Whether `path` (relative to the repo, or absolute) names a file or folder."""
    return (Path(path) if Path(path).is_absolute() else ROOT / path).exists()


def stamp_argv(command: str) -> list:
    """The arguments of a stamp's space-joined `command`; a PATH_FLAGS value that held spaces is rejoined (the
    longest run of words before the next flag that names an existing path, else one word)."""
    words, out, i = command.split()[1:], [], 0
    while i < len(words):
        out.append(words[i])
        i += 1
        if out[-1] in PATH_FLAGS and i < len(words):
            stop = next((j for j in range(i, len(words)) if words[j].startswith('--')), len(words))
            end = next((e for e in range(stop, i, -1) if _exists(' '.join(words[i:e]))), i + 1)
            out.append(' '.join(words[i:end]))
            i = end
    return out


def retarget(argv: list, plugin: Path, dirs: list) -> list:
    """`argv` building `plugin` in its own folder: --out `plugin`, --data its folder, --plugin-dirs `dirs` (a
    command recorded for a scratch build would otherwise write the scratch copy again, against scratch masters)."""
    rest, i = [], 0
    while i < len(argv):
        word = argv[i]
        i += 1
        if word in ('--out', '--data'):
            i += 1
        elif word == '--plugin-dirs':
            while i < len(argv) and not argv[i].startswith('--'):
                i += 1
        else:
            rest.append(word)
    return ['--out', str(plugin), '--data', str(plugin.parent), *(['--plugin-dirs', *map(str, dirs)] if dirs else []),
            *rest]


def build_argv(plugin: Path, dirs: list) -> list:
    """`plugin`'s last build arguments (its inputs record, else its stamp), retargeted to its own folder."""
    rec = json.loads(inputs_path(plugin).read_text(encoding='utf-8')) if inputs_path(plugin).is_file() else None
    if rec is None:
        kept = json.loads(stamp_path(plugin).read_text(encoding='utf-8'))
        argv = kept.get('argv') or stamp_argv(kept['command'])
    else:
        argv = rec['argv']
    return retarget(argv, plugin, dirs)


def master_dirs(plugin: Path, plugins: list) -> list:
    """The folders of the `plugins` that `plugin`'s header names as masters."""
    names = {m.lower() for m in file_masters(plugin)}
    return sorted({Path(p).parent for p in plugins if Path(p).name.lower() in names})


def rebuild(plugin: Path, dirs: list = ()) -> int:
    """Build `plugin` again in its own folder, masters from `dirs`; the exit code."""
    print(f'== building {plugin.name}', flush=True)
    return subprocess.call([sys.executable, '-m', 'fo4_import.pipeline.run', *build_argv(plugin, dirs)], cwd=ROOT)


def run(plugins: list) -> int:
    """Build every plugin of `plugins` that needs it, masters first, checking the rest again after each; the first
    failing build's exit code, 3 when a plugin still needs a build after its own, else 0."""
    built = set()
    while True:
        todo = [(p, reason) for p, verdict, reason in plan(plugins) if verdict == BUILD]
        if not todo:
            return 0
        plugin, reason = todo[0]
        if plugin.resolve() in built:
            print(f'{plugin.name} still needs a build after building it ({reason}); stopped', flush=True)
            return 3
        print(f'{plugin.name}: {reason}', flush=True)
        code = rebuild(plugin, master_dirs(plugin, plugins))
        if code:
            return code
        built.add(plugin.resolve())


def verify(plugin: Path) -> int:
    """Rebuild current `plugin` and compare its bytes and ledger with the build it replaces; 0 when the same."""
    verdict, reason = check(plugin)
    if verdict != CURRENT:
        print(f'{plugin.name} is not current ({reason}); nothing to verify')
        return 1
    ledger = ledger_path(plugin)
    before = (plugin.read_bytes(), ledger.read_bytes() if ledger.is_file() else b'')
    code = rebuild(plugin)
    after = (plugin.read_bytes(), ledger.read_bytes() if ledger.is_file() else b'')
    same = code == 0 and before == after
    print(f'{plugin.name}: {"same bytes" if same else "DIFFERENT: the record missed an input"}')
    return 0 if same else 2


def main():
    """Print the plan, or build what needs it (--run), or verify a current plugin (--verify)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugins', nargs='+', type=Path, help='Built plugins (each beside its stamp and inputs record)')
    ap.add_argument('--run', action='store_true', help='Build every plugin that needs it, masters first')
    ap.add_argument('--verify', action='store_true', help='Rebuild the (current) plugin and compare its bytes')
    args = ap.parse_args()
    if args.verify:
        sys.exit(verify(args.plugins[0]))
    if args.run:
        sys.exit(run(args.plugins))
    for plugin, verdict, reason in plan(args.plugins):
        print(f'{plugin.name}: {verdict}{f" ({reason})" if reason else ""}')


if __name__ == '__main__':
    main()
