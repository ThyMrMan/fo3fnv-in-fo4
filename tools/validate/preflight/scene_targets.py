"""Scene dialogue steps against their lines' speaker and alias tests: a step whose lines can never pass.

Each way a scene starts gives its aliases a fill (forced references, StartConversation's Speaker and Listener,
a starting line's fill and ALFA); identity, list and faction tests on the speaker, an alias or a reference are
decided against it. Anything else can pass.

See: docs/fork/fo4_story_tests.md#data
"""

import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from tools.validate.preflight.condition_diff import (FO4, OPS, OR_NEXT, PLAYER_REF, REFERENCE, SUBJECT, TARGET,
                                                     USE_GLOBAL, decode)
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.fo4_dialogue import BEGIN_ON_QUEST_START
from tools.validate.preflight.plugin_index import FO4_FRAGMENT_AT, every, first, u32, vmad_scripts
from tools.validate.preflight.quest_converted import strip_papyrus_comment
from tools.validate.preflight.quest_start import aliases

#: Run-on value of a quest alias (its id is parameter 3), and the player's base.
QUEST_ALIAS, PLAYER_BASE = 5, 0x07

#: The aliases TES4Polyfill.StartConversation fills: the speaker and the listener.
SPEAKER, LISTENER = 0, 1000

#: Scene action types: Dialogue, Player Dialogue, Start Scene, Radio.
DIALOGUE, PLAYER_DIALOGUE, START_SCENE, RADIO = 0, 3, 4, 6

#: Player Dialogue topics the player says (target: DTGT) and the ones the actor answers with (target: the player).
PLAYER_TOPICS, NPC_TOPICS = ('PTOP', 'NTOP', 'NETO', 'QTOP'), ('NPOT', 'NNGT', 'NNUT', 'NQUT')

#: Functions reading one form of an actor base: {function: its NPC_ subrecord}.
BASE_FORMS = {'GetIsVoiceType': 'VTCK', 'GetIsRace': 'RNAM'}

#: Condition functions decided against a known reference.
DECIDED = frozenset({'GetIsID', 'GetIsReference', 'IsInList', 'GetInFaction'}) | frozenset(BASE_FORMS)

#: Record types of a placed reference, and of a talking base that belongs to no faction.
PLACED, TALKERS = ('ACHR', 'REFR'), ('ACTI', 'TACT')

#: TES4Polyfill calls filling the Speaker alias (and the Listener with StartConversation's third argument).
CALL = re.compile(r'TES4Polyfill\.(StartConversation|TalkerActivate)\s*\(\s*(\w+)\s*,\s*(\w+)(?:\s+as\s+\w+)?'
                  r'(?:\s*,\s*(\w+))?', re.I)
#: TES4Polyfill.ChatArrived(speaker, package, scene, listener, ...): an NPC chat's StartConversation.
CHAT_CALL = re.compile(r'TES4Polyfill\.ChatArrived\s*\(\s*(\w+)\s*,\s*\w+\s*,\s*(\w+)\s*,\s*(\w+)', re.I)

#: Papyrus block comments (`;/ ... /;`) and documentation comments (`{...}`).
BLOCK_COMMENT, DOC_COMMENT = re.compile(r';/.*?/;', re.S), re.compile(r'\{[^}]*\}')

#: The build's own static scripts (F3NV_DialoguePackage), read beside the converted ones.
STATIC_SCRIPTS = Path(__file__).resolve().parents[3] / 'script_convert' / 'static_scripts' / 'fallout4'

#: Fills followed per scene; lines listed per finding.
MAX_FILLS, SHOWN = 64, 6

#: The player as a speaker or target.
PLAYER = frozenset({PLAYER_REF})


def conditions(rec) -> list:
    """The decoded CTDAs of a built INFO, each with its parameter 3 (a quest alias id)."""
    out = []
    for data in every(rec, 'CTDA'):
        cond = decode(data)
        cond['p3'] = struct.unpack_from('<i', data, 28)[0] if len(data) >= 32 else -1
        out.append(cond)
    return out


def _step_topics(atype: int, fields: dict) -> list:
    """[(topic, speaker alias or None for the player, target alias, 'player' or None)] of one scene action."""
    alias, out = u32(fields.get('ALID', b'')), []
    if atype in (DIALOGUE, RADIO) and u32(fields.get('DATA', b'')):
        out.append((u32(fields['DATA']), alias, None))
    if atype == PLAYER_DIALOGUE:
        target = struct.unpack('<i', fields['DTGT'])[0] if len(fields.get('DTGT', b'')) == 4 else None
        out += [(u32(fields[s]), None, target) for s in PLAYER_TOPICS if u32(fields.get(s, b''))]
        out += [(u32(fields[s]), alias, 'player') for s in NPC_TOPICS if u32(fields.get(s, b''))]
    return out


def scene_steps(scene) -> tuple:
    """([(action index, topic, speaker alias, target)], [scenes its Start Scene actions start]) of one SCEN."""
    steps, started, atype, fields = [], [], None, {}
    for sub in scene.subrecords:
        if sub.type == 'ANAM':
            if atype is not None:
                steps += [(u32(fields.get('INAM', b'')), *t) for t in _step_topics(atype, fields)]
            atype, fields = (struct.unpack_from('<H', sub.data)[0], {}) if len(sub.data) >= 2 else (None, {})
        elif atype is not None:
            fields.setdefault(sub.type, sub.data)
            started += [u32(sub.data)] if atype == START_SCENE and sub.type == 'LCEP' else []
    return steps, started


class World:
    """What decides a test: placed references, quest aliases, package owners, and forms scripts may change."""

    def __init__(self, index):
        """Index placed references by base, every quest's aliases, NPC packages and runtime-changeable forms."""
        self.index, self.placed = index, defaultdict(set)
        for rec in (r for sig in PLACED for r in index.by_type[sig]):
            self.placed[u32(first(rec, 'NAME'))].add(rec.form_id)
        self.aliases = {q.form_id: aliases(q) for q in index.by_type['QUST']}
        self.leveled = {u32(d, 4) for r in index.by_type['LVLN'] for d in every(r, 'LVLO')}
        self.mutable = {t for _s, _p, t in index.object_props} | {
            u32(d) for found in self.aliases.values() for _n, subs in found for d in subs['ALFC']}
        self.packages, self.templated = defaultdict(set), defaultdict(set)
        for npc in index.by_type['NPC_']:
            for data in every(npc, 'PKID'):
                self.packages[u32(data)].add(npc.form_id)
            for data in every(npc, 'TPLT') + every(npc, 'TPTA'):
                for i in range(0, len(data) - 3, 4):
                    self.templated[u32(data, i)].add(npc.form_id)
        self._forced = {}

    def alias_name(self, quest: int, alias: int) -> str:
        """The name of `quest`'s alias `alias`, or its id."""
        return next((n for n, subs in self.aliases.get(quest, ()) if u32(subs['ALST'][0]) == alias), str(alias))

    def forced(self, quest: int) -> dict:
        """{alias id: references} of `quest`'s forced (ALFR) and unique-actor (ALUA) aliases."""
        if quest not in self._forced:
            out = {}
            for _n, subs in self.aliases.get(quest, ()):
                refs = {u32(subs['ALFR'][0])} if subs['ALFR'] else self.placed.get(u32(subs['ALUA'][0]), set()) \
                    if subs['ALUA'] else set()
                if refs:
                    out[u32(subs['ALST'][0])] = frozenset(refs)
            self._forced[quest] = out
        return self._forced[quest]

    def owners(self, package: int):
        """The placed actors that run `package` (NPCs listing it, their templated NPCs, forced aliases running it),
        or None when one may be anyone (a leveled list's actor, a script-filled alias)."""
        bases, todo = set(), list(self.packages.get(package, ()))
        while todo:
            npc = todo.pop()
            if npc not in bases:
                bases.add(npc)
                todo += self.templated.get(npc, ())
        refs = set().union(*(self.placed.get(b, set()) for b in bases))
        for found in self.aliases.values():
            for _n, subs in (a for a in found if package in {u32(d) for d in a[1]['ALPC']}):
                if not subs['ALFR']:
                    return None
                refs.add(u32(subs['ALFR'][0]))
        return frozenset(refs) if refs and not bases & self.leveled else None

    def base(self, ref: int):
        """The base of placed reference `ref` (the player's too), or None."""
        if ref == PLAYER_REF:
            return PLAYER_BASE
        rec = self.index.by_fid.get(ref)
        return u32(first(rec, 'NAME')) if rec is not None and rec.type in PLACED else None

    def own_npc(self, base: int):
        """The NPC_ record of `base` when its data is its own (no template), else None."""
        rec = self.index.by_fid.get(base)
        own = rec is not None and rec.type == 'NPC_' and not first(rec, 'TPLT') and not first(rec, 'TPTA')
        return rec if own else None

    def in_faction(self, faction: int, base: int):
        """1.0 or 0.0 for a talker or an untemplated NPC no script or alias can add to `faction`; else None."""
        if base == PLAYER_BASE or faction in self.mutable:
            return None
        if getattr(self.index.by_fid.get(base), 'type', '') in TALKERS:
            return 0.0
        npc = self.own_npc(base)
        if npc is None:
            return None
        return float(any(u32(d) == faction and struct.unpack_from('<b', d, 4)[0] >= 0 for d in every(npc, 'SNAM')))

    def base_form(self, name: str, form: int, base: int):
        """Whether untemplated NPC `base`'s voice type or race is `form`; else None."""
        npc = self.own_npc(base)
        own = u32(first(npc, BASE_FORMS[name])) if npc is not None else 0
        return float(own == form) if own and getattr(self.index.by_fid.get(own), 'type', '') != 'FLST' else None

    def fact(self, name: str, p1: int, ref: int):
        """The value function `name` reads on `ref`, or None when the records cannot tell."""
        base = self.base(ref)
        if name == 'GetIsReference':
            return float(ref == p1)
        if base is None:
            return None
        if name == 'GetIsID':
            return float(base == p1)
        if name == 'GetInFaction':
            return self.in_faction(p1, base)
        if name in BASE_FORMS:
            return self.base_form(name, p1, base)
        listed = self.index.by_fid.get(p1)
        if listed is None or listed.type != 'FLST' or p1 in self.mutable:
            return None
        forms = {u32(d) for d in every(listed, 'LNAM')}
        return float(ref in forms or base in forms)

    def decide(self, cond: dict, refs):
        """True or False when `cond` passes or fails on every reference in `refs`; None when it cannot be decided."""
        name, op = FO4.name(cond['func']), OPS.get(cond['type'] & 0xE0)
        if name not in DECIDED or not refs or op is None or cond['type'] & USE_GLOBAL:
            return None
        values = {self.fact(name, cond['p1'], ref) for ref in refs}
        if None in values:
            return None
        return any(op(v, cond['value']) for v in values)

    def failing(self, conds: list, refs_of) -> list:
        """The OR-groups of `conds` whose every test is decided false (`refs_of(cond)`: whom it runs on); [] when
        the line can pass."""
        groups, group = [], []
        for cond in conds:
            group.append(cond)
            if not cond['type'] & OR_NEXT:
                groups.append(group)
                group = []
        groups += [group] if group else []
        return [g for g in groups if all(self.decide(c, refs_of(c)) is False for c in g)]


def refs_for(cond: dict, speakers, fill: dict, target):
    """The references `cond` runs on in a step: its speaker, the fill's alias, its target or a fixed reference."""
    run = cond['run_on']
    if run == SUBJECT:
        return speakers
    if run == QUEST_ALIAS:
        return fill.get(cond['p3'])
    if run == REFERENCE:
        return frozenset({cond['ref']})
    return target if run == TARGET else None


class Sources:
    """Script sources by name, from the converted scripts and the build's static ones."""

    def __init__(self, dirs: list):
        """Index every .psc under `dirs`; a name in an earlier folder wins."""
        self.paths = {}
        for folder in reversed([Path(d) for d in dirs if d]):
            self.paths.update({p.stem.lower(): p for p in folder.glob('*.psc')})

    def code(self, name: str):
        """Script `name`'s source without comments, or None when it is not found."""
        path = self.paths.get(name)
        if path is None:
            return None
        text = BLOCK_COMMENT.sub('', path.read_text(encoding='utf-8', errors='replace'))
        return DOC_COMMENT.sub('', '\n'.join(strip_papyrus_comment(line) for line in text.splitlines()))


def argument(world: World, rec, props: dict, name: str):
    """The references a call argument names: `Self` (a placed reference), a package fragment's `akActor` (its
    owners) or a property of `rec` holding a placed reference; None when the records cannot tell."""
    key = (name or '').lower()
    if key == 'self' and rec.type in PLACED:
        return frozenset({rec.form_id})
    if key == 'akactor' and rec.type == 'PACK':
        return world.owners(rec.form_id)
    target = props.get(key)
    if isinstance(target, int) and getattr(world.index.by_fid.get(target), 'type', '') in PLACED:
        return frozenset({target})
    return None


def scene_calls(code: str) -> list:
    """[(scene, speaker, listener or None)] of `code`'s scene-starting calls."""
    out = [(m.group(2), m.group(3), m.group(4) if m.group(1).lower() == 'startconversation' else None)
           for m in CALL.finditer(code)]
    return out + [(m.group(2), m.group(1), m.group(3)) for m in CHAT_CALL.finditer(code)]


def call_fill(world: World, rec, props: dict, call: tuple) -> dict:
    """{alias: references} one scene_calls call fills; an alias it leaves alone or that cannot be told is absent."""
    speaker = argument(world, rec, props, call[1])
    listener = argument(world, rec, props, call[2]) if call[2] else None
    fill = {SPEAKER: speaker} if speaker else {}
    if listener and listener != speaker:
        fill[LISTENER] = listener
    return fill


def script_fills(world: World, sources: Sources, rec, script: str, props: dict, scenes) -> list:
    """[(scene, fill or None)] for the scenes `script` on `rec` names: one per TES4Polyfill call starting it; None
    (unknown) when the script is not found, names it in an array, or uses it any other way."""
    named = {p: v for p, v in props.items() if isinstance(v, int) and v in scenes}
    out = [(v, None) for value in props.values() if isinstance(value, list) for v in value if v in scenes]
    code = sources.code(script) if named else None
    for prop, scene in named.items():
        calls = [call for call in scene_calls(code or '') if call[0].lower() == prop]
        out += [(scene, call_fill(world, rec, props, call)) for call in calls]
        uses = len(re.findall(rf'\b{re.escape(prop)}\b', code or '', re.I)) - 1
        out += [(scene, None)] if code is None or uses > len(calls) else []
    return out


def unknown_starts(index, step_topics: set) -> set:
    """Scenes started on quest start, by a holotape, or by a line no step says."""
    out = {r.form_id for r in index.by_type['SCEN'] if u32(first(r, 'FNAM')) & BEGIN_ON_QUEST_START}
    out |= {u32(first(r, 'SNAM')) for r in index.by_type['NOTE']}
    return out | {u32(d) for r in index.by_type['INFO'] if r.parent_dial not in step_topics for d in every(r, 'TSCE')}


class Steps:
    """Every scene played under each fill it can start with, and the lines of each step that fail under it."""

    def __init__(self, index, world: World):
        """Read the scenes' steps and the lines of every topic."""
        self.index, self.world = index, world
        self.scenes = {s.form_id: (u32(first(s, 'PNAM')), *scene_steps(s)) for s in index.by_type['SCEN']}
        self.lines = defaultdict(list)
        for rec in index.by_type['INFO']:
            self.lines[rec.parent_dial].append((rec, conditions(rec)))
        self.runs, self.seen = defaultdict(list), defaultdict(set)

    def topics(self) -> set:
        """The topics scene steps say."""
        return {step[1] for _q, steps, _s in self.scenes.values() for step in steps}

    def frozen(self, scene: int, fill) -> frozenset:
        """`fill` (None: unknown) as `scene` holds it, its quest's forced aliases over it."""
        return frozenset({**(fill or {}), **self.world.forced(self.scenes[scene][0])}.items())

    def solve(self, starts: list) -> None:
        """Play each [(scene, fill)] start, and every scene a passing line or action starts from it."""
        pending = [(s, self.frozen(s, f)) for s, f in starts if s in self.scenes]
        while pending:
            scene, fill = pending.pop()
            if fill in self.seen[scene] or len(self.seen[scene]) >= MAX_FILLS:
                continue
            self.seen[scene].add(fill)
            pending += self.play(scene, dict(fill))

    def play(self, scene: int, fill: dict) -> list:
        """Judge each step of `scene` under `fill`; the [(scene, fill)] its actions and passing lines start."""
        quest, steps, started = self.scenes[scene]
        out = [(s, self.carry(quest, s, fill, None, None)) for s in started if s in self.scenes]
        for index, topic, speaker, target in steps:
            speakers = PLAYER if speaker is None else fill.get(speaker)
            targets = PLAYER if target == 'player' else fill.get(target)
            failed = {}
            for rec, conds in self.lines.get(topic, ()):
                groups = self.world.failing(conds, lambda c: refs_for(c, speakers, fill, targets))
                if groups:
                    failed[rec.form_id] = groups
                    continue
                forced = first(rec, 'ALFA')
                alias = struct.unpack('<i', forced)[0] if len(forced) == 4 else None
                out += [(u32(d), self.carry(quest, u32(d), fill, alias, speakers))
                        for d in every(rec, 'TSCE') if u32(d) in self.scenes]
            self.runs[scene, index, topic].append((fill, failed, speakers is not None))
        return out

    def carry(self, quest: int, scene: int, fill: dict, alias, speakers) -> frozenset:
        """The fill `scene` starts with from a step of `quest` under `fill`: the same quest keeps it; ALFA's `alias`
        takes the line's `speakers`."""
        out = dict(fill) if self.scenes[scene][0] == quest else {}
        if alias is not None:
            out.pop(alias, None)
            out.update({alias: speakers} if speakers else {})
        return self.frozen(scene, out)


#: Comparison operators by the top three bits of a condition type, as written.
OP_TEXT = {0x00: '==', 0x20: '!=', 0x40: '>', 0x60: '>=', 0x80: '<', 0xA0: '<='}


class Report:
    """Findings over the judged steps, each line named with its source FormID through the ledger."""

    def __init__(self, game: str, steps: Steps, parts: dict):
        """`parts`: line_parts' {source INFO: {part: [built INFOs]}}."""
        self.game, self.steps, self.index, self.world = game, steps, steps.index, steps.world
        self.source = {b: s for s, by in parts.items() for group in by.values() for b in group}
        self.counts = Counter()

    def ref(self, ref: int) -> str:
        """One reference by its EditorID or its base's."""
        base = self.world.base(ref)
        return f'{self.index.edid(ref) or (self.index.edid(base) if base else "") or "?"} {ref:08X}'

    def fill(self, quest: int, fill: dict) -> str:
        """The aliases a fill knows beyond the quest's forced ones, by name."""
        forced = self.world.forced(quest)
        return '; '.join(f'{self.world.alias_name(quest, a)} = {", ".join(sorted(map(self.ref, refs))[:3])}'
                         for a, refs in sorted(fill.items()) if forced.get(a) != refs) or 'only forced aliases known'

    def cond(self, quest: int, cond: dict) -> str:
        """One condition, readable."""
        run = cond['run_on']
        who = {SUBJECT: 'the speaker', TARGET: 'the target', REFERENCE: self.ref(cond['ref']),
               QUEST_ALIAS: f'alias {self.world.alias_name(quest, cond["p3"])}'}.get(run, f'run-on {run}')
        named = 'Player' if cond['p1'] in (PLAYER_BASE, PLAYER_REF) else self.index.edid(cond['p1']) or f'{cond["p1"]:08X}'
        return f'{FO4.name(cond["func"])} {named} on {who} {OP_TEXT.get(cond["type"] & 0xE0, "?")} {cond["value"]:g}'

    def line(self, fid: int) -> str:
        """A built INFO with its source FormID."""
        src = self.source.get(fid)
        return f'INFO {fid:08X}' + (f' (source {src:08X})' if src is not None else ' (no source line)')

    def failed(self, quest: int, fid: int, group: list) -> str:
        """Why one line fails: its failing OR-group."""
        return f'{self.line(fid)} fails ' + ' OR '.join(self.cond(quest, c) for c in group)

    def step(self, scene: int, index: int, topic: int) -> str:
        """`<scene> action <n> (topic <topic>)`."""
        return f'{self.index.edid(scene)} action {index} (topic {self.index.edid(topic) or f"{topic:08X}"})'

    def findings(self) -> list:
        """An error per step no line can pass under some fill; a review per line whose known speaker can say it
        but whose listener or alias tests fail under every fill. Lines for another speaker are only counted.
        See: docs/fork/fo4_story_tests.md#data
        """
        out = []
        for (scene, index, topic), runs in sorted(self.steps.runs.items()):
            quest, lines = self.steps.scenes[scene][0], self.steps.lines.get(topic, [])
            silent = [(fill, failed) for fill, failed, _known in runs if lines and len(failed) == len(lines)]
            if silent:
                fill, failed = silent[0]
                out.append(Finding('conditions', f'conditions|{self.game}|scene-step|{self.index.edid(scene)}|{index}',
                                   'error', f'{self.step(scene, index, topic)}: no line can pass, so the step '
                                   f'plays nothing, when {self.fill(quest, fill)}',
                                   tuple(self.failed(quest, f, g[0]) for f, g in list(failed.items())[:SHOWN])))
                continue
            known = lines and all(k for _fill, _failed, k in runs)
            never = set.intersection(*(set(failed) for _fill, failed, _k in runs)) if known else set()
            mine = {fid for fid in never if not any(other_speaker(failed[fid]) for _fill, failed, _k in runs)}
            self.counts['lines for another speaker'] += len(never - mine)
            out += [self.never(scene, index, topic, fid, runs) for fid in sorted(mine)]
        return out

    def never(self, scene: int, index: int, topic: int, fid: int, runs: list) -> Finding:
        """The review for one line its speaker can say but whose listener or alias tests fail under every fill."""
        quest, src = self.steps.scenes[scene][0], self.source.get(fid, fid)
        return Finding('conditions', f'conditions|{self.game}|scene-line|{self.index.edid(scene)}|{index}|{src:08X}',
                       'review', f'{self.step(scene, index, topic)}: {self.line(fid)} fits the speaker but never '
                       'its listener', (self.failed(quest, fid, runs[0][1][fid][0]),
                                        f'{len(runs)} fills judged, first: {self.fill(quest, runs[0][0])}'))


def other_speaker(groups: list) -> bool:
    """Whether a line fails a speaker-only group: another speaker's line."""
    return any(all(c['run_on'] == SUBJECT for c in group) for group in groups)


def audit(game: str, index, parts: dict, script_dirs: list) -> list:
    """The scene-step findings for one Fallout 4 build; `script_dirs`: the converted .psc folders."""
    world, sources = World(index), Sources(list(script_dirs) + [STATIC_SCRIPTS])
    steps = Steps(index, world)
    starts = [(s, None) for s in unknown_starts(index, steps.topics())]
    for rec in (r for r in index.by_fid.values() if first(r, 'VMAD')):
        for script, props in vmad_scripts(first(rec, 'VMAD'), FO4_FRAGMENT_AT.get(rec.type, 0)):
            starts += script_fills(world, sources, rec, script, props, steps.scenes)
    steps.solve(starts)
    report = Report(game, steps, parts)
    out = report.findings()
    known = sum(1 for fills in steps.seen.values() for fill in fills if dict(fill).get(SPEAKER))
    print(f'  scene targets: {len(steps.seen)} scenes played under {sum(map(len, steps.seen.values()))} fills '
          f'({known} with a known speaker), {len(steps.runs)} steps judged, '
          f'{report.counts["lines for another speaker"]} lines only another speaker says')
    return out
