"""fo4_import.app.files and fo4_import.app.catalog on small hand-built plugins and archives."""

import struct

from fo4_import.app import catalog as C
from fo4_import.app.files import Files, mesh_path
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.equipment import DNAM_DAMAGE, DNAM_VALUE, DNAM_WEIGHT
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord


def _group(sig: str, *recs: bytes) -> bytes:
    """A top-level GRUP of `recs`."""
    body = b''.join(recs)
    return b'GRUP' + struct.pack('<I4sIII', 24 + len(body), sig.encode(), 0, 0, 0) + body


def _plugin(path, groups: list, masters=(), flags: int = 0):
    """Write a plugin of `groups` with `masters` and header `flags`; its path."""
    header = b''.join(pack_string_subrecord('MAST', m) + pack_subrecord('DATA', b'\0' * 8) for m in masters)
    path.write_bytes(pack_fo4_record('TES4', 0, flags, header) + b''.join(groups))
    return path


def _ba2(path, files: dict):
    """Write a GNRL BA2 storing `files` {name: bytes} unpacked."""
    names = list(files)
    data_at, entries, blobs = 24 + 36 * len(names), b'', b''
    for name in names:
        entries += struct.pack('<I4sIIQIII', 0, b'nif\0', 0, 0, data_at + len(blobs), 0, len(files[name]), 0xBAADF00D)
        blobs += files[name]
    table = b''.join(struct.pack('<H', len(n)) + n.encode() for n in names)
    path.write_bytes(struct.pack('<4sI4sIQ', b'BTDX', 1, b'GNRL', len(names), data_at + len(blobs)) + entries + blobs +
                     table)


def test_files_loose_wins_and_ignores_case(tmp_path):
    """A loose file beats an archived one; the winning folder's loose file beats a later folder's."""
    win, lose = tmp_path / 'Win', tmp_path / 'Lose'
    (win / 'Meshes').mkdir(parents=True)
    (lose / 'meshes').mkdir(parents=True)
    (win / 'Meshes' / 'Gun.NIF').write_bytes(b'win')
    (lose / 'meshes' / 'gun.nif').write_bytes(b'lose')
    _ba2(lose / 'Mod - Main.ba2', {'meshes\\gun.nif': b'archived', 'meshes\\only.nif': b'only'})
    files = Files([win, lose])
    assert files.read('meshes/gun.nif') == b'win'
    assert files.read('MESHES\\ONLY.NIF') == b'only'
    assert files.read('meshes\\none.nif') is None


def test_mesh_path():
    """A record's model is relative to meshes; one already under it is kept."""
    assert mesh_path('Weapons/Gun.NIF') == 'meshes\\weapons\\gun.nif'
    assert mesh_path('Meshes\\Weapons\\Gun.nif') == 'meshes\\weapons\\gun.nif'


def _weap(fid: int, edid: str, name: str, damage: int) -> bytes:
    """A WEAP with a DNAM holding `damage`, value 50 and weight 2.5."""
    dnam = bytearray(DNAM_DAMAGE + 4)
    struct.pack_into('<H', dnam, DNAM_DAMAGE, damage)
    struct.pack_into('<I', dnam, DNAM_VALUE, 50)
    struct.pack_into('<f', dnam, DNAM_WEIGHT, 2.5)
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', name)
    template = pack_subrecord('OBTE', struct.pack('<I', 1)) + pack_string_subrecord('FULL', 'Default')
    return pack_fo4_record('WEAP', fid, 0, subs + pack_string_subrecord('MODL', 'Weapons\\Gun.nif') +
                           pack_subrecord('DNAM', bytes(dnam)) + template)


def test_scan_reads_items_overrides_and_addons(tmp_path):
    """Names, models, worn models through the plugin's addon, stats, and a master's record as an override."""
    arma = pack_fo4_record('ARMA', 0x01000900, 0, pack_string_subrecord('EDID', 'HatAA') +
                           pack_string_subrecord('MOD2', 'Armor\\Hat_M.nif'))
    armo = pack_fo4_record('ARMO', 0x01000901, 0, pack_string_subrecord('EDID', 'Hat') +
                           pack_string_subrecord('FULL', 'Hat') + pack_string_subrecord('MOD2', 'Armor\\Hat_Go.nif') +
                           pack_subrecord('MODL', struct.pack('<I', 0x01000900)) +
                           pack_subrecord('DATA', struct.pack('<ifI', 12, 0.5, 100)) +
                           pack_subrecord('FNAM', struct.pack('<HBB', 7, 0, 0)))
    plugin = _plugin(tmp_path / 'Port.esp', [
        _group('WEAP', _weap(0x01000800, 'PortGun', 'Port Gun', 31), _weap(0x00004822, '10mm', 'Better 10mm', 20)),
        _group('ARMO', armo), _group('ARMA', arma)], masters=['Fallout4.esm'])
    entries = C.scan(plugin)
    found = {e.edid: e for e in entries}
    gun = found['PortGun']
    assert (gun.name, gun.category, gun.model, gun.owner) == ('Port Gun', 'weapon', 'Weapons\\Gun.nif', '')
    assert gun.stats == {'damage': 31, 'value': 50, 'weight': 2.5, 'magazine': 0, 'ammo': '00000000'}
    assert found['10mm'].owner == 'Fallout4.esm' and gun.use == 'Port.esp|PortGun'
    hat = found['Hat']
    assert (hat.model, hat.stats) == ('Armor\\Hat_Go.nif', {'value': 12, 'weight': 0.5, 'armor rating': 7})
    assert C.preview_models(hat, C.index({'Port.esp': entries})) == (['Armor\\Hat_M.nif'], '')
    assert found['HatAA'].category == 'addon' and C.in_category({'Port.esp': entries}, 'armor') == [hat]


def test_localized_names_come_from_strings_files(tmp_path):
    """A localized plugin's FULL is a string ID into its strings file, found loose through Files."""
    (tmp_path / 'Strings').mkdir()
    text = b'Laser Musket\0'
    (tmp_path / 'Strings' / 'Port_en.STRINGS').write_bytes(struct.pack('<II', 1, len(text)) +
                                                            struct.pack('<II', 0x77, 0) + text)
    rec = pack_fo4_record('WEAP', 0x01000800, 0, pack_string_subrecord('EDID', 'Musket') +
                          pack_subrecord('FULL', struct.pack('<I', 0x77)))
    plugin = _plugin(tmp_path / 'Port.esp', [_group('WEAP', rec)], masters=['Fallout4.esm'], flags=C.LOCALIZED)
    assert C.scan(plugin, Files([tmp_path]))[0].name == 'Laser Musket'


def test_in_category_filters_and_sorts(tmp_path):
    """in_category keeps one category, optionally only some plugins, sorted by name."""
    plugin = _plugin(tmp_path / 'Port.esp', [_group('WEAP', _weap(0x01000800, 'Z', 'zeta', 1),
                                                    _weap(0x01000801, 'A', 'Alpha', 2))], ['Fallout4.esm'])
    found = C.catalog({'port.esp': plugin})
    assert [e.name for e in C.in_category(found, 'weapon')] == ['Alpha', 'zeta']
    assert C.in_category(found, 'weapon', C.BASE_GAME) == []
