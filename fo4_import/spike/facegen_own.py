"""The faces stage's own FaceGen (--own-facegen): for each NPC the Creation Kit exports (facegeom.exported), our
FaceGeom NIF (facegeom.build) and face _d, _msn and _s (face_tint) at vanilla's formats and sizes, written where
the CK's export lands in the mod folder, in facegen_skin's worker pool. An NPC that fails is listed with its error
instead of stopping the run; the stage gives those NPCs the CK's export (facegen.fallback).

See: docs/fork/fo4_facegen_plan.md#own-stage
"""

import functools
import hashlib
import pickle
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import numpy as np

from fo4_import.face import face_tint, facegeom, own_facegen
from fo4_import.face.texture import TEXCONV, VANILLA_FACE, vanilla_dds
from fo4_import.pipeline import work_cache
from fo4_import.pipeline.ran_code import ran_while
from fo4_import.spike import facegen_skin
from tes5_import.base.tes5_reader import masters, walk

#: own_face's status of an NPC written, written from the work cache, and one the CK exports no FaceGen for.
WRITTEN, KEPT, SKIPPED = 'written', 'kept', 'skipped'
#: The work cache site of an NPC's own FaceGen files (cached_files).
SITE = 'own_face'


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


def face_files(src: facegeom.Sources, plugin: str, form_id: int) -> 'dict | None':
    """{path under Data: bytes} of NPC `form_id`'s FaceGeom NIF and face textures, as the CK names them; None for
    an NPC the CK exports none for."""
    npc, race, female, _ = facegeom.npc_face(src, plugin, form_id)
    if not facegeom.exported(npc, race):
        return None
    stem = f'{form_id:08X}'
    files = {(own_facegen.GEOM_DIR / plugin / f'{stem}.nif').as_posix(): facegeom.build(src, plugin, form_id)}
    for kind, rgba in face_textures(face_tint.Face(src, npc, race, female)).items():
        files[(own_facegen.FACE_DIR / plugin / f'{stem}_{kind}.dds').as_posix()] = vanilla_dds(rgba, kind)
    return files


def held(rec: 'facegeom.Rec | None') -> bytes:
    """A record's owner, signature and subrecords as bytes (b'' for none)."""
    return pickle.dumps((rec.owner, rec.sig, rec.subs)) if rec else b''


@functools.cache
def digest(src: facegeom.Sources, item) -> 'str | None':
    """SHA-1 of what `src` holds for `item` (Sources.seen: a record's (owner, local id), or a file); None if absent."""
    try:
        data = held(src.records.get(item)) if isinstance(item, tuple) else src.stored(item)
    except (OSError, KeyError):
        return None
    return hashlib.sha1(data).hexdigest()


def npc_record(src: facegeom.Sources, item) -> bool:
    """Whether `item` (Sources.seen) is an NPC_ record."""
    return isinstance(item, tuple) and getattr(src.records.get(item), 'sig', None) == b'NPC_'


def reading(src: facegeom.Sources, make) -> tuple:
    """(make()'s value, {item: digest} of what it read (Sources.seen) and what earlier work in this process read,
    which a memo may hold, but other NPCs' records).
    See: docs/fork/fo4_facegen_plan.md#own-cache
    """
    earlier = set(src.seen)
    src.seen.clear()
    try:
        value = make()
    finally:
        mine = set(src.seen)
        src.seen |= earlier
    used = mine | {item for item in earlier if not npc_record(src, item)}
    return value, {item: digest(src, item) for item in used}


def unchanged(src: facegeom.Sources, kept: dict) -> bool:
    """Whether `src` holds every record and file of `kept` (reads) as it was."""
    return all(digest(src, item) == was for item, was in kept.items())


@functools.cache
def texconv() -> str:
    """SHA-1 of the texconv the face textures are encoded with."""
    return hashlib.sha1(TEXCONV.read_bytes()).hexdigest()


def cached_files(src: facegeom.Sources, plugin: str, form_id: int) -> tuple:
    """(face_files(), whether it came from the work cache): kept by the NPC record, the plugins' masters and texconv,
    and used while every other record and file it read (reads) and the code that made it are unchanged.
    See: docs/fork/fo4_facegen_plan.md#own-cache
    """
    npc = src.records.get((plugin.lower(), form_id & 0xFFFFFF))
    inputs = (plugin.lower(), form_id, held(npc), sorted(src.masters.items()), texconv())
    kept = work_cache.lookup(SITE, __name__, inputs)
    if kept is not None and unchanged(src, kept[0]):
        return kept[1], True
    (files, ran), read = reading(src, functools.partial(ran_while, functools.partial(face_files, src, plugin, form_id)))
    work_cache.store(SITE, __name__, inputs, (read, files), ran)
    return files, False


def write_face(src: facegeom.Sources, plugin: str, form_id: int, data_dir: Path) -> str:
    """Write NPC `form_id`'s FaceGeom NIF and face textures (cached_files) under `data_dir`; WRITTEN, KEPT (from the
    cache) or SKIPPED (none exported)."""
    files, kept = cached_files(src, plugin, form_id)
    for rel, data in (files or {}).items():
        (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (data_dir / rel).write_bytes(data)
    return SKIPPED if files is None else KEPT if kept else WRITTEN


def own_face(form_id: int) -> tuple:
    """(FormID, WRITTEN, SKIPPED or the error) of write_face in a facegen_skin worker; never raises."""
    worker = facegen_skin.shared()
    try:
        return form_id, write_face(worker['src'], worker['plugin'], form_id, worker['data'])
    except Exception as e:
        return form_id, f'{type(e).__name__}: {e}'


def export_own(job: tuple, forms: list) -> tuple:
    """(written, kept, skipped, {FormID: error}) of own_face over `forms` in facegen_skin's pool sharing `job`
    (kept: written from the work cache); a pool that breaks (a worker killed) fails every face."""
    try:
        results = facegen_skin.pool(job, own_face, forms)
    except BrokenProcessPool as e:
        results = [(form_id, f'worker pool broke: {e}') for form_id in forms]
    failed = {form_id: status for form_id, status in results if status not in (WRITTEN, KEPT, SKIPPED)}
    return tuple(sum(s == want for _, s in results) for want in (WRITTEN, KEPT, SKIPPED)) + (failed,)
