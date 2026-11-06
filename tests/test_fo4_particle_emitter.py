"""A particle mesh emitter linking another particle system (pyffi Patch 17, fo4_import.nif.particles._shape)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.nif import convert_static
from fo4_import.nif import particles as P
from pyffi.formats.nif import NifFormat


NUKE = Path(__file__).resolve().parents[1] / 'export/LonesomeRoad.esm/meshes/nvdlc04/effects/nvdlc04_wastelandnukeexp.nif'


def test_a_mesh_emitters_meshes_are_pointers_to_any_scene_object():
    """Patch 17: Emitter Meshes are Ptrs to NiAVObject (current nif.xml)."""
    assert convert_static is not None
    attr = next(a for a in NifFormat.NiPSysMeshEmitter._attrs if a.name == 'emitter_meshes')
    assert attr.type_ is NifFormat.Ptr and attr.template is NifFormat.NiAVObject


@pytest.mark.skipif(not NUKE.exists(), reason="needs Lonesome Road's export")
def test_lonesome_roads_nuke_explosion_reads_and_converts():
    """A mesh emitting from a particle system reads and converts."""
    assert type(convert_static.convert(str(NUKE), NUKE.parents[3], None, True, None)).__name__ == 'Converted'


def test_only_an_emitter_mesh_with_triangles_is_converted():
    """_shape(): a triangle shape, not a particle system or no link."""
    assert P._shape(SimpleNamespace(data=SimpleNamespace(get_triangles=list)))
    assert not P._shape(SimpleNamespace(data=SimpleNamespace()))
    assert not P._shape(None)
