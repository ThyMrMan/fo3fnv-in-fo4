"""Every FNV dialogue line a Fallout 4 build left out, and every menu choice left with no line, by cause.

    py -3.14 -m tools.validate.fo4_dialogue_census <plugin> [--export DIR] [--readiness JSON] [--rows TSV] [--top N]

Joins the plugin's FNV export (every INFO) with the readiness entries its
build wrote (fo4_import/spike/readiness.py). A line is built (a `line`
entry), left out by a condition (`line left out`, grouped by the function
and first missing form), or never reached: its quest has no built line
(`quest not built`) or its topic never reached the converter (`topic not
reached`, grouped by quest and topic). Choices with no line are grouped by
topic and cause. `--rows` writes one TSV row per line not built.

See: docs/fork/fo4_dialogue_gaps.md#census
"""

import argparse
import collections
import json
import sys
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import readiness as R


def causes(export: Path, entries: list) -> list:
    """[(FNV INFO, cause, topic EditorID, quest EditorID, first response)] of each line `entries` do not build."""
    dials = {r['FormID'].upper(): r.get('EditorID', '') for r in export_records(export, 'DIAL')}
    quests = {r['FormID'].upper(): r.get('EditorID', '') for r in export_records(export, 'QUST')}
    built = {e['detail'] for e in entries if e['kind'] == R.LINE}
    left = {e['detail'].split(' ', 1)[0]: e['detail'].split('(condition: ', 1)[-1][:-1]
            for e in entries if e['kind'] == R.LINE_LEFT_OUT}
    with_lines = {e['owner'] for e in entries if e['kind'] == R.LINE}
    rows = []
    for rec in export_records(export, 'INFO'):
        fid, quest = rec['FormID'].upper(), rec.get('QSTI.Quest', '').upper()
        if fid in built:
            continue
        cause = (f'condition: {left[fid]}' if fid in left else
                 'quest not built' if quest not in with_lines else 'topic not reached')
        rows.append((fid, cause, dials.get(rec.get('ParentDIAL', '').upper(), ''), quests.get(quest, quest),
                     rec.get('Response[0].ResponseText', '')[:80]))
    return rows


def report(rows: list, entries: list, total: int, top: int) -> None:
    """Print the counts by cause, the quests and topics behind the larger causes, and the unanswered choices."""
    print(f'FNV lines: {total}; built: {total - len(rows)}; not built: {len(rows)}')
    by_cause = collections.Counter(row[1] for row in rows)
    for cause, count in by_cause.most_common():
        print(f'{count:6}  {cause}')
        if not cause.startswith('condition'):
            where = collections.Counter(f'{row[3]} / {row[2]}' for row in rows if row[1] == cause)
            print(''.join(f'          {n:5}  {place}\n' for place, n in where.most_common(top)), end='')
    choices = collections.Counter(e['detail'] for e in entries if e['kind'] == R.CHOICE_UNANSWERED)
    print(f'choices with no line: {len(choices)} topics, {sum(choices.values())} menus')
    for detail, count in sorted(choices.items()):
        print(f'{count:6}  {detail}')


def main() -> int:
    """Print the census of the plugin named on the command line; 0."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', help='the built plugin (its name picks the readiness entries)')
    ap.add_argument('--export', type=Path, default=Path('export/FalloutNV.esm'))
    ap.add_argument('--readiness', type=Path, help='readiness entries (default: the build of this plugin name)')
    ap.add_argument('--rows', type=Path, help='write one TSV row per line not built')
    ap.add_argument('--top', type=int, default=15, help='quests/topics shown per cause')
    args = ap.parse_args()
    entries = json.loads((args.readiness or R.report_path(args.plugin)).read_text(encoding='utf-8'))
    rows = causes(args.export, entries)
    report(rows, entries, len(export_records(args.export, 'INFO')), args.top)
    if args.rows:
        args.rows.write_text(''.join('\t'.join(row) + '\n' for row in rows), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
