"""An FNV creature's own rig as FO4 files: skeleton.hkx (the animation skeleton only), clips with root motion,
skeleton.nif (FNV's ragdoll and a character controller through hknp_ragdoll, else Elric) and the skinned body.

Bone names are FNV's except the accumulation root `Bip01`, which is `Root` (vanilla FO4's bone 0) everywhere.
The ragdoll lives only in skeleton.nif: a ragdoll and mappers in skeleton.hkx beside it freeze plain deaths.

See: docs/fork/fo4_spikes.md#own-rig-ragdoll
"""

import math
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from asset_convert.havok.hkx_anim import clip_to_animation_data
from asset_convert.havok.hkx_skeleton import BONE_RENAMES, Bone, load_skeleton_bones, mat33_to_quat_xyzw
from asset_convert.havok.kf_decode import split_root_motion
from external.pynifly_hkx.anim_fo4 import BonePose, Skeleton, write_fo4_animation, write_fo4_skeleton
from fo4_import.havok import packfile
from fo4_import.havok.kf_cache import decoded
from fo4_import.nif import convert_static as CS
from fo4_import.nif import elric
from fo4_import.nif import file as F
from fo4_import.nif import hknp_ragdoll
from fo4_import.nif.animation import add_nodes
from fo4_import.nif.ragdoll_order import in_node_order
from fo4_import.nif.blocks import NONE, SHADER_SKINNED, pack_tri_shape
from fo4_import.nif.collision import character_controller
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.headgear import shape_arrays
from fo4_import.rig.table import WEAPON, weapon_node
from fo4_import.nif.outfit import copy_material, fnv_nif, fnv_skin, is_cap, originals, prn_bone, segments, skin_blocks, skinned_shape
from fo4_import.nif.clip_shaders import clip_channels
from fo4_import.nif.shader_anim import add_running, emit_multi, free_controllers, free_running, shape_entry

FNV_ROOT, ROOT = 'Bip01', 'Root'
#: A bone pose (translation, rotation w x y z, scale) unmoved: FNV plays a clip's accumulation root so.
UNMOVED = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), 1.0)
#: The node FO4 fires a gun's shots from, under the node the gun hangs on.
FIRE_NODE = 'ProjectileNode'
#: The name load_skeleton_bones (written for Skyrim) gives FNV's accumulation root.
SKYRIM_ROOT = 'NPC Root [Root]'
#: Bones whose translation animates (vanilla unlocks Root and its body root only).
UNLOCKED = {ROOT, 'Bip01 NonAccum'}
#: Bone weights kept per vertex (FO4's skinned shapes take four).
WEIGHTS = 4
#: Vanilla creature skeleton.nif BSXFlags (Havok, Ragdoll, Dynamic, Articulated): 28 of 33 actor skeletons.
SKELETON_BSX = 0xC6
#: The shape FNV's SetSecuritronExpression retextures, and its texture by (face, expression) (FalloutNV.exe's).
SCREEN_SHAPE, SCREEN_TEXTURE = 'Screen01:0', 'textures\\creatures\\securitron\\{}_{}.dds'


def fo4_name(name: str) -> str:
    return ROOT if name in (FNV_ROOT, SKYRIM_ROOT) else name


def skeleton_bones(fnv_skeleton: Path, fire: tuple = ()) -> list:
    """The FNV skeleton's bones (load_skeleton_bones), parents first, the accumulation root as Root; WEAPON moved
    onto FNV node fire[0] turned fire[1] when given (move_weapon)."""
    bones = load_skeleton_bones(str(fnv_skeleton))
    for b in bones:
        b.name = fo4_name(b.name)
    return move_weapon(bones, *fire) if fire else bones


def move_weapon(bones: list, fire: str, turn: tuple) -> list:
    """`bones` with WEAPON (childless) last, under bone `fire`, turned `turn` (aim_turn), as the eyebot's WEAPON
    sits on its Laser bone in line with its ProjectileNode: FO4 fires a gun from the model it hangs there.
    See: docs/fork/fo4_own_rig.md#ranged
    """
    bones = lift_children(bones, WEAPON)
    names = [b.name for b in bones]
    kept = [b for b in bones if b.name != WEAPON]
    index = {b.name: i for i, b in enumerate(kept)}
    out = [Bone(b.name, index[names[b.parent]] if b.parent >= 0 else -1, b.translation, b.quat_xyzw, b.scale)
           for b in kept]
    m = NifFormat.Matrix33()
    (m.m_11, m.m_12, m.m_13, m.m_21, m.m_22, m.m_23, m.m_31, m.m_32, m.m_33) = turn
    return out + [Bone(WEAPON, index[fire], (0.0, 0.0, 0.0), mat33_to_quat_xyzw(m), 1.0)]


def lift_children(bones: list, name: str) -> list:
    """`bones` with bone `name`'s children moved, in place, onto its parent.
    See: docs/fork/fo4_own_rig.md#think-tank
    """
    at = next((i for i, b in enumerate(bones) if b.name == name), None)
    return bones if at is None else [lifted(bones[at], b) if b.parent == at else b for b in bones]


def lifted(parent, child):
    """Bone `child` (under Bone `parent`) on `parent`'s parent, in the same place."""
    r, t = skeleton_frames([Bone(parent.name, -1, parent.translation, parent.quat_xyzw, parent.scale),
                            Bone(child.name, 0, child.translation, child.quat_xyzw, child.scale)])[child.name]
    scale = parent.scale * child.scale
    m = NifFormat.Matrix33()
    (m.m_11, m.m_12, m.m_13, m.m_21, m.m_22, m.m_23, m.m_31, m.m_32, m.m_33) = (r / scale).T.flatten()
    return Bone(child.name, parent.parent, tuple(float(v) for v in t), mat33_to_quat_xyzw(m), scale)


def aim_turn(bones: list, clip, node: str, at: float) -> tuple:
    """The rotation (row-major) under bone `node` that faces a gun level ahead (+Y forward, +Z up, model space) in
    decoded FNV clip `clip`'s pose at `at` seconds, the root unmoved: FO4 fires along the gun's node, FNV toward its target.
    See: docs/fork/fo4_own_rig.md#ranged
    """
    frame = int(np.argmin(np.abs(np.asarray(clip.times) - at)))
    pose = {b.name: b.quat_xyzw for b in bones}
    pose.update({fo4_name(BONE_RENAMES.get(t.bone, t.bone)): (*t.rotations[frame][1:], t.rotations[frame][0])
                 for t in clip.tracks if t.rotations is not None})
    pose.update({b.name: (0.0, 0.0, 0.0, 1.0) for b in bones if b.parent < 0})
    world = skeleton_frames([Bone(b.name, b.parent, b.translation, pose[b.name], b.scale) for b in bones])[node][0]
    return tuple(float(v) for v in (world / np.linalg.norm(world, axis=0)).T.flatten())


def write_skeleton(path: Path, bones: list) -> None:
    """skeleton.hkx: the animation skeleton alone, in vanilla's layout."""
    skel = Skeleton(name=ROOT, bones=[b.name for b in bones], parents=[b.parent for b in bones],
                    reference_pose=[BonePose(list(b.translation), list(b.quat_xyzw), [b.scale] * 3) for b in bones],
                    lock_translation=[b.name not in UNLOCKED for b in bones])
    path.parent.mkdir(parents=True, exist_ok=True)
    write_fo4_skeleton(str(path), skel)


def motion_samples(motion, frames: int) -> list:
    """Per frame (x, y, z, yaw) since the first: FNV's accumulation-root motion as FO4's reference frame."""
    trans = motion['translations'] if motion and motion['translations'] is not None else np.zeros((frames, 3))
    yaw = np.zeros(frames)
    if motion and motion['rotations'] is not None:
        q = motion['rotations']
        yaw = np.unwrap(2.0 * np.arctan2(q[:, 3], q[:, 0]))
    return [(float(x), float(y), float(z), float(a)) for (x, y, z), a in zip(trans, yaw)]


def patch_motion(path: Path, samples: list) -> None:
    """Fill the clip's zero hkaDefaultAnimatedReferenceFrame samples with `samples`, in place."""
    data = bytearray(path.read_bytes())
    pf = packfile.read(bytes(data))
    rel = next(s for s, c in pf.virtual if c == 'hkaDefaultAnimatedReferenceFrame')
    member = next(m for m in pf.cl.members('hkaDefaultAnimatedReferenceFrame') if m.name == 'referenceFrameSamples')
    at = pf.local[rel + member.offset]
    count = struct.unpack_from('<i', data, pf.base + rel + member.offset + 8)[0]
    if count != len(samples):
        raise ValueError(f'{path.name}: {count} samples, {len(samples)} frames')
    for i, s in enumerate(samples):
        struct.pack_into('<4f', data, pf.base + at + 16 * i, *s)
    path.write_bytes(bytes(data))


def write_clip(kf: Path, path: Path, bones: list, held: tuple = ()) -> dict:
    """FNV clip `kf` as an FO4 animation on `bones`, root motion in its reference frame, the root unmoved where
    the clip has no track for it (FNV plays the accumulation root so, whatever the skeleton's rest); a summary.
    Bones `held` keep their skeleton pose (FNV's keys for them dropped).
    See: docs/fork/fo4_own_rig.md#ranged
    See: docs/commentary/asset_convert_falloutnv.md#accum-root-identity
    """
    clip = decoded(str(kf))[0]
    motion = split_root_motion(clip)
    for track in clip.tracks:
        track.bone = fo4_name(BONE_RENAMES.get(track.bone, track.bone))
    clip.tracks = [t for t in clip.tracks if t.bone not in held]
    pose = {b.name: (tuple(b.translation), (b.quat_xyzw[3], *b.quat_xyzw[:3]), b.scale) for b in bones}
    pose[ROOT] = UNMOVED
    anim = clip_to_animation_data(clip, [b.name for b in bones], pose)
    anim.bone_names = [''] * anim.num_tracks
    path.parent.mkdir(parents=True, exist_ok=True)
    write_fo4_animation(str(path), anim)
    samples = motion_samples(motion, anim.num_frames)
    patch_motion(path, samples)
    end = samples[-1]
    return {'frames': anim.num_frames, 'duration': round(anim.duration, 3),
            'travel': round(math.hypot(end[0], end[1]), 1), 'yaw': round(math.degrees(end[3]), 1)}


def bound(fnv_skeleton: Path) -> tuple:
    """(centre, half sizes) of the FNV skeleton's BSBound, game units."""
    root = fnv_nif(fnv_skeleton)
    for e in root.get_extra_datas():
        if isinstance(e, NifFormat.BSBound):
            return (e.center.x, e.center.y, e.center.z), (e.dimensions.x, e.dimensions.y, e.dimensions.z)
    raise ValueError(f'{fnv_skeleton}: no BSBound')


def write_skeleton_nif(fnv_skeleton: Path, path: Path, fires: dict = None) -> dict:
    """skeleton.nif: every FNV bone (Bip01 as Root), FNV's ragdoll and a CharacterController/Bumper (hknp_ragdoll,
    else Elric); BSXFlags 0xC6 and FNV's BSBound; each equip slot's gun node on its FNV fire node, turned (`fires`
    {slot: (node, turn)}, add_fire_node), its ragdoll in node order (ragdoll_order). {bone name: ragdoll bone
    index}, which the graph takes its ragdoll indices from."""
    pre = CS.convert(str(fnv_skeleton), animated=False, every_bone=True).nif
    pre.strings = [ROOT if s == FNV_ROOT else s for s in pre.strings]
    for slot, (under, turn) in (fires or {}).items():
        add_fire_node(pre, under, weapon_node(slot), turn)
    center, half = bound(fnv_skeleton)
    character_controller(pre, center, half, CS.NODE_FLAGS)
    data = F.write(pre)
    ours = hknp_ragdoll.finish(F.read(data))
    out = F.write(ours) if ours else elric.process({'skeleton.nif': data}).get('skeleton.nif')
    if not out:
        raise RuntimeError(f'Elric made no skeleton.nif from {fnv_skeleton}')
    nif = finish_skeleton(in_node_order(F.read(out)), center, half)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(F.write(nif))
    return ragdoll_bones(nif)


def add_fire_node(nif, under: str, name: str, turn: tuple) -> None:
    """Put node `name` (FNV's WEAPON moved, else a new node) under the node named `under` (an FNV gun's fire node),
    turned `turn` (aim_turn), and hang FIRE_NODE on it unturned, as the standing turret's skeleton has it."""
    nodes = {BONE_RENAMES.get(nif.strings[b['name']], nif.strings[b['name']]): i
             for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode'}
    if name not in nodes:
        nif.blocks.append(('NiNode', {**nif.blocks[nodes[under]][1], 'name': nif.string(name), 'extra': [],
                                      'controller': NONE, 'collision': NONE, 'children': []}))
        nodes[name] = len(nif.blocks) - 1
    weapon = nodes[name]
    for kind, block in nif.blocks:
        if kind == 'NiNode' and weapon in block['children']:
            block['children'].remove(weapon)
            block['children'] += lift_nif_children(nif, weapon)
    nif.blocks[nodes[under]][1]['children'].append(weapon)
    nif.blocks[weapon][1].update(translation=(0.0, 0.0, 0.0), rotation=turn, scale=1.0)
    nif.blocks.append(('NiNode', {**nif.blocks[weapon][1], 'name': nif.string(FIRE_NODE), 'extra': [],
                                  'controller': NONE, 'rotation': CS.IDENTITY,
                                  'collision': NONE, 'children': []}))
    nif.blocks[weapon][1]['children'].append(len(nif.blocks) - 1)


#: The one class ragdoll_bones decodes, so a ragdoll's shapes need no layout (the centaur's spheres).
RAGDOLL_DATA = frozenset({'hknpRagdollData'})


def lift_nif_children(nif, node: int) -> list:
    """Block `node`'s children, each put in its parent's frame where it is (its transform composed with the node's,
    rotations row-vector); the indices, which the node no longer holds.
    See: docs/fork/fo4_own_rig.md#think-tank
    """
    w = nif.blocks[node][1]
    sw = np.array(w['rotation']).reshape(3, 3)
    for child in w['children']:
        b = nif.blocks[child][1]
        t = np.array(w['translation']) + w['scale'] * sw.T @ np.array(b['translation'])
        b.update(translation=tuple(float(v) for v in t), scale=w['scale'] * b['scale'],
                 rotation=tuple(float(v) for v in (np.array(b['rotation']).reshape(3, 3) @ sw).flatten()))
    lifted_ids, w['children'] = w['children'], []
    return lifted_ids


def ragdoll_bones(nif) -> dict:
    """{bone name: ragdoll bone index} of a skeleton.nif's bhkRagdollSystem: each node's collision object names
    its body, and the ragdoll's boneToBodyMap gives the body's bone."""
    system = next(i for i, (k, _) in enumerate(nif.blocks) if k == 'bhkRagdollSystem')
    data = next(o['fields'] for o in packfile.read(nif.blocks[system][1][4:], only=RAGDOLL_DATA).objects
                if o['class'] == 'hknpRagdollData')
    bone_of_body = {body: bone for bone, body in enumerate(data['boneToBodyMap'])}
    out = {}
    for kind, block in nif.blocks:
        if kind == 'bhkNPCollisionObject':
            target, _flags, owner, body = struct.unpack_from('<iHiI', block)
            if owner == system:
                out[nif.strings[nif.blocks[target][1]['name']]] = bone_of_body[body]
    return out


def finish_skeleton(nif, center: tuple, half: tuple):
    """Vanilla creature skeleton extras on Elric's output: BSXFlags 0xC6 and a BSBound on the root."""
    root = nif.blocks[0][1]
    for i in root['extra']:
        if nif.blocks[i][0] == 'BSXFlags':
            nif.blocks[i][1]['value'] = SKELETON_BSX
    if not any(nif.blocks[i][0] == 'BSBound' for i in root['extra']):
        nif.blocks.append(('BSBound', struct.pack('<i6f', nif.string('BBX'), *center, *half)))
        root['extra'].append(len(nif.blocks) - 1)
    return nif


def skeleton_frames(bones: list) -> dict:
    """{bone: (rotation, translation)} of each bone's world rest transform (column vectors), from the hkx pose."""
    world = {}
    for b in bones:
        x, y, z, w = b.quat_xyzw
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]) * b.scale
        t = np.array(b.translation)
        if b.parent >= 0:
            pr, pt = world[bones[b.parent].name]
            r, t = pr @ r, pr @ t + pt
        world[b.name] = (r, t)
    return world


def rest_shape(geom, root) -> tuple:
    """(root-space rest positions, unit normals) of FNV skinned `geom` (pyffi's skin deformation, then its node)."""
    verts, normals = geom.get_skin_deformation()
    m = np.array(geom.get_transform(root).as_list())
    pos = (np.array([(v.x, v.y, v.z, 1.0) for v in verts]) @ m)[:, :3]
    nrm = np.array([(n.x, n.y, n.z) for n in normals]) @ m[:3, :3]
    return pos, nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)


def skin_arrays(weights: list, index: dict) -> tuple:
    """(weights, bone indices) per vertex: its WEIGHTS strongest FNV bones (renamed), normalized."""
    w, b = np.zeros((len(weights), WEIGHTS)), np.zeros((len(weights), WEIGHTS), int)
    for i, vw in enumerate(weights):
        top = sorted(((v, fo4_name(k)) for k, v in vw.items() if v > 0), reverse=True)[:WEIGHTS]
        total = sum(v for v, _ in top) or 1.0
        for k, (v, name) in enumerate(top):
            w[i, k], b[i, k] = v / total, index[name]
    return w, b


def body_skeleton(nif, fnv_skeleton: Path, bones: list) -> tuple:
    """The body's bone nodes (FNV's skeleton nodes, Bip01 as Root) under a new root in `nif`: (skin fit, {bone
    index: node block})."""
    skel_root = fnv_nif(fnv_skeleton)
    for node in skel_root.tree():
        if isinstance(node, NifFormat.NiNode) and node.name.decode('cp1252') == FNV_ROOT:
            node.name = ROOT.encode()
    order = [n for n in skel_root.tree() if isinstance(n, NifFormat.NiNode) and n is not skel_root]
    made = add_nodes(nif, order, skel_root, CS.NODE_FLAGS)
    by_name = {n.name.decode('cp1252'): made[id(n)] for n in order}
    frames = skeleton_frames(bones)
    bind = [(None, frames[b.name][0].T, -frames[b.name][0].T @ frames[b.name][1]) for b in bones]
    fit = SimpleNamespace(bind=bind, nodes=list(range(len(bones))), frames=frames)
    return fit, {i: by_name[b.name] for i, b in enumerate(bones) if b.name in by_name}


def screen_part(parts: list) -> 'Path | None':
    """The part among `parts` holding SCREEN_SHAPE, or None."""
    return next((p for p in parts if any(isinstance(g, NifFormat.NiTriBasedGeom) and g.name.decode('cp1252')
                                         == SCREEN_SHAPE for g in fnv_nif(p).tree())), None)


def retextured(static, name: str, texture: str) -> None:
    """Show FNV texture `texture` on converted mesh `static`'s unlit shape `name` (an effect shader's own texture)."""
    for kind, shape in static.nif.blocks:
        if kind == 'BSTriShape' and static.nif.strings[shape['name']] == name:
            static.nif.blocks[shape['shader']][1]['source_texture'] = f'textures\\{CS.fo4_texture(texture)}'
    static.textures = set(static.textures) | {texture}


def write_body(fnv_parts: list, fnv_skeleton: Path, bones: list, path: Path, export_dir: Path, looks: tuple = ()):
    """The FNV body parts `fnv_parts` as one body on their own bones (add_part), caps left out. `looks` is (idle
    clip, {shape name: FNV texture}): its shapes loop the idle's shader channels, and the named ones show those
    textures (retextured). The static conversions (convert_static: their materials and textures, for the caller to
    stage) and a per-shape summary."""
    idle, textures = (tuple(looks) + (None, None))[:2]
    looped = clip_channels(idle) if idle else None
    nif = F.NifFile()
    nif.blocks.append(('NiNode', {'name': nif.string(path.name), 'extra': [], 'controller': NONE,
                                  'flags': CS.NODE_FLAGS, 'translation': (0.0, 0.0, 0.0), 'rotation': CS.IDENTITY,
                                  'scale': 1.0, 'collision': NONE, 'children': []}))
    fit, nodes = body_skeleton(nif, fnv_skeleton, bones)
    rig = (fit, nodes, {b.name: i for i, b in enumerate(bones)})
    statics, summary = [], {}
    for part in fnv_parts:
        static = CS.convert(str(part), export_dir)
        for name, texture in (textures or {}).items():
            retextured(static, name, texture)
        statics.append(static)
        summary.update(add_part(nif, static, fnv_nif(part), rig, (export_dir, looped)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(F.write(nif))
    return statics, summary


def add_part(nif, static, fnv_root, rig: tuple, looks: tuple) -> dict:
    """Append FNV body part `fnv_root`'s converted shapes (`static`) as BSSubIndexTriShapes on the body's bones
    (`rig`, add_skinned's): a skinned shape on its own bones, a rigid one weighted fully to the bone its part
    attaches to (`Prn`), each animated as animate() does with `looks` (texture root, idle clip channels). A
    summary per shape.

    See: docs/fork/fo4_own_rig.md#rigid-parts
    """
    prn = prn_bone(fnv_root)
    rigid = prn if prn and fo4_name(prn) in rig[2] else ''
    fnv = {g.name.decode('cp1252'): g for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    summary, made = {}, {}
    for shape in [static.nif.blocks[i][1] for i in static.nif.blocks[0][1]['children']
                  if static.nif.blocks[i][0] == 'BSTriShape']:
        name = static.nif.strings[shape['name']]
        geom = fnv.get(name)
        if geom is not None and not is_cap(geom) and (geom.skin_instance or rigid):
            summary[name], made[name] = add_skinned(nif, static, shape, (geom, fnv_root, rigid), rig)
    animate(nif, fnv_root, made, looks)
    return summary


def animate(nif, fnv_root, made: dict, looks: tuple) -> None:
    """Give body shapes `made` (shape_entry by FNV name, from part `fnv_root`) the idle clip's shader channels as
    loops and their own free-running controllers on the other channels; `looks` is (texture root, clip_channels()
    of the idle or None).

    See: docs/fork/fo4_own_rig.md#screen-clips
    """
    texture_root, looped = looks
    when, clip = looped or (None, [])
    baked = [c for c in clip if c[0] in made]
    keys = {(c[0], c[1]) for c in baked}
    found = [f for f in free_controllers(fnv_root) if f[0] in made and (f[0], f[2]) not in keys]
    if not found and not baked:
        return
    at = {'shapes': made, 'peaks': CS.texel_peaks(fnv_root, texture_root)}
    free_running(nif, found, at['peaks'], made)
    materials = {g.name.decode('cp1252'): g for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    for name, entry, source, fnv_type in baked:
        material = next((p for p in materials[name].get_properties() if isinstance(p, NifFormat.NiMaterialProperty)),
                        None)
        add_running(nif, at, (name, entry, source), (fnv_type, when, emit_multi(material)))


def add_skinned(nif, static, shape: dict, fnv: tuple, rig: tuple) -> tuple:
    """Append converted `shape` as a skinned BSSubIndexTriShape on the body's bones: FNV `fnv` (geometry, its
    root, the bone a rigid geometry is weighted to) gives rest positions and weights, `rig` is (skin fit, bone
    nodes, bone index). (A summary, its shape_entry)."""
    geom, fnv_root, rigid = fnv
    fit, nodes, index = rig
    pos, uv, nrm, tris = shape_arrays(shape)
    own = fnv_skin(geom, fnv_root, '' if geom.skin_instance else rigid)
    near = originals((pos, uv, nrm), (own[0], own[3], own[1]))
    rest, rest_nrm = rest_shape(geom, fnv_root) if geom.skin_instance else \
        attached(own[0], own[1], fit.frames[fo4_name(rigid)])
    weights, bone_index = skin_arrays([own[2][i] for i in near], index)
    made = skinned_shape((rest[near], rest_nrm[near], uv), tris, (weights, bone_index), [0, len(tris)])
    at = len(nif.blocks)
    nif.blocks.append(None)
    shader, alpha = copy_material(nif, static.nif, shape)
    nif.blocks[shader][1]['flags1'] |= SHADER_SKINNED
    skin = skin_blocks(nif, fit, nodes, made.used, made.points, made.local, made.weights)
    fields = dict(shape, **made.fields, name=nif.string(static.nif.strings[shape['name']]), shader=shader,
                  alpha_property=alpha, skin=skin)
    nif.blocks[at] = ('BSSubIndexTriShape', pack_tri_shape(fields) + segments(made.counts))
    nif.blocks[0][1]['children'].append(at)
    return ({'vertices': len(made.points), 'triangles': len(tris), 'bones': len(made.used)},
            shape_entry(nif, at, shader, alpha))


def attached(pos: np.ndarray, nrm: np.ndarray, frame: tuple) -> tuple:
    """Part-root `pos`, `nrm` in skeleton space, the root at bone `frame`."""
    rotation, translation = frame
    moved = nrm @ rotation.T
    return pos @ rotation.T + translation, moved / np.maximum(np.linalg.norm(moved, axis=1, keepdims=True), 1e-9)
