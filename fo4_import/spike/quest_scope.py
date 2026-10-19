"""Which FNV quests a build includes: the quests its content names, and the quests those start or advance.

The content is the scripts of the bases placed in the build, of its placed
actors and of their packages, the actors' package conditions, and the
dialogue lines spoken there (a GetIsID on a placed actor's base, a
GetIsReference on a placed reference, a GetInCell on a built cell). A
quest is named by a converted script's property of its name (attach.py
fills properties by FNV EditorID) or by a condition on it. Each such quest
adds the quests its own scripts (quest script, stage results, its lines'
results) start, set a stage on or write a variable of, one step: those run
or keep state when it does (VCG01's psych test answers tally in
VCG01Test). A quest it only reads stays out, and the readiness report shows
the read.

See: docs/fork/fo4_pipeline.md#quest-scope
"""

import collections
import re
import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.script import FRAGMENT_PREFIX, PACKAGE_PREFIX, QUEST_PREFIX, declared_properties
from script_convert.constants import papyrus_script_name

#: Converted script name prefix of an FNV script (attach.SCRIPT_PREFIX).
SCRIPT_PREFIX = 'FALLOUTNV_'
#: FNV CTDA byte offsets of parameter 1 and 2.
PARAMS = (12, 16)
#: FNV condition functions that say who speaks a line or where: GetIsID, GetIsReference, GetInCell.
GET_IS_ID, GET_IS_REFERENCE, GET_IN_CELL = 72, 136, 67
#: A converted call starting or advancing a quest, or writing its variable (TES4Add_<variable>, assignment).
STARTS = re.compile(r'\b(?:TES4Start|TES4SetStage|StartForObjective)\(\s*\(?(\w+)'
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

    def included(self, bases: dict, refs: list, actors: list) -> list:
        """FNV QUST records of a build placing `bases` {FormID: (type, record)}, references `refs` and actors
        `actors` (ACHR/ACRE records), in FormID order."""
        actor_bases = {int(a['NAME'], 16) for a in actors}
        where = {GET_IS_ID: actor_bases, GET_IS_REFERENCE: {int(r['FormID'], 16) for r in refs + actors},
                 GET_IN_CELL: {int(r['ParentCELL'], 16) for r in refs + actors if r.get('ParentCELL')}}
        named = set().union(*(self._script(rec.get('SCRI'))[0] for _, rec in bases.values()))
        for fid in actor_bases & self.actors.keys():
            named |= self._actor(self.actors[fid])
        named |= {quest for quest, lines in self.lines.items() if any(_placed(line, where) for line in lines)}
        named &= self.quests.keys()
        started = set().union(*(self._starts(self.quests[q]) for q in named)) & self.quests.keys()
        return [self.quests[q] for q in sorted(named | started)]

    def _actor(self, rec: dict) -> set:
        """Quests an FNV actor base names: its script, its packages' result scripts and conditions."""
        out = self._script(rec.get('SCRI'))[0]
        for i in range(int(rec.get('AIPackageCount', 0) or 0)):
            pack = int(rec[f'AIPackage[{i}]'], 16)
            out |= self._file(f'{PACKAGE_PREFIX}{pack:08X}')[0] | (_params(self.packs.get(pack, {})) & self.quests.keys())
        return out

    def _starts(self, quest: dict) -> set:
        """Quests an FNV quest's scripts start, set a stage on or write a variable of: quest script, stage results,
        lines' results."""
        out = self._script(quest.get('SCRI'))[1] | self._file(f'{QUEST_PREFIX}{quest["EditorID"]}')[1]
        for line in self.lines[int(quest['FormID'], 16)]:
            out |= self._file(f'{FRAGMENT_PREFIX}{line["FormID"].upper()}')[1]
        return out

    def _script(self, scri: 'str | None') -> tuple:
        """_file() of the converted FNV script `scri` (FormID hex)."""
        name = self.scripts.get(int(scri, 16), '') if scri else ''
        return self._file(papyrus_script_name(name, SCRIPT_PREFIX)) if name else (set(), set())

    def _file(self, script: str) -> tuple:
        """(quests a converted script's properties name, quests it starts, sets a stage on or writes a variable of),
        by FNV EditorID; empty when it was not converted."""
        if script not in self.read:
            path = self.dir / f'{script}.psc' if self.dir else None
            text = path.read_text(encoding='utf-8') if path and path.exists() else ''
            named = {self.names[p.lower()] for _, p in declared_properties(text) if p.lower() in self.names}
            started = {self.names[n.lower()] for m in STARTS.finditer(text) for n in m.groups()
                       if n and n.lower() in self.names}
            self.read[script] = (named, started)
        return self.read[script]


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


def _params(rec: dict) -> set:
    """The FormID parameters of FNV record `rec`'s conditions."""
    out, i = set(), 0
    while f'Condition[{i}].Raw' in rec:
        raw = bytes.fromhex(rec[f'Condition[{i}].Raw'])
        out |= {struct.unpack_from('<I', raw, at)[0] for at in PARAMS if len(raw) >= at + 4}
        i += 1
    return out
