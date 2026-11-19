"""Write the layer 1 stage sweep from quest_plan.json: one story case file per quest, and a last case that reports.

    py -3.14 -m tools.live.fo4_stage_sweep temp/stage_sweep/FalloutNV.esm/quest_plan.json [--save NAME]
        [--quest EDID ...] [--all-stages] [--routes] [--chain] [--out DIR]

Each case loads sandbox save NAME, starts the quest when the source starts it
(Start Game Enabled or a StartQuest), then for each stage the build holds and
the source reaches (every stage with --all-stages), in order: waits for it
when an earlier stage's result script or the quest's timer sets it, sets it,
checks GetStageDone, and checks the Papyrus errors converted scripts raised
meanwhile. Every check is soft (`check`), so a broken quest stops nothing;
`zz_report.f4test`, last by name, fails the run listing every failed check.

See: docs/fork/fo4_test_layers_plan.md#l1
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from tools.live import fo4_route_steps as route_steps

#: Seconds a stage set from the console has to report done.
STAGE_SECONDS = 10
#: Seconds an earlier stage's result script has to set a stage.
AUTO_SECONDS = 10
#: Seconds a quest script's timer has to set a stage.
TIMER_SECONDS = 30
#: Seconds a started quest has to report running.
START_SECONDS = 10
#: Setters a stage's comment names before the rest are left out.
SHOWN = 3
#: One quest's case file, by its source EditorID; the report's, which sorts after every quest's.
CASE_FILE, REPORT_FILE = 'q_%s.f4test', 'zz_report.f4test'
REPORT_CASE = ('# The stage sweep\'s verdict: fails listing every check that failed in the cases before it.\n'
               'case zz_report\nreport\nend\n')


# ---------------------------------------------------------------------------
#  One quest
# ---------------------------------------------------------------------------

def how(setter: dict) -> str:
    """A source setter in a few words, for a stage's comment."""
    if setter['kind'] == 'stage':
        return '%s stage %d' % (setter['quest'], setter['stage'])
    if setter['kind'] == 'info':
        return 'line %s (%s; %s)' % (setter['info'], setter.get('topic') or '?',
                                     ', '.join(setter.get('speakers') or ['anyone']))
    if setter['kind'] == 'package':
        return 'package %s %s' % (setter['package'], setter['section'])
    return '%s %s %s' % (setter['kind'], setter['script'], setter['block'])


def automatic(quest: dict, entry: dict, before: set) -> tuple:
    """(seconds, setter) when stage `entry` follows on its own: the result script of an earlier swept stage of the
    quest (`before`: (quest lower, stage)) or the quest's timer sets it; else (0, '')."""
    own = quest['source'].lower()
    live = [s for s in entry['setters'] if s['live'] and s.get('quest', '').lower() == own]
    by_stage = [s for s in live if s['kind'] == 'stage' and (own, s['stage']) in before]
    if by_stage:
        return AUTO_SECONDS, "%s stage %d's result script" % (by_stage[0]['quest'], by_stage[0]['stage'])
    timers = [s for s in live if s['kind'] == 'timer']
    if timers:
        return TIMER_SECONDS, "%s's %s timer" % (timers[0]['script'], timers[0]['block'])
    return 0, ''


def stage_steps(quest: dict, entry: dict, before: set) -> list:
    """The case lines for one stage: a comment naming its setters, the wait when it follows on its own, the
    setstage and its checks."""
    fo4, stage = quest['fo4'], entry['stage']
    note = '%s stage %d' % (fo4, stage)
    setters = '; '.join(how(s) for s in entry['setters'][:SHOWN]) or 'no setter in the source'
    more = ' and %d more' % (len(entry['setters']) - SHOWN) if len(entry['setters']) > SHOWN else ''
    lines = ['# stage %d, set by %s%s' % (stage, setters, more)]
    seconds, by = automatic(quest, entry, before)
    if seconds:
        lines.append('check until %d GetStageDone %s %d == 1 | %s: not set by %s' % (seconds, fo4, stage, note, by))
    return lines + ['run setstage %s %d' % (fo4, stage),
                    'check until %d GetStageDone %s %d == 1 | %s' % (STAGE_SECONDS, fo4, stage, note),
                    'check errors | %s' % note]


def starts(quest: dict) -> bool:
    """Whether the source starts the quest: Start Game Enabled, or a StartQuest."""
    return quest['start_enabled'] or quest['started']


def swept(quest: dict, all_stages: bool, story: bool = False) -> list:
    """Stages to set: built, reached (or `all_stages`); with `story`, not failing."""
    return [s for s in quest['stages'] if s['built'] is not False and (all_stages or s['reached'])
            and not (story and s.get('ends') == 'fail')]


def start_steps(quest: dict) -> list:
    """Layer 1's quest start: startquest, then the checks."""
    fo4 = quest['fo4']
    return ['run startquest %s' % fo4,
            'check until %d GetQuestRunning %s == 1 | %s did not start: a required alias left empty?'
            % (START_SECONDS, fo4, fo4),
            'check errors | %s start' % fo4]


def case_lines(quest: dict, stages: list, save: str, game: str = '', before: 'set | None' = None,
               opening: tuple = ()) -> list:
    """One quest's case: load `save` (when given) and take the `opening` lines, start the quest if the source
    does, then each of `stages`; with `game` (the source plugin) each by its layer 2 route (fo4_route_steps), else
    by setstage. `before`, the run's done stages and played lines, is shared by a chain's cases, and a chained
    route case ends by completing the quest the way the source does."""
    lines = ['# %s (source %s): %d stages' % (quest['fo4'], quest['source'], len(stages)), 'case %s' % quest['source']]
    lines += ['load %s' % save, *opening] if save else []
    chained, before = before is not None, set() if before is None else before
    if starts(quest):
        lines += route_steps.start_lines(game, quest, before) if game else start_steps(quest)
    for entry in stages:
        lines += route_steps.stage_lines(game, quest, entry, before) if game else stage_steps(quest, entry, before)
        before.add((quest['source'].lower(), entry['stage']))
    if chained and game and quest.get('completes'):
        lines += route_steps.complete_lines(game, quest, before)
    return lines + ['end']


# ---------------------------------------------------------------------------
#  The sweep
# ---------------------------------------------------------------------------

def chosen_quests(plan: dict, wanted: list, chain: bool) -> list:
    """The plan's quests named in `wanted` (lower EditorIDs; every quest when empty), in its order for a chain."""
    if not chain:
        return [q for q in plan['quests'] if not wanted or q['source'].lower() in wanted]
    by_name = {q['source'].lower(): q for q in plan['quests']}
    return [by_name[name] for name in wanted if name in by_name]


def write_sweep(plan: dict, out: Path, save: str, wanted: list, all_stages: bool, routes: bool = False,
                chain: bool = False) -> tuple:
    """Writes one case file per quest worth sweeping, and the report case, into `out`, replacing the case files an
    earlier run wrote there; (quests, stages, stages waited for, {route kind: blocks} with `routes`). `wanted`
    (lower EditorIDs) narrows the quests. A `chain` runs them in `wanted`'s order in one game: numbered files,
    only the first loads `save`, one shared done set, no stage that fails its quest."""
    out.mkdir(parents=True, exist_ok=True)
    for old in [*out.glob(CASE_FILE % '*'), out / REPORT_FILE]:
        old.unlink(missing_ok=True)
    quests = stages = waits = 0
    kinds, before, game = Counter(), set(), plan['game'] if routes else ''
    picked = chosen_quests(plan, wanted, chain)
    for quest in picked:
        chosen = swept(quest, all_stages, chain)
        if quest['built'] is False or not (chosen or starts(quest)):
            continue
        opening = route_steps.opening_lines(game, picked if chain else [quest]) if game else []
        lines = case_lines(quest, chosen, '' if chain and quests else save, game, before if chain else None,
                           tuple(opening))
        name = '%02d_%s' % (quests + 1, quest['source']) if chain else quest['source']
        (out / (CASE_FILE % name)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        quests, stages = quests + 1, stages + len(chosen)
        waits += sum(': not set by ' in line for line in lines)
        kinds.update(m.group(1) for m in map(route_steps.ROUTE.match, lines) if m)
    (out / REPORT_FILE).write_text(REPORT_CASE, encoding='utf-8')
    return quests, stages, waits, dict(kinds)


def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plan', type=Path, help='a quest_plan.json (tools.live.fo4_quest_plan)')
    ap.add_argument('--save', default='', help='the sandbox save each case loads first (a start save)')
    ap.add_argument('--quest', nargs='*', default=[], help='only these source EditorIDs')
    ap.add_argument('--all-stages', action='store_true', help='also the stages the source never reaches')
    ap.add_argument('--routes', action='store_true', help='layer 2: each stage by its route, not setstage')
    ap.add_argument('--chain', action='store_true',
                    help='story order: the --quest quests in that order in one game, without stages that fail one')
    ap.add_argument('--out', type=Path, help='default: the plan\'s folder')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    """Writes the sweep's case files and prints their counts; 0."""
    args = parse_args(argv)
    if args.chain and not args.quest:
        raise SystemExit('--chain needs the quests in story order: --quest A B ...')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if not args.save:
        print('no --save: the quests run one after another in one game, each on the state the last one left')
    out = args.out or args.plan.parent
    quests, stages, waits, kinds = write_sweep(plan, out, args.save, [q.lower() for q in args.quest],
                                               args.all_stages, args.routes, args.chain)
    print('%s: %d quest cases, %d stages (%d waited for first) -> %s' % (plan['game'], quests, stages, waits, out))
    if kinds:
        print('routes: %s' % ', '.join('%s %d' % kv for kv in sorted(kinds.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
