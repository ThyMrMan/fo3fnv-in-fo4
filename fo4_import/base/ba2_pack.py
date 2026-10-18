"""Pack a Data folder's loose textures into the plugin's texture BA2 with the CK's Archive2.

Fallout 4 streams a texture's mips from a BA2's chunks; a loose DDS can stay
on a low mip, and past iTextureDegradeDistance the game drops a texture's top
chunk (a 512 FNV texture to 256). Each texture is one chunk, as some vanilla
ones are, so it always shows in full, as in FNV. Loose files under
<data>/Textures move into <data>/_ba2/Textures (a folder the game does not
read), and all of it becomes `<plugin> - Textures.ba2`, loaded with the
plugin. Folders the archiver cannot take (uncompressed one-mip LUTs, which
vanilla keeps in a general archive) stay loose. A build writes its textures
through stage_texture(): once per run, and not at all while the staged copy
is current; pack_textures() then drops staged OWN textures the build neither
wrote nor confirmed, and repacks only a changed staging folder.

See: docs/fork/fo4_spikes.md#spike-4-exterior
See: docs/fork/fo4_tool_audit.md#rebuild
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR

ARCHIVE2 = FALLOUT4_DIR / 'Tools' / 'Archive2' / 'Archive2.exe'
#: Folder under the Data folder holding every texture packed so far.
STAGING = '_ba2'
#: Chunks per texture: one, so the game has no top mips to drop with distance.
CHUNKS = 1
#: The staging folder's record of its files at the last pack: {texture key: [size, mtime_ns, signature or None]}.
MANIFEST = 'manifest.json'
#: Texture keys (lowercase, under Textures) a build writes itself; only these are pruned (FaceGen is not).
OWN = 'fnv/'
#: Per resolved Data folder, this run's {'manifest': the last pack's record, 'staged': {key: signature}}.
_RUNS = {}


def texture_key(rel: str) -> str:
    """Texture path `rel` (under Textures) as a key: lowercase, forward slashes."""
    return rel.replace('\\', '/').lower()


def _run_key(data_dir: Path) -> str:
    """`data_dir` as a _RUNS key."""
    return os.path.normcase(os.path.abspath(data_dir))


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
        _RUNS[key] = {'manifest': _read_json(Path(data_dir) / STAGING / MANIFEST), 'staged': {}}
    return _RUNS[key]


def _current(staged: Path, recorded, signature: str) -> bool:
    """Whether `staged` is unchanged since the last pack recorded it as `recorded` with `signature`."""
    if not recorded or recorded[2] != signature:
        return False
    try:
        stat = staged.stat()
    except OSError:
        return False
    return [stat.st_size, stat.st_mtime_ns] == recorded[:2]


def stage_texture(data_dir: Path, rel: str, plan) -> bool:
    """Write texture `rel` (under <data_dir>/Textures) once per run, unless the last pack staged it with the same
    signature and it is unchanged since; whether it was written. plan() is (signature, write(target)): the
    signature names everything the file is made from (a copy's source, size and time; a derived map's work-cache
    key). Paths name contents (convert_static), so a second call this run is skipped unplanned."""
    run, key = _run(data_dir), texture_key(rel)
    if key in run['staged']:
        return False
    signature, write = plan()
    run['staged'][key] = signature
    target = Path(data_dir) / 'Textures' / rel.replace('\\', '/')
    if not target.exists() and _current(Path(data_dir) / STAGING / 'Textures' / key, run['manifest'].get(key),
                                        signature):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    write(target)
    return True


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


def _pack(staged: Path, root: Path, archive: Path, files: dict) -> None:
    """Pack `staged` as `archive` with Archive2 unless the record beside it shows the same `files` packed."""
    state = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
    record = archive.with_name(archive.name + '.json')
    packed = _read_json(record)
    stat = archive.stat() if archive.exists() else None
    if stat and packed.get('files') == state and packed.get('archive') == [stat.st_size, stat.st_mtime_ns]:
        return
    subprocess.run([str(ARCHIVE2), str(staged), f'-c={archive}', '-f=DDS', f'-r={root}', f'-maxChunkCount={CHUNKS}',
                    '-q'], check=True, capture_output=True, **POPEN_FLAGS)
    stat = archive.stat()
    record.write_text(json.dumps({'files': state, 'archive': [stat.st_size, stat.st_mtime_ns]}), encoding='utf-8')


def pack_textures(data_dir: Path, plugin: str, keep_loose: tuple = ()) -> int:
    """Stage <data_dir>/Textures (but `keep_loose` folders), drop staged OWN textures this run neither wrote nor
    confirmed (stage_texture), and pack the staging as `<plugin stem> - Textures.ba2` when it changed since that
    archive was packed; the staged file count."""
    root = data_dir / STAGING
    run = _RUNS.pop(_run_key(data_dir), None) or {'manifest': _read_json(root / MANIFEST), 'staged': {}}
    moved = _move_loose(data_dir / 'Textures', root / 'Textures', keep_loose)
    paths = _staged_files(root / 'Textures', moved | set(run['staged']))
    files = {}
    for key, path in paths.items():
        stat = path.stat()
        files[key] = [stat.st_size, stat.st_mtime_ns, run['staged'].get(key)]
    _pack(root / 'Textures', root, data_dir / f'{Path(plugin).stem} - Textures.ba2',
          {key: value[:2] for key, value in files.items()})
    (root / MANIFEST).write_text(json.dumps(files, sort_keys=True), encoding='utf-8')
    return len(files)
