"""The Fallout 4 animation blocks of a mesh (a door's or container's Open and Close), as dicts.

Layouts from NifSkope's nif.xml at 20.2.0.7: NiControllerManager,
NiMultiTargetTransformController, NiControllerSequence (its controlled
blocks by string; anim note arrays as BS stream > 28), NiTransformInterpolator,
NiTransformData (key groups by interpolation type: linear, quadratic with
tangents, TBC), NiTextKeyExtraData, NiDefaultAVObjectPalette. FNV (stream 34)
and Fallout 4 (130) share them all, so FNV's blocks carry over with their
strings and references renumbered. Strings and references are indices, as in
blocks.

See: docs/fork/fo4_spikes.md#spike-4-animations
"""

import struct

from fo4_import.nif.blocks import Reader, pack_refs, pack_sized

#: Key interpolation types (nif.xml KeyType) with extra per-key values: quadratic (tangents), TBC.
QUADRATIC, TBC, XYZ_ROTATION = 2, 3, 4
#: NiTimeController after NiObject: next controller, flags, frequency, phase, start and stop time, target.
_CONTROLLER = 'iHffffi'


def _controller(r: Reader) -> dict:
    """NiTimeController's fields."""
    keys = ('next', 'flags', 'frequency', 'phase', 'start', 'stop', 'target')
    return dict(zip(keys, r.take(_CONTROLLER)))


def _pack_controller(b: dict) -> bytes:
    """NiTimeController's bytes."""
    return struct.pack('<' + _CONTROLLER, b['next'], b['flags'], b['frequency'], b['phase'], b['start'], b['stop'],
                       b['target'])


def read_manager(r: Reader) -> dict:
    """NiControllerManager: controller, cumulative, sequences, object palette."""
    out = _controller(r)
    out['cumulative'], out['sequences'], out['palette'] = r.take('B'), r.refs(), r.take('i')
    return out


def pack_manager(b: dict) -> bytes:
    """NiControllerManager's bytes."""
    return _pack_controller(b) + struct.pack('<B', b['cumulative']) + pack_refs(b['sequences']) + struct.pack(
        '<i', b['palette'])


def read_multi_target(r: Reader) -> dict:
    """NiMultiTargetTransformController: controller, extra targets (u16 count)."""
    out = _controller(r)
    out['targets'] = _short_refs(r)
    return out


def _short_refs(r: Reader) -> list:
    """A u16 count, then that many i32 references."""
    n = r.take('H')
    return [r.take('i') for _ in range(n)]


def pack_multi_target(b: dict) -> bytes:
    """NiMultiTargetTransformController's bytes."""
    return _pack_controller(b) + struct.pack(f'<H{len(b["targets"])}i', len(b['targets']), *b['targets'])


#: ControlledBlock at 20.2.0.7: interpolator, controller, priority, then five strings (_BLOCK_KEYS).
_BLOCK = 'iiBiiiii'
_BLOCK_KEYS = ('interpolator', 'controller', 'priority', 'node', 'property', 'controller_type', 'controller_id',
               'interpolator_id')
#: NiControllerSequence's fields after its controlled blocks.
_SEQUENCE_KEYS = ('weight', 'text_keys', 'cycle', 'frequency', 'start', 'stop', 'manager', 'accum_root')


def read_sequence(r: Reader) -> dict:
    """NiControllerSequence: name, controlled blocks, weight, text keys, cycle, timing, manager, accum root, notes."""
    out = {'name': r.take('i')}
    count, out['grow_by'] = r.take('I'), r.take('I')
    out['blocks'] = [dict(zip(_BLOCK_KEYS, r.take(_BLOCK))) for _ in range(count)]
    out.update(zip(_SEQUENCE_KEYS, r.take('fiIfffii')))
    out['notes'] = _short_refs(r)
    return out


def pack_sequence(b: dict) -> bytes:
    """NiControllerSequence's bytes."""
    out = struct.pack('<iII', b['name'], len(b['blocks']), b['grow_by'])
    out += b''.join(struct.pack('<' + _BLOCK, *(c[k] for k in _BLOCK_KEYS)) for c in b['blocks'])
    out += struct.pack('<fiIfffii', *(b[k] for k in _SEQUENCE_KEYS))
    return out + struct.pack(f'<H{len(b["notes"])}i', len(b['notes']), *b['notes'])


def read_transform_interpolator(r: Reader) -> dict:
    """NiTransformInterpolator: translation, rotation (w, x, y, z), scale, data."""
    return {'translation': r.take('3f'), 'rotation': r.take('4f'), 'scale': r.take('f'), 'data': r.take('i')}


def pack_transform_interpolator(b: dict) -> bytes:
    """NiTransformInterpolator's bytes."""
    return struct.pack('<3f4ffi', *b['translation'], *b['rotation'], b['scale'], b['data'])


def _key_size(width: int, kind: int) -> int:
    """Floats per key of `width` values: time, value, tangents (quadratic) or TBC."""
    return 1 + width + (2 * width if kind == QUADRATIC else 3 if kind == TBC else 0)


def _read_group(r: Reader, width: int) -> dict:
    """A KeyGroup of `width`-float values: interpolation and keys (flat float tuples)."""
    n = r.take('I')
    kind = r.take('I') if n else 0
    size = _key_size(width, kind)
    return {'kind': kind, 'keys': [r.take(f'{size}f') if size > 1 else (r.take('f'),) for _ in range(n)]}


def _pack_group(g: dict) -> bytes:
    """A KeyGroup's bytes."""
    out = struct.pack('<I', len(g['keys'])) + (struct.pack('<I', g['kind']) if g['keys'] else b'')
    return out + b''.join(struct.pack(f'<{len(k)}f', *k) for k in g['keys'])


def read_transform_data(r: Reader) -> dict:
    """NiTransformData: rotation keys (quaternion, or XYZ key groups), translation and scale key groups."""
    out = {'rotation_count': r.take('I'), 'rotation_kind': 0, 'rotations': [], 'xyz': []}
    if out['rotation_count']:
        out['rotation_kind'] = r.take('I')
        if out['rotation_kind'] == XYZ_ROTATION:
            out['xyz'] = [_read_group(r, 1) for _ in range(3)]
        else:
            size = 5 + (3 if out['rotation_kind'] == TBC else 0)
            out['rotations'] = [r.take(f'{size}f') for _ in range(out['rotation_count'])]
    out['translations'], out['scales'] = _read_group(r, 3), _read_group(r, 1)
    return out


def pack_transform_data(b: dict) -> bytes:
    """NiTransformData's bytes."""
    out = struct.pack('<I', b['rotation_count'])
    if b['rotation_count']:
        out += struct.pack('<I', b['rotation_kind'])
        out += b''.join(_pack_group(g) for g in b['xyz']) if b['rotation_kind'] == XYZ_ROTATION else b''.join(
            struct.pack(f'<{len(k)}f', *k) for k in b['rotations'])
    return out + _pack_group(b['translations']) + _pack_group(b['scales'])


def read_text_keys(r: Reader) -> dict:
    """NiTextKeyExtraData: name, keys (time, string)."""
    name, n = r.take('i'), r.take('I')
    return {'name': name, 'keys': [r.take('fi') for _ in range(n)]}


def pack_text_keys(b: dict) -> bytes:
    """NiTextKeyExtraData's bytes."""
    return struct.pack('<iI', b['name'], len(b['keys'])) + b''.join(struct.pack('<fi', *k) for k in b['keys'])


def read_palette(r: Reader) -> dict:
    """NiDefaultAVObjectPalette: scene, objects (name, block)."""
    scene, n = r.take('i'), r.take('I')
    return {'scene': scene, 'objects': [(r.sized(), r.take('i')) for _ in range(n)]}


def pack_palette(b: dict) -> bytes:
    """NiDefaultAVObjectPalette's bytes."""
    out = struct.pack('<iI', b['scene'], len(b['objects']))
    return out + b''.join(pack_sized(name) + struct.pack('<i', ref) for name, ref in b['objects'])


#: Block type -> (reader, packer).
ANIM_BLOCKS = {
    'NiControllerManager': (read_manager, pack_manager),
    'NiMultiTargetTransformController': (read_multi_target, pack_multi_target),
    'NiControllerSequence': (read_sequence, pack_sequence),
    'NiTransformInterpolator': (read_transform_interpolator, pack_transform_interpolator),
    'NiTransformData': (read_transform_data, pack_transform_data),
    'NiTextKeyExtraData': (read_text_keys, pack_text_keys),
    'NiDefaultAVObjectPalette': (read_palette, pack_palette),
}
