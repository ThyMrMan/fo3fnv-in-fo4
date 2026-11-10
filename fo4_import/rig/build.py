"""Own-rig creatures for one plugin build: per FNV skeleton folder (once) its skeleton, clips, skeleton.nif,
behaviour, project file data and records; per FNV body (once) its body NIF and skin.

See: docs/fork/fo4_own_rig.md#modules
"""

import pickle
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok import packfile_write
from fo4_import.havok.kf_cache import decoded
from fo4_import.nif import file as nif_file
from fo4_import.pipeline.elric_cache import write_new
from fo4_import.pipeline.master_copies import master_dirs
from fo4_import.pipeline.mesh_cache import mesh_files
from fo4_import.pipeline.work_cache import cached
from fo4_import.rig import assets, behavior, records
from fo4_import.spike.creature_attacks import power_share, with_attacks, with_spell
from fo4_import.spike.statics import stage_files
from fo4_import.pipeline.export_index import asset_root, export_file
from fo4_import.rig.table import rigs

#: AnimTextData's project file data folder (the Creation Kit does not write a project's list).
FILE_DATA = Path('Meshes') / 'AnimTextData' / 'AnimationFileData'
#: The work cache sites of an own-rig body (its NIF and staged files) and of its skeleton.nif (and ragdoll bones).
BODY_SITE, SKELETON_SITE = 'rig_body', 'rig_skeleton_nif'


def project_file_data(rig) -> bytes:
    """A project's AnimationFileData list, as vanilla's: 3, 0, its name, the count, its root behaviour, character,
    skeleton and the root graph's clips, 0; CRLF lines."""
    files = [f'Behaviors\\{rig.project}RootBehavior.hkx', f'Characters\\{rig.project}Character.hkx',
             'CharacterAssets\\skeleton.hkx'] + [f'Animations\\{c}.hkx' for c in rig.clips]
    lines = ['3', '0', f'{rig.project}Project', str(len(files))] + files + ['0']
    return ('\r\n'.join(lines) + '\r\n').encode('cp1252')


def gun_nodes(rig, fnv_dir: Path) -> dict:
    """{equip slot: (FNV fire node, its gun node's turn: assets.aim_turn at its clip's first shot)} of `rig`'s guns
    (records.with_slots)."""
    bones, out = assets.skeleton_bones(fnv_dir / 'skeleton.nif'), {}
    for role, slot, _, node in rig.guns:
        clip = decoded(str(fnv_dir / rig.clips[role]))[0]
        at = (behavior.shot_times(clip.text_keys) or [behavior.ATTACK_BLEND])[0]
        out[slot] = node, assets.aim_turn(bones, clip, node, at)
    return out


class Rigs:
    """Writes own-rig creatures' files and records for one build."""

    def __init__(self, builder, export_dir: Path, data_dir: Path):
        """For `builder`'s plugin (its writer, Fallout4.esm bytes and counts), from `export_dir` into `data_dir`."""
        self.builder, self.export_dir, self.data_dir = builder, export_dir, data_dir
        self.templates = records.Templates(builder.fo4)
        self.game = Archives(FALLOUT4_DIR / 'Data')
        self.races, self.skins, self.bones, self.sounds, self.armors = {}, {}, {}, {}, {}
        self.masters = master_dirs(builder)

    def out(self, rig, *parts: str) -> Path:
        return self.data_dir / 'Meshes' / rig.actor_dir / Path(*parts)

    def attacks(self, rig, race: int, style: dict, spell: int):
        """An NPC edit: `race`'s attacks at `style`'s power share, each casting `spell`.
        See: docs/fork/fo4_pipeline.md#attack-spells
        """
        subs = records.attack_subs(rig, records.normal_attack(rig, self.templates), power_share(style))
        return with_attacks(race, with_spell(subs, spell))

    def race(self, rig, rec: dict, style: dict, sounds, talks: bool) -> int:
        """The creature race of `rig`, written with all its files on first use; `rec` (the first FNV creature on
        it) names it and gives its first body, `style` (its FNV combat style) the power-attack share, `sounds`
        (creature_sounds.RigSounds) the graph's sound events; `talks`: one of its creatures may talk."""
        if rig.folder in self.races:
            return self.races[rig.folder]
        bones = self.rig_bones(rig)
        rig = records.with_slots(rig, self.templates)
        fnv_dir = asset_root(self.export_dir, 'meshes', rig.folder)
        shipped = self.shipped(rig)
        ragdoll = (assets.ragdoll_bones(nif_file.read(shipped.read_bytes())) if shipped
                   else self.write_rig(rig, fnv_dir, bones))
        self.sounds[rig.folder] = sounds
        maker = behavior.Builder(rig, fnv_dir, ragdoll, sounds, bones)
        if not shipped:
            self.write_behavior(rig, maker, [b.name for b in bones])
        self.builder.counts["own-rig files left to the master's folder" if shipped else 'own-rig files written'] += 1
        body = body_name(rec)
        made = {'name': rec.get('FULL', '') or rig.project, 'body': body, 'screen': self.write_body(rig, body),
                'share': power_share(style),
                'footsteps': not sounds.feet, 'talks': talks, 'kind': int(rec.get('DATA.CreatureType', 0) or 0),
                'parents': {b.name: bones[b.parent].name for b in bones if b.parent >= 0},
                'strings': self.builder.equipment.strings,
                'speeds': (maker.root_speed('WalkForward'), maker.root_speed('RunForward'))}
        self.races[rig.folder] = race = records.write(self.builder.writer, rig, self.templates, made)
        self.skins[(rig.folder, body.lower())] = self.builder.writer.derive_formid(
            records.SITE, f'{rig.folder} {body.lower()} skin')
        self.builder.counts['own-rig creature races'] += 1
        return race

    def shipped(self, rig, name: str = 'skeleton.nif') -> 'Path | None':
        """A built master's file `name` in `rig`'s CharacterAssets (left to it); None.
        See: docs/fork/fo4_own_rig.md#ragdoll-order
        """
        found = (d / self.out(rig, 'CharacterAssets', name).relative_to(self.data_dir) for d in self.masters)
        return next((p for p in found if p.is_file()), None)

    def write_rig(self, rig, fnv_dir: Path, bones: list) -> dict:
        """`rig`'s skeleton.hkx, clips and skeleton.nif (skeleton_nif); its ragdoll bones."""
        fires = gun_nodes(rig, fnv_dir)
        assets.write_skeleton(self.out(rig, 'CharacterAssets', 'skeleton.hkx'), bones)
        for role, kf in rig.clips.items():
            assets.write_clip(fnv_dir / kf, self.out(rig, 'Animations', f'{role}.hkx'), bones,
                              (assets.WEAPON,) if 0 in fires else ())
        return self.skeleton_nif(fnv_dir, rig, fires)

    def write_behavior(self, rig, maker, bone_names: list) -> None:
        """The root graph, character, project and the project's AnimationFileData list."""
        template = rig.template
        graph = maker.build(behavior.template_names(self.game.read(template['behavior']), rig.project))
        files = {('Behaviors', f'{rig.project}RootBehavior.hkx'): packfile_write.write(graph.objects, graph.top),
                 ('Characters', f'{rig.project}Character.hkx'):
                     behavior.character(self.game.read(template['character']), rig, bone_names),
                 (f'{rig.project}Project.hkx',): behavior.project(self.game.read(template['project']), rig)}
        for parts, data in files.items():
            self.out(rig, *parts).parent.mkdir(parents=True, exist_ok=True)
            self.out(rig, *parts).write_bytes(data)
        listed = self.data_dir / FILE_DATA / f'{rig.project.lower()}project.txt'
        listed.parent.mkdir(parents=True, exist_ok=True)
        listed.write_bytes(project_file_data(rig))

    def write_body(self, rig, body: str) -> 'str | None':
        """FNV body `body` (a file in the skeleton folder) on the rig, with its materials and textures, its face
        screen part (assets.screen_part) apart as its own model; the screen's file name, or None.

        See: docs/fork/fo4_own_rig.md#expressions
        """
        fnv_dir = asset_root(self.export_dir, 'meshes', rig.folder)
        parts = [fnv_dir / part for part in body_parts(body)]
        screen = assets.screen_part(parts)
        self.model(rig, [p for p in parts if p != screen], body)
        if screen:
            self.model(rig, [screen], screen.name)
        return screen.name if screen else None

    def model(self, rig, parts: list, name: str, textures: dict = None) -> None:
        """FNV body parts `parts` as the rig's model `name` (in CharacterAssets), with its materials and textures,
        `textures` retexturing shapes (assets.write_body), in file records.model_file; none of it when a built master
        ships the model (shipped). It and its files are kept in the work cache by its FNV meshes, bones, name and
        textures (the textures it names are FNV's export, not read again).
        See: docs/fork/fo4_plugin_layout.md#stage-times
        """
        file = records.model_file(name)
        if self.shipped(rig, file):
            self.builder.counts["own-rig bodies left to the master's folder"] += 1
            return
        fnv_dir, target = asset_root(self.export_dir, 'meshes', rig.folder), self.out(rig, 'CharacterAssets', file)
        inputs = (*(Path(str(p)).read_bytes() for p in parts + idle_clip(rig, fnv_dir)),
                  Path(str(fnv_dir / 'skeleton.nif')).read_bytes(), pickle.dumps(self.rig_bones(rig), protocol=5),
                  target.name, repr(sorted((textures or {}).items())))
        nif, files = cached(BODY_SITE, assets.__name__, inputs,
                            lambda: self._body(parts, fnv_dir, rig, (target, textures)))
        write_new(target, nif)
        for made in files:
            stage_files(self.export_dir, made, self.data_dir)

    def rig_bones(self, rig) -> list:
        """`rig`'s skeleton bones (assets.skeleton_bones with its main gun's fire node), read once."""
        if rig.folder not in self.bones:
            rig = records.with_slots(rig, self.templates)
            fnv_dir = asset_root(self.export_dir, 'meshes', rig.folder)
            self.bones[rig.folder] = assets.skeleton_bones(fnv_dir / 'skeleton.nif', gun_nodes(rig, fnv_dir).get(0, ()))
        return self.bones[rig.folder]

    def idle_clip(self, rig, kf: Path, name: str) -> str:
        """FNV idle clip `kf` (`name` under `rig`'s folder) on the rig's skeleton, in its DynamicAnimation folder as
        vanilla's creature idles; its path under Meshes.
        See: docs/fork/fo4_own_rig.md#idles
        """
        clip = rig.path('Animations', 'DynamicAnimation', str(Path(name).with_suffix('.hkx')))
        held = (assets.WEAPON,) if 0 in records.with_slots(rig, self.templates).fire_nodes else ()
        assets.write_clip(kf, self.data_dir / 'Meshes' / clip, self.rig_bones(rig), held)
        return clip

    def screen_armor(self, face: str, expression: str) -> int:
        """The armor showing securitron face `face` (FNV's spelling) with `expression` (Neutral, Alert): the first
        rig's face screen part, retextured as SetSecuritronExpression does, made once; 0 without one or its texture.

        See: docs/fork/fo4_own_rig.md#expressions
        """
        key = (face.lower(), expression.lower())
        if key not in self.armors:
            texture = assets.SCREEN_TEXTURE.format(*key)
            found = next(((rig, part) for rig in rigs().values() for part in screen_parts(self.export_dir, rig)), None)
            self.armors[key] = 0
            if found and export_file(self.export_dir, texture.replace('\\', '/')).exists():
                rig, part = found
                model = f'Screen_{key[0]}_{key[1]}.nif'
                self.model(rig, [part], model, {assets.SCREEN_SHAPE: texture})
                self.armors[key] = records.screen_armor(self.builder.writer, rig, self.templates, model,
                                                        f'{face}_{expression}')
            self.builder.counts['securitron screen armor' if self.armors[key] else
                                f'securitron screen without a rig or texture: {face} {expression}'] += 1
        return self.armors[key]

    def skeleton_nif(self, fnv_dir, rig, fires: dict) -> dict:
        """assets.write_skeleton_nif's skeleton.nif and ragdoll bones, kept in the work cache by the FNV skeleton and
        `fires` (Elric runs only when they change)."""
        target = self.out(rig, 'CharacterAssets', 'skeleton.nif')
        inputs = (Path(str(fnv_dir / 'skeleton.nif')).read_bytes(), repr(sorted(fires.items())))
        nif, ragdoll = cached(SKELETON_SITE, assets.__name__, inputs, lambda: self._skeleton(fnv_dir, target, fires))
        write_new(target, nif)
        return ragdoll

    @staticmethod
    def _skeleton(fnv_dir, target: Path, fires: dict) -> tuple:
        """(write_skeleton_nif's bytes at `target`, its ragdoll bones)."""
        ragdoll = assets.write_skeleton_nif(fnv_dir / 'skeleton.nif', target, fires)
        return target.read_bytes(), ragdoll

    def _body(self, parts: list, fnv_dir, rig, written: tuple) -> tuple:
        """(write_body's bytes at `written`'s target, its statics' mesh_files); `written` is (target, textures)."""
        target, textures = written
        statics, _ = assets.write_body(parts, fnv_dir / 'skeleton.nif', self.rig_bones(rig), target, self.export_dir,
                                       (next(iter(idle_clip(rig, fnv_dir)), None), textures))
        return target.read_bytes(), [mesh_files(static) for static in statics]

    def skin(self, rig, rec: dict) -> int:
        """The skin showing FNV creature `rec`'s body (and face screen) on its race, written once per body; its addon
        keeps the template's footstep set only when the rig plays no FNV foot sounds."""
        body = body_name(rec)
        key = (rig.folder, body.lower())
        if key not in self.skins:
            screen = self.write_body(rig, body)
            self.skins[key] = records.write_skin(self.builder.writer, rig, self.templates, self.races[rig.folder],
                                                 body, not self.sounds[rig.folder].feet, screen)
        return self.skins[key]


def screen_parts(export_dir: Path, rig) -> list:
    """`rig`'s FNV parts holding a face screen (screen_part), by name."""
    folder = asset_root(export_dir, 'meshes', rig.folder)
    found = sorted(Path(str(folder)).glob('*.nif'), key=lambda p: p.name.lower()) if Path(str(folder)).is_dir() else []
    return [p for p in found if assets.SCREEN_SHAPE.encode() in p.read_bytes() and assets.screen_part([p])]


def idle_clip(rig, fnv_dir) -> list:
    """[`rig`'s FNV idle clip, whose shader channels its body loops], or []."""
    return [fnv_dir / rig.clips['Idle']] if 'Idle' in rig.clips else []


def body_name(rec: dict) -> str:
    """FNV creature `rec`'s body NIF as a file name with a lower-case extension: its one NIFZ part's name, or
    its parts' stems joined by records.PART_JOIN (body_parts reads them back)."""
    parts = [rec[f'NIFZ[{i}]'] for i in range(int(rec.get('NIFZCount', 0) or 0))]
    if not parts:
        raise ValueError(f'{rec.get("EditorID")}: an own rig needs a body NIF, it has none')
    stem, _, ext = parts[0].rpartition('.')
    return f'{stem}.{ext.lower()}' if len(parts) == 1 else \
        records.PART_JOIN.join(p.rsplit('.', 1)[0] for p in parts) + '.nif'


def body_parts(body: str) -> list:
    """The FNV part files of body name `body` (body_name)."""
    stems = body[:-4].split(records.PART_JOIN)
    return [body] if len(stems) == 1 else [f'{stem}.nif' for stem in stems]
