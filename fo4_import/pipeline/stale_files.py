"""Meshes, materials and idle clips a plugin's build no longer makes, removed from the data folder.

Every writer under roots() (ROOTS, plus DLC_ROOTS in a DLC's own data
folder) rewrites its file or, when it already holds those bytes, touches it
(elric_cache.write_new), so the files there dated from the
build's start on are what this build made. They are listed beside the plugin
(`<plugin>.files.txt`, in the build records: build_files). The next build of that plugin deletes what its last
list named and its new one does not, unless another plugin's list in the
same folder names it (two plugins' builds share these folders). With no
earlier list nothing is deleted. FaceGen and voice files have their own
pruning (facegen.prune, voice.remove_stale).

See: docs/fork/fo4_pipeline.md#stale-files
"""

from pathlib import Path

from fo4_import.base.build_files import all_moved_in, moved_in
from fo4_import.base.file_stamps import files_under

#: Data-folder folders only this converter writes: meshes, materials, and a plugin's idle clips ({clips}).
ROOTS = ('Meshes/fnv', 'Materials/fnv', 'Meshes/Actors/Character/Animations/{clips}')
#: More folders a DLC build (its own data folder) rewrites every build: rigs, LOD, loose textures.
DLC_ROOTS = ('Meshes/Actors', 'Meshes/Terrain', 'Textures/Terrain', 'Textures/fnv', 'Textures/Effects', 'LODSettings')
#: A plugin's file list's suffix, beside the plugin.
LIST_SUFFIX = '.files.txt'
#: Seconds of slack for file times against the build's start.
SLACK = 2.0


def roots(clips: str, dlc: bool) -> tuple:
    """A build's listed folders: ROOTS (clip folder `clips`), and DLC_ROOTS if `dlc`.
    See: docs/fork/fo4_pipeline.md#stale-files
    """
    return tuple(r.format(clips=clips) for r in ROOTS) + (DLC_ROOTS if dlc else ())


def list_path(plugin: Path) -> Path:
    """`plugin`'s file list, in the build records beside it (build_files)."""
    return moved_in(plugin.with_name(plugin.name + LIST_SUFFIX))


def list_paths(folder: Path) -> list:
    """The file lists of every plugin in `folder`."""
    return all_moved_in(folder, '*' + LIST_SUFFIX)


def listed(plugin: Path) -> set:
    """The paths `plugin`'s file list names (empty when it has none)."""
    return _listed(list_path(plugin))


def made(data_dir: Path, clips: str, started: float, dlc: bool = False) -> set:
    """Paths (relative to `data_dir`, '/'-separated) under roots() dated from `started` on."""
    out, base = set(), len(str(data_dir)) + 1
    for root in roots(clips, dlc):
        folder = data_dir / root
        files = files_under(folder) if folder.is_dir() else ()
        out |= {f.path[base:].replace('\\', '/') for f in files if f.stat().st_mtime >= started - SLACK}
    return out


def _listed(path: Path) -> set:
    """The paths a file list names."""
    return set(path.read_text(encoding='utf-8').splitlines()) if path.is_file() else set()


def prune(plugin: Path, data_dir: Path, current: set) -> list:
    """Delete what `plugin`'s last list named and `current` does not (unless another list names it), then save
    `current` as its list; the paths removed, sorted."""
    own = list_path(plugin)
    others = set().union(*(_listed(p) for p in list_paths(plugin.parent) if p != own))
    removed = []
    for rel in sorted(_listed(own) - current - others):
        try:
            (data_dir / rel).unlink(missing_ok=True)
        except OSError:
            continue
        removed.append(rel)
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_text(''.join(f'{rel}\n' for rel in sorted(current)), encoding='utf-8')
    return removed
