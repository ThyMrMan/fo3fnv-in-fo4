"""FO4 items after the converter audit: form lists, headgear paths and swaps, worn mesh names, gun assets and keys.

See: docs/fork/fo4_tool_audit.md#fix-first
See: docs/fork/fo4_tool_audit.md#drops
See: docs/fork/fo4_tool_audit.md#meshes
"""

import collections
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fo4_import.face import bake as B
from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F
from fo4_import.nif import headgear as H
from fo4_import.spike import equipment as E
from fo4_import.spike import guns as G
from fo4_import.spike import items as I
from fo4_import.spike import replacements as RP
from fo4_import.spike.gun_choice import Choice
from fo4_import.spike.weapon_mods import ZOOMS
from tes5_import.base.tes5_reader import subrecords

MESHES = Path('export/FalloutNV.esm/meshes')
SKINNED_FEDORA = MESHES / 'armor/headgear/gambler/gambler_fedora_01.nif'
RIGID_FEDORA = MESHES / 'armor/headgear/1950stylehat/m/suithat.nif'
FNV_HEAD = MESHES / 'characters/head/headhuman.nif'


def _list_builder(**maps) -> SimpleNamespace:
    """A stub cell builder for form lists: `maps` are its made forms; FLSTs it writes kept in `written`."""
    written = []
    scripts = SimpleNamespace(messages={'MsgA': {'FormID': '00000050'}}, message=lambda edid: 0x03000050)
    return SimpleNamespace(counts=collections.Counter(), scripts=scripts, written=written,
                           writer=SimpleNamespace(add_record=lambda sig, rec: written.append(rec)),
                           fnv_id=lambda f: 0x03000000 | int(f, 16), **maps)


def _flst(fid: int, *entries: int) -> tuple:
    """An index() FLST entry listing `entries`."""
    rec = {'FormID': f'{fid:08X}', 'EditorID': f'List{fid:X}'}
    rec.update({f'LNAM[{i}]': f'{e:08X}' for i, e in enumerate(entries)})
    return 'FLST', rec


def test_a_form_list_keeps_items_and_forms_the_build_made_and_counts_the_rest():
    """An item (made now), a placed base and a creature the build made, a message: kept in order; an explosion
    the build never makes is dropped and counted by type."""
    builder = _list_builder(made={0x30: 0x0300AAAA}, creatures=SimpleNamespace(made={0x40: 0x0300BBBB}),
                            fnv_types={0x60: 'EXPL'})
    records = {0x10: ('WEAP', {'FormID': '00000010'}), 0x20: _flst(0x20, 0x10, 0x30, 0x40, 0x50, 0x60)}
    items = I.Items(builder, records, {}, {'WEAP': lambda fid, rec: 0x03000010})
    assert items.item(0x20) == 0x03000020
    lnam = [struct.unpack('<I', b)[0] for s, b in subrecords(builder.written[0][24:]) if s == b'LNAM']
    assert lnam == [0x03000010, 0x0300AAAA, 0x0300BBBB, 0x03000050]
    assert builder.counts['form list entry dropped (EXPL)'] == 1 and builder.counts['FLST'] == 1


def test_a_form_list_whose_every_entry_drops_is_not_made_but_an_authored_empty_one_is():
    """Every entry unbuilt: no record, None (a property naming it stays unfilled), counted; FNV's empty list
    (scripts fill it) is written empty."""
    builder = _list_builder(fnv_types={0x60: 'CREA'})
    items = I.Items(builder, {0x20: _flst(0x20, 0x60), 0x21: _flst(0x21)}, {})
    assert items.item(0x20) is None and not builder.written
    assert builder.counts['form list not made (no entry converts)'] == 1
    assert builder.counts['form list entry dropped (CREA)'] == 1
    assert items.item(0x21) == 0x03000021 and len(builder.written) == 1


def test_an_item_type_list_holds_the_forms_made_for_its_types_items_and_only_named_lists_are_written():
    """RemoveAllTypedItems' weapon list: the weapons made and a shared stand-in, not one never made nor armor; a
    list no script names is not written.
    See: docs/fork/script_markers.md#removealltypeditems"""
    builder = _list_builder()
    builder.writer.derive_formid = lambda site, key: hash((site, key)) & 0xFFFFFF
    records = {0x10: ('WEAP', {'FormID': '00000010'}), 0x11: ('WEAP', {'FormID': '00000011'}),
               0x12: ('WEAP', {'FormID': '00000012'}), 0x13: ('ARMO', {'FormID': '00000013'})}
    items = I.Items(builder, records, {0x12: 0x0001F669}, {'WEAP': lambda fid, rec: 0x03000000 | fid,
                                                            'ARMO': lambda fid, rec: 0x03000000 | fid})
    items.item(0x10), items.item(0x13)
    fid = items.type_list('TES4ItemType40')
    assert items.type_list('TES4WeapAnimType1') is None
    items.write_type_lists()
    lnam = [struct.unpack('<I', b)[0] for s, b in subrecords(builder.written[-1][24:]) if s == b'LNAM']
    assert struct.unpack('<I', builder.written[-1][12:16])[0] == fid
    assert lnam == [0x0001F669, 0x03000010] and builder.counts['item type lists'] == 1


@pytest.mark.skipif(not SKINNED_FEDORA.exists(), reason='needs the FalloutNV.esm export')
def test_skinned_fnv_headgear_moves_into_the_frame_rigid_headgear_is_drawn_in():
    """The gambler fedora (skinned to Bip01 Head) lands where the rigid suit hat sits on FNV's head mesh; a
    rigid hat has no frame."""
    frame = H.head_frame(SKINNED_FEDORA, FNV_HEAD)
    assert np.allclose(frame[:3, :3], np.eye(3), atol=0.01)
    assert np.allclose(frame[3, :3], (0.0, -0.24, -112.85), atol=0.05)
    assert H.head_frame(RIGID_FEDORA, FNV_HEAD) is None


def _quad(z: float) -> bytes:
    """A converted-static-like NIF: one lit two-triangle shape facing +Y at y 9, from height `z`."""
    nif = F.NifFile(strings=['Root'])
    pos = np.array([(-1, 9, z), (1, 9, z), (1, 9, z + 2), (-1, 9, z + 2)], float)
    tris = np.array([(0, 1, 2), (0, 2, 3)])
    verts = C.vertices(pos, np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float), np.tile((0.0, 1.0, 0.0), (4, 1)),
                       None, tris)
    nif.blocks = [('NiNode', {'name': 0, 'extra': [], 'controller': -1, 'flags': 14, 'translation': (0.0,) * 3,
                              'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1, 'children': [1]}),
                  ('BSTriShape', {'name': nif.string('Hat:0'), 'extra': [], 'controller': -1, 'flags': 14,
                                  'translation': (0.0,) * 3, 'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1,
                                  'bound': (0.0, 9.0, z + 1, 1.5), 'skin': -1, 'shader': 2, 'alpha_property': -1,
                                  'vertex_desc': C.DESC_PLAIN, 'vertices': verts,
                                  'triangles': [tuple(t) for t in tris.tolist()]}),
                  ('BSLightingShaderProperty', C.lighting_shader(nif, 'materials\\fnv\\hat.bgsm', 3, 0)),
                  ('BSShaderTextureSet', {'textures': [''] * C.TEXTURE_SLOTS})]
    return F.write(nif)


def _worn_positions(raw: bytes) -> np.ndarray:
    """The worn shape's vertex positions in a headgear.worn() NIF."""
    back = F.read(raw)
    return B.positions(next(b for k, b in back.blocks if k == 'BSSubIndexTriShape'))


def test_worn_headgear_in_its_skeletons_space_matches_the_same_mesh_in_the_heads_frame():
    """A frame lowering the mesh by 100 gives what the mesh already 100 lower gives."""
    fit = H.HeadFit(1.0, np.eye(3), np.zeros(3), (0.0, 0.0, 0.0), C.IDENTITY, np.zeros((8, 3)), np.zeros((8, 3)),
                    np.zeros((1, 3)), np.zeros((1, 3)))
    frame = np.eye(4)
    frame[3, 2] = -100.0
    moved = _worn_positions(H.worn(_quad(100.0), fit, (47,), frame))
    assert np.allclose(moved, _worn_positions(H.worn(_quad(0.0), fit, (47,))), atol=1e-2)


def test_worn_headgear_gets_a_file_per_slots_apart_from_its_static(tmp_path, monkeypatch):
    """One FNV mesh in slots 46 and 30+46, male and female: three worn files, each made once; the static's
    file (also its world model) is never written over."""
    made = []
    monkeypatch.setattr(E.headgear, 'worn', lambda static, fit, slots, frame: made.append(slots) or repr(slots).encode())
    (tmp_path / 'Meshes' / 'fnv').mkdir(parents=True)
    eq = E.Equipment.__new__(E.Equipment)
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire_armor=lambda fnv, fid, subs, fields: subs)
    eq.builder, eq.fits, eq.worn_paths = SimpleNamespace(data_dir=tmp_path), {'male': 0, 'female': 0}, {}
    eq.statics = {'hat.nif': ('fnv\\red_beret.nif', b'static')}
    paths = [eq._worn('hat.nif', sex, slots, None) for sex, slots in
             (('male', (46,)), ('male', (30, 46)), ('female', (46,)), ('male', (46,)))]
    assert paths == ['fnv\\red_beret_worn_46.nif', 'fnv\\red_beret_worn_30_46.nif',
                     'fnv\\red_beret_worn_46_female.nif', 'fnv\\red_beret_worn_46.nif']
    assert made == [(46,), (30, 46), (46,)] and not (tmp_path / 'Meshes' / 'fnv' / 'red_beret.nif').exists()


def test_headgear_puts_fnvs_worn_alternate_textures_on_its_addon():
    """The male model's swap goes after MOD2 (MO2S), none for a female model without alternates."""
    eq = E.Equipment.__new__(E.Equipment)
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire_armor=lambda fnv, fid, subs, fields: subs)
    taken = {}
    eq._on_head = lambda model, sex: (True, None)
    eq._worn = lambda model, sex, slots, frame: f'{model}_{sex}'
    eq._worn_swaps = lambda fnv, rec, models: [0x0300AAAA, None]
    eq._addon = lambda fnv, rec, template, bod2, models, swaps: taken.update(models=models, swaps=swaps) or 7
    eq._world = lambda fnv, rec, addon: {b'MODL': struct.pack('<I', addon)}
    out = eq._headgear(1, {'BMDT.BipedFlags': '1024', 'Male.BipedModel.MODL': 'hat.nif'},
                       {b'MODL': struct.pack('<I', 9)})
    assert taken == {'models': {b'MOD2': 'hat.nif_male', b'MOD3': 'hat.nif_female'}, 'swaps': {b'MO2S': 0x0300AAAA}}
    assert out[b'BOD2'] == E._bod2((30, 46)) and out[b'MODL'] == struct.pack('<I', 7)


def test_an_armor_fnv_gives_no_world_model_wears_its_own_mesh_on_the_templates_world_model():
    """The addon is ours; MOD2 and its model data and swap stay the template's; counted."""
    template = [(b'EDID', b'ClothesMobsterhat\0'), (b'MOD2', b'Clothes\\Hat.nif\0'), (b'MO2T', b'data'),
                (b'MO2S', struct.pack('<I', 5)), (b'MOD4', b'Clothes\\HatF.nif\0'), (b'BOD2', bytes(4)),
                (b'INDX', bytes(2)), (b'MODL', struct.pack('<I', 0x216376)), (b'DATA', bytes(12)), (b'FNAM', bytes(8))]
    written = []
    eq = E.Equipment.__new__(E.Equipment)
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire_armor=lambda fnv, fid, subs, fields: subs)
    eq.builder = SimpleNamespace(counts=collections.Counter(), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x0300F00D, add_record=lambda sig, rec: written.append(rec)))
    eq.fnv, eq.strings, eq.vanilla = {1: {'value': 5, 'weight': 1.0, 'rating': 2.0}}, {}, {'ClothesMobsterhat': template}
    eq.table = {'HatX': RP.Replacement(RP.BASE, 'ClothesMobsterhat', 'fnv')}
    eq._headgear = lambda fnv, rec, tpl: {b'BOD2': b'\1\0\0\0', **E.Equipment._world(eq, fnv, rec, 0x0300ABCD)}
    eq.armo(1, {'EditorID': 'HatX', 'Male.BipedModel.MODL': 'hat.nif'})
    subs = dict(subrecords(written[0][24:]))
    assert (subs[b'MOD2'], subs[b'MO2T'], subs[b'MO2S']) == (b'Clothes\\Hat.nif\0', b'data', struct.pack('<I', 5))
    assert subs[b'MODL'] == struct.pack('<I', 0x0300ABCD) and b'MOD4' not in subs
    assert eq.builder.counts["ARMO on the template's world model (FNV has none)"] == 1


def test_an_armor_no_fnv_mesh_path_takes_is_counted_by_why():
    """No worn model, headgear off the head, a rigid upper body, other slots (FNV's Head bit, a choker)."""
    assert E._on_template({'BMDT.BipedFlags': '1538'}) == 'no FNV worn model'
    worn = {'Male.BipedModel.MODL': 'x.nif'}
    assert E._on_template({**worn, 'BMDT.BipedFlags': '1538'}) == 'headgear not on the head'
    assert E._on_template({**worn, 'BMDT.BipedFlags': '4'}) == 'rigid upper body'
    assert E._on_template({**worn, 'BMDT.BipedFlags': str(0x203)}) == 'other slots'
    assert E._on_template({**worn, 'BMDT.BipedFlags': str(0x8200)}) == 'other slots'


def _guns(tmp_path) -> 'G.Guns':
    """A Guns over stubs: its data folder under `tmp_path`, every OMOD key and record noted."""
    keys, written = [], []
    guns = G.Guns.__new__(G.Guns)
    guns.builder = SimpleNamespace(export_dir=tmp_path / 'export', data_dir=tmp_path / 'data',
                                   counts=collections.Counter(), keys=keys, written=written,
                                   writer=SimpleNamespace(add_record=lambda sig, rec: written.append(rec),
                                                          derive_formid=lambda site, key: keys.append(key) or 0x0300C0DE))
    guns.strings, guns.converted = {}, {}
    return guns


def test_choosing_a_gun_writes_none_of_its_fnv_assets_and_building_on_it_does(tmp_path, monkeypatch):
    """choose() reads the conversion only; templates() writes the mesh with its materials, then the gun."""
    guns, written = _guns(tmp_path), []
    monkeypatch.setattr(G, 'cached_convert', lambda path, root, pose, animated: SimpleNamespace(nif='nif'))
    monkeypatch.setattr(G, 'nif_file', SimpleNamespace(write=lambda nif: b'static'))
    monkeypatch.setattr(G, 'gun', SimpleNamespace(fnv_nodes=lambda path: {}, fnv_layout=lambda static, nodes: {},
                                                  placement=lambda static, nodes, receiver: np.eye(4),
                                                  gun=lambda static, nodes, receiver, matrix: b'gun'))
    monkeypatch.setattr(G, 'write_assets', lambda root, model, data, animated: written.append(model) or (
        'fnv\\weapons\\pistol.nif', None))
    choice = Choice('10mm', (0x10,), 0x10, 'r.nif', {})
    guns.choices = SimpleNamespace(choose=lambda rec, layout, only=None: choice, weapons={'10mm': (1, [])})
    chosen = guns.choose({'Model.MODL': 'Weapons\\Pistol.NIF'})
    assert (chosen[2][0], chosen[2][2]) == ('Weapons\\Pistol.NIF', b'static') and not written and not (tmp_path / 'data').exists()
    (tmp_path / 'data' / 'Meshes' / 'fnv' / 'weapons').mkdir(parents=True)
    guns._read, guns._lift = lambda model: b'receiver', lambda layout, ch: 0.0
    guns._clips = lambda fnv, rec, template, path, receiver, static: None
    guns._part = lambda fnv, rec, fid, placed, props=(): placed[0] and 0x0300C0DE
    guns._fnv_scope = lambda rec, combo: (None, (), None)
    obts = struct.pack('<I', 1) + bytes(10) + b'\1' + b'\0' + bytes(2) + struct.pack('<I', 0x10) + bytes(3)
    guns.templates(0x1234, {'EditorID': 'WeapX'}, choice, [(b'FULL', b'Default\0'), (b'OBTS', obts)], chosen[2], False)
    assert written == ['Weapons\\Pistol.NIF']
    assert (tmp_path / 'data' / 'Meshes' / 'fnv' / 'weapons' / 'pistol_gun.nif').read_bytes() == b'gun'


def test_a_gun_part_copy_is_keyed_on_the_fnv_gun_and_its_attach_point(tmp_path):
    """Not on the vanilla part chosen there, so choosing another moves no FormID."""
    guns = _guns(tmp_path)
    guns.mods = {0x10: [(b'EDID', b'mod_Receiver\0'), (b'MODL', b'r.nif\0'), (b'DATA', bytes(24))]}
    guns.choices = SimpleNamespace(model=lambda fid: 'r.nif', attach=lambda fid: 0x99, names={0x99: 'ap_gun_receiver'})
    assert guns._part(0x1234, {'EditorID': 'WeapX'}, 0x10, ('fnv\\x_gun.nif', 0.0, False)) == 0x0300C0DE
    assert guns.builder.keys == ['00001234 ap_gun_receiver'] and guns.builder.counts['OMOD'] == 1


def test_a_built_in_scope_takes_fnvs_zoom_and_the_lift_its_camera_offset(tmp_path):
    """A scoped FNV gun's scope part gets the props of FNV's own sight FOV and the lift subtracts that zoom's camera
    z; an unscoped gun gets none and the lift falls back to the template's zoom data."""
    guns = _guns(tmp_path)
    guns.zooms = {name: (i, mult, 3.0 * i) for i, (name, mult) in enumerate(
        zip(ZOOMS, (2.0, 4.0, 6.0, 10.0)), start=1)}
    guns.builder.keywords, guns.builder.fo4 = {'HasScope': 7, 'dn_HasScope': 8}, b''
    guns.choices = SimpleNamespace(magnified_scope=lambda combo: 0x55)
    scoped = {'DNAM.Flags1': '68', 'DNAM.Flags2': '8', 'DNAM.SightFOV': '35.0'}
    scope, props, camera_z = guns._fnv_scope(scoped, (0x55,))
    assert scope == 0x55 and camera_z == 3.0 and len(props) == 5
    assert guns._clip_lift(10.0, [], camera_z) == 7.0
    assert guns._fnv_scope(dict(scoped, **{'DNAM.Flags2': '8200'}), (0x55,)) == (None, (), None)
    assert guns._clip_lift(10.0, []) == 10.0


def test_a_copy_keeps_only_its_default_mod_combination(tmp_path):
    """default_only cuts a template's object template (OBTE ... STOP) to its default combination; a record with
    no combination gets None."""
    guns = _guns(tmp_path)
    default, loot = bytearray(20), bytearray(20)
    default[G.OBTS_DEFAULT] = 1
    template = [(b'EDID', b'x\0'), (b'OBTE', struct.pack('<I', 2)), (b'OBTF', b''), (b'FULL', b'Default\0'),
                (b'OBTS', bytes(default)), (b'OBTF', b''), (b'FULL', b'Standard Epic\0'), (b'OBTS', bytes(loot)),
                (b'STOP', b'')]
    block = guns.default_only(template)
    assert block == [(b'OBTE', struct.pack('<I', 1)), (b'OBTF', b''), (b'FULL', b'Default\0'),
                     (b'OBTS', bytes(default)), (b'STOP', b'')]
    assert guns.default_only([(b'EDID', b'x\0')]) is None
