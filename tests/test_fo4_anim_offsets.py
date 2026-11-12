"""AnimationOffsets V4: reading, writing and the Creation Kit's root keys."""

import math
import struct

import pytest

from fo4_import.havok import anim_offsets as O
from fo4_import.havok import ck_float

#: FNVQueenAnt AttackRight's reference frame y per sample (float32 bits): a lunge forward and back.
LUNGE_Y = [0, 0x4067345a, 0x40e7345a, 0x412d6744, 0x4167345a, 0x419080b8, 0x41ad6744, 0x41ca4dcf, 0x41e7345a,
           0x42020d73, 0x421080b9, 0x421fa069, 0x422ec01a, 0x423ddfcb, 0x424cff7c, 0x425c1f2c, 0x42461c0d,
           0x423018ee, 0x421a15ce, 0x420412af, 0x41dc1f1f, 0x41b018e0, 0x418412a1, 0x413018c4, 0x40b0188d, 0]


def _f(u: int) -> float:
    """The float32 with bits `u`."""
    return struct.unpack('<f', struct.pack('<I', u))[0]


def test_a_file_reads_back_to_the_same_bytes():
    """A file with names, a moving clip and events packs to the bytes it was read from."""
    clip = O.Clip('Actors\\X\\Animations\\Walk', 1.0, [(0.5, 1.0, 2.0, 3.0), (1.0, 2.0, 4.0, 6.0)],
                  [(1.0, 0.0, 0.0, 0.0, 1.0)], [(0.25, 'FootLeft')])
    data = O.pack(O.Offsets('Actors\\X\\Behaviors\\Root.hkx', [('Walk', clip.path)], [clip]))
    assert data.startswith(O.MAGIC) and O.pack(O.parse(data)) == data
    assert O.parse(data).clips[0].events == [(0.25, 'FootLeft')]


def test_a_file_that_runs_past_its_counts_is_refused():
    """Bytes after the last record mean the layout was misread."""
    data = O.pack(O.Offsets('G.hkx'))
    with pytest.raises(ValueError):
        O.parse(data + b'\0')


def test_a_lunge_gets_the_cks_record_bit_for_bit():
    """The CK's own record for FNVQueenAnt AttackRight, whose time bits need the AMD rcpps table."""
    duration = _f(0x3f555550)
    motion = O.Motion(duration, 26, [(0.0, _f(y), 0.0, 0.0) for y in LUNGE_Y], duration)
    clip = O.clip_record('C', motion, [])
    assert clip.moves == [(_f(0x3efffff9), 0.0, _f(0x425c1f2c), 0.0), (duration, 0.0, 0.0, 0.0)]
    assert clip.turns == [(duration, 0.0, 0.0, 0.0, 1.0)]


def test_a_still_root_keys_only_its_last_frame():
    """A root that never moves: one zero and one identity key, at the end."""
    clip = O.clip_record('C', O.Motion(1.0, 31, [(0.0, 0.0, 0.0, 0.0)] * 31, 1.0), [(0.5, 'HitFrame')])
    assert clip.moves == [(1.0, 0.0, 0.0, 0.0)] and clip.turns == [(1.0, 0.0, 0.0, 0.0, 1.0)]
    assert clip.events == [(0.5, 'HitFrame')]


def test_a_clip_without_a_reference_frame_gets_no_keys():
    """No samples at all: the CK writes no root keys."""
    clip = O.clip_record('C', O.Motion(1.0, 30), [])
    assert (clip.moves, clip.turns, clip.duration) == ([], [], 1.0)


def test_a_turn_is_keyed_about_the_up_axis_where_it_stops():
    """A quarter turn over half the clip, then still: rotation keys at the stop and the end, about z."""
    samples = [(0.0, 0.0, 0.0, math.pi / 2 * min(i, 10) / 10) for i in range(21)]
    turns = O.clip_record('C', O.Motion(2.0, 21, samples, 2.0), []).turns
    assert [round(t[0], 4) for t in turns] == [1.0, 2.0]
    assert turns[-1][1:3] == (0.0, 0.0) and math.isclose(turns[-1][3], math.sin(math.pi / 4), rel_tol=1e-6)


def test_the_cks_float_helpers_stay_close_to_exact_math():
    """Refined reciprocals within a float32 step; sincos and slerp agree with math to 1e-6."""
    for x in (0.03333, 1.0, 3.0, 37.5, 1e5):
        assert math.isclose(ck_float.recip(ck_float.F(x)), 1 / x, rel_tol=2e-7)
        assert math.isclose(ck_float.norm_factor(ck_float.F(x)), x ** -0.5, rel_tol=2e-7)
    for a in (-3.0, -0.5, 0.0, 0.7, 2.5):
        s, c = ck_float.sincos(a)
        assert abs(s - math.sin(a)) < 1e-6 and abs(c - math.cos(a)) < 1e-6
    half = ck_float.slerp((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)), 0.5)
    assert abs(half[2] - math.sin(math.pi / 8)) < 1e-6
