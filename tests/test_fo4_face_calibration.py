"""The face bases are measured on our own FaceGen, without the Creation Kit, and a head takes its morph presets as
the CK bakes them: a part's chargen .tri morph by vertex index, extras unmoved.

See: docs/fork/fo4_facegen_plan.md#calibration
"""

import struct

import numpy as np
import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import calibration, chargen, facegeom, presets
from tes5_import.base.tes5_reader import subrecords


def _part(path: str) -> facegeom.Rec:
    """A head part listing an expression .tri, then the chargen .tri `path`."""
    return facegeom.Rec('x.esp', b'HDPT', [(b'NAM0', struct.pack('<I', 1)), (b'NAM1', b'Expr.tri\0'),
                                           (b'NAM0', struct.pack('<I', chargen.CHARGEN)),
                                           (b'NAM1', path.encode() + b'\0')])


class _Src:
    """A Sources holding one .tri's morphs."""

    def __init__(self, morphs: dict):
        """`morphs` {lower-case name: deltas}, whatever path is asked."""
        self.morphs = morphs

    def tri_morphs(self, path: str) -> dict:
        """The one .tri's morphs, for the chargen path only."""
        assert path == 'Chargen.tri'
        return self.morphs


def test_a_preset_moves_vertex_i_by_the_tri_vertex_i_and_leaves_the_extras():
    """Weight times delta by index; the part's vertices past the .tri's count stay; no preset moves nothing."""
    src = _Src({'nosefeature1': np.ones((3, 3))})
    moved = chargen.offsets(src, _part('Chargen.tri'), {'nosefeature1': 0.5}, 5)
    assert moved.tolist() == [[0.5] * 3] * 3 + [[0.0] * 3] * 2
    assert chargen.offsets(src, _part('Chargen.tri'), {'other': 1.0}, 5) is None
    assert chargen.offsets(src, _part('Chargen.tri'), {}, 5) is None


def test_an_npc_weights_its_race_presets_by_morph_name():
    """MSDK keys name the race's presets for the NPC's sex (MPPI to MPPM, matched without case); MSDV weights them."""
    race = facegeom.Rec('fallout4.esm', b'RACE', [
        (b'MNAM', b''), (b'MPGN', b'Nose\0'), (b'MPPI', struct.pack('<I', 7)), (b'MPPM', b'NoseFeature1\0'),
        (b'FNAM', b''), (b'MPGN', b'Nose\0'), (b'MPPI', struct.pack('<I', 9)), (b'MPPM', b'NoseFeature2\0')])
    npc = facegeom.Rec('x.esp', b'NPC_', [(b'MSDK', struct.pack('<2I', 7, 9)), (b'MSDV', struct.pack('<2f', 0.5, 1.0))])
    assert chargen.npc_weights(npc, race, female=False) == {'nosefeature1': 0.5}
    assert chargen.npc_weights(npc, race, female=True) == {'nosefeature2': 1.0}


def test_ensure_measures_only_the_missing_bases(tmp_path, monkeypatch):
    """Each sex's sculpt, preset and tint base is measured once; a cached one is left alone."""
    made = []

    def fake(base):
        """A measure writing `base`'s file for one sex."""
        def measure(female):
            """Write and note the file."""
            made.append((base.__name__, female))
            base.basis_path(female).write_bytes(b'')
            return base.basis_path(female)
        return measure
    for base, _ in calibration.MEASURES:
        monkeypatch.setattr(base, 'basis_path', lambda female=False, n=base.__name__: tmp_path / f'{n}{female}.npz')
    monkeypatch.setattr(calibration, 'MEASURES', tuple((base, fake(base)) for base, _ in calibration.MEASURES))
    (tmp_path / 'fo4_import.face.sculptFalse.npz').write_bytes(b'')
    assert calibration.ensure(log=lambda line: None) == 5
    assert ('fo4_import.face.sculpt', False) not in made
    assert calibration.ensure(log=lambda line: None) == 0


@pytest.mark.skipif(not FALLOUT4_ESM.is_file(), reason='Fallout 4 is not installed here')
def test_our_preset_heads_carry_the_head_tri_morphs(tmp_path, monkeypatch):
    """Measured on our heads, each male preset's effect on the face is its BaseMaleHeadCharGen.tri morph by index
    (half-float positions: within 0.016).
    See: docs/fork/fo4_facegen_plan.md#preset-morphs
    """
    monkeypatch.setattr(presets, 'basis_path', lambda female=False: tmp_path / 'presets.npz')
    calibration.measure_presets(False)
    with np.load(tmp_path / 'presets.npz') as data:
        basis, names = data['basis'], [str(n) for n in data['names']]
    race = calibration.template(False)[0]
    src = facegeom.Sources(FALLOUT4_ESM, [])
    morphs = src.tri_morphs('Actors\\Character\\CharacterAssets\\BaseMaleHeadCharGen.tri')
    assert len(names) == len(presets.morphs(presets.race_presets(subrecords(race.body), False))) > 20
    for row, name in zip(basis, names):
        want = np.zeros_like(row)
        n = min(len(row), len(morphs[name.lower()]))
        want[:n] = morphs[name.lower()][:n]
        assert np.abs(row - want).max() < 0.016, name
