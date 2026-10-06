"""Fallout 4 effect materials (.bgem, version 2), read and written as dicts.

The Material Editor's BaseMaterialFile fields (shared with .bgsm), five
texture paths, then the effect fields. Vanilla Fallout 4 ships version 2 only.

See: docs/fork/fo4_spikes.md#spike-2-bgem
"""

import struct

from fo4_import.nif.bgsm import BASE, Cursor, read_fields, pack_fields, pack_string

MAGIC = b'BGEM'
VERSION = 2
TEXTURES = ('base', 'grayscale', 'envmap', 'normal', 'env_mask')
EFFECT = (('blood', '?'), ('effect_lighting', '?'), ('falloff', '?'), ('falloff_color', '?'),
          ('grayscale_to_palette_alpha', '?'), ('soft', '?'), ('base_color', '3f'), ('base_color_scale', 'f'),
          ('falloff_start_angle', 'f'), ('falloff_stop_angle', 'f'), ('falloff_start_opacity', 'f'),
          ('falloff_stop_opacity', 'f'), ('lighting_influence', 'f'), ('env_min_lod', 'B'), ('soft_depth', 'f'))


def read(data: bytes) -> dict:
    """A material from .bgem bytes."""
    if data[:4] != MAGIC:
        raise ValueError('not a BGEM file')
    cur = Cursor(data)
    cur.pos = 4
    out = {'version': cur.take('I')}
    if out['version'] != VERSION:
        raise ValueError(f"BGEM version {out['version']} not supported")
    read_fields(cur, out, BASE)
    out['textures'] = {name: cur.string() for name in TEXTURES}
    read_fields(cur, out, EFFECT)
    return out


def write(m: dict) -> bytes:
    """A material's .bgem bytes."""
    out = MAGIC + struct.pack('<I', m['version']) + pack_fields(m, BASE)
    return out + b''.join(pack_string(m['textures'][name]) for name in TEXTURES) + pack_fields(m, EFFECT)
