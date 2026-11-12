"""An FNV face as FO4 slider values: sculpt regions and at most one morph preset per group, never maxed, fitted to
FNV's proportions (C2F: FNV's own surface below the eyes and on the jaw), and refitted to a Creation Kit export's
miss.

See: docs/fork/fo4_facegen_plan.md#proportions
"""

import functools
import struct
from dataclasses import dataclass

import numpy as np

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import facegeom, presets, proportions, sculpt, tint
from fo4_import.face.bake import face_moves, face_shape
from fo4_import.nif import file as nif_file
from tes5_import.base.tes5_reader import subrecords, walk

#: The HDPT part type of the eyes.
EYES_PART = 2
#: The target shape every build fit aims at (bake variant).
SHAPE = 'C2F'
#: Decimal places a record's slider values keep (zero unsigned): BLAS rounding never changes the record.
PLACES = 4


@dataclass(frozen=True)
class Problem:
    """One sex's fit: measure matrix, sculpt basis and regions, baseline face and FaceGeom, preset basis."""

    measures: np.ndarray
    basis: np.ndarray
    regions: list
    face: np.ndarray
    baseline: bytes
    presets: tuple
    eye_part: str


@functools.cache
def human_race() -> bytes:
    """Fallout4.esm's HumanRace body."""
    return next(r for r, _ in walk(FALLOUT4_ESM.read_bytes(), b'RACE') if r.form_id == tint.HUMAN_RACE).body


@functools.cache
def eye_parts() -> frozenset:
    """Fallout4.esm's eyes head part EditorIDs."""
    out = set()
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), b'HDPT'):
        subs = dict(subrecords(rec.body))
        if subs.get(b'PNAM') == struct.pack('<I', EYES_PART):
            out.add(facegeom.zstr(subs[b'EDID']))
    return frozenset(out)


def calibrated(female: bool) -> bool:
    """Whether one sex's sculpt and preset bases are measured."""
    return sculpt.basis_path(female).exists() and presets.basis_path(female).exists()


@functools.cache
def problem(female: bool) -> Problem:
    """The fit problem for one sex (both bases must be measured); once per process."""
    basis, regions, baseline = sculpt.load_basis(female)
    face = face_shape(baseline)[0]
    names = proportions.region_names(human_race(), female)
    measures = proportions.measure_matrix(proportions.region_sets(basis, regions, names, face), face)
    morph_basis, morphs = presets.load_basis(female)
    picks = {(p.group, p.morph): p.key for p in presets.race_presets(human_race(), female) if p.morph in morphs}
    eye_part = next(name for name in shape_names(baseline) if name in eye_parts())
    return Problem(measures, basis, regions, face, baseline,
                   (morph_basis, [(g, key, morphs.index(m)) for (g, m), key in picks.items()]), eye_part)


def shape_names(nif_bytes: bytes) -> list:
    """A NIF's shape names."""
    nif = nif_file.read(nif_bytes)
    return [nif.strings[struct.unpack_from('<i', raw)[0]] for kind, raw in nif.blocks
            if kind in facegeom.SHAPES and isinstance(raw, bytes)]


def target(p: Problem, fnv_head) -> np.ndarray:
    """The target measures: SHAPE's moves of FO4's baseline toward `fnv_head`."""
    return p.measures @ face_moves(p.baseline, fnv_head, SHAPE, p.eye_part)[1].ravel()


def measured(p: Problem, nif_bytes: bytes) -> np.ndarray:
    """A FaceGeom's measures off the baseline face."""
    return p.measures @ (face_shape(nif_bytes)[0] - p.face).ravel()


def predicted(p: Problem, values: np.ndarray, weights: dict) -> np.ndarray:
    """The measures slider values predict: sculpt `values` [region, CONTROLS], preset `weights` {MSDK key: w}."""
    moves = p.basis.reshape(len(p.basis), -1).T @ values.ravel()
    for _, key, m in p.presets[1]:
        moves = moves + p.presets[0][m].ravel() * weights.get(key, 0.0)
    return p.measures @ moves


def only(p: Problem, keys) -> tuple:
    """The preset basis limited to MSDK `keys` (the record's slots)."""
    return p.presets[0], [entry for entry in p.presets[1] if entry[1] in keys]


def rms(values: np.ndarray) -> float:
    """Root mean square."""
    return float(np.sqrt((values ** 2).mean()))


def fit(female: bool, fnv_head) -> tuple:
    """(FMRI/FMRS for every region, ((MSDK key, weight), ...), rms miss of the measures) of FNV head `fnv_head`,
    values to PLACES."""
    p = problem(female)
    goal = target(p, fnv_head)
    out = proportions.unmaxed_fit(p.measures, p.basis, p.presets, goal)
    picks = tuple((int(k), round(float(v), PLACES)) for k, _, v in out.presets)
    morphs = sculpt.face_morphs(p.regions, np.round(out.sculpt, PLACES) + 0.0, all_regions=True)
    return morphs, picks, rms(out.predicted - goal)


def refit(p: Problem, aim: np.ndarray, keys) -> proportions.Fit:
    """The unmaxed fit to `aim` on the record's preset slots `keys`."""
    return proportions.unmaxed_fit(p.measures, p.basis, only(p, keys), aim)
