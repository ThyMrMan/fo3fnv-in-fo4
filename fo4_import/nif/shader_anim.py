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
#: A controller's own blend interpolator, idle until a sequence plays, as vanilla's: manager-controlled flag,
#: array size 2, value unset (-FLT_MAX).
MANAGER_CONTROLLED, BLEND_SIZE, UNSET = 1, 2, -3.4028234663852886e38
#: A bool interpolator's unset value (vanilla's controller-owned NiBoolInterpolators hold 2).
BOOL_UNSET = 2
#: FNV interpolator -> (FO4 interpolator, its data, values per key).
INTERPOLATORS = {'NiFloatInterpolator': ('NiFloatInterpolator', 'NiFloatData', 1),
                 'NiPoint3Interpolator': ('NiPoint3Interpolator', 'NiPosData', 3)}


def channel(cb) -> 'tuple | None':
    """CHANNELS' entry of an FNV controlled block, or None when FO4 has no shader equivalent."""
    ctype = cb.controller_type.decode('cp1252')
    found = CHANNELS.get((ctype, cb.variable_1.decode('cp1252').rsplit('-', 1)[-1])) or CHANNELS.get((ctype, ''))
    return found if found and type(cb.interpolator).__name__ in INTERPOLATORS else None


def shapes_by_name(nif) -> dict:
    """{name: (BSTriShape index, shader index, 'Effect' or 'Lighting')} of a converted mesh's shapes."""
    out = {}
    for i, (kind, block) in enumerate(nif.blocks):
        if kind == 'BSTriShape' and block['shader'] >= 0:
            shader = 'Effect' if nif.blocks[block['shader']][0] == 'BSEffectShaderProperty' else 'Lighting'
            out.setdefault(nif.strings[block['name']], (i, block['shader'], shader))
    return out


def shader_block(nif, cb, timing: dict, at: dict, priority: int) -> 'dict | None':
    """The FO4 controlled block (with its controller and interpolator appended) of FNV shader channel `cb`;
    None when unsupported or its shape is not converted. `at` holds the converted `shapes` (shapes_by_name),
    `made` (controllers per shape and variable) and unlit shapes' texel `peaks`."""
    shapes, made = at['shapes'], at['made']
    found = channel(cb)
    name = cb.node_name.decode('cp1252')
    if found and cb.controller_type.decode('cp1252') in EMISSIVE and name + GLOW_SUFFIX in shapes:
        name += GLOW_SUFFIX
    if not found or name not in shapes:
        return None
    value_kind, effect_var, lit_var = found
    shape, shader, shader_kind = shapes[name]
    if cb.controller_type.decode('cp1252') == EMITTANCE and blended_unlit(nif, shape, name, shader_kind):
        return None
    variable = effect_var if shader_kind == 'Effect' else lit_var
    ctype = f'BS{shader_kind}ShaderProperty{value_kind}Controller'
    interp = interpolator(nif, cb.interpolator)
    if cb.controller_type.decode('cp1252') == EMITTANCE:
        neon = name.endswith(GLOW_SUFFIX)
        map_keys(nif, interp, 'neon' if neon else 'lit', 1.0 if neon else at['peaks'].get(name, 1.0))
    key = (shader, ctype, variable)
    if key not in made:
        blend = idle_blend(nif, 'Point3' if value_kind == 'Color' else 'Float')
        made[key] = len(nif.blocks)
        nif.blocks.append((ctype, {**timing, 'next': nif.blocks[shader][1]['controller'], 'target': shader,
                                   'interpolator': blend, 'variable': variable}))
        nif.blocks[shader][1]['controller'] = made[key]
    return {'interpolator': interp, 'controller': made[key], 'priority': priority, 'node': nif.string(name),
            'property': nif.string(f'BS{shader_kind}ShaderProperty'), 'controller_type': nif.string(ctype),
            'controller_id': nif.string(str(variable)), 'interpolator_id': NONE, 'shape': (name, shape)}


def blended_unlit(nif, shape: int, name: str, shader_kind: str) -> bool:
    """Whether converted shape `shape` is unlit (not a glow overlay) and alpha-blends: FNV clips its emissive
    colour before blending, so its emittance multiplier must not light the faint texels.

    See: docs/fork/fo4_look.md#emissive
    """
    alpha = nif.blocks[shape][1]['alpha_property']
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
    kind, data_kind, width = INTERPOLATORS[kind]
    index = len(nif.blocks)
    point = interp.point_3_value if width == 3 else None
    value = interp.float_value if width == 1 else (point.x, point.y, point.z)
    nif.blocks.append((kind, {'value': value, 'data': index + 1 if interp.data is not None else NONE}))
    if interp.data is not None:
        nif.blocks.append((data_kind, {'keys': key_group(interp.data.data, width)}))
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
