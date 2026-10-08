"""An FNV outfit (a skinned body mesh) as a Fallout 4 worn one, on FO4's body.

FNV skins an outfit to its Bip01 skeleton, in that skeleton's bind pose;
Fallout 4 skins one to its own bones (and the body's helper `_skin` bones),
its vertices in the body's frame: the skeleton's world shifted so the neck
sits near the origin (vanilla MaleBody.nif, SweaterVest\\MOutfit.nif). The
outfit is carried across in three steps:

- **Retarget.** Each FNV bone maps to an FO4 one (BONES). A bone that spans
  a limb or spine part (ENDS) is turned so its direction matches FO4's and
  stretched along itself to FO4's length; the rest move with the bone they
  follow (FOLLOW: twist bones, hands, feet, the head) or, unmapped, their
  nearest mapped ancestor. Each vertex moves by its FNV weights.
- **Conform.** FNV's body, retargeted the same way, is compared with FO4's;
  each outfit vertex takes the smoothed offset of the FNV body vertices
  nearest it, so the outfit meets FO4's head, hands and feet where FNV's
  met FNV's.
- **Skin.** Each vertex takes the weights of FO4's body at its nearest
  surface point (four largest), on the body's bones and their bind data;
  the body's skeleton nodes come along. Each triangle goes to the body-part
  segment of its strongest bone (arms, legs, torso), as vanilla's body
  orders them; dismemberment cut data is left out.

FNV's dismemberment caps (partitions 100-999) and the sleeve it shows
without a Pip-Boy (`pipboyoff`; FO4's player always wears one) are left out.
Skin shapes (FNV's FaceGen shader flag) take FO4's skin-tint shader and
skin material, with FNV's textures. The first-person model is the arm
segments alone; FO4's first-person body shares the third-person bind data.

See: docs/fork/fo4_spikes.md#spike-4-outfits
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face.bake import surface
from fo4_import.nif import bgsm
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE, Reader, pack_tri_shape, read_tri_shape
from fo4_import.nif.convert_static import IDENTITY, NifFormat, vertices
from fo4_import.nif.elric import without_havok
from fo4_import.nif.headgear import DESC_SKINNED, NO_PARENT, SHADER_SKINNED, shape_arrays

#: Per sex: FO4's body (in Fallout 4 - Meshes.ba2), its skin material, and FNV's body (under the export's meshes).
FO4_BODIES = {'male': 'meshes\\actors\\character\\characterassets\\malebody.nif',
              'female': 'meshes\\actors\\character\\characterassets\\femalebody.nif'}
FO4_SKINS = {'male': 'materials\\actors\\character\\basehumanmale\\basehumanskin.bgsm',
             'female': 'materials\\actors\\character\\basehumanfemale\\basehumanfemaleskin.bgsm'}
FNV_BODIES = {'male': 'characters\\_male\\upperbody.nif', 'female': 'characters\\_male\\femaleupperbody.nif'}
FO4_SKELETON = 'meshes\\actors\\character\\characterassets\\skeleton.nif'
FNV_SKELETON = 'characters\\_male\\skeleton.nif'
SIDES = (('L', 'L'), ('R', 'R'))
#: FNV bone -> FO4 bone.
BONES = {'Bip01 Pelvis': 'Pelvis', 'Bip01 Spine': 'SPINE1', 'Bip01 Spine1': 'SPINE2', 'Bip01 Spine2': 'Chest',
         'Bip01 Neck': 'Neck', 'Bip01 Neck1': 'Neck', 'Bip01 Head': 'HEAD'}
for _fnv, _fo4 in SIDES:
    BONES.update({f'Bip01 {_fnv} Thigh': f'{_fo4}Leg_Thigh', f'Bip01 {_fnv} Calf': f'{_fo4}Leg_Calf',
                  f'Bip01 {_fnv} Foot': f'{_fo4}Leg_Foot', f'Bip01 {_fnv} Toe0': f'{_fo4}Leg_Toe1',
                  f'Bip01 {_fnv} Clavicle': f'{_fo4}Arm_Collarbone', f'Bip01 {_fnv} UpperArm': f'{_fo4}Arm_UpperArm',
                  f'Bip01 {_fnv} Forearm': f'{_fo4}Arm_ForeArm1', f'Bip01 {_fnv} Hand': f'{_fo4}Arm_Hand'})
#: FNV bone -> the FNV bone its part runs to (the matching FO4 bones span the same part).
ENDS = {'Bip01 Spine': 'Bip01 Spine1', 'Bip01 Spine1': 'Bip01 Spine2', 'Bip01 Spine2': 'Bip01 Neck1',
        'Bip01 Neck1': 'Bip01 Head'}
#: FNV bone -> the bone whose move it takes.
FOLLOW = {'Bip01 Neck': 'Bip01 Neck1', 'Bip01 Head': 'Bip01 Neck1'}
for _fnv, _ in SIDES:
    ENDS.update({f'Bip01 {_fnv} Thigh': f'Bip01 {_fnv} Calf', f'Bip01 {_fnv} Calf': f'Bip01 {_fnv} Foot',
                 f'Bip01 {_fnv} Foot': f'Bip01 {_fnv} Toe0', f'Bip01 {_fnv} Clavicle': f'Bip01 {_fnv} UpperArm',
                 f'Bip01 {_fnv} UpperArm': f'Bip01 {_fnv} Forearm', f'Bip01 {_fnv} Forearm': f'Bip01 {_fnv} Hand'})
    FOLLOW.update({f'Bip01 {_fnv} Hand': f'Bip01 {_fnv} Forearm', f'Bip01 {_fnv} Toe0': f'Bip01 {_fnv} Foot',
                   f'Bip01 {_fnv}UpArmTwistBone': f'Bip01 {_fnv} UpperArm',
                   f'Bip01 {_fnv} ForeTwist': f'Bip01 {_fnv} Forearm'})
ROOT_BONE = 'Bip01 Pelvis'
#: FNV dismemberment partitions that are caps (section, torso and limb caps): shown only once a limb is cut.
CAP_PARTS = range(100, 1000)
PIPBOY_OFF = 'pipboyoff'
#: FNV body vertices whose offsets an outfit vertex averages (inverse distance), and smoothing passes over them.
NEIGHBOURS, SMOOTH_PASSES = 8, 3
#: UV and normal weights against position when a converted vertex finds its FNV original (shared positions).
MATCH_UV, MATCH_NORMAL = 100.0, 10.0
WEIGHTS_PER_VERTEX = 4
#: Vanilla body segments (MaleBody.nif): left arm, torso, right arm, left leg, right leg; first person has five.
SEG_LARM, SEG_TORSO, SEG_RARM, SEG_LLEG, SEG_RLEG = 2, 3, 4, 5, 6
SEGMENTS, FIRST_PERSON_SEGMENTS = 7, 5
ARMS = (SEG_LARM, SEG_RARM)
#: FO4 bone name prefix -> segment; other bones (spine, collarbones, neck, pelvis) are the torso's.
SEGMENT_OF = (('LArm_Collarbone', SEG_TORSO), ('RArm_Collarbone', SEG_TORSO), ('LArm_ShoulderFat', SEG_TORSO),
              ('RArm_ShoulderFat', SEG_TORSO), ('LArm', SEG_LARM), ('RArm', SEG_RARM), ('LLeg', SEG_LLEG),
              ('RLeg', SEG_RLEG))
BONE_DATA_SIZE = 68


def segment_of(bone: str) -> int:
    """The body-part segment of FO4 bone `bone`."""
    return next((seg for prefix, seg in SEGMENT_OF if bone.startswith(prefix)), SEG_TORSO)


def _turn(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest rotation taking unit vector `a` onto unit vector `b`."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def part_move(joint, end, fo4_joint, fo4_end) -> tuple:
    """(L, c) with x' = L x + c: the part `joint`->`end` turned onto `fo4_joint`->`fo4_end` and stretched along
    itself to its length."""
    span, fo4_span = np.subtract(end, joint), np.subtract(fo4_end, fo4_joint)
    d = span / np.linalg.norm(span)
    k = np.linalg.norm(fo4_span) / np.linalg.norm(span)
    move = _turn(d, fo4_span / np.linalg.norm(fo4_span)) @ (np.eye(3) + (k - 1.0) * np.outer(d, d))
    return move, np.asarray(fo4_joint) - move @ joint


def bone_moves(fnv_joints: dict, fnv_parents: dict, fo4_joints: dict) -> dict:
    """{FNV bone: (L, c)} for every FNV skeleton bone (retarget, in the module notes)."""
    moves = {ROOT_BONE: (np.eye(3), np.asarray(fo4_joints[BONES[ROOT_BONE]]) - fnv_joints[ROOT_BONE])}
    for bone, end in ENDS.items():
        moves[bone] = part_move(fnv_joints[bone], fnv_joints[end], fo4_joints[BONES[bone]], fo4_joints[BONES[end]])
    for bone, leader in FOLLOW.items():
        moves[bone] = moves[leader]
    for bone in fnv_parents:
        up = bone
        while up not in moves and up in fnv_parents:
            up = fnv_parents[up]
        moves[bone] = moves.get(up, moves[ROOT_BONE])
    return moves


def _fnv_nif(path: Path):
    """An FNV NIF's root (pyffi)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return data.roots[0]


def is_cap(geom) -> bool:
    """Whether an FNV skinned shape is all dismemberment caps."""
    parts = [p.body_part for p in getattr(geom.skin_instance, 'partitions', [])]
    return bool(parts) and all(p in CAP_PARTS for p in parts)


def is_skin(geom) -> bool:
    """Whether an FNV shape shows the wearer's skin (its shader's FaceGen flag)."""
    shader = next((p for p in geom.get_properties() if isinstance(p, NifFormat.BSShaderPPLightingProperty)), None)
    return bool(shader and shader.shader_flags.sf_face_gen)


def fnv_skin(geom, root) -> tuple:
    """(root-space positions, unit normals, [{bone: weight}], UVs per vertex) of a skinned FNV shape."""
    m = np.array(geom.get_transform(root).as_list())
    pos = (np.array([(v.x, v.y, v.z, 1.0) for v in geom.data.vertices]) @ m)[:, :3]
    nrm = np.array([(n.x, n.y, n.z) for n in geom.data.normals]) @ m[:3, :3] if geom.data.has_normals else \
        np.zeros_like(pos)
    weights = [{} for _ in pos]
    skin = geom.skin_instance
    for bone, data in zip(skin.bones, skin.data.bone_list):
        name = bone.name.decode('cp1252')
        for vw in data.vertex_weights:
            weights[vw.index][name] = weights[vw.index].get(name, 0.0) + vw.weight
    uv = (np.array([(t.u, t.v) for t in geom.data.uv_sets[0]]) if geom.data.num_uv_sets and len(geom.data.uv_sets)
          else np.zeros((len(pos), 2)))
    return pos, nrm, weights, uv


def _fo4_joints(skeleton) -> dict:
    """{name: world position} of an FO4 skeleton NIF's nodes (nif rotations act on column vectors)."""
    parent = {c: i for i, (_, b) in enumerate(skeleton.blocks) if isinstance(b, dict) and 'children' in b
              for c in b['children']}
    world = {}

    def place(i):
        """(world rotation, position) of node `i`."""
        if i not in world:
            b = skeleton.blocks[i][1]
            rot, pos = np.array(b['rotation']).reshape(3, 3) * b['scale'], np.array(b['translation'])
            if i in parent:
                up_rot, up_pos = place(parent[i])
                rot, pos = up_rot @ rot, up_rot @ pos + up_pos
            world[i] = rot, pos
        return world[i]

    return {skeleton.strings[b['name']]: place(i)[1] for i, (_, b) in enumerate(skeleton.blocks)
            if isinstance(b, dict) and 'children' in b}


def _bone_data(raw: bytes) -> list:
    """[(sphere 4f, rotation 3x3, translation)] per bone of a BSSkin::BoneData; bone space is rot @ p + t."""
    n = struct.unpack_from('<I', raw)[0]
    out = []
    for i in range(n):
        vals = struct.unpack_from('<4f9f3ff', raw, 4 + i * BONE_DATA_SIZE)
        out.append((vals[:4], np.array(vals[4:13]).reshape(3, 3), np.array(vals[13:16])))
    return out


def _skin_bones(nif, shape: dict) -> tuple:
    """(bone node indices, BoneData block index) of a skinned FO4 shape."""
    r = Reader(nif.blocks[shape['skin']][1])
    r.take('i')
    data = r.take('i')
    return r.refs(), data


@dataclass
class BodyFit:
    """FNV bone moves onto FO4's skeleton; FNV body vertices moved (`anchors`) and their offsets onto FO4's
    body; FO4's body (its NIF, bones, bind data, per-vertex weights, surface samples) and skin shader."""
    moves: dict
    anchors: np.ndarray
    offsets: np.ndarray
    body: object
    bones: list
    nodes: list
    bind: list
    weights: np.ndarray
    samples: tuple
    tris: np.ndarray
    skin_shader: dict

    def retargeted(self, points: np.ndarray, normals: np.ndarray, weights: list) -> tuple:
        """(positions, unit normals) of FNV root-space points moved by their FNV bones' moves."""
        out, nrm = np.zeros_like(points), np.zeros_like(points)
        for i, (p, n, w) in enumerate(zip(points, normals, weights)):
            total = sum(w.values()) or 1.0
            for bone, share in (w or {ROOT_BONE: 1.0}).items():
                move, shift = self.moves.get(bone, self.moves[ROOT_BONE])
                out[i] += share / total * (move @ p + shift)
                nrm[i] += share / total * (move @ n)
        return out, nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)

    def placed(self, points: np.ndarray, normals: np.ndarray, weights: list) -> tuple:
        """retargeted(), then each point shifted by its nearest FNV body vertices' offsets (inverse distance)."""
        points, normals = self.retargeted(points, normals, weights)
        dist, near = cKDTree(self.anchors).query(points, k=NEIGHBOURS)
        share = 1.0 / np.maximum(dist, 1e-6)
        return points + (self.offsets[near] * share[:, :, None]).sum(1) / share.sum(1)[:, None], normals

    def skin(self, points: np.ndarray) -> tuple:
        """(weights, body bone indices), WEIGHTS_PER_VERTEX each, of FO4's body at its nearest surface points."""
        points_s, owner, bary = self.samples
        idx = cKDTree(points_s).query(points)[1]
        dense = (bary[idx][:, :, None] * self.weights[self.tris[owner[idx]]]).sum(1)
        top = np.argsort(-dense, axis=1)[:, :WEIGHTS_PER_VERTEX]
        w = np.take_along_axis(dense, top, axis=1)
        return w / np.maximum(w.sum(1, keepdims=True), 1e-9), top


def body_fit(export_dir: Path, sex: str, archives: Archives = None) -> BodyFit:
    """The fit of FNV's skeleton and body of `sex` onto FO4's."""
    archives = archives or Archives(FALLOUT4_DIR / 'Data')
    body = nif_file.read(archives.read(FO4_BODIES[sex]))
    raw = next(b for kind, b in body.blocks if kind == 'BSSubIndexTriShape')
    shape = read_tri_shape(Reader(raw))
    nodes, data = _skin_bones(body, shape)
    bones = [body.strings[body.blocks[i][1]['name']] for i in nodes]
    bind = _bone_data(body.blocks[data][1])
    skeleton = _fo4_joints(nif_file.read(archives.read(FO4_SKELETON)))
    shift = np.mean([-rot.T @ t - skeleton[b] for b, (_, rot, t) in zip(bones, bind) if b in skeleton], axis=0)
    moves = bone_moves(*_fnv_skeleton(export_dir), {name: pos + shift for name, pos in skeleton.items()})
    points = np.array([v['position'] for v in shape['vertices']], float)
    tris = np.array(shape['triangles'])
    weights = np.zeros((len(points), len(bones)))
    for i, v in enumerate(shape['vertices']):
        for w, b in zip(v['weights'], v['bones']):
            weights[i, b] += w
    samples = surface(points, tris)
    fit = BodyFit(moves, np.zeros((0, 3)), np.zeros((0, 3)), body, bones, nodes, bind, weights, samples, tris,
                  body.blocks[shape['shader']][1])
    fit.anchors, fit.offsets = _anchors(fit, export_dir / 'meshes' / FNV_BODIES[sex])
    return fit


def _fnv_skeleton(export_dir: Path) -> tuple:
    """({bone: world position}, {bone: parent}) of FNV's skeleton."""
    skeleton = _fnv_nif(export_dir / 'meshes' / FNV_SKELETON)
    joints, parents = {}, {}
    for node in skeleton.tree():
        if isinstance(node, NifFormat.NiNode):
            name = node.name.decode('cp1252')
            joints[name] = np.array(node.get_transform(skeleton).as_list())[3, :3]
            parents.update({c.name.decode('cp1252'): name for c in node.children if c})
    return joints, parents


def _anchors(fit: BodyFit, fnv_body_path: Path) -> tuple:
    """(FNV's body vertices retargeted by `fit`, their smoothed offsets onto FO4's body surface)."""
    fnv_body = _fnv_nif(fnv_body_path)
    parts = [fnv_skin(g, fnv_body) for g in fnv_body.tree()
             if isinstance(g, NifFormat.NiTriBasedGeom) and g.skin_instance and not is_cap(g)]
    anchors, _ = fit.retargeted(np.vstack([p[0] for p in parts]), np.vstack([p[1] for p in parts]),
                                [w for p in parts for w in p[2]])
    samples = fit.samples[0]
    offsets = samples[cKDTree(samples).query(anchors)[1]] - anchors
    _, near = cKDTree(anchors).query(anchors, k=NEIGHBOURS)
    for _ in range(SMOOTH_PASSES):
        offsets = offsets[near].mean(1)
    return anchors, offsets


def skin_material(fnv: dict, sex: str, archives: Archives = None) -> dict:
    """FO4's skin material of `sex` with FNV material `fnv`'s textures."""
    archives = archives or Archives(FALLOUT4_DIR / 'Data')
    out = bgsm.read(archives.read(FO4_SKINS[sex]))
    out['textures'] = dict(out['textures'], **{k: fnv['textures'][k] for k in ('diffuse', 'normal', 'smooth_spec')})
    return out


def skin_path(material: str) -> str:
    """The skin material written beside FNV material `material`."""
    return material.rsplit('.', 1)[0] + '_skin.bgsm'


def _segments(counts: list) -> bytes:
    """A BSSubIndexTriShape trailer of segments holding `counts` triangles each, in order, no sub-segments."""
    out, start = struct.pack('<3I', sum(counts), len(counts), len(counts)), 0
    for n in counts:
        out += struct.pack('<4I', start * 3, n, NO_PARENT, 0)
        start += n
    return out


def _copy_skeleton(nif, fit: BodyFit) -> dict:
    """Append FO4's body's skeleton nodes under `nif`'s root; {body node index: new index}."""
    kept = [i for i, (kind, _) in enumerate(fit.body.blocks) if kind == 'NiNode' and i]
    new = {old: len(nif.blocks) + k for k, old in enumerate(kept)}
    for old in kept:
        b = dict(fit.body.blocks[old][1])
        b.update(name=nif.string(fit.body.strings[b['name']]), extra=[], controller=NONE, collision=NONE,
                 children=[new[c] for c in b['children'] if c in new])
        nif.blocks.append(('NiNode', b))
    nif.blocks[0][1]['children'] += [new[c] for c in fit.body.blocks[0][1]['children'] if c in new]
    return new


def _skin_blocks(nif, fit: BodyFit, nodes: dict, used: list, points: np.ndarray, local: np.ndarray,
                 weights: np.ndarray) -> int:
    """Append a BSSkin::Instance and BoneData on body bones `used` for a shape's points; the instance's index."""
    out = bytearray(struct.pack('<I', len(used)))
    for k, bone in enumerate(used):
        _, rot, t = fit.bind[bone]
        mine = points[((local == k) & (weights > 0)).any(1)]
        mine = (mine @ rot.T + t) if len(mine) else np.zeros((1, 3))
        center = (mine.min(0) + mine.max(0)) / 2
        out += struct.pack('<4f9f3ff', *center, float(np.linalg.norm(mine - center, axis=1).max()), *rot.ravel(),
                           *t, 1.0)
    index = len(nif.blocks)
    bone_nodes = [nodes[fit.nodes[b]] for b in used]
    nif.blocks.append(('BSSkin::Instance', struct.pack(f'<iiI{len(used)}iI', 0, index + 1, len(used),
                                                       *bone_nodes, 0)))
    nif.blocks.append(('BSSkin::BoneData', bytes(out)))
    return index


def originals(converted: tuple, fnv: tuple) -> np.ndarray:
    """Per converted vertex (positions, UVs, unit normals), the index of its FNV original (the same three)."""
    def key(pos, uv, nrm):
        """A vertex as one point: position, scaled UV, scaled normal."""
        unit = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        return np.hstack([pos, MATCH_UV * uv, MATCH_NORMAL * unit])
    return cKDTree(key(*fnv)).query(key(*converted))[1]


@dataclass
class WornShape:
    """A shape skinned on FO4's body: its BSTriShape fields, triangles per segment, body bones `used` and per
    vertex positions, bone indices into `used` and weights."""
    fields: dict
    counts: list
    used: list
    points: np.ndarray
    local: np.ndarray
    weights: np.ndarray


def _segment_order(segment: np.ndarray, first_person: bool) -> tuple:
    """(triangle indices sorted by segment, triangles per segment): arm segments only in first person."""
    n = FIRST_PERSON_SEGMENTS if first_person else SEGMENTS
    order = [s for s in range(n) if not first_person or s in ARMS]
    kept = np.concatenate([np.flatnonzero(segment == s) for s in order])
    return kept, [int((segment[kept] == s).sum()) for s in range(n)]


def worn_shape(shape: dict, fit: BodyFit, fnv: tuple, first_person: bool) -> 'WornShape | None':
    """Static shape `shape` (of FNV shape `fnv`: positions, normals, weights, UVs) skinned on FO4's body, its triangles
    in body-part segments (arms only in first person); None when nothing is left of it."""
    pos, uv, nrm, tris = shape_arrays(shape)
    fnv_pos, fnv_nrm, fnv_weights, fnv_uv = fnv
    near = originals((pos, uv, nrm), (fnv_pos, fnv_uv, fnv_nrm))
    points, normals = fit.placed(fnv_pos[near], fnv_nrm[near], [fnv_weights[i] for i in near])
    weights, bones = fit.skin(points)
    strength = np.zeros((len(tris), len(fit.bones)))
    for k in range(3):
        np.add.at(strength, (np.repeat(np.arange(len(tris)), WEIGHTS_PER_VERTEX), bones[tris[:, k]].ravel()),
                  weights[tris[:, k]].ravel())
    kept, counts = _segment_order(np.array([segment_of(fit.bones[b]) for b in strength.argmax(1)]), first_person)
    if not len(kept):
        return None
    used_verts, flat = np.unique(tris[kept], return_inverse=True)
    tris = flat.reshape(-1, 3)
    points, normals, uv = points[used_verts], normals[used_verts], uv[used_verts]
    weights, bones = weights[used_verts], bones[used_verts]
    used = sorted(set(bones[weights > 0].tolist()))
    local = np.where(weights > 0, np.searchsorted(used, bones), 0)
    verts = vertices(points, uv, normals, None, tris)
    for v, w, b in zip(verts, weights, local):
        v.update(weights=tuple(map(float, w)), bones=tuple(map(int, b)))
    center = (points.min(0) + points.max(0)) / 2
    fields = dict(vertices=verts, triangles=[tuple(map(int, t)) for t in tris], vertex_desc=DESC_SKINNED,
                  translation=(0.0, 0.0, 0.0), rotation=IDENTITY, scale=1.0, collision=NONE, extra=[],
                  controller=NONE, bound=(*map(float, center), float(np.linalg.norm(points - center, axis=1).max())))
    return WornShape(fields, counts, used, points, local, weights)


def _copy_material(nif, static, shape: dict) -> tuple:
    """Append copies of static shape `shape`'s shader (and texture set) and alpha property; (shader, alpha)."""
    kind, shader = static.blocks[shape['shader']]
    index = len(nif.blocks)
    shader = dict(shader, name=nif.string(static.strings[shader['name']]), extra=[], controller=NONE)
    nif.blocks.append((kind, shader))
    if kind == 'BSLightingShaderProperty':
        shader.update(root_material=nif.empty_string(), texture_set=index + 1)
        nif.blocks.append(static.blocks[static.blocks[shape['shader']][1]['texture_set']])
    alpha = NONE
    if shape['alpha_property'] != NONE:
        alpha = len(nif.blocks)
        nif.blocks.append(static.blocks[shape['alpha_property']])
    return index, alpha


def _skin_shader(nif, shader: int, fit: BodyFit) -> str:
    """Make lighting shader `shader` FO4's body skin shader on the skin material beside its own; that material."""
    own = nif.blocks[shader][1]
    material = nif.strings[own['name']]
    nif.blocks[shader] = ('BSLightingShaderProperty', dict(
        fit.skin_shader, name=nif.string(skin_path(material)), extra=[], controller=NONE,
        texture_set=own['texture_set'], root_material=nif.empty_string()))
    return material


def _wanted(geom) -> bool:
    """Whether FO4 draws an FNV outfit shape (skinned, no cap, no pipboyoff)."""
    return bool(geom is not None and geom.skin_instance and not is_cap(geom)
                and not geom.name.lower().startswith(PIPBOY_OFF.encode()))


def worn(static_bytes: bytes, fnv_path: Path, fit: BodyFit, first_person: bool = False) -> tuple:
    """(FO4 worn NIF, FNV materials its skin shapes need skin versions of) of a converted FNV outfit
    (convert_static's, of the FNV NIF at `fnv_path`), on `fit`'s body; arms only when `first_person`."""
    static = without_havok(nif_file.read(static_bytes))
    fnv_root = _fnv_nif(fnv_path)
    fnv = {g.name.decode('cp1252'): g for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    root = static.blocks[0][1]
    nif = nif_file.NifFile()
    nif.blocks.append(('NiNode', dict(root, name=nif.string(static.strings[root['name']]), extra=[], children=[])))
    nodes, skins = _copy_skeleton(nif, fit), set()
    for shape in [static.blocks[i][1] for i in root['children'] if static.blocks[i][0] == 'BSTriShape']:
        geom = fnv.get(static.strings[shape['name']])
        made = worn_shape(shape, fit, fnv_skin(geom, fnv_root), first_person) if _wanted(geom) else None
        if made is None:
            continue
        index = len(nif.blocks)
        nif.blocks.append(None)
        shader, alpha = _copy_material(nif, static, shape)
        if nif.blocks[shader][0] == 'BSLightingShaderProperty' and is_skin(geom):
            skins.add(_skin_shader(nif, shader, fit))
        else:
            nif.blocks[shader][1]['flags1'] |= SHADER_SKINNED
        skin = _skin_blocks(nif, fit, nodes, made.used, made.points, made.local, made.weights)
        out = dict(shape, **made.fields, name=nif.string(static.strings[shape['name']]), shader=shader,
                   alpha_property=alpha, skin=skin)
        nif.blocks[index] = ('BSSubIndexTriShape', pack_tri_shape(out) + _segments(made.counts))
        nif.blocks[0][1]['children'].append(index)
    return nif_file.write(nif), skins
