"""A FaceGen head's skin drawn from one source on both sides of its seams: the face texture is FNV's colour on
FO4's face as drawn (T1, the tone kept in), the rear head gets its own texture with the same colour divided
through the skin tint it is drawn with, and both fade to the body's own drawn colour over the last NECK_BLEND
units above the neck seam.

The game draws a FaceGen face texture as it is, and a skin-tint part (rear head, body) as its texture times the
skin tint times SKIN_TINT_DRAW.

See: docs/fork/fo4_facegen_plan.md#rear-head-texture
"""

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.face.bake import NECK_BLEND
from fo4_import.face.texture import bilinear, face_colours, texel_map, texel_points

#: Per channel, a skin-tint part's drawn colour over texture x skin tint (CK faces at 24 NPCs' seams and necks).
SKIN_TINT_DRAW = np.array([1.76, 1.98, 2.24])


def neck_weight(points: np.ndarray, seam: cKDTree) -> np.ndarray:
    """Per point [n, 1]: 1 on the neck seam, 0 from NECK_BLEND above it."""
    return np.clip(1.0 - seam.query(points)[0] / NECK_BLEND, 0.0, 1.0)[:, None]


def body_drawn(points: np.ndarray, body: tuple, tint: np.ndarray) -> np.ndarray:
    """The body's drawn colour at its vertex nearest each point (positions, UVs, RGB)."""
    positions, uvs, rgb = body
    return bilinear(rgb, uvs[cKDTree(positions).query(points)[1]]) * tint * SKIN_TINT_DRAW


def _repadded(out: np.ndarray, edge: tuple) -> np.ndarray:
    """`out`'s island padding copied again from its edge, as bytes."""
    (pad_r, pad_c), (near_r, near_c) = edge
    out[pad_r, pad_c, :3] = out[near_r, near_c, :3]
    return np.clip(out, 0, 255).astype(np.uint8)


def face_texture(baseline: np.ndarray, face: tuple, fnv, pieces: tuple, neck: tuple) -> tuple:
    """(the face _d RGBA: T1 on the untinted `baseline` face as drawn, faded at the neck to the body; T1's tone
    scale). `neck` = (seam tree, body, tone -> the skin tint the body is drawn with)."""
    seam, body, tint_of = neck
    out, tone, edge = face_colours(baseline, face, fnv, pieces, 'T1')
    rows, cols, where = texel_points(*face, out.shape[0])
    weight = neck_weight(where, seam)
    drawn = out[rows, cols, :3] * tone
    out[rows, cols, :3] = drawn * (1 - weight) + body_drawn(where, body, tint_of(tone)) * weight
    return _repadded(out, edge), tone


def rear_texture(own: np.ndarray, rear: tuple, frame: np.ndarray, colour: tuple, neck: tuple,
                 whole=None) -> np.ndarray:
    """The rear head's own texture RGBA from its texture `own` (RGBA): FNV's colour (T1: `own` as the template's
    skin tint draws it, plus FNV's offset and race skin; given `whole`, FNV's whole skin times that per-channel
    scale), faded at the neck to `own` as drawn, divided through the NPC's skin tint. `rear` = (points, UVs,
    triangles), `frame` the face points placing it on FNV's head, `colour` = (FNV head, pieces), `neck` = (seam
    tree, (template skin tint, NPC skin tint))."""
    fnv, (stock, offset, race_skin) = colour
    seam, (template, tint) = neck
    rows, cols, fnv_uv, edge = texel_map(rear, (fnv.mean, fnv.triangles, fnv.uvs), own.shape[:2], frame)
    _, _, where = texel_points(*rear, own.shape[0])
    out = own.astype(float)
    base = out[rows, cols, :3]
    added = bilinear(offset, fnv_uv) + (0 if race_skin is None else bilinear(race_skin, fnv_uv))
    above = base * template * SKIN_TINT_DRAW + added if whole is None else (bilinear(stock, fnv_uv) + added) * whole
    weight = neck_weight(where, seam)
    drawn = above * (1 - weight) + base * tint * SKIN_TINT_DRAW * weight
    out[rows, cols, :3] = drawn / (tint * SKIN_TINT_DRAW)
    return _repadded(out, edge)
