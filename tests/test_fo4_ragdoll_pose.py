"""A placed dead actor's ragdoll pose, FNV's onto FO4's skeleton (fo4_import.spike.ragdoll_pose)."""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, source_walk
from fo4_import.spike import ragdoll_pose as P
from fo4_import.spike.scol import angles, rotation
from tes5_import.base.tes5_reader import subrecords, walk

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
def test_feral_ghouls_map_every_body_and_a_brahmin_maps_too_few_to_write():
    """FNV's ghoul skeleton finds a source for all 18 of FO4's feral ghoul bodies (FERAL_GHOUL); FNV's brahmin
    finds under MAPPED_SHARE of FO4's 39."""
    ar = Archives(FALLOUT4_DIR / 'Data')
    for fnv_model, fo4_model, enough in (('Creatures\\Ghoul\\Skeleton.nif', 'Actors\\FeralGhoul\\CharacterAssets\\skeleton.nif', True),
                                         ('Creatures\\Brahmin\\Skeleton.nif', 'Actors\\Brahmin\\CharacterAssets\\Skeleton.nif', False)):
        fnv = P.fnv_skeleton(EXPORT / 'meshes' / fnv_model.lower().replace('\\', '/'))
        fo4 = P.fo4_skeleton(ar.read('meshes\\' + fo4_model.lower()))
        share = len(P.sources(fnv, fo4, P.bone_map(fnv_model, fo4_model))) / len(fo4.bodies)
        assert (share >= P.MAPPED_SHARE) == enough, fnv_model


def test_a_race_skeleton_follows_a_traits_template_and_a_lists_first_entry():
    """NPC 1 takes traits from list 2, whose first entry NPC 3 is race 4: its male skeleton (ANAM after MNAM).
    ACBS holds the template flags at byte 14."""
    acbs = lambda flags: bytes(14) + struct.pack('<H', flags) + bytes(4)
    recs = {1: (b'NPC_', [(b'ACBS', acbs(P.USE_TRAITS)), (b'TPLT', struct.pack('<I', 2))]),
            2: (b'LVLN', [(b'LVLO', struct.pack('<HHI', 1, 0, 3))]),
            3: (b'NPC_', [(b'ACBS', acbs(0)), (b'RNAM', struct.pack('<I', 4))]),
            4: (b'RACE', [(b'ANAM', b'nope\0'), (b'MNAM', b''), (b'ANAM', b'Actors\\X\\skeleton.nif\0')])}
    assert P.race_skeleton(recs.get, 1) == 'Actors\\X\\skeleton.nif'
