"""Bake an FNV face shape into the FaceGen head the Creation Kit exported for an FO4 NPC.

The CK's FaceGeom NIF is the head the game draws: every head part as a
skinned BSSubIndexTriShape in one head-local frame. Its face part, exported
for an NPC with no face shape, is FO4's mean head. FNV's mean head is aligned
to it (similarity fit over the front of the face), then each FO4 head vertex
gets a displacement:

- 'C1': the NPC's FNV FaceGen offset from FNV's mean, carried across;
- 'C2': onto the NPC's FNV surface itself.

It is smoothed over the head, faded to zero at the body seam (body_seam),
and
every part's vertices (head, eyes, mouth, hair, beard) move with their
nearest head vertices. Positions are rewritten in place; topology, skinning
and vertex order (which FO4's expression and lip morphs index) are kept.

See: docs/fork/fo4_spikes.md#spike-2-facegen
"""

import struct

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from fo4_import.face.fnv_head import FnvHead
from fo4_import.nif import file as nif_file

#: FaceGeom parts that are the face (FO4 HumanRace's male and female face head parts).
FACE_PARTS = frozenset({'MaleHeadHuman', 'FemaleHeadHuman'})
#: Distance (FO4 head units) from the body seam over which the displacement fades in.
NECK_BLEND = 3.0
#: Points this close are one vertex (just over half-float precision at head size, 0.008); in-shape weld decimals.
WELD_DISTANCE, WELD_DECIMALS = 0.01, 3
SMOOTH_PASSES, ICP_ROUNDS, PART_NEIGHBOURS = 4, 40, 4
#: Samples per triangle edge when FNV's surface is sampled for nearest-point queries.
SURFACE_DENSITY = 6
VA_FULL_PRECISION = 0x400


def _vertex_layout(raw: bytes) -> tuple:
    """(first vertex offset, stride, count, full precision) of a BSTriShape-like block's vertex data."""
    n_extra = struct.unpack_from('<I', raw, 4)[0]
    pos = 4 + 4 + 4 * n_extra + 4 + 4 + 12 + 36 + 4 + 4 + 16 + 12
    desc = struct.unpack_from('<Q', raw, pos)[0]
    count = struct.unpack_from('<H', raw, pos + 12)[0]
    return pos + 18, (desc & 0xF) * 4, count, bool((desc >> 44) & VA_FULL_PRECISION)


def positions(raw: bytes) -> np.ndarray:
    """A shape block's vertex positions."""
    start, stride, count, full = _vertex_layout(raw)
    fmt = '<3f' if full else '<3e'
    return np.array([struct.unpack_from(fmt, raw, start + i * stride) for i in range(count)], float)


def uvs(raw: bytes) -> np.ndarray:
    """A shape block's vertex UVs (after the position and its bitangent x)."""
    start, stride, count, full = _vertex_layout(raw)
    skip = 16 if full else 8
    return np.array([struct.unpack_from('<2e', raw, start + i * stride + skip) for i in range(count)], float)


def with_positions(raw: bytes, points: np.ndarray) -> bytes:
    """`raw` with its vertex positions replaced by `points`."""
    start, stride, count, full = _vertex_layout(raw)
    out, fmt = bytearray(raw), '<3f' if full else '<3e'
    for i in range(count):
        struct.pack_into(fmt, out, start + i * stride, *points[i])
    return bytes(out)


def surface(vertices: np.ndarray, triangles: np.ndarray) -> tuple:
    """Points spread over the triangles and, per point, (triangle, barycentric weights)."""
    steps = np.linspace(0, 1, SURFACE_DENSITY)
    grid = np.array([(a, b, 1 - a - b) for a in steps for b in steps if a + b <= 1 + 1e-9])
    corners = vertices[triangles]
    points = np.einsum('gk,tkd->gtd', grid, corners).reshape(-1, 3)
    owner = np.tile(np.arange(len(triangles)), len(grid))
    return points, owner, np.repeat(grid, len(triangles), axis=0)


def _similarity(src: np.ndarray, dst: np.ndarray) -> tuple:
    """(s, R, t) minimising |s R src + t - dst| (Umeyama)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, sig, vt = np.linalg.svd(b.T @ a / len(src))
    d = np.diag([1.0, 1.0, np.sign(np.linalg.det(u @ vt))])
    r = u @ d @ vt
    s = float((sig * np.diag(d)).sum() / (a ** 2).sum() * len(src))
    return s, r, mu_d - s * r @ mu_s


def align(fo4_head: np.ndarray, fnv_mean: np.ndarray, surface: tuple) -> tuple:
    """(s, R, t) taking FO4 head coordinates onto FNV's mean head, fitted over the front of the face."""
    tree = cKDTree(surface[0])
    front = fo4_head[fo4_head[:, 1] > 0]
    s = np.ptp(fnv_mean[fnv_mean[:, 1] > 0][:, 0]) / np.ptp(front[:, 0])
    r, t = np.eye(3), fnv_mean[fnv_mean[:, 1] > 0].mean(0) - s * front.mean(0)
    for _ in range(ICP_ROUNDS):
        _, idx = tree.query(s * front @ r.T + t)
        s, r, t = _similarity(front, surface[0][idx])
    return s, r, t


def _interpolate(values: np.ndarray, triangles: np.ndarray, surface: tuple, idx: np.ndarray) -> np.ndarray:
    """Per-vertex `values` at surface samples `idx`, barycentrically."""
    _, owner, bary = surface
    return (bary[idx][:, :, None] * values[triangles[owner[idx]]]).sum(1)


def head_displacement(fo4_head: np.ndarray, fnv: FnvHead, variant: str) -> np.ndarray:
    """Per FO4 head vertex, its move for `variant` in the FO4 frame."""
    mean_surface = surface(fnv.mean, fnv.triangles)
    s, r, t = align(fo4_head, fnv.mean, mean_surface)
    placed = s * fo4_head @ r.T + t
    if variant == 'C1':
        _, idx = cKDTree(mean_surface[0]).query(placed)
        moved = _interpolate(fnv.npc - fnv.mean, fnv.triangles, mean_surface, idx)
    elif variant == 'C2':
        npc_surface = surface(fnv.npc, fnv.triangles)
        _, idx = cKDTree(npc_surface[0]).query(placed)
        moved = npc_surface[0][idx] - placed
    else:
        raise ValueError(f'unknown face variant {variant}')
    return (moved @ r) / s


def triangles(raw: bytes) -> np.ndarray:
    """A shape block's triangles (vertex index triples)."""
    start, stride, count, _ = _vertex_layout(raw)
    n_tris = struct.unpack_from('<I', raw, start - 10)[0]
    return np.frombuffer(raw, '<u2', n_tris * 3, start + count * stride).reshape(-1, 3)


def outer_border(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Positions on a shape's largest open boundary loop, vertices welded by position (UV seams split them)."""
    _, weld = np.unique(np.round(points, WELD_DECIMALS), axis=0, return_inverse=True)
    weld = weld.ravel()
    welded = weld[tris]
    edges = np.sort(np.concatenate([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = unique[counts == 1]
    if not len(open_edges):
        return np.zeros((0, 3))
    graph = coo_matrix((np.ones(len(open_edges)), (open_edges[:, 0], open_edges[:, 1])), shape=(weld.max() + 1,) * 2)
    _, label = connected_components(graph, directed=False)
    on_loop = np.unique(open_edges)
    biggest = np.bincount(label[on_loop]).argmax()
    where = np.zeros((weld.max() + 1, 3))
    where[weld] = points
    return where[on_loop[label[on_loop] == biggest]]


def body_seam(face: np.ndarray, borders: list) -> np.ndarray:
    """Where the body joins: the outer border points of the face, and of each part sharing border with
    it, that no other of those parts shares (shared stretches join head parts to each other).

    `face` is the face's border; `borders` every other part's.
    """
    near = [b for b in borders if len(b) and (cKDTree(face).query(b)[0] < WELD_DISTANCE).any()]
    seams = []
    for i, border in enumerate([face] + near):
        others = np.vstack([b for j, b in enumerate([face] + near) if j != i])
        seams.append(border[cKDTree(others).query(border)[0] >= WELD_DISTANCE])
    return np.vstack(seams)


def _smoothed(points: np.ndarray, moves: np.ndarray) -> np.ndarray:
    """`moves` averaged with each vertex's nearest neighbours, SMOOTH_PASSES times."""
    _, near = cKDTree(points).query(points, k=PART_NEIGHBOURS + 1)
    for _ in range(SMOOTH_PASSES):
        moves = moves[near].mean(1)
    return moves


def _shapes(nif) -> tuple:
    """(indices of a FaceGeom NIF's head part shapes, the face's index)."""
    shapes = [i for i, (kind, _) in enumerate(nif.blocks) if kind == 'BSSubIndexTriShape']
    face = next(i for i in shapes if nif.strings[struct.unpack_from('<i', nif.blocks[i][1], 0)[0]] in FACE_PARTS)
    return shapes, face


def face_shape(nif_bytes: bytes) -> tuple:
    """(positions, UVs, triangles) of a FaceGeom NIF's face part."""
    nif = nif_file.read(nif_bytes)
    raw = nif.blocks[_shapes(nif)[1]][1]
    return positions(raw), uvs(raw), triangles(raw)


def _seam(nif, shapes: list, face: int) -> cKDTree:
    """A tree over the FaceGeom NIF's body seam points."""
    borders = {i: outer_border(positions(nif.blocks[i][1]), triangles(nif.blocks[i][1])) for i in shapes}
    return cKDTree(body_seam(borders[face], [b for i, b in borders.items() if i != face]))


def face_moves(nif_bytes: bytes, fnv: FnvHead, variant: str) -> tuple:
    """(face vertex positions, their moves for `variant`: smoothed, faded to zero at the body seam)."""
    nif = nif_file.read(nif_bytes)
    shapes, face = _shapes(nif)
    head = positions(nif.blocks[face][1])
    moves = _smoothed(head, head_displacement(head, fnv, variant))
    return head, moves * np.clip(_seam(nif, shapes, face).query(head)[0] / NECK_BLEND, 0.0, 1.0)[:, None]


def bake(nif_bytes: bytes, fnv: FnvHead, variant: str) -> bytes:
    """The FaceGeom NIF `nif_bytes` with its face and every head part moved to `variant`'s shape."""
    nif = nif_file.read(nif_bytes)
    shapes, face = _shapes(nif)
    head = positions(nif.blocks[face][1])
    moves = _smoothed(head, head_displacement(head, fnv, variant))
    seam = _seam(nif, shapes, face)
    tree = cKDTree(head)
    for i in shapes:
        points = positions(nif.blocks[i][1])
        dist, near = tree.query(points, k=PART_NEIGHBOURS)
        weights = 1.0 / np.maximum(dist, 1e-6)
        shift = (moves[near] * weights[:, :, None]).sum(1) / weights.sum(1)[:, None]
        shift *= np.clip(seam.query(points)[0] / NECK_BLEND, 0.0, 1.0)[:, None]
        nif.blocks[i] = (nif.blocks[i][0], with_positions(nif.blocks[i][1], points + shift))
    return nif_file.write(nif)
