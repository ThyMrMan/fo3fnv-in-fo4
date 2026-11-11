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
from fo4_import.face import tint
from fo4_import.face.fnv_head import FnvHead
from fo4_import.face.sculpt import FACE_FIELDS
from fo4_import.face.texture import fnv_texture
from fo4_import.spike import fnv_npc
from fo4_import.spike import npcs as N
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
