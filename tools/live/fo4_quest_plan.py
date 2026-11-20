"""Write quest_plan.json: per source quest, its Fallout 4 EditorID, its stages in order and how the source sets each.

    py -3.14 -m tools.live.fo4_quest_plan --game FalloutNV.esm [--plugin <built FalloutNV.esm>] [--out FILE]

The setters come from the preflight's source model (`quest_source.SourceGame`),
and whether the source reaches a stage from its quest progression graph. Each
setter is one of: `stage` (another stage's result script), `info` (a line's
result script: its topic and speakers), `quest script`, `timer` (a quest
script's GameMode block in a script that reads GetSecondsPassed), `object
script` or `package`. With `--plugin`, each quest and stage is marked built or
not from the built plugin's QUST records (`FNV_<EditorID>`, INDX).

See: docs/fork/fo4_test_layers_plan.md#l1
"""
import argparse
import json
import re
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from tes5_import.base.tes5_reader import records, subrecords, zstr
from tes5_import.base.text_reader import get_str, parse_export_file
from tools.live.fo4_quest_routes import Routes
from tools.validate.fo4_quest_readiness import RECORD_PREFIX
from tools.validate.preflight.quest_progression import reached_stages, source_live
from tools.validate.preflight.quest_source import (COMPLETE, COMPLETE_QUEST, FAIL_QUEST, START, VARIABLE, SourceGame,
                                                   coded_lines, required_speakers)

#: A script that waits on real time.
TIMER = re.compile(r'\bgetsecondspassed\b', re.I)
#: The script blocks a quest script's timer runs in.
TIMER_BLOCKS = ('gamemode', 'menumode')
#: A timer: `set t to t - GetSecondsPassed` (a countdown) or `+` (a count up): (variable, sign).
COUNTED = re.compile(r'\bset\s+(\w+)\s+to\s+\(?\s*\1\s*([-+])\s*getsecondspassed', re.I)
#: A count up's end: `t > 5` or `t >= 5`, a variable as `%s`.
REACHES = r'\b%s\s*>=?\s*(\d+(?:\.\d+)?|\.\d+)'
#: A number set to a variable on a code line, `set [quest.]var to 2.5`: (quest or '', var, number).
NUMBER_SET = re.compile(r'\bset\s+(?:(\w+)\.)?(\w+)\s+to\s+(\d+(?:\.\d+)?|\.\d+)\s*$', re.I)
#: The opener of an `if` frame, a branch of one, and its close, on a code line.
IF, ELSEIF, ENDIF = re.compile(r'if\b', re.I), re.compile(r'elseif\b', re.I), re.compile(r'endif\b', re.I)
#: Where the plan goes when --out is not given: under this, `<game>/quest_plan.json`.
OUT_ROOT = Path('temp') / 'stage_sweep'


# ---------------------------------------------------------------------------
#  Reading
# ---------------------------------------------------------------------------

def built_stages(plugin: Path) -> dict:
    """{EditorID: {stage}} of the quests in built plugin `plugin`, from their EDID and INDX."""
    out = {}
    for rec in records(Path(plugin).read_bytes(), b'QUST'):
        subs = subrecords(rec.body)
        edid = next((zstr(data) for tag, data in subs if tag == b'EDID'), '')
        out[edid] = {int.from_bytes(data[:2], 'little') for tag, data in subs if tag == b'INDX'}
    return out


def script_texts(export_dir: Path) -> dict:
    """{script EditorID lower: source text} of the export's SCPT records."""
    path = Path(export_dir) / 'SCPT.txt'
    rows = parse_export_file(str(path)) if path.is_file() else []
    return {get_str(r, 'EditorID').lower(): r.get('SCTX', '') for r in rows}


def source_reached(source) -> tuple:
    """(reached {(quest lower, stage)}, live(site)) over the source's live setters."""
    live = partial(source_live, ctx=SimpleNamespace(source=source, source_topics=source.reachable_topics()))
    return reached_stages([s for s in source.setters if live(s)], lambda s: True, source), live


# ---------------------------------------------------------------------------
#  Timers
# ---------------------------------------------------------------------------

def timer_lengths(source) -> dict:
    """{(quest lower, variable lower): the largest number any source text sets it to by `set quest.var`}."""
    out = {}
    for text in source.texts:
        for code, _line, _block in coded_lines(text):
            for quest, var, number in NUMBER_SET.findall(code.strip()):
                if quest:
                    key = (quest.lower(), var.lower())
                    out[key] = max(out.get(key, 0.0), float(number))
    return out


def guard_words(text: str, raw: str) -> set:
    """Lower words of the conditions around the first line `raw` of script `text`: each enclosing `if`, and its
    `elseif`s up to the line's branch."""
    frames = []
    for code, line, _block in coded_lines(text):
        code = code.strip()
        if ELSEIF.match(code) and frames:
            frames[-1].append(code[6:])
        elif IF.match(code):
            frames.append([code[2:]])
        elif ENDIF.match(code) and frames:
            frames.pop()
        if line == raw:
            return {w.lower() for frame in frames for cond in frame for w in re.findall(r'\w+', cond)}
    return set()


def timer_seconds(quest: str, text: str, lengths: dict, raw: str = '') -> float:
    """The longest authored run of the timers of script `text` that the conditions around line `raw` name, 0
    when they name none or none is a number: the largest number set to a countdown (in `text`, or as
    `quest.var` anywhere: `lengths`, timer_lengths()) or a count up is compared with."""
    codes = [code.strip() for code, _line, _block in coded_lines(text)]
    near = guard_words(text, raw)
    timers = {v.lower(): sign for code in codes for v, sign in COUNTED.findall(code) if v.lower() in near}
    down = {v for v, sign in timers.items() if sign == '-'}
    up = {v for v, sign in timers.items() if sign == '+'}
    own = [float(n) for code in codes for q, v, n in NUMBER_SET.findall(code) if not q and v.lower() in down]
    own += [float(n) for code in codes for v in up for n in re.findall(REACHES % v, code, re.I)]
    return max([*own, *(lengths.get((quest.lower(), v), 0.0) for v in down)], default=0.0)


# ---------------------------------------------------------------------------
#  Setters
# ---------------------------------------------------------------------------

#: How deep prerequisites nest: a talk needs an objective, set by shooting bottles, enabled by a bark, said in a trigger.
DEPTH = 3


def need_text(need: tuple, source) -> str:
    """A line_needs need as the case names it, with its quest's and variable's own spelling: `completed VCG02 10`,
    `variable VFreeformGoodsprings bKnowRingoHiding 1`."""
    quest = source.quests.get(need[1], need[1])
    if need[0] != VARIABLE:
        return '%s %s %d' % (need[0], quest, need[2])
    name = next((n for (q, _i), n in source.variables.items() if q == need[1] and n.lower() == need[2]), need[2])
    return '%s %s %s %g' % (VARIABLE, quest, name, need[3])


def info_fields(owner: str, source) -> dict:
    """The line `owner` (hex) names: its topic, its quest and the speakers its conditions allow."""
    info = source.infos.get(int(owner, 16))
    if info is None:
        return {'info': owner}
    speakers = required_speakers(info.conditions) or []
    return {'info': owner, 'topic': source.dials.get(info.dial, ('',))[0],
            'quest': source.quest_fids.get(info.quest, ''),
            'speakers': [source.actor_names.get(fid) or '%08X' % fid for fid in speakers]}


def script_fields(site, source, texts: dict, lengths: dict) -> dict:
    """A script setter: quest script, timer (with its authored `seconds`, timer_seconds()) or object script, its
    block, and the quest a quest script runs in; `lengths` is timer_lengths()."""
    quest = source.quest_script_of.get(site.owner.lower())
    text = texts.get(site.owner.lower(), '')
    timed = site.part.lower().startswith(TIMER_BLOCKS) and TIMER.search(text)
    kind = 'timer' if quest and timed else 'quest script' if quest else 'object script'
    out = {'kind': kind, 'script': site.owner, 'block': site.part} | ({'quest': source.quests[quest]} if quest else {})
    if kind == 'timer':
        out['seconds'] = timer_seconds(source.quests[quest], text, lengths, site.raw)
    return out


def setter(site, source, texts: dict, live, routes, depth: int = DEPTH, lengths: 'dict | None' = None) -> dict:
    """One source setter as plan data: its kind, where it sits, its line, whether its container runs, and for a
    line or an object script how a player makes it run (`routes`, fo4_quest_routes), with what it waits on
    (prerequisites()) while `depth` lasts; `lengths` (timer_lengths()) times a timer."""
    lengths = {} if lengths is None else lengths
    entry = {'kind': site.kind, 'line': site.raw, 'live': bool(live(site))}
    if site.kind == 'stage':
        quest, stage = site.owner.split('|')
        entry.update(quest=quest, stage=int(stage))
    elif site.kind == 'info':
        entry.update(info_fields(site.owner, source), route=routes.line(site.owner))
    elif site.kind == 'package':
        entry.update(package=source.packages.get(site.owner, {}).get('EditorID', site.owner), section=site.part)
    else:
        entry.update(script_fields(site, source, texts, lengths))
    if entry['kind'] == 'object script':
        entry['route'] = routes.script(site.owner, site.part)
    if 'route' in entry:
        prerequisites(entry, lambda sites: [setter(s, source, texts, live, routes, depth - 1, lengths)
                                            for s in sites], source, depth)
    return entry


def prerequisites(entry: dict, plan, source, depth: int) -> None:
    """Fills `entry`'s route (when `depth` > 0) with the sites, as setters by `plan`, that must run first: enabling
    a line's speakers who all start disabled or a step's disabled reference (`enabled_by`), setting each
    objective a line's way needs (`needs[].by`), and saying a line no talk reaches (`said_by`)."""
    route = entry['route']
    disabled = {int(r, 16) for r in route['refs']} if route.get('disabled') else set()
    disabled |= {int(route['enable'], 16)} if route.get('enable') else set()
    if depth > 0 and disabled:
        route['enabled_by'] = plan(source.enablers(disabled))
    if entry['kind'] == 'info':
        route['needs'] = [{'need': need_text(need, source), 'by': plan(source.need_setters(need))}
                          for need in route.get('needs', ()) if depth > 0]
    if depth > 0 and entry['kind'] == 'info' and route.get('prompts') is None and entry.get('topic'):
        route['said_by'] = plan(source.sayers(entry['topic']))


# ---------------------------------------------------------------------------
#  The plan
# ---------------------------------------------------------------------------

def stage_end(flags: int) -> str:
    """'fail' or 'complete' when a stage's log flags end its quest, else ''."""
    return 'fail' if flags & FAIL_QUEST else 'complete' if flags & COMPLETE_QUEST else ''


def quest_entry(edid: str, stages: list, sites: dict, reached: set, built, describe) -> dict:
    """One quest's plan: names, how it starts, each of `stages` in order with its setters (`sites` by stage, each
    as `describe` gives it), what completes it; `built` is built_stages() or None when unknown."""
    lower, fo4 = edid.lower(), RECORD_PREFIX + edid
    held = None if built is None else built.get(fo4, set())
    return {'source': edid, 'fo4': fo4, 'built': None if built is None else fo4 in built,
            'started': (lower, START) in reached, 'starts': [describe(s) for s in sites.get(START, ())],
            'completes': [describe(s) for s in sites.get(COMPLETE, ())],
            'computed': [describe(s) for s in sites.get(None, ())],
            'stages': [{'stage': n, 'reached': (lower, n) in reached, 'built': None if held is None else n in held,
                        'setters': [describe(s) for s in sites.get(n, ())]} for n in sorted(set(stages))]}


def build_plan(export_dir: Path, built: 'dict | None') -> dict:
    """The plan of every source quest in `export_dir` with stages or a start; `built` is built_stages() or None."""
    source = SourceGame(str(export_dir))
    reached, live = source_reached(source)
    texts, routes, lengths = script_texts(export_dir), Routes(source, export_dir), timer_lengths(source)
    by_quest = {}
    for site in [*source.setters, *source.completers]:
        by_quest.setdefault(site.quest.lower(), {}).setdefault(site.stage, []).append(site)
    quests = []
    for lower, edid in sorted(source.quests.items()):
        stages, sites = source.stages.get(lower, []), by_quest.get(lower, {})
        if not (stages or START in sites or lower in source.start_enabled):
            continue
        entry = quest_entry(edid, stages, sites, reached, built,
                            partial(setter, source=source, texts=texts, live=live, routes=routes, lengths=lengths))
        entry['start_enabled'] = lower in source.start_enabled
        for stage in entry['stages']:
            stage['ends'] = stage_end(source.stage_flags[(lower, stage['stage'])])
            stage['stops'] = (lower, stage['stage']) in source.stops
        quests.append(entry)
    return {'game': Path(export_dir).name, 'prefix': RECORD_PREFIX, 'quests': quests}


def summary(plan: dict) -> str:
    """Counts of a plan: quests, built quests, stages, and the stages the source reaches."""
    quests = plan['quests']
    stages = [s for q in quests for s in q['stages']]
    built = sum(q['built'] is not False for q in quests)
    return ('%s: %d quests (%d built or unknown), %d stages, %d reached in the source'
            % (plan['game'], len(quests), built, len(stages), sum(s['reached'] for s in stages)))


def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--game', required=True, help='the source export folder name, e.g. FalloutNV.esm')
    ap.add_argument('--export', type=Path, default=Path('export'))
    ap.add_argument('--plugin', type=Path, help='the built Fallout 4 plugin, to mark what was built')
    ap.add_argument('--out', type=Path, help='default temp/stage_sweep/<game>/quest_plan.json')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    """Writes the plan and prints its counts; 0."""
    args = parse_args(argv)
    if args.plugin is None:
        print('no --plugin: built is unknown; every quest is assumed built as %s<EditorID>' % RECORD_PREFIX)
    built = built_stages(args.plugin) if args.plugin else None
    plan = build_plan(args.export / args.game, built)
    out = args.out or OUT_ROOT / args.game / 'quest_plan.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding='utf-8')
    print('%s -> %s' % (summary(plan), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
