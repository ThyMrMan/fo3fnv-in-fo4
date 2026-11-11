"""What a dependent build (an FNV DLC on the built game plugin) would ship that its master's build already ships.

A DLC build remakes the game's meshes, materials, clips, animation data, textures and sounds its records reach.
The master's mod already carries them, so the DLC's folder keeps only what differs: loose files byte-identical
to the master folder's same path are dropped once the build is done (drop_loose), textures whose master staged
them with the same signature are never staged (ba2_pack.share_masters), and sounds from the master's export
that the master converted are not converted (master_sound). A master's meshes ship in its archive, where
drop_loose cannot see them, so each build records how it finished its meshes beside its plugin, and a
dependent build does not write or finish a mesh its master finished the same way (theirs).

See: docs/fork/fo4_plugin_layout.md#dlc-build
"""

import concurrent.futures
import functools
import json
import os
from pathlib import Path

from fo4_import.base.ba2_pack import share_masters, sound_root
from fo4_import.base.file_stamps import files_under

#: Beside a plugin: {mesh path: [elric_cache.mark(), collision ok]} of each mesh it ships as Elric finished it.
MESHES_SUFFIX = '.meshes.json'
#: Threads drop_loose compares files in: it waits on opening and reading them, not on the CPU.
DROP_THREADS = 16


def master_dirs(builder) -> list:
    """The data folders of `builder`'s built masters, but its own data folder."""
    own = os.path.normcase(os.path.abspath(builder.data_dir))
    dirs = dict.fromkeys(Path(p).parent for p in builder.built)
    return [d for d in dirs if os.path.normcase(os.path.abspath(d)) != own]


def share(builder) -> None:
    """Have texture staging skip what `builder`'s masters staged alike."""
    share_masters(builder.data_dir, master_dirs(builder))


def _same(path: Path, other: Path) -> bool:
    """Whether `other` is a file holding exactly `path`'s bytes."""
    return other.is_file() and other.stat().st_size == path.stat().st_size and other.read_bytes() == path.read_bytes()


def drop_loose(data_dir: Path, masters: list) -> int:
    """Delete each file in `data_dir`'s folders (not its top-level plugin files) that a master folder holds with
    the same bytes at the same path, compared in DROP_THREADS threads; how many.
    See: docs/fork/fo4_build_speed.md#fixed
    """
    if not masters:
        return 0
    top = os.path.normcase(os.path.abspath(data_dir))
    files = [Path(e.path) for e in files_under(data_dir)
             if os.path.normcase(os.path.abspath(os.path.dirname(e.path))) != top]
    with concurrent.futures.ThreadPoolExecutor(max_workers=DROP_THREADS) as threads:
        return sum(threads.map(functools.partial(_drop, data_dir=data_dir, masters=masters), files))


def _drop(path: Path, data_dir: Path, masters: list) -> bool:
    """Delete `path` when a master folder holds its bytes at its place under `data_dir`; whether it did."""
    rel = path.relative_to(data_dir)
    if not any(_same(path, m / rel) for m in masters):
        return False
    path.unlink()
    return True


def _meshes_file(plugin) -> Path:
    """`plugin`'s record of its finished meshes (MESHES_SUFFIX)."""
    return Path(plugin).with_name(Path(plugin).name + MESHES_SUFFIX)


def _rel(path, data_dir) -> str:
    """`path` under `data_dir`, '/'-separated, lower case."""
    return os.path.relpath(path, data_dir).replace('\\', '/').lower()


def theirs(builder, paths: list) -> dict:
    """{normcased path of `paths`: [mark, ok]} of each mesh a built master in another folder ships finished the same
    way (its MESHES_SUFFIX record, the last master's winning); none unless every such master has a record.
    See: docs/fork/fo4_build_speed.md#fixed
    """
    dirs = {os.path.normcase(os.path.abspath(d)) for d in master_dirs(builder)}
    records = [_meshes_file(p) for p in builder.built if os.path.normcase(os.path.abspath(Path(p).parent)) in dirs]
    if not records or not all(r.is_file() for r in records):
        return {}
    shipped = {}
    for record in records:
        shipped.update(json.loads(record.read_text(encoding='utf-8')))
    return {os.path.normcase(str(p)): shipped[r] for p in paths if (r := _rel(p, builder.data_dir)) in shipped}


def write_meshes(plugin: Path, data_dir: Path, paths: list, marks: dict) -> int:
    """Write `plugin`'s MESHES_SUFFIX record: each of `paths` (finished, not changed after) still in `data_dir`
    that `marks` ({normcased path: [mark, ok]}) names; how many."""
    rows = {_rel(p, data_dir): marks[k] for p in paths
            if (k := os.path.normcase(str(p))) in marks and marks[k][0] and Path(p).is_file()}
    _meshes_file(plugin).write_text(json.dumps(rows, sort_keys=True), encoding='utf-8')
    return len(rows)


def master_sound(job: tuple, export_dir: Path, data_dir: Path, masters: list) -> bool:
    """Whether sound job (source, target, text) converts a master export's file the master already converted;
    such a job's old copy in `data_dir`'s sound staging is deleted; a job writing outside the staging (music,
    loose) is not one."""
    source, target = Path(job[0]), Path(job[1]).resolve()
    root = sound_root(data_dir).resolve()
    if not masters or source.is_relative_to(export_dir) or not target.is_relative_to(root):
        return False
    rel = target.relative_to(root)
    if not any((sound_root(m) / rel).is_file() for m in masters):
        return False
    target.unlink(missing_ok=True)
    return True
