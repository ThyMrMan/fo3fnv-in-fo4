"""A placed decal's texture set (fo4_import.spike.decals): a slot whose texture no export layer holds is left out."""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fo4_import.spike import decals as D
from tes5_import.base.tes5_reader import subrecords


def test_a_decal_texture_in_no_archive_is_left_out_and_counted(tmp_path, monkeypatch):
    """TX00 found in the export is staged and kept; TX01 in no layer (Old World Blues' energy cell decal names a
    path no archive ships) is left out, counted, and the build goes on."""
    (tmp_path / 'textures' / 'a').mkdir(parents=True)
    (tmp_path / 'textures' / 'a' / 'here.dds').write_bytes(b'x')
    monkeypatch.setattr(D, 'export_file', lambda export_dir, rel: Path(export_dir) / rel)
    staged, written = [], []
    monkeypatch.setattr(D, 'copy_texture', lambda export_dir, data_dir, source: staged.append(source))
    decals = D.Decals.__new__(D.Decals)
    decals.dodt, decals.builder = {}, SimpleNamespace(
        export_dir=tmp_path, data_dir=None, counts=Counter(),
        writer=SimpleNamespace(add_record=lambda sig, rec: written.append(rec)))
    decals.record(0x04000800, {'FormID': '01000800', 'EditorID': 'Cell', 'TX00': 'a\\here.dds', 'TX01': 'a\\gone.dds'})
    tags = [tag for tag, _ in subrecords(written[0][24:])]
    assert staged == ['textures\\a\\here.dds'] and b'TX00' in tags and b'TX01' not in tags
    assert decals.builder.counts['decal textures in no archive (left out)'] == 1
