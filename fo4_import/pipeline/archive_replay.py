"""Replay a built plugin's archives part (build_plan: its only changes are code that ran there alone): the loose
files back, the FaceGen prune and the texture archive, the Main archive, the loose files out again; then the
inputs record takes the code as it is now. A file the records part read that the build made, changed since,
drops the record instead: the plugin then needs a whole build.

    py -3.14 -m fo4_import.pipeline.archive_replay <plugin>

See: docs/fork/fo4_plugin_layout.md#build-parts
"""

import argparse
import json
import sys
from pathlib import Path

from core.heavy_lock import hold_heavy_lock
from fo4_import.base.ba2_pack import drop_packed, pack_main, restore_packed
from fo4_import.pipeline.build_inputs import inputs_path
from fo4_import.pipeline.build_plan import NEEDS_BUILD, record, replayable, same_file
from fo4_import.pipeline.code_identity import hashes
from fo4_import.pipeline.ran_code import ARCHIVES
from fo4_import.pipeline.stage_timer import charged, report
from fo4_import.spike.build_finish import faces_and_textures
from tes5_import.base.tes5_reader import walk


def master_dirs(rec: dict, data_dir: Path) -> list:
    """The folders of the built masters inputs record `rec` read, but `data_dir`."""
    dirs = dict.fromkeys(Path(p).parent for p in rec['masters']['paths'].get('plugin', []))
    return [d for d in dirs if d.resolve() != data_dir.resolve()]


def npcs(plugin: Path) -> list:
    """The FormIDs of `plugin`'s NPC_ records."""
    return [rec.form_id for rec, _ in walk(plugin.read_bytes(), b'NPC_')]


def moved_reads(rec: dict) -> list:
    """The made_reads files (records read, the build made) no longer as kept."""
    return [path for path, kept in rec.get('made_reads', {}).items() if not same_file(path, kept)]


def replay(plugin: Path) -> int:
    """Replay `plugin`'s archives part (module doc) when replayable() (else nothing); 0, or NEEDS_BUILD when a made
    file the records read moved."""
    if not replayable(plugin):
        print(f'{plugin.name}: not only code its archives part ran changed; nothing replayed')
        return 0
    rec, data = record(plugin), plugin.parent
    print(f'loose files restored from the Main archive: {restore_packed(data, plugin.name)}')
    counts = charged('FaceGen and texture archive', faces_and_textures, data, plugin, master_dirs(rec, data),
                     npcs(plugin), False, part=ARCHIVES)
    counts['files packed into the Main and voices archives'] = charged('main archive', pack_main, data, plugin.name,
                                                                      part=ARCHIVES)
    counts['loose files the archives hold, removed'] = drop_packed(data, plugin.name)
    for key, count in sorted(counts.items()):
        print(f'{key}: {count}')
    print('\n'.join(report()))
    moved = moved_reads(rec)
    if moved:
        print(f'{len(moved)} files the records part read changed (first {moved[0]}): the plugin needs a whole build')
        inputs_path(plugin).unlink()
        return NEEDS_BUILD
    rec['code'] = hashes(rec['code'])
    inputs_path(plugin).write_text(json.dumps(rec, indent=0, sort_keys=True), encoding='utf-8')
    return 0


def main():
    """Replay the plugin named on the command line once any other heavy job has finished."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path, help='The built plugin (beside its stamp and inputs record)')
    args = ap.parse_args()
    hold_heavy_lock(' '.join(['fo4_import.pipeline.archive_replay'] + sys.argv[1:]))
    sys.exit(replay(args.plugin))


if __name__ == '__main__':
    main()
