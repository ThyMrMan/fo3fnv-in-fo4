"""FO3/FNV `begin SayToDone <topic>`: the speaker's script runs a block as its line ends.

Skyrim has no such event. The block becomes a function on its own script, and
every INFO End fragment of the topic calls it on the speaker, through a cast
that is None for any speaker without that script. A block naming no topic runs
after any SayTo the actor finishes, whichever script started it (Lucas Simms'
greeting is a package's `sayTo`), so it is hooked to every topic its script
names and every topic anything says with SayTo.

See: docs/commentary/script_convert.md#saytodone
"""

import re

from script_convert.constants import papyrus_script_name, sanitize_name
from script_convert.target import is_fallout4

#: `begin SayToDone [topic]`, the topic group empty when the block names none.
_BEGIN_RE = re.compile(r'(?im)^[ \t]*begin[ \t]+saytodone\b[ \t]*(\w*)')

#: Any identifier, for the topics a topic-less block's script names.
_WORD_RE = re.compile(r'\w+')

#: The block type as the parser lowercases it.
BLOCK_TYPE = 'saytodone'

#: FO4 says bookkeeping: the end fragment's wait, and the call that asks for a line.
_SETTLED, _SAY_CALL = '  TES4Polyfill.SaysSettled()', 'TES4Polyfill.SayWhenFree('
#: A block's hold flag: declared, taken before each ask (for its speaker), released before each Return and at the end.
_HELD = 'TES4_SaysHeld'
_DECLARE, _RELEASE = f'Bool {_HELD} = False', f'TES4Polyfill.ReleaseSays({_HELD})'
_OPENER = re.compile(r'^(Function|Event) ')
_CLOSERS = frozenset({'EndFunction', 'EndEvent'})
_RETURN_RE = re.compile(r'^(\s*)Return\b')


def function_name(topic: str) -> str:
    """The Papyrus function a SayToDone block on `topic` ('' for none) becomes."""
    return f'TES4_SayToDone_{topic.lower()}' if topic else 'TES4_SayToDone'


def block_header(block) -> tuple:
    """(opener, closer) of the function a SayToDone block becomes."""
    match = _WORD_RE.match(block.filter or '')
    return f'Function {function_name(match.group(0) if match else "")}()', 'EndFunction'


def engine_topics(dials: list) -> set:
    """EditorIDs (lower) of the engine's own topics, FormID below 0x800: GREETING, HELLO, Attack.

    The engine barks them too, so their line ending says nothing about a SayTo.
    See: docs/commentary/script_convert.md#saytodone
    """
    return {(r.get('EditorID') or '').strip().lower() for r in dials
            if int(r.get('FormID') or '0', 16) & 0xFFFFFF < 0x800}


def _hooked_topics(text: str, dial_edids: set, said_to=(), engine=()) -> dict:
    """{topic EditorID (lower): function} for one script's SayToDone blocks.

    A topic-less block takes the topics its script names and the `said_to`
    (SayTo) topics, `engine` topics excluded.
    """
    out = {}
    for topic in _BEGIN_RE.findall(text):
        if topic:
            out[topic.lower()] = function_name(topic)
            continue
        for word in [w.lower() for w in _WORD_RE.findall(text)] + sorted(said_to):
            if word in dial_edids and word not in engine:
                out.setdefault(word, function_name(''))
    return out


def say_to_done_topics(scpt_records: list, dials: list, said_to=()) -> set:
    """Topic EditorIDs (lower) some script's SayToDone waits on."""
    dial_edids = {(r.get('EditorID') or '').strip().lower() for r in dials} - {''}
    engine = engine_topics(dials)
    return {topic for rec in scpt_records
            for topic in _hooked_topics(rec.get('SCTX') or '', dial_edids, said_to, engine)
            if topic in dial_edids}


def script_name(rec: dict) -> str:
    """The Papyrus name of FO3/FNV SCPT `rec`'s converted script."""
    return papyrus_script_name(sanitize_name(rec.get('EditorID') or f'Script_{rec.get("FormID", "")}'))


def say_to_done_hooks(by_type: dict, said_to=()) -> dict:
    """{DIAL FormID (upper hex, as INFO.ParentDIAL): [(script name, function)]}; `said_to` are the SayTo topics."""
    dial_fid = {(r.get('EditorID') or '').strip().lower(): (r.get('FormID') or '').upper()
                for r in by_type.get('DIAL', ())}
    dial_fid.pop('', None)
    dial_edids = set(dial_fid)
    engine = engine_topics(by_type.get('DIAL', ()))
    hooks = {}
    for rec in by_type.get('SCPT', ()):
        for topic, func in _hooked_topics(rec.get('SCTX') or '', dial_edids, said_to, engine).items():
            if topic in dial_fid:
                hooks.setdefault(dial_fid[topic], []).append((script_name(rec), func))
    return hooks


def settled_says() -> list:
    """An FO4 INFO end fragment's wait for scripts still asking for lines."""
    return [_SETTLED] if is_fallout4() else []


def held_says(lines: list) -> list:
    """Fallout 4 script `lines` with each function or event that calls SayWhenFree holding the count SaysSettled
    waits on while it runs (_held).
    See: docs/fork/fo4_pipeline.md#says-settled
    """
    if not is_fallout4():
        return lines
    out, body = [], None
    for line in lines:
        if body is None:
            out.append(line)
            body = [] if _OPENER.match(line) and not line.rstrip().endswith(' Native') else None
        elif line in _CLOSERS:
            out += _held(body) + [line]
            body = None
        else:
            body.append(line)
    return out + (body or [])


def _held(body: list) -> list:
    """A body calling SayWhenFree taking the hold at its first ask and releasing it, if taken, before each Return and
    at its end; any other body as it is."""
    if not any(_SAY_CALL in line for line in body):
        return body
    at = next((i + 1 for i, line in enumerate(body) if line == _SETTLED), 0)
    out = body[:at] + ['  ' + _DECLARE]
    for line in body[at:]:
        indent = line[:len(line) - len(line.lstrip())]
        if _SAY_CALL in line:
            out.append(f'{indent}{_HELD} = TES4Polyfill.HoldSays({_HELD}, {_speaker(line)})')
        elif _RETURN_RE.match(line):
            out.append(indent + _RELEASE)
        out.append(line)
    return out + ['  ' + _RELEASE]


def _speaker(line: str) -> str:
    """The first argument (the speaker) of the SayWhenFree call in `line`."""
    text, depth = line[line.index(_SAY_CALL) + len(_SAY_CALL):], 0
    for i, char in enumerate(text):
        depth += (char == '(') - (char == ')')
        if depth < 0 or (char == ',' and depth == 0):
            return text[:i].strip()
    return text.strip()


def fragment_calls(hooks, subject: str = 'akSpeakerRef') -> list:
    """Fragment lines running each hooked (script, function) on `subject`, cast to that script."""
    out = []
    for i, (script, func) in enumerate(hooks):
        out += [f'  {script} TES4_Done{i} = {subject} as {script}',
                f'  If TES4_Done{i}', f'    TES4_Done{i}.{func}()', '  EndIf']
    return out
