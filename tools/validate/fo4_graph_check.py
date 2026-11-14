"""Offline check of a plugin's FO4 creature behavior graphs and AnimTextData, for the mistakes that froze the gecko
spike: per race whose subgraph graph is in the data folder, its names, wildcards, clip names, iState variables,
attacks, clips and AnimTextData files; its plugin's MOVT speed layouts; loose AnimTextData. Exits 1 on an error.
Usage: py -3.14 -m tools.validate.fo4_graph_check <plugin> [--data DIR] [--race EDID ...]
See: docs/fork/fo4_own_rig.md#graph-check
"""

import argparse
import ntpath
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok import packfile
from fo4_import.havok.anim_text import file_data_names, string_field, transition_owners
from fo4_import.havok.graph import LOCAL_WILDCARD
from fo4_import.havok.gun_anim_text import ANIM_TEXT, FIRST_PERSON, crc, entry_id
from fo4_import.havok.gun_clips import subgraph_entries
from fo4_import.spike.creature_speed import ISTATE, PROJECT_MARK
from tes5_import.base.tes5_reader import masters, walk

#: Names every vanilla root graph carries; a root without them never attaches its subgraphs.
ROOT_EVENTS = ('PickNewIdle', 'Ragdoll', 'SoundPlay', 'weapEquip', 'weaponDraw', 'weaponSheathe')
ROOT_VARIABLES = ('bAnimationDriven', 'camerafromx', 'camerafromy', 'camerafromz')
#: The event an attack state raises (on exit or from its generators); without it the creature attacks once.
ATTACK_STOP = 'attackstop'
#: A wildcard transition's scope flags: local or global (FLAG_IS_GLOBAL_WILDCARD); Havok ignores one with neither.
WILDCARD_SCOPE = LOCAL_WILDCARD | 0x400
#: The variable holding the graph's movement state; the iState_ constants name MOVTs by value.
CURRENT_STATE = 'iState'
#: AnimTextData kinds the game reads per subgraph entry, and per root graph.
ENTRY_KINDS = ('AnimationFileData', 'DynamicIdleData')
GRAPH_KINDS = ('AnimEventInfo',)
#: The class loading another behavior file into a graph, and its field naming it (relative to the actor folder).
REFERENCE, REFERENCE_NAME = 'hkbBehaviorReferenceGenerator', 'behaviorName'
#: MOVT form version from which SPED is 28 floats; that layout's size.
NEW_SPED_VERSION, NEW_SPED_SIZE = 104, 112


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class Graph:
    """A behavior graph file's objects by name, event names, variable names and their initial word values."""
    path: str
    objs: dict
    events: list
    variables: list
    values: list = field(default_factory=list)


@dataclass
class Report:
    """Errors and warnings per subject (a race's EditorID, or the plugin)."""
    errors: dict = field(default_factory=dict)
    warnings: dict = field(default_factory=dict)

    def add(self, subject: str, check: str, lines: list, warn: bool = False) -> None:
        """File `lines` under `subject` as `check` findings (none: nothing filed)."""
        if lines:
            (self.warnings if warn else self.errors).setdefault(subject, []).extend(f'{check}: {t}' for t in lines)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def parse(path: str, raw: bytes) -> Graph:
    """The Graph of behavior file `path` (bytes `raw`)."""
    objs = {o['#']: o for o in packfile.read(raw).objects}
    return graph_of(path, objs)


def graph_of(path: str, objs: dict) -> Graph:
    """The Graph of behavior file `path`'s objects `objs`."""
    strings = next((o['fields'] for o in objs.values() if o['class'] == 'hkbBehaviorGraphStringData'), {})
    words = next((o['fields']['wordVariableValues'] for o in objs.values() if o['class'] == 'hkbVariableValueSet'), [])
    return Graph(path, objs, list(strings.get('eventNames', [])), list(strings.get('variableNames', [])),
                 [w['value'] for w in words])


def root_graph(project: str, read) -> 'str | None':
    """The Meshes path of project `project`'s root graph (its first character's behavior file); None if unread."""
    folder = PureWindowsPath(project).parent
    character = string_field(read(project), 'hkbProjectStringData', 'characterFilenames')
    behavior = string_field(read(str(folder / character[0])), 'hkbCharacterStringData', 'behaviorFilename') \
        if character else None
    return str(folder / behavior) if behavior else None


@dataclass
class Race:
    """A RACE's EditorID, behavior project (MODL after NAM3), attack events (ATKE, lower case) and subgraph
    entries."""
    edid: str
    project: str
    attack: set
    entries: list


def race_of(subs: list) -> Race:
    """The Race of RACE subrecords `subs`."""
    edid, project, marked = '', '', False
    for sig, data in subs:
        edid = _text(data) if sig == b'EDID' else edid
        project = _text(data) if sig == b'MODL' and marked and not project else project
        marked = marked or sig == PROJECT_MARK
    attack = {_text(data).lower() for sig, data in subs if sig == b'ATKE'}
    return Race(edid, project, attack, [e for e in subgraph_entries(subs) if 'graph' in e])


def _text(data: bytes) -> str:
    """A zero-terminated string subrecord's text."""
    return data.rstrip(b'\0').decode('cp1252')


def plugin_records(raw: bytes) -> tuple:
    """([Race] of `raw`'s races, {MOVT EditorID: (form version, MNAM lower case, SPED)})."""
    races, movts = [], {}
    for rec, _ in walk(raw, b'RACE', b'MOVT'):
        subs = list(rec.subs())
        if rec.sig == b'RACE':
            races.append(race_of(subs))
            continue
        found = dict(subs)
        movts[_text(found.get(b'EDID', b''))] = (rec.form_version, _text(found.get(b'MNAM', b'')).lower(),
                                                 found.get(b'SPED', b''))
    return races, movts


def movement_names(raw: bytes, data_dir: Path) -> set:
    """The MOVT MNAMs (lower case) of plugin `raw`, its masters found in `data_dir` or the game's Data, and
    Fallout4.esm."""
    names = {name for _, name, _ in plugin_records(raw)[1].values()}
    for master in {m.lower() for m in masters(raw)} | {'fallout4.esm'}:
        path = next((p for p in (data_dir / master, FALLOUT4_DIR / 'Data' / master) if p.is_file()), None)
        names |= {name for _, name, _ in plugin_records(path.read_bytes())[1].values()} if path else set()
    return names


# ---------------------------------------------------------------------------
# Graph checks
# ---------------------------------------------------------------------------

def root_names(root: Graph) -> list:
    """Warnings: the ROOT_EVENTS and ROOT_VARIABLES `root` lacks."""
    events, variables = {e.lower() for e in root.events}, {v.lower() for v in root.variables}
    out = [f'{root.path} lacks event {e}' for e in ROOT_EVENTS if e.lower() not in events]
    return out + [f'{root.path} lacks variable {v}' for v in ROOT_VARIABLES if v.lower() not in variables]


def missing_names(root: Graph, subgraphs: list) -> list:
    """Each third-person subgraph's event and variable names `root` lacks (first-person ones attach elsewhere)."""
    events, variables = {e.lower() for e in root.events}, {v.lower() for v in root.variables}
    out = []
    for sub in (s for s in subgraphs if FIRST_PERSON not in s.path.lower()):
        gone = sorted({e for e in sub.events if e.lower() not in events})
        gone += sorted({v for v in sub.variables if v.lower() not in variables})
        out += [f'{root.path} lacks {len(gone)} names {sub.path} uses: {", ".join(gone[:8])}'] if gone else []
    return out


def unflagged_wildcards(g: Graph) -> list:
    """Each state machine of `g` with wildcard transitions flagged neither local nor global (Havok ignores them)."""
    out = []
    for o in g.objs.values():
        array = g.objs.get(o['fields'].get('wildcardTransitions')) if o['class'] == 'hkbStateMachine' else None
        bad = [g.events[t['eventId']] for t in array['fields']['transitions'] if not t['flags'] & WILDCARD_SCOPE] \
            if array else []
        out += [f'{g.path}: {o["fields"]["name"]} wildcards on {", ".join(bad[:8])}'] if bad else []
    return out


def shared_clip_names(g: Graph) -> list:
    """Each clip generator name `g` gives more than one clip generator."""
    names = Counter(o['fields']['name'] for o in g.objs.values() if o['class'] == 'hkbClipGenerator')
    return [f'{g.path}: {name}' for name in sorted(n for n, count in names.items() if count > 1)]


def state_values(g: Graph) -> tuple:
    """(the value CURRENT_STATE starts at, 0 without it; {initial value: [the iState_ variables starting there]})."""
    values = dict(zip(g.variables, g.values))
    shared = {}
    for v in g.variables:
        if ISTATE.fullmatch(v.encode('cp1252')):
            shared.setdefault(values.get(v, 0), []).append(v)
    return values.get(CURRENT_STATE, 0), shared


def clashing_states(g: Graph) -> list:
    """`g`'s iState_ variables sharing the value the graph starts at."""
    start, shared = state_values(g)
    names = shared.get(start, [])
    return [f'{g.path}: {", ".join(names)} all start at {start}'] if len(names) > 1 else []


def odd_states(g: Graph, movts: set) -> list:
    """Warnings: iState_ variables of `g` sharing another value, and each naming no MOVT in `movts`."""
    start, shared = state_values(g)
    out = [f'{g.path}: {", ".join(n)} all start at {value}' for value, n in shared.items()
           if value != start and len(n) > 1]
    names = [n for group in shared.values() for n in group]
    return out + [f'{g.path}: {v} names no MOVT' for v in names if v[len('iState_'):].lower() not in movts]


def attack_faults(graphs: list, attack: set) -> list:
    """Each state an attack transition (on an event in `attack`, lower case) enters in `graphs` that never raises
    attackStop, itself or through the states its transitions lead to (a combo)."""
    out = []
    for g in graphs:
        up = parents(g)
        for event, machine, state in attack_states(g, attack):
            msg = f'{g.path}: state {state["fields"]["name"]} ({event}) never raises attackStop'
            stops = any(ATTACK_STOP in raised(g, s) for s in chained(g, machine, state['#'])) or any(
                ATTACK_STOP in exits(g, s) for s in enclosing(g, machine, up))
            out += [msg] if not stops and msg not in out else []
    return out


def parents(g: Graph) -> dict:
    """{object: [the objects of `g` whose fields name it]}."""
    out = {}
    for ref, o in g.objs.items():
        for child in _names(o['fields']):
            out.setdefault(child, []).append(ref)
    return out


def _names(value) -> list:
    """Every '#nnnn' object name inside a field value."""
    if isinstance(value, str):
        return [value] if value.startswith('#') else []
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return [name for v in items for name in _names(v)]


def enclosing(g: Graph, ref: str, up: dict) -> list:
    """The state infos of `g` whose generators hold object `ref` (`up`: parents)."""
    seen, todo = set(), list(up.get(ref, []))
    while todo:
        cur = todo.pop()
        if cur not in seen:
            seen.add(cur)
            todo += up.get(cur, [])
    return [s for s in seen if g.objs[s]['class'] == 'hkbStateMachineStateInfo']


def exits(g: Graph, state: str) -> set:
    """The event names (lower case) state info `state` of `g` raises on exit."""
    array = g.objs.get(g.objs[state]['fields'].get('exitNotifyEvents'))
    return {g.events[e['id']].lower() for e in array['fields']['events']} if array else set()


def unnamed_attacks(graphs: list, attack: set) -> list:
    """Warnings: each attack event (lower case) no graph names."""
    named = {e.lower() for g in graphs for e in g.events}
    return [f'no graph names attack event {e}' for e in sorted(attack - named)]


def chained(g: Graph, machine: str, state: str) -> list:
    """State `state` of state machine `machine` in `g`, and every state its transitions lead to there."""
    by_id = {g.objs[s]['fields']['stateId']: s for s in g.objs[machine]['fields']['states']}
    out, todo = [], [state]
    while todo:
        cur = todo.pop()
        if cur in out:
            continue
        out.append(cur)
        array = g.objs.get(g.objs[cur]['fields'].get('transitions'))
        todo += [by_id[t['toStateId']] for t in array['fields']['transitions'] if t['toStateId'] in by_id] \
            if array else []
    return out


def raised(g: Graph, ref: str) -> set:
    """The event names (lower case) object `ref` of `g` and the objects under it raise (each {id, payload})."""
    seen, todo, out = set(), [ref], set()
    while todo:
        cur = todo.pop()
        if cur in seen or cur not in g.objs:
            continue
        seen.add(cur)
        stack = [g.objs[cur]['fields']]
        while stack:
            value = stack.pop()
            if isinstance(value, dict) and 'payload' in value and isinstance(value.get('id'), int):
                out |= {g.events[value['id']].lower()} if 0 <= value['id'] < len(g.events) else set()
            stack += list(value.values()) if isinstance(value, dict) else value if isinstance(value, list) else []
            todo += [value] if isinstance(value, str) and value.startswith('#') else []
    return out


def attack_states(g: Graph, attack: set):
    """Yield (event, its state machine, state info object) per transition of `g` on an event in `attack`."""
    for ref, (machine, _) in transition_owners(g.objs).items():
        states = {g.objs[s]['fields']['stateId']: g.objs[s] for s in g.objs[machine]['fields']['states']}
        for t in g.objs[ref]['fields']['transitions']:
            event = g.events[t['eventId']] if t['eventId'] >= 0 else ''
            if event.lower() in attack and t['toStateId'] in states:
                yield event, machine, states[t['toStateId']]


def unlisted_clips(g: Graph, listed: dict, read, folder: PureWindowsPath, strict: bool = True) -> list:
    """Each clip `g` plays that read() lacks though its file data (`listed`: file_data_names) names it, and with
    `strict`, each its file data lacks; a listed path is relative to `folder` unless it starts there."""
    out = []
    for o in g.objs.values():
        name = PureWindowsPath(o['fields']['animationName']).stem if o['class'] == 'hkbClipGenerator' else None
        path = listed.get(name) if name else None
        if strict and name and path is None:
            out.append(f'{g.path}: {name} not in its file data')
        elif path and read(_under(folder, path) + '.hkx') is None:
            out.append(f'{g.path}: {name} listed as {path}.hkx, which is not there')
    return sorted(set(out))


def _under(folder: PureWindowsPath, path: str) -> str:
    """`path` under `folder`, '..' resolved, unless it starts there."""
    return path if path.lower().startswith(str(folder).lower() + '\\') else ntpath.normpath(str(folder / path))


# ---------------------------------------------------------------------------
# AnimTextData
# ---------------------------------------------------------------------------

def anim_text(kind: str, name, read) -> 'bytes | None':
    """AnimTextData file `name` (an id or a file stem) of `kind`."""
    return read(f'AnimTextData\\{kind}\\{name}.txt')


def missing_anim_text(race: Race, root: str, read) -> list:
    """The AnimTextData files `race` lacks: its project's file data, its root graph's GRAPH_KINDS, and each of its
    entries' ENTRY_KINDS unless the persistent list names the entry."""
    persistent = anim_text('AnimationOffsets', 'PersistantSubgraphInfoAndOffsetData', read) or b''
    listed = {line.strip().lower() for line in persistent.decode('cp1252').split()}
    stem = PureWindowsPath(race.project).stem.lower()
    out = [f'AnimationFileData\\{stem}.txt'] if anim_text('AnimationFileData', stem, read) is None else []
    out += [f'{kind}\\{crc(root.lower())}.txt ({root})' for kind in GRAPH_KINDS
            if anim_text(kind, crc(root.lower()), read) is None]
    for e in race.entries:
        key = entry_id(e['paths'], e['graph'])
        out += [f'{kind}\\{key}.txt ({e["graph"]})' for kind in ENTRY_KINDS
                if f'{key}.txt' not in listed and anim_text(kind, key, read) is None]
    return out


def loose_anim_text(data_dir: Path) -> int:
    """How many AnimTextData files `data_dir` holds loose."""
    root = data_dir / ANIM_TEXT
    return sum(1 for p in root.rglob('*') if p.is_file()) if root.is_dir() else 0


def bad_speeds(movts: dict) -> list:
    """Each MOVT whose SPED size isn't its form version's layout."""
    return [f'{edid}: form version {version}, SPED {len(sped)} bytes' for edid, (version, _, sped) in movts.items()
            if sped and (len(sped) == NEW_SPED_SIZE) != (version >= NEW_SPED_VERSION)]


# ---------------------------------------------------------------------------
# A race
# ---------------------------------------------------------------------------

def own_graphs(race: Race, own, read) -> tuple:
    """(root Graph or None, [the entries' other Graphs], [the Graphs those load by reference]) of `race`: those own()
    finds, read through read()."""
    root = root_graph(race.project, read) if race.project else None
    paths = {e['graph'].lower(): e['graph'] for e in race.entries}
    if root:
        paths.pop(root.lower(), None)
    raw = read(root) if root and own(root) else None
    subs = [parse(p, data) for p in sorted(paths.values()) if own(p) and (data := read(p))]
    top = ([parse(root, raw)] if raw else []) + subs
    return (top[0] if raw else None), subs, referenced(top, own, read)


def referenced(graphs: list, own, read) -> list:
    """The Graphs `graphs` load by reference (REFERENCE), and those load, each once: the files own() finds; a name
    is relative to the actor folder above its graph's Behaviors folder."""
    seen, out, todo = {g.path.lower() for g in graphs}, [], list(graphs)
    while todo:
        g = todo.pop()
        base = PureWindowsPath(g.path).parent.parent
        for o in g.objs.values():
            path = str(base / o['fields'][REFERENCE_NAME]) if o['class'] == REFERENCE else None
            if path and path.lower() not in seen and own(path) and (data := read(path)):
                seen.add(path.lower())
                out.append(parse(path, data))
                todo.append(out[-1])
    return out


def check_race(race: Race, own, read, movts: set, report: Report) -> bool:
    """Run every check on `race` into `report`; False when none of its graphs is own()."""
    root, subs, refs = own_graphs(race, own, read)
    if root is None and not subs:
        return False
    graphs = ([root] if root else []) + subs + refs
    report.add(race.edid, 'names', missing_names(root, subs) if root else [])
    report.add(race.edid, 'names', root_names(root) if root else [], warn=True)
    for g in graphs:
        report.add(race.edid, 'wildcards', unflagged_wildcards(g))
        report.add(race.edid, 'clip names', shared_clip_names(g))
        report.add(race.edid, 'iState', clashing_states(g))
        report.add(race.edid, 'iState', odd_states(g, movts), warn=True)
    report.add(race.edid, 'attacks', attack_faults(graphs, race.attack))
    report.add(race.edid, 'attacks', unnamed_attacks(graphs, race.attack), warn=True)
    report.add(race.edid, 'clips', _clip_faults(race, root, subs, read))
    report.add(race.edid, 'anim text', missing_anim_text(race, root.path, read) if root else [])
    return True


def _clip_faults(race: Race, root: 'Graph | None', subs: list, read) -> list:
    """unlisted_clips of the root graph against its project's file data, and of each entry graph against that
    entry's, not strict (vanilla's shared graphs name clips an entry's folders may lack)."""
    folder = PureWindowsPath(race.project).parent
    project = anim_text('AnimationFileData', PureWindowsPath(race.project).stem.lower(), read)
    out = unlisted_clips(root, file_data_names(project.decode('cp1252')), read, folder) if root and project else []
    for g in subs:
        entries = [e for e in race.entries if e['graph'].lower() == g.path.lower()]
        listed = [anim_text('AnimationFileData', entry_id(e['paths'], e['graph']), read) for e in entries]
        out += [line for text in listed if text for line in unlisted_clips(
            g, file_data_names(text.decode('cp1252')), read, PureWindowsPath(), False)]
    return out


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def folder_reader(data_dir: Path, *more: Archives):
    """read(path under Meshes) -> bytes or None: loose in `data_dir`, else from its BA2s (indexed once), else
    from `more`."""
    archives = (Archives(data_dir, '*.ba2'), *more) if data_dir.is_dir() else more

    def read(rel: str) -> 'bytes | None':
        """The file at Meshes path `rel`."""
        loose = data_dir / 'Meshes' / rel.replace('\\', '/')
        if loose.is_file():
            return loose.read_bytes()
        key = f'meshes\\{rel}'.lower().replace('/', '\\')
        return next((a.read(key) for a in archives if key in a.by_name), None)
    return read


def check(plugin: Path, data_dir: Path, only: set = frozenset()) -> tuple:
    """(Report, races checked) for `plugin` with its files in `data_dir` (the game's archives behind it)."""
    raw, report = plugin.read_bytes(), Report()
    races, movts = plugin_records(raw)
    names, own_read = movement_names(raw, data_dir), folder_reader(data_dir)
    read = folder_reader(data_dir, Archives(FALLOUT4_DIR / 'Data'))
    checked = [r.edid for r in races if (not only or r.edid in only) and
               check_race(r, lambda path: own_read(path) is not None, read, names, report)]
    report.add(plugin.name, 'MOVT speed', bad_speeds(movts))
    loose = loose_anim_text(data_dir)
    report.add(plugin.name, 'loose', [f'{loose} AnimTextData files are loose (packed is the tested form)'] if loose
               else [], warn=True)
    return report, checked


def print_report(report: Report, checked: list) -> int:
    """Print `report`; the exit code (1 on an error)."""
    for kind, found in (('error', report.errors), ('warning', report.warnings)):
        for subject, lines in found.items():
            print(subject)
            print('\n'.join(f'  {kind} {line}' for line in lines))
    errors, warnings = (sum(map(len, d.values())) for d in (report.errors, report.warnings))
    print(f'{len(checked)} races checked: {errors} errors, {warnings} warnings')
    return 1 if errors else 0


def main(argv=None) -> int:
    """Check a plugin's creature graphs and AnimTextData; the exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--data', type=Path, help="the plugin's data folder (default: the plugin's folder)")
    ap.add_argument('--race', nargs='*', default=(), help='only these race EditorIDs')
    args = ap.parse_args(argv)
    report, checked = check(args.plugin, args.data or args.plugin.parent, set(args.race))
    return print_report(report, checked)


if __name__ == '__main__':
    sys.exit(main())
