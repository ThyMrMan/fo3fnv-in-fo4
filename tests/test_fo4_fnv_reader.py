"""fnv_reader reads an FNV NIF as pyffi does, field for field, with its number arrays as numpy written through;
fnv_file.read uses it, pyffi as the fallback; convert_static makes the same FO4 mesh from either read.

See: docs/fork/research/fnv_nif_reader.md#proof
"""

from pathlib import Path

import pytest

from fo4_import.nif import fnv_file, fnv_reader
from fo4_import.nif.fnv_schema import FORMAT, LAYOUTS_PATH, NifFormat, klass
from tools.generators import gen_fnv_nif_layouts
from tools.nif import fnv_convert_check
from tools.nif.fnv_reader_check import compare

MESHES = Path('export/FalloutNV.esm/meshes')
#: A static with packed collision, a skinned mesh, an animated sign (controller sequences).
SAMPLES = ('furniture/shelveswoodenhalf02.nif', 'clutter/skeleton/gorycorpseparts.nif', 'clutter/signnv/nvposter09.nif')
needs_export = pytest.mark.skipif(not MESHES.exists(), reason='needs the FalloutNV.esm export')


def test_the_frozen_layouts_are_pyffis():
    """fnv_layouts.json is what the generator makes from today's patched pyffi."""
    assert gen_fnv_nif_layouts.text() == LAYOUTS_PATH.read_text(encoding='utf-8')


def test_our_classes_and_pyffis_accept_each_others_instances():
    """isinstance() holds both ways, and retyping ours to a pyffi class keeps it ours."""
    node, theirs = klass('NiNode')(), NifFormat.NiNode()
    assert isinstance(node, NifFormat.NiAVObject) and isinstance(theirs, FORMAT.NiAVObject)
    assert not isinstance(node, NifFormat.NiTriShape)
    node.__class__ = NifFormat.BSFadeNode
    assert type(node) is FORMAT.BSFadeNode


@needs_export
@pytest.mark.parametrize('name', SAMPLES)
def test_every_field_reads_as_pyffi_reads_it(name):
    """No field differs from pyffi's read, links and get_refs order included."""
    result = compare(str(MESHES / name))
    assert (result['diffs'], result['first'], result['skipped'], result['resized']) == (0, [], [], [])


@needs_export
def test_the_tree_walks_as_pyffi_and_arrays_are_numpy_written_through():
    """tree() order matches pyffi's; vertices are one float64 array; a write lands in it."""
    path = MESHES / SAMPLES[0]
    theirs, ours = fnv_file.read_pyffi(path), fnv_file.read(path)
    assert [type(b).__name__ for b in ours.roots[0].tree()] == [type(b).__name__ for b in theirs.roots[0].tree()]
    data = next(b for b in ours.blocks if isinstance(b, NifFormat.NiTriBasedGeomData))
    mine = next(b for b in theirs.blocks if type(b).__name__ == type(data).__name__)
    assert [(v.x, v.y, v.z) for v in data.vertices] == [(v.x, v.y, v.z) for v in mine.vertices]
    assert data.get_triangles() == mine.get_triangles()
    data.vertices[0].x = 0.1
    assert data.vertices.array['x'][0] == 0.1 and data.vertices[0] == data.vertices[0]


@needs_export
def test_a_file_with_a_block_skipped_reads_with_pyffi(monkeypatch):
    """fnv_file.read falls back to pyffi when our reader skipped a block."""
    skipped = fnv_reader.NifData(0, 0, 0, [], skipped=[(0, 'NiNode', 'test')])
    monkeypatch.setattr(fnv_reader, 'read', lambda path: skipped)
    assert type(fnv_file.read(MESHES / SAMPLES[0])) is fnv_file.Data


@needs_export
def test_convert_static_makes_the_same_mesh_from_either_read(monkeypatch):
    """The FO4 NIF bytes and every material and texture named are the same."""
    path = str(MESHES / SAMPLES[2])
    ours = fnv_convert_check.digest(fnv_convert_check.run_static(path))
    monkeypatch.setattr(fnv_file, 'read', fnv_file.read_pyffi)
    assert fnv_convert_check.digest(fnv_convert_check.run_static(path)) == ours
