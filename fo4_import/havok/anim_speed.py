"""AnimationSpeedInfo files: read, write, and an own-rig creature's file from its behavior graph and clips.

A file holds one entry per state machine with moving states: its key (`<graph>.hkb/<state machine>`), a speed
contour and a tail. Contours are a collection of child contours, one clip's speed, or a parametric blend's speeds
sampled over its blend parameter.

See: docs/fork/research/anim_text_data.md#speed
"""

import math
import re
import struct
from dataclasses import dataclass, field
from typing import Callable

from fo4_import.havok import packfile
from fo4_import.havok.ck_float import F
from fo4_import.havok.graph import FLAG_PARAMETRIC

#: The format version the Creation Kit writes.
VERSION = 6
#: The contour type names.
COLLECTION = 'CollectionAnimationSpeedContourName'
INDIVIDUAL = 'IndividualClipAnimationSpeedContour'
SAMPLED = 'SpeedSampledAnimationSpeedContour'
#: The graph classes the generator reads.
MACHINE, BLENDER = 'hkbStateMachine', 'hkbBlenderGenerator'
#: The CK's blend-parameter step between speed samples, and its graph update rate (per second).
PARAM_STEP, SIM_RATE = 20.0, 30
#: Units per second a sample may stray from the line between its neighbours before it is kept.
SPEED_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# The format
# ---------------------------------------------------------------------------

@dataclass
class Tail:
    """What follows a contour: the event entering its state, the sync variable and value (-1 none), stop time."""
    event: str = ''
    sync: str = ''
    value: int = -1
    stop: float = 0.0


@dataclass
class Individual:
    """One clip: its root travel direction (x, y, z), its playback-speed variable and its speed."""
    direction: tuple
    variable: str
    speed: float


@dataclass
class Sampled:
    """A parametric blend: node index, bounds (direction min, max, parameter min, max), direction bins
    [(direction, [(parameter, speed)])], outline [(direction, speed)] and the zero-centered flag."""
    node: int
    bounds: tuple
    directions: list = field(default_factory=list)
    outline: list = field(default_factory=list)
    centered: int = 1


@dataclass
class Collection:
    """Child contours [(contour, Tail)] and their kind (0 speed bins, 1 directions)."""
    children: list = field(default_factory=list)
    kind: int = 0


@dataclass
class Entry:
    """One state machine's entry: its key, contour and tail."""
    key: str
    contour: object
    tail: Tail = field(default_factory=Tail)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

class _Reader:
    """A cursor over a file's bytes."""

    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, form: str) -> tuple:
        """The values of struct `form` at the cursor, which moves past them."""
        values = struct.unpack_from('<' + form, self.data, self.at)
        self.at += struct.calcsize('<' + form)
        return values

    def one(self, form: str):
        return self.take(form)[0]

    def text(self) -> str:
        """A u8-length string (length 0: empty, with no NUL)."""
        size = self.one('B')
        self.at += size
        return self.data[self.at - size:self.at - 1].decode('cp1252') if size else ''

    def pairs(self) -> list:
        """A u32-counted list of float pairs."""
        count = self.one('I')
        flat = self.take(f'{2 * count}f')
        return list(zip(flat[::2], flat[1::2]))


def _tail(r: _Reader) -> Tail:
    return Tail(r.text(), r.text(), *r.take('if'))


def _sampled(r: _Reader) -> Sampled:
    """A speed-sampled contour's body."""
    node, bounds = r.one('I'), r.take('4f')
    directions = [(r.one('f'), r.pairs()) for _ in range(r.one('I'))]
    return Sampled(node, bounds, directions, r.pairs(), r.one('B'))


def _contour(r: _Reader):
    """The contour at the cursor; ValueError for an unknown type."""
    kind = r.text()
    if kind == COLLECTION:
        children = [(_contour(r), _tail(r)) for _ in range(r.one('I'))]
        return Collection(children, r.one('B'))
    if kind == INDIVIDUAL:
        return Individual(r.take('3f'), r.text(), r.one('f'))
    if kind == SAMPLED:
        return _sampled(r)
    raise ValueError(f'unknown contour {kind!r} at {r.at}')


def parse(data: bytes) -> list:
    """A file's [Entry]; ValueError when it is not version 6 or does not end where its counts say."""
    r = _Reader(data)
    version, count = r.take('II')
    if version != VERSION:
        raise ValueError(f'AnimationSpeedInfo version {version}')
    entries = [Entry(r.text(), _contour(r), _tail(r)) for _ in range(count)]
    if r.at != len(data):
        raise ValueError(f'AnimationSpeedInfo ends at {r.at}, not {len(data)}')
    return entries


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _text(text: str) -> bytes:
    """`text` as the format stores a string."""
    raw = text.encode('cp1252') + b'\0' if text else b''
    return bytes([len(raw)]) + raw


def _pairs(pairs: list) -> bytes:
    return struct.pack(f'<I{2 * len(pairs)}f', len(pairs), *[v for pair in pairs for v in pair])


def _pack_tail(t: Tail) -> bytes:
    return _text(t.event) + _text(t.sync) + struct.pack('<if', t.value, t.stop)


def _pack_contour(c) -> bytes:
    """A contour with its type name."""
    if isinstance(c, Collection):
        kids = b''.join(_pack_contour(kid) + _pack_tail(t) for kid, t in c.children)
        return _text(COLLECTION) + struct.pack('<I', len(c.children)) + kids + bytes([c.kind])
    if isinstance(c, Individual):
        return _text(INDIVIDUAL) + struct.pack('<3f', *c.direction) + _text(c.variable) + struct.pack('<f', c.speed)
    bins = b''.join(struct.pack('<f', d) + _pairs(samples) for d, samples in c.directions)
    return (_text(SAMPLED) + struct.pack('<I4fI', c.node, *c.bounds, len(c.directions)) + bins + _pairs(c.outline)
            + bytes([c.centered]))


def pack(entries: list) -> bytes:
    """[Entry] as an AnimationSpeedInfo file."""
    body = b''.join(_text(e.key) + _pack_contour(e.contour) + _pack_tail(e.tail) for e in entries)
    return struct.pack('<II', VERSION, len(entries)) + body


# ---------------------------------------------------------------------------
# An own-rig creature's file
# ---------------------------------------------------------------------------

@dataclass
class _Child:
    """A blend child: its weight, its clip's root speed (units per second) and heading (radians, 0 forward)."""
    weight: float
    speed: float
    heading: float


def _child(objects: dict, ref: str, clip: Callable) -> _Child:
    """A blender child's weight and its clip's root speed and heading (0 and 0 without root motion)."""
    fields = objects[ref]['fields']
    generator = objects[fields['generator']]['fields']
    motion = clip(generator['animationName']) if 'animationName' in generator else None
    if motion is None or len(motion.samples) < 2 or not motion.span:
        return _Child(float(F(fields['weight'])), 0.0, 0.0)
    first, last = motion.samples[0], motion.samples[-1]
    dx, dy, dz = (float(last[k] - first[k]) for k in range(3))
    return _Child(float(F(fields['weight'])), math.sqrt(dx * dx + dy * dy + dz * dz) / float(motion.span),
                  math.atan2(dx, dy))


def _speed_at(kids: list, param: float) -> float:
    """The root speed at blend parameter `param`, linear between the children by weight."""
    for a, b in zip(kids, kids[1:]):
        if param <= b.weight:
            u = (param - a.weight) / (b.weight - a.weight) if b.weight > a.weight else 0.0
            return a.speed + (b.speed - a.speed) * u
    return kids[-1].speed


def _simplified(samples: list) -> list:
    """`samples` [(param, speed)] without the inner ones on the line between their neighbours."""
    kept = samples[:1]
    for before, here, after in zip(samples, samples[1:], samples[2:]):
        line = before[1] + (after[1] - before[1]) * (here[0] - before[0]) / (after[0] - before[0])
        if abs(here[1] - line) > SPEED_TOLERANCE:
            kept.append(here)
    return kept + samples[1:][-1:]


def _sampled_contour(kids: list, node: int) -> Sampled:
    """A parametric blend's contour: one direction bin, the parameter stepped by PARAM_STEP from the lowest child
    weight to the highest, the outline at both ends.
    See: docs/fork/research/anim_text_data.md#speed-rules
    """
    lo, hi = kids[0].weight, kids[-1].weight
    params = [float(F(lo) + F(PARAM_STEP) * F(k)) for k in range(int((hi - lo) // PARAM_STEP) + 1)]
    heading = sum(k.heading for k in kids) / len(kids)
    samples = _simplified([(p, _speed_at(kids, p)) for p in params])
    outline = [(kids[0].heading, kids[0].speed), (kids[-1].heading, kids[-1].speed)]
    return Sampled(node, (heading, heading, lo, hi), [(heading, samples)], outline, 1)


def _stop_time(objects: dict, state: dict) -> float:
    """Seconds of top speed the root travels while state `state`'s first transition blends it out: the smooth blend
    curve's remaining weight summed over its frames at SIM_RATE.
    See: docs/fork/research/anim_text_data.md#speed-rules
    """
    rows = objects[state['transitions']]['fields']['transitions'] if state.get('transitions') else []
    effect = objects[rows[0]['transition']]['fields'] if rows and rows[0].get('transition') else {}
    frames = round(effect.get('duration', 0.0) * SIM_RATE)
    return sum(1.0 - (k / frames) ** 2 * (3 - 2 * k / frames) for k in range(1, frames + 1)) / SIM_RATE


def _moving_blend(objects: dict, ref: str) -> 'dict | None':
    """The parametric blender a state's generator `ref` plays, under any modifier generators; None for another."""
    node = objects[ref]
    while node['class'] == 'hkbModifierGenerator' and node['fields'].get('generator'):
        node = objects[node['fields']['generator']]
    flags = node['fields'].get('flags', 0) if node['class'] == BLENDER else 0
    return node['fields'] if flags & FLAG_PARAMETRIC else None


def _machine_entry(objects: dict, machine: dict, prefix: str, clip: Callable) -> 'Entry | None':
    """The entry of a state machine whose state plays a parametric blend with root motion; None for another."""
    for index, ref in enumerate(machine['states']):
        state = objects[ref]['fields']
        blend = _moving_blend(objects, state['generator']) if state.get('generator') else None
        if blend is None:
            continue
        kids = sorted((_child(objects, c, clip) for c in blend['children']), key=lambda k: k.weight)
        if len(kids) > 1 and max(k.speed for k in kids) > 0:
            return Entry(f"{prefix}/{machine['name']}", _sampled_contour(kids, index),
                         Tail(stop=_stop_time(objects, state)))
    return None


def rig_speed(graph: bytes, graph_path: str, clip: Callable) -> 'bytes | None':
    """The AnimationSpeedInfo file of a creature project whose root behavior graph is `graph`, at Data-relative
    `graph_path`; `clip(animationName)` gives the root motion (anim_offsets.Motion) of a clip the graph plays, or
    None. One entry per state machine with a moving state, in file order; None when no state moves.
    See: docs/fork/research/anim_text_data.md#speed-rules
    """
    objects = {o['#']: o for o in packfile.read(graph).objects}
    prefix = re.split(r'[\\/]', graph_path)[-1].rsplit('.', 1)[0] + '.hkb'
    entries = [_machine_entry(objects, o['fields'], prefix, clip) for o in objects.values()
               if o['class'] == MACHINE]
    entries = [e for e in entries if e]
    return pack(entries) if entries else None
