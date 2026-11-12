"""A head part's chargen .tri with the base head's slider morphs copied onto it, and how far a hair sits off the
scalp.

Each morph of the race's base head chargen .tri reaches a part vertex from its
NEIGHBOURS nearest head points, inverse-distance weighted, as Outfit Studio
copies slider data; both are in the same character frame. Clearance is signed
along the nearest scalp vertex's normal, negative inside.

See: docs/fork/fo4_facegen_plan.md#hair-morphs
"""

import numpy as np
from scipy.spatial import cKDTree

from asset_convert.character.facegen_tri import TriFile
from fo4_import.face.bake import positions, triangles, uvs

NEIGHBOURS = 4


def copied_morphs(head: TriFile, points: np.ndarray) -> dict:
    """{morph name: deltas [n, 3]} of `head`'s morphs at `points`."""
    dist, near = cKDTree(np.array(head.vertices)).query(points, k=NEIGHBOURS)
    weights = 1.0 / np.maximum(dist, 1e-6)
    weights /= weights.sum(1, keepdims=True)
    return {name: (np.array(deltas)[near] * weights[:, :, None]).sum(1) for name, deltas in head.morphs.items()}


def part_tri(head: TriFile, raw: bytes) -> bytes:
    """Shape block `raw` as a chargen .tri carrying `head`'s morphs."""
    points, tris = positions(raw), triangles(raw).tolist()
    morphs = {name: d.tolist() for name, d in copied_morphs(head, points).items()}
    return TriFile(points.tolist(), tris, uvs(raw).tolist(), tris, morphs).to_bytes()


def vertex_normals(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Area-weighted unit vertex normals of a triangle mesh."""
    faces = np.cross(points[tris[:, 1]] - points[tris[:, 0]], points[tris[:, 2]] - points[tris[:, 0]])
    out = np.zeros_like(points)
    for corner in range(3):
        np.add.at(out, tris[:, corner], faces)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def clearance(points: np.ndarray, scalp: tuple) -> np.ndarray:
    """Per point, its signed distance off the scalp (points, triangles)."""
    surface, tris = scalp
    near = cKDTree(surface).query(points)[1]
    return ((points - surface[near]) * vertex_normals(surface, tris)[near]).sum(1)
