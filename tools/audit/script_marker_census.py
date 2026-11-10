"""Count the `;NE:` / `;TODO:` markers left in converted Papyrus, per source function.

Reads a folder of converted `.psc` (a scratch `script_convert.pipeline` run) and
the plugin's export folder, which names each script's quests or the base records
carrying it. Prints the totals and the largest rows; `--json` writes every row.

    python -m tools.audit.script_marker_census <psc dir> export/FalloutNV.esm --json out.json

See: docs/fork/script_markers.md#measuring
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from asset_convert.audio.voice_races import iter_records
from asset_convert.game_paths import namespace_for

#: Base record types whose SCRI names an object script.
OBJECT_SIGS = ('ACTI', 'NPC_', 'CREA', 'CONT', 'DOOR', 'MISC', 'ARMO', 'WEAP', 'ALCH',
               'BOOK', 'TERM', 'FURN', 'KEYM', 'NOTE', 'LIGH', 'TACT', 'INGR', 'AMMO')
#: Fragment-script name stems after the prefix, and the kind each one is.
FRAGMENT_KINDS = (('PF_', 'package'), ('TM_', 'terminal'), ('PM_', 'patrol'))
#: Marker text that opens a prose note rather than a call.
PROSE_OPENERS = ('the source compiler', 'Type mismatch', 'unreachable', 'OBSE', 'Verify')

MARK = re.compile(r';+(NE|TODO):\s*(.*)')
MARK_START = re.compile(r'(?=;+(?:NE|TODO):)')
OP_PREFIX = re.compile(r'^(?:&&|\|\||==|!=|<=|>=|<|>|\+|-|\*|/|!)\s*')
CALL = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?')
CONDITION = re.compile(r'(?i)(If|ElseIf|While)\b')
QF = re.compile(r'QF_(.+)')
TIF = re.compile(r'TIF__([0-9A-F]{8})')


class Owners:
    """Which quests own a script, and which base records carry an object script."""

    def __init__(self, export_dir: Path):
        """Index SCPT, QUST, INFO and the object records of one export folder."""
        def rec(sig):
            """The export's records of type `sig`."""
            return iter_records(Path(export_dir) / f'{sig}.txt')
        self.prefix = namespace_for(export_dir).upper() + '_'
        self.scpt = {r.get('EditorID', '').lower(): r['FormID'] for r in rec('SCPT')}
        quest_edid, self.script_quests = {}, collections.defaultdict(set)
        for r in rec('QUST'):
            quest_edid[r['FormID']] = r.get('EditorID', r['FormID'])
            if 'SCRI' in r:
                self.script_quests[r['SCRI']].add(r.get('EditorID'))
        self.info_quest = {r['FormID']: quest_edid.get(r['QSTI.Quest'], r['QSTI.Quest'])
                           for r in rec('INFO') if 'QSTI.Quest' in r}
        self.users = collections.defaultdict(list)
        for sig in OBJECT_SIGS:
            for r in rec(sig):
                if 'SCRI' in r:
                    self.users[r['SCRI']].append(f"{sig}:{r.get('EditorID')}")

    def owner(self, stem: str) -> tuple:
        """(kind, quest or record names) of the generated script named `stem`."""
        if not stem.startswith(self.prefix):
            return 'static', []
        rest = stem[len(self.prefix):]
        if m := QF.match(rest):
            return 'quest-stage', [m.group(1)]
        if m := TIF.match(rest):
            quest = self.info_quest.get(m.group(1))
            return 'topic-info', [quest] if quest else []
        for opener, kind in FRAGMENT_KINDS:
            if rest.startswith(opener):
                return kind, []
        fid = self.scpt.get(rest.lower())
        if fid in self.script_quests:
            return 'quest-script', sorted(self.script_quests[fid])
        return 'object-script', self.users.get(fid, [])[:4]


def marker_function(text: str) -> str:
    """The function a marker's text names, lower case, or `(note) ...` for prose."""
    t = OP_PREFIX.sub('', text.strip())
    t = OP_PREFIX.sub('', re.sub(r'^TODO:\s*', '', t)).lstrip('(').strip()
    m = CALL.match(t)
    if not m:
        return '(other)'
    if t.startswith(PROSE_OPENERS):
        return '(note) ' + ' '.join(t.split()[:3])
    if ' is not declared in ' in t:
        return '(note) undeclared var'
    return (m.group(2) or m.group(1)).lower()


def line_markers(line: str) -> list:
    """The function named by each marker on one Papyrus line."""
    return [marker_function(m.group(2)) for seg in MARK_START.split(line)[1:]
            if (m := MARK.match(seg))]


def census(psc_dir: Path, owners: Owners) -> list:
    """One row per function, largest first: markers, scripts, conditions, kinds, owners."""
    rows = collections.defaultdict(lambda: {'count': 0, 'scripts': set(), 'quests': set(),
                                            'kinds': collections.Counter(), 'conditions': 0,
                                            'samples': []})
    for path in sorted(Path(psc_dir).glob('*.psc')):
        kind, names = owners.owner(path.stem)
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            in_condition = bool(CONDITION.match(line.split(';', 1)[0].strip()))
            for func in line_markers(line):
                row = rows[func]
                row['count'] += 1
                row['scripts'].add(path.stem)
                row['quests'].update(n for n in names if n)
                row['kinds'][kind] += 1
                row['conditions'] += in_condition
                if len(row['samples']) < 3:
                    row['samples'].append(f'{path.stem}: {line.strip()[:160]}')
    out = [{'func': func, 'count': r['count'], 'n_scripts': len(r['scripts']),
            'conditions': r['conditions'], 'quests': sorted(r['quests']),
            'kinds': dict(r['kinds']), 'scripts': sorted(r['scripts']), 'samples': r['samples']}
           for func, r in rows.items()]
    return sorted(out, key=lambda r: (-r['count'], r['func']))


def totals(rows: list) -> dict:
    """Markers, scripts and functions (prose notes counted apart) over all rows."""
    notes = [r for r in rows if r['func'].startswith('(')]
    return {'markers': sum(r['count'] for r in rows),
            'scripts': len(set().union(*(r['scripts'] for r in rows))),
            'functions': len(rows) - len(notes),
            'note_markers': sum(r['count'] for r in notes),
            'condition_markers': sum(r['conditions'] for r in rows)}


def main(argv=None) -> int:
    """Run the census and print it; exit 0."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    ap.add_argument('psc_dir', type=Path, help='folder of converted .psc files')
    ap.add_argument('export_dir', type=Path, help="the plugin's export folder")
    ap.add_argument('--json', type=Path, help='write every row here')
    ap.add_argument('--top', type=int, default=40, help='rows to print (default 40)')
    args = ap.parse_args(argv)
    rows = census(args.psc_dir, Owners(args.export_dir))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding='utf-8')
    print(' '.join(f'{k}={v}' for k, v in totals(rows).items()))
    for r in rows[:args.top]:
        print(f"{r['count']:5d} {r['n_scripts']:4d} cond={r['conditions']:3d} "
              f"{r['func']}  {r['kinds']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
