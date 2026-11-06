"""Quest stages and actors that a build's conditions and scripts name: each must exist in the build or its built
masters.

GetStageDone (and GetStage ==) conditions name a quest and a stage, and SetStage, GetStageDone and IsStageDone calls
in the scripts the build attaches do too. The quest's stages are those of its last copy in load order (a DLC's
override wins), and a missing stage is an error unless the source game's quest lacks it too (then a review). A
GetIsID condition names an actor base. It is an error when the build places that base nowhere, directly or
through a placed leveled list or a script property, while the source game places it.

See: docs/fork/fo4_preflight.md#targets
"""

import re
import struct
from collections import defaultdict
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import walk, zstr
from tools.validate.preflight.condition_diff import FO4, decode
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.plugin_index import every, u32

#: Condition functions naming a quest (parameter 1) and a stage (parameter 2, or the compared value).
FUNCS = {name: i for i, name in FO4.names.items() if name in ('GetStage', 'GetStageDone', 'GetIsID')}

#: A CTDA type's flag for a value read from a global, and its comparison bits (0 is ==).
USE_GLOBAL, COMPARISON_SHIFT = 0x04, 5

#: Script calls naming a stage: `Quest.SetStage(N)` and `Fn(Quest [as Type], N)`.
RECEIVER_CALL = re.compile(r'\b(\w+)\s*\.\s*(?:SetStage|GetStageDone|IsStageDone)\s*\(\s*(\d+)\s*\)', re.I)
ARGUMENT_CALL = re.compile(r'\b(?:TES4SetStage|SetStage|GetStageDone|IsStageDone)\s*\(\s*(\w+)(?:\s+as\s+\w+)?\s*,'
                           r'\s*(\d+)\s*\)', re.I)

#: An export QUST key holding one stage's index.
STAGE_KEY = re.compile(r'Stage\[\d+\]\.Index')

#: Users listed per finding.
SHOWN = 4


def quest_stages(subs) -> set:
    """The stage indexes of a Fallout 4 QUST's (signature, data) subrecords."""
    return {struct.unpack_from('<H', d)[0] for t, d in subs if t == 'INDX' and len(d) >= 2}


class Built:
    """The quests, stages, actor names and placed actor bases of a build and its built masters; `held`: the load
    bytes whose records it holds."""

    def __init__(self, index, masters: list, prefix: str):
        """Read the built masters (in load order), then the build itself."""
        self.stages, self.names, self.prefix = {}, {}, prefix
        self.placed, self.leveled, self.npcs = set(), {}, set()
        self.held = {len(index.masters)} | {index.masters.index(Path(p).name) for p in masters}
        for path in masters:
            for rec, _ in walk(Path(path).read_bytes(), b'QUST', b'ACHR', b'LVLN', b'NPC_'):
                self._add(rec.sig.decode(), rec.form_id, [(t.decode(), d) for t, d in rec.subs()])
        for sig in ('QUST', 'ACHR', 'LVLN', 'NPC_'):
            for rec in index.by_type[sig]:
                self._add(sig, rec.form_id, [(s.type, s.data) for s in rec.subrecords])
        self.placed |= {t for _s, _p, t in index.object_props}
        self._expand()

    def _add(self, sig: str, fid: int, subs: list) -> None:
        """Take one record's part: a quest's stages, an actor's name, a placement or a leveled list."""
        edid = next((zstr(d) for t, d in subs if t == 'EDID'), '')
        self.names[fid] = edid[len(self.prefix):] if edid.startswith(self.prefix) else edid
        if sig == 'QUST':
            self.stages[fid] = quest_stages(subs)
        elif sig == 'ACHR':
            self.placed.add(next((u32(d) for t, d in subs if t == 'NAME'), 0))
        elif sig == 'LVLN':
            self.leveled[fid] = {u32(d, 4) for t, d in subs if t == 'LVLO'}
        else:
            self.npcs.add(fid)

    def _expand(self) -> None:
        """Add the actors placed leveled lists can give, to any depth."""
        todo = [f for f in self.placed if f in self.leveled]
        while todo:
            for fid in self.leveled[todo.pop()] - self.placed:
                self.placed.add(fid)
                todo += [fid] if fid in self.leveled else []


class Source:
    """The source game's quest stages and placed actors, by EditorID."""

    def __init__(self, export_dir: Path):
        """Read the export's QUST, ACHR, ACRE, NPC_ and CREA records, masters' included."""
        self.stages = {r.get('EditorID', '').lower(): {int(r[k]) for k in r if STAGE_KEY.fullmatch(k)}
                       for r in export_records(export_dir, 'QUST')}
        placed = {int(r['NAME'], 16) for sig in ('ACHR', 'ACRE') for r in export_records(export_dir, sig)
                  if r.get('NAME')}
        self.placed = {r.get('EditorID', '').lower() for sig in ('NPC_', 'CREA')
                       for r in export_records(export_dir, sig) if int(r['FormID'], 16) in placed}


def is_equal(ctype: int) -> bool:
    """Whether a CTDA type compares with == against a value of its own (not a global)."""
    return not ctype & USE_GLOBAL and not ctype >> COMPARISON_SHIFT


def condition_targets(index) -> tuple:
    """([(quest, stage, user)], [(actor, user)]) of every CTDA in the build: GetStageDone, GetStage == N (0 is
    "not started", no stage), GetIsID."""
    stages, actors = [], []
    every_cond = ((rec, decode(d)) for recs in index.by_type.values() for rec in recs for d in every(rec, 'CTDA'))
    for rec, cond in every_cond:
        if cond['func'] == FUNCS['GetStageDone']:
            stages.append((cond['p1'], cond['p2'], rec))
        elif cond['func'] == FUNCS['GetStage'] and is_equal(cond['type']) and cond['value']:
            stages.append((cond['p1'], int(cond['value']), rec))
        elif cond['func'] == FUNCS['GetIsID']:
            actors.append((cond['p1'], rec))
    return stages, actors


def script_targets(index, scripts_dir: Path) -> list:
    """[(quest, stage, user)] of the stage calls in each attached script whose quest is a property of it."""
    files = {p.stem.lower(): p for p in Path(scripts_dir).glob('*.psc')} if scripts_dir else {}
    out = []
    for script, fids in index.attached.items():
        props, path = index.script_props.get(script, {}), files.get(script)
        if path is None or not props:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        user = index.by_fid.get(fids[0])
        for name, stage in RECEIVER_CALL.findall(text) + ARGUMENT_CALL.findall(text):
            if props.get(name.lower()):
                out.append((props[name.lower()], int(stage), user))
    return out


def _user(index, rec) -> str:
    """A finding's detail line naming one user."""
    return f'{rec.type} {index.edid(rec.form_id)} {rec.form_id:08X}' if rec is not None else 'a script'


def stage_findings(game: str, index, built: Built, source: Source, targets: list) -> list:
    """Findings for named stages and quests the build does not hold."""
    missing, unheld = defaultdict(list), defaultdict(list)
    for quest, stage, rec in targets:
        if quest in built.stages and stage not in built.stages[quest]:
            missing[quest, stage].append(_user(index, rec))
        elif quest not in built.stages and quest >> 24 in built.held:
            unheld[quest].append(_user(index, rec))
    out = [Finding('targets', f'targets|{game}|quest|{quest:08X}', 'error',
                   f'{len(users)} conditions or scripts name quest {quest:08X}, which the build does not hold',
                   tuple(sorted(set(users))[:SHOWN])) for quest, users in sorted(unheld.items())]
    for (quest, stage), users in sorted(missing.items()):
        name = built.names.get(quest) or f'{quest:08X}'
        authored = source.stages.get(name.lower())
        severity = 'review' if authored is not None and stage not in authored else 'error'
        why = ', and so does the source game\'s' if severity == 'review' else ''
        out.append(Finding('targets', f'targets|{game}|stage|{name}|{stage}', severity,
                           f'{len(users)} conditions or scripts name stage {stage} of {name}, which lacks it{why}',
                           tuple(sorted(set(users))[:SHOWN])))
    return out


def actor_findings(game: str, index, built: Built, source: Source, targets: list) -> list:
    """Findings for GetIsID tests of actors the build never places."""
    unplaced = defaultdict(list)
    for actor, rec in targets:
        if actor in built.npcs and actor not in built.placed:
            unplaced[actor].append(_user(index, rec))
    out = []
    for actor, users in sorted(unplaced.items()):
        name = built.names.get(actor) or f'{actor:08X}'
        severity = 'error' if name.lower() in source.placed else 'review'
        where = 'the source game places it' if severity == 'error' else 'nor does the source game'
        out.append(Finding('targets', f'targets|{game}|actor|{name}', severity,
                           f'{len(users)} GetIsID tests name {name} {actor:08X}, which the build places nowhere '
                           f'({where})', tuple(sorted(set(users))[:SHOWN])))
    return out


def audit(game: str, index, masters: list, export_dir: Path, scripts_dir: Path) -> list:
    """The quest-stage and actor target findings for one Fallout 4 build."""
    built, source = Built(index, masters, index.edid_prefix), Source(export_dir)
    stages, actors = condition_targets(index)
    calls = script_targets(index, scripts_dir)
    print(f'  targets: {len(stages)} stage conditions, {len(calls)} script stage calls, {len(actors)} GetIsID tests;'
          f' {len(masters)} built masters')
    return (stage_findings(game, index, built, source, stages + calls)
            + actor_findings(game, index, built, source, actors))
