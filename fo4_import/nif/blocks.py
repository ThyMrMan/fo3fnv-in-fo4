"""The Fallout 4 blocks of a static mesh, as dicts, read from and packed to bytes.

Layouts from NifSkope 2.0's nif.xml at BS stream 130: NiNode, BSXFlags,
BSTriShape, BSLightingShaderProperty, BSShaderTextureSet, NiAlphaProperty.
A `string` field is an index into the file's string table (-1: none); a
reference is a block index (-1: none). Vertices are dicts of the attributes
their descriptor names.

See: docs/fork/fo4_spikes.md#spike-2-nif
"""

import struct

NONE = -1
#: BSVertexDesc attribute bits (nif.xml VertexAttribute).
VA_VERTEX, VA_UV, VA_NORMAL, VA_TANGENT, VA_COLOR, VA_SKINNED, VA_FULL_PRECISION = 0x1, 0x2, 0x8, 0x10, 0x20, 0x40, 0x400
#: Vanilla Raider02MaskM.nif's vertex descriptor: half positions, UV, normal, tangent, skin (32 bytes).
DESC_SKINNED = 0x5B00050430208
#: The same with vertex colours before the skin (36 bytes).
DESC_SKINNED_COLOR = 0x7B00065430209
#: Shader flags1 bit Skinned (lighting and effect shaders alike).
SHADER_SKINNED = 0x2


class Reader:
    """A cursor over one block's bytes."""

    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def take(self, fmt: str):
        """Unpack `fmt` (little-endian) at the cursor; one value or a tuple."""
        values = struct.unpack_from('<' + fmt, self.data, self.pos)
        self.pos += struct.calcsize('<' + fmt)
        return values[0] if len(values) == 1 else values

    def sized(self) -> str:
        """A u32-length string."""
        n = self.take('I')
        text = self.data[self.pos:self.pos + n].decode('cp1252')
        self.pos += n
        return text

    def refs(self) -> list:
        """A u32 count, then that many i32 references."""
        n = self.take('I')
        return list(self.take(f'{n}i')) if n > 1 else ([self.take('i')] if n else [])


def pack_refs(values: list) -> bytes:
    """A u32 count, then the i32 references."""
    return struct.pack(f'<I{len(values)}i', len(values), *values)


def pack_sized(text: str) -> bytes:
    """A u32-length string."""
    raw = text.encode('cp1252')
    return struct.pack('<I', len(raw)) + raw


def read_net(r: Reader, out: dict) -> None:
    """NiObjectNET: name, extra data, controller."""
    out['name'], out['extra'], out['controller'] = r.take('i'), r.refs(), r.take('i')


def pack_net(b: dict) -> bytes:
    """NiObjectNET's bytes."""
    return struct.pack('<i', b['name']) + pack_refs(b['extra']) + struct.pack('<i', b['controller'])


def read_av(r: Reader, out: dict) -> None:
    """NiAVObject at stream 130: NiObjectNET, flags, transform, collision."""
    read_net(r, out)
    out['flags'] = r.take('I')
    out['translation'], out['rotation'], out['scale'] = r.take('3f'), r.take('9f'), r.take('f')
    out['collision'] = r.take('i')


def pack_av(b: dict) -> bytes:
    """NiAVObject's bytes."""
    return (pack_net(b) + struct.pack('<I3f9ff', b['flags'], *b['translation'], *b['rotation'], b['scale'])
            + struct.pack('<i', b['collision']))


def read_node(r: Reader) -> dict:
    """NiNode (and BSFadeNode)."""
    out = {}
    read_av(r, out)
    out['children'] = r.refs()
    return out


def pack_node(b: dict) -> bytes:
    """NiNode's bytes."""
    return pack_av(b) + pack_refs(b['children'])


def read_value_node(r: Reader) -> dict:
    """BSValueNode: a NiNode, its value (an add-on node's ADDN index) and a flags byte."""
    out = read_node(r)
    out['value'], out['value_flags'] = r.take('I'), r.take('B')
    return out


def pack_value_node(b: dict) -> bytes:
    """BSValueNode's bytes."""
    return pack_node(b) + struct.pack('<IB', b['value'], b.get('value_flags', 0))


def read_bsx(r: Reader) -> dict:
    """BSXFlags: a name and an integer."""
    return {'name': r.take('i'), 'value': r.take('I')}


def pack_bsx(b: dict) -> bytes:
    """BSXFlags' bytes."""
    return struct.pack('<iI', b['name'], b['value'])


def read_alpha(r: Reader) -> dict:
    """NiAlphaProperty: NiObjectNET, flags, threshold."""
    out = {}
    read_net(r, out)
    out['alpha_flags'], out['threshold'] = r.take('H'), r.take('B')
    return out


def pack_alpha(b: dict) -> bytes:
    """NiAlphaProperty's bytes."""
    return pack_net(b) + struct.pack('<HB', b['alpha_flags'], b['threshold'])


def read_texture_set(r: Reader) -> dict:
    """BSShaderTextureSet: its texture paths."""
    return {'textures': [r.sized() for _ in range(r.take('I'))]}


def pack_texture_set(b: dict) -> bytes:
    """BSShaderTextureSet's bytes."""
    return struct.pack('<I', len(b['textures'])) + b''.join(pack_sized(t) for t in b['textures'])


#: BSLightingShaderProperty after NiObjectNET at stream 130, for a shader type with no extra fields.
_LIGHTING = (('flags1', 'I'), ('flags2', 'I'), ('uv_offset', '2f'), ('uv_scale', '2f'), ('texture_set', 'i'),
             ('emissive_color', '3f'), ('emissive_multiple', 'f'), ('root_material', 'i'), ('clamp', 'I'),
             ('alpha', 'f'), ('refraction', 'f'), ('smoothness', 'f'), ('specular_color', '3f'),
             ('specular_strength', 'f'), ('subsurface_rolloff', 'f'), ('rimlight_power', 'f'))
_LIGHTING_TAIL = (('grayscale_scale', 'f'), ('fresnel_power', 'f'), ('wetness', '6f'))
_FLT_MAX = struct.unpack('<f', struct.pack('<f', 3.4028234663852886e38))[0]
#: Shader types whose extra fields this module reads (default, environment map, glow: none extra; skin tint).
SHADER_DEFAULT, SHADER_ENVMAP, SHADER_GLOW, SHADER_SKIN_TINT = 0, 1, 2, 5


def read_lighting(r: Reader) -> dict:
    """BSLightingShaderProperty at stream 130 (default, environment-map or skin-tint type)."""
    out = {'shader_type': r.take('I')}
    read_net(r, out)
    for name, fmt in _LIGHTING:
        out[name] = r.take(fmt)
    if _FLT_MAX <= out['rimlight_power'] < float('inf'):
        out['backlight_power'] = r.take('f')
    for name, fmt in _LIGHTING_TAIL:
        out[name] = r.take(fmt)
    if out['shader_type'] == SHADER_ENVMAP:
        out['envmap'] = r.take('f2B')
    elif out['shader_type'] == SHADER_SKIN_TINT:
        out['skin_tint'] = r.take('4f')
    elif out['shader_type'] not in (SHADER_DEFAULT, SHADER_GLOW):
        raise ValueError(f"shader type {out['shader_type']} not supported")
    if r.pos != len(r.data):
        raise ValueError(f"shader type {out['shader_type']}: {len(r.data) - r.pos} bytes not read")
    return out


def _flat(value) -> tuple:
    """A field's value as a tuple for struct.pack."""
    return value if isinstance(value, tuple) else (value,)


def pack_lighting(b: dict) -> bytes:
    """BSLightingShaderProperty's bytes."""
    out = struct.pack('<I', b['shader_type']) + pack_net(b)
    for name, fmt in _LIGHTING:
        out += struct.pack('<' + fmt, *_flat(b[name]))
    if 'backlight_power' in b:
        out += struct.pack('<f', b['backlight_power'])
    for name, fmt in _LIGHTING_TAIL:
        out += struct.pack('<' + fmt, *_flat(b[name]))
    if b['shader_type'] == SHADER_ENVMAP:
        out += struct.pack('<f2B', *b['envmap'])
    elif b['shader_type'] == SHADER_SKIN_TINT:
        out += struct.pack('<4f', *b['skin_tint'])
    return out


#: BSEffectShaderProperty's fields between its two groups of texture paths, at stream 130.
_EFFECT_MID = (('clamp', 'B'), ('lighting_influence', 'B'), ('env_min_lod', 'B'), ('unused', 'B'),
               ('falloff', '4f'), ('base_color', '4f'), ('base_color_scale', 'f'), ('soft_depth', 'f'))


def read_effect(r: Reader) -> dict:
    """BSEffectShaderProperty at stream 130."""
    out = {}
    read_net(r, out)
    out['flags1'], out['flags2'], out['uv_offset'], out['uv_scale'] = r.take('I'), r.take('I'), r.take('2f'), r.take('2f')
    out['source_texture'] = r.sized()
    for name, fmt in _EFFECT_MID:
        out[name] = r.take(fmt)
    out['greyscale'], out['env_map'], out['normal'], out['env_mask'] = r.sized(), r.sized(), r.sized(), r.sized()
    out['env_map_scale'] = r.take('f')
    return out


def pack_effect(b: dict) -> bytes:
    """BSEffectShaderProperty's bytes."""
    out = pack_net(b) + struct.pack('<II2f2f', b['flags1'], b['flags2'], *b['uv_offset'], *b['uv_scale'])
    out += pack_sized(b['source_texture'])
    for name, fmt in _EFFECT_MID:
        out += struct.pack('<' + fmt, *_flat(b[name]))
    out += b''.join(pack_sized(b[k]) for k in ('greyscale', 'env_map', 'normal', 'env_mask'))
    return out + struct.pack('<f', b['env_map_scale'])


def read_vertex(r: Reader, attrs: int) -> dict:
    """One BSVertexData for the descriptor's attribute bits."""
    v = {}
    if attrs & VA_VERTEX:
        full = attrs & VA_FULL_PRECISION
        v['position'] = r.take('3f' if full else '3e')
        v['bitangent_x'] = r.take(('f' if full else 'e') if attrs & VA_TANGENT else ('I' if full else 'H'))
    if attrs & VA_UV:
        v['uv'] = r.take('2e')
    if attrs & VA_NORMAL:
        v['normal'], v['bitangent_y'] = r.take('3B'), r.take('B')
        if attrs & VA_TANGENT:
            v['tangent'], v['bitangent_z'] = r.take('3B'), r.take('B')
    if attrs & VA_COLOR:
        v['color'] = r.take('4B')
    if attrs & VA_SKINNED:
        v['weights'], v['bones'] = r.take('4e'), r.take('4B')
    return v


def pack_vertex(v: dict, attrs: int) -> bytes:
    """One BSVertexData's bytes; normals and tangents stay in their stored bytes (0..255)."""
    out = b''
    if attrs & VA_VERTEX:
        full = attrs & VA_FULL_PRECISION
        out += struct.pack('<3f' if full else '<3e', *v['position'])
        fmt = ('f' if full else 'e') if attrs & VA_TANGENT else ('I' if full else 'H')
        out += struct.pack('<' + fmt, v['bitangent_x'])
    if attrs & VA_UV:
        out += struct.pack('<2e', *v['uv'])
    if attrs & VA_NORMAL:
        out += bytes(v['normal']) + bytes([v['bitangent_y']])
        if attrs & VA_TANGENT:
            out += bytes(v['tangent']) + bytes([v['bitangent_z']])
    if attrs & VA_COLOR:
        out += bytes(v['color'])
    if attrs & VA_SKINNED:
        out += struct.pack('<4e', *v['weights']) + bytes(v['bones'])
    return out


def read_tri_shape(r: Reader) -> dict:
    """BSTriShape at stream 130 (a skinned one's vertices carry weights and bone indices)."""
    out = {}
    read_av(r, out)
    out['bound'] = r.take('4f')
    out['skin'], out['shader'], out['alpha_property'] = r.take('3i')
    out['vertex_desc'] = r.take('Q')
    n_tris, n_verts, size = r.take('I'), r.take('H'), r.take('I')
    attrs = out['vertex_desc'] >> 44
    out['vertices'] = [read_vertex(r, attrs) for _ in range(n_verts)] if size else []
    out['triangles'] = [r.take('3H') for _ in range(n_tris)] if size else []
    if not size:
        out['counts'] = (n_tris, n_verts)
    return out


def pack_tri_shape(b: dict) -> bytes:
    """BSTriShape's bytes; the data size is recomputed, `counts` kept for a shape with no data (particles)."""
    desc, verts, tris = b['vertex_desc'], b['vertices'], b['triangles']
    size = (desc & 0xF) * len(verts) * 4 + len(tris) * 6
    n_tris, n_verts = b.get('counts', (len(tris), len(verts)))
    out = pack_av(b) + struct.pack('<4f3iQIHI', *b['bound'], b['skin'], b['shader'], b['alpha_property'],
                                   desc, n_tris, n_verts, size)
    attrs = desc >> 44
    out += b''.join(pack_vertex(v, attrs) for v in verts)
    return out + b''.join(struct.pack('<3H', *t) for t in tris)


#: Block type -> (reader, packer). NiNode subclasses that add nothing share NiNode's.
BLOCKS = {
    'NiNode': (read_node, pack_node), 'BSFadeNode': (read_node, pack_node), 'BSLeafAnimNode': (read_node, pack_node),
    'BSValueNode': (read_value_node, pack_value_node),
    'BSXFlags': (read_bsx, pack_bsx), 'NiAlphaProperty': (read_alpha, pack_alpha),
    'BSShaderTextureSet': (read_texture_set, pack_texture_set),
    'BSLightingShaderProperty': (read_lighting, pack_lighting),
    'BSEffectShaderProperty': (read_effect, pack_effect),
    'BSTriShape': (read_tri_shape, pack_tri_shape),
}
