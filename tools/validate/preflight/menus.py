"""The dialogue menu audit, checks 1 to 3: each built XDI menu against the FNV lines it stands for.

Check 1 (structure, no state): an option's pads carry its conditions, its
answers line up with its range and are copies of its FNV topic's lines in
FNV's order, its prompt is its line's, no two FNV topics share a prompt in
one menu, a Say Once answer carries its marker script, and each answer leads
where its FNV line leads (Choices to a menu of those topics, Follow Ups to
lines, Goodbye to the end). Check 2: two options of one FNV topic in one
menu never pass together, tried over their gates' facts with the speaker's
fixed facts settled. Check 3, the same search: an option shows only while an
answer can play, an answer that can play has its topic shown, and no option
shows while a line FNV tries first passes.

See: docs/fork/fo4_menu_audit.md#built
"""

import html
import itertools
import math
import re
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.conversation import MAX_CLAUSES, speaker_index
from fo4_import.spike.records import INFO_END_SCENE, shown
from fo4_import.spike.talking_activators import LIST_PREFIX
from tools.validate.preflight.condition_diff import FO4, IDENTITY, OR_NEXT, USE_GLOBAL, built_conditions, domains, \
    evaluate
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.fo4_dialogue import line_parts
from tools.validate.preflight.plugin_index import every, first, u32
from tools.validate.preflight.xdi_menus import listed, menus

#: A ledger key of a built option or pad: `INFO prompt <FNV topic> <text> at <place> <FNV topic> for <FNV quest>`.
PROMPT_KEY = re.compile(r'''^["']INFO prompt ([0-9A-Fa-f]{8}) .* \1 for ([0-9A-Fa-f]*)(?: pad \d+)?["']$''')

#: CTDA Run On: the subject (the player, on an option) and the target (the NPC); the player's base form.
SUBJECT, TARGET, PLAYER_BASE = 0, 1, 0x7

#: The facts naming who says an option (the NPC) and who picks it (the player).
SPEAKER, PICKER = ('is', 'GetIsID', TARGET), ('is', 'GetIsID', SUBJECT)

#: FNV INFO DATA flags Goodbye and Say Once; the script a built Say Once line sets its marker with.
GOODBYE, SAY_ONCE, SAY_ONCE_SCRIPT = 0x01, 0x04, 'f3nv_sayonce'

#: Scene action types: Dialogue (DATA names its topic) and Player Dialogue (PTOP its first player topic).
DIALOGUE_ACTION, MENU_ACTION = 0, 3

#: States tried per pair before check 2 gives up on it (a review).
BUDGET = 200_000

#: Facts and examples listed per finding.
SHOWN = 8

#: Functions reading a quest, not the actor they run on: an option and its answers test them on different run-ons.
UNACTORED = frozenset({'GetStageDone', 'GetStage', 'GetQuestRunning', 'GetQuestCompleted', 'GetObjectiveCompleted',
                       'GetObjectiveDisplayed'})

#: The prefix of the global a topic's AddTopic sets: an option tests it, its answers do not (the topic is known).
UNLOCK_PREFIX = 'TES4Unlock_'

#: GetIsSex: true for exactly one of its two values (0 male, 1 female), never for neither.
SEX, SEXES = 'GetIsSex', [0, 1]


@dataclass
class Option:
    """One listed player line of a menu: its range's pads and answers, and the FNV topic and quest it offers."""

    rec: object
    topic: int
    quest: str
    pads: list = field(default_factory=list)
    answers: list = field(default_factory=list)


@dataclass
class Menu:
    """One Player Dialogue action: its name (first player topic's EditorID), place, options, and whether its
    player and NPC lines line up."""

    name: str
    place: tuple
    options: list
    aligned: bool


class Source:
    """The FNV lines and topics of an export: each line's record and position, each topic's record and the
    lines it shares."""

    def __init__(self, infos, dials):
        """Index the exported INFO and DIAL records."""
        self.lines = {int(r['FormID'], 16): r for r in infos}
        self.position = {fid: i for i, fid in enumerate(self.lines)}
        self.topics = {int(d['FormID'], 16): d for d in dials}
        self.shared = {fid: {int(d[f'SharedInfo[{i}].Info'], 16) for i in range(int(d.get('SharedInfoCount', 0) or 0))}
                       for fid, d in self.topics.items()}

    def topic_name(self, fid: int) -> str:
        """The EditorID of FNV topic `fid`, or its FormID."""
        return self.topics.get(fid, {}).get('EditorID') or f'{fid:08X}'

    def prompt(self, line: int, topic: int) -> str:
        """FNV line `line`'s prompt under `topic`, else the topic's name."""
        return self.lines[line].get('Prompt') or self.topics.get(topic, {}).get('FULL', '')

    def leads(self, line: int) -> tuple:
        """Where FNV line `line` leads: ('end',), ('line', Follow Ups), ('menu', Choices) or ('list',)."""
        rec = self.lines[line]
        if int(rec.get('DATA.Flags', 0) or 0) & GOODBYE:
            return ('end',)
        for kind, key in (('line', 'FollowUp'), ('menu', 'Choice')):
            fids = {int(rec[f'{key}[{i}]'], 16) for i in range(int(rec.get(f'{key}Count', 0) or 0))}
            if fids:
                return kind, fids
        return ('list',)


def prompt_topics(index, ledger) -> dict:
    """{built option or pad FormID: (FNV topic, FNV quest hex)} from the ledger's prompt keys."""
    own, out = len(index.masters) << 24, {}
    path = Path(ledger)
    for row in (line.split('\t') for line in (path.read_text(encoding='utf-8').splitlines() if path.is_file() else [])):
        match = PROMPT_KEY.match(row[2]) if len(row) == 4 else None
        fid = own | int(row[3], 16) if match else 0
        if match and getattr(index.by_fid.get(fid), 'type', '') == 'INFO':
            out[fid] = (int(match.group(1), 16), match.group(2).upper())
    return out


def places(index) -> dict:
    """{(scene, phase): step (scene_steps)} of every scene's actions."""
    return {(scene.form_id, phase): step for scene in index.by_type['SCEN'] for phase, step in scene_steps(scene)}


def scene_steps(scene) -> list:
    """[(phase, ('menu', first player topic) or ('line', topic))] of one scene's actions."""
    out, action, phase = [], None, 0
    for sub in scene.subrecords:
        if sub.type == 'ANAM':
            action = struct.unpack_from('<H', sub.data)[0] if len(sub.data) >= 2 else None
        elif sub.type == 'SNAM' and len(sub.data) == 4:
            phase = u32(sub.data)
        elif (sub.type, action) in (('PTOP', MENU_ACTION), ('DATA', DIALOGUE_ACTION)):
            out.append((phase, ('menu' if sub.type == 'PTOP' else 'line', u32(sub.data))))
    return out


def answer_topics(index) -> dict:
    """{first player topic: NPC topic (NPOT)} of every Player Dialogue action."""
    out = {}
    for scene in index.by_type['SCEN']:
        player = 0
        for sub in scene.subrecords:
            player = u32(sub.data) if sub.type == 'PTOP' else player
            if sub.type == 'NPOT' and player:
                out[player] = u32(sub.data)
    return out


def read_menus(index, prompts: dict) -> list:
    """Every Player Dialogue action as a Menu; an option the ledger names no FNV topic for ([Leave]) is left out."""
    by_topic, npc_topic = defaultdict(list), answer_topics(index)
    for info in index.by_type['INFO']:
        by_topic[info.parent_dial].append(info)
    out = []
    for scene, phase, topics in menus(index):
        player, npc = [i for t in topics for i in by_topic.get(t, ())], by_topic.get(npc_topic.get(topics[0]), [])
        options = []
        for i, info in enumerate(player):
            if listed(info):
                options.append(Option(info, *prompts.get(info.form_id, (0, ''))))
            elif options:
                options[-1].pads.append(info)
            if options and i < len(npc):
                options[-1].answers.append(npc[i])
        name = index.edid(topics[0]) or f'{topics[0]:08X}'
        out.append(Menu(name, (scene.form_id, phase), [o for o in options if o.topic], len(player) == len(npc)))
    return out


def edge_kind(fnv: tuple, built, offered: set) -> tuple:
    """(finding kind or '', FNV topics offered beyond FNV's Choices) of an answer leading to `built` (a place's
    step; None: the talk ends) whose menu offers `offered`, where its FNV line leads to `fnv` (Source.leads)."""
    if fnv[0] == 'end':
        return ('goes on where FNV ends' if built else '', set())
    if built is None:
        return ('' if fnv[0] == 'list' else 'ends where FNV goes on', set())
    if fnv[0] != 'list' and built[0] != fnv[0]:
        return 'next step differs', set()
    extra = offered - fnv[1] if fnv[0] == 'menu' else set()
    return ('choices differ' if extra else '', extra)


def conditions(rec) -> list:
    """The raw condition subrecords (CTDA, CIS1, CIS2) of a built INFO, in order."""
    return [(s.type, s.data) for s in rec.subrecords if s.type in ('CTDA', 'CIS1', 'CIS2')]


def fact(cond: dict) -> tuple:
    """(fact key, identity or None) of one built condition, read as the built plugin states it; a quest test's
    run-on is left out (UNACTORED)."""
    name, on = FO4.name(cond['func']), cond['run_on'] if cond['run_on'] in (SUBJECT, TARGET) else (cond['run_on'],
                                                                                                    cond['ref'])
    on = None if name in UNACTORED else on
    if name == 'GetGlobalValue':
        return ('glob', cond['p1']), None
    if name == 'GetVMQuestVariable':
        return ('qvar', cond['p1'], re.sub(r'^::|_var$', '', cond['text']).lower()), None
    if name in IDENTITY or name == SEX:
        return ('is', name, on), cond['p1']
    return (name, on, cond['p1'], cond['p2']), None


def gate(rec) -> list:
    """An option's gate as OR-chains [(fact, op, right side, OR with next)], all of which must pass."""
    chains, chain = [], []
    for cond in built_conditions(rec):
        rhs = (('glob', cond['value_fid']), None) if cond['type'] & USE_GLOBAL else cond['value']
        chain.append((fact(cond), cond['type'] & 0xE0, rhs, bool(cond['type'] & OR_NEXT)))
        if not chain[-1][3]:
            chains.append(chain)
            chain = []
    return chains + ([chain] if chain else [])


def chain_keys(chain: list) -> set:
    """The fact keys an OR-chain reads."""
    return {t[0] for term, _op, rhs, _or in chain for t in (term, rhs) if isinstance(t, tuple)}


class Speakers:
    """Built NPCs' fixed facts: voice type, factions (a faction some script changes left free) and talking-as
    lists, which scripts fill only with talking activators."""

    def __init__(self, index, unfixed: set):
        """`unfixed`: built faction FormIDs a script adds actors to or takes them from."""
        self.index, self.unfixed = index, unfixed

    def settled(self, npc, key) -> 'list | None':
        """The one value fact `key` takes while `npc` (None: another actor) speaks, or None when it is free (no
        record, a template). A talking-as list holds its LNAM actors: no other actor talks through an activator."""
        if key[:2] == ('IsInList', TARGET) and self.index.edid(key[2]).startswith(LIST_PREFIX):
            return [1.0 if npc in {u32(d) for d in every(self.index.by_fid[key[2]], 'LNAM')} else 0.0]
        rec = self.index.by_fid.get(npc) if npc else None
        if rec is None or rec.type != 'NPC_' or first(rec, 'TPLT'):
            return None
        if key[:3] == ('is', 'GetIsVoiceType', TARGET):
            return [u32(first(rec, 'VTCK'))]
        if key[:2] == ('GetInFaction', TARGET) and key[2] not in self.unfixed:
            return [1.0 if key[2] in {u32(d) for d in every(rec, 'SNAM')} else 0.0]
        return None


def unfixed_factions(index, export_dir) -> set:
    """Built FormIDs of the FNV factions scripts change, by EditorID."""
    fnv = {int(r['FormID'], 16): r.get('EditorID', '').lower() for r in export_records(export_dir, 'FACT')}
    built = {index.edid(r.form_id).lower(): r.form_id for r in index.by_type['FACT']}
    return {built[fnv[f]] for f in speaker_index(export_dir)[1] if fnv.get(f) in built}


def flipped(term):
    """A fact (or number) with its run-on turned from an answer's side to its option's: subject and target swap."""
    if not isinstance(term, tuple):
        return term
    key, identity = term
    turn = {SUBJECT: TARGET, TARGET: SUBJECT}
    if key[0] == 'is':
        return (key[0], key[1], turn.get(key[2], key[2])), identity
    if key[0] in ('glob', 'qvar') or not isinstance(key[1], int):
        return term
    return (key[0], turn.get(key[1], key[1]), *key[2:]), identity


def answer_side(chains: list) -> list:
    """An answer's OR-chains as its option reads them (NPC the target)."""
    return [[(flipped(term), op, flipped(rhs), ored) for term, op, rhs, ored in chain] for chain in chains]


def one_each_gate(answers: list) -> bool:
    """Whether `answers`' option is gated by one_each (_either past MAX_CLAUSES).
    See: docs/fork/fo4_pipeline.md#dialogue-conditions
    """
    rest = [[c for c in a if not all(c in b for b in answers)] for a in answers]
    return all(rest) and math.prod(len(r) for r in rest) > MAX_CLAUSES


def named(chains: list) -> list:
    """The NPCs `chains` name as the speaker (GetIsID on the target)."""
    return sorted({term[1] for chain in chains for term, *_ in chain if term[0] == SPEAKER and term[1] != PLAYER_BASE})


def search_plan(chains: list, only: tuple, fails: tuple) -> tuple:
    """(domains, fact order, {depth: chains to pass}, {depth: chain lists to fail}) of together()'s search: a
    chain is judged at the depth of its last fact, the speaker and picker first."""
    doms = domains([[atom for chain in [*chains, *(c for failing in fails for c in failing)] for atom in chain]])
    doms[PICKER] = [PLAYER_BASE]
    doms.update({key: SEXES for key in doms if key[:2] == ('is', SEX)})
    if SPEAKER in doms or only:
        doms[SPEAKER] = list(only) or [v for v in doms[SPEAKER] if v != PLAYER_BASE]
    order = sorted(doms, key=lambda k: (k != SPEAKER, k != PICKER))
    at = {k: i for i, k in enumerate(order)}
    ready, unless = defaultdict(list), defaultdict(list)
    for chain in chains:
        ready[max((at[k] for k in chain_keys(chain)), default=-1)].append(chain)
    for failing in fails:
        unless[max((at[k] for c in failing for k in chain_keys(c)), default=-1)].append(failing)
    return doms, order, ready, unless


def together(chains: list, speakers: Speakers, only: tuple = (), fails: tuple = ()) -> 'dict | None | str':
    """A state passing every chain in `chains` and failing each chain list in `fails` (said by one of `only` when
    given), None when none can, 'budget' when BUDGET states ran out.

    Facts are tried speaker first, so its fixed facts settle the rest.
    """
    doms, order, ready, unless = search_plan(chains, only, fails)
    state, tried = {}, [0]

    def clear(depth: int) -> bool:
        """Whether `depth`'s chains pass and none of its chain lists to fail does."""
        return all(evaluate(c, state) for c in ready[depth]) and not any(
            all(evaluate(c, state) for c in failing) for failing in unless[depth])

    def search(depth: int) -> bool:
        """Whether facts from `depth` on can take values passing every chain."""
        if depth == len(order):
            return True
        key = order[depth]
        for value in speakers.settled(state.get(SPEAKER), key) or doms[key]:
            tried[0] += 1
            if tried[0] > BUDGET:
                raise TimeoutError
            state[key] = value
            if clear(depth) and search(depth + 1):
                return True
        state.pop(key, None)
        return False
    if not clear(-1):
        return None
    try:
        return dict(state) if search(0) else None
    except (TimeoutError, RecursionError):
        return 'budget'


def fact_text(index, key, value) -> str:
    """One fact of a state, named by EditorIDs."""
    def form(fid) -> str:
        """A form's EditorID, else its FormID."""
        return index.edid(fid) or f'{fid:08X}' if isinstance(fid, int) else str(fid)
    if key[0] == 'is':
        return f'{key[1]}={form(value) if value is not None else "another"}'
    if key[0] == 'glob':
        return f'{form(key[1])}={value:g}'
    if key[0] == 'qvar':
        return f'{form(key[1])}.{key[2]}={value:g}'
    on = f'{form(key[1][1])}.' if isinstance(key[1], tuple) else ''
    return f'{on}{key[0]}({form(key[2])}{", " + str(key[3]) if key[3] else ""})={value:g}'


def describe(index, state: dict) -> str:
    """A state's facts, the speaker first."""
    rows = [fact_text(index, k, v) for k, v in sorted(state.items(), key=lambda kv: (kv[0] != SPEAKER, repr(kv[0])))
            if k != PICKER]
    return ', '.join(rows[:SHOWN]) + (' ...' if len(rows) > SHOWN else '') or 'no facts'


def text(rec) -> str:
    """An option's prompt as shown (RNAM in cp1252, unescaped)."""
    return html.unescape(first(rec, 'RNAM').split(b'\0', 1)[0].decode('cp1252', errors='replace'))


class MenuAudit:
    """Checks 1 and 2 over one built plugin's menus."""

    def __init__(self, game: str, index, source: Source, copies: dict, speakers: Speakers):
        """`copies` {built INFO: (FNV line, response part)}."""
        self.game, self.index, self.source, self.copies, self.speakers = game, index, source, copies, speakers
        self.places, self.gates, self.met = places(index), {}, {}
        self.once = set(index.attached.get(SAY_ONCE_SCRIPT, ()))
        self.split = {fnv for fnv, part in copies.values() if part > 1}
        self.found = defaultdict(list)

    def add(self, menu: Menu, topic: int, kind: str, row: str) -> None:
        """Note one example of `kind` for `topic` (0: the whole menu) in `menu`."""
        self.found[(menu.name, self.source.topic_name(topic) if topic else '*', kind)].append(row)

    def structure(self, menu: Menu, by_place: dict) -> None:
        """Check 1 on one menu."""
        if not menu.aligned:
            self.add(menu, 0, 'answers misaligned', 'its player and NPC topics hold different counts')
        for option in menu.options:
            for pad in option.pads:
                if conditions(pad) != conditions(option.rec):
                    self.add(menu, option.topic, 'pad gate', f'pad {pad.form_id:08X} of {option.rec.form_id:08X}')
            self.answers(menu, option, text(option.rec), by_place)

    def answers(self, menu: Menu, option: Option, shown_text: str, by_place: dict) -> None:
        """Check 1 on one option's answers: topic, order, prompt, Say Once marks and edges."""
        lines = [(a, self.copies[a.form_id][0]) for a in option.answers if a.form_id in self.copies]
        mine = self.source.shared.get(option.topic, set())
        for answer, line in lines:
            if line in self.source.lines and self.source.lines[line].get('ParentDIAL', '').upper() != \
                    f'{option.topic:08X}' and line not in mine:
                self.add(menu, option.topic, 'answer of another topic', f'{answer.form_id:08X} copies {line:08X}')
        said = [line for _, line in lines]
        if len(set(said)) < len(said):
            self.add(menu, option.topic, 'answer repeated', ' '.join(f'{a.form_id:08X}={line:08X}' for a, line in lines))
        own = [self.source.position.get(line, -1) for line in dict.fromkeys(said) if line not in mine]
        if own != sorted(own):
            self.add(menu, option.topic, 'answers out of order', ' '.join(f'{line:08X}' for line in said))
        if lines and lines[0][1] in self.source.lines:
            expected = shown(self.source.prompt(lines[0][1], option.topic))
            if expected and expected not in shown_text:
                self.add(menu, option.topic, 'prompt differs', f'"{shown_text}", FNV "{expected}"')
        for answer, line in lines:
            rec = self.source.lines.get(line, {})
            if int(rec.get('DATA.Flags', 0) or 0) & SAY_ONCE and answer.form_id not in self.once:
                self.add(menu, option.topic, 'say once unmarked', f'{answer.form_id:08X} copies {line:08X}')
            if rec and line not in self.split:
                self.edge(menu, option.topic, answer, line, by_place)

    def edge(self, menu: Menu, topic: int, answer, line: int, by_place: dict) -> None:
        """Check 1's edge: where `answer` leads against where FNV line `line` leads."""
        fnv = self.source.leads(line)
        tsce = u32(first(answer, 'TSCE'))
        ends = not tsce and struct.unpack_from('<H', first(answer, 'ENAM') or bytes(2))[0] & INFO_END_SCENE
        place = (tsce, u32(first(answer, 'INTV'))) if tsce else (menu.place[0], menu.place[1] + 1)
        built = None if ends else self.places.get(place)
        kind, extra = edge_kind(fnv, built, {o.topic for o in by_place.get(place, ())})
        if kind:
            names = ', '.join(sorted(map(self.source.topic_name, extra)))
            self.add(menu, topic, kind, f'{answer.form_id:08X} copies {line:08X}' + (f' offers {names}' if names else
                                                                                   f': FNV {fnv[0]}'))

    def exclusion(self, menu: Menu) -> None:
        """Check 2 on one menu, with check 1's shared prompts: two options of one FNV topic, or of two topics with
        one prompt, that can pass together."""
        for a, b in itertools.combinations(menu.options, 2):
            kind = 'two options' if a.topic == b.topic else 'duplicate prompt' if text(a.rec) == text(b.rec) else ''
            state, who = self.meet(a.rec, b.rec) if kind else (None, '')
            if state is None:
                continue
            pair = f'"{text(a.rec)}" ({a.rec.form_id:08X}) and "{text(b.rec)}" ({b.rec.form_id:08X}' + (
                f', {self.source.topic_name(b.topic)})' if a.topic != b.topic else ')')
            self.add(menu, a.topic, kind + TOO_MANY if state == 'budget' else kind,
                     pair if state == 'budget' else f'{pair}{who} when {describe(self.index, state)}')

    def meet(self, a, b) -> tuple:
        """(together()'s state for options `a` and `b`, ' for <the named speakers it holds for>'), memoized by
        their conditions."""
        key = (tuple(conditions(a)), tuple(conditions(b)))
        if key not in self.met:
            chains = self.gate(a) + self.gate(b)
            state = together(chains, self.speakers)
            who = [self.index.edid(n) or f'{n:08X}' for n in named(chains)
                   if isinstance(state, dict) and isinstance(together(chains, self.speakers, (n,)), dict)]
            self.met[key] = state, f' for {", ".join(who[:SHOWN])}' + (' ...' if len(who) > SHOWN else '') if who \
                else ''
        return self.met[key]

    def gate(self, rec) -> list:
        """The memoized gate of one option."""
        if rec.form_id not in self.gates:
            self.gates[rec.form_id] = gate(rec)
        return self.gates[rec.form_id]

    def side(self, answer) -> list:
        """The memoized conditions of one answer from its option's side (answer_side)."""
        if ('answer', answer.form_id) not in self.gates:
            self.gates[('answer', answer.form_id)] = answer_side(gate(answer))
        return self.gates[('answer', answer.form_id)]

    def known(self, rec) -> list:
        """An option's gate with its unlock global's chain left out (topic known)."""
        return [chain for chain in self.gate(rec) if not (len(chain) == 1 and chain[0][0][0][0] == 'glob' and
                                                         self.index.edid(chain[0][0][0][1]).startswith(UNLOCK_PREFIX))]

    def option_gates(self, menu: Menu) -> None:
        """Check 3 on one menu: an option showing with no answer able to play (empty), an answer able to play
        for a speaker the option names with no option of its topic showing (hidden), an option showing while a
        line FNV tries before its own of another option of the topic passes, that option hidden (wrong prompt)."""
        for option in menu.options:
            answers = [self.side(a) for a in option.answers]
            self.solve(menu, option, 'empty' + (ONE_EACH if one_each_gate(answers) else ''), self.gate(option.rec),
                       answers)
            rivals = [self.known(o.rec) for o in menu.options if o.topic == option.topic]
            scope = [c for c in self.gate(option.rec) if all(t[0] == SPEAKER for t, *_ in c)]
            for answer, chains in zip(option.answers, answers):
                self.solve(menu, option, 'hidden', chains + scope, rivals, f'{answer.form_id:08X} plays')
            for other in menu.options:
                if other is not option and other.topic == option.topic and other.quest == option.quest:
                    self.wrong_prompt(menu, option, other)

    def wrong_prompt(self, menu: Menu, option: Option, other: Option) -> None:
        """Check 3's wrong prompt: `option` shows while a line of `other` passes before any of its own."""
        mine = self.source.shared.get(option.topic, set())

        def place(answer) -> int:
            """FNV's position of an answer's own line, -1 for a shared or unpaired one."""
            line = self.copies.get(answer.form_id, (0,))[0]
            return -1 if line in mine else self.source.position.get(line, -1)
        for answer in other.answers:
            at = place(answer)
            if at >= 0:
                before = [self.side(a) for a in option.answers if 0 <= place(a) < at]
                self.solve(menu, option, 'wrong prompt', self.gate(option.rec) + self.side(answer),
                           before + [self.gate(other.rec)], f'{answer.form_id:08X} of "{text(other.rec)}" plays')

    def solve(self, menu: Menu, option: Option, kind: str, chains: list, fails: list, what: str = '') -> None:
        """Note a finding of `kind` when a state passes `chains` and fails each of `fails` (memoized)."""
        key = (kind, repr(chains), repr(fails))
        if key not in self.met:
            self.met[key] = together(chains, self.speakers, fails=tuple(fails))
        state = self.met[key]
        if state is not None:
            row = f'"{text(option.rec)}" ({option.rec.form_id:08X})' + (f', {what}' if what else '')
            self.add(menu, option.topic, kind + TOO_MANY if state == 'budget' else kind,
                     row if state == 'budget' else f'{row} when {describe(self.index, state)}')

    def run(self, built_menus: list) -> list:
        """Checks 1 to 3 over `built_menus`; one finding per (menu, topic, kind)."""
        by_place = {m.place: m.options for m in built_menus}
        for menu in built_menus:
            self.structure(menu, by_place)
            self.exclusion(menu)
            if menu.aligned:
                self.option_gates(menu)
        return [Finding('menus', f'menus|{self.game}|{name}|{topic}|{kind}',
                        'review' if kind in REVIEW or kind.endswith((TOO_MANY, ONE_EACH)) else 'error',
                        f'{name}: {kind} in topic {topic}', (f'{len(rows)} found',) + tuple(rows[:SHOWN]))
                for (name, topic, kind), rows in sorted(self.found.items())]


#: Finding kinds a person decides: a scene that ends on a loop by design; a pair past BUDGET carries TOO_MANY.
REVIEW, TOO_MANY = frozenset({'ends where FNV goes on'}), ', too many states'

#: An empty option whose gate the build wrote loosely by design (conversation.one_each): a review.
ONE_EACH = ' (one_each gate)'


def audit(game: str, index, ledger, export_dir) -> list:
    """Checks 1 and 2 over a built Fallout 4 plugin; prints the counts."""
    source = Source(export_records(export_dir, 'INFO'), export_records(export_dir, 'DIAL'))
    copies = {built: (fnv, part) for fnv, parts in line_parts(index, ledger, source.lines).items()
              for part, fids in parts.items() for built in fids}
    built_menus = read_menus(index, prompt_topics(index, ledger))
    found = MenuAudit(game, index, source, copies, Speakers(index, unfixed_factions(index, export_dir))).run(built_menus)
    print(f'  menus: {len(built_menus)} menus, {sum(len(m.options) for m in built_menus)} options, '
          f'{len(found)} findings')
    return found
