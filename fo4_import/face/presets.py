"""FO4 face morph presets (a race's morph groups) measured through the Creation Kit, and written into an NPC.

A preset names a morph of the head's chargen .tri; an NPC weights presets by
MSDK keys and MSDV values, at most one per group (as every vanilla NPC). One
calibration NPC per distinct morph at weight 1, minus the baseline, is that
morph's effect on the face vertices; cached per sex beside the sculpt basis.

See: docs/fork/fo4_facegen_plan.md#morph-presets
"""

import functools
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face.bake import face_shape
from fo4_import.face.memo import frozen
from fo4_import.face.sculpt import CACHE
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

BASELINE, PREFIX = 'FNVPreset_Base', 'FNVPreset_'


@dataclass(frozen=True)
class Preset:
    """One morph preset of a race: its group, MSDK key (MPPI) and morph name (MPPM)."""

    group: str
    key: int
    morph: str


def race_presets(race_body: bytes, female: bool) -> list:
    """The race's presets for one sex that name a morph, in record order."""
    want, sex, group, key, out = (b'FNAM' if female else b'MNAM'), None, '', 0, []
    for tag, data in subrecords(race_body):
        text = data.rstrip(b'\0')
        sex = tag if tag in (b'MNAM', b'FNAM') else sex
        group = text.decode('cp1252') if tag == b'MPGN' else group
        key = struct.unpack('<I', data)[0] if tag == b'MPPI' else key
        if tag == b'MPPM' and sex == want and text:
            out.append(Preset(group, key, text.decode('cp1252')))
    return out


def morphs(presets: list) -> list:
    """The distinct morph names of `presets`, first seen first."""
    return list(dict.fromkeys(p.morph for p in presets))


def with_presets(npc_subs: bytes, keys: list, values: list) -> bytes:
    """NPC subrecords with MSDK/MSDV `keys`/`values` (none when empty) right after QNAM, replacing any."""
    morph = pack_subrecord('MSDK', struct.pack(f'<{len(keys)}I', *keys)) + \
        pack_subrecord('MSDV', struct.pack(f'<{len(values)}f', *values)) if keys else b''
    out = b''
    for tag, data in subrecords(npc_subs):
        if tag not in (b'MSDK', b'MSDV'):
            out += pack_subrecord(tag.decode(), data) + (morph if tag == b'QNAM' else b'')
    return out


def calibration_names(names: list) -> list:
    """Calibration NPC EditorIDs: the baseline, then one per morph name."""
    return [BASELINE] + [PREFIX + name for name in names]


def calibration_plugin(path: Path, template: bytes, flags: int, presets: list) -> list:
    """Write a calibration plugin from a face-shape-free NPC body (with QNAM): the baseline, then per distinct
    morph its first preset at weight 1; its NPCs' EditorIDs in FormID order (from 0x800)."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='FO4 morph preset calibration')
    first = {}
    for p in presets:
        first.setdefault(p.morph, p.key)
    names = calibration_names(list(first))
    for i, edid in enumerate(names):
        subs = pack_subrecord('EDID', edid.encode() + b'\0') + b''.join(
            pack_subrecord(t.decode(), d) for t, d in subrecords(template) if t != b'EDID')
        if edid != BASELINE:
            subs = with_presets(subs, [first[edid[len(PREFIX):]]], [1.0])
        w.add_record('NPC_', pack_fo4_record('NPC_', 0x01000800 + i, flags, subs))
    w.next_object_id = 0x800 + len(names)
    w.write(str(path))
    return names


def measure(nifs: dict, names: list) -> np.ndarray:
    """Basis [morph, vertex, 3]: each morph NPC's face minus the baseline's."""
    base = face_shape(nifs[BASELINE])[0]
    return np.array([face_shape(nifs[PREFIX + n])[0] - base for n in names])


def basis_path(female: bool = False) -> Path:
    """The cached preset basis file for HumanRace of one sex."""
    return CACHE / f'preset_basis_{"female" if female else "male"}.npz'


def load_basis(female: bool = False):
    """(basis, morph names) cached; None when not measured."""
    path = basis_path(female)
    return _loaded(path, path.stat().st_mtime_ns) if path.exists() else None


@functools.lru_cache(maxsize=2)
def _loaded(path: Path, stamp: int) -> tuple:
    """load_basis() of the file at `path` as of `stamp`: once per process, read-only."""
    with np.load(path) as data:
        return frozen((data['basis'], [str(n) for n in data['names']]))
