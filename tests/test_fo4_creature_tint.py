"""FO4's body material in an FNV creature's skin color (fo4_import.spike.creature_tint)."""

import numpy as np
import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.nif.creature import PAIRS
from fo4_import.spike import creature_tint as T


def test_a_tinted_texture_takes_the_skins_color_spread_and_keeps_its_alpha():
    """Each color channel's mean and deviation become the FNV skin's; alpha is untouched."""
    rng = np.random.default_rng(1)
    rgba = rng.integers(60, 200, (16, 16, 4), dtype=np.uint8)
    skin = rng.normal((70, 75, 84), (9, 6, 5), (32, 32, 3)).clip(0, 255).astype(np.uint8)
    out = T.matched(rgba, skin)
    assert np.allclose(out[..., :3].reshape(-1, 3).mean(0), skin.reshape(-1, 3).mean(0), atol=0.6)
    assert np.allclose(out[..., :3].reshape(-1, 3).std(0), skin.reshape(-1, 3).std(0), atol=0.6)
    assert (out[..., 3] == rgba[..., 3]).all()


@pytest.mark.skipif(not (FALLOUT4_DIR / 'Data').exists(), reason='needs Fallout 4')
def test_the_super_mutant_body_tints_its_skin_material_and_not_its_gore():
    """Of FO4's super mutant body only its skin, Supermutant1, is tinted."""
    raw = Archives(FALLOUT4_DIR / 'Data').read(PAIRS['creatures\\smspinebreaker'].body)
    assert T.body_materials(raw) == ['materials\\actors\\supermutant\\supermutant1.bgsm']
