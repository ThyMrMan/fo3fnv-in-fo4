#!/usr/bin/env python3
"""Explain a play-test session: the flight recorder's events against the source game's data.

The recorder logs what the engine did; the source export holds what the
original game set up to happen. This report puts the two side by side, so a
deviation shows without knowing the game by heart:

- quests: each stage reached, its journal text, and the stages and quests its
  result scripts set going that never followed;
- packages: actors that ran nothing but the last (fallback) package of their
  source list, or a package their source never gave them;
- dialogue: each conversation's lines, with a line repeated in one talk or a
  return to the greeting flagged;
- marks (the TES4DebugMark key): where the player stood, what the crosshair
  was on with its source record, and each actor nearby with the package it ran
  against the source packages whose schedule fits the hour.

    python tools/live/session_report.py --game Fallout3 [--run 1] [--out report.md]

See: docs/commentary/tools_live_session_report.md
"""

import argparse
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tes5_import.base.text_reader import parse_export_file
from tes5_import.generated.ctda_fnv_remap import FNV_FUNC_ABSENT, FNV_FUNC_REMAP
from tools.live.flight_log import Namer, Plugin, event_ids, events_path, read_events, render

#: Source game -> (export folder, converted plugin).
GAMES = {
    'Fallout3': ('export/Fallout3.esm', 'output/Fallout3.esm/Fallout3.esm'),
    'FalloutNV': ('export/FalloutNV.esm', 'output/FalloutNV.esm/FalloutNV.esm'),
    'Oblivion': ('export/Oblivion.esm', 'output/Oblivion.esm/Oblivion.esm'),
}

#: Export files never searched for a form: big, and holding nothing a report names.
_SKIP_SCAN = {'LAND', 'NAVM', 'NAVI', 'PGRE', 'textures_used', 'overlay_diffuses', '_HEADER'}

#: The player's fixed ids, which the export holds no record for.
_PLAYER = {0x14: 'player', 0x07: 'PlayerBase'}

#: CTDA comparison operators by the type byte's top three bits.
_OPS = ('==', '!=', '>', '>=', '<', '<=')

#: CTDA Run On values.
_RUN_ON = ('', 'target.', 'ref.', 'combattarget.', 'linkedref.')

#: FO3/FNV/Oblivion package types (PKDT.Type).
_PACK_TYPES = ('Find', 'Follow', 'Escort', 'Eat', 'Sleep', 'Wander', 'Travel', 'Accompany', 'UseItemAt',
               'Ambush', 'FleeNotCombat', 'Type11', 'Sandbox', 'Patrol', 'Guard', 'Dialogue', 'UseWeapon')

#: Where a session's Papyrus errors and quest stops are triaged; this report does not repeat them.
_TRIAGE_NOTE = ('Papyrus errors and where each quest stopped: '
                'python -m tools.validate.preflight --game <Game>.esm --audit logs')

#: Seconds of silence that end a conversation.
_TALK_GAP = 20.0

#: Seconds of events shown before a mark.
_MARK_CONTEXT = 60.0

#: How close (units) an actor must be for a mark to list its schedule candidates.
_MARK_DETAIL_RANGE = 2000.0


# ----------------------------------------------------------------------------
# source data
# ----------------------------------------------------------------------------


def _function_table() -> dict:
    """Skyrim CTDA index -> (function name, [whether each parameter is a form]), from the engine's own table."""
    path = ROOT / 'tes5_import' / 'generated' / 'dialog_engine_tables.json'
    tables = json.loads(path.read_text(encoding='utf-8'))
    return {f['ctda_index']: (f['name'], [bool(p.get('is_formid')) for p in f.get('params', [])])
            for f in tables['functions'] if f.get('ctda_index') is not None}


class Source:
    """The source game's export: records by type and FormID, EditorIDs, on demand."""

    def __init__(self, export_dir: Path, fallout: bool):
        """Index nothing yet; each type is parsed the first time it is asked for."""
        self.dir = Path(export_dir)
        self.fallout = fallout
        self._types = {}
        self._edids = None
        self._funcs = None

    def records(self, sig: str) -> dict:
        """FormID (8-hex text) -> record, for one exported type."""
        if sig not in self._types:
            path = self.dir / f'{sig}.txt'
            recs = parse_export_file(str(path)) if path.exists() else []
            self._types[sig] = {r['FormID']: r for r in recs}
        return self._types[sig]

    def record(self, fid: int, *sigs) -> dict:
        """The record `fid` among the given types, or {}."""
        key = f'{fid:08X}'
        for sig in sigs:
            rec = self.records(sig).get(key)
            if rec:
                return rec
        return {}

    def edid(self, fid: int) -> str:
        """The source EditorID of `fid`, '' when it has none or is not a source record."""
        if self._edids is None:
            self._edids = {}
            pattern = re.compile(r'FormID=([0-9A-F]{8})\r?\nEditorID=([^\r\n]*)')
            for path in self.dir.glob('*.txt'):
                if path.stem in _SKIP_SCAN:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
                self._edids.update((int(a, 16), b) for a, b in pattern.findall(text))
        return self._edids.get(fid, '')

    def find(self, fid: int) -> dict:
        """The record `fid` in whichever export file holds it, or {}."""
        needle = f'FormID={fid:08X}\n'.encode()
        for path in sorted(self.dir.glob('*.txt'), key=lambda p: p.stat().st_size):
            if path.stem in _SKIP_SCAN:
                continue
            data = path.read_bytes()
            at = data.find(needle)
            if at < 0:
                at = data.find(needle.replace(b'\n', b'\r\n'))
            if at >= 0:
                return self.records(path.stem).get(f'{fid:08X}', {})
        return {}

    def name(self, fid: int) -> str:
        """`EDID` or the bare id, for a source FormID."""
        return self.edid(fid) or f'{fid:08X}'

    def function(self, index: int) -> tuple:
        """(name, [parameter is a form]) of a condition function, from its source index."""
        if self._funcs is None:
            self._funcs = _function_table()
        if self.fallout:
            if index in FNV_FUNC_ABSENT:
                return f'func{index}', []
            index = FNV_FUNC_REMAP.get(index, index)
        return self._funcs.get(index, (f'func{index}', []))

    def condition(self, raw_hex: str, stages: dict = None) -> str:
        """One CTDA as `[ref.]Function Param op value`, with this session's stage of a named quest."""
        raw = bytes.fromhex(raw_hex)
        if len(raw) < 20:
            return f'<{raw_hex}>'
        kind = raw[0]
        value = struct.unpack_from('<f', raw, 4)[0]
        func = struct.unpack_from('<H', raw, 8)[0]
        p1, p2 = struct.unpack_from('<II', raw, 12)
        run_on = struct.unpack_from('<I', raw, 20)[0] if len(raw) >= 28 else 0
        ref = struct.unpack_from('<I', raw, 24)[0] if len(raw) >= 28 else 0
        if kind & 0x04:
            shown = self.name(struct.unpack_from('<I', raw, 4)[0])
        else:
            shown = f'{value:g}'
        subject = _RUN_ON[run_on] if run_on < len(_RUN_ON) else f'runon{run_on}.'
        if run_on == 2 and ref:
            subject = f"{_PLAYER.get(ref) or self.name(ref)}."
        name, forms = self.function(func)
        forms = forms + [False] * (2 - len(forms))
        params = [self._param(p, forms[k]) for k, p in enumerate((p1, p2)) if p or forms[k]]
        text = f"{subject}{name} {' '.join(params)} {_OPS[kind >> 5 & 7] if kind >> 5 < 6 else '?'} {shown}"
        text = re.sub(r'\s+', ' ', text)
        if stages and func in (58, 59) and p1 in stages:
            text += f' (this session: {self.name(p1)} reached {max(stages[p1])})'
        if kind & 0x01:
            text += ' OR'
        return text

    def _param(self, value: int, form: bool) -> str:
        """A form parameter as its source EditorID; any other as its number."""
        if form:
            return _PLAYER.get(value) or self.edid(value) or f'{value:08X}'
        return str(value)


def package_summary(src: Source, pack: dict) -> str:
    """`EDID Type @location sched`."""
    ptype = int(pack.get('PKDT.Type', -1))
    kind = _PACK_TYPES[ptype] if 0 <= ptype < len(_PACK_TYPES) else f'type{ptype}'
    loc = pack.get('PLDT.Location')
    where = f" @{src.name(int(loc, 16))}" if loc and loc.strip('0') and len(loc) == 8 else ''
    return f"{pack.get('EditorID', pack.get('FormID'))} {kind}{where} {schedule_text(pack)}"


def schedule_text(pack: dict) -> str:
    """A package's schedule: `any time` or `08:00+4h`, with day and month limits."""
    time = int(pack.get('PSDT.Time', -1) or -1)
    dur = int(pack.get('PSDT.Duration', 0) or 0)
    text = 'any time' if time < 0 else f'{time:02d}:00+{dur}h'
    day, month = int(pack.get('PSDT.DayOfWeek', -1) or -1), int(pack.get('PSDT.Month', -1) or -1)
    if day >= 0:
        text += f' day{day}'
    if month >= 0:
        text += f' month{month}'
    return text


def schedule_fits(pack: dict, hour: float) -> bool:
    """Whether the package's daily window holds `hour` (day and month limits are not checked)."""
    time = int(pack.get('PSDT.Time', -1) or -1)
    if time < 0:
        return True
    dur = int(pack.get('PSDT.Duration', 0) or 0)
    return dur <= 0 or (hour - time) % 24 < dur


def package_list(src: Source, base: int) -> list:
    """The source NPC or creature's package FormIDs, in order."""
    rec = src.record(base, 'NPC_', 'CREA')
    return [int(rec[f'AIPackage[{i}]'], 16) for i in range(int(rec.get('AIPackageCount', 0) or 0))]


def conditions(src: Source, rec: dict, prefix: str = '', stages: dict = None) -> list:
    """Every condition of a record (or of the sub-block `prefix`) as text."""
    count = int(rec.get(f'{prefix}ConditionCount', 0) or 0)
    return [src.condition(rec[f'{prefix}Condition[{i}].Raw'], stages) for i in range(count)
            if rec.get(f'{prefix}Condition[{i}].Raw')]


# ----------------------------------------------------------------------------
# session
# ----------------------------------------------------------------------------


def seconds(ev: dict) -> float:
    """An event's time since the recorder started, in seconds."""
    return ev.get('ms', 0) / 1000.0


class Session:
    """One recorder run, with the converted plugin to name it and the source to judge it."""

    def __init__(self, events: list, plugin: Plugin, src: Source):
        """Detect the plugin's load-order prefix and keep the namer."""
        self.events = events
        self.plugin = plugin
        self.src = src
        plugin.detect_prefix(event_ids(events))
        self.namer = Namer([plugin])
        self.stages = defaultdict(list)
        for ev in events:
            if ev.get('ev') == 'quest_stage' and self.source_id(ev['quest']) is not None:
                self.stages[self.source_id(ev['quest'])].append(ev['stage'])

    def source_id(self, runtime) -> 'int | None':
        """The source FormID of a runtime id from the converted plugin, else None."""
        if runtime is None:
            return None
        value = int(runtime, 16) if isinstance(runtime, str) else runtime
        local = self.plugin.local_id(value & 0xFFFFFFFF)
        return None if local is None else local & 0xFFFFFF

    def name(self, runtime) -> str:
        """A runtime id as the converted plugin's name for it."""
        if runtime in (None, 0, '0'):
            return 'none'
        value = int(runtime, 16) if isinstance(runtime, str) else runtime
        return self.namer.name(value & 0xFFFFFFFF)

    def ours(self, runtime) -> bool:
        """Whether a runtime id belongs to the converted plugin."""
        return self.source_id(runtime) is not None


def _add_cell(out: list, t: str, label: str) -> None:
    """Add a loaded cell to the line of its second (a load attaches cells in a burst); unnamed ones are counted."""
    named = not label.startswith('[')
    if out and out[-1].startswith(f'- {t[:8]}') and ' cells' in out[-1]:
        out[-1] += f', {label}' if named else ' +1'
    else:
        out.append(f"- {t} cells {label if named else '+1'}")


def section_overview(s: Session, out: list) -> None:
    """Loads, saves and the cells entered, in order."""
    out.append('## Session\n')
    for ev in s.events:
        kind = ev.get('ev')
        if kind in ('session', 'loading', 'load_game', 'new_game', 'saved'):
            extra = ev.get('save', '')
            out.append(f"- {ev['t']} {kind} {extra}".rstrip())
        elif kind == 'cell_loaded':
            _add_cell(out, ev['t'], s.name(ev.get('cell')))
        elif kind == 'location':
            out.append(f"- {ev['t']} location {s.name(ev.get('from'))} -> {s.name(ev.get('to'))}")
    out.append('')


def _follow_ups(script: str) -> list:
    """(kind, quest EditorID, stage or None, conditional) for each SetStage/StartQuest in a result script."""
    found, depth = [], 0
    for line in script.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', ' ').split('\n'):
        code = line.split(';', 1)[0].strip()
        low = code.lower()
        if re.match(r'(else)?if\b', low):
            depth += 1 if low.startswith('if') else 0
            continue
        if low.startswith('endif'):
            depth = max(0, depth - 1)
            continue
        m = re.match(r'(?:\w+\.)?setstage\s+(\w+)\s+(\d+)', low)
        if m:
            found.append(('stage', m.group(1), int(m.group(2)), depth > 0))
        m = re.match(r'(?:\w+\.)?startquest\s+(\w+)', low)
        if m:
            found.append(('start', m.group(1), None, depth > 0))
    return found


def _quest_events_after(s: Session, i: int) -> tuple:
    """({(quest EditorID, stage)} set, {quest EditorID} started) by this plugin's events after index `i`."""
    stages, started = set(), set()
    for ev in s.events[i + 1:]:
        sid = s.source_id(ev.get('quest')) if ev.get('ev') in ('quest_stage', 'quest_init') else None
        if sid is None:
            continue
        if ev['ev'] == 'quest_stage':
            stages.add((s.src.edid(sid).lower(), ev['stage']))
        else:
            started.add(s.src.edid(sid).lower())
    return stages, started


def _stage_lines(s: Session, quest: dict, stage: int, i: int) -> list:
    """A reached stage's journal text, and each SetStage/StartQuest its result scripts name that never followed."""
    stages, started = _quest_events_after(s, i)
    lines = []
    for prefix in _stage_logs(quest, stage):
        text = quest.get(f'{prefix}Text')
        if text:
            lines.append(f'  - journal: "{text[:160]}"')
        conds = conditions(s.src, quest, prefix, s.stages)
        for kind, target, step, nested in _follow_ups(quest.get(f'{prefix}ResultScript', '')):
            if ((target, step) in stages) if kind == 'stage' else (target in started):
                continue
            what = f'SetStage {target} {step}' if kind == 'stage' else f'StartQuest {target}'
            why = (['entry conditioned on ' + '; '.join(conds)] if conds else []) + (['inside an If'] if nested else [])
            note = f" ({', '.join(why)})" if why else ''
            lines.append(f"  - {'' if why else '⚠ '}expected {what}, not seen after it{note}")
    return lines


def section_quests(s: Session, out: list) -> None:
    """Each quest start and stage reached, with its journal text and unmet follow-ups."""
    out.append('## Quests\n')
    rows = 0
    for i, ev in enumerate(s.events):
        sid = s.source_id(ev.get('quest')) if ev.get('ev') in ('quest_stage', 'quest_init') else None
        if sid is None:
            continue
        rows += 1
        if ev['ev'] == 'quest_init':
            out.append(f"- {ev['t']} **{s.src.name(sid)}** started")
            continue
        out.append(f"- {ev['t']} **{s.src.name(sid)}** stage {ev['stage']}")
        out.extend(_stage_lines(s, s.src.record(sid, 'QUST'), ev['stage'], i))
    if not rows:
        out.append('- no quest events from this plugin')
    out.append('')


def _stage_logs(quest: dict, stage: int) -> list:
    """Key prefixes (`Stage[i].Log[j].`) of every log entry of `stage`."""
    found = []
    for i in range(int(quest.get('StageCount', 0) or 0)):
        if int(quest.get(f'Stage[{i}].Index', -1)) != stage:
            continue
        for j in range(int(quest.get(f'Stage[{i}].LogCount', 0) or 0)):
            found.append(f'Stage[{i}].Log[{j}].')
    return found


def _met(s: Session) -> set:
    """Runtime ids of the actors the player talked with or caught near a mark."""
    met = {ev.get('speaker') for ev in s.events if ev.get('ev') == 'topic_info'}
    for mark in parse_marks(s.events):
        met.update(_hex(a['ref']) for a in mark['actors'] if float(a.get('dist', 0)) <= _MARK_DETAIL_RANGE)
    return met


def _always(s: Session, source: list, upto: int) -> list:
    """Names of the packages listed before index `upto` with no conditions and an any-time schedule."""
    found = []
    for fid in source[:upto]:
        pack = s.src.record(fid, 'PACK')
        if pack and not int(pack.get('ConditionCount', 0) or 0) and int(pack.get('PSDT.Time', -1) or -1) < 0:
            found.append(s.src.name(fid))
    return found


def _ahead(s: Session, source: list, upto: int, limit: int = 10) -> list:
    """The packages listed before index `upto`, each with its schedule and conditions."""
    lines = []
    for k, fid in enumerate(source[:upto][:limit]):
        pack = s.src.record(fid, 'PACK')
        if pack:
            why = '; '.join(conditions(s.src, pack, '', s.stages)) or 'no conditions'
            lines.append(f'  - ahead of it: #{k + 1} {package_summary(s.src, pack)} -- {why}')
    if upto > limit:
        lines.append(f'  - ... {upto - limit} more ahead of it')
    return lines


def _packages_run(s: Session) -> tuple:
    """({actor: [package runtime ids, first-run order]}, {actor: base}) for this plugin's actors."""
    ran, bases = defaultdict(list), {}
    for ev in s.events:
        if ev.get('ev') != 'package' or ev.get('phase') not in ('start', 'change') or not s.ours(ev.get('actor_base')):
            continue
        if ev.get('package') not in ran[ev['actor']]:
            ran[ev['actor']].append(ev.get('package'))
        bases[ev['actor']] = ev['actor_base']
    return ran, bases


def _judge_actor(s: Session, actor: str, packs: list, base: int, met: bool) -> tuple:
    """([certainly wrong lines], met-actor block or None, whether it quietly ran only its last package)."""
    source = package_list(s.src, base)
    if not source:
        return [], None, False
    ids = [s.source_id(p) for p in packs if s.ours(p)]
    listed = [i for i in ids if i in source]
    head = f'- **{s.name(actor)}** ({s.src.name(base)}, {len(source)} source packages)'
    certain = []
    for i in listed:
        always = _always(s, source, source.index(i))
        if always:
            certain.append(f"{head}: ran #{source.index(i) + 1} {s.src.name(i)} although "
                           f"{', '.join(always)} comes first and always applies")
    foreign = sorted({s.src.name(i) for i in ids if i not in source})
    if foreign:
        certain.append(f"{head}: ran packages not in its source list: {', '.join(foreign)}")
    if met and ids:
        ran_text = ', '.join(f'#{source.index(i) + 1} {s.src.name(i)}' for i in listed) or 'none of its own'
        first = min(source.index(i) for i in listed) if listed else len(source)
        return certain, '\n'.join([f'{head}: ran {ran_text}'] + _ahead(s, source, first)), False
    return certain, None, len(source) > 1 and bool(listed) and set(listed) == {source[-1]}


def section_packages(s: Session, out: list) -> None:
    """Packages against the source lists: certain misses first, then the actors the player met.

    FO3/FNV/Oblivion run the first listed package whose schedule and
    conditions hold. A package run while an earlier one has neither is
    certainly wrong. An actor that ran only its list's last package is shown
    only when the player met it: a default is often the right package.
    """
    out.append('## Packages\n')
    ran, bases = _packages_run(s)
    met = _met(s)
    certain, looks, quiet = [], [], 0
    for actor, packs in ran.items():
        wrong, look, fallback = _judge_actor(s, actor, packs, s.source_id(bases[actor]), actor in met)
        certain += wrong
        looks += [look] if look else []
        quiet += fallback
    out.append("**Certainly wrong** (an earlier package always applies, or the package is not the actor's):\n")
    out.extend(certain or ['- none'])
    out.append('\n**Actors you met**, with the packages listed ahead of what they ran:\n')
    out.extend(looks or ['- none'])
    out.append(f"\n{len(ran)} of this plugin's actors ran packages; {quiet} others ran only their last-listed "
               'package, which is often the intended default.\n')


def conversations(s: Session) -> list:
    """Each speaker's lines split into talks at a silence over _TALK_GAP: [{'speaker', 'start', 'lines'}]."""
    talks, last = [], {}
    for ev in s.events:
        if ev.get('ev') != 'topic_info' or ev.get('phase') != 'begin':
            continue
        talk = last.get(ev.get('speaker'))
        if talk is None or seconds(ev) - talk['end'] > _TALK_GAP:
            talk = {'speaker': ev.get('speaker'), 'start': ev['t'], 'lines': []}
            talks.append(talk)
            last[ev.get('speaker')] = talk
        talk['end'] = seconds(ev)
        talk['lines'].append(ev.get('info'))
    return talks


def _talk_lines(s: Session, talk: dict) -> list:
    """One talk: a single line, one topic's chatter, or every line with repeats and greeting returns flagged."""
    lines, who = talk['lines'], s.name(talk['speaker'])
    topics = {s.name(i).split(':', 1)[0] for i in lines}
    if len(lines) == 1:
        return [f"- {talk['start']} {who}: {s.name(lines[0])}"]
    if len(topics) == 1:
        return [f"- {talk['start']} {who}: {len(lines)} lines of {topics.pop()}"]
    out = [f"- {talk['start']} **{who}**, {len(lines)} lines"]
    count, flagged, spoken_other = Counter(lines), set(), False
    for info in lines:
        label = s.name(info)
        flags = []
        if count[info] > 1 and info not in flagged:
            flags.append(f'⚠ said {count[info]}x in this talk')
            flagged.add(info)
        greeting = label.upper().startswith('GREETING')
        if greeting and spoken_other:
            flags.append('⚠ back to a greeting')
        spoken_other = spoken_other or not greeting
        out.append(f"  - {label}{'  ' + ', '.join(flags) if flags else ''}")
    return out


def section_dialogue(s: Session, out: list) -> None:
    """Each conversation's lines, with repeats and returns to the greeting flagged."""
    out.append('## Dialogue\n')
    talks = conversations(s)
    for talk in talks:
        out.extend(_talk_lines(s, talk))
    out.append('' if talks else '- no dialogue recorded\n')


# ----------------------------------------------------------------------------
# marks
# ----------------------------------------------------------------------------


def _hex(value: str) -> str:
    """A Papyrus-printed form id (decimal, maybe negative) as 8-hex text."""
    return f'{int(float(value)) & 0xFFFFFFFF:08X}'


def _mark_line(ev: dict):
    """(mark number, line kind, {field: value}) of a `mark` event, or None."""
    parts = ev.get('text', '').split() if ev.get('ev') == 'mark' else []
    if len(parts) < 2:
        return None
    return parts[0], parts[1], dict(p.split('=', 1) for p in parts[2:] if '=' in p)


def parse_marks(events: list) -> list:
    """Each mark as {'n', 't', 'ms', 'player', 'aim', 'actors', 'index'} in log order."""
    marks, current = [], None
    for i, ev in enumerate(events):
        line = _mark_line(ev)
        if line is None:
            continue
        n, kind, fields = line
        if kind == 'player':
            current = {'n': n, 't': ev['t'], 'ms': ev.get('ms', 0), 'index': i,
                       'player': fields, 'aim': None, 'actors': []}
            marks.append(current)
            continue
        if current is None or current['n'] != n:
            continue
        if kind == 'aim':
            current['aim'] = fields
        if kind == 'actor':
            current['actors'].append(fields)
        if kind == 'end':
            current = None
    return marks


def _actor_state(a: dict) -> str:
    """A mark's actor flags as words: dead, disabled, combat, talking, AI off, sit state."""
    state = [k for k in ('dead', 'disabled', 'combat', 'talking') if a.get(k) == '1']
    if a.get('ai') == '0':
        state.append('AI off')
    if a.get('sit', '0') not in ('0', ''):
        state.append(f"sit{a['sit']}")
    return ' '.join(state)


def _list_place(source: list, pack_src) -> tuple:
    """(index of the running package in the source list, or its length; how to describe that place)."""
    if pack_src in source:
        at = source.index(pack_src)
        last = at == len(source) - 1 and len(source) > 1
        return at, f"#{at + 1} of {len(source)}{', the last (fallback)' if last else ''}"
    return len(source), 'not in its source list' if pack_src is not None else 'a Skyrim package'


def _actor_line(s: Session, a: dict, hour: float) -> list:
    """One actor of a mark: state, package against its source list, and earlier packages that fit the hour."""
    ref, base, package = _hex(a['ref']), _hex(a['base']), _hex(a.get('package', '0'))
    dist = float(a.get('dist', 0))
    lines = [f"- **{s.name(ref)}** {dist:.0f}u {_actor_state(a)}".rstrip()]
    base_src = s.source_id(base)
    source = package_list(s.src, base_src) if base_src is not None else []
    if not source:
        return lines + [f'  - running {s.name(package)}']
    at, where = _list_place(source, s.source_id(package))
    lines.append(f'  - running {s.name(package)} ({where})')
    if dist > _MARK_DETAIL_RANGE and a.get('talking') != '1':
        return lines
    for i, fid in enumerate(source[:at]):
        pack = s.src.record(fid, 'PACK')
        if not pack or not schedule_fits(pack, hour):
            continue
        conds = conditions(s.src, pack, '', s.stages)
        why = '; '.join(conds) if conds else 'no conditions'
        lines.append(f"  - {'' if conds else '⚠ '}ahead of it, fits the hour: #{i + 1} "
                     f'{package_summary(s.src, pack)} -- {why}')
    return lines


def _aim_lines(s: Session, aim: dict) -> list:
    """The crosshair's ref, its converted base, and the source record behind it."""
    ref, base = _hex(aim['ref']), _hex(aim['base'])
    lines = [f"- aim: {s.name(ref)} base {s.name(base)} at {aim.get('pos')} "
             f"dist {float(aim.get('dist', 0)):.0f}u{' (disabled)' if aim.get('disabled') == '1' else ''}"]
    for label, runtime in (('ref', ref), ('base', base)):
        sid = s.source_id(runtime)
        if sid is None:
            continue
        rec = s.src.find(sid)
        if rec:
            model = rec.get('Model.MODL') or rec.get('MODL') or ''
            out_sig = s.plugin.fields(s.plugin.local_id(int(runtime, 16))).get('sig', '?')
            lines.append(f"  - source {label}: {rec.get('Signature')} {rec.get('EditorID', '')} [{sid:08X}]"
                         f" -> converted as {out_sig}{'; model ' + model if model else ''}")
        else:
            lines.append(f'  - source {label}: [{sid:08X}] is not a source record (made by the converter)')
    return lines


def _mark_context(s: Session, mark: dict, start: float) -> list:
    """The last 25 events since `start` before a mark; no line ends; packages only for its actors."""
    near = {_hex(a['ref']) for a in mark['actors']}
    recent = [e for e in s.events[:mark['index']]
              if seconds(e) >= start and e.get('ev') not in ('mark', 'papyrus', 'lock_changed')
              and (e.get('ev') != 'package' or e.get('actor') in near) and e.get('phase') != 'end']
    return recent[-25:]


def section_marks(s: Session, out: list, only: str = None) -> None:
    """Each mark: place, time, crosshair, nearby actors, and the events just before it."""
    marks = parse_marks(s.events)
    out.append('## Marks\n')
    if not marks:
        out.append('- no marks (TES4DebugMark key) in this run\n')
        return
    for k, mark in enumerate(marks, 1):
        if only and str(k) != only:
            continue
        p = mark['player']
        days = float(p.get('days', 0))
        hour = (days % 1) * 24
        out.append(f"### Mark {k}: {mark['t']} (in-game day {int(days)}, {int(hour):02d}:{int(hour % 1 * 60):02d})\n")
        where = s.name(_hex(p.get('cell', '0')))
        world = _hex(p.get('world', '0'))
        out.append(f"- player at {p.get('pos')} in {where}"
                   f"{' / ' + s.name(world) if world != '00000000' else ''}"
                   f"{', in dialogue' if p.get('dialogue') == '1' else ''}")
        if mark['aim']:
            out.extend(_aim_lines(s, mark['aim']))
        actors = sorted(mark['actors'], key=lambda a: float(a.get('dist', 0)))
        out.append(f'\nNearby actors ({len(actors)}):\n')
        for a in actors:
            out.extend(_actor_line(s, a, hour))
        out.append(f'\nEvents in the {int(_MARK_CONTEXT)} s before it:\n')
        start = mark['ms'] / 1000.0 - _MARK_CONTEXT
        for ev in _mark_context(s, mark, start):
            out.append(f'    {render(ev, s.namer, False)}')
        out.append('')


# ----------------------------------------------------------------------------
# cli
# ----------------------------------------------------------------------------


def build_report(s: Session, path: Path, mark: str = None) -> str:
    """The whole report as markdown; only that mark's section when `mark` is given."""
    out = [f'# Session report: {path.name}\n',
           f'{len(s.events)} events; converted plugin {s.plugin.path.name} at prefix '
           f"{'%02X' % s.plugin.prefix if s.plugin.prefix is not None else 'not found'}.\n"]
    if mark:
        section_marks(s, out, mark)
        return '\n'.join(out)
    section_marks(s, out)
    section_quests(s, out)
    section_packages(s, out)
    section_dialogue(s, out)
    section_overview(s, out)
    out.append(_TRIAGE_NOTE)
    return '\n'.join(out)


def main(argv=None) -> int:
    """Read one recorder run and print or write its report."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--game', required=True, choices=sorted(GAMES))
    ap.add_argument('--run', type=int, default=0, choices=(0, 1, 2), help='0 = newest run')
    ap.add_argument('--path', help='read this recorder file instead')
    ap.add_argument('--plugin', help='the converted plugin (default: output/<game>.esm/<game>.esm)')
    ap.add_argument('--export', help='the source export folder (default: export/<game>.esm)')
    ap.add_argument('--mark', help='only this mark (1 = the first in the run)')
    ap.add_argument('--out', help='write the report here instead of printing it')
    args = ap.parse_args(argv)
    export, plugin = GAMES[args.game]
    path = Path(args.path) if args.path else events_path(args.run)
    if not path.exists():
        print(f'no recorder log at {path}', file=sys.stderr)
        return 1
    src = Source(ROOT / (args.export or export), args.game != 'Oblivion')
    session = Session(read_events(path), Plugin(ROOT / (args.plugin or plugin)), src)
    text = build_report(session, path, args.mark)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
        print(f'wrote {args.out}')
    else:
        enc = sys.stdout.encoding or 'utf-8'
        print(text.encode(enc, 'replace').decode(enc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
