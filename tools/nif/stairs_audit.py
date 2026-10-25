"""Census of FNV mesh collision through the FO4 stairs pass: which meshes still hold steps FO4's character may
not climb, ranked by how often the export places them.

    py -3.14 -m tools.nif.stairs_audit [--export DIR] [--out FILE] [--max N] [--workers N] [folder under meshes/ ...]

Per collision body (as fo4_import.nif.collision converts it: repaired soup, stairs()), in game units:

- open foot: a stair-helper ramp whose foot stands more than OPEN_FOOT above the mesh's lowest point (the
  flight's first steps are another reference's, as UtlCatStairsHalfTop's);
- tall risers: a step stairs() left plain, PLAIN_MAX to CLIMBED tall (Novac motel's 16-unit riser): an upright
  face whose top corners meet an unmarked tread's and whose bottom ones a tread's or the ground;
- over max: such a step taller than CLIMBED, up to LEDGE (a ledge, or a step FO4 refuses);
- flights: ramps built, for scale.

The report lists each category's totals, then its meshes, most placed first.

See: docs/fork/fo4_pipeline.md#stairs-audit
"""

import argparse
import collections
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from asset_convert.collision.collision import repaired_mesh_soup
from asset_convert.nif.pyffi_monkey_patch import apply_patches
from fo4_import.nif import stairs as S
from fo4_import.nif.collision import GAME_PER_HAVOK, repair_oracle, stairs_material, triangle_materials
from fo4_import.pipeline.export_index import export_records
from pyffi.formats.nif import NifFormat

#: A plain step at least this tall (game units) stops FO4's character (stairs.py's module notes).
PLAIN_MAX = 16.0
#: Tallest step FO4's character is known to climb: utlcatstairsfull01's 26.3 floor step (played 2026-10-25).
CLIMBED = 28.0
#: Tallest face counted as a step rather than a wall.
LEDGE = 40.0
#: Foot height above the mesh's lowest point that counts as open: full01's one-step 26.3 is not, HalfTop's 48 is.
OPEN_FOOT = 32.0
#: |normal z| from which a face is walkable ground or ramp (50 degrees; Novac motel's stairs ramp is 38).
WALKABLE = 0.64
#: Mesh collision blocks: a NIF holding none goes through no stairs pass.
MESH_BLOCKS = (b'hkPackedNiTriStripsData', b'bhkNiTriStripsShape', b'bhkCompressedMeshShape')
#: Record types whose model the export places with REFRs.
PLACED = ('STAT', 'MSTT', 'FURN', 'ACTI', 'DOOR', 'CONT', 'TACT')
CATEGORIES = ('open_foot', 'tall_risers', 'over_max', 'flights')


def body_counts(tris: list, materials: list) -> dict:
    """{category: count} of one collision body's triangles (Havok units) and their materials; 'foot' the highest
    ramp foot above the mesh's lowest point."""
    _, marks, ramps = S.stairs(tris, materials, GAME_PER_HAVOK, stairs_material)
    corners, nz = S.faces(tris, GAME_PER_HAVOK)
    plain = np.array([a == b for a, b in zip(materials, marks[:len(materials)])])
    base = corners[:, :, 2].min()
    heights = _step_heights(corners, nz, plain, base)
    feet = [float(r[0][0][2] * GAME_PER_HAVOK - base) for r in ramps]
    return {'flights': len(ramps), 'open_foot': sum(1 for gap in feet if gap > OPEN_FOOT),
            'tall_risers': int(((heights >= PLAIN_MAX - S.TOUCH) & (heights <= CLIMBED)).sum()),
            'over_max': int(((heights > CLIMBED) & (heights <= LEDGE)).sum()), 'foot': max(feet, default=0.0)}


def _step_heights(corners: np.ndarray, nz: np.ndarray, plain: np.ndarray, base: float) -> np.ndarray:
    """Per face, the height of the plain step it is (0 for none): an upright face whose top corners each meet a
    walkable face's (a tread or a ramp up to WALKABLE), none of them marked stairs, and whose bottom corners each
    meet a walkable face's or the ground (`base`)."""
    walk = np.nonzero(nz >= WALKABLE)[0]
    out = np.zeros(len(corners))
    marked = np.repeat(~plain[walk], 3)
    if not len(walk):
        return out
    points = corners[walk].reshape(-1, 3)
    tree = cKDTree(points)
    stairs_tree = cKDTree(points[marked]) if marked.any() else None
    for i in np.nonzero(nz <= S.VERTICAL)[0]:
        z = corners[i, :, 2]
        high, low = z.max(), z.min()
        top, bottom = corners[i][z >= high - S.TOUCH], corners[i][z <= low + S.TOUCH]
        if high - low <= S.TOUCH or not all(tree.query(v)[0] <= S.TOUCH for v in top):
            continue
        on_stairs = stairs_tree is not None and any(stairs_tree.query(v)[0] <= S.TOUCH for v in top)
        grounded = low <= base + S.TOUCH or all(tree.query(v)[0] <= S.TOUCH for v in bottom)
        out[i] = high - low if grounded and not on_stairs else 0.0
    return out


def mesh_counts(path: str) -> 'tuple | None':
    """(path, {category: count summed over its collision bodies}) of one FNV NIF, or None without mesh collision."""
    raw = Path(path).read_bytes()
    if not any(b in raw for b in MESH_BLOCKS):
        return None
    apply_patches()
    data = NifFormat.Data()
    try:
        with open(path, 'rb') as f:
            data.read(f)
    except Exception:
        return None
    total = collections.Counter()
    root = data.roots[0]
    for node in root.tree():
        body = getattr(getattr(node, 'collision_object', None), 'body', None)
        soup = repaired_mesh_soup(body, node, triangle_materials, repair_oracle(root, node)) if body else None
        if soup and soup != 'drop' and soup[0]:
            counts = body_counts(soup[0], soup[1])
            total['foot'] = max(total['foot'], counts.pop('foot'))
            total.update(counts)
    return (path, dict(total)) if total else None


def placements(export: Path) -> collections.Counter:
    """{lowercase model path under meshes/: REFRs placing it} over the export."""
    model = {}
    for sig in PLACED:
        for rec in export_records(export, sig):
            if rec.get('Model.MODL'):
                model[rec['FormID']] = rec['Model.MODL'].lower().replace('/', '\\')
    return collections.Counter(model[r['NAME']] for r in export_records(export, 'REFR') if r.get('NAME') in model)


def report(rows: list, placed: collections.Counter, meshes: Path) -> str:
    """The report text: per category its meshes and placements, then its meshes most placed first."""
    def uses(path):
        """How often the export places mesh `path`."""
        return placed[str(Path(path).relative_to(meshes)).lower()]
    lines = [f'{len(rows)} meshes with mesh collision', '']
    for cat in CATEGORIES:
        hit = [r for r in rows if r[1].get(cat)]
        lines.append(f'{cat}: {len(hit)} meshes, {sum(uses(p) for p, _ in hit)} placements')
    for cat in CATEGORIES[:-1]:
        lines += ['', f'== {cat} (placements, count, highest ramp foot, mesh)']
        for path, counts in sorted((r for r in rows if r[1].get(cat)), key=lambda r: -uses(r[0])):
            lines.append(f'{uses(path):6} {counts[cat]:5} {counts.get("foot", 0):6.0f}  {Path(path).relative_to(meshes)}')
    return '\n'.join(lines) + '\n'


def main():
    """Count every FNV mesh in a pool, printing as it goes; write the report."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', type=Path, default=Path('export/FalloutNV.esm'))
    ap.add_argument('--out', type=Path, default=Path('temp/stairs_audit.txt'))
    ap.add_argument('--max', type=int, default=0, help='Only the first N meshes (0: all)')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('folders', nargs='*', default=['.'], help='Folders under meshes/ to count (default: all)')
    args = ap.parse_args()
    meshes = args.export / 'meshes'
    paths = sorted({str(p) for folder in args.folders for p in (meshes / folder).rglob('*.nif')})[:args.max or None]
    rows = []
    with ProcessPoolExecutor(args.workers) as pool:
        for row in pool.map(mesh_counts, paths, chunksize=16):
            if row:
                rows.append(row)
                print(Path(row[0]).relative_to(meshes), row[1], flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report(rows, placements(args.export), meshes), encoding='utf-8')
    print('wrote', args.out, file=sys.stderr)


if __name__ == '__main__':
    main()
