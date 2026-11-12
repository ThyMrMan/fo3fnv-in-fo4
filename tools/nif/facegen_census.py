"""Our FaceGeom vertex positions (face_bones sculpt) against the Creation Kit's export, for every NPC it exported.

Reads a reference folder that holds the plugin the CK read and its FaceGeom NIFs
(Meshes\\Actors\\Character\\FaceGenData\\FaceGeom\\<plugin>\\<id>.nif). Each NPC's head parts get their positions as
facegeom.build gives them; per part it records the vertex count, our max and RMS distance to the CK's, the distance
with no sculpt, and whether a sculpt applied. One JSON line per NPC goes to --out as it is measured, then the
spread and the worst NPCs are printed. --summary reprints them from an existing --out.

Usage:
  python -m tools.nif.facegen_census --ref temp/ck_facegen_reference_2026-11-12 --dirs <loose files> --out <jsonl>
  python -m tools.nif.facegen_census --summary <jsonl>

See: docs/fork/fo4_facegen_plan.md#sculpt-census
"""

import argparse
import json
import multiprocessing
import os
import struct
from pathlib import Path

import numpy as np

from fo4_import.face import facegeom
from fo4_import.face.bake import positions
from fo4_import.face.face_bones import Sculpt
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import pack_tri_shape

#: Max-error buckets (FO4 units) the summary counts NPCs into.
BUCKETS = (0.005, 0.05, 0.1, 0.5, 1.0)
#: Worst NPCs, and head parts (by their worst error), the summary lists.
WORST, PARTS = 20, 40
STATE = {}


def ck_files(ref: Path, plugin: str) -> list:
    """[(local form id, path)] of every FaceGeom NIF the CK wrote for `plugin` under `ref`."""
    root = next((p for p in ref.rglob('FaceGeom') if p.is_dir()), None)
    folder = next((d for d in root.iterdir() if d.name.lower() == plugin.lower()), None) if root else None
    files = sorted(folder.glob('*.nif')) if folder else []
    return [(int(f.stem, 16) & 0xFFFFFF, f) for f in files]


def shape_points(nif) -> dict:
    """{shape name: positions} of a NIF's shapes."""
    out = {}
    for kind, b in nif.blocks:
        if kind in facegeom.SHAPES:
            name = b['name'] if isinstance(b, dict) else struct.unpack_from('<i', b)[0]
            out[nif.strings[name]] = positions(b if isinstance(b, bytes) else pack_tri_shape(b))
    return out


def _init(plugin: Path, dirs: list) -> None:
    """Worker set-up: one Sources per process."""
    STATE['src'], STATE['plugin'] = facegeom.Sources(plugin, dirs), plugin.name


def _distance(a: np.ndarray, b: np.ndarray) -> tuple:
    """(max, RMS) of the per-vertex distances."""
    e = np.linalg.norm(a - b, axis=1)
    return round(float(e.max()), 5), round(float(np.sqrt((e ** 2).mean())), 5)


def part_row(src, sculpt: Sculpt, part, ck: dict) -> tuple:
    """(part EDID, row) of one head part: [vertex count, max, RMS, unsculpted max, sculpted] or a status text."""
    name, model = facegeom.zstr(part.first(b'EDID')), facegeom.zstr(part.first(b'MODL'))
    if name not in ck:
        return name, 'not in the CK file'
    own = positions(facegeom.Shape.of(nif_file.read(src.read('meshes\\' + model))).pack())
    if len(own) != len(ck[name]):
        return name, f'{len(own)} vertices, the CK {len(ck[name])}'
    moved = sculpt.positions(model, len(own))
    ours = own if moved is None else moved
    return name, [len(own), *_distance(ours, ck[name]), _distance(own, ck[name])[0], moved is not None]


def measure(item: tuple) -> dict:
    """One NPC's census line (or its error)."""
    form, path = item
    src = STATE['src']
    line = {'form': f'{form:06X}'}
    try:
        npc, race, female, _ = facegeom.npc_face(src, STATE['plugin'], form)
        line.update(edid=facegeom.zstr(npc.first(b'EDID', b'\0')), race=facegeom.zstr(race.first(b'EDID', b'\0')),
                    female=female)
        sculpt, ck = Sculpt(src, npc, female), shape_points(nif_file.read(path.read_bytes()))
        parts = facegeom.head_parts(src, npc, race, female)
        line['parts'] = dict(part_row(src, sculpt, part, ck) for part in parts)
        line['ck_only'] = sorted(set(ck) - set(line['parts']))
    except (KeyError, ValueError, StopIteration, struct.error) as e:
        line['error'] = f'{type(e).__name__}: {e}'
    return line


def worst_part(line: dict) -> tuple:
    """(max error, part) over a line's measured parts; (-1, '') when none was measured."""
    rows = [(row[1], name) for name, row in line.get('parts', {}).items() if isinstance(row, list)]
    return max(rows, default=(-1.0, ''))


def by_part(lines: list) -> None:
    """Print, per head part, its NPC count and the median and worst of our max error and of the unsculpted one."""
    rows = {}
    for ln in lines:
        for name, row in ln.get('parts', {}).items():
            if isinstance(row, list):
                rows.setdefault(name, []).append(row)
    print(f"  {'part':34s} {'NPCs':>5s} {'median':>7s} {'worst':>7s} {'unsculpted median':>18s} {'worst':>7s}")
    for name, got in sorted(rows.items(), key=lambda kv: -max(r[1] for r in kv[1]))[:PARTS]:
        ours, raw = np.array([r[1] for r in got]), np.array([r[3] for r in got])
        print(f'  {name:34s} {len(got):5d} {np.median(ours):7.4f} {ours.max():7.4f} {np.median(raw):18.4f} {raw.max():7.4f}')


def summary(lines: list) -> None:
    """Print the spread of per-NPC max error, the status counts and the worst NPCs."""
    errors = [ln for ln in lines if 'error' in ln]
    statuses = {}
    for ln in lines:
        for row in ln.get('parts', {}).values():
            if not isinstance(row, list):
                key = row.split(',')[0] if 'vertices' not in row else 'vertex count differs'
                statuses[key] = statuses.get(key, 0) + 1
    worst = sorted(((worst_part(ln), ln) for ln in lines if 'error' not in ln), key=lambda t: -t[0][0])
    measured = [w for (w, _), _ in worst if w >= 0]
    print(f'NPCs {len(lines)}, errors {len(errors)}, measured {len(measured)}; part statuses {statuses}')
    edges = (0.0,) + BUCKETS + (float('inf'),)
    for lo, hi in zip(edges, edges[1:]):
        print(f'  max error [{lo}, {hi}): {sum(lo <= w < hi for w in measured)}')
    for (w, part), ln in worst[:WORST]:
        print(f"  {ln['form']} {ln.get('edid', '')} ({ln.get('race', '')}) {part}: {ln['parts'][part]}")
    for ln in errors[:WORST]:
        print(f"  error {ln['form']}: {ln['error']}")
    by_part(lines)


def run(args) -> list:
    """Measure every CK FaceGeom under --ref (up to --max), writing lines to --out as they come."""
    plugin = args.plugin or next(args.ref.glob('*.es[mp]'))
    items = ck_files(args.ref, plugin.name)[:args.max or None]
    print(f'{len(items)} CK FaceGeom files for {plugin.name}', flush=True)
    lines = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w') as out, multiprocessing.Pool(args.workers, _init, (plugin, [args.ref, *args.dirs])) as pool:
        for i, line in enumerate(pool.imap_unordered(measure, items, chunksize=8), 1):
            out.write(json.dumps(line) + '\n')
            lines.append(line)
            if i % 200 == 0:
                out.flush()
                print(f'  {i}/{len(items)}', flush=True)
    return lines


def main(argv=None) -> None:
    """Run the census, or with --summary reprint one."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--ref', type=Path, help='folder with the plugin the CK read and its FaceGeom NIFs')
    p.add_argument('--plugin', type=Path, help='the plugin (default: the first .esm/.esp in --ref)')
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='more folders of masters, loose files and BA2s')
    p.add_argument('--out', type=Path, help='JSON lines written as NPCs are measured')
    p.add_argument('--max', type=int, default=0, help='measure only the first N NPCs')
    p.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument('--summary', type=Path, help='reprint the summary of an existing --out')
    args = p.parse_args(argv)
    if args.summary:
        summary([json.loads(x) for x in args.summary.read_text().splitlines() if x.strip()])
        return
    summary(run(args))


if __name__ == '__main__':
    main()
