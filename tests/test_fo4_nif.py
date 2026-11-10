"""FO4 meshes and materials from FNV statics: formats, tangent convention, specular, glass.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

import struct
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree

from fo4_import.nif import bgem, bgsm
from fo4_import.nif import convert_static as C
from fo4_import.nif import creature as CR
from fo4_import.nif.addons import addon_map
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face import bake as B
from fo4_import.nif import file as F
from fo4_import.nif import blocks as K
from fo4_import.nif import gun as G
from fo4_import.nif import headgear as H
from fo4_import.nif import outfit as O
from fo4_import.nif.particle_blocks import PARTICLE_BLOCKS
from fo4_import.nif import retarget as RT
from fo4_import.nif import stairs as S
from fo4_import.nif import tree as T
from fo4_import.nif import weapon as W
from fo4_import.pipeline.elric_cache import mesh_bytes
from fo4_import.spike.statics import write_assets

SHELF = Path('export/FalloutNV.esm/meshes/furniture/shelveswoodenhalf02.nif')


GRASS = Path('export/FalloutNV.esm/meshes/landscape/grass/grasswasteland05.nif')


@pytest.mark.skipif(not GRASS.exists(), reason='needs the FalloutNV.esm export')
def test_grass_keeps_its_vertex_alpha_ramp():
    """FNV grass keeps its vertex alpha, rising from 0 at the base, as FO4's grass expects."""
    shape = next(b for k, b in C.convert(str(GRASS)).nif.blocks if k == 'BSTriShape')
    alpha = np.array([v['color'][3] for v in shape['vertices']])
    height = np.array([v['position'][2] for v in shape['vertices']])
    assert alpha.min() == 0 and alpha.max() < 255 and np.corrcoef(height, alpha)[0, 1] > 0.5


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
    nodes = {'ProjectileNode': np.array([22.0, 1.5, 0.0])}
    out = F.read(G.gun(F.write(src), nodes, F.write(rec), G.placement(F.write(src), nodes, F.write(rec))))
    worlds = G.node_worlds(out)
    names = {out.strings[b['name']]: i for i, (k, b) in enumerate(out.blocks) if isinstance(b, dict) and 'name' in b}
    for old in ('OldTrigger:0', 'OldBody:0'):
        assert out.blocks[names[old]][0] == 'BSTriShape' and out.blocks[names[old]][1]['vertices'] == []
    placed = {n: G._moved(np.array([v['position'] for v in out.blocks[names[n]][1]['vertices']], float),
                          worlds[names[n]]) for n in ('##Trigger:0', '##Clip:1', 'Gun:0')}
    assert np.allclose(G._trigger_top(placed["##Trigger:0"]), (0.1, 10.25, 0.0), atol=0.01)
    assert names['##Clip:1'] in out.blocks[names['WeaponMagazine']][1]['children']
    assert np.ptp(placed['Gun:0'][:, 1]) == pytest.approx(25.0, abs=0.01)
    assert np.allclose(worlds[names["ProjectileNode"]][3, :3], (0.0, 30.0, 1.5), atol=0.01)


def test_a_trigger_bone_with_nothing_drawn_does_not_move_the_gun():
    """A receiver whose trigger another part draws (FO4's laser) keeps a placeholder bone far off the gun: the FNV
    gun stays at its own origin, where both games put the hand."""
    rec = F.NifFile()
    rec.blocks = [('NiNode', _node(rec, 'WEAPON', children=[1, 2])),
                  ('NiNode', _node(rec, 'WeaponTrigger', (-1.8, -8.6, -19.4))),
                  ('BSTriShape', _box_shape(rec, 'Receiver:0', (-2, 0, 0), (2, 13, 6), 3)),
                  ('BSLightingShaderProperty', C.lighting_shader(rec, 'materials\\old.bgsm', -1, 0))]
    src = F.NifFile()
    src.blocks = [('NiNode', _node(src, 'Gun', children=[1, 2])),
                  ('BSTriShape', _box_shape(src, '##Trigger:0', (2, -2, 0), (2.5, 0, 0.2), 3)),
                  ('BSTriShape', _box_shape(src, 'Gun:0', (-5, 0, -1), (20, 3, 1), 3)),
                  ('BSLightingShaderProperty', C.lighting_shader(src, 'materials\\fnv\\gun.bgsm', -1, 0))]
    assert np.allclose(G.placement(F.write(src), {}, F.write(rec))[3, :3], 0.0)


def test_a_gun_parts_shader_controller_comes_with_it():
    """An FNV part's shader controller, interpolator and keys are copied with its shader onto the gun, driving the
    copy (they kept the FNV mesh's block number, a node in the gun, and the game crashed on it).
    See: docs/fork/fo4_pipeline.md#gun-controllers
    """
    rec = F.NifFile()
    rec.blocks = [('NiNode', _node(rec, 'WEAPON', children=[1])),
                  ('BSTriShape', _box_shape(rec, 'Receiver:0', (-2, 0, 0), (2, 13, 6), 2)),
                  ('BSLightingShaderProperty', C.lighting_shader(rec, 'materials\\old.bgsm', -1, 0))]
    src = F.NifFile()
    shader = {**C.lighting_shader(src, 'materials\\fnv\\gun.bgsm', -1, 0), 'controller': 3}
    src.blocks = [('NiNode', _node(src, 'Gun', children=[1])),
                  ('BSTriShape', _box_shape(src, 'Gun:0', (-5, 0, -1), (20, 3, 1), 2)),
                  ('BSLightingShaderProperty', shader),
                  ('BSLightingShaderPropertyFloatController', {'next': -1, 'flags': 72, 'frequency': 1.0, 'phase': 0.0,
                                                               'start': 0.0, 'stop': 1.0, 'target': 2,
                                                               'interpolator': 4, 'variable': 11}),
                  ('NiFloatInterpolator', {'value': (0.0,), 'data': 5}),
                  ('NiFloatData', {'keys': {'kind': 1, 'keys': [(0.0, 0.0), (1.0, 1.0)]}})]
    out = F.read(G.gun(F.write(src), {}, F.write(rec), G.placement(F.write(src), {}, F.write(rec))))
    shape = next(b for k, b in out.blocks if k == 'BSTriShape' and out.strings[b['name']] == 'Gun:0')
    kind, ctl = out.blocks[out.blocks[shape['shader']][1]['controller']]
    assert kind == 'BSLightingShaderPropertyFloatController' and ctl['target'] == shape['shader']
    interp = out.blocks[ctl['interpolator']]
    assert interp[0] == 'NiFloatInterpolator' and out.blocks[interp[1]['data']][0] == 'NiFloatData'


def test_a_weapons_root_turn_is_left_out():
    """The game puts a weapon's root on its bone as is (FO4's Missile Launcher root is turned 180 degrees)."""
    nif = F.NifFile()
    root = _node(nif, 'MissileLauncher', (5.0, 0.0, 0.0), [1])
    root['rotation'] = (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
    nif.blocks = [('NiNode', root), ('NiNode', _node(nif, 'ProjectileNode', (0.0, 33.0, 11.0)))]
    worlds = G.node_worlds(nif)
    assert np.allclose(worlds[0], np.eye(4))
    assert np.allclose(worlds[1][3, :3], (0.0, 33.0, 11.0))


def test_a_hidden_backpack_is_not_drawn_on_the_gun():
    """Hide Backpack: the converted gun's Backpack part is dropped, the rest kept."""
    src = F.NifFile()
    src.blocks = [('NiNode', _node(src, 'Flamer', children=[1, 2])),
                  ('BSTriShape', _box_shape(src, '##FlamerGun:0', (0, 0, 0), (60, 4, 2), 3)),
                  ('BSTriShape', _box_shape(src, 'Backpack:0', (0, -40, 0), (30, -10, 2), 3)),
                  ('BSLightingShaderProperty', C.lighting_shader(src, 'materials\\fnv\\flamer.bgsm', -1, 0))]
    out = F.read(G.without(F.write(src), G.BACKPACK))
    assert [out.strings[out.blocks[c][1]['name']] for c in out.blocks[0][1]['children']] == ['##FlamerGun:0']


def test_part_move_turns_and_stretches_a_bone_onto_fo4s():
    """FNV's forearm (along +X, length 10) onto FO4's (down, length 12): its joint and end land on FO4's; a point
    beside the joint keeps its distance from the bone."""
    move, shift = RT.part_move((0, 0, 0), (10, 0, 0), (5, 5, 5), (5, 5, -7))
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
    moves = RT.bone_moves(O.HUMAN, fnv, parents, fo4)
    assert moves['Bip01 LUpArmTwistBone'] is moves['Bip01 L UpperArm']
    assert moves['Bip01 L Finger0'] is moves['Bip01 L Forearm']
    assert np.allclose(moves['Bip01 Pelvis'][0], np.eye(3))
    assert np.allclose(moves['Bip01 Pelvis'][0] @ fnv['Bip01 Pelvis'] + moves['Bip01 Pelvis'][1], fo4['Pelvis'])


def test_segments_follow_vanillas_body_order():
    """Arms 2 and 4 (collarbones and shoulders are torso), legs 5 and 6; the trailer counts triangles in order."""
    assert [O.segment_of(b) for b in ('LArm_ForeArm1_skin', 'RArm_Hand', 'LArm_Collarbone', 'RArm_ShoulderFat_skin',
                                      'LLeg_Calf_skin', 'RLeg_Foot', 'SPINE2', 'Neck_skin')] == [2, 4, 3, 3, 5, 6, 3, 3]
    raw = O.segments([0, 0, 2, 3, 0])
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


def test_specular_scale_keeps_fnvs_reflected_energy():
    """Glossiness n scales FNV specular by 2 pi / (n + 2), at most 1."""
    for n in (10.0, 30.0, 60.0):
        assert C.specular_scale(C.smoothness(n)) == pytest.approx(2 * np.pi / (n + 2), rel=1e-6)
    assert C.specular_scale(0.0) == 1.0


def test_open_edges_weld_split_vertices_and_find_the_rim():
    """Two triangles of a quad, one corner split in two (a UV seam): the four rim edges, not the diagonal."""
    pts = np.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)])
    edges = O.open_edges(pts, np.array([(0, 1, 2), (0, 4, 3)]))
    assert sorted(map(tuple, np.sort(pts[edges].sum(1), axis=1).tolist())) == sorted(
        map(tuple, np.sort(np.array([[1, 0, 0], [2, 1, 0], [1, 2, 0], [0, 1, 0]], float), axis=1).tolist()))


def test_seam_moves_the_edge_on_fnvs_body_edge_onto_fo4s_and_fades_inward():
    """A strip whose bottom edge was on FNV's body edge: that edge lands on FO4's, a row 1 up moves 2/3 as far,
    a row 4 up stays."""
    xs = np.arange(4.0)
    pts = np.array([(x, 0.0, z) for z in (0.0, 1.0, 4.0) for x in xs])
    tris = np.array([t for r in range(2) for c in range(3) for t in
                     ((r * 4 + c, r * 4 + c + 1, r * 4 + c + 5), (r * 4 + c, r * 4 + c + 5, r * 4 + c + 4))])
    fnv_edge = np.array([(x, 0.0, 0.0) for x in xs])
    fo4 = (np.array([(-1.0, 0.0, -1.0)]), np.array([(5.0, 0.0, -1.0)]))
    fit = O.BodyFit({}, None, None, None, [], [], [], None, None, None, 0, seams=[(fnv_edge, fo4)])
    out = fit.seamed(pts, pts, tris)
    assert np.allclose(out[:4, 2], -1.0) and np.allclose(out[4:8, 2], 1.0 - 1.0 * (1 - 1 / 3))
    assert np.allclose(out[8:], pts[8:])


def _ring(z: float, segments: int = 8) -> np.ndarray:
    """`segments` points on a radius-4 circle at height `z`."""
    a = np.linspace(0.0, 2 * np.pi, segments, endpoint=False)
    return np.stack([4 * np.cos(a), 4 * np.sin(a), np.full(segments, z)], axis=1)


def test_a_skin_loop_near_fnvs_body_edge_moves_whole():
    """A tube's bottom rim 1.0 from FNV's neck edge (past SEAM_REACH, within LOOP_REACH) lands on FO4's edge when
    the shape is skin, and stays when it is cloth; its top rim, 4 up, stays."""
    pts, n = np.vstack([_ring(0.0), _ring(4.0)]), 8
    tris = np.array([t for i in range(n) for t in ((i, (i + 1) % n, n + i), ((i + 1) % n, n + (i + 1) % n, n + i))])
    fo4_ring = _ring(-3.0, 64)
    fo4 = (fo4_ring, np.roll(fo4_ring, -1, axis=0))
    fit = O.BodyFit({}, None, None, None, [], [], [], None, None, None, 0, seams=[(_ring(-1.0), fo4)])
    skin, cloth = fit.seamed(pts, pts, tris, skin=True), fit.seamed(pts, pts, tris)
    assert np.allclose(skin[:n, 2], -3.0, atol=0.01) and np.allclose(skin[n:], pts[n:])
    assert np.allclose(cloth, pts)


def test_a_body_edge_fnv_lacks_gets_no_seam():
    """FO4's wrists and neck against FNV's wrists alone: each wrist pairs with its own, the neck with none (it
    took the left wrist on a tie, pulling left sleeves onto the neck)."""
    def rims(xs):
        """One open triangle per x: (points, triangles)."""
        pts = np.array([(x + dx, 0.0, dz) for x in xs for dx, dz in ((0, 0), (1, 0), (0, 1))], float)
        return pts, np.arange(len(pts)).reshape(-1, 3)
    fo4, fnv = rims((-10.0, 0.0, 10.0)), rims((-10.0, 10.0))
    seams = O._seams(*fo4, fnv, fnv[0])
    assert [(round(e[:, 0].mean()), round(a[:, 0].mean())) for e, (a, _) in seams] == [(-10, -10), (10, 10)]


def test_fnv_24_unit_steps_with_float_noise_are_marked():
    """The hotel's 24-unit risers read 24.003 apart after the Havok scale; each step still gets the stairs material
    and a riser."""
    rise = 24.0034 / 7.0
    tris = [tuple(tuple(c) for c in face) for i in range(3) for face in (
        ((0, 4 * i, rise * i), (4, 4 * i, rise * i), (4, 4 * i + 4, rise * i)),
        ((0, 4 * i, rise * i), (4, 4 * i + 4, rise * i), (0, 4 * i + 4, rise * i)))]
    out, mats, _ = S.stairs(tris, [0] * len(tris), 7.0, lambda m: m + 1)
    assert len(out) - len(tris) == 4 and all(1 in mats[k:k + 2] for k in range(0, len(tris), 2))


def _flight(steps: int, rise: float = 24.0, run: float = 27.0) -> list:
    """`steps` + 1 floating treads, 100 wide, `run` deep, `rise` apart, up +Y."""
    return [tuple(tuple(c) for c in face) for i in range(steps + 1) for face in (
        ((0, run * i, rise * i), (100, run * i, rise * i), (100, run * i + run, rise * i)),
        ((0, run * i, rise * i), (100, run * i + run, rise * i), (0, run * i + run, rise * i)))]


def test_a_flight_gets_one_stair_helper_ramp_through_its_nosings_and_two_low_steps_none():
    """Four steps up: one 8-corner slab, its top face from the foot of the first riser to the last nosing, as wide
    as the treads; two 24-unit steps (a catwalk turn's half) get one, two 12-unit steps none."""
    (corners, crc), = S.stairs(_flight(4), [0] * 10, 1.0, lambda m: m + 1)[2]
    top = {(round(float(c[0])), round(float(c[1])), round(float(c[2]))) for c in corners[::2]}
    assert crc == 1 and len(corners) == 8 and top == {(0, 0, 0), (100, 0, 0), (0, 108, 96), (100, 108, 96)}
    assert np.allclose(corners[::2, 2] - corners[1::2, 2], S.RAMP_THICK)
    assert len(S.stairs(_flight(2), [0] * 6, 1.0, lambda m: m + 1)[2]) == 1
    assert S.stairs(_flight(2, rise=12.0), [0] * 6, 1.0, lambda m: m + 1)[2] == []


def test_a_flight_whose_first_steps_are_elsewhere_ramps_down_to_the_floor_but_one_off_a_landing_does_not():
    """UtlCatStairsHalfTop: four steps standing 48 above the body's lowest point (a stringer down to 0) get a slab
    reaching down to 0; with a deep landing at the foot's level the slab starts on the landing."""
    raised = [tuple((x, y, z + 48) for x, y, z in face) for face in _flight(4)]
    stringer = [((-10, 0, 0), (-10, 108, 144), (-10, 0, 144))]
    landing = [((0, -100, 48), (100, 0, 48), (100, -100, 48)), ((0, -100, 48), (0, 0, 48), (100, 0, 48))]
    feet = []
    for tris in (raised + stringer, raised + stringer + landing):
        (corners, _), = S.stairs(tris, [0] * len(tris), 1.0, lambda m: m + 1)[2]
        feet.append(round(float(corners[::2, 2].min())))
    assert feet == [0, 48]


def test_skin_uv_extends_one_body_triangles_mapping_and_stretch_compares_uv_to_size():
    """A point off a triangle's corner takes its mapping extended; a triangle spanning the atlas is stretched."""
    corners = np.array([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)])
    uvs = np.array([(0.1, 0.1), (0.2, 0.1), (0.1, 0.2)])
    assert np.allclose(O._affine_uv(np.array([12.0, 1.0, 3.0]), corners, uvs), (0.22, 0.11))
    tris = np.array([(0, 1, 2)])
    assert O.uv_stretch(corners, uvs, tris)[0] == pytest.approx(0.1 * np.sqrt(2) / (10 * np.sqrt(2)))
    assert O.uv_stretch(corners, np.array([(0.1, 0.1), (0.9, 0.1), (0.1, 0.2)]), tris)[0] > 0.05


SHRUB = {'EditorID': 'WastelandShrub01', 'Model.MODL': 'WastelandShrub01.spt', 'ICON': 'WastelandShrub01Foliage.dds',
         'Seed[0]': '1'}


@pytest.mark.skipif(not Path('export/FalloutNV.esm/trees/wastelandshrub01.spt').exists(),
                    reason='needs the FalloutNV.esm export')
def test_a_speedtree_becomes_a_wind_animated_tree_like_vanillas():
    """BSLeafAnimNode root with BSX 130, bark and leaves (Tree Anim shader, two-sided tree-flagged material), a body."""
    out = T.tree_mesh(Path('export/FalloutNV.esm'), SHRUB)
    kinds = [k for k, _ in out.nif.blocks]
    assert kinds[:2] == ['BSLeafAnimNode', 'BSXFlags'] and out.nif.blocks[1][1]['value'] == T.TREE_BSX
    assert kinds.count('BSTriShape') == 2 and 'bhkCollisionObject' in kinds
    leaves = next(b for k, b in out.nif.blocks if k == 'BSLightingShaderProperty' and b['flags2'] & 0x20000000)
    material = out.materials[out.nif.strings[leaves['name']]]
    assert material['tree'] and material['two_sided'] and material['alpha_test']


DOOR = Path('export/FalloutNV.esm/meshes/dungeons/nv_craftsmanhomesinterior/nvcraftsmanrmdooranimated.nif')


@pytest.mark.skipif(not DOOR.exists(), reason='needs the FalloutNV.esm export')
def test_an_animated_fnv_door_keeps_its_moving_node_and_sequences():
    """The panel stays its own node (shape and collision on it); Open and Close drive it; BSX gets Animated."""
    nif = F.read(F.write(C.convert(str(DOOR), 'export/FalloutNV.esm').nif))
    name = {i: nif.strings[b['name']] for i, (k, b) in enumerate(nif.blocks) if k == 'NiNode'}
    panel = next(i for i, n in name.items() if n == 'OffDoorHotelSm')
    node = nif.blocks[panel][1]
    assert nif.blocks[node['children'][0]][0] == 'BSTriShape' and node['collision'] != K.NONE
    sequences = [b for k, b in nif.blocks if k == 'NiControllerSequence']
    assert [nif.strings[b['name']] for b in sequences] == ['Open', 'Close']
    assert all(nif.strings[c['node']] == 'OffDoorHotelSm' for b in sequences for c in b['blocks'])
    assert nif.blocks[0][1]['controller'] != K.NONE
    assert next(b['value'] for k, b in nif.blocks if k == 'BSXFlags') & C.BSX_ANIMATED
    assert not C.convert(str(DOOR), 'export/FalloutNV.esm', animated=False).nif.blocks[0][1]['controller'] >= 0



SALOON_LIGHTS = Path('export/FalloutNV.esm/meshes/architecture/goodsprings/nv_prospectorsaloon_lights.nif')


@pytest.mark.skipif(not SALOON_LIGHTS.exists(), reason='needs the FalloutNV.esm export')
def test_shader_animation_drives_the_shapes_shader_through_idle_blend_controllers():
    """The saloon's Left/Right light states: emittance and emissive colour on the window glass's lighting shader,
    each controller's own interpolator an idle blend (it ran Left forever: solid yellow windows)."""
    nif = F.read(F.write(C.convert(str(SALOON_LIGHTS), 'export/FalloutNV.esm').nif))
    controllers = {(k, b['variable']): b for k, b in nif.blocks
                   if k.startswith('BSLightingShaderProperty') and k.endswith('Controller')}
    assert set(controllers) == {('BSLightingShaderPropertyFloatController', 11),
                                ('BSLightingShaderPropertyColorController', 1)}
    blends = [nif.blocks[b['interpolator']] for b in controllers.values()]
    assert all(k.startswith('NiBlend') and b['flags'] == 1 and min(np.atleast_1d(b['value'])) < -1e38 for k, b in blends)
    blocks = [c for k, b in nif.blocks if k == 'NiControllerSequence' for c in b['blocks']]
    shader_blocks = [c for c in blocks if nif.strings[c['property']] == 'BSLightingShaderProperty']
    assert {nif.strings[c['controller_id']] for c in shader_blocks} == {'11', '1'}
    assert all(nif.blocks[c['interpolator']][0] in ('NiFloatInterpolator', 'NiPoint3Interpolator') for c in shader_blocks)


WHIRLWIND = Path('export/FalloutNV.esm/meshes/effects/ambient/fxdustwhirlwind01.nif')


@pytest.mark.skipif(not WHIRLWIND.exists(), reason='needs the FalloutNV.esm export')
def test_a_particle_controller_only_drives_a_modifier_its_system_has():
    """Goodsprings crashed (NiPSysModifierActiveCtlr on a null modifier): every particle controller's modifier
    name is one of its system's converted modifiers."""
    nif = F.read(F.write(C.convert(str(WHIRLWIND), 'export/FalloutNV.esm').nif))
    name = lambda i: nif.strings[i] if i >= 0 else ''
    for kind, system in nif.blocks:
        if kind != 'NiParticleSystem':
            continue
        modifiers = {name(nif.blocks[m][1]['name']) for m in system['modifiers']}
        controller = system['controller']
        while controller >= 0:
            block = nif.blocks[controller][1]
            assert 'modifier_name' not in block or name(block['modifier_name']) in modifiers
            controller = block['next']


@pytest.mark.skipif(not WHIRLWIND.exists(), reason='needs the FalloutNV.esm export')
def test_a_mesh_emitter_points_at_a_hidden_emitter_shape_and_the_modifiers_stay_modifiers():
    """The whirlwind crashed loading: its emitter shape was made mid-way through the modifiers, shifting them onto
    the shape and its BSPositionData. Each system's modifiers are modifiers; the emitter shape is vanilla's form."""
    nif = F.read(F.write(C.convert(str(WHIRLWIND), 'export/FalloutNV.esm').nif))
    for kind, system in nif.blocks:
        if kind == 'NiParticleSystem':
            assert all(nif.blocks[m][0].startswith(('NiPSys', 'BSPSys')) for m in system['modifiers'])
    emitters = [b for k, b in nif.blocks if k == 'NiPSysMeshEmitter']
    shape = nif.blocks[emitters[0]['meshes'][0]][1]
    assert len(emitters) == 2 and emitters[0]['meshes'] == emitters[1]['meshes']
    assert shape['flags'] & 1 and shape['vertex_desc'] == 0 and shape['shader'] == K.NONE
    triangles, corners = shape['counts']
    position = nif.blocks[shape['extra'][0]]
    assert position[0] == 'BSPositionData' and corners == 3 * triangles and len(position[1]['values']) == 7 * corners


SNOW_GLOBE = Path('export/FalloutNV.esm/meshes/clutter/snowglobes/snowglobes_goodsprings.nif')


@pytest.mark.skipif(not SNOW_GLOBE.exists(), reason='needs the FalloutNV.esm export')
def test_a_collider_manager_keeps_its_chain_of_colliders_on_kept_nodes():
    """The snow globe's flakes fell through the glass: its colliders were dropped. Each of its 5 systems keeps its
    manager and its 15 colliders, chained, each naming its manager, its spawn modifier and a kept node."""
    nif = F.read(F.write(C.convert(str(SNOW_GLOBE), 'export/FalloutNV.esm').nif))
    managers = [b for k, b in nif.blocks if k == 'NiPSysColliderManager']
    assert len(managers) == 5
    for manager in managers:
        chain, at = [], manager['collider']
        while at != K.NONE:
            kind, collider = nif.blocks[at]
            assert kind in ('NiPSysPlanarCollider', 'NiPSysSphericalCollider')
            assert nif.blocks[collider['parent']][1] is manager
            assert nif.blocks[collider['spawn_modifier']][0] == 'NiPSysSpawnModifier'
            assert nif.blocks[collider['collider_object']][0] == 'NiNode'
            chain.append(at)
            at = collider['next_collider']
        assert len(chain) == 15


@pytest.mark.skipif(not (FALLOUT4_DIR / 'Data').exists(), reason='needs Fallout 4')
def test_every_particle_block_layout_round_trips_a_vanilla_effect_mesh():
    """particle_blocks reads each vanilla block to its exact length and packs back the same bytes."""
    data = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2').read('meshes\\effects\\dustfloatingslow.nif')
    _, entries, pos = F.read_header(data)
    seen = set()
    for kind, size in entries:
        raw, pos = data[pos:pos + size], pos + size
        if kind in PARTICLE_BLOCKS:
            reader, packer = PARTICLE_BLOCKS[kind]
            r = K.Reader(raw)
            assert packer(reader(r)) == raw and r.pos == len(raw), kind
            seen.add(kind)
    assert {'NiParticleSystem', 'NiPSysData', 'NiPSysBoxEmitter', 'BSPSysSimpleColorModifier'} <= seen


#: Byte of a pre-Elric bhkRigidBody holding its motion system (after the 32-byte head and the body info before it).
MOTION_BYTE = 216


@pytest.mark.skipif(not DOOR.exists(), reason='needs the FalloutNV.esm export')
def test_an_animated_doors_moving_body_is_keyframed_and_a_static_ones_fixed():
    """The panel's keyframed FNV body stays keyframed when it animates, else becomes fixed (the door held still)."""
    for animated, motion in ((True, 4), (False, 5)):
        nif = C.convert(str(DOOR), 'export/FalloutNV.esm', animated=animated).nif
        bodies = [b for k, b in nif.blocks if k.startswith('bhkRigidBody')]
        assert [b[MOTION_BYTE] for b in bodies] == [motion]


FLAG = Path('export/FalloutNV.esm/meshes/clutter/flags/nv_nevadaflag.nif')


@pytest.mark.skipif(not FLAG.exists(), reason='needs the FalloutNV.esm export')
def test_a_skinned_flag_keeps_its_skin_and_matches_fnvs_deformation():
    """Each flag shape is skinned to the kept bones; at the stored pose it lands where pyffi's skinning puts FNV's."""
    nif = F.read(F.write(C.convert(str(FLAG), 'export/FalloutNV.esm').nif))
    parent = {c: i for i, (k, b) in enumerate(nif.blocks) if k == 'NiNode' for c in b['children']}

    def world(i):
        """Column-form world transform of node `i`."""
        b, m = nif.blocks[i][1], np.eye(4)
        m[:3, :3], m[:3, 3] = np.array(b['rotation']).reshape(3, 3) * b['scale'], b['translation']
        return world(parent[i]) @ m if i in parent else m

    data = C.NifFormat.Data()
    with open(FLAG, 'rb') as f:
        data.read(f)
    root = data.roots[0]
    fnv = {g.name.decode(): g for g in root.tree() if isinstance(g, C.NifFormat.NiTriBasedGeom) and g.skin_instance}
    shapes = [b for k, b in nif.blocks if k == 'BSTriShape']
    assert shapes and all(b['skin'] != K.NONE for b in shapes)
    for b in shapes:
        _, data_index, n = struct.unpack_from('<iiI', nif.blocks[b['skin']][1])
        bones = struct.unpack_from(f'<{n}i', nif.blocks[b['skin']][1], 12)
        mats = []
        for j in range(n):
            v = struct.unpack_from('<4f9f3ff', nif.blocks[data_index][1], 4 + j * 68)
            m = np.eye(4)
            m[:3, :3], m[:3, 3] = np.array(v[4:13]).reshape(3, 3), v[13:16]
            mats.append(world(bones[j]) @ m)
        ours = np.array([sum(w * (mats[i] @ np.array([*v['position'], 1.0]))[:3] for w, i in zip(v['weights'], v['bones']))
                         for v in b['vertices']])
        g = fnv[nif.strings[b['name']]]
        ref = np.array([(d.x, d.y, d.z, 1.0) for d in g.get_skin_deformation()[0]]) @ np.array(
            g.get_transform(root).as_list())
        assert np.linalg.norm(ours[:, None] - ref[None, :, :3], axis=2).min(axis=1).max() < 0.2


@pytest.mark.skipif(not DOOR.exists() or not SHELF.exists(), reason='needs the FalloutNV.esm export')
def test_a_load_door_is_written_static_beside_its_animated_mesh(tmp_path):
    """An animated door's load copy is <name>load.nif with no controller; a mesh with no animation has none."""
    export = Path('export/FalloutNV.esm')
    model = str(DOOR.relative_to(export / 'meshes'))
    path, _ = write_assets(export, model, tmp_path, load=True)
    assert path.endswith('nvcraftsmanrmdooranimatedload.nif')
    nif = F.read(mesh_bytes(tmp_path / 'Meshes' / path))
    assert nif.blocks[0][1]['controller'] == K.NONE
    assert write_assets(export, str(SHELF.relative_to(export / 'meshes')), tmp_path, load=True) is None


DOG = Path('export/FalloutNV.esm/meshes/creatures/dog')


@pytest.mark.skipif(not (DOG / 'dogskin.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the FalloutNV.esm export and Fallout 4')
def _creature_shapes(folder: Path, parts: tuple, skin: str = None) -> tuple:
    """(fit, {shape name: positions}, the NIF) of FNV creature `parts` in `folder` on its FO4 pair (over FO4's body
    with FNV bare skin texture `skin`); every shape skinned, no dismemberment cap among them."""
    export = next(p for p in folder.parents if p.suffix == '.esm')
    key = '\\'.join(folder.relative_to(export / 'meshes').parts)
    fit = CR.creature_fit(export, key, Archives(FALLOUT4_DIR / 'Data'))
    converted = [(C.convert(str(folder / n), str(export), animated=False), folder / n) for n in parts]
    nif = F.read(F.write(CR.creature_mesh(converted, fit, CR.PAIRS[key].rig.root,
                                          CR.skeleton_parents(folder / 'skeleton.nif'), skin).nif))
    shapes = {}
    for kind, raw in nif.blocks:
        if kind == 'BSSubIndexTriShape':
            shape = K.read_tri_shape(K.Reader(raw))
            assert shape['skin'] != K.NONE
            shapes[nif.strings[shape['name']]] = np.array([v['position'] for v in shape['vertices']])
    assert not any(n.startswith('MeatCap') for n in shapes)
    return fit, shapes, nif


@pytest.mark.skipif(not (DOG / 'dogskin.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the FalloutNV.esm export and Fallout 4')
def test_fnvs_dog_sits_on_dogmeats_skeleton_with_its_eyes_level():
    """Cheyenne's parts on Dogmeat: the body on Dogmeat's surface, the eyes symmetric."""
    fit, shapes, _ = _creature_shapes(DOG, ('dogskin.nif', 'eyessetblue.nif'))
    assert np.median(cKDTree(fit.samples[0]).query(shapes['Dog'])[0]) < 1.0
    eyes = shapes['EyesBlue:0']
    assert abs(eyes[:, 0].min() + eyes[:, 0].max()) < 0.5 and 25 < eyes[:, 1].mean() < 35


SUPER_MUTANT = Path('export/FalloutNV.esm/meshes/creatures/smspinebreaker')


@pytest.mark.skipif(not (SUPER_MUTANT / 'nv_sm_v2_1_base.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the FalloutNV.esm export and Fallout 4')
def test_fnvs_super_mutant_stands_in_fo4s_super_mutant_body_space():
    """FO4's super mutant body skins 140 units below its skeleton: FNV's mutant and armor land on it, feet on its
    soles."""
    fit, shapes, _ = _creature_shapes(SUPER_MUTANT, ('nv_sm_v2_1_base.nif', 'smspinebreakerlight.nif'))
    near = cKDTree(fit.samples[0])
    assert np.median(near.query(shapes['New_UV_lo_lfeet:0'])[0]) < 2.0
    assert np.median(near.query(shapes['Boots00:0'])[0]) < 3.0
    assert abs(shapes['Boots00:0'][:, 2].min() - fit.samples[0][:, 2].min()) < 2.0


GHOSTS = Path('export/DeadMoney.esm/meshes/nvdlc01/creatures/ghosts')


@pytest.mark.skipif(not (GHOSTS / 'nvdlc01ghost.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the DeadMoney.esm export and Fallout 4')
def test_a_ghost_person_wears_its_suit_on_fo4s_human_its_hood_on_the_head_bone():
    """Dead Money's ghost suit on FO4's human body (no HEAD of its own, so the fit adds the skeleton's): the hood
    turns with HEAD, the gloves sit at the wrists."""
    fit, shapes, nif = _creature_shapes(GHOSTS, ('nvdlc01ghost.nif', 'nvdlc01glovel.nif', 'nvdlc01glover.nif'))
    assert 'HEAD' in fit.bones
    joint = {b: -r.T @ t for b, (_, r, t) in zip(fit.bones, fit.bind)}
    assert np.linalg.norm(shapes['ghosthelmet:0'].mean(0) - joint['HEAD']) < 10
    assert np.linalg.norm(shapes['leftglove'].mean(0) - joint['LArm_Hand']) < 15
    hood = next(K.read_tri_shape(K.Reader(raw)) for kind, raw in nif.blocks if kind == 'BSSubIndexTriShape'
                and nif.strings[K.read_tri_shape(K.Reader(raw))['name']] == 'ghosthelmet:1')
    assert [nif.strings[nif.blocks[n][1]['name']] for n in O.shape_bones(nif, hood)[0]] == ['HEAD']


def _arm_raised_stretch(nif, fit) -> float:
    """The most any edge of `nif`'s shapes stretches with the left arm raised 90 degrees at the shoulder."""
    _, rot, t = fit.bind[fit.bones.index('LArm_UpperArm')]
    joint, turn = -rot.T @ t, np.array([[0.0, 0, -1], [0, 1, 0], [1, 0, 0]])
    most = 0.0
    for kind, raw in nif.blocks:
        if kind != 'BSSubIndexTriShape':
            continue
        shape = K.read_tri_shape(K.Reader(raw))
        names = [nif.strings[nif.blocks[n][1]['name']] for n in O.shape_bones(nif, shape)[0]]
        arm = {i for i, n in enumerate(names) if n.startswith('LArm_') and 'Collarbone' not in n}
        rest = np.array([v['position'] for v in shape['vertices']])
        share = np.array([sum(w for w, b in zip(v['weights'], v['bones']) if b in arm) for v in shape['vertices']])
        posed = rest + share[:, None] * ((rest - joint) @ turn.T + joint - rest)
        edges = np.vstack([np.array(shape['triangles'])[:, pair] for pair in ((0, 1), (1, 2), (2, 0))])
        before = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
        after = np.linalg.norm(posed[edges[:, 0]] - posed[edges[:, 1]], axis=1)
        most = max(most, float((after / np.maximum(before, 1e-4))[before > 1e-4].max()))
    return most


@pytest.mark.skipif(not (SUPER_MUTANT / 'nightkinbare.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the FalloutNV.esm export and Fallout 4')
def test_fnvs_nightkin_keeps_its_own_weights_so_a_raised_arm_does_not_tear_its_armor():
    """A raised arm stretches nightkin no more than FO4's own body (4x)."""
    fit, _, nif = _creature_shapes(SUPER_MUTANT, ('nightkinbare.nif', 'nv_night_base.nif'))
    assert _arm_raised_stretch(nif, fit) < 4.0


def _inside_share(points: np.ndarray, fit) -> float:
    """The share of `points` more than 0.05 units inside FO4's body (fit.points, fit.tris, wound outward)."""
    corners = fit.points[fit.tris]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    samples, owner, _ = fit.samples
    _, i = cKDTree(samples).query(points)
    n = normal[owner[i]] / np.linalg.norm(normal[owner[i]], axis=1, keepdims=True)
    return float(np.mean(np.einsum('ij,ij->i', points - samples[i], n) < -0.05))


@pytest.mark.skipif(not (SUPER_MUTANT / 'nightkinbare.nif').exists() or not (FALLOUT4_DIR / 'Data').exists(),
                    reason='needs the FalloutNV.esm export and Fallout 4')
def test_nightkin_over_fo4s_body_and_head_keep_only_fnvs_armor():
    """Over FO4's body and head: FNV's bare skin (SM3D1024_D) part drops whole (no NEW_UV_lo head, teeth or bands),
    no shape binds a finger, and no armor shape has over 2% of its vertices inside FO4's body."""
    parts = ('nightkinbare.nif', 'nv_night_base.nif')
    skin = CR.skin_texture([SUPER_MUTANT / n for n in parts])
    assert skin.endswith('sm3d1024_d.dds')
    fit, shapes, nif = _creature_shapes(SUPER_MUTANT, parts, skin)
    names = []
    for kind, raw in nif.blocks:
        if kind == 'BSSubIndexTriShape':
            shape = K.read_tri_shape(K.Reader(raw))
            name = nif.strings[shape['name']]
            names.append(name)
            bones = [nif.strings[nif.blocks[n][1]['name']] for n in O.shape_bones(nif, shape)[0]]
            assert not any('Finger' in b for b in bones), name
            assert _inside_share(shapes[name], fit) <= 0.02, name
    assert names and not any(n.startswith('NEW_UV_lo') for n in names)


def test_a_fire_addon_maps_to_fo4s_by_name_and_damage_stages_keep_theirs():
    """Barrel02fireLight's AddOnNode14 (FNV MPSFireSmall01) becomes FO4's index 4. car03's six fires stay under
    FO4 damage stages (hidden, FNV's ranges) beside its blast nodes, as vanilla Coupe01_Postwar; all survive a
    write and read."""
    export = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
    if not export.exists():
        pytest.skip('no FNV export')
    addons = addon_map(str(export))
    barrel, car = (F.read(F.write(C.convert(str(export / 'meshes' / m), str(export), addons=addons).nif))
                   for m in ('clutter/barrel02firelight.nif', 'vehicles/car03.nif'))
    assert [b['value'] for k, b in barrel.blocks if k == 'BSValueNode'] == [4]
    ranges = {car.strings[b['name']]: (k, b['range'], b['flags'],
                                       sorted(car.blocks[c][1]['value'] for c in b['children']))
              for k, b in car.blocks if k in C.RANGE_NODES}
    assert ranges == {
        'DamageStage3': ('BSDamageStage', (3, 3, 0), C.RANGE_FLAGS, [5]),
        'DamageStage2-3': ('BSDamageStage', (2, 3, 0), C.RANGE_FLAGS, [5, 5, 5]),
        'DamageStage1-3': ('BSDamageStage', (1, 3, 0), C.RANGE_FLAGS, [4, 4]),
        'BlastNode2': ('BSBlastNode', (2, 2, 0), C.RANGE_FLAGS, []),
        'BlastNode4': ('BSBlastNode', (4, 4, 0), C.RANGE_FLAGS, [])}
    assert all(i in car.blocks[0][1]['children'] for i, (k, _) in enumerate(car.blocks) if k in C.RANGE_NODES)


def test_shapes_under_a_damage_stage_go_under_it():
    """VertibirdHulk's debris shapes (VBDebris-28, -30) sit under its third DamageStage3, not the root."""
    export = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
    if not export.exists():
        pytest.skip('no FNV export')
    nif = C.convert(str(export / 'meshes' / 'vehicles' / 'vertibirdhulk.nif'), str(export)).nif
    parent = {c: k for k, b in nif.blocks if isinstance(b, dict) for c in b.get('children', [])}
    debris = [i for i, (k, b) in enumerate(nif.blocks) if k == 'BSTriShape'
              and nif.strings[b['name']].startswith(('VBDebris-28', 'VBDebris-30'))]
    assert debris and {parent[i] for i in debris} == {'BSDamageStage'}


def test_an_alpha_tested_glow_shape_keeps_its_cut_and_glows_through_an_additive_decal_overlay():
    """The OPEN 24 HOURS sign drew its hidden panel with a glow BGSM; the cut stays on a glow-free BGSM and the
    glow is a neon-like BGEM (additive, decal) on the baked glow map."""
    alpha = type('A', (), {'flags': 0x12EC, 'threshold': 64})()
    mat = C.lit_material(['a.dds', 'a_n.dds', 'a_e.dds'], {}, alpha, False, False, None)
    glow = mat.overlay
    assert mat.data['alpha_test'] and not mat.data['glowmap'] and mat.alpha == (0x12EC, 64)
    assert glow.kind == 'effect' and glow.alpha == C.NEON_ALPHA and glow.glow[0] == 'fnv\\a_a_e_cut64.dds'
    assert (glow.data['src_blend'], glow.data['dst_blend'], glow.data['decal']) == (6, 0, True)
    assert glow.shader[1][0] & C.DECAL_FLAGS == C.DECAL_FLAGS


def test_a_lit_shape_without_a_diffuse_fnv_has_draws_white_under_its_vertex_colours(tmp_path):
    """mountedbrahminhead01's plaque names grey.bmp, absent from FNV: vanilla's white, the untextured name, its
    normal map still in slot 1; a texture swap names the material from the new diffuse."""
    normal = tmp_path / 'textures' / 'a_n.dds'
    normal.parent.mkdir(parents=True)
    normal.write_bytes(b'')
    mat = C.lit_material(['grey.bmp', 'textures\\a_n.dds'], {}, None, False, False, tmp_path)
    assert mat.data['textures']['diffuse'] == C.WHITE_DIFFUSE and mat.path.startswith('materials\\fnv\\untextured')
    assert mat.textures == ['', 'textures\\a_n.dds']
    swapped = dict(mat.data, textures=dict(mat.data['textures'], diffuse='fnv/b.dds'))
    assert C.retextured(mat.path, mat.data, swapped).startswith('materials\\fnv\\b')


def test_a_glow_map_lights_the_material_with_fnvs_emissive_colour():
    """MojaveExpressSign's glow map: glowmap and emittance on, FNV's emissive colour (clamped), a path per colour;
    the glow slot names the map baked from the diffuse."""
    material = type('M', (), {'emissive_color': type('C', (), {'r': 1.0, 'g': 0.35, 'b': -0.2})(), 'emit_multi': 1.0})()
    flags = type('F', (), {'sf_external_emittance': 0})()
    props = {'NiMaterialProperty': material, 'BSShaderPPLightingProperty': type('S', (), {'shader_flags': flags})()}
    mat = dict(C.MATERIAL, textures=dict.fromkeys(C.BGSM_TEXTURES, ''))
    suffix = C._glow(mat, ['a.dds', 'a_n.dds', 'textures\\a_g.dds'], props)
    assert mat['glowmap'] and mat['emittance'] and mat['emittance_color'] == (1.0, 0.35, 0.0)
    assert suffix == '_glowff5900' and mat['textures']['glow'] == 'fnv/a_a_g.dds'
    assert C._glow(dict(mat), ['a.dds', 'a_n.dds'], props) == ''


def test_an_unlit_shape_with_normals_keeps_fnvs_view_falloff():
    """IndFXLightRays01's beam fades by view angle (Use_Falloff, FNV's four values); without normals, no falloff."""
    shader = type('S', (), {'file_name': b'textures\\effects\\FXSoftGlowBeamMulti.dds',
                            'shader_flags': type('F', (), {'sf_vertex_alpha': 1, 'sf_external_emittance': 1})(),
                            'falloff_start_angle': 0.98, 'falloff_stop_angle': 0.17, 'falloff_start_opacity': 1.0,
                            'falloff_stop_opacity': 0.0})()
    nif = F.NifFile()
    lit = C._unlit_shader(nif, C._unlit(shader, None, True, True, True), True)
    assert lit['flags1'] & C.USE_FALLOFF and lit['falloff'] == (0.98, 0.17, 1.0, 0.0)
    assert lit['flags1'] & C.EXTERNAL_EMITTANCE
    flat = C._unlit_shader(nif, C._unlit(shader, None, True, True, False), True)
    assert not flat['flags1'] & C.USE_FALLOFF and flat['falloff'] == (1.0, 1.0, 1.0, 1.0)


def test_a_blended_black_fill_draws_as_vanillas_opaque_black_flat_and_mist_stays_an_effect():
    """bldgcorner04_nv's black box (unlit, blended, alpha 1, dark) is lit on vanilla's black flat.bgsm with no alpha
    property and no BGSM of ours; fxmistlow01's mist (0.5 grey) stays an effect shader."""
    export = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
    if not export.exists():
        pytest.skip('no FNV export')
    shapes = {}
    for mesh in ('architecture/suburban/bldgcorner04_nv.nif', 'effects/ambient/fxmistlow01.nif'):
        done = C.convert(str(export / 'meshes' / mesh), str(export))
        assert C.BLACK_FLAT not in done.materials
        nif = done.nif
        shapes |= {nif.strings[b['name']]: (b, nif.blocks[b['shader']]) for k, b in nif.blocks if k == 'BSTriShape'}
    box, (kind, shader) = shapes['BldgCorner04_NV:5']
    assert kind == 'BSLightingShaderProperty' and box['alpha_property'] == -1
    assert (shader['flags1'], shader['flags2']) == C.BLACK_FLAGS
    assert shapes['FXMistLow01:3'][1][0] == 'BSEffectShaderProperty'



def test_a_hat_covers_the_hair_top_unless_it_is_a_mask():
    """A cap (headband, hat) also takes 30; the hockey mask (hat and mask) does not."""
    assert H.slots(0x600) == (30, 46) and H.slots(0x4E00) == (46, 47, 48, 49)


def test_refraction_surface_is_a_materialless_refraction_shader():
    """An FNV refraction shape draws as vanilla's gas leak: no material, Refraction at FNV's strength, no z-write."""
    textures = ['effects\\fxgas.dds', 'effects\\fxgas_n.dds']
    mat = C.ShapeMaterial('refract', '', {'strength': 0.03}, textures, None, None)
    (kind, shader), (_, texture_set) = C._refract_blocks(F.NifFile(), mat, 0, False)
    assert kind == 'BSLightingShaderProperty' and shader['name'] == -1 and shader['texture_set'] == 1
    assert (shader['flags1'], shader['flags2'], shader['refraction']) == (*C.REFRACT_FLAGS, 0.03)
    assert texture_set['textures'][:2] == [f'textures\\{C.fo4_texture(t)}' for t in textures]


def test_attaching_moves_the_roots_children_and_a_named_root_moves_alone():
    """ATTACH (a body part's Prn bone) moves the root's children; a translation-only pose naming the root (a
    weapon's hold) moves just the root."""
    root, child = C.NifFormat.NiNode(), C.NifFormat.NiNode()
    root.name, child.name = b'HeartRoot', b'Heart'
    child.translation.x = 1.0
    root.add_child(child)
    C.posed(root, {C.ATTACH: ((0.0, 0.0, 5.0), [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])})
    assert (child.translation.x, child.translation.z, root.translation.z) == (1.0, 5.0, 0.0)
    C.posed(root, {'HeartRoot': ((0.0, 0.0, 2.0), None)})
    assert (child.translation.z, root.translation.z) == (5.0, 2.0)


HOUSE_SCREEN = Path('export/FalloutNV.esm/meshes/creatures/nvpenthouemaincomputer/nvdefaultscreen.nif')


@pytest.mark.skipif(not HOUSE_SCREEN.exists(), reason='needs the FalloutNV.esm export')
def test_free_running_screen_layers_keep_their_controllers_and_fade_by_blending():
    """Mr. House's screen has no controller manager: each layer's alpha controller runs on its own with FNV's
    flags and keys, and the layers blend so their alpha hides the Lost and Yes Man faces behind House's."""
    nif = F.read(F.write(C.convert(str(HOUSE_SCREEN), 'export/FalloutNV.esm').nif))
    shapes = {nif.strings[b['name']]: b for k, b in nif.blocks if k == 'BSTriShape'}
    alpha = {}
    for kind, block in nif.blocks:
        if kind == 'BSEffectShaderPropertyFloatController' and block['variable'] == 5:
            owner = next(n for n, s in shapes.items() if s['shader'] == block['target'])
            keys = nif.blocks[nif.blocks[block['interpolator']][1]['data']][1]['keys']['keys']
            alpha[owner] = (block['flags'], round(keys[-1][1]))
    assert alpha == {'##ConnectionLost:0': (76, 1), '##HouseScree:0': (76, 0), '##YesMan:0': (76, 0)}
    for name in alpha:
        assert nif.blocks[shapes[name]['alpha_property']][1]['alpha_flags'] == C.VERTEX_ALPHA_BLEND[0]
    assert [b['value'] & 1 for k, b in nif.blocks if k == 'BSXFlags'] == [1]


def test_texel_peaks_wraps_a_uv_a_hair_below_zero(tmp_path):
    """A UV of -1e-17 is 1.0 after Python's `% 1`: the texel lookup wraps it to the first texel, not one past the
    image (Old World Blues crashed on it)."""
    from PIL import Image
    Image.new('RGB', (4, 4), (51, 102, 255)).save(tmp_path / 'glow.dds', format='PNG')
    shape, data = C.NifFormat.NiTriShape(), C.NifFormat.NiTriShapeData()
    data.num_vertices, data.num_uv_sets, data.has_vertex_colors = 1, 1, False
    data.uv_sets.update_size()
    data.uv_sets[0][0].u, data.uv_sets[0][0].v = -1e-17, -1e-17
    shader = C.NifFormat.BSShaderNoLightingProperty()
    shader.file_name = b'glow.dds'
    shape.data, shape.name = data, b'Glow'
    shape.add_property(shader)
    root = C.NifFormat.NiNode()
    root.add_child(shape)
    (tmp_path / 'textures').mkdir()
    (tmp_path / 'glow.dds').rename(tmp_path / 'textures' / 'glow.dds')
    assert C.texel_peaks(root, tmp_path) == {'Glow': pytest.approx(1.0)}
