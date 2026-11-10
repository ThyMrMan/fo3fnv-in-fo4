"""The face fit's repeated work done once: the factored brow fits give what a full fit per brow gave, a basis and a
hair's colour candidates are worked out once per process, and a sculpt control with no effect stays 0.

See: docs/fork/fo4_build_speed.md#faces
"""

import io
import os
import struct
from types import SimpleNamespace

import numpy as np
from PIL import Image
from scipy.optimize import lsq_linear

from fo4_import.face import hair, sculpt, tint


def _full_fit_per_brow(effects: np.ndarray, target: np.ndarray, mask: np.ndarray, brow_rows: list) -> tuple:
    """tint's fit with a brow as it was before BrowFits: one full bounded fit of the free options per brow."""
    free = np.setdiff1d(np.arange(len(effects)), brow_rows)
    best = None
    for brow in [None] + list(brow_rows):
        fixed = effects[brow] if brow is not None else 0.0
        values = np.zeros(len(effects))
        values[free] = tint.fit(effects[free], target - fixed, mask)[0]
        if brow is not None:
            values[brow] = 1.0
        captured = tint.captured_share(np.tensordot(values, effects, 1), target, mask)
        if best is None or captured > best[1]:
            best = (values, captured)
    return best


def _tint_case(seed: int) -> tuple:
    """(9 options' random effects on 24 x 24 texels, a mask, the brow rows)."""
    rng = np.random.default_rng(seed)
    effects = rng.normal(0, 20, (9, 24, 24, 3)).astype(np.float32)
    return effects, rng.random((24, 24)) > 0.3, [2, 5, 7]


def test_factored_brow_fits_give_the_full_fit_per_brow():
    """For targets that want no brow, each brow, and bounds that bind: the same brow, values and share captured."""
    effects, mask, brows = _tint_case(0)
    fits = tint.BrowFits(effects, mask, brows)
    rng = np.random.default_rng(1)
    for brow in (None, *brows):
        wanted = rng.uniform(-0.5, 1.5, 9)
        wanted[brows] = 0.0
        target = np.tensordot(wanted, effects, 1) + (effects[brow] if brow is not None else 0.0)
        target += rng.normal(0, 1, target.shape)
        new, old = fits.best(target), _full_fit_per_brow(effects, target, mask, brows)
        assert [b for b in brows if new[0][b]] == [b for b in brows if old[0][b]] == ([] if brow is None else [brow])
        assert np.abs(new[0] - old[0]).max() < 1e-9 and abs(new[1] - old[1]) < 1e-12
        assert new[0].min() >= 0.0 and new[0].max() <= 1.0 and (new[0] == 0.0).any()


def test_the_first_of_two_equal_brows_wins():
    """Two brows with one effect tie; the first is chosen, as the full fits chose it."""
    effects, mask, brows = _tint_case(2)
    effects[7] = effects[5]
    target = np.tensordot(np.full(9, 0.3), effects, 1) + effects[5]
    new, old = tint.BrowFits(effects, mask, brows).best(target), _full_fit_per_brow(effects, target, mask, brows)
    assert new[0][5] == old[0][5] == 1.0 and new[0][7] == old[0][7] == 0.0


def test_a_sculpt_control_with_no_effect_stays_zero():
    """Controls whose basis rows are zero get 0, whatever the solver would leave there; the others their fit."""
    rng = np.random.default_rng(3)
    basis = rng.normal(0, 1, (2 * sculpt.CONTROLS, 30, 3))
    dead = [1, 4, 9, 13]
    basis[dead] = 0.0
    target = np.tensordot(rng.uniform(-2, 2, len(basis)), basis, 1)
    values, captured = sculpt.fit(basis, target)
    live = [i for i in range(len(basis)) if i not in dead]
    wanted = lsq_linear(basis[live].reshape(len(live), -1).T, target.ravel(), bounds=(-sculpt.BOUND, sculpt.BOUND)).x
    assert not values.ravel()[dead].any() and np.array_equal(values.ravel()[live], wanted)
    assert values.shape == (2, sculpt.CONTROLS) and 0.0 < captured <= 1.0


def test_a_basis_is_read_once_until_its_file_changes(tmp_path, monkeypatch):
    """load_basis hands back the same read-only arrays, and reads the file again once it is rewritten."""
    monkeypatch.setattr(sculpt, 'CACHE', tmp_path)
    monkeypatch.setattr(tint, 'CACHE', tmp_path)
    assert sculpt.load_basis() is None and tint.load_basis() is None
    np.savez(sculpt.basis_path(), basis=np.ones((7, 2, 3)), regions=np.array([4]), baseline=np.frombuffer(b'nif', 'u1'))
    np.savez(tint.basis_path(), effects=np.ones((2, 4, 4, 3)), options=np.array([8, 9]), brows=np.array([9]),
             baseline=np.zeros((4, 4, 4), np.uint8))
    shape, colour = sculpt.load_basis(), tint.load_basis()
    assert sculpt.load_basis()[0] is shape[0] and tint.load_basis()[0] is colour[0]
    assert shape[1:] == ([4], b'nif') and colour[1] == [8, 9] and colour[3] == [9]
    assert not shape[0].flags.writeable and not colour[0].flags.writeable and colour[0].dtype == np.float32
    np.savez(sculpt.basis_path(), basis=np.zeros((7, 2, 3)), regions=np.array([5]), baseline=np.frombuffer(b'new', 'u1'))
    os.utime(sculpt.basis_path(), ns=(1, 1))
    assert sculpt.load_basis()[1:] == ([5], b'new')


def _png(pixels: np.ndarray) -> bytes:
    """`pixels` (RGBA) as PNG bytes."""
    out = io.BytesIO()
    Image.fromarray(pixels, 'RGBA').save(out, 'PNG')
    return out.getvalue()


def test_a_hairs_colour_candidates_are_worked_out_once():
    """Each hair colour form's colour on a hair is read from its gradient row once per material; the nearest to
    the target wins, a form that is no hair colour never."""
    gradient = np.zeros((2, 4, 4), np.uint8)
    gradient[0, :, 0], gradient[1, :, 2], gradient[..., 3] = 200, 200, 255
    diffuse = np.full((2, 2, 4), 255, np.uint8)
    reads = []
    assets = hair.Fo4Assets.__new__(hair.Fo4Assets)
    assets.kept, assets.archives = {}, SimpleNamespace(read=lambda path: _png(gradient))
    assets.texture = lambda path: reads.append(path) or diffuse
    assets.colours = {1: {b'FNAM': [bytes([3])], b'CNAM': [struct.pack('<f', 0.0)]},
                      2: {b'FNAM': [bytes([3])], b'CNAM': [struct.pack('<f', 0.9)]},
                      3: {b'FNAM': [bytes([1])], b'CNAM': [struct.pack('<f', 0.9)]}}
    material = {'textures': {'diffuse': 'hair_d.dds'}, 'alpha_test_ref': 128, 'grayscale_scale': 1.0}
    red, blue = (hair.lab(np.array(rgb)).mean(0) for rgb in ((200, 0, 0), (0, 0, 200)))
    assert [hair.best_hair_colour(assets, material, target) for target in (red, blue, blue)] == [1, 2, 2]
    assert reads == ['hair_d.dds'] and [fid for _, fid in hair.hair_colours(assets, material)] == [1, 2]
