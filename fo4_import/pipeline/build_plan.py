"""Which plugins need a build: each built plugin's record (build_inputs) checked against the code, files and its
masters' builds as they are now.

    py -3.14 -m fo4_import.pipeline.build_plan temp/profile_data/FalloutNV.esm temp/profile_data_dm/DeadMoney.esm
    py -3.14 -m fo4_import.pipeline.build_plan --run <plugins...>      # build what needs it, masters first
    py -3.14 -m fo4_import.pipeline.build_plan --verify <plugin>       # rebuild a current plugin; same bytes?

A plugin is current, needs a build (with the first changed input), or waits for a master that does. --run also
runs a plugin's faces stage again after its rebuild (spike/facegen.faces_stale), stops when a build flips a plugin
that does not depend on it (a hidden input), and refuses a plugin whose master is a scratch copy under temp/. Each
plugin is rebuilt by the module its stamp names (pipeline.run, or pipeline.overlay for an asset overlay).

See: docs/fork/fo4_plugin_layout.md#build-plan
"""

import argparse
import functools
import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.ledger import ID, Ledger, ledger_path
from fo4_import.base.master_overrides import read_built
from fo4_import.pipeline import creation_kit, mod_dirs
from fo4_import.pipeline.build_inputs import inputs_path, listing, stamp
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.code_identity import changed, rebase
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.stage_timer import clocked
from tes5_import.base.tes5_reader import walk

CURRENT, BUILD, AFTER = 'current', 'build', 'after'
#: run()'s own exit codes (its docstring): rebuilt plugin still BUILD, hidden input leaked, scratch master.
STILL_BUILD, LEAKED, SCRATCH_MASTER = 3, 4, 5
#: Folders holding scratch builds: a plugin outside them must not read a master inside them.
SCRATCH = (ROOT / 'temp',)
#: The build modules a stamp's command can name, each replayed with its own retarget (build_command).
RUN, OVERLAY = 'fo4_import.pipeline.run', 'fo4_import.pipeline.overlay'
#: run's and overlay's flags that take one path.
PATH_FLAGS = frozenset({'--export', '--out', '--data', '--scripts', '--mod-sources', '--replacements',
                        '--export-root'})
#: Flags that take several paths (overlay's --built and --mods, run's --plugin-dirs).
MULTI_PATH_FLAGS = frozenset({'--built', '--mods', '--plugin-dirs'})
#: Flags whose one value is text that may hold spaces (overlay's --name).
TEXT_FLAGS = frozenset({'--name'})


def record(plugin: Path) -> 'dict | None':
    """`plugin`'s inputs record; None without one, or when its stamp is not a finished build."""
    path, stamp_file = inputs_path(plugin), stamp_path(plugin)
    if not path.is_file() or not stamp_file.is_file() or not plugin.is_file():
        return None
    return _record(path, stamp_file, path.stat().st_mtime_ns, stamp_file.stat().st_mtime_ns)


@functools.lru_cache(maxsize=256)
def _record(path: Path, stamp_file: Path, *_mtimes) -> 'dict | None':
    """record() of `path`, read once per pair of file mtimes (`_mtimes`)."""
    if json.loads(stamp_file.read_text(encoding='utf-8')).get('status') != 'finished':
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def same_file(path: str, kept: list) -> bool:
    """Whether file `path` still matches its kept [size, mtime_ns, SHA-1 or None]: the same size, and the same
    mtime or (hashed only then) the same bytes."""
    now = file_stat(path)
    if now is None or now.st_size != kept[0] or not stat.S_ISREG(now.st_mode):
        return False
    return now.st_mtime_ns == kept[1] or (kept[2] is not None and (stamp(Path(path)) or [None] * 3)[2] == kept[2])


@functools.cache
def file_stat(path: str) -> 'os.stat_result | None':
    """os.stat of `path` (None when absent), taken once per plan() (which clears it)."""
    try:
        return os.stat(path)
    except OSError:
        return None


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


@functools.cache
def built_walk(path: str, masters: tuple, sigs: frozenset) -> dict:
    """{FormID: (signature, body SHA-1 for `sigs`)} of `path` read for `masters`.
    See: docs/fork/fo4_plugin_layout.md#plan-memos
    """
    return {rec.form_id: (rec.sig.decode('latin-1'), hashlib.sha1(rec.body).hexdigest() if rec.sig in sigs else None)
            for rec, _ in walk(read_built(path, list(masters)), bodies=sigs)}


def _records(paths: list, wanted: dict, masters: list) -> dict:
    """{FormID: [signature, SHA-1 of the body]} of `wanted` ({FormID: signature}) in plugins `paths`, the last
    one holding each, numbered as a build mastering `masters` reads them (as master_overrides.master_records)."""
    out, sigs = {}, _sigs(wanted)
    for path in paths:
        found = built_walk(str(path), tuple(masters), sigs)
        out.update({fid: list(found[fid]) for fid, sig in wanted.items() if found.get(fid, ('',))[0] == sig})
    return out


def _sigs(wanted: dict) -> frozenset:
    """The signatures (bytes) of `wanted` ({FormID: signature})."""
    return frozenset(s.encode('latin-1') for s in wanted.values())


@functools.cache
def held(paths: tuple, masters: tuple, sigs: frozenset) -> frozenset:
    """Every FormID in plugins `paths` read for `masters` (built_walk)."""
    return frozenset(fid for path in paths for fid in built_walk(path, masters, sigs))


@functools.cache
def read_ledger(path: str) -> Ledger:
    """The ledger at `path`, read once per plan()."""
    return Ledger(Path(path))


def _ledgers(log: dict, held: frozenset) -> 'str | None':
    """The first master ledger lookup that now answers differently."""
    ledgers = {int(k.split(':')[1]): read_ledger(v[0]) for k, v in log['paths'].items() if k.startswith('ledger:')}
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


def _masters(log: dict, plugin: Path) -> 'str | None':
    """The first master question that now has another answer (build_inputs.MasterLog), master FormIDs read in
    the numbering of `plugin`'s own masters."""
    plugins = log['paths'].get('plugin', [])
    for path, masters in log['headers'].items():
        if not Path(path).is_file() or file_masters(Path(path)) != masters:
            return f'master header {path}'
    own = file_masters(plugin) if plugins else []
    wanted = {int(fid, 16): sig for fid, (sig, _) in log['records'].items()}
    asked = plugins and (log['held'] or log['ledgers'])
    found = held(tuple(map(str, plugins)), tuple(own), _sigs(wanted)) if asked else frozenset()
    moved = next((fid for fid, answer in log['held'].items() if (int(fid, 16) in found) != answer), None)
    if moved:
        return f'master holds {moved}'
    now = _records(plugins, wanted, own) if wanted else {}
    moved = next((fid for fid, kept in log['records'].items() if now.get(int(fid, 16), [kept[0], None]) != kept), None)
    if moved:
        return f'master record {moved}'
    return _ledgers(log, found) or _staged(log) or _scripts(log)


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
    """verdict() of `plugin` with the disk read afresh (fresh_reads)."""
    fresh_reads()
    return verdict(plugin)


def fresh_reads() -> None:
    """Forget the files, masters and ledgers read so far (each read once until the next call).
    See: docs/fork/fo4_plugin_layout.md#plan-memos
    """
    for memo in (file_stat, built_walk, held, read_ledger):
        memo.cache_clear()


def verdict(plugin: Path) -> tuple:
    """(CURRENT or BUILD, the first changed input or '') of built `plugin`, its masters taken as they are now."""
    rec = record(plugin)
    if rec is None:
        return BUILD, 'no finished build with an inputs record'
    key = changed(rec['code'])
    if key:
        return BUILD, f'code {key}'
    reason = _environment(rec) or _files(rec) or _asked(rec) or _masters(rec['masters'], plugin)
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
    fresh_reads()
    out, building = [], set()
    for plugin in ordered(plugins):
        waiting = [m for m in masters_of(plugin) if m.resolve() in building]
        found = (AFTER, waiting[0].name) if waiting else verdict(plugin)
        if found[0] != CURRENT:
            building.add(plugin.resolve())
        out.append((plugin, *found))
    return out


def _exists(path: str) -> bool:
    """Whether `path` (relative to the repo, or absolute) names a file or folder."""
    return (Path(path) if Path(path).is_absolute() else ROOT / path).exists()


def _longest(words: list, i: int, stop: int) -> int:
    """End of the longest words[i:end<=stop] naming a path, else i + 1."""
    return next((e for e in range(stop, i, -1) if _exists(' '.join(words[i:e]))), i + 1)


def stamp_argv(command: str) -> list:
    """The arguments of a stamp's space-joined `command`, values that held spaces rejoined: a PATH_FLAGS value is
    the longest run of words before the next flag naming an existing path (else one word), a MULTI_PATH_FLAGS
    value that again until the next flag, a TEXT_FLAGS value every word up to it.
    See: docs/fork/fo4_plugin_layout.md#replay
    """
    words, out, i = command.split()[1:], [], 0
    while i < len(words):
        flag = words[i]
        out.append(flag)
        i += 1
        stop = next((j for j in range(i, len(words)) if words[j].startswith('--')), len(words))
        if flag in TEXT_FLAGS and i < stop:
            out.append(' '.join(words[i:stop]))
            i = stop
        elif flag in PATH_FLAGS and i < len(words):
            end = _longest(words, i, stop)
            out.append(' '.join(words[i:end]))
            i = end
        elif flag in MULTI_PATH_FLAGS:
            out += _paths(words[i:stop])
            i = stop
    return out


def _paths(words: list) -> list:
    """`words` split into the longest runs naming existing paths (_longest)."""
    out, i = [], 0
    while i < len(words):
        end = _longest(words, i, len(words))
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


def retarget_overlay(argv: list, plugin: Path, masters: list) -> list:
    """Overlay `argv` writing `plugin` in its own folder (--out, --name its stem) over built `masters` (--built;
    the recorded ones kept when `masters` is empty)."""
    rest, i = [], 0
    while i < len(argv):
        word = argv[i]
        i += 1
        if word in ('--out', '--name'):
            i += 1
        elif word == '--built' and masters:
            while i < len(argv) and not argv[i].startswith('--'):
                i += 1
        else:
            rest.append(word)
    return ['--out', str(plugin.parent), '--name', plugin.stem, *(['--built', *map(str, masters)] if masters else []),
            *rest]


def header_masters(plugin: Path, dirs: list) -> list:
    """`plugin`'s masters, each in the first of `dirs`; [] if any is missing."""
    found = [next((Path(d) / name for d in dirs if (Path(d) / name).is_file()), None) for name in file_masters(plugin)]
    return found if found and None not in found else []


def build_module(plugin: Path) -> str:
    """The module that built `plugin`: its stamp command's first word, else RUN."""
    kept = json.loads(stamp_path(plugin).read_text(encoding='utf-8')) if stamp_path(plugin).is_file() else {}
    return (kept.get('command') or RUN).split()[0]


def build_argv(plugin: Path, dirs: list) -> list:
    """`plugin`'s last build arguments (its inputs record, else its stamp), retargeted to its own folder and to the
    masters in `dirs` as its build module (build_module) takes them.
    See: docs/fork/fo4_plugin_layout.md#replay
    """
    rec = json.loads(inputs_path(plugin).read_text(encoding='utf-8')) if inputs_path(plugin).is_file() else None
    if rec is None:
        kept = json.loads(stamp_path(plugin).read_text(encoding='utf-8'))
        argv = kept.get('argv') or stamp_argv(kept['command'])
    else:
        argv = rec['argv']
    if build_module(plugin) == OVERLAY:
        return retarget_overlay(argv, plugin, header_masters(plugin, dirs))
    return retarget(argv, plugin, dirs)


def master_dirs(plugin: Path, plugins: list) -> list:
    """The folders of the `plugins` that `plugin`'s header names as masters."""
    names = {m.lower() for m in file_masters(plugin)}
    return sorted({Path(p).parent for p in plugins if Path(p).name.lower() in names})


def rebuild(plugin: Path, dirs: list = ()) -> int:
    """Build `plugin` again in its own folder with the module that built it, masters from `dirs`; the exit code
    (2 for a module this cannot replay)."""
    module = build_module(plugin)
    if module not in (RUN, OVERLAY):
        print(f'{plugin.name} was built by {module}, which build_plan cannot replay', flush=True)
        return 2
    print(f'== building {plugin.name} ({module})', flush=True)
    return subprocess.call([sys.executable, '-m', module, *build_argv(plugin, dirs)], cwd=ROOT)


def _scratch(path: Path) -> bool:
    """Whether `path` lies in a SCRATCH folder."""
    path = Path(path).resolve()
    return any(path.is_relative_to(root.resolve()) for root in SCRATCH)


def scratch_masters(plugins: list) -> list:
    """'<plugin>: master <path>' for each of `plugins` outside SCRATCH whose last build read a master inside it, or
    whose next build would (master_dirs over `plugins`).
    See: docs/fork/fo4_plugin_layout.md#plan-guards
    """
    out = []
    for plugin in map(Path, plugins):
        if _scratch(plugin):
            continue
        names = {m.lower() for m in file_masters(plugin)} if plugin.is_file() else set()
        nxt = [Path(p) for p in plugins if Path(p).name.lower() in names]
        out += [f'{plugin.name}: master {m}' for m in dict.fromkeys([*masters_of(plugin), *nxt]) if _scratch(m)]
    return out


def dependents(plugin: Path, plugins: list) -> set:
    """`plugin` and every one of `plugins` reading it as a master, directly or through another (resolved paths)."""
    out, grew = {Path(plugin).resolve()}, True
    reads = {Path(p).resolve(): {m.resolve() for m in masters_of(Path(p))} for p in plugins}
    while grew:
        more = {p for p, masters in reads.items() if p not in out and masters & out}
        out |= more
        grew = bool(more)
    return out


def leaked(rows: list, before: dict, built: Path, plugins: list) -> 'tuple | None':
    """(plugin, reason) of a row now BUILD, CURRENT in `before`, not depending on `built`; None if none.
    See: docs/fork/fo4_plugin_layout.md#plan-guards
    """
    deps = dependents(built, plugins)
    flipped = [(p, why) for p, verdict, why in rows if verdict == BUILD and before.get(p.resolve()) == CURRENT]
    return next(((p, why) for p, why in flipped if p.resolve() not in deps), None)


def faces_again(plugins: list) -> int:
    """Run the faces stage again (its recorded arguments) for each of `plugins` whose faces ran on another build
    of it; the first failing run's exit code, else 0.
    See: docs/fork/fo4_facegen_plan.md#faces-stamp
    """
    from fo4_import.spike import facegen
    for plugin in map(Path, plugins):
        reason = facegen.faces_stale(plugin)
        if reason is None:
            continue
        kept = facegen.faces_stamp(plugin)
        print(f'== faces of {plugin.name} again: {reason}', flush=True)
        code = subprocess.call([sys.executable, '-m', 'fo4_import.spike.facegen', *kept['argv']],
                               cwd=kept.get('cwd') or ROOT)
        if code:
            return code
    return 0


def run(plugins: list) -> int:
    """Build every plugin of `plugins` that needs it, masters first, checking the rest again after each, and run a
    rebuilt plugin's faces stage again (faces_again); the first failing build's exit code, STILL_BUILD when a
    plugin still needs a build after its own with none of its masters built since, LEAKED when a build flips a plugin that does not depend on it,
    SCRATCH_MASTER when a plugin reads a master from a scratch copy, else 0.
    See: docs/fork/fo4_plugin_layout.md#plan-guards
    """
    scratch = scratch_masters(plugins)
    if scratch:
        print('masters from scratch copies under temp/ (build those plugins against the real masters):\n  '
              + '\n  '.join(scratch), flush=True)
        return SCRATCH_MASTER
    built, before, last = set(), None, None
    while True:
        code, faces = clocked(faces_again, plugins)
        if code:
            return code
        rows, planned = clocked(plan, plugins)
        print(f'plan: {len(rows)} plugins in {planned:.1f}s (faces check {faces:.1f}s)', flush=True)
        found = leaked(rows, before, last, plugins) if last is not None else None
        if found:
            print(f'{found[0].name} needs a build after building {last.name}, which it does not depend on '
                  f'({found[1]}): that build changed an input of {found[0].name}; stopped', flush=True)
            return LEAKED
        todo = [(p, reason) for p, verdict, reason in rows if verdict == BUILD]
        if not todo:
            return 0
        plugin, reason = todo[0]
        if plugin.resolve() in built:
            print(f'{plugin.name} still needs a build after building it ({reason}); stopped', flush=True)
            return STILL_BUILD
        print(f'{plugin.name}: {reason}', flush=True)
        code, took = clocked(rebuild, plugin, master_dirs(plugin, plugins))
        print(f'{plugin.name}: build process {took:.0f}s, start to exit', flush=True)
        if code:
            return code
        built = (built - dependents(plugin, plugins)) | {plugin.resolve()}
        before, last = {p.resolve(): verdict for p, verdict, _ in rows}, plugin


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
