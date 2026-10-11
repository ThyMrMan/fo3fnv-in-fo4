"""FNV particle systems as Fallout 4's: the system, its data, modifiers and controllers (particle_blocks layouts).

A modifier or controller FO4 shares with FNV keeps FNV's values (pyffi's
older names mapped by ALIASES); references go to the converted system,
modifiers and kept nodes (the emitter, gravity and drag objects), strings to
the file's table. FO4 never uses NiPSysGrowFadeModifier (0 of vanilla's 729
systems), so FNV's grow and fade times become a BSPSysScaleModifier's scale
curve over the first emitter's life span. FO4-only fields take vanilla's
values (all 729: vertex description, zero bound; most: no LOD distances,
aspect 1). Colliders, bomb and mesh emitters are left out.

See: docs/fork/fo4_pipeline.md#particles
"""

from fo4_import.nif.blocks import NONE
from fo4_import.nif.particle_blocks import SPECS
from fo4_import.nif.shader_anim import interpolator, timing

#: Our field name -> pyffi's for the FNV blocks where they differ.
ALIASES = {'rotation_speed': 'initial_rotation_speed', 'rotation_speed_variation': 'initial_rotation_speed_variation',
           'rotation_angle': 'initial_rotation_angle', 'rotation_angle_variation': 'initial_rotation_angle_variation',
           'random_axis': 'random_initial_axis', 'axis': 'initial_axis', 'spawn_speed_variation': 'spawn_speed_chaos',
           'spawn_dir_variation': 'spawn_dir_chaos', 'world_aligned': 'unknown_byte', 'drag_object': 'parent',
           'fade_in': 'fade_in_percent', 'fade_out': 'fade_out_percent', 'color1_end': 'color_1_end_percent',
           'color1_start': 'color_1_start_percent', 'color2_end': 'color_2_end_percent',
           'color2_start': 'color_2_start_percent', 'lod_begin': 'uknown_float_1', 'lod_end': 'uknown_float_2',
           'end_emit_scale': 'uknown_float_3', 'end_size': 'uknown_float_4'}
#: Fields naming a scene node (kept as a node so the reference resolves).
OBJECT_FIELDS = ('emitter_object', 'gravity_object', 'drag_object')
#: Controllers FO4 shares with FNV on a particle system.
CONTROLLERS = ('NiPSysEmitterCtlr', 'NiPSysModifierActiveCtlr', 'NiPSysUpdateCtlr')
#: Vanilla's NiParticleSystem vertex description (all 729 systems).
VERTEX_DESC = 594510335218548785
#: Points of a grow/fade scale curve over the particle's life.
SCALE_SAMPLES = 33


def drives_particles(cb) -> bool:
    """Whether an FNV controlled block drives a particle controller (emitter rate or activity, a modifier's)."""
    return cb.controller_type.decode('cp1252') in CONTROLLERS


def particle_block(nif, cb, made: dict) -> 'dict | None':
    """The FO4 controlled block of FNV particle channel `cb`, bound to its converted controller in `made`
    ({id(FNV controller): FO4 index}); None when that controller is not converted."""
    controller = made.get(id(cb.controller)) if cb.controller is not None else None
    if controller is None:
        return None
    text = lambda value: nif.string(value.decode('cp1252')) if value else NONE
    return {'interpolator': interpolator(nif, cb.interpolator), 'controller': controller, 'priority': cb.priority,
            'node': text(cb.node_name), 'property': text(cb.property_type), 'controller_type': text(cb.controller_type),
            'controller_id': text(cb.variable_1), 'interpolator_id': text(cb.variable_2)}


def systems(root) -> list:
    """FNV `root`'s shown particle systems."""
    return [b for b in root.tree() if type(b).__name__ == 'NiParticleSystem' and not b.flags & 1]


def wanted_nodes(root, found: list) -> set:
    """ids of the FNV nodes the particle systems hang under or name (emitter, gravity and drag objects)."""
    parents = {id(c): n for n in root.tree() if hasattr(n, 'children') for c in n.children if c is not None}
    out = {id(parents[id(s)]) for s in found if id(s) in parents}
    for system in found:
        for mod in system.modifiers:
            for field in OBJECT_FIELDS:
                target = getattr(mod, ALIASES.get(field, field), None)
                if target is not None:
                    out.add(id(target))
    return out


def add_system(nif, system, owner: int, nodes: dict, shader: tuple) -> dict:
    """Append FNV particle `system` under block `owner` with `shader` (shader, alpha indices); {id(FNV controller):
    FO4 index} of its converted controllers."""
    index = len(nif.blocks)
    nif.blocks.append(('NiParticleSystem', {}))
    data = _data(nif, system.data)
    supported = [m for m in system.modifiers
                 if type(m).__name__ in SPECS or type(m).__name__ == 'BSPSysScaleModifier' or _grow_fade(m)]
    refs = {'system': index, 'nodes': nodes,
            'modifiers': {id(m): len(nif.blocks) + i for i, m in enumerate(supported)}}
    life = next((float(m.life_span) for m in supported if hasattr(m, 'emitter_object')), 1.0)
    for mod in supported:
        nif.blocks.append(_modifier(nif, mod, refs, life))
    made = _controllers(nif, system, index, {m.name for m in supported})
    t = system.translation
    nif.blocks[index] = ('NiParticleSystem', {
        'name': nif.string(system.name.decode('cp1252')), 'extra': [], 'controller': next(iter(made.values()), NONE),
        'flags': system.flags, 'translation': (t.x, t.y, t.z),
        'rotation': tuple(v for column in zip(*system.rotation.as_list()) for v in column), 'scale': system.scale,
        'collision': NONE, 'bound': (0.0, 0.0, 0.0, 0.0), 'skin': NONE, 'shader': shader[0],
        'alpha_property': shader[1], 'vertex_desc': VERTEX_DESC, 'far_begin': 0, 'far_end': 0, 'near_begin': 0,
        'near_end': 0, 'data': data, 'world_space': int(system.world_space),
        'modifiers': list(refs['modifiers'].values())})
    nif.blocks[owner][1]['children'].append(index)
    return made


def _data(nif, d) -> int:
    """Append FO4 NiPSysData for FNV data `d` (its counts, flags and subtextures); its index."""
    nif.blocks.append(('NiPSysData', {
        'group_id': 0, 'max_vertices': d.bs_max_vertices, 'keep_flags': 0, 'compress_flags': 0, 'has_vertices': 1,
        'data_flags': 0, 'material_crc': 0, 'has_normals': 0, 'bound': (0.0, 0.0, 0.0, 0.0),
        'has_colors': int(d.has_vertex_colors), 'consistency': 0, 'additional_data': NONE,
        'has_radii': int(d.has_radii), 'num_active': 0, 'has_sizes': int(d.has_sizes),
        'has_rotations': int(d.has_rotations), 'has_rotation_angles': int(d.has_rotation_angles),
        'has_rotation_axes': int(d.has_rotation_axes), 'has_texture_indices': int(d.has_uv_quadrants),
        'subtextures': [(q.x, q.y, q.z, q.w) for q in d.uv_quadrants] if d.has_uv_quadrants else [],
        'aspect_ratio': 1.0, 'aspect_flags': 0, 'speed_aspect2': 0.0, 'speed1': 0.0, 'speed2': 0.0,
        'has_rotation_speeds': int(d.unknown_byte_2)}))
    return len(nif.blocks) - 1


def _grow_fade(mod) -> bool:
    """Whether `mod` is an FNV grow/fade modifier (made a scale curve)."""
    return type(mod).__name__ == 'NiPSysGrowFadeModifier'


def _modifier(nif, mod, refs: dict, life: float) -> tuple:
    """The FO4 (type, dict) of a supported FNV modifier."""
    head = {name: _value(nif, name, getattr(mod, name), refs) for name, _ in SPECS['NiPSysPositionModifier']}
    if _grow_fade(mod):
        return 'BSPSysScaleModifier', {**head, 'scales': scale_curve(mod.grow_time, mod.fade_time, life)}
    kind = type(mod).__name__
    if kind == 'BSPSysScaleModifier':
        return kind, {**head, 'scales': [float(v) for v in mod.floats]}
    return kind, {name: _value(nif, name, getattr(mod, ALIASES.get(name, name)), refs) for name, _ in SPECS[kind]}


def scale_curve(grow: float, fade: float, life: float) -> list:
    """Particle scale at SCALE_SAMPLES even points of `life`: 0 to 1 over `grow` seconds, back to 0 over the last
    `fade`."""
    out = []
    for i in range(SCALE_SAMPLES):
        age = life * i / (SCALE_SAMPLES - 1)
        up = age / grow if grow > 0 else 1.0
        down = (life - age) / fade if fade > 0 else 1.0
        out.append(max(0.0, min(1.0, up, down)))
    return out


def _value(nif, name: str, value, refs: dict):
    """One field's FO4 value: strings and references renumbered, vectors and colours as tuples."""
    if name in ('name', 'modifier_name'):
        return nif.string(value.decode('cp1252'))
    if name == 'target':
        return refs['system']
    if name in OBJECT_FIELDS:
        return refs['nodes'].get(id(value), NONE) if value is not None else NONE
    if name == 'spawn_modifier':
        return refs['modifiers'].get(id(value), NONE) if value is not None else NONE
    if name == 'colors':
        return tuple(v for c in value for v in (c.r, c.g, c.b, c.a))
    if hasattr(value, 'a'):
        return value.r, value.g, value.b, value.a
    if hasattr(value, 'z'):
        return value.x, value.y, value.z
    return int(value) if isinstance(value, bool) else value


def _controllers(nif, system, target: int, modifiers: set) -> dict:
    """Append FO4 copies of FNV `system`'s particle controllers, chained in FNV's order; {id(FNV): FO4 index}.

    A controller of a modifier not converted (not in `modifiers`, FNV names) is left out: FO4 crashes looking
    it up (NiPSysModifierActiveCtlr::InterpTargetIsCorrectType on a null modifier).
    See: docs/fork/fo4_pipeline.md#particles
    """
    made, previous = {}, None
    controller = system.controller
    while controller is not None:
        kind = type(controller).__name__
        named = getattr(controller, 'modifier_name', None)
        if kind in CONTROLLERS and (named is None or kind == 'NiPSysUpdateCtlr' or named in modifiers):
            block = {**timing(controller), 'next': NONE, 'target': target}
            if kind != 'NiPSysUpdateCtlr':
                block.update(interpolator=interpolator(nif, controller.interpolator),
                             modifier_name=nif.string(controller.modifier_name.decode('cp1252')))
            if kind == 'NiPSysEmitterCtlr':
                block['visibility_interpolator'] = interpolator(nif, controller.visibility_interpolator)
            made[id(controller)] = len(nif.blocks)
            nif.blocks.append((kind, block))
            if previous is not None:
                nif.blocks[previous][1]['next'] = made[id(controller)]
            previous = made[id(controller)]
        controller = controller.next_controller
    return made
