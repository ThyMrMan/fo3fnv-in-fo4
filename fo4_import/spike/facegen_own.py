"""The faces stage's own FaceGen (--own-facegen): for each NPC the Creation Kit exports (facegeom.exported), our
FaceGeom NIF (facegeom.build) and face _d, _msn and _s (face_tint) at vanilla's formats and sizes, written where
the CK's export lands in the mod folder, in facegen_skin's worker pool. An NPC that fails is listed with its error
instead of stopping the run; the stage gives those NPCs the CK's export (facegen.fallback).

See: docs/fork/fo4_facegen_plan.md#own-stage
"""

from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import numpy as np

from fo4_import.face import face_tint, facegeom, own_facegen
from fo4_import.face.texture import VANILLA_FACE, vanilla_dds
from fo4_import.spike import facegen_skin
from tes5_import.base.tes5_reader import masters, walk

#: own_face's status of an NPC written, and of one the CK exports no FaceGen for.
WRITTEN, SKIPPED = 'written', 'skipped'


def own_npcs(plugin_path: Path) -> list:
    """Sorted local FormIDs of the NPC_ records the plugin adds."""
    data = plugin_path.read_bytes()
    own = len(masters(data))
    return sorted(rec.form_id & 0xFFFFFF for rec, _ in walk(data, b'NPC_') if rec.form_id >> 24 == own)


def face_textures(face: face_tint.Face) -> dict:
    """{kind: RGBA uint8} of the face's _d, _msn and _s, each drawn at vanilla's size for it (VANILLA_FACE)."""
    out = {}
    for kind, (_, size) in VANILLA_FACE.items():
        values = face_tint.face_diffuse(face, size) if kind == 'd' else face_tint.face_map(face, kind, size)
        rgb = np.asarray(face_tint.as_image(values))
        out[kind] = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    return out


def write_face(src: facegeom.Sources, plugin: str, form_id: int, data_dir: Path) -> str:
    """Write NPC `form_id`'s FaceGeom NIF and face textures under `data_dir`, as the CK names them; WRITTEN, or
    SKIPPED for an NPC the CK exports none for. Everything is made before anything is written."""
    npc, race, female, _ = facegeom.npc_face(src, plugin, form_id)
    if not facegeom.exported(npc, race):
        return SKIPPED
    nif = facegeom.build(src, plugin, form_id)
    textures = {kind: vanilla_dds(rgba, kind)
                for kind, rgba in face_textures(face_tint.Face(src, npc, race, female)).items()}
    stem, folder = f'{form_id:08X}', data_dir / own_facegen.FACE_DIR / plugin
    geom = data_dir / own_facegen.GEOM_DIR / plugin / f'{stem}.nif'
    geom.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    geom.write_bytes(nif)
    for kind, dds in textures.items():
        (folder / f'{stem}_{kind}.dds').write_bytes(dds)
    return WRITTEN


def own_face(form_id: int) -> tuple:
    """(FormID, WRITTEN, SKIPPED or the error) of write_face in a facegen_skin worker; never raises."""
    worker = facegen_skin.shared()
    try:
        return form_id, write_face(worker['src'], worker['plugin'], form_id, worker['data'])
    except Exception as e:
        return form_id, f'{type(e).__name__}: {e}'


def export_own(job: tuple, forms: list) -> tuple:
    """(written, skipped, {FormID: error}) of own_face over `forms` in facegen_skin's pool sharing `job`; a pool
    that breaks (a worker killed) fails every face."""
    try:
        results = facegen_skin.pool(job, own_face, forms)
    except BrokenProcessPool as e:
        results = [(form_id, f'worker pool broke: {e}') for form_id in forms]
    failed = {form_id: status for form_id, status in results if status not in (WRITTEN, SKIPPED)}
    return sum(s == WRITTEN for _, s in results), sum(s == SKIPPED for _, s in results), failed
