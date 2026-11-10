"""FNV furniture poses Fallout 4 has no furniture for (the crucifix), as own furniture subgraphs of FNV's clips.

FO4 picks a furniture's animations by keyword: HumanRaceSubGraphData maps
it to a furniture behavior graph and a folder of the clips that graph plays
(EnterFromStand, PoseA_Idle1, ExitToStand; vanilla's prisoner and hostage
furniture use FurnitureNoMirrorBehavior). A POSES slot gets its own keyword
and an additive race (SADD on HumanRaceSubGraphData, as the gun race) mapping
it to that graph and a folder of FNV's enter, held and exit clips, retargeted
onto FO4's skeleton in FNV's marker frame (the FO4 marker is FNV's). A slot
whose clips are missing keeps its vanilla stand-in (furniture.SLOT_SEATS).

See: docs/fork/fo4_pipeline.md#crucifix
"""

import struct
from pathlib import Path

from fo4_import.base.source import plugin_stem
from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.gun_clips import HUMAN_SUBGRAPHS
from fo4_import.havok.human_clip import HumanClips
from fo4_import.pipeline.export_index import asset_root
from fo4_import.spike import records as R
from fo4_import.spike.furniture import CRUCIFIED
from fo4_import.spike.idles import FO4_CLIPS
from fo4_import.spike.mutant_subgraphs import additive_race
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV clips (under meshes) by the furniture graph's clip names, per FNV marker slot: (pose name, {clip: .kf}).
POSES = {CRUCIFIED: ('NVCrucified', {
    'EnterFromStand.hkx': 'characters\\_male\\idleanims\\specialidle_nvcrucifixenter.kf',
    'PoseA_Idle1.hkx': 'characters\\_male\\idleanims\\dynamicidle_nvcrucifiedidle.kf',
    'ExitToStand.hkx': 'characters\\_male\\idleanims\\specialidle_nvcrucifixexit.kf'})}
#: The furniture graph vanilla's prisoner and hostage furniture name (AnimFurnPrisonerFloorSit's entry).
GRAPH = 'Actors\\Character\\Behaviors\\FurnitureNoMirrorBehavior.hkx'
#: SRAF of vanilla's furniture entries: role 2, third person.
FURNITURE_ENTRY = struct.pack('<HH', 2, 0)
#: The poses' folder under a plugin's clip folder; derive_formid site (keys: EditorIDs); the race's EditorID.
FOLDER, SITE, RACE_EDID = 'Furniture', 'FNV furniture pose', 'FNV_FurniturePoseSubGraphDataAdditive'


class FurniturePoses:
    """The build's own furniture poses: `keyword` hands one out, `write` converts its clips and writes its records."""

    def __init__(self, builder, export_dir: Path):
        """Poses of `export_dir`'s clips for `builder`."""
        self.builder, self.meshes, self.used = builder, asset_root(export_dir, 'meshes'), {}
        self.plugin = plugin_stem(export_dir)

    def keyword(self, slot: int) -> 'str | None':
        """The EditorID of FNV marker slot `slot`'s own pose keyword (added to the builder's keywords); None when
        it has no pose, no enter motion or a clip is missing."""
        if slot not in POSES or slot not in self.builder.enter_motions or \
                not all((self.meshes / kf).is_file() for kf in POSES[slot][1].values()):
            return None
        if slot not in self.used:
            edid = self._edid(f'FNV_AnimFurn{POSES[slot][0]}')
            self.builder.keywords[edid] = self.builder.writer.derive_formid(SITE, edid)
            self.used[slot] = edid
        return self.used[slot]

    def _edid(self, edid: str) -> str:
        """`edid`, suffixed with the plugin in a dependent build."""
        return f'{edid}_{self.plugin}' if self.builder.built else edid

    def write(self, data_dir: Path) -> None:
        """Convert each handed-out pose's clips into `data_dir`, and write its keyword and the race mapping them."""
        if not self.used:
            return
        builder, entries = self.builder, []
        clips = builder.idles.clips = builder.idles.clips or HumanClips(self.meshes)
        for slot, edid in sorted(self.used.items()):
            name, files = POSES[slot]
            folder = Path(FO4_CLIPS, self.plugin, FOLDER, name)
            for clip, kf in files.items():
                clips.write_pose(kf, data_dir / 'Meshes' / folder / clip, builder.creatures.sounds.named)
            keyword = builder.keywords[edid]
            builder.writer.add_record('KYWD', R.pack_kywd(keyword, edid, 0))
            entries.append(pose_entry(str(folder), keyword))
            builder.counts['furniture pose (own clips)'] += 1
        human = next(list(subrecords(r.body)) for r, _ in walk(builder.fo4, b'RACE') if r.form_id == HUMAN_SUBGRAPHS)
        race = self._edid(RACE_EDID)
        subs = additive_race(race, human, entries, HUMAN_SUBGRAPHS)
        builder.writer.add_record('RACE', pack_fo4_record('RACE', builder.writer.derive_formid(SITE, race), 0, b''.join(
            pack_subrecord(s.decode(), b) for s, b in subs)))


def pose_entry(folder: str, keyword: int) -> dict:
    """The subgraph entry playing `folder`'s clips on GRAPH for `keyword`."""
    return {'actor': [], 'graph': GRAPH, 'paths': [folder], 'target': [keyword], 'flags': FURNITURE_ENTRY}
