"""FNV's crucifix as an own FO4 furniture pose: FNV's marker, the subgraph race, the converted clips.

See: docs/fork/fo4_pipeline.md#crucifix
"""

import collections
import math
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.gun_clips import HUMAN_SUBGRAPHS, subgraph_entries
from fo4_import.havok.human_clip import COM, HumanClips
from fo4_import.spike import furniture as F
from fo4_import.spike import furniture_poses as P
from tes5_import.base.tes5_reader import subrecords, walk

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
FO4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
needs_data = pytest.mark.skipif(not (EXPORT / 'IDLE.txt').exists() or not FO4_ESM.exists(),
                                reason='needs the FalloutNV.esm export and Fallout4.esm')
#: FNV's crucifix clips: (pose clip, FNV length in seconds).
LENGTHS = {'EnterFromStand.hkx': 2.0, 'PoseA_Idle1.hkx': 14.0, 'ExitToStand.hkx': 2.6667}


class _Writer:
    """The writer calls FurniturePoses makes: hashed ids, records kept by signature."""

    def __init__(self):
        """No records yet."""
        self.records = collections.defaultdict(list)

    def derive_formid(self, site: str, key: str) -> int:
        """A stable id per (site, key)."""
        return 0x01000000 | hash((site, key)) & 0xFFFFFF

    def add_record(self, sig: str, record: bytes) -> None:
        """Keep `record`."""
        self.records[sig].append(record)


def _builder(fo4: bytes = b'', motions: dict = None) -> SimpleNamespace:
    """A builder stub with what FurniturePoses reads."""
    sounds = SimpleNamespace(named=lambda edid: f'SoundPlay.FNV_{edid}')
    return SimpleNamespace(writer=_Writer(), keywords={}, built=None, fo4=fo4, counts=collections.Counter(),
                           enter_motions=motions or {}, idles=SimpleNamespace(clips=None),
                           creatures=SimpleNamespace(sounds=sounds))


def test_the_crucifix_takes_its_own_pose_keyword_when_it_has_one():
    """Slot 10 with an own pose: that keyword alone, at FNV's marker; without one, the prisoner floor sit."""
    poses = SimpleNamespace(keyword=lambda slot: 'FNV_AnimFurnNVCrucified' if slot == F.CRUCIFIED else None)
    still = {F.CRUCIFIED: (0.0, 0.0, 0.0)}
    seats, words, marker = F.slot_seats([(0.0, 0.0, 0.0, 0.0, F.CRUCIFIED)], 1, still, poses)
    assert words == ('FNV_AnimFurnNVCrucified',) and marker == F.SLOT_SEATS[F.CRUCIFIED][1]
    assert [s[:4] for s in seats] == [(0.0, 0.0, 0.0, 0.0)]
    assert F.slot_seats([(0.0, 0.0, 0.0, 0.0, F.CRUCIFIED)], 1, still)[1] == ('AnimFurnPrisonerFloorSit',)


def test_a_pose_without_its_clips_falls_back(tmp_path):
    """No FNV clips (or no enter motion): no keyword, so the vanilla stand-in stays, and nothing is written."""
    poses = P.FurniturePoses(_builder(motions={F.CRUCIFIED: (3.6, 59.4, math.pi)}), tmp_path / 'FalloutNV.esm')
    assert poses.keyword(F.CRUCIFIED) is None and poses.keyword(F.SIT_STOOL) is None
    poses.write(tmp_path)
    assert not poses.builder.writer.records


@needs_data
def test_the_crucifix_race_entry_is_laid_out_as_vanillas_prisoner_sit(tmp_path):
    """The keyword (TNAM 0, as AnimFurnPrisonerFloorSit), and one additive race on HumanRaceSubGraphData whose
    entry names vanilla's prisoner-sit graph and flags, the pose's folder and keyword; the clips are written."""
    fo4 = FO4_ESM.read_bytes()
    builder = _builder(fo4, {F.CRUCIFIED: F.enter_motion(str(EXPORT / 'meshes' / F.ENTER_ANIMS[F.CRUCIFIED]))})
    poses = P.FurniturePoses(builder, EXPORT)
    edid = poses.keyword(F.CRUCIFIED)
    assert edid == 'FNV_AnimFurnNVCrucified' and builder.keywords[edid]
    poses.write(tmp_path)
    keyword = builder.keywords[edid]
    (kywd,), (race,) = builder.writer.records['KYWD'], builder.writer.records['RACE']
    assert dict(subrecords(kywd[24:]))[b'TNAM'] == bytes(4)
    subs = list(subrecords(race[24:]))
    assert [struct.unpack('<I', b)[0] for s, b in subs if s == b'SADD'] == [HUMAN_SUBGRAPHS]
    human = next(list(subrecords(r.body)) for r, _ in walk(fo4, b'RACE') if r.form_id == HUMAN_SUBGRAPHS)
    prisoner = next(e for e in subgraph_entries(human) if e['paths'][0].endswith('PrisonerSitOnFloor'))
    (entry,) = subgraph_entries(subs)
    folder = 'Actors' + chr(92) + 'Character' + chr(92) + 'Animations' + chr(92) + 'FalloutNV' + chr(92) + \
        'Furniture' + chr(92) + 'NVCrucified'
    assert (entry['graph'], entry['flags'], entry['actor']) == (prisoner['graph'], prisoner['flags'], [])
    assert (entry['paths'], entry['target']) == ([folder], [keyword])
    assert all((tmp_path / 'Meshes' / folder / clip).is_file() for clip in LENGTHS)


@needs_data
def test_the_crucified_hang_on_the_cross_ahead_of_fnvs_marker(tmp_path):
    """Read back, each clip keeps FNV's length on FO4's 95 bones. The held pose hangs COM about 180 up on the
    cross, 59.4 ahead of the marker where FNV stands the actor, turned half round from FO4's rest COM within FNV's
    2 degree twist (back to the cross), and plays FNV's moan; the exit ends standing."""
    clips = HumanClips(EXPORT / 'meshes')
    com, (w, x, y, z) = clips.fo4.names.index(COM), clips.pose[COM][1]
    back = np.array((-z, -y, x, w))
    read = {}
    for clip, kf in P.POSES[F.CRUCIFIED][1].items():
        clips.write_pose(kf, tmp_path / clip, lambda edid: f'SoundPlay.FNV_{edid}')
        read[clip] = parse_fo4_animation((tmp_path / clip).read_bytes())
        assert read[clip].num_tracks == 95 and math.isclose(read[clip].duration, LENGTHS[clip], abs_tol=1e-3)
    for clip in ('EnterFromStand.hkx', 'PoseA_Idle1.hkx'):
        track = read[clip].tracks[com]
        for t, r in zip(track.translations, track.rotations):
            assert math.hypot(t[0] - 3.6, t[1] - 59.4) < 1.5 and 175 < t[2] < 185
            q = np.array((r[3], *r[:3]))
            assert abs(np.dot(q, back)) > math.cos(math.radians(6) / 2)
    assert [(round(a.time, 2), a.text) for a in read['PoseA_Idle1.hkx'].annotations] == \
        [(0.33, 'SoundPlay.FNV_NPCIdleCrucifiedVox')]
    assert 60 < read['ExitToStand.hkx'].tracks[com].translations[-1][2] < 72
