"""Which FNV quests a build includes: the quests its content names, and the quests those start or advance.

The content is the scripts of the bases placed in the build, of the items
its placed actors and containers carry (a faction outfit's equip script),
of its placed actors and of their packages, the actors' package conditions, and the
dialogue lines spoken there (a GetIsID on a placed actor's or object's base,
a GetIsReference on a placed reference, a GetInCell on a built cell, or a
speaker test a placed actor passes by its authored base: GetInFaction,
GetIsVoiceType, GetIsRace, GetIsClass, IsInList), in a line's conditions or
its quest's own, which FNV adds to every line (a radio station's quest names
its talking activator; vDialogueNCRCivilian's lines name its dialogue faction). A
quest is named by a converted script's property of its name (attach.py
fills properties by FNV EditorID) or of one of its topics (a Say needs
the topic's quest built), or by a condition on it. Each such quest
adds the quests its own scripts (quest script, stage results, its lines'
results) start, set a stage on or write a variable of, one step: those run
or keep state when it does (VCG01's psych test answers tally in
VCG01Test). A quest it only reads stays out, and the readiness report shows
the read.

See: docs/fork/fo4_pipeline.md#quest-scope
See: docs/fork/fo4_pipeline.md#disguises
"""

import collections
import re
import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike.items import ITEM_TYPES
from fo4_import.spike.npcs import USE_FACTIONS, USE_INVENTORY, USE_TRAITS
from fo4_import.spike.records import RUN_SUBJECT
from fo4_import.spike.say_topics import CONVERSATION, GREETING, TOPIC_TYPE, raws
from fo4_import.spike.script import FRAGMENT, PACKAGE, QUEST, declared_properties, prefix
from script_convert.constants import papyrus_script_name

#: FNV records that hold others (_holds): actors, containers, leveled lists.
HOLDERS = ('NPC_', 'CREA', 'CONT', 'LVLI', 'LVLN', 'LVLC')
#: Export keys of a held FormID: an inventory item, a leveled entry.
HELD = re.compile(r'(?:Item|Entry)\[\d+\]\.FormID$')
#: FNV CTDA byte offsets of parameter 1 and 2.
PARAMS = (12, 16)
#: FNV condition functions that say who speaks a line or where: GetIsID, GetIsReference, GetInCell.
GET_IS_ID, GET_IS_REFERENCE, GET_IN_CELL = 72, 136, 67
#: FNV speaker tests of a trait an actor base authors: {function: its field}, taken with the template's traits.
TRAITS = {'GetIsVoiceType': 'VTCK.Voice', 'GetIsRace': 'RNAM.Race', 'GetIsClass': 'CNAM.Class'}
#: FNV's test of the speaker's base in a form list.
IN_LIST = 'IsInList'
#: FNV leveled actor lists: a placed actor or template naming one may be any of its entries.
LEVELED_ACTORS = ('LVLN', 'LVLC')
#: A converted call starting or advancing a quest, or writing its variable (TES4Add_<variable>, assignment).
STARTS = re.compile(r'\b(?:TES4Start|TES4SetStage|StartForObjective|TES4Polyfill\.SetStage)\(\s*\(?(\w+)'
                    r'|\b(\w+)\.(?:SetStage\(|Start\(|TES4Add_\w+\(|\w+\s*=(?!=))')


class QuestScope:
    """FNV quests by what names them; `included()` gives a build's."""

    def __init__(self, export_dir: Path, scripts_dir: 'Path | None'):
        """Index FNV's quests, scripts, lines, packages and actor bases; converted scripts in `scripts_dir`."""
        self.dir, self.read = scripts_dir, {}
        self.quests = {int(r['FormID'], 16): r for r in export_records(export_dir, 'QUST') if r.get('EditorID')}
        self.names = {r['EditorID'].lower(): fid for fid, r in self.quests.items()}
        self.scripts = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'SCPT')}
        self.lines = collections.defaultdict(list)
        for info in export_records(export_dir, 'INFO'):
            self.lines[int(info.get('QSTI.Quest', '0') or '0', 16)].append(info)
        self.packs = {int(r['FormID'], 16): r for r in export_records(export_dir, 'PACK')}
        self.actors = {int(r['FormID'], 16): r for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}
        self.items = {int(r['FormID'], 16): r['SCRI'] for sig in ITEM_TYPES for r in export_records(export_dir, sig)
                      if r.get('SCRI')}
        self.holds = {int(r['FormID'], 16): _holds(r) for sig in HOLDERS for r in export_records(export_dir, sig)}
        self.leveled = {int(r['FormID'], 16): [int(v, 16) for k, v in r.items() if HELD.match(k)]
                        for sig in LEVELED_ACTORS for r in export_records(export_dir, sig)}
        self.form_lists = {int(r['FormID'], 16): frozenset(int(v, 16) for k, v in r.items() if k.startswith('LNAM['))
                           for r in export_records(export_dir, 'FLST')}
        self.topic_quests = topic_quests(export_records(export_dir, 'DIAL'))

    def _held(self, start: set) -> set:
        """What the records `start` hold, at any depth: inventories, leveled entries, inventory templates."""
        seen, todo = set(), list(start)
        while todo:
            for fid in self.holds.get(todo.pop(), ()):
                if fid not in seen:
                    seen.add(fid)
                    todo.append(fid)
        return seen

    def included(self, bases: dict, refs: list, actors: list, held: set = frozenset()) -> list:
        """FNV QUST records of a build placing `bases` {FormID: (type, record)}, references `refs` and actors
        `actors` (ACHR/ACRE records), with quests `held` (a DLC's own) always in; in FormID order."""
        actor_bases = {int(a['NAME'], 16) for a in actors}
        where = {GET_IS_ID: actor_bases | bases.keys(), GET_IS_REFERENCE: {int(r['FormID'], 16) for r in refs + actors},
                 GET_IN_CELL: {int(r['ParentCELL'], 16) for r in refs + actors if r.get('ParentCELL')}}
        scripts = [rec.get('SCRI') for _, rec in bases.values()]
        scripts += [self.items[fid] for fid in self._held(bases.keys() | actor_bases) if fid in self.items]
        named = set().union(*(self._script(scri)[0] for scri in scripts))
        for fid in actor_bases & self.actors.keys():
            named |= self._actor(self.actors[fid])
        named |= {quest for quest, lines in self.lines.items() if any(_placed(line, where) for line in lines)}
        named |= {quest for quest, rec in self.quests.items() if self.lines.get(quest) and _placed(rec, where)}
        named |= self._spoken(actor_bases, named)
        named = (named | set(held)) & self.quests.keys()
        started = set().union(*(self._starts(self.quests[q]) for q in named)) & self.quests.keys()
        return [self.quests[q] for q in sorted(named | started)]

    def _spoken(self, bases: set, named: set) -> set:
        """Quests outside `named` with a line whose speaker tests (TRAITS, GetInFaction, IsInList on the Subject,
        its quest's conditions ANDed in) one of the placed actor `bases` passes, at least one by having the tested
        form. See: docs/fork/fo4_pipeline.md#quest-scope"""
        index = collections.defaultdict(set)
        for facts in {facts for base in bases for facts in self.speakers(base)}:
            for func, forms in facts:
                for form in forms:
                    index[(func, form)].add(facts)
        out = set()
        for quest, lines in self.lines.items():
            if quest in named or quest not in self.quests:
                continue
            head = [C.parse(raw) for raw in raws(self.quests[quest])]
            if any(self._speaks(head + [C.parse(raw) for raw in raws(line)], index) for line in lines):
                out.add(quest)
        return out

    def _speaks(self, conds: list, index: dict) -> bool:
        """Whether a placed speaker in `index` {(function, form): speaker facts} has a form one of `conds` tests and
        passes them all (tests of anything else may pass)."""
        tests = [c for c in conds if _membership(c)]
        for facts in {f for c in tests for form in self._members(c) for f in index.get((_fact(c), form), ())}:
            known = dict(facts)
            if C.simplify(conds, lambda c: self._settle(c, known)) is not None:
                return True
        return False

    def _settle(self, cond: dict, known: dict) -> 'bool | None':
        """The outcome of Subject speaker test `cond` on a speaker's facts `known` {function: forms}; None for any
        other test or a fact the speaker's base does not author."""
        forms = known.get(_fact(cond))
        if cond['run_on'] != RUN_SUBJECT or cond['op_flags'] & C.USE_GLOBAL or forms is None:
            return None
        return C.compare(cond, float(bool(self._members(cond) & forms)))

    def _members(self, cond: dict) -> frozenset:
        """The forms a speaker test names: its parameter, or a form list's entries."""
        listed = self.form_lists.get(cond['p1'])
        return listed if listed is not None else frozenset() if cond['func'] == IN_LIST else frozenset({cond['p1']})

    def speakers(self, base: int, seen: frozenset = frozenset()) -> list:
        """Who a placed actor of FNV base `base` may be: one facts tuple ((function, forms), ...) per actor its
        leveled lists and templates can give, its traits and factions from where its template flags take them."""
        if base in seen:
            return []
        seen |= {base}
        if base in self.leveled:
            return [f for entry in self.leveled[base] for f in self.speakers(entry, seen)]
        rec = self.actors.get(base)
        if rec is None:
            return []
        out = []
        for traits in self._sources(rec, USE_TRAITS, seen):
            for member in self._sources(rec, USE_FACTIONS, seen):
                facts = {'GetIsID': frozenset({base, int(traits['FormID'], 16)}),
                         'GetInFaction': frozenset(int(member[f'Faction[{i}].FormID'], 16)
                                                   for i in range(int(member.get('FactionCount', 0) or 0))
                                                   if int(member[f'Faction[{i}].Rank']) >= 0)}
                facts.update({func: frozenset({int(traits[field], 16)}) for func, field in TRAITS.items()
                              if traits.get(field)})
                out.append(tuple(sorted(facts.items())))
        return out

    def _sources(self, rec: dict, flag: int, seen: frozenset) -> list:
        """The actor records FNV `rec` takes template part `flag` from: itself, or its template's (each entry's
        of a leveled list), followed while the template flags take it."""
        if not int(rec.get('ACBS.TemplateFlags', 0) or 0) & flag or 'TPLT.Template' not in rec:
            return [rec]
        template = int(rec['TPLT.Template'], 16)
        if template in seen:
            return []
        if template in self.leveled:
            return [s for entry in self.leveled[template] if entry in self.actors and entry not in seen
                    for s in self._sources(self.actors[entry], flag, seen | {template, entry})]
        nxt = self.actors.get(template)
        return self._sources(nxt, flag, seen | {template}) if nxt else []

    def _actor(self, rec: dict) -> set:
        """Quests an FNV actor base names: its script, its packages' result scripts and conditions."""
        out = self._script(rec.get('SCRI'))[0]
        for i in range(int(rec.get('AIPackageCount', 0) or 0)):
            pack = int(rec[f'AIPackage[{i}]'], 16)
            out |= self._file(f'{prefix(PACKAGE)}{pack:08X}')[0] | (_params(self.packs.get(pack, {})) & self.quests.keys())
        return out

    def _starts(self, quest: dict) -> set:
        """Quests an FNV quest's scripts start, set a stage on or write a variable of: quest script, stage results,
        lines' results."""
        out = self._script(quest.get('SCRI'))[1] | self._file(f'{prefix(QUEST)}{quest["EditorID"]}')[1]
        for line in self.lines[int(quest['FormID'], 16)]:
            out |= self._file(f'{prefix(FRAGMENT)}{line["FormID"].upper()}')[1]
        return out

    def _script(self, scri: 'str | None') -> tuple:
        """_file() of the converted FNV script `scri` (FormID hex)."""
        name = self.scripts.get(int(scri, 16), '') if scri else ''
        return self._file(papyrus_script_name(name, prefix())) if name else (set(), set())

    def _file(self, script: str) -> tuple:
        """(quests a converted script's properties name, quests it starts, sets a stage on or writes a variable of),
        by FNV EditorID; empty when it was not converted."""
        if script not in self.read:
            path = self.dir / f'{script}.psc' if self.dir else None
            text = path.read_text(encoding='utf-8') if path and path.exists() else ''
            declared = declared_properties(text)
            named = {self.names[p.lower()] for _, p in declared if p.lower() in self.names}
            named |= {q for kind, p in declared if kind == 'Topic' for q in self.topic_quests.get(p.lower(), ())}
            started = {self.names[n.lower()] for m in STARTS.finditer(text) for n in m.groups()
                       if n and n.lower() in self.names}
            self.read[script] = (named, started)
        return self.read[script]


def topic_quests(dials) -> dict:
    """{EditorID (lower): DIAL quests} of player/Conversation `dials`, not GREETING.
    See: docs/fork/fo4_pipeline.md#said-topics
    """
    return {d['EditorID'].lower(): {int(d[f'Quest[{i}]'], 16) for i in range(int(d.get('QuestCount', 0) or 0))}
            for d in dials if d.get('EditorID') and d.get('DATA.Type') in (TOPIC_TYPE, CONVERSATION)
            and d['FormID'].upper() != GREETING}


def _placed(line: dict, where: dict) -> bool:
    """Whether a line's speaker or cell test (GetIsID, GetIsReference, GetInCell) names one of `where`'s forms."""
    i = 0
    while f'Condition[{i}].Raw' in line:
        raw = bytes.fromhex(line[f'Condition[{i}].Raw'])
        i += 1
        func, p1 = struct.unpack_from('<II', raw, 8) if len(raw) >= 16 else (None, None)
        if p1 in where.get(func, ()):
            return True
    return False


def _fact(cond: dict) -> str:
    """The speaker fact a test reads: IsInList reads the speaker's base (GetIsID)."""
    return 'GetIsID' if cond['func'] == IN_LIST else cond['func']


def _membership(cond: dict) -> bool:
    """Whether `cond` is a Subject speaker test passed by having the form it names."""
    return (cond['run_on'] == RUN_SUBJECT and not cond['op_flags'] & C.USE_GLOBAL
            and cond['func'] in (*TRAITS, 'GetInFaction', IN_LIST)
            and C.compare(cond, 1.0) and not C.compare(cond, 0.0))


def _holds(rec: dict) -> list:
    """What FNV `rec` holds: items, leveled entries, its inventory's template."""
    out = [int(v, 16) for k, v in rec.items() if HELD.match(k)]
    template = int(rec.get('ACBS.TemplateFlags', 0) or 0) & USE_INVENTORY and rec.get('TPLT.Template')
    return out + ([int(template, 16)] if template else [])


def _params(rec: dict) -> set:
    """The FormID parameters of FNV record `rec`'s conditions."""
    out, i = set(), 0
    while f'Condition[{i}].Raw' in rec:
        raw = bytes.fromhex(rec[f'Condition[{i}].Raw'])
        out |= {struct.unpack_from('<I', raw, at)[0] for at in PARAMS if len(raw) >= at + 4}
        i += 1
    return out
