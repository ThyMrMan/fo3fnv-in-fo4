"""The progress timing audit: each fact's start value, writers and prerequisites in the build against FNV's.

Phase 1 is *topic known*. FNV lists a Topic-type topic from the start when it
is Top-level, else once something AddTopics it. The build lists a topic when a
hub option of it exists, and holds it back while every such option tests an
unlock global, which scripts set through a property. Each side's prerequisites
for knowing the topic are what every one of its revealers needs; one FNV needs
and the build does not, that a line of the topic does not already need, lets
the topic show too soon, and the other way too late. Phase 2 pairs every FNV
write with the build's on the same trigger (timing_writers).

See: docs/fork/fo4_timing_audit.md#design
"""

import re
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from tools.validate.preflight.condition_diff import FO4, OR_NEXT, Names, built_conditions, built_fact, decode, source_fact
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.quest_progression import source_live
from tools.validate.preflight.timing_prereqs import common, describe, implied, missing, prerequisites, stage_reached
from tools.validate.preflight.timing_writers import (SourceWrites, Write, block_state, blocks, built_writes, expected,
                                                    inert_objectives)

#: A ledger key of a hub option: the FNV topic it offers, before any pad suffix.
_HUB_OPTION = re.compile(r'''^["']INFO prompt ([0-9A-Fa-f]{8}) .* menu hub [0-9A-Fa-f]{8} for [0-9A-Fa-f]{8}["']$''')

#: The prefix of the build's unlock globals.
UNLOCK = 'TES4Unlock_'

#: FNV DIAL type of a plain topic, and its Top-level flag.
TOPIC_TYPE, TOP_LEVEL = 0, 0x02

#: A quest stage fragment's function: its stage.
_STAGE_FRAGMENT = re.compile(r'^fragment_stage_(\d+)_')

#: A converted line script and the FNV line it holds.
_LINE_SCRIPT = re.compile(r'^\w+_tif__([0-9a-f]{8})$')

#: Facts whose loss the quest audit already reports, so a missing write of one is left to it.
QUEST_AUDIT_FACTS = ('stage', 'start')

#: Writers listed per finding.
SHOWN = 4


def hub_options(index, ledger) -> dict:
    """{FNV topic FormID: [built option FormIDs]} of the options the build lists on its hubs' topic lists."""
    own, out = len(index.masters) << 24, defaultdict(list)
    path = Path(ledger)
    for row in (line.split('\t') for line in (path.read_text(encoding='utf-8').splitlines() if path.is_file() else [])):
        match = _HUB_OPTION.match(row[2]) if len(row) == 4 else None
        fid = own | int(row[3], 16) if match else 0
        if match and getattr(index.by_fid.get(fid), 'type', '') == 'INFO':
            out[int(match.group(1), 16)].append(fid)
    return out


def unlock_gates(index, rec) -> set:
    """The unlock globals one built option requires set to 1."""
    out = set()
    for cond in built_conditions(rec):
        if FO4.name(cond['func']) == 'GetGlobalValue' and index.edid(cond['p1']).startswith(UNLOCK) \
                and (cond['type'] & 0xE0) == 0 and cond['value'] == 1.0 and not cond['type'] & OR_NEXT:
            out.add(cond['p1'])
    return out


class TopicKnown:
    """Both sides' rule for when each FNV topic is on the topic list, and what must happen before."""

    def __init__(self, ctx, names: Names, ledger, writes: SourceWrites, parts: dict):
        """Read hub options and their gates from the build, and adders from FNV's writes; `parts` is line_parts'."""
        self.ctx, self.names, self.writes, self.parts = ctx, names, writes, parts
        self.options = hub_options(ctx.index, ledger)
        self.gated = {t: set.union(*map(lambda f: unlock_gates(ctx.index, ctx.index.by_fid[f]), fids))
                      for t, fids in self.options.items()
                      if all(unlock_gates(ctx.index, ctx.index.by_fid[f]) for f in fids)}
        self.gates = defaultdict(set)
        for topic, globs in self.gated.items():
            for glob in globs:
                self.gates[glob].add(ctx.source.dials[topic][0].lower())
        self.adders = defaultdict(list)
        for write in writes.writes:
            if write.fact[0] == 'topic' and source_live(write, ctx):
                self.adders[write.fact[1]].append(write)
        self.revealers = defaultdict(list)

    def line_needs(self, fid: int) -> frozenset:
        """What FNV line `fid` needs, its quest's conditions included."""
        info = self.ctx.source.infos[fid]
        quest = [decode(d) for d in self.ctx.source.quest_conditions.get(info.quest, ())]
        conds = quest + [decode(d) for d in info.raw]
        return prerequisites(conds, lambda c: source_fact(c, self.names, {}))

    def fnv_needs(self, write: Write) -> frozenset:
        """What an FNV write's container needs before it runs; a script's guard is not read, so nothing."""
        if write.kind == 'info':
            return self.line_needs(int(write.owner, 16))
        if write.kind == 'stage':
            quest, stage = write.owner.split('|')
            return stage_reached(('form', quest.lower()), int(stage))
        return frozenset()

    def built_needs(self, script: str, function: str) -> frozenset:
        """What a build write needs: its stage, or what every first-response copy of its line needs (a later
        response plays only after the first); for another script, every record it sits on, else nothing."""
        stage = _STAGE_FRAGMENT.match(function)
        quest = self.ctx.context_quest(script)
        if stage and quest:
            return stage_reached(('form', quest), int(stage.group(1)))
        line = _LINE_SCRIPT.match(script)
        fids = self.parts.get(int(line.group(1), 16), {}).get(1, []) if line else self.ctx.index.attached.get(script, ())
        copies = [self.ctx.index.by_fid[f] for f in fids if self.ctx.index.by_fid[f].type == 'INFO']
        return common([prerequisites(built_conditions(r), lambda c: built_fact(c, self.names)) for r in copies])

    def fnv_known(self, topic: int):
        """FNV's prerequisites for knowing `topic`: none when Top-level, else what every adder needs; None if never."""
        edid, _type, flags = self.ctx.source.dials[topic]
        if flags & TOP_LEVEL:
            return frozenset()
        adders = self.adders.get(edid.lower(), [])
        return common([self.fnv_needs(w) for w in adders]) if adders else None

    def built_known(self, topic: int):
        """The build's prerequisites: none when ungated, else what every unlock write needs; None if never listed."""
        if topic not in self.options:
            return None
        if topic not in self.gated:
            return frozenset()
        reveals = self.revealers.get(self.ctx.source.dials[topic][0].lower(), [])
        return common([self.built_needs(s, f) for s, f in reveals]) if reveals else 'never'


def _topic_finding(game: str, edid: str, kind: str, gap: list, detail: tuple) -> Finding:
    """One topic-known finding: `kind` too-soon or too-late, `gap` the prerequisites one side lacks."""
    words = {'too-soon': 'can show before FNV lists it: the build does not wait for',
             'too-late': 'can show later than in FNV: the build also waits for'}[kind]
    return Finding('timing', f'timing|{game}|topic {edid}|{kind}', 'error',
                   f'topic {edid} {words} ' + ', '.join(describe(n) for n in gap), detail)


def judge_topic(known: TopicKnown, topic: int, counts: Counter) -> list:
    """The findings for one Topic-type FNV topic."""
    edid, _type, flags = known.ctx.source.dials[topic]
    fnv, built = known.fnv_known(topic), known.built_known(topic)
    fnv_rule = 'top-level' if flags & TOP_LEVEL else 'never listed' if fnv is None else 'added'
    built_rule = 'never listed' if built is None else 'gated' if topic in known.gated else 'ungated'
    counts[f'FNV {fnv_rule} / build {built_rule}'] += 1
    if built == 'never' and fnv is not None:
        return [Finding('timing', f'timing|{known.ctx.game}|topic {edid}|never', 'error',
                        f'topic {edid} is gated in the build and no script sets its unlock global', ())]
    if fnv is None or built is None:
        return []
    lines = [known.line_needs(i.fid) for i in known.ctx.source.infos.values() if i.dial == topic]
    soon = [n for n in missing(fnv, built) if any(not implied(n, line) for line in lines)]
    late = [n for n in missing(built, fnv) if any(not implied(n, line) for line in lines)]
    reveals = known.revealers.get(edid.lower(), [])
    choice = any((m := _LINE_SCRIPT.match(s)) and _is_choice(known.ctx, m.group(1).upper(), edid.lower())
                 for s, _f in reveals)
    detail = (f'FNV adders: {_sites(known.adders.get(edid.lower(), []))}',
              f'build unlock writes: {", ".join(f"{s} {f}" for s, f in reveals[:SHOWN])}') + \
        (('a build unlock comes from a Choice, so this rests on FNV rule 1',) if choice else ())
    found = ([_topic_finding(known.ctx.game, edid, 'too-soon', soon, detail)] if soon else []) + \
        ([_topic_finding(known.ctx.game, edid, 'too-late', late, detail)] if late else [])
    return [replace(f, severity='review') for f in found] if choice else found


def _sites(writes: list) -> str:
    """A short list of FNV write sites."""
    return ', '.join(f'{w.kind} {w.owner}{" " + w.part if w.part else ""}' for w in writes[:SHOWN]) or 'Top-level'


class BuildWrites:
    """Every converted script's writes, its text, and the scripts that write each topic's unlock."""

    def __init__(self, ctx, scripts_dir, gates: dict):
        """Read every converted source in `scripts_dir`."""
        self.by_script, self.texts = {}, {}
        for path in Path(scripts_dir).glob('*.psc'):
            name = path.stem.lower()
            self.texts[name] = path.read_text(encoding='utf-8', errors='replace')
            self.by_script[name] = built_writes(self.texts[name], name, ctx, gates)

    def topic_writers(self) -> dict:
        """{topic EditorID: [(script, function)]} of every unlock write."""
        out = defaultdict(list)
        for script, writes in self.by_script.items():
            for fact, function in writes:
                if fact[0] == 'topic':
                    out[fact[1]].append((script, function))
        return out


def _write_finding(game: str, write: Write, status: str, why: str, severity: str = 'error') -> Finding:
    """One writer finding: an FNV write the build lost, moved or kept only as a comment."""
    fact = ' '.join(str(p) for p in write.fact)
    where = f'{write.kind} {write.owner}{" " + write.part if write.part else ""}'
    return Finding('timing', f'timing|{game}|{where}|{fact}|{status}', severity,
                   f'{fact}: {status} ({where})', (why, f'FNV: {write.raw[:100]}'))


def judge_write(write: Write, ctx, writes: SourceWrites, built: BuildWrites, gated_topics: set):
    """A finding for one FNV write the build does not make on the same trigger, or None."""
    script = writes.script(write)
    if script not in built.texts or (write.kind == 'info' and not ctx.index.attached.get(script)):
        return None
    here = [function for fact, function in built.by_script[script] if fact == write.fact]
    scope = expected(write, ctx)
    if any(scope(f) for f in here):
        return None
    if here:
        severity = 'review' if write.part == 'menumode' else 'error'
        return _write_finding(ctx.game, write, 'moved', f'{script} makes it in {", ".join(sorted(set(here)))}', severity)
    if write.fact[0] in QUEST_AUDIT_FACTS or (write.fact[0] == 'topic' and write.fact[1] not in gated_topics):
        return None
    why = inert_objectives(built.texts[script]).get(write.fact[:3]) if write.fact[0].startswith('obj') else None
    if why is not None:
        return None if 'no such' in why else _write_finding(ctx.game, write, 'comment', f'{script}: {why}', 'review')
    return _write_finding(ctx.game, write, 'missing', f'{script} has no such write')


def _noop(fact: tuple, writes: SourceWrites) -> bool:
    """Whether a build write hides an objective, or shows one FNV never authors."""
    return fact[0] in ('objshown', 'objdone') and (not fact[3] or fact[2] not in writes.objectives.get(fact[1], ()))


def extra_writes(ctx, writes: SourceWrites, built: BuildWrites) -> list:
    """Build writes in a converted script whose FNV container never writes that fact; topic unlocks grouped by topic
    and reason (a Choice of the line, else a stage the build derived)."""
    fnv = defaultdict(set)
    for write in writes.writes:
        fnv[writes.script(write)].add(write.fact)
    out, topics = [], defaultdict(list)
    for script, (kind, owner) in writes.containers.items():
        for fact, function in built.by_script.get(script, ()):
            if fact in fnv[script] or _noop(fact, writes):
                continue
            if fact[0] == 'topic':
                why = 'choice' if kind == 'info' and _is_choice(ctx, owner, fact[1]) else kind
                topics[(fact[1], why)].append(f'{script} {function}')
                continue
            out.append(Finding('timing', f'timing|{ctx.game}|{script} {function}|{" ".join(map(str, fact))}|extra',
                               'error', f'{" ".join(map(str, fact))}: extra write in {script} {function}',
                               (f'{kind} {owner} never writes it in FNV',)))
    for (topic, why), where in sorted(topics.items()):
        words = 'it is a Choice of the line (FNV rule 1 is open)' if why == 'choice' else f'no FNV {why} adds it there'
        out.append(Finding('timing', f'timing|{ctx.game}|topic {topic}|extra unlock {why}', 'review',
                           f'topic {topic}: {len(where)} build writes unlock it where {words}', tuple(where[:SHOWN])))
    return out


def _is_choice(ctx, owner: str, topic: str) -> bool:
    """Whether FNV line `owner` lists `topic` among its Choices."""
    info = ctx.source.infos.get(int(owner, 16))
    return bool(info) and any(ctx.source.dials.get(c, ('',))[0].lower() == topic for c in info.choices)


def dropped_blocks(ctx, writes: SourceWrites, built: BuildWrites) -> list:
    """FNV script blocks with code that the build neither handles nor keeps as comments, for scripts in use."""
    out = []
    for script, (kind, owner) in writes.containers.items():
        if kind != 'script' or owner.lower() not in ctx.source.used_scripts or script not in built.texts:
            continue
        for block, code in blocks(writes.texts.get(owner.lower(), '')):
            state = block_state(block, built.texts[script]) if code else 'handler'
            if not state:
                out.append(Finding('timing', f'timing|{ctx.game}|script {owner}|{block}|dropped', 'error',
                                   f'script {owner}: its Begin {block} block is gone from {script}',
                                   ('no handler and no comment; its code never runs',)))
    return out


def audit(ctx, parts: dict, export_dir, ledger, scripts_dir) -> list:
    """The timing findings for one Fallout 4 build; prints what was compared."""
    names = Names(ctx.index, export_dir, ledger)
    writes = SourceWrites(export_dir, ctx.source, ctx.prefix)
    known = TopicKnown(ctx, names, ledger, writes, parts)
    built = BuildWrites(ctx, scripts_dir, known.gates)
    known.revealers = built.topic_writers()
    counts = Counter()
    topics = [t for t, (_e, dtype, _f) in ctx.source.dials.items() if dtype == TOPIC_TYPE]
    out = [f for t in topics for f in judge_topic(known, t, counts)]
    gated = {e for globs in known.gates.values() for e in globs}
    judged = [judge_write(w, ctx, writes, built, gated) for w in writes.writes if source_live(w, ctx)]
    out += [f for f in judged if f] + extra_writes(ctx, writes, built) + dropped_blocks(ctx, writes, built)
    print('  timing: ' + ', '.join(f'{n} {what}' for what, n in counts.most_common()))
    print(f'  timing: {len(writes.writes)} FNV writes, {sum(map(len, built.by_script.values()))} build writes')
    return out
