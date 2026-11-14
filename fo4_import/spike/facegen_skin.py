"""The faces stage's work on the Creation Kit's heads, in worker processes: each fitted NPC's sliders refitted to
the miss of the CK's first export, then its skin (face.npc_skin) and skin tone, both patched into the plugin where
they lie (fixed sizes, one pass).

A fitted NPC is a converted one with sculpt regions (FMRI); its own face set (FTST) marks a race with its own
skin. Records and assets resolve through MO2's selected profile, as the CK sees them, without FaceGen test
plugins (description starting TEST_DESCRIPTION) or the mod folders holding them.

See: docs/fork/fo4_facegen_plan.md#build-faces
"""

import os
import struct
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.build_resources import pool_workers
from core.process_job import join_pool_job
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import facegeom, npc_skin, own_facegen, sculpt, slider_fit, tint
from fo4_import.face.bake import face_shape
from fo4_import.pipeline import creation_kit
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.face_fit import brow_overlay, record_subrecords
from fo4_import.spike.fnv_npc import fnv_face, fnv_shine, npc_head
from tes5_import.base.tes5_reader import subrecords, walk

#: How every FaceGen test plugin's description starts, so the stage reads past them.
TEST_DESCRIPTION = 'FaceGen test'
#: Bytes one worker holds at most (Sources peaks at 1.84 GB). See #own-stage-speed.
WORKER_BYTES = 2 << 30
#: FO4 ACBS flag Female.
FEMALE = 0x1
#: A worker process's shared inputs (_start).
_worker = {}


@dataclass(frozen=True)
class Face:
    """A fitted NPC of the plugin: local FormID, FNV EditorID, female, own face set."""

    form_id: int
    edid: str
    female: bool
    own: bool


def fitted_faces(data_dir: Path, plugin: str, export_dir: Path) -> list:
    """The plugin's fitted NPCs (module doc) whose FaceGeom the export wrote and that FNV made as NPCs (`export_dir`'s
    NPC_ records), by FormID. One the export skips (facegeom.exported) or a converted creature has no FNV FaceGen
    to refit or skin to.
    See: docs/fork/fo4_facegen_plan.md#own-stage
    """
    out, geom = [], data_dir / own_facegen.GEOM_DIR / plugin
    npcs = {own_facegen.FNV_PREFIX + r['EditorID'] for r in export_records(export_dir, 'NPC_') if 'EditorID' in r}
    for rec, _ in walk((data_dir / plugin).read_bytes(), b'NPC_'):
        subs = dict(subrecords(rec.body))
        edid = facegeom.zstr(subs.get(b'EDID', b'\0'))
        has_geom = (geom / f'{rec.form_id & 0xFFFFFF:08X}.nif').is_file()
        if b'FMRI' in subs and edid in npcs and has_geom:
            female = bool(struct.unpack_from('<I', subs[b'ACBS'])[0] & FEMALE)
            out.append(Face(rec.form_id & 0xFFFFFF, edid[len(own_facegen.FNV_PREFIX):], female, b'FTST' in subs))
    return sorted(out, key=lambda f: f.form_id)


def without_tests(dirs: list, order: list) -> tuple:
    """(`dirs`, `order`) without FaceGen test plugins and the mod folders holding one."""
    tests = {name for name in order if own_facegen.find(dirs, name).is_file()
             and description(own_facegen.find(dirs, name).read_bytes()).startswith(TEST_DESCRIPTION)}
    return [d for d in dirs if not any((d / name).is_file() for name in tests)], [n for n in order if n not in tests]


def description(data: bytes) -> str:
    """A plugin's description (TES4 SNAM)."""
    size = struct.unpack_from('<I', data, 4)[0]
    return next((facegeom.zstr(d) for t, d in subrecords(data[24:24 + size]) if t == b'SNAM'), '')


def sources(plugin_path: Path, data_dir: Path) -> facegeom.Sources:
    """The plugin's records and files as the CK sees them (module doc)."""
    dirs, order = own_facegen.profile_order(creation_kit.profile_dir(), creation_kit.MO2, (data_dir.name,))
    dirs, order = without_tests(dirs, order)
    return facegeom.Sources(plugin_path, [data_dir, *dirs], order)


def _start(job: tuple) -> None:
    """A worker's start: join the pool job; job = (export, data folder, plugin, Skin Tone layers)."""
    join_pool_job()
    export_dir, data_dir, plugin, layers = job
    templates = own_facegen.template_tones(FALLOUT4_ESM.read_bytes(), layers)
    _worker.update(export=export_dir, data=data_dir, plugin=plugin, src=sources(data_dir / plugin, data_dir),
                   templates={f: np.array(struct.unpack('<4f', t[0])[:3]) for f, t in templates.items()}, bodies={})


def shared() -> dict:
    """This worker's shared inputs (_start): export, data, plugin, src..."""
    return _worker


def workers(jobs: int) -> int:
    """Worker processes for `jobs` faces: half the cores, pool_workers()' memory."""
    return pool_workers(WORKER_BYTES, jobs, max(1, (os.cpu_count() or 2) // 2))


def pool(job: tuple, work, faces: list) -> list:
    """`work` over `faces` in worker processes sharing `job` (_start), in order."""
    if not faces:
        return []
    with ProcessPoolExecutor(max_workers=workers(len(faces)), initializer=_start, initargs=(job,)) as executor:
        return list(executor.map(work, faces, chunksize=4))


def nif_path(face: Face) -> Path:
    """The face's FaceGeom NIF in the worker's data folder."""
    return _worker['data'] / own_facegen.GEOM_DIR / _worker['plugin'] / f'{face.form_id:08X}.nif'


def record_sliders(npc: facegeom.Rec, p: slider_fit.Problem) -> tuple:
    """(sculpt values [region, CONTROLS] in p.regions' order, {MSDK key: weight}) of NPC record `npc`."""
    values, region, keys, weights = np.zeros((len(p.regions), sculpt.CONTROLS)), None, [], []
    for tag, data in npc.subs:
        region = struct.unpack('<I', data)[0] if tag == b'FMRI' else region
        if tag == b'FMRS' and region in p.regions:
            values[p.regions.index(region)] = struct.unpack_from(f'<{sculpt.CONTROLS}f', data)
        keys = list(struct.unpack(f'<{len(data) // 4}I', data)) if tag == b'MSDK' else keys
        weights = list(struct.unpack(f'<{len(data) // 4}f', data)) if tag == b'MSDV' else weights
    return values, dict(zip(keys, weights))


def refit_face(face: Face) -> 'tuple | None':
    """(FormID, new sculpt values {region: controls}, new weights in the record's MSDK order, rms miss of the
    export) of the face refitted to its target moved by the CK export's miss; None when a later plugin overrides
    the NPC (its sliders are that plugin's, not ours to patch).
    See: docs/fork/fo4_facegen_plan.md#own-stage
    """
    p = slider_fit.problem(face.female)
    npc = facegeom.npc_face(_worker['src'], _worker['plugin'], face.form_id)[0]
    if npc.owner != _worker['plugin'].lower():
        return None
    values, weights = record_sliders(npc, p)
    goal = slider_fit.target(p, npc_head(_worker['export'], face.edid)[0])
    actual = slider_fit.measured(p, nif_path(face).read_bytes())
    new = slider_fit.refit(p, goal + slider_fit.predicted(p, values, weights) - actual, weights)
    picked = {k: v for k, _, v in new.presets}
    rows = dict(zip(p.regions, new.sculpt))
    return face.form_id, rows, [picked.get(k, 0.0) for k in weights], slider_fit.rms(actual - goal)


def body(npc, race, female: bool, slot: int) -> tuple:
    """own_facegen.body of the NPC's body texture set slot `slot`, read once per worker per texture."""
    src = _worker['src']
    key = (facegeom.body_textures(src, npc, race, female)[slot], female)
    if key not in _worker['bodies']:
        _worker['bodies'][key] = own_facegen.body(src, npc, race, female, slot)
    return _worker['bodies'][key]


def skin_of(face: Face) -> npc_skin.Skin:
    """The face's npc_skin.Skin, read through the worker's Sources and export."""
    src, export = _worker['src'], _worker['export']
    npc, race, female, _ = facegeom.npc_face(src, _worker['plugin'], face.form_id)
    textures = facegeom.body_textures(src, npc, race, female)
    size = npc_skin.template_face(female).shape[0]
    brows = None if face.own else brow_overlay(export, face.edid, face_shape(sculpt.load_basis(female)[2]), size)
    return npc_skin.Skin(female, fnv_face(export, face.edid), face.own, brows,
                         fnv_shine(export, face.edid) if face.own else None, body(npc, race, female, 0),
                         body(npc, race, female, npc_skin.SPECULAR) if face.own else None,
                         (src.read('textures\\' + textures[0]), src.read('textures\\' + textures[npc_skin.SPECULAR])),
                         _worker['templates'][female])


def skin_face(face: Face) -> tuple:
    """Write the face's skin and FaceGeom; (FormID, QNAM RGB, report lines)."""
    stem, plugin = f'{face.form_id:08X}', _worker['plugin']
    folder = _worker['data'] / own_facegen.FACE_DIR / plugin
    rear = (_worker['data'] / 'Textures', f'{own_facegen.FACE_PATH}\\{plugin}\\{stem}_rear')
    nif, qnam, lines = npc_skin.skinned(skin_of(face), nif_path(face).read_bytes(), folder, stem, rear)
    nif_path(face).write_bytes(nif)
    return face.form_id, qnam, lines


def patch(plugin_path: Path, edits: dict) -> None:
    """Apply `edits` {FormID: edit(raw, [(tag, data offset, size)])} to the plugin's NPC_ records where they lie."""
    raw = bytearray(plugin_path.read_bytes())
    for rec, _ in walk(bytes(raw), b'NPC_'):
        edit = edits.get(rec.form_id & 0xFFFFFF)
        if edit:
            edit(raw, record_subrecords(raw, rec.offset, rec.size))
    plugin_path.write_bytes(bytes(raw))


def slider_edit(rows: dict, weights: list):
    """An edit writing sculpt values `rows` {region: controls} (each FMRS by its FMRI) and preset `weights`."""
    def edit(raw: bytearray, subs: list) -> None:
        """Patch the record's FMRS and MSDV."""
        region = None
        for tag, at, size in subs:
            region = struct.unpack_from('<I', raw, at)[0] if tag == b'FMRI' else region
            if tag == b'FMRS' and region in rows:
                struct.pack_into(f'<{sculpt.CONTROLS}f', raw, at, *rows[region])
            elif tag == b'MSDV':
                struct.pack_into(f'<{size // 4}f', raw, at, *weights)
    return edit


def tone_edit(qnam: np.ndarray, layers: frozenset):
    """An edit scaling the record's QNAM to `qnam` and its Skin Tone layer colour by the same scale."""
    def edit(raw: bytearray, subs: list) -> None:
        """Patch the record's QNAM and Skin Tone TEND."""
        at = next(a for t, a, _ in subs if t == b'QNAM')
        scale, layer = npc_skin.tone_scale(qnam, bytes(raw[at:at + 16])), None
        for tag, at, size in subs:
            layer = struct.unpack_from('<HH', raw, at)[1] if tag == b'TETI' else layer
            if tag == b'QNAM' or (tag == b'TEND' and layer in layers and size >= 4):
                raw[at:at + size] = tint.scaled_tone(tag, bytes(raw[at:at + size]), scale)
    return edit


def refine(job: tuple, faces: list) -> list:
    """Refit every face the plugin's own record shows (refit_face) to the export and patch the plugin; report
    lines."""
    data_dir, plugin = job[1], job[2]
    results = pool(job, refit_face, faces)
    fits = [fit for fit in results if fit]
    patch(data_dir / plugin, {fid: slider_edit(values, weights) for fid, values, weights, _ in fits})
    misses = [miss for *_, miss in fits]
    return [f'sliders refitted to the export: {len(fits)} faces, rms miss median {np.median(misses):.3f}, '
            f'max {max(misses):.3f}; overridden by a later plugin, left: {len(results) - len(fits)}'] if fits else []


def skin(job: tuple, faces: list) -> list:
    """Write every face's skin, FaceGeom and skin tone (patched into the plugin); report lines."""
    data_dir, plugin, layers = job[1], job[2], job[3]
    done = pool(job, skin_face, faces)
    patch(data_dir / plugin, {fid: tone_edit(qnam, layers) for fid, qnam, _ in done})
    return [f'{fid:08X} {line}' for fid, _, lines in done for line in lines] + [f'faces skinned: {len(done)}']
