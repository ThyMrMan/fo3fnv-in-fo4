"""FNV packages a Fallout 4 build left out, by cause, and the actors left with no package.

Each FNV package pairs with the built PACK of its EditorID. One the build did
not write is reported when a built actor lists it, the build's readiness
report names an actor it was left out for, or a converted script declares a
property of its name; the rest were never reached. Its cause is the reason
the readiness report gives. A built actor whose FNV list is not empty but
which runs no package is an error.

See: docs/fork/fo4_plan_npc_behavior.md#phase-1
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.packages import listed
from fo4_import.spike.readiness import PACKAGE_LEFT_OUT
from fo4_import.spike.script import declared_properties
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.package_ai import SAMPLES, package_source
from tools.validate.preflight.plugin_index import every

#: A readiness detail of a package left out: `<EditorID> (<why>)`, for an NPC `<EditorID> (<why>; keeps <n> of <m>)`.
_DETAIL = re.compile(r'^(\S+) \((.*?)(?:; keeps \d+ of \d+)?\)$')

#: The cause of a left-out package the readiness report does not name (a build from before 2026-11-09).
NO_CAUSE = 'no cause recorded (a script names it)'


def readiness_causes(report: Path) -> tuple:
    """({package EditorID: why}, {package EditorID: {FNV owner FormID}}) of the readiness report's packages."""
    path = Path(report)
    entries = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
    why, owners = {}, defaultdict(set)
    for e in (e for e in entries if e['kind'] == PACKAGE_LEFT_OUT):
        m = _DETAIL.match(e['detail'])
        if m:
            why.setdefault(m.group(1).lower(), m.group(2))
            owners[m.group(1).lower()].add(e['owner'].upper())
    return why, owners


def script_names(scripts: Path) -> set:
    """The property names, lowercase, the converted scripts in `scripts` declare."""
    folder = Path(scripts) if scripts else None
    paths = folder.glob('*.psc') if folder and folder.is_dir() else ()
    return {name.lower() for p in paths for _t, name in declared_properties(p.read_text(encoding='utf-8',
                                                                                      errors='replace'))}


def left_out(index, export: Path, report: Path, scripts: Path) -> tuple:
    """([(package EditorID, why, [holder EditorIDs], script-named)], {actor EditorID: [left-out EditorIDs]})
    for the FNV packages the build reached but did not write, and the built actors' FNV package lists."""
    built = {index.edid(r.form_id).lower() for r in index.by_type['PACK']}
    built_actors = {index.edid(r.form_id).lower() for r in index.by_type['NPC_']}
    actors = [a for sig in ('NPC_', 'CREA') for a in export_records(str(export), sig)]
    by_fid = {a['FormID'].upper(): a for a in actors}
    packs = {r['FormID'].upper(): r['EditorID'] for r in export_records(str(export), 'PACK') if r.get('EditorID')}
    why, owners = readiness_causes(report)
    named = script_names(scripts)
    holders, lists = defaultdict(set), {}
    for actor in (a for a in actors if a.get('EditorID', '').lower() in built_actors and listed(a)):
        lists[actor['EditorID']] = own = [packs.get(p.upper(), p) for p in listed(actor)]
        for name in own:
            holders[name.lower()].add(actor['EditorID'])
    for name, fids in owners.items():
        holders[name] |= {by_fid[f].get('EditorID', f) for f in fids if f in by_fid}
    rows = [(name, why.get(name.lower(), NO_CAUSE), sorted(holders[name.lower()]), name.lower() in named)
            for name in sorted(set(packs.values()), key=str.lower)
            if name.lower() not in built and (holders[name.lower()] or name.lower() in named)]
    return rows, lists


def runs_nothing(index, lists: dict) -> list:
    """Built actors in `lists` whose FO4 record (or template) holds no package."""
    npcs = {index.edid(r.form_id).lower(): r for r in index.by_type['NPC_']}
    return sorted(a for a in lists if not every(package_source(index, npcs[a.lower()]), 'PKID'))


def audit(game: str, index, export: Path, report: Path, scripts: Path) -> list:
    """The behavior findings for one Fallout 4 build; prints the left-out packages counted by cause."""
    rows, lists = left_out(index, export, report, scripts)
    why = {name: cause for name, cause, _h, _s in rows}
    print(f'  behavior: {len(rows)} packages left out: '
          + ', '.join(f'{cause} {n}' for cause, n in Counter(why.values()).most_common()))
    out = [Finding('behavior', f'behavior|{game}|no-package|{actor}', 'error',
                   f'{actor} runs no package; FNV gives it {len(lists[actor])}',
                   tuple(f'{p}: {why.get(p, "built")}' for p in lists[actor][:SAMPLES]))
           for actor in runs_nothing(index, lists)]
    return out + [Finding('behavior', f'behavior|{game}|package|{name}', 'review',
                          f'package {name} left out ({why})',
                          tuple(held[:SAMPLES]) + (('a script names it',) if named else ()))
                  for name, why, held, named in rows]
