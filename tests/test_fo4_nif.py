"""FO4 meshes and materials from FNV statics: formats, tangent convention, specular, glass.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.nif import bgem, bgsm
from fo4_import.nif import convert_static as C
from fo4_import.face import bake as B
from fo4_import.nif import file as F
from fo4_import.nif import blocks as K
from fo4_import.nif import gun as G
from fo4_import.nif import headgear as H
from fo4_import.nif import outfit as O
from fo4_import.nif import weapon as W

SHELF = Path('export/FalloutNV.esm/meshes/furniture/shelveswoodenhalf02.nif')


def test_tangent_frame_is_du_then_dv():
    """A quad whose u runs along +X and v along +Y: dP/du is +X, dP/dv +Y (FO4 stores dv as 'tangent')."""
    pos = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], float)
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    nrm = np.tile((0.0, 0.0, 1.0), (4, 1))
    du, dv = C.tangent_frame(pos, uv, nrm, np.array([(0, 1, 2), (0, 2, 3)]))
    assert np.allclose(du, (1, 0, 0)) and np.allclose(dv, (0, 1, 0))


def test_glossiness_maps_to_ggx_smoothness():
    """Power 0 is rough; 60 (the FNV shelf) is about 0.58."""
    assert C.smoothness(0.0) == 0.0
    assert C.smoothness(60.0) == pytest.approx(0.5762, abs=1e-3)


def test_spec_map_sits_beside_the_normal_map():
    """x_n.dds gives fnv\\x_s.dds."""
    assert C.spec_map_path('textures\\furniture\\Shelves01_n.dds') == 'fnv\\furniture\\shelves01_s.dds'


@pytest.mark.parametrize('module, template, key', [(bgsm, C.MATERIAL, 'diffuse'), (bgem, C.GLASS_EFFECT, 'base')])
def test_material_templates_write_and_read_back(module, template, key):
    """The lit and glass templates survive write then read unchanged."""
    names = bgsm.TEXTURES if module is bgsm else bgem.TEXTURES
    mat = dict(template, textures={n: '' for n in names})
    mat['textures'][key] = 'fnv/a/b.dds'
    if module is bgsm:
        mat['root_material'] = ''
    assert module.write(module.read(module.write(mat))) == module.write(mat)


@pytest.mark.skipif(not SHELF.exists(), reason='needs the FalloutNV.esm export')
def test_converted_shelf_round_trips_through_the_fo4_reader():
    """The FNV shelf as one lit shape, then its collision as pre-Elric Havok blocks (its bottom board, 11

    units up, a step: two materials); it reads back identically.
    """
    converted = C.convert(str(SHELF))
    raw = F.write(converted.nif)
    assert F.write(F.read(raw)) == raw
    assert [k for k, _ in converted.nif.blocks] == ['NiNode', 'BSTriShape', 'BSLightingShaderProperty',
                                                    'BSShaderTextureSet', 'BSXFlags', 'NiTriStripsData',
                                                    'NiTriStripsData', 'bhkNiTriStripsShape', 'bhkRigidBody',
                                                    'bhkCollisionObject']


def _quad_nif():
    """A converted-static-like NIF: root, BSXFlags, one lit two-triangle shape facing +Y at y 9."""
    nif = F.NifFile(strings=['Root', 'BSX'])
    pos = np.array([(-1, 9, 0), (1, 9, 0), (1, 9, 2), (-1, 9, 2)], float)
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    tris = np.array([(0, 1, 2), (0, 2, 3)])
    verts = C.vertices(pos, uv, np.tile((0.0, 1.0, 0.0), (4, 1)), None, tris)
    nif.blocks = [('NiNode', {'name': 0, 'extra': [1], 'controller': -1, 'flags': 14, 'translation': (0.0,) * 3,
                              'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1, 'children': [2]}),
                  ('BSXFlags', {'name': 1, 'value': 2}),
                  ('BSTriShape', {'name': nif.string('Mask:0'), 'extra': [], 'controller': -1, 'flags': 14,
                                  'translation': (0.0,) * 3, 'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1,
                                  'bound': (0.0, 9.0, 1.0, 1.5), 'skin': -1, 'shader': 3, 'alpha_property': -1,
                                  'vertex_desc': C.DESC_PLAIN, 'vertices': verts,
                                  'triangles': [tuple(t) for t in tris.tolist()]}),
                  ('BSLightingShaderProperty', C.lighting_shader(nif, 'materials\\fnv\\mask.bgsm', 4, 0)),
                  ('BSShaderTextureSet', {'textures': [''] * C.TEXTURE_SLOTS})]
    return nif


def test_weapon_dress_adds_parent_bone_bsx_and_hidden_blood_copy():
    """Vanilla melee weapons: Prn WEAPON, BSXFlags 194, each lit shape again with the blood material, hidden."""
    nif = _quad_nif()
    W.dress(nif)
    back = F.read(F.write(nif))
    extra = {back.blocks[i][0]: back.blocks[i][1] for i in back.blocks[0][1]['extra']}
    assert extra['BSXFlags']['value'] == W.BSX
    name, value = struct.unpack('<ii', extra['NiStringExtraData'])
    assert (back.strings[name], back.strings[value]) == ('Prn', 'WEAPON')
    blood, shape = (back.blocks[i][1] for i in back.blocks[0][1]['children'])
    assert back.strings[blood['name']] == 'Mask_Blood:0' and blood['flags'] == shape['flags'] | W.HIDDEN
    assert back.strings[back.blocks[blood['shader']][1]['name']] == W.BLOOD_MATERIAL
    assert blood['vertices'] == shape['vertices']


def test_headgear_slots_follow_vanillas_hats_glasses_and_masks():
    """FNV flags: the hockey mask keeps the hair (no hair bit), the hat hides it; a body flag is not headgear."""
    assert H.slots(19968) == (46, 47, 48, 49)
    assert H.slots(1538) == (30, 46)
    assert H.slots(18432) == (47, 48, 49)
    assert H.slots(4) is None and H.slots(0) is None


def test_worn_headgear_is_skinned_to_head_in_the_fitted_frame():
    """The fit's inverse moves the vertices; one HEAD bone takes every weight; the trailer is vanilla's pattern."""
    rot = (0.0, 0.0, -1.0, 0.065, 0.998, 0.0, 0.998, -0.065, 0.0)
    fit = H.HeadFit(2.0, np.eye(3), np.array([0.0, 1.0, 0.0]), (0.0, -0.88, 120.84), rot,
                    np.zeros((8, 3)), np.zeros((8, 3)), _sphere(1000.0), _sphere(0.1))
    back = F.read(H.worn(F.write(_quad_nif()), fit, (47,)))
    kinds = [k for k, _ in back.blocks]
    shape = back.blocks[kinds.index('BSSubIndexTriShape')][1]
    assert np.allclose(B.positions(shape).min(0), (-0.5, 4.0, 0.0), atol=1e-2)
    root, data, n, bone, scales = struct.unpack_from('<iiIiI', back.blocks[kinds.index('BSSkin::Instance')][1])
    assert (root, n, scales, back.strings[back.blocks[bone][1]['name']]) == (0, 1, 0, 'HEAD')
    bone_rot = struct.unpack_from('<9f', back.blocks[data][1], 4 + 16)
    assert np.allclose(np.array(bone_rot).reshape(3, 3), np.array(rot).reshape(3, 3).T, atol=1e-6)
    start, stride, count, _ = B.vertex_layout(shape)
    assert stride == 32 and all(shape[start + i * stride + 20:start + i * stride + 32]
                                == struct.pack('<4e', 1, 0, 0, 0) + bytes(4) for i in range(count))
    assert shape.endswith(struct.pack('<3I', 47, H.HEAD_BONE_ID, 0) + struct.pack('<H', 0))


def _sphere(radius: float, center=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Points over a sphere."""
    a, b = np.meshgrid(np.linspace(0, np.pi, 30), np.linspace(0, 2 * np.pi, 60))
    unit = np.c_[(np.sin(a) * np.cos(b)).ravel(), (np.sin(a) * np.sin(b)).ravel(), np.cos(a).ravel()]
    return np.asarray(center) + radius * unit


def test_hat_hiding_hair_tips_back_to_the_hair_line_about_its_front_brim():
    """A brim ring sloping up toward the back: tipped until the back brim is at HAIR_LINE, the front brim kept."""
    angle = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    ring = np.c_[8 * np.cos(angle), 8 * np.sin(angle), 4.0 - 0.25 * 8 * np.sin(angle)]
    out, turn = H.tipped(ring)
    assert H._brim(ring, -90) > H.HAIR_LINE and H._brim(out, -90) == pytest.approx(H.HAIR_LINE, abs=0.01)
    assert H._brim(out, 90) == pytest.approx(H._brim(ring, 90), abs=1e-6)
    assert np.allclose(turn @ turn.T, np.eye(3))
    low = ring - (0.0, 0.0, 5.0)
    assert H.tipped(low)[0] is low


def test_cleared_keeps_fnvs_clearance_from_fo4s_head():
    """A point 1 outside FNV's head (radius 5) but inside FO4's (radius 7) ends 1 outside FO4's; one placed
    further out than its FNV clearance stays."""
    fit = H.HeadFit(1.0, np.eye(3), np.zeros(3), (0.0,) * 3, C.IDENTITY, np.zeros((8, 3)), np.zeros((8, 3)),
                    _sphere(5.0), _sphere(7.0))
    fnv, placed = np.array([(0.0, -6.0, 0.0), (0.0, 0.0, 6.0)]), np.array([(0.0, -6.0, 0.0), (0.0, 0.0, 9.0)])
    out = fit.cleared(fnv, placed)
    assert np.linalg.norm(out[0]) == pytest.approx(8.0, abs=0.1) and np.allclose(out[1], placed[1])


def _node(nif, name: str, translation=(0.0, 0.0, 0.0), children=()) -> dict:
    """A NiNode dict named `name`."""
    return {'name': nif.string(name), 'extra': [], 'controller': -1, 'flags': 14, 'translation': translation,
            'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1, 'children': list(children)}


def _box_shape(nif, name: str, lo, hi, shader: int) -> dict:
    """A two-triangle BSTriShape dict spanning `lo` to `hi`."""
    pos = np.array([lo, (hi[0], lo[1], lo[2]), hi, (lo[0], hi[1], hi[2])], float)
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    tris = np.array([(0, 1, 2), (0, 2, 3)])
    return {'name': nif.string(name), 'extra': [], 'controller': -1, 'flags': 14, 'translation': (0.0,) * 3,
            'rotation': C.IDENTITY, 'scale': 1.0, 'collision': -1, 'bound': (0.0, 0.0, 0.0, 1.0), 'skin': -1,
            'shader': shader, 'alpha_property': -1, 'vertex_desc': C.DESC_PLAIN,
            'vertices': C.vertices(pos, uv, np.tile((0.0, 0.0, 1.0), (4, 1)), None, tris),
            'triangles': [tuple(t) for t in tris.tolist()]}


def test_fnv_gun_hangs_on_the_receivers_bones_turned_and_trigger_aligned():
    """FNV (+X long, +Y up) turns to FO4's (+Y long, +Z up); trigger tops meet; the clip hangs from WeaponMagazine;
    the receiver's own shapes stay shapes with no geometry; the muzzle moves to FNV's."""
    rec = F.NifFile()
    rec.blocks = [('NiNode', _node(rec, 'WEAPON', children=[1, 2, 4, 5])),
                  ('NiNode', _node(rec, 'WeaponMagazine', (0.0, 20.0, 0.0))),
                  ('NiNode', _node(rec, 'WeaponTrigger', (0.0, 10.0, 0.0), [3])),
                  ('BSTriShape', _box_shape(rec, 'OldTrigger:0', (0, 0, -2), (0.2, 0.5, 0), 6)),
                  ('NiNode', _node(rec, 'Body', children=[7, 8])),
                  ('NiNode', _node(rec, 'WeaponBolt', (0.0, 15.0, 1.0))),
                  ('BSLightingShaderProperty', C.lighting_shader(rec, 'materials\\old.bgsm', -1, 0)),
                  ('NiNode', _node(rec, 'ProjectileNode', (0.0, 30.0, 1.0))),
                  ('BSTriShape', _box_shape(rec, 'OldBody:0', (-1, 0, -1), (1, 30, 1), 6))]
    src = F.NifFile()
    src.blocks = [('NiNode', _node(src, 'Gun', children=[1, 2, 3])),
                  ('BSTriShape', _box_shape(src, '##Trigger:0', (2, -2, 0), (2.5, 0, 0.2), 4)),
                  ('BSTriShape', _box_shape(src, '##Clip:1', (8, -6, 0), (10, 0, 0.5), 4)),
                  ('BSTriShape', _box_shape(src, 'Gun:0', (-5, 0, -1), (20, 3, 1), 4)),
                  ('BSLightingShaderProperty', C.lighting_shader(src, 'materials\\fnv\\gun.bgsm', -1, 0))]
    out = F.read(G.gun(F.write(src), {'ProjectileNode': np.array([22.0, 1.5, 0.0])}, F.write(rec)))
    worlds = G._worlds(out)
    names = {out.strings[b['name']]: i for i, (k, b) in enumerate(out.blocks) if isinstance(b, dict) and 'name' in b}
    for old in ('OldTrigger:0', 'OldBody:0'):
        assert out.blocks[names[old]][0] == 'BSTriShape' and out.blocks[names[old]][1]['vertices'] == []
    placed = {n: G._moved(np.array([v['position'] for v in out.blocks[names[n]][1]['vertices']], float),
                          worlds[names[n]]) for n in ('##Trigger:0', '##Clip:1', 'Gun:0')}
    assert np.allclose(G._trigger_top(placed["##Trigger:0"]), (0.1, 10.25, 0.0), atol=0.01)
    assert names['##Clip:1'] in out.blocks[names['WeaponMagazine']][1]['children']
    assert np.ptp(placed['Gun:0'][:, 1]) == pytest.approx(25.0, abs=0.01)
    assert np.allclose(worlds[names["ProjectileNode"]][3, :3], (0.0, 30.0, 1.5), atol=0.01)


def test_part_move_turns_and_stretches_a_bone_onto_fo4s():
    """FNV's forearm (along +X, length 10) onto FO4's (down, length 12): its joint and end land on FO4's; a point
    beside the joint keeps its distance from the bone."""
    move, shift = O.part_move((0, 0, 0), (10, 0, 0), (5, 5, 5), (5, 5, -7))
    assert np.allclose(move @ (0, 0, 0) + shift, (5, 5, 5)) and np.allclose(move @ (10, 0, 0) + shift, (5, 5, -7))
    beside = move @ np.array([0.0, 2.0, 0.0]) + shift
    assert np.linalg.norm(beside - (5, 5, 5)) == pytest.approx(2.0)


def test_bone_moves_follow_their_part_and_fall_back_to_a_mapped_ancestor():
    """A twist bone takes its upper arm's move; a finger (unmapped) its hand's; the pelvis only shifts."""
    fnv = {b: np.zeros(3) for b in O.BONES}
    fo4 = {b: np.zeros(3) for b in O.BONES.values()}
    for i, bone in enumerate(O.BONES):
        fnv[bone] = np.array([i, 1.0 + i * i, 2.0 * i])
        fo4[O.BONES[bone]] = fnv[bone] + (0.0, 0.5 * i, 1.0)
    parents = {'Bip01 L Finger0': 'Bip01 L Hand', 'Bip01 L Hand': 'Bip01 L Forearm'}
    moves = O.bone_moves(fnv, parents, fo4)
    assert moves['Bip01 LUpArmTwistBone'] is moves['Bip01 L UpperArm']
    assert moves['Bip01 L Finger0'] is moves['Bip01 L Forearm']
    assert np.allclose(moves['Bip01 Pelvis'][0], np.eye(3))
    assert np.allclose(moves['Bip01 Pelvis'][0] @ fnv['Bip01 Pelvis'] + moves['Bip01 Pelvis'][1], fo4['Pelvis'])


def test_segments_follow_vanillas_body_order():
    """Arms 2 and 4 (collarbones and shoulders are torso), legs 5 and 6; the trailer counts triangles in order."""
    assert [O.segment_of(b) for b in ('LArm_ForeArm1_skin', 'RArm_Hand', 'LArm_Collarbone', 'RArm_ShoulderFat_skin',
                                      'LLeg_Calf_skin', 'RLeg_Foot', 'SPINE2', 'Neck_skin')] == [2, 4, 3, 3, 5, 6, 3, 3]
    raw = O._segments([0, 0, 2, 3, 0])
    assert struct.unpack_from('<3I', raw) == (5, 5, 5)
    assert [struct.unpack_from('<4I', raw, 12 + 16 * i) for i in (2, 3)] == [(0, 2, H.NO_PARENT, 0),
                                                                            (6, 3, H.NO_PARENT, 0)]
    kept, counts = O._segment_order(np.array([3, 2, 5, 4, 2]), True)
    assert kept.tolist() == [1, 4, 3] and counts == [0, 0, 2, 0, 1]


def test_caps_are_fnvs_dismemberment_partitions():
    """Partitions 100-999 are caps; torso sections (1000 and up) and body parts are drawn."""
    class Part:
        def __init__(self, n):
            self.body_part = n

    class Shape:
        def __init__(self, parts):
            self.skin_instance = type('Skin', (), {'partitions': [Part(n) for n in parts]})()

    assert O.is_cap(Shape([205, 203])) and O.is_cap(Shape([101]))
    assert not O.is_cap(Shape([5000, 5, 3000, 3])) and not O.is_cap(Shape([0, 7, 10]))


def test_skin_tint_shader_round_trips():
    """A type-5 lighting shader keeps its skin tint colour through the reader and packer."""
    nif = F.NifFile()
    shader = dict(C.lighting_shader(nif, 'materials\\skin.bgsm', 1, 0), shader_type=K.SHADER_SKIN_TINT,
                  skin_tint=(0.25, 0.5, 1.0, 0.75))
    back = K.read_lighting(K.Reader(K.pack_lighting(shader)))
    assert back['shader_type'] == 5 and back['skin_tint'] == (0.25, 0.5, 1.0, 0.75)


def test_converted_vertices_find_their_own_fnv_original_where_positions_are_shared():
    """A hem's two sides share positions with opposite normals; a UV seam shares position and normal."""
    pos = np.array([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (5.0, 0.0, 0.0)])
    uv = np.array([(0.1, 0.1), (0.1, 0.1), (0.6, 0.1), (0.2, 0.2)])
    nrm = np.array([(0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 1.0, 0.0)])
    order = [2, 3, 1, 0]
    rounded = (pos[order] + 0.03, uv[order], nrm[order] * 0.98)
    assert O.originals(rounded, (pos, uv, nrm)).tolist() == order

