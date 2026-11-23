"""A converted face's skin: the body copy's own face texture set is dropped, and the race's head skin reaches the
colour fit.

See: docs/fork/fo4_facegen_plan.md#body-skin
See: docs/fork/fo4_facegen_plan.md#race-skin
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import texture as TX
from fo4_import.face import race_body, skin_seams, skin_tint, tint
from fo4_import.face.fnv_head import FnvHead
from fo4_import.face.sculpt import FACE_FIELDS
from fo4_import.face.texture import fnv_texture
from fo4_import.spike import fnv_npc
from fo4_import.spike import npcs as N
from fo4_import.spike import race_skins
from fo4_import.spike import records as R
from fo4_import.spike import replacements
from fo4_import.spike.face_fit import tint_fit
from tes5_import.base.tes5_reader import subrecords
from tests.test_fo4_faces_audit import uv_grid

#: The mod export holding a race with its own head skin and no .egt (NVWillow's WillowRace).
MOD_EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'NVWillow'


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_a_fitted_copy_of_a_human_body_has_no_face_texture_set():
    """The human bodies' copies with a fitted face keep no FTST, though a body has one (DoctorAmari's old skin)."""
    rules = replacements.load().rules.body
    found = N.bodies(FALLOUT4_ESM.read_bytes(), {k: rules[k] for k in ('human_male', 'human_female')})
    assert any(tag == b'FTST' for rec in found.values() for tag, _ in subrecords(rec.body))
    for rec in found.values():
        copy = R.clone_npc(0x800, rec.body, rec.flags, 'FNV_Test', 'Test', FACE_FIELDS)
        assert b'FTST' not in [tag for tag, _ in subrecords(copy[24:])]


def _face(tmp_path, monkeypatch, race_skin: np.ndarray, stock_skin: np.ndarray, same: bool = False) -> tuple:
    """fnv_face's pieces for an NPC on a race whose head skin is `race_skin` (no .egt), FNV's stock skin
    `stock_skin`; with `same`, the race names the stock skin itself."""
    Image.fromarray(race_skin).save(tmp_path / 'race.png')
    Image.fromarray(stock_skin).save(tmp_path / 'stock.png')
    race = {'FemalePart[0].Model': 'head.nif', 'FemalePart[0].Texture': 'stock.png' if same else 'race.png'}
    monkeypatch.setattr(fnv_npc, 'npc_head', lambda export_dir, edid: ('head', {}, race, 'FemalePart[0]'))
    monkeypatch.setattr(fnv_npc, 'STOCK_SKIN', {'FemalePart[0]': 'stock.png'})
    monkeypatch.setattr(fnv_npc, 'asset', lambda export_dir, folder, rel: tmp_path / rel)
    return fnv_npc.fnv_face(tmp_path, 'Test')[1]


def test_a_race_skin_is_its_own_piece(tmp_path, monkeypatch):
    """A race skin other than the stock one: the stock skin at the race's size, the FaceGen offset (none without
    an .egt), and the race's difference from the stock skin."""
    rng = np.random.default_rng(1)
    race, stock = rng.integers(0, 256, (8, 8, 3), np.uint8), rng.integers(0, 256, (4, 4, 3), np.uint8)
    base, offset, skin = _face(tmp_path, monkeypatch, race, stock)
    assert np.array_equal(base, np.asarray(Image.fromarray(stock).resize((8, 8), Image.BILINEAR), float))
    assert not offset.any() and np.allclose(base + skin, race)


def test_a_stock_race_keeps_its_pieces_bit_for_bit(tmp_path, monkeypatch):
    """A race on the stock skin gets fnv_texture's pieces and no race skin, so its fits do not move."""
    skin = np.random.default_rng(2).integers(0, 256, (4, 4, 3), np.uint8)
    base, offset, own = _face(tmp_path, monkeypatch, skin, skin, same=True)
    want = fnv_texture(tmp_path / 'stock.png', tmp_path / 'head.egt', np.zeros(50))
    assert np.array_equal(base, want[0]) and np.array_equal(offset, want[1]) and own is None


def test_a_race_skin_reaches_the_face_texture_but_not_the_skin_tone():
    """T1 and T2 with a race skin: the same skin tone as without it (FNV's body never takes the head texture),
    and the face texels carry the race skin."""
    rng = np.random.default_rng(3)
    fnv_points, fnv_uvs, fnv_tris = uv_grid(7, 1.1, 0.1)
    fnv, fo4 = FnvHead(fnv_points, fnv_tris, fnv_points, fnv_uvs), uv_grid(9, 1.0, 0.0)
    image = rng.integers(60, 200, (64, 64, 3), dtype=np.uint8)
    base, offset = rng.uniform(0, 200, (32, 32, 3)), rng.uniform(-20, 20, (32, 32, 3))
    race = np.full((32, 32, 3), -40.0)
    for variant in ('T1', 'T2'):
        plain, plain_tone, _ = TX.face_colours(image, fo4, fnv, (base, offset, None), variant)
        raced, raced_tone, _ = TX.face_colours(image, fo4, fnv, (base, offset, race), variant)
        assert np.array_equal(raced_tone, plain_tone) and (raced < plain).any() and (raced <= plain).all()


@pytest.mark.skipif(not (MOD_EXPORT / 'NPC_.txt').exists() or not tint.basis_path(True).exists(),
                    reason='needs the NVWillow export and the female bases')
def test_a_mod_race_skin_without_an_egt_reaches_the_tint_fit():
    """Willow (own race skin, no .egt) gets tint layers; no FaceGen colour, so no tone."""
    values, tone, captured = tint_fit(MOD_EXPORT, 'Willow', True)
    assert (np.asarray(values) > 0.005).any() and np.array_equal(tone, np.ones(3)) and captured > 0


def test_the_skin_tint_soft_light_inverts_at_every_tint():
    """untinted undoes tinted and tint_for finds the tint, at tints 0, low, 0.5, high and 1."""
    texture = np.array([[20.0, 95.0, 200.0]] * 5)
    tint = np.array([[0.0] * 3, [0.3] * 3, [0.5] * 3, [0.8] * 3, [1.0] * 3])
    drawn = skin_tint.tinted(texture, tint)
    assert np.allclose(skin_tint.untinted(drawn, tint), texture, atol=1e-6)
    assert np.allclose(skin_tint.tinted(texture[2], 0.5), texture[2])
    assert np.allclose(skin_tint.tint_for(drawn[1], texture[1]), 0.3)


def test_the_race_dirt_fades_in_from_the_neck_as_vanillas_dirty_skin_does():
    """fade_curve: 0 where vanilla's dirty body equals its clean one at the neck, rising with distance, then 1.

    See: docs/fork/fo4_look_races_plan.md#body-transfer
    """
    distance = np.tile(np.arange(20.0), (20, 1))
    clean = np.full((20, 20, 3), 120.0)
    dirty = clean - np.minimum(distance, 10.0)[..., None] * 2
    fade = race_body.fade_curve(distance, clean, dirty)[..., 0]
    assert fade[0, 0] == 0 and fade[0, -1] == 1 and (np.diff(fade[0]) >= 0).all() and 0 < fade[0, 3] < 1


def test_a_faded_out_race_dirt_draws_the_clean_body():
    """drawn_dirt: weight 0 keeps the clean texture; weight 1 draws the clean body's drawing times the dirt."""
    clean = np.random.default_rng(4).integers(40, 220, (8, 8, 4)).astype(np.uint8)
    tint, dirt = np.array([0.46, 0.47, 0.57]), np.array([0.8, 0.85, 0.9])
    assert np.abs(race_body.drawn_dirt(clean, dirt, 0.0, tint).astype(int) - clean).max() <= 1
    drawn = skin_tint.tinted(race_body.drawn_dirt(clean, dirt, 1.0, tint)[..., :3].astype(float), tint)
    assert np.allclose(drawn, skin_tint.tinted(clean[..., :3].astype(float), tint) * dirt, atol=2.5)


def test_race_dirt_skips_what_is_dark_in_both_fnv_textures():
    """dirt: stock texels darker than bare skin (underwear) take their nearest skin texel's dirt, not their noise."""
    stock = np.full((32, 32, 3), 160.0)
    stock[:, 24:] = 20.0
    race = stock * 0.7
    race[:, 24:] = 5.0
    out = race_body.dirt(race, stock, np.ones(3))
    assert np.allclose(out[:, 28], 0.7, atol=0.01) and np.allclose(out[:, :16], 0.7, atol=0.01)


def test_a_race_on_fnvs_stock_textures_has_no_look_skin():
    """race_textures: None for each part on its kind's stock texture (human or ghoul), the race's own otherwise."""
    human, ghoul = (race_skins.KINDS[k].stock for k in ('human', 'ghoul'))
    stock = {f'{p}.Texture': ['head.dds', t] for p, t in zip(race_skins.PARTS, human)}
    raider = dict(stock, **{'MalePart[0].Texture': ['head.dds', 'Characters\\Raider\\UpperBodyMale.dds']})
    marked = {f'{p}.Texture': ['head.dds', t] for p, t in zip(race_skins.PARTS, ghoul)}
    marked['MalePart[1].Texture'] = ['head.dds', 'Characters\\NVDLC04\\MarkedMen\\HandMale.dds']
    assert race_skins.race_textures(stock, human) == (None,) * 4
    assert race_skins.race_textures(raider, human) == ('characters\\raider\\upperbodymale.dds', None, None, None)
    assert race_skins.race_textures(marked, ghoul) == (None, 'characters\\nvdlc04\\markedmen\\handmale.dds', None, None)


def _old_texel_points(points: np.ndarray, uv: np.ndarray, tris: np.ndarray, size: int) -> tuple:
    """texel_points as it was: each triangle's texels and their points worked out in turn, every call."""
    rows, cols, where = [], [], []
    for tri in tris:
        corners = uv[tri] * size - 0.5
        lo, hi = np.floor(corners.min(0)).astype(int), np.ceil(corners.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0], size - 1) + 1),
                             np.arange(max(lo[1], 0), min(hi[1], size - 1) + 1))
        p = np.stack([xs.ravel(), ys.ravel()], 1).astype(float)
        m = np.array([corners[1] - corners[0], corners[2] - corners[0]]).T
        if abs(np.linalg.det(m)) < 1e-12 or not len(p):
            continue
        b = np.linalg.solve(m, (p - corners[0]).T).T
        bary = np.column_stack([1 - b.sum(1), b])
        inside = (bary >= -1e-6).all(1)
        rows.append(ys.ravel()[inside])
        cols.append(xs.ravel()[inside])
        where.append(bary[inside] @ points[tri])
    return np.concatenate(rows), np.concatenate(cols), np.vstack(where)


def test_texel_points_from_the_kept_cover_match_the_per_triangle_points():
    """Two faces on one UV layout: each one's texels and points are bit for bit the per-triangle loop's.

    See: docs/fork/fo4_facegen_plan.md#skin-speed
    """
    points, uv, tris = uv_grid(9, 1.0, 0.0)
    for scale in (1.0, 1.3):
        new, old = TX.texel_points(points * scale, uv, tris, 64), _old_texel_points(points * scale, uv, tris, 64)
        assert all(a.tobytes() == b.tobytes() for a, b in zip(new, old))


def test_the_neck_fade_matches_the_unbounded_search():
    """neck_weight (box-filtered, bounded search) gives the plain unbounded weights.

    See: docs/fork/fo4_facegen_plan.md#skin-speed
    """
    rng = np.random.default_rng(3)
    seam = skin_seams.cKDTree(rng.uniform(0, 4, (50, 3)))
    points = rng.uniform(-30, 30, (4000, 3))
    plain = np.clip(1.0 - seam.query(points)[0] / skin_seams.NECK_BLEND, 0.0, 1.0)[:, None]
    weight = skin_seams.neck_weight(points, seam)
    assert weight.tobytes() == plain.tobytes() and 0 < np.count_nonzero(weight) < len(points)
