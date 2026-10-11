"""Fallout 4's particle system blocks (stream 130), as dicts: the system, its data, modifiers and controllers.

Layouts from NifSkope's nif.xml. The NiPSys modifiers and controllers carry
no Bethesda-version conditions, so FNV's (stream 34) values fill the same
fields; NiParticleSystem takes BSGeometry's fields (bound, skin, shader,
alpha, vertex description) and LOD distances, and NiPSysData keeps only
counts and flags (no per-particle arrays). Each layout round-trips vanilla
Fallout 4's particle meshes byte for byte (tests). Strings and references
are indices, as in blocks.

See: docs/fork/fo4_pipeline.md#particles
"""

import struct

from fo4_import.nif.blocks import Reader, pack_refs, read_av, pack_av

#: NiPSysModifier: name (string), order, target (the system), active.
MODIFIER = (('name', 'i'), ('order', 'I'), ('target', 'i'), ('active', 'B'))
#: NiPSysEmitter's fields after the modifier's.
EMITTER = MODIFIER + (('speed', 'f'), ('speed_variation', 'f'), ('declination', 'f'),
                      ('declination_variation', 'f'), ('planar_angle', 'f'), ('planar_angle_variation', 'f'),
                      ('initial_color', '4f'), ('initial_radius', 'f'), ('radius_variation', 'f'),
                      ('life_span', 'f'), ('life_span_variation', 'f'), ('emitter_object', 'i'))
#: NiTimeController: next, flags, frequency, phase, start, stop, target.
CONTROLLER = (('next', 'i'), ('flags', 'H'), ('frequency', 'f'), ('phase', 'f'), ('start', 'f'), ('stop', 'f'),
              ('target', 'i'))
#: Fixed layouts: block type -> its fields in order.
SPECS = {
    'NiPSysBoxEmitter': EMITTER + (('width', 'f'), ('height', 'f'), ('depth', 'f')),
    'NiPSysCylinderEmitter': EMITTER + (('radius', 'f'), ('height', 'f')),
    'NiPSysAgeDeathModifier': MODIFIER + (('spawn_on_death', 'B'), ('spawn_modifier', 'i')),
    'NiPSysSpawnModifier': MODIFIER + (('num_spawn_generations', 'H'), ('percentage_spawned', 'f'),
                                       ('min_num_to_spawn', 'H'), ('max_num_to_spawn', 'H'),
                                       ('spawn_speed_variation', 'f'), ('spawn_dir_variation', 'f'),
                                       ('life_span', 'f'), ('life_span_variation', 'f')),
    'NiPSysRotationModifier': MODIFIER + (('rotation_speed', 'f'), ('rotation_speed_variation', 'f'),
                                          ('rotation_angle', 'f'), ('rotation_angle_variation', 'f'),
                                          ('random_rot_speed_sign', 'B'), ('random_axis', 'B'), ('axis', '3f')),
    'NiPSysGravityModifier': MODIFIER + (('gravity_object', 'i'), ('gravity_axis', '3f'), ('decay', 'f'),
                                         ('strength', 'f'), ('force_type', 'I'), ('turbulence', 'f'),
                                         ('turbulence_scale', 'f'), ('world_aligned', 'B')),
    'NiPSysDragModifier': MODIFIER + (('drag_object', 'i'), ('drag_axis', '3f'), ('percentage', 'f'),
                                      ('range', 'f'), ('range_falloff', 'f')),
    'NiPSysGrowFadeModifier': MODIFIER + (('grow_time', 'f'), ('grow_generation', 'H'), ('fade_time', 'f'),
                                          ('fade_generation', 'H'), ('base_scale', 'f')),
    'NiPSysBoundUpdateModifier': MODIFIER + (('update_skip', 'H'),),
    'NiPSysPositionModifier': MODIFIER,
    'BSPSysSimpleColorModifier': MODIFIER + (('fade_in', 'f'), ('fade_out', 'f'), ('color1_end', 'f'),
                                             ('color1_start', 'f'), ('color2_end', 'f'), ('color2_start', 'f'),
                                             ('colors', '12f')),
    'BSPSysSubTexModifier': MODIFIER + (('start_frame', 'f'), ('start_frame_fudge', 'f'), ('end_frame', 'f'),
                                        ('loop_start_frame', 'f'), ('loop_start_frame_fudge', 'f'),
                                        ('frame_count', 'f'), ('frame_count_fudge', 'f')),
    'BSPSysLODModifier': MODIFIER + (('lod_begin', 'f'), ('lod_end', 'f'), ('end_emit_scale', 'f'),
                                     ('end_size', 'f')),
    'NiPSysEmitterCtlr': CONTROLLER + (('interpolator', 'i'), ('modifier_name', 'i'),
                                       ('visibility_interpolator', 'i')),
    'NiPSysModifierActiveCtlr': CONTROLLER + (('interpolator', 'i'), ('modifier_name', 'i')),
    'NiPSysUpdateCtlr': CONTROLLER,
    'NiBoolInterpolator': (('value', 'B'), ('data', 'i')),
    'NiBoolTimelineInterpolator': (('value', 'B'), ('data', 'i')),
    'NiBlendBoolInterpolator': (('flags', 'B'), ('size', 'B'), ('threshold', 'f'), ('value', 'B')),
}
#: NiPSysData at stream 130 before its subtexture offsets, and after them.
DATA_HEAD = (('group_id', 'i'), ('max_vertices', 'H'), ('keep_flags', 'B'), ('compress_flags', 'B'),
             ('has_vertices', 'B'), ('data_flags', 'H'), ('material_crc', 'I'), ('has_normals', 'B'),
             ('bound', '4f'), ('has_colors', 'B'), ('consistency', 'H'), ('additional_data', 'i'), ('has_radii', 'B'),
             ('num_active', 'H'), ('has_sizes', 'B'), ('has_rotations', 'B'), ('has_rotation_angles', 'B'),
             ('has_rotation_axes', 'B'), ('has_texture_indices', 'B'))
DATA_TAIL = (('aspect_ratio', 'f'), ('aspect_flags', 'H'), ('speed_aspect2', 'f'), ('speed1', 'f'), ('speed2', 'f'),
             ('has_rotation_speeds', 'B'))
#: NiParticleSystem after NiAVObject: BSGeometry's bound and references, vertex description, LOD, data.
SYSTEM = (('bound', '4f'), ('skin', 'i'), ('shader', 'i'), ('alpha_property', 'i'), ('vertex_desc', 'Q'),
          ('far_begin', 'H'), ('far_end', 'H'), ('near_begin', 'H'), ('near_end', 'H'), ('data', 'i'),
          ('world_space', 'B'))


def read_fields(r: Reader, fields: tuple) -> dict:
    """`fields` read in order (a multi-value format gives a tuple)."""
    return {name: r.take(fmt) for name, fmt in fields}


def pack_fields(b: dict, fields: tuple) -> bytes:
    """`fields` of `b` packed in order."""
    return b''.join(struct.pack('<' + fmt, *(b[n] if isinstance(b[n], tuple) else (b[n],))) for n, fmt in fields)


def fixed(fields: tuple) -> tuple:
    """(reader, packer) of a fixed layout."""
    return (lambda r: read_fields(r, fields)), (lambda b: pack_fields(b, fields))


def read_data(r: Reader) -> dict:
    """NiPSysData at stream 130."""
    out = read_fields(r, DATA_HEAD)
    out['subtextures'] = [r.take('4f') for _ in range(r.take('I'))]
    out.update(read_fields(r, DATA_TAIL))
    return out


def pack_data(b: dict) -> bytes:
    """NiPSysData's bytes."""
    offsets = b''.join(struct.pack('<4f', *o) for o in b['subtextures'])
    return pack_fields(b, DATA_HEAD) + struct.pack('<I', len(b['subtextures'])) + offsets + pack_fields(b, DATA_TAIL)


def read_system(r: Reader) -> dict:
    """NiParticleSystem at stream 130."""
    out = {}
    read_av(r, out)
    out.update(read_fields(r, SYSTEM))
    out['modifiers'] = r.refs()
    return out


def pack_system(b: dict) -> bytes:
    """NiParticleSystem's bytes."""
    return pack_av(b) + pack_fields(b, SYSTEM) + pack_refs(b['modifiers'])


def read_scale(r: Reader) -> dict:
    """BSPSysScaleModifier: the modifier, then its scales."""
    out = read_fields(r, MODIFIER)
    out['scales'] = [r.take('f') for _ in range(r.take('I'))]
    return out


def pack_scale(b: dict) -> bytes:
    """BSPSysScaleModifier's bytes."""
    return pack_fields(b, MODIFIER) + struct.pack(f'<I{len(b["scales"])}f', len(b['scales']), *b['scales'])


def read_bool_data(r: Reader) -> dict:
    """NiBoolData: a key group of byte values (time, value; interpolation as the keys say)."""
    n = r.take('I')
    kind = r.take('I') if n else 0
    return {'kind': kind, 'keys': [r.take('fB') for _ in range(n)]}


def pack_bool_data(b: dict) -> bytes:
    """NiBoolData's bytes."""
    head = struct.pack('<I', len(b['keys'])) + (struct.pack('<I', b['kind']) if b['keys'] else b'')
    return head + b''.join(struct.pack('<fB', *k) for k in b['keys'])


#: Block type -> (reader, packer).
PARTICLE_BLOCKS = {
    **{kind: fixed(fields) for kind, fields in SPECS.items()},
    'NiPSysData': (read_data, pack_data),
    'NiParticleSystem': (read_system, pack_system),
    'BSPSysScaleModifier': (read_scale, pack_scale),
    'NiBoolData': (read_bool_data, pack_bool_data),
}
