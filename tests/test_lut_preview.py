"""Tests for tools/validate/lut_preview.py: LUT round trip, identity lookup, a graded lookup, neutral LUTs."""
import numpy as np
import pytest

from fo4_import.spike import imagespace as IM
from tools.validate import lut_preview as LP


def test_the_identity_lut_leaves_colours_alone():
    """The identity maps any colour to itself, within 8-bit rounding."""
    lut = IM.read_lut(IM.lut_dds(IM.identity()))
    colours = np.array([[0.0, 0.0, 0.0], [0.1, 0.5, 0.9], [0.33, 0.66, 1.0]])
    assert IM.apply_lut(colours, lut) == pytest.approx(colours, abs=1 / 255)


def test_a_graded_lut_shows_fnvs_grading():
    """Between the LUT's grid points, the lookup matches the grading it was made from."""
    grading = IM.Cinematic(0.6, (1.0, 0.74, 0.05), 0.4)
    lut = IM.read_lut(IM.lut_dds(IM.grade(IM.identity(), grading)))
    colours = np.array([[0.2, 0.3, 0.4], [0.7, 0.6, 0.5]])
    assert IM.apply_lut(colours, lut) == pytest.approx(IM.grade(colours, grading), abs=0.01)


def test_neutral_writes_an_identity_under_each_built_name(tmp_path):
    """One identity DDS per built LUT, same names."""
    built = tmp_path / 'built'
    built.mkdir()
    for name in ('FNV_A.dds', 'FNV_B.dds'):
        (built / name).write_bytes(b'x')
    assert LP.neutral(built, tmp_path / 'out') == 2
    assert (tmp_path / 'out' / 'FNV_B.dds').read_bytes() == IM.lut_dds(IM.identity())
