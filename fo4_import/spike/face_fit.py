"""FNV faces fitted to FO4's own face data: sculpt regions and tint layers, then refined against the CK.

At plugin build time a clone's sculpt values (face.sculpt) and tint layers
(face.tint) are fitted to its FNV NPC; after each CK export, `refine_*`
measure what the CK made, refit the miss, and patch the values in place
(the layouts are fixed, so the plugin keeps its sizes).

See: docs/fork/fo4_spikes.md#spike-2-sculpt
See: docs/fork/fo4_spikes.md#spike-2-tints
"""

import struct
from pathlib import Path

import numpy as np

from fo4_import.face import hair, sculpt, tint
from fo4_import.face.bake import face_moves, face_shape
from fo4_import.face.texture import face_texture
from fo4_import.spike import fnv_npc
from fo4_import.spike.fnv_npc import fnv_face, npc_head
from tes5_import.base.tes5_reader import REC_HDR, SUB_HDR, first_sub, walk


def npc_subrecords(raw: bytearray, form_id: int) -> list:
    """[(tag, data offset, size)] of NPC `form_id`'s subrecords in the plugin bytes `raw` (uncompressed)."""
    rec = next(r for r, _ in walk(bytes(raw), b'NPC_') if r.form_id & 0xFFFFFF == form_id)
    out, pos, end = [], rec.offset + REC_HDR, rec.offset + REC_HDR + rec.size
    while pos < end:
        size = struct.unpack_from('<H', raw, pos + 4)[0]
        out.append((bytes(raw[pos:pos + 4]), pos + SUB_HDR, size))
        pos += SUB_HDR + size
    return out


def variant_npcs(plugin_path: Path, variants) -> dict:
    """{FormID: (FNV EditorID, variant)} of the plugin's NPCs named `FNV_<EditorID>_<variant in variants>`."""
    out = {}
    for rec, _ in walk(plugin_path.read_bytes(), b'NPC_'):
        edid = (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')
        stem, _, variant = edid.rpartition('_')
        if edid.startswith('FNV_') and variant in variants:
            out[rec.form_id & 0xFFFFFF] = (stem[len('FNV_'):], variant)
    return out


def sculpt_fit(export_dir: Path, edid: str) -> tuple:
    """(FMRI/FMRS for every region fitted to FNV NPC `edid`'s face, fraction captured); None uncalibrated."""
    cached = sculpt.load_basis()
    if cached is None:
        return None
    basis, regions, baseline = cached
    values, captured = sculpt.fit(basis, face_moves(baseline, npc_head(export_dir, edid)[0], 'C1')[1])
    return sculpt.face_morphs(regions, values, all_regions=True), captured


def refine_sculpt(plugin_path: Path, form_id: int, edid: str, nif: Path, export_dir: Path, apply: bool) -> float:
    """Measure NPC `form_id`'s exported head (`nif`) and, with `apply`, refine its sculpt values; captured."""
    basis, _, baseline = sculpt.load_basis()
    head_points, target = face_moves(baseline, npc_head(export_dir, edid)[0], 'C1')
    raw = bytearray(plugin_path.read_bytes())
    slots = [data for tag, data, _ in npc_subrecords(raw, form_id) if tag == b'FMRS']
    values = np.array([struct.unpack_from(f'<{sculpt.CONTROLS}f', raw, s) for s in slots])
    values, captured = sculpt.refine(basis, values, target, face_shape(nif.read_bytes())[0] - head_points)
    if apply:
        for s, row in zip(slots, values):
            struct.pack_into(f'<{sculpt.CONTROLS}f', raw, s, *row)
        plugin_path.write_bytes(bytes(raw))
    return captured


def brow_overlay(export_dir: Path, edid: str, face: tuple) -> np.ndarray:
    """[WORK_SIZE, WORK_SIZE, 4] RGBA of FNV NPC `edid`'s brows as FNV draws them, on the FO4 face's texels."""
    at = fnv_npc.frame(export_dir, edid, face[0])
    out = np.zeros((tint.WORK_SIZE, tint.WORK_SIZE, 4))
    for mesh in fnv_npc.sorted_parts(export_dir, at)[1]:
        points, tris, uv, _ = hair.fnv_shape(mesh)
        spread, spread_uv = hair.samples(at.to_fo4(points), tris, uv)
        drawn = hair.texels(fnv_npc.hair_rgb(fnv_npc.mesh_texture(export_dir, mesh), at.npc), spread_uv)
        layer = hair.onto_face(face, tint.WORK_SIZE, spread, drawn)
        out = np.where(layer[..., 3:] > out[..., 3:], layer, out)
    return out


def tint_target(export_dir: Path, edid: str) -> tuple:
    """(target change of the reduced face texture, face mask, skin tone scale) for FNV NPC `edid`.

    The target is T1's colour with the NPC's brows drawn over it.
    """
    face = face_shape(sculpt.load_basis()[2])
    base = tint.load_basis()[2]
    fnv, pieces = fnv_face(export_dir, edid)
    rgba, tone = face_texture(base, face, fnv, pieces, 'T1')
    brows = brow_overlay(export_dir, edid, face)
    alpha = brows[..., 3:] / 255
    target = tint.reduced(rgba) * (1 - alpha) + brows[..., :3] * alpha
    return target - tint.reduced(base), tint.face_mask(face), tone


def tint_fit(export_dir: Path, edid: str) -> tuple:
    """(fitted value per option, skin tone scale, fraction captured); None uncalibrated."""
    cached = tint.load_basis()
    if cached is None or sculpt.load_basis() is None:
        return None
    target, mask, tone = tint_target(export_dir, edid)
    values, captured = tint.fit_with_brow(cached[0], target, mask, [cached[1].index(b) for b in cached[3]])
    return values, tone, captured


def refine_tint(plugin_path: Path, form_id: int, edid: str, diffuse: Path, export_dir: Path, apply: bool) -> float:
    """Measure NPC `form_id`'s exported face texture and, with `apply`, refine its tint layers; captured."""
    effects, options, baseline, brows = tint.load_basis()
    target, mask, _ = tint_target(export_dir, edid)
    raw = bytearray(plugin_path.read_bytes())
    slots, index = {}, None
    for tag, data, _ in npc_subrecords(raw, form_id):
        if tag == b'TETI':
            index = struct.unpack_from('<HH', raw, data)[1]
        elif tag == b'TEND' and index in options:
            slots[index] = data
    values = np.array([raw[slots[o]] / 100 if o in slots else 0.0 for o in options])
    free = [i for i, o in enumerate(options) if o not in brows]
    actual = tint.reduced(diffuse) - tint.reduced(baseline)
    values, captured = tint.refine(effects, values, target, actual, mask, free)
    if apply:
        for i in free:
            raw[slots[options[i]]] = int(round(values[i] * 100))
        plugin_path.write_bytes(bytes(raw))
    return captured
