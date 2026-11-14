"""A mod's own hair, eyes and face skin as FO4 head parts and a face texture set.

See: docs/fork/fo4_facegen_plan.md#own-heads
"""

import collections
import struct
from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.face import eyes as EY
from fo4_import.face import hair
from fo4_import.face import texture as TX
from fo4_import.face.fnv_head import FnvHead
from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F
from fo4_import.nif import hair_mesh as HM
from fo4_import.nif import headgear as H
from fo4_import.spike import own_heads as OH
from fo4_import.spike.head_parts import HeadChoice, head_parts_edit
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord
from tests.test_fo4_faces_audit import uv_grid
from tests.test_fo4_items_audit import hat_quad

NO_PARENT = 0xFFFFFFFF


def test_two_part_segments_are_a_vanilla_hairs_trailer():
    """FemaleHair15's trailer: 3,820 top triangles (30), then 2,230 (31)."""
    want = struct.pack('<35I', 6050, 2, 4, 0, 0, NO_PARENT, 0, 0, 6050, NO_PARENT, 2, 0, 3820, 1, 0, 11460, 2230, 1,
                       0, 2, 4, 0, 1, 0, NO_PARENT, 0, 1, NO_PARENT, 0, 30, H.HEAD_BONE_ID, 0, 31, H.HEAD_BONE_ID, 0)
    assert H.segments([(30, 3820), (31, 2230)]) == want + struct.pack('<H', 0)


def _fit() -> H.HeadFit:
    """A head fit that moves nothing."""
    return H.HeadFit(1.0, np.eye(3), np.zeros(3), (0.0, 0.0, 0.0), C.IDENTITY, np.zeros((8, 3)), np.zeros((8, 3)),
                     np.zeros((1, 3)), np.zeros((1, 3)))


def test_a_hair_mesh_puts_its_top_first_in_slot_30_with_vanillas_alpha_and_its_material():
    """Of a two-triangle mesh, the field votes the second triangle into the top: it comes first, the trailer
    names 30 then 31, the shape takes HAIR_ALPHA and the hair material."""
    worn = H.worn(hat_quad(0.0), _fit(), (31,))
    shape, _ = HM.sub_segments(next(raw for kind, raw in F.read(worn).blocks if kind == 'BSSubIndexTriShape'))
    points, _, _, tris = H.shape_arrays(shape)
    centres = points[tris].mean(1)
    field = (cKDTree(np.repeat(centres, HM.FIELD_NEIGHBOURS, 0)), np.repeat([False, True], HM.FIELD_NEIGHBOURS))
    nif = F.read(HM.as_hair(worn, field, 'materials\\fnv\\own\\hair.bgsm'))
    out, subs = HM.sub_segments(next(raw for kind, raw in nif.blocks if kind == 'BSSubIndexTriShape'))
    assert subs == [(0, 1, 30), (1, 1, 31)] and out['triangles'] == [tuple(tris[1]), tuple(tris[0])]
    alpha = nif.blocks[out['alpha_property']]
    assert alpha[0] == 'NiAlphaProperty' and (alpha[1]['alpha_flags'], alpha[1]['threshold']) == HM.HAIR_ALPHA
    assert nif.strings[nif.blocks[out['shader']][1]['name']] == 'materials\\fnv\\own\\hair.bgsm'


def _hair_pair() -> bytes:
    """hat_quad's NIF as an FNV hair: the quad as NoHat, and as Hat 0.5 lower."""
    nif = F.read(hat_quad(0.0))
    no_hat = nif.blocks[1][1]
    no_hat['name'] = nif.string('NoHat')
    lowered = [dict(v, position=(v['position'][0], v['position'][1], v['position'][2] - 0.5)) for v in no_hat['vertices']]
    nif.blocks.append(('BSLightingShaderProperty', dict(nif.blocks[2][1])))
    nif.blocks.append(('BSTriShape', dict(no_hat, name=nif.string('Hat'), shader=len(nif.blocks) - 1, vertices=lowered)))
    nif.blocks[0][1]['children'].append(len(nif.blocks) - 1)
    return F.write(nif)


def test_an_fnv_hair_with_a_hat_shape_hides_its_nohat_under_hats_and_shows_its_hat_shape():
    """NoHat and Hat become one shape, NoHat's triangles slot 30 and Hat's 31, whatever the vote; Hat leaves the
    scene, and the bounds hold both."""
    worn = H.worn(_hair_pair(), _fit(), (31,))
    field = (cKDTree(np.zeros((HM.FIELD_NEIGHBOURS, 3))), np.ones(HM.FIELD_NEIGHBOURS, bool))
    nif = F.read(HM.as_hair(worn, field, 'materials\\fnv\\own\\hair.bgsm'))
    reached = [i for i in nif.blocks[0][1]['children'] if nif.blocks[i][0] == 'BSSubIndexTriShape']
    assert len(reached) == 1
    out, subs = HM.sub_segments(nif.blocks[reached[0]][1])
    assert subs == [(0, 2, 30), (2, 2, 31)] and out['triangles'][2:] == [(4, 5, 6), (4, 6, 7)]
    points = H.shape_arrays(out)[0]
    assert np.allclose(points[4:, 2], points[:4, 2] - 0.5, atol=0.01)
    centre, radius = np.array(out['bound'][:3]), out['bound'][3]
    assert (np.linalg.norm(points - centre, axis=1) <= radius + 1e-3).all()


def test_the_enclosing_sphere_holds_both_or_keeps_the_bigger():
    """Two unit spheres 4 apart: radius 3 midway; a sphere inside another: the outer."""
    assert np.allclose(HM.enclosing((0, 0, 0, 1), (4, 0, 0, 1)), (2, 0, 0, 3))
    assert HM.enclosing((0, 0, 0, 5), (1, 0, 0, 1)) == (0, 0, 0, 5)


def test_a_sphere_centre_is_found_from_its_surface():
    """Points on a sphere of radius 2 about (1, 2, 3) give that centre."""
    d = np.random.default_rng(4).normal(size=(50, 3))
    points = (1.0, 2.0, 3.0) + 2.0 * d / np.linalg.norm(d, axis=1, keepdims=True)
    assert np.allclose(EY.sphere_centre(points), (1.0, 2.0, 3.0))


def _eyeball(centre: tuple, u: tuple) -> tuple:
    """(points, UVs, triangles) of a unit sphere band about `centre`, longitude across UV `u` (start, end)."""
    lat, lon = np.meshgrid(np.linspace(0.3, 0.7, 9) * np.pi, np.linspace(0.0, 2 * np.pi, 33), indexing='ij')
    points = np.column_stack([(np.sin(lat) * np.cos(lon)).ravel(), (np.sin(lat) * np.sin(lon)).ravel(),
                              np.cos(lat).ravel()]) + centre
    uv = np.column_stack([u[0] + (u[1] - u[0]) * lon.ravel() / (2 * np.pi), lat.ravel() / np.pi])
    rows, cols = lat.shape
    quads = [(r * cols + c, r * cols + c + 1, (r + 1) * cols + c + 1, (r + 1) * cols + c)
             for r in range(rows - 1) for c in range(cols - 1)]
    return points, uv, np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])


def test_an_fnv_eye_texture_goes_onto_both_fo4_eyes_by_direction_mirrored_for_the_other_side():
    """FNV's eye (at +x) is red facing -x, green facing +x. FO4's eye on the same side takes red where it faces
    -x; the other eye, mirrored, takes green there; texels far outside FO4's islands keep FO4's blue."""
    fnv_points, fnv_uv, fnv_tris = _eyeball((3.0, 0.0, 0.0), (0.0, 1.0))
    fnv = np.zeros((64, 64, 4), np.uint8)
    fnv[..., 1], fnv[:, 16:48, 0], fnv[:, 16:48, 1] = 255, 255, 0
    right, left = _eyeball((3.0, 0.0, 0.0), (0.0, 0.5)), _eyeball((-3.0, 0.0, 0.0), (0.5, 1.0))
    fo4 = (np.vstack([right[0], left[0]]), np.vstack([right[1], left[1]]),
           np.vstack([right[2], left[2] + len(right[0])]))
    blue = np.zeros((64, 64, 4), np.uint8)
    blue[..., 2:] = 255
    out = EY.eye_texture(blue, fo4, (fnv_points, fnv_tris, fnv_uv), fnv)
    facing_in = out[28:36, 14:18, :3].reshape(-1, 3), out[28:36, 46:50, :3].reshape(-1, 3)
    assert (facing_in[0] == (255, 0, 0)).all() and (facing_in[1] == (0, 255, 0)).all()
    assert tuple(out[0, 0]) == (0, 0, 255, 255)


def _assets(parts: dict) -> hair.Fo4Assets:
    """Fo4Assets over head parts {FormID: (PNAM type, [extras])}."""
    assets = hair.Fo4Assets.__new__(hair.Fo4Assets)
    assets.parts = {p: {b'PNAM': [struct.pack('<I', kind)], b'HNAM': [struct.pack('<I', e) for e in extras]}
                    for p, (kind, extras) in parts.items()}
    return assets


def test_own_parts_take_a_chosen_parts_place_without_its_extras():
    """The chosen hair swapped for an own part drops the vanilla hair's hairline; the eyes keep theirs; the
    stand-in's hair and its extra go, its face stays."""
    assets = _assets({0x100: (3, [0x101]), 0x101: (3, []), 0x200: (2, [0x201]), 0x201: (2, []),
                      0x300: (3, [0x301]), 0x301: (3, []), 0x400: (1, [])})
    subs = b''.join(pack_subrecord('PNAM', struct.pack('<I', p)) for p in (0x300, 0x301, 0x400))
    edit = head_parts_edit(HeadChoice(hair=0x100, eyes=0x200), assets, {0x100: [0x900]})
    pnams = [struct.unpack('<I', d)[0] for t, d in subrecords(edit(subs)) if t == b'PNAM']
    assert pnams == [0x200, 0x201, 0x900, 0x400]


def test_only_records_a_plugin_with_masters_makes_are_its_own(monkeypatch):
    """A mod's new HAIR (its own load slot) is its own, its override of a master's is not; nothing is in a
    masterless game plugin."""
    held = [{'FormID': '01000ABC'}, {'FormID': '00000DEF'}]
    monkeypatch.setattr(OH, 'own_records', lambda export_dir, sig: held if sig == 'HAIR' else [])
    for masters, owned in (((), False), (('FalloutNV.esm',), True)):
        monkeypatch.setattr(OH, 'export_masters', lambda export_dir, m=masters: m)
        heads = OH.OwnHeads(None, 'export')
        assert heads.owns('HAIR', '01000ABC') is owned and not heads.owns('HAIR', '00000DEF')
        assert not heads.owns('EYES', '01000ABC')


def test_an_own_race_face_keeps_only_its_brows_and_takes_the_face_textures_tone(monkeypatch):
    """Own hair, eyes and race: the hair and eyes are swapped (eyes with their extras), FTST names the face set,
    and the tint fit keeps its brow at its value, every other option at 0, the face texture's tone."""
    monkeypatch.setattr(OH.tint, 'load_basis', lambda female: (None, [5, 7, 9], None, [7]))
    monkeypatch.setattr(OH.fnv_npc, 'worn_parts', lambda export_dir, form_id: [])
    heads = OH.OwnHeads(None, 'export')
    heads.own = {'HAIR': {'H'}, 'EYES': {'E'}, 'RACE': {'R'}}
    heads._hair = lambda npc, female, assets: 0x900
    heads._eyes = lambda npc, female, vanilla, assets: 0x901
    heads._face = lambda npc, female, assets: (0x902, np.full(3, 1.2))
    assets = _assets({0x100: (3, [0x101]), 0x200: (2, [0x201])})
    npc = {'HNAM.Hair': 'H', 'ENAM.Eyes': 'E', 'RNAM.Race': 'R', 'FormID': '01000001'}
    swaps, worn, face, tinted = heads.of(npc, True, HeadChoice(hair=0x100, eyes=0x200), ([0.3, 0.6, 0.2], 1.0, 0.5),
                                   assets)
    assert swaps == {0x100: [0x900], 0x200: [0x901, 0x201]} and worn == []
    assert dict(subrecords(face(pack_subrecord('QNAM', bytes(16)))))[b'FTST'] == struct.pack('<I', 0x902)
    assert np.array_equal(tinted[0], [0.0, 0.6, 0.0]) and np.array_equal(tinted[1], np.full(3, 1.2))


def test_an_own_race_on_fnvs_stock_skin_keeps_the_slider_face(monkeypatch):
    """A mod's race wearing FNV's stock head skin: no face set, the tint fit as it was."""
    monkeypatch.setattr(OH.fnv_npc, 'fnv_face', lambda export_dir, edid: ('head', ('stock', 'offset', None)))
    monkeypatch.setattr(OH.fnv_npc, 'worn_parts', lambda export_dir, form_id: [])
    heads = OH.OwnHeads(None, 'export')
    heads.own = {'HAIR': set(), 'EYES': set(), 'RACE': {'R'}}
    fit = ([0.3, 0.6, 0.2], 1.0, 0.5)
    npc = {'RNAM.Race': 'R', 'FormID': '01000001', 'EditorID': 'Test'}
    assert heads.of(npc, True, HeadChoice(), fit, _assets({})) == ({}, [], None, fit)


#: FNV's eyepatch head part as worn_parts gives it.
EYEPATCH = (0x73D56, 'Eyepatch', 'Characters\\Hair\\Eyepatch.NIF')


def _worn_heads(tmp_path, on_head: bool = True) -> tuple:
    """(OwnHeads over a fake builder in `tmp_path`, {(site, key): FormID} derived, [(sig, record)] added, [head_worn
    slots asked]); head_worn gives b'NIF' when `on_head`, else None."""
    derived, added, asked = {}, [], []
    writer = SimpleNamespace(derive_formid=lambda site, key: derived.setdefault((site, key), 0x800 + len(derived)),
                             add_record=lambda sig, raw: added.append((sig, raw)))
    equipment = SimpleNamespace(head_worn=lambda model, sex, slots: asked.append((model, sex, slots)) or (
        ('fnv\\characters\\hair\\eyepatch.nif', b'NIF') if on_head else None))
    builder = SimpleNamespace(writer=writer, equipment=equipment, data_dir=tmp_path, counts=collections.Counter())
    heads = OH.OwnHeads(builder, 'export')
    heads.own = {'HAIR': set(), 'EYES': set(), 'RACE': set()}
    heads._hair_tri = lambda mesh, female, assets: mesh[0][:-4] + 'Chargen.tri'
    return heads, derived, added, asked


def test_a_part_not_drawn_as_hair_is_worn_as_a_new_misc_head_part_per_sex(monkeypatch, tmp_path):
    """Two men and a woman with FNV's eyepatch: one Misc HDPT per sex, keyed by the FNV HDPT FormID and sex, on
    its mesh worn in FaceGen Head (32) and written once, with its chargen .tri; each NPC lists its sex's."""
    monkeypatch.setattr(OH.fnv_npc, 'worn_parts', lambda export_dir, form_id: [EYEPATCH])
    heads, derived, added, asked = _worn_heads(tmp_path)
    worn = [heads.of({'FormID': f'0000000{i}'}, female, HeadChoice(), None, None)[1]
            for i, female in ((1, False), (2, False), (3, True))]
    assert list(derived) == [(OH.SITE, 'PART 00073D56 male'), (OH.SITE, 'PART 00073D56 female')]
    assert worn == [[0x800], [0x800], [0x801]] and [a[1:] for a in asked] == [('male', (32,)), ('female', (32,))]
    subs = dict(subrecords(added[0][1][24:]))
    assert [sig for sig, _ in added] == ['HDPT', 'HDPT'] and subs[b'EDID'] == b'FNV_Eyepatch_male\0'
    assert subs[b'PNAM'] == struct.pack('<I', OH.MISC) and subs[b'DATA'] == bytes([hair.MALE])
    assert subs[b'MODL'] == b'fnv\\own\\Eyepatch_male.nif\0' and subs[b'NAM1'] == b'fnv\\own\\Eyepatch_maleChargen.tri\0'
    assert (tmp_path / 'Meshes' / 'fnv' / 'own' / 'Eyepatch_female.nif').read_bytes() == b'NIF'


def test_a_worn_part_off_the_head_adds_nothing(monkeypatch, tmp_path):
    """A part whose mesh is not drawn on the head: no record, asked once."""
    monkeypatch.setattr(OH.fnv_npc, 'worn_parts', lambda export_dir, form_id: [EYEPATCH])
    heads, derived, added, asked = _worn_heads(tmp_path, on_head=False)
    for i in range(2):
        assert heads.of({'FormID': f'0000000{i}'}, False, HeadChoice(), None, None)[1] == []
    assert not derived and not added and len(asked) == 1


def test_worn_parts_follow_the_chosen_parts():
    """The worn parts join the chosen ones; the stand-in's own Misc part stays."""
    assets = _assets({0x100: (3, []), 0x300: (3, []), 0x500: (0, [])})
    subs = b''.join(pack_subrecord('PNAM', struct.pack('<I', p)) for p in (0x300, 0x500))
    edit = head_parts_edit(HeadChoice(hair=0x100), assets, None, [0x800])
    assert [struct.unpack('<I', d)[0] for t, d in subrecords(edit(subs)) if t == b'PNAM'] == [0x100, 0x800, 0x500]


def test_the_shown_factor_moves_only_the_tone():
    """A face set's raw diffuse drawn twice as bright: the same face texture, half the skin tone."""
    rng = np.random.default_rng(5)
    fnv_points, fnv_uvs, fnv_tris = uv_grid(7, 1.1, 0.1)
    fnv, fo4 = FnvHead(fnv_points, fnv_tris, fnv_points, fnv_uvs), uv_grid(9, 1.0, 0.0)
    image = rng.integers(30, 120, (64, 64, 4), dtype=np.uint8)
    pieces = (rng.uniform(0, 200, (32, 32, 3)), rng.uniform(-20, 20, (32, 32, 3)), None)
    plain, plain_tone = TX.face_texture(image, fo4, fnv, pieces, 'T2')
    shown, shown_tone = TX.face_texture(image, fo4, fnv, pieces, 'T2', 2.0)
    assert np.allclose(shown_tone, plain_tone / 2) and np.abs(shown.astype(int) - plain).max() <= 1
