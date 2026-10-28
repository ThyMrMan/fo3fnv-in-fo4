"""The Havok 2014 packfile reader and writer against vanilla Fallout 4 files: each rebuilt byte for byte."""

import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok import packfile, packfile_write

DATA = FALLOUT4_DIR / 'Data'
VANILLA = ['meshes\\actors\\molerat\\behaviors\\moleratrootbehavior.hkx',
           'meshes\\actors\\radroach\\behaviors\\radroachrootbehavior.hkx',
           'meshes\\actors\\shared\\behaviors\\moleratsharedcorewrappingbehavior.hkx',
           'meshes\\actors\\molerat\\characters\\moleratcharacter.hkx',
           'meshes\\actors\\molerat\\moleratproject.hkx',
           'meshes\\actors\\molerat\\characterassets\\skeleton.hkx']


@pytest.fixture(scope='module')
def meshes():
    """The game's archives (the tests skip without them)."""
    if not (DATA / 'Fallout4 - Meshes.ba2').exists():
        pytest.skip('Fallout 4 is not installed')
    return Archives(DATA)


@pytest.mark.parametrize('name', VANILLA)
def test_vanilla_rebuilds_byte_for_byte(meshes, name):
    """Reading then writing a vanilla file gives its exact bytes."""
    data = meshes.read(name)
    pf = packfile.read(data)
    assert packfile_write.write(pf.objects, pf.objects[0]['#'], extension=pf.extension,
                                keep_order=pf.extension) == data


def test_skeleton_ragdoll_shapes_keep_their_inline_data(meshes):
    """A capsule's vertices and planes past its class size survive the round trip."""
    pf = packfile.read(meshes.read(VANILLA[-1]))
    capsules = [o for o in pf.objects if o['class'] == 'hknpCapsuleShape']
    assert capsules and all(len(o['fields']['__tail__']) == 312 for o in capsules)


def test_only_decodes_the_named_classes(meshes):
    """`only` decodes just its classes' objects; the rest keep their names and classes with no fields."""
    pf = packfile.read(meshes.read(VANILLA[-1]), only=frozenset({'hknpRagdollData'}))
    decoded = {o['class'] for o in pf.objects if o['fields']}
    assert decoded == {'hknpRagdollData'} and any(o['class'] == 'hknpCapsuleShape' for o in pf.objects)
