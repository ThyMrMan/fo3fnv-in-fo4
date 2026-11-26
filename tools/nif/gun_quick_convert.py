"""Convert FNV guns' first-person clips and meshes the way the build does, without a build, and measure each hold.

    py -3.14 -m tools.nif.gun_quick_convert WeapFlamer WeapTeslaCannon --out <dir>
    py -3.14 -m tools.nif.gun_quick_convert --all --out <dir> [--report report.tsv] [--export export/Fallout3.esm]

Guns the default chart keeps on an FO4 gun of their own (not "as": "fnv") are skipped unless --template is given.
Each gun goes on the FO4 gun its default chart entry names (replacements.json, a Fallout4.esm target), else on
the one the build's own choice picks (gun_choice), and is written under <dir> as the build writes it
(Meshes/fnv/<model>_<editorid>_gun.nif, the first-person clips under Meshes/Actors/FNV/...), so gun_pose_scene.py can view
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
from fo4_import.havok.gun_clips import FO4_VIEW_FOV, GRIP_FINGER, VIEW_ASPECT, VIEWS, WEAPON, GunClips, vanilla_worlds
from fo4_import.havok.gun_view import Arms, shapes
from fo4_import.nif import file as nif_file
from fo4_import.nif import gun
from fo4_import.spike import replacements
from fo4_import.spike.guns import Guns, gun_mesh
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.text_reader import parse_export_file

B = chr(92)
EXPORT = Path('export/FalloutNV.esm')
#: FNV WEAP DNAM.Flags1's Non-Playable bit (creature and turret guns).
NON_PLAYABLE = 0x80


def builder(export: Path) -> SimpleNamespace:
    """What Guns reads of the build: Fallout4.esm, its keywords, `export`."""
    fo4 = FALLOUT4_ESM.read_bytes()
    keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id for r, _ in walk(fo4, b'KYWD')}
    return SimpleNamespace(fo4=fo4, keywords=keywords, export_dir=export)


def gun_records(export: Path, names: list) -> list:
    """`export`'s playable guns of a clip class with a model; those in `names` when it is given."""
    out = []
    for rec in parse_export_file(str(export / 'WEAP.txt')):
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
    matrix, made = gun.built(static, nodes, receiver)
    mesh = out / 'Meshes' / 'fnv' / gun_mesh(model_path(rec), rec['EditorID'])
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
    raw = (out / 'Meshes' / 'fnv' / gun_mesh(model_path(rec), rec['EditorID'])).read_bytes()
    points = np.vstack([v for _, v, _ in shapes(nif_file.read(raw))])
    placed = np.hstack([points, np.ones((len(points), 1))]) @ world[skeleton.index[WEAPON]]
    seen = placed @ np.linalg.inv(world[skeleton.index[VIEWS[0].camera[1]]])
    ahead, across = -seen[:, 2], math.tan(math.radians(FO4_VIEW_FOV / 2))
    inside = (ahead > 0) & (np.abs(seen[:, 0]) < ahead * across) & (np.abs(seen[:, 1]) < ahead * across * VIEW_ASPECT)
    finger = world[skeleton.index[GRIP_FINGER]][3, :3]
    return float(inside.mean()), float(np.linalg.norm(placed[:, :3] - finger, axis=1).min())


def aim_hand(out: Path, rec: dict, arms: Arms, lift: float) -> 'float | None':
    """Arms.hand_share of our WPNIdleSighted under `out`; None without it."""
    clip = out / 'Meshes' / VIEWS[0].folder.replace(B, '/') / rec['EditorID'] / 'WPNIdleSighted.hkx'
    return arms.hand_share(clip.read_bytes(), lift) if clip.is_file() else None


def report(guns: Guns, clips: GunClips, rec: dict, only: tuple, out: Path, arms: Arms) -> list:
    """Convert FNV gun `rec` on `only` and measure it: [EditorID, class, template, moved, on screen, left gap,
    right hand on screen while aiming]."""
    made = convert(guns, clips, rec, only, out)
    done = made and made[1]
    measured = hold(out, rec, arms.skeleton) if done else None
    aiming = aim_hand(out, rec, arms, made[1].lift or 0.0) if done else None
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
    parser.add_argument('--export', type=Path, default=EXPORT, help='the FNV or FO3 export folder')
    args = parser.parse_args()
    if not args.guns and not args.all:
        parser.error('name guns or pass --all')
    table, base, data = replacements.load(), builder(args.export), Archives(FALLOUT4_DIR / 'Data')
    guns, clips = Guns(base, {}), GunClips(base.fo4, args.export / 'meshes', args.out)
    rig = Arms(data.read)
    rows = ['\t'.join(('gun', 'class', 'template', 'moved', 'on_screen', 'left_gap', 'aim_hand'))]
    for rec in gun_records(args.export, args.guns):
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
