"""FNV imagespace modifiers (IMAD) as FO4 ones, for the cell spike.

FO4's IMAD keeps FNV's layout (xEdit's wbDefinitionsFNV/FO4.pas): DNAM's key
counts, the time-keyed arrays (blur, double vision, tint, fade, radial blur,
depth of field, motion blur) and the mult/add pairs `\\x00IAD`..`\\x14IAD` and
`@IAD`..`TIAD`. The pairs' meanings differ past the first: FNV's HDR slots
1-13 and bloom alphas have no FO4 counterpart, and the cinematic slots move
(SLOTS). Form version 131 adds vignette radius and strength, vanilla's zero.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import struct

from fo4_import.base.install import fnv_esm
from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import subrecords, walk, zstr
from tes5_import.base.writer import pack_subrecord

#: FNV pair slot -> FO4's: eye adapt speed, bloom blur radius, saturation, contrast, brightness.
SLOTS = {0: 0, 14: 1, 17: 17, 18: 19, 20: 18}
#: Mult/add pairs in both games' DNAM and IAD subrecords.
PAIRS = 21
#: DNAM int slots: flags, duration, then a mult and an add key count per pair.
FIRST_COUNT = 2
#: FO4 DNAM length (form version 116 and up: vignette radius and strength counts) and FNV's.
FO4_DNAM, FNV_DNAM = 252, 244
#: 0.5 as DNAM stores it, an int slot holding a float.
HALF = struct.unpack('<I', struct.pack('<f', 0.5))[0]
#: FNV DNAM ints a short record lacks, by index: radial blur use target 0, its center 0.5, DoF flags 0; else count 2.
DNAM_DEFAULTS = {50: 0, 51: HALF, 52: HALF, 56: 0}
#: Time-keyed arrays in FO4 order; NAM5/NAM6 (vignette) are FO4's own; TNAM and NAM3 are colour keys.
ARRAYS = (b'BNAM', b'VNAM', b'TNAM', b'NAM3', b'RNAM', b'SNAM', b'UNAM', b'NAM1', b'NAM2', b'WNAM', b'XNAM',
          b'YNAM', b'NAM5', b'NAM6', b'NAM4')
COLOR_ARRAYS = (b'TNAM', b'NAM3')
#: Two keys at time 0 and 1: a value array at 0, a colour array at clear, a mult pair at 1, an add pair at 0.
ZERO_KEYS = struct.pack('<4f', 0.0, 0.0, 1.0, 0.0)
CLEAR_KEYS = struct.pack('<10f', 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
MULT_KEYS = struct.pack('<4f', 0.0, 1.0, 1.0, 1.0)


def _iad(slot: int, add: bool) -> bytes:
    """The subrecord tag of pair `slot`'s mult (`\\x00IAD`) or add (`@IAD`) keys."""
    return bytes([slot | (0x40 if add else 0)]) + b'IAD'


def convert(body: bytes) -> bytes:
    """The FO4 IMAD subrecords after EDID for FNV IMAD `body`; FNV's sounds (RDSD) are not kept."""
    subs = dict(subrecords(body))
    raw = subs[b'DNAM'][:FNV_DNAM]
    ints = list(struct.unpack(f'<{len(raw) // 4}I', raw))
    ints += [DNAM_DEFAULTS.get(i, 2) for i in range(len(ints), FNV_DNAM // 4)]
    counts = [2] * (PAIRS * 2)
    pairs = {}
    for fnv, fo4 in SLOTS.items():
        for add in (0, 1):
            counts[fo4 * 2 + add] = ints[FIRST_COUNT + fnv * 2 + add]
            pairs[_iad(fo4, add)] = subs.get(_iad(fnv, add))
    ints[FIRST_COUNT:FIRST_COUNT + PAIRS * 2] = counts
    out = pack_subrecord('DNAM', struct.pack(f'<{len(ints)}I2I', *ints, 2, 2))
    for tag in ARRAYS:
        out += pack_subrecord(tag.decode(), subs.get(tag) or (CLEAR_KEYS if tag in COLOR_ARRAYS else ZERO_KEYS))
    for slot in range(PAIRS):
        for add in (False, True):
            out += pack_subrecord(_iad(slot, add).decode('latin-1'),
                                  pairs.get(_iad(slot, add)) or (ZERO_KEYS if add else MULT_KEYS))
    return out


class ImageSpaces:
    """FNV IMADs converted on first use, by FNV EditorID."""

    def __init__(self, builder):
        """FNV's IMADs indexed by EditorID (FalloutNV.esm)."""
        self.builder, self.made = builder, {}
        self.fnv = {}
        for r, _ in walk(fnv_esm(), b'IMAD'):
            subs = subrecords(r.body)
            self.fnv[zstr(subs[0][1])] = r

    def modifier(self, edid: str) -> 'int | None':
        """The FO4 IMAD of FNV modifier `edid`, written once; None when FNV has none."""
        if edid not in self.made:
            rec = self.fnv.get(edid)
            fid = self.builder.fnv_id(rec.form_id) if rec else None
            if fid:
                self.builder.writer.add_record('IMAD', pack_fo4_record(
                    'IMAD', fid, 0, pack_subrecord('EDID', f'FNV_{edid}'.encode() + b'\0') + convert(rec.body)))
                self.builder.counts['IMAD'] += 1
            self.made[edid] = fid
        return self.made[edid]
