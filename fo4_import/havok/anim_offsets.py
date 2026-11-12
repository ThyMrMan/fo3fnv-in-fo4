"""AnimationOffsets V4 files: read, write, and an FNV clip's record as the Creation Kit computes it.

A file names its graph, then each clip name the graph plays through the entry with the file it resolves to, then
one record per file: duration, root translation and rotation keys, and the annotations the graph listens for.

See: docs/fork/research/anim_text_data.md#offsets
"""

import struct
from dataclasses import dataclass, field

import numpy as np

from external.pynifly_hkx.anim_fo4 import fo4_animation_header
from fo4_import.havok import packfile
from fo4_import.havok.ck_float import F, ONE, ZERO, axis_angle, norm_factor, recip, slerp

#: The format's first line.
MAGIC = b'V4\n'
#: How far a frame may stray from the line between kept keys: game units, and 0.3 degrees as the CK makes radians.
MOVE_TOLERANCE, TURN_TOLERANCE = F(2.0), F(0.3) * F(0.0174532924)
#: The class holding a clip's extracted root motion.
REFERENCE_FRAME = 'hkaDefaultAnimatedReferenceFrame'
#: Where getNumOriginalFrames reads the frame count of the classes fo4_animation_header doesn't count (CK vfunc +0x48).
FRAME_FIELD = {'hkaLosslessCompressedAnimation': 0xd8, 'hkaPredictiveCompressedAnimation': 0xa4}


@dataclass
class Clip:
    """One clip file's record: duration, [(time, x, y, z)], [(time, x, y, z, w)], [(time, event)]."""
    path: str
    duration: float
    moves: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    events: list = field(default_factory=list)


@dataclass
class Offsets:
    """An AnimationOffsets file: its graph, [(clip name, file)] and the files' records in order."""
    graph: str
    names: list = field(default_factory=list)
    clips: list = field(default_factory=list)


def _string(data: bytes, at: int) -> tuple:
    """(text, next offset) of a u8-length, NUL-ended string at `at`."""
    size = data[at]
    return data[at + 1:at + size].decode('cp1252'), at + 1 + size


def pack_string(text: str) -> bytes:
    """`text` as the format stores a string."""
    raw = text.encode('cp1252') + b'\0'
    return bytes([len(raw)]) + raw


def _keys(data: bytes, at: int, form: str) -> tuple:
    """([key tuples of struct `form`], next offset) of a u32-counted key list at `at`."""
    count, at, size = struct.unpack_from('<I', data, at)[0], at + 4, struct.calcsize(form)
    return [struct.unpack_from(form, data, at + i * size) for i in range(count)], at + count * size


def parse(data: bytes) -> Offsets:
    """An AnimationOffsets file's contents; ValueError when it is not V4 or does not end where its counts say."""
    if not data.startswith(MAGIC):
        raise ValueError('not an AnimationOffsets V4 file')
    graph, at = _string(data, len(MAGIC))
    out = Offsets(graph)
    count, at = struct.unpack_from('<I', data, at)[0], at + 4
    for _ in range(count):
        name, at = _string(data, at)
        path, at = _string(data, at)
        out.names.append((name, path))
    at = _clips(data, at, out)
    if at != len(data):
        raise ValueError(f'AnimationOffsets ends at {at}, not {len(data)}')
    return out


def _clips(data: bytes, at: int, out: Offsets) -> int:
    """Read the clip records at `at` into `out`; the offset after them."""
    count, at = struct.unpack_from('<I', data, at)[0], at + 4
    for _ in range(count):
        path, at = _string(data, at)
        duration, at = struct.unpack_from('<f', data, at)[0], at + 4
        moves, at = _keys(data, at, '<4f')
        turns, at = _keys(data, at, '<5f')
        events, n = [], struct.unpack_from('<I', data, at)[0]
        at += 4
        for _ in range(n):
            time, at = struct.unpack_from('<f', data, at)[0], at + 4
            text, at = _string(data, at)
            events.append((time, text))
        out.clips.append(Clip(path, duration, moves, turns, events))
    return at


def pack(offsets: Offsets) -> bytes:
    """`offsets` as an AnimationOffsets V4 file."""
    out = [MAGIC, pack_string(offsets.graph), struct.pack('<I', len(offsets.names))]
    out += [pack_string(name) + pack_string(path) for name, path in offsets.names]
    out.append(struct.pack('<I', len(offsets.clips)))
    for clip in offsets.clips:
        out += [pack_string(clip.path), struct.pack('<fI', clip.duration, len(clip.moves))]
        out += [struct.pack('<4f', *key) for key in clip.moves]
        out.append(struct.pack('<I', len(clip.turns)))
        out += [struct.pack('<5f', *key) for key in clip.turns]
        out.append(struct.pack('<I', len(clip.events)))
        out += [struct.pack('<f', time) + pack_string(text) for time, text in clip.events]
    return b''.join(out)




@dataclass
class Motion:
    """A clip's animation duration and frame count, its reference frame's samples [(x, y, z, yaw)], duration and
    up axis (no samples without a reference frame), stored as float32, and its annotations [(time, text)]."""
    duration: float
    frames: int
    samples: list = field(default_factory=list)
    span: float = 0.0
    up: tuple = (0.0, 0.0, 1.0, 0.0)
    annotations: list = field(default_factory=list)

    def __post_init__(self):
        """Round every value to float32, as the CK reads them."""
        self.duration, self.span = F(self.duration), F(self.span)
        self.samples = [tuple(F(v) for v in sample) for sample in self.samples]
        self.up = tuple(F(v) for v in self.up)


def motion(raw: bytes) -> Motion:
    """The root motion and annotations of a clip `.hkx` of any animation class; ValueError when it holds none."""
    head = fo4_animation_header(raw)
    if head is None:
        raise ValueError('no animation')
    notes, pf = [(a.time, a.text) for a in head.annotations], packfile.read(raw, only={REFERENCE_FRAME})
    frames = head.num_frames or _frames(pf, raw)
    frame = next((o['fields'] for o in pf.objects if o['class'] == REFERENCE_FRAME), None)
    if not frame:
        return Motion(head.duration, frames, annotations=notes)
    return Motion(head.duration, frames, frame['referenceFrameSamples'], frame['duration'], frame['up'], notes)


def _frames(pf, raw: bytes) -> int:
    """A FRAME_FIELD class's frame count, read where the CK reads it; 0 without one."""
    found = next(((src, cls) for src, cls in pf.virtual if cls in FRAME_FIELD), None)
    return struct.unpack_from('<i', raw, pf.base + found[0] + FRAME_FIELD[found[1]])[0] if found else 0


def _sample(m: Motion, t) -> tuple:
    """The reference frame's (x, y, z, yaw) at time `t`, interpolated between samples as Havok does."""
    s, n = m.samples, len(m.samples)
    if t >= m.span:
        return s[-1]
    if ZERO > t:
        return s[0]
    frame = recip(m.span * recip(F(n - 1))) * t
    i = min(int(np.trunc(frame)), n - 2)
    a, b, delta = s[i], s[i + 1], frame - F(i)
    return tuple((b[k] - a[k]) * delta + a[k] for k in range(4))


def _turn(m: Motion, t) -> tuple:
    """The root's rotation (x, y, z, w) at time `t`."""
    return axis_angle(m.up, _sample(m, t)[3])


def _off_line(p: tuple, a: tuple, b: tuple, u) -> F:
    """How far position `p` lies from the point `u` of the way from `a` to `b`."""
    d = [(u * (b[k] - a[k]) + a[k]) - p[k] for k in range(3)]
    s = (d[1] * d[1] + d[0] * d[0]) + d[2] * d[2]
    return norm_factor(s) * s


def _off_turn(q: tuple, a: tuple, b: tuple, u) -> F:
    """Twice the largest vector component of rotation `q` against slerp(`a`, `b`, `u`)."""
    r = slerp(a, b, u)
    cross = (q[2] * r[1] - r[2] * q[1], q[0] * r[2] - r[0] * q[2], q[1] * r[0] - r[1] * q[0])
    v = [(cross[k] - q[3] * r[k]) + r[3] * q[k] for k in range(3)]
    return max(abs(x + x) for x in v)


def _worst(m: Motion, step, span: tuple, at, off) -> F:
    """The largest `off` of a frame strictly inside `span` (first, last frame) from the line between its ends, each
    frame read with `at` at frame × `step`, positioned by time."""
    start, end = span
    ts, te = F(start) * step, F(end) * step
    a, b, inverse = at(m, ts), at(m, te), ONE / (te - ts)
    worst = ZERO
    for i in range(start + 1, end):
        t = F(i) * step
        error = off(at(m, t), a, b, (t - ts) * inverse)
        worst = error if error > worst else worst
    return worst


def _kept(m: Motion, step, at, off, tolerance) -> list:
    """The frames the CK keeps as keys: from the last kept frame, a frame is kept when the line to the next one
    strays more than `tolerance` from a frame between; the last frame always.
    See: docs/fork/research/anim_text_data.md#root-keys
    """
    kept, start = [], 0
    for end in range(2, m.frames):
        if _worst(m, step, (start, end), at, off) > tolerance:
            kept.append(end - 1)
            start = end - 1
    return kept + [m.frames - 1]


def clip_record(path: str, m: Motion, events: list) -> Clip:
    """The record the CK writes for a clip with root motion `m`, bit for bit; no keys without a reference frame.
    See: docs/fork/research/anim_text_data.md#root-keys
    """
    if len(m.samples) < 2 or m.frames < 2:
        return Clip(path, float(m.duration), [], [], list(events))
    step = m.duration / F(m.frames - 1)
    moves = [F(f) * step for f in _kept(m, step, _sample, _off_line, MOVE_TOLERANCE)]
    turns = [F(f) * step for f in _kept(m, step, _turn, _off_turn, TURN_TOLERANCE)]
    return Clip(path, float(m.duration), [tuple(map(float, (t, *_sample(m, t)[:3]))) for t in moves],
                [tuple(map(float, (t, *_turn(m, t)))) for t in turns], list(events))


def spelled_record(path: str, raw: bytes, spelled: dict) -> Clip:
    """The CK's record for clip `path` (bytes `raw`): its root keys, and its annotations up to the first '.' that
    vanilla's offsets name ({lower case: spelling} `spelled`), spelled as they spell them.
    See: docs/fork/research/anim_text_data.md#root-keys
    """
    m = motion(raw)
    events = [(t, spelled[name]) for t, text in m.annotations if (name := text.split('.')[0].lower()) in spelled]
    return clip_record(path, m, events)
