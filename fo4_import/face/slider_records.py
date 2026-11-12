"""The records of a slider FaceGen test plugin: NPC overrides carrying fitted sculpt values, morph presets and a
skin tone; per NPC its own rear head part and texture set (the body set's normal and specular, its own diffuse);
an own hair's override naming its chargen .tri (a path under Meshes).

See: docs/fork/fo4_facegen_plan.md#rear-head-part
"""

import struct
from pathlib import Path

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import facegeom, own_facegen, presets, sculpt
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Head part type of the rear head, and HDPT's chargen .tri part kind (NAM0).
REAR_PART, CHARGEN_TRI = 9, 2
#: Texture set slots the rear head's own set keeps from the body's (TX01 normal, TX07 specular), and its DNAM.
KEPT_SLOTS, TXST_FLAGS = ((1, b'TX01'), (7, b'TX07')), struct.pack('<H', 2)
#: HDPT subrecords that follow the part list, where a chargen .tri goes before.
AFTER_PARTS = (b'TNAM', b'CNAM', b'RNAM')
#: The face fields a fitted NPC replaces.
FITTED = frozenset({b'FMRI', b'FMRS', b'MSDK', b'MSDV'})


def pack(subs) -> bytes:
    """Subrecords [(tag, data)] packed."""
    return b''.join(pack_subrecord(t.decode(), d) for t, d in subs)


def source_record(path: Path, form_id: int, sig: bytes = b'NPC_'):
    """Plugin `path`'s own record `sig` with local id `form_id` (body decompressed)."""
    data = path.read_bytes()
    own = len(own_facegen.master_names(data))
    return next(r for r, _ in walk(data, sig) if r.form_id >> 24 == own and r.form_id & 0xFFFFFF == form_id)


def fitted_npc(body: bytes, fit, regions: list, rear: tuple) -> bytes:
    """NPC subrecords `body` with `fit`'s sculpt values and presets, and the rear head part (old FormID bytes or
    None when the race gives it, new FormID) swapped in its PNAM, or added after the last."""
    old, new = rear
    subs = [(t, struct.pack('<I', new) if t == b'PNAM' and d == old else d)
            for t, d in subrecords(body) if t not in FITTED]
    if old is None:
        last = max(i for i, (t, _) in enumerate(subs) if t == b'PNAM')
        subs.insert(last + 1, (b'PNAM', struct.pack('<I', new)))
    out = sculpt.with_face_morphs(pack(subs), sculpt.face_morphs(regions, fit.sculpt, all_regions=True))
    return presets.with_presets(out, [k for k, _, _ in fit.presets], [v for _, _, v in fit.presets])


def rear_texture_set(edid: str, textures: list, diffuse: str) -> bytes:
    """The rear head's own texture set (see the module doc)."""
    subs = [(b'EDID', edid.encode() + b'\0'), (b'OBND', bytes(12)), (b'TX00', diffuse.encode() + b'\0')]
    subs += [(tag, textures[slot].encode() + b'\0') for slot, tag in KEPT_SLOTS if textures[slot]]
    return pack(subs + [(b'DNAM', TXST_FLAGS)])


def rear_part(part: facegeom.Rec, edid: str, texture_set: int) -> bytes:
    """A copy of rear head part `part` named `edid`, on texture set `texture_set`, not taking the body's."""
    subs = []
    for tag, data in part.subs:
        if tag == b'EDID':
            data = edid.encode() + b'\0'
        elif tag == b'DATA':
            data = bytes([data[0] & ~facegeom.USES_BODY_TEXTURE]) + data[1:]
        if tag == b'RNAM':
            subs.append((b'TNAM', struct.pack('<I', texture_set)))
        if tag != b'TNAM':
            subs.append((tag, data))
    return pack(subs)


def with_chargen_tri(part: facegeom.Rec, tri: str) -> bytes:
    """Head part `part`'s subrecords with chargen .tri `tri` added."""
    parts = [(b'NAM0', struct.pack('<I', CHARGEN_TRI)), (b'NAM1', tri.encode() + b'\0')]
    at = next((i for i, (t, _) in enumerate(part.subs) if t in AFTER_PARTS), len(part.subs))
    return pack(part.subs[:at] + parts + part.subs[at:])


class TestPlugin:
    """A test plugin under construction: masters as the source plugins have them, overrides and new records."""

    def __init__(self, plugins: list):
        """Masters: the deepest of `plugins` (paths) and its masters; every other's must be their prefix."""
        self.order = own_facegen.master_names(plugins[-1].read_bytes()) + [plugins[-1].name]
        self.records, self.next_id = [], 0x800
        for path in plugins:
            own = own_facegen.master_names(path.read_bytes()) + [path.name]
            if [m.lower() for m in self.order[:len(own)]] != [m.lower() for m in own]:
                raise ValueError(f'{path.name} masters are not a prefix of {self.order}')

    def new_id(self) -> int:
        """The next new record's FormID in this plugin."""
        self.next_id += 1
        return (len(self.order) << 24) | (self.next_id - 1)

    def add(self, sig: str, form_id: int, subs: bytes, flags: int = 0) -> int:
        """Add a record; its FormID."""
        self.records.append((sig, pack_fo4_record(sig, form_id, flags & ~own_facegen.COMPRESSED, subs)))
        return form_id

    def write(self, path: Path) -> list:
        """Write the plugin; its masters."""
        w = FO4PluginWriter(masters=self.order, is_esm=False, description='FaceGen test: native sliders')
        for sig, raw in self.records:
            w.add_record(sig, raw)
        w.next_object_id = self.next_id
        w.write(str(path))
        return self.order
