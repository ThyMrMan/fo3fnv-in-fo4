"""Audit a built Fallout 4 plugin of FNV content for the defects play-testing found, before playing it.

    py -3.14 -m tools.validate.fo4_audit <plugin.esp> [--export export/FalloutNV.esm]
        [--scripts temp/fo4_scripts/FalloutNV.esm] [--plugin-dirs DIR ...] [--examples N]

Each check prints a count and examples; exit 1 when any finds something. The checks:

- properties: script object properties declared and left unfilled, or filled with a FormID no file defines;
- stats: creatures keeping their own stats (no Stats template) with Health 0 or every S.P.E.C.I.A.L. value 0
  (vanilla's humans leave theirs 0: 531 of 663);
- class: actors keeping the vanilla body's TurretTripodClass;
- creatures: non-human actors with no factions or no combat style that no template supplies;
- burrowers: placed actors of a burrowing race (MoleratRace), which can stick under terrain;
- fragments: FNV packages with begin/end/change sections whose built package has no VMAD;
- persistence: package targets FNV made persistent and the build placed without the flag;
- duplicates: FNV actors placed once in FNV and more than once in the build;
- hazards, over the scripts the plugin attaches and TES4Polyfill: a cross-script `X.v = X.v + n` left as a
  read and a write (two threads lose one); a counter tested with `==` after its atomic add (two adders both
  see the later value and both miss); a Say in a dialogue result (FO4 queues it, FNV began the line before
  returning); GetFormFromFile naming a file outside the plugin, its masters and the helper plugin.

See: docs/fork/fo4_pipeline.md#audit
"""

import argparse
import collections
import re
import struct
import sys
from pathlib import Path

from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.vmad import Unsupported, read_entry, read_wstring
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.script import FRAGMENT_PREFIX, declared_properties
from script_convert.atomic_adds import PREFIX as ADD_PREFIX
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.packages.scripts_falloutnv import package_flags
from tools.validate.fo4_check import find, masters

#: Fallout4.esm forms the checks name: HumanRace, MoleratRace, TurretTripodClass, Health, S.P.E.C.I.A.L.
HUMAN_RACE, BURROWING_RACES, TURRET_CLASS = 0x13746, {0x1D810}, 0x123E22
HEALTH, SPECIAL = 0x2D4, tuple(range(0x2C2, 0x2C9))
#: ACBS template flags: Stats, Factions, AI Data.
USE_STATS, USE_FACTIONS, USE_AI_DATA = 0x2, 0x4, 0x10
#: Papyrus property types that hold no form.
VALUE_TYPES = frozenset({'int', 'float', 'bool', 'string'})
#: Properties a polyfill does without when unfilled: a player seat, the combat-approach queue.
OPTIONAL_PROPERTIES = ('TES4Pose_', 'TES4CombatApproaches')
PERSISTENT = 0x400
#: Fallout4.esm FormIDs below this are forms the engine makes itself (the player 0x14, Aggression 0x2BC).
ENGINE_FORMS = 0x800
#: ACHR record flag Starts Dead.
STARTS_DEAD = 0x200
#: The shared helper script every converted script calls, read with the attached ones.
POLYFILL = 'TES4Polyfill'
#: Files a converted script may name in GetFormFromFile beside the plugin and its masters.
HELPER_FILES = frozenset({'FalloutHelpers.esl'})
_SHARED_ADD = re.compile(r'^\s*(\w+)\.(\w+) = \1\.\2 [-+] ', re.MULTILINE)
_ATOMIC_ADD = re.compile(rf'(\w+)\.{ADD_PREFIX}(\w+)\(')
_FUNCTION = re.compile(r'^(?:\w+\s+)?(?:Event|Function)\s', re.MULTILINE | re.IGNORECASE)
_SAY = re.compile(r'\bSayWhenFree\(|\.Say\(')
_FORM_FILE = re.compile(r'GetFormFromFile\([^,]+,\s*"([^"]+)"\)')


# ---------------------------------------------------------------------------
# The plugin
# ---------------------------------------------------------------------------


class Plugin:
    """A plugin's records {FormID (load-order adjusted): (sig, flags, [(tag, data)])} and the forms of its masters."""

    def __init__(self, path: Path, dirs: list):
        """Read `path` and every master's FormIDs (from the game's Data, the plugin's folder or `dirs`)."""
        names = masters(path)
        self.index, self.records, self.defined = len(names), {}, set(range(ENGINE_FORMS))
        for i, name in enumerate(names):
            raw = find(name, [FALLOUT4_DIR / 'Data', path.parent, *dirs]).read_bytes()
            self.defined |= {i << 24 | r.form_id & 0xFFFFFF for r, _ in walk(raw, bodies=())}
        for rec, _ in walk(path.read_bytes()):
            fid = self.index << 24 | rec.form_id & 0xFFFFFF if rec.form_id >> 24 >= self.index else rec.form_id
            self.records[fid] = (rec.sig, rec.flags, list(subrecords(rec.body)))
        self.defined |= set(self.records)

    def of(self, sig: bytes):
        """(FormID, flags, {tag: first data}, [(tag, data)]) of every record of `sig`."""
        for fid, (s, flags, subs) in self.records.items():
            if s == sig:
                first = {}
                for tag, data in subs:
                    first.setdefault(tag, data)
                yield fid, flags, first, subs

    def edid(self, fid: int) -> str:
        """The EditorID of one of the plugin's records, else the FormID."""
        subs = dict(self.records.get(fid, (b'', 0, []))[2])
        return subs.get(b'EDID', b'').rstrip(b'\0').decode('latin1') or f'{fid:08X}'


# ---------------------------------------------------------------------------
# Script properties
# ---------------------------------------------------------------------------

def vmad_scripts(sig: bytes, vmad: bytes) -> list:
    """[(script, {property: FormID})] of a VMAD: attached scripts, and the fragment script of an INFO, PACK or
    QUST (alias scripts are not read)."""
    _, _, count = struct.unpack_from('<hhH', vmad)
    out, pos = [], 6
    for _ in range(count):
        (name, objects, _), pos = read_entry(vmad, pos)
        out.append((name, objects))
    if sig in (b'INFO', b'PACK') and pos < len(vmad):
        (name, objects, _), _ = read_entry(vmad, pos + 2)
        out.append((name, objects))
    elif sig == b'QUST' and pos < len(vmad):
        name, _ = read_wstring(vmad, pos + 3)
        if name:
            (name, objects, _), _ = read_entry(vmad, pos + 3)
            out.append((name, objects))
    return out


def assigned(psc: str, name: str) -> bool:
    """Whether the script sets property `name` (`mySelf = Self`, `akQuest.rRef = v2`)."""
    return re.search(rf'^\s*(\w+\.)?{re.escape(name)}\s*=[^=]', psc, re.MULTILINE | re.IGNORECASE) is not None


def fnv_names(export: Path) -> set:
    """Every EditorID in the FNV export, lower-cased (a property filled by name names one)."""
    out = set()
    for path in export.glob('*.txt'):
        with path.open(encoding='utf-8', errors='replace') as lines:
            out |= {line[9:].strip().lower() for line in lines if line.startswith('EditorID=')}
    return out


def attachments(plugin: Plugin):
    """(FormID, script, {property: FormID}) of every script a VMAD of the plugin attaches."""
    for fid, (sig, _, subs) in plugin.records.items():
        vmad = dict(subs).get(b'VMAD')
        try:
            attached = vmad_scripts(sig, vmad) if vmad else []
        except (Unsupported, struct.error):
            continue
        for script, objects in attached:
            yield fid, script, objects


def source(scripts: Path, script: str) -> str:
    """A converted script's Papyrus source; '' when it was not written."""
    psc = scripts / f'{script}.psc'
    return psc.read_text(encoding='utf-8') if psc.exists() else ''


def check_properties(plugin: Plugin, scripts: Path) -> tuple:
    """(unfilled, dangling) [(record, script, property)] over every VMAD the plugin writes."""
    unfilled, dangling, declared = [], [], {}
    for fid, script, objects in attachments(plugin):
        if script not in declared:
            text = source(scripts, script)
            declared[script] = [n for t, n in declared_properties(text) if t.lower() not in VALUE_TYPES
                                and not t.endswith('[]') and not assigned(text, n)
                                and not n.startswith(OPTIONAL_PROPERTIES)]
        unfilled += [(plugin.edid(fid), script, n) for n in declared[script] if n not in objects]
        dangling += [(plugin.edid(fid), script, n) for n, v in objects.items() if v and v not in plugin.defined]
    return unfilled, dangling


# ---------------------------------------------------------------------------
# Script hazards: FNV's one-script-at-a-time model meeting Papyrus threads
# ---------------------------------------------------------------------------

def _tested_after_add(text: str) -> set:
    """{(owner, variable)} a function of `text` tests with == after its own add to it."""
    out = set()
    for body in _FUNCTION.split(text):
        for m in _ATOMIC_ADD.finditer(body):
            if re.search(rf'\b{re.escape(m[1])}\.{re.escape(m[2])}\s*==', body[m.end():], re.IGNORECASE):
                out.add((m[1], m[2]))
    return out


def check_hazards(plugin: Plugin, scripts: Path, files: set) -> dict:
    """{hazard: ['script: detail']} over the scripts the plugin attaches, plus TES4Polyfill; `files` are the
    plugin, its masters and the helper plugin, the files a GetFormFromFile may name."""
    out = collections.defaultdict(list)
    for script in sorted({s for _, s, _ in attachments(plugin)} | {POLYFILL}):
        text = source(scripts, script)
        for owner, var in set(_SHARED_ADD.findall(text)):
            if owner.lower() != 'self':
                out['hazards: cross-script add not made atomic'].append(f'{script}: {owner}.{var}')
        for owner, var in sorted(_tested_after_add(text)):
            out['hazards: counter tested with == after its add (both adders can miss it)'].append(
                f'{script}: {owner}.{var}')
        if script.startswith(FRAGMENT_PREFIX) and _SAY.search(text):
            out['hazards: Say from a dialogue result (FO4 queues it, FNV began it)'].append(script)
        for name in set(_FORM_FILE.findall(text)) - files:
            out['hazards: GetFormFromFile on a file the load order lacks'].append(f'{script}: {name}')
    return out


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------

def _u32(data: bytes) -> int:
    """A little-endian FormID."""
    return struct.unpack_from('<I', data)[0]


def check_actors(plugin: Plugin) -> dict:
    """{check: [actor EditorID]} for the stats, class and creature checks; bases placed only dead skipped."""
    out, dead = collections.defaultdict(list), dead_only(plugin)
    for fid, _, first, subs in plugin.of(b'NPC_'):
        if fid in dead:
            continue
        inherited = struct.unpack_from('<H', first[b'ACBS'], 14)[0] if b'TPLT' in first else 0
        name, human = plugin.edid(fid), _u32(first[b'RNAM']) == HUMAN_RACE
        prps = first.get(b'PRPS', b'')
        values = dict(struct.unpack_from('<If', prps, i) for i in range(0, len(prps), 8))
        if not inherited & USE_STATS and not human and values.get(HEALTH, 0.0) <= 0.0:
            out['stats: own Health 0'].append(name)
        if not inherited & USE_STATS and not human and not any(values.get(av, 0.0) for av in SPECIAL):
            out['stats: own S.P.E.C.I.A.L. all 0'].append(name)
        if b'CNAM' in first and _u32(first[b'CNAM']) == TURRET_CLASS:
            out['class: TurretTripodClass'].append(name)
        if not human and not inherited & USE_FACTIONS and not any(t == b'SNAM' for t, _ in subs):
            out['creatures: no factions'].append(name)
        if not human and not inherited & USE_AI_DATA and b'ZNAM' not in first:
            out['creatures: no combat style'].append(name)
    return out


def dead_only(plugin: Plugin) -> set:
    """Actor bases every placement of which starts dead."""
    alive = collections.Counter(), collections.Counter()
    for _, flags, first, _ in plugin.of(b'ACHR'):
        alive[not flags & STARTS_DEAD][_u32(first[b'NAME'])] += 1
    return set(alive[False]) - set(alive[True])


def check_burrowers(plugin: Plugin) -> list:
    """Living placed actors whose base (or its template chain's) race burrows."""
    races = {fid: _u32(first[b'RNAM']) for fid, _, first, _ in plugin.of(b'NPC_')}
    templates = {fid: _u32(first[b'TPLT']) for fid, _, first, _ in plugin.of(b'NPC_') if b'TPLT' in first}
    out = []
    for fid, flags, first, _ in plugin.of(b'ACHR'):
        base, seen = _u32(first[b'NAME']), set()
        if flags & STARTS_DEAD:
            continue
        while base in templates and base not in seen:
            seen.add(base)
            base = templates[base]
        if races.get(base) in BURROWING_RACES:
            out.append(f'{fid:08X} ({plugin.edid(_u32(first[b"NAME"]))})')
    return out


# ---------------------------------------------------------------------------
# Packages and placement
# ---------------------------------------------------------------------------

def check_fragments(plugin: Plugin, export: Path) -> list:
    """FNV packages that run a section whose built package has no VMAD."""
    built = {plugin.edid(fid): b'VMAD' in first for fid, _, first, _ in plugin.of(b'PACK')}
    return [r['EditorID'] for r in export_records(export, 'PACK')
            if package_flags(r) and built.get(f'FNV_{r.get("EditorID")}') is False]


def check_persistence(plugin: Plugin, export: Path) -> list:
    """Package target references (PLDT near reference, PTDA reference) FNV made persistent and the build did not."""
    fnv_flags = {int(r['FormID'], 16) & 0xFFFFFF: int(r.get('RecordFlags', 0) or 0)
                 for sig in ('REFR', 'ACHR', 'ACRE') for r in export_records(export, sig)}
    out = set()
    for _, _, _, subs in plugin.of(b'PACK'):
        for tag, data in subs:
            if tag in (b'PLDT', b'PTDA') and len(data) >= 8 and struct.unpack_from('<i', data)[0] == 0:
                target = _u32(data[4:])
                rec = plugin.records.get(target)
                if rec and not rec[1] & PERSISTENT and fnv_flags.get(target & 0xFFFFFF, 0) & PERSISTENT:
                    out.add(plugin.edid(target))
    return sorted(out)


def check_duplicates(plugin: Plugin, export: Path) -> list:
    """FNV NPC/creature bases placed once in FNV and more than once in the build (by the built base's EditorID)."""
    fnv = collections.Counter(r['NAME'] for sig in ('ACHR', 'ACRE') for r in export_records(export, sig))
    names = {f'FNV_{r["EditorID"]}': r['FormID'] for sig in ('NPC_', 'CREA') for r in export_records(export, sig)
             if r.get('EditorID')}
    built = collections.Counter(plugin.edid(_u32(first[b'NAME'])) for _, _, first, _ in plugin.of(b'ACHR'))
    return [f'{edid}: {n} placed' for edid, n in sorted(built.items())
            if n > 1 and fnv.get(names.get(edid, ''), 0) == 1]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(findings: dict, examples: int) -> int:
    """Print each check's count and first `examples` findings; the number of checks that found something."""
    failed = 0
    for check, items in findings.items():
        print(f'{check}: {len(items)}')
        for item in items[:examples]:
            print(f'    {item}')
        failed += bool(items)
    return failed


def main() -> int:
    """Run every check on the plugin named on the command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--export', type=Path, default=Path('export/FalloutNV.esm'))
    ap.add_argument('--scripts', type=Path, default=Path('temp/fo4_scripts/FalloutNV.esm'))
    ap.add_argument('--plugin-dirs', nargs='*', default=[])
    ap.add_argument('--examples', type=int, default=8)
    args = ap.parse_args()
    plugin = Plugin(args.plugin, args.plugin_dirs)
    unfilled, dangling = check_properties(plugin, args.scripts)
    fnv = fnv_names(args.export)
    findings = {'properties: unfilled, no FNV form of that name': [f'{r} {s}.{p}' for r, s, p in unfilled
                                                                    if p.lower() not in fnv],
                'properties: unfilled, FNV form outside the build': [f'{r} {s}.{p}' for r, s, p in unfilled
                                                                     if p.lower() in fnv],
                'properties: dangling FormID': [f'{r} {s}.{p}' for r, s, p in dangling],
                **check_actors(plugin), 'burrowers placed': check_burrowers(plugin),
                'fragments: package section not attached': check_fragments(plugin, args.export),
                'persistence: package target lost Persistent': check_persistence(plugin, args.export),
                'duplicates: unique actor placed again': check_duplicates(plugin, args.export),
                **check_hazards(plugin, args.scripts, {*masters(args.plugin), args.plugin.name, *HELPER_FILES})}
    return 1 if report(findings, args.examples) else 0


if __name__ == '__main__':
    sys.exit(main())
