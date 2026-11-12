"""Loose files out of the Data folder: archived copies dropped after a build and restored before the next
(ba2_pack), master folders read through their archives, and the build's records in build_files.BOOKS.

See: docs/fork/fo4_pipeline.md#main-archive
See: docs/fork/fo4_pipeline.md#build-files
"""

import os

from fo4_import.base import ba2_pack as BP
from fo4_import.base import build_files as BF
from fo4_import.base.ledger import ledger_path
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
    """drop_packed deletes the loose copies the archives hold (and the folders left empty), not other files;
    restore_packed writes them back, spelled as the archive stores them and dated as the archive, so a build
    neither counts them as made nor finds them missing from its last file list (stale_files compares spellings)."""
    data = _packed(tmp_path, monkeypatch)
    assert BP.drop_packed(data, 'P.esm') == len(FILES)
    assert not (data / 'Meshes').exists() and not (data / 'Materials').exists()
    assert (data / 'Scripts' / 'compile_state.json').is_file() and (data / 'Textures/Effects/LUTs/FNV/lut.dds').is_file()
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
