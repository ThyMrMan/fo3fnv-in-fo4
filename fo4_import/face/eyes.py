"""An FNV eye texture carried onto FO4's eye texture layout by eyeball direction.

The two games lay their eye textures out differently (FNV's paints lashes
and shadow round a centred iris; FO4's puts the iris low in a clean
sclera), so the colours go across by geometry. Each FO4 eye texel is a
point on one of FO4's eyeballs (its UV triangle); its direction from that
eyeball's centre (a least-squares sphere) finds the FNV eye surface sample
facing the same way from FNV's eyeball centre, both in FO4's head frame
(fnv_npc.Frame), FNV's eye mirrored across x for the other side. That
sample's UV gives the colour. Texels no sample faces within EYE_REACH, and
texels outside FO4's UV islands, keep FO4's; alpha is FO4's.

See: docs/fork/fo4_facegen_plan.md#own-heads
"""

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.face import hair
from fo4_import.face.texture import bilinear, island_padding, texel_points

#: The most two unit directions may differ for an FO4 texel to take an FNV sample's colour (about 3 degrees).
EYE_REACH = 0.05


def sphere_centre(points: np.ndarray) -> np.ndarray:
    """The centre of the least-squares sphere through `points`."""
    system = np.column_stack([2 * points, np.ones(len(points))])
    return np.linalg.lstsq(system, (points ** 2).sum(1), rcond=None)[0][:3]


def _unit(vectors: np.ndarray) -> np.ndarray:
    """`vectors` scaled to length 1."""
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def eye_texture(fo4_rgba: np.ndarray, fo4_eye: tuple, fnv_eye: tuple, fnv_rgba: np.ndarray) -> np.ndarray:
    """FO4's square eye texture `fo4_rgba` with FNV's eye colours (module notes) as RGBA uint8; fo4_eye = FO4's
    eye mesh (positions, UVs, triangles), fnv_eye = FNV's (positions in FO4's frame, triangles, UVs)."""
    points, uv, tris = fo4_eye
    out = fo4_rgba.astype(float)
    fnv_points, fnv_tris, fnv_uv = fnv_eye
    spread, spread_uv = hair.samples(fnv_points, fnv_tris, fnv_uv, hair.IRIS_SAMPLES)
    fnv_centre = sphere_centre(fnv_points)
    left = points[tris].mean(1)[:, 0] < 0
    rows, cols = [], []
    for side in (tris[left], tris[~left]):
        if not len(side):
            continue
        centre = sphere_centre(points[np.unique(side)])
        mirror = np.array([1.0 if np.sign(centre[0]) == np.sign(fnv_centre[0]) else -1.0, 1.0, 1.0])
        r, c, where = texel_points(points, uv, side, out.shape[0])
        dist, near = cKDTree(_unit((spread - fnv_centre) * mirror)).query(_unit(where - centre))
        hit = dist <= EYE_REACH
        out[r[hit], c[hit], :3] = bilinear(fnv_rgba[..., :3].astype(float), spread_uv[near[hit]])
        rows.append(r)
        cols.append(c)
    pad, near = island_padding(np.concatenate(rows), np.concatenate(cols), out.shape[:2])
    out[pad[0], pad[1], :3] = out[near[0], near[1], :3]
    return np.clip(out, 0, 255).astype(np.uint8)
