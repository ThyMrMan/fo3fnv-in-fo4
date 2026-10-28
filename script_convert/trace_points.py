"""Fallout 4 trace points: lines the converted scripts add so a play session can be read back.

Each point calls a TES4Polyfill `Trace*` function, which writes one
`TES4TRACE|<real time>|<kind>|...` line to the Papyrus log only while the
helper global `TES4Trace` is on (console: `set TES4Trace to 1`); off, a point
costs one call and one global read. `tools/validate/fo4_trace.py` reads the
lines back as a timeline. Every function here returns nothing for a target
other than Fallout 4.

See: docs/fork/fo4_pipeline.md#trace
"""

import re

from script_convert.target import is_fallout4

_INFO_FRAGMENT = re.compile(r'^Function (Fragment_[01])\(ObjectReference akSpeakerRef\)$')
_PACKAGE_FRAGMENT = re.compile(r'^Function (Fragment_\d+)\(Actor akActor\)$')
_PACKAGE_SUBJECT = '  ObjectReference akSpeakerRef = akActor'
#: Actor events every FO4 actor script traces: opener -> the trace line opening it.
_ACTOR_EVENTS = {'Event OnLoad()': '  TES4Polyfill.TraceLoad(Self)\n  TES4Polyfill.TraceAnimEvents(Self, Self)',
                 'Event OnAnimationEvent(ObjectReference akSource, string asEventName)':
                     '  TES4Polyfill.TraceAnim(akSource, asEventName)',
                 'Event OnDeath(Actor akKiller)': '  TES4Polyfill.TraceDeath(Self, akKiller)',
                 'Event OnPackageStart(Package akNewPackage)': '  TES4Polyfill.TracePackageStart(Self, akNewPackage)'}
#: Actor events traced only where the script has them (adding one would change nothing worth a line).
_OPENED_EVENTS = {'Event OnActivate(ObjectReference akActionRef)': '  TES4Polyfill.TraceActivate(Self, akActionRef)'}
#: INFO fragment -> the moment it marks.
_INFO_WHEN = {'Fragment_1': 'begin', 'Fragment_0': 'end'}
#: A statement giving the player an item or taking one: indent, the call, the item, then the arguments after it.
_PLAYER_ITEM = re.compile(r'^(\s*)(?:Game\.GetPlayer\(\)|PlayerREF|Player)\.(AddItem|RemoveItem)\((\w+)(\s*,\s*([^,)]*))?')


def items(lines: list) -> list:
    """`lines` with a TraceItem after each statement giving the player an item or taking one (its count, or -1)."""
    if not is_fallout4():
        return lines
    out = []
    for line in lines:
        out.append(line)
        m = _PLAYER_ITEM.match(line)
        if m:
            count = 1 if m[4] is None else int(m[5]) if m[5].strip().lstrip('-').isdigit() else -1
            verb = 'added' if m[2] == 'AddItem' else 'removed'
            out.append(f'{m[1]}TES4Polyfill.TraceItem("{verb}", {m[3]}, {count})')
    return out


def stage_suffix() -> str:
    """The stage wrapper's StageSet line suffix: the stage asked for, whether set."""
    return '\n  TES4Polyfill.TraceStage(akQuest, aiStage, TES4_StageSet)' if is_fallout4() else ''


def info(lines: list, info_id: str) -> list:
    """An INFO fragment script's lines with a TraceLine opening each fragment (begin, end)."""
    if not is_fallout4():
        return lines
    out = []
    for line in lines:
        out.append(line)
        m = _INFO_FRAGMENT.match(line)
        if m:
            out.append(f'  TES4Polyfill.TraceLine(akSpeakerRef, "{info_id}", "{_INFO_WHEN[m[1]]}")')
    return out


def package(lines: list, script: str) -> list:
    """A package fragment script's lines with a TracePackage once each fragment has its subject (past its guard)."""
    if not is_fallout4():
        return lines
    out, fragment = [], ''
    for line in lines:
        out.append(line)
        m = _PACKAGE_FRAGMENT.match(line)
        fragment = m[1] if m else fragment
        if line == _PACKAGE_SUBJECT:
            out.append(f'  TES4Polyfill.TracePackage(akActor, "{script}.{fragment}")')
    return out


def actor(lines: list, extends: str) -> list:
    """An actor script's lines with each _ACTOR_EVENTS event opened by its trace line, the event added when the
    script has none, and each _OPENED_EVENTS event it has opened by its own (an opener target.event_opener
    already traced is left as it is)."""
    if not is_fallout4() or extends != 'Actor':
        return lines
    for opener, trace in {**_ACTOR_EVENTS, **_OPENED_EVENTS}.items():
        at = next((i for i, line in enumerate(lines) if line.startswith(opener)), None)
        if at is None and opener in _OPENED_EVENTS:
            continue
        if at is None:
            lines = lines + [opener, trace, 'EndEvent', '']
        elif trace.strip() not in lines[at]:
            lines = lines[:at + 1] + [trace] + lines[at + 1:]
    return lines


def global_line(name: str, value: str) -> str:
    """Write `value` to mirror global `name` (FO4: traced, packages re-checked)."""
    return f'TES4Polyfill.SetMirror({name}, {value})' if is_fallout4() else f'{name}.SetValue({value})'


def value_line(var: str) -> str:
    """The line ending an atomic adder: the variable's new value on its owner."""
    return f'  TES4Polyfill.TraceValue(Self, "{var}", {var})'
