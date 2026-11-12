"""The slider fit to proportions and its refit, morph preset records, the rear head cut, the in-place record
patches and hair morph copying."""

import struct

import numpy as np

from asset_convert.character.facegen_tri import TriFile
from fo4_import.face import hair_morphs, npc_skin, presets, proportions, slider_fit
from fo4_import.spike import facegen_skin
from fo4_import.spike.face_fit import record_subrecords
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

FACE = np.array([[1.0, 0, 0], [-1.0, 0, 0], [0, 0, 1.0], [0, 0, -1.0]])


def _subs(*pairs) -> bytes:
    """Packed subrecords from (tag, data) pairs."""
    return b''.join(pack_subrecord(t, d) for t, d in pairs)


def test_presets_go_right_after_qnam_and_replace_any():
    """MSDK/MSDV land after QNAM, once."""
    body = _subs(('EDID', b'x\0'), ('QNAM', bytes(16)), ('MSDK', bytes(4)), ('MSDV', bytes(4)), ('TETI', bytes(4)))
    tags = [t for t, _ in subrecords(presets.with_presets(body, [7, 9], [0.25, 0.5]))]
    assert tags == [b'EDID', b'QNAM', b'MSDK', b'MSDV', b'TETI']


def test_race_presets_read_one_sex_and_skip_texture_only_ones():
    """Only the asked sex's presets that name a morph."""
    race = _subs(('MNAM', b''), ('MPGN', b'Nose\0'), ('MPPI', struct.pack('<I', 1)), ('MPPM', b'NoseA\0'),
                 ('FNAM', b''), ('MPGN', b'Nose\0'), ('MPPI', struct.pack('<I', 2)), ('MPPM', b'\0'),
                 ('MPPI', struct.pack('<I', 3)), ('MPPM', b'NoseB\0'))
    assert presets.race_presets(race, True) == [presets.Preset('Nose', 3, 'NoseB')]


def _problem():
    """A width and a height over 4 vertices, a 2-region sculpt basis and one preset group of two morphs."""
    sets = {'A': np.array([True, True, False, False]), 'B': np.array([False, False, True, False]),
            'C': np.array([False, False, False, True])}
    measures = proportions.measure_matrix(sets, FACE, (('w', 'w', 'A', None), ('h', 'z', 'B', 'C')))
    basis = np.zeros((14, 4, 3))
    basis[0, 0, 0], basis[0, 1, 0] = 0.1, -0.1
    basis[7, 2, 2] = 0.1
    morphs = np.zeros((2, 4, 3))
    morphs[1, 2, 2] = 0.5
    return measures, basis, (morphs, [('G', 11, 0), ('G', 12, 1)])


def test_measures_are_widths_and_differences():
    """Right minus left mean x; one region's mean z minus another's."""
    measures, _, _ = _problem()
    assert np.allclose(measures @ FACE.ravel(), [2.0, 2.0])


def test_unmaxed_fit_leaves_nothing_at_the_bound():
    """A target past the bound is fitted with no control at it."""
    measures, basis, morph_basis = _problem()
    out = proportions.unmaxed_fit(measures, basis, morph_basis, np.array([0.5, 0.2]))
    assert proportions.at_bound(out) == 0


def test_fit_picks_at_most_one_preset_per_group():
    """Of a group's presets only the useful one is taken."""
    measures, basis, morph_basis = _problem()
    out = proportions.fit(measures, basis, morph_basis, np.array([0.0, 0.2]), np.full(16, proportions.RIDGE))
    assert [k for k, _, _ in out.presets] == [12]


def _slider_problem() -> slider_fit.Problem:
    """_problem as a slider_fit.Problem over two regions."""
    measures, basis, morph_basis = _problem()
    return slider_fit.Problem(measures, basis, [5, 6], FACE, b'', morph_basis, 'Eyes')


def test_a_records_sliders_predict_what_the_fit_predicted():
    """predicted() of the fit's own values is the fit's prediction (the refine starts from it)."""
    p = _slider_problem()
    out = proportions.fit(p.measures, p.basis, p.presets, np.array([0.05, 0.2]), np.full(16, proportions.RIDGE))
    weights = {k: v for k, _, v in out.presets}
    assert np.allclose(slider_fit.predicted(p, out.sculpt, weights), out.predicted)


def test_a_refit_keeps_the_records_preset_slots():
    """A refit picks only among the record's MSDK keys."""
    p = _slider_problem()
    assert slider_fit.only(p, {11})[1] == [('G', 11, 0)]
    assert [k for k, _, _ in slider_fit.refit(p, np.array([0.0, 0.2]), {11}).presets] in ([], [11])


def test_the_rear_head_island_holds_its_uvs_and_moves_them_into_the_cut():
    """The square cut covers every UV plus padding, on whole texels, and the moved UVs fall inside 0..1."""
    uv = np.array([[0.06, 0.67], [0.19, 0.85], [0.1, 0.7]])
    lo, hi = npc_skin.island(uv, 2048)
    assert (lo <= uv.min(0)).all() and (hi >= uv.max(0)).all() and np.isclose(*(hi - lo))
    moved = (uv - lo) / (hi - lo)
    assert (moved > 0).all() and (moved < 1).all()
    crop = npc_skin.cut(np.zeros((2048, 2048, 4), np.uint8), (lo, hi))
    assert crop.shape[0] == crop.shape[1] == round((hi - lo)[0] * 2048)


def _record(*pairs) -> bytearray:
    """One uncompressed NPC_ record of `pairs`."""
    body = _subs(*pairs)
    return bytearray(b'NPC_' + struct.pack('<IIIIHH', len(body), 0, 0x801, 0, 0, 0) + body)


def test_slider_and_tone_patches_write_in_place():
    """FMRS by its FMRI, MSDV in order, QNAM to the asked colour and the Skin Tone TEND by the same scale."""
    raw = _record(('QNAM', struct.pack('<4f', 0.5, 0.5, 0.5, 1)), ('MSDK', struct.pack('<I', 11)),
                  ('MSDV', struct.pack('<f', 0.1)), ('TETI', struct.pack('<HH', 12, 7)),
                  ('TEND', bytes([1, 100, 100, 100, 0, 0, 0])),
                  ('FMRI', struct.pack('<I', 6)), ('FMRS', bytes(36)))
    subs = record_subrecords(raw, 0, len(raw) - 24)
    facegen_skin.slider_edit({6: np.arange(7.0)}, [0.3])(raw, subs)
    facegen_skin.tone_edit(np.array([0.25, 0.5, 1.0]), frozenset({7}))(raw, subs)
    out = dict((t, bytes(raw[a:a + n])) for t, a, n in subs)
    assert struct.unpack('<7f', out[b'FMRS'][:28]) == tuple(range(7)) and np.isclose(struct.unpack('<f', out[b'MSDV'])[0], 0.3)
    assert struct.unpack('<4f', out[b'QNAM']) == (0.25, 0.5, 1.0, 1.0) and out[b'TEND'][1:4] == bytes([50, 100, 200])


def test_a_part_vertex_on_a_head_point_takes_its_morph():
    """Copied morph deltas are the head's at its own points."""
    head = TriFile([(0, 0, 0), (5, 0, 0), (0, 5, 0), (0, 0, 5)], [(0, 1, 2)], morphs={
        'M': [(1, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)]})
    assert np.allclose(hair_morphs.copied_morphs(head, np.array([[0.0, 0, 0]]))['M'], [[1, 0, 0]])
