"""FNV faces fitted to FO4's own face data: slider values (sculpt regions and morph presets) and tint layers.

At plugin build time a clone's sliders (face.slider_fit) and tint layers
(face.tint) are fitted to its FNV NPC; the faces stage refits the sliders to
the Creation Kit's export (spike.facegen_skin).

See: docs/fork/fo4_facegen_plan.md#build-faces
See: docs/fork/fo4_spikes.md#spike-2-tints
"""

import struct
from pathlib import Path

import numpy as np

from fo4_import.face import hair, sculpt, slider_fit, tint
from fo4_import.face.bake import face_shape
from fo4_import.face.texture import face_colours
from fo4_import.spike import fnv_npc
from fo4_import.spike.fnv_npc import fnv_face, npc_head
from tes5_import.base.tes5_reader import REC_HDR, SUB_HDR


def record_subrecords(raw: bytearray, offset: int, size: int) -> list:
    """[(tag, data offset, size)] of the uncompressed record at `offset` (body `size`) in `raw`."""
    out, pos, end = [], offset + REC_HDR, offset + REC_HDR + size
    while pos < end:
        length = struct.unpack_from('<H', raw, pos + 4)[0]
        out.append((bytes(raw[pos:pos + 4]), pos + SUB_HDR, length))
        pos += SUB_HDR + length
    return out


def sculpt_fit(export_dir: Path, edid: str, female: bool = False) -> 'tuple | None':
    """slider_fit.fit of FNV NPC `edid`; None uncalibrated."""
    if not slider_fit.calibrated(female):
        return None
    return slider_fit.fit(female, npc_head(export_dir, edid)[0])


def brow_overlay(export_dir: Path, edid: str, face: tuple, size: int = tint.WORK_SIZE) -> np.ndarray:
    """[size, size, 4] RGBA of FNV NPC `edid`'s brows as FNV draws them, on the FO4 face's texels."""
    at = fnv_npc.frame(export_dir, edid, face[0])
    out = np.zeros((size, size, 4))
    for mesh in fnv_npc.sorted_parts(export_dir, at)[1]:
        points, tris, uv, _ = hair.fnv_shape(mesh)
        spread, spread_uv = hair.samples(at.to_fo4(points), tris, uv)
        drawn = hair.texels(fnv_npc.hair_rgb(fnv_npc.mesh_texture(export_dir, mesh), at.npc), spread_uv)
        layer = hair.onto_face(face, size, spread, drawn)
        out = np.where(layer[..., 3:] > out[..., 3:], layer, out)
    return out


def tint_target(export_dir: Path, edid: str, female: bool = False) -> tuple:
    """(target change of the reduced face texture, face mask, skin tone scale) for FNV NPC `edid`.

    The target is T1's colour, worked out on the reduced texture, with the NPC's brows drawn over it.
    See: docs/fork/fo4_build_speed.md#faces
    """
    face = face_shape(sculpt.load_basis(female)[2])
    base = tint.reduced(tint.load_basis(female)[2])
    fnv, pieces = fnv_face(export_dir, edid)
    colour, tone, _ = face_colours(base, face, fnv, pieces, 'T1')
    brows = brow_overlay(export_dir, edid, face)
    alpha = brows[..., 3:] / 255
    target = np.clip(colour, 0, 255) * (1 - alpha) + brows[..., :3] * alpha
    return target - base, tint.face_mask(face), tone


def tint_fit(export_dir: Path, edid: str, female: bool = False) -> tuple:
    """(fitted value per option of its sex's basis, skin tone scale, fraction captured); None uncalibrated."""
    if tint.load_basis(female) is None or sculpt.load_basis(female) is None:
        return None
    target, mask, tone = tint_target(export_dir, edid, female)
    values, captured = tint.brow_fits(female, mask).best(target)
    return values, tone, captured
