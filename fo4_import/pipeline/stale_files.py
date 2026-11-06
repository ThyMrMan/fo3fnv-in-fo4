"""Meshes, materials and idle clips a plugin's build no longer makes, removed from the data folder.

Every writer under roots() (ROOTS, plus DLC_ROOTS in a DLC's own data
folder) rewrites its file or, when it already holds those bytes, touches it
(elric_cache.write_new), so the files there dated from the
build's start on are what this build made. They are listed beside the plugin
(`<plugin>.files.txt`). The next build of that plugin deletes what its last
list named and its new one does not, unless another plugin's list in the
same folder names it (two plugins' builds share these folders). With no
earlier list nothing is deleted. FaceGen and voice files have their own
pruning (facegen.prune, voice.remove_stale).

See: docs/fork/fo4_pipeline.md#stale-files
"""

from pathlib import Path

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


def listed(plugin: Path) -> set:
    """The paths `plugin`'s file list names (empty when it has none)."""
    return _listed(plugin.with_name(plugin.name + LIST_SUFFIX))


def made(data_dir: Path, clips: str, started: float, dlc: bool = False) -> set:
    """Paths (relative to `data_dir`, '/'-separated) under roots() dated from `started` on."""
    out = set()
    for root in roots(clips, dlc):
        folder = data_dir / root
        files = (p for p in folder.rglob('*') if p.is_file()) if folder.is_dir() else ()
        out |= {p.relative_to(data_dir).as_posix() for p in files if p.stat().st_mtime >= started - SLACK}
    return out


def _listed(path: Path) -> set:
    """The paths a file list names."""
    return set(path.read_text(encoding='utf-8').splitlines()) if path.is_file() else set()


def prune(plugin: Path, data_dir: Path, current: set) -> list:
    """Delete what `plugin`'s last list named and `current` does not (unless another list names it), then save
    `current` as its list; the paths removed, sorted."""
    own = plugin.with_name(plugin.name + LIST_SUFFIX)
    others = set().union(*(_listed(p) for p in plugin.parent.glob('*' + LIST_SUFFIX) if p != own))
    removed = []
    for rel in sorted(_listed(own) - current - others):
        try:
            (data_dir / rel).unlink(missing_ok=True)
        except OSError:
            continue
        removed.append(rel)
    own.write_text(''.join(f'{rel}\n' for rel in sorted(current)), encoding='utf-8')
    return removed
