"""An FNV NPC's head as FNV draws it: the race's head mesh moved by FaceGen's .egm morphs.

FNV's head (`characters\\head\\headhuman.nif` for the human races) is the
mean face; its .egm holds 50 symmetric and 30 asymmetric morph modes over
the FaceGen vertex list (the mesh's vertices, then the .tri's modifier
vertices), each a float scale times int16 x/y/z per vertex. An NPC's shape
is the mean plus FGGS times the symmetric modes plus FGGA times the
asymmetric ones.

See: docs/fork/fo4_spikes.md#spike-2-facegen
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from asset_convert.nif.pyffi_monkey_patch import apply_patches

apply_patches()
from pyffi.formats.nif import NifFormat

EGM_MAGIC = b'FREGM002'
EGM_HEADER = 64


@dataclass
class FnvHead:
    """A head mesh: mean vertices, triangles, and the NPC's vertices."""
    mean: np.ndarray
    triangles: np.ndarray
    npc: np.ndarray


def read_egm(data: bytes, n_vertices: int) -> tuple:
    """(symmetric, asymmetric) morph deltas [mode, vertex, 3] for the first `n_vertices` vertices."""
    if data[:8] != EGM_MAGIC:
        raise ValueError('not a FaceGen .egm')
    total, n_sym, n_asym = struct.unpack_from('<3I', data, 8)
    pos, modes = EGM_HEADER, []
    for _ in range(n_sym + n_asym):
        scale = struct.unpack_from('<f', data, pos)[0]
        deltas = np.frombuffer(data, '<i2', total * 3, pos + 4).reshape(total, 3)[:n_vertices]
        modes.append(deltas.astype(float) * scale)
        pos += 4 + total * 6
    modes = np.array(modes)
    return modes[:n_sym], modes[n_sym:]


def coefficients(hex_text: str, count: int) -> np.ndarray:
    """An NPC's FGGS/FGGA export text as `count` floats (zeros when absent)."""
    return np.frombuffer(bytes.fromhex(hex_text), '<f4').astype(float) if hex_text else np.zeros(count)


def head(meshes: Path, model: str, fggs: str, fgga: str) -> FnvHead:
    """The FNV head `model` (under `meshes`) as the mean face and as the NPC with FaceGen text fggs/fgga."""
    path = meshes / model.replace('\\', '/').lower()
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    shape = next(b for b in data.blocks if isinstance(b, NifFormat.NiTriBasedGeom))
    mean = np.array([(v.x, v.y, v.z) for v in shape.data.vertices])
    sym, asym = read_egm(path.with_suffix('.egm').read_bytes(), len(mean))
    npc = mean + np.tensordot(coefficients(fggs, len(sym)), sym, 1)
    npc += np.tensordot(coefficients(fgga, len(asym)), asym, 1)
    return FnvHead(mean, np.array(shape.data.get_triangles()), npc)
