"""AnimTextData for a plugin's own-rig creatures, from the Creation Kit's -GenerateAnimInfo.

The CK writes the binary files the game reads for a race's graphs (animation offsets, speed info, stance data,
clip generator data, event info, file data, dynamic idle data and the persistent subgraph list); the converter
does not write those formats. The step runs after the plugin is written, when its inputs changed: the CK sees
MO2's Data, the deployed mod included, and writes only files that change, so the files dated from the run's start
are collected (new ones MO2 put in its CK output folder moved into the build's folder, ones it edited in place in
an enabled mod copied) and added to last run's list, beside the plugin.

See: docs/fork/fo4_own_rig.md#anim-info
"""

import hashlib
import shutil
import struct
import time
from pathlib import Path

from fo4_import.base.build_files import moved_in
from fo4_import.pipeline import creation_kit
from tes5_import.base.tes5_reader import subrecords, walk

#: The CK's arguments: the plugin, its data and output folders (MO2's virtual Data), speed and stance data too.
ARGUMENTS = '-GenerateAnimInfo:{plugin} Data Data --speed --stance'
#: The folder the CK writes, under the data folder.
ANIM_TEXT = Path('Meshes') / 'AnimTextData'
#: The list of files the last run collected, and the hash of its inputs (inputs_key), beside the plugin.
LIST_SUFFIX, KEY_SUFFIX = '.animinfo.txt', '.animinfo.key'
#: A packed FO4 record's header size, before its subrecords (uncompressed records: the build writes no others).
HEADER_SIZE = 24
#: The plugin records the export reads: races (their graphs and subgraph entries), idles, movement, keywords, actions.
READ_TYPES = (b'RACE', b'IDLE', b'MOVT', b'KYWD', b'AACT')
#: Seconds to allow the CK: a bound, not an estimate (loading the Spike profile for a test plugin took 15 minutes).
CK_TIMEOUT = 7200
#: Seconds of slack for file times against the run's start.
SLACK = 2.0
#: An entry's dynamic idle data when it has no dynamic idles: vanilla's text.
DYNAMIC_IDLE = b'Version 1\n'


def needed(races, data_dir: Path) -> bool:
    """Whether a race in `races` (packed) names a graph (SGNM) in `data_dir`."""
    return any((data_dir / 'Meshes' / body.rstrip(b'\0').decode('cp1252')).is_file()
               for rec in races for sig, body in subrecords(rec[HEADER_SIZE:]) if sig == b'SGNM')


def inputs_key(plugin: Path, data_dir: Path) -> str:
    """What the CK's AnimInfo export reads, one `name<TAB>sha1` line each: its arguments, the plugin's
    READ_TYPES records (each record its own line) and every file under the data folder's Meshes/Actors.
    See: docs/fork/fo4_own_rig.md#anim-info
    """
    lines = [f'arguments\t{hashlib.sha1(ARGUMENTS.encode()).hexdigest()}']
    for rec, _ in walk(plugin.read_bytes(), *READ_TYPES):
        body = struct.pack('<I', rec.flags) + rec.body
        lines.append(f'{rec.sig.decode()} {rec.form_id:08X}\t{hashlib.sha1(body).hexdigest()}')
    actors = data_dir / 'Meshes' / 'Actors'
    for path in actors.rglob('*') if actors.is_dir() else ():
        if path.is_file():
            lines.append(f'{path.relative_to(actors).as_posix().lower()}\t{hashlib.sha1(path.read_bytes()).hexdigest()}')
    return '\n'.join(sorted(lines)) + '\n'


def changed(old: str, new: str) -> list:
    """The inputs added, removed or changed between two inputs_key values."""
    before, after = (dict(line.split('\t') for line in key.splitlines() if '\t' in line) for key in (old, new))
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def _restore(data_dir: Path, rels: list) -> list:
    """Copy each of `rels` missing from `data_dir` back from the MO2 folder holding it (creation_kit.holding: the
    deployed mod); the ones still missing."""
    missing = []
    for rel in rels:
        target, held = data_dir / rel, None if (data_dir / rel).is_file() else creation_kit.holding(Path(rel))
        if held is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(held, target)
        missing += [rel] if not target.is_file() else []
    return missing


def _collect(data_dir: Path, since: float) -> list:
    """The AnimTextData files the CK wrote from `since` on, into `data_dir`: moved out of MO2's output folder, copied
    from a mod it edited in place; their Data paths."""
    out = []
    for path, rel, new in creation_kit.written_since(ANIM_TEXT, since):
        (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        if new:
            shutil.move(str(path), str(data_dir / rel))
        elif path.resolve() != (data_dir / rel).resolve():
            shutil.copy2(path, data_dir / rel)
        out.append(rel.as_posix())
    return out


def generate(plugin: Path, data_dir: Path) -> int:
    """The CK's AnimInfo export for `plugin` in `data_dir`, run only when its inputs (inputs_key) changed or a
    listed file is found nowhere; how many files. The CK sees MO2's Data (the deployed mod), not `data_dir`, and
    writes only what changed, so the list keeps last run's files and adds this run's (_collect); a listed file
    missing here is copied back from MO2 (_restore).
    See: docs/fork/fo4_own_rig.md#anim-info
    """
    listed, key_file = (moved_in(plugin.with_name(plugin.name + s)) for s in (LIST_SUFFIX, KEY_SUFFIX))
    key = inputs_key(plugin, data_dir)
    last = listed.read_text(encoding='utf-8').splitlines() if listed.is_file() else []
    old = key_file.read_text(encoding='utf-8') if key_file.is_file() else ''
    missing = _restore(data_dir, last)
    if last and old == key and not missing:
        return len(last)
    print(f'animation data: {len(changed(old, key))} inputs changed {changed(old, key)[:8]}, '
          f'{len(missing)} of {len(last)} files missing {missing[:3]}')
    key_file.unlink(missing_ok=True)
    started = time.time()
    creation_kit.run(ARGUMENTS.format(plugin=plugin.name), CK_TIMEOUT, f'generating animation data for {plugin.name}')
    made = list(dict.fromkeys([r for r in last if (data_dir / r).is_file()] + _collect(data_dir, started - SLACK)))
    made += [r for r in dynamic_idles(data_dir, made) if r not in made]
    listed.parent.mkdir(parents=True, exist_ok=True)
    listed.write_text(''.join(f'{rel}\n' for rel in made), encoding='utf-8')
    key_file.write_text(key, encoding='utf-8')
    return len(made)


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
