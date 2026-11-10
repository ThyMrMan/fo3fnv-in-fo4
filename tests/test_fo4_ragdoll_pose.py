"""A placed dead actor's ragdoll pose, FNV's onto FO4's skeleton (fo4_import.spike.ragdoll_pose)."""

import collections
import struct
import types
from pathlib import Path

import numpy as np
import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, source_walk
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike import ragdoll_pose as P
from fo4_import.spike.scol import angles, rotation
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

FALLOUT4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
FO4_HUMAN = 'actors\\character\\characterassets\\skeleton.nif'
#: Fallout4.esm's human corpses' part numbers, entry by entry (507 of them).
FO4_HUMAN_PARTS = (2, 8, 9, 10, 14, 15, 16, 2, 3, 4, 5, 6, 7, 0, 1, 11, 12, 13)
needs_fo4 = pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout 4')
needs_both = pytest.mark.skipif(not FALLOUT4_ESM.exists() or not EXPORT.exists(), reason='needs Fallout 4 and the export')


def _toy() -> P.Skeleton:
    """A root, arm (turned at rest), hand chain; bodies root and hand."""
    nodes = {'root': (None, np.eye(3), np.zeros(3)), 'arm': ('root', rotation((0.0, 0.0, 0.7)), np.array([5.0, 0, 0])),
             'hand': ('arm', np.eye(3), np.array([3.0, 0, 0]))}
    return P.Skeleton(nodes, [('root', 2), ('hand', 7)])


def test_a_pose_converted_onto_its_own_skeleton_comes_back_unchanged():
    """Same skeleton, same names: each entry's part, rest offset and rotation return as they went in."""
    sk = _toy()
    pose = P.ENTRY.pack(2, 1.0, 2.0, 3.0, 0.3, -0.2, 1.1) + P.ENTRY.pack(7, 3.0, 0, 0, 0.1, 0.4, -0.5)
    back = P.convert(sk, sk, {}, pose)
    a, b = (list(P.ENTRY.iter_unpack(x)) for x in (pose, back))
    assert [e[0] for e in b] == [2, 7] and np.allclose(b[0][1:4], a[0][1:4])
    assert all(np.allclose(rotation(x[4:7]), rotation(y[4:7]), atol=1e-6) for x, y in zip(a, b))


def test_a_bone_without_a_source_stays_at_rest_under_its_parent_and_the_angles_round_trip():
    """FO4's hand has no FNV source: its local rotation is its rest (identity); angles() inverts rotation()."""
    fnv = P.Skeleton({'root': (None, np.eye(3), np.zeros(3))}, [('root', 2)])
    pose = P.convert(fnv, _toy(), {}, P.ENTRY.pack(2, 0, 0, 0, 0.5, 0.2, -0.3))
    hand = list(P.ENTRY.iter_unpack(pose))[1]
    assert np.allclose(rotation(hand[4:7]), np.eye(3), atol=1e-6)
    turn = (0.4, -1.2, 2.5)
    assert np.allclose(rotation(angles(rotation(turn))), rotation(turn))


def test_a_pose_that_is_not_the_skeletons_body_count_does_not_convert():
    sk = _toy()
    assert P.convert(sk, sk, {}, P.ENTRY.pack(2, 0, 0, 0, 0, 0, 0)) is None


@needs_fo4
def test_fo4s_human_skeleton_gives_its_corpses_part_numbers_and_every_one_round_trips():
    """The human ragdoll's bodies in tree order carry vanilla corpses' part numbers; each such corpse in
    Fallout4.esm converts onto its own skeleton unchanged (the layout check against vanilla)."""
    sk = P.fo4_skeleton(Archives(FALLOUT4_DIR / 'Data').read('meshes\\' + FO4_HUMAN))
    assert tuple(p for _, p in sk.bodies) == FO4_HUMAN_PARTS
    checked = 0
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), b'ACHR'):
        x = dict(subrecords(rec.body)).get(b'XRGD', b'') if rec.flags & 0x200 else b''
        if len(x) == 28 * 18 and tuple(x[o] for o in range(0, len(x), 28)) == FO4_HUMAN_PARTS:
            back = P.convert(sk, sk, {}, x)
            for e, f in zip(P.ENTRY.iter_unpack(x), P.ENTRY.iter_unpack(back)):
                assert np.allclose(rotation(e[4:7]), rotation(f[4:7]), atol=1e-3)
            checked += 1
    assert checked >= 500


TOY = 'Actors\\Toy\\skeleton.nif'
#: A RACE record whose skeleton is TOY, as race_skeleton reads it.
TOY_RACE = (b'RACE', [(b'MNAM', b''), (b'ANAM', TOY.encode() + b'\0')])


def _corpse(fid: int, pose: bytes, angles_xyz=(0.0, 0.0, 1.2), flags=0x200) -> types.SimpleNamespace:
    """A Fallout4.esm ACHR on base 7 (TOY_RACE) posed `pose`, far from origin."""
    body = (pack_subrecord('NAME', struct.pack('<I', 7)) + pack_subrecord('XRGD', pose)
            + pack_subrecord('DATA', struct.pack('<6f', 1000, 2000, 300, *angles_xyz)))
    return types.SimpleNamespace(form_id=fid, flags=flags, body=body)


def _toy_pose(root_turn=(0.0, 0.0, 0.0), parts=(2, 7)) -> bytes:
    """A TOY pose: the root turned `root_turn` at the origin, the hand at rest."""
    return P.ENTRY.pack(parts[0], 0, 0, 0, *root_turn) + P.ENTRY.pack(parts[1], 3.0, 0, 0, 0, 0, 0)


def _toy_poses(corpses: list) -> P.Poses:
    """Poses with no FNV poses, Fallout4.esm's corpses `corpses` and TOY's skeleton, FO4 base 7 being TOY_RACE."""
    poses = object.__new__(P.Poses)
    poses.builder = types.SimpleNamespace(counts=collections.Counter(), writer=types.SimpleNamespace(own_index=1))
    poses.ragdolls, poses.fnv_records, poses.vanilla, poses.fallbacks = {}, {}, {7: TOY_RACE}, {}
    poses.skeletons = {('fo4', TOY): _toy()}
    poses.corpses = P.vanilla_corpses([(c, None) for c in corpses], poses.vanilla.get)
    return poses


def test_a_dead_actor_fnv_gives_no_pose_takes_the_flattest_upright_vanilla_corpses_on_its_skeleton():
    """No FNV pose: the flattest Fallout4.esm corpse on the same skeleton, placed upright (a tilted one and one
    whose parts are not the skeleton's lose), is written as it is, its root at the reference's own origin rather
    than the donor's place; counted apart.
    See: docs/fork/fo4_spikes.md#fallback-pose"""
    leaning, flat = _toy_pose((0.0, 1.0, 0.0)), _toy_pose()
    poses = _toy_poses([_corpse(5, leaning), _corpse(6, flat), _corpse(1, flat, (0.4, 0.0, 0.0)),
                        _corpse(2, _toy_pose(parts=(9, 7))), _corpse(3, flat, flags=0)])
    out = poses.subrecords(0x100, 0x200, 7)
    assert out == pack_subrecord('XRGD', flat)
    root = P.decode(_toy(), dict(subrecords(out))[b'XRGD'])['root']
    assert np.allclose(root[1], 0) and np.allclose(root[0], np.eye(3))
    assert poses.builder.counts == {f'ragdoll pose written (fallback): {TOY}': 1}


def test_a_dead_actor_without_a_pose_or_a_vanilla_corpse_on_its_skeleton_is_left_out():
    """Nothing written, counted under the old reason."""
    poses = _toy_poses([])
    assert poses.subrecords(0x100, 0x200, 7) == b''
    assert poses.builder.counts == {f'ragdoll pose left out: no FNV pose: {TOY}': 1}


@needs_fo4
def test_fo4s_human_has_an_upright_vanilla_corpse_lying_flat_for_the_fallback():
    """Fallout4.esm's flattest upright human corpse has FO4's human parts, its root at the reference's origin
    (XRGD is the reference's space: no donor position to move), and its bodies within 15 units of height."""
    raw = FALLOUT4_ESM.read_bytes()
    vanilla = {r.form_id: (s, list(subrecords(r.body))) for s in (b'NPC_', b'LVLN', b'RACE') for r, _ in walk(raw, s)}
    sk = P.fo4_skeleton(Archives(FALLOUT4_DIR / 'Data').read('meshes\\' + FO4_HUMAN))
    xrgd, _ = P.flattest(sk, P.vanilla_corpses(walk(raw, b'ACHR'), vanilla.get)[FO4_HUMAN])
    posed = P.decode(sk, xrgd)
    assert tuple(xrgd[::P.ENTRY.size]) == FO4_HUMAN_PARTS and np.allclose(P.ENTRY.unpack_from(xrgd)[1:4], 0)
    assert np.ptp([posed[n][1][2] for n, _ in sk.bodies]) < 15


def _fnv_pose(ref: int) -> bytes:
    """FNV reference `ref`'s XRGD."""
    return P.ragdolls(r for r in source_walk(b'ACHR', b'ACRE') if r[0].form_id == ref)[ref][0]


@needs_both
def test_an_fnv_human_corpse_lands_on_fo4s_human_lying_as_flat():
    """FNV's 0015863A (18 human bodies) becomes 18 FO4 entries with FO4's part numbers; its joints span about the
    same height on FO4's skeleton as on FNV's (both lie on the floor)."""
    fnv = P.fnv_skeleton(EXPORT / 'meshes' / 'characters' / '_male' / 'skeleton.nif')
    fo4 = P.fo4_skeleton(Archives(FALLOUT4_DIR / 'Data').read('meshes\\' + FO4_HUMAN))
    pose = _fnv_pose(0x0015863A)
    out = P.convert(fnv, fo4, P.bone_map('Characters\\_Male\\Skeleton.NIF', FO4_HUMAN), pose)
    assert tuple(e[0] for e in P.ENTRY.iter_unpack(out)) == FO4_HUMAN_PARTS
    spread = [np.ptp([w[n][1][2] for n, _ in sk.bodies]) for sk, w in ((fnv, P.decode(fnv, pose)), (fo4, P.decode(fo4, out)))]
    assert spread[0] < 25 and abs(spread[1] - spread[0]) < 8


@needs_both
@pytest.mark.parametrize('fnv_model, fo4_model, least', [
    ('Creatures\\Ghoul\\Skeleton.nif', 'Actors\\FeralGhoul\\CharacterAssets\\skeleton.nif', 1.0),
    ('Creatures\\Brahmin\\Skeleton.nif', 'Actors\\Brahmin\\CharacterAssets\\Skeleton.nif', 33 / 39),
    ('Creatures\\Molerat\\Skeleton.nif', 'Actors\\Molerat\\CharacterAssets\\Skeleton.nif', 1.0)])
@needs_both
def test_creature_skeletons_map_enough_bodies_to_write_a_pose(fnv_model, fo4_model, least):
    """FNV's ghoul, brahmin and mole rat skeletons find a source for at least `least` of FO4's ragdoll bodies
    (FERAL_GHOUL 18 of 18, BRAHMIN 33 of 39, MOLERAT 20 of 20).
    See: docs/fork/fo4_spikes.md#creature-poses"""
    fnv = P.fnv_skeleton(EXPORT / 'meshes' / fnv_model.lower().replace('\\', '/'))
    fo4 = P.fo4_skeleton(Archives(FALLOUT4_DIR / 'Data').read('meshes\\' + fo4_model.lower()))
    share = len(P.sources(fnv, fo4, P.bone_map(fnv_model, fo4_model))) / len(fo4.bodies)
    assert share >= least >= P.MAPPED_SHARE


def test_a_race_skeleton_follows_a_traits_template_and_a_lists_first_entry():
    """NPC 1 takes traits from list 2, whose first entry NPC 3 is race 4: its male skeleton (ANAM after MNAM).
    ACBS holds the template flags at byte 14."""
    acbs = lambda flags: bytes(14) + struct.pack('<H', flags) + bytes(4)
    recs = {1: (b'NPC_', [(b'ACBS', acbs(P.USE_TRAITS)), (b'TPLT', struct.pack('<I', 2))]),
            2: (b'LVLN', [(b'LVLO', struct.pack('<HHI', 1, 0, 3))]),
            3: (b'NPC_', [(b'ACBS', acbs(0)), (b'RNAM', struct.pack('<I', 4))]),
            4: (b'RACE', [(b'ANAM', b'nope\0'), (b'MNAM', b''), (b'ANAM', b'Actors\\X\\skeleton.nif\0')])}
    assert P.race_skeleton(recs.get, 1) == 'Actors\\X\\skeleton.nif'


def test_a_dlc_corpse_on_a_game_base_reads_the_built_game_plugins_race(tmp_path):
    """_lookup: a FormID of the built game plugin (byte 3) resolves from that plugin's records, read once."""
    game = FO4PluginWriter(masters=['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm'], is_esm=True)
    anam = b'Actors/G/skeleton.nif\0'
    game.add_record('RACE', pack_fo4_record('RACE', 0x03000801, 0, pack_subrecord('ANAM', anam)))
    path = tmp_path / 'FalloutNV.esm'
    game.write(str(path))
    poses = object.__new__(P.Poses)
    poses.builder = types.SimpleNamespace(built=[path], writer=types.SimpleNamespace(own_index=4),
                                          masters=['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'FalloutNV.esm'])
    poses.vanilla, poses.mastered = {}, None
    assert poses._lookup(0x03000801) == (b'RACE', [(b'ANAM', anam)])
    assert poses._lookup(0x03000802) is None
