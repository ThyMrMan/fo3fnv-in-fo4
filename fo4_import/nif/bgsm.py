"""Fallout 4 lighting materials (.bgsm, versions 1 and 2), read and written as dicts.

Field order is the Material Editor's BaseMaterialFile then BGSM, for the
versions vanilla Fallout 4 ships; strings are u32-length and keep their null.

See: docs/fork/fo4_spikes.md#spike-2-bgsm
"""

import struct

MAGIC = b'BGSM'
VERSION = 2
_B, _F, _I, _COLOR = '?', 'f', 'I', '3f'
#: BaseMaterialFile after the version: (name, struct format).
BASE = (('tile_flags', _I), ('uv_offset', '2f'), ('uv_scale', '2f'), ('alpha', _F),
        ('alpha_blend', _B), ('src_blend', _I), ('dst_blend', _I), ('alpha_test_ref', 'B'),
        ('alpha_test', _B), ('zbuffer_write', _B), ('zbuffer_test', _B), ('ssr', _B), ('wetness_ssr', _B),
        ('decal', _B), ('two_sided', _B), ('decal_no_fade', _B), ('non_occluder', _B), ('refraction', _B),
        ('refraction_falloff', _B), ('refraction_power', _F), ('env_mapping', _B), ('env_mask_scale', _F),
        ('grayscale_to_palette', _B))
TEXTURES = ('diffuse', 'normal', 'smooth_spec', 'greyscale', 'envmap', 'glow', 'inner_layer', 'wrinkles',
            'displacement')
#: BGSM after the textures, up to the root material.
LIGHTING = (('editor_alpha_ref', _B), ('rim_lighting', _B), ('rim_power', _F), ('backlight_power', _F),
            ('subsurface', _B), ('subsurface_rolloff', _F), ('specular', _B), ('specular_color', _COLOR),
            ('specular_mult', _F), ('smoothness', _F), ('fresnel_power', _F), ('wet_spec_scale', _F),
            ('wet_spec_power', _F), ('wet_spec_minvar', _F), ('wet_env_map_scale', _F), ('wet_fresnel', _F),
            ('wet_metalness', _F))
#: After the root material; emittance colour is written only when emittance is on.
TAIL = (('aniso_lighting', _B), ('emittance', _B))
AFTER_EMIT = (('emittance_mult', _F), ('model_space_normals', _B), ('external_emittance', _B),
              ('back_lighting', _B), ('receive_shadows', _B), ('hide_secret', _B), ('cast_shadows', _B),
              ('dissolve_fade', _B), ('assume_shadowmask', _B), ('glowmap', _B), ('env_window', _B),
              ('env_eye', _B), ('hair', _B), ('hair_tint', _COLOR), ('tree', _B), ('facegen', _B),
              ('skin_tint', _B), ('tessellate', _B), ('displacement_bias', _F), ('displacement_scale', _F),
              ('tessellation_pn_scale', _F), ('tessellation_base', _F), ('tessellation_fade', _F),
              ('grayscale_scale', _F))
SKEW = (('skew_specular_alpha', _B),)


class Cursor:
    """A read position over the file."""

    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def take(self, fmt: str):
        """One field: a value, or a tuple for multi-value formats."""
        values = struct.unpack_from('<' + fmt, self.data, self.pos)
        self.pos += struct.calcsize('<' + fmt)
        return values[0] if len(values) == 1 else values

    def string(self) -> str:
        """A u32-length string, its null dropped."""
        n = self.take('I')
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw.rstrip(b'\x00').decode('cp1252')


def read_fields(cur: Cursor, out: dict, fields: tuple) -> None:
    """Read `fields` into `out`."""
    for name, fmt in fields:
        out[name] = cur.take(fmt)


def read(data: bytes) -> dict:
    """A material from .bgsm bytes."""
    if data[:4] != MAGIC:
        raise ValueError('not a BGSM file')
    cur = Cursor(data)
    cur.pos = 4
    out = {'version': cur.take('I')}
    if out['version'] not in (1, 2):
        raise ValueError(f"BGSM version {out['version']} not supported")
    read_fields(cur, out, BASE)
    out['textures'] = {name: cur.string() for name in TEXTURES}
    read_fields(cur, out, LIGHTING)
    out['root_material'] = cur.string()
    read_fields(cur, out, TAIL)
    if out['emittance']:
        out['emittance_color'] = cur.take(_COLOR)
    read_fields(cur, out, AFTER_EMIT)
    if out['version'] >= 2:
        read_fields(cur, out, SKEW)
    return out


def pack_string(text: str) -> bytes:
    """A u32-length string with its null."""
    raw = text.encode('cp1252') + b'\x00'
    return struct.pack('<I', len(raw)) + raw


def pack_fields(m: dict, fields: tuple) -> bytes:
    """`fields` of material `m`."""
    return b''.join(struct.pack('<' + fmt, *(m[n] if isinstance(m[n], tuple) else (m[n],))) for n, fmt in fields)


def write(m: dict) -> bytes:
    """A material's .bgsm bytes."""
    out = MAGIC + struct.pack('<I', m['version']) + pack_fields(m, BASE)
    out += b''.join(pack_string(m['textures'][name]) for name in TEXTURES)
    out += pack_fields(m, LIGHTING) + pack_string(m['root_material']) + pack_fields(m, TAIL)
    if m['emittance']:
        out += struct.pack('<3f', *m['emittance_color'])
    out += pack_fields(m, AFTER_EMIT)
    return out + (pack_fields(m, SKEW) if m['version'] >= 2 else b'')
