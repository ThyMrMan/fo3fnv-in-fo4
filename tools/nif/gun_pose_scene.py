"""A converted FNV gun's first-person hold, posed for viewing: per FO4 clip, FNV's pose (its gun, arms and camera,
from the FNV clip the converter played), ours (the converted gun and clip on FO4's arms) and vanilla's (the
template's own gun and clip), each in its game's camera frame, written as JSON for blender_pose_scene.py.

    py -3.14 -m tools.nif.gun_pose_scene WeapTeslaCannon --data <mod folder> \\
        --vanilla missilelauncher:weapons/missilelauncher/missilelauncher_1.nif --out scene.json

Coordinates are Blender's camera frame: the camera at the origin looking down -Z, +Y up, +X right; each group
carries its game's first-person field of view (FNV fDefault1stPersonFOV 55, FO4 80).
See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from asset_convert.havok.clip_retarget import Skeleton, world_positions
from asset_convert.havok.gun_vocabulary_falloutnv import ANIM_TYPE_CLASS, FNV_BACKPACK
from asset_convert.havok.hkx_anim import decode_clip
from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.gun_clips import HELD_FROM, VIEWS, WEAPON, fo4_skeleton, vanilla_worlds
from fo4_import.nif import file as nif_file
from fo4_import.app.preview.scene import SHAPES
from fo4_import.nif import gun
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import bone_data, shape_bones
from fo4_import.pipeline.mesh_cache import cached_convert
from fo4_import.spike.guns import GUN_SUFFIX
from tes5_import.base.text_reader import parse_export_file

B = chr(92)
EXPORT = Path('export/FalloutNV.esm')
FNV_1ST = EXPORT / 'meshes/characters/_1stperson'
#: FNV's first-person arms: the body and both first-person hands, posed on its first-person skeleton.
FNV_ARMS = ('characters/_male/upperbody.nif', 'characters/_male/lefthand1st.nif', 'characters/_male/righthand1st.nif')
#: FO4's first-person arms, posed on its first-person skeleton.
FO4_ARMS = ('actors/character/characterassets/1stpersonmalebody.nif',
            'actors/character/characterassets/1stpersonmalehands.nif')
#: Each game's first-person field of view (degrees; Fallout.ini / Fallout4.ini fDefault1stPersonFOV).
FOV = {'fnv': 55.0, 'fo4': 80.0}
#: Bones marked in each game (the hands and their middle fingers' bases).
FNV_MARKS = ('Bip01 L Hand', 'Bip01 L Finger21', 'Bip01 R Hand', 'Bip01 R Finger21')
FO4_MARKS = ('LArm_Hand', 'LArm_Finger21', 'RArm_Hand', 'RArm_Finger21')
#: The renders blender_pose_scene makes per group: the game's camera, then orthographic left and top views.
VIEWS_RENDERED = ('view', 'left', 'top')
#: FNV camera frame (forward +Y, up +Z) -> Blender camera frame (forward -Z, up +Y); FO4's camera already is it.
FNV_TO_CAMERA = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def _homogeneous(points: np.ndarray) -> np.ndarray:
    """Row vectors with a 1 appended."""
    return np.hstack([points, np.ones((len(points), 1))])


def shapes(nif) -> list:
    """[(name, vertices in the root's frame, triangles)] of a FO4 NIF's unskinned BSTriShapes."""
    worlds = gun.node_worlds(nif)
    return [(nif.strings[b['name']], (_homogeneous(np.array([v['position'] for v in b['vertices']], float))
                                      @ worlds[i])[:, :3], b['triangles'])
            for i, (kind, b) in enumerate(nif.blocks)
            if kind == 'BSTriShape' and i in worlds and b['vertices'] and b['skin'] < 0]


def fo4_skinned(raw: bytes, worlds: dict) -> list:
    """[(name, posed vertices, triangles)] of a FO4 NIF's skinned shapes on bone frames `worlds` ({name: 4x4}), a
    vertex's weight on bones `worlds` lacks shared among its others."""
    nif = nif_file.read(raw)
    out = []
    for kind, b in nif.blocks:
        b = b if isinstance(b, dict) or kind not in SHAPES else read_tri_shape(Reader(b))
        if kind not in SHAPES or b.get('skin', -1) < 0 or not b['vertices']:
            continue
        refs, data = shape_bones(nif, b)
        names = [nif.strings[nif.blocks[r][1]['name']] for r in refs]
        binds = bone_data(nif.blocks[data][1])
        points = np.array([v['position'] for v in b['vertices']], float)
        posed, total = np.zeros_like(points), np.zeros(len(points))
        for k, name in enumerate(names):
            _, rot, t = binds[k]
            weight = np.array([sum(w for w, j in zip(v['weights'], v['bones']) if j == k) for v in b['vertices']])
            if name in worlds and weight.any():
                posed += weight[:, None] * (_homogeneous(points @ rot.T + t) @ worlds[name])[:, :3]
                total += weight
        out.append((nif.strings[b['name']], posed / np.maximum(total, 1e-6)[:, None], b['triangles']))
    return out


def fnv_skinned(path: Path, worlds: dict) -> list:
    """[(name, posed vertices, triangles)] of an FNV NIF's skinned shapes on bone frames `worlds` ({name: 4x4})."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    out = []
    for geom in data.roots[0].tree():
        skin = getattr(geom, 'skin_instance', None)
        if not isinstance(geom, NifFormat.NiTriBasedGeom) or skin is None:
            continue
        points = _homogeneous(np.array([(v.x, v.y, v.z) for v in geom.data.vertices], float))
        posed = np.zeros((len(points), 3))
        for bone, bind in zip(skin.bones, skin.data.bone_list):
            name = bone.name.decode('cp1252')
            if name not in worlds:
                continue
            moved = (points @ np.array(bind.get_transform().as_list()) @ worlds[name])[:, :3]
            for vw in bind.vertex_weights:
                posed[vw.index] += vw.weight * moved[vw.index]
        out.append((geom.name.decode('cp1252'), posed, [tuple(t) for t in geom.data.get_triangles()]))
    return out


def fnv_gun(rec: dict) -> tuple:
    """([(name, vertices, triangles)] of FNV gun `rec`'s converted mesh in its own frame (FNV axes), {node: position})."""
    path = EXPORT / 'meshes' / rec['Model.MODL'].replace(B + B, '/').replace(B, '/').lower()
    static = nif_file.write(cached_convert(path, EXPORT, None, False).nif)
    if int(rec.get('DNAM.Flags1', 0)) & FNV_BACKPACK:
        static = gun.without(static, gun.BACKPACK)
    return shapes(gun.without_havok(nif_file.read(static))), gun.fnv_nodes(path)


class Scene:
    """The groups written: {group name: {fov, meshes: [{name, kind, verts, tris}], marks: [{name, at}]}}."""

    def __init__(self):
        self.groups = {}

    def add(self, group: str, game: str, camera: np.ndarray, meshes: list, marks: dict) -> None:
        """Group `group` of `game` ('fnv'/'fo4'): `meshes` [(name, kind, world vertices, triangles)] and `marks`
        {name: world position}, moved into Blender's frame of world camera bone `camera`."""
        turn = FNV_TO_CAMERA if game == 'fnv' else np.eye(3)
        into = np.linalg.inv(camera)

        def placed(points):
            return np.round((_homogeneous(np.asarray(points, float)) @ into)[:, :3] @ turn, 3).tolist()

        self.groups[group] = {
            'fov': FOV[game],
            'meshes': [{'name': n, 'kind': k, 'verts': placed(v), 'tris': [list(map(int, t)) for t in tris]}
                       for n, k, v, tris in meshes if len(v)],
            'marks': [{'name': n, 'at': placed([p])[0]} for n, p in marks.items()]}


def fnv_group(scene: Scene, label: str, stem: str, rec: dict, frame: int) -> bool:
    """FNV's pose at `frame` of first-person clip `stem` into `scene`; False when FNV has no such clip."""
    kf = FNV_1ST / f'{stem}.kf'
    if not kf.is_file():
        return False
    skeleton = Skeleton.from_nif(str(FNV_1ST / 'skeleton.nif'))
    clip = decode_clip(str(kf))[0]
    world = world_positions(clip, skeleton, min(frame, len(clip.times) - 1))
    worlds = {n: world[i] for i, n in enumerate(skeleton.names)}
    held = worlds['Weapon']
    parts, nodes = fnv_gun(rec)
    meshes = [(n, 'gun', (_homogeneous(v) @ held)[:, :3], t) for n, v, t in parts]
    for path in FNV_ARMS:
        meshes += [(n, 'arms', v, t) for n, v, t in fnv_skinned(EXPORT / 'meshes' / path, worlds)]
    marks = {n: worlds[n][3, :3] for n in FNV_MARKS}
    marks.update({n: (np.append(p, 1.0) @ held)[:3] for n, p in nodes.items() if n.startswith('##') or 'Node' in n})
    scene.add(f'FNV {label} ({stem} f{frame})', 'fnv', worlds[VIEWS[0].camera[0]], meshes, marks)
    return True


def with_helpers(worlds: dict, skeleton_nif: bytes) -> dict:
    """`worlds` ({bone: 4x4}) plus every node of skeleton NIF `skeleton_nif` it lacks (skin helpers the animated
    skeleton leaves out), each at its rest offset from its posed parent."""
    nif = nif_file.read(skeleton_nif)
    out = dict(worlds)
    stack = [(0, np.eye(4))]
    while stack:
        index, parent = stack.pop()
        block = nif.blocks[index][1]
        if not isinstance(block, dict) or 'children' not in block:
            continue
        name = nif.strings[block['name']]
        here = out.setdefault(name, gun.node_matrix(block) @ parent) if index else parent
        stack += [(c, here) for c in block['children'] if c >= 0]
    return out


def fo4_group(scene: Scene, label: str, anim, archives: Archives, gun_nif: bytes, frame: int) -> None:
    """FO4's pose at `frame` of clip `anim` (parsed hkx) holding `gun_nif` into `scene` as group `label`."""
    skeleton = fo4_skeleton(archives.read(VIEWS[0].skeleton))[0]
    world = vanilla_worlds(anim, skeleton, min(frame, anim.num_frames - 1))
    worlds = with_helpers({n: world[i] for i, n in enumerate(skeleton.names)},
                          archives.read(VIEWS[0].skeleton[:-len('.hkx')] + '.nif'))
    held = worlds[WEAPON]
    meshes = [(n, 'gun', (_homogeneous(v) @ held)[:, :3], t) for n, v, t in shapes(nif_file.read(gun_nif))]
    for path in FO4_ARMS:
        meshes += [(n, 'arms', v, t) for n, v, t in fo4_skinned(archives.read('meshes' + B + path.replace('/', B)), worlds)]
    marks = {n: worlds[n][3, :3] for n in FO4_MARKS}
    marks[WEAPON] = held[3, :3]
    scene.add(label, 'fo4', worlds[VIEWS[0].camera[1]], meshes, marks)


def vanilla_anim(archives: Archives, folder: str, clip: str) -> tuple:
    """(the name read, parsed clip) of vanilla first-person clip `clip` in animation folder `folder`, else of the
    first of HELD_FROM that parses (the parser reads spline clips only); (None, None) without one."""
    root = B.join(('meshes', 'actors', 'character', '_1stperson', 'animations', folder, ''))
    for name in (clip.lower(), *HELD_FROM):
        raw = archives.read(root + name + '.hkx')
        anim = parse_fo4_animation(raw) if raw else None
        if anim:
            return name, anim
    return None, None


def build(args) -> Scene:
    """The scene of args' gun, one FNV, ours and (with --vanilla) vanilla group per --pair."""
    rec = next(r for r in parse_export_file(str(EXPORT / 'WEAP.txt')) if r.get('EditorID') == args.gun)
    cls = ANIM_TYPE_CLASS[int(rec['DNAM.FalloutAnimType'])]
    archives = Archives(FALLOUT4_DIR / 'Data')
    folder, vanilla_gun = args.vanilla.split(':', 1) if args.vanilla else (None, None)
    ours_gun = (args.data / 'Meshes' / 'fnv' / (rec['Model.MODL'].replace(B + B, '/').replace(B, '/').lower()[:-4]
                                                 + GUN_SUFFIX)).read_bytes()
    theirs_gun = archives.read('meshes' + B + vanilla_gun.replace('/', B).lower()) if vanilla_gun else None
    clips = args.data / 'Meshes' / VIEWS[0].folder.replace(B, '/') / args.gun
    scene, shown = Scene(), set()
    for pair in args.pair:
        clip, suffix = pair.split('=')
        fnv_group(scene, clip, cls + suffix, rec, args.frame)
        ours = clips / f'{clip}.hkx'
        if ours.is_file():
            fo4_group(scene, f'ours {clip} f{args.frame}', parse_fo4_animation(ours.read_bytes()), archives,
                      ours_gun, args.frame)
        name, anim = vanilla_anim(archives, folder, clip) if folder else (None, None)
        if anim and name not in shown:
            shown.add(name)
            fo4_group(scene, f'vanilla {clip} ({name} f{args.frame})', anim, archives, theirs_gun, args.frame)
    return scene


def sheet(folder: Path) -> Path:
    """<folder>/sheet.png: blender_pose_scene's renders in `folder`, one row per group (VIEWS_RENDERED), each
    labeled, at half size."""
    rows = sorted({p.stem.rsplit(' ', 1)[0] for p in folder.glob('* view.png')})
    tiles = [[Image.open(folder / f'{row} {label}.png').convert('RGB') for label in VIEWS_RENDERED] for row in rows]
    w, h = tiles[0][0].width // 2, tiles[0][0].height // 2
    out = Image.new('RGB', (w * len(VIEWS_RENDERED), h * len(rows)))
    draw = ImageDraw.Draw(out)
    for r, (row, pair) in enumerate(zip(rows, tiles)):
        for c, tile in enumerate(pair):
            out.paste(tile.resize((w, h)), (c * w, r * h))
        draw.text((8, r * h + 8), row, fill=(255, 255, 0))
    path = folder / 'sheet.png'
    out.save(path)
    return path


def main() -> None:
    """Write the scene JSON and list its groups, or with --sheet stitch a render folder."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--sheet', type=Path, help='only stitch this blender_pose_scene render folder into sheet.png')
    parser.add_argument('gun', nargs='?', help='FNV WEAP EditorID')
    parser.add_argument('--data', type=Path, help='the mod folder the build wrote (Meshes/...)')
    parser.add_argument('--vanilla', help='<template animation folder>:<template gun NIF under Meshes>')
    parser.add_argument('--pair', nargs='+', default=['WPNIdleReady=aim', 'WPNIdleSighted=aimis'],
                        help='<FO4 clip>=<FNV clip suffix after the class>')
    parser.add_argument('--frame', type=int, default=0)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.sheet:
        print('wrote', sheet(args.sheet))
        return
    if not (args.gun and args.data and args.out):
        parser.error('gun, --data and --out are needed without --sheet')
    scene = build(args)
    args.out.write_text(json.dumps(scene.groups), encoding='utf-8')
    for name, group in scene.groups.items():
        print(f'{name}: {len(group["meshes"])} meshes, {sum(len(m["verts"]) for m in group["meshes"])} vertices')
    print('wrote', args.out)


if __name__ == '__main__':
    main()
