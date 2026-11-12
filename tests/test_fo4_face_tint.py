"""The face _d compositor: reading race tint options and NPC layers, race defaults, and the layer rules.

See: docs/fork/fo4_facegen_plan.md#face-d-decode
"""

import struct

import numpy as np

from fo4_import.face import face_tint as FT
from fo4_import.face.facegeom import Rec


def _option(slot: int, index: int, texture: str, blend: int, default=None, colours=()) -> list:
    """The subrecords of one race tint option; `colours` = [(FormID, alpha, template index, blend)]."""
    subs = [(b'TETI', struct.pack('<HH', slot, index)), (b'TTET', texture.encode() + b'\0'),
            (b'TTEB', struct.pack('<I', blend))]
    if colours:
        subs.append((b'TTEC', b''.join(struct.pack('<IfHI', *c) for c in colours)))
    return subs + ([(b'TTED', struct.pack('<f', default))] if default is not None else [])


def _race() -> Rec:
    """Male: tone, default brow, detail. Female: a tone."""
    male = (_option(12, 1, 'Tone.dds', 0, colours=[(0x10, 0.5, 900, 3), (0x11, 1.0, 901, 3)])
            + _option(23, 2, 'Brow.dds', 0, default=1.0) + _option(22, 3, 'Blotch.dds', 0))
    return Rec('race.esm', b'RACE', [(b'MNAM', b'')] + male + [(b'FNAM', b'')] + _option(12, 7, 'F.dds', 0))


def test_race_options_are_per_sex_with_colours_by_template_index():
    """Options come from the sex's section; TTEC colours are keyed by their template index field, not position."""
    male, female = FT.race_options(_race(), False), FT.race_options(_race(), True)
    assert sorted(male) == [1, 2, 3] and sorted(female) == [7]
    assert male[1].slot == 12 and male[1].texture == 'Tone.dds' and sorted(male[1].colours) == [900, 901]
    assert male[1].colours[901] == (struct.pack('<I', 0x11), 1.0, 3)
    assert male[2].default == 1.0 and male[3].default == 0.0


def test_npc_layers_and_race_defaults_fill_only_empty_slots():
    """TEND gives value, colour and template; a race default is added only for a slot the NPC leaves empty."""
    tone = struct.pack('<B4Bh', 100, 200, 180, 160, 0, -1)
    npc = Rec('p.esp', b'NPC_', [(b'TETI', struct.pack('<HH', 1, 1)), (b'TEND', tone),
                                 (b'TETI', struct.pack('<HH', 2, 3)), (b'TEND', bytes([40]))])
    layers = FT.npc_layers(npc)
    assert layers == [FT.Layer(1, 1, 1.0, (200, 180, 160), -1), FT.Layer(3, 2, 0.4)]
    options = FT.race_options(_race(), False)
    assert FT.with_defaults(layers, options)[-1] == FT.Layer(2, 2, 1.0)
    browed = layers + [FT.Layer(2, 2, 0.0)]
    assert FT.with_defaults(browed, options) == browed


def test_a_toneless_npc_gets_the_first_template_tone():
    """No Skin Tone layer: the first TTEC colour at full value."""
    options = FT.race_options(_race(), False)
    assert FT.with_defaults([], options) == [FT.Layer(2, 2, 1.0), FT.Layer(1, FT.COLOUR_LAYER, 1.0, None, 900)]


def test_blends_match_their_formulas():
    """Soft Light is Photoshop's; Default replaces; Multiply, Overlay and Hard Light at known points."""
    a, b = np.array([0.25, 0.25]), np.array([0.25, 0.75])
    assert np.allclose(FT.soft_light(a, b), [2 * .25 * .25 + .0625 * .5, 2 * .25 * .25 + 0.5 * 0.5])
    assert np.allclose(FT.blend(FT.DEFAULT, a, b), b) and np.allclose(FT.blend(FT.MULTIPLY, a, b), a * b)
    assert np.allclose(FT.blend(FT.OVERLAY, a, b), 2 * a * b)
    assert np.allclose(FT.blend(FT.HARD_LIGHT, a, b), [2 * .25 * .25, 1 - 2 * .75 * .25])


def test_layer_rules_tone_unmasked_and_default_details_twice():
    """The tone is Soft Light at value x alpha over the whole face; a Default detail goes twice at sqrt(alpha)."""
    out = np.full((1, 1, 3), 0.25, np.float32)
    rgba = np.zeros((1, 1, 4), np.float32)
    options = FT.race_options(_race(), False)
    tone = FT.apply(out, options[1], FT.Layer(1, 1, 1.0), rgba, (np.full(3, 0.75), 0.5, FT.DEFAULT))
    assert np.allclose(tone, 0.25 * 0.5 + 0.5 * FT.soft_light(np.float32(0.25), np.float32(0.75)))
    rgba[..., 3], rgba[..., :3] = 0.25, 1.0
    m = 0.5 * np.sqrt(0.25)
    once = 0.25 * (1 - m) + m
    assert np.allclose(FT.apply(out, options[3], FT.Layer(3, 2, 0.5), rgba), once * (1 - m) + m)
    assert np.allclose(FT.apply(out, options[2], FT.Layer(2, 2, 0.5), rgba), 0.25 * 0.875 + 0.125)
