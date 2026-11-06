"""An FNV creature's body on a Fallout 4 creature's skeleton (FNV's mesh, FO4's animations).

FNV builds its creatures on `Bip01` biped rigs; FO4 names its own bones,
so a mesh moves across by position, as an outfit does (outfit.py): the
creature's parts (its NIFZ list) are converted as statics (convert_static),
each vertex is moved from FNV's skeleton onto the FO4 creature's (the
pair's `Rig`, retarget.py), then takes the weights of the FO4 creature's
own body at its nearest surface point, on its bones and bind data; a pair
whose FNV body is shaped unlike FO4's (`own_weights`) keeps FNV's own
weights instead, each FNV bone on its rig bone in FO4's body. A rigid part
(eyes) moves with its parent node. Shapes are BSSubIndexTriShapes with
one segment, as vanilla Dogmeat.nif's (an empty one, then every triangle);
FNV's dismemberment caps are left out.

A pair worn over FO4's own body and head (`fo4_body`: super mutants, whose
FNV hands can't take FO4's finger bones, nor its head FO4's neck) keeps
only FNV's armor. The part holding FNV's bare skin (the texture of the
shape with the most finger-weighted vertices: FNV's body, head, eyes and
teeth) drops; elsewhere a triangle with two finger-weighted corners drops.
Each armor vertex then moves, by its share of head weight, from FNV's head
box (the bare skin's head-led vertices) onto FO4's (`head_box`: FO4's
head-led body and its face plate, `Pair.head`), and the armor is pushed
PUSH_MARGIN outside FO4's body along its nearest triangle's normal.

See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.base.ba2 import Archives
from fo4_import.face.bake import surface
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE, SHADER_SKINNED, Reader, pack_tri_shape, read_tri_shape
from fo4_import.nif.convert_static import Converted, NifFormat
from fo4_import.nif.headgear import shape_arrays
from fo4_import.nif.outfit import (FO4_BODIES, FO4_SKELETON, HUMAN, NEIGHBOURS, SMOOTH_PASSES, BodyFit, bone_data, copy_material,
                                   copy_skeleton, fnv_nif, fnv_skeleton, fnv_skin, fo4_frames, is_cap, originals, segments, shape_bones, skin_blocks, skin_shift, skinned_shape, strongest)
from fo4_import.nif.retarget import Rig, bone_moves, retargeted
from fo4_import.pipeline.export_index import export_file

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


#: BOD2 bits of slot 32 (FaceGen head): FNV's body has its own head, so its skin hides the race's (as vanilla's do).
HEAD_SLOT = 0x4
#: BOD2 bits a full hood covers on a human, as vanilla AAArmorHazmatSuitHat's: hair 30-31, head 32, face 46-50.
HOOD_SLOTS = 0x7 | 0x1F << 16


@dataclass(frozen=True)
class Pair:
    """An FNV creature skeleton folder's FO4 counterpart: the rig, FO4's body and skeleton NIFs (in the archives),
    whether its parts keep FNV's weights, the head NIF (its race's default head part) of FO4's body when its body
    and head are worn beneath them (the module notes), the slots (BOD2 bits) FNV's head covers on FO4's race, and
    whether that race is FO4's human, whose own voice speaks words and who holds FNV's creature guns in hand."""
    rig: Rig
    body: str
    skeleton: str
    own_weights: bool = False
    head: str = ''
    head_slots: int = HEAD_SLOT
    human: bool = False

    @property
    def fo4_body(self) -> bool:
        """Whether FO4's body and head are worn beneath FNV's parts."""
        return bool(self.head)


#: FNV creature skeleton folder (under meshes) -> its FO4 counterpart.
PAIRS = {'creatures\\dog': Pair(DOG, 'meshes\\actors\\dogmeat\\characterassets\\dogmeat.nif',
                                'meshes\\actors\\dogmeat\\characterassets\\skeleton.nif'),
         'creatures\\smspinebreaker': Pair(HUMAN, 'meshes\\actors\\supermutant\\characterassets\\supermutantbody.nif',
                                           'meshes\\actors\\supermutant\\characterassets\\skeleton.nif', True,
                                           'meshes\\actors\\supermutant\\characterassets\\supermutanthead.nif'),
         **{folder: Pair(HUMAN, FO4_BODIES['male'], FO4_SKELETON, True, head_slots=HOOD_SLOTS, human=True)
            for folder in ('nvdlc01\\creatures\\ghosts', 'nvdlc01\\creatures\\hologram', 'nvdlc03\\creatures\\hologram')}}
#: FO4 body bone name prefix (lower case) of the head's bones.
HEAD_BONE = 'head'
#: How far (game units) a part's surface is kept outside FO4's body, and the passes that settle it.
PUSH_MARGIN, PUSH_PASSES = 0.5, 3


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
    frames = fo4_frames(nif_file.read(archives.read(pair.skeleton)))
    skeleton = {name: pos for name, (_, pos) in frames.items()}
    shift = skin_shift(bones, bind, skeleton)
    if pair.own_weights:
        _add_rig_bones(body, pair.rig, frames, shift, (bones, nodes, bind))
    points, tris, weights = _merged(parts, len(bones))
    joints, parents = fnv_skeleton(export_file(export_dir, 'meshes', folder, 'skeleton.nif'))
    moves = bone_moves(pair.rig, joints, parents, {name: pos + shift for name, pos in skeleton.items()})
    return BodyFit(moves, np.zeros((0, 3)), np.zeros((0, 3)), body, bones, nodes, bind, weights,
                   surface(points, tris), tris, NONE, points=points,
                   targets=_targets(pair.rig, parents, bones) if pair.own_weights else None,
                   head_box=_fo4_head_box(archives, pair.head, points[head_share(weights, bones) > 0.5]))


def _add_rig_bones(body, rig: Rig, frames: dict, shift: np.ndarray, fit: tuple) -> None:
    """Add each FO4 bone `rig` maps to that body NIF `body` skins neither by name nor as its `_skin` helper (FO4's
    human body has no HEAD) to its nodes and to `fit` (bones, their nodes, bind data), at its skeleton rest frame in
    `frames` moved by `shift`."""
    bones, nodes, bind = fit
    have = {b.lower() for b in bones}
    for name in sorted(n for n in set(rig.bones.values()) if not {n.lower(), n.lower() + '_skin'} & have):
        rot, pos = frames[name]
        at = pos + shift
        body.blocks.append(('NiNode', {'name': body.string(name), 'extra': [], 'controller': NONE, 'flags': 0xE,
                                       'translation': tuple(map(float, at)), 'rotation': tuple(map(float, rot.ravel())),
                                       'scale': 1.0, 'collision': NONE, 'children': []}))
        body.blocks[0][1]['children'].append(len(body.blocks) - 1)
        nodes.append(len(body.blocks) - 1)
        bind.append(((0.0,) * 4, rot.T, -rot.T @ at))
        bones.append(name)


def _fo4_head_box(archives: Archives, head: str, led: np.ndarray) -> 'np.ndarray | None':
    """[min, max] corners of FO4's head: body points `led` by the head and head NIF `head`'s; None without one."""
    if not head:
        return None
    nif = nif_file.read(archives.read(head))
    points = np.vstack([led] + [np.array([v['position'] for v in read_tri_shape(Reader(raw))['vertices']], float)
                                for kind, raw in nif.blocks if kind == 'BSSubIndexTriShape'])
    return np.array([points.min(0), points.max(0)])


def _targets(rig: Rig, parents: dict, bones: list) -> dict:
    """{FNV bone: index in FO4 body `bones`} of its rig bone or its nearest ancestor's, by name or as that bone's
    `_skin` helper."""
    index = {b.lower(): i for i, b in enumerate(bones)}
    out = {}
    for bone in [rig.root, *parents]:
        up = bone
        while up not in rig.bones and up in parents:
            up = parents[up]
        name = rig.bones.get(up, rig.bones[rig.root]).lower()
        out[bone] = index.get(name, index.get(name + '_skin'))
    return out


def _own_dense(targets: dict, root: str, weights: list, n_bones: int) -> np.ndarray:
    """FNV per-vertex weights {bone: share} on their `targets` (`root`'s else), one column per FO4 body bone."""
    dense = np.zeros((len(weights), n_bones))
    for i, w in enumerate(weights):
        for bone, share in (w or {root: 1.0}).items():
            dense[i, targets.get(bone, targets[root])] += share
    return dense


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


def _placed(geom, root, skeleton: dict) -> bool:
    """Whether `geom` is skinned or under a node `skeleton` names."""
    return bool(geom.skin_instance) or _anchor(geom, root, skeleton).name.decode('cp1252') in skeleton


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


def diffuse(geom) -> str:
    """An FNV shape's diffuse texture path (lower case), '' without one."""
    for prop in geom.get_properties():
        textures = getattr(prop, 'texture_set', None)
        if textures is not None and textures.num_textures:
            return textures.textures[0].decode('cp1252').lower()
    return ''


def skin_texture(paths: list) -> str:
    """The diffuse of FNV's bare skin among part NIFs `paths`: the shape's with the most vertices weighted mostly to
    a finger; '' without one, or when every shape shares it (the skin is the armor too)."""
    best, out, seen = 0, '', set()
    for path in paths:
        root = fnv_nif(path)
        for geom in root.tree():
            if isinstance(geom, NifFormat.NiTriBasedGeom) and geom.skin_instance and not is_cap(geom):
                seen.add(diffuse(geom))
                fingers = sum(1 for w in fnv_skin(geom, root)[2] if w and 'Finger' in max(w, key=w.get))
                if fingers > best:
                    best, out = fingers, diffuse(geom)
    return out if seen - {out} else ''


@dataclass
class _Shape:
    """A converted FNV part shape on a fit's skeleton: its static mesh and block, FNV geometry, retargeted points
    and normals, UVs, triangles, FNV per-vertex weights, and weights on FO4's body bones (one column each)."""
    static: object
    shape: dict
    geom: object
    points: np.ndarray
    normals: np.ndarray
    uv: np.ndarray
    tris: np.ndarray
    weights: list
    dense: np.ndarray


def _normals(fit: BodyFit) -> np.ndarray:
    """Unit outward normal of each of FO4's body triangles (fit.points, fit.tris)."""
    corners = fit.points[fit.tris]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return normal / np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)


def pushed(points: np.ndarray, fit: BodyFit) -> np.ndarray:
    """`points` moved out of FO4's body (fit.points, fit.tris, wound outward) to PUSH_MARGIN along the nearest
    triangle's normal, each move first smoothed over the nearest points."""
    normal = _normals(fit)
    samples, owner, _ = fit.samples
    tree = cKDTree(samples)

    def push(at):
        """Each point's move out to PUSH_MARGIN, zero for one already there."""
        _, i = tree.query(at)
        n = normal[owner[i]]
        depth = PUSH_MARGIN - np.einsum('ij,ij->i', at - samples[i], n)
        return np.maximum(depth, 0.0)[:, None] * n
    move = push(points)
    if len(points) > NEIGHBOURS:
        _, near = cKDTree(points).query(points, k=NEIGHBOURS)
        for _ in range(SMOOTH_PASSES):
            move = move[near].mean(1)
    points = points + move
    for _ in range(PUSH_PASSES):
        points = points + push(points)
    return points


def head_share(dense: np.ndarray, bones: list) -> np.ndarray:
    """Each row of `dense` (a column per bone of `bones`): its share on head bones."""
    head = [i for i, b in enumerate(bones) if b.lower().startswith(HEAD_BONE)]
    return dense[:, head].sum(1) / np.maximum(dense.sum(1), 1e-9)


def creature_mesh(parts: list, fit: BodyFit, root_bone: str, skeleton: dict, skin: 'str | None' = None) -> Converted:
    """One FO4 creature body from converted FNV parts [(Converted static, FNV NIF path)] on `fit`'s skeleton
    (`skeleton`: skeleton_parents(), placing rigid parts); its materials and textures are the parts'. With FO4's body
    and head worn beneath, `skin` is FNV's bare skin texture (skin_texture()) and the rest is fitted over them
    (_over_body)."""
    nif = nif_file.NifFile()
    nif.blocks.append(('NiNode', {'name': nif.string('BASE'), 'extra': [], 'controller': NONE, 'flags': 0xE,
                                  'translation': (0.0, 0.0, 0.0), 'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
                                  'scale': 1.0, 'collision': NONE, 'children': []}))
    nodes, out, found = copy_skeleton(nif, fit), Converted(nif), []
    for converted, path in parts:
        for name, value in (('materials', converted.materials), ('effects', converted.effects),
                            ('spec_maps', converted.spec_maps), ('glow_maps', converted.glow_maps)):
            getattr(out, name).update(value)
        out.textures |= converted.textures
        found.append(list(_part_shapes(converted.nif, fnv_nif(path), (fit, root_bone, skeleton))))
    for shape in _over_body(found, fit, skin) if skin is not None else [s for shapes in found for s in shapes]:
        _add_shape(nif, shape, fit, nodes)
    return out


def _part_shapes(static, fnv_root, fitting: tuple):
    """The _Shapes of static mesh `static` (of FNV part `fnv_root`) placed by `fitting` (fit, FNV root bone, FNV
    skeleton nodes)."""
    fit, root_bone, skeleton = fitting
    fnv = {g.name.decode('cp1252'): g for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    for shape in [static.blocks[i][1] for i in static.blocks[0][1]['children'] if static.blocks[i][0] == 'BSTriShape']:
        geom = fnv.get(static.strings[shape['name']])
        if geom is None or is_cap(geom) or not _placed(geom, fnv_root, skeleton):
            continue
        pos, uv, nrm, tris = shape_arrays(shape)
        own = fnv_skin(geom, fnv_root, 'rigid')
        fnv_pos, fnv_nrm, fnv_weights, _ = _fnv_part(geom, fnv_root, skeleton)
        near = originals((pos, uv, nrm), (own[0], own[3], own[1]))
        weights = [fnv_weights[i] for i in near]
        points, normals = retargeted(fit.moves, root_bone, fnv_pos[near], fnv_nrm[near], weights)
        dense = _own_dense(fit.targets, root_bone, weights, len(fit.bones)) if fit.targets else fit.dense(points)
        yield _Shape(static, shape, geom, points, normals, uv, tris, weights, dense)


def _head_box(found: list, fit: BodyFit, skin: str) -> np.ndarray:
    """[min, max] corners of FNV's head: the bare skin `skin`'s vertices led by the head; fit.head_box without."""
    heads = [s.points[head_share(s.dense, fit.bones) > 0.5] for shapes in found for s in shapes
             if diffuse(s.geom) == skin]
    heads = np.vstack(heads) if heads else np.zeros((0, 3))
    return np.array([heads.min(0), heads.max(0)]) if len(heads) else fit.head_box


def _over_body(found: list, fit: BodyFit, skin: str) -> list:
    """The _Shapes of parts `found` [[_Shape]] worn over FO4's body and head (the module notes)."""
    base = {id(shapes) for shapes in found if any(diffuse(s.geom) == skin for s in shapes)}
    fnv_box = _head_box(found, fit, skin)
    scale = (fit.head_box[1] - fit.head_box[0]) / np.maximum(fnv_box[1] - fnv_box[0], 1e-6)
    out = []
    for s in (s for shapes in found if id(shapes) not in base for s in shapes):
        finger = np.array([bool(w) and 'Finger' in max(w, key=w.get) for w in s.weights])
        tris = s.tris[finger[s.tris].sum(1) < 2]
        if not len(tris):
            continue
        moved = (s.points - fnv_box[0]) * scale + fit.head_box[0]
        share = head_share(s.dense, fit.bones)[:, None]
        out.append(replace(s, points=pushed(s.points + share * (moved - s.points), fit), tris=tris))
    return out


def _add_shape(nif, s: _Shape, fit: BodyFit, nodes: list) -> None:
    """Append _Shape `s` to `nif`, skinned on `fit`'s bones (copied skeleton `nodes`), with its static's material."""
    made = skinned_shape((s.points, s.normals, s.uv), s.tris, strongest(s.dense), [0, len(s.tris)])
    index = len(nif.blocks)
    nif.blocks.append(None)
    shader, alpha = copy_material(nif, s.static, s.shape)
    nif.blocks[shader][1]['flags1'] |= SHADER_SKINNED
    skin = skin_blocks(nif, fit, nodes, made.used, made.points, made.local, made.weights)
    fields = dict(s.shape, **made.fields, name=nif.string(s.static.strings[s.shape['name']]), shader=shader,
                  alpha_property=alpha, skin=skin)
    nif.blocks[index] = ('BSSubIndexTriShape', pack_tri_shape(fields) + segments(made.counts))
    nif.blocks[0][1]['children'].append(index)


