"""Layer 2 routes: how a player makes each stage setter of quest_plan.json run in the source game.

A line (an `info` setter) is reached by talking to a placed actor its GetIsID conditions allow, then picking the
prompts of the lines whose choices lead from the greeting, a top-level topic or an added topic to the line's
topic. An object script runs by its block on a placed reference whose base carries it: the player walking into a
trigger, activating it, killing it, or taking the item. quest_plan stores the route on each setter;
`fo4_stage_sweep --routes` writes it as steps.

See: docs/fork/fo4_test_layers_plan.md#l2
"""
import math
from collections import defaultdict

from tools.validate.fo4_quest_readiness import RECORD_PREFIX
from tools.validate.preflight.quest_source import (GET_IS_ID, INFO_GOODBYE, line_needs, required_speakers,
                                                    script_bases)

#: DIAL flag Top-level: the topic is listed in every talk with a speaker its lines allow.
TOP_LEVEL = 0x02
#: The topic a talk opens with: its line is said, not picked.
GREETING = 'GREETING'
#: INFO DATA flag Say Once.
SAY_ONCE = 0x04
#: The most lines a choice chain holds, from the first pick to the setter's line.
MAX_DEPTH = 6
#: The most ways (choice chains) a line's route keeps; a talk tries each in turn.
WAYS = 3
#: Placed references a route keeps (a case uses the first; the rest are for review).
SHOWN_REFS = 3
#: An object script's block (first word, lower case) -> the route step that runs it.
BLOCK_STEPS = {'ontriggerenter': 'trigger', 'ontrigger': 'trigger', 'onactivate': 'activate',
               'ondeath': 'kill', 'onadd': 'take', 'onhitwith': 'shoot'}
#: Game units per side of an exterior cell.
CELL_UNITS = 4096
#: Steps that want every carrier: a count (three geckos dead, three bottles hit) may need all.
EVERY_CARRIER = ('kill', 'shoot')
#: The block arguments that mean the player does it (none: anyone, so the player too).
PLAYER_WORDS = ('', 'player', 'playerref')
#: Steps the player fights in: its fighting controls must be on.
FIGHTING_STEPS = ('shoot',)
#: Steps by which a player runs a script that turns its controls back on.
REACHED_STEPS = ('trigger', 'activate')


def hexes(fids, limit: 'int | None' = SHOWN_REFS) -> list:
    """FormIDs as 8-digit hex, the first `limit` (None: all)."""
    return ['%08X' % fid for fid in list(fids)[:limit]]


def gap(here: tuple, there: tuple) -> float:
    """Level distance of two `places` in one world or interior cell; else inf."""
    if not here or not there or here[0] != there[0] or not here[0] and here[1] != there[1]:
        return math.inf
    return math.hypot(here[2] - there[2], here[3] - there[3])


class Routes:
    """The routes of one source game, over its dialogue model (`SourceGame`) and its scripted bases."""

    def __init__(self, source, export_dir):
        """Index which lines offer each topic as a choice, which line each follows up, and which bases run each
        script, once."""
        self.source, self.offered, self.followed = source, defaultdict(list), defaultdict(list)
        self.lines_of, self.found = defaultdict(list), {}
        for info in source.infos.values():
            self.lines_of[info.dial].append(info)
            for topic in info.choices:
                self.offered[topic].append(info)
            for line in info.follow_ups:
                self.followed[line].append(info)
        self.bases = script_bases(str(export_dir))

    def says(self, info, speakers: set) -> bool:
        """Whether one of `speakers` (any when empty) may say `info`."""
        allowed = required_speakers(info.conditions)
        return allowed is None or not speakers or bool(speakers & set(allowed))

    def ways(self, info, speakers: set) -> list:
        """Up to WAYS distinct (prompt list, what its lines need set first (line_needs), whether it starts at a
        greeting), shortest first, a player picks from the start of a talk to `info` ([] for a greeting line):
        along choices of lines `speakers` may say (a greeting is said, never picked), and from a follow-up line to
        the line it follows (said on, nothing picked); [] when none of MAX_DEPTH reaches it."""
        queue, seen, found = [[info]], {info.fid}, []
        while queue and len(found) < WAYS:
            path = queue.pop(0)
            edid, _type, flags = self.source.dials.get(path[0].dial, ('', 0, 0))
            greeting = edid.upper() == GREETING
            way = [self.prompt(i) for i in (path[1:] if greeting else path)]
            if (greeting or flags & TOP_LEVEL or path[0].dial in self.source.external_topics) and way not in (
                    w for w, _n, _g in found):
                needs = (n for i in path for n in line_needs(i, self.source.quest_fids, self.source.variables))
                found.append((way, list(dict.fromkeys(needs)), greeting))
            picked = len(path) < MAX_DEPTH and not greeting
            steps = [[p] + path for p in self.offered.get(path[0].dial, ())] if picked else []
            steps += [[p] + path[1:] for p in self.followed.get(path[0].fid, ())]
            for step in steps:
                if step[0].fid not in seen and self.says(step[0], speakers):
                    seen.add(step[0].fid)
                    queue.append(step)
        return found

    def opening(self, speakers: set) -> list:
        """The prompts that get through `speakers`' first-meeting greeting (Say Once, conditioned on the speaker
        alone, so said before any other) back to the topic list: its shortest choice chain to a line with no
        choices, follow-ups or Goodbye; [] when there is none."""
        firsts = [g for t, d in self.source.dials.items() if d[0].upper() == GREETING for g in self.lines_of[t]
                  if g.flags & SAY_ONCE and g.conditions and all(c[2] == GET_IS_ID for c in g.conditions)
                  and speakers & set(required_speakers(g.conditions) or ())]
        queue = [(g, []) for g in firsts]
        while queue:
            line, prompts = queue.pop(0)
            for said in (i for t in line.choices for i in self.lines_of[t] if self.says(i, speakers)):
                if not (said.choices or said.follow_ups or said.flags & INFO_GOODBYE):
                    return prompts + [self.prompt(said)]
                queue += [(said, prompts + [self.prompt(said)])] * (len(prompts) < MAX_DEPTH)
        return []

    def prompt(self, info) -> str:
        """What a player picks to hear `info`: its own prompt, else its topic's name."""
        return self.source.prompts.get(info.fid) or self.source.topic_names.get(info.dial, '')

    def line(self, owner: str) -> dict:
        """line_route(owner), worked out once; a copy, which the plan fills in."""
        if owner not in self.found:
            self.found[owner] = self.line_route(owner)
        return dict(self.found[owner])

    def script(self, script: str, block: str) -> dict:
        """script_route(script, block), worked out once; a copy, which the plan fills in."""
        if (script, block) not in self.found:
            self.found[script, block] = self.script_route(script, block)
        return dict(self.found[script, block])

    def line_route(self, owner: str) -> dict:
        """The route to line `owner` (hex): the placed speakers, whether every one starts disabled, the speaker's
        display name, the prompts to pick (None when no chain reaches its topic), the objectives that way's lines
        need (`needs`) and the other ways' prompts (`more`); {} for an unknown line."""
        info = self.source.infos.get(int(owner, 16))
        if info is None:
            return {}
        bases = required_speakers(info.conditions) or []
        ways, opened = self.ways(info, set(bases)), self.opening(set(bases))
        names = [self.source.display_names.get(b) for b in bases if self.source.display_names.get(b)]
        refs = [r for b in bases for r in self.source.placed.get(b, ())]
        more = [way for way, _n, _g in ways[1:]] + [opened + way for way, _n, greeting in ways
                                                     if opened and not greeting and way[:len(opened)] != opened]
        return {'refs': hexes(refs), 'disabled': bool(refs) and all(r in self.source.disabled for r in refs),
                'name': names[0] if names else '', 'prompts': ways[0][0] if ways else None,
                'needs': ways[0][1] if ways else [], 'more': more}

    def script_route(self, script: str, block: str) -> dict:
        """The route of object script `script`'s `block`: its step (None when a player can't run that block; the
        `actor` it names when another runs it) and the placed references whose base runs it (all of them to kill
        or shoot: a count may want every one), with those bases; for a step, where to go first (`goto`), the
        reference to enable first (`enable`: the first one, or its enable parent, starting disabled) and, for a
        fight, the route turning the player's fighting on (`controls`)."""
        word, _, rest = block.strip().partition(' ')
        player = rest.strip().lower() in PLAYER_WORDS
        step = BLOCK_STEPS.get(word.lower()) if player else None
        bases = self.bases.get(self.source.script_fids.get(script.lower()), [])
        refs = [r for b in bases for r in self.source.placed.get(b, ())]
        route = {'step': step, 'refs': hexes(refs, None if step in EVERY_CARRIER else SHOWN_REFS),
                 'bases': hexes(bases)}
        route |= {'actor': rest.strip()} if word.lower() in BLOCK_STEPS and not player else {}
        if step and refs:
            enable = [r for r in (refs[0], self.source.parents.get(refs[0])) if r in self.source.disabled]
            goto, controls = self.goto(refs[0]), self.fighting(refs[0]) if step in FIGHTING_STEPS else {}
            route |= ({'goto': goto} if goto else {}) | ({'enable': hexes(enable)[0]} if enable else {})
            route |= {'controls': controls} if controls else {}
        return route

    def fighting(self, ref: int) -> dict:
        """The route, with its `script` and `block`, of the script nearest placed `ref` (same world or cell) that
        turns the player's fighting back on (EnablePlayerControls) in a block a player walks into or activates;
        {} for none. FNV keeps fighting off until the player leaves Doc's house through such a trigger.
        See: docs/fork/fo4_test_layers_plan.md#fighting-controls
        """
        here, found = self.source.places.get(ref), []
        for site in self.source.fighting_sites:
            if site.kind == 'script' and BLOCK_STEPS.get(site.part.split(' ')[0].lower()) in REACHED_STEPS:
                route = self.script(site.owner, site.part) | {'script': site.owner, 'block': site.part}
                far = gap(here, self.source.places.get(int(route['refs'][0], 16))) if route['refs'] else math.inf
                found += [(far, route)] if route['step'] and far < math.inf else []
        return min(found, key=lambda pair: pair[0], default=(0, {}))[1]

    def goto(self, ref: int) -> dict:
        """Where the player goes before a step on placed `ref` that is not persistent (the game finds it only
        in a loaded cell): its interior cell (`cell`), else its world and grid cell; {} for a persistent ref.
        See: docs/fork/fo4_test_layers_plan.md#l2-built
        """
        world, cell, x, y, persistent = self.source.places.get(ref, (0, 0, 0.0, 0.0, True))
        if persistent:
            return {}
        if world:
            return {'world': RECORD_PREFIX + self.source.space_ids.get(world, ''), 'x': math.floor(x / CELL_UNITS),
                    'y': math.floor(y / CELL_UNITS)}
        return {'cell': RECORD_PREFIX + self.source.space_ids.get(cell, '')}
