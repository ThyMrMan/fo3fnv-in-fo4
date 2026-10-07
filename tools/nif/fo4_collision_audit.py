"""Audit FNV-to-FO4 collision: each part's box in FNV, in ours before Elric and in the shipped mesh.

    python -m tools.nif.fo4_collision_audit --export export/FalloutNV.esm --plugin <FO4 plugin>
        [--data <Data folder>] [--near X Y R] [--tolerance 4] [--workers N]

FNV's side is read straight from the source mesh with pyffi (node transforms
with scale, bhkRigidBodyT, shape trees); ours from the Havok blocks
fo4_import.nif.convert_static writes for Elric; with --data, also the
shipped mesh's Elric physics (fo4_import.nif.hknp) under its owner node's
transform. A part (keyed by its node name) whose root-space box differs by
more than the tolerance, or that one side lacks, is listed with the placed
references that use the model.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import argparse
import math
import os
import struct
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.collision import GAME_PER_HAVOK
from fo4_import.nif.convert_static import PREFIX, convert
from fo4_import.nif.hknp import PhysicsSystem
from tes5_import.base.tes5_reader import subrecords, walk

apply_patches()
from pyffi.formats.nif import NifFormat

#: FNV game units per Havok unit.
FNV_UNIT = 7.0
#: Byte offset of a pre-Elric bhkRigidBody(T)'s translation and rotation (8 floats), see collision._rigid_body.
BODY_PLACE = 52


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _rotate(q, pts: np.ndarray) -> np.ndarray:
    """Points rotated by quaternion (x, y, z, w)."""
    x, y, z, w = q
    m = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    return pts @ m.T


def _corners(center, half) -> np.ndarray:
    """The eight corners of a box."""
    signs = np.array([[a, b, c] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)])
    return np.asarray(center) + signs * np.asarray(half)


# ---------------------------------------------------------------------------
# FNV side
# ---------------------------------------------------------------------------


def _fnv_points(s) -> np.ndarray:
    """An FNV Havok shape's points in game units (its own frame)."""
    kind = type(s).__name__
    if kind == 'bhkMoppBvTreeShape':
        return _fnv_points(s.shape)
    if kind == 'bhkListShape':
        return np.vstack([_fnv_points(c) for c in s.sub_shapes])
    if kind in ('bhkConvexTransformShape', 'bhkTransformShape'):
        m = np.array(s.transform.as_list())
        child = _fnv_points(s.shape)
        return child @ m[:3, :3].T + m[:3, 3] * FNV_UNIT
    if kind == 'bhkPackedNiTriStripsShape':
        return np.array([(v.x, v.y, v.z) for v in s.data.vertices]) * FNV_UNIT
    if kind == 'bhkConvexVerticesShape':
        return np.array([(v.x, v.y, v.z) for v in s.vertices]) * FNV_UNIT
    if kind == 'bhkBoxShape':
        return _corners((0, 0, 0), np.array([s.dimensions.x, s.dimensions.y, s.dimensions.z]) * FNV_UNIT)
    if kind == 'bhkSphereShape':
        return _corners((0, 0, 0), [s.radius * FNV_UNIT] * 3)
    if kind == 'bhkCapsuleShape':
        ends = np.array([(p.x, p.y, p.z) for p in (s.first_point, s.second_point)]) * FNV_UNIT
        return np.vstack([_corners(e, [r * FNV_UNIT] * 3) for e, r in zip(ends, (s.radius_1, s.radius_2))])
    raise ValueError(f'unhandled FNV shape {kind}')


def fnv_parts(path: Path) -> dict:
    """{node name: (lo, hi)} of every collision body in the FNV mesh, in root space (game units)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    root, parts = data.roots[0], {}
    for node in root.tree():
        co = getattr(node, 'collision_object', None)
        if co is None or getattr(co, 'body', None) is None:
            continue
        body = co.body
        pts = _fnv_points(body.shape)
        if type(body).__name__ == 'bhkRigidBodyT':
            r, t = body.rotation, body.translation
            pts = _rotate((r.x, r.y, r.z, r.w), pts) + np.array([t.x, t.y, t.z]) * FNV_UNIT
        if node is not root:
            m = np.array(node.get_transform(root).as_list())
            pts = np.hstack([pts, np.ones((len(pts), 1))]) @ m
        parts[node.name.decode('cp1252') if node is not root else ''] = (pts[:, :3].min(0), pts[:, :3].max(0))
    return parts


# ---------------------------------------------------------------------------
# Our side
# ---------------------------------------------------------------------------


def _our_points(blocks: list, index: int) -> np.ndarray:
    """A pre-Elric Havok shape block's points in game units (its own frame)."""
    kind, raw = blocks[index]
    if kind == 'bhkListShape':
        n = struct.unpack_from('<I', raw)[0]
        return np.vstack([_our_points(blocks, c) for c in struct.unpack_from(f'<{n}i', raw, 4)])
    if kind == 'bhkConvexTransformShape':
        child = struct.unpack_from('<i', raw)[0]
        cells = np.array(struct.unpack_from('<16f', raw, 20)).reshape(4, 4).T
        return _our_points(blocks, child) @ cells[:3, :3].T + cells[:3, 3] * GAME_PER_HAVOK
    if kind == 'bhkNiTriStripsShape':
        n = struct.unpack_from('<I', raw, 48)[0]
        return np.vstack([_strip_points(blocks[s][1]) for s in struct.unpack_from(f'<{n}i', raw, 52)])
    if kind == 'bhkConvexVerticesShape':
        n = struct.unpack_from('<I', raw, 32)[0]
        return np.array(struct.unpack_from(f'<{n * 4}f', raw, 36)).reshape(n, 4)[:, :3] * GAME_PER_HAVOK
    if kind == 'bhkBoxShape':
        return _corners((0, 0, 0), np.array(struct.unpack_from('<3f', raw, 16)) * GAME_PER_HAVOK)
    if kind == 'bhkSphereShape':
        return _corners((0, 0, 0), [struct.unpack_from('<f', raw, 4)[0] * GAME_PER_HAVOK] * 3)
    if kind == 'bhkCapsuleShape':
        p1, r1, p2, r2 = (struct.unpack_from(f, raw, o) for f, o in (('<3f', 16), ('<f', 28), ('<3f', 32), ('<f', 44)))
        return np.vstack([_corners(np.array(p) * GAME_PER_HAVOK, [r[0] * GAME_PER_HAVOK] * 3)
                          for p, r in ((p1, r1), (p2, r2))])
    raise ValueError(f'unhandled shape block {kind}')


def _strip_points(raw: bytes) -> np.ndarray:
    """NiTriStripsData vertex positions (game units)."""
    n = struct.unpack_from('<H', raw, 4)[0]
    return np.array(struct.unpack_from(f'<{n * 3}f', raw, 9)).reshape(n, 3)


def our_parts(nif) -> dict:
    """{node name: (lo, hi)} of every pre-Elric collision body in our NIF, in root space (game units)."""
    parts = {}
    for i, (kind, b) in enumerate(nif.blocks):
        if not isinstance(b, dict) or b.get('collision', NONE) == NONE:
            continue
        body_kind, body = nif.blocks[struct.unpack_from('<iHi', nif.blocks[b['collision']][1])[2]]
        pts = _our_points(nif.blocks, struct.unpack_from('<i', body)[0])
        if body_kind == 'bhkRigidBodyT':
            place = struct.unpack_from('<8f', body, BODY_PLACE)
            pts = _rotate(place[4:], pts) + np.array(place[:3]) * GAME_PER_HAVOK
        if i:
            pts = _placed(b, pts)
        parts[nif.strings[b['name']] if i and b['name'] >= 0 else ''] = (pts.min(0), pts.max(0))
    return parts


def _placed(node: dict, pts: np.ndarray) -> np.ndarray:
    """Points under a NiNode's transform (scale, rotation as stored, translation)."""
    return node['scale'] * pts @ np.array(node['rotation']).reshape(3, 3).T + np.array(node['translation'])


def shipped_parts(path: Path) -> dict:
    """{owner node name: (lo, hi)} of a shipped mesh's Elric bodies, under the owner's transform (game units)."""
    nif = nif_file.read(path.read_bytes())
    parts = {}
    for kind, raw in nif.blocks:
        if kind != 'bhkNPCollisionObject':
            continue
        target, _, system, body = struct.unpack('<iHiI', raw)
        position, orientation, local = PhysicsSystem(nif.blocks[system][1]).bodies()[body]
        pts = (_rotate(orientation, local) + np.array(position)) * GAME_PER_HAVOK
        node = nif.blocks[target][1]
        if target:
            pts = _placed(node, pts)
        parts[nif.strings[node['name']] if target and node['name'] >= 0 else ''] = (pts.min(0), pts.max(0))
    return parts


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def compare(theirs: dict, ours: dict, label: str, tolerance: float) -> list:
    """[(part, problem)] where `ours` (named `label`) differs from FNV's parts."""
    problems = [(name, f'missing in {label}') for name in theirs if name not in ours]
    problems += [(name, f'{label}: not in FNV') for name in ours if name not in theirs]
    for name in set(theirs) & set(ours):
        delta = max(np.abs(theirs[name][0] - ours[name][0]).max(), np.abs(theirs[name][1] - ours[name][1]).max())
        if delta > tolerance:
            problems.append((name, f'{label} off by {delta:.0f}: FNV {_box(theirs[name])} {label} {_box(ours[name])}'))
    return problems


def audit_model(export_dir: Path, model: str, tolerance: float, data_dir) -> list:
    """[(part, problem)] for one FNV model path (under meshes); `data_dir` adds the shipped mesh."""
    source = export_dir / 'meshes' / model
    try:
        theirs = fnv_parts(source)
        problems = compare(theirs, our_parts(convert(str(source), export_dir).nif), 'pre-Elric', tolerance)
        shipped = data_dir / 'Meshes' / PREFIX / model if data_dir else None
        if shipped and shipped.exists():
            problems += compare(theirs, shipped_parts(shipped), 'shipped', tolerance)
    except Exception as e:
        return [('', f'error: {type(e).__name__}: {e}')]
    return problems


def _box(box) -> str:
    """A box as rounded lo..hi."""
    return f'{np.round(box[0]).astype(int).tolist()}..{np.round(box[1]).astype(int).tolist()}'


def placed_models(plugin: Path, near) -> dict:
    """{FNV model path under meshes: [(ref id, position)]} of the plugin's placed references (within `near`)."""
    raw = plugin.read_bytes()
    models, out = {}, {}
    for rec, _ in walk(raw):
        model = dict(subrecords(rec.body)).get(b'MODL') if rec.sig not in (b'REFR', b'ACHR', b'CELL', b'LAND') else None
        if model and model.lower().startswith(PREFIX.encode() + b'\\'):
            models[rec.form_id] = model.rstrip(b'\0').decode('cp1252')[len(PREFIX) + 1:].lower()
    for rec, _ in walk(raw):
        s = dict(subrecords(rec.body)) if rec.sig == b'REFR' else {}
        model = models.get(struct.unpack('<I', s[b'NAME'])[0]) if s else None
        pos = struct.unpack_from('<3f', s[b'DATA']) if model else None
        if pos and (near is None or math.dist(pos[:2], near[:2]) <= near[2]):
            out.setdefault(model, []).append((rec.form_id, pos))
    return out


def main():
    """Audit every placed model and print the parts that differ, with their references."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', type=Path, required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--plugin', type=Path, required=True, help='Converted FO4 plugin whose references to audit')
    ap.add_argument('--data', type=Path, help='Data folder holding the shipped Meshes, to audit Elric output too')
    ap.add_argument('--near', type=float, nargs=3, metavar=('X', 'Y', 'R'), help='Only references within R of X, Y')
    ap.add_argument('--tolerance', type=float, default=4.0, help='Game units a box may differ by')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()
    placed = placed_models(args.plugin, args.near)
    print(f'{len(placed)} models, {sum(len(v) for v in placed.values())} references')
    with ProcessPoolExecutor(args.workers) as pool:
        results = pool.map(audit_model, [args.export] * len(placed), sorted(placed), [args.tolerance] * len(placed),
                           [args.data] * len(placed))
        for model, problems in zip(sorted(placed), results):
            for part, problem in problems:
                refs = ', '.join(f'{fid:08X}@{round(p[0])},{round(p[1])}' for fid, p in placed[model][:4])
                print(f'{model} [{part}] {problem} -- {len(placed[model])} refs: {refs}', flush=True)


if __name__ == '__main__':
    main()
