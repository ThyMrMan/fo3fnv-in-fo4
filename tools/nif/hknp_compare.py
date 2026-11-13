"""Compare our FO4 physics writer (fo4_import/nif/hknp_write.py) with Elric's, field by field.

    py -3.14 -m tools.nif.hknp_compare --export export/FalloutNV.esm [--cache DIR] [--max N] [--workers N]
        [--tolerance 1e-4] [--json OUT] [--show N] [--pre-elric] <mesh or folder> ...

Each argument is an FNV mesh or folder (a path, or one under the export's
meshes/), converted as the build converts it; with --pre-elric, a pre-Elric
NIF read as it is. A pair is that pre-Elric NIF and Elric's output for it
from the Elric cache (`--cache`, default the build's), so Elric never runs.
Both physics systems are walked from their root, pointers followed, so
object names and order do not matter; a convex shape's hull is compared as
a set of corners and faces matched by normal, packed mass properties
unpacked. A compressed mesh is compared as the triangles it decodes to, per
material, each corner allowed one quantization step of the coarser tree;
fields that only follow its tree layout (key bits, the two bit fields) are
left out. A compound is compared by its instances and each instance's
leaf box, without its tree's layout. Prints, per field (array indices folded), how many covered pairs
differ, with examples; --json writes each pair's differences as computed.

See: docs/fork/fo4_hknp_writer.md#check
"""

import argparse
import json
import os
import re
import struct
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from fo4_import.havok import packfile
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_mesh, hknp_write
from fo4_import.nif.elric import havok_start
from fo4_import.pipeline import elric_cache
from fo4_import.pipeline.mesh_cache import cached_files

#: Relative-array members of a convex polytope: (element size, struct format of one element).
POLYTOPE_ARRAYS = {'vertices': (16, '<3fI'), 'planes': (16, '<4f'), 'faces': (4, '<HBB'), 'indices': (1, '<B')}
#: Classes laid out as a convex polytope (vertices, planes, faces, indices after the class).
POLYTOPES = frozenset({'hknpConvexPolytopeShape', 'hknpCapsuleShape'})
#: Low bits of a polytope vertex's fourth word holding the corner index it repeats.
VERTEX_INDEX = 0xFFFFFF
#: First value of a hull difference over matched rows; the second is the largest difference.
OFF_BY = 'off by'
#: hknpCompressedMeshShape fields set by its tree's layout rather than its geometry.
TREE_LAYOUT = frozenset({'numShapeKeyBits', 'quadIsFlat', 'triangleIsInterior'})
#: The key a leaf dict is known by: a convex hull's corners, a compressed mesh's triangles.
LEAVES = frozenset({'points', 'triangles'})
#: A system's root classes, and each system block's path prefix in a comparison.
ROOTS = frozenset({'hknpPhysicsSystemData', 'hknpRagdollData'})
SYSTEMS = {'bhkPhysicsSystem': '', 'bhkRagdollSystem': 'ragdoll.'}


# ---------------------------------------------------------------------------
# Flattening a physics system
# ---------------------------------------------------------------------------

def unpack_vector(packed) -> tuple:
    """A packed mass-properties vector (3 int16, exponent word) as floats."""
    exponent = (packed[3] >> 7) - 96
    return tuple(c / 32768 * 2.0 ** exponent for c in packed[:3])


def unpack_quaternion(packed) -> tuple:
    """A packed mass-properties frame quaternion as floats."""
    return tuple(((c & 0xFFFF) - 0x8000) / 30000 for c in packed)


def hull(fields: dict, cls: str = 'hknpConvexPolytopeShape') -> dict:
    """{'points': (n, 3) distinct corners, 'faces': (f, 6) rows of normal, offset, angle byte, corner count} of a
    polytope's (class `cls`) decoded fields."""
    cl = packfile.classes()
    at = {m.name: m.offset for m in cl.members(cls)}
    base = cl.size(cls)
    tail = fields.get('__tail__', b'')
    parts = {}
    for name, (size, fmt) in POLYTOPE_ARRAYS.items():
        count, offset = fields[name]
        start = at[name] + offset - base
        parts[name] = list(struct.iter_unpack(fmt, tail[start:start + count * size]))
    corners = {w & VERTEX_INDEX: (x, y, z) for x, y, z, w in parts['vertices']}
    faces = [(*plane, angle, count) for plane, (_, count, angle) in zip(parts['planes'], parts['faces'])]
    return {'points': np.array(sorted(corners.values())).reshape(-1, 3), 'faces': np.array(faces).reshape(-1, 6)}


def mesh(tree: dict) -> dict:
    """A meshTree's decoded triangles (n, 9), their materials, its box's step."""
    tris, materials = hknp_mesh.triangles(tree)
    lo, hi = (np.array(tree['domain'][k][:3]) for k in ('min', 'max'))
    return {'triangles': tris.reshape(-1, 9), 'materials': materials, 'step': (hi - lo) / hknp_mesh.STEPS}


def _bits(value: float) -> int:
    """The bits of float32 `value`."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def leaves(tree: dict) -> list:
    """A compound tree's leaf boxes (min xyz, max xyz) in instance order, walked from its root."""
    out, todo = {}, [tree['root']]
    while todo:
        box = tree['nodes'][todo.pop()]['aabb']
        children = _bits(box['max'][3])
        if children & 0xFFFF:
            todo += [children & 0xFFFF, children >> 16]
        else:
            out[children >> 16] = (*box['min'][:3], *box['max'][:3])
    return [out[i] for i in sorted(out)]


def _compound(fields: dict) -> dict:
    """A compound shape's fields less its tree's layout (leaf nodes, min.w)."""
    elements = [{**e, 'transform': [*e['transform'][:15], None]} for e in fields['instances']['elements']]
    aabb = {'min': (*fields['aabb']['min'][:3], None), 'max': fields['aabb']['max']}
    return {**fields, 'instances': {**fields['instances'], 'elements': elements}, 'aabb': aabb}


def _object(fields: dict, cls: str) -> dict:
    """An object's fields as compared: a polytope's or capsule's arrays as its hull, a sphere's as its center, a
    compressed mesh as its triangles without its TREE_LAYOUT fields, a compound without its tree's layout,
    constraints in body order (Elric's own order is random), a skeleton's pose without its unused w lanes, packed
    mass properties unpacked."""
    if cls in ROOTS:
        return {**fields, 'constraintCinfos': sorted(fields['constraintCinfos'], key=lambda c: (c['bodyA'], c['bodyB']))}
    if cls == 'hkaSkeleton':
        return {**fields, 'referencePose': [[*p[:3], *p[4:11]] for p in fields['referencePose']]}
    if cls == 'hknpDynamicCompoundShape':
        return _compound(fields)
    if cls == 'hknpDynamicCompoundShapeData':
        tree = fields['aabbTree']
        return {'numLeaves': tree['numLeaves'], 'leaves': leaves(tree)}
    if cls == 'hknpCompressedMeshShapeData':
        return {**fields, 'meshTree': mesh(fields['meshTree'])}
    if cls == 'hknpCompressedMeshShape':
        return {k: v for k, v in fields.items() if k not in TREE_LAYOUT}
    if cls in POLYTOPES:
        kept = {k: v for k, v in fields.items() if k not in POLYTOPE_ARRAYS and k != '__tail__'}
        return {**kept, 'hull': hull(fields, cls)}
    if cls == 'hknpSphereShape':
        kept = {k: v for k, v in fields.items() if k not in ('vertices', '__tail__')}
        return {**kept, 'center': struct.unpack_from('<3f', fields['__tail__'])}
    if cls == 'hknpShapeMassProperties':
        packed = fields['compressedMassProperties']
        return {**packed, 'centerOfMass': unpack_vector(packed['centerOfMass']),
                'inertia': unpack_vector(packed['inertia']),
                'majorAxisSpace': unpack_quaternion(packed['majorAxisSpace'])}
    return fields


class _Flattener:
    """flatten()'s walk: {field path: leaf value}, every pointer followed; an object met again is a leaf naming
    the path it was first met at; a polytope's hull or a mesh's triangles is one leaf (a dict, LEAVES); an object
    of a class the layouts lack is its class alone."""

    def __init__(self, objects: list):
        """Index `objects` by name."""
        self.named = {o['#']: o for o in objects}
        self.out, self.first = {}, {}

    def pointer(self, name: str, path: str) -> None:
        """Object `name` met at `path`: walked the first time, else a leaf naming where it was."""
        if name in self.first:
            self.out[path] = f'-> {self.first[name]}'
            return
        self.first[name] = path
        target = self.named[name]
        self.out[f'{path}.class'] = target['class']
        self.walk(_object(target['fields'], target['class']), path)

    def walk(self, value, path: str) -> None:
        """Put `value`'s leaves under `path`."""
        if isinstance(value, str) and value in self.named:
            self.pointer(value, path)
        elif isinstance(value, dict) and not LEAVES & value.keys():
            for key, item in value.items():
                self.walk(item, f'{path}.{key}' if path else key)
        elif isinstance(value, list):
            self.out[f'{path}.len'] = len(value)
            for i, item in enumerate(value):
                self.walk(item, f'{path}[{i}]')
        else:
            self.out[path] = value


def flatten(objects: list) -> dict:
    """A packfile's leaves from its system root (ROOTS, _Flattener)."""
    walker = _Flattener(objects)
    walker.walk(next(o['#'] for o in objects if o['class'] in ROOTS), '')
    return walker.out


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------

def close(a, b, tolerance: float) -> bool:
    """Whether leaves `a` and `b` agree: numbers within `tolerance` relative to max(1, |b|), the rest equal."""
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        return abs(a - b) <= tolerance * max(1.0, abs(b))
    return a == b


def matched(ours: np.ndarray, theirs: np.ndarray) -> np.ndarray:
    """Per column, the largest difference between rows of `ours` and `theirs` paired by nearest first three
    columns (an optimal assignment); empty when the row counts differ."""
    if len(ours) != len(theirs) or not len(ours):
        return np.empty(0)
    cost = ((ours[:, None, :3] - theirs[None, :, :3]) ** 2).sum(-1)
    rows, cols = linear_sum_assignment(cost)
    return np.abs(ours[rows] - theirs[cols]).max(0)


def _hull_diff(path: str, ours: dict, theirs: dict, tolerance: float) -> dict:
    """The differing hull fields under `path`: corner and face counts, then corner positions, face normals,
    offsets, angle bytes and corner counts by matched rows (as OFF_BY and the largest difference)."""
    out = {}
    for part in ('points', 'faces'):
        if len(ours[part]) != len(theirs[part]):
            out[f'{path}.{part}.len'] = (len(ours[part]), len(theirs[part]))
    spread = matched(ours['points'], theirs['points'])
    if len(spread) and spread.max() > tolerance:
        out[f'{path}.points'] = (OFF_BY, float(spread.max()))
    spread = matched(ours['faces'], theirs['faces'])
    for name, columns in (('normal', slice(0, 3)), ('offset', slice(3, 4)), ('angle', slice(4, 5)),
                          ('corners', slice(5, 6))):
        if len(spread) and spread[columns].max() > (tolerance if name in ('normal', 'offset') else 0):
            out[f'{path}.faces.{name}'] = (OFF_BY, float(spread[columns].max()))
    return out


def _farthest(ours: np.ndarray, theirs: np.ndarray, allow: np.ndarray) -> float:
    """The largest amount any corner of `ours` (n, 9) passes `allow` from the nearest of `theirs` in any
    rotation (winding kept); -inf when either is empty."""
    if not len(ours) or not len(theirs):
        return -np.inf
    rolled = np.vstack([np.roll(theirs.reshape(-1, 3, 3), -k, 1).reshape(-1, 9) for k in range(3)])
    nearest = rolled[cKDTree(rolled).query(ours)[1]]
    return float((np.abs(ours - nearest) - allow).max())


def _mesh_diff(path: str, ours: dict, theirs: dict, tolerance: float) -> dict:
    """The differing mesh fields under `path`: triangle counts, overall and per material, then (OFF_BY) how far
    any corner passes one step of the coarser tree from its match of the same material, both ways."""
    out = {}
    if len(ours['triangles']) != len(theirs['triangles']):
        out[f'{path}.triangles.len'] = (len(ours['triangles']), len(theirs['triangles']))
    allow, worst = np.tile(np.maximum(ours['step'], theirs['step']), 3), -np.inf
    for material in np.union1d(ours['materials'], theirs['materials']):
        a, b = ours['triangles'][ours['materials'] == material], theirs['triangles'][theirs['materials'] == material]
        if len(a) != len(b):
            out[f'{path}.materials[{material}].len'] = (len(a), len(b))
        worst = max(worst, _farthest(a, b, allow), _farthest(b, a, allow))
    if worst > tolerance:
        out[f'{path}.triangles'] = (OFF_BY, worst)
    return out


def diff(ours: dict, theirs: dict, tolerance: float) -> dict:
    """{field path: (ours, Elric's)} of every leaf of two flatten() results that disagrees (close()); a hull's or
    mesh's differences as _hull_diff or _mesh_diff gives them, a value one side lacks as None."""
    out = {}
    for path in sorted(ours.keys() | theirs.keys()):
        a, b = ours.get(path), theirs.get(path)
        if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
            out.update((_mesh_diff if 'triangles' in a else _hull_diff)(path, a, b, tolerance))
        elif isinstance(a, dict) or isinstance(b, dict):
            out[path] = ('hull' if isinstance(a, dict) else a, 'hull' if isinstance(b, dict) else b)
        elif not close(a, b, tolerance):
            out[path] = (a, b)
    return out


def collision_objects(nif) -> list:
    """Sorted [(owner node name, lower case; flags; system block kind; body id)] of each bhkNPCollisionObject in a
    finished NIF."""
    out = []
    for kind, raw in nif.blocks:
        if kind == 'bhkNPCollisionObject':
            target, flags, system, body = struct.unpack('<iHiI', raw)
            out.append((nif.strings[nif.blocks[target][1]['name']].lower(), flags, nif.blocks[system][0], body))
    return sorted(out)


def physics(nif, kind: str = 'bhkPhysicsSystem') -> 'list | None':
    """The objects of a finished NIF's first system block of `kind`, or None."""
    block = next((raw for k, raw in nif.blocks if k == kind), None)
    known = frozenset(packfile.classes().raw)
    return None if block is None else packfile.read(block[4:], only=known).objects


def leaves_of(nif) -> dict:
    """flatten() of each system block in a finished NIF, its paths prefixed per SYSTEMS."""
    out = {}
    for kind, prefix in SYSTEMS.items():
        objects = physics(nif, kind)
        out.update({prefix + path: v for path, v in flatten(objects).items()} if objects else {})
    return out


def compare_pair(source: bytes, elric_out: bytes, tolerance: float, writer=hknp_write.finish) -> 'dict | None':
    """{field path: (ours, Elric's)} for pre-Elric NIF `source` and Elric's output for it, ours from `writer`;
    None when it does not cover it."""
    ours = writer(nif_file.read(source))
    if ours is None:
        return None
    theirs = nif_file.read(elric_out)
    found = diff(leaves_of(ours), leaves_of(theirs), tolerance)
    mine, elrics = collision_objects(ours), collision_objects(theirs)
    return found if mine == elrics else {**found, 'nif.collisionObjects': (mine, elrics)}


# ---------------------------------------------------------------------------
# Pairs
# ---------------------------------------------------------------------------

def pre_elric(path: Path, export_dir: 'Path | None') -> 'bytes | None':
    """Elric's input for `path` (converted unless no `export_dir`); None without Havok."""
    raw = path.read_bytes() if export_dir is None else cached_files(path, export_dir).nif
    nif = nif_file.read(raw)
    return None if havok_start(nif) is None else nif_file.write(nif)


def _job(path: str, export_dir: 'str | None', cache: str, tolerance: float) -> tuple:
    """(path, status, differences) of one mesh: 'no havok', 'not cached', 'elric failed', 'not covered',
    'error: ...', or 'compared' with its differences."""
    try:
        source = pre_elric(Path(path), export_dir and Path(export_dir))
        if source is None:
            return path, 'no havok', {}
        entry = elric_cache.entry(source, Path(cache))
        if not entry.is_file():
            return path, 'not cached', {}
        elric_out = entry.read_bytes()
        if not elric_out:
            return path, 'elric failed', {}
        found = compare_pair(source, elric_out, tolerance)
        return (path, 'not covered', {}) if found is None else (path, 'compared', found)
    except Exception as error:
        return path, f'error: {type(error).__name__}: {error}', {}


def meshes(args: list, export_dir: 'Path | None') -> list:
    """Every .nif named by `args` (files, or folders searched), each tried as given and under export meshes/."""
    out = []
    for arg in args:
        path = Path(arg)
        if not path.exists() and export_dir is not None:
            path = export_dir / 'meshes' / arg
        out += sorted(path.rglob('*.nif')) if path.is_dir() else [path]
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def field_kind(path: str) -> str:
    """`path` with its array indices folded, so every body's field counts as one."""
    return re.sub(r'\[\d+\]', '[]', path)


def _shown(ours, theirs) -> str:
    """One difference as a report shows it."""
    return f'off by {theirs:.4g}' if ours == OFF_BY else f'ours {ours!r:.80}  elric {theirs!r:.80}'


def summary(results: list, show: int) -> list:
    """Report lines over `results` (_job rows): status counts, pairs matching in every field, and per folded
    field the pairs differing with up to `show` examples."""
    statuses = Counter(status if not status.startswith('error') else 'error' for _, status, _ in results)
    compared = [(path, found) for path, status, found in results if status == 'compared']
    lines = [f'{n} {status}' for status, n in statuses.most_common()]
    lines.append(f'{sum(1 for _, found in compared if not found)} of {len(compared)} compared pairs match in every field')
    kinds, examples = Counter(), {}
    for path, found in compared:
        for kind in {field_kind(f) for f in found}:
            kinds[kind] += 1
            first = next(v for f, v in found.items() if field_kind(f) == kind)
            examples.setdefault(kind, []).append((Path(path).name, first))
    for kind, n in kinds.most_common():
        offs = [theirs for _, (ours, theirs) in examples[kind] if ours == OFF_BY]
        lines.append(f'  {n:5d}  {kind}' + (f'  (largest {max(offs):.4g})' if offs else ''))
        lines += [f'           {name}: {_shown(ours, theirs)}' for name, (ours, theirs) in examples[kind][:show]]
    errors = [f'  {Path(path).name}: {status}' for path, status, _ in results if status.startswith('error')]
    return lines + errors[:show * 5]


def _jsonable(value):
    """A difference value JSON can hold."""
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return value if isinstance(value, (int, float, str)) or value is None else repr(value)


def _arguments(argv) -> argparse.Namespace:
    """The command line, checked."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--export', type=Path, help='the FNV export (needed unless --pre-elric)')
    parser.add_argument('--pre-elric', action='store_true', help='the paths are pre-Elric NIFs')
    parser.add_argument('--cache', type=Path, default=elric_cache.CACHE)
    parser.add_argument('--max', type=int, default=0)
    parser.add_argument('--workers', type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    parser.add_argument('--tolerance', type=float, default=1e-4)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--show', type=int, default=2)
    args = parser.parse_args(argv)
    if args.export is None and not args.pre_elric:
        parser.error('--export is needed unless --pre-elric')
    return args


def main(argv=None) -> int:
    """Run the comparison and print the summary; exit 1 when any compared pair differs."""
    args = _arguments(argv)
    export_dir = None if args.pre_elric else args.export
    paths = meshes(args.paths, export_dir)[:args.max or None]
    print(f'{len(paths)} meshes, Elric cache {args.cache}', flush=True)
    results = []
    out = args.json.open('w', encoding='utf-8') if args.json else None
    with ProcessPoolExecutor(args.workers) as pool:
        jobs = [pool.submit(_job, str(p), export_dir and str(export_dir), str(args.cache), args.tolerance)
                for p in paths]
        for i, job in enumerate(jobs, 1):
            results.append(job.result())
            path, status, found = results[-1]
            if out:
                out.write(json.dumps({'mesh': path, 'status': status,
                                      'differs': {k: _jsonable(v) for k, v in found.items()}}) + '\n')
                out.flush()
            if i % 100 == 0:
                print(f'  {i}/{len(paths)}', flush=True)
    if out:
        out.close()
    print('\n'.join(summary(results, args.show)))
    return 1 if any(found for _, status, found in results if status == 'compared') else 0


if __name__ == '__main__':
    sys.exit(main())
