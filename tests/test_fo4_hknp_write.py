"""Our convex hknp writer: polytope geometry, Elric's packed mass properties, and a written physics system.

See: docs/fork/fo4_hknp_writer.md#convex
"""

import struct

import numpy as np
import pytest

from fo4_import.havok import packfile, packfile_write
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_convex, hknp_hull, hknp_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.pipeline import elric_cache
from fo4_import.nif.hknp_write import DAMPING, FILTER, FRICTION, MASS, MAX_ANGULAR, MOTION, RESTITUTION

BOX = hknp_convex.box_planes((1.0, 2.0, 3.0))
CORNERS = hknp_convex.box_corners((1.0, 2.0, 3.0))


def _body(motion: int, mass: float) -> bytes:
    """A pre-Elric rigid body's bytes with the fields the writer reads."""
    raw = bytearray(220)
    struct.pack_into('<I', raw, FILTER, 0x2A)
    struct.pack_into('<f', raw, MASS, mass)
    struct.pack_into('<2f', raw, DAMPING, 0.1, 0.05)
    struct.pack_into('<f', raw, FRICTION, 0.5)
    struct.pack_into('<f', raw, RESTITUTION, 0.4)
    struct.pack_into('<f', raw, MAX_ANGULAR, 31.4)
    raw[MOTION] = motion
    return bytes(raw)


def _system(*motions) -> dict:
    """The root fields of a system holding one box body per (motion, mass)."""
    place = (np.array([1.0, 0.0, 0.0]), (0.0, 0.0, 0.0, 1.0))
    box = lambda name: hknp_convex.polytope(name, CORNERS, 0.0, 7)
    rows = [(i, _body(m, w), box, place) for i, (m, w) in enumerate(motions)]
    data = hknp_write.system(rows)
    assert struct.unpack_from('<I', data)[0] == len(data) - 4
    return packfile.read(data[4:]).objects[0]['fields']


def test_box_has_eight_corners_and_six_ccw_faces():
    """Each face loop is four corners, counter-clockwise seen along its outward normal."""
    verts, loops, planes = hknp_convex.faces(BOX, np.zeros(3))
    assert len(verts) == 8 and len(loops) == 6
    for loop, plane in zip(loops, planes):
        a, b, c = verts[loop[:3]]
        assert np.cross(b - a, c - b) @ plane[:3] > 0


def test_angle_byte_is_the_steepest_neighbour_rise():
    """Box faces rise at 90 degrees (128); a 45-degree bevel brings the faces beside it down to 64."""
    verts, loops, planes = hknp_convex.faces(BOX, np.zeros(3))
    assert hknp_convex.angle_bytes(verts, loops, planes) == [128] * 6
    bevel = np.vstack([BOX, [*(np.array([1.0, 0.0, 1.0]) / np.sqrt(2)), -3.5 / np.sqrt(2)]])
    verts, loops, planes = hknp_convex.faces(bevel, np.zeros(3))
    bytes_ = dict(zip(map(tuple, planes[:, :3].round(3)), hknp_convex.angle_bytes(verts, loops, planes)))
    assert bytes_[(1.0, 0.0, 0.0)] == 64 and bytes_[(0.0, 0.0, 1.0)] == 64


def test_faces_over_sixteen_corners_are_trimmed():
    """A 20-sided prism's caps keep 16 corners, lean 0 on the dropped ones, and the shape loses SMALL_FACES."""
    turns = np.linspace(0, 2 * np.pi, 20, endpoint=False)
    sides = np.column_stack([np.cos(turns), np.sin(turns), np.zeros(20), -np.ones(20)])
    caps = np.array([[0.0, 0.0, 1.0, -1.0], [0.0, 0.0, -1.0, -1.0]])
    planes = np.vstack([sides, caps])
    verts, loops, planes = hknp_convex.faces(planes, np.zeros(3))
    kept = [hknp_convex.trim(verts, loop) for loop in loops]
    assert sorted(map(len, kept))[-2:] == [16, 16] and set(kept[-1]) <= set(loops[-1])
    assert sorted(hknp_convex.angle_bytes(verts, kept, planes))[:2] == [0, 0]
    objects, _ = hknp_convex.polytope('#s0', verts, 0.0, 0)
    assert objects[0]['fields']['flags'] == hknp_convex.SHAPE_FLAGS & ~hknp_convex.SMALL_FACES


def test_box_mass_is_its_volume_with_scaled_principal_inertia():
    """Density 1, Elric's 1.5x inertia, an identity frame packed as Elric packs it."""
    verts, _, planes = hknp_convex.corners(CORNERS)
    mass = hknp_convex.mass_properties(verts, planes, 0.0)
    assert mass.volume == pytest.approx(48.0)
    assert mass.inertia == pytest.approx(1.5 * 48 / 3 * np.array([13.0, 10.0, 5.0]))
    assert hknp_convex.pack_quaternion(mass.frame) == [-32768, -32768, -32768, -2768]


def test_packed_vector_shares_one_exponent():
    """The largest component sets the exponent word; the rest scale by it."""
    assert hknp_convex.pack_vector((1.0, 0.5, 0.0)) == [16384, 8192, 0, 97 << 7]


def test_half_keeps_the_top_bits_rounded():
    """hkHalf of 1.0 and of a value that rounds up."""
    assert hknp_write.half(1.0) == 0x3F80
    assert hknp_write.half(struct.unpack('<f', struct.pack('<I', 0x3F808000))[0]) == 0x3F81


def test_motions_follow_elric_per_motion_system():
    """Dynamic and massive keyframed bodies get a full motion, massless keyframed the preset, fixed none."""
    root = _system((2, 10.0), (4, 50.0), (4, 0.0), (5, 0.0))
    bodies, motions = root['bodyCinfos'], root['motionCinfos']
    assert [b['flags'] for b in bodies] == [128, 0x10080, 0, 0]
    assert [b['motionId'] for b in bodies] == [0, 1, 2, hknp_write.NO_ID]
    assert motions[0]['inverseMass'] == pytest.approx(0.1) and motions[1]['inverseMass'] == pytest.approx(0.02)
    assert motions[2]['motionPropertiesId'] == hknp_write.PRESET
    assert motions[2]['centerOfMassWorld'] == bodies[2]['position']
    assert motions[2]['orientation'] == bodies[2]['orientation']
    assert len(root['motionProperties']) == 2 and bodies[0]['collisionFilterInfo'] == 0x2A


def test_a_card_thinner_than_a_micron_has_four_corner_faces():
    """Corners go to the planes that made them: a 1e-6 thick card has 4-corner faces."""
    verts, loops, _ = hknp_convex.faces(hknp_convex.box_planes((0.05, 0.08, 7e-7)), np.zeros(3))
    assert len(verts) == 8 and sorted(map(len, loops)) == [4] * 6


def test_grid_keeps_box_corners_and_rounds_others_to_a_step():
    """Box corners stay put; any point moves at most half a step (half size / 8191)."""
    assert np.allclose(hknp_hull.grid(CORNERS), CORNERS, atol=1e-6)
    points = np.random.default_rng(1).uniform(-1, 1, (50, 3))
    assert np.abs(hknp_hull.grid(points) - points).max() <= 0.5 / 8191 * 1.001


def test_a_bent_face_merges_back_into_one():
    """A box whose top is raised 0.002 at one corner gets its two top triangles merged: six faces."""
    points = CORNERS.copy()
    points[np.argmax(points.sum(1))] += (0.0, 0.0, 0.002)
    _, loops, _ = hknp_convex.corners(points)
    assert len(loops) == 6


def _bevelled(depth: float) -> np.ndarray:
    """CORNERS with the (1, 2, 3) corner cut `depth` deep along each edge."""
    cut = [(1.0, 2.0, 3.0 - depth), (1.0, 2.0 - depth, 3.0), (1.0 - depth, 2.0, 3.0)]
    return np.vstack([CORNERS[:-1], cut])


def test_a_small_bevel_collapses_away():
    """A corner cut 0.015 deep collapses back to eight corners."""
    verts, loops, _ = hknp_convex.corners(_bevelled(0.015))
    assert len(verts) == 8 and len(loops) == 6


def test_a_degenerate_hull_keeps_every_point():
    """A 0.002 cut is a degenerate triangle: both passes skip, the cut stays."""
    assert hknp_hull.degenerate(hknp_hull.snap(_bevelled(0.002)))
    verts, loops, _ = hknp_convex.corners(_bevelled(0.002))
    assert len(verts) == 10 and len(loops) == 7


def _box_nif(*extra) -> bytes:
    """A pre-Elric NIF: a root node owning one dynamic box body, then `extra` (kind, bytes) blocks."""
    nif = NifFile()
    root = {'name': nif.string('Root'), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': 1, 'children': []}
    body = bytearray(_body(3, 5.0)) + bytes(30)
    struct.pack_into('<i', body, 0, 3)
    nif.blocks = [('NiNode', root), ('bhkCollisionObject', struct.pack('<iHi', 0, 0, 2)),
                  ('bhkRigidBody', bytes(body)), ('bhkBoxShape', struct.pack('<If8x3ff', 7, 0.01, 1, 2, 3, 0)),
                  *extra]
    return nif_file.write(nif)


def test_elric_cache_finishes_a_convex_nif_itself_and_sends_only_the_rest_to_elric(tmp_path, monkeypatch):
    """A box body is finished by our writer, never reaching Elric or its cache; a constraint we do not write still goes to Elric.

    See: docs/fork/fo4_hknp_writer.md#seam
    """
    sent = []
    monkeypatch.setattr(elric_cache, 'CACHE', tmp_path)
    monkeypatch.setattr(elric_cache, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(elric_cache.elric, 'process', lambda todo: sent.append(set(todo)) or {})
    listed = _box_nif(('bhkStiffSpringConstraint', bytes(8)))
    done = elric_cache.process({'box.nif': _box_nif(), 'list.nif': listed})
    assert sent == [{'list.nif'}] and list(done) == ['box.nif']
    kinds = [k for k, _ in nif_file.read(done['box.nif']).blocks]
    assert kinds == ['NiNode', 'bhkPhysicsSystem', 'bhkNPCollisionObject']
    assert elric_cache.entry(listed, tmp_path).read_bytes() == b''
    assert [p.name for p in tmp_path.rglob('*') if p.is_file()] == [elric_cache.entry(listed, tmp_path).name]


def test_meshes_needing_elric_wait_for_one_run_and_the_rest_finish_alone(tmp_path, monkeypatch):
    """finish(): a box is finished alone by our writer; two constraint meshes Elric's cache lacks share one run.

    See: docs/fork/fo4_build_speed.md#collision-pool
    """
    sent = []
    monkeypatch.setattr(elric_cache, 'CACHE', tmp_path / 'elric')
    monkeypatch.setattr(elric_cache.work_cache, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(elric_cache, 'MARKS', {})
    monkeypatch.setattr(elric_cache, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(elric_cache.elric, 'process', lambda todo: sent.append(sorted(todo)) or {})
    listed = _box_nif(('bhkStiffSpringConstraint', bytes(8)))
    meshes = {tmp_path / 'box.nif': _box_nif(), tmp_path / 'a.nif': listed, tmp_path / 'b.nif': listed}
    for path, data in meshes.items():
        path.write_bytes(data)
    assert elric_cache.finish(list(meshes)) == [tmp_path / 'a.nif', tmp_path / 'b.nif']
    assert sent == [['00000.nif', '00001.nif']]
    kinds = [k for k, _ in nif_file.read((tmp_path / 'box.nif').read_bytes()).blocks]
    assert kinds == ['NiNode', 'bhkPhysicsSystem', 'bhkNPCollisionObject']


def test_the_pool_finishes_meshes_as_one_process_does(tmp_path):
    """POOLED misses go to worker processes, each back with one process's bytes; every record, a worker's later
    meshes included, keeps the layout memo (packfile.classes) and holds no ragdoll or round-body code."""
    meshes = {tmp_path / f'{i}.nif': _box_nif() for i in range(elric_cache.POOLED)}
    alone = [elric_cache.finish_one(job) for job in meshes.items()]
    pooled = list(elric_cache.finished_each(meshes))
    assert [r[:3] for r in pooled] == [r[:3] for r in alone] and all(r[1] for r in pooled)
    for record in (r[3] for r in pooled):
        assert 'fo4_import/havok/packfile.py::classes' in record
        assert not [k for k in record if k.startswith(('fo4_import/nif/hknp_ragdoll', 'fo4_import/nif/hknp_round'))]


def test_a_flat_box_is_left_to_elric():
    """A box with no height has no 3-D hull: not covered, so Elric gets it.

    See: docs/fork/fo4_hknp_writer.md#flat
    """
    nif = nif_file.read(_box_nif())
    nif.blocks[3] = ('bhkBoxShape', struct.pack('<If8x3ff', 7, 0.01, 1, 2, 0, 0))
    assert hknp_write.physics(nif) is None


def test_bs_material_entries_sit_0x18_apart_as_elric_writes_them():
    """Bethesda's material table: entries from +0x20, 0x18 apart, filter then CRC after 16 zero bytes.

    See: docs/fork/fo4_hknp_writer.md#bs-material
    """
    rows = [(1, 0x064003D4), (0x2001, 0xDF02F237)]
    entries = [{'reserved': [0, 0], 'collisionFilterInfo': f, 'materialCrc': c} for f, c in rows]
    objects = [{'#': '#m', 'class': 'hknpBSMaterialProperties', 'fields': {'materials': entries}}]
    pf = packfile.read(packfile_write.write(objects, '#m'))
    assert pf.objects[0]['fields']['materials'] == entries
    at = pf.base + pf.virtual[0][0]
    for i, row in enumerate(rows):
        assert pf.data[at + 0x20 + i * 0x18:at + 0x30 + i * 0x18] == bytes(16)
        assert struct.unpack_from('<2I', pf.data, at + 0x30 + i * 0x18) == row
