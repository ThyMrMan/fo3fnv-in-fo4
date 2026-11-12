"""The slider fit to proportions, morph preset records, the rear head part copy and hair morph copying."""

import struct

import numpy as np

from asset_convert.character.facegen_tri import TriFile
from fo4_import.face import hair_morphs, presets, proportions, slider_records
from fo4_import.face.facegeom import USES_BODY_TEXTURE, Rec
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


def test_rear_part_copy_takes_its_own_texture_set():
    """The copy is renamed, drops Uses Body Texture and names its own TXST before RNAM."""
    part = Rec('fallout4.esm', b'HDPT', [(b'EDID', b'Rear\0'), (b'DATA', bytes([0x35])),
                                         (b'TNAM', struct.pack('<I', 5)), (b'RNAM', struct.pack('<I', 9))])
    subs = list(subrecords(slider_records.rear_part(part, 'Mine', 0x04000800)))
    assert subs == [(b'EDID', b'Mine\0'), (b'DATA', bytes([0x35 & ~USES_BODY_TEXTURE])),
                    (b'TNAM', struct.pack('<I', 0x04000800)), (b'RNAM', struct.pack('<I', 9))]


def test_a_race_given_rear_head_is_added_after_the_last_head_part():
    """With no rear head in PNAM, the own part follows the NPC's last PNAM."""
    fit = proportions.Fit(np.zeros((0, 7)), [], np.zeros(0), np.zeros(0))
    body = _subs(('EDID', b'x\0'), ('PNAM', struct.pack('<I', 1)), ('QNAM', bytes(16)))
    subs = list(subrecords(slider_records.fitted_npc(body, fit, [], (None, 0x04000801))))
    assert [d for t, d in subs if t == b'PNAM'] == [struct.pack('<I', 1), struct.pack('<I', 0x04000801)]


def test_a_part_vertex_on_a_head_point_takes_its_morph():
    """Copied morph deltas are the head's at its own points."""
    head = TriFile([(0, 0, 0), (5, 0, 0), (0, 5, 0), (0, 0, 5)], [(0, 1, 2)], morphs={
        'M': [(1, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)]})
    assert np.allclose(hair_morphs.copied_morphs(head, np.array([[0.0, 0, 0]]))['M'], [[1, 0, 0]])
