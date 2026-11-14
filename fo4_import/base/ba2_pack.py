"""Pack a Data folder's loose textures into the plugin's texture BA2 (ba2_textures, our own writer), its voices
into `<plugin> - Voices_<language>.ba2`, and its other sounds, meshes, materials and scripts into its Main BA2
(pack_main); the loose copies the archives hold leave the Data folder after the build (drop_packed: the Main
archive's into a stash beside the staging folder) and come back before the next (restore_packed).

Fallout 4 streams a texture's mips from a BA2's chunks; a loose DDS can stay
on a low mip, and past iTextureDegradeDistance the game drops a texture's top
chunk (a 512 FNV texture to 256). Each texture is one chunk, as some vanilla
ones are, so it always shows in full, as in FNV. Loose files under
<data>/Textures move into the Data folder's staging folder (staging_root,
outside it, so neither the game nor MO2 lists it), and all of it becomes
`<plugin> - Textures.ba2`, loaded with the
plugin. Folders the caller keeps loose (uncompressed one-mip LUTs, which
vanilla keeps in a general archive) stay loose. A build writes its textures
through stage_texture(): once per run, and not at all while the staged copy
is current; pack_textures() then drops staged OWN textures the build neither
wrote nor confirmed, and repacks only a changed staging folder.

See: docs/fork/fo4_spikes.md#spike-4-exterior
See: docs/fork/fo4_tool_audit.md#rebuild
"""

import functools
import glob
import hashlib
import json
import multiprocessing
import os
import shutil
from pathlib import Path

from core.build_resources import pool_workers
from fo4_import.base.ba2 import Archive
from fo4_import.base.ba2_textures import write_textures
from fo4_import.base.ba2_write import same_bytes, write_general
from fo4_import.base.build_files import moved_in
from fo4_import.base.install import game_language
from fo4_import.pipeline.build_inputs import MASTERS
from fo4_import.pipeline.code_tag import ROOT

#: The staging folder's old place, under the Data folder (moved out by staging_root), and its new home.
STAGING, STAGING_CACHE = '_ba2', ROOT / 'output' / 'fo4_cache' / 'ba2'
#: The staging folder's record of its files at the last pack: {texture key: [size, mtime_ns, signature or None]}.
MANIFEST = 'manifest.json'
#: Texture key prefixes a build writes itself (its textures, its worldspaces' LOD); only these are pruned, not FaceGen.
OWN = ('fnv/', 'terrain/fnv_')
#: The Data folder's folder packed into `<plugin> - Main.ba2`, uncompressed (.fuz and .xwm are compressed already).
SOUND = 'Sound'
#: The staged sound folder (lowercase, '/'-separated, ending '/') packed apart, into voices_archive().
VOICE = 'sound/voice/'
#: Data folders the build writes loose that the Main archive holds, each with the one file ending it packs (None: all).
PACKED = (('Meshes', None), ('Materials', None), ('Scripts', '.pex'))
#: The staging folder's folder keeping, per plugin, the loose Main files between builds (stash_dir), and its stamp.
LOOSE, STAMP = 'loose', 'stash.json'
#: What a write_later worker commits, for the worker count (build_resources.pool_workers).
WRITE_WORKER_BYTES = 512 << 20
#: Per resolved Data folder, this run's {'manifest': the last pack's record, 'staged': {key: signature}}.
_RUNS = {}


def texture_key(rel: str) -> str:
    """Texture path `rel` (under Textures) as a key: lowercase, forward slashes."""
    return rel.replace('\\', '/').lower()


def _run_key(data_dir: Path) -> str:
    """`data_dir` as a _RUNS key."""
    return os.path.normcase(os.path.abspath(data_dir))


def staging_root(data_dir: Path) -> Path:
    """The folder staging `data_dir`'s archive files, in STAGING_CACHE (_staging)."""
    return _staging(Path(STAGING_CACHE), _run_key(data_dir))


@functools.cache
def _staging(cache: Path, data_key: str) -> Path:
    """staging_root() of normalized Data folder `data_key` under `cache`: outside the Data folder, so a deployed
    mod folder carries no staging; an old <data>/_ba2 moves there on first use, or goes when the new one
    exists.
    See: docs/fork/fo4_pipeline.md#sound-archive
    """
    data = Path(data_key)
    root = cache / f'{data.name}-{hashlib.sha1(data_key.encode()).hexdigest()[:12]}'
    legacy = data / STAGING
    if legacy.is_dir() and not root.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(root))
    elif legacy.is_dir():
        shutil.rmtree(legacy)
    return root


def _read_json(path: Path) -> dict:
    """The JSON object in `path`; {} when it is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _run(data_dir: Path) -> dict:
    """This run's texture record for `data_dir` (_RUNS), made on first use."""
    key = _run_key(data_dir)
    if key not in _RUNS:
        _RUNS[key] = {'manifest': _read_json(staging_root(data_dir) / MANIFEST), 'staged': {}, 'masters': (),
                         'shared': set()}
    return _RUNS[key]


def share_masters(data_dir: Path, masters: list) -> None:
    """stage_texture() skips what a `masters` data folder packed alike.
    See: docs/fork/fo4_plugin_layout.md#dlc-build
    """
    for master in masters:
        MASTERS.cover('manifest', staging_root(master) / MANIFEST)
    _run(data_dir)['masters'] = tuple(_read_json(staging_root(m) / MANIFEST) for m in masters)


def _in_master(run: dict, key: str, signature) -> bool:
    """Whether a master of `run` packed texture `key` with `signature` (the masters' answers logged)."""
    packed = [(m.get(key) or [None] * 3)[2] for m in run['masters']]
    if packed:
        MASTERS.texture(key, packed)
    return signature is not None and signature in packed


def _current(staged: Path, recorded, signature: str) -> bool:
    """Whether `staged` is unchanged since the last pack recorded it as `recorded` with `signature`."""
    if not recorded or recorded[2] != signature:
        return False
    try:
        stat = staged.stat()
    except OSError:
        return False
    return [stat.st_size, stat.st_mtime_ns] == recorded[:2]


def stage_texture(data_dir: Path, rel: str, plan, later: 'list | None' = None) -> bool:
    """Write texture `rel` (under <data_dir>/Textures) once per run, unless the last pack staged it with the same
    signature and it is unchanged since; whether it was (or, with `later`, will be: write_later) written. plan() is
    (signature, write(target)): the signature names everything the file is made from (a copy's source, size and
    time; a derived map's work-cache key). A second call this run is skipped unplanned (staged)."""
    if staged(data_dir, rel):
        return False
    run, key = _run(data_dir), texture_key(rel)
    signature, write = plan()
    if _in_master(run, key, signature):
        run['shared'].add(key)
        return False
    run['staged'][key] = signature
    target = Path(data_dir) / 'Textures' / rel.replace('\\', '/')
    if not target.exists() and _current(staging_root(data_dir) / 'Textures' / key, run['manifest'].get(key),
                                        signature):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if later is None:
        write(target)
    else:
        later.append((write, target))
    return True


def staged(data_dir: Path, rel: str) -> bool:
    """Whether stage_texture already took texture `rel` this run.
    See: docs/fork/fo4_build_speed.md#staged-first
    """
    run, key = _run(data_dir), texture_key(rel)
    return key in run['staged'] or key in run['shared']


def _write_one(job: tuple) -> None:
    """Run one (write, target) job of stage_texture's `later`."""
    write, target = job
    write(target)


def write_later(jobs: list, workers: int) -> None:
    """Run (write, target) `jobs` on `workers` processes (0: the resource profile's)."""
    with multiprocessing.Pool(pool_workers(WRITE_WORKER_BYTES, len(jobs), workers)) as pool:
        pool.map(_write_one, jobs, chunksize=1)


def _move_loose(loose: Path, staged: Path, keep_loose: tuple) -> set:
    """Move every file under `loose` but `keep_loose` folders into `staged`; their texture keys. A loose file the
    staged copy already matches byte for byte is deleted instead, so the copy keeps its time and the archive
    copies it rather than compressing it again.
    See: docs/fork/fo4_pipeline.md#faces-repack
    """
    kept = [loose / folder.replace(chr(92), '/') for folder in keep_loose]
    moved = set()
    for path in sorted(p for p in loose.rglob('*') if p.is_file()) if loose.exists() else []:
        if any(path.is_relative_to(folder) for folder in kept):
            continue
        target = staged / path.relative_to(loose)
        if _same_file(path, target):
            path.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
        moved.add(path.relative_to(loose).as_posix().lower())
    return moved


def _same_file(path: Path, other: Path) -> bool:
    """Whether `other` exists and holds exactly `path`'s bytes."""
    return other.is_file() and other.stat().st_size == path.stat().st_size and other.read_bytes() == path.read_bytes()


def _unstage(staged: Path, loose: Path, keep_loose: tuple) -> int:
    """Move files an older build staged under `keep_loose` folders back to `loose`, or delete them where a loose
    copy exists; how many came back."""
    back = 0
    for folder in keep_loose:
        base = staged / folder.replace(chr(92), '/')
        for path in sorted(p for p in base.rglob('*') if p.is_file()) if base.is_dir() else []:
            target = loose / path.relative_to(staged)
            if target.exists():
                path.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
            back += 1
    return back


def _staged_files(staged: Path, keep: 'set | None') -> dict:
    """{key: path} of the files under `staged`, OWN ones not in `keep` deleted first (None: none deleted)."""
    out = {}
    for path in sorted(p for p in staged.rglob('*') if p.is_file()) if staged.exists() else []:
        key = path.relative_to(staged).as_posix().lower()
        if keep is not None and key.startswith(OWN) and key not in keep:
            path.unlink()
            continue
        out[key] = path
    return out


def _pack(archive: Path, files: dict, make) -> None:
    """Pack `archive` with make(kept) unless the record beside it shows the same `files` ({key: [size, mtime]})
    packed; `kept` are the keys unchanged since the archive on disk was packed."""
    state = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
    record = pack_record(archive)
    packed = _read_json(record)
    stat = archive.stat() if archive.exists() else None
    current = bool(stat) and packed.get('archive') == [stat.st_size, stat.st_mtime_ns]
    if current and packed.get('files') == state:
        return
    before = packed.get('manifest', {}) if current else {}
    make({key for key, value in files.items() if before.get(key) == value})
    stat = archive.stat()
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({'files': state, 'archive': [stat.st_size, stat.st_mtime_ns], 'manifest': files}),
                      encoding='utf-8')


def pack_record(archive: Path) -> Path:
    """`archive`'s record of what it holds, in the build records (build_files)."""
    return moved_in(archive.with_name(archive.name + '.json'))


def _signature(run: dict, key: str, stat) -> 'str | None':
    """Staged texture `key`'s signature: this run's (stage_texture), else the last pack's while the file is
    unchanged since."""
    if key in run['staged']:
        return run['staged'][key]
    kept = run['manifest'].get(key) or [None] * 3
    return kept[2] if kept[:2] == [stat.st_size, stat.st_mtime_ns] else None


def pack_textures(data_dir: Path, plugin: str, keep_loose: tuple = (), prune: bool = True) -> int:
    """Stage <data_dir>/Textures (but `keep_loose` folders), drop staged OWN textures this run neither wrote nor
    confirmed (stage_texture; not without `prune`, for a run that stages none), and pack the staging as
    `<plugin stem> - Textures.ba2` when it changed since that archive was packed; the staged file count."""
    root = staging_root(data_dir)
    run = _RUNS.pop(_run_key(data_dir), None) or {'manifest': _read_json(root / MANIFEST), 'staged': {}}
    _unstage(root / 'Textures', data_dir / 'Textures', keep_loose)
    moved = _move_loose(data_dir / 'Textures', root / 'Textures', keep_loose)
    paths = _staged_files(root / 'Textures', moved | set(run['staged']) if prune else None)
    files = {}
    for key, path in paths.items():
        stat = path.stat()
        files[key] = [stat.st_size, stat.st_mtime_ns, _signature(run, key, stat)]
    archive = data_dir / f'{Path(plugin).stem} - Textures.ba2'
    named = {f'Textures/{key}': path for key, path in paths.items()}
    _pack(archive, {key: value[:2] for key, value in files.items()},
          lambda kept: write_textures(named, archive, {f'textures/{key}' for key in kept}))
    (root / MANIFEST).write_text(json.dumps(files, sort_keys=True), encoding='utf-8')
    return len(files)


def sound_root(data_dir: Path) -> Path:
    """Where sounds are written, as <it>/Sound/...: the staging folder (staging_root)."""
    return staging_root(data_dir)


def stage_loose_sounds(data_dir: Path, own: tuple) -> int:
    """Move loose files in the `own` Sound folders into sound_root; how many."""
    root = sound_root(data_dir) / SOUND
    return sum(len(_move_loose(Path(data_dir) / SOUND / folder, root / folder, ())) for folder in own)


def _tree(base: Path, folder: str) -> dict:
    """{name relative to `base`, '/'-separated: path} of every file under `base`/`folder`."""
    out = {}
    for top, _dirs, names in os.walk(Path(base) / folder):
        rel = Path(top).relative_to(base).as_posix()
        out.update((f'{rel}/{name}', Path(top, name)) for name in names)
    return out


def archive_files(data_dir: Path) -> tuple:
    """({archive name: path} of what `<plugin> - Main.ba2` holds, of what voices_archive() holds): the staged
    sounds (sound_root) but VOICE and the loose PACKED files of `data_dir`; the staged VOICE files."""
    main, voices = {}, {}
    for name, path in _tree(sound_root(data_dir), SOUND).items():
        (voices if name.lower().startswith(VOICE) else main)[name] = path
    return {**main, **_packed_loose(Path(data_dir))}, voices


def _packed_loose(base: Path) -> dict:
    """{name relative to `base`, '/'-separated: path} of the PACKED files loose under `base`."""
    out = {}
    for folder, ending in PACKED:
        out.update((name, path) for name, path in _tree(base, folder).items()
                   if ending is None or name.lower().endswith(ending))
    return out


def voices_archive(data_dir: Path, plugin: str) -> Path:
    """`plugin`'s voices archive in `data_dir`, named for the game's language."""
    return Path(data_dir) / f'{Path(plugin).stem} - Voices_{game_language()}.ba2'


def _voice_archives(data_dir: Path, plugin: str) -> list:
    """`plugin`'s voices archives in `data_dir`, of any language."""
    return sorted(Path(data_dir).glob(f'{glob.escape(Path(plugin).stem)} - Voices_*.ba2'))


def _pack_general(archive: Path, named: dict, held: 'dict | None' = None) -> None:
    """Pack `named` ({name: loose path}) and `held` ({name: [size, mtime]} that `archive` holds as packed,
    archived(), none of them in `named`) as general `archive` when that changed since it was packed; delete the
    archive and its record when both are empty (an earlier build's would ship stale files)."""
    held = held or {}
    stats = {name: path.stat() for name, path in named.items()}
    files = {**held, **{name: [st.st_size, st.st_mtime_ns] for name, st in stats.items()}}
    if files:
        everything = {**dict.fromkeys(held), **named}
        _pack(archive, {name.lower(): value for name, value in files.items()},
              lambda kept: write_general(everything, archive, kept, {name: value[0] for name, value in files.items()}))
    for stale in () if files else (archive, pack_record(archive)):
        stale.unlink(missing_ok=True)


def archived(archive: Path) -> 'dict | None':
    """{name as `archive` spells it, '/'-separated: [size, mtime] it was packed with}, from its pack record; None
    when the record does not describe the archive on disk.
    See: docs/fork/fo4_pipeline.md#faces-repack
    """
    packed, stat = _read_json(pack_record(archive)), archive.stat() if archive.exists() else None
    if not stat or packed.get('archive') != [stat.st_size, stat.st_mtime_ns]:
        return None
    spelled = {name.replace(chr(92), '/'): text.replace(chr(92), '/')
               for name, text in Archive(archive).spelled.items()}
    return {spelled[name]: value for name, value in packed.get('manifest', {}).items() if name in spelled}


def _held(archive: Path, main: dict, replaced: tuple) -> dict:
    """What `archive` keeps as packed ({name as it spells it: [size, mtime]}, archived()): each loose file of
    `main` ({name: path}) whose size and time, else bytes, match its packed copy; with `replaced` folders, also
    every entry outside them that is not loose (a stage that rewrites only those folders).
    See: docs/fork/fo4_pipeline.md#unchanged-bytes
    """
    record = archived(archive) or {}
    spelled = {name.lower(): name for name in record}
    loose = {name.lower(): path for name, path in main.items()}
    held = {spelled[n]: record[spelled[n]] for n in spelled
            if replaced and n not in loose and not n.startswith(replaced)}
    stats = {n: loose[n].stat() for n in spelled.keys() & loose.keys()}
    same = {n for n, st in stats.items() if record[spelled[n]] == [st.st_size, st.st_mtime_ns]}
    sized = {n: loose[n] for n, st in stats.items() if n not in same and record[spelled[n]][0] == st.st_size}
    for n in same | (same_bytes(archive, sized) if sized else set()):
        held[spelled[n]] = record[spelled[n]]
    return held


def pack_main(data_dir: Path, plugin: str, replaced: tuple = ()) -> int:
    """Pack archive_files() as `<plugin stem> - Main.ba2` and voices_archive(), each only when its files changed
    since it was packed (_pack_general); another language's voices archive goes; the file count. The loose PACKED
    files stay until drop_packed(). Main keeps what _held() says as packed (`replaced`: folders this stage
    rewrites, the rest needing no restore_packed()).
    See: docs/fork/fo4_pipeline.md#main-archive
    See: docs/fork/fo4_pipeline.md#unchanged-bytes
    See: docs/fork/fo4_build_speed.md#voices-archive
    """
    main, voices = archive_files(data_dir)
    target = voices_archive(data_dir, plugin)
    for old in _voice_archives(data_dir, plugin):
        if old != target:
            _pack_general(old, {})
    archive = Path(data_dir) / f'{Path(plugin).stem} - Main.ba2'
    held = _held(archive, main, replaced)
    same = {name.lower() for name in held}
    main = {name: path for name, path in main.items() if name.lower() not in same}
    _pack_general(archive, main, held)
    _pack_general(target, voices)
    return len(main) + len(held) + len(voices)


def own_archives(data_dir: Path, plugin: str) -> list:
    """`plugin`'s Main, voices and Textures archives in `data_dir` that exist."""
    stem = Path(plugin).stem
    return [p for p in (Path(data_dir) / f'{stem} - {kind}.ba2' for kind in ('Main', 'Textures')) if p.is_file()] \
        + _voice_archives(data_dir, plugin)


def stash_dir(data_dir: Path, plugin: str) -> Path:
    """Where drop_packed() keeps `plugin`'s loose Main files, outside the Data folder."""
    return staging_root(data_dir) / LOOSE / Path(plugin).stem


def stashed(data_dir: Path, plugin: str) -> bool:
    """Whether stash_dir() holds the loose copies of `plugin`'s Main archive as it is on disk."""
    archive = Path(data_dir) / f'{Path(plugin).stem} - Main.ba2'
    stat = archive.stat() if archive.is_file() else None
    stamp = _read_json(stash_dir(data_dir, plugin) / STAMP)
    return bool(stat) and stamp.get('archive') == [stat.st_size, stat.st_mtime_ns]


def _stash(data_dir: Path, plugin: str) -> int:
    """Move the loose PACKED files into stash_dir() (each top folder in one rename), stamped with the Main
    archive's size and time, when they are exactly the archive's PACKED entries and the stash is on the Data
    folder's drive; how many (0: none moved, the earlier stash gone).
    See: docs/fork/fo4_pipeline.md#loose-stash
    """
    data, stash = Path(data_dir), stash_dir(data_dir, plugin)
    archive = data / f'{Path(plugin).stem} - Main.ba2'
    shutil.rmtree(stash, ignore_errors=True)
    stash.mkdir(parents=True, exist_ok=True)
    loose = _packed_loose(data) if archive.is_file() and os.stat(stash).st_dev == os.stat(data).st_dev else {}
    folders = tuple(folder.lower() + chr(92) for folder, _ in PACKED)
    held = {name for name in Archive(archive).entries if name.startswith(folders)} if loose else set()
    if not loose or {name.lower().replace('/', chr(92)) for name in loose} != held:
        shutil.rmtree(stash, ignore_errors=True)
        return 0
    whole = {folder.lower() for folder, ending in PACKED if ending is None}
    for top in [name for name in os.listdir(data) if name.lower() in whole]:
        os.replace(data / top, stash / top)
    for name, path in loose.items():
        if path.is_file():
            (stash / name).parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, stash / name)
    stat = archive.stat()
    (stash / STAMP).write_text(json.dumps({'archive': [stat.st_size, stat.st_mtime_ns], 'files': len(loose)}))
    return len(loose)


def _unstash(data_dir: Path, plugin: str) -> int:
    """Move stash_dir()'s files back where the Data folder has none (a whole top folder in one rename) when
    stashed(), else drop the stash; how many came back.
    See: docs/fork/fo4_pipeline.md#loose-stash
    """
    stash = stash_dir(data_dir, plugin)
    files = _read_json(stash / STAMP).get('files', 0) if stashed(data_dir, plugin) else 0
    (stash / STAMP).unlink(missing_ok=True)
    for top in os.listdir(stash) if files else ():
        if not (Path(data_dir) / top).exists():
            os.replace(stash / top, Path(data_dir) / top)
    for path in sorted(p for p in stash.rglob('*') if p.is_file()) if files else ():
        target = Path(data_dir) / path.relative_to(stash)
        if target.exists():
            path.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
    shutil.rmtree(stash, ignore_errors=True)
    return files


def drop_packed(data_dir: Path, plugin: str) -> int:
    """Take each loose file in `data_dir` that `plugin`'s archives hold out of it: loose wins over an archive, and
    under MO2 the game's launch pays for every loose file; how many. The Main archive's go to stash_dir() when
    _stash() can, the rest are deleted; restore_packed() brings the Main archive's back.
    See: docs/fork/fo4_pipeline.md#main-archive
    See: docs/fork/fo4_pipeline.md#loose-stash
    """
    gone = _stash(data_dir, plugin)
    for archive in own_archives(data_dir, plugin):
        for name in Archive(archive).entries:
            path = Path(data_dir) / name.replace(chr(92), '/')
            if path.is_file():
                path.unlink()
                gone += 1
    _remove_empty(Path(data_dir), tuple(folder for folder, _ in PACKED) + ('Textures',))
    return gone


def _remove_empty(data_dir: Path, folders: tuple) -> None:
    """Remove the empty folders under `data_dir`'s `folders`, deepest first (each of `folders` too when empty)."""
    for folder in folders:
        tops = sorted(os.walk(data_dir / folder), key=lambda t: -len(t[0])) if (data_dir / folder).is_dir() else []
        for top, _dirs, _names in tops:
            if not any(Path(top).iterdir()):
                Path(top).rmdir()


def restore_packed(data_dir: Path, plugin: str) -> int:
    """Bring back each PACKED file of `plugin`'s Main archive that `data_dir` lacks loose (drop_packed): moved
    back from stash_dir() (_unstash), the rest written from the archive, spelled and dated as the archive, so a
    build or the faces stage reads what the last build made; how many.
    See: docs/fork/fo4_pipeline.md#main-archive
    See: docs/fork/fo4_pipeline.md#loose-stash
    """
    archive = Path(data_dir) / f'{Path(plugin).stem} - Main.ba2'
    if not archive.is_file():
        return 0
    main, when, restored = Archive(archive), archive.stat().st_mtime, _unstash(data_dir, plugin)
    folders = tuple(folder.lower() + chr(92) for folder, _ in PACKED)
    for name, spelled in main.spelled.items():
        path = Path(data_dir) / spelled.replace(chr(92), '/')
        if name.startswith(folders) and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(main.read(name))
            os.utime(path, (when, when))
            restored += 1
    return restored


def archived_names(data_dir: Path) -> set:
    """The lowercase '/'-separated paths the BA2s at the top of `data_dir` hold."""
    archives = sorted(Path(data_dir).glob('*.ba2')) if Path(data_dir).is_dir() else []
    return set().union(*(_names(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in archives))


@functools.lru_cache(maxsize=64)
def _names(path: str, size: int, mtime: int) -> frozenset:
    """Archive `path`'s paths, lowercase, '/'-separated (size and time key the cache)."""
    return frozenset(name.replace(chr(92), '/') for name in _archive(path, size, mtime).entries)


@functools.lru_cache(maxsize=8)
def _archive(path: str, _size: int, _mtime: int) -> Archive:
    """Archive `path` indexed once while its size and time stay (they key the cache)."""
    return Archive(Path(path))


def data_file(data_dir: Path, rel: str) -> 'bytes | None':
    """The bytes of Data path `rel` in `data_dir`: loose, else from its top-level archives; None when neither."""
    loose = Path(data_dir) / rel
    if loose.is_file():
        return loose.read_bytes()
    key = str(rel).replace(chr(92), '/').lower()
    for archive in sorted(Path(data_dir).glob('*.ba2'), reverse=True) if Path(data_dir).is_dir() else ():
        stamp = str(archive), archive.stat().st_size, archive.stat().st_mtime_ns
        if key in _names(*stamp):
            return _archive(*stamp).read(key)
    return None
