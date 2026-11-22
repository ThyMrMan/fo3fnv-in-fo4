"""A FaceGen head's skin with only the skin tone crossing the neck: the face texture is FO4's face as drawn
scaled by FNV's colour over its stock skin (T1, the tone kept in), faded out by the race's neck mask to the face
set's untinted diffuse under the NPC's skin tint, the QNAM that draws its neck darkened by the tone and race shade;
the rear head gets its own texture with the same colour, untinted through that skin tint, faded to its own texture
by the face's neck mask at the nearest face point and over the last NECK_BLEND units above the neck seam.

The game draws a FaceGen face texture as it is, and a skin-tint part (rear head, body) through skin_tint.

See: docs/fork/fo4_look_races_plan.md#face
"""

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.face.bake import NECK_BLEND, point_tree
from fo4_import.face.skin_tint import tint_for, tinted, untinted
from fo4_import.face.texture import bilinear, face_colours, fnv_ratios, per_texel, shared_texel_points, texel_map

#: A face texel counts as neck (where its untinted diffuse sets the skin tint) from this neck mask value up.
NECK_TEXEL = 0.5


def neck_weight(points: np.ndarray, seam: cKDTree) -> np.ndarray:
    """Per point [n, 1]: 1 on the neck seam, 0 from NECK_BLEND above it."""
    near = ((points >= seam.mins - NECK_BLEND) & (points <= seam.maxes + NECK_BLEND)).all(1)
    weight = np.zeros((len(points), 1))
    weight[near, 0] = np.clip(1.0 - seam.query(points[near], distance_upper_bound=NECK_BLEND)[0] / NECK_BLEND, 0, 1)
    return weight


def _repadded(out: np.ndarray, edge: tuple) -> np.ndarray:
    """`out`'s island padding copied again from its edge, as bytes."""
    (pad_r, pad_c), (near_r, near_c) = edge
    out[pad_r, pad_c, :3] = out[near_r, near_c, :3]
    return np.clip(out, 0, 255).astype(np.uint8)


def face_texture(baseline: np.ndarray, face: tuple, fnv, pieces: tuple, neck: tuple) -> tuple:
    """(the face _d RGBA: T1 on the `baseline` face as drawn, faded by the neck mask to the untinted face `head`
    under the NPC's skin tint; that QNAM RGB, drawing the neck as the template's times the tone and race shade).
    `neck` = (mask 0..1, the template's skin tint, the race's shade, `head` RGB), all at `baseline`'s size."""
    mask, template, shade, head = neck
    out, tone, edge = face_colours(baseline, face, fnv, pieces, 'T1')
    rows, cols, _ = shared_texel_points(*face, out.shape[0])
    base = np.median(head[mask >= NECK_TEXEL][:, :3], 0)
    qnam = tint_for(tinted(base, template) * tone * shade, base)

    def blended(r: np.ndarray, c: np.ndarray) -> np.ndarray:
        """Texels (`r`, `c`) faded by the neck mask to `head` under the NPC's tint."""
        stock = tinted(head[r, c, :3], qnam)
        return stock + (out[r, c, :3] * tone - stock) * (1.0 - mask[r, c, None])
    out[rows, cols, :3] = per_texel(blended, rows, cols)
    return _repadded(out, edge), qnam


def rear_texture(own: np.ndarray, rear: tuple, frame: np.ndarray, colour: tuple, neck: tuple,
                 whole=None) -> np.ndarray:
    """The rear head's texture RGBA from its own `own` (RGBA): FNV's colour (T1: `own` as the template's tint
    draws it times fnv_ratios; given `whole`, FNV's whole skin times that scale), faded to `own` as drawn by the
    neck seam and the face's neck fade, over the NPC's tint. `rear` = (points, UVs, triangles), `frame` the face
    points placing it on FNV's head, `colour` = (FNV head, pieces), `neck` = (seam tree, (template tint, NPC
    tint), (face UVs, face neck mask) or None)."""
    fnv, pieces = colour
    seam, (template, tint), face_neck = neck
    rows, cols, fnv_uv, edge = texel_map(rear, (fnv.mean, fnv.triangles, fnv.uvs), own.shape[:2], frame)
    _, _, where = shared_texel_points(*rear, own.shape[0])
    out = own.astype(float)
    base = out[rows, cols, :3]
    if whole is None:
        above = tinted(base, template) * fnv_ratios(pieces, fnv_uv)[1]
    else:
        stock, offset, race_skin = pieces
        above = bilinear(stock + offset if race_skin is None else stock + offset + race_skin, fnv_uv) * whole
    weight = np.maximum(neck_weight(where, seam), face_faded(where, frame, face_neck))
    drawn = above * (1 - weight) + tinted(base, tint) * weight
    out[rows, cols, :3] = untinted(drawn, tint)
    return _repadded(out, edge)


def face_faded(points: np.ndarray, frame: np.ndarray, face_neck) -> np.ndarray:
    """Per point [n, 1]: the face's neck mask at its nearest face point `frame`; zeros without `face_neck`."""
    if face_neck is None:
        return np.zeros((len(points), 1))
    face_uv, mask = face_neck
    return bilinear(mask[..., None], face_uv[point_tree(frame).query(points)[1]])


def shine_texture(own: np.ndarray, part: tuple, frame, fnv, shine: np.ndarray, seam: cKDTree) -> np.ndarray:
    """Specular map `own` (RGBA) with FNV's skin shine `shine` (an FO4 _s image in FNV's head UVs) on part
    `part` = (points, UVs, triangles), placed on FNV's head by the face points `frame` (None: the part's own),
    faded over NECK_BLEND above the neck `seam` to `own`.
    See: docs/fork/fo4_facegen_plan.md#fnv-shine
    """
    rows, cols, fnv_uv, edge = texel_map(part, (fnv.mean, fnv.triangles, fnv.uvs), own.shape[:2], frame)
    _, _, where = shared_texel_points(*part, own.shape[0])
    weight = neck_weight(where, seam)
    out = own.astype(float)
    out[rows, cols, :3] = bilinear(shine, fnv_uv) * (1 - weight) + out[rows, cols, :3] * weight
    return _repadded(out, edge)
