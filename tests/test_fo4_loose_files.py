"""Loose files out of the Data folder: archived copies dropped after a build and restored before the next
(ba2_pack), master folders read through their archives, and the build's records in build_files.BOOKS.

See: docs/fork/fo4_pipeline.md#main-archive
See: docs/fork/fo4_pipeline.md#build-files
"""

import os
import shutil

from fo4_import.base import ba2_pack as BP
from fo4_import.base import build_files as BF
from fo4_import.base.ba2 import Archive
from fo4_import.base.ledger import ledger_path
from fo4_import.spike import facegen
from fo4_import.spike.script import adopted_scripts

FILES = {'Meshes/fnv/Cup.nif': b'cup', 'Materials/fnv/a.bgsm': b'm', 'Scripts/A.pex': b'pex',
         'Meshes/AnimTextData/AnimationOffsets/PersistantSubgraphInfoAndOffsetData.txt': b'1.txt\n'}


def _packed(tmp_path, monkeypatch):
    """A data folder whose FILES (and one LUT kept loose) are packed into P.esm's Main archive."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    data = tmp_path / 'data'
    for name, payload in {**FILES, 'Textures/Effects/LUTs/FNV/lut.dds': b'lut', 'Scripts/compile_state.json': b'{}'}.items():
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).write_bytes(payload)
    assert BP.pack_main(data, 'P.esm') == len(FILES)
    return data


def test_drop_then_restore_brings_back_what_the_main_archive_holds(tmp_path, monkeypatch):
    """drop_packed takes the loose copies the archives hold out (and the folders left empty), not other files;
    with no stash, restore_packed writes them back, spelled as the archive stores them and dated as the archive,
    so a build neither counts them as made nor finds them missing from its last file list (stale_files compares
    spellings)."""
    data = _packed(tmp_path, monkeypatch)
    assert BP.drop_packed(data, 'P.esm') == len(FILES)
    assert not (data / 'Meshes').exists() and not (data / 'Materials').exists()
    assert (data / 'Scripts' / 'compile_state.json').is_file() and (data / 'Textures/Effects/LUTs/FNV/lut.dds').is_file()
    shutil.rmtree(BP.stash_dir(data, 'P.esm'))
    assert BP.restore_packed(data, 'P.esm') == len(FILES)
    assert all((data / name).read_bytes() == payload for name, payload in FILES.items())
    assert os.listdir(data / 'Meshes') == ['AnimTextData', 'fnv'] and os.listdir(data / 'Meshes' / 'fnv') == ['Cup.nif']
    archive_time = (data / 'P - Main.ba2').stat().st_mtime
    assert abs(os.stat(data / 'Meshes/fnv/Cup.nif').st_mtime - archive_time) < 1
    assert BP.restore_packed(data, 'P.esm') == 0


def test_a_master_folder_is_read_through_its_archives(tmp_path, monkeypatch):
    """data_file and adopted_scripts find a packed master's files in its archive: a script it ships compiled is
    not adopted, one it lacks is."""
    data = _packed(tmp_path, monkeypatch)
    BP.drop_packed(data, 'P.esm')
    persistent = 'Meshes/AnimTextData/AnimationOffsets/PersistantSubgraphInfoAndOffsetData.txt'
    assert BP.data_file(data, persistent) == FILES[persistent] and BP.data_file(data, 'Meshes/none.nif') is None
    sources = tmp_path / 'psc'
    sources.mkdir()
    for name in ('A', 'B'):
        (sources / f'{name}.psc').write_text('x')
    assert adopted_scripts(['A', 'B'], (sources,), (data,)) == [sources / 'B.psc']


def test_data_file_indexes_each_archive_once_while_it_is_unchanged(tmp_path, monkeypatch):
    """Reads through a master's archive parse its index once; a repacked archive is indexed again."""
    data = _packed(tmp_path, monkeypatch)
    BP.drop_packed(data, 'P.esm')
    opened = []
    monkeypatch.setattr(BP, 'Archive', lambda path: opened.append(path) or Archive(path))
    for name, payload in FILES.items():
        assert BP.data_file(data, name) == payload
    assert len(opened) == 1
    BP.restore_packed(data, 'P.esm')
    (data / 'Scripts' / 'B.pex').write_bytes(b'b')
    BP.pack_main(data, 'P.esm')
    BP.drop_packed(data, 'P.esm')
    before = len(opened)
    assert BP.data_file(data, 'Scripts/B.pex') == b'b' and BP.data_file(data, 'Scripts/A.pex') == b'pex'
    assert len(opened) == before + 1


def test_records_move_into_the_records_folder_and_the_newer_one_wins(tmp_path):
    """moved_in moves an old record beside the plugin into BOOKS; with both there, the newer one stays."""
    old = tmp_path / 'P.formids.tsv'
    old.write_text('old ledger')
    assert ledger_path(tmp_path / 'P.esm') == tmp_path / BF.BOOKS / 'P.formids.tsv'
    assert not old.exists() and (tmp_path / BF.BOOKS / 'P.formids.tsv').read_text() == 'old ledger'
    old.write_text('stale copy')
    os.utime(old, (1, 1))
    assert BF.moved_in(old).read_text() == 'old ledger' and not old.exists()
    old.write_text('newer copy')
    assert BF.moved_in(old).read_text() == 'newer copy' and not old.exists()
    assert BF.moved_in(tmp_path / 'none.txt') == tmp_path / BF.BOOKS / 'none.txt'


def test_a_faces_run_packs_its_textures_without_pruning_the_builds(tmp_path, monkeypatch):
    """pack_textures(prune=False) (the faces stage, which stages no texture) keeps the build's staged textures and
    their signatures, and packs the new face texture with them."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    monkeypatch.setattr(BP, 'write_textures', lambda named, archive, kept: archive.write_bytes(b'x'))
    data = tmp_path / 'data'
    assert BP.stage_texture(data, 'fnv/a.dds', lambda: ('sig-a', lambda target: target.write_bytes(b'a')))
    assert BP.pack_textures(data, 'P.esm') == 1
    face = data / 'Textures/Actors/Character/FaceCustomization/P.esm/00001234_d.dds'
    face.parent.mkdir(parents=True)
    face.write_bytes(b'f')
    assert BP.pack_textures(data, 'P.esm', prune=False) == 2 and not face.exists()
    manifest = BP._read_json(BP.staging_root(data) / BP.MANIFEST)
    assert manifest['fnv/a.dds'][2] == 'sig-a'


FACE = 'Meshes/Actors/Character/FaceGenData/FaceGeom/P.esm/'


def test_a_faces_run_repacks_main_without_restoring_it(tmp_path, monkeypatch):
    """With the FaceGeom folder replaced, pack_main keeps Main's other entries as packed (nothing restored loose)
    and swaps the old faces for the loose new ones; faces written again unchanged leave Main as it is; a record
    that no longer matches the archive gives None."""
    data = _packed(tmp_path, monkeypatch)
    (data / FACE).mkdir(parents=True)
    (data / FACE / '00000001.nif').write_bytes(b'old face')
    BP.pack_main(data, 'P.esm')
    BP.drop_packed(data, 'P.esm')
    main = data / 'P - Main.ba2'
    replaced = (FACE.lower(),)
    assert set(BP.archived(main)) == {*FILES, FACE + '00000001.nif'}
    (data / FACE).mkdir(parents=True)
    (data / FACE / '00000002.nif').write_bytes(b'new face')
    assert BP.pack_main(data, 'P.esm', replaced) == len(FILES) + 1
    assert not (data / 'Meshes/fnv/Cup.nif').exists()
    packed = Archive(main)
    assert {name: packed.read(name.lower().replace('/', chr(92))) for name in FILES} == FILES
    assert packed.read((FACE + '00000002.nif').lower().replace('/', chr(92))) == b'new face'
    assert (FACE + '00000001.nif').lower().replace('/', chr(92)) not in packed.entries
    assert set(BP.archived(main)) == {*FILES, FACE + '00000002.nif'}
    BP.drop_packed(data, 'P.esm')
    (data / FACE).mkdir(parents=True)
    (data / FACE / '00000002.nif').write_bytes(b'new face')
    when = main.stat().st_mtime_ns
    assert BP.pack_main(data, 'P.esm', replaced) == len(FILES) + 1 and main.stat().st_mtime_ns == when
    os.utime(main, ns=(1, 1))
    assert BP.archived(main) is None


def test_a_face_texture_written_again_unchanged_keeps_its_staged_copy(tmp_path, monkeypatch):
    """A loose texture with the same bytes as its staged copy is deleted, so the copy keeps its time and the pack
    sees nothing changed; a changed one replaces the copy."""
    monkeypatch.setattr(BP, 'STAGING_CACHE', tmp_path / 'cache')
    written = []
    monkeypatch.setattr(BP, 'write_textures', lambda named, archive, kept: written.append(1) or archive.write_bytes(b'x'))
    data = tmp_path / 'data'
    face = data / 'Textures/Actors/Character/FaceCustomization/P.esm/00001234_d.dds'
    face.parent.mkdir(parents=True)
    face.write_bytes(b'f')
    assert BP.pack_textures(data, 'P.esm', prune=False) == 1
    staged = BP.staging_root(data) / face.relative_to(data)
    before = staged.stat().st_mtime_ns
    face.write_bytes(b'f')
    assert BP.pack_textures(data, 'P.esm', prune=False) == 1 and not face.exists()
    assert staged.stat().st_mtime_ns == before and len(written) == 1
    face.write_bytes(b'g')
    BP.pack_textures(data, 'P.esm', prune=False)
    assert staged.read_bytes() == b'g' and len(written) == 2


def test_a_build_that_rewrites_the_same_bytes_leaves_main_as_it_is(tmp_path, monkeypatch):
    """Restored files touched by the build (write_new) but holding the same bytes keep Main unwritten; a file with
    new bytes of the same size is packed anew."""
    data = _packed(tmp_path, monkeypatch)
    main = data / 'P - Main.ba2'
    BP.drop_packed(data, 'P.esm')
    BP.restore_packed(data, 'P.esm')
    for name in FILES:
        os.utime(data / name)
    when = main.stat().st_mtime_ns
    assert BP.pack_main(data, 'P.esm') == len(FILES) and main.stat().st_mtime_ns == when
    (data / 'Scripts/A.pex').write_bytes(b'PEX')
    BP.pack_main(data, 'P.esm')
    assert main.stat().st_mtime_ns != when and Archive(main).read('scripts/a.pex') == b'PEX'
    assert Archive(main).read('materials/fnv/a.bgsm') == b'm'


def test_the_loose_copies_wait_in_the_stash_with_their_dates(tmp_path, monkeypatch):
    """drop_packed moves Main's loose files into stash_dir (outside the Data folder) and restore_packed moves
    them back with their own dates, the stash gone; the faces stage's restore() takes them back too."""
    data = _packed(tmp_path, monkeypatch)
    dated = {name: (data / name).stat().st_mtime_ns for name in FILES}
    BP.drop_packed(data, 'P.esm')
    stash = BP.stash_dir(data, 'P.esm')
    assert BP.stashed(data, 'P.esm') and not stash.is_relative_to(data)
    assert {name: (stash / name).read_bytes() for name in FILES} == FILES
    assert facegen.restore(data, 'P.esm') == len(FILES) and not stash.exists()
    assert {name: (data / name).stat().st_mtime_ns for name in FILES} == dated
    assert {name: (data / name).read_bytes() for name in FILES} == FILES


def test_a_stash_the_archive_moved_on_from_is_not_used(tmp_path, monkeypatch):
    """A stash whose stamp no longer matches the Main archive is deleted and the archive restores the files;
    loose files that are not exactly the archive's PACKED entries are deleted, not stashed."""
    data = _packed(tmp_path, monkeypatch)
    BP.drop_packed(data, 'P.esm')
    stash, main = BP.stash_dir(data, 'P.esm'), data / 'P - Main.ba2'
    (stash / 'Scripts/A.pex').write_bytes(b'stale')
    os.utime(main, ns=(1, 1))
    assert not BP.stashed(data, 'P.esm') and BP.restore_packed(data, 'P.esm') == len(FILES)
    assert (data / 'Scripts/A.pex').read_bytes() == b'pex' and not stash.exists()
    (data / 'Meshes/fnv/Extra.nif').write_bytes(b'not packed')
    BP.drop_packed(data, 'P.esm')
    assert not stash.exists() and not (data / 'Meshes/fnv/Cup.nif').exists()
