"""Layer 2 route steps: each stage's setter run as a player runs it, from the routes in quest_plan.json.

A stage waits alone for an earlier stage of the run, its timer, or a line the run already played; else it tries
the lines its live setters offer as one conversation per speaker (`talk`: moveto, look, talk, choose whichever
way's prompt is listed, hear any of the lines, bye; a speaker who starts disabled is enabled first by a line
that enables them), then each object script's block (`trigger`: walk in; `activate`; `kill`: every carrier;
`take`: the player gets the item), then the quest's own script or an actor's package (waited for). A stage with
none is a `gap`, set with setstage as in layer 1. Every step is a soft check skipped once the stage is done
(`unless`); a setstage keeps the case going only when no route set it (a finished quest is not restarted).

See: docs/fork/fo4_test_layers_plan.md#l2
"""
import re

from tools.validate.fo4_quest_readiness import RECORD_PREFIX
from tools.validate.preflight.quest_source import VARIABLE

#: Seconds `talk` waits for the dialogue menu, `choose` for each prompt, `heard` for the line to end.
TALK_SECONDS, CHOOSE_SECONDS, HEAR_SECONDS = 30, 20, 60
#: Seconds a route's own effect has to set the stage; a waited setter's (a package walks somewhere first).
DONE_SECONDS, WAIT_SECONDS = 10, 60
#: Seconds before `ready` after a `coc`/`cow` (the loading menu is not up at once); seconds `ready` waits for it.
SETTLE_SECONDS, LOAD_SECONDS = 2, 120
#: Units from the first target a `shoot` route walks to before it fires.
SHOOT_RANGE = 600
#: Routes a block tries in turn before its fallback.
TRIES = 3
#: Setter kinds a stage waits for: their own code runs once the stages before them are done.
WAITED = ('timer', 'quest script', 'package')
#: A route's comment line, naming its kind (counted for the sweep's coverage).
ROUTE = re.compile(r'^# (?:stage \d+|start|complete) route (\w+)')
#: A needed objective's state -> the word in its mirror global's EditorID (tes5_import objectives_falloutnv).
OBJECTIVE_MIRRORS = {'completed': 'Done', 'displayed': 'Shown'}


def source_ref(game: str, fid: str) -> str:
    """Source record `fid` (hex) of plugin `game` as a story case names it."""
    return '{%s:%s}' % (game, fid)


def usable(setter: dict, kind: str) -> bool:
    """Whether a live setter of `kind` has what its route needs (a speaker and a chain; a step and a reference)."""
    route = setter.get('route') or {}
    if kind == 'info':
        return bool(route.get('refs')) and route.get('prompts') is not None
    return bool(route.get('step')) and bool(route.get('bases' if route.get('step') == 'take' else 'refs'))


def action(setter: dict):
    """(route kind, setter) a player runs `setter` by, or None: a line's talk, else the first usable site saying it
    (`said_by`); an object script's step."""
    route = setter.get('route') or {}
    if setter['kind'] == 'info':
        if usable(setter, 'info'):
            return 'talk', setter
        return next(iter(actions([s for s in route.get('said_by', ()) if s['live']])), None)
    return (route['step'], setter) if setter['kind'] == 'object script' and usable(setter, 'object script') else None


def actions(live: list) -> list:
    """[action()] of the lines (disabled speakers last), then object scripts."""
    lines = sorted((s for s in live if s['kind'] == 'info'), key=lambda s: bool(s['route'].get('disabled')))
    return [found for found in map(action, lines + [s for s in live if s['kind'] == 'object script']) if found]


def waits(setter: dict) -> bool:
    """Whether its own code (WAITED) or another actor (`actor`) runs it."""
    return setter['kind'] in WAITED or bool((setter.get('route') or {}).get('actor'))


def candidates(quest: dict, setters: list, before: set) -> list:
    """[(route kind, setter)] to try in turn, at most TRIES: one waited setter when an earlier stage of the run,
    the quest's timer or a line already played sets it; else actions(), then one waited quest script or package.
    `before` holds the run's done stages, (quest lower, stage), and ('info', FormID) of the lines it played."""
    own = quest['source'].lower()
    live = [s for s in setters if s['live']]
    for setter in live:
        if (setter['kind'] == 'stage' and (setter['quest'].lower(), setter['stage']) in before
                or setter['kind'] == 'info' and ('info', setter['info']) in before
                or setter['kind'] == 'timer' and setter.get('quest', '').lower() == own):
            return [('wait', setter)]
    waited = [s for s in live if waits(s)]
    return (actions(live) + [('wait', s) for s in waited[:1]])[:TRIES]


def join(groups: dict, setter: dict, needs: str = '', skip: str = '') -> None:
    """Adds line `setter` to its speaker's conversation in `groups` (by first ref): its ways and its line. `needs`
    is a console condition to wait for before that talk (the speaker enabled); `skip`, one that makes the talk
    pointless (an enabler's, once its speaker is enabled), dropped when a line without one joins."""
    route = setter['route']
    talk = groups.setdefault(route['refs'][0], {'ref': route['refs'][0], 'name': route.get('name', ''),
                                                'ways': [], 'infos': [], 'needs': needs, 'skip': skip})
    talk['skip'] = talk['skip'] and skip
    talk['ways'] += [way for way in [route['prompts'], *route.get('more', ())] if way not in talk['ways']]
    talk['infos'] += [setter['info']] * (setter['info'] not in talk['infos'])


def first_action(setters: list):
    """The first (route kind, setter) of the live usable `setters`, or None."""
    return next(iter(actions([s for s in setters if s['live']])), None)


def need_done(need: str) -> str:
    """Console condition that `need` holds, by the mirror global the line's own condition reads: an objective's
    (`completed VCG02 10`: TES4ObjDone_VCG02_10 == 1) or a quest variable's (`variable Q v 1`: TES4QVar_Q_v == 1)."""
    words = need.split()
    if words[0] == VARIABLE:
        return 'GetGlobalValue TES4QVar_%s_%s == %s' % tuple(words[1:])
    return 'GetGlobalValue TES4Obj%s_%s_%s == 1' % (OBJECTIVE_MIRRORS[words[0]], words[1], words[2])


def needed(tries: list, guards: 'dict | None' = None, guard: str = '') -> list:
    """[(route kind, setter)] to run before a block's routes, each once, its own needs before it: per need of a
    talk's way (`needs`: an objective or quest variable) and per step's disabled reference (`enabled_by`), the
    first usable live site. `guards` gets, by id of each site run for a need (and what it needs), need_done()."""
    found, guards = [], {} if guards is None else guards
    for kind, setter in tries:
        route = setter.get('route') or {}
        groups = ([(need['by'], need_done(need['need'])) for need in route.get('needs', ())]
                  if kind == 'talk' else [(route.get('enabled_by', []), guard)])
        for first, skip in ((first_action(group), skip) for group, skip in groups):
            if first:
                guards.update({id(first[1]): skip} if skip else {})
                found += [item for item in needed([first], guards, skip) + [first] if item not in found]
    return found


def conversations(game: str, tries: list, guards: 'dict | None' = None) -> list:
    """One conversation per speaker for a block's talk routes, in order: a Say Once greeting a first talk used up
    would not offer its choices to a second. A line whose speakers all start disabled is preceded by the first
    usable live line enabling them (`enabled_by`), joined to that line's speaker's talk. A line in `guards` (by id,
    needed()) is skipped once its need holds."""
    groups, guards = {}, guards or {}
    for kind, setter in tries:
        if kind != 'talk':
            continue
        route, needs = setter['route'], ''
        enabler = next((s for k, s in actions([e for e in route.get('enabled_by', ()) if e['live']])
                        if k == 'talk'), None)
        if route.get('disabled') and enabler:
            needs = '%s.GetDisabled == 0' % source_ref(game, route['refs'][0])
            join(groups, enabler, skip=needs)
        join(groups, setter, needs, guards.get(id(setter), ''))
    return list(groups.values())


def conversation_steps(game: str, talk: dict) -> list:
    """One talk: wait for what it needs, moveto, look, talk, look, then at each depth `choose` whichever way's
    prompt is listed (or nothing, `-`, past a shorter way's end), hear any of its lines, bye; each step behind
    `unless <skip> | check` when it has one."""
    ref, ways = source_ref(game, talk['ref']), talk['ways']
    picks = [' || '.join(dict.fromkeys([way[depth] for way in ways if len(way) > depth]
                                       + ['-'] * any(len(way) <= depth for way in ways)))
             for depth in range(max(map(len, ways), default=0))]
    heard = ['heard %d %s %s' % (HEAR_SECONDS, talk['name'], ','.join(talk['infos']))] if talk['name'] else []
    steps = (['until %d %s' % (WAIT_SECONDS, talk['needs'])] * bool(talk['needs'])
             + ['run player.moveto %s' % ref, 'look %s' % ref, 'talk %d %s' % (TALK_SECONDS, ref), 'look %s' % ref]
             + ['choose %d %s' % (CHOOSE_SECONDS, p) for p in picks] + heard + ['bye'])
    return ['unless %s | check %s' % (talk['skip'], step) for step in steps] if talk['skip'] else steps


def goto_steps(goto: dict) -> list:
    """The steps taking the player to a route's `goto` cell (interior by EditorID, else world and grid), then
    waiting for it to load; [] for none."""
    if not goto:
        return []
    command = 'coc %s' % goto['cell'] if 'cell' in goto else 'cow %s %d %d' % (goto['world'], goto['x'], goto['y'])
    return ['run %s' % command, 'wait %d' % SETTLE_SECONDS, 'ready %d' % LOAD_SECONDS]


def route_steps(game: str, kind: str, setter: dict) -> list:
    """The steps (without `check`) a player takes for route `kind` of `setter`, its `goto` cell first."""
    route = setter.get('route') or {}
    if kind == 'talk':
        return [step for talk in conversations(game, [(kind, setter)]) for step in conversation_steps(game, talk)]
    return goto_steps(route.get('goto')) + object_steps(game, kind, route)


def object_steps(game: str, kind: str, route: dict) -> list:
    """The steps of an object script's route `kind` once its references are loaded."""
    ref = source_ref(game, route['refs'][0]) if route.get('refs') else ''
    if kind == 'trigger':
        return ['run player.moveto %s' % ref, 'walk 30 %s' % ref]
    if kind == 'activate':
        return ['run player.moveto %s' % ref, 'look %s' % ref, 'activate %s' % ref]
    if kind == 'kill':
        return ['run %s.kill' % source_ref(game, fid) for fid in route['refs']]
    if kind == 'shoot':
        return ['walk 30 %s %d' % (ref, SHOOT_RANGE)] + ['shoot 1 %s' % source_ref(game, fid) for fid in route['refs']]
    if kind == 'take':
        return ['run player.additem %s 1' % source_ref(game, route['bases'][0])]
    return []


def fights(node) -> list:
    """Every `controls` route under `node` (plan quests, their setters' routes and what those need)."""
    if isinstance(node, list):
        return [found for item in node for found in fights(item)]
    if not isinstance(node, dict):
        return []
    own = [node['controls']] if 'controls' in node else []
    return own + [found for value in node.values() for found in fights(value)]


def opening_lines(game: str, quests: list) -> list:
    """The lines a run takes right after loading its save: each script turning the player's fighting on that a
    `shoot` route of `quests` needs (`controls`), run once by its route, as the story runs it before them.
    See: docs/fork/fo4_test_layers_plan.md#fighting-controls
    """
    scripts = {}
    for route in fights(quests):
        scripts.setdefault(route['script'], route)
    return [line for script, route in scripts.items()
            for line in ['# controls: %s %s' % (script, route['block'])]
            + ['check %s | controls: %s' % (step, script)
               for step in goto_steps(route.get('goto')) + object_steps(game, route['step'], route)]]


def heading(head: str, tries: list) -> list:
    """The block's comments: `head route <kind>` for the first candidate (counted), `head else <kind>` after."""
    return ['# %s %s %s: %s %s' % (head, 'else' if number else 'route', kind, setter['kind'],
                                   setter.get('info') or setter.get('script') or setter.get('package')
                                   or setter.get('quest', ''))
            for number, (kind, setter) in enumerate(tries)]


def need_steps(tries: list) -> list:
    """Per need of a block's talks: check its mirror global (need_done()) holds, else set it from the console (an
    objective's own too), so the talk is still tested when the sites that should set it failed.
    See: docs/fork/fo4_test_layers_plan.md#objective-fallback
    """
    found = dict.fromkeys(need['need'] for kind, setter in tries if kind == 'talk'
                          for need in (setter.get('route') or {}).get('needs', ()))
    steps = []
    for need in found:
        how, quest, index = need.split()[:3]
        done = need_done(need)
        unset = 'unless %s | check run ' % done
        objective = [unset + 'setobjective%s %s%s %s 1' % (how, RECORD_PREFIX, quest, index)] * (how != VARIABLE)
        steps += ['until %d %s' % (DONE_SECONDS, done)] + objective + [unset + 'set %s to %s' % tuple(done.split()[1::2])]
    return steps


def block_steps(game: str, tries: list) -> list:
    """[(step, part)] of a block's routes: what its talks need (needed(); a line in a talk of its own, before) and
    the fallbacks for their needs (need_steps), its candidates' talks (one conversation per speaker; part `talk N
    with <name>`, so a talk that breaks is cut short alone), then their other routes (part `the route`)."""
    guards = {}
    first = needed(tries, guards)
    early = conversations(game, [p for p in first if p[0] == 'talk'], guards)
    talks = list(enumerate(early + conversations(game, tries), 1))
    steps = [('unless %s | check %s' % (guards[id(setter)], step) if id(setter) in guards else step, 'the route')
             for kind, setter in first if kind != 'talk' for step in route_steps(game, kind, setter)]
    said = [[(step, 'talk %d with %s' % (number, talk['name'] or talk['ref']))
             for step in conversation_steps(game, talk)] for number, talk in talks]
    steps += [step for group in said[:len(early)] for step in group]
    steps += [(step, 'the route') for step in need_steps(tries)]
    steps += [step for group in said[len(early):] for step in group]
    return steps + [(step, 'the route') for kind, setter in tries if kind != 'talk'
                    for step in route_steps(game, kind, setter)]


def block(game: str, quest: dict, head: str, setters: list, before: set, done: tuple) -> list:
    """The lines of one route block: its routes (block_steps), then the wait for `done`'s condition, each a soft
    check skipped once it holds; then the command that sets it when no route did, the check that it holds, and
    the Papyrus errors meanwhile."""
    condition, fallback, note = done
    tries = candidates(quest, setters, before)
    seconds = WAIT_SECONDS if any(waits(setter) for _, setter in tries) else DONE_SECONDS
    steps = block_steps(game, tries) + [('until %d %s' % (seconds, condition), 'the route')] * bool(tries)
    lines = heading(head, tries) or ['# %s route gap: no route' % head]
    lines += ['unless %s | %s | %s: %s' % (condition, step if step.startswith('unless ') else 'check ' + step,
                                           note, part) for step, part in steps]
    if tries and tries[0][0] == 'talk':
        before.add(('info', tries[0][1]['info']))
    return lines + ['unless %s | run %s' % (condition, fallback),
                    'check until %d %s | %s' % (DONE_SECONDS, condition, note), 'check errors | %s' % note]


def stage_lines(game: str, quest: dict, entry: dict, before: set) -> list:
    """One stage's route block; its stage joins `before`'s done stages after."""
    fo4, stage = quest['fo4'], entry['stage']
    done = ('GetStageDone %s %d == 1' % (fo4, stage), 'setstage %s %d' % (fo4, stage), '%s stage %d' % (fo4, stage))
    return block(game, quest, 'stage %d' % stage, entry['setters'], before, done)


def complete_lines(game: str, quest: dict, before: set) -> list:
    """The completion route block, by the source's CompleteQuest sites."""
    fo4 = quest['fo4']
    done = ('GetQuestCompleted %s == 1' % fo4, 'completequest %s' % fo4, '%s complete' % fo4)
    return block(game, quest, 'complete', quest['completes'], before, done)


def start_lines(game: str, quest: dict, before: set) -> list:
    """The quest start's route block, by the setters the source starts it with."""
    fo4 = quest['fo4']
    done = ('GetQuestRunning %s == 1' % fo4, 'startquest %s' % fo4, '%s start' % fo4)
    return block(game, quest, 'start', quest['starts'], before, done)
