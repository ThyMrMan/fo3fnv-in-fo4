"""The Replacements screen's parts without a window: stand-ins, the user file, gun parts and their assembly."""

import struct

import numpy as np
import pytest

from fo4_import.app import catalog as C
from fo4_import.app import standins as SI
from fo4_import.app import user_table as U
from fo4_import.app.preview import assembly as A
from fo4_import.app.replacements_view import allowed_modes
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif import blocks as K
from fo4_import.nif import file as F
from fo4_import.spike import replacements as RP
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord


def _form(sig: str, edid: str, **record) -> SI.SourceForm:
    """A source form of `sig` with export fields `record`."""
    rec = {'Signature': sig, 'EditorID': edid, **record}
    category = next(c for c, sigs in SI.CATEGORY_SIGS.items() if sig in sigs)
    return SI.SourceForm(category, sig, 1, edid, '', SI.source_model(rec), 0, rec)


def test_current_follows_table_rules_and_converter():
    """A table entry wins, then the rules, then the converter's choice; a creature without either is skipped."""
    table = RP.load()
    assert SI.current(table, _form('WEAP', 'WeapKnife')).label == 'table (default)'
    melee = SI.current(table, _form('WEAP', 'WeapX', **{'DNAM.FalloutAnimType': '2'}))
    assert (melee.how, melee.entry.edid) == ('rule', 'BaseballBat')
    assert SI.current(table, _form('WEAP', 'WeapGun', **{'DNAM.FalloutAnimType': '5'})).how == 'gun'
    hat = SI.current(table, _form('ARMO', 'HatX', **{'BMDT.BipedFlags': str(0x400)}))
    assert hat.entry.edid == 'ClothesMobsterhat'
    gecko = SI.current(table, _form('CREA', 'GeckoX', **{'Model.MODL': 'Creatures\\NVGecko\\Skeleton.nif'}))
    assert (gecko.how, gecko.entry.edid) == ('rule', 'EncViciousDog01Template')
    assert SI.current(table, _form('CREA', 'Nothing', **{'Model.MODL': 'Creatures\\Spore\\s.nif'})).how == 'none'


def test_converted_mesh_paths():
    """An item's own mesh lands under meshes\\fnv by its FNV path; a creature's as its parts joined."""
    assert SI.converted_mesh(_form('MISC', 'Can', **{'Model.MODL': 'Clutter\\Junk\\TinCan01.NIF'})) == \
        'meshes\\fnv\\clutter\\junk\\tincan01.nif'
    dog = _form('CREA', 'CrCoyote', **{'Model.MODL': 'Creatures\\Dog\\Skeleton.NIF', 'NIFZCount': '1',
                                       'NIFZ[0]': 'Coyote.NIF'})
    assert SI.converted_mesh(dog) == 'meshes\\fnv\\creatures\\dog\\coyote.nif'


def test_user_file_set_clear_and_refuse(tmp_path):
    """Set and clear entries, write, read back through the loader; a copy of another plugin is refused."""
    path, data = tmp_path / 'mine.json', {}
    U.set_entry(data, 'weapon', 'WeapKnife', 'Fallout4.esm|CombatKnife', 'stats')
    U.set_entry(data, 'creature', 'CrGecko', 'Fallout4.esm|EncMolerat01Template', 'item')
    with pytest.raises(ValueError):
        U.set_entry(data, 'weapon', 'WeapX', 'Mod.esp|Gun', 'stats')
    U.write(path, data)
    table = RP.load(path)
    assert table['WeapKnife'].edid == 'CombatKnife' and table.creatures['CrGecko'].origin == 'user'
    assert U.clear_entry(data, 'weapon', 'WeapKnife') and not U.clear_entry(data, 'weapon', 'WeapKnife')
    U.write(path, data)
    assert RP.load(path)['WeapKnife'].edid == 'Knife' and U.read(path)['creature']


def test_allowed_modes():
    """FO4 records take any mode; others and leveled lists only as they are; creature fnv needs a rig pair."""
    entry = lambda plugin, sig, category: C.Entry(plugin, 1, sig, 'X', '', category)
    gecko = _form('CREA', 'G', **{'Model.MODL': 'Creatures\\NVGecko\\s.nif'})
    dog = _form('CREA', 'D', **{'Model.MODL': 'Creatures\\Dog\\s.nif'})
    assert allowed_modes(entry('Mod.esp', 'WEAP', 'weapon'), None) == ('item',)
    assert allowed_modes(entry('Fallout4.esm', 'WEAP', 'weapon'), None) == RP.MODES
    assert allowed_modes(entry('Fallout4.esm', 'LVLN', 'creature'), gecko) == ('item',)
    assert allowed_modes(entry('Fallout4.esm', 'NPC_', 'creature'), gecko) == ('item', 'stats')
    assert allowed_modes(entry('Fallout4.esm', 'NPC_', 'creature'), dog) == RP.MODES


def _group(sig: str, *recs: bytes) -> bytes:
    """A top-level GRUP of `recs`."""
    body = b''.join(recs)
    return b'GRUP' + struct.pack('<I4sIII', 24 + len(body), sig.encode(), 0, 0, 0) + body


def _obts(mods: list, default: bool) -> bytes:
    """An OBTS (gun_choice's layout) including `mods`, default or not."""
    head = struct.pack('<IIBBBBhBB', len(mods), 0, 0, 0, 0, 0, -1, int(default), 0) + bytes(2)
    return head + b''.join(struct.pack('<IBBB', m, 0, 0, 0) for m in mods)


def _record(sig: str, fid: int, edid: str, **subs) -> bytes:
    """A record with an EditorID and subrecords {tag: FormID int, str or bytes}."""
    body = pack_string_subrecord('EDID', edid)
    for tag, value in subs.items():
        body += pack_subrecord(tag, struct.pack('<I', value)) if isinstance(value, int) else \
            pack_string_subrecord(tag, value) if isinstance(value, str) else pack_subrecord(tag, value)
    return pack_fo4_record(sig, fid, 0, body)


def _write_plugin(path, masters: list, records: dict):
    """Write a plugin of {type: [record bytes]} with `masters`; its path."""
    header = b''.join(pack_string_subrecord('MAST', m) + pack_subrecord('DATA', bytes(8)) for m in masters)
    path.write_bytes(pack_fo4_record('TES4', 0, 0, header) + b''.join(_group(s, *r) for s, r in records.items()))
    return path


def _catalog(tmp_path) -> dict:
    """Base.esm (an addon, skin, race, a gun part) and Port.esp (Base.esm's master): a gun, NPCs on Base's race,
    one through a template, a leveled list, and an NPC with no body."""
    base = _write_plugin(tmp_path / 'Base.esm', [], {
        'OMOD': [_record('OMOD', 0x10, 'mod_Grip', MODL='Weapons\\Grip.nif')],
        'ARMA': [_record('ARMA', 0x30, 'BodyAA', MOD2='Actors\\Gecko.nif')],
        'ARMO': [_record('ARMO', 0x31, 'SkinGecko', MODL=0x30)],
        'RACE': [_record('RACE', 0x32, 'GeckoRace', WNAM=0x31)]})
    acbs = struct.pack('<IhHHHhHhh', 0, 0, 1, 0, 0, 0, 1, 0, 0)
    lvlo = struct.pack('<HHIHBB', 1, 0, 0x01000801, 1, 0, 0)
    port = _write_plugin(tmp_path / 'Port.esp', ['Base.esm'], {
        'WEAP': [_record('WEAP', 0x01000800, 'Gun', OBTS=_obts([0x00000099], False)),
                 _record('WEAP', 0x01000810, 'Gun2', OBTS=_obts([0x00000010], True))],
        'NPC_': [_record('NPC_', 0x01000801, 'EncGecko', RNAM=0x00000032),
                 _record('NPC_', 0x01000802, 'GeckoCopy', TPLT=0x01000801, ACBS=acbs),
                 _record('NPC_', 0x01000803, 'Nobody')],
        'LVLN': [_record('LVLN', 0x01000804, 'LGecko', LVLO=lvlo), _record('LVLN', 0x01000805, 'LEmpty')]})
    return C.catalog({'base.esm': base, 'port.esp': port})


def test_previews_follow_links_across_plugins(tmp_path):
    """Gun parts, an NPC on another plugin's race, a template's body and a leveled list's first entry resolve."""
    found = _catalog(tmp_path)
    known, by = C.index(found), {e.edid: e for e in found['Port.esp']}
    assert by['Gun2'].links['parts'] == ('base.esm|000010',)
    assert C.preview_models(by['Gun2'], known) == (['', 'Weapons\\Grip.nif'], '')
    for edid in ('EncGecko', 'GeckoCopy', 'LGecko'):
        assert C.preview_models(by[edid], known) == (['Actors\\Gecko.nif'], ''), edid
    assert C.in_category(found, 'weapon') == [by['Gun'], by['Gun2']]


def test_previews_say_why_there_is_nothing(tmp_path):
    """No body, an empty list, parts with no mesh, a mesh not installed: each gives its reason."""
    found = _catalog(tmp_path)
    known, by = C.index(found), {e.edid: e for e in found['Port.esp']}
    assert 'no skin' in C.preview_models(by['Nobody'], known)[1]
    assert C.preview_models(by['LEmpty'], known)[1] == 'this leveled list has no entries'
    assert 'have a mesh' in C.preview_models(by['Gun'], known)[1]
    assert A.entry_parts(by['EncGecko'], _Files({}), known) == ([], 'the mesh is not installed: '
                                                                    'meshes\\actors\\gecko.nif')


def _sized(text: str) -> bytes:
    """A u32-length string."""
    return struct.pack('<I', len(text)) + text.encode()


def _part_nif(points: bytes = b'', children: str = '') -> bytes:
    """A NIF of one triangle at the origin, with optional connect point parents and a child."""
    nif = F.NifFile(strings=['Root', 'Tri'])
    vert = lambda x, y: {'position': (x, y, 0.0), 'bitangent_x': 0, 'uv': (0.0, 0.0), 'normal': (128, 128, 255),
                         'bitangent_y': 0}
    av = {'extra': [], 'controller': -1, 'flags': 0, 'translation': (0.0, 0.0, 0.0),
          'rotation': (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), 'scale': 1.0, 'collision': -1}
    shape = {**av, 'name': 1, 'bound': (0.0, 0.0, 0.0, 1.0), 'skin': -1, 'shader': -1, 'alpha_property': -1,
             'vertex_desc': (K.VA_VERTEX | K.VA_UV | K.VA_NORMAL) << 44 | 4,
             'vertices': [vert(0, 0), vert(1, 0), vert(0, 1)], 'triangles': [(0, 1, 2)]}
    nif.blocks = [('NiNode', {**av, 'name': 0, 'children': [1]}), ('BSTriShape', shape)]
    if points:
        nif.blocks.append(('BSConnectPoint::Parents', points))
    if children:
        nif.blocks.append(('BSConnectPoint::Children', struct.pack('<iBI', -1, 0, 1) + _sized(children)))
    return F.write(nif)


class _Files:
    """Files holding {Data path: bytes}."""

    def __init__(self, found: dict):
        """Files with `found`."""
        self.found = found

    def read(self, path: str):
        """The bytes at `path`, or None."""
        return self.found.get(path)


def test_assembly_places_a_part_on_its_connect_point():
    """A grip naming C-Grip lands on the receiver's P-Grip, turned by its quaternion (90 degrees about Z)."""
    half = np.sqrt(0.5)
    parents = struct.pack('<iI', -1, 1) + _sized('') + _sized('P-Grip') + struct.pack('<4f3ff', half, 0, 0, half,
                                                                                       0.0, 10.0, 0.0, 1.0)
    files = _Files({'meshes\\receiver.nif': _part_nif(parents), 'meshes\\grip.nif': _part_nif(children='C-Grip')})
    parts, why = A.assemble(files, ['Receiver.nif', 'Grip.nif'])
    assert len(parts) == 2 and why == ''
    assert np.allclose(parts[0].positions, [(0, 0, 0), (1, 0, 0), (0, 1, 0)], atol=1e-6)
    assert np.allclose(parts[1].positions, [(0, 10, 0), (0, 11, 0), (-1, 10, 0)], atol=1e-5)
