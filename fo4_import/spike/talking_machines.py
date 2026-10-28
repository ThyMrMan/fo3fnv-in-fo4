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

from fo4_import.nif.convert_static import ATTACH, NifFormat
from fo4_import.nif.outfit import fnv_nif
from fo4_import.spike import records as R
from fo4_import.spike.statics import write_assets
from fo4_import.spike.void_actors import invisible_race
from tes5_import.base.writer import pack_subrecord

#: The talkable race the speaker copies; FO4 RACE flag Immobile.
SPEAKER_RACE, IMMOBILE = 'ProtectronRace', 0x200
SITE = 'FNV talking machine'
#: The posed parts' file suffix, beside the unposed conversion.
SUFFIX = '_speaker'
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
    """posed()'s ATTACH of `part` at its `Prn` bone's world (FNV attaches it there); {} for a skinned or
    unparented part."""
    root = fnv_nif(part)
    prn = next((e.string_data.decode('cp1252') for e in root.get_extra_datas()
                if isinstance(e, NifFormat.NiStringExtraData) and e.name == b'Prn'), None)
    return {ATTACH: worlds[prn]} if prn in worlds else {}


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
        """The activators showing FNV creature `rec`'s body parts (its NIFZ) posed on its skeleton, written once."""
        folder = '\\'.join(rec['Model.MODL'].replace('/', '\\').split('\\')[:-1]).lower()
        names = [rec[f'NIFZ[{i}]'].lower() for i in range(int(rec.get('NIFZCount', 0) or 0))]
        worlds = bone_worlds(self.export_dir / 'meshes' / folder / 'skeleton.nif')
        present = [name for name in names if (self.export_dir / 'meshes' / folder / name).is_file()]
        self.builder.counts['talking machine part left out (no file)'] += len(names) - len(present)
        return [self._part(folder, name, worlds, rec.get('FULL', '')) for name in present]

    def _part(self, folder: str, name: str, worlds: dict, full: str) -> int:
        """The activator of body part `name` in skeleton folder `folder`, posed by `worlds`, named `full`."""
        model = f'{folder}\\{name}'
        if (model, full) not in self.parts:
            pose = part_pose(self.export_dir / 'meshes' / model, worlds)
            written, bounds = write_assets(self.export_dir, model, self.data_dir, pose, suffix=SUFFIX)
            fid = self.parts[(model, full)] = self.builder.writer.derive_formid(SITE, f'{model} {full}')
            edid = f'FNV_{name[:-4]}{full.replace(" ", "").replace(".", "")}Speaker'
            self.builder.writer.add_record('ACTI', R.pack_acti(fid, edid, full, written, bounds, b'', PROMPT))
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
