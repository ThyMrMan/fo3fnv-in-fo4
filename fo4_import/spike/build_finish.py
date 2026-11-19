"""The end of a build, after every record is made: collision, voices and sounds, the archives, the records
written from everything made, the script compile, then the plugin, its ledger and the stale files pruned.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import collections
import struct
from pathlib import Path

from fo4_import import cleanroom
from fo4_import import dialogue_menu as menu_links
from fo4_import import level_up as level_up_menu, pipboy_overlay
from fo4_import.base import translations
from fo4_import.classic_look import CLASSIC_FOLDER
from fo4_import.base.ba2_pack import pack_main, pack_textures, sound_root, stage_loose_sounds
from fo4_import.base.bink import write_movies
from fo4_import.base.dangling_scripts import clear_dangling
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.master_overrides import drop_unchanged
from fo4_import.base.source import plugin_stem
from fo4_import.base.ba2 import GAME_ARCHIVES, Archives
from fo4_import.base.build_files import moved_in
from fo4_import.havok import anim_text, anim_text_skip, gun_anim_text
from fo4_import.nif import weapon
from fo4_import.pipeline import elric_cache, master_copies, mesh_cache, object_lod, replay_manifest, stale_files
from fo4_import.pipeline.build_inputs import MASTERS, master_scripts
from fo4_import.pipeline.light_choice import finish_flag
from fo4_import.pipeline.ran_code import ARCHIVES, MESHES, SCRIPTS
from fo4_import.pipeline.stage_timer import timed
from fo4_import.spike import (ammo_casings, ammo_switch, companion_barks, facegen, level_up_icons, list_adds,
                               script_overrides, script_view, skeleton, voice)
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
#: The kinds an entry playing clips of its own copies from its template: its offsets are written (entry_files).
TEMPLATE_KINDS = ('AnimationSpeedInfo', 'AnimationStanceData', 'DynamicIdleData')
#: The file list and input key the Creation Kit stage kept beside the plugin (older builds), now removed.
ANIM_INFO_LISTS = ('.animinfo.txt', '.animinfo.key')


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
    """Voices (_voice) and the sound records' files, staged for the plugin's Main BA2 (_main_archive).
    See: docs/fork/fo4_pipeline.md#sound-archive
    """
    _voice(builder, export_dir, data_dir, plugin)
    masters = master_copies.master_dirs(builder)
    jobs = [job for job in dict.fromkeys(builder.sounds.jobs)
            if not master_copies.master_sound(job, export_dir, data_dir, masters)]
    builder.counts["sound files left to the master's archive"] = len(dict.fromkeys(builder.sounds.jobs)) - len(jobs)
    todo = [job for job in jobs if not job[1].exists()]
    builder.counts['sound files'] = voice.convert(todo, LIP_GENERATOR)


@timed('main archive', ARCHIVES)
def _main_archive(builder, data_dir: Path, plugin: str) -> None:
    """The Main and voices BA2s (pack_main), after every writer and the stale prune.
    See: docs/fork/fo4_pipeline.md#main-archive
    """
    builder.counts['files packed into the Main and voices archives'] = pack_main(data_dir, plugin)


@timed('plugin write')
def _write_plugin(builder, out: Path, data_dir: Path) -> None:
    """Save the ledger, then write the plugin to `out` (a dependent build's master records only where they change
    the master's: master_overrides; light or full: light_choice.finish_flag), clear script properties naming no
    written record, then write the animation data the written races need (_anim_text)."""
    builder.writer.next_object_id = builder.top
    if builder.built:
        adds = {}
        builder.counts.update(drop_unchanged(builder.writer, builder.built, builder.held, adds))
        script_overrides.apply(builder, data_dir / 'Scripts')
        builder.counts['master form list entries added at run time'] = list_adds.write(builder, adds)
    builder.counts[f'plugin written {finish_flag(builder.writer)}'] = 1
    out.parent.mkdir(parents=True, exist_ok=True)
    builder.writer.ledger.save()
    builder.writer.write(str(out))
    for key, count in clear_dangling(out, len(builder.writer.masters)).items():
        builder.counts[f'script properties naming no written record ({key})'] = count
    _anim_text(builder, [r for r in builder.writer.top_records() if r[:4] in (b'RACE', b'BPTD')], data_dir, out)


@timed('animation data')
def _anim_text(builder, records: list, data_dir: Path, plugin: Path) -> None:
    """Every AnimTextData file the written races (in packed `records`, with the body part data) need, in place of
    the Creation Kit (_made), or the last run's files touched when nothing it read changed (anim_text_skip); then
    stale files pruned, the persistent list merged and the Creation Kit stage's old lists beside the plugin
    removed; counted.
    See: docs/fork/research/anim_text_data.md#ours
    See: docs/fork/research/anim_text_data.md#skip
    """
    races = [r for r in records if r[:4] == b'RACE']
    vanilla, dirs = gun_anim_text.load_vanilla(FALLOUT4_DIR / 'Data'), [data_dir, *master_copies.master_dirs(builder)]
    copies = gun_anim_text.copied_entries(races, data_dir, vanilla)
    stamps = vanilla.stamp, anim_text_skip.archive_stamps(FALLOUT4_DIR / 'Data', GAME_ARCHIVES)
    key = anim_text_skip.inputs(plugin, records, stamps, dirs, copies)
    run = anim_text_skip.kept(key, dirs, data_dir)
    builder.counts['animation data runs skipped (nothing read changed)'] = int(run is not None)
    if run is None:
        run = anim_text_skip.live(key, data_dir, lambda logs: _made(logs, records, dirs, plugin, vanilla, copies))
    written = [data_dir / rel for rel in run['files']]
    builder.counts['animation data files written'] = len(written)
    builder.counts['stale animation data files removed'] = anim_text.prune(data_dir, written)
    builder.counts['ids added to the persistent subgraph list'] = gun_anim_text.merge_persistent(
        data_dir, {**copies, **run['templates']}, vanilla, dirs[1:])
    for suffix in ANIM_INFO_LISTS:
        moved_in(plugin.with_name(plugin.name + suffix)).unlink(missing_ok=True)
        plugin.with_name(plugin.name + suffix).unlink(missing_ok=True)


def _made(logs: list, records: list, dirs: list, plugin: Path, vanilla, copies: dict) -> tuple:
    """([written paths], {entry: template}) in the plugin's data folder (dirs[0]; its masters' follow): gun
    entries playing only vanilla clips (`copies`) copied from vanilla, own-rig creature projects' and entries'
    (read from the data folder only), other entries' offsets with their template's other files, and the sync data;
    each reader's reads logged in `logs` (anim_text_skip.live)."""
    races, data_dir, known = [r for r in records if r[:4] == b'RACE'], dirs[0], anim_text.known(vanilla)
    made = anim_text.creatures(races, anim_text_skip.logged_reader(logs, data_dir), known,
                               anim_text.body_parts([r for r in records if r[:4] == b'BPTD']))
    own = {entry: v for entry, v in anim_text.own_clips(races, vanilla, copies).items()
           if f'AnimationOffsets\\{entry}.txt' not in made}
    templates = {entry: template for entry, (_, template) in own.items() if template is not None}
    read = anim_text_skip.logged_reader(logs, *dirs, Archives(FALLOUT4_DIR / 'Data', GAME_ARCHIVES))
    files = {**made, **anim_text.entry_files(own, read, known), **anim_text.sync_data(plugin.name)}
    anim_text.save(known)
    written = (gun_anim_text.write(data_dir, copies, vanilla) + anim_text.write(data_dir, files)
               + gun_anim_text.write(data_dir, templates, vanilla, TEMPLATE_KINDS))
    return written, templates


def _finished(builder, data_dir: Path) -> tuple:
    """([every written mesh], [those nothing changes or reads after Elric: not weapons (dressed) or object LOD])."""
    paths = [data_dir / 'Meshes' / model for model, _ in builder.meshes.values()]
    later = {data_dir / 'Meshes' / m for m in builder.weapons}
    later |= {data_dir / 'Meshes' / made[0] for key, made in builder.meshes.items() if key.endswith('#lod')}
    return paths, [p for p in paths if p not in later]


@timed('collision', MESHES)
def _collision(builder, data_dir: Path) -> None:
    """Elric's collision for every written mesh but those a master ships finished alike (master_copies.theirs),
    then the weapon meshes dressed; counted."""
    paths, alone = _finished(builder, data_dir)
    builder.finished_alike = master_copies.theirs(builder, alone)
    failed = finish_meshes(data_dir, paths, builder.finished_alike, sorted(builder.weapons))
    builder.counts['meshes without collision (Elric failed)'] = len(failed)
    builder.counts["meshes left to the master's archive (finished alike)"] = len(elric_cache.LEFT)
    builder.counts['mesh vertices with a UV clamped to the half-float range'] = sum(mesh_cache.CLAMPED.values())
    builder.counts['weapon meshes'] = len(builder.weapons)


def finish_meshes(data_dir: Path, paths: list, theirs: dict, weapons: list) -> list:
    """elric_cache.finish() of `paths` (`theirs`: a master's finished-alike marks), then `weapons` (models under
    Meshes) dressed; the paths left without collision."""
    failed = elric_cache.finish(paths, theirs)
    for model in weapons:
        weapon.dress_file(data_dir / 'Meshes' / model)
    return failed


@timed('object LOD', MESHES)
def _object_lod(builder, export_dir: Path, data_dir: Path) -> None:
    """Built worldspaces' object LOD (after Elric, before the texture BA2)."""
    builder.counts.update(object_lod.bake_all(export_dir, data_dir, builder.object_lod.worlds))


@timed('assets')
def _assets(builder, export_dir: Path, data_dir: Path, out: Path) -> None:
    """Lowered skeletons, voices, sounds, movies and the level-up icons; counted."""
    builder.counts['human skeletons lowered'] = skeleton.write(data_dir)
    _sounds(builder, export_dir, data_dir, out.name)
    builder.counts['movies written'] = write_movies(export_dir, data_dir)
    level_up_icons.stage(builder, export_dir, data_dir)


@timed('FaceGen and texture archive', ARCHIVES)
def _faces(builder, data_dir: Path, out: Path) -> None:
    """After the plugin is written: faces_and_textures() for its NPC_ records; counted."""
    npcs = [struct.unpack_from('<I', rec, 12)[0] for rec in builder.writer.top_records() if rec[:4] == b'NPC_']
    builder.counts.update(faces_and_textures(data_dir, out, master_copies.master_dirs(builder), npcs))


def faces_and_textures(data_dir: Path, out: Path, masters: list, npcs: list, prune: bool = True) -> dict:
    """Drop FaceGen naming none of `npcs` (the plugin's NPC_ FormIDs) or drawing parts it no longer has
    (facegen.outdated against `masters`' folders; the game draws those NPCs from the record), then pack the
    texture BA2 (`prune`: pack_textures', off for a run that staged no texture); the counts."""
    stale = facegen.outdated(out, data_dir, masters)
    for path in stale:
        path.unlink()
    return {'FaceGeom NIFs older than their NPC head parts removed (run the faces stage)': len(stale),
            'stale FaceGen files removed': facegen.prune(out.name, data_dir, npcs),
            'textures packed': pack_textures(data_dir, out.name, (LUT_FOLDER, CLASSIC_FOLDER), prune)}


@timed('script compile', SCRIPTS)
def _compile(builder, data_dir: Path, scripts_dir) -> None:
    """compile_scripts() of the build's scripts (none without `scripts_dir`), then the script views
    (script_view.digests of its own and its masters' converted scripts) for a scripts replay."""
    builder.script_views = {}
    if scripts_dir is not None:
        built = [str(p) for p in builder.built]
        compile_scripts(Path(scripts_dir), data_dir, builder.scripts.used, built)
        builder.script_views = script_view.digests(script_folders(Path(scripts_dir).resolve(), built))


def script_folders(scripts_dir: Path, built: list) -> list:
    """`scripts_dir`, then the converted scripts of each built master in `built` (beside it, named for it)."""
    return [scripts_dir, *(scripts_dir.parent / Path(p).name for p in built)]


def compile_scripts(scripts_dir: Path, data_dir: Path, used: list, built: list) -> None:
    """Compile `used` (converted scripts in `scripts_dir`) into `data_dir`'s Scripts against the built masters
    `built`; the masters' scripts they name logged (build_inputs.master_scripts)."""
    if not used:
        return
    masters = tuple(script_folders(scripts_dir, built)[1:])
    print(compile_into(scripts_dir, data_dir, used, masters, tuple(Path(p).parent for p in built)))
    for path in master_scripts([scripts_dir / f'{name}.psc' for name in used], masters) if masters else ():
        MASTERS.script(path)


def compiled_names(names, data_dir: Path) -> dict:
    """{name: whether it compiled into `data_dir`'s Scripts} of script `names`, sorted."""
    return {name: (data_dir / 'Scripts' / f'{name}.pex').exists() for name in sorted(set(names))}


@timed('closing records')
def _closing_records(builder, export_dir: Path, data_dir: Path, out: Path, helper: int) -> None:
    """The records written from everything made: script packages, ammo, condition (helper plugin index
    `helper`), the Pip-Boy pages, challenges, Hardcore mode, the casino, the dialogue menu links; the masterless
    build also installs our Pip-Boy movie."""
    builder.counts['script packages'] = write_script_packages(builder)
    ammo_casings.write(builder, builder.equipment.ammo_mods.loaded)
    ammo_switch.write(builder, builder.equipment.ammo_mods)
    builder.equipment.condition.write(builder.equipment.ammo_mods, data_dir, helper)
    write_karma_page(builder, export_dir, builder.reputation_slots)
    write_page(builder)
    builder.challenges.write()
    builder.imposter_gate.write()
    builder.region_watch.write()
    builder.hardcore.write(builder.consumables.effects)
    builder.casino.write(data_dir)
    companion_barks.write(builder)
    builder.counts['Pip-Boy Tabs files removed'] = len(remove_legacy_tabs(data_dir, out.name))
    menu_links.write(builder, data_dir, out.name)
    if builder.built:
        builder.scripts.used += [list_adds.SCRIPT]
    else:
        builder.counts['Pip-Boy movies installed'] = pipboy_overlay.install(data_dir)
        builder.counts['level-up menu files installed (Cleanroom UI)'] = level_up_menu.install(data_dir)
        builder.counts['menu translation files installed'] = translations.install(data_dir)
        builder.counts['HUD host files installed (Cleanroom UI)'] = len(cleanroom.install(data_dir,
                                                                                            cleanroom.HUD_FILES))


@timed('closing records')
def _lists(builder, data_dir: Path) -> None:
    """Weapon and item type lists and the gun race, ammo, poisons, idles, furniture poses, combat settings."""
    builder.equipment.write_anim_lists()
    builder.items.write_type_lists()
    builder.consumables.write_ammo()
    builder.consumables.poisons.write()
    builder.idles.write(data_dir)
    builder.furniture_poses.write(data_dir)
    builder.combat.write()
    write_settings(builder, builder.combat.settings)


def _scripts_manifest(builder, export_dir: Path, data_dir: Path, scripts_dir) -> 'dict | None':
    """What a scripts replay takes from the build: the export, the converted scripts' folder, the scripts
    compiled, the built masters, the views and whether each changed master script compiled; None without scripts.
    See: docs/fork/fo4_plugin_layout.md#scripts-replay
    """
    if scripts_dir is None:
        return None
    planned = [entry[3] for entry in getattr(builder, 'script_overrides', {}).values()]
    return {'export': str(Path(export_dir).resolve()), 'dir': str(Path(scripts_dir).resolve()),
            'used': list(builder.scripts.used),
            'built': [str(p) for p in builder.built], 'views': builder.script_views,
            'overrides': compiled_names(planned, data_dir)}


@timed('ledger and cleanup')
def finish(builder, export_dir: Path, data_dir: Path, out: Path, scripts_dir, helper: int) -> collections.Counter:
    """Collision, object LOD, assets, the records written from everything made, scripts, then the plugin, its
    ledger and the stale files pruned; `builder`'s counts (`helper`: the helper plugin's master index)."""
    _collision(builder, data_dir)
    _object_lod(builder, export_dir, data_dir)
    _assets(builder, export_dir, data_dir, out)
    _closing_records(builder, export_dir, data_dir, out, helper)
    script_overrides.plan(builder, export_dir, scripts_dir)
    _compile(builder, data_dir, scripts_dir)
    _lists(builder, data_dir)
    _write_plugin(builder, out, data_dir)
    _faces(builder, data_dir, out)
    builder.counts["files left to the master's folder"] = master_copies.drop_loose(data_dir,
                                                                                    master_copies.master_dirs(builder))
    made = stale_files.made(data_dir, plugin_stem(export_dir), builder.started, bool(builder.built))
    builder.counts['stale meshes, materials and clips removed'] = len(stale_files.prune(out, data_dir, made))
    finished = _finished(builder, data_dir)[1]
    builder.counts['finished meshes recorded for dependent builds'] = master_copies.write_meshes(
        out, data_dir, finished, elric_cache.MARKS)
    replay_manifest.write(out, {'pre_elric': elric_cache.INPUTS, 'theirs': builder.finished_alike,
                                'weapons': sorted(builder.weapons), 'lod_worlds': builder.object_lod.worlds,
                                'finished': [str(p) for p in finished], 'export': str(export_dir),
                                'scripts': _scripts_manifest(builder, export_dir, data_dir, scripts_dir)})
    _main_archive(builder, data_dir, out.name)
    builder.counts['cache entries pruned (unused 14 days)'] = elric_cache.prune_caches(days=14)
    print(f'readiness entries: {builder.readiness.write(out.name)}')
    return builder.counts
