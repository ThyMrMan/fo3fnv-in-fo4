"""FNV idle props with no vanilla stand-in, converted: their FO4 prop bone moves as FNV moved the prop.

See: docs/fork/fo4_idles.md#converted-props
"""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from asset_convert.havok.clip_retarget import posed_world, quat_wxyz_to_mat, world_positions
from fo4_import.havok.fnv_props import HANDS, local_at, unscaled
from fo4_import.havok.human_clip import HumanClips
from fo4_import.havok.kf_cache import decoded
from fo4_import.nif import file as nif_file
from fo4_import.spike.idle_props import IdleProps, chain_of
from fo4_import.nif.outfit import fnv_nif
from fo4_import.spike.statics import prop_assets
from tes5_import.base.tes5_reader import subrecords

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
#: FNV idles: Doc's mirror hand-over (the clip moves the Reflectron's nodes), reading a test paper (still).
MIRROR, PAPER = 0x0010658C, 0x0005DB21
MIRROR_CLIP = 'characters\\_male\\idleanims\\specialidle_nvcg01docgivemirror.kf'
needs_export = pytest.mark.skipif(not (EXPORT / 'ANIO.txt').exists(), reason='needs the FalloutNV.esm export')


class Builder:
    """CellBuilder's prop_mesh, fnv_id, writer and counts, writing under `data`."""

    def __init__(self, data: Path):
        """Meshes written under `data`."""
        self.data, self.counts, self.records = data, Counter(), []
        self.writer = SimpleNamespace(add_record=lambda sig, raw: self.records.append((sig, raw)))

    def prop_mesh(self, model, pose, bone):
        """prop_assets() of `model` into `data`."""
        return prop_assets(EXPORT, model, self.data, pose, bone)

    def fnv_id(self, fid):
        """FNV's own FormID."""
        return int(fid, 16)


@pytest.fixture(scope='module')
def clips():
    """FNV's and FO4's human skeletons, read once."""
    return HumanClips(EXPORT / 'meshes')


@needs_export
def test_a_props_chain_runs_from_its_root_to_the_node_holding_every_shape():
    """The Reflectron's chain ends at the node above all of its shapes."""
    chain = chain_of(fnv_nif(EXPORT / 'meshes' / 'animobjects' / 'nvpropreflectron.nif'))
    assert [name for name, _ in chain] == ['Dummy01_Reflectron', '##Dummy01_Reflectron01', '##NV_Reflectron']


@needs_export
def test_doc_s_mirror_turns_on_fo4_s_hand_exactly_as_on_fnv_s(clips, tmp_path):
    """On every frame, the FO4 prop bone's world turn (FO4's retargeted hand, then the track) is the FNV mirror's."""
    (prop,) = IdleProps(Builder(tmp_path), EXPORT, clips).get(MIRROR)
    clip = decoded(str(EXPORT / 'meshes' / MIRROR_CLIP))[0]
    track, hand = prop.track(clip, clips.fnv), clips.fnv.index[prop.parent]
    matched, fo4_hand = posed_world(clips.fnv, clips.deltas), clips.fo4.world[clips.fo4.index[HANDS[prop.parent][1]]]
    tracks = {t.bone: t for t in clip.tracks}
    for f in range(0, len(clip.times), 10):
        world = world_positions(clip, clips.fnv, f)[hand]
        fnv = np.eye(4)
        for name, rest in reversed(prop.chain):
            fnv = fnv @ local_at(tracks.get(name), f, rest)
        fnv = unscaled(fnv @ world)[:3, :3]
        on_hand = fo4_hand[:3, :3] @ np.linalg.inv(matched[hand][:3, :3]) @ world[:3, :3]
        assert np.allclose(quat_wxyz_to_mat(track.rotations[f]) @ on_hand, fnv, atol=1e-4)


@needs_export
def test_a_converted_prop_gets_an_anio_and_a_mesh_hung_from_its_hands_prop_bone(clips, tmp_path):
    """The test paper becomes an ANIO on FNV's FormID unloading on AnimObjUnequip, its mesh hung from AnimObjectR1."""
    builder = Builder(tmp_path)
    (prop,) = IdleProps(builder, EXPORT, clips).get(PAPER)
    assert (prop.name, prop.bone) == ('aoExamPaperA', 'AnimObjectR1')
    sig, raw = builder.records[0]
    subs = dict(subrecords(raw[24:]))
    assert (sig, subs[b'BNAM'], subs[b'MODL']) == ('ANIO', b'AnimObjUnequip\0', b'fnv\\animobjects\\aotestpaper_prop.nif\0')
    nif = nif_file.read((tmp_path / 'Meshes' / 'fnv' / 'animobjects' / 'aotestpaper_prop.nif').read_bytes())
    assert nif.blocks[nif.blocks[0][1]['extra'][0]][0] == 'NiStringExtraData' and 'AnimObjectR1' in nif.strings
