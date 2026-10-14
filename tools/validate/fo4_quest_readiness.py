"""Per-quest readiness of a Fallout 4 build: what each built FNV quest is missing, before it is played.

    py -3.14 -m tools.validate.fo4_quest_readiness <plugin> [--plugin-dirs DIR ...] [--quest EDID ...] [--brief]

For each FNV quest the plugin builds: its lines built and left out (with
the condition that blocked each), player choices left with no reply,
objective targets not in the build, its scripts' unfilled properties (stage
results, quest script, its lines' results; a property naming an FNV form
outside the build or no FNV form), and the packages left out of the NPCs
who speak its lines. The build writes its part as it goes
(fo4_import/spike/readiness.py); the properties come from the plugin
(fo4_audit.check_properties). A quest with none of these is clear. Exit 1
when any quest is not.

See: docs/fork/fo4_pipeline.md#readiness
"""

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import readiness as R
from fo4_import.spike.script import FRAGMENT_PREFIX, QUEST_PREFIX
from script_convert.constants import papyrus_script_name
from tools.validate.fo4_audit import Plugin, check_properties, fnv_names

#: FNV GetIsID and its condition layout: function at byte 8, parameter 1 at 12, Run On at 20 (0: the speaker).
GET_IS_ID, SUBJECT = 72, 0
#: Prefix of the converted FNV scripts and of the plugin's records.
SCRIPT_PREFIX, RECORD_PREFIX = 'FALLOUTNV_', 'FNV_'


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

class Quests:
    """The FNV export's quests, their lines' speakers and which converted scripts belong to which quest."""

    def __init__(self, export: Path):
        """Index quests, scripts and lines from the FNV `export`."""
        self.by_edid = {r['EditorID']: r for r in export_records(export, 'QUST') if r.get('EditorID')}
        self.by_fid = {r['FormID'].upper(): r['EditorID'] for r in self.by_edid.values()}
        scripts = {r['FormID'].upper(): r.get('EditorID', '') for r in export_records(export, 'SCPT')}
        self.owner = {f'{QUEST_PREFIX}{e}': e for e in self.by_edid}
        self.owner.update({papyrus_script_name(scripts.get(r['SCRI'].upper(), ''), SCRIPT_PREFIX): e
                           for e, r in self.by_edid.items() if r.get('SCRI')})
        self.speakers = collections.defaultdict(set)
        for info in export_records(export, 'INFO'):
            quest = self.by_fid.get(info.get('QSTI.Quest', '').upper())
            self.owner[f'{FRAGMENT_PREFIX}{info["FormID"].upper()}'] = quest
            self.speakers[quest] |= _speakers(info)
        self.npc_names = {r['FormID'].upper(): r.get('EditorID', r['FormID'])
                          for sig in ('NPC_', 'CREA') for r in export_records(export, sig)}


def _speakers(info: dict) -> set:
    """FNV NPC FormIDs (hex) a line's GetIsID conditions name as its speaker."""
    out, i = set(), 0
    while f'Condition[{i}].Raw' in info:
        raw = bytes.fromhex(info[f'Condition[{i}].Raw'])
        if len(raw) >= 24 and struct.unpack_from('<I', raw, 8)[0] == GET_IS_ID and struct.unpack_from(
                '<I', raw, 20)[0] == SUBJECT:
            out.add('%08X' % struct.unpack_from('<I', raw, 12)[0])
        i += 1
    return out


def built_quests(plugin: Plugin, quests: Quests) -> list:
    """EditorIDs of the FNV quests the plugin writes, sorted."""
    names = {plugin.edid(fid) for fid, (sig, _, _) in plugin.records.items() if sig == b'QUST'}
    return sorted(e for e in quests.by_edid if f'{RECORD_PREFIX}{e}' in names)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def findings(entries: list, unfilled: list, quests: Quests, fnv: set) -> dict:
    """{quest EditorID: {'lines': built count, finding kind: [details]}} from the build's entries and the
    plugin's unfilled properties."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    lines = collections.defaultdict(set)
    packages = collections.defaultdict(list)
    for e in entries:
        if e['kind'] == R.PACKAGE_LEFT_OUT:
            packages[e['owner']].append(e['detail'])
        elif e['kind'] == R.LINE:
            lines[quests.by_fid.get(e['owner'])].add(e['detail'])
        else:
            out[quests.by_fid.get(e['owner'])][e['kind']].append(e['detail'])
    for _, script, prop in unfilled:
        where = 'names an FNV form, not filled' if prop.lower() in fnv else 'no FNV form of that name'
        out[quests.owner.get(script)][f'unfilled property ({where})'].append(f'{script}.{prop}')
    for quest, npcs in quests.speakers.items():
        for npc in npcs & packages.keys():
            out[quest][R.PACKAGE_LEFT_OUT] += [f'{quests.npc_names.get(npc, npc)}: {d}' for d in packages[npc]]
    for quest, said in lines.items():
        out[quest]['lines'] = len(said)
    return out


def show(edid: str, quest: dict, found: dict, brief: bool) -> bool:
    """Print one quest's findings; True when it is clear."""
    kinds = {k: sorted(set(v)) for k, v in found.items() if k != 'lines' and v}
    state = 'clear' if not kinds else 'check'
    counts = ', '.join(f'{k} {len(v)}' for k, v in sorted(kinds.items()))
    print(f'{state:5s} {edid} "{quest.get("FULL", "")}" ({quest["FormID"]}): lines built {found.get("lines", 0)}'
          + (f'; {counts}' if counts else ''))
    if not brief:
        for kind, details in sorted(kinds.items()):
            print(f'        {kind}:')
            print('\n'.join(f'          {d}' for d in details))
    return not kinds


def main() -> int:
    """Print every built quest's readiness; exit 1 when one is not clear."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--export', type=Path, default=Path('export/FalloutNV.esm'))
    ap.add_argument('--scripts', type=Path, default=Path('temp/fo4_scripts/FalloutNV.esm'))
    ap.add_argument('--plugin-dirs', nargs='*', default=[])
    ap.add_argument('--quest', nargs='*', default=[], help='only these quests (FNV EditorIDs)')
    ap.add_argument('--brief', action='store_true', help='one line per quest')
    args = ap.parse_args()
    entries_path = R.report_path(args.plugin.name)
    if not entries_path.exists():
        print(f'{entries_path}: no readiness entries; build the plugin first')
        return 2
    plugin, quests = Plugin(args.plugin, args.plugin_dirs), Quests(args.export)
    unfilled, _ = check_properties(plugin, args.scripts)
    found = findings(json.loads(entries_path.read_text(encoding='utf-8')), unfilled, quests, fnv_names(args.export))
    names = [e for e in built_quests(plugin, quests) if not args.quest or e in args.quest]
    clear = [show(e, quests.by_edid[e], found.get(e, {}), args.brief) for e in names]
    print(f'\n{sum(clear)} of {len(clear)} quests clear')
    return 0 if all(clear) else 1


if __name__ == '__main__':
    sys.exit(main())
