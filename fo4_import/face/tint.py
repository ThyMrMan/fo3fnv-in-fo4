"""FO4 face tint layers fitted to an FNV complexion, their effect measured through the Creation Kit.

A FO4 NPC's face colour, besides its runtime skin tone, is a list of tint
layers (TETI: data type and the race's option index; TEND: value 0-100,
and for a colour layer an RGBA colour and a template colour index) that the
CK bakes into the face texture. Fitted here: the face detail patterns
(FIT_SLOTS) that are value-only. A colour layer must name one of its race's
template colours (an index of -1 crashes the CK), and the region masks, which
have none and no vanilla NPC uses, crash it as value-only layers. Their
effect is measured, not decoded: per option one
NPC at full value; the CK's face textures, reduced to WORK_SIZE, minus the
baseline's are that option's effect, taken as linear in its value. A
complexion is the bounded least-squares fit, refined against the CK's export.

See: docs/fork/fo4_spikes.md#spike-2-tints
"""

import struct

import numpy as np
from PIL import Image
from scipy.optimize import lsq_linear

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face.sculpt import CACHE
from fo4_import.face.texture import texel_points
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: xEdit's TETI slot enum: the slots fitted (face detail) and Skin Tone.
FIT_SLOTS = frozenset({22})
SKIN_TONE_SLOT = 12
#: NPC TETI data type of a value-only layer.
VALUE_ONLY = 2
WORK_SIZE = 256
BASELINE = 'FNVTint_Base'


def race_options(race_body: bytes, female: bool) -> tuple:
    """(fitted value-only option indices, Skin Tone option indices) of the race's tint options for one sex."""
    sex, options = None, []
    for tag, data in subrecords(race_body):
        if tag in (b'MNAM', b'FNAM'):
            sex = tag
        elif tag == b'TETI' and sex == (b'FNAM' if female else b'MNAM'):
            options.append(list(struct.unpack('<HH', data)) + [False])
        elif tag == b'TTEC' and sex == (b'FNAM' if female else b'MNAM') and options:
            options[-1][2] = True
    fitted = [i for slot, i, coloured in options if slot in FIT_SLOTS and not coloured]
    return fitted, [i for slot, i, _ in options if slot == SKIN_TONE_SLOT]


def layer(index: int, value: float) -> bytes:
    """One value-only TETI/TEND pair, value 0..1."""
    return (pack_subrecord('TETI', struct.pack('<HH', VALUE_ONLY, index))
            + pack_subrecord('TEND', bytes([int(round(value * 100))])))


def without_tints(npc_subs: bytes, keep: frozenset) -> tuple:
    """(NPC subrecords without tint layers, except those of option indices `keep`; those kept, in order)."""
    out, kept, pending = b'', b'', None
    for tag, data in subrecords(npc_subs):
        if tag == b'TETI':
            pending = (data, struct.unpack('<HH', data)[1] in keep)
            continue
        if tag == b'TEND' and pending:
            if pending[1]:
                kept += pack_subrecord('TETI', pending[0]) + pack_subrecord('TEND', data)
            pending = None
            continue
        out += pack_subrecord(tag.decode(), data)
    return out, kept


def with_tints(npc_subs: bytes, layers: bytes) -> bytes:
    """NPC subrecords with tint `layers` before MRSV (their place in xEdit's order), else at the end."""
    out, placed = b'', False
    for tag, data in subrecords(npc_subs):
        if tag in (b'MRSV', b'FMRI', b'FMIN') and not placed:
            out, placed = out + layers, True
        out += pack_subrecord(tag.decode(), data)
    return out if placed else out + layers


def calibration_names(options: list) -> list:
    """Calibration NPC EditorIDs: the baseline, then one per option."""
    return [BASELINE] + [f'FNVTint_{o:04X}' for o in options]


def calibration_plugin(path, template: bytes, flags: int, options: list, tone: list) -> list:
    """Write the calibration plugin (template without its tints but Skin Tone); NPC EditorIDs in FormID order."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='FO4 tint calibration')
    names = calibration_names(options)
    base, kept = without_tints(b''.join(pack_subrecord(t.decode(), d) for t, d in subrecords(template)
                                        if t != b'EDID'), frozenset(tone))
    for i, edid in enumerate(names):
        layers = kept if edid == BASELINE else kept + layer(int(edid.split('_')[1], 16), 1.0)
        subs = pack_subrecord('EDID', edid.encode() + b'\0') + with_tints(base, layers)
        w.add_record('NPC_', pack_fo4_record('NPC_', 0x01000800 + i, flags, subs))
    w.next_object_id = 0x800 + len(names)
    w.write(str(path))
    return names


def reduced(texture) -> np.ndarray:
    """A face texture (path or RGB(A) array) as WORK_SIZE RGB, 0..255 float."""
    image = Image.fromarray(texture[:, :, :3]) if isinstance(texture, np.ndarray) else Image.open(texture)
    return np.asarray(image.convert('RGB').resize((WORK_SIZE, WORK_SIZE), Image.BOX), np.float32)


def scaled_tone(tag: bytes, data: bytes, scale) -> bytes:
    """A QNAM (texture lighting) or Skin Tone TEND with its colour multiplied by `scale` (clamped)."""
    if tag == b'QNAM':
        rgba = struct.unpack('<4f', data)
        return struct.pack('<4f', *(min(c * s, 1.0) for c, s in zip(rgba, scale)), rgba[3])
    colour = bytes(min(round(data[1 + i] * scale[i]), 255) for i in range(3))
    return data[:1] + colour + data[4:]


def with_tone(npc_subs: bytes, scale, tone_options: frozenset) -> bytes:
    """NPC subrecords with QNAM and the Skin Tone layer colour multiplied by `scale`."""
    out, index = b'', None
    for tag, data in subrecords(npc_subs):
        if tag == b'TETI':
            index = struct.unpack('<HH', data)[1]
        if tag == b'QNAM' or (tag == b'TEND' and index in tone_options and len(data) >= 4):
            data = scaled_tone(tag, data, scale)
        out += pack_subrecord(tag.decode(), data)
    return out


def measure(textures: dict, options: list) -> np.ndarray:
    """Per option its full-value effect from {EditorID: reduced face texture}."""
    return np.array([textures[f'FNVTint_{o:04X}'] - textures[BASELINE] for o in options])


def fit(effects: np.ndarray, target: np.ndarray, mask: np.ndarray, bounds=(0.0, 1.0)) -> tuple:
    """(value per option, fraction captured): the linear fit of `target` over `mask`, within `bounds`."""
    a = effects[:, mask].reshape(len(effects), -1).T.astype(np.float64)
    b = target[mask].ravel().astype(np.float64)
    values = lsq_linear(a, b, bounds=bounds).x
    return values, 1.0 - float(((a @ values - b) ** 2).sum() / (b ** 2).sum())


def refine(effects: np.ndarray, values: np.ndarray, target: np.ndarray, actual: np.ndarray, mask) -> tuple:
    """(`values` plus the fit of the CK's measured miss, kept in 0..1; fraction `actual` captured)."""
    step, _ = fit(effects, target - actual, mask, bounds=(-values, 1.0 - values))
    captured = 1.0 - float(((actual - target)[mask] ** 2).sum() / (target[mask] ** 2).sum())
    return np.clip(values + step, 0.0, 1.0), captured


def pack_layers(options: list, values, kept: bytes) -> bytes:
    """`kept` (Skin Tone), then every fitted option, 0s too (a fixed layout)."""
    return kept + b''.join(layer(o, v) for o, v in sorted(zip(options, values)))


def face_mask(face: tuple) -> np.ndarray:
    """WORK_SIZE texels inside the face's UV triangles; face = (positions, UVs, triangles)."""
    rows, cols, _ = texel_points(*face, WORK_SIZE)
    mask = np.zeros((WORK_SIZE, WORK_SIZE), bool)
    mask[rows, cols] = True
    return mask


def basis_path(female: bool = False):
    """The cached tint basis for HumanRace of one sex."""
    return CACHE / f'tint_basis_{"female" if female else "male"}.npz'


def load_basis(female: bool = False):
    """(effects, options, baseline face texture RGBA) cached, or None."""
    path = basis_path(female)
    if not path.exists():
        return None
    d = np.load(path)
    return d['effects'].astype(np.float32), [int(o) for o in d['options']], d['baseline']
