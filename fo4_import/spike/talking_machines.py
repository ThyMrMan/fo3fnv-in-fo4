"""FNV's talking machines (creature mode `speaker`): Mr. House's screen and pod, Yes Man's mainframe, Festus.

FNV draws them as creatures: skinned frames and rigid screens animated by
their own controllers (alpha, texture scroll, transform), on a skeleton with
no ragdoll, two to seven body parts, speaking through dialogue. An own rig
keeps only skinned shapes and needs a ragdoll, so each becomes an invisible
speaker with its look beside it:

- the speaker: its entry's NPC copied as a `stats` copy is (FNV's name,
  voice, scripts, factions, packages) on SpeakerRace, ProtectronRace (which
  allows player dialogue and has no FaceGen head) with an empty skin and the
  Immobile flag;
- its look: each FNV body part as an activator named as the machine, posed
  where FNV attaches it, placed where the speaker is and enable-parented to
  it (`look`), so a quest swapping one screen for another swaps both;
  activating it activates the speaker (LOOK_SCRIPT), as activating FNV's
  screen talked to it.

See: docs/fork/fo4_creature_audit.md#talking-machines
"""

import struct

import numpy as np

from fo4_import.base.source_fault import without_fault
from fo4_import.nif.clip_motion import clip_tracks, hang, loop
from fo4_import.nif.clip_shaders import bake, clip_channels
from fo4_import.nif.convert_static import ATTACH, NifFormat, convert
from fo4_import.nif.outfit import fnv_nif, prn_bone
from fo4_import.nif.terminal import placed_bounds
from fo4_import.pipeline.mesh_cache import cached_convert
from fo4_import.spike import records as R
from fo4_import.spike.statics import write_converted
from fo4_import.spike.void_actors import invisible_race
from fo4_import.pipeline.export_index import export_file
from tes5_import.base.writer import pack_subrecord

#: The talkable race the speaker copies; FO4 RACE flag Immobile.
SPEAKER_RACE, IMMOBILE = 'ProtectronRace', 0x200
SITE = 'FNV talking machine'
#: The posed parts' file suffix, beside the unposed conversion.
SUFFIX = '_speaker'
#: A creature's idle clip in its skeleton folder (FNV's `mtidle.kf`).
IDLE_CLIP = 'mtidle.kf'
#: The look's script and its property naming the speaker; the look's activate prompt.
LOOK_SCRIPT, SPEAKER_PROPERTY, PROMPT = 'F3NV_SpeakerLook', 'Speaker', 'Talk'


def bone_worlds(skeleton) -> dict:
    """{node name: (translation, rotation rows)} of every node of FNV skeleton NIF `skeleton` in its world."""
    root = fnv_nif(skeleton)
    out = {}
    for node in root.tree():
        if isinstance(node, NifFormat.NiNode):
            world = np.array(node.get_transform(root).as_list())
            out[node.name.decode('cp1252')] = (tuple(map(float, world[3, :3])),
                                               [list(map(float, row[:3])) for row in world[:3]])
    return out


def part_pose(part, worlds: dict) -> dict:
    """posed()'s ATTACH of `part` at its `Prn` bone's world; {} for none."""
    prn = prn_bone(fnv_nif(part))
    return {ATTACH: worlds[prn]} if prn in worlds else {}


def idle_rig(skeleton, idle) -> 'tuple | None':
    """(skeleton root, clip_channels(), clip_tracks()) of `idle`; None for none."""
    return (fnv_nif(skeleton), clip_channels(idle), clip_tracks(idle)) if idle.is_file() else None


def speaker_assets(export_dir, part: tuple, rig: 'tuple | None', data_dir) -> tuple:
    """write_converted() of FNV body part `part` (model, pose) as `<name><SUFFIX>.nif`. With an idle_rig() `rig`
    it is converted with its nodes, hung on the skeleton by its `Prn` bone, looping the idle's node and shader
    tracks, bounded where its nodes put it; without one, posed and flattened.

    See: docs/fork/fo4_creature_audit.md#talking-machine-clips
    """
    model, pose = part
    path = export_file(export_dir, 'meshes', model.replace('/', '\\').lower())
    rel = model.lower()[:-4] + SUFFIX + '.nif'
    if rig is None:
        return write_converted(export_dir, cached_convert(path, export_dir, pose), rel, data_dir)
    skeleton, looped, tracks = rig
    converted, fnv = convert(str(path), export_dir, every_bone=True), fnv_nif(path)
    hang(converted.nif, skeleton, prn_bone(fnv))
    loop(converted.nif, tracks, looped[0])
    bake(converted.nif, fnv, looped, export_dir)
    return write_converted(export_dir, converted, rel, data_dir)[0], placed_bounds(converted.nif)


class TalkingMachines:
    """The speaker race and the talking machines' looks, written once through `builder`."""

    def __init__(self, builder, export_dir, data_dir):
        """For `builder`'s plugin, reading `export_dir`'s meshes, writing into `data_dir`."""
        self.builder, self.export_dir, self.data_dir = builder, export_dir, data_dir
        self.speaker, self.parts = None, {}

    def race(self) -> tuple:
        """(race, skin): SPEAKER_RACE invisible and immobile, written once."""
        if self.speaker is None:
            self.speaker = invisible_race(self.builder, SPEAKER_RACE, SITE, 'Speaker', IMMOBILE)
        return self.speaker

    def statics(self, rec: dict) -> list:
        """The activators showing FNV creature `rec`'s body parts (its NIFZ) posed on its skeleton, written once; with
        no skeleton (a model alone: creature_routes' STILL), its model unposed."""
        folder, _, model = rec['Model.MODL'].replace('/', '\\').lower().rpartition('\\')
        skeleton = export_file(self.export_dir, 'meshes', folder, 'skeleton.nif')
        names = [rec[f'NIFZ[{i}]'].lower() for i in range(int(rec.get('NIFZCount', 0) or 0))]
        if not skeleton.is_file():
            names, rig, worlds = [model], None, {}
        else:
            rig = idle_rig(skeleton, export_file(self.export_dir, 'meshes', folder, IDLE_CLIP))
            worlds = bone_worlds(skeleton) if rig is None else {}
        present = [name for name in names if export_file(self.export_dir, 'meshes', folder, name).is_file()]
        self.builder.counts['talking machine part left out (no file)'] += len(names) - len(present)
        made = [self._part(folder, name, (worlds, rig), rec.get('FULL', '')) for name in present]
        self.builder.counts['talking machine part left out (a source fault)'] += made.count(None)
        return [fid for fid in made if fid is not None]

    def _part(self, folder: str, name: str, posing: tuple, full: str) -> 'int | None':
        """The activator of body part `name` in skeleton folder `folder`, named `full`, `posing` being (bone
        worlds, idle_rig()): rigged when there is an idle, else posed by the worlds. A part with no triangles (a
        particle spray) is bounded by zeros; None for one with a source fault."""
        model = f'{folder}\\{name}'
        if (model, full) not in self.parts:
            worlds, rig = posing
            pose = part_pose(export_file(self.export_dir, 'meshes', model), worlds) if rig is None else None
            made = without_fault(speaker_assets, self.export_dir, (model, pose), rig, self.data_dir)
            if made is None:
                self.parts[(model, full)] = None
                return None
            written, bounds = made
            fid = self.parts[(model, full)] = self.builder.writer.derive_formid(SITE, f'{model} {full}')
            edid = f'FNV_{name[:-4]}{full.replace(" ", "").replace(".", "")}Speaker'
            self.builder.writer.add_record('ACTI', R.pack_acti(fid, edid, full, written, bounds or (0,) * 6, b'', PROMPT))
            self.builder.counts['talking machine part'] += 1
        return self.parts[(model, full)]

    def look(self, achr: int, rec: dict, ref_key: str, placed: tuple) -> bytes:
        """The placed statics of speaker `achr` (FNV creature `rec`, placed reference `ref_key`), each
        enable-parented to it: `placed` is its ACHR's (position, rotation, scale, persistent, disabled)."""
        pos, rot, scale, persistent, disabled = placed
        parent = pack_subrecord('XESP', struct.pack('<IB3x', achr, 0))
        vmad = self.builder.scripts.vmad(0, ((LOOK_SCRIPT, {SPEAKER_PROPERTY: achr}, {}),))
        self.builder.scripts.used.append(LOOK_SCRIPT)
        return b''.join(R.pack_refr(self.builder.new_id(ref_key, key=f'{ref_key} speaker part {i}'), base, pos, rot,
                                    scale, persistent=persistent, placement=parent, disabled=disabled, vmad=vmad)
                        for i, base in enumerate(self.statics(rec)))
