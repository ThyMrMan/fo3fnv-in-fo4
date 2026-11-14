"""A build's replay manifest, kept beside the plugin: what its meshes part took from the records part (each mesh's
pre-Elric SHA-1, the master's finished-alike marks, the weapons, the object LOD worlds, the finished list and the
export), so part_replay can run that part again without the records.

See: docs/fork/fo4_plugin_layout.md#meshes-replay
"""

import json
from pathlib import Path

from fo4_import.base.build_files import moved_in

SUFFIX = '.replay.json'


def manifest_path(plugin: Path) -> Path:
    """`plugin`'s replay manifest, in the build records beside it."""
    return moved_in(Path(plugin).with_name(Path(plugin).name + SUFFIX))


def write(plugin: Path, body: dict) -> None:
    """Keep `body` as `plugin`'s replay manifest."""
    path = manifest_path(plugin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True), encoding='utf-8')


def read(plugin: Path) -> 'dict | None':
    """`plugin`'s replay manifest; None without one."""
    try:
        return json.loads(manifest_path(plugin).read_text(encoding='utf-8'))
    except OSError:
        return None
