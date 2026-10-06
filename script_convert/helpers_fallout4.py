"""Fallout 4 versions of the shared static helper scripts.

The Fallout 4 helper set is the shared static_scripts/ with: the helpers
FO3/FNV on Fallout 4 never use left out; the converter's Fallout 4 rules
applied to the source (actor values through TES4Polyfill.AV, the update loop
as a timer, menu names); and single functions or events replaced from
static_scripts/fallout4/overrides/<Script>.psc. Each override names the
shared block it replaces and that block's SHA-1, so an edit to the shared
block stops the run instead of shipping a stale Fallout 4 copy.

See: docs/fork/fo4_spikes.md#spike-3-helpers
"""

import hashlib
import os
import re

from script_convert.constants import (FALLOUT4_ACTOR_VALUE_IDS, FALLOUT4_AV_NATIVES, FALLOUT4_EVENTS,
                                      FALLOUT4_HELPER_NATIVES, FALLOUT4_MENU_NAMES, FALLOUT4_UNUSED_HELPERS)

OVERRIDES_DIR = os.path.join(os.path.dirname(__file__), 'static_scripts', 'fallout4', 'overrides')
#: A Skyrim actor-value call and its first argument: a string, a one-argument call, or a name.
_AV_CALL = re.compile(r'\b(' + '|'.join(FALLOUT4_AV_NATIVES) + r')\(\s*("[^"]*"|\w+\(\w+\)|\w+)')
_HEADER = re.compile(r'^[ \t]*(?:[\w\[\]]+[ \t]+)?(?:Function|Event)[ \t]+([\w.]+)[ \t]*\(', re.I)
_END = re.compile(r'^[ \t]*End(?:Function|Event)\b', re.I)
_MARKER = re.compile(r'^;\s*fallout4:\s*(?:replaces\s+([\w.]+)\s+([0-9a-f]{40})|(new))\s*$', re.I)


class StaleOverride(ValueError):
    """A Fallout 4 override whose shared block changed, or that names no block."""


def is_unused(script: str) -> bool:
    """True for a shared helper FO3/FNV on Fallout 4 never use."""
    return script in FALLOUT4_UNUSED_HELPERS


def blocks(lines: list) -> dict:
    """{lower-case name: (first line, last line)} of every Function and Event."""
    out, start = {}, None
    for i, line in enumerate(lines):
        head = _HEADER.match(line)
        if head and start is None:
            start, name = i, head.group(1).lower()
        elif start is not None and _END.match(line):
            out[name] = (start, i)
            start = None
    return out


def block_hash(lines: list, span: tuple) -> str:
    """The SHA-1 a `; fallout4: replaces` marker records for one shared block."""
    return hashlib.sha1('\n'.join(lines[span[0]:span[1] + 1]).encode('utf-8')).hexdigest()


def apply_rules(text: str) -> str:
    """The converter's Fallout 4 rules on helper source; each keeps its line count."""
    text = _AV_CALL.sub(lambda m: f'{FALLOUT4_AV_NATIVES[m.group(1)]}(TES4Polyfill.AV({m.group(2)})', text)
    for old, new in list(FALLOUT4_EVENTS.items()) + list(FALLOUT4_HELPER_NATIVES.items()):
        text = text.replace(old, new)
    for old, new in FALLOUT4_MENU_NAMES.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    return text


def overrides(script: str) -> list:
    """[(replaced name or None, its SHA-1 or None, block lines)] from the script's override file."""
    path = os.path.join(OVERRIDES_DIR, script + '.psc')
    if not os.path.isfile(path):
        return []
    lines = open(path, encoding='utf-8').read().splitlines()
    out = []
    for name, (start, end) in sorted(blocks(lines).items(), key=lambda kv: kv[1]):
        marker = _MARKER.match(lines[start - 1]) if start else None
        if not marker:
            raise StaleOverride(f'{script} override {name}: no "; fallout4:" marker above it')
        out.append((marker.group(1), marker.group(2), lines[start:end + 1]))
    return out


def av_function() -> list:
    """TES4Polyfill.AV(name): the Fallout 4 actor value named `name`, generated from FALLOUT4_ACTOR_VALUE_IDS."""
    out = ['ActorValue Function AV(String asName) Global',
           '  {The Fallout 4 actor value named asName; None for one this does not know.}', '  Int id = 0']
    for i, (name, fid) in enumerate(FALLOUT4_ACTOR_VALUE_IDS.items()):
        out += [f'  {"If" if i == 0 else "ElseIf"} asName == "{name}"', f'    id = 0x{fid:X}']
    return out + ['  EndIf', '  If id == 0',
                  '    Debug.Trace("TES4Polyfill.AV: no Fallout 4 actor value named " + asName)',
                  '    Return None', '  EndIf',
                  '  Return Game.GetFormFromFile(id, "Fallout4.esm") as ActorValue', 'EndFunction']


def fallout4_helper(script: str, text: str) -> str:
    """A shared helper's source as its Fallout 4 version: the rules, then the overrides."""
    base = text.splitlines()
    spans = blocks(base)
    lines = apply_rules(text).splitlines()
    added, swaps = [], []
    for replaces, sha, block in overrides(script):
        if replaces is None:
            added += block + ['']
            continue
        span = spans.get(replaces.lower())
        if span is None or block_hash(base, span) != sha:
            current = block_hash(base, span) if span else 'missing'
            raise StaleOverride(f'{script}.{replaces}: the shared block changed (now {current}); '
                                f'update static_scripts/fallout4/overrides/{script}.psc')
        swaps.append((span, block))
    for span, block in sorted(swaps, reverse=True):
        lines[span[0]:span[1] + 1] = block
    if script == 'TES4Polyfill':
        added += av_function() + ['']
    return '\n'.join(lines + [''] + added)
