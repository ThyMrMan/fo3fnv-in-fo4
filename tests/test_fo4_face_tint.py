"""The face _d compositor: reading race tint options and NPC layers, the CK's layer list, and the shader's rules.

See: docs/fork/fo4_facegen_plan.md#ck-face-shader
"""

import io
import struct

import numpy as np
from PIL import Image

from fo4_import.face import face_tint as FT
from fo4_import.face.facegeom import Rec

#: A palette TTED holding default entry index 1 (the CK reads the float's bits as a u32).
ENTRY_1 = struct.unpack('<f', struct.pack('<I', 1))[0]


def _option(slot: int, index: int, texture: str, blend: int, default=None, colours=()) -> list:
    """The subrecords of one race tint option; `texture` names its _d, _n, _s (comma-separated); `colours` =
    [(FormID, alpha, template index, blend)]."""
    subs = [(b'TETI', struct.pack('<HH', slot, index))]
    subs += [(b'TTET', name.encode() + b'\0') for name in texture.split(',')] + [(b'TTEB', struct.pack('<I', blend))]
    if colours:
        subs.append((b'TTEC', b''.join(struct.pack('<IfHI', *c) for c in colours)))
    return subs + ([(b'TTED', struct.pack('<f', default))] if default is not None else [])


def _race() -> Rec:
    """Male: tone, default brow, detail, lip (default entry 1). Female: a tone."""
    male = (_option(12, 1, 'Tone.dds', 0, colours=[(0x10, 0.5, 900, 0), (0x11, 1.0, 901, 0)])
            + _option(23, 2, 'Brow.dds', 0, default=1.0) + _option(22, 3, 'Blotch_d,Blotch_n,Blotch_s', 0)
            + _option(13, 4, 'Lip.dds', 0, ENTRY_1, [(0x12, 0.25, 950, 1), (0x13, 0.75, 951, 3)]))
    return Rec('race.esm', b'RACE', [(b'MNAM', b'')] + male + [(b'FNAM', b'')] + _option(12, 7, 'F.dds', 0))


def test_race_options_are_per_sex_with_colours_by_template_index():
    """Options come from the sex's section; TTEC colours are keyed by their template index field, not position."""
    male, female = FT.race_options(_race(), False), FT.race_options(_race(), True)
    assert sorted(male) == [1, 2, 3, 4] and sorted(female) == [7]
    assert male[1].slot == 12 and male[1].texture == 'Tone.dds' and sorted(male[1].colours) == [900, 901]
    assert male[1].colours[901] == (struct.pack('<I', 0x11), 1.0, 0)
    assert male[2].default == 1.0 and male[3].default == 0.0
    assert male[3].texture == 'Blotch_d' and male[3].map_texture('msn') == 'Blotch_n'
    assert male[3].map_texture('s') == 'Blotch_s' and male[2].map_texture('s') == ''


def test_a_palettes_tted_is_its_default_entry_index():
    """Palette slots 7..20 read TTED's bits as an index into TTEC; no TTED is entry 0; past the end is none."""
    male = FT.race_options(_race(), False)
    assert male[1].palette and male[4].palette and not male[2].palette
    assert male[4].default_entry == (951, (struct.pack('<I', 0x13), 0.75, 3))
    assert male[1].default_entry[0] == 900
    assert FT.Option(13, (), 0, {}, 0.0).default_entry == (None, None)


def test_npc_layers_and_the_ck_layer_list():
    """TEND gives value, colour and template; every unlisted option gets its default; reverse race order."""
    tone = struct.pack('<B4Bh', 100, 200, 180, 160, 0, -1)
    npc = Rec('p.esp', b'NPC_', [(b'TETI', struct.pack('<HH', 1, 1)), (b'TEND', tone),
                                 (b'TETI', struct.pack('<HH', 2, 3)), (b'TEND', bytes([40]))])
    layers = FT.npc_layers(npc)
    assert layers == [FT.Layer(1, 1, 1.0, (200, 180, 160), -1), FT.Layer(3, 2, 0.4)]
    options = FT.race_options(_race(), False)
    baked = [layer for _, layer in FT.baked_layers(layers, options)]
    assert baked == [FT.Layer(4, FT.COLOUR_LAYER, 0.75, template=951), FT.Layer(3, 2, 0.4), FT.Layer(2, 2, 1.0),
                     layers[0]]


def test_a_brow_layer_drops_the_default_brow_and_a_toneless_npc_gets_entry_0():
    """A listed brow blocks the brow default (at 0 it draws nothing); no tone layer: the tone default entry."""
    options = FT.race_options(_race(), False)
    browed = [layer for _, layer in FT.baked_layers([FT.Layer(2, 2, 0.3)], options)]
    assert browed == [FT.Layer(4, 1, 0.75, template=951), FT.Layer(2, 2, 0.3), FT.Layer(1, 1, 0.5, template=900)]
    zero = [layer.index for _, layer in FT.baked_layers([FT.Layer(2, 2, 0.0)], options)]
    assert zero == [4, 1]


def test_blends_match_the_shader():
    """Default replaces; Multiply; Overlay keyed on the base; Hard Light on the layer; Soft Light in gamma."""
    a, b = np.array([0.25, 0.75]), np.array([0.25, 0.75])
    assert np.allclose(FT.soft_light(a, b), [2 * .25 * .25 + .0625 * .5, 2 * .75 * .25 + np.sqrt(.75) * .5])
    assert np.allclose(FT.blend(FT.DEFAULT, a, b), b) and np.allclose(FT.blend(FT.MULTIPLY, a, b), a * b)
    assert np.allclose(FT.blend(FT.OVERLAY, a, b[::-1]), [2 * .25 * .75, 1 - 2 * .25 * .75])
    assert np.allclose(FT.blend(FT.HARD_LIGHT, a[::-1], b), [2 * .75 * .25, 1 - 2 * .75 * .25])
    g = 1 / FT.GAMMA
    assert np.allclose(FT.blend(FT.SOFT_LIGHT, a, b), FT.soft_light(a ** g, b ** g) ** FT.GAMMA)


def test_layers_go_on_at_mask_to_one_over_gamma_times_value():
    """A palette uses its texture's red, a texture set its linear RGB at its alpha; both lerp at mask^(1/2.2) x v."""
    out = np.full((1, 1, 3), 0.25, np.float32)
    rgba = np.array([[[0.5, 0.0, 0.0, 0.25]]], np.float32)
    options = FT.race_options(_race(), False)
    m = 0.5 ** (1 / FT.GAMMA) * 0.8
    got = FT.apply(out, options[4], FT.Layer(4, 1, 0.8), rgba, (np.full(3, 0.6, np.float32), FT.MULTIPLY))
    assert np.allclose(got, 0.25 + m * (0.25 * 0.6 - 0.25))
    m = 0.25 ** (1 / FT.GAMMA) * 0.5
    got = FT.apply(out, options[3], FT.Layer(3, 2, 0.5), rgba)
    assert np.allclose(got, 0.25 + m * (FT.linear(rgba[..., :3]) - 0.25))


def test_a_layers_map_goes_on_at_its_diffuse_weight():
    """_msn and _s: the layer's own map lerped in at its _d alpha^(1/2.2) x value, red and green only."""
    out = np.full((1, 1, 2), 0.5, np.float32)
    diffuse = np.zeros((1, 1, 4), np.float32)
    diffuse[..., 3] = 0.25
    own = np.array([[[1.0, 0.0, 0.7, 1.0]]], np.float32)
    got = FT.apply_map(out, FT.Layer(3, 2, 0.8), diffuse, own)
    m = 0.8 * 0.25 ** (1 / FT.GAMMA)
    assert got.shape == (1, 1, 2) and np.allclose(got, [[[0.5 * (1 - m) + m, 0.5 * (1 - m)]]])


def test_an_own_colour_takes_the_default_entrys_blend_and_the_tone_is_always_soft_light():
    """No matching template: the layer's colour, linear, by the default entry's blend; the skin tone by Soft Light."""
    options = FT.race_options(_race(), False)
    rgb, op = FT.colour_of(None, None, options[4], FT.Layer(4, 1, 1.0, (255, 0, 0), -1))
    assert op == FT.SOFT_LIGHT and np.allclose(rgb, [1, 0, 0])
    assert FT.colour_of(None, None, options[1], FT.Layer(1, 1, 1.0, (128, 0, 0), -1))[1] == FT.SOFT_LIGHT
    lip = FT.Option(13, (), FT.MULTIPLY, {5: (b'', 1.0, FT.OVERLAY)}, 0.0)
    assert FT.colour_of(None, None, lip, FT.Layer(4, 1, 1.0, (0, 0, 0), -1))[1] == FT.OVERLAY


class _Src:
    """A Sources stand-in: CLFM records by FormID data, and one 4 x 2 hair gradient for every texture read."""

    def __init__(self, colours: dict):
        self.colours = colours

    def get(self, owner, data):
        """The CLFM for `data`, or None."""
        return self.colours.get(data)

    def read(self, path: str) -> bytes:
        """A 4 x 2 PNG: row 0 dark greys, row 1 reds rising left to right."""
        out = io.BytesIO()
        pixels = [(10, 10, 10), (20, 20, 20), (30, 30, 30), (40, 40, 40), (60, 0, 0), (120, 0, 0), (180, 0, 0), (240, 0, 0)]
        img = Image.new('RGB', (4, 2))
        img.putdata(pixels)
        img.save(out, 'PNG')
        return out.getvalue()


def _clfm(row: float, flags: int) -> Rec:
    """A CLFM with CNAM `row` (as a float) and FNAM `flags`."""
    return Rec('p.esp', b'CLFM', [(b'CNAM', struct.pack('<f', row)), (b'FNAM', struct.pack('<I', flags))])


def _face(npc_hair: bytes, hnam: bool = True) -> FT.Face:
    """A male Face whose NPC names `npc_hair` (b'' for none) and whose race defaults to hair 3 (male) and 4."""
    src = _Src({b'\1\0\0\0': _clfm(0.5, 3), b'\2\0\0\0': _clfm(0.5, 1), b'\3\0\0\0': _clfm(0.0, 2)})
    race = Rec('race.esm', b'RACE', [(b'HCLF', b'\3\0\0\0\4\0\0\0')] + ([(b'HNAM', b'Hair/Lut.dds\0')] if hnam else []))
    npc = Rec('p.esp', b'NPC_', [(b'HCLF', npc_hair)] if npc_hair else [])
    return FT.Face(src, npc, race, False)


def test_the_hair_row_is_a_remapping_clfms_cnam_float():
    """NPC HCLF, else the race's; needs the Remapping Index flag and the CLFM."""
    assert _face(b'\1\0\0\0').hair_row() == 0.5 and _face(b'\2\0\0\0').hair_row() is None
    assert _face(b'').hair_row() == 0.0 and _face(b'\x09\0\0\0').hair_row() is None


def test_brows_take_the_hair_gradient_or_black():
    """Column (linear green)^(1/2.2), row hair_row(), decoded to linear; black without HNAM or a row."""
    rgba = np.array([[[0, 0, 0, 1], [0, 1, 0, 1]]], np.float32)
    got = FT.brow_colour(_face(b'\1\0\0\0'), rgba)
    assert np.allclose(got, FT.linear(np.array([[[60, 0, 0], [240, 0, 0]]], np.float32) / 255))
    assert not FT.brow_colour(_face(b'\1\0\0\0', hnam=False), rgba).any()
    assert not FT.brow_colour(_face(b'\2\0\0\0'), rgba).any()
