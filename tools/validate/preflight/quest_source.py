"""Quest stage setters and dialogue reachability read from a source export.

Every `SetStage` in a quest stage result, an INFO result, a package section
or a script becomes a `Setter`. A stage number that is not a literal is kept
as None, so the audit marks it for review instead of guessing.

See: docs/commentary/tools_preflight.md#source-setters
"""

import os
import re
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tes5_import.base.text_reader import get_int, get_str, info_result_script, parse_export_file
from tools.validate.preflight.plugin_index import TALKERS

#: `SetStage Quest Stage`, with the space or comma separators FO3 allows.
SETSTAGE = re.compile(r'\bsetstage\s*[\s,]\s*(\w+)\s*[\s,]\s*([^\s;,]+)', re.I)

#: `StartQuest Quest`.
STARTQUEST = re.compile(r'\bstartquest\s*[\s,]\s*(\w+)', re.I)

#: The pseudo-stage a StartQuest site reaches, so quest starts ride the same graph as stages.
START = 'start'

#: `Begin OnFire` and the like: the block the following lines run in.
_BEGIN = re.compile(r'^\s*begin\s+(.+)$', re.I)

#: Commands whose arguments name a topic, which makes that topic reachable.
_TOPIC_COMMANDS = re.compile(r'\b(addtopic|say|sayto|startconversation|forcegreet)\b(.*)', re.I)
#: Of those, the ones that play one line of the topic and open no conversation (no Choices, no LinkFrom).
SAY_COMMANDS = frozenset({'say', 'sayto'})

#: The package sections that carry a script in FO3 and FNV.
PACKAGE_SECTIONS = ('OnBegin', 'OnEnd', 'OnChange')
#: Package fields naming a topic its actor says: a Dialogue package's, and each section's.
PACKAGE_TOPICS = ('PKDD.Topic',) + tuple(f'{section}.Topic' for section in PACKAGE_SECTIONS)
#: DIAL type Conversation; of its topics only these start a conversation on their own (the random ones).
CONVERSATION, ENGINE_CONVERSATIONS = 1, frozenset({'HELLO', 'GOODBYE'})
#: The Radio topic type; a station plays its RadioHello and the topics its lines choose.
RADIO, RADIO_HELLO = 7, 'RADIOHELLO'
#: INFO DATA flag Goodbye: the conversation ends after the line, its Choices unoffered.
INFO_GOODBYE = 0x01
#: The topics the engine says after a speech challenge (DNAM) passes or fails, from the line linking from the topic.
CHALLENGE_OUTCOMES = frozenset({'SPEECHCHALLENGESUCCESS', 'SPEECHCHALLENGEFAILURE'})

#: CTDA function index of GetIsID, the same in every game.
GET_IS_ID = 72

#: CTDA run-on values: the speaker, and whom the line is said to.
SUBJECT, TARGET = 0, 1

#: The player's FormIDs (reference and base), the same in every game.
PLAYER = (0x14, 0x07)

#: Export files of placements, geometry and dialogue, which never attach a script.
_NO_SCRIPT_FILES = frozenset({'REFR', 'ACHR', 'ACRE', 'LAND', 'NAVM', 'NAVI', 'CELL', 'PGRE',
                              'SCPT', 'INFO', 'DIAL'})

#: A `Key=0001ABCD` export line, whose value may be a script's FormID.
_FID_VALUE = re.compile(rb'^[^=\r\n]+=([0-9A-Fa-f]{8})\r?$', re.M)


def referenced_fids(export_dir: str) -> set:
    """Every FormID a base record in the export names, which includes each attached script."""
    out = set()
    for path in Path(export_dir).glob('*.txt'):
        if path.stem not in _NO_SCRIPT_FILES:
            out |= {int(v, 16) for v in _FID_VALUE.findall(path.read_bytes())}
    return out


@dataclass(frozen=True)
class Setter:
    """One `SetStage` site: where it lives and what it sets."""

    kind: str
    owner: str
    part: str
    quest: str
    stage: object
    raw: str = ''


@dataclass
class SourceInfo:
    """What the dialogue model needs of one INFO."""

    fid: int
    dial: int
    quest: int
    conditions: list
    choices: list
    link_from: list
    flags: int = 0
    raw: tuple = ()
    challenge: int = 0


def strip_comment(line: str) -> str:
    """`line` up to its `;` comment."""
    return line.split(';', 1)[0]


def script_lines(text: str) -> list:
    """The lines of a script text, whether its newlines are real or escaped."""
    return text.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r', '').split('\n')


def find_setters(text: str, quests: dict) -> list:
    """[(quest EditorID, stage, raw, block)] of the uncommented SetStages and StartQuests.

    The stage is an int, START for a StartQuest, or None when it is computed;
    the block is the `Begin` block the line sits in, or ''.
    """
    out, block = [], ''
    for line in script_lines(text):
        code = strip_comment(line)
        begin = _BEGIN.match(code)
        block = begin.group(1).strip() if begin else block
        for quest, stage in SETSTAGE.findall(code):
            if quest.lower() in quests:
                number = int(stage) if re.fullmatch(r'-?\d+', stage) else None
                out.append((quests[quest.lower()], number, line.strip(), block))
        out += [(quests[q.lower()], START, line.strip(), block) for q in STARTQUEST.findall(code)
                if q.lower() in quests]
    return out


def decode_condition(data: bytes) -> tuple:
    """(type, comparison value, function, parameter 1, run-on) of a CTDA; a short one reads zeros past its end.

    See: docs/commentary/tes5_import_conditions.md#fallout-short-ctda
    """
    data = data + bytes(max(0, 24 - len(data)))
    ctype, comp = data[0], struct.unpack_from('<f', data, 4)[0]
    func, param = struct.unpack_from('<HxxI', data, 8)
    return ctype, comp, func, param, struct.unpack_from('<I', data, 20)[0]


def _requires_id(condition: tuple, side: int = SUBJECT) -> bool:
    """Whether a condition is `GetIsID X == 1` (or `!= 0`) run on `side`."""
    ctype, comp, func, _param, run_on = condition
    return func == GET_IS_ID and run_on == side and ((ctype >> 5 == 0 and comp == 1.0)
                                                      or (ctype >> 5 == 1 and comp == 0.0))


def or_groups(conditions: list) -> list:
    """The conditions split into OR chains; a chain ends at a condition without the OR flag."""
    groups, current = [], []
    for condition in conditions:
        current.append(condition)
        if not condition[0] & 0x01:
            groups.append(current)
            current = []
    return groups + ([current] if current else [])


def required_speakers(conditions: list, side: int = SUBJECT):
    """Bases the GetIsID chains on `side` allow, or None for anyone.

    See: docs/commentary/tools_preflight.md#source-setters
    """
    chains = [{c[3] for c in group} for group in or_groups(conditions)
              if all(_requires_id(c, side) for c in group)]
    return sorted(set.intersection(*chains)) if chains else None


def addressed_elsewhere(conditions: list) -> list:
    """The actors a line must be said to when none is the player, else []."""
    listeners = required_speakers(conditions, TARGET) or []
    return [] if any(fid & 0xFFFFFF in PLAYER for fid in listeners) else listeners


def _truth(condition: tuple) -> 'bool | None':
    """True for `F == 1` (or `!= 0`), False for `F == 0` (or `!= 1`), else None."""
    ctype, comp = condition[0] >> 5, condition[1]
    return {(0, 1.0): True, (1, 0.0): True, (0, 0.0): False, (1, 1.0): False}.get((ctype, comp))


def never_passes(conditions: list) -> bool:
    """Whether two lone tests require one function, parameter and subject both true and false (Red Lucy's "Two."
    answer: GetIsID Lucy == 1 AND != 1; VDialogueTEST's quest: GetInFaction == 1 AND == 0).
    See: docs/commentary/tools_preflight.md#dialogue-loss
    """
    seen = {}
    for (cond,) in (g for g in or_groups(conditions) if len(g) == 1):
        truth, key = _truth(cond), cond[2:]
        if truth is not None and seen.setdefault(key, truth) != truth:
            return True
    return False


def _linked(info: SourceInfo, opened: set, links: dict) -> bool:
    """Whether an `opened` topic links to `info` (a challenge outcome: from `links`).
    See: docs/commentary/tools_preflight.md#dialogue-loss
    """
    sources = links.get(info.dial)
    return any(t in opened and (sources is None or t in sources) for t in info.link_from)


def speakable(conditions: list, present: set) -> bool:
    """False when no placed actor passes the GetIsID tests, or they never pass."""
    required = required_speakers(conditions)
    return not never_passes(conditions) and (required is None or any(fid in present for fid in required))


def _fids(rec: dict, prefix: str) -> list:
    """Every `prefix[i]` FormID value of `rec`."""
    return [int(v, 16) for k, v in rec.items() if k.startswith(prefix + '[') and v]


def _records(export_dir: str, sig: str) -> list:
    """Every record of the export file `sig`.txt, or [] when it is absent."""
    path = os.path.join(export_dir, f'{sig}.txt')
    return parse_export_file(path) if os.path.isfile(path) else []


class SourceGame:
    """A source game's quests, stage setters, dialogue and placed actors."""

    def __init__(self, export_dir: str):
        """Read one game's export folder."""
        self.quests, self.quest_fids, self.start_enabled = {}, {}, set()
        for rec in _records(export_dir, 'QUST'):
            edid = get_str(rec, 'EditorID')
            if edid:
                self.quests[edid.lower()] = edid
                self.quest_fids[int(rec['FormID'], 16)] = edid
            if edid and get_int(rec, 'DATA.Flags') & 0x01:
                self.start_enabled.add(edid.lower())
        self.packages = {rec['FormID'].upper(): rec for rec in _records(export_dir, 'PACK')}
        self.setters, self.texts = [], []
        self.dials, self.infos = {}, {}
        self.present = set()
        self.external_topics, self.said_topics = set(), set()
        self.package_texts, self.package_topics = {}, {}
        self.used_scripts = set()
        self.quest_scri, self.quest_script_of = {}, {}
        self.actor_names = {}
        self.stages = {}
        self.quest_conditions = {}
        self.fallout = False
        self._read(export_dir)

    def _add(self, kind: str, owner: str, part: str, text: str) -> None:
        """Record the setters in one script text and keep the text for topic lookups (a package's: once it is used)."""
        if kind == 'package':
            self.package_texts.setdefault(owner, []).append(text)
        else:
            self.texts.append(text)
        for quest, stage, raw, block in find_setters(text, self.quests):
            self.setters.append(Setter(kind, owner, block if kind == 'script' else part, quest, stage, raw))

    def _read(self, export_dir: str) -> None:
        """Fill the model from the export's QUST, PACK, SCPT, DIAL, INFO and actor files."""
        for rec in _records(export_dir, 'QUST'):
            self._read_quest(rec)
        for fid, rec in self.packages.items():
            for section in PACKAGE_SECTIONS:
                self._add('package', fid, section, rec.get(f'{section}.Script', ''))
            self.package_topics[fid] = {int(rec.get(key) or '0', 16) for key in PACKAGE_TOPICS}
        talkers = {int(r['FormID'], 16): get_str(r, 'EditorID') for sig in TALKERS for r in _records(export_dir, sig)}
        self.actor_names.update(talkers)
        for rec in _records(export_dir, 'REFR'):
            self.texts.append(rec.get('Patrol.Script', ''))
            self.external_topics.add(int(rec.get('Patrol.Topic') or '0', 16))
            self.present |= {int(rec.get('NAME') or '0', 16)} & talkers.keys()
        named, script_names = referenced_fids(export_dir), {}
        for rec in _records(export_dir, 'SCPT'):
            self._add('script', get_str(rec, 'EditorID'), '', rec.get('SCTX', ''))
            script_names[int(rec['FormID'], 16)] = get_str(rec, 'EditorID').lower()
            if int(rec['FormID'], 16) in named:
                self.used_scripts.add(get_str(rec, 'EditorID').lower())
        self.quest_script_of = {script_names[s]: q for q, s in self.quest_scri.items() if s in script_names}
        for rec in _records(export_dir, 'DIAL'):
            self.fallout |= 'DATA.Flags' in rec
            self.dials[int(rec['FormID'], 16)] = (get_str(rec, 'EditorID'),
                                                  get_int(rec, 'DATA.Type'),
                                                  get_int(rec, 'DATA.Flags'))
        for rec in _records(export_dir, 'INFO'):
            self._read_info(rec)
        for sig in ('ACHR', 'ACRE'):
            self.present |= {int(r['NAME'], 16) for r in _records(export_dir, sig) if r.get('NAME')}
        listed = set()
        for sig in ('NPC_', 'CREA'):
            actors = _records(export_dir, sig)
            self.actor_names.update((int(r['FormID'], 16), get_str(r, 'EditorID')) for r in actors)
            listed |= {v.upper() for r in actors for k, v in r.items() if k.startswith('AIPackage[')}
        self._use_packages(listed)
        self._topics_named_by_scripts()

    def _use_packages(self, listed: set) -> None:
        """Count the topics and scripts of the packages an actor lists (`listed`, FormIDs) or a script names; a
        package nothing gives an actor plays nothing.
        See: docs/commentary/tools_preflight.md#dialogue-loss
        """
        words = {w.lower() for text in self.texts for line in script_lines(text)
                 for w in re.findall(r'\w+', strip_comment(line))}
        for fid, rec in self.packages.items():
            if fid in listed or get_str(rec, 'EditorID').lower() in words:
                self.texts += self.package_texts.get(fid, [])
                self.external_topics |= self.package_topics.get(fid, set())
        self.external_topics.discard(0)

    def _read_quest(self, rec: dict) -> None:
        """Record one quest's stage list, its conditions (which gate all its lines) and the setters in every stage
        result script."""
        edid = get_str(rec, 'EditorID')
        if rec.get('SCRI'):
            self.quest_scri[edid.lower()] = int(rec['SCRI'], 16)
        self.quest_conditions[int(rec['FormID'], 16)] = tuple(
            bytes.fromhex(rec[f'Condition[{i}].Raw']) for i in range(get_int(rec, 'ConditionCount'))
            if rec.get(f'Condition[{i}].Raw'))
        for i in range(get_int(rec, 'StageCount')):
            stage = get_int(rec, f'Stage[{i}].Index')
            self.stages.setdefault(edid.lower(), []).append(stage)
            for j in range(get_int(rec, f'Stage[{i}].LogCount')):
                text = rec.get(f'Stage[{i}].Log[{j}].ResultScript', '')
                self._add('stage', f'{edid}|{stage}', str(j), text)

    def _read_info(self, rec: dict) -> None:
        """Record one INFO's setters, dialogue links and conditions."""
        fid = int(rec['FormID'], 16)
        self._add('info', rec['FormID'].upper(), '', info_result_script(rec))
        raw = tuple(bytes.fromhex(rec[f'Condition[{i}].Raw']) for i in range(get_int(rec, 'ConditionCount'))
                    if rec.get(f'Condition[{i}].Raw'))
        self.infos[fid] = SourceInfo(fid, int(rec.get('ParentDIAL', '0'), 16),
                                     int(rec.get('QSTI.Quest', '0') or '0', 16), [decode_condition(d) for d in raw],
                                     _fids(rec, 'Choice'), _fids(rec, 'LinkFrom'), get_int(rec, 'DATA.Flags'), raw,
                                     get_int(rec, 'DNAM.SpeechChallenge'))
        self.external_topics.update(_fids(rec, 'AddTopic'))

    def _topics_named_by_scripts(self) -> None:
        """Add every topic a script names after AddTopic, StartConversation or ForceGreet; one only Say or SayTo
        names is said, not opened (said_topics)."""
        by_edid = {edid.lower(): fid for fid, (edid, _t, _f) in self.dials.items() if edid}
        said = set()
        for text in self.texts:
            for line in script_lines(text):
                for command, rest in _TOPIC_COMMANDS.findall(strip_comment(line)):
                    topics = {by_edid[w.lower()] for w in re.findall(r'\w+', rest) if w.lower() in by_edid}
                    (said if command.lower() in SAY_COMMANDS else self.external_topics).update(topics)
        self.said_topics = said - self.external_topics

    def reachable_topics(self) -> set:
        """Topics a player can reach in the source game, by a fixed point over links.

        A topic starts reachable as a bark (not Topic, Conversation or Radio),
        RadioHello, top-level, GREETING, HELLO or GOODBYE, or named by AddTopic,
        a used package, a patrol marker or a script. Choices from a
        speakable line in a reachable topic, and links from such a topic, make
        that topic reachable; not from a Goodbye line, nor a topic only Say or
        SayTo plays, nor to a challenge outcome unchallenged.
        See: docs/commentary/tools_preflight.md#dialogue-loss
        """
        live = {fid for fid, (edid, dtype, flags) in self.dials.items()
                if dtype not in (0, CONVERSATION, RADIO) or flags & 0x02
                or edid.upper() in ('GREETING', RADIO_HELLO) or edid.upper() in ENGINE_CONVERSATIONS}
        live |= self.external_topics
        challenged = {info.dial for info in self.infos.values() if info.challenge}
        links = {fid: challenged for fid, (edid, _t, _f) in self.dials.items() if edid.upper() in CHALLENGE_OUTCOMES}
        opened, changed = set(), True
        while changed:
            before = len(live) + len(opened)
            for info in self.infos.values():
                if info.dial in live and speakable(info.conditions, self.present) and not info.flags & INFO_GOODBYE:
                    live.update(info.choices)
                    opened.add(info.dial)
                if info.dial not in live and _linked(info, opened, links):
                    live.add(info.dial)
            changed = len(live) + len(opened) != before
        return live | self.said_topics

    def radio_lines(self) -> set:
        """FormIDs of the Radio lines a station plays: its quest's RadioHello lines, then the lines of each topic a
        played line of that quest chooses.
        See: docs/commentary/tools_preflight.md#dialogue-loss
        """
        by_quest = defaultdict(lambda: defaultdict(list))
        for info in self.infos.values():
            if self.dials.get(info.dial, ('', 0))[1] == RADIO:
                by_quest[info.quest][info.dial].append(info)
        hello = {fid for fid, (edid, _t, _f) in self.dials.items() if edid.upper() == RADIO_HELLO}
        played = set()
        for topics in by_quest.values():
            queue = [t for t in topics if t in hello]
            reached = set(queue)
            while queue:
                lines = topics[queue.pop()]
                played.update(line.fid for line in lines)
                nxt = {c for line in lines for c in line.choices if c in topics} - reached
                reached |= nxt
                queue += nxt
        return played

