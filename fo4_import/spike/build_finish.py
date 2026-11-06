"""The end of a build, after every record is made: collision, voices and sounds, the archives, the records
written from everything made, the script compile, then the plugin, its ledger and the stale files pruned.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import collections
import struct
from pathlib import Path

from fo4_import.base.ba2_pack import pack_sounds, pack_textures, sound_root, stage_loose_sounds
from fo4_import.base.bink import write_movies
from fo4_import.base.dangling_scripts import clear_dangling
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.master_overrides import drop_unchanged
from fo4_import.nif import weapon
from fo4_import.pipeline import elric_cache, master_copies, mesh_cache, object_lod, stale_files
from fo4_import.pipeline.build_inputs import MASTERS, master_scripts
from fo4_import.pipeline.stage_timer import charged, timed
from fo4_import.rig import anim_info
from fo4_import.spike import ammo_casings, ammo_switch, companion_barks, facegen, list_adds, skeleton, voice
from fo4_import.spike.combat_feel import write_settings
from fo4_import.spike.imagespace import LUT_FOLDER
from fo4_import.spike.karma_page import write_karma_page
from fo4_import.spike.pipboy_tabs import remove_legacy_tabs
from fo4_import.spike.reputation import write_page
from fo4_import.spike.script import compile_into
from fo4_import.spike.script_packages import write_script_packages
from fo4_import.spike.sounds import FOLDER as SOUND_FOLDER

#: Voice recordings no built line uses, kept under the sound staging folder outside what is packed (voice-cache).
VOICE_CACHE = 'VoiceCache'
LIP_GENERATOR = FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator'
#: The record of voice jobs that failed (voice.convert_new), per plugin, under the sound staging root.
VOICE_FAILED = 'VoiceFailed'
#: The stamp of how a plugin's built lips were made (voice.relip_once), per plugin, under the sound staging root.
VOICE_LIPS = 'VoiceLips'


@timed('voice')
def _voice(builder, export_dir: Path, data_dir: Path, plugin: str) -> None:
    """The built lines' FNV recordings as .fuz under each NPC's converted voice type (voice_types), staged for
    the Main BA2 (sound_root); files in any other folder of the plugin's voice directory are stale."""
    voices = [(voice.fnv_folders(export_dir, fnv), fo4) for fo4, fnv in sorted(builder.npcs.voices.made.items())]
    builder.counts['loose sound files staged'] = stage_loose_sounds(data_dir, (f'Voice/{plugin}', f'FX/{SOUND_FOLDER}'))
    root, own = sound_root(data_dir), len(builder.writer.masters)
    todo = voice.jobs(voice.own_lines(builder.say.voiced, own), voices, root, plugin)
    todo += voice.silent_jobs(voice.own_lines(builder.say.silent, own), sorted({fo4 for _, fo4 in voices}), root,
                              plugin)
    ours, cache = root / 'Sound' / 'Voice' / plugin, root / VOICE_CACHE / plugin
    builder.counts['voice files kept aside'] = voice.remove_stale(todo, [p for p in ours.glob('*') if p.is_dir()],
                                                                  cache)
    builder.counts['voice files restored'] = voice.restore(todo, cache)
    builder.counts['voice lips redone'] = voice.relip_once(todo, root / VOICE_LIPS / f'{plugin}.txt')
    builder.counts['voice files written'] = voice.convert_new(todo, LIP_GENERATOR, root / VOICE_FAILED / f'{plugin}.json')


@timed('sounds')
def _sounds(builder, export_dir: Path, data_dir: Path, plugin: str) -> None:
    """Voices (_voice) and the sound records' files, packed into the plugin's Main BA2.
    See: docs/fork/fo4_pipeline.md#sound-archive
    """
    _voice(builder, export_dir, data_dir, plugin)
    masters = master_copies.master_dirs(builder)
    jobs = [job for job in dict.fromkeys(builder.sounds.jobs)
            if not master_copies.master_sound(job, export_dir, data_dir, masters)]
    builder.counts["sound files left to the master's archive"] = len(dict.fromkeys(builder.sounds.jobs)) - len(jobs)
    todo = [job for job in jobs if not job[1].exists()]
    builder.counts['sound files'] = voice.convert(todo, LIP_GENERATOR)
    builder.counts['sound files packed'] = pack_sounds(data_dir, plugin)


@timed('plugin write')
def _write_plugin(builder, out: Path, data_dir: Path) -> None:
    """Write the plugin to `out` (a dependent build's master records only where they change the master's:
    master_overrides), clear script properties naming no written record, then, when a written race names a
    graph of its own (anim_info.needed), have the Creation Kit write their animation data into `data_dir`."""
    builder.writer.next_object_id = builder.top
    if builder.built:
        adds = {}
        builder.counts.update(drop_unchanged(builder.writer, builder.built, builder.held, adds))
        builder.counts['master form list entries added at run time'] = list_adds.write(builder, adds)
    out.parent.mkdir(parents=True, exist_ok=True)
    builder.writer.write(str(out))
    for key, count in clear_dangling(out, len(builder.writer.masters)).items():
        builder.counts[f'script properties naming no written record ({key})'] = count
    if anim_info.needed((r for r in builder.writer.top_records() if r[:4] == b'RACE'), data_dir):
        builder.counts['own-rig animation data files (Creation Kit)'] = charged(
            'own-rig animation data (Creation Kit)', anim_info.generate, out, data_dir)


@timed('collision')
def _collision(builder, data_dir: Path) -> None:
    """Elric's collision for every written mesh, then the weapon meshes dressed; counted."""
    failed = elric_cache.finish([data_dir / 'Meshes' / model for model, _ in builder.meshes.values()])
    builder.counts['meshes without collision (Elric failed)'] = len(failed)
    builder.counts['mesh vertices with a UV clamped to the half-float range'] = sum(mesh_cache.CLAMPED.values())
    for model in sorted(builder.weapons):
        weapon.dress_file(data_dir / 'Meshes' / model)
    builder.counts['weapon meshes'] = len(builder.weapons)


@timed('object LOD')
def _object_lod(builder, export_dir: Path, data_dir: Path) -> None:
    """Built worldspaces' object LOD (after Elric, before the texture BA2)."""
    builder.counts.update(object_lod.bake_all(export_dir, data_dir, builder.object_lod.worlds))


@timed('assets')
def _assets(builder, export_dir: Path, data_dir: Path, out: Path) -> None:
    """Lowered skeletons, voices, sounds and movies, stale FaceGen pruned, the texture BA2; counted."""
    builder.counts['human skeletons lowered'] = skeleton.write(data_dir)
    _sounds(builder, export_dir, data_dir, out.name)
    builder.counts['movies written'] = write_movies(export_dir, data_dir)
    npcs = [struct.unpack_from('<I', rec, 12)[0] for rec in builder.writer.top_records() if rec[:4] == b'NPC_']
    builder.counts['stale FaceGen files removed'] = facegen.prune(out.name, data_dir, npcs)
    builder.counts['textures packed'] = pack_textures(data_dir, out.name, (LUT_FOLDER,))


@timed('script compile')
def _compile(builder, data_dir: Path, scripts_dir) -> None:
    """Compile the build's scripts (none without `scripts_dir`); the masters' scripts they name logged
    (build_inputs.master_scripts)."""
    if builder.scripts.used and scripts_dir is not None:
        masters = tuple(Path(scripts_dir).parent / p.name for p in builder.built)
        print(compile_into(scripts_dir, data_dir, builder.scripts.used, masters,
                           tuple(Path(p).parent / 'Scripts' for p in builder.built)))
        own = [Path(scripts_dir) / f'{name}.psc' for name in builder.scripts.used]
        for path in master_scripts(own, masters) if masters else ():
            MASTERS.script(path)


@timed('closing records')
def _closing_records(builder, export_dir: Path, data_dir: Path, out: Path, helper: int) -> None:
    """The records written from everything made: script packages, ammo, condition (helper plugin index
    `helper`), the Pip-Boy pages, challenges."""
    builder.counts['script packages'] = write_script_packages(builder)
    ammo_casings.write(builder, builder.equipment.ammo_mods.loaded)
    ammo_switch.write(builder, builder.equipment.ammo_mods)
    builder.equipment.condition.write(builder.equipment.ammo_mods, data_dir, helper)
    write_karma_page(builder, export_dir, builder.reputation_slots)
    write_page(builder)
    builder.challenges.write()
    builder.region_watch.write()
    companion_barks.write(builder)
    builder.counts['Pip-Boy Tabs files removed'] = len(remove_legacy_tabs(data_dir, out.name))
    if builder.built:
        builder.scripts.used += [list_adds.SCRIPT]


@timed('closing records')
def _lists(builder, data_dir: Path) -> None:
    """Weapon and item type lists and the gun race, ammo, poisons, idles, combat settings."""
    builder.equipment.write_anim_lists()
    builder.items.write_type_lists()
    builder.consumables.write_ammo()
    builder.consumables.poisons.write()
    builder.idles.write(data_dir)
    builder.combat.write()
    write_settings(builder, builder.combat.settings)


@timed('ledger and cleanup')
def finish(builder, export_dir: Path, data_dir: Path, out: Path, scripts_dir, helper: int) -> collections.Counter:
    """Collision, object LOD, assets, the records written from everything made, scripts, then the plugin, its
    ledger and the stale files pruned; `builder`'s counts (`helper`: the helper plugin's master index)."""
    _collision(builder, data_dir)
    _object_lod(builder, export_dir, data_dir)
    _assets(builder, export_dir, data_dir, out)
    _closing_records(builder, export_dir, data_dir, out, helper)
    _compile(builder, data_dir, scripts_dir)
    _lists(builder, data_dir)
    _write_plugin(builder, out, data_dir)
    builder.writer.ledger.save()
    builder.counts["files left to the master's folder"] = master_copies.drop_loose(data_dir,
                                                                                    master_copies.master_dirs(builder))
    made = stale_files.made(data_dir, Path(export_dir.name).stem, builder.started, bool(builder.built))
    builder.counts['stale meshes, materials and clips removed'] = len(stale_files.prune(out, data_dir, made))
    builder.counts['cache entries pruned (unused 14 days)'] = elric_cache.prune_caches(days=14)
    print(f'readiness entries: {builder.readiness.write(out.name)}')
    return builder.counts
