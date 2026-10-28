"""Fallout 4's dialogue model over a built plugin: which scenes start, which topics they play, which lines speak.

A topic is reachable when the engine plays it on its own (any subtype but
scene and custom), when a script property names it, or when a reachable
scene's action names it. A scene is reachable when it begins on quest start,
when a script property names it, when a reachable line starts it (TSCE), or
when a reachable scene's Start Scene action names it. A line speaks when its
topic is reachable and a placed actor passes its GetIsID tests.

The FormID ledger maps each source line to its built copies.

See: docs/fork/fo4_preflight.md#fo4-dialogue
"""

import json
import re
import struct
from collections import defaultdict
from pathlib import Path

from fo4_import.spike.readiness import LINE_LEFT_OUT
from tools.validate.preflight.plugin_index import every, first, u32, zstring
from tools.validate.preflight.quest_source import decode_condition, speakable

#: Topic subtypes a scene or a script plays; the engine plays every other one by itself.
_SCENE_PLAYED = ('SCEN', 'CUST')

#: SCEN FNAM flag: the scene begins when its quest starts.
_BEGIN_ON_QUEST_START = 0x01

#: Scene action types whose DATA is a topic: Dialogue and Radio.
_DATA_TOPIC_ACTIONS = (0, 6)

#: Scene action subrecords that name a topic in Player Dialogue, NPC Response and Start Scene actions.
_ACTION_TOPICS = frozenset({'PTOP', 'NTOP', 'NETO', 'QTOP', 'NPOT', 'NNGT', 'NNUT', 'NQUT', 'STSC'})

#: A ledger key of a built copy of a source line: `INFO <source FormID> <response part> ...`, quoted.
_LINE_KEY = re.compile(r'''^["']INFO ([0-9A-Fa-f]{8}) (\d+)\b''')


def scene_actions(scene) -> tuple:
    """({topics}, {scenes}) the actions of one SCEN name."""
    topics, scenes, action = set(), set(), None
    for sub in scene.subrecords:
        if sub.type == 'ANAM':
            action = struct.unpack_from('<H', sub.data)[0] if len(sub.data) >= 2 else None
            continue
        if action is not None and (sub.type in _ACTION_TOPICS or sub.type == 'DATA' and action in _DATA_TOPIC_ACTIONS):
            topics.add(u32(sub.data))
        if action is not None and sub.type == 'LCEP':
            scenes.add(u32(sub.data))
    return topics - {0}, scenes - {0}


class Fo4Dialogue:
    """Reachable scenes and topics of a built Fallout 4 plugin, and why a line cannot speak."""

    def __init__(self, index):
        """Read topics, scenes, lines and placed actors from a PluginIndex, then solve reachability."""
        self.index = index
        self.present = index.placed_bases()
        self.subtype = {r.form_id: zstring(first(r, 'SNAM'))[:4] for r in index.by_type['DIAL']}
        self.actions = {r.form_id: scene_actions(r) for r in index.by_type['SCEN']}
        self.starts = defaultdict(list)
        for rec in index.by_type['INFO']:
            self.starts[rec.parent_dial] += [(rec, u32(data)) for data in every(rec, 'TSCE')]
        self.scenes, self.live = self._reachable()

    def _seeds(self) -> tuple:
        """(scenes, topics) reachable before any link: quest-start scenes, engine topics, script properties."""
        named = {target for _script, _prop, target in self.index.object_props}
        scenes = {r.form_id for r in self.index.by_type['SCEN'] if u32(first(r, 'FNAM')) & _BEGIN_ON_QUEST_START}
        scenes |= named & set(self.actions)
        topics = {fid for fid, sub in self.subtype.items() if sub not in _SCENE_PLAYED}
        return scenes, topics | (named & set(self.subtype))

    def _started_by(self, dial: int) -> set:
        """The scenes a speakable line of topic `dial` starts."""
        return {scene for rec, scene in self.starts.get(dial, ()) if self.line_speakable(rec)}

    def _reachable(self) -> tuple:
        """(reachable scenes, reachable topics) by a fixed point over scene actions and lines' TSCE."""
        scenes, topics = self._seeds()
        pending, done = set(scenes).union(*map(self._started_by, topics)), set()
        while pending:
            scene = pending.pop()
            done.add(scene)
            named_topics, named_scenes = self.actions.get(scene, (set(), set()))
            pending |= set().union(*map(self._started_by, named_topics - topics))
            topics |= named_topics
            pending = (pending | named_scenes) - done
        return done, topics

    def conditions(self, rec) -> list:
        """The decoded CTDAs of one built INFO."""
        return [decode_condition(data) for data in every(rec, 'CTDA')]

    def line_speakable(self, rec) -> bool:
        """Whether a placed actor passes the line's GetIsID tests."""
        return speakable(self.conditions(rec), self.present)

    def reachable_info(self, fid: int) -> str:
        """'' when the built INFO `fid` can be spoken, else why it cannot."""
        rec = self.index.by_fid.get(fid)
        if rec is None or rec.type != 'INFO':
            return 'the INFO is missing from the built plugin'
        if rec.parent_dial not in self.live:
            kind = 'in no scene that starts' if self.subtype.get(rec.parent_dial) == 'SCEN' else 'never played'
            return f'its topic {self.index.edid(rec.parent_dial) or hex(rec.parent_dial)} is {kind}'
        if not self.line_speakable(rec):
            return 'no placed actor passes its GetIsID condition'
        return ''


def _is_info(index, fid: int) -> bool:
    """Whether the plugin holds an INFO at `fid`."""
    return getattr(index.by_fid.get(fid), 'type', '') == 'INFO'


def line_parts(index, ledger: Path, source_infos) -> dict:
    """{source INFO FormID: {response part: [built INFO FormIDs]}}.

    Copies come from the ledger, plus the INFO kept at the source FormID (a
    first response).
    """
    own, parts = len(index.masters) << 24, defaultdict(lambda: defaultdict(list))
    path = Path(ledger)
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    for row in (line.split('\t') for line in lines):
        match = _LINE_KEY.match(row[2]) if len(row) == 4 else None
        if match and _is_info(index, own | int(row[3], 16)):
            parts[int(match.group(1), 16)][int(match.group(2))].append(own | int(row[3], 16))
    for fid in source_infos:
        kept = own | (fid & 0xFFFFFF)
        if _is_info(index, kept) and kept not in parts[fid][1]:
            parts[fid][1].append(kept)
    return parts


def line_copies(parts: dict) -> dict:
    """{source INFO: [built INFOs]}; [] for a line whose first response is not built."""
    return {fid: [f for group in by_part.values() for f in group] if by_part.get(1) else []
            for fid, by_part in parts.items()}


def left_out(report: Path) -> dict:
    """{source INFO FormID hex: why} from the build's readiness report: the lines it left out and their condition."""
    path = Path(report)
    entries = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
    return {e['detail'].split(' ', 1)[0].upper(): 'the build left it out (' + e['detail'].split('(', 1)[-1]
            for e in entries if e['kind'] == LINE_LEFT_OUT and '(' in e['detail']}
