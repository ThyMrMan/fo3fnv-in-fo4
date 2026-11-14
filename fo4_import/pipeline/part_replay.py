"""Replay a built plugin's meshes and archives parts (build_plan.replay_parts: its only changes are code that ran
in those parts alone). The loose files come back; for the meshes part each mesh's pre-Elric bytes are held again
from the store and finished, the weapons dressed and object LOD baked as the build does, the copies a master
holds alike dropped and the finished-mesh record rewritten; then the FaceGen prune and the texture archive, the
Main archive, and the loose files out again. The inputs record then takes the code as it is now. A file the
records part read that the build made, changed since, or a pre-Elric mesh gone from the store, drops the record
instead: the plugin then needs a whole build.

    py -3.14 -m fo4_import.pipeline.part_replay <plugin>

See: docs/fork/fo4_plugin_layout.md#build-parts
See: docs/fork/fo4_plugin_layout.md#meshes-replay
"""

import argparse
import json
import sys
from pathlib import Path

from core.heavy_lock import hold_heavy_lock
from fo4_import.base.ba2_pack import drop_packed, pack_main, restore_packed
from fo4_import.pipeline import elric_cache, master_copies, object_lod, replay_manifest
from fo4_import.pipeline.build_inputs import inputs_path
from fo4_import.pipeline.build_plan import NEEDS_BUILD, record, replay_parts, same_file
from fo4_import.pipeline.code_identity import hashes
from fo4_import.pipeline.ran_code import ARCHIVES, MESHES
from fo4_import.pipeline.stage_timer import charged, report
from fo4_import.spike.build_finish import faces_and_textures, finish_meshes
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


def meshes(data_dir: Path, manifest: dict) -> 'dict | None':
    """The meshes part again from replay `manifest`: each mesh's pre-Elric bytes held (elric_cache.write_mesh) and
    finished, the weapons dressed (finish_meshes), object LOD baked; the counts, None when a pre-Elric mesh is gone
    from the store."""
    held = {path: elric_cache.kept_input(key) for path, key in manifest['pre_elric'].items()}
    if any(raw is None for raw in held.values()):
        return None
    for path, raw in held.items():
        elric_cache.write_mesh(Path(path), raw)
    failed = charged('collision', finish_meshes, data_dir, list(held), manifest['theirs'], manifest['weapons'],
                     part=MESHES)
    counts = dict(charged('object LOD', object_lod.bake_all, Path(manifest['export']), data_dir,
                          manifest['lod_worlds'], part=MESHES))
    return {**counts, 'meshes without collision (Elric failed)': len(failed)}


def after_meshes(plugin: Path, rec: dict, manifest: dict) -> dict:
    """The meshes part's records after it: the copies a master holds alike dropped, the finished-mesh record."""
    data = plugin.parent
    return {"files left to the master's folder": master_copies.drop_loose(data, master_dirs(rec, data)),
            'finished meshes recorded for dependent builds': master_copies.write_meshes(
                plugin, data, [Path(p) for p in manifest['finished']], elric_cache.MARKS)}


def needs_build(plugin: Path, why: str) -> int:
    """Drop `plugin`'s inputs record (the plan then builds it whole), saying `why`; NEEDS_BUILD."""
    print(f'{why}: {plugin.name} needs a whole build')
    inputs_path(plugin).unlink(missing_ok=True)
    return NEEDS_BUILD


def replay(plugin: Path) -> int:
    """Replay `plugin`'s parts (module doc) when replay_parts() names some (else nothing); 0, or NEEDS_BUILD."""
    parts = replay_parts(plugin)
    if not parts:
        print(f'{plugin.name}: not only code its meshes or archives parts ran changed; nothing replayed')
        return 0
    rec, data, manifest = record(plugin), plugin.parent, replay_manifest.read(plugin)
    print(f'== replaying {", ".join(sorted(parts))} of {plugin.name}')
    print(f'loose files restored from the Main archive: {restore_packed(data, plugin.name)}')
    counts = meshes(data, manifest) if MESHES in parts else {}
    if counts is None:
        return needs_build(plugin, 'a pre-Elric mesh is gone from the store')
    counts.update(charged('FaceGen and texture archive', faces_and_textures, data, plugin, master_dirs(rec, data),
                          npcs(plugin), False, part=ARCHIVES))
    counts.update(after_meshes(plugin, rec, manifest) if MESHES in parts else {})
    counts['files packed into the Main and voices archives'] = charged('main archive', pack_main, data, plugin.name,
                                                                      part=ARCHIVES)
    counts['loose files the archives hold, removed'] = drop_packed(data, plugin.name)
    print('\n'.join([f'{key}: {count}' for key, count in sorted(counts.items())] + report()))
    moved = moved_reads(rec)
    if moved:
        return needs_build(plugin, f'{len(moved)} files the records part read changed (first {moved[0]})')
    rec['code'] = hashes(rec['code'])
    inputs_path(plugin).write_text(json.dumps(rec, indent=0, sort_keys=True), encoding='utf-8')
    return 0


def main():
    """Replay the plugin named on the command line once any other heavy job has finished."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path, help='The built plugin (beside its stamp and inputs record)')
    args = ap.parse_args()
    hold_heavy_lock(' '.join(['fo4_import.pipeline.part_replay'] + sys.argv[1:]))
    sys.exit(replay(args.plugin))


if __name__ == '__main__':
    main()
