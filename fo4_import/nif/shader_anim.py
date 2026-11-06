"""FNV shader animation in a controller sequence as Fallout 4's: shader property controllers on the converted shape.

FNV animates a shape's material through a sequence's controlled block naming
the shape, the property and the controller type: NiAlphaController (alpha),
NiTextureTransformController (`0-0-TT_TRANSLATE_U`: scroll), NiMaterialColorController
(`SELF_ILLUM`: emissive colour), BSMaterialEmittanceMultController. FO4 drives the
same values on the shape's shader property, as vanilla sentrybotfacelight.nif
and ashpile01.nif: a BS{Effect,Lighting}ShaderProperty{Float,Color}Controller
whose controlled variable is the block's controller ID ("5"), with FNV's
float or point interpolator and keys. An emissive channel of a cut-out glow
shape drives its neon overlay (named <shape>Glow).

See: docs/fork/fo4_pipeline.md#effect-animation
"""

import struct

import numpy as np

from asset_convert.havok.kf_decode import SPLINE_DEGREE, eval_bspline
from fo4_import.nif.blocks import NONE
from fo4_import.nif.glow_scale import map_keys

#: (FNV controller type, FNV channel) -> (FO4 value kind, effect shader variable, lighting shader variable).
CHANNELS = {
    ('NiAlphaController', ''): ('Float', 5, 12),
    ('NiTextureTransformController', 'TT_TRANSLATE_U'): ('Float', 6, 20),
    ('NiTextureTransformController', 'TT_TRANSLATE_V'): ('Float', 8, 22),
    ('NiTextureTransformController', 'TT_SCALE_U'): ('Float', 7, 21),
    ('NiTextureTransformController', 'TT_SCALE_V'): ('Float', 9, 23),
    ('NiMaterialColorController', 'SELF_ILLUM'): ('Color', 0, 1),
    ('BSMaterialEmittanceMultController', ''): ('Float', 0, 11),
}
#: FNV controller types that light a shape: on a cut-out glow shape they drive its overlay.
EMISSIVE = ('NiMaterialColorController', 'BSMaterialEmittanceMultController')
#: FNV's emittance multiplier (dropped on blended unlit shapes) and NiAlphaProperty's blend bit.
EMITTANCE, ALPHA_BLEND = 'BSMaterialEmittanceMultController', 1
#: The neon overlay's name suffix (convert_static's cut-out glow).
GLOW_SUFFIX = 'Glow'
#: A controller's idle blend interpolator, as vanilla's: manager-controlled flag, size 2, value unset (-FLT_MAX).
MANAGER_CONTROLLED, BLEND_SIZE, UNSET = 1, 2, -3.4028234663852886e38
#: A bool interpolator's unset value (vanilla's controller-owned NiBoolInterpolators hold 2).
BOOL_UNSET = 2
#: FNV interpolator -> (FO4 interpolator, its data, values per key).
INTERPOLATORS = {'NiFloatInterpolator': ('NiFloatInterpolator', 'NiFloatData', 1),
                 'NiPoint3Interpolator': ('NiPoint3Interpolator', 'NiPosData', 3),
                 'NiBSplineCompFloatInterpolator': ('NiFloatInterpolator', 'NiFloatData', 1),
                 'NiBSplineCompPoint3Interpolator': ('NiPoint3Interpolator', 'NiPosData', 3)}
#: The compressed B-spline interpolators among them (spline() samples them); a channel with no control points.
SPLINES, NO_HANDLE = ('NiBSplineCompFloatInterpolator', 'NiBSplineCompPoint3Interpolator'), 0xFFFF
#: Keys per second a B-spline channel is sampled at; NiAnimationKey linear interpolation.
SPLINE_FPS, LINEAR = 30, 1
#: NiTimeController flag of a controller a manager's sequences drive (unset: it runs on its own).
MANAGED = 0x20
#: A free NiTextureTransformController's operation and NiMaterialColorController's target, as sequences name them.
OPERATIONS = ('TT_TRANSLATE_U', 'TT_TRANSLATE_V', 'TT_ROTATE', 'TT_SCALE_U', 'TT_SCALE_V')
TARGET_COLORS = ('AMB', 'DIFF', 'SPEC', 'SELF_ILLUM')


def channel_of(ctype: str, variable: str, interp) -> 'tuple | None':
    """CHANNELS' entry of FNV controller `ctype` on `variable` by `interp`, or None."""
    found = CHANNELS.get((ctype, variable.rsplit('-', 1)[-1])) or CHANNELS.get((ctype, ''))
    return found if found and type(interp).__name__ in INTERPOLATORS else None


def channel(cb) -> 'tuple | None':
    """channel_of() an FNV controlled block."""
    return channel_of(cb.controller_type.decode('cp1252'), cb.variable_1.decode('cp1252'), cb.interpolator)


def free_controllers(root) -> list:
    """(shape name, controller, CHANNELS entry) of every controller on FNV `root`'s shape properties that runs on
    its own (no manager drives it) and that FO4 has a shader channel for.

    See: docs/fork/fo4_pipeline.md#free-controllers
    """
    out = []
    for geom in (g for g in root.tree() if hasattr(g, 'get_properties')):
        for prop in geom.get_properties():
            controller = prop.controller
            while controller is not None:
                found = not controller.flags & MANAGED and channel_of(
                    type(controller).__name__, _variable(controller), controller.interpolator)
                if found:
                    out.append((geom.name.decode('cp1252'), controller, found))
                controller = controller.next_controller
    return out


def _variable(controller) -> str:
    """A free FNV controller's channel as a controlled block names it ('' if one)."""
    if hasattr(controller, 'operation') and controller.texture_slot == 0:
        return OPERATIONS[controller.operation]
    return TARGET_COLORS[controller.target_color] if hasattr(controller, 'target_color') else ''


def free_running(nif, found: list, peaks: dict, shapes: dict = None) -> int:
    """Append FO4 shader controllers for free_controllers() `found`, each with its own keyed interpolator and FNV's
    flags (vanilla's free controllers: active, loop or clamp), on `shapes` (shapes_by_name's form; by default the
    mesh's BSTriShapes); unlit shapes' texel `peaks` scale emittance. How many were written."""
    at = {'shapes': shapes if shapes is not None else shapes_by_name(nif), 'peaks': peaks}
    return sum(add_running(nif, at, (name, entry, controller.interpolator),
                           (type(controller).__name__, timing(controller), emit_multi(controller.target)))
               for name, controller, entry in found)


def add_running(nif, at: dict, channel_on: tuple, how: tuple) -> int:
    """Append one free-running FO4 shader controller for FNV channel `channel_on` (shape name, CHANNELS entry,
    FNV interpolator) among `at` (free_running's), `how` being (FNV controller type, timing, the shape's FNV
    emittance multiplier); 1 if written, else 0.

    See: docs/fork/fo4_pipeline.md#free-controllers
    """
    name, entry, source = channel_on
    fnv_type, when, mult = how
    target = _target(nif, fnv_type, entry, name, at)
    if target is None:
        return 0
    name, shader, kind, ctype, variable = target
    interp = interpolator(nif, source)
    _emittance_keys(nif, fnv_type, interp, name, at)
    if fnv_type == 'NiMaterialColorController' and kind == 'BSEffectShaderProperty' and not name.endswith(GLOW_SUFFIX):
        unlit_emissive(nif, interp, mult)
    nif.blocks.append((ctype, {**when, 'next': nif.blocks[shader][1]['controller'], 'target': shader,
                               'interpolator': interp, 'variable': variable}))
    nif.blocks[shader][1]['controller'] = len(nif.blocks) - 1
    return 1


def emit_multi(material) -> float:
    """An FNV NiMaterialProperty's emittance multiplier (1 for another property)."""
    return float(getattr(material, 'emit_multi', 1.0))


def unlit_emissive(nif, interp: int, mult: float) -> None:
    """Make an unlit shape's emissive colour keys what FNV shows: colour times its emittance multiplier `mult`,
    clipped to 1 (the static conversion's white).

    See: docs/fork/fo4_pipeline.md#unlit-emissive
    """
    data = nif.blocks[interp][1]['data'] if interp >= 0 else NONE
    if data < 0:
        return
    group = nif.blocks[data][1]['keys']
    group['keys'] = [(k[0], *(min(1.0, v * mult) for v in k[1:4]), *(t * mult for t in k[4:])) for k in group['keys']]


def shapes_by_name(nif) -> dict:
    """{name: shape_entry()} of a converted mesh's BSTriShapes."""
    out = {}
    for i, (kind, block) in enumerate(nif.blocks):
        if kind == 'BSTriShape' and block['shader'] >= 0:
            out.setdefault(nif.strings[block['name']], shape_entry(nif, i, block['shader'], block['alpha_property']))
    return out


def shape_entry(nif, shape: int, shader: int, alpha: int) -> tuple:
    """(shape, shader, 'Effect' or 'Lighting', alpha property) of a shape."""
    return shape, shader, 'Effect' if nif.blocks[shader][0] == 'BSEffectShaderProperty' else 'Lighting', alpha


def shader_block(nif, cb, timing: dict, at: dict, priority: int) -> 'dict | None':
    """The FO4 controlled block (with its controller and interpolator appended) of FNV shader channel `cb`;
    None when unsupported or its shape is not converted. `at` holds the converted `shapes` (shapes_by_name),
    `made` (controllers per shape and variable) and unlit shapes' texel `peaks`."""
    made, found, fnv_type = at['made'], channel(cb), cb.controller_type.decode('cp1252')
    target = _target(nif, fnv_type, found, cb.node_name.decode('cp1252'), at) if found else None
    if target is None:
        return None
    name, shader, kind, ctype, variable = target
    interp = interpolator(nif, cb.interpolator)
    _emittance_keys(nif, fnv_type, interp, name, at)
    key = (shader, ctype, variable)
    if key not in made:
        blend = idle_blend(nif, 'Point3' if ctype.endswith('ColorController') else 'Float')
        made[key] = len(nif.blocks)
        nif.blocks.append((ctype, {**timing, 'next': nif.blocks[shader][1]['controller'], 'target': shader,
                                   'interpolator': blend, 'variable': variable}))
        nif.blocks[shader][1]['controller'] = made[key]
    return {'interpolator': interp, 'controller': made[key], 'priority': priority, 'node': nif.string(name),
            'property': nif.string(kind), 'controller_type': nif.string(ctype), 'controller_id': nif.string(str(variable)),
            'interpolator_id': NONE, 'shape': (name, at['shapes'][name][0])}


def _target(nif, fnv_type: str, found: tuple, name: str, at: dict) -> 'tuple | None':
    """(shape name, shader index, shader type, FO4 controller type, variable) that FNV channel `found` of
    controller type `fnv_type` on shape `name` drives among `at['shapes']`; None when the shape is not converted
    or FO4 leaves the channel out (emittance on a blended unlit shape)."""
    shapes = at['shapes']
    if fnv_type in EMISSIVE and name + GLOW_SUFFIX in shapes:
        name += GLOW_SUFFIX
    if name not in shapes:
        return None
    value_kind, effect_var, lit_var = found
    _, shader, shader_kind, alpha = shapes[name]
    if fnv_type == EMITTANCE and blended_unlit(nif, alpha, name, shader_kind):
        return None
    kind = f'BS{shader_kind}ShaderProperty'
    return name, shader, kind, f'{kind}{value_kind}Controller', effect_var if shader_kind == 'Effect' else lit_var


def _emittance_keys(nif, fnv_type: str, interp: int, name: str, at: dict) -> None:
    """Rank emittance keys (`interp`, shape `name`) into vanilla's glow range."""
    if fnv_type == EMITTANCE:
        neon = name.endswith(GLOW_SUFFIX)
        map_keys(nif, interp, 'neon' if neon else 'lit', 1.0 if neon else at['peaks'].get(name, 1.0))


def blended_unlit(nif, alpha: int, name: str, shader_kind: str) -> bool:
    """Whether shape `name` (alpha `alpha`) is unlit, not a glow overlay, and blends.

    See: docs/fork/fo4_look.md#emissive
    """
    if shader_kind != 'Effect' or name.endswith(GLOW_SUFFIX) or alpha < 0:
        return False
    return bool(nif.blocks[alpha][1]['alpha_flags'] & ALPHA_BLEND)


def timing(controller) -> dict:
    """A NiTimeController's flags, frequency, phase, start and stop."""
    return {'flags': controller.flags, 'frequency': controller.frequency, 'phase': controller.phase,
            'start': controller.start_time, 'stop': controller.stop_time}


def idle_blend(nif, kind: str) -> int:
    """Append a controller's own NiBlend{kind}Interpolator (Float, Point3, Bool), idle until a sequence plays,
    as vanilla's; its index."""
    value = {'Point3': (UNSET,) * 3, 'Float': (UNSET,), 'Bool': BOOL_UNSET}[kind]
    nif.blocks.append((f'NiBlend{kind}Interpolator', {'flags': MANAGER_CONTROLLED, 'size': BLEND_SIZE,
                                                      'threshold': 0.0, 'value': value}))
    return len(nif.blocks) - 1


def interpolator(nif, interp) -> int:
    """Append an FNV interpolator (float, point, bool, or a controller's blend) and its key data; its index (-1
    for none)."""
    kind = type(interp).__name__
    if interp is None:
        return NONE
    if kind.startswith('NiBlend'):
        return idle_blend(nif, kind[len('NiBlend'):-len('Interpolator')])
    if kind in ('NiBoolInterpolator', 'NiBoolTimelineInterpolator'):
        index = len(nif.blocks)
        nif.blocks.append((kind, {'value': int(interp.bool_value), 'data': index + 1 if interp.data else NONE}))
        if interp.data:
            group = interp.data.data
            nif.blocks.append(('NiBoolData', {'kind': group.interpolation if group.num_keys else 0,
                                              'keys': [(k.time, int(k.value)) for k in group.keys]}))
        return index
    if kind not in INTERPOLATORS:
        return NONE
    if kind in SPLINES:
        return spline(nif, interp)
    kind, data_kind, width = INTERPOLATORS[kind]
    index = len(nif.blocks)
    point = interp.point_3_value if width == 3 else None
    value = interp.float_value if width == 1 else (point.x, point.y, point.z)
    nif.blocks.append((kind, {'value': value, 'data': index + 1 if interp.data is not None else NONE}))
    if interp.data is not None:
        nif.blocks.append((data_kind, {'keys': key_group(interp.data.data, width)}))
    return index


def spline(nif, interp) -> int:
    """Append FNV compressed B-spline float or point channel `interp` as FO4's plain interpolator with linear keys
    sampled at SPLINE_FPS over its span (its value alone when it has no control points); its index."""
    kind, data_kind, width = INTERPOLATORS[type(interp).__name__]
    floats = [float(f) for f in interp.unknown_floats]
    handle = struct.unpack('<I', struct.pack('<f', floats[width]))[0]
    offset, half_range = floats[width + 1:width + 3]
    index = len(nif.blocks)
    if handle == NO_HANDLE:
        nif.blocks.append((kind, {'value': floats[0] if width == 1 else tuple(floats[:3]), 'data': NONE}))
        return index
    count = interp.basis_data.num_control_points
    points = np.array(list(interp.spline_data.get_comp_data(handle, count, width, offset, half_range)))
    start, stop = float(interp.start_time), float(interp.stop_time)
    times = np.linspace(start, stop, max(2, round((stop - start) * SPLINE_FPS) + 1))
    values = eval_bspline(points, (times - start) / max(stop - start, 1e-9) * (count - SPLINE_DEGREE)) \
        if count > SPLINE_DEGREE else np.repeat(points[:1], len(times), axis=0)
    nif.blocks.append((kind, {'value': UNSET if width == 1 else (UNSET,) * 3, 'data': index + 1}))
    nif.blocks.append((data_kind, {'keys': {'kind': LINEAR, 'keys': [
        (float(t), *map(float, v)) for t, v in zip(times, values)]}}))
    return index


def key_group(group, width: int) -> dict:
    """An FNV KeyGroup's interpolation and flat float keys (time, value, tangents or TBC)."""
    kind = group.interpolation if group.num_keys else 0
    out = []
    for k in group.keys:
        values = (k.value.x, k.value.y, k.value.z) if width == 3 else (k.value,)
        extra = ()
        if kind == 2:
            extra = ((k.forward.x, k.forward.y, k.forward.z, k.backward.x, k.backward.y, k.backward.z) if width == 3
                     else (k.forward, k.backward))
        elif kind == 3:
            extra = (k.tbc.t, k.tbc.b, k.tbc.c)
        out.append((k.time, *values, *extra))
    return {'kind': kind, 'keys': out}
