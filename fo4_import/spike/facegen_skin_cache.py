"""The faces stage's skin step (facegen_skin.skin_face) kept per NPC in the work cache, so a rebuild writes each
face's skin, rear head and FaceGeom from the cache instead of drawing them again.

An entry is keyed by the NPC record, its plugin's masters, texconv, the skin tone templates, and the bytes of the
face's FaceGeom NIF and face textures the heads step left (the skin reads and rewrites them in place). It holds
what the skin read beside those (the profile's records and files, Sources.seen; the export's files, file_access)
and is used while all of it and the code that made it are unchanged; it keeps the files the skin wrote and the
NPC's skin tone.

See: docs/fork/fo4_facegen_plan.md#skin-cache
"""

import functools
import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np

from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face import own_facegen
from fo4_import.pipeline import file_access, work_cache
from fo4_import.pipeline.ran_code import ran_while
from fo4_import.spike import facegen_skin
from fo4_import.spike.facegen_own import held, reading, texconv, unchanged

#: The work cache site of an NPC's skin.
SITE = 'face_skin'
#: The face texture kinds the heads step writes and the skin reads.
KINDS = ('d', 'msn', 's')
#: Suffixes of the code a call may import while it runs: not an input of the face.
CODE = ('.py', '.pyc', '.pyd', '.dll')


def face_inputs(face: facegen_skin.Face) -> tuple:
    """The cache key's inputs of `face` (module doc)."""
    worker, stem = facegen_skin.shared(), f'{face.form_id:08X}'
    src, plugin, folder = worker['src'], worker['plugin'], worker['data'] / own_facegen.FACE_DIR / worker['plugin']
    npc = src.records.get((plugin.lower(), face.form_id))
    files = [facegen_skin.nif_path(face)] + [folder / f'{stem}_{kind}.dds' for kind in KINDS]
    return (plugin.lower(), face, held(npc), src.masters.get(plugin.lower()), texconv(),
            {k: v.round(6).tolist() for k, v in worker['templates'].items()},
            [hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else None for p in files])


def outside(paths, src) -> dict:
    """{path: SHA-1} of `paths` (not code) outside `src`'s folders, game Data and temp."""
    folders = (*src.dirs, FALLOUT4_DIR / 'Data', tempfile.gettempdir())
    roots = tuple(os.path.normcase(os.path.abspath(d)) + os.sep for d in folders)
    return {p: file_access.digest(p) for p in sorted(paths) if not p.startswith(roots) and not p.endswith(CODE)}


def written(paths, data_dir: Path) -> dict:
    """{path under `data_dir` (posix): bytes} of the files `paths` (file_access) there."""
    root = Path(os.path.abspath(data_dir))
    return {Path(p).relative_to(root).as_posix(): Path(p).read_bytes() for p in sorted(paths)
            if Path(p).is_relative_to(root) and Path(p).is_file()}


def skin_face(face: facegen_skin.Face) -> tuple:
    """facegen_skin.skin_face's (FormID, QNAM RGB, report lines) and whether it came from the work cache: its
    files written from there when an entry for its inputs is current, else drawn and kept."""
    worker = facegen_skin.shared()
    src, data_dir, inputs = worker['src'], worker['data'], face_inputs(face)
    kept = work_cache.lookup(SITE, __name__, inputs)
    if kept is not None and unchanged(src, kept[0]) and all(file_access.digest(p) == d for p, d in kept[1].items()):
        files, qnam, lines = kept[2:]
        for rel, data in files.items():
            (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (data_dir / rel).write_bytes(data)
        return face.form_id, np.array(qnam), lines, True
    make = functools.partial(file_access.opened, functools.partial(ran_while, functools.partial(
        facegen_skin.skin_face, face)))
    (((form_id, qnam, lines), ran), reads, writes), records = reading(src, make)
    value = (records, outside(reads, src), written(writes, data_dir), np.asarray(qnam).tolist(), lines)
    work_cache.store(SITE, __name__, inputs, value, ran)
    return form_id, qnam, lines, False


def skin(job: tuple, faces: list) -> list:
    """Write every face's skin, FaceGeom and skin tone (skin_face; tones patched into the plugin); report lines."""
    data_dir, plugin, layers = job[1], job[2], job[3]
    done = facegen_skin.pool(job, skin_face, faces)
    facegen_skin.patch(data_dir / plugin, {fid: facegen_skin.tone_edit(qnam, layers) for fid, qnam, *_ in done})
    kept = sum(hit for *_, hit in done)
    return ([f'{fid:08X} {line}' for fid, _, lines, _ in done for line in lines]
            + [f'faces skinned: {len(done)} ({kept} from the work cache)'])
