#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anim_fo4.py — Read FO4 hkaSplineCompressedAnimation data.

No Blender dependencies.  Can be run standalone:

    python anim_fo4.py <file.hkx>          # binary HKX (native reader, no deps)
    python anim_fo4.py <file.xml>          # hkpackfile XML (from hkxpack-cli)

Produces an in-memory AnimationData structure with fully decompressed per-frame
translation / rotation / scale for every bone track, plus skeleton info if present.

Based on spline decompression from Dagobaking's skyrim-fo4-animation-conversion
(itself based on PredatorCZ/HavokLib, GPL-3.0).
"""

import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import shutil
import xml.etree.ElementTree as ET

import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
#  Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BonePose:
    """Rest-pose for a single bone (local space)."""
    translation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])  # xyzw
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])


@dataclass
class Skeleton:
    """Skeleton definition parsed from an hkpackfile."""
    name: str = ""
    bones: List[str] = field(default_factory=list)
    parents: List[int] = field(default_factory=list)
    reference_pose: List[BonePose] = field(default_factory=list)
    lock_translation: List[bool] = field(default_factory=list)
    float_slots: List[str] = field(default_factory=list)
    reference_floats: List[float] = field(default_factory=list)

    def __repr__(self):
        return f"Skeleton('{self.name}', {len(self.bones)} bones)"


@dataclass
class TrackData:
    """Fully decompressed per-frame data for one bone track."""
    translations: List[List[float]] = field(default_factory=list)  # [frame][x,y,z]
    rotations: List[List[float]] = field(default_factory=list)     # [frame][x,y,z,w]
    scales: List[List[float]] = field(default_factory=list)        # [frame][x,y,z]


@dataclass
class Annotation:
    """A single annotation event."""
    time: float = 0.0
    text: str = ""


@dataclass
class AnimationData:
    """Complete parsed animation."""
    # Header info
    duration: float = 0.0
    num_frames: int = 0
    num_tracks: int = 0
    num_blocks: int = 0
    max_frames_per_block: int = 256
    block_duration: float = 8.5
    frame_duration: float = 1.0 / 30.0

    # Bone names (from annotationTracks/trackName, one per track)
    bone_names: List[str] = field(default_factory=list)

    # Per-track decompressed data
    tracks: List[TrackData] = field(default_factory=list)

    # Annotations (text events at specific times)
    annotations: List[Annotation] = field(default_factory=list)

    # Binding info (from hkaAnimationBinding)
    track_to_bone_indices: List[int] = field(default_factory=list)
    original_skeleton_name: str = ""
    blend_hint: int = 0  # 0=NORMAL, 1=ADDITIVE

    # Skeleton (if present in the same file)
    skeleton: Optional[Skeleton] = None

    def summary(self) -> str:
        """Return a human-readable summary of the animation."""
        lines = []
        lines.append(f"Duration:       {self.duration:.4f}s")
        lines.append(f"Frame count:    {self.num_frames}")
        fps = 1.0 / self.frame_duration if self.frame_duration > 0 else 0
        lines.append(f"Frame rate:     {fps:.1f} fps")
        lines.append(f"Track count:    {self.num_tracks}")
        lines.append(f"Blocks:         {self.num_blocks}")
        lines.append(f"Block duration: {self.block_duration:.4f}s")
        lines.append(f"Max frames/blk: {self.max_frames_per_block}")

        if self.skeleton:
            lines.append(f"Skeleton:       {self.skeleton.name} ({len(self.skeleton.bones)} bones)")

        if self.annotations:
            lines.append(f"Annotations:    {len(self.annotations)}")
            for a in self.annotations:
                lines.append(f"  {a.time:.4f}s  {a.text}")

        # Analyse which tracks have actual motion
        animated_pos = []
        animated_rot = []
        animated_scale = []
        static_rot = []
        identity_tracks = []

        for i, track in enumerate(self.tracks):
            name = self.bone_names[i] if i < len(self.bone_names) and self.bone_names[i] else f"Bone #{i}"
            has_pos = False
            has_rot = False
            has_scale = False

            if track.translations and len(track.translations) > 1:
                t0 = track.translations[0]
                for t in track.translations[1:]:
                    if any(abs(t[j] - t0[j]) > 1e-5 for j in range(3)):
                        has_pos = True
                        break

            if track.rotations and len(track.rotations) > 1:
                r0 = track.rotations[0]
                for r in track.rotations[1:]:
                    dot = sum(r0[j] * r[j] for j in range(4))
                    if abs(abs(dot) - 1.0) > 1e-5:
                        has_rot = True
                        break

            if track.scales and len(track.scales) > 1:
                s0 = track.scales[0]
                for s in track.scales[1:]:
                    if any(abs(s[j] - s0[j]) > 1e-5 for j in range(3)):
                        has_scale = True
                        break

            if has_pos:
                animated_pos.append(name)
            if has_rot:
                animated_rot.append(name)
            elif track.rotations:
                # Has rotation data but it's static
                r0 = track.rotations[0]
                is_identity = abs(r0[3]) > 0.9999 and sum(r0[j]**2 for j in range(3)) < 1e-6
                if not is_identity:
                    static_rot.append(name)
            if has_scale:
                animated_scale.append(name)

            if not has_pos and not has_rot and not has_scale:
                identity_tracks.append(name)

        lines.append("")
        lines.append(f"Animated rotation:    {len(animated_rot)} tracks")
        for name in animated_rot:
            lines.append(f"  {name}")

        lines.append(f"Static rotation:      {len(static_rot)} tracks")
        for name in static_rot:
            lines.append(f"  {name}")

        if animated_pos:
            lines.append(f"Animated position:    {len(animated_pos)} tracks")
            for name in animated_pos:
                lines.append(f"  {name}")

        if animated_scale:
            lines.append(f"Animated scale:       {len(animated_scale)} tracks")
            for name in animated_scale:
                lines.append(f"  {name}")

        lines.append(f"Identity/unused:      {len(identity_tracks)} tracks")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Quaternion helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _quat_normalize(q):
    mag = math.sqrt(sum(c * c for c in q))
    if mag < 1e-10:
        return [0.0, 0.0, 0.0, 1.0]
    return [c / mag for c in q]


# ═══════════════════════════════════════════════════════════════════════════════
#  Spline decompression primitives
# ═══════════════════════════════════════════════════════════════════════════════

def _align(offset, alignment=4):
    r = offset % alignment
    return offset + (alignment - r) if r else offset


def _read_32bit_quat(data, offset):
    cval = struct.unpack_from('<I', data, offset)[0]
    r_mask = (1 << 10) - 1
    r_frac = 1.0 / r_mask
    R = ((cval >> 18) & r_mask) * r_frac
    R = 1.0 - R * R
    phi_theta = float(cval & 0x3FFFF)
    phi = math.floor(math.sqrt(phi_theta))
    theta = 0.0
    if phi > 0.0:
        theta = (math.pi / 4.0) * (phi_theta - phi * phi) / phi
        phi = (math.pi / 2.0 / 511.0) * phi
    magnitude = math.sqrt(max(0, 1.0 - R * R))
    sp, cp = math.sin(phi), math.cos(phi)
    st, ct = math.sin(theta), math.cos(theta)
    result = [sp * ct * magnitude, sp * st * magnitude, cp * magnitude, R]
    sign_masks = [0x10000000, 0x20000000, 0x40000000, 0x80000000]
    for i in range(4):
        if cval & sign_masks[i]:
            result[i] = -result[i]
    return _quat_normalize(result), offset + 4


def _read_uncompressed_quat(data, offset):
    x, y, z, w = struct.unpack_from('<ffff', data, offset)
    return _quat_normalize([x, y, z, w]), offset + 16


#: Step between quanta of a 48-bit (format 2) and a 40-bit (format 1) quaternion component.
_FRACTAL_48, _FRACTAL_40 = 0.000043161, 0.000345436
#: The other three components, in order, beside each largest one (whose index goes in the spare bits).
_OTHERS = np.array([[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]])

_QUAT_ALIGN = {0: 4, 1: 1, 2: 2, 3: 1, 4: 2, 5: 4}


def _py_sum(terms: list) -> np.ndarray:
    """Elementwise, Python's `sum` of the arrays `terms`: from int 0, then as CPython (3.12+) sums floats, with
    Neumaier compensation added at the end when nonzero and finite. Array code then matches per-value code that
    calls `sum` exactly.
    See: docs/fork/fo4_build_speed.md#codec-steps
    """
    total = 0.0 + terms[0]
    comp = np.zeros_like(total)
    with np.errstate(over='ignore', invalid='ignore'):
        for x in terms[1:]:
            t = total + x
            comp = comp + np.where(np.abs(total) >= np.abs(x), (total - t) + x, (x - t) + total)
            total = t
        return np.where((comp != 0) & np.isfinite(comp), total + comp, total)


def _normalized(q: np.ndarray) -> np.ndarray:
    """Quaternions `q` [n, 4] over their lengths, as _quat_normalize; under 1e-10, identity."""
    length = np.sqrt(_py_sum([q[:, i] * q[:, i] for i in range(4)]))
    with np.errstate(divide='ignore', invalid='ignore'):
        unit = q / length[:, None]
    unit[length < 1e-10] = (0.0, 0.0, 0.0, 1.0)
    return unit


def _chain_signs(q: np.ndarray, resets: 'np.ndarray | None' = None) -> np.ndarray:
    """Per quaternion of `q` [n, 4], -1.0 where its dot with the one before (as kept) is negative, else 1.0; 1.0
    where `resets` is set. The kept one before is the raw one times its sign, so its dot is the raw dot times that
    sign, exactly."""
    dots = _py_sum([q[1:, i] * q[:-1, i] for i in range(4)])
    fresh = resets.tolist() if resets is not None else [False] * len(q)
    signs = [1.0]
    for k, dot in enumerate(dots.tolist(), 1):
        signs.append(-1.0 if not fresh[k] and dot * signs[-1] < 0 else 1.0)
    return np.array(signs)


def _unpacked(data, off: int, n: int, fmt: int) -> tuple:
    """(three smaller components [n, 3], the largest one's index, whether it is negative, offset after) of `n`
    48-bit (`fmt` 2) or 40-bit (else) quaternions at `off`."""
    if fmt == 2:
        raw = np.frombuffer(data, '<u2', 3 * n, off).reshape(n, 3).astype(np.int64)
        shift = (raw[:, 1] >> 14 & 2) | (raw[:, 0] >> 15 & 1)
        return ((raw & 0x7FFF) - 16383) * _FRACTAL_48, shift, raw[:, 2] >> 15 != 0, off + 6 * n
    raw = (np.frombuffer(data, np.uint8, 5 * n, off).reshape(n, 5).astype(np.int64) << np.arange(0, 40, 8)).sum(1)
    parts = np.stack([raw, raw >> 12, raw >> 24], 1) & 0xFFF
    return (parts - 2049) * _FRACTAL_40, raw >> 36 & 3, (raw >> 38 & 1) != 0, off + 5 * n


def _read_quats(fmt: int, data, off: int, n: int) -> tuple:
    """(`n` normalized quaternions [n, 4] (x, y, z, w) of format `fmt` at `off`, offset after). Formats 0 and 5 go
    one at a time through their readers; any other but 2 reads as 40-bit."""
    if fmt in (0, 5):
        reader = _read_32bit_quat if fmt == 0 else _read_uncompressed_quat
        rows = []
        for _ in range(n):
            q, off = reader(data, off)
            rows.append(q)
        return np.array(rows, float).reshape(n, 4), off
    vals, shift, negative, off = _unpacked(data, off, n, fmt)
    w = np.sqrt(np.maximum(0.0, 1.0 - _py_sum([vals[:, i] * vals[:, i] for i in range(3)])))
    q = np.empty((n, 4))
    rows = np.arange(n)
    q[rows[:, None], _OTHERS[shift]] = vals
    q[rows, shift] = np.where(negative, -w, w)
    return _normalized(q), off


# ═══════════════════════════════════════════════════════════════════════════════
#  B-spline evaluation
# ═══════════════════════════════════════════════════════════════════════════════

def _find_knot_span(degree, value, num_cp, knots):
    if num_cp <= 0:
        return 0
    if value >= knots[num_cp]:
        return num_cp - 1
    low, high = degree, num_cp
    mid = (low + high) // 2
    for _ in range(100):
        if value < knots[mid]:
            high = mid
        elif value >= knots[mid + 1]:
            low = mid
        else:
            break
        mid = (low + high) // 2
    return mid


#: Bytes per quaternion of formats 0, 1, 2 and 5; any other reads as 40-bit.
_QUAT_SIZE = {0: 4, 1: 5, 2: 6, 5: 16}


def _runs(starts, counts, step=1) -> np.ndarray:
    """start + k * step for k below count, run by run; `step` per run or one."""
    counts = np.asarray(counts, np.int64)
    k = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    return np.repeat(np.asarray(starts, np.int64), counts) + k * np.repeat(np.broadcast_to(step, counts.shape), counts)


def _padded(knots: list) -> np.ndarray:
    """Knot tuples as rows of one array, padded with infinity."""
    width = max(map(len, knots))
    return np.array([k + (math.inf,) * (width - len(k)) for k in knots])


def _basis_row(knot_span: int, degree: int, t: float, knots) -> list:
    """The degree + 1 nonzero B-spline basis values at `t` in `knot_span` (de Boor)."""
    values = [0.0] * (degree + 1)
    values[0] = 1.0
    for i in range(1, degree + 1):
        for j in range(i - 1, -1, -1):
            denom = knots[knot_span + i - j] - knots[knot_span - j]
            ratio = (t - knots[knot_span - j]) / denom if denom >= 1e-10 else 0.0
            tmp = values[j] * ratio
            values[j + 1] += values[j] - tmp
            values[j] = tmp
    return values


def _spans_weights(degree: int, knots: list, n_cps: np.ndarray, frames: int) -> tuple:
    """([spline, frame] knot spans, [spline, frame, degree + 1] basis values) of frames 0..frames-1, as
    _find_knot_span and _basis_row give them. With sorted knots and degree below the point count, the span is the
    last knot at or below the frame, clamped to [degree, n_cp - 1]; other splines of 2+ points go frame by frame."""
    padded = _padded(knots)
    t = np.arange(frames, dtype=float)
    spans = np.clip((padded[:, None, :] <= t[None, :, None]).sum(2) - 1, degree, (n_cps - 1)[:, None])
    weight = _weights(degree, padded, spans, frames)
    with np.errstate(invalid='ignore'):
        odd = ((np.diff(padded, axis=1) < 0).any(1) | (n_cps <= degree)) & (n_cps > 1)
    for row in np.flatnonzero(odd).tolist():
        k, n = knots[row], int(n_cps[row])
        spans[row] = [_find_knot_span(degree, float(f), n, k) for f in range(frames)]
        weight[row] = [_basis_row(s, degree, float(f), k) for f, s in enumerate(spans[row].tolist())]
    return spans, weight


def _weights(degree: int, padded: np.ndarray, spans: np.ndarray, frames: int) -> np.ndarray:
    """[spline, frame, degree + 1] B-spline basis values at `spans` (de Boor), each operation as per value."""
    t = np.arange(frames, dtype=float)
    out = np.zeros(spans.shape + (degree + 1,))
    out[..., 0] = 1.0
    with np.errstate(divide='ignore', invalid='ignore'):
        for i in range(1, degree + 1):
            for j in range(i - 1, -1, -1):
                low = np.take_along_axis(padded, spans - j, 1)
                denom = np.take_along_axis(padded, spans + i - j, 1) - low
                ratio = np.where(denom >= 1e-10, (t - low) / denom, 0.0)
                tmp = out[..., j] * ratio
                out[..., j + 1] += out[..., j] - tmp
                out[..., j] = tmp
    return out


def _spline_values(points: np.ndarray, rows: list, degree: int, frames: int) -> np.ndarray:
    """[spline, frame, width] values of `rows` (first, stride, degree, knots, n_cp) of one `degree`, point p of a
    spline at points[first + p * stride]: terms added to 0.0 in span order; a one-point spline is its point."""
    first, stride, _, knots, n_cps = (np.array(c) if i != 3 else c for i, c in enumerate(zip(*rows)))
    spans, weight = _spans_weights(degree, knots, n_cps, frames)
    out = np.zeros((len(rows), frames, points.shape[1]))
    for i in range(degree + 1):
        index = spans - i
        exists = (index >= 0) & (index < n_cps[:, None])
        picked = points[first[:, None] + np.clip(index, 0, (n_cps - 1)[:, None]) * stride[:, None]]
        out = out + np.where(exists[..., None], picked * weight[..., i:i + 1], 0.0)
    one = n_cps == 1
    out[one] = points[first[one]][:, None, :]
    return out


def _evaluate(points: np.ndarray, rows: list, frames: int) -> np.ndarray:
    """[row, frame, width] values of spline `rows` (first, stride, degree, knots, n_cp) over `points` [n, width]."""
    out = np.empty((len(rows), frames, points.shape[1]))
    for degree in sorted({row[2] for row in rows}):
        pick = [i for i, row in enumerate(rows) if row[2] == degree]
        out[pick] = _spline_values(points, [rows[i] for i in pick], degree, frames)
    return out


def _read_spline_header(data, off: int, align: int) -> tuple:
    """(degree, float knots, point count, aligned offset after) of a spline."""
    num_items, degree = struct.unpack_from('<HB', data, off)
    knots = tuple(map(float, data[off + 3:off + 3 + num_items + degree + 2]))
    return degree, knots, num_items + 1, _align(off + 3 + len(knots), align)


def _flag_kinds(flags: int) -> list:
    """Axis kinds (0 identity, 1 static, 2 spline) of a mask byte."""
    return [2 if flags >> axis + 4 & 1 else flags >> axis & 1 for axis in range(3)]


class _Layout:
    """Where one block's values sit, noted track by track: statics (channel, track, axis, value), scalar splines
    (channel, track, axes, degree, knots, n_cp, offset, size, bounds) and quaternions (track, format, count,
    offset, degree, knots, kind); channel 0 is position, 2 scale."""

    def __init__(self):
        """No notes yet."""
        self.statics, self.scalars, self.quats = [], [], []


def _layout_scalar(data, off: int, kinds: list, quant: int, track: int, channel: int, out: _Layout) -> int:
    """Note a position or scale channel at `off` by axis `kinds` (0 identity, 1 static, 2 spline), control points
    8-bit at `quant` 0 else 16-bit, into `out`; the offset after padding to 4."""
    spline = [axis for axis in range(3) if kinds[axis] == 2]
    if spline:
        degree, knots, n_cp, off = _read_spline_header(data, off, 4)
    bounds = []
    for axis in range(3):
        if kinds[axis] == 1:
            out.statics.append((channel, track, axis, struct.unpack_from('<f', data, off)[0]))
        elif kinds[axis] == 2:
            bounds.append(struct.unpack_from('<2f', data, off))
        off += 4 * kinds[axis]
    if spline:
        size = 1 if quant == 0 else 2
        out.scalars.append((channel, track, spline, degree, knots, n_cp, off, size, bounds))
        off += n_cp * len(spline) * size
    return _align(off, 4)


def _layout_rotation(data, off: int, kind: int, fmt: int, track: int, out: _Layout) -> int:
    """Note a rotation channel at `off` (`kind` 2 spline, 1 static, 0 identity) into `out`; the offset after
    padding to 4."""
    align = _QUAT_ALIGN.get(fmt, 4)
    if kind == 0:
        return _align(off, 4)
    if kind == 2:
        degree, knots, n_cp, off = _read_spline_header(data, off, align)
    else:
        degree, knots, n_cp, off = 0, (), 1, _align(off, align)
    out.quats.append((track, fmt, n_cp, off, degree, knots, kind))
    return _align(off + n_cp * _QUAT_SIZE.get(fmt, 5), 4)


def _layout_track(data, off: int, track: int, mask: bytes, out: _Layout) -> int:
    """Note track `track`'s channels at `off` by its four `mask` bytes into `out`; the offset after."""
    quant, pos_flags, rot_flags, scale_flags = mask
    off = _layout_scalar(data, off, _flag_kinds(pos_flags), quant & 3, track, 0, out)
    rot_kind = 2 if rot_flags >> 4 & 0xF else 1 if rot_flags & 0xF else 0
    off = _layout_rotation(data, off, rot_kind, quant >> 2 & 0xF, track, out)
    return _layout_scalar(data, off, _flag_kinds(scale_flags), quant >> 6 & 3, track, 2, out)


def _scalar_points(data8: np.ndarray, jobs: list) -> np.ndarray:
    """[n, 1] every control point of scalar spline `jobs`, job by job, point-major then axis, as
    low + (high - low) * (raw / top) with top 255 (8-bit) or 65535 (16-bit)."""
    counts = [job[5] * len(job[2]) for job in jobs]
    sizes = np.repeat([job[7] for job in jobs], counts)
    at = _runs([job[6] for job in jobs], counts, [job[7] for job in jobs])
    raw = data8[at].astype(np.int64) + np.where(sizes == 2, data8[at + 1].astype(np.int64) << 8, 0)
    low = np.array([b[0] for job in jobs for _ in range(job[5]) for b in job[8]])
    high = np.array([b[1] for job in jobs for _ in range(job[5]) for b in job[8]])
    return (low + (high - low) * (raw / np.where(sizes == 2, 65535.0, 255.0)))[:, None]


def _place_scalars(data8: np.ndarray, jobs: list, channels: dict, frames: int) -> None:
    """Evaluate every scalar spline of `jobs` into `channels` ({0: positions, 2: scales})."""
    points = _scalar_points(data8, jobs)
    rows, targets, first = [], [], 0
    for channel, track, axes, degree, knots, n_cp, *_ in jobs:
        for k, axis in enumerate(axes):
            rows.append((first + k, len(axes), degree, knots, n_cp))
            targets.append((channel, track, axis))
        first += n_cp * len(axes)
    for (channel, track, axis), values in zip(targets, _evaluate(points, rows, frames)[..., 0]):
        channels[channel][track, :, axis] = values


def _quat_points(data8: np.ndarray, jobs: list) -> np.ndarray:
    """[n, 4] every quaternion of `jobs`, job by job, normalized as read."""
    counts = [job[2] for job in jobs]
    out = np.empty((sum(counts), 4))
    firsts = np.cumsum([0] + counts[:-1])
    for fmt in sorted({job[1] for job in jobs}):
        pick = [i for i, job in enumerate(jobs) if job[1] == fmt]
        size = _QUAT_SIZE.get(fmt, 5)
        at = _runs([jobs[i][3] for i in pick], [counts[i] for i in pick], size)
        raw = data8[at[:, None] + np.arange(size)].tobytes()
        out[_runs(firsts[pick], [counts[i] for i in pick])] = _read_quats(fmt, raw, 0, len(at))[0]
    return out


def _place_quats(data8: np.ndarray, jobs: list, rot: np.ndarray, frames: int) -> None:
    """Read every quaternion of `jobs` into `rot`: a static one as read; a spline's points sign-chained,
    evaluated and normalized."""
    points = _quat_points(data8, jobs)
    firsts = np.cumsum([0] + [job[2] for job in jobs[:-1]]).tolist()
    resets = np.zeros(len(points), bool)
    resets[firsts] = True
    chained = points * _chain_signs(points, resets)[:, None]
    splines = [(first, job) for first, job in zip(firsts, jobs) if job[6] == 2]
    for first, job in zip(firsts, jobs):
        if job[6] == 1:
            rot[job[0]] = points[first]
    if splines:
        values = _evaluate(chained, [(first, 1, job[4], job[5], job[2]) for first, job in splines], frames)
        rot[[job[0] for _, job in splines]] = _normalized(values.reshape(-1, 4)).reshape(values.shape)


def _block_values(data8: np.ndarray, layout: _Layout, tracks: int, frames: int) -> tuple:
    """(positions, rotations, scales), each [track, frame, axis], of one block from its `layout`."""
    pos, scale = np.zeros((tracks, frames, 3)), np.ones((tracks, frames, 3))
    rot = np.tile((0.0, 0.0, 0.0, 1.0), (tracks, frames, 1))
    channels = {0: pos, 2: scale}
    for channel, track, axis, value in layout.statics:
        channels[channel][track, :, axis] = value
    if layout.scalars:
        _place_scalars(data8, layout.scalars, channels, frames)
    if layout.quats:
        _place_quats(data8, layout.quats, rot, frames)
    return pos, rot, scale


def _decompress_spline(data_bytes, num_tracks, num_frames, num_blocks,
                       max_frames_per_block, block_offsets,
                       mask_and_quant_size=0):
    """Decompress hkaSplineCompressedAnimation data blob into one TrackData per track, every frame's translations,
    rotations and scales evaluated. mask_and_quant_size: the size of each block's masks plus float track
    quantization bytes; 0 means _align(4 * num_tracks, 4)."""
    all_tracks = [TrackData() for _ in range(num_tracks)]
    size = mask_and_quant_size or _align(4 * num_tracks, 4)
    data = bytes(data_bytes)
    data8 = np.frombuffer(data + b'\0', np.uint8)
    for block_idx in range(num_blocks):
        start = block_offsets[block_idx]
        first_frame = block_idx * max_frames_per_block
        frames = num_frames - first_frame if block_idx == num_blocks - 1 else max_frames_per_block
        layout, off = _Layout(), start + size
        for track in range(num_tracks):
            off = _layout_track(data, off, track, data[start + 4 * track:start + 4 * track + 4], layout)
        values = (v.tolist() for v in _block_values(data8, layout, num_tracks, frames))
        for track, pos, rot, scale in zip(all_tracks, *values):
            track.translations.extend(pos)
            track.rotations.extend(rot)
            track.scales.extend(scale)
    return all_tracks


# ═══════════════════════════════════════════════════════════════════════════════
#  Binary HKX reader (native — no external tools)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  hk_2014.1.0-r1 packfile layout (FO4, 64-bit pointers):
#
#    0x00: File header (0x40 bytes)
#    0x40: padding11 value (2 bytes) — if 0x10, next 16 bytes are padding
#    0x50: Section header 0 __classnames__  (0x40 bytes each)
#    0x90: Section header 1 __types__       (empty)
#    0xD0: Section header 2 __data__
#    Then: classnames data, data section, fixup tables
#
#  hkaSplineCompressedAnimation struct (relative to object start):
#    +0x00  vtable ptr             (8, zeros in file)
#    +0x08  memSizeAndFlags etc    (8, serialise-ignored)
#    +0x10  type                   (4, enum — 3 = SPLINE_COMPRESSED)
#    +0x14  duration               (4, float)
#    +0x18  numberOfTransformTracks (4, int32)
#    +0x1C  numberOfFloatTracks    (4, int32)
#    +0x20  extractedMotion        (8, pointer)
#    +0x28  annotationTracks       (16, hkArray of hkaAnnotationTrack)
#    +0x38  numFrames              (4, int32)
#    +0x3C  numBlocks              (4, int32)
#    +0x40  maxFramesPerBlock      (4, int32)
#    +0x44  maskAndQuantizationSize (4, int32)
#    +0x48  blockDuration          (4, float)
#    +0x4C  blockInverseDuration   (4, float)
#    +0x50  frameDuration          (4, float)
#    +0x54  padding                (4)
#    +0x58  blockOffsets           (16, hkArray<u32>)
#    +0x68  floatBlockOffsets      (16, hkArray<u32>)
#    +0x78  transformOffsets       (16, hkArray<u32>)
#    +0x88  floatOffsets           (16, hkArray<u32>)
#    +0x98  data                   (16, hkArray<u8>)
#
#  hkaAnnotationTrack struct (0x18 bytes each):
#    +0x00  trackName              (8, string pointer)
#    +0x08  annotations            (16, hkArray of hkaAnnotation)
#
#  hkArray layout (16 bytes):
#    +0x00  data pointer           (8, resolved via local fixups)
#    +0x08  size                   (4, int32)
#    +0x0C  capacityAndFlags       (4, int32 — high bit = owned flag)

_HKX_MAGIC = b'\x57\xe0\xe0\x57'

def _u32(data, off):
    return struct.unpack_from('<I', data, off)[0]

def _i32(data, off):
    return struct.unpack_from('<i', data, off)[0]

def _f32(data, off):
    return struct.unpack_from('<f', data, off)[0]


def _parse_hkx_sections(data):
    """Parse v11 packfile section headers. Returns dict of name -> info.

    Standalone HKX v11 layout:
      0x00-0x3F  file header (64 bytes)
      0x40-0x4F  padding (16 bytes)
      0x50+      3 section headers, each 0x40 bytes
    Section header layout (relative to section header base):
      +0x00  name              (16 bytes, null-terminated)
      +0x10  marker            (4 bytes, 0xFF000000)
      +0x14  abs_data_start    (4 bytes, absolute file offset of section data)
      +0x18  local_fixup_off   (relative to abs_data_start)
      +0x1C  global_fixup_off  (relative to abs_data_start)
      +0x20  virtual_fixup_off (relative to abs_data_start)
      +0x24  exports_off       (relative to abs_data_start)
      +0x28  (unused)
      +0x2C  end_off           (relative to abs_data_start)
    """
    version = _u32(data, 0x0C)
    if version != 11:
        raise ValueError(f"Unsupported HKX version {version} (expected 11 for FO4)")

    # Section headers start at 0x50 in standalone HKX v11 files
    sec_start = 0x50

    sections = {}
    for i in range(3):
        base = sec_start + i * 0x40
        name = data[base:base + 16].split(b'\x00')[0].decode('ascii', errors='replace')
        s = _u32(data, base + 0x14)
        sections[name] = {
            'offset': s,
            'data1': s + _u32(data, base + 0x18),
            'data2': s + _u32(data, base + 0x1C),
            'data3': s + _u32(data, base + 0x20),
            'exports': s + _u32(data, base + 0x24),
            'end':   s + _u32(data, base + 0x2C),
        }
    return sections


def _parse_local_fixups(data, sec):
    """Parse local fixup table (data1): src_rel -> dst_rel within __data__."""
    fixups = {}
    pos = sec['data1']
    end = sec['data2']
    while pos + 8 <= end:
        src = _u32(data, pos)
        dst = _u32(data, pos + 4)
        if src == 0xFFFFFFFF:
            break
        fixups[src] = dst
        pos += 8
    return fixups


def _parse_virtual_fixups(data, sec, cn_start):
    """Parse virtual fixup table (data3): returns [(rel_offset, class_name)]."""
    objects = []
    pos = sec['data3']
    end = sec['exports']
    while pos + 12 <= end:
        src = _u32(data, pos)
        _u32(data, pos + 4)  # section index (unused)
        name_off = _u32(data, pos + 8)
        if src == 0xFFFFFFFF:
            break
        abs_name = cn_start + name_off
        try:
            ne = data.index(b'\x00', abs_name, abs_name + 256)
            cls = data[abs_name:ne].decode('ascii', errors='replace')
        except ValueError:
            cls = f'?{name_off:#x}'
        objects.append((src, cls))
        pos += 12
    return objects


def _read_hkarray_u32(data, data_abs, obj_rel, field_off, fixups):
    """Read an hkArray<uint32> field, returning a list of uint32 values."""
    arr_rel = obj_rel + field_off
    count = _u32(data, data_abs + arr_rel + 8)
    if count == 0:
        return []
    content_rel = fixups.get(arr_rel)
    if content_rel is None:
        return []
    content_abs = data_abs + content_rel
    return [_u32(data, content_abs + i * 4) for i in range(count)]


def _read_hkarray_u8(data, data_abs, obj_rel, field_off, fixups):
    """Read an hkArray<uint8> field, returning bytes."""
    arr_rel = obj_rel + field_off
    count = _u32(data, data_abs + arr_rel + 8)
    if count == 0:
        return b''
    content_rel = fixups.get(arr_rel)
    if content_rel is None:
        return b''
    content_abs = data_abs + content_rel
    return data[content_abs:content_abs + count]


def _read_null_string(data, abs_off):
    """Read a null-terminated ASCII string."""
    try:
        end = data.index(b'\x00', abs_off, abs_off + 256)
        return data[abs_off:end].decode('ascii', errors='replace')
    except ValueError:
        return ''


def _parse_animation_hkx(data, header_only: bool = False) -> Optional[AnimationData]:
    """Parse hkaSplineCompressedAnimation from a binary HKX file; `header_only`: any hka*Animation's length,
    track count, annotations and binding (blend hint), no tracks."""
    if data[:4] != _HKX_MAGIC:
        return None

    sections = _parse_hkx_sections(data)
    cn_sec = sections.get('__classnames__')
    data_sec = sections.get('__data__')
    if not cn_sec or not data_sec:
        return None

    cn_start = cn_sec['offset']
    data_abs = data_sec['offset']

    fixups = _parse_local_fixups(data, data_sec)
    objects = _parse_virtual_fixups(data, data_sec, cn_start)

    # Find hkaSplineCompressedAnimation
    anim_rel = None
    for rel, cls in objects:
        if cls == 'hkaSplineCompressedAnimation' or (header_only and cls.startswith('hka')
                                                      and cls.endswith('Animation')):
            anim_rel = rel
            break
    if anim_rel is None:
        return None

    a = data_abs + anim_rel
    anim = AnimationData()
    anim.duration = _f32(data, a + 0x14)
    anim.num_tracks = _u32(data, a + 0x18)
    anim.num_frames = _u32(data, a + 0x38)
    anim.num_blocks = _u32(data, a + 0x3C)
    anim.max_frames_per_block = _u32(data, a + 0x40)
    mask_and_quant_size = _u32(data, a + 0x44)
    anim.block_duration = _f32(data, a + 0x48)
    anim.frame_duration = _f32(data, a + 0x50)

    block_offsets = None if header_only else _read_hkarray_u32(data, data_abs, anim_rel, 0x58, fixups)
    data_blob = None if header_only else _read_hkarray_u8(data, data_abs, anim_rel, 0x98, fixups)

    if not header_only and (not data_blob or not block_offsets):
        return None

    # ── Parse annotation tracks (bone names) ──
    # annotationTracks is an hkArray at anim+0x28
    ann_arr_rel = anim_rel + 0x28
    ann_count = _u32(data, data_abs + ann_arr_rel + 8)
    ann_content_rel = fixups.get(ann_arr_rel)

    if ann_content_rel is not None and ann_count > 0:
        # Each hkaAnnotationTrack is 0x18 bytes: string ptr (8) + hkArray (16)
        ANNTRACK_STRIDE = 0x18
        for i in range(ann_count):
            track_rel = ann_content_rel + i * ANNTRACK_STRIDE
            # The string pointer at track_rel is resolved via local fixup
            str_target_rel = fixups.get(track_rel)
            if str_target_rel is not None:
                name = _read_null_string(data, data_abs + str_target_rel)
                anim.bone_names.append(name)
            else:
                anim.bone_names.append('')

            # Check for annotation events within this track
            ann_events_rel = track_rel + 0x08  # annotations hkArray
            ann_events_count = _u32(data, data_abs + ann_events_rel + 8)
            ann_events_content_rel = fixups.get(ann_events_rel)
            if ann_events_content_rel is not None and ann_events_count > 0:
                # Each hkaAnnotation is 0x10 bytes: float time (4) + pad (4) + string ptr (8)
                for j in range(ann_events_count):
                    evt_rel = ann_events_content_rel + j * 0x10
                    evt_time = _f32(data, data_abs + evt_rel)
                    evt_str_rel = fixups.get(evt_rel + 0x08)
                    evt_text = ''
                    if evt_str_rel is not None:
                        evt_text = _read_null_string(data, data_abs + evt_str_rel)
                    anim.annotations.append(Annotation(time=evt_time, text=evt_text))

    # ── Parse hkaAnimationBinding (bone indices, skeleton name) ──
    for rel, cls in objects:
        if cls == 'hkaAnimationBinding':
            # bind_abs = data_abs + rel
            # +0x10: originalSkeletonName (string ptr)
            anim.blend_hint = _u32(data, data_abs + rel + 0x50)
            skel_name_rel = fixups.get(rel + 0x10)
            if skel_name_rel is not None:
                anim.original_skeleton_name = _read_null_string(data, data_abs + skel_name_rel)
            # +0x20: transformTrackToBoneIndices (hkArray<int16>)
            idx_arr_rel = rel + 0x20
            idx_count = _u32(data, data_abs + idx_arr_rel + 8)
            idx_content_rel = fixups.get(idx_arr_rel)
            if idx_content_rel is not None and idx_count > 0:
                idx_abs = data_abs + idx_content_rel
                anim.track_to_bone_indices = [
                    struct.unpack_from('<h', data, idx_abs + i * 2)[0]
                    for i in range(idx_count)
                ]
            break

    if header_only:
        return anim

    # ── Decompress spline data ──
    anim.tracks = _decompress_spline(
        data_blob, anim.num_tracks, anim.num_frames,
        anim.num_blocks, anim.max_frames_per_block, block_offsets,
        mask_and_quant_size
    )

    return anim


# ═══════════════════════════════════════════════════════════════════════════════
#  XML parsing (hkpackfile format — produced by hkxpack-cli)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_skeleton_xml(root) -> Optional[Skeleton]:
    """Extract the first non-ragdoll hkaSkeleton from an hkpackfile XML tree."""
    for obj in root.iter('hkobject'):
        if obj.attrib.get('class') != 'hkaSkeleton':
            continue
        name_p = obj.find(".//hkparam[@name='name']")
        if name_p is not None and name_p.text and 'Ragdoll' in name_p.text:
            continue

        skel = Skeleton()
        if name_p is not None and name_p.text:
            skel.name = name_p.text

        bones_p = obj.find(".//hkparam[@name='bones']")
        if bones_p is not None:
            for bone_obj in bones_p.findall('hkobject'):
                np = bone_obj.find("hkparam[@name='name']")
                skel.bones.append(np.text if np is not None and np.text else '')

        parents_p = obj.find(".//hkparam[@name='parentIndices']")
        if parents_p is not None and parents_p.text:
            skel.parents = [int(x) for x in parents_p.text.strip().split()]

        ref_p = obj.find(".//hkparam[@name='referencePose']")
        if ref_p is not None and ref_p.text:
            tuples = re.findall(r'\(([^)]+)\)', ref_p.text)
            for i in range(0, len(tuples) - 2, 3):
                t = [float(x) for x in tuples[i].split()]
                r = [float(x) for x in tuples[i + 1].split()]
                s = [float(x) for x in tuples[i + 2].split()]
                skel.reference_pose.append(BonePose(t[:3], r[:4], s[:3]))
        return skel

    return None


def _parse_animation_xml(root) -> Optional[AnimationData]:
    """Parse hkaSplineCompressedAnimation from an hkpackfile XML tree."""
    anim = AnimationData()

    anim_obj = None
    for obj in root.iter('hkobject'):
        if obj.attrib.get('class') == 'hkaSplineCompressedAnimation':
            anim_obj = obj
            break
    if anim_obj is None:
        return None

    block_offsets = []
    data_ints = []

    for param in anim_obj.findall('hkparam'):
        name = param.attrib.get('name', '')
        text = param.text.strip() if param.text else ''
        if name == 'duration':
            anim.duration = float(text)
        elif name == 'numberOfTransformTracks':
            anim.num_tracks = int(text)
        elif name == 'numFrames':
            anim.num_frames = int(text)
        elif name == 'numBlocks':
            anim.num_blocks = int(text)
        elif name == 'maxFramesPerBlock':
            anim.max_frames_per_block = int(text)
        elif name == 'blockDuration':
            anim.block_duration = float(text)
        elif name == 'frameDuration':
            anim.frame_duration = float(text)
        elif name == 'blockOffsets':
            block_offsets = [int(x) for x in text.split()]
        elif name == 'data':
            data_ints = [int(x) for x in text.split()]
        elif name == 'annotationTracks':
            for track_obj in param.findall('hkobject'):
                tn = track_obj.find("hkparam[@name='trackName']")
                anim.bone_names.append(tn.text if tn is not None and tn.text else '')
                ann_param = track_obj.find("hkparam[@name='annotations']")
                if ann_param is not None:
                    for ann_obj in ann_param.findall('hkobject'):
                        time_p = ann_obj.find("hkparam[@name='time']")
                        text_p = ann_obj.find("hkparam[@name='text']")
                        if time_p is not None and time_p.text:
                            a = Annotation()
                            a.time = float(time_p.text.strip())
                            a.text = text_p.text.strip() if text_p is not None and text_p.text else ''
                            anim.annotations.append(a)

    if not data_ints or not block_offsets:
        return None

    data_bytes = bytes(data_ints)
    anim.tracks = _decompress_spline(
        data_bytes, anim.num_tracks, anim.num_frames,
        anim.num_blocks, anim.max_frames_per_block, block_offsets
    )

    anim.skeleton = _parse_skeleton_xml(root)
    return anim


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def is_fo4_hkx(filepath: str) -> bool:
    """Return True if filepath is a FO4 (hk_2014) binary HKX file."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(0x38)
        if len(header) < 0x38:
            return False
        if header[:4] != _HKX_MAGIC:
            return False
        version = struct.unpack_from('<I', header, 0x0C)[0]
        if version != 11:
            return False
        contents = header[0x28:0x38].split(b'\x00')[0].decode('ascii', errors='replace')
        return contents.startswith('hk_2014')
    except (OSError, IOError):
        return False


def _parse_skeleton_hkx(data: bytes) -> Optional[Skeleton]:
    """Parse hkaSkeleton from a binary HKX file."""
    if data[:4] != _HKX_MAGIC:
        return None

    sections = _parse_hkx_sections(data)
    cn_sec = sections.get('__classnames__')
    data_sec = sections.get('__data__')
    if not cn_sec or not data_sec:
        return None

    cn_start = cn_sec['offset']
    data_abs = data_sec['offset']

    fixups = _parse_local_fixups(data, data_sec)
    objects = _parse_virtual_fixups(data, data_sec, cn_start)

    # Find hkaSkeleton
    skel_rel = None
    for rel, cls in objects:
        if cls == 'hkaSkeleton':
            skel_rel = rel
            break
    if skel_rel is None:
        return None

    s = data_abs + skel_rel
    skel = Skeleton()

    # +0x10: name (string ptr)
    name_target = fixups.get(skel_rel + 0x10)
    if name_target is not None:
        skel.name = _read_null_string(data, data_abs + name_target)

    # +0x18: parentIndices (hkArray<int16>)
    pi_count = _u32(data, s + 0x18 + 8)
    pi_content = fixups.get(skel_rel + 0x18)
    if pi_content is not None and pi_count > 0:
        pi_abs = data_abs + pi_content
        skel.parents = [
            struct.unpack_from('<h', data, pi_abs + i * 2)[0]
            for i in range(pi_count)
        ]

    # +0x28: bones (hkArray<hkaBone>) — each hkaBone is 0x10: string ptr (8) + lockTranslation (4) + pad (4)
    bone_count = _u32(data, s + 0x28 + 8)
    bone_content = fixups.get(skel_rel + 0x28)
    if bone_content is not None and bone_count > 0:
        BONE_STRIDE = 0x10
        for i in range(bone_count):
            bone_rel = bone_content + i * BONE_STRIDE
            str_target = fixups.get(bone_rel)
            if str_target is not None:
                skel.bones.append(_read_null_string(data, data_abs + str_target))
            else:
                skel.bones.append('')
            lt = data[data_abs + bone_rel + 8]
            skel.lock_translation.append(bool(lt))

    # +0x38: referencePose (hkArray<hkQsTransform>) — each is 0x30 bytes: vec4 pos + vec4 rot + vec4 scale
    pose_count = _u32(data, s + 0x38 + 8)
    pose_content = fixups.get(skel_rel + 0x38)
    if pose_content is not None and pose_count > 0:
        POSE_STRIDE = 0x30
        for i in range(pose_count):
            p = data_abs + pose_content + i * POSE_STRIDE
            tx, ty, tz = _f32(data, p), _f32(data, p+4), _f32(data, p+8)
            rx, ry, rz, rw = _f32(data, p+16), _f32(data, p+20), _f32(data, p+24), _f32(data, p+28)
            sx, sy, sz = _f32(data, p+32), _f32(data, p+36), _f32(data, p+40)
            skel.reference_pose.append(BonePose([tx, ty, tz], [rx, ry, rz, rw], [sx, sy, sz]))

    # +0x48: referenceFloats (hkArray<float>)
    rfloat_count = _u32(data, s + 0x48 + 8)
    rfloat_content = fixups.get(skel_rel + 0x48)
    if rfloat_content is not None and rfloat_count > 0:
        rabs = data_abs + rfloat_content
        skel.reference_floats = [_f32(data, rabs + i * 4) for i in range(rfloat_count)]

    # +0x58: floatSlots (hkArray<hkStringPtr>)
    fslot_count = _u32(data, s + 0x58 + 8)
    fslot_content = fixups.get(skel_rel + 0x58)
    if fslot_content is not None and fslot_count > 0:
        for i in range(fslot_count):
            slot_ptr_rel = fslot_content + i * 8
            str_target = fixups.get(slot_ptr_rel)
            if str_target is not None:
                skel.float_slots.append(_read_null_string(data, data_abs + str_target))
            else:
                skel.float_slots.append('')

    return skel


def parse_fo4_skeleton(raw: bytes) -> Optional[Skeleton]:
    """A FO4 skeleton from binary HKX bytes (e.g. read from a BA2); None without one.

    TESConversion: public entry for in-memory files.
    """
    return _parse_skeleton_hkx(raw)


def parse_fo4_animation(raw: bytes) -> Optional[AnimationData]:
    """A FO4 animation from binary HKX bytes (e.g. read from a BA2); None without one."""
    return _parse_animation_hkx(raw)


def fo4_animation_header(raw: bytes) -> Optional[AnimationData]:
    """Any FO4 animation's (lossless-compressed too) length, track count, annotations and blend hint, no tracks."""
    return _parse_animation_hkx(raw, header_only=True) if raw[:4] == _HKX_MAGIC else None


def load_fo4_skeleton(filepath: str) -> Optional[Skeleton]:
    """Load a FO4 skeleton from a binary HKX file.

    Returns Skeleton with bone names, parent indices, and reference pose,
    or None if no hkaSkeleton was found.
    """
    filepath = str(filepath)
    with open(filepath, 'rb') as f:
        raw = f.read()

    if raw[:4] == _HKX_MAGIC:
        return _parse_skeleton_hkx(raw)

    # Try XML
    if raw[:5] == b'<?xml' or raw[:1] == b'<':
        try:
            tree = ET.parse(filepath)
        except ET.ParseError:
            return None
        root = tree.getroot()
        if root.tag == 'hkpackfile':
            return _parse_skeleton_xml(root)

    return None


def load_fo4_animation(filepath: str) -> AnimationData:
    """Load a FO4 animation from a binary HKX or hkpackfile XML.

    Parameters
    ----------
    filepath : str
        Path to a .hkx (binary) or .xml (hkpackfile) file.

    Returns
    -------
    AnimationData with fully decompressed tracks.

    Raises
    ------
    ValueError  if the file cannot be parsed.
    """
    filepath = str(filepath)

    with open(filepath, 'rb') as f:
        raw = f.read()

    # Detect format by magic bytes
    if raw[:4] == _HKX_MAGIC:
        anim = _parse_animation_hkx(raw)
        if anim is None:
            raise ValueError("No hkaSplineCompressedAnimation found in HKX file.")
        return anim

    # Try XML
    if raw[:5] == b'<?xml' or raw[:1] == b'<':
        try:
            tree = ET.parse(filepath)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML: {e}")

        root = tree.getroot()
        if root.tag != 'hkpackfile':
            raise ValueError(
                f"Expected hkpackfile XML, got <{root.tag}>. "
                f"This may be a Skyrim tagfile — FO4 uses hkpackfile format."
            )

        anim = _parse_animation_xml(root)
        if anim is None:
            raise ValueError("No hkaSplineCompressedAnimation found in file.")
        return anim

    raise ValueError(f"Unrecognized file format (not HKX binary or XML).")


# ═══════════════════════════════════════════════════════════════════════════════
#  Export: Writer helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _w_u8(v: int) -> bytes: return struct.pack('<B', v & 0xFF)
def _w_u16(v: int) -> bytes: return struct.pack('<H', v & 0xFFFF)
def _w_u32(v: int) -> bytes: return struct.pack('<I', v & 0xFFFFFFFF)
def _w_u64(v: int) -> bytes: return struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF)
def _w_i16(v: int) -> bytes: return struct.pack('<h', v)
def _w_f32(v: float) -> bytes: return struct.pack('<f', v)

def _pad16(data: bytes, fill: int = 0xFF) -> bytes:
    r = len(data) % 16
    return data + (bytes([fill]) * (16 - r) if r else b'')

def _pad4(data: bytearray) -> None:
    r = len(data) % 4
    if r:
        data.extend(b'\x00' * (4 - r))

def _hkarray(count: int) -> bytes:
    cap = (count | 0x80000000) if count > 0 else 0x80000000
    return _w_u64(0) + _w_u32(count) + _w_u32(cap)


def _packed_quats(q: np.ndarray, rot_quant: int) -> bytes:
    """Quaternions `q` [n, 4] (x, y, z, w) packed 40-bit at rot_quant 1, else 48-bit, as _read_quats unpacks
    them: the three smaller components quantized, the largest one's index and sign in the
    spare bits."""
    shift = np.abs(q).argmax(1)
    sign = (q[np.arange(len(q)), shift] < 0).astype(np.int64)
    rest = np.take_along_axis(q, _OTHERS[shift], 1)
    if rot_quant == 1:
        raw = np.clip(np.rint(rest / _FRACTAL_40 + 2049), 0, 0xFFF).astype(np.int64)
        packed = raw[:, 0] | raw[:, 1] << 12 | raw[:, 2] << 24 | shift << 36 | sign << 38
        return packed.astype('<u8').view(np.uint8).reshape(-1, 8)[:, :5].tobytes()
    raw = np.clip(np.rint(rest / _FRACTAL_48 + 16383), 0, 0x7FFF).astype(np.int64)
    raw |= np.stack([shift & 1, shift >> 1 & 1, sign], 1) << 15
    return raw.astype('<u2').tobytes()


def _write_48bit_quat(q) -> bytes:
    """Quaternion `q` (x, y, z, w) as 6 bytes, as _read_quats reads it."""
    return _packed_quats(np.array([q], float), 2)


def _write_40bit_quat(q) -> bytes:
    """Quaternion `q` (x, y, z, w) as 5 bytes, as _read_quats reads it."""
    return _packed_quats(np.array([q], float), 1)


def _quantized(values: np.ndarray, lows, highs, quant: int) -> bytes:
    """`values` [n, k] as fractions of each column's [low, high], 8-bit at quant 0 else 16-bit, row by row; 0 in a
    column whose high - low is under 1e-30."""
    top = 255 if quant == 0 else 65535
    span = np.subtract(highs, lows)
    with np.errstate(divide='ignore', invalid='ignore'):
        scaled = np.clip(np.rint((values - lows) / span * top), 0, top)
    return np.where(np.abs(span) < 1e-30, 0, scaled).astype('<u1' if quant == 0 else '<u2').tobytes()


def _write_16bit_scalar(val: float, mn: float, mx: float) -> bytes:
    """`val` as a 16-bit fraction of [mn, mx]."""
    return _quantized(np.array([[val]], float), [mn], [mx], 1)


def _write_8bit_scalar(val: float, mn: float, mx: float) -> bytes:
    """`val` as an 8-bit fraction of [mn, mx]."""
    return _quantized(np.array([[val]], float), [mn], [mx], 0)


def _make_clamped_knots(n_cp: int, degree: int) -> List[int]:
    """Build a clamped uniform knot vector with integer values (uint8-storable).

    For n_cp control points and given degree, returns n_cp + degree + 1 knots.
    Knot range is [0, n_cp - degree - 1] for the standard clamped uniform form,
    BUT we remap to [0, max_t] where max_t = n_cp - 1 (matching frame indices).
    """
    if n_cp <= degree + 1:
        # Bezier-like: all knots clamped at 0 and n_cp-1
        return [0] * (degree + 1) + [n_cp - 1] * (degree + 1)

    max_t = n_cp - 1
    # Clamped: first (degree+1) at 0, last (degree+1) at max_t
    # Interior knots evenly spaced at integer values
    knots = [0] * (degree + 1)
    n_interior = n_cp - degree - 1
    for i in range(n_interior):
        knots.append(int(round((i + 1) * max_t / (n_interior + 1))))
    knots.extend([max_t] * (degree + 1))
    return knots


#: Tolerance for the identity and static tests.
_EPS = 1e-5
#: FO4's quantizations: 16-bit positions, 48-bit quaternions (Skyrim's 40-bit is rot_quant 1), 16-bit scales.
_POS_QUANT, _ROT_QUANT, _SCALE_QUANT = 1, 2, 1


def _kinds(near: np.ndarray, values: np.ndarray, axes) -> np.ndarray:
    """Per track: 0 if `near` over `axes`, else 1 if static (_EPS), else 2."""
    still = np.abs(values - values[:, :1]) < _EPS
    return np.where(near.all(axes), 0, np.where(still.all(axes), 1, 2))


def _axis_flags(kinds: np.ndarray) -> np.ndarray:
    """Per track, mask bit `axis` if static, `axis + 4` if a spline."""
    return ((kinds == 1) << np.arange(3)).sum(1) | ((kinds == 2) << np.arange(4, 7)).sum(1)


def _masks(pos: np.ndarray, rot: np.ndarray, scale: np.ndarray, rot_quant: int) -> bytes:
    """Every track's four mask bytes from its kinds: the quantizations, then position, rotation and scale flags."""
    quant = _POS_QUANT & 3 | (rot_quant & 0xF) << 2 | (_SCALE_QUANT & 3) << 6
    turn = np.where(rot == 1, 0x0F, np.where(rot == 2, 0xF0, 0))
    rows = [np.full(len(rot), quant), _axis_flags(pos), turn, _axis_flags(scale)]
    return np.stack(rows, 1).astype(np.uint8).tobytes()


def _align_out(out: bytearray, align: int) -> None:
    """Zeros onto `out` until its length is a multiple of `align`."""
    out.extend(bytes(-len(out) % align))


def _spline_header(out: bytearray, n_cp: int, align: int) -> None:
    """A spline's control point count less one (u16), degree (1, or 0 for one point) and clamped knots (u8),
    aligned to `align`."""
    degree = min(1, n_cp - 1)
    out.extend(_w_u16(n_cp - 1))
    out.append(degree)
    out.extend(min(255, k) for k in _make_clamped_knots(n_cp, degree))
    _align_out(out, align)


def _scalar_channel(out: bytearray, values: np.ndarray, kinds: np.ndarray, quant: int) -> None:
    """A position or scale channel of `values` [frame, axis] by axis `kinds` (0 identity, 1 static, 2 spline): a
    spline header when any axis is a spline; per axis, a static value or a spline's (min, max) as f32; then each
    frame's spline axes quantized (8-bit at quant 0, else 16-bit); padded to 4. Frames are the control points."""
    spline = kinds == 2
    if spline.any():
        _spline_header(out, len(values), 4)
    lows, highs = [], []
    for axis in np.flatnonzero(kinds).tolist():
        if kinds[axis] == 1:
            out.extend(_w_f32(values[0, axis].item()))
            continue
        column = values[:, axis].tolist()
        low, high = min(column), max(column)
        high = low + 1e-6 if abs(high - low) < 1e-30 else high
        out.extend(_w_f32(low) + _w_f32(high))
        lows.append(low)
        highs.append(high)
    if lows:
        out.extend(_quantized(values[:, spline], lows, highs, quant))
    _pad4(out)


def _rotation_channel(out: bytearray, quats: np.ndarray, kind: int, rot_quant: int) -> None:
    """A rotation channel of `quats` [frame, 4] (x, y, z, w) by `kind`: a spline's header and every frame sign-chained
    and normalized, or the static first frame as is; packed for `rot_quant`; padded to 4."""
    align = _QUAT_ALIGN.get(rot_quant, 4)
    if kind == 2:
        _spline_header(out, len(quats), align)
        out.extend(_packed_quats(_normalized(quats * _chain_signs(quats)[:, None]), rot_quant))
    elif kind == 1:
        _align_out(out, align)
        out.extend(_packed_quats(quats[:1], rot_quant))
    _pad4(out)


def _compress_block(pos: np.ndarray, rot: np.ndarray, scale: np.ndarray, rot_quant: int = _ROT_QUANT) -> bytes:
    """One block's bytes from `pos`, `rot` (x, y, z, w) and `scale`, each [track, frame, axis]: every track's
    mask, padded to 4, then per track its position, rotation and scale channels."""
    kinds = (_kinds(np.abs(pos) < _EPS, pos, 1),
             _kinds(np.abs(np.abs(rot) - (0.0, 0.0, 0.0, 1.0)) < _EPS, rot, (1, 2)),
             _kinds(np.abs(scale - 1.0) < _EPS, scale, 1))
    out = bytearray(_masks(*kinds, rot_quant))
    _pad4(out)
    for track in range(len(pos)):
        _scalar_channel(out, pos[track], kinds[0][track], _POS_QUANT)
        _rotation_channel(out, rot[track], kinds[1][track], rot_quant)
        _scalar_channel(out, scale[track], kinds[2][track], _SCALE_QUANT)
    return bytes(out)


def _channel(tracks: List[TrackData], name: str, width: int, frames: int) -> np.ndarray:
    """The tracks' `name` over `frames` frames as [track, frame, width]."""
    return np.array([getattr(t, name)[:frames] for t in tracks], float).reshape(len(tracks), frames, width)


def _compress_all_blocks(anim: AnimationData, rot_quant: int = _ROT_QUANT) -> Tuple[bytes, List[int]]:
    """Compress all animation blocks. Returns (data_blob, block_offsets)."""
    max_fpb, num_blocks = anim.max_frames_per_block or 256, anim.num_blocks or 1
    channels = [_channel(anim.tracks, name, width, anim.num_frames)
                for name, width in (('translations', 3), ('rotations', 4), ('scales', 3))]
    data, block_offsets = bytearray(), []
    for block_idx in range(num_blocks):
        first = block_idx * max_fpb
        last = anim.num_frames if block_idx == num_blocks - 1 else first + max_fpb
        block_offsets.append(len(data))
        data.extend(_compress_block(*(c[:, first:last] for c in channels), rot_quant))
    return bytes(data), block_offsets


# ═══════════════════════════════════════════════════════════════════════════════
#  Export: HKX packfile writer
# ═══════════════════════════════════════════════════════════════════════════════

_ANIM_CLASS_ENTRIES: List[Tuple[int, str]] = [
    (0x33D42383, 'hkClass'),
    (0xB0EFA719, 'hkClassMember'),
    (0x8A3609CF, 'hkClassEnum'),
    (0xCE6F8A6C, 'hkClassEnumItem'),
    (0x2772C11E, 'hkRootLevelContainer'),
    (0x26859F4C, 'hkaAnimationContainer'),
    (0x8C3B5F7E, 'hkaSplineCompressedAnimation'),
    (0x60F8E0B8, 'hkaDefaultAnimatedReferenceFrame'),
    (0x0FAF9150, 'hkaAnimationBinding'),
    (0x1DE13A73, 'hkMemoryResourceContainer'),
]


class _FixupBuilder:
    """Accumulates local, global, and virtual fixup entries."""
    def __init__(self):
        self.local: List[Tuple[int, int]] = []
        self.global_: List[Tuple[int, int, int]] = []
        self.virtual: List[Tuple[int, int, int]] = []

    def add_local(self, src_rel: int, dst_rel: int):
        self.local.append((src_rel, dst_rel))

    def add_global(self, src_rel: int, sec_idx: int, dst_rel: int):
        self.global_.append((src_rel, sec_idx, dst_rel))

    def add_virtual(self, obj_rel: int, sec_idx: int, name_off: int):
        self.virtual.append((obj_rel, sec_idx, name_off))

    # TESConversion: each table is padded to 16 bytes with 0xFF, as every vanilla FO4 packfile's is.
    def build_local_table(self) -> bytes:
        out = b''
        for src, dst in sorted(self.local):
            out += _w_u32(src) + _w_u32(dst)
        return _pad16(out)

    def build_global_table(self) -> bytes:
        out = b''
        for src, sec, dst in sorted(self.global_):
            out += _w_u32(src) + _w_u32(sec) + _w_u32(dst)
        return _pad16(out)

    def build_virtual_table(self) -> bytes:
        out = b''
        for obj, sec, noff in sorted(self.virtual):
            out += _w_u32(obj) + _w_u32(sec) + _w_u32(noff)
        return _pad16(out)


def _build_anim_classnames() -> Tuple[bytes, Dict[str, int]]:
    """Build __classnames__ section for animation HKX."""
    data = b''
    name_offs: Dict[str, int] = {}
    for hash_val, name in _ANIM_CLASS_ENTRIES:
        name_offs[name] = len(data) + 5
        data += struct.pack('<IB', hash_val, 0x09) + name.encode('ascii') + b'\x00'
    data = _pad16(data, fill=0xFF)
    return data, name_offs


def _anim_file_header(cn_name_off: int) -> bytes:
    """Build the 0x40-byte file header for a standalone HKX."""
    hdr = bytearray(0x50)  # 0x40 header + 0x10 padding block
    hdr[0x00:0x04] = _HKX_MAGIC
    hdr[0x04:0x08] = b'\x10\xc0\xc0\x10'          # second magic
    struct.pack_into('<i', hdr, 0x08, 0)           # userTag
    struct.pack_into('<i', hdr, 0x0C, 11)          # fileVersion
    hdr[0x10:0x14] = b'\x08\x01\x00\x01'          # layoutRules (64-bit LE)
    struct.pack_into('<i', hdr, 0x14, 3)           # numSections
    struct.pack_into('<i', hdr, 0x18, 2)           # contentsSectionIndex
    struct.pack_into('<i', hdr, 0x1C, 0)           # contentsSectionOffset
    struct.pack_into('<i', hdr, 0x20, 0)           # contentsClassNameSectionIndex
    struct.pack_into('<i', hdr, 0x24, cn_name_off) # contentsClassNameSectionOffset
    hdr[0x28:0x38] = b'hk_2014.1.0-r1\x00\xff'
    struct.pack_into('<i', hdr, 0x38, 0)           # flags
    struct.pack_into('<H', hdr, 0x3C, 21)          # maxPredicate (u16)
    struct.pack_into('<H', hdr, 0x3E, 0x10)        # sectionOffset (u16)
    # Padding block at 0x40
    struct.pack_into('<i', hdr, 0x40, 0x14)        # padding block marker
    return bytes(hdr)


def _anim_section_header(name: str, abs_start: int,
                         local_fix: int, global_fix: int,
                         virt_fix: int, exports: int) -> bytes:
    """Build a 0x40-byte section header."""
    hdr = bytearray(0x40)
    # TESConversion: the name zero-padded to 16 bytes, then the 0xFF000000 marker, as vanilla's section headers.
    hdr[:16] = name.encode('ascii').ljust(16, b'\x00')
    struct.pack_into('<I', hdr, 0x10, 0xFF000000)
    struct.pack_into('<I', hdr, 0x14, abs_start)
    struct.pack_into('<I', hdr, 0x18, local_fix - abs_start)
    struct.pack_into('<I', hdr, 0x1C, global_fix - abs_start)
    struct.pack_into('<I', hdr, 0x20, virt_fix - abs_start)
    struct.pack_into('<I', hdr, 0x24, exports - abs_start)
    struct.pack_into('<I', hdr, 0x28, exports - abs_start)
    struct.pack_into('<I', hdr, 0x2C, exports - abs_start)
    for i in range(0x30, 0x40):
        hdr[i] = 0xFF
    return bytes(hdr)


def _build_anim_data_section(anim: AnimationData, name_offs: Dict[str, int]) -> Tuple[bytes, '_FixupBuilder']:
    """Build the __data__ section object data for an animation HKX.

    Returns (object_data_bytes, fixup_builder).
    """
    fx = _FixupBuilder()
    data = bytearray()

    def rel():
        return len(data)

    def write(b):
        off = len(data)
        data.extend(b)
        return off

    def write_string(s: str) -> int:
        off = rel()
        data.extend(s.encode('ascii') + b'\x00')
        return off

    def align16():
        while len(data) % 16:
            data.append(0)

    def write_string16(s: str) -> int:
        """TESConversion: a member string padded to 16 bytes, as vanilla FO4 packfiles lay them out."""
        off = write_string(s)
        align16()
        return off

    spline_blob, block_offsets = _compress_all_blocks(anim)

    num_tracks = anim.num_tracks
    bone_names = anim.bone_names or [f"Bone{i}" for i in range(num_tracks)]
    skel_name = anim.original_skeleton_name or "Root"
    binding_indices = anim.track_to_bone_indices or list(range(num_tracks))

    # ═══ hkRootLevelContainer (0x00) ═══
    rlc_rel = rel()
    fx.add_virtual(rlc_rel, 0, name_offs['hkRootLevelContainer'])
    # namedVariants hkArray — 2 entries
    arr_rlc = write(_hkarray(2))
    align16()

    # namedVariant data: 2 entries, each 0x18 bytes (name_ptr + class_ptr + variant_ptr)
    nv_data_rel = rel()
    fx.add_local(arr_rlc, nv_data_rel)
    # Variant 0: animation container
    nv0_name = write(bytes(8))    # name ptr (patched)
    nv0_class = write(bytes(8))   # class ptr (patched)
    nv0_variant = write(bytes(8)) # variant ptr (patched)
    # Variant 1: resource data
    nv1_name = write(bytes(8))
    nv1_class = write(bytes(8))
    nv1_variant = write(bytes(8))
    align16()

    # Variant strings
    nv0_name_str = write_string16("Merged Animation Container")
    nv0_class_str = write_string16("hkaAnimationContainer")
    nv1_name_str = write_string16("Resource Data")
    nv1_class_str = write_string16("hkMemoryResourceContainer")

    # Fixups for variant name/class strings (local)
    fx.add_local(nv0_name, nv0_name_str)
    fx.add_local(nv0_class, nv0_class_str)
    fx.add_local(nv1_name, nv1_name_str)
    fx.add_local(nv1_class, nv1_class_str)

    # ═══ hkaAnimationContainer ═══
    ac_rel = rel()
    fx.add_virtual(ac_rel, 0, name_offs['hkaAnimationContainer'])
    fx.add_global(nv0_variant, 2, ac_rel)  # RLC variant[0] → here

    # Base class (vtable + memSizeAndFlags) then 5 hkArrays + padding
    write(bytes(16))                # base class
    write(_hkarray(0))              # +0x10: skeletons
    arr_anims = write(_hkarray(1))  # +0x20: animations
    arr_binds = write(_hkarray(1))  # +0x30: bindings
    write(_hkarray(0))              # +0x40: attachments
    write(_hkarray(0))              # +0x50: skins
    align16()

    # Animation pointer array (1 entry, 8 bytes, aligned to 16)
    anim_ptr_array_rel = rel()
    fx.add_local(arr_anims, anim_ptr_array_rel)
    anim_ptr = write(bytes(8))  # ptr → hkaSplineCompressedAnimation
    align16()

    # Binding pointer array (1 entry, 8 bytes, aligned to 16)
    bind_ptr_array_rel = rel()
    fx.add_local(arr_binds, bind_ptr_array_rel)
    bind_ptr = write(bytes(8))  # ptr → hkaAnimationBinding
    align16()

    # ═══ hkaSplineCompressedAnimation ═══
    spline_rel = rel()
    fx.add_virtual(spline_rel, 0, name_offs['hkaSplineCompressedAnimation'])
    fx.add_global(anim_ptr, 2, spline_rel)  # AnimContainer.animations[0] → here

    # hkaAnimation base: type(u32) + pad + ... (0x28 bytes base, then specific fields)
    # Simplified: write 0xA8 bytes for the full hkaSplineCompressedAnimation header
    spline_hdr = bytearray(0xA8)
    struct.pack_into('<I', spline_hdr, 0x10, 3)    # type = HK_SPLINE_COMPRESSED_ANIMATION (after base class)
    # +0x10: annotationTracks hkArray → filled below
    struct.pack_into('<f', spline_hdr, 0x14, anim.duration)
    struct.pack_into('<I', spline_hdr, 0x18, num_tracks)
    # +0x20: extractedMotion ptr → filled below
    # +0x28: annotationTracks hkArray → filled below
    struct.pack_into('<I', spline_hdr, 0x38, anim.num_frames)
    struct.pack_into('<I', spline_hdr, 0x3C, anim.num_blocks or 1)
    struct.pack_into('<I', spline_hdr, 0x40, anim.max_frames_per_block or 256)
    # +0x44: maskAndQuantizationSize (will compute)
    struct.pack_into('<f', spline_hdr, 0x48, anim.block_duration)
    # +0x4C: inverseDuration
    if anim.duration > 0:
        struct.pack_into('<f', spline_hdr, 0x4C, 1.0 / anim.block_duration if anim.block_duration > 0 else 0.0)
    struct.pack_into('<f', spline_hdr, 0x50, anim.frame_duration)
    # hkArrays at known offsets (relative to spline_rel):
    # +0x58: blockOffsets
    # +0x68: floatBlockOffsets
    # +0x78: transformOffsets
    # +0x88: floatOffsets
    # +0x98: data (the spline blob)
    n_blocks = anim.num_blocks or 1
    struct.pack_into('<I', spline_hdr, 0x58 + 8, n_blocks)           # blockOffsets size
    struct.pack_into('<I', spline_hdr, 0x58 + 12, n_blocks | 0x80000000)
    struct.pack_into('<I', spline_hdr, 0x68 + 8, n_blocks)           # floatBlockOffsets size
    struct.pack_into('<I', spline_hdr, 0x68 + 12, n_blocks | 0x80000000)
    struct.pack_into('<I', spline_hdr, 0x78 + 12, 0x80000000)        # transformOffsets DONT_DEALLOCATE
    struct.pack_into('<I', spline_hdr, 0x88 + 12, 0x80000000)        # floatOffsets DONT_DEALLOCATE
    struct.pack_into('<I', spline_hdr, 0x98 + 8, len(spline_blob))   # data size
    struct.pack_into('<I', spline_hdr, 0x98 + 12, len(spline_blob) | 0x80000000)

    # Compute maskAndQuantizationSize (bytes of mask data per block = 4 * numTracks, aligned)
    mask_size = _align(4 * num_tracks, 4)
    struct.pack_into('<I', spline_hdr, 0x44, mask_size)

    # annotationTracks array
    struct.pack_into('<I', spline_hdr, 0x28 + 8, num_tracks)
    struct.pack_into('<I', spline_hdr, 0x28 + 12, num_tracks | 0x80000000)

    write(bytes(spline_hdr))
    align16()

    # Annotation track structs (0x18 each: name_ptr + annotations hkArray)
    annot_tracks_rel = rel()
    fx.add_local(spline_rel + 0x28, annot_tracks_rel)
    annot_track_offsets = []
    for i in range(num_tracks):
        at_rel = rel()
        annot_track_offsets.append(at_rel)
        write(bytes(8))      # name ptr
        # TESConversion: the clip's events sit on track 0, as vanilla FO4 clips keep them.
        write(_hkarray(len(anim.annotations) if i == 0 else 0))

    # TESConversion: each track's name string, then (track 0) its hkaAnnotation structs (time f32, pad, text ptr)
    # and their texts, every string padded to 16: vanilla's order and layout.
    for i in range(num_tracks):
        name = bone_names[i] if i < len(bone_names) else ""
        fx.add_local(annot_track_offsets[i], write_string16(name))
        if i == 0 and anim.annotations:
            events_rel = rel()
            fx.add_local(annot_track_offsets[0] + 8, events_rel)
            for a in anim.annotations:
                write(_w_f32(a.time) + bytes(12))
            for j, a in enumerate(anim.annotations):
                fx.add_local(events_rel + j * 0x10 + 8, write_string16(a.text))

    # Block offsets array
    block_off_data_rel = rel()
    fx.add_local(spline_rel + 0x58, block_off_data_rel)
    for bo in block_offsets:
        write(_w_u32(bo))
    align16()

    # Float block offsets array
    float_block_off_data_rel = rel()
    fx.add_local(spline_rel + 0x68, float_block_off_data_rel)
    for _ in range(n_blocks):
        write(_w_u32(0))
    align16()

    # Spline data blob
    spline_data_rel = rel()
    fx.add_local(spline_rel + 0x98, spline_data_rel)
    write(spline_blob)
    align16()

    # extractedMotion → hkaDefaultAnimatedReferenceFrame
    ref_frame_rel = rel()
    fx.add_virtual(ref_frame_rel, 0, name_offs['hkaDefaultAnimatedReferenceFrame'])
    fx.add_global(spline_rel + 0x20, 2, ref_frame_rel)

    # hkaDefaultAnimatedReferenceFrame: 0x60 header (vanilla's size) + referenceFrameSamples
    # Base class is 0x20 bytes (16-byte base + padding for vec4 alignment)
    ref_hdr = bytearray(0x60)
    # +0x20: up vec4 = (0,0,1,0)
    struct.pack_into('<ffff', ref_hdr, 0x20, 0.0, 0.0, 1.0, 0.0)
    # +0x30: forward vec4 = (0,1,0,0)
    struct.pack_into('<ffff', ref_hdr, 0x30, 0.0, 1.0, 0.0, 0.0)
    # +0x40: duration
    struct.pack_into('<f', ref_hdr, 0x40, anim.duration)
    # +0x48: referenceFrameSamples hkArray
    n_samples = anim.num_frames
    struct.pack_into('<I', ref_hdr, 0x48 + 8, n_samples)
    struct.pack_into('<I', ref_hdr, 0x48 + 12, n_samples | 0x80000000)
    write(bytes(ref_hdr))

    # referenceFrameSamples data (vec4 per sample, all zeros = no root motion)
    ref_samples_rel = rel()
    fx.add_local(ref_frame_rel + 0x48, ref_samples_rel)
    write(bytes(16 * n_samples))
    align16()

    # ═══ hkaAnimationBinding ═══
    binding_rel = rel()
    fx.add_virtual(binding_rel, 0, name_offs['hkaAnimationBinding'])
    fx.add_global(bind_ptr, 2, binding_rel)  # AnimContainer.bindings[0] → here

    bind_hdr = bytearray(0x58)
    # +0x10: originalSkeletonName ptr → filled below
    # +0x18: animation ptr → filled below (global to spline)
    # +0x20: transformTrackToBoneIndices hkArray
    struct.pack_into('<I', bind_hdr, 0x20 + 8, len(binding_indices))
    struct.pack_into('<I', bind_hdr, 0x20 + 12, len(binding_indices) | 0x80000000)
    # +0x30: floatTrackToFloatSlotIndices (empty, flagged)
    struct.pack_into('<I', bind_hdr, 0x30 + 12, 0x80000000)
    # +0x40: partitionIndices (empty, flagged)
    struct.pack_into('<I', bind_hdr, 0x40 + 12, 0x80000000)
    # +0x50: blendHint (0 normal, 2 additive)
    struct.pack_into('<I', bind_hdr, 0x50, anim.blend_hint)
    write(bytes(bind_hdr))
    align16()

    # Skeleton name string
    fx.add_local(binding_rel + 0x10, write_string16(skel_name))

    # Animation ptr (global fixup — inter-object reference)
    fx.add_global(binding_rel + 0x18, 2, spline_rel)

    # Binding indices array
    bind_idx_rel = rel()
    fx.add_local(binding_rel + 0x20, bind_idx_rel)
    for idx in binding_indices:
        write(_w_i16(idx))
    align16()

    # ═══ hkMemoryResourceContainer ═══
    mrc_rel = rel()
    fx.add_virtual(mrc_rel, 0, name_offs['hkMemoryResourceContainer'])
    fx.add_global(nv1_variant, 2, mrc_rel)  # RLC variant[1] → here
    # TESConversion: vanilla's 64-byte layout: base(16), name(8, an empty string, never null), parent(8, runtime),
    # resourceHandles and children (empty hkArrays, DONT_DEALLOCATE). A null name crashed the game when it freed
    # the clip. See docs/fork/fo4_spikes.md#own-rig-clip-layout
    mrc_buf = bytearray(64)
    struct.pack_into('<I', mrc_buf, 0x2C, 0x80000000)  # resourceHandles cap
    struct.pack_into('<I', mrc_buf, 0x3C, 0x80000000)  # children cap
    write(bytes(mrc_buf))
    fx.add_local(mrc_rel + 0x10, write_string16(''))

    return bytes(data), fx


def write_fo4_animation(filepath: str, anim: AnimationData) -> None:
    """Write an AnimationData to a FO4 HKX binary file.

    Parameters
    ----------
    filepath : str
        Output path for the .hkx file.
    anim : AnimationData
        Must have tracks, duration, num_frames, frame_duration populated.
    """
    # Fill in defaults
    if not anim.num_blocks:
        max_fpb = anim.max_frames_per_block or 256
        anim.num_blocks = max(1, (anim.num_frames + max_fpb - 1) // max_fpb)
    if not anim.block_duration:
        anim.block_duration = anim.duration / anim.num_blocks if anim.num_blocks > 0 else anim.duration
    if not anim.frame_duration:
        anim.frame_duration = anim.duration / max(1, anim.num_frames - 1) if anim.num_frames > 1 else 1.0 / 30.0

    # Build sections
    cn_data, name_offs = _build_anim_classnames()
    obj_data, fx = _build_anim_data_section(anim, name_offs)

    local_tbl = fx.build_local_table()
    global_tbl = fx.build_global_table()
    virt_tbl = fx.build_virtual_table()
    data_section = obj_data + local_tbl + global_tbl + virt_tbl

    # Standalone HKX layout:
    # 0x00: file header (0x40)
    # 0x40: 16 bytes padding
    # 0x50: section header 0 (0x40)
    # 0x90: section header 1 (0x40)
    # 0xD0: section header 2 (0x40)
    # 0x110: classnames data
    # cn_end: data section
    cn_start = 0x110
    cn_end = cn_start + len(cn_data)
    data_start = cn_end

    local_fix_abs = data_start + len(obj_data)
    global_fix_abs = local_fix_abs + len(local_tbl)
    virt_fix_abs = global_fix_abs + len(global_tbl)
    data_end = virt_fix_abs + len(virt_tbl)

    cn_name_off = name_offs['hkRootLevelContainer']
    hdr = _anim_file_header(cn_name_off)

    shdr0 = _anim_section_header('__classnames__', cn_start,
                                  cn_start + len(cn_data), cn_start + len(cn_data),
                                  cn_start + len(cn_data), cn_start + len(cn_data))
    shdr1 = _anim_section_header('__types__', cn_end,
                                  cn_end, cn_end, cn_end, cn_end)
    shdr2 = _anim_section_header('__data__', data_start,
                                  local_fix_abs, global_fix_abs,
                                  virt_fix_abs, data_end)

    result = hdr + shdr0 + shdr1 + shdr2 + cn_data + data_section

    with open(filepath, 'wb') as f:
        f.write(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  FO4 skeleton writer
# ═══════════════════════════════════════════════════════════════════════════════

# Class hashes for a skeleton-only FO4 HKX (hk_2014).
# hkaSkeleton hash 0xFEC1CEDB extracted from vanilla FO4 skeleton.hkx.
_SKEL_CLASS_ENTRIES_FO4: List[Tuple[int, str]] = [
    (0x33D42383, 'hkClass'),
    (0xB0EFA719, 'hkClassMember'),
    (0x8A3609CF, 'hkClassEnum'),
    (0xCE6F8A6C, 'hkClassEnumItem'),
    (0x2772C11E, 'hkRootLevelContainer'),
    (0x26859F4C, 'hkaAnimationContainer'),
    (0xFEC1CEDB, 'hkaSkeleton'),
]


def _build_skel_classnames_fo4() -> Tuple[bytes, Dict[str, int]]:
    """Build __classnames__ section for a FO4 skeleton HKX."""
    data = b''
    name_offs: Dict[str, int] = {}
    for hash_val, name in _SKEL_CLASS_ENTRIES_FO4:
        name_offs[name] = len(data) + 5
        data += struct.pack('<IB', hash_val, 0x09) + name.encode('ascii') + b'\x00'
    data = _pad16(data, fill=0xFF)
    return data, name_offs


def _build_skel_data_section_fo4(skel: Skeleton, name_offs: Dict[str, int]) -> Tuple[bytes, '_FixupBuilder']:
    """Build the __data__ section for a FO4 skeleton HKX.

    FO4 uses hk_2014 with 64-bit pointers exclusively.
    hkaSkeleton has 7 arrays (the 7th is 'partitions', always empty).
    """
    fx = _FixupBuilder()
    data = bytearray()

    def rel():
        return len(data)

    def write(b):
        off = len(data)
        data.extend(b)
        return off

    def write_string(s: str) -> int:
        off = rel()
        data.extend(s.encode('ascii') + b'\x00')
        return off

    def align16():
        while len(data) % 16:
            data.append(0)

    def align_to(n):
        while len(data) % n:
            data.append(0)

    def write_string16(s: str) -> int:
        """TESConversion: a member string padded to 16 bytes, as vanilla FO4 packfiles lay them out."""
        off = write_string(s)
        align16()
        return off

    P = 8
    arr_sz = 16   # hkArray: ptr(8) + count(4) + cap(4)
    base_sz = 16  # hkReferencedObject: vtable(8) + memSizeAndFlags(8)

    bones = list(skel.bones)
    nbones = len(bones)
    parents = list(skel.parents) if skel.parents else [-1] * nbones
    poses = list(skel.reference_pose)
    while len(poses) < nbones:
        poses.append(BonePose())
    lock = list(skel.lock_translation) if skel.lock_translation else [False] * nbones
    skel_name = bones[0] if bones else (skel.name or "Root")
    float_slots = list(skel.float_slots)
    ref_floats = list(skel.reference_floats)
    if len(ref_floats) < len(float_slots):
        ref_floats = ref_floats + [0.0] * (len(float_slots) - len(ref_floats))

    # ═══ hkRootLevelContainer ═══
    # TESConversion: one named variant, the animation container. Vanilla skeletons carry no resource container.
    rlc_rel = rel()
    fx.add_virtual(rlc_rel, 0, name_offs['hkRootLevelContainer'])
    arr_rlc = write(_hkarray(1))
    align16()

    # NamedVariant data: 1 entry x 3 pointers
    nv_data_rel = rel()
    fx.add_local(arr_rlc, nv_data_rel)
    nv0_name = write(bytes(P)); nv0_class = write(bytes(P)); nv0_variant = write(bytes(P))

    fx.add_local(nv0_name, write_string16("Merged Animation Container"))
    fx.add_local(nv0_class, write_string16("hkaAnimationContainer"))

    # ═══ hkaAnimationContainer ═══
    ac_rel = rel()
    fx.add_virtual(ac_rel, 0, name_offs['hkaAnimationContainer'])
    fx.add_global(nv0_variant, 2, ac_rel)

    write(bytes(base_sz))              # base class
    arr_skels = write(_hkarray(1))     # skeletons
    write(_hkarray(0))                 # animations
    write(_hkarray(0))                 # bindings
    write(_hkarray(0))                 # attachments
    write(_hkarray(0))                 # skins
    align16()

    # Skeleton pointer array (1 entry)
    skel_ptr_array_rel = rel()
    fx.add_local(arr_skels, skel_ptr_array_rel)
    skel_ptr = write(bytes(P))
    align16()

    # ═══ hkaSkeleton ═══
    # Layout (hk_2014, P=8):
    #   base(16) + name(8) + parentIndices(16) + bones(16) + referencePose(16)
    #   + referenceFloats(16) + floatSlots(16) + localFrames(16) + partitions(16)
    #   = 16 + 8 + 7*16 = 136 = 0x88 bytes
    o_name = base_sz           # 0x10
    o_pi = o_name + P          # 0x18
    o_bones = o_pi + arr_sz    # 0x28
    o_pose = o_bones + arr_sz  # 0x38
    o_rfloats = o_pose + arr_sz    # 0x48
    o_fslots = o_rfloats + arr_sz  # 0x58
    o_lframes = o_fslots + arr_sz  # 0x68
    o_parts = o_lframes + arr_sz   # 0x78
    skel_struct_size = _align(o_parts + arr_sz, 16)  # 0x88 -> 0x90

    skel_obj_rel = rel()
    fx.add_virtual(skel_obj_rel, 0, name_offs['hkaSkeleton'])
    fx.add_global(skel_ptr, 2, skel_obj_rel)

    skel_buf = bytearray(skel_struct_size)
    # parentIndices count/cap
    struct.pack_into('<I', skel_buf, o_pi + P, nbones)
    struct.pack_into('<I', skel_buf, o_pi + P + 4, nbones | 0x80000000)
    # bones count/cap
    struct.pack_into('<I', skel_buf, o_bones + P, nbones)
    struct.pack_into('<I', skel_buf, o_bones + P + 4, nbones | 0x80000000)
    # referencePose count/cap
    struct.pack_into('<I', skel_buf, o_pose + P, nbones)
    struct.pack_into('<I', skel_buf, o_pose + P + 4, nbones | 0x80000000)
    # referenceFloats
    if ref_floats:
        struct.pack_into('<I', skel_buf, o_rfloats + P, len(ref_floats))
        struct.pack_into('<I', skel_buf, o_rfloats + P + 4, len(ref_floats) | 0x80000000)
    else:
        struct.pack_into('<I', skel_buf, o_rfloats + P + 4, 0x80000000)
    # floatSlots
    if float_slots:
        struct.pack_into('<I', skel_buf, o_fslots + P, len(float_slots))
        struct.pack_into('<I', skel_buf, o_fslots + P + 4, len(float_slots) | 0x80000000)
    else:
        struct.pack_into('<I', skel_buf, o_fslots + P + 4, 0x80000000)
    # localFrames empty
    struct.pack_into('<I', skel_buf, o_lframes + P + 4, 0x80000000)
    # partitions empty
    struct.pack_into('<I', skel_buf, o_parts + P + 4, 0x80000000)
    write(bytes(skel_buf))

    # TESConversion: from here every array starts 16-aligned and every member string is padded to 16, as vanilla.
    fx.add_local(skel_obj_rel + o_name, write_string16(skel_name))

    # parentIndices data (int16 array)
    pi_data_rel = rel()
    fx.add_local(skel_obj_rel + o_pi, pi_data_rel)
    for p in parents:
        write(_w_i16(p))
    align16()

    # bones array — one hkaBone per bone (0x10 bytes each: ptr(8) + lockTranslation(4) + pad(4))
    bone_stride = 0x10
    bones_data_rel = rel()
    fx.add_local(skel_obj_rel + o_bones, bones_data_rel)
    bone_struct_offsets = []
    for i in range(nbones):
        bs_rel = rel()
        bone_struct_offsets.append(bs_rel)
        write(bytes(P))                                    # name ptr (placeholder)
        write(struct.pack('<I', 1 if lock[i] else 0))      # lockTranslation
        write(bytes(bone_stride - P - 4))                  # padding

    # bone name strings (hkaBone members)
    for i in range(nbones):
        fx.add_local(bone_struct_offsets[i], write_string16(bones[i] or ""))

    # referencePose data — hkQsTransform (0x30 bytes each)
    pose_data_rel = rel()
    fx.add_local(skel_obj_rel + o_pose, pose_data_rel)
    for bp in poses:
        tx = bp.translation if bp.translation else [0.0, 0.0, 0.0]
        rq = bp.rotation if bp.rotation else [0.0, 0.0, 0.0, 1.0]
        sc = bp.scale if bp.scale else [1.0, 1.0, 1.0]
        write(struct.pack('<ffff', tx[0], tx[1], tx[2], 0.0))
        write(struct.pack('<ffff', rq[0], rq[1], rq[2], rq[3]))
        write(struct.pack('<ffff', sc[0], sc[1], sc[2], 0.0))
    align16()

    # referenceFloats / floatSlots data
    if ref_floats:
        rf_rel = rel()
        fx.add_local(skel_obj_rel + o_rfloats, rf_rel)
        for v in ref_floats:
            write(struct.pack('<f', v))
        align16()

    if float_slots:
        fs_arr_rel = rel()
        fx.add_local(skel_obj_rel + o_fslots, fs_arr_rel)
        slot_ptr_offsets = []
        for _ in float_slots:
            slot_ptr_offsets.append(rel())
            write(bytes(P))
        for i, name in enumerate(float_slots):
            fx.add_local(slot_ptr_offsets[i], write_string(name))
            align_to(2)
        align16()

    align16()
    return bytes(data), fx


def write_fo4_skeleton(filepath: str, skel: Skeleton) -> None:
    """Write a Skeleton to a FO4 binary HKX file (hk_2014, 64-bit).

    Parameters
    ----------
    filepath : str
        Output path for the .hkx file.
    skel : Skeleton
        Must have bones, parents, and reference_pose populated.
    """
    if not skel.bones:
        raise ValueError("Skeleton has no bones -- cannot export.")

    cn_data, name_offs = _build_skel_classnames_fo4()
    obj_data, fx = _build_skel_data_section_fo4(skel, name_offs)

    local_tbl = fx.build_local_table()
    global_tbl = fx.build_global_table()
    virt_tbl = fx.build_virtual_table()
    data_section = obj_data + local_tbl + global_tbl + virt_tbl

    cn_start = 0x110
    cn_end = cn_start + len(cn_data)
    data_start = cn_end

    local_fix_abs = data_start + len(obj_data)
    global_fix_abs = local_fix_abs + len(local_tbl)
    virt_fix_abs = global_fix_abs + len(global_tbl)
    data_end = virt_fix_abs + len(virt_tbl)

    cn_name_off = name_offs['hkRootLevelContainer']
    hdr = _anim_file_header(cn_name_off)

    shdr0 = _anim_section_header('__classnames__', cn_start,
                                  cn_start + len(cn_data), cn_start + len(cn_data),
                                  cn_start + len(cn_data), cn_start + len(cn_data))
    shdr1 = _anim_section_header('__types__', cn_end,
                                  cn_end, cn_end, cn_end, cn_end)
    shdr2 = _anim_section_header('__data__', data_start,
                                  local_fix_abs, global_fix_abs,
                                  virt_fix_abs, data_end)

    result = hdr + shdr0 + shdr1 + shdr2 + cn_data + data_section

    with open(filepath, 'wb') as f:
        f.write(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <animation.hkx|animation.xml>")
        sys.exit(1)

    filepath = sys.argv[1]

    print(f"Loading: {filepath}")
    print()

    anim = load_fo4_animation(filepath)
    print(anim.summary())


if __name__ == '__main__':
    main()
