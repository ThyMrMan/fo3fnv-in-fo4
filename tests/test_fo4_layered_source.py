"""A source plugin read with its master: the layered export and binary source (export_index, install)."""

import pytest

from fo4_import.base import install as I
from fo4_import.base.writer import pack_fo4_header, pack_fo4_record
from fo4_import.pipeline import export_index as X
from tes5_import.base.writer import pack_group, pack_subrecord
from tools.validate.export_master_refs import check

PISTOL, RIFLE, AMMO, MISSING, GUN = 0x1000, 0x1001, 0x1002, 0x2000, 0x01000800


def _plugin(path, masters: list, weapons: dict) -> None:
    """Write a plugin at `path` with `masters` and WEAP records {FormID: EditorID}."""
    recs = b''.join(pack_fo4_record('WEAP', fid, 0, pack_subrecord('EDID', f'{e}\0'.encode())) for fid, e in weapons.items())
    path.write_bytes(pack_fo4_header(masters, len(weapons), 0x800, 0, '') + pack_group(0, b'WEAP', recs))


def _export(folder, masters: list, weapons: dict) -> None:
    """Write an export folder with `masters` in _HEADER.txt and WEAP.txt of {FormID: (EditorID, ammo)}."""
    folder.mkdir()
    (folder / '_HEADER.txt').write_text(''.join(f'Master[{i}]={m}\n' for i, m in enumerate(masters)), encoding='utf-8')
    blocks = [f'Signature=WEAP\nFormID={fid:08X}\nEditorID={e}\nNAM0={ammo:08X}\n' for fid, (e, ammo) in weapons.items()]
    (folder / 'WEAP.txt').write_text('\n'.join(f'---RECORD_BEGIN---\n{b}---RECORD_END---\n' for b in blocks),
                                     encoding='utf-8')


def test_a_dlc_export_reads_its_own_records_then_its_masters_it_does_not_override(tmp_path):
    """The DLC's override and gun first, then the game's gun it leaves; the game export alone is unchanged; the
    check finds the gun's ammo in the master and the override's missing one."""
    _export(tmp_path / 'Game.esm', [], {PISTOL: ('Pistol', AMMO), RIFLE: ('Rifle', AMMO)})
    _export(tmp_path / 'Dlc.esm', ['Game.esm'], {RIFLE: ('RifleDlc', MISSING), GUN: ('Gun', PISTOL)})
    X.export_masters.cache_clear()
    names = [r['EditorID'] for r in X.export_records(tmp_path / 'Dlc.esm', 'WEAP')]
    assert names == ['RifleDlc', 'Gun', 'Pistol'] and len(X.export_records(tmp_path / 'Game.esm', 'WEAP')) == 2
    found = check(tmp_path / 'Dlc.esm')
    assert (found['master'], found['own'], sum(found['missing'].values())) == (1, 0, 1)


def test_a_dlc_export_with_its_master_missing_says_so(tmp_path):
    """An export naming a master not exported stops the build with its name."""
    _export(tmp_path / 'Dlc.esm', ['Game.esm'], {})
    X.export_masters.cache_clear()
    with pytest.raises(SystemExit, match='Game.esm'):
        X.export_records(tmp_path / 'Dlc.esm', 'WEAP')


def test_the_binary_source_walks_the_dlc_then_its_masters_records(tmp_path, monkeypatch):
    """source_walk: the DLC's records (its override first), then the master's it leaves, each FormID once."""
    _plugin(tmp_path / 'Game.esm', [], {PISTOL: 'Pistol', RIFLE: 'Rifle'})
    _plugin(tmp_path / 'Dlc.esm', ['Game.esm'], {RIFLE: 'RifleDlc', GUN: 'Gun'})
    monkeypatch.setitem(I._SOURCE, 'plugin', tmp_path / 'Dlc.esm')
    I._read.cache_clear()
    walked = [(r.form_id, r.body) for r, _ in I.source_walk(b'WEAP')]
    assert [f for f, _ in walked] == [RIFLE, GUN, PISTOL] and b'RifleDlc' in walked[0][1]
    assert [r.form_id for r, _ in I.plugin_walk((tmp_path / 'Game.esm').read_bytes(), b'WEAP')] == [PISTOL, RIFLE]
    assert I.masters_of((tmp_path / 'Dlc.esm').read_bytes()) == ['Game.esm']


def test_a_dlc_asset_is_its_own_file_else_its_masters(tmp_path):
    """export_file: the DLC's file, else the game's, else the DLC's own path; AssetRoot joins the same way."""
    _export(tmp_path / 'Game.esm', [], {})
    _export(tmp_path / 'Dlc.esm', ['Game.esm'], {})
    for folder, name in (('Game.esm', 'base.nif'), ('Game.esm', 'both.nif'), ('Dlc.esm', 'both.nif'), ('Dlc.esm', 'new.nif')):
        (tmp_path / folder / 'meshes').mkdir(exist_ok=True)
        (tmp_path / folder / 'meshes' / name).write_bytes(folder.encode())
    X.export_masters.cache_clear()
    dlc = tmp_path / 'Dlc.esm'
    assert [X.export_file(dlc, 'meshes', n).read_bytes() for n in ('base.nif', 'both.nif', 'new.nif')] == [
        b'Game.esm', b'Dlc.esm', b'Dlc.esm']
    assert X.export_file(dlc, 'meshes', 'gone.nif') == dlc / 'meshes' / 'gone.nif'
    assert (X.asset_root(dlc, 'meshes') / 'base.nif').read_bytes() == b'Game.esm'
    assert (X.asset_root(dlc, 'meshes') / 'sub' / 'deep.nif').path() == dlc / 'meshes' / 'sub' / 'deep.nif'
    (tmp_path / 'Game.esm' / 'meshes' / 'sub').mkdir()
    (tmp_path / 'Game.esm' / 'meshes' / 'sub' / 'deep.nif').write_bytes(b'x')
    (dlc / 'meshes' / 'sub').mkdir()
    assert str(X.asset_root(dlc, 'meshes') / 'sub' / 'deep.nif') == str(tmp_path / 'Game.esm' / 'meshes' / 'sub' / 'deep.nif')
