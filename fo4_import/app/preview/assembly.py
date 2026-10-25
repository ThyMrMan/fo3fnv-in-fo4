"""What the preview draws for a record: its models (fo4_import.app.catalog.preview_models), a gun's placed on each
other's connect points.

A gun is its record's model (a receiver "dummy" with no geometry) and its default combination's mods' meshes. A
part's BSConnectPoint::Children `C-X` attaches to a placed part's BSConnectPoint::Parents `P-X`, with that point's
rotation and position (fo4_import.nif.gun.connect_frames); parts are placed as soon as what they attach to is, and
a part with nothing to attach to stays at the origin. A skinned part (a robot's) is already where the skeleton's
bind pose puts it, so it is not moved.

See: docs/fork/fo4_gui.md#preview
"""

import struct

import numpy as np

from fo4_import.app.catalog import preview_models
from fo4_import.app.files import mesh_path
from fo4_import.app.preview.scene import SHAPES, parts_of
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.nif.gun import connect_children, connect_frames, node_worlds


def entry_parts(entry, files, known: dict) -> tuple:
    """(the scene Parts previewing a catalog Entry, why there are none or ''); `known` is catalog.index()."""
    models, why = preview_models(entry, known)
    if not models:
        return [], why
    parts, unread = assemble(files, models)
    if parts:
        return parts, ''
    missing = [m for m in models if m and files.read(mesh_path(m)) is None]
    if missing:
        return [], f'the mesh is not installed: {mesh_path(missing[0])}'
    return [], unread or f'the mesh has no shapes the preview can draw: {mesh_path(models[-1])}'


def assemble(files, models: list) -> tuple:
    """(the scene Parts of `models` (paths under Meshes) found through `files`, placed on their connect points,
    why a mesh could not be read or '')."""
    pending, unread = [], ''
    for model in filter(None, models):
        raw = files.read(mesh_path(model))
        try:
            pending += [nif_file.read(raw)] if raw else []
        except (ValueError, struct.error, IndexError, UnicodeDecodeError) as error:
            unread = f'{mesh_path(model)} could not be read ({error})'
    return _placed(pending), unread


def _placed(pending: list) -> list:
    """The parts of read NIFs `pending`, each placed on the connect point it names once that point is placed."""
    frames, placed = {}, []
    while pending:
        ready = [nif for nif in pending if not connect_children(nif)
                 or any(name in frames for name in connect_children(nif))]
        batch = ready or pending
        for nif in batch:
            frame = np.eye(4) if _skinned(nif) else next((frames[n] for n in connect_children(nif) if n in frames),
                                                         np.eye(4))
            placed += [_moved(part, frame) for part in parts_of(nif)]
            for name, local in connect_frames(nif, node_worlds(nif)).items():
                frames.setdefault(name, local @ frame)
        done = {id(nif) for nif in batch}
        pending = [nif for nif in pending if id(nif) not in done]
    return placed


def _skinned(nif) -> bool:
    """Whether a NIF has skinned shapes (placed by the bind pose)."""
    return any((block if isinstance(block, dict) else read_tri_shape(Reader(block))).get('skin', -1) >= 0
               for kind, block in nif.blocks if kind in SHAPES)


def _moved(part, frame: np.ndarray):
    """`part` with its positions and normals through 4x4 row-vector transform `frame`."""
    part.positions = (part.positions @ frame[:3, :3] + frame[3, :3]).astype(np.float32)
    normals = part.normals @ frame[:3, :3]
    part.normals = (normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)).astype(np.float32)
    return part
