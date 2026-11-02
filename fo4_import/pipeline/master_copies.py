"""What a dependent build (an FNV DLC on the built game plugin) would ship that its master's build already ships.

A DLC build remakes the game's meshes, materials, clips, animation data, textures and sounds its records reach.
The master's mod already carries them, so the DLC's folder keeps only what differs: loose files byte-identical
to the master folder's same path are dropped once the build is done (drop_loose), textures whose master staged
them with the same signature are never staged (ba2_pack.share_masters), and sounds from the master's export
that the master converted are not converted (master_sound).

See: docs/fork/fo4_plugin_layout.md#dlc-build
"""

import os
from pathlib import Path

from fo4_import.base.ba2_pack import share_masters, sound_root


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
    the same bytes at the same path; how many."""
    dropped = 0
    for top, _dirs, names in os.walk(data_dir) if masters else ():
        if Path(top) == Path(data_dir):
            continue
        for name in names:
            path = Path(top, name)
            rel = path.relative_to(data_dir)
            if any(_same(path, m / rel) for m in masters):
                path.unlink()
                dropped += 1
    return dropped


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
