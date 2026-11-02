"""XDI menus that can show only "dialogueentry", by XDI 1.4.4's rules (its DLL and DialogueMenu.swf).

XDI lists one option per player line with content (responses, or a shared line) in a Player Dialogue action's
four player topics, enabled while its conditions pass. The menu keeps the enabled options with a response; with
none it lists the engine's button strings, which show the list entry's default text, "dialogueentry". So:
* a menu none of whose player lines has content always shows it;
* a listed line with no response text never shows;
* a listed line with FO4's Say Once drops once said, and can leave the menu empty;
* a menu opened by a line whose speaker no option's speaker test (GetIsID on the Target) admits shows it;
* a Greeting line opening its scene by TSCE leaves every later talk menu-less once a run is left playing.

See: docs/commentary/tools_preflight.md#xdi-menus
"""

import struct
from collections import defaultdict

from tools.validate.preflight.findings import Finding
from tools.validate.preflight.plugin_index import every, first, u32, zstring
from tools.validate.preflight.quest_source import decode_condition

#: A Player Dialogue action's four player topics, in record order.
PLAYER_TOPICS = ('PTOP', 'NTOP', 'NETO', 'QTOP')

#: FO4 INFO ENAM flag Say Once.
_SAY_ONCE = 0x0004

#: FO4 GetIsID, and the CTDA Run On values for the subject and target.
_IS_ID, _SUBJECT, _TARGET = 72, 0, 1

#: CTDA operator bits (compare type) and the OR flag.
_COMPARE, _OR = 0xE0, 0x01

#: Lines listed per finding.
SAMPLES = 5


def menus(index) -> list:
    """[(scene, phase index, [player topic FormIDs])] of every Player Dialogue action."""
    return [menu for scene in index.by_type['SCEN'] for menu in _scene_menus(scene)]


def _scene_menus(scene) -> list:
    """[(scene, start phase, [player topic FormIDs])] of `scene`'s Player Dialogue actions."""
    out, phase = [], 0
    for sub in scene.subrecords:
        if sub.type == 'SNAM' and len(sub.data) == 4:
            phase = u32(sub.data)
        elif sub.type == 'PTOP':
            out.append((scene, phase, [u32(sub.data)]))
        elif sub.type in PLAYER_TOPICS[1:] and out:
            out[-1][2].append(u32(sub.data))
    return out


def resolved(index, info):
    """The line `info` shows: itself, or the end of its shared-line (DNAM) chain."""
    seen = set()
    while u32(first(info, 'DNAM')) in index.by_fid and info.form_id not in seen:
        seen.add(info.form_id)
        info = index.by_fid[u32(first(info, 'DNAM'))]
    return info


def listed(info) -> bool:
    """Whether XDI lists player line `info`: it has responses or a shared line."""
    return bool(every(info, 'TRDA') or every(info, 'NAM1') or u32(first(info, 'DNAM')))


def _response(index, info) -> str:
    """The first response text of the line `info` shows."""
    return next((zstring(text) for text in every(resolved(index, info), 'NAM1') if zstring(text)), '')


def _say_once(info) -> bool:
    """Whether `info` carries FO4's Say Once flag (ENAM)."""
    enam = first(info, 'ENAM')
    return len(enam) >= 2 and bool(struct.unpack_from('<H', enam)[0] & _SAY_ONCE)


def speakers(info, run_on: int) -> set:
    """NPCs `info`'s GetIsID == 1 tests on `run_on` admit; empty: anyone."""
    conds = [decode_condition(c) for c in every(info, 'CTDA')]
    return {c[3] for c in conds if c[2] == _IS_ID and c[4] == run_on and c[1] == 1.0 and not c[0] & _COMPARE}


def _named(info) -> 'int | None':
    """The NPC `info` must be said by: a GetIsID == 1 on the subject alone in its condition group, else None."""
    group, alone = [], []
    for raw in every(info, 'CTDA'):
        group.append(decode_condition(raw))
        if not group[-1][0] & _OR:
            alone += group if len(group) == 1 else []
            group = []
    return next((c[3] for c in alone if c[2] == _IS_ID and c[4] == _SUBJECT and c[1] == 1.0
                 and not c[0] & _COMPARE), None)


def _openers(index) -> dict:
    """{scene FormID: [lines starting it (TSCE)]}."""
    out = defaultdict(list)
    for info in index.by_type['INFO']:
        if u32(first(info, 'TSCE')):
            out[u32(first(info, 'TSCE'))].append(info)
    return out


def _unadmitted(index, options: list, openers: list) -> list:
    """['opener FormID by NPC'] for each line in `openers` whose named speaker no option in `options` admits."""
    admitted = [speakers(o, _TARGET) for o in options]
    if any(not names for names in admitted):
        return []
    rows = []
    for opener in openers:
        npc = _named(opener)
        if npc and not any(npc in names for names in admitted):
            rows.append(f'{opener.form_id:08X} by {index.edid(npc) or f"{npc:08X}"}')
    return rows


def _menu_rows(index, topics: list, by_topic: dict, openers: list, started: bool) -> dict:
    """{kind: rows} of one menu's ways to show only "dialogueentry"; `openers` start its scene at it, and it is
    `started` when they do or an earlier phase leads to it."""
    options = [info for topic in topics for info in by_topic.get(topic, ()) if listed(info)]
    if not options:
        return {'no option' if started else 'no option, nothing starts it': ['no player line has content']}
    return {'blank option': [f'{o.form_id:08X}' for o in options if not _response(index, o)],
            'say once option': [f'{o.form_id:08X}' for o in options if _say_once(o)],
            'no option for its speaker': _unadmitted(index, options, openers)}


#: Finding severity per kind: a menu nothing starts cannot be seen.
_SEVERITY = {'no option, nothing starts it': 'review'}


def tsce_greetings(game: str, index) -> list:
    """One error per Greeting-topic line opening its scene by TSCE: a run left playing blocks every later talk.
    See: docs/fork/fo4_pipeline.md#greeting-scene
    """
    greeting = {d.form_id for d in index.by_type['DIAL'] if first(d, 'SNAM') == b'GREE'}
    rows = [f'{i.form_id:08X}' for i in index.by_type['INFO'] if i.parent_dial in greeting and u32(first(i, 'TSCE'))]
    return [Finding('dialogue', f'dialogue|{game}|xdi-menu|greeting by TSCE', 'error',
                    f'{len(rows)} Greeting lines start their scene by TSCE, which a run left playing blocks: '
                    'every later talk shows only "dialogueentry"', tuple(rows[:SAMPLES]))] if rows else []


def audit(game: str, index) -> list:
    """One finding per (menu, kind) that can show only "dialogueentry"."""
    by_topic, starts = defaultdict(list), _openers(index)
    for info in index.by_type['INFO']:
        by_topic[info.parent_dial].append(info)
    out = tsce_greetings(game, index)
    for scene, phase, topics in menus(index):
        name = zstring(first(scene, 'EDID')) or f'{scene.form_id:08X}'
        openers = starts.get(scene.form_id, []) if phase == 0 else []
        for kind, rows in _menu_rows(index, topics, by_topic, openers, phase > 0 or bool(openers)).items():
            if rows:
                out.append(Finding('dialogue', f'dialogue|{game}|xdi-menu|{kind}|{name}|{phase}',
                                   _SEVERITY.get(kind, 'error'),
                                   f'{name} (phase {phase}): {kind}, so XDI shows only "dialogueentry"',
                                   tuple(rows[:SAMPLES])))
    return out
