"""FO4 face sculpt regions fitted to an FNV face, their effect measured through the Creation Kit.

A FO4 NPC's face shape is, besides its morph presets, a list of sculpt
regions (FMRI, the race's region index) each with seven controls (FMRS:
position x/y/z, rotation x/y/z, scale; 0 is no change), driving face bones.
Their effect is not decoded from the engine: a calibration plugin holds a
baseline NPC and, per region and control, one NPC at +STEP and one at -STEP;
the CK exports their heads, and the central difference per face vertex is
that control's effect. The basis depends only on race and sex, so it is
measured once and cached (it is Bethesda geometry: under output/, never
committed). A face is then the bounded least-squares fit of the controls to
the target vertex moves.

See: docs/fork/fo4_spikes.md#spike-2-sculpt
"""

import functools
import struct
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face.bake import face_shape
from fo4_import.face.memo import frozen
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

CONTROLS, STEP, BOUND = 7, 0.5, 1.0
CACHE = Path(__file__).resolve().parents[2] / 'output' / 'fo4_cache'
BASELINE = 'FNVSculpt_Base'
#: NPC_ face subrecords a fitted copy drops from its body: morphs, region sculpts, face texture set (the body's age).
FACE_FIELDS = frozenset({b'MSDK', b'MSDV', b'FMRI', b'FMRS', b'FTST'})


def race_regions(race_body: bytes, female: bool) -> list:
    """The race's sculpt region indices for one sex (FMRI after MNAM for male, FNAM for female)."""
    sex, out = None, []
    for tag, data in subrecords(race_body):
        if tag in (b'MNAM', b'FNAM'):
            sex = tag
        elif tag == b'FMRI' and sex == (b'FNAM' if female else b'MNAM'):
            out.append(struct.unpack('<I', data)[0])
    return out


def pack_fmrs(values) -> bytes:
    """One FMRS: the seven controls and the 8 unknown bytes (zero, as vanilla)."""
    return struct.pack('<7f', *values) + bytes(8)


def face_morphs(regions: list, values: np.ndarray, all_regions: bool = False) -> bytes:
    """FMRI/FMRS subrecord pairs for the regions with any non-zero control (every region with `all_regions`)."""
    out = b''
    for region, row in zip(regions, values):
        if all_regions or np.any(row):
            out += pack_subrecord('FMRI', struct.pack('<I', region)) + pack_subrecord('FMRS', pack_fmrs(row))
    return out


def with_face_morphs(npc_body_subs: bytes, morphs: bytes) -> bytes:
    """NPC subrecords with `morphs` before FMIN (their place in xEdit's order), else at the end."""
    out, placed = b'', False
    for tag, data in subrecords(npc_body_subs):
        if tag == b'FMIN' and not placed:
            out, placed = out + morphs, True
        out += pack_subrecord(tag.decode(), data)
    return out if placed else out + morphs


def calibration_names(regions: list) -> list:
    """Calibration NPC EditorIDs: the baseline, then +/- per region and control."""
    return [BASELINE] + [f'FNVSculpt_{r:08X}_{c}_{s}' for r in regions for c in range(CONTROLS) for s in 'pm']


def calibration_plugin(path: Path, template: bytes, flags: int, regions: list) -> list:
    """Write the calibration plugin from a face-shape-free NPC body; its NPCs' EditorIDs in FormID order."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='FO4 sculpt calibration')
    names = calibration_names(regions)
    for i, edid in enumerate(names):
        subs = pack_subrecord('EDID', edid.encode() + b'\0') + b''.join(
            pack_subrecord(t.decode(), d) for t, d in subrecords(template) if t != b'EDID')
        if edid != BASELINE:
            _, region, control, sign = edid.split('_')
            row = np.zeros(CONTROLS)
            row[int(control)] = STEP if sign == 'p' else -STEP
            subs = with_face_morphs(subs, face_morphs([int(region, 16)], [row]))
        w.add_record('NPC_', pack_fo4_record('NPC_', 0x01000800 + i, flags, subs))
    w.next_object_id = 0x800 + len(names)
    w.write(str(path))
    return names


def measure(nifs: dict, regions: list) -> np.ndarray:
    """Basis [region * control, vertex, 3] from {EditorID: FaceGeom NIF bytes}: (plus - minus) / (2 STEP)."""
    basis = []
    for r in regions:
        for c in range(CONTROLS):
            plus = face_shape(nifs[f'FNVSculpt_{r:08X}_{c}_p'])[0]
            minus = face_shape(nifs[f'FNVSculpt_{r:08X}_{c}_m'])[0]
            basis.append((plus - minus) / (2 * STEP))
    return np.array(basis)


def fit(basis: np.ndarray, target: np.ndarray) -> tuple:
    """(controls [region, CONTROLS] within +/-BOUND best moving the face by `target`, fraction captured); a
    control the basis gives no effect (it moves no face vertex) stays 0.
    See: docs/fork/fo4_build_speed.md#faces
    """
    a = basis.reshape(len(basis), -1).T
    b = target.ravel()
    live = a.any(0)
    values = np.zeros(a.shape[1])
    values[live] = lsq_linear(a[:, live], b, bounds=(-BOUND, BOUND)).x
    captured = 1.0 - float(((a @ values - b) ** 2).sum() / (b ** 2).sum())
    return values.reshape(-1, CONTROLS), captured


def refine(basis: np.ndarray, values: np.ndarray, target: np.ndarray, actual: np.ndarray) -> tuple:
    """(`values` plus the fit of the CK's measured miss; fraction `actual` captured)."""
    step, _ = fit(basis, target - actual)
    return np.clip(values + step, -BOUND, BOUND), 1.0 - float(((actual - target) ** 2).sum() / (target ** 2).sum())


def basis_path(female: bool = False) -> Path:
    """The cached basis file for HumanRace of one sex."""
    return CACHE / f'sculpt_basis_{"female" if female else "male"}.npz'


def load_basis(female: bool = False):
    """(basis, regions, baseline FaceGeom NIF bytes) cached; None when not measured."""
    path = basis_path(female)
    return _loaded(path, path.stat().st_mtime_ns) if path.exists() else None


@functools.lru_cache(maxsize=2)
def _loaded(path: Path, stamp: int) -> tuple:
    """load_basis() of the file at `path` as of `stamp`: once per process, read-only."""
    with np.load(path) as data:
        return frozen((data['basis'], [int(r) for r in data['regions']], data['baseline'].tobytes()))
