"""FNV static collections placed as their parts: a reference per part, where the GECK put it.

FNV's SCOL mesh is the GECK's merge of its parts, collision included; in
FO4 that merged collision walled off open ground. A SCOL record lists each
part (ONAM, a STAT) and its placements (DATA: position, rotation, scale; 28
bytes each). The export drops them, so they are read from FalloutNV.esm.
A placement rotates as a reference does, Rx(-x)·Ry(-y)·Rz(-z). A part
reference's FormID is hashed from its SCOL reference's FNV FormID and its
index in the SCOL's list (PART_SITE); a part's base is its FNV STAT, on
FNV's FormID as when it is placed by itself.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import math
import struct

import numpy as np

from fo4_import.base.install import source_esm
from tes5_import.base.tes5_reader import subrecords, walk

#: derive_formid site of a part reference (key: SCOL reference FormID, part index).
PART_SITE = 'FNV SCOL part'
PLACEMENT = struct.Struct('<7f')


def read_parts(scols: set) -> dict:
    """{FNV SCOL FormID: [(part FormID, (x, y, z, rx, ry, rz, scale))]} for the SCOLs in `scols`."""
    out = {}
    for rec, _ in walk(source_esm(), b'SCOL'):
        if rec.form_id not in scols:
            continue
        part, placed = None, []
        for tag, data in subrecords(rec.body):
            if tag == b'ONAM':
                part = struct.unpack('<I', data)[0]
            elif tag == b'DATA' and part is not None:
                placed += [(part, p) for p in PLACEMENT.iter_unpack(data)]
        out[rec.form_id] = placed
    return out


def rotation(angles: tuple) -> np.ndarray:
    """A reference's rotation matrix (applied as M @ v) for its (x, y, z) angles."""
    (cx, sx), (cy, sy), (cz, sz) = ((math.cos(-a), math.sin(-a)) for a in angles)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rx @ ry @ rz


def angles(m: np.ndarray) -> tuple:
    """The (x, y, z) angles whose rotation is `m`."""
    b = math.asin(max(-1.0, min(1.0, m[0, 2])))
    return -math.atan2(-m[1, 2], m[2, 2]), -b, -math.atan2(-m[0, 1], m[0, 0])


def compose(position: tuple, angle: tuple, scale: float, placement: tuple) -> tuple:
    """(position, angles, scale) of a part at `placement` in a reference placed so."""
    m = rotation(angle)
    at = np.array(position) + scale * m @ np.array(placement[:3])
    return tuple(at.tolist()), angles(m @ rotation(placement[3:6])), scale * placement[6]


class Parts:
    """The SCOLs' parts."""

    def __init__(self, scols: set):
        """Read the parts of the SCOLs in `scols`."""
        self.parts = read_parts(scols) if scols else {}

    def fids(self) -> set:
        """Every part's FNV FormID."""
        return {part for placed in self.parts.values() for part, _ in placed}
