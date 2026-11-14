"""Triangle meshes as Elric writes them: an hknpCompressedMeshShape, its data and Bethesda's material table.

`read()` takes the bhkNiTriStripsShape nif/collision.py writes (one strip per
material, each with its collision filter); `compressed()` gives the packfile
objects; `triangles()` decodes a written mesh tree back to triangles. Triangles
pair into quads across a shared edge, primitives split into sections of at most
127 primitives and 255 vertices, each section quantized 11/11/10 bits on its own
box, and both trees' boxes coded as square-root insets of their parent's.
Ported from NifSkope Wild Wasteland Edition's encoder (src/gl/hknpencode.cpp);
its BSD-3 notice is in NIFSKOPE_LICENSE.txt beside this file.

See: docs/fork/fo4_hknp_writer.md#mesh
"""

import math
import struct
from dataclasses import dataclass

import numpy as np

#: Packed vertex steps per axis (11, 11 and 10 bits) and the shared-vertex steps over the tree box (21/21/22).
STEPS = np.array([2047.0, 2047.0, 1023.0])
SHARED_STEPS = np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF], float)
#: A section's limits: a mesh-tree leaf holds twice its primitive index in a byte; vertex indices are a byte.
SECTION_PRIMITIVES, SECTION_VERTICES = 127, 255
#: A section-tree node's inner flag in its 16 data bits (hiData << 8 | loData).
INNER = 0x8000
#: A quad is flat when its fourth corner lies within this of the first three's plane (Elric's build tolerance).
FLAT = 0.01
#: A quad corner turning back by at most this share of its quad's squared normal still counts as straight.
STRAIGHT = 1e-6
#: Shape constants on every Elric compressed mesh: flags, dispatch type, the material-table property key.
SHAPE_FLAGS, DISPATCH_COMPOSITE, MATERIALS_KEY = 516, 2, 0xF601
#: hkReal's largest value as Havok writes an empty box.
FLT_MAX = 3.402820018375656e+38
#: FO4 game units per Havok unit as Elric reads a strip's vertices and places a body.
GAME_PER_HAVOK = 69.99125
#: Bytes of bhkNiTriStripsShape before its strip count.
STRIPS_AT = 48


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

@dataclass
class Mesh:
    """A triangle soup: points (Havok units), triangles (point indices), each one's strip, and per strip its
    (collision filter, material CRC)."""
    points: np.ndarray
    tris: np.ndarray
    strip: np.ndarray
    strips: list


def _strip(raw: bytes) -> tuple:
    """(points, triangles, material CRC) of one NiTriStripsData as collision.tri_strips_data writes it, less
    triangles naming a point twice: written as (a, b, b, b) the game reads one as a custom primitive.
    See: docs/fork/fo4_hknp_writer.md#mesh-writer
    """
    n = struct.unpack_from('<H', raw, 4)[0]
    points = np.array(struct.unpack_from(f'<{3 * n}f', raw, 9)).reshape(-1, 3) / GAME_PER_HAVOK
    at = 9 + 12 * n
    crc = struct.unpack_from('<I', raw, at + 2)[0]
    count = struct.unpack_from('<H', raw, at + 30)[0]
    at += 34 + 2 * count + 1
    tris = np.array(struct.unpack_from(f'<{3 * count}H', raw, at)).reshape(-1, 3)
    return points, tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])], crc


def read(blocks: list, index: int) -> 'Mesh | None':
    """The Mesh of bhkNiTriStripsShape block `index`; None for any other block."""
    kind, raw = blocks[index]
    if kind != 'bhkNiTriStripsShape':
        return None
    n = struct.unpack_from('<I', raw, STRIPS_AT)[0]
    refs = struct.unpack_from(f'<{n}i', raw, STRIPS_AT + 4)
    filters = struct.unpack_from(f'<{n}I', raw, STRIPS_AT + 8 + 4 * n)
    points, tris, strip, strips = [], [], [], []
    for i, ref in enumerate(refs):
        pts, faces, crc = _strip(blocks[ref][1])
        tris.append(faces + sum(len(p) for p in points))
        points.append(pts)
        strip += [i] * len(faces)
        strips.append((filters[i], crc))
    return Mesh(np.vstack(points), np.vstack(tris), np.array(strip), strips)


# ---------------------------------------------------------------------------
# Quads
# ---------------------------------------------------------------------------

def _normal(points: np.ndarray, tri) -> np.ndarray:
    """Triangle `tri`'s unit normal (zero when degenerate)."""
    n = np.cross(points[tri[1]] - points[tri[0]], points[tri[2]] - points[tri[0]])
    length = np.linalg.norm(n)
    return n / length if length > 0 else n


def _convex(points: np.ndarray, prim: list) -> bool:
    """Whether flat quad `prim` (a, b, c, d) is convex: no corner turns against its first triangle's facing (a
    straight corner allowed)."""
    corners = points[prim]
    normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    turns = np.cross(np.roll(corners, -1, 0) - corners, np.roll(corners, -2, 0) - np.roll(corners, -1, 0))
    return bool(np.all(turns @ normal >= -STRAIGHT * (normal @ normal)))


def _partner(mesh: Mesh, i: int, edges: dict, used: list) -> 'tuple | None':
    """(score, -other triangle, edge of i, edge of other) of the flattest unused same-strip triangle sharing an
    edge with triangle i in the opposite direction whose quad is flat and convex; None when there is none.
    The game collides a quad as the convex hull of its corners, so any other pair is a solid it must not be.
    See: docs/fork/fo4_hknp_writer.md#mesh-writer
    """
    tri, best = mesh.tris[i], None
    normal = _normal(mesh.points, tri)
    for e in range(3):
        for other, slot in edges.get((tri[(e + 1) % 3], tri[e]), ()):
            far = mesh.tris[other][(slot + 2) % 3]
            if used[other] or mesh.strip[other] != mesh.strip[i] or far == tri[(e + 2) % 3]:
                continue
            prim = [tri[(e + 1) % 3], tri[(e + 2) % 3], tri[e], far]
            if not (flat(mesh.points, prim) and _convex(mesh.points, prim)):
                continue
            score = (float(normal @ _normal(mesh.points, mesh.tris[other])), -other, e, slot)
            best = max(best, score) if best else score
    return best


def quads(mesh: Mesh) -> list:
    """[([a, b, c, d], first triangle)] in triangle order: each triangle with its flattest partner across a
    shared edge, read back as (a, b, c) and (a, c, d); a triangle left alone is (a, b, c, c)."""
    edges = {}
    for i, tri in enumerate(mesh.tris):
        for e in range(3):
            edges.setdefault((tri[e], tri[(e + 1) % 3]), []).append((i, e))
    used, out = [False] * len(mesh.tris), []
    for i, tri in enumerate(mesh.tris):
        if used[i]:
            continue
        used[i] = True
        best = _partner(mesh, i, edges, used)
        if best is None:
            out.append(([int(v) for v in tri] + [int(tri[2])], i))
            continue
        _, other, e, slot = best
        used[-other] = True
        far = mesh.tris[-other][(slot + 2) % 3]
        out.append(([int(tri[(e + 1) % 3]), int(tri[(e + 2) % 3]), int(tri[e]), int(far)], i))
    return out


def flat(points: np.ndarray, prim: list) -> bool:
    """Whether quad `prim`'s fourth corner lies within FLAT of its first three's plane (a triangle: not flat)."""
    a, b, c, d = prim
    if c == d:
        return False
    n = _normal(points, (a, b, c))
    return bool(np.linalg.norm(n) > 0 and abs(n @ (points[d] - points[a])) < FLAT)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def sections(points: np.ndarray, prims: list) -> list:
    """[[primitive index]] per section: primitives sorted along the mesh's longest axis by their first three
    corners, taken in order until one more would pass SECTION_PRIMITIVES or SECTION_VERTICES."""
    axis = int(np.argmax(np.ptp(points, 0)))
    order = sorted(range(len(prims)), key=lambda k: sum(points[v][axis] for v in prims[k][0][:3]))
    out, current, seen = [], [], set()
    for k in order:
        corners = set(prims[k][0])
        if len(current) >= SECTION_PRIMITIVES or len(seen | corners) > SECTION_VERTICES:
            out.append(current)
            current, seen = [], set()
        current.append(k)
        seen |= corners
    return out + [current]


def quantize(points: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> tuple:
    """(packed u32 per point, decoded points) on box (lo, hi): each axis `trunc(t × N + 0.5)` of t, the point's
    place in the box clamped to [0, 1], as Elric's section encoder."""
    extent = hi - lo
    t = np.clip((points - lo) / np.where(extent > 0, extent, 1), 0, 1) * (extent > 0)
    q = np.trunc(t * STEPS + 0.5).astype(np.int64)
    return [int(x | y << 11 | z << 22) for x, y, z in q], lo + q / STEPS * extent


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------

def _inset(inset: float, span: float) -> int:
    """The largest 4-bit n whose square-root-scale inset (n/15)² × span does not pass `inset` (float32)."""
    if span <= 0 or inset <= 0:
        return 0
    n = min(15, int(math.sqrt(min(inset / span, 1.0)) * 15))
    while n and np.float32((n / 15) ** 2) * np.float32(span) > np.float32(inset):
        n -= 1
    return n


def coded(box: tuple, parent: tuple) -> tuple:
    """([x, y, z] bytes of `box` against `parent`, the box a reader decodes from them, which contains `box`)."""
    lo, hi, xyz = list(parent[0]), list(parent[1]), []
    for a in range(3):
        span = parent[1][a] - parent[0][a]
        low, high = _inset(box[0][a] - parent[0][a], span), _inset(parent[1][a] - box[1][a], span)
        xyz.append(low << 4 | high)
        lo[a] = parent[0][a] + (low / 15) ** 2 * span
        hi[a] = parent[1][a] - (high / 15) ** 2 * span
    return xyz, (np.array(lo), np.array(hi))


def _union(boxes: list, members: list) -> tuple:
    """The box around `boxes[i]` for i in `members`."""
    return (np.min([boxes[i][0] for i in members], 0), np.max([boxes[i][1] for i in members], 0))


def tree(boxes: list, members: list, parent: tuple, node) -> list:
    """Nodes (depth first) of the tree over `members` (indices into `boxes`) inside `parent`: each node's box
    coded against its parent's decoded box; a node with several members splits at the median along its widest
    axis, left half first. `node(xyz, member or None, left count)` makes one node."""
    xyz, own = coded(_union(boxes, members), parent)
    if len(members) == 1:
        return [node(xyz, members[0], 0)]
    axis = int(np.argmax(own[1] - own[0]))
    members = sorted(members, key=lambda i: boxes[i][0][axis] + boxes[i][1][axis])
    left = len(members) // 2
    return [node(xyz, None, left)] + tree(boxes, members[:left], own, node) + tree(boxes, members[left:], own, node)


def _mesh_node(xyz: list, member, left: int) -> dict:
    """A mesh-tree node: leaf 2 × primitive, inner 2 × left leaves + 1."""
    return {'xyz': xyz, 'data': member * 2 if member is not None else left * 2 | 1}


def _section_node(xyz: list, member, left: int) -> dict:
    """A section-tree node: leaf its section; inner INNER | left leaves."""
    value = member if member is not None else INNER | left
    return {'xyz': xyz, 'hiData': value >> 8, 'loData': value & 0xFF}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _runs(materials: list) -> list:
    """Data runs over a section's primitive materials: consecutive equal ones as one (material, start, count)."""
    out = []
    for k, m in enumerate(materials):
        if out and out[-1]['value']['data'] == m:
            out[-1]['count'] += 1
        else:
            out.append({'value': {'data': m}, 'index': k, 'count': 1})
    return out


def _aabb(lo, hi) -> dict:
    """An hkAabb with w 1, as Elric writes a domain."""
    return {'min': (*map(float, lo), 1.0), 'max': (*map(float, hi), 1.0)}


def _section(mesh: Mesh, prims: list, members: list, state: dict) -> dict:
    """One section over primitives `members`: its packed vertices, primitives and runs appended to `state`'s
    lists; its own fields (leaf index set later)."""
    local = list(dict.fromkeys(v for k in members for v in prims[k][0]))
    at = {v: i for i, v in enumerate(local)}
    lo, hi = mesh.points[local].min(0), mesh.points[local].max(0)
    packed, decoded = quantize(mesh.points[local], lo, hi)
    corners = [decoded[[at[v] for v in prims[k][0]]] for k in members]
    runs = _runs([int(mesh.strip[prims[k][1]]) for k in members])
    key = tuple((r['value']['data'], r['index'], r['count']) for r in runs)
    if key not in state['run_at']:
        state['run_at'][key] = len(state['runs'])
        state['runs'] += runs
    out = {'nodes': tree([(c.min(0), c.max(0)) for c in corners], list(range(len(members))), (lo, hi), _mesh_node),
           'domain': _aabb(lo, hi), 'codecParms': [*map(float, lo), *map(float, (hi - lo) / STEPS)],
           'firstPackedVertex': len(state['packed']), 'sharedVertices': {'data': len(local)},
           'primitives': {'data': len(state['prims']) << 8 | len(members)},
           'dataRuns': {'data': state['run_at'][key] << 8 | len(runs)}, 'numPackedVertices': len(local),
           'numSharedIndices': 0, 'leafIndex': 0, 'page': 0, 'flags': 0, 'layerData': 0, 'unusedData': 0}
    state['packed'] += packed
    state['prims'] += [{'indices': [at[v] for v in prims[k][0]]} for k in members]
    state['flat'] += [flat(mesh.points, prims[k][0]) for k in members]
    return out


def _keys(groups: list) -> tuple:
    """(key bits, primitive bits, largest key) for sections `groups`."""
    prim_bits = 8 if len(groups) > 1 else (2 * len(groups[0])).bit_length()
    bits = (len(groups) - 1).bit_length() + prim_bits
    return bits, prim_bits, (len(groups) - 1) << prim_bits | 2 * len(groups[-1]) - 1


def _bitfield(bits: int, on: list) -> dict:
    """An hkBitField of `bits` bits with the bits `on` set, no stray bits past the end."""
    words = [0] * ((bits + 31) // 32)
    for b in on:
        words[b // 32] |= 1 << b % 32
    return {'storage': {'words': words, 'numBits': bits}}


def _tree_fields(mesh: Mesh, prims: list, groups: list) -> tuple:
    """(the meshTree fields, flat bit indices) of `prims` split into `groups`."""
    state = {'packed': [], 'prims': [], 'flat': [], 'runs': [], 'run_at': {}}
    built = [_section(mesh, prims, g, state) for g in groups]
    lo, hi = mesh.points.min(0), mesh.points.max(0)
    boxes = [(np.array(s['domain']['min'][:3]), np.array(s['domain']['max'][:3])) for s in built]
    nodes = tree(boxes, list(range(len(built))), (lo, hi), _section_node)
    for i, n in enumerate(nodes):
        if not n['hiData'] << 8 & INNER:
            built[n['hiData'] << 8 | n['loData']]['leafIndex'] = i
    bits, prim_bits, top = _keys(groups)
    firsts = [s['primitives']['data'] >> 8 for s in built]
    on = [s << prim_bits - 1 | k - firsts[s] for s in range(len(built))
          for k in range(firsts[s], firsts[s] + len(groups[s])) if state['flat'][k]]
    triangle_count = sum(1 if p['indices'][2] == p['indices'][3] else 2 for p in state['prims'])
    fields = {'nodes': nodes, 'domain': _aabb(lo, hi), 'numPrimitiveKeys': triangle_count, 'bitsPerKey': bits,
              'maxKeyValue': top, 'sections': built, 'primitives': state['prims'], 'sharedVerticesIndex': [],
              'packedVertices': state['packed'], 'sharedVertices': [], 'primitiveDataRuns': state['runs']}
    return fields, on


def _simd_tree() -> dict:
    """The two empty hkcdSimdTree nodes on every Elric compressed mesh."""
    empty = {'lx': (FLT_MAX,) * 4, 'hx': (-FLT_MAX,) * 4, 'ly': (FLT_MAX,) * 4, 'hy': (-FLT_MAX,) * 4,
             'lz': (FLT_MAX,) * 4, 'hz': (-FLT_MAX,) * 4, 'data': [0, 0, 0, 0]}
    return {'nodes': [dict(empty), dict(empty)]}


def compressed(name: str, mesh: Mesh) -> list:
    """[shape, its properties, its material table, its data] as packfile objects named from `name`."""
    prims = quads(mesh)
    fields, on = _tree_fields(mesh, prims, sections(mesh.points, prims))
    keys = fields['maxKeyValue'] + 1
    shape = {'flags': SHAPE_FLAGS, 'numShapeKeyBits': fields['bitsPerKey'], 'dispatchType': DISPATCH_COMPOSITE,
             'convexRadius': 0.0, 'userData': mesh.strips[0][1], 'properties': f'{name}p',
             'edgeWeldingMap': {'secondaryKeyMask': 0xFFFFFFFF, 'sencondaryKeyBits': 0, 'primaryKeyToIndex': [],
                                'valueAndSecondaryKeys': []},
             'shapeTagCodecInfo': 0xFFFFFFFF, 'data': f'{name}d', 'quadIsFlat': _bitfield((keys + 1) // 2, on),
             'triangleIsInterior': _bitfield(keys, [])}
    table = [{'reserved': [0, 0], 'collisionFilterInfo': f, 'materialCrc': c} for f, c in mesh.strips]
    return [{'#': name, 'class': 'hknpCompressedMeshShape', 'fields': shape},
            {'#': f'{name}p', 'class': 'hkRefCountedProperties',
             'fields': {'entries': [{'object': f'{name}m', 'key': MATERIALS_KEY, 'flags': 0}]}},
            {'#': f'{name}m', 'class': 'hknpBSMaterialProperties', 'fields': {'materials': table}},
            {'#': f'{name}d', 'class': 'hknpCompressedMeshShapeData',
             'fields': {'meshTree': fields, 'simdTree': _simd_tree()}}]


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------

def _corners(tree_fields: dict, section: dict) -> np.ndarray:
    """A section's vertices: its packed ones, then the shared ones it names."""
    first, n = section['firstPackedVertex'], section['numPackedVertices']
    codec = np.array(section['codecParms'])
    q = np.array([(v & 0x7FF, v >> 11 & 0x7FF, v >> 22) for v in tree_fields['packedVertices'][first:first + n]],
                 float).reshape(-1, 3)
    lo, hi = (np.array(tree_fields['domain'][k][:3]) for k in ('min', 'max'))
    start = section['sharedVertices']['data'] >> 8
    shared = [tree_fields['sharedVertices'][i] for i in
              tree_fields['sharedVerticesIndex'][start:start + section['numSharedIndices']]]
    s = np.array([(v & 0x1FFFFF, v >> 21 & 0x1FFFFF, v >> 42) for v in shared], float).reshape(-1, 3)
    return np.vstack([codec[:3] + q * codec[3:], lo + s * (hi - lo) / SHARED_STEPS])


def triangles(tree_fields: dict) -> tuple:
    """(triangles as (n, 3, 3) corners, material index per triangle) a written meshTree decodes to; a primitive
    naming a vertex its section lacks (one in Elric's 1,016 sections) is skipped."""
    tris, materials = [], []
    for section in tree_fields['sections']:
        corners = _corners(tree_fields, section)
        first = section['primitives']['data'] >> 8
        runs_at, run_count = section['dataRuns']['data'] >> 8, section['dataRuns']['data'] & 0xFF
        for run in tree_fields['primitiveDataRuns'][runs_at:runs_at + run_count]:
            for k in range(run['index'], run['index'] + run['count']):
                a, b, c, d = indices = tree_fields['primitives'][first + k]['indices']
                if max(indices) >= len(corners):
                    continue
                for tri in ((a, b, c),) + (((a, c, d),) if c != d else ()):
                    tris.append(corners[list(tri)])
                    materials.append(run['value']['data'])
    return np.array(tris).reshape(-1, 3, 3), np.array(materials)
