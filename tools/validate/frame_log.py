"""Summarize MSI Afterburner logs (.hml) per route: average fps, 1% low, median frame time, GPU load, spikes.

Usage: python tools/validate/frame_log.py LOG.hml [LOG.hml ...] [--names A B ...]
       [--segment NAME=HH:MM:SS-HH:MM:SS ...] [--gap 10] [--spike-ms 100] [--cap FPS]

See: docs/fork/fo4_plan_world_look.md#gate
"""
import argparse
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, time

#: Afterburner's line codes: a new logging session, the column names, a data row.
SESSION, COLUMNS, DATA = '00', '02', '80'
FRAMERATE, FRAMETIME = 'Framerate', 'Frametime'
#: A GPU's load column (`GPU2 usage`), not its memory columns.
GPU_USAGE = re.compile(r'GPU\d* usage')


@dataclass
class Sample:
    """One logged poll: its time, its logging session and {column: value or None}."""
    at: datetime
    session: int
    values: dict


@dataclass
class Segment:
    """A named stretch of samples the game drew frames in."""
    name: str
    samples: list = field(default_factory=list)


def read_hml(lines, session=0) -> list:
    """Samples of one .hml file's `lines`; each `00` header starts a new session, numbered from `session`."""
    samples, names = [], []
    for line in lines:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 3:
            continue
        if parts[0] == SESSION:
            session += 1
        elif parts[0] == COLUMNS:
            names = parts[2:]
        elif parts[0] == DATA and names:
            at = datetime.strptime(parts[1], '%d-%m-%Y %H:%M:%S')
            samples.append(Sample(at, session, dict(zip(names, map(_number, parts[2:])))))
    return samples


def _number(text: str):
    """A logged value as a float, None for `N/A` or blank."""
    try:
        return float(text)
    except ValueError:
        return None


def drawing(samples: list) -> list:
    """The samples with a frame rate: the game was running and in front."""
    return [s for s in samples if s.values.get(FRAMERATE) is not None]


def split(samples: list, gap: float, names: list) -> list:
    """Segments of drawing `samples`: a new one at each logging session or a pause over `gap` seconds; named
    from `names` in order, the rest `run N`."""
    runs = []
    for s in drawing(samples):
        last = runs[-1][-1] if runs else None
        if last is None or s.session != last.session or (s.at - last.at).total_seconds() > gap:
            runs.append([])
        runs[-1].append(s)
    return [Segment(names[i] if i < len(names) else f'run {i + 1}', run) for i, run in enumerate(runs)]


def windows(samples: list, specs: list) -> list:
    """Segments for `specs` (`NAME=HH:MM:SS-HH:MM:SS`): the drawing samples whose time of day falls inside."""
    out = []
    for spec in specs:
        name, span = spec.split('=', 1)
        start, end = (time.fromisoformat(t) for t in span.split('-'))
        out.append(Segment(name, [s for s in drawing(samples) if start <= s.at.time() <= end]))
    return out


def one_percent_low(rates: list) -> float:
    """The frame rate of the slowest 1% of polls (nearest rank; minimum under 100)."""
    ordered = sorted(rates)
    return ordered[max(0, math.ceil(len(ordered) / 100) - 1)]


def busiest_gpu(samples: list):
    """(column, median %) of the GPU load column with the highest median, or None."""
    gpus = {k for s in samples for k, v in s.values.items() if GPU_USAGE.fullmatch(k) and v is not None}
    medians = {k: statistics.median(s.values[k] for s in samples if s.values.get(k) is not None) for k in gpus}
    return max(sorted(medians.items()), key=lambda kv: kv[1], default=None)


def summary(seg: Segment, cap: float, spike_ms: float) -> dict:
    """Numbers for one segment: polls, start, average and 1% low fps, share at the cap, median frame time,
    the busiest GPU's median load and every poll whose frame time is over `spike_ms`."""
    rates = [s.values[FRAMERATE] for s in seg.samples]
    times = [s.values[FRAMETIME] for s in seg.samples if s.values.get(FRAMETIME) is not None]
    return {
        'name': seg.name, 'polls': len(rates), 'start': seg.samples[0].at.strftime('%H:%M:%S'),
        'avg': statistics.fmean(rates), 'low': one_percent_low(rates),
        'at_cap': sum(r >= cap - 2 for r in rates) / len(rates),
        'median_ms': statistics.median(times) if times else None, 'gpu': busiest_gpu(seg.samples),
        'spikes': [(s.at.strftime('%H:%M:%S'), s.values[FRAMETIME]) for s in seg.samples
                   if (s.values.get(FRAMETIME) or 0) > spike_ms],
    }


def cap_of(samples: list) -> float:
    """The frame cap: the most common whole frame rate among drawing `samples`."""
    return statistics.mode(round(s.values[FRAMERATE]) for s in samples)


def report(rows: list, cap: float, spike_ms: float) -> str:
    """The per-segment table, then each segment's spikes."""
    out = [f'cap {cap:g} fps; spikes: frame time over {spike_ms:g} ms',
           f'{"segment":<16}{"start":>9}{"polls":>7}{"avg fps":>9}{"1% low":>8}{"at cap":>8}{"median ms":>11}'
           f'{"GPU %":>7}{"spikes":>8}']
    for r in rows:
        median = f'{r["median_ms"]:.2f}' if r['median_ms'] is not None else '-'
        gpu = f'{r["gpu"][1]:.0f}' if r['gpu'] else '-'
        out.append(f'{r["name"]:<16}{r["start"]:>9}{r["polls"]:>7}{r["avg"]:>9.1f}{r["low"]:>8.1f}'
                   f'{r["at_cap"]:>8.0%}{median:>11}{gpu:>7}{len(r["spikes"]):>8}')
    for r in rows:
        out += [f'  {r["name"]}: {at} {ms:.0f} ms' for at, ms in r['spikes']]
    return '\n'.join(out)


def main(argv=None) -> int:
    """Read the logs, cut them into segments and print the summary."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('logs', nargs='+', help='Afterburner .hml logs, read in order')
    ap.add_argument('--names', nargs='*', default=[], help='names for the automatic segments, in order')
    ap.add_argument('--segment', action='append', default=[], help='NAME=HH:MM:SS-HH:MM:SS; replaces the split')
    ap.add_argument('--gap', type=float, default=10, help='seconds without frames that end a segment')
    ap.add_argument('--spike-ms', type=float, default=100)
    ap.add_argument('--cap', type=float, help='frame cap (default: the most common frame rate)')
    args = ap.parse_args(argv)
    samples = []
    for path in args.logs:
        with open(path, encoding='utf-8', errors='replace') as f:
            samples += read_hml(f, samples[-1].session if samples else 0)
    segments = windows(samples, args.segment) if args.segment else split(samples, args.gap, args.names)
    segments = [s for s in segments if s.samples]
    if not segments:
        print('no samples with a frame rate', file=sys.stderr)
        return 1
    cap = args.cap or cap_of([s for seg in segments for s in seg.samples])
    print(report([summary(seg, cap, args.spike_ms) for seg in segments], cap, args.spike_ms))
    return 0


if __name__ == '__main__':
    sys.exit(main())
