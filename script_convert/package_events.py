"""FO3/FNV `begin OnPackageStart|Done|End|Change <package>` on Fallout 4: run by the package's own fragments.

Fallout 4 sends converted actor scripts none of its package events, and vanilla
answers a package from its fragments. So on Fallout 4 the block becomes a
function on its own script, and each fragment of the named package that the
block maps to (SECTIONS) calls it on the actor, through a cast that is None for
an actor without that script.

See: docs/fork/fo4_script_compile.md#package-events
"""

import re

from script_convert.constants import FALLOUT4_WALK_PREFIX
from script_convert.say_to_done import script_name
from script_convert.target import is_fallout4
from fo4_import.spike.conditions import parse, raws
from tes5_import.packages.scripts_falloutnv import DIALOGUE_TYPE, package_sections, says_to_player

#: The Int property holding a SayTo package's number (GreetOnce), its DialogueDone mark once its walk-up starts.
WALK_DONE = 'TES4WalkDone'
#: The FNV Trigger Location of a SayTo (PLD2 type, -1: none; its form; its radius) its walk-up waits for the player in.
WALK_PLACE, WALK_TRIGGER, WALK_REACH = 'TES4WalkPlace', 'TES4WalkTrigger', 'TES4WalkReach'
#: Block type: the package fragments it runs in (Done on completion, Change on leaving it, End on either).
SECTIONS = {'onpackagestart': ('OnBegin',), 'onpackagedone': ('OnEnd',), 'onpackageend': ('OnEnd', 'OnChange'),
            'onpackagechange': ('OnChange',)}

#: The Faction property a day_marked package's OnEnd puts its actor in (Packages: one hidden FACT per package).
DAY_DONE = 'TES4DayDone'
#: FO3/FNV PKDT flag Once Per Day; the condition functions testing a quest.
ONCE_PER_DAY = 0x400
QUEST_TESTS = frozenset({'GetStage', 'GetStageDone', 'GetQuestRunning', 'GetQuestCompleted', 'GetQuestVariable',
                         'GetObjectiveCompleted', 'GetObjectiveDisplayed'})

#: `begin <package block> <package>`.
_BEGIN_RE = re.compile(r'(?im)^[ \t]*begin[ \t]+(onpackage(?:start|done|end|change))\b[ \t]+(\w+)')


def function_name(btype: str, package: str) -> str:
    """The Papyrus function a `begin <btype> <package>` block becomes."""
    return f'TES4_{btype.lower()}_{package.lower()}'


def block_header(block) -> tuple:
    """(opener, closer) of the function a package block becomes."""
    return f'Function {function_name(block.btype, re.match(r"\w+", block.filter).group(0))}()', 'EndFunction'


def quest_gated(rec: dict) -> bool:
    """Whether a condition of FO3/FNV package `rec` tests a quest (QUEST_TESTS)."""
    return any(parse(raw)['func'] in QUEST_TESTS for raw in raws(rec))


def day_marked(rec: dict) -> bool:
    """Whether non-Dialogue package `rec` is quest-gated Once Per Day.
    See: docs/fork/fo4_pipeline.md#once-per-day
    """
    once = int(rec.get('PKDT.Flags', 0) or 0) & ONCE_PER_DAY
    return bool(once) and rec.get('PKDT.Type') != DIALOGUE_TYPE and quest_gated(rec)


def day_done(rec: dict, section: str) -> tuple:
    """({property: type}, FO4 OnEnd lines) marking day_marked `rec` done."""
    if section != 'OnEnd' or not is_fallout4() or not day_marked(rec):
        return {}, []
    return {DAY_DONE: 'Faction'}, [f'  TES4Polyfill.PackageDone(akActor, {DAY_DONE})']


def walk_up(rec: dict, end: 'str | None' = None) -> tuple:
    """({property: type}, fragment lines) a SayTo package to the player adds to its OnBegin: its walk-up scene once
    the player is in its trigger area, then its `end` fragment function (its OnEnd, None: none) once the scene has
    played, as FO3/FNV end a SayTo once its line is said.
    See: docs/fork/fo4_pipeline.md#say-to-packages
    """
    if not says_to_player(rec):
        return {}, []
    scene = FALLOUT4_WALK_PREFIX + rec['FormID'].upper()
    call = f'TES4Polyfill.WalkUp(akActor, Self, {scene}, {WALK_DONE}, {WALK_PLACE}, {WALK_TRIGGER}, {WALK_REACH})'
    lines = [f'  If {call}', f'    {end}(akActor)', '  EndIf'] if end else [f'  {call}']
    return {scene: 'Scene', WALK_DONE: 'Int', WALK_PLACE: 'Int', WALK_TRIGGER: 'Form', WALK_REACH: 'Float'}, lines


def package_hooks(scripts, packages) -> dict:
    """{PACK FormID (upper hex): {section: [(script name, function)]}} of `scripts`' package blocks (SCPT records)
    naming `packages` (PACK records); a SayTo package to the player also gets an OnBegin (walk_up).
    See: docs/fork/fo4_pipeline.md#say-to-packages
    """
    by_name = {(r.get('EditorID') or '').lower(): (r.get('FormID') or '').upper() for r in packages}
    hooks = {}
    for rec in scripts:
        for btype, package in _BEGIN_RE.findall((rec.get('SCTX') or '').replace('\\r\\n', '\n')):
            call = (script_name(rec), function_name(btype, package))
            for section in SECTIONS[btype.lower()] if package.lower() in by_name else ():
                calls = hooks.setdefault(by_name[package.lower()], {}).setdefault(section, [])
                calls += [call] if call not in calls else []
    for rec in packages:
        own = [('OnBegin',)] * says_to_player(rec) + [('OnEnd',)] * day_marked(rec)
        for section, in own:
            hooks.setdefault((rec.get('FormID') or '').upper(), {}).setdefault(section, [])
    return hooks


def package_work(by_type: dict) -> list:
    """[(PACK record, its section hooks)] of `by_type`'s packages with a fragment to write; hooks on Fallout 4 only."""
    packs = by_type.get('PACK', ())
    hooks = package_hooks(by_type.get('SCPT', ()), packs) if is_fallout4() else {}
    pairs = [(rec, hooks.get((rec.get('FormID') or '').upper(), {})) for rec in packs]
    return [(rec, hooked) for rec, hooked in pairs if package_sections(rec, hooked)]
