"""Read a Fallout 4 play session's trace back as a timeline, and flag what went wrong in it.

    py -3.14 -m tools.validate.fo4_trace [--log Papyrus.0.log] [--grep TEXT ...] [--kind KIND ...] [--quiet]

The converted scripts write `TES4TRACE|<real time>|<kind>|...` lines to the
Papyrus log while the helper global is on (`set TES4Trace to 1` in the
console; script_convert/trace_points.py). Kinds: stage (quest, stage asked,
set, stage after), value (owner, variable, new value), global (global, value),
line (speaker, FNV INFO, begin/end), say (speaker, topic, asked/started/not
started/dropped), package (actor, fragment, current package), death (dead,
killer), load (actor, x, y, z, loaded / 5 s later; scripted actors only), hit (target, aggressor,
source, the target's health after), pkgstart (actor, package; scripted actors only), scene (scene,
speaker, listener or None, playing; StartConversation), evaluate (nearby and the actors re-evaluated after a
mirror global changed, or scene ended, the scene, seconds waited, its actors), rep (reputation, fame, infamy,
title index), karma (change, new value), item (added/removed, item, count or -1; given to or taken from the
player by a converted script). Times are seconds from the first trace line. `--grep`
keeps lines containing any of the texts (a quest, an actor's name, an INFO id).

Flags: a SetStage that did not set; a quest's stage going back; a Say or
conversation scene that never started or was dropped as a duplicate; one line begun twice by the
same speaker within 30 s; a counter that skips or goes back; an actor
falling more than 100 units in the 5 s after it loads; the VM's
suspended-stacks warning (calls jammed behind one busy script object).

See: docs/fork/fo4_pipeline.md#trace
"""

import argparse
import collections
import os
import re
import sys
from pathlib import Path

_LINE = re.compile(r'TES4TRACE\|([-\d.]+)\|(\w+)\|(.*)$')
#: The Papyrus VM's warning that calls are piling up behind a busy script object.
_JAM = 'Count of suspended stacks is over our warning threshold'
#: Seconds within which one speaker beginning the same line again counts as said twice.
REPEAT_WINDOW = 30.0
#: Units an actor's z may drop between its load and 5 s later before it counts as fallen.
FALL = 100.0


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def default_log() -> 'Path | None':
    """Papyrus.0.log under My Games (OneDrive's Documents first, as Windows redirects it)."""
    home = Path(os.environ.get('USERPROFILE', Path.home()))
    for docs in (home / 'OneDrive' / 'Documents', home / 'Documents'):
        log = docs / 'My Games' / 'Fallout4' / 'Logs' / 'Script' / 'Papyrus.0.log'
        if log.exists():
            return log
    return None


def read(log: Path) -> list:
    """[(time, kind, [fields])] of the log's trace lines, in order; a VM stack jam takes the last trace time."""
    out = []
    for text in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = _LINE.search(text)
        if m:
            out.append((float(m[1]), m[2].lower(), m[3].split('|')))
        elif _JAM in text and out:
            out.append((out[-1][0], 'jam', ['suspended stacks over the VM threshold (stack dump follows in the log)']))
    return out


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

def stage_flags(events: list) -> list:
    """SetStages that did not set, and quests whose stage went back."""
    out, last = [], {}
    for t, kind, f in events:
        if kind != 'stage' or len(f) < 4:
            continue
        quest, asked, done, after = f[:4]
        if done == 'False':
            out.append((t, f'stage {asked} not set on {quest} (stays {after})'))
        if quest in last and _num(after) < last[quest]:
            out.append((t, f'{quest} went back from {last[quest]:g} to {after}'))
        last[quest] = _num(after)
    return out


def say_flags(events: list) -> list:
    """Says and conversation scenes that never started or were dropped, and lines one speaker began twice within
    REPEAT_WINDOW."""
    out, begun = [], {}
    for t, kind, f in events:
        if kind == 'say' and len(f) >= 3 and f[2].lower() in ('not started', 'dropped'):
            out.append((t, f'say {f[2]}: {f[0]} {f[1]}'))
        elif kind == 'scene' and len(f) >= 4 and f[3].lower() == 'false':
            out.append((t, f'scene not started: {f[0]} ({f[1]}, {f[2]})'))
        elif kind == 'line' and len(f) >= 3 and f[2].lower() == 'begin':
            key = (f[0], f[1])
            if key in begun and t - begun[key] < REPEAT_WINDOW:
                out.append((t, f'line {f[1]} begun again by {f[0]} after {t - begun[key]:.1f} s'))
            begun[key] = t
    return out


def value_flags(events: list) -> list:
    """Counters (atomic adds) that went back or skipped a step."""
    out, last = [], {}
    for t, kind, f in events:
        if kind != 'value' or len(f) < 3:
            continue
        key, value = (f[0], f[1]), _num(f[2])
        if key in last and (value < last[key] or value - last[key] > 1):
            out.append((t, f'{f[1]} on {f[0]} went {last[key]:g} -> {value:g}'))
        last[key] = value
    return out


def load_flags(events: list) -> list:
    """Actors whose z dropped more than FALL units between their load and 5 s later."""
    out, loaded = [], {}
    for t, kind, f in events:
        if kind != 'load' or len(f) < 5:
            continue
        if f[4].lower() == 'loaded':
            loaded[f[0]] = _num(f[3])
        elif f[0] in loaded and loaded[f[0]] - _num(f[3]) > FALL:
            out.append((t, f'{f[0]} fell {loaded[f[0]] - _num(f[3]):.0f} units after loading (z {f[3]})'))
    return out


def _num(text: str) -> float:
    """A trace field as a number; 0 when it is not one."""
    try:
        return float(text)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def collapsed(flags: list) -> list:
    """[(first time, last time, text, count)] of the time-sorted flags, a run of one text as one entry."""
    out = []
    for t, text in flags:
        if out and out[-1][2] == text:
            out[-1] = (out[-1][0], t, text, out[-1][3] + 1)
        else:
            out.append((t, t, text, 1))
    return out


def timeline(events: list, start: float) -> None:
    """Print each event: seconds from `start`, kind, fields."""
    for t, kind, f in events:
        print(f'{t - start:9.2f}  {kind:8s} ' + '  '.join(f))


def main() -> int:
    """Print the trace timeline and its flags; exit 1 when anything is flagged."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--log', type=Path, default=default_log())
    ap.add_argument('--grep', nargs='*', default=[], help='keep lines containing any of these texts')
    ap.add_argument('--kind', nargs='*', default=[], help='keep only these kinds')
    ap.add_argument('--quiet', action='store_true', help='flags and counts only, no timeline')
    args = ap.parse_args()
    if args.log is None or not args.log.exists():
        print('no Papyrus log found; pass --log')
        return 2
    events = read(args.log)
    if not events:
        print(f'{args.log}: no TES4TRACE lines (is the trace on? console: set TES4Trace to 1)')
        return 2
    start = events[0][0]
    shown = [e for e in events if (not args.kind or e[1] in args.kind)
             and (not args.grep or any(g.lower() in '|'.join(e[2]).lower() for g in args.grep))]
    if not args.quiet:
        timeline(shown, start)
    print(f'\n{len(events)} trace lines, {len(shown)} shown;', dict(collections.Counter(e[1] for e in events)))
    flags = sorted(stage_flags(shown) + say_flags(shown) + value_flags(shown) + load_flags(shown)
                   + [(t, f[0]) for t, kind, f in events if kind == 'jam'])
    for first, last, text, count in collapsed(flags):
        print(f'FLAG {first - start:9.2f}  {text}' + (f'  (x{count}, until {last - start:.2f})' if count > 1 else ''))
    return 1 if flags else 0


if __name__ == '__main__':
    sys.exit(main())
