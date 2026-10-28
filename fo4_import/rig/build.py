"""Own-rig creatures for one plugin build: per FNV skeleton folder (once) its skeleton, clips, skeleton.nif,
behaviour, project file data and records; per FNV body (once) its body NIF and skin.

See: docs/fork/fo4_own_rig.md#modules
"""

from pathlib import Path

from asset_convert.havok.kf_decode import decode_kf
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok import packfile_write
from fo4_import.pipeline.mesh_cache import mesh_files
from fo4_import.rig import assets, behavior, records
from fo4_import.spike.creature_attacks import power_share, with_attacks, with_spell
from fo4_import.spike.statics import stage_files

#: AnimTextData's project file data folder (the Creation Kit does not write a project's list).
FILE_DATA = Path('Meshes') / 'AnimTextData' / 'AnimationFileData'


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
        clip = decode_kf(str(fnv_dir / rig.clips[role]))[0]
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
        self.races, self.skins, self.bones, self.sounds = {}, {}, {}, {}

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
        rig = records.with_slots(rig, self.templates)
        fnv_dir = self.export_dir / 'meshes' / rig.folder
        fires = gun_nodes(rig, fnv_dir)
        self.bones[rig.folder] = bones = assets.skeleton_bones(fnv_dir / 'skeleton.nif', fires.get(0, ()))
        assets.write_skeleton(self.out(rig, 'CharacterAssets', 'skeleton.hkx'), bones)
        for role, kf in rig.clips.items():
            assets.write_clip(fnv_dir / kf, self.out(rig, 'Animations', f'{role}.hkx'), bones,
                              (assets.WEAPON,) if 0 in fires else ())
        ragdoll = assets.write_skeleton_nif(fnv_dir / 'skeleton.nif', self.out(rig, 'CharacterAssets', 'skeleton.nif'),
                                            fires)
        self.sounds[rig.folder] = sounds
        maker = behavior.Builder(rig, fnv_dir, ragdoll, sounds, bones)
        self.write_behavior(rig, maker, [b.name for b in bones])
        body = self.write_body(rig, body_name(rec))
        made = {'name': rec.get('FULL', '') or rig.project, 'body': body, 'share': power_share(style),
                'footsteps': not sounds.feet, 'talks': talks, 'kind': int(rec.get('DATA.CreatureType', 0) or 0),
                'speeds': (maker.root_speed('WalkForward'), maker.root_speed('RunForward'))}
        self.races[rig.folder] = race = records.write(self.builder.writer, rig, self.templates, made)
        self.skins[(rig.folder, body.lower())] = self.builder.writer.derive_formid(
            records.SITE, f'{rig.folder} {body.lower()} skin')
        self.builder.counts['own-rig creature races'] += 1
        return race

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

    def write_body(self, rig, body: str) -> str:
        """FNV body `body` (a file in the skeleton folder) on the rig, with its materials and textures; its name."""
        fnv_dir = self.export_dir / 'meshes' / rig.folder
        parts = [fnv_dir / part for part in body_parts(body)]
        statics, _ = assets.write_body(parts, fnv_dir / 'skeleton.nif', self.bones[rig.folder],
                                       self.out(rig, 'CharacterAssets', body), self.export_dir)
        for static in statics:
            stage_files(self.export_dir, mesh_files(static), self.data_dir)
        return body

    def skin(self, rig, rec: dict) -> int:
        """The skin showing FNV creature `rec`'s body on its race, written once per body; its addon keeps the
        template's footstep set only when the rig plays no FNV foot sounds."""
        body = body_name(rec)
        key = (rig.folder, body.lower())
        if key not in self.skins:
            self.write_body(rig, body)
            self.skins[key] = records.write_skin(self.builder.writer, rig, self.templates, self.races[rig.folder],
                                                 body, not self.sounds[rig.folder].feet)
        return self.skins[key]


#: Between the parts' stems in a several-part body's name.
PART_JOIN = '+'


def body_name(rec: dict) -> str:
    """FNV creature `rec`'s body NIF as a file name with a lower-case extension: its one NIFZ part's name, or
    its parts' stems joined by PART_JOIN (body_parts reads them back)."""
    parts = [rec[f'NIFZ[{i}]'] for i in range(int(rec.get('NIFZCount', 0) or 0))]
    if not parts:
        raise ValueError(f'{rec.get("EditorID")}: an own rig needs a body NIF, it has none')
    stem, _, ext = parts[0].rpartition('.')
    return f'{stem}.{ext.lower()}' if len(parts) == 1 else PART_JOIN.join(p.rsplit('.', 1)[0] for p in parts) + '.nif'


def body_parts(body: str) -> list:
    """The FNV part files of body name `body` (body_name)."""
    stems = body[:-4].split(PART_JOIN)
    return [body] if len(stems) == 1 else [f'{stem}.nif' for stem in stems]
