"""fnv_reader reads an FNV NIF as pyffi does, field for field, with its number arrays as numpy; convert_static
makes the same FO4 mesh from either read.

See: docs/fork/research/fnv_nif_reader.md#proof
"""

from pathlib import Path

import pytest

from fo4_import.nif.fnv_schema import FORMAT
from fo4_import.nif import fnv_file, fnv_reader
from tools.nif import fnv_convert_check
from tools.nif.fnv_reader_check import compare

MESHES = Path('export/FalloutNV.esm/meshes')
#: A static with packed collision, a skinned mesh, an animated sign (controller sequences).
SAMPLES = ('furniture/shelveswoodenhalf02.nif', 'clutter/skeleton/gorycorpseparts.nif', 'clutter/signnv/nvposter09.nif')
needs_export = pytest.mark.skipif(not MESHES.exists(), reason='needs the FalloutNV.esm export')


@needs_export
@pytest.mark.parametrize('name', SAMPLES)
def test_every_field_reads_as_pyffi_reads_it(name):
    """No field differs from pyffi's read, links and get_refs order included."""
    result = compare(str(MESHES / name))
    assert (result['diffs'], result['first'], result['skipped'], result['resized']) == (0, [], [], [])


@needs_export
def test_the_tree_walks_as_pyffi_and_arrays_are_numpy():
    """tree() order matches pyffi's; a shape's vertices are one float32 array, readable per element as pyffi's."""
    path = MESHES / SAMPLES[0]
    theirs, ours = fnv_file.read(path), fnv_reader.read(path)
    assert [type(b).__name__ for b in ours.roots[0].tree()] == [type(b).__name__ for b in theirs.roots[0].tree()]
    data = next(b for b in ours.blocks if isinstance(b, FORMAT.NiTriBasedGeomData))
    mine = next(b for b in theirs.blocks if type(b).__name__ == type(data).__name__)
    assert data.vertices.array.dtype.names == ('x', 'y', 'z')
    assert [(v.x, v.y, v.z) for v in data.vertices] == [(v.x, v.y, v.z) for v in mine.vertices]
    assert data.get_triangles() == mine.get_triangles()


@needs_export
def test_convert_static_makes_the_same_mesh_from_either_read():
    """The FO4 NIF bytes and every material and texture named are the same."""
    result = fnv_convert_check.check(str(MESHES / SAMPLES[2]))
    assert (result['same'], result['pyffi_error']) == (True, None)
