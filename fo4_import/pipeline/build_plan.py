"""Which plugins need a build: each built plugin's record (build_inputs) checked against the code, files and its
masters' builds as they are now.

    py -3.14 -m fo4_import.pipeline.build_plan temp/profile_data/FalloutNV.esm temp/profile_data_dm/DeadMoney.esm
    py -3.14 -m fo4_import.pipeline.build_plan --run <plugins...>      # build what needs it, masters first
    py -3.14 -m fo4_import.pipeline.build_plan --verify <plugin>       # rebuild a current plugin; same bytes?

A plugin is current, needs a build (with the first changed input), or waits for a master that does. --run also
runs a plugin's faces stage when due (faces_due: never run, stale, or older than a master's), stops when a build flips a plugin
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
import sys
from pathlib import Path

from asset_convert.sources import source_registry
from asset_convert.sources.source_registry import REGISTRY_NAME
from core.subprocess_flags import call_inherited
from fo4_import.base import release, source
from fo4_import.base.install import file_masters
from fo4_import.base.ledger import ID, Ledger, ledger_path
from fo4_import.base.master_overrides import read_built
from fo4_import.pipeline import creation_kit, mod_dirs, replay_manifest
from fo4_import.pipeline.build_inputs import inputs_path, listing, stamp
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.code_identity import changed, identity, rebase
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.ran_code import ARCHIVES, MESHES, SCRIPTS
from fo4_import.pipeline.stage_timer import clocked
from fo4_import.spike import facegen
from tes5_import.base.tes5_reader import walk

CURRENT, BUILD, AFTER = 'current', 'build', 'after'
#: run()'s own exit codes (its docstring): rebuilt plugin still BUILD, hidden input leaked, scratch master.
STILL_BUILD, LEAKED, SCRATCH_MASTER = 3, 4, 5
#: run()'s exit code for a plugin an older release built: the app converts it in full instead.
OLD_RELEASE = 7
#: Folders holding scratch builds: a plugin outside them must not read a master inside them.
SCRATCH = (ROOT / 'temp',)
#: The build modules a stamp's command can name, each replayed with its own retarget (build_command).
RUN, OVERLAY = 'fo4_import.pipeline.run', 'fo4_import.pipeline.overlay'
#: The parts replay (part_replay) and its exit code for a plugin that needs a whole build after all.
REPLAY, NEEDS_BUILD = 'fo4_import.pipeline.part_replay', 6
#: The build parts a replay can run again without the records part.
REPLAYABLE = frozenset({MESHES, ARCHIVES, SCRIPTS})
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
    """record() of `path` (here()), read once per pair of file mtimes (`_mtimes`)."""
    if json.loads(stamp_file.read_text(encoding='utf-8')).get('status') != 'finished':
        return None
    return here(json.loads(path.read_text(encoding='utf-8')))


def moved(path: str, old: str) -> str:
    """`path` in app folder `old` as the same path in this one; others as they are."""
    inside = os.path.normcase(path).startswith(os.path.normcase(old) + os.sep)
    return str(ROOT) + path[len(old):] if inside else path


def made_in(rec: dict) -> 'str | None':
    """Inputs record `rec`'s app folder: its root, else its fo4_import's folder."""
    tail = os.sep + 'fo4_import'
    return rec.get('root') or next((d[:-len(tail)] for d in rec['dirs'] if d.endswith(tail)), None)


def here(rec: dict) -> dict:
    """Inputs record `rec` with its paths in the app folder that made it (made_in) moved into this one.
    See: docs/fork/fo4_plugin_layout.md#moved-app-folder
    """
    old = made_in(rec)
    if not old or os.path.normcase(old) == os.path.normcase(str(ROOT)):
        return rec
    keyed = {k: {moved(p, old): v for p, v in rec.get(k, {}).items()} for k in ('files', 'dirs', 'programs', 'natives')}
    return {**rec, **keyed, 'root': str(ROOT), 'argv': [moved(a, old) for a in rec['argv']]}


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
    """The first input file, folder, program or native extension no longer as the build saw it; the export's source
    registry is never one (a record from before its lookups were logged lists it).
    See: docs/fork/fo4_mod_builds.md#mo2-answers
    """
    for path, kept in rec['files'].items():
        if Path(path).name != REGISTRY_NAME and not same_file(path, kept):
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
        asks = {mod_dirs.FOUND: mod_dirs.ask, source.ASKED: source.ask}
        if (asks[kind](arg) if kind in asks else creation_kit.ask(kind, arg)) != answer:
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


def _masters(log: dict, plugin: Path, scripts: bool = True) -> 'str | None':
    """The first master question that now has another answer (build_inputs.MasterLog), master FormIDs read in
    the numbering of `plugin`'s own masters; the master scripts compiled against only with `scripts`."""
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
    return _ledgers(log, found) or _staged(log) or (_scripts(log) if scripts else None)


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


def built_release(plugin: Path) -> str:
    """The release that last built `plugin` (its build stamp's): release.DEV for a checkout's build that recorded
    only its commit, '' when neither is recorded."""
    try:
        kept = json.loads(stamp_path(plugin).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    return kept.get('release') or (release.DEV if kept.get('commit') else '')


def from_older_release(plugin: Path) -> str:
    """'built by <release>, an older release' when one built `plugin`, else ''."""
    made = built_release(plugin)
    return f'built by {made}, an older release' if release.older(made) else ''


def verdict(plugin: Path) -> tuple:
    """(CURRENT or BUILD, the first changed input or '') of built `plugin`, its masters taken as they are now."""
    rec, older = record(plugin), from_older_release(plugin)
    if rec is None or older:
        return BUILD, older or 'no finished build with an inputs record'
    key = changed(rec['code'])
    if key:
        parts = stale_parts(rec)
        return BUILD, f'code {key} (parts: {", ".join(sorted(parts)) if parts else "unknown"})'
    reason = _environment(rec) or _files(rec) or _asked(rec) or _masters(rec['masters'], plugin)
    return (BUILD, reason) if reason else (CURRENT, '')


def stale_parts(rec: dict) -> 'frozenset | None':
    """The build parts every changed code key of inputs record `rec` ran in; None when one ran in none (a record
    from before parts were kept).
    See: docs/fork/fo4_plugin_layout.md#build-parts
    """
    parts = {part: set(keys) for part, keys in rec.get('code_parts', {}).items()}
    found = [{p for p, ran in parts.items() if key in ran} for key, value in rec['code'].items()
             if value is None or identity(key) != value]
    return None if not found or not all(found) else frozenset().union(*found)


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


def stamp_options(plugin: Path) -> dict:
    """{flag: [values]} of the command `plugin`'s build stamp records (stamp_argv); {} without a stamp."""
    path = stamp_path(plugin)
    out, flag = {}, None
    command = json.loads(path.read_text(encoding='utf-8')).get('command', '') if path.is_file() else ''
    for word in stamp_argv(command):
        if word.startswith('--'):
            flag = word
            out.setdefault(flag, [])
        elif flag:
            out[flag].append(word)
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
    rec = here(json.loads(inputs_path(plugin).read_text(encoding='utf-8'))) if inputs_path(plugin).is_file() else None
    if rec is None:
        kept = json.loads(stamp_path(plugin).read_text(encoding='utf-8'))
        argv = kept.get('argv') or stamp_argv(kept['command'])
    else:
        argv = rec['argv']
    if build_module(plugin) == OVERLAY:
        return retarget_overlay(argv, plugin, header_masters(plugin, dirs))
    return retarget(argv, plugin, dirs)


def in_root(root: Path, value: str) -> str:
    """Recorded folder `value` in `root`: root/<its name>, else the registry's record folder of that name."""
    name = Path(value).name
    plain = Path(root) / name
    if plain.is_dir() or not source_registry.get(root, name):
        return str(plain)
    return str(source_registry.record_dir(root, name))


def rooted(argv: list, roots: dict) -> list:
    """`argv` with the value of each flag in `roots` ({flag: folder}) moved into that folder (in_root).
    See: docs/fork/fo4_gui.md#rebuild-folders
    """
    out = list(argv)
    for i, word in enumerate(argv[:-1]):
        if roots.get(word):
            out[i + 1] = in_root(roots[word], argv[i + 1])
    return out


def master_dirs(plugin: Path, plugins: list) -> list:
    """The folders of the `plugins` that `plugin`'s header names as masters."""
    names = {m.lower() for m in file_masters(plugin)}
    return sorted({Path(p).parent for p in plugins if Path(p).name.lower() in names})


def replay_parts(plugin: Path) -> 'frozenset | None':
    """The parts to replay of `plugin` (built by pipeline.run) when its only changes are code that ran in
    REPLAYABLE parts alone and the master scripts it compiled against (the scripts part); the meshes and scripts
    parts only with a replay manifest holding them. None when it needs a whole build or nothing.
    See: docs/fork/fo4_plugin_layout.md#build-parts
    See: docs/fork/fo4_plugin_layout.md#scripts-replay
    """
    rec = record(plugin)
    if rec is None or build_module(plugin) != RUN:
        return None
    parts = stale_parts(rec) if changed(rec['code']) else frozenset()
    if parts is None or not parts <= REPLAYABLE:
        return None
    if _environment(rec) or _files(rec) or _asked(rec) or _masters(rec['masters'], plugin, scripts=False):
        return None
    parts |= {SCRIPTS} if _scripts(rec['masters']) else set()
    manifest = replay_manifest.read(plugin) if parts & {MESHES, SCRIPTS} else {}
    if not parts or manifest is None or (SCRIPTS in parts and not manifest.get('scripts')):
        return None
    return frozenset(parts)


def rebuild(plugin: Path, dirs: list = (), roots: dict = None) -> int:
    """Build `plugin` again in its own folder with the module that built it, masters from `dirs`, its folders moved
    into `roots` (rooted), or only replay the parts that changed (replay_parts, when `roots` moved nothing; a whole
    build after all when that says NEEDS_BUILD); the exit code (2 for a module this cannot replay)."""
    recorded = build_argv(plugin, dirs)
    argv = rooted(recorded, roots or {})
    if argv == recorded and replay_parts(plugin):
        print(f'== replaying parts of {plugin.name} ({REPLAY})', flush=True)
        code = call_inherited([sys.executable, '-m', REPLAY, str(plugin)], cwd=ROOT)
        if code != NEEDS_BUILD:
            return code
    module = build_module(plugin)
    if module not in (RUN, OVERLAY):
        print(f'{plugin.name} was built by {module}, which build_plan cannot replay', flush=True)
        return 2
    print(f'== building {plugin.name} ({module})', flush=True)
    return call_inherited([sys.executable, '-m', module, *argv], cwd=ROOT)


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


def faces_due(plugin: Path, plugins: list, roots: dict = None) -> 'tuple | None':
    """(why, the faces stage's arguments, its folder) when `plugin`'s faces must run: stale (facegen.faces_stale),
    run before a master's among `plugins` (only its overrides step: it takes their patched faces), or never run
    on a built plugin with fitted NPCs (arguments from its build stamp's export); None otherwise. The export is
    moved into `roots` (rooted).
    See: docs/fork/fo4_facegen_plan.md#addon-faces
    """
    kept = facegen.faces_stamp(plugin)
    if kept is None:
        export = stamp_options(plugin).get('--export')
        if not export or facegen.base_build(plugin) is None or not facegen.fitted(plugin):
            return None
        argv = rooted(['--export', export[0], '--data', str(plugin.parent), plugin.name], roots or {})
        return 'its faces never ran', argv, ROOT
    names = {m.lower() for m in file_masters(plugin)}
    later = [m.name for m in map(Path, plugins) if m.name.lower() in names
             and ((facegen.faces_stamp(m) or {}).get('ended') or '') > (kept.get('ended') or '')]
    old = kept.get('cwd') or str(ROOT)
    argv = rooted(in_folder([moved(a, old) for a in kept['argv']], plugin), roots or {})
    stale = facegen.faces_stale(plugin)
    if stale or not later:
        return (stale, argv, ROOT) if stale else None
    return f'its master {later[0]}\'s faces ran after its own', [facegen.OVERRIDES_ONLY, *argv], ROOT


def in_folder(argv: list, plugin: Path) -> list:
    """Faces stage arguments `argv` with `--data` set to `plugin`'s own folder."""
    if '--data' not in argv:
        return ['--data', str(plugin.parent), *argv]
    at = argv.index('--data') + 1
    return argv[:at] + [str(plugin.parent)] + argv[at + 1:]


def faces_again(plugins: list, roots: dict = None) -> int:
    """Run the faces stage (faces_due's arguments, its export in `roots`) for each of `plugins`, in order, whose
    faces are due; the first failing run's exit code, else 0.
    See: docs/fork/fo4_facegen_plan.md#faces-stamp
    """
    for plugin in map(Path, plugins):
        due = faces_due(plugin, plugins, roots)
        if due is None:
            continue
        reason, argv, cwd = due
        print(f'== faces of {plugin.name}: {reason}', flush=True)
        code = call_inherited([sys.executable, '-m', 'fo4_import.spike.facegen', *argv], cwd=cwd)
        if code:
            return code
    return 0


def refusal(plugins: list) -> 'tuple | None':
    """(exit code, why) when run() must not replay `plugins`: a master from a scratch copy (SCRATCH_MASTER), or one
    an older release built (OLD_RELEASE); None when it may."""
    scratch = scratch_masters(plugins)
    if scratch:
        return SCRATCH_MASTER, ('masters from scratch copies under temp/ (build those plugins against the real '
                                'masters):\n  ' + '\n  '.join(scratch))
    old = [f'{Path(p).name} ({from_older_release(Path(p))})' for p in plugins if from_older_release(Path(p))]
    if old:
        return OLD_RELEASE, f'convert in full (the Build stage), not rebuilt: {", ".join(old)}'
    return None


def run(plugins: list, roots: dict = None) -> int:
    """Build every plugin of `plugins` that needs it, masters first, from the folders in `roots` (rooted),
    checking the rest again after each, and run a rebuilt plugin's faces again (faces_again); the first failing
    build's exit code, STILL_BUILD when one still needs a build after its own, LEAKED when a build flips a
    plugin not depending on it, SCRATCH_MASTER for a master from a scratch copy, OLD_RELEASE for one an older
    release built, else 0.
    See: docs/fork/fo4_plugin_layout.md#plan-guards
    """
    refused = refusal(plugins)
    if refused:
        print(refused[1], flush=True)
        return refused[0]
    built, before, last = set(), None, None
    while True:
        code, faces = clocked(faces_again, plugins, roots)
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
            print('every plugin is up to date now' if built else 'nothing to rebuild: every plugin is up to date',
                  flush=True)
            return 0
        plugin, reason = todo[0]
        if plugin.resolve() in built:
            print(f'{plugin.name} still needs a build after building it ({reason}); stopped', flush=True)
            return STILL_BUILD
        print(f'{plugin.name}: {reason}', flush=True)
        code, took = clocked(rebuild, plugin, master_dirs(plugin, plugins), roots)
        print(f'{plugin.name}: build process {took:.0f}s, start to exit', flush=True)
        if code:
            print(f'{plugin.name}: its build failed (exit code {code}); the lines above say why', flush=True)
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
    ap.add_argument('--export-root', help='--run: read each export from this folder, not the recorded one')
    ap.add_argument('--scripts-root', help='--run: convert each plugin\'s scripts into this folder')
    args = ap.parse_args()
    if args.verify:
        sys.exit(verify(args.plugins[0]))
    if args.run:
        sys.exit(run(args.plugins, {'--export': args.export_root, '--scripts': args.scripts_root}))
    for plugin, verdict, reason in plan(args.plugins):
        print(f'{plugin.name}: {verdict}{f" ({reason})" if reason else ""}')


if __name__ == '__main__':
    main()
