"""An FNV creature's body on a Fallout 4 creature's skeleton (FNV's mesh, FO4's animations).

FNV builds its creatures on `Bip01` biped rigs; FO4 names its own bones,
so a mesh moves across by position, as an outfit does (outfit.py): the
creature's parts (its NIFZ list) are converted as statics (convert_static),
each vertex is moved from FNV's skeleton onto the FO4 creature's (the
pair's `Rig`, retarget.py), then takes the weights of the FO4 creature's
own body at its nearest surface point, on its bones and bind data. A rigid
part (eyes) moves with its parent node. Shapes are BSSubIndexTriShapes with
one segment, as vanilla Dogmeat.nif's (an empty one, then every triangle);
FNV's dismemberment caps are left out.

See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.face.bake import surface
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE, SHADER_SKINNED, Reader, pack_tri_shape, read_tri_shape
from fo4_import.nif.convert_static import Converted, NifFormat
from fo4_import.nif.headgear import shape_arrays
from fo4_import.nif.outfit import (BodyFit, bone_data, copy_material, copy_skeleton, fnv_nif, fnv_skeleton, fnv_skin,
                                   fo4_joints, is_cap, originals, segments, shape_bones, skin_blocks, skinned_shape)
from fo4_import.nif.retarget import Rig, bone_moves, retargeted

_DOG_BONES = {'Bip01 Pelvis': 'Dogmeat_Pelvis', 'Bip01 Spine2': 'Dogmeat_Spine3', 'Bip01 Neck': 'Dogmeat_Neck1',
              'Bip01 Neck1': 'Dogmeat_Neck2', 'Bip01 Head': 'Dogmeat_Head',
              'Bip01 Spine0 Tail': 'Dogmeat_Tail1', 'Bip01 Spine0 Tail4': 'Dogmeat_Tail5'}
_DOG_ENDS = {'Bip01 Pelvis': 'Bip01 Spine2', 'Bip01 Spine2': 'Bip01 Neck', 'Bip01 Neck': 'Bip01 Neck1',
             'Bip01 Neck1': 'Bip01 Head', 'Bip01 Spine0 Tail': 'Bip01 Spine0 Tail4'}
_DOG_FOLLOW = {'Bip01 Spine': 'Bip01 Pelvis', 'Bip01 Spine1': 'Bip01 Pelvis', 'Bip01 Spine3': 'Bip01 Spine2',
               'Bip01 Neck2': 'Bip01 Neck1', 'Bip01 Head': 'Bip01 Neck1'}
for _side in 'LR':
    _DOG_BONES.update({f'Bip01 {_side} Clavicle': f'Dogmeat_Front_{_side}LegCollarbone',
                       f'Bip01 {_side} UpperArm': f'Dogmeat_Front_{_side}Leg1',
                       f'Bip01 {_side} Forearm': f'Dogmeat_Front_{_side}Leg2',
                       f'Bip01 {_side} Hand': f'Dogmeat_Front_{_side}LegAnkle',
                       f'Bip01 {_side} Finger0': f'Dogmeat_Front_{_side}LegToe1',
                       f'Bip01 {_side} Thigh': f'Dogmeat_Rear_{_side}Leg1',
                       f'Bip01 {_side} Calf': f'Dogmeat_Rear_{_side}Leg2',
                       f'Bip01 {_side} Foot': f'Dogmeat_Rear_{_side}LegAnkle',
                       f'Bip01 {_side} Toe0': f'Dogmeat_Rear_{_side}LegToe1'})
    for _a, _b in (('Clavicle', 'UpperArm'), ('UpperArm', 'Forearm'), ('Forearm', 'Hand'), ('Hand', 'Finger0'),
                   ('Thigh', 'Calf'), ('Calf', 'Foot'), ('Foot', 'Toe0')):
        _DOG_ENDS[f'Bip01 {_side} {_a}'] = f'Bip01 {_side} {_b}'
#: FNV's dog rig (creatures\\dog) on FO4's Dogmeat skeleton.
DOG = Rig(_DOG_BONES, _DOG_ENDS, _DOG_FOLLOW, 'Bip01 Pelvis')


@dataclass(frozen=True)
class Pair:
    """An FNV creature skeleton folder's FO4 counterpart: the rig, FO4's body and skeleton NIFs (in the archives)."""
    rig: Rig
    body: str
    skeleton: str


#: FNV creature skeleton folder (under meshes) -> its FO4 counterpart.
PAIRS = {'creatures\\dog': Pair(DOG, 'meshes\\actors\\dogmeat\\characterassets\\dogmeat.nif',
                                'meshes\\actors\\dogmeat\\characterassets\\skeleton.nif')}


def creature_fit(export_dir: Path, folder: str, archives: Archives) -> BodyFit:
    """The fit of FNV creature skeleton folder `folder` onto its FO4 pair: bone moves, and FO4's body (every
    shape's surface, weights on one bone list, bind data) to weight from."""
    pair = PAIRS[folder]
    body = nif_file.read(archives.read(pair.body))
    bones, nodes, bind, parts = [], [], [], []
    for kind, raw in body.blocks:
        if kind != 'BSSubIndexTriShape':
            continue
        shape = read_tri_shape(Reader(raw))
        shape_nodes, data = shape_bones(body, shape)
        for node, b in zip(shape_nodes, bone_data(body.blocks[data][1])):
            if node not in nodes:
                nodes.append(node)
                bones.append(body.strings[body.blocks[node][1]['name']])
                bind.append(b)
        parts.append((shape, [nodes.index(n) for n in shape_nodes]))
    points, tris, weights = _merged(parts, len(bones))
    skeleton = fo4_joints(nif_file.read(archives.read(pair.skeleton)))
    moves = bone_moves(pair.rig, *fnv_skeleton(export_dir / 'meshes' / folder / 'skeleton.nif'), skeleton)
    return BodyFit(moves, np.zeros((0, 3)), np.zeros((0, 3)), body, bones, nodes, bind, weights,
                   surface(points, tris), tris, NONE)


def _merged(parts: list, n_bones: int) -> tuple:
    """(positions, triangles, weights on the merged bone list) of FO4 body shapes [(shape, merged bone index per
    shape bone)]."""
    points, tris, weights, start = [], [], [], 0
    for shape, index in parts:
        w = np.zeros((len(shape['vertices']), n_bones))
        for i, v in enumerate(shape['vertices']):
            for share, b in zip(v['weights'], v['bones']):
                w[i, index[b]] += share
        points.append(np.array([v['position'] for v in shape['vertices']], float))
        tris.append(np.array(shape['triangles']) + start)
        weights.append(w)
        start += len(shape['vertices'])
    return np.vstack(points), np.vstack(tris), np.vstack(weights)


def _fnv_part(geom, root, skeleton: dict) -> tuple:
    """outfit.fnv_skin() of an FNV part shape in skeleton space. A rigid one is weighted fully to its nearest
    ancestor the skeleton names, which FNV puts in place of the skeleton's node: its own local transform under
    that node's parent (`skeleton`: {name: parent's world matrix})."""
    if geom.skin_instance:
        return fnv_skin(geom, root)
    anchor = _anchor(geom, root, skeleton)
    name = anchor.name.decode('cp1252')
    pos, nrm, weights, uv = fnv_skin(geom, anchor, name)
    m = np.array(anchor.get_transform().as_list()) @ skeleton[name]
    return (np.hstack([pos, np.ones((len(pos), 1))]) @ m)[:, :3], nrm @ m[:3, :3], weights, uv


def _anchor(geom, root, skeleton: dict):
    """The nearest ancestor node of `geom` under `root` whose name `skeleton` holds (the root at last)."""
    parents = {id(c): n for n in root.tree() if isinstance(n, NifFormat.NiNode) for c in n.children if c is not None}
    node = parents.get(id(geom), root)
    while node is not root and node.name.decode('cp1252') not in skeleton:
        node = parents.get(id(node), root)
    return node


def skeleton_parents(path: Path) -> dict:
    """{node name: its parent's world matrix (pyffi's row-vector form)} of the FNV skeleton NIF at `path`."""
    skeleton = fnv_nif(path)
    out = {skeleton.name.decode('cp1252'): np.eye(4)}
    for node in skeleton.tree():
        if isinstance(node, NifFormat.NiNode):
            world = np.array(node.get_transform(skeleton).as_list())
            out.update({c.name.decode('cp1252'): world for c in node.children if isinstance(c, NifFormat.NiNode)})
    return out


def creature_mesh(parts: list, fit: BodyFit, root_bone: str, skeleton: dict) -> Converted:
    """One FO4 creature body from converted FNV parts [(Converted static, FNV NIF path)] on `fit`'s skeleton
    (`skeleton`: skeleton_parents(), placing rigid parts); its materials and textures are the parts'."""
    nif = nif_file.NifFile()
    nif.blocks.append(('NiNode', {'name': nif.string('BASE'), 'extra': [], 'controller': NONE, 'flags': 0xE,
                                  'translation': (0.0, 0.0, 0.0), 'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
                                  'scale': 1.0, 'collision': NONE, 'children': []}))
    nodes, out = copy_skeleton(nif, fit), Converted(nif)
    for converted, path in parts:
        for name, value in (('materials', converted.materials), ('effects', converted.effects),
                            ('spec_maps', converted.spec_maps)):
            getattr(out, name).update(value)
        out.textures |= converted.textures
        _add_part(nif, converted.nif, fnv_nif(path), (fit, nodes, root_bone, skeleton))
    return out


def _add_part(nif, static, fnv_root, fitting: tuple) -> None:
    """Append static mesh `static`'s shapes (of FNV part `fnv_root`) moved and skinned by `fitting` (fit, copied
    skeleton nodes, FNV root bone, FNV skeleton nodes)."""
    fit, nodes, root_bone, skeleton = fitting
    fnv = {g.name.decode('cp1252'): g for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    for shape in [static.blocks[i][1] for i in static.blocks[0][1]['children'] if static.blocks[i][0] == 'BSTriShape']:
        geom = fnv.get(static.strings[shape['name']])
        if geom is None or is_cap(geom):
            continue
        pos, uv, nrm, tris = shape_arrays(shape)
        own = fnv_skin(geom, fnv_root, 'rigid')
        fnv_pos, fnv_nrm, fnv_weights, _ = _fnv_part(geom, fnv_root, skeleton)
        near = originals((pos, uv, nrm), (own[0], own[3], own[1]))
        points, normals = retargeted(fit.moves, root_bone, fnv_pos[near], fnv_nrm[near], [fnv_weights[i] for i in near])
        made = skinned_shape((points, normals, uv), tris, fit.skin(points), [0, len(tris)])
        index = len(nif.blocks)
        nif.blocks.append(None)
        shader, alpha = copy_material(nif, static, shape)
        nif.blocks[shader][1]['flags1'] |= SHADER_SKINNED
        skin = skin_blocks(nif, fit, nodes, made.used, made.points, made.local, made.weights)
        fields = dict(shape, **made.fields, name=nif.string(static.strings[shape['name']]), shader=shader,
                      alpha_property=alpha, skin=skin)
        nif.blocks[index] = ('BSSubIndexTriShape', pack_tri_shape(fields) + segments(made.counts))
        nif.blocks[0][1]['children'].append(index)
