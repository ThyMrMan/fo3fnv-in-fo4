"""Convert FNV guns' first-person clips and meshes the way the build does, without a build, and measure each hold.

    py -3.14 -m tools.nif.gun_quick_convert WeapFlamer WeapTeslaCannon --out <dir>
    py -3.14 -m tools.nif.gun_quick_convert --all --out <dir> [--report report.tsv]

Guns the default chart keeps on an FO4 gun of their own (not "as": "fnv") are skipped unless --template is given.
Each gun goes on the FO4 gun its default chart entry names (replacements.json, a Fallout4.esm target), else on
the one the build's own choice picks (gun_choice), and is written under <dir> as the build writes it
(Meshes/fnv/<model>_gun.nif, the first-person clips under Meshes/Actors/FNV/...), so gun_pose_scene.py can view
it with --data <dir>. Per gun it prints the template, whether the hold was moved for being off screen, how much
of the gun is on FO4's screen in WPNIdleReady's first frame and how far the left middle finger's base is from it.
See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import argparse
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from asset_convert.havok.gun_vocabulary_falloutnv import ANIM_TYPE_CLASS
from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.havok.gun_clips import (FO4_VIEW_FOV, GRIP_FINGER, VIEW_ASPECT, VIEWS, WEAPON, GunClips,
                                        fo4_skeleton, vanilla_worlds)
from fo4_import.nif import file as nif_file
from fo4_import.nif import gun
from fo4_import.spike import replacements
from fo4_import.spike.guns import GUN_SUFFIX, Guns
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.text_reader import parse_export_file
from tools.nif.gun_pose_scene import FO4_ARMS, fo4_skinned, shapes, with_helpers

B = chr(92)
EXPORT = Path('export/FalloutNV.esm')
#: The right hand bone and the reach from it counted as hand and wrist (aim_hand).
HAND, HAND_REACH = 'RArm_Hand', 9.0
#: How much wider a 16:9 screen sees than the 4:3 one FO4's first-person FOV is taken as measured on.
WIDE = (16 / 9) / (4 / 3)
#: FNV WEAP DNAM.Flags1's Non-Playable bit (creature and turret guns).
NON_PLAYABLE = 0x80


def builder() -> SimpleNamespace:
    """What Guns reads of the build: Fallout4.esm, its keywords, the export."""
    fo4 = FALLOUT4_ESM.read_bytes()
    keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id for r, _ in walk(fo4, b'KYWD')}
    return SimpleNamespace(fo4=fo4, keywords=keywords, export_dir=EXPORT)


def gun_records(names: list) -> list:
    """The export's playable FNV guns of a clip class with a model; those in `names` when it is given."""
    out = []
    for rec in parse_export_file(str(EXPORT / 'WEAP.txt')):
        if names and rec.get('EditorID') not in names:
            continue
        playable = not int(rec.get('DNAM.Flags1', 0)) & NON_PLAYABLE
        if rec.get('Model.MODL') and int(rec.get('DNAM.FalloutAnimType', -1)) in ANIM_TYPE_CLASS and playable:
            out.append(rec)
    return out


def model_path(rec: dict) -> str:
    """FNV gun `rec`'s model path, forward slashes, lower case."""
    return rec['Model.MODL'].replace(B + B, '/').replace(B, '/').lower()


def convert(guns: Guns, clips: GunClips, rec: dict, only: tuple, out: Path) -> 'tuple | None':
    """FNV gun `rec` on `only` (FO4 gun or None for the build's choice, parts) written under `out`: (the template's EditorID,
    the conversion: gun_clips.Converted, None when its clips do not convert); None without a template."""
    chosen = guns.choose(rec, *only)
    if chosen is None:
        return None
    choice, subs, (_, fnv_path, static, nodes, _) = chosen
    receiver = Archives(FALLOUT4_DIR / 'Data').read('meshes' + B + choice.model.lower())
    matrix = gun.placement(static, nodes, receiver)
    made = gun.gun(static, nodes, receiver, matrix)
    mesh = out / 'Meshes' / 'fnv' / (model_path(rec)[:-4] + GUN_SUFFIX)
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_bytes(made)
    result = clips.convert(rec, guns.choices.clip_keywords(subs, choice.includes), lambda old: old, fnv_path,
                           gun.receiver_bones(receiver), matrix,
                           (gun.pieces(made), gun.pieces(receiver)))
    return choice.weapon, result


def hold(out: Path, rec: dict, skeleton) -> 'tuple | None':
    """(the share of the gun on FO4's screen, the left middle finger base's distance to it) in our
    WPNIdleReady's first frame under `out`; None without the clip."""
    clip = out / 'Meshes' / VIEWS[0].folder.replace(B, '/') / rec['EditorID'] / 'WPNIdleReady.hkx'
    if not clip.is_file():
        return None
    world = vanilla_worlds(parse_fo4_animation(clip.read_bytes()), skeleton, 0)
    raw = (out / 'Meshes' / 'fnv' / (model_path(rec)[:-4] + GUN_SUFFIX)).read_bytes()
    points = np.vstack([v for _, v, _ in shapes(nif_file.read(raw))])
    placed = np.hstack([points, np.ones((len(points), 1))]) @ world[skeleton.index[WEAPON]]
    seen = placed @ np.linalg.inv(world[skeleton.index[VIEWS[0].camera[1]]])
    ahead, across = -seen[:, 2], math.tan(math.radians(FO4_VIEW_FOV / 2))
    inside = (ahead > 0) & (np.abs(seen[:, 0]) < ahead * across) & (np.abs(seen[:, 1]) < ahead * across * VIEW_ASPECT)
    finger = world[skeleton.index[GRIP_FINGER]][3, :3]
    return float(inside.mean()), float(np.linalg.norm(placed[:, :3] - finger, axis=1).min())


def aim_hand(out: Path, rec: dict, rig: tuple, lift: float) -> 'float | None':
    """The share of the right hand's (and wrist's) vertices on a 16:9 screen (FO4's first-person FOV taken as
    measured on 4:3: 96 degrees across) in our WPNIdleSighted's first frame under `out`, the camera moved by
    the aiming `lift`; `rig`: (skeleton, skeleton NIF bytes, arm NIF bytes); None without the clip.
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    clip = out / 'Meshes' / VIEWS[0].folder.replace(B, '/') / rec['EditorID'] / 'WPNIdleSighted.hkx'
    if not clip.is_file():
        return None
    skeleton, skeleton_nif, arms = rig
    world = vanilla_worlds(parse_fo4_animation(clip.read_bytes()), skeleton, 0)
    worlds = with_helpers({n: world[i] for i, n in enumerate(skeleton.names)}, skeleton_nif)
    hand = worlds[HAND][3, :3]
    verts = np.vstack([v for raw in arms for _, v, _ in fo4_skinned(raw, worlds)])
    near = verts[np.linalg.norm(verts - hand, axis=1) < HAND_REACH]
    seen = (np.hstack([near, np.ones((len(near), 1))]) @ np.linalg.inv(worlds[VIEWS[0].camera[1]]))[:, :3]
    seen[:, 1] -= lift
    ahead = -seen[:, 2]
    across = math.tan(math.radians(FO4_VIEW_FOV / 2)) * WIDE
    inside = (ahead > 0) & (np.abs(seen[:, 0]) < ahead * across) & (np.abs(seen[:, 1]) < ahead * across * VIEW_ASPECT)
    return float(inside.mean())


def report(guns: Guns, clips: GunClips, rec: dict, only: tuple, out: Path, rig: tuple) -> list:
    """Convert FNV gun `rec` on `only` and measure it: [EditorID, class, template, moved, on screen, left gap,
    right hand on screen while aiming]."""
    made = convert(guns, clips, rec, only, out)
    done = made and made[1]
    measured = hold(out, rec, rig[0]) if done else None
    aiming = aim_hand(out, rec, rig, made[1].lift or 0.0) if done else None
    return [rec['EditorID'], ANIM_TYPE_CLASS[int(rec['DNAM.FalloutAnimType'])], made[0] if made else '-',
            'yes' if done and made[1].moved else 'no', f'{measured[0]:.0%}' if measured else '-',
            f'{measured[1]:.1f}' if measured else '-', f'{aiming:.0%}' if aiming is not None else '-']


def main() -> None:
    """Convert the named (or --all) guns and print one line each; with --report also write them as TSV."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('guns', nargs='*', help='FNV WEAP EditorIDs')
    parser.add_argument('--all', action='store_true', help="every playable FNV gun of a clip class")
    parser.add_argument('--template', help='FO4 WEAP EditorID to build on, for every gun named')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if not args.guns and not args.all:
        parser.error('name guns or pass --all')
    table, base, data = replacements.load(), builder(), Archives(FALLOUT4_DIR / 'Data')
    guns, clips = Guns(base, {}), GunClips(base.fo4, EXPORT / 'meshes', args.out)
    rig = (fo4_skeleton(data.read(VIEWS[0].skeleton))[0], data.read(VIEWS[0].skeleton[:-len('.hkx')] + '.nif'),
           [data.read('meshes' + B + p.replace('/', B)) for p in FO4_ARMS])
    rows = ['\t'.join(('gun', 'class', 'template', 'moved', 'on_screen', 'left_gap', 'aim_hand'))]
    for rec in gun_records(args.guns):
        entry = table.get(rec['EditorID'])
        if entry and entry.mode != 'fnv' and not args.template:
            continue
        only = (args.template, ()) if args.template else (entry.edid, entry.mods) if entry and entry.base else (None, ())
        fields = report(guns, clips, rec, only, args.out, rig)
        rows.append('\t'.join(fields))
        print('  '.join(f'{f:<24}' if i == 0 else f'{f:<14}' for i, f in enumerate(fields)), flush=True)
    if args.report:
        args.report.write_text('\n'.join(rows) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
