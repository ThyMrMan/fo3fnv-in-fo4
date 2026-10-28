"""AnimTextData for a plugin's own-rig creatures, from the Creation Kit's -GenerateAnimInfo.

The CK writes the binary files the game reads for a race's graphs (animation offsets, speed info, stance data,
clip generator data, event info, file data, dynamic idle data and the persistent subgraph list); the converter
does not write those formats. The step runs after the plugin is written: last run's files (listed beside the
plugin) are deleted so the CK writes them all as new files, which MO2 puts in its CK output folder; those dated
from the run's start move into the mod folder, and their list is saved.

See: docs/fork/fo4_own_rig.md#anim-info
"""

import shutil
import time
from pathlib import Path

from fo4_import.pipeline import creation_kit

#: The CK's arguments: the plugin, its data and output folders (MO2's virtual Data), speed and stance data too.
ARGUMENTS = '-GenerateAnimInfo:{plugin} Data Data --speed --stance'
#: The folder the CK writes, under the data folder.
ANIM_TEXT = Path('Meshes') / 'AnimTextData'
#: The list of files the last run collected, beside the plugin.
LIST_SUFFIX = '.animinfo.txt'
#: Seconds to allow the CK: a bound, not an estimate (loading the Spike profile for a test plugin took 15 minutes).
CK_TIMEOUT = 7200
#: Seconds of slack for file times against the run's start.
SLACK = 2.0
#: An entry's dynamic idle data when it has no dynamic idles: vanilla's text.
DYNAMIC_IDLE = b'Version 1\n'


def generate(plugin: Path, data_dir: Path) -> int:
    """Run the CK's AnimInfo export for `plugin` (in mod folder `data_dir`) and move its files into `data_dir`;
    how many files."""
    listed = plugin.with_name(plugin.name + LIST_SUFFIX)
    for rel in listed.read_text(encoding='utf-8').splitlines() if listed.is_file() else ():
        (data_dir / rel).unlink(missing_ok=True)
    started = time.time()
    creation_kit.run(ARGUMENTS.format(plugin=plugin.name), CK_TIMEOUT, f'generating animation data for {plugin.name}')
    source = creation_kit.output_dir()
    moved = []
    for path in sorted((source / ANIM_TEXT).rglob('*')) if (source / ANIM_TEXT).is_dir() else ():
        if path.is_file() and path.stat().st_mtime >= started - SLACK:
            rel = path.relative_to(source)
            (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(data_dir / rel))
            moved.append(rel.as_posix())
    moved += dynamic_idles(data_dir, moved)
    listed.write_text(''.join(f'{rel}\n' for rel in moved), encoding='utf-8')
    return len(moved)


def dynamic_idles(data_dir: Path, moved: list) -> list:
    """A `Version 1` DynamicIdleData file for each entry the CK wrote offsets for (every vanilla entry has one;
    the CK writes none); their paths."""
    ids = {Path(rel).stem for rel in moved if Path(rel).parent.name == 'AnimationOffsets' and Path(rel).stem.isdigit()}
    out = []
    for entry in sorted(ids):
        rel = ANIM_TEXT / 'DynamicIdleData' / f'{entry}.txt'
        (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (data_dir / rel).write_bytes(DYNAMIC_IDLE)
        out.append(rel.as_posix())
    return out
