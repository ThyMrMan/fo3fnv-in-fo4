"""A head part's chargen .tri with the base head's slider morphs copied onto it.

Each morph of the race's base head chargen .tri reaches a part vertex from its
NEIGHBOURS nearest head points, inverse-distance weighted, as Outfit Studio
copies slider data; both are in the same character frame.

See: docs/fork/fo4_facegen_plan.md#hair-morphs
"""

import numpy as np
from scipy.spatial import cKDTree

from asset_convert.character.facegen_tri import TriFile
from fo4_import.face import facegeom
from fo4_import.face.bake import positions, triangles, uvs
from fo4_import.nif import file as nif_file

NEIGHBOURS = 4
#: Per sex (female?), the base head's chargen .tri under Meshes.
CHARGEN_HEADS = {True: 'Actors\\Character\\CharacterAssets\\BaseFemaleHeadChargen.tri',
                 False: 'Actors\\Character\\CharacterAssets\\BaseMaleHeadCharGen.tri'}


def copied_morphs(head: TriFile, points: np.ndarray) -> dict:
    """{morph name: deltas [n, 3]} of `head`'s morphs at `points`."""
    dist, near = cKDTree(np.array(head.vertices)).query(points, k=NEIGHBOURS)
    weights = 1.0 / np.maximum(dist, 1e-6)
    weights /= weights.sum(1, keepdims=True)
    return {name: (np.array(deltas)[near] * weights[:, :, None]).sum(1) for name, deltas in head.morphs.items()}


def part_tri(head: TriFile, raw: bytes) -> bytes:
    """Shape block `raw` as a chargen .tri carrying `head`'s morphs."""
    points, tris = positions(raw), triangles(raw).tolist()
    morphs = {name: d.tolist() for name, d in copied_morphs(head, points).items()}
    return TriFile(points.tolist(), tris, uvs(raw).tolist(), tris, morphs).to_bytes()


def hair_tri(head_tri: bytes, hair_nif: bytes) -> bytes:
    """A hair NIF's first shape as a chargen .tri of a base head .tri."""
    raw = next(b for k, b in nif_file.read(hair_nif).blocks if k in facegeom.SHAPES and isinstance(b, bytes))
    return part_tri(TriFile.from_bytes(head_tri), raw)
