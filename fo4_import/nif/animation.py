"""An FNV mesh's embedded animation (a door's or container's Open and Close) as Fallout 4 blocks.

FNV and Fallout 4 animate doors and containers alike: a NiControllerManager
on the root (201 of vanilla's 227 door meshes, 94 of 119 container ones)
whose NiControllerSequences drive named nodes through a
NiMultiTargetTransformController, NiTransformInterpolators and their key
data, with text keys and an object palette. The nodes a sequence names, and
those between them and the root, are kept with their own transforms (the
static conversion flattens every other); the controller blocks carry over
with strings and references renumbered (layouts in anim_blocks). Empty
controlled-block strings are -1 and a text key list's name is '', as vanilla's.
A skinned shape (a flag) keeps its bones as nodes and its skin, as a
BSSkin::Instance and BoneData (vanilla FlagWavingMinutemen01.nif).

See: docs/fork/fo4_spikes.md#spike-4-animations
"""

import struct

import numpy as np

from fo4_import.nif.blocks import DESC_SKINNED, DESC_SKINNED_COLOR, NONE, SHADER_SKINNED
from fo4_import.nif.file import NifFile
from fo4_import.nif.fnv_file import parent_map
from fo4_import.nif.particles import drives_particles, particle_block
from fo4_import.nif.shader_anim import channel, key_group, shader_block, shapes_by_name, timing

#: Bones a BSTriShape vertex is weighted to.
VERTEX_BONES = 4


def manager_of(root):
    """The FNV root's NiControllerManager, or None."""
    controller = root.controller
    return controller if controller is not None and type(controller).__name__ == 'NiControllerManager' else None


def moves(cb) -> bool:
    """Whether an FNV controlled block moves a node (a NiTransformInterpolator)."""
    return type(cb.interpolator).__name__ == 'NiTransformInterpolator'


def animatable(manager) -> bool:
    """Whether a sequence moves a node, animates a shader or drives particles.

    See: docs/fork/fo4_pipeline.md#effect-animation
    """
    return any(moves(cb) or channel(cb) or drives_particles(cb)
               for seq in manager.controller_sequences for cb in seq.controlled_blocks)


def skin_bones(root) -> set:
    """Names of the bones the skinned shapes under FNV `root` are weighted to."""
    return {bone.name for g in root.tree() if getattr(g, 'skin_instance', None) is not None
            for bone in g.skin_instance.bones if bone is not None}


def kept_nodes(root, manager) -> list:
    """with_parents() of the nodes a sequence names or a skin is weighted to."""
    named = {cb.node_name for seq in manager.controller_sequences for cb in seq.controlled_blocks} | skin_bones(root)
    return with_parents(root, lambda node: node.name in named)


def with_parents(root, wanted) -> list:
    """The FNV nodes under `root` for which `wanted(node)` holds, and those between each and `root`, parents first."""
    parents = parent_map(root)
    out = []
    for node in root.tree():
        if hasattr(node, 'children') and node is not root and wanted(node):
            chain, current = [], node
            while current is not None and current is not root:
                chain.append(current)
                current = parents.get(id(current))
            out += [n for n in reversed(chain) if n not in out]
    return out


def add_nodes(nif: NifFile, kept: list, root, flags: int) -> dict:
    """FO4 NiNodes for `kept` (parents first), each under its parent's; {id(FNV node): FO4 index}, root 0.
    A rotation is written in the file's order (pyffi's matrix transposed)."""
    index = {id(root): 0}
    for node in kept:
        parent = next(p for p in root.tree() if hasattr(p, 'children') and node in p.children)
        index[id(node)] = len(nif.blocks)
        nif.blocks.append(('NiNode', {
            'name': nif.string(node.name.decode('cp1252')), 'extra': [], 'controller': NONE, 'flags': flags,
            'translation': (node.translation.x, node.translation.y, node.translation.z),
            'rotation': tuple(v for column in zip(*node.rotation.as_list()) for v in column), 'scale': node.scale,
            'collision': NONE, 'children': []}))
        nif.blocks[index[id(parent)]][1]['children'].append(index[id(node)])
    return index


def controllers(nif: NifFile, root, manager, nodes: dict, particles: dict, peaks: dict = None) -> int:
    """Append FNV `manager`'s blocks (sequences, interpolators, data, text keys, palette) for the kept `nodes`
    and converted `particles` controllers ({id(FNV): FO4}), unlit shapes' texel `peaks` (convert_static.texel_peaks)
    scaling their emittance; the FO4 manager's index, set as the root's controller."""
    base = len(nif.blocks)
    multi = _multi_target(manager)
    at = {'manager': base, 'multi': base + 1, 'shapes': shapes_by_name(nif), 'made': {}, 'animated': {},
          'particles': particles, 'peaks': peaks or {}}
    nif.blocks += [('NiControllerManager', {}), ('NiMultiTargetTransformController', {})]
    seq_index = [_sequence(nif, seq, at, root) for seq in manager.controller_sequences]
    palette = len(nif.blocks)
    nif.blocks.append(('NiDefaultAVObjectPalette', {
        'scene': 0, 'objects': [(o.name.decode('cp1252'), nodes.get(id(o.av_object), NONE))
                                for o in manager.object_palette.objs if id(o.av_object) in nodes]
        + sorted(at['animated'].items())}))
    nif.blocks[at['manager']] = ('NiControllerManager', {
        **timing(manager), 'next': at['multi'], 'target': 0, 'cumulative': int(manager.cumulative),
        'sequences': seq_index, 'palette': palette})
    nif.blocks[at['multi']] = ('NiMultiTargetTransformController', {
        **(timing(multi) if multi else timing(manager)), 'next': NONE, 'target': 0,
        'targets': [nodes[id(t)] for t in (multi.extra_targets if multi else []) if id(t) in nodes]})
    nif.blocks[0][1]['controller'] = at['manager']
    return at['manager']


def _multi_target(manager):
    """The NiMultiTargetTransformController in the FNV manager's controller chain, or None."""
    controller = manager.next_controller
    while controller is not None and type(controller).__name__ != 'NiMultiTargetTransformController':
        controller = controller.next_controller
    return controller


def _string(nif: NifFile, value: bytes) -> int:
    """The string index of an FNV string field (-1 for empty)."""
    return nif.string(value.decode('cp1252')) if value else NONE


def _sequence(nif: NifFile, seq, at: dict, root) -> int:
    """Append FNV sequence `seq` with its interpolators, data and text keys; its index."""
    index = len(nif.blocks)
    nif.blocks.append(('NiControllerSequence', {}))
    blocks = []
    for cb in seq.controlled_blocks:
        if drives_particles(cb):
            block = particle_block(nif, cb, at['particles'])
            if block:
                at['animated'][cb.node_name.decode('cp1252')] = nif.blocks[block['controller']][1]['target']
                blocks.append(block)
            continue
        if channel(cb):
            when = timing(cb.controller) if cb.controller is not None else timing(seq.manager)
            block = shader_block(nif, cb, when, at, cb.priority)
            if block:
                name, shape = block.pop('shape')
                at['animated'][name] = shape
                blocks.append(block)
            continue
        if cb.interpolator is not None and not moves(cb):
            continue
        blocks.append({'interpolator': _interpolator(nif, cb.interpolator), 'controller': at['multi'],
                       'priority': cb.priority, 'node': _string(nif, cb.node_name),
                       'property': _string(nif, cb.property_type), 'controller_type': _string(nif, cb.controller_type),
                       'controller_id': _string(nif, cb.variable_1),
                       'interpolator_id': _string(nif, cb.variable_2)})
    keys = len(nif.blocks)
    nif.blocks.append(('NiTextKeyExtraData', {'name': nif.empty_string(), 'keys': [
        (k.time, _string(nif, k.value)) for k in seq.text_keys.text_keys]}))
    nif.blocks[index] = ('NiControllerSequence', {
        'name': _string(nif, seq.name), 'grow_by': seq.unknown_int_1, 'blocks': blocks, 'weight': seq.weight,
        'text_keys': keys, 'cycle': seq.cycle_type, 'frequency': seq.frequency, 'start': seq.start_time,
        'stop': seq.stop_time, 'manager': at['manager'],
        'accum_root': _string(nif, seq.target_name or root.name), 'notes': []})
    return index


def _interpolator(nif: NifFile, interp) -> int:
    """Append an FNV NiTransformInterpolator and its NiTransformData; its index (-1 for none)."""
    if interp is None:
        return NONE
    index = len(nif.blocks)
    nif.blocks.append(('NiTransformInterpolator', {
        'translation': (interp.translation.x, interp.translation.y, interp.translation.z),
        'rotation': (interp.rotation.w, interp.rotation.x, interp.rotation.y, interp.rotation.z), 'scale': interp.scale,
        'data': index + 1 if interp.data is not None else NONE}))
    if interp.data is not None:
        nif.blocks.append(('NiTransformData', _data(interp.data)))
    return index


def _data(d) -> dict:
    """NiTransformData's fields from FNV's."""
    kind = d.rotation_type if d.num_rotation_keys else 0
    rotations = [(k.time, k.value.w, k.value.x, k.value.y, k.value.z) + ((k.tbc.t, k.tbc.b, k.tbc.c) if kind == 3
                                                                          else ()) for k in d.quaternion_keys]
    return {'rotation_count': d.num_rotation_keys, 'rotation_kind': kind,
            'rotations': rotations if kind != 4 else [],
            'xyz': [key_group(g, 1) for g in d.xyz_rotations] if kind == 4 else [],
            'translations': key_group(d.translations, 3), 'scales': key_group(d.scales, 1)}


def skin(nif: NifFile, shapes: list, geom, root, nodes: dict) -> None:
    """Skin converted `shapes` (of FNV skinned `geom`, positions in `root` space) to the kept bone `nodes`.

    A bone's transform takes a root-space point to bone space: the shape's
    placement undone, then FNV's skin transform (pyffi's skinning reads it
    so). Each vertex keeps its four heaviest weights, normalized.
    """
    placed = np.array(geom.get_transform(root).as_list())
    pos = (np.array([(v.x, v.y, v.z, 1.0) for v in geom.data.vertices]) @ placed)[:, :3]
    instance = geom.skin_instance
    weights = np.zeros((len(pos), max(len(instance.bones), VERTEX_BONES)))
    for k, bone in enumerate(instance.data.bone_list):
        for vw in bone.vertex_weights:
            weights[vw.index, k] += vw.weight
    to_bone = [np.linalg.inv(placed) @ np.array(bone.get_transform().as_list()) for bone in instance.data.bone_list]
    source = {tuple(map(float, p)): i for i, p in enumerate(pos)}
    bones = [nodes[id(b)] for b in instance.bones]
    for index in shapes:
        _skin_shape(nif, index, weights, source, to_bone, bones)


def _skin_shape(nif: NifFile, index: int, weights: np.ndarray, source: dict, to_bone: list, bones: list) -> None:
    """Weight shape `index` (its vertices found in `source` by position) and append its skin blocks."""
    shape = nif.blocks[index][1]
    w = weights[[source[v['position']] for v in shape['vertices']]]
    top = np.argsort(-w, axis=1)[:, :VERTEX_BONES]
    top_w = np.take_along_axis(w, top, axis=1)
    top_w /= np.maximum(top_w.sum(axis=1, keepdims=True), 1e-9)
    for v, b, x in zip(shape['vertices'], top, top_w):
        v.update(weights=tuple(float(c) for c in x), bones=tuple(int(c) if c < len(bones) else 0 for c in b))
    points = np.array([v['position'] for v in shape['vertices']])
    data = bytearray(struct.pack('<I', len(bones)))
    for k, m in enumerate(to_bone):
        mine = points[(w[:, k] > 0)] if (w[:, k] > 0).any() else points
        mine = np.hstack([mine, np.ones((len(mine), 1))]) @ m
        center = (mine[:, :3].min(0) + mine[:, :3].max(0)) / 2
        radius = float(np.linalg.norm(mine[:, :3] - center, axis=1).max())
        data += struct.pack('<4f9f3ff', *center, radius, *m[:3, :3].T.ravel(), *m[3, :3], 1.0)
    shape['skin'] = len(nif.blocks)
    shape['vertex_desc'] = DESC_SKINNED_COLOR if 'color' in shape['vertices'][0] else DESC_SKINNED
    nif.blocks[shape['shader']][1]['flags1'] |= SHADER_SKINNED
    nif.blocks.append(('BSSkin::Instance', struct.pack(f'<iiI{len(bones)}iI', 0, shape['skin'] + 1, len(bones),
                                                       *bones, 0)))
    nif.blocks.append(('BSSkin::BoneData', bytes(data)))
