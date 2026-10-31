"""A plugin renamed between builds: its old folders moved, its old file dropped (spike.plugin_rename)."""

from fo4_import.spike import plugin_rename as PR


def test_a_renamed_plugins_voice_folder_moves_once_and_the_old_file_goes(tmp_path):
    """Sound/Voice/FalloutNV.esp becomes FalloutNV.esm, files kept; an existing new folder is left alone."""
    voice = tmp_path / 'Sound' / 'Voice'
    (voice / 'FalloutNV.esp' / 'MaleAdult').mkdir(parents=True)
    (voice / 'FalloutNV.esp' / 'MaleAdult' / 'a.fuz').write_bytes(b'x')
    (tmp_path / 'FalloutNV.esp').write_bytes(b'old')
    (tmp_path / 'FalloutNV.esp.files.txt').write_text('x')
    (tmp_path / 'FalloutNV.formids.tsv').write_text('x')
    assert PR.move_renamed('FalloutNV.esm', [voice, tmp_path / 'missing']) == 1
    assert (voice / 'FalloutNV.esm' / 'MaleAdult' / 'a.fuz').read_bytes() == b'x'
    (voice / 'FalloutNV.esp').mkdir()
    assert PR.move_renamed('FalloutNV.esm', [voice]) == 0
    assert PR.drop_old_plugins(tmp_path, 'FalloutNV.esm') == 2 and not (tmp_path / 'FalloutNV.esp').exists()
    assert (tmp_path / 'FalloutNV.formids.tsv').exists()
    assert PR.is_master('FalloutNV.esm') and not PR.is_master('FalloutNV.esp')


def test_a_facegen_nif_points_at_the_renamed_plugins_textures(tmp_path):
    """The texture path's FalloutNV.esp folder becomes FalloutNV.esm in place, same length; other bytes kept."""
    nif = tmp_path / '001A8DD5.NIF'
    old = b'x\x30\x00' + rb'Data\Textures\Actors\Character\FaceCustomization\FalloutNV.esp\001A8DD5_d.dds' + b'y'
    nif.write_bytes(old)
    assert PR.retarget_faces(tmp_path, 'FalloutNV.esm') == 1
    assert nif.read_bytes() == old.replace(b'FalloutNV.esp', b'FalloutNV.esm')
    assert PR.retarget_faces(tmp_path, 'FalloutNV.esm') == 0
