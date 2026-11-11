"""Pack a Data folder's loose textures into the plugin's texture BA2 with the CK's Archive2, and its sounds,
meshes and materials into its Main BA2 (pack_main).

Fallout 4 streams a texture's mips from a BA2's chunks; a loose DDS can stay
on a low mip, and past iTextureDegradeDistance the game drops a texture's top
chunk (a 512 FNV texture to 256). Each texture is one chunk, as some vanilla
ones are, so it always shows in full, as in FNV. Loose files under
<data>/Textures move into the Data folder's staging folder (staging_root,
outside it, so neither the game nor MO2 lists it), and all of it becomes
`<plugin> - Textures.ba2`, loaded with the
plugin. Folders the archiver cannot take (uncompressed one-mip LUTs, which
vanilla keeps in a general archive) stay loose. A build writes its textures
through stage_texture(): once per run, and not at all while the staged copy
is current; pack_textures() then drops staged OWN textures the build neither
wrote nor confirmed, and repacks only a changed staging folder.

See: docs/fork/fo4_spikes.md#spike-4-exterior
See: docs/fork/fo4_tool_audit.md#rebuild
"""

import functools
import hashlib
import json
import multiprocessing
import os
import shutil
import subprocess
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.ba2_write import write_general
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.pipeline.build_inputs import MASTERS
from fo4_import.pipeline.code_tag import ROOT

ARCHIVE2 = FALLOUT4_DIR / 'Tools' / 'Archive2' / 'Archive2.exe'
#: The staging folder's old place, under the Data folder (moved out by staging_root), and its new home.
STAGING, STAGING_CACHE = '_ba2', ROOT / 'output' / 'fo4_cache' / 'ba2'
#: Chunks per texture: one, so the game has no top mips to drop with distance.
CHUNKS = 1
#: The staging folder's record of its files at the last pack: {texture key: [size, mtime_ns, signature or None]}.
MANIFEST = 'manifest.json'
#: Texture key prefixes a build writes itself (its textures, its worldspaces' LOD); only these are pruned, not FaceGen.
OWN = ('fnv/', 'terrain/fnv_')
#: Archive2's options for the texture archive: DDS, CHUNKS chunks per texture.
TEXTURE_OPTIONS = ('-f=DDS', f'-maxChunkCount={CHUNKS}')
#: The Data folder's folder packed into `<plugin> - Main.ba2`, uncompressed (.fuz and .xwm are compressed already).
SOUND = 'Sound'
#: Data folders the build writes loose and the Main archive also holds (Scripts stay loose, so hotfixes still win).
PACKED = ('Meshes', 'Materials')
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
    time; a derived map's work-cache key). A second call this run is skipped unplanned."""
    run, key = _run(data_dir), texture_key(rel)
    if key in run['staged'] or key in run['shared']:
        return False
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


def _write_one(job: tuple) -> None:
    """Run one (write, target) job of stage_texture's `later`."""
    write, target = job
    write(target)


def write_later(jobs: list, workers: int) -> None:
    """Run (write, target) `jobs` on `workers` processes (0: CPUs - 1)."""
    with multiprocessing.Pool(workers or max(1, os.cpu_count() - 1)) as pool:
        pool.map(_write_one, jobs, chunksize=1)


def _move_loose(loose: Path, staged: Path, keep_loose: tuple) -> set:
    """Move every file under `loose` but `keep_loose` folders into `staged`; their texture keys."""
    kept = [loose / folder.replace(chr(92), '/') for folder in keep_loose]
    moved = set()
    for path in sorted(p for p in loose.rglob('*') if p.is_file()) if loose.exists() else []:
        if any(path.is_relative_to(folder) for folder in kept):
            continue
        target = staged / path.relative_to(loose)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(path, target)
        moved.add(path.relative_to(loose).as_posix().lower())
    return moved


def _staged_files(staged: Path, keep: set) -> dict:
    """{key: path} of the files under `staged`, OWN ones not in `keep` deleted first."""
    out = {}
    for path in sorted(p for p in staged.rglob('*') if p.is_file()) if staged.exists() else []:
        key = path.relative_to(staged).as_posix().lower()
        if key.startswith(OWN) and key not in keep:
            path.unlink()
            continue
        out[key] = path
    return out


def _archive2(staged: Path, root: Path, archive: Path) -> None:
    """Pack `staged` as the texture archive `archive` (TEXTURE_OPTIONS), named from `root`, with Archive2."""
    done = subprocess.run([str(ARCHIVE2), str(staged.resolve()), f'-c={archive.resolve()}', *TEXTURE_OPTIONS,
                           f'-r={root.resolve()}', '-q'],
                          capture_output=True, text=True, **POPEN_FLAGS)
    if done.returncode or not archive.exists():
        raise RuntimeError(f'Archive2 could not pack {archive} (absolute paths only): {done.stdout}{done.stderr}')


def _pack(archive: Path, files: dict, make) -> None:
    """Pack `archive` with make(kept) unless the record beside it shows the same `files` ({key: [size, mtime]})
    packed; `kept` are the keys unchanged since the archive on disk was packed."""
    state = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
    record = archive.with_name(archive.name + '.json')
    packed = _read_json(record)
    stat = archive.stat() if archive.exists() else None
    current = bool(stat) and packed.get('archive') == [stat.st_size, stat.st_mtime_ns]
    if current and packed.get('files') == state:
        return
    before = packed.get('manifest', {}) if current else {}
    make({key for key, value in files.items() if before.get(key) == value})
    stat = archive.stat()
    record.write_text(json.dumps({'files': state, 'archive': [stat.st_size, stat.st_mtime_ns], 'manifest': files}),
                      encoding='utf-8')


def pack_textures(data_dir: Path, plugin: str, keep_loose: tuple = ()) -> int:
    """Stage <data_dir>/Textures (but `keep_loose` folders), drop staged OWN textures this run neither wrote nor
    confirmed (stage_texture), and pack the staging as `<plugin stem> - Textures.ba2` when it changed since that
    archive was packed; the staged file count."""
    root = staging_root(data_dir)
    run = _RUNS.pop(_run_key(data_dir), None) or {'manifest': _read_json(root / MANIFEST), 'staged': {}}
    moved = _move_loose(data_dir / 'Textures', root / 'Textures', keep_loose)
    paths = _staged_files(root / 'Textures', moved | set(run['staged']))
    files = {}
    for key, path in paths.items():
        stat = path.stat()
        files[key] = [stat.st_size, stat.st_mtime_ns, run['staged'].get(key)]
    archive = data_dir / f'{Path(plugin).stem} - Textures.ba2'
    _pack(archive, {key: value[:2] for key, value in files.items()},
          lambda _kept: _archive2(root / 'Textures', root, archive))
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
        for name in names:
            path = Path(top, name)
            out[path.relative_to(base).as_posix()] = path
    return out


def main_files(data_dir: Path) -> dict:
    """{archive name: path} of what `<plugin> - Main.ba2` holds: the staged sounds (sound_root) and the loose
    PACKED folders of `data_dir`."""
    named = _tree(sound_root(data_dir), SOUND)
    for folder in PACKED:
        named.update(_tree(Path(data_dir), folder))
    return named


def pack_main(data_dir: Path, plugin: str) -> int:
    """Pack main_files() as `<plugin stem> - Main.ba2` when they changed since it was packed, or delete that archive
    and its record when there are none (an earlier build's would ship stale files); the file count. Loose PACKED
    files stay for the build; the deploy ships the archive in their place.
    See: docs/fork/fo4_pipeline.md#main-archive
    """
    named, archive = main_files(data_dir), Path(data_dir) / f'{Path(plugin).stem} - Main.ba2'
    if named:
        stats = {name.lower(): path.stat() for name, path in named.items()}
        _pack(archive, {key: [st.st_size, st.st_mtime_ns] for key, st in stats.items()},
              lambda kept: write_general(named, archive, kept))
    for stale in () if named else (archive, archive.with_name(archive.name + '.json')):
        stale.unlink(missing_ok=True)
    return len(named)
