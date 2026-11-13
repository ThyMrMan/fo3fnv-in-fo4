"""Our compressed-mesh writer: quads, sections, coded boxes, and a mesh written, read back and decoded.

See: docs/fork/fo4_hknp_writer.md#mesh
"""

import struct

import numpy as np

from fo4_import.havok import packfile, packfile_write
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_mesh, hknp_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.collision import tri_strips_data
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_write import MASS, MOTION

FILTERS = (1, 0x2001)
CRCS = (0x064003D4, 0xDF02F237)


def _grid(n: int) -> hknp_mesh.Mesh:
    """An n × n grid of unit squares, two triangles each, bumped in z; the right half on strip 1."""
    xs, ys = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
    points = np.column_stack([xs.ravel(), ys.ravel(), np.sin(xs.ravel() * 0.7) * 0.3]).astype(float) * 0.25
    tris, strip = [], []
    for i in range(n):
        for j in range(n):
            a, b, c, d = i * (n + 1) + j, (i + 1) * (n + 1) + j, (i + 1) * (n + 1) + j + 1, i * (n + 1) + j + 1
            tris += [(a, b, c), (a, c, d)]
            strip += [int(i >= n // 2)] * 2
    return hknp_mesh.Mesh(points, np.array(tris), np.array(strip), list(zip(FILTERS, CRCS)))


def _written(mesh: hknp_mesh.Mesh) -> dict:
    """{class: fields} of `mesh`'s objects after a packfile write and read."""
    objects = hknp_mesh.compressed('#s0', mesh)
    return {o['class']: o['fields'] for o in packfile.read(packfile_write.write(objects, '#s0')).objects}


def _canonical(tris: np.ndarray) -> np.ndarray:
    """Sorted triangles, each its smallest rotation, rounded to 3 places."""
    return np.array(sorted(min(tuple(np.roll(t, -k, 0).round(3).ravel()) for k in range(3)) for t in tris))


def test_a_grid_round_trips_through_several_sections():
    """A 20 × 20 grid (800 triangles) writes, reads back and decodes to its own triangles and strips."""
    mesh = _grid(20)
    written = _written(mesh)
    tree = written['hknpCompressedMeshShapeData']['meshTree']
    assert len(tree['sections']) > 1
    tris, materials = hknp_mesh.triangles(tree)
    assert np.allclose(_canonical(tris), _canonical(mesh.points[mesh.tris]), atol=2e-3)
    assert sorted(materials.tolist()) == sorted(mesh.strip.tolist())
    assert tree['numPrimitiveKeys'] == 800
    assert written['hknpBSMaterialProperties']['materials'][1]['materialCrc'] == CRCS[1]


def test_sections_keep_their_limits_and_name_their_tree_leaf():
    """Each section holds at most 128 primitives and 255 vertices and points back at its own leaf."""
    tree = _written(_grid(20))['hknpCompressedMeshShapeData']['meshTree']
    for index, section in enumerate(tree['sections']):
        assert section['primitives']['data'] & 0xFF <= hknp_mesh.SECTION_PRIMITIVES
        assert section['numPackedVertices'] <= hknp_mesh.SECTION_VERTICES
        leaf = tree['nodes'][section['leafIndex']]
        assert leaf['hiData'] << 8 | leaf['loData'] == index


def test_keys_and_bit_fields_are_sized_as_elric_sizes_them():
    """Interior bits: largest key + 1; flat bits: half that, rounded up; no stray bits past the end."""
    written = _written(_grid(20))
    shape, tree = written['hknpCompressedMeshShape'], written['hknpCompressedMeshShapeData']['meshTree']
    assert tree['maxKeyValue'] < 1 << shape['numShapeKeyBits']
    assert shape['triangleIsInterior']['storage']['numBits'] == tree['maxKeyValue'] + 1
    flat = shape['quadIsFlat']['storage']
    assert flat['numBits'] == (tree['maxKeyValue'] + 2) // 2
    assert flat['words'][-1] >> (flat['numBits'] - 32 * (len(flat['words']) - 1)) == 0


def test_two_triangles_on_an_edge_make_one_flat_quad():
    """A square's two triangles pair as (a, b, c) and (a, c, d); one on another strip stays alone, c repeated."""
    points = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [5, 5, 5]])
    mesh = hknp_mesh.Mesh(points, np.array([(0, 1, 2), (0, 2, 3), (1, 4, 2)]), np.array([0, 0, 1]), [(1, 2)] * 2)
    (square, _), (lone, _) = hknp_mesh.quads(mesh)
    assert square == [0, 1, 2, 3] and hknp_mesh.flat(points, square)
    assert lone == [1, 4, 2, 2]


def test_a_quad_the_game_would_fill_in_stays_two_triangles():
    """The game collides a quad as its corners' hull: two coplanar triangles making a dart (a doorway's jamb and
    lintel) and two meeting at a fold (a wall and its floor) each stay single, so no hull covers an opening."""
    points = np.array([[0.0, 0, 0], [2, 0, 0], [0.8, 0.8, 0], [0, 2, 0], [-0.5, 0.5, 1]])
    for far in (3, 4):
        mesh = hknp_mesh.Mesh(points, np.array([(0, 1, 2), (0, 2, far)]), np.array([0, 0]), [(1, 2)])
        assert [prim for prim, _ in hknp_mesh.quads(mesh)] == [[0, 1, 2, 2], [0, 2, far, far]]


def test_a_coded_box_holds_the_box_it_codes():
    """Square-root insets round toward the parent, so the decoded box always contains the original."""
    rng = np.random.default_rng(3)
    parent = (np.zeros(3), np.array([4.0, 2.0, 1.0]))
    for _ in range(200):
        lo, hi = np.sort(rng.uniform(parent[0], parent[1], (2, 3)), 0)
        _, (dlo, dhi) = hknp_mesh.coded((lo, hi), parent)
        assert (dlo <= lo).all() and (dhi >= hi).all()


def _mesh_nif(motion: int, mass: float) -> NifFile:
    """A pre-Elric NIF: a root node owning one body of `motion` and `mass` on a two-strip square mesh."""
    nif = NifFile()
    root = {'name': nif.string('Root'), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': 1, 'children': []}
    body = bytearray(250)
    struct.pack_into('<i', body, 0, 3)
    struct.pack_into('<f', body, MASS, mass)
    body[MOTION] = motion
    square = [(0.0, 0.0, 0.0), (70.0, 0.0, 0.0), (70.0, 70.0, 0.0), (0.0, 70.0, 0.0)]
    shape = struct.pack('<If20xI4fI', CRCS[0], 0.01, 1, 1.0, 1.0, 1.0, 0.0, 2)
    shape += struct.pack('<2iI', 4, 5, 2) + struct.pack('<2I', *FILTERS)
    nif.blocks = [('NiNode', root), ('bhkCollisionObject', struct.pack('<iHi', 0, 0, 2)),
                  ('bhkRigidBody', bytes(body)), ('bhkNiTriStripsShape', shape),
                  ('NiTriStripsData', tri_strips_data(square, [(0, 1, 2)], CRCS[0])),
                  ('NiTriStripsData', tri_strips_data(square, [(0, 2, 3)], CRCS[1]))]
    return nif_file.read(nif_file.write(nif))


def test_a_fixed_mesh_body_gets_a_compressed_mesh_and_a_dynamic_one_goes_to_elric():
    """Our strips read back as Havok-unit triangles, one strip each; a body with a full motion is not covered."""
    block, owners = hknp_write.physics(_mesh_nif(hknp_write.FIXED, 0.0))
    classes = {o['class']: o['fields'] for o in packfile.read(block[4:]).objects}
    tris, materials = hknp_mesh.triangles(classes['hknpCompressedMeshShapeData']['meshTree'])
    assert owners == [0] and sorted(materials.tolist()) == [0, 1]
    assert np.allclose(tris.reshape(-1, 3).max(0), [70 / hknp_mesh.GAME_PER_HAVOK] * 2 + [0.0], atol=1e-6)
    assert classes['hknpCompressedMeshShape']['userData'] == CRCS[0]
    assert hknp_write.physics(_mesh_nif(3, 5.0)) is None
