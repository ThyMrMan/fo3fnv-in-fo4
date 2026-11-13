"""Our own FaceGeom NIF: the CK's rules for part order, bone nodes, shaders and shapes, and Willow against the CK.

See: docs/fork/fo4_facegen_plan.md#phase-1-our-own-facegeom
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.face import facegeom as FG
from fo4_import.face.bake import positions, with_positions
from fo4_import.nif import blocks as K
from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F
from fo4_import.pipeline.creation_kit import MO2

WILLOW_MOD = MO2 / 'mods' / 'F3NV - NVWillow'
PROFILE = Path(__file__).resolve().parents[1] / 'temp' / 'profile_data'
WILLOW = 0x47CBE4


class FakeSources:
    """Records by FormID, for FG.head_parts."""

    def __init__(self, records: dict):
        """`records`: {FormID: Rec}."""
        self.records = records

    def get(self, _rec, data: bytes):
        """The record the FormID in `data` names."""
        return self.records.get(struct.unpack('<I', data)[0])


def _part(edid: str, kind: int, extras=(), extra_part=False) -> FG.Rec:
    """A head part record with a model."""
    subs = [(b'EDID', edid.encode() + b'\0'), (b'MODL', b'x.nif\0'), (b'DATA', bytes([FG.EXTRA_PART if extra_part else 0])),
            (b'PNAM', struct.pack('<I', kind))]
    return FG.Rec('p.esp', b'HDPT', subs + [(b'HNAM', struct.pack('<I', e)) for e in extras])


def test_facegen_and_hair_tint_shaders_round_trip():
    """Type 4 (FaceGen, no extra fields) and type 6 (hair tint colour) keep their fields through reader and packer."""
    nif = F.NifFile()
    for kind, extra in ((K.SHADER_FACEGEN, {}), (K.SHADER_HAIR_TINT, {'hair_tint': (0.25, 0.5, 1.0)})):
        shader = dict(C.lighting_shader(nif, 'materials\\skin.bgsm', 1, 0), shader_type=kind, **extra)
        back = K.read_lighting(K.Reader(K.pack_lighting(shader)))
        assert back['shader_type'] == kind and back.get('hair_tint') == extra.get('hair_tint')


def test_parts_are_race_defaults_then_the_npcs_own_each_last_first_led_by_extras():
    """The NPC's head and eyes (last first), behind the defaults for types it lacks (gore, mouth: last first)."""
    parts = {1: _part('Head', 1, extras=[10]), 2: _part('Eyes', 2, extras=[11, 12]), 3: _part('Gore', 7),
             4: _part('Mouth', 8), 5: _part('DefaultHead', 1), 10: _part('Shadow', 0, extra_part=True),
             11: _part('Wet', 0, extra_part=True), 12: _part('Lashes', 0, extra_part=True)}
    npc = FG.Rec('p.esp', b'NPC_', [(b'PNAM', struct.pack('<I', f)) for f in (2, 11, 1)])
    race = FG.Rec('p.esp', b'RACE', [(b'MNAM', b''), (b'HEAD', struct.pack('<I', 9)), (b'FNAM', b'')]
                  + [(b'HEAD', struct.pack('<I', f)) for f in (5, 3, 4)])
    order = FG.head_parts(FakeSources(parts), npc, race, True)
    assert [FG.zstr(p.first(b'EDID')) for p in order] == ['Mouth', 'Gore', 'Shadow', 'Head', 'Wet', 'Lashes', 'Eyes']


def _node(nif: F.NifFile, name: str, pos: tuple, rot=FG.IDENTITY, children=()) -> tuple:
    """A NiNode block."""
    return 'NiNode', {'name': nif.string(name), 'extra': [], 'controller': -1, 'flags': 14, 'translation': pos,
                      'rotation': rot, 'scale': 1.0, 'collision': -1, 'children': list(children)}


def test_bone_positions_scale_the_skeleton_root_by_the_race_height():
    """A child 10 up a root turned a quarter about z lands at height x (rotated offset + root offset)."""
    nif = F.NifFile()
    quarter = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    nif.blocks = [_node(nif, 'Root', (0.0, 0.0, 100.0), quarter, [1]), _node(nif, 'Head', (10.0, 0.0, 0.0))]
    world = FG.world32(nif, 0.5)
    assert np.allclose(world['Root'], (0.0, 0.0, 50.0)) and np.allclose(world['Head'], (0.0, 5.0, 50.0))


def test_shader_type_and_flags_come_from_the_material():
    """Glow beats hair; hair tint, env map; specular off when its strength is 0; Transform_Changed always set."""
    assert FG.shader_type({'glowmap': True, 'hair': True}) == K.SHADER_GLOW
    assert FG.shader_type({'hair': True}) == K.SHADER_HAIR_TINT
    assert FG.shader_type({'env_mapping': True}) == K.SHADER_ENVMAP and FG.shader_type({}) == K.SHADER_DEFAULT
    sh = {'flags1': 1 | FG.EYE_ENVIRONMENT, 'flags2': 0}
    FG.set_flags(sh, {'specular': False, 'hair': True})
    assert sh == {'flags1': 1 << 18, 'flags2': FG.TRANSFORM_CHANGED}


def test_eye_data_offset_is_set_only_where_a_shape_has_none():
    """A shape with no eye data gets the CK's offset; male eyes' own is kept."""
    assert FG.eye_data(0x5B00050430208) == 0x5B00050430208 | FG.EYE_DATA
    assert FG.eye_data(0x5B08050430208) == 0x5B08050430208


def test_texture_set_paths_override_its_materials():
    """A set's own TX paths win; its material fills the rest."""
    class Mat:
        """A material source."""

        @staticmethod
        def material(_name):
            """One BGSM's textures."""
            return {'textures': {'diffuse': 'm_d.dds', 'normal': 'm_n.dds', 'smooth_spec': 'm_s.dds'}}

    txst = FG.Rec('p.esp', b'TXST', [(b'TX00', b'own_d.dds\0'), (b'MNAM', b'm.bgsm\0')])
    assert FG.txst_slots(Mat(), txst) == ['own_d.dds', 'm_n.dds', '', '', '', '', '', 'm_s.dds', '', '']


def _ck_willow() -> Path:
    """The deployed CK FaceGeom of Willow, or skip."""
    path = WILLOW_MOD / 'Meshes/Actors/Character/FaceGenData/FaceGeom/NVWillow.esp' / f'{WILLOW:08X}.NIF'
    if not path.exists() or not (PROFILE / 'FalloutNV.esm').exists():
        pytest.skip('no deployed NVWillow CK FaceGen')
    return path


def test_willow_matches_the_ck_byte_for_byte_but_her_slider_shape_and_one_bone_name_case():
    """With the CK's vertex positions (its slider morphs) and its 'Head' spelling, ours is the CK's file."""
    ck_bytes = _ck_willow().read_bytes()
    ours = F.read(FG.build(FG.Sources(WILLOW_MOD / 'NVWillow.esp', [WILLOW_MOD, PROFILE]), 'NVWillow.esp', WILLOW))
    ck = F.read(ck_bytes)
    for i, (kind, raw) in enumerate(ours.blocks):
        if kind == 'BSSubIndexTriShape':
            ours.blocks[i] = (kind, with_positions(raw, positions(ck.blocks[i][1])))
    ours.strings = ['Head' if s == 'HEAD' else s for s in ours.strings]
    assert F.write(ours) == ck_bytes
