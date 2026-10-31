"""Every write of a fact in FNV and in the build, and whether each FNV write lands on the same trigger.

A write is a fact (a stage set; a quest started, stopped or completed; a topic
added; an objective shown, hidden or completed) on a trigger. FNV writes come
from stage result scripts, line begin and end scripts and Add Topics lists,
package sections, terminal items and script blocks. The build's come from the
converted fragments and events, read from their sources.

See: docs/fork/fo4_timing_audit.md#writers
"""

import re
from dataclasses import dataclass
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from script_convert.constants import papyrus_script_name
from tools.validate.preflight.quest_converted import strip_papyrus_comment
from tools.validate.preflight.quest_progression import converted_name, fragment_scope
from tools.validate.preflight.quest_source import START, script_lines, strip_comment

#: An FNV command that writes a fact, its first argument and up to two numbers after it.
_COMMAND = re.compile(r'\b(setstage|startquest|stopquest|completequest|addtopic|setobjectivedisplayed'
                      r'|setobjectivecompleted)[\s,]+(\w+)((?:[\s,]+-?\d+){0,2})', re.I)

#: An FNV `Begin` line and its block kind.
_BEGIN = re.compile(r'^\s*begin\s+(\w+)', re.I)

#: The start of a Papyrus function or event.
_FUNCTION = re.compile(r'^\s*(?:\w+\s+)?(?:function|event)\s+(\w+)', re.I)

#: Converted Stop, CompleteQuest and objective calls; the quest expression is absent for the script's own quest.
_STOP = re.compile(r'(?:([\w.()]+)\.)?(?<![\w])(Stop|CompleteQuest)\(\s*\)')
_OBJECTIVE = re.compile(r'(?:([\w.()]+)\.)?(?<![\w])SetObjective(Displayed|Completed)\(\s*(\d+)\s*(?:,\s*(\w+))?')

#: A global set to 1 through a script property: the build's AddTopic.
_SET_ONE = re.compile(r'\b(\w+)\.SetValue\(\s*1(?:\.0)?\s*\)')

#: A converted SetObjective call the converter left as a comment, and why.
_INERT_OBJECTIVE = re.compile(r';NE:\s*setobjective(displayed|completed)\s+(\w+)\s+(\d+)(.*)', re.I)

#: The header the converter writes over a source block it keeps only as comments.
_DEAD_BLOCK = re.compile(r'tes4\s*`\s*begin\s+(\w+)', re.I)

#: FNV block kinds and the converted functions their code runs in (each confirmed on the whole-map build).
BLOCK_EVENTS = {
    'gamemode': ('ontimer',), 'scripteffectupdate': ('ontimer',),
    'menumode': ('tes4_messageboxclosed', 'onmenuopencloseevent', 'tes4_menumode', 'tes4_menupass'),
    'ondeath': ('ondeath',), 'onmurder': ('ondeath',), 'ontriggerenter': ('ontriggerenter',),
    'ontriggerleave': ('ontriggerleave',), 'ontrigger': ('tes4_ontriggerbody',), 'onhit': ('onhit',),
    'onhitwith': ('onhit',), 'onactivate': ('onactivate',), 'onload': ('onload',), 'onreset': ('onreset',),
    'onstartcombat': ('oncombatstatechanged',), 'oncombatend': ('oncombatstatechanged',),
    'onadd': ('oncontainerchanged',), 'ondrop': ('oncontainerchanged',), 'onequip': ('onequipped',),
    'onunequip': ('onunequipped',), 'saytodone': ('tes4_saytodone',), 'onopen': ('onopen',), 'onclose': ('onclose',),
    'ondestructionstagechange': ('ondestructionstagechanged',), 'scripteffectstart': ('oneffectstart',),
    'scripteffectfinish': ('oneffectfinish',), 'onpackagestart': ('onpackagestart',),
    'onpackagedone': ('onpackageend',), 'onpackageend': ('onpackageend',), 'onpackagechange': ('onpackagechange',),
    'ongrab': ('ongrab',), 'onrelease': ('onrelease',), 'onmagiceffecthit': ('onmagiceffectapply',),
    'onfire': ('onanimationevent',), 'onactorequip': ('onitemequipped',),
}

#: Line halves and the fragment each runs in; the Add Topics list applies with the line.
INFO_HALVES = {'begin': ('fragment_1',), 'end': ('fragment_0',), 'list': ('fragment_1', 'fragment_0')}

#: The test a converted poll runs MenuMode code behind; a poll with or without it keeps a MenuMode block (rule 5).
MENU_BRANCH = 'inmenumode()'

#: FNV stage log entry flag: finishing the stage completes the quest.
COMPLETES_QUEST = 0x01

#: Script lines that do nothing a converted script must keep: blank, or passing activation on.
_TRIVIAL = re.compile(r'^\s*(?:activate\s*;?)?\s*$', re.I)


@dataclass(frozen=True)
class Write:
    """One FNV write: its fact, the container kind and owner, and the trigger part (the quest audit's Setter shape)."""

    fact: tuple
    kind: str
    owner: str
    part: str
    raw: str = ''


def _fact(command: str, name: str, numbers: list, quests: dict, topics: set):
    """The fact one FNV command writes, or None when it names nothing the game holds or a stage is computed."""
    command, name = command.lower(), name.lower()
    if command == 'addtopic':
        return ('topic', name) if name in topics else None
    if name not in quests:
        return None
    if command == 'setstage':
        return ('stage', name, numbers[0]) if numbers else None
    if command.startswith('setobjective'):
        shown = numbers[1] != 0 if len(numbers) > 1 else True
        return (('objshown' if command.endswith('displayed') else 'objdone'), name, numbers[0], shown) \
            if numbers else None
    return {'startquest': 'start', 'stopquest': 'stop', 'completequest': 'complete'}[command], name


def find_writes(text: str, quests: dict, topics: set) -> list:
    """[(fact, block, raw line)] of the uncommented writes in one FNV script text."""
    out, block = [], ''
    for line in script_lines(text):
        code = strip_comment(line)
        begin = _BEGIN.match(code)
        block = begin.group(1).lower() if begin else block
        for command, name, rest in _COMMAND.findall(code):
            fact = _fact(command, name, [int(n) for n in re.findall(r'-?\d+', rest)], quests, topics)
            out += [(fact, block, line.strip())] if fact else []
    return out


class SourceWrites:
    """Every write in an FNV export, and every container that can hold one (by converted script name)."""

    def __init__(self, export_dir, source, prefix: str):
        """Read SourceGame `source`'s writes; `prefix` heads converted script names."""
        self.source, self.prefix, self.writes, self.containers, self.texts = source, prefix, [], {}, {}
        self.objectives = {}
        self.topics = {edid.lower() for edid, _t, _f in source.dials.values() if edid}
        self._read(Path(export_dir))

    def _add(self, kind: str, owner: str, part: str, text: str) -> None:
        """Record one script text's writes; a script block is its own part."""
        for fact, block, raw in find_writes(text, self.source.quests, self.topics):
            self.writes.append(Write(fact, kind, owner, block if kind == 'script' else part, raw))

    def _container(self, kind: str, owner: str) -> None:
        """Remember a container by the converted script that holds its code."""
        self.containers[self.script(Write((), kind, owner, ''))] = (kind, owner)

    def _read(self, export_dir: Path) -> None:
        """Every container of the export, and its writes."""
        for rec in export_records(export_dir, 'QUST'):
            self._quest(rec)
        for rec in export_records(export_dir, 'INFO'):
            self._info(rec)
        for rec in export_records(export_dir, 'PACK'):
            self._container('package', rec['FormID'].upper())
            for section in ('OnBegin', 'OnEnd', 'OnChange'):
                self._add('package', rec['FormID'].upper(), section, rec.get(f'{section}.Script', ''))
        for rec in export_records(export_dir, 'TERM'):
            self._container('terminal', rec['FormID'].upper())
            for i in range(_count(rec, 'Item', 'Text')):
                self._add('terminal', rec['FormID'].upper(), str(i), rec.get(f'Item[{i}].Script', ''))
        for rec in export_records(export_dir, 'SCPT'):
            if rec.get('EditorID'):
                self.texts[rec['EditorID'].lower()] = rec.get('SCTX', '')
                self._container('script', rec['EditorID'])
                self._add('script', rec['EditorID'], '', rec.get('SCTX', ''))

    def _quest(self, rec: dict) -> None:
        """A quest's stage result scripts, each the container of its stage."""
        edid = rec.get('EditorID', '')
        self._container('stage', f'{edid}|0')
        self.objectives[edid.lower()] = {int(rec[f'Objective[{k}].Index']) for k in range(_count(rec, 'Objective', 'Index'))}
        for i in range(_count(rec, 'Stage', 'Index')):
            stage = int(rec[f'Stage[{i}].Index'])
            for j in range(int(rec.get(f'Stage[{i}].LogCount', 0) or 0)):
                self._add('stage', f'{edid}|{stage}', '', rec.get(f'Stage[{i}].Log[{j}].ResultScript', ''))
                if int(rec.get(f'Stage[{i}].Log[{j}].Flags', 0) or 0) & COMPLETES_QUEST:
                    self.writes.append(Write(('complete', edid.lower()), 'stage', f'{edid}|{stage}', '',
                                             'Complete Quest flag'))

    def _info(self, rec: dict) -> None:
        """A line's begin and end scripts and its Add Topics list."""
        owner = rec['FormID'].upper()
        self._container('info', owner)
        self._add('info', owner, 'begin', rec.get('ResultScript', ''))
        self._add('info', owner, 'end', rec.get('ResultScriptEnd', ''))
        own = int(rec.get('ParentDIAL', '0') or '0', 16)
        for i in range(_count(rec, 'AddTopic', '')):
            topic = int(rec[f'AddTopic[{i}]'], 16)
            edid = self.source.dials.get(topic, ('',))[0].lower() if topic != own else ''
            self.writes += [Write(('topic', edid), 'info', owner, 'list', 'Add Topics')] if edid else []

    def script(self, write: Write) -> str:
        """The converted script (lower) that holds a write's container."""
        if write.kind == 'terminal':
            return f'{self.prefix}TM__{write.owner}'.lower()
        if write.kind == 'script':
            return papyrus_script_name(write.owner, self.prefix).lower()
        return converted_name(write, self.prefix)


def _count(rec: dict, prefix: str, field: str) -> int:
    """How many `prefix[i].field` (or `prefix[i]` when `field` is empty) keys `rec` holds from 0."""
    n = 0
    while (f'{prefix}[{n}].{field}' if field else f'{prefix}[{n}]') in rec:
        n += 1
    return n


def built_writes(text: str, script: str, ctx, gates: dict) -> list:
    """[(fact, function)] of one converted script's writes; `gates` is {unlock global FormID: {topic EditorID}}."""
    calls = ctx.scripts.get(script)
    out = [((('start', q) if c.stage == START else ('stage', q, c.stage)), c.function)
           for c in (calls.calls if calls else ()) for q in [ctx.resolve(c.quest_expr, script)] if q]
    function, props = '', ctx.index.script_props.get(script, {})
    for line in text.splitlines():
        match = _FUNCTION.match(line)
        function = match.group(1).lower() if match else function
        code = strip_papyrus_comment(line)
        for expr, verb in _STOP.findall(code):
            quest = ctx.resolve(expr.lower(), script)
            out += [(('stop' if verb == 'Stop' else 'complete', quest), function)] if quest else []
        for expr, kind, number, flag in _OBJECTIVE.findall(code):
            quest = ctx.resolve(expr.lower(), script)
            fact = ('objshown' if kind == 'Displayed' else 'objdone', quest, int(number), flag.lower() not in ('0', 'false'))
            out += [(fact, function)] if quest else []
        for prop in _SET_ONE.findall(code):
            out += [(('topic', t), function) for t in gates.get(props.get(prop.lower()), ())]
    return out


def inert_objectives(text: str) -> dict:
    """{(fact kind, quest, objective): why} for SetObjective commands the converter kept only as comments."""
    out = {}
    for kind, quest, number, why in _INERT_OBJECTIVE.findall(text):
        out[('objshown' if kind.lower() == 'displayed' else 'objdone', quest.lower(), int(number))] = why.strip(' -')
    return out


def expected(write: Write, ctx):
    """A test of whether a converted function is where an FNV write's trigger runs."""
    if write.kind in ('stage', 'package'):
        return fragment_scope(write, ctx)
    if write.kind == 'info':
        return lambda function: function in INFO_HALVES[write.part]
    if write.kind == 'terminal':
        return lambda function: function == f'fragment_terminal_{int(write.part) + 1:02d}'
    names = BLOCK_EVENTS.get(write.part, ())
    return lambda function: any(function.startswith(n) for n in names)


def blocks(text: str) -> list:
    """[(block kind, has code)] of an FNV script: code is anything but blanks, comments and a plain Activate."""
    out = []
    for line in script_lines(text):
        code = strip_comment(line)
        begin = _BEGIN.match(code)
        if begin:
            out.append([begin.group(1).lower(), False])
        elif out and not re.match(r'^\s*end\b', code, re.I) and not _TRIVIAL.match(code):
            out[-1][1] = True
    return [tuple(b) for b in out]


def block_state(kind: str, text: str) -> str:
    """'handler' when a converted script has a function for FNV block `kind`, 'comment' when kept as comments, else ''."""
    functions = {m.group(1).lower() for m in map(_FUNCTION.match, text.splitlines()) if m}
    if any(f.startswith(n) for f in functions for n in BLOCK_EVENTS.get(kind, ())):
        return 'handler'
    if kind == 'menumode' and (MENU_BRANCH in text.lower() or 'ontimer' in functions):
        return 'handler'
    return 'comment' if kind in {b.lower() for b in _DEAD_BLOCK.findall(text)} else ''
