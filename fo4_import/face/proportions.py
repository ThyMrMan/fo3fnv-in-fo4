"""A face's proportions (widths, heights and depths over the race's named sculpt regions) and the slider fit to
them: sculpt values and at most one morph preset per group, bounded and ridge-penalised so nothing is maxed.

A measure is a width (right minus left mean x of a region) or the mean
difference along x, y or z of two regions; a region name ending '<' is its
lower half by z.

See: docs/fork/fo4_facegen_plan.md#proportions
"""

import struct
from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear

from fo4_import.base.strings import fallout4
from fo4_import.face.sculpt import CONTROLS
from tes5_import.base.tes5_reader import subrecords

#: Each control's limit (sculpt +/-, preset 0..), and the least and most ridge weight per control squared.
BOUND, RIDGE, RIDGE_MAX = 0.6, 0.002, 0.1
#: A preset weight under this is left out.
MIN_WEIGHT = 0.005
#: A region's vertex set: the vertices it moves by at least this share of its peak.
REGION_SHARE = 0.5
#: Vertices nearer the midline than this count on neither side of a width.
MIDLINE = 0.1
#: (name, axis 'w' for a width or x/y/z, region, other region or None); see the module doc.
MEASURES = (
    ('cheek width', 'w', 'Cheekbones', None), ('jaw width', 'w', 'Jaw - Outer', None),
    ('eye spacing', 'w', 'Eyes', None), ('nose width', 'w', 'Nose - Full', None),
    ('chin length', 'z', 'Mouth - Bottom', 'Chin<'), ('brow to chin', 'z', 'Eyebrows - Full', 'Chin<'),
    ('nose length', 'z', 'Nose - Bridge', 'Nostrils'), ('nose height', 'z', 'Nose - Tip', 'Eyes'),
    ('nose depth', 'y', 'Nose - Tip', 'Cheekbones'), ('upper lip', 'y', 'Mouth - Top', 'Mouth - Corners'),
    ('lower lip', 'y', 'Mouth - Bottom', 'Mouth - Corners'), ('lip height', 'z', 'Mouth - Top', 'Mouth - Bottom'),
)
AXES = {'x': 0, 'y': 1, 'z': 2}


def region_names(race_body: bytes, female: bool) -> dict:
    """{sculpt region index: name} of the race's regions for one sex (FMRI, FMRN's string)."""
    want, sex, index, out = (b'FNAM' if female else b'MNAM'), None, 0, {}
    for tag, data in subrecords(race_body):
        sex = tag if tag in (b'MNAM', b'FNAM') else sex
        index = struct.unpack('<I', data)[0] if tag == b'FMRI' else index
        if tag == b'FMRN' and sex == want:
            out[index] = fallout4().get(struct.unpack('<I', data)[0], b'').decode('cp1252')
    return out


def region_sets(basis: np.ndarray, regions: list, names: dict, face: np.ndarray) -> dict:
    """{name: vertex mask} of each named sculpt region on the baseline `face`, plus '<name><' lower halves."""
    reach = np.linalg.norm(basis, axis=2).reshape(len(regions), CONTROLS, -1).max(1)
    out = {}
    for region, row in zip(regions, reach):
        if row.max() > 0 and region in names:
            mask = row >= REGION_SHARE * row.max()
            out[names[region]] = mask
            out[names[region] + '<'] = mask & (face[:, 2] < np.median(face[mask, 2]))
    return out


def measure_matrix(sets: dict, face: np.ndarray, specs=MEASURES) -> np.ndarray:
    """[measure, vertex * 3]: each of `specs` (as MEASURES) as weights on the flattened face positions."""
    rows = []
    for _, axis, first, second in specs:
        row = np.zeros(face.shape)
        if axis == 'w':
            right, left = sets[first] & (face[:, 0] > MIDLINE), sets[first] & (face[:, 0] < -MIDLINE)
            row[right, 0], row[left, 0] = 1 / right.sum(), -1 / left.sum()
        else:
            row[sets[first], AXES[axis]] += 1 / sets[first].sum()
            row[sets[second], AXES[axis]] -= 1 / sets[second].sum()
        rows.append(row.ravel())
    return np.array(rows)


@dataclass
class Fit:
    """A slider fit: sculpt values [region, CONTROLS], presets [(MSDK key, morph index, weight)], measures
    predicted, and the ridge each control (sculpt controls, then morphs) ended with."""

    sculpt: np.ndarray
    presets: list
    predicted: np.ndarray
    ridge: np.ndarray


def _solve(a: np.ndarray, b: np.ndarray, lower: np.ndarray, ridge: np.ndarray) -> tuple:
    """(values, objective): least squares of `a`, `b` with per-column `ridge`, in [lower, BOUND]."""
    stacked = np.vstack([a, np.diag(np.sqrt(ridge))])
    rhs = np.concatenate([b, np.zeros(a.shape[1])])
    x = lsq_linear(stacked, rhs, bounds=(lower, BOUND)).x
    return x, float(((stacked @ x - rhs) ** 2).sum())


def unmaxed_fit(measures: np.ndarray, sculpt_basis: np.ndarray, preset_basis: tuple, target: np.ndarray) -> Fit:
    """fit() with each control's ridge (sculpt controls, then morphs) doubled from RIDGE, up to RIDGE_MAX, while
    it sits at the bound."""
    ridge = np.full(len(sculpt_basis) + len(preset_basis[0]), RIDGE)
    while True:
        out = fit(measures, sculpt_basis, preset_basis, target, ridge)
        values = np.concatenate([np.abs(out.sculpt.ravel()), np.zeros(len(preset_basis[0]))])
        values[[len(sculpt_basis) + m for _, m, _ in out.presets]] = [v for _, _, v in out.presets]
        maxed = (values >= BOUND - 1e-3) & (ridge < RIDGE_MAX)
        if not maxed.any():
            return out
        ridge = np.where(maxed, ridge * 2, ridge)


def fit(measures: np.ndarray, sculpt_basis: np.ndarray, preset_basis: tuple, target: np.ndarray,
        ridge: np.ndarray) -> Fit:
    """The slider values moving the face's `measures` (matrix) by `target`, control i (sculpt controls, then
    morphs) penalised by ridge[i]; `preset_basis` = (basis [morph, vertex, 3], [(group, MSDK key, morph index)])
    picks greedily at most one preset per group, each morph once."""
    a_s = measures @ sculpt_basis.reshape(len(sculpt_basis), -1).T
    a_p = measures @ preset_basis[0].reshape(len(preset_basis[0]), -1).T
    n, chosen = a_s.shape[1], {}

    def solve(picks: dict) -> tuple:
        """Values and objective with the sculpt controls and `picks` {group: (key, morph)}."""
        cols = [m for _, m in picks.values()]
        lower = np.concatenate([np.full(n, -BOUND), np.zeros(len(cols))])
        return _solve(np.hstack([a_s, a_p[:, cols]]), target, lower, ridge[list(range(n)) + [n + c for c in cols]])
    best = solve(chosen)[1]
    for group in dict.fromkeys(g for g, _, _ in preset_basis[1]):
        used = {m for _, m in chosen.values()}
        trials = [(solve({**chosen, group: (key, m)})[1], key, m) for g, key, m in preset_basis[1]
                  if g == group and m not in used]
        score, key, m = min(trials, default=(best, 0, 0))
        if score < best * 0.999:
            chosen[group], best = (key, m), score
    x, _ = solve(chosen)
    predicted = a_s @ x[:n] + a_p[:, [m for _, m in chosen.values()]] @ x[n:]
    return Fit(x[:n].reshape(-1, CONTROLS),
               [(k, m, float(v)) for (k, m), v in zip(chosen.values(), x[n:]) if v > MIN_WEIGHT], predicted, ridge)


def at_bound(f: Fit) -> int:
    """How many of the fit's controls sit at the bound."""
    values = np.concatenate([np.abs(f.sculpt).ravel(), [v for _, _, v in f.presets]])
    return int((values >= BOUND - 1e-3).sum())
