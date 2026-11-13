"""AnimTextData the Creation Kit used to write: own-rig creature projects, the offsets of entries playing clips of
their own, and the plugin's sync data.

A creature (a race whose root graph, SGNM, is in the data folder) gets offsets, speed info and dynamic idle data
under its project's id (MODL), and event info and clip generator data under its root graph's id: both the CRC of the
lower-cased path. Its names are the clips its attacks play. Its subgraph entries on that graph get the project's
files and a one-pose stance. Any other entry vanilla and the copier (gun_anim_text) leave gets offsets naming its
file data's clips; its other files are its template's, or empty dynamic idle data without one.

See: docs/fork/research/anim_text_data.md#ours
"""

import concurrent.futures
import functools
import hashlib
import re
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from asset_convert.havok.clip_retarget import Skeleton, compose, mat_to_quat_wxyz, quat_wxyz_to_mat
from core.build_resources import pool_workers
from core.process_job import join_pool_job
from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.havok import anim_offsets, anim_speed, packfile
from fo4_import.base.ba2 import Archives
from fo4_import.base.ba2_pack import data_file
from fo4_import.havok.gun_anim_text import (ANIM_TEXT, HEADER_SIZE, PERSISTENT, Vanilla, crc, entry_id,
                                           template_paths)
from fo4_import.pipeline import work_cache
from fo4_import.pipeline.elric_cache import write_new
from fo4_import.havok.gun_clips import fo4_skeleton, subgraph_entries
from fo4_import.rig.behavior import FIRE_START
from tes5_import.base.tes5_reader import subrecords

#: An entry's dynamic idle data when it has no dynamic idles: vanilla's text.
DYNAMIC_IDLE = b'Version 1\n'
#: The plugin's resolved synchronized animations: FNV and FO3 have none.
SYNC_DATA = b'V4\n0\n'
#: hkbClipGenerator's mirror flag; the class whose children are dynamic idle placeholders.
MIRROR, DYNAMIC = 4, 'DynamicAnimationTaggingGenerator'
#: The events that start a gun attack in our graphs (behavior.fire_start).
FIRE = re.compile(re.escape(FIRE_START).replace(re.escape('{}'), r'\d+'), re.IGNORECASE)
#: The AnimTextData kinds the build writes in full, so files it did not write this run are stale (prune).
OWNED = ('AnimationOffsets', 'AnimationSpeedInfo', 'AnimationStanceData', 'DynamicIdleData', 'AnimEventInfo',
         'ClipGeneratorData', 'SyncAnimData')
#: The CK's transition arrays, skipped when following a state's generator.
TRANSITIONS = 'hkbStateMachineTransitionInfoArray'
#: The event (lower case) a creature's stance pose follows, and the BPND part types of its head and torso.
EQUIP, TORSO, HEAD = 'weapequip', 0, 1
#: A packed BPND's part type byte.
PART_TYPE = 65
#: A one-pose stance file's start (type name, version 1, one pose) and a pose's DirectAt transform (identity).
STANCE_START = anim_offsets.pack_string('AnimationBoneTransform') + struct.pack('<2I', 1, 1)
IDENTITY = struct.pack('<7f', 1, 0, 0, 0, 0, 0, 0)
#: Work cache site and version of {(clip path lower, SHA-1 of its bytes): Clip}; records worth a process pool.
RECORDS_SITE, RECORDS_VERSION, POOLED = 'anim offsets records', 1, 16
#: What a record worker commits, for the worker count (build_resources.pool_workers).
RECORD_WORKER_BYTES = 256 << 20
#: A record worker's event spellings (_start).
_worker = {}


# ---------------------------------------------------------------------------
# Offsets
# ---------------------------------------------------------------------------

@dataclass
class Race:
    """A RACE record's animation fields: its project (the first MODL after NAM3), root graphs (SGNM), attack events
    (ATKE, lower case), body part data (GNAM), the ids of its subgraph entries on its first root graph, and its equip
    slots naming a node: [(index among its slots, QNAM; node, ZNAM)]."""
    project: str = ''
    graphs: list = field(default_factory=list)
    attack: set = field(default_factory=set)
    body: int = 0
    entries: list = field(default_factory=list)
    slots: list = field(default_factory=list)


@dataclass
class Known:
    """What vanilla's offsets know: each event name (lower case) as they spell it, and each clip path's record; the
    records this run computed, by clip path (lower case); the work cache's records table, read once per run
    (compute), and whether this run added to it (save)."""
    spelled: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    computed: dict = field(default_factory=dict)
    table: 'dict | None' = None
    unsaved: bool = False


def known(vanilla: Vanilla) -> Known:
    """Every vanilla offsets file's event spellings (the most common) and clip records (the first)."""
    counts, out = {}, Known()
    for (kind, _), reader in sorted(vanilla.files.items()):
        if kind != 'animationoffsets':
            continue
        for clip in anim_offsets.parse(reader()).clips:
            out.records.setdefault(clip.path.lower(), clip)
            for _, text in clip.events:
                counts.setdefault(text.lower(), Counter())[text] += 1
    out.spelled = {name: spellings.most_common(1)[0][0] for name, spellings in counts.items()}
    return out


def compute(paths: list, read, k: Known) -> None:
    """Put each clip of `paths` (no extension) not in k.computed there: its record (spelled_record of read(path +
    '.hkx')) looked up in the work cache's table by path and bytes (k.table, kept by save()), the rest made in
    worker processes; vanilla's record when the clip can't be read, else None.
    See: docs/fork/research/anim_text_data.md#ours
    """
    todo = {path.lower(): path for path in paths if path.lower() not in k.computed}
    raws = {key: raw for key, path in todo.items() if (raw := read(path + '.hkx'))}
    keys = {key: (key, hashlib.sha1(raw).hexdigest()) for key, raw in raws.items()}
    if k.table is None and keys:
        k.table = work_cache.lookup(RECORDS_SITE, anim_offsets.__name__, _inputs(k), {})
    table = k.table if k.table is not None else {}
    missing = [key for key in keys if keys[key] not in table]
    table.update(zip((keys[key] for key in missing), _records([(todo[key], raws[key]) for key in missing], k.spelled)))
    k.unsaved |= bool(missing)
    k.computed.update({key: table[keys[key]] if key in keys else k.records.get(key) for key in todo})


def _inputs(k: Known) -> tuple:
    """The records table's work cache inputs: its version and the event spellings."""
    return RECORDS_VERSION, sorted(k.spelled.items())


def save(k: Known) -> None:
    """Keep the records table in the work cache when compute() added to it this run."""
    if k.unsaved:
        work_cache.store(RECORDS_SITE, anim_offsets.__name__, _inputs(k), k.table)
        k.unsaved = False


def _records(jobs: list, spelled: dict) -> list:
    """spelled_record of each (path, bytes) in `jobs`, in order: in worker processes (the resource profile's,
    build_resources.pool_workers) when there are POOLED or more."""
    if len(jobs) < POOLED:
        return [anim_offsets.spelled_record(path, raw, spelled) for path, raw in jobs]
    workers = pool_workers(RECORD_WORKER_BYTES, len(jobs))
    with concurrent.futures.ProcessPoolExecutor(workers, initializer=_start, initargs=(spelled,)) as pool:
        return list(pool.map(_record, jobs, chunksize=8))


def _start(spelled: dict) -> None:
    """A record worker's start: join the pool job; the event spellings."""
    join_pool_job()
    _worker['spelled'] = spelled


def _record(job: tuple) -> anim_offsets.Clip:
    """spelled_record of `job` (path, bytes) in a worker."""
    return anim_offsets.spelled_record(*job, _worker['spelled'])


def offsets(graph: str, names: dict, read, k: Known) -> bytes:
    """The offsets file of `graph` naming `names` {clip name: path, no extension}, in name order, each record
    compute()d."""
    out = anim_offsets.Offsets(graph, sorted(names.items()))
    compute([path for _, path in out.names], read, k)
    records = {path.lower(): k.computed[path.lower()] for _, path in out.names}
    out.clips = [clip for clip in records.values() if clip]
    return anim_offsets.pack(out)


# ---------------------------------------------------------------------------
# Creatures
# ---------------------------------------------------------------------------

def _refs(value):
    """Every '#nnnn' object reference inside a field value."""
    if isinstance(value, str) and value.startswith('#'):
        yield value
    elif isinstance(value, (dict, list)):
        for v in value.values() if isinstance(value, dict) else value:
            yield from _refs(v)


def _settled(objs: dict, ref: str, out: list, seen: set, sent: frozenset = frozenset()) -> None:
    """Append the clip generators `ref` plays once settled: each state machine enters only its start state, or
    the state a transition from it on an event id in `sent` leads to."""
    if ref in seen or ref not in objs:
        return
    seen.add(ref)
    cls, f = objs[ref]['class'], objs[ref]['fields']
    if cls == 'hkbClipGenerator':
        out.append(ref)
    elif cls == 'hkbStateMachine':
        state = _entered(objs, f, sent)
        if state:
            _settled(objs, objs[state]['fields']['generator'], out, seen, sent)
    else:
        for child in _refs(f):
            if objs.get(child, {}).get('class') != TRANSITIONS:
                _settled(objs, child, out, seen, sent)


def _entered(objs: dict, machine: dict, sent: frozenset) -> 'str | None':
    """The state a state machine (fields `machine`) settles in: its start state, or where a transition from it on
    an event id in `sent` leads."""
    by_id = {objs[s]['fields']['stateId']: s for s in machine['states']}
    state = by_id.get(machine['startStateId'])
    array = objs.get(objs[state]['fields'].get('transitions'), {}) if state else {}
    to = [t['toStateId'] for t in array.get('fields', {}).get('transitions', []) if t['eventId'] in sent]
    return by_id.get(to[0], state) if to else state


def _owners(objs: dict) -> dict:
    """{transition array: (its state machine, whether it is the machine's wildcard transitions)}."""
    out = {}
    for ref, o in objs.items():
        if o['class'] == 'hkbStateMachine':
            out[o['fields'].get('wildcardTransitions')] = (ref, True)
            out.update({objs[s]['fields']['transitions']: (ref, False) for s in o['fields']['states']})
    out.pop(None, None)
    return out


def attacks(objs: dict, events: list, attack: set) -> list:
    """[(event, wildcard, [clip generators])] per transition on an attack event (lower case in `attack`, or a gun's
    fire event), in the graph's order: the clips its target state plays (_settled).
    See: docs/fork/research/anim_text_data.md#root-keys
    """
    out, owners = [], _owners(objs)
    for ref, o in objs.items():
        if o['class'] != TRANSITIONS:
            continue
        machine, wildcard = owners[ref]
        for t in o['fields']['transitions']:
            name = events[t['eventId']] if t['eventId'] >= 0 else ''
            if name.lower() in attack or FIRE.fullmatch(name):
                state = next(s for s in objs[machine]['fields']['states']
                             if objs[s]['fields']['stateId'] == t['toStateId'])
                played = []
                _settled(objs, objs[state]['fields']['generator'], played, set())
                out.append((name, wildcard, played))
    return out


def event_info(graph: str, found: list, objs: dict) -> bytes:
    """AnimEventInfo V2: the graph, an empty line, then per attack its event, 1 for a wildcard transition, and the
    names of the clip generators it plays."""
    lines = ['V2', graph, '', str(len(found))]
    for event, wildcard, played in found:
        lines += [event, str(int(wildcard)), str(len(played))] + [objs[g]['fields']['name'] for g in played]
    return ('\n'.join(lines) + '\n').encode('cp1252')


@functools.lru_cache(maxsize=1 << 16)
def _stem(name: str) -> str:
    """A graph path's file name without its extension."""
    return PureWindowsPath(name).stem


def _generator(f: dict, dynamic: bool, events: list, triggers: list, spelled: dict) -> bytes:
    """One clip generator's ClipGeneratorData record: names, speed, crops, mirror and dynamic bytes, and the first
    trigger of each event vanilla's offsets name."""
    first = {}
    for t in triggers:
        name = events[t['event']['id']].lower()
        if name in spelled:
            first.setdefault(spelled[name], t)
    out = [anim_offsets.pack_string(f['name']), anim_offsets.pack_string('' if dynamic else _stem(f['animationName'])),
           struct.pack('<3f2BI', f['playbackSpeed'], f['cropStartAmountLocalTime'], f['cropEndAmountLocalTime'],
                       bool(f['flags'] & MIRROR), dynamic, len(first))]
    out += [anim_offsets.pack_string(name) + struct.pack('<fB', t['localTime'], t['relativeToEndOfClip'])
            for name, t in first.items()]
    return b''.join(out)


def generator_data(graph: str, played: list, objs: dict, events: list, spelled: dict) -> bytes:
    """ClipGeneratorData V4: the graph, then a record per clip generator in `played`.
    See: docs/fork/research/anim_text_data.md#project-files
    """
    dynamic = {child for o in objs.values() if o['class'] == DYNAMIC for child in _refs(o['fields'])}
    out = [anim_offsets.MAGIC, anim_offsets.pack_string(graph), struct.pack('<I', len(played))]
    for ref in played:
        f = objs[ref]['fields']
        triggers = objs[f['triggers']]['fields']['triggers'] if f.get('triggers') in objs else []
        out.append(_generator(f, ref in dynamic, events, triggers, spelled))
    return b''.join(out)


def creature(race: Race, read, k: Known, parts: dict) -> dict:
    """{Data path: bytes} of a creature `race` (Data paths; read(path) gives a Data file's bytes; parts: its body
    part data, {BPND part type: node}): its project's files, and the same under each of its root graph's subgraph
    entries with a stance.
    See: docs/fork/research/anim_text_data.md#ours
    """
    project, graph = race.project, race.graphs[0]
    raw = read(graph)
    objs = {o['#']: o for o in packfile.read(raw).objects}
    events = next(o for o in objs.values() if o['class'] == 'hkbBehaviorGraphStringData')['fields']['eventNames']
    found = attacks(objs, events, race.attack)
    played = [g for _, _, gens in found for g in gens]
    folder = str(PureWindowsPath(project).parent)
    names = {_stem(objs[g]['fields']['animationName']): str(PureWindowsPath(folder, objs[g]['fields']['animationName'])
                                                             .with_suffix('')) for g in played}
    own, root = crc(project.lower()), crc(graph.lower())
    mine = {'AnimationOffsets': offsets(graph, names, read, k), 'DynamicIdleData': DYNAMIC_IDLE,
            'AnimationSpeedInfo': anim_speed.rig_speed(raw, graph, lambda name: _motion(
                read(str(PureWindowsPath(folder, name).with_suffix('.hkx')))))}
    entry = {**mine, 'AnimationStanceData': stance(race, armed_pose(project, objs, events, read), parts)}
    out = {f'AnimEventInfo\\{root}.txt': event_info(graph, found, objs),
           f'ClipGeneratorData\\{root}.txt': generator_data(graph, played, objs, events, k.spelled)}
    out.update({f'{kind}\\{own}.txt': data for kind, data in mine.items() if data is not None})
    out.update({f'{kind}\\{e}.txt': data for e in race.entries for kind, data in entry.items() if data is not None})
    return out


def armed_clip(folder: str, objs: dict, events: list) -> 'str | None':
    """The Data path of the first clip a graph (objects `objs`, project folder `folder`) plays once settled with a
    weapon out; None when it plays none."""
    played, sent = [], frozenset(i for i, name in enumerate(events) if name.lower() == EQUIP)
    for ref, o in objs.items():
        if o['class'] == 'hkbBehaviorGraph':
            _settled(objs, ref, played, set(), sent)
    return str(PureWindowsPath(folder, objs[played[0]]['fields']['animationName']).with_suffix('.hkx')) \
        if played else None


def _skeleton(project: str, read) -> 'Skeleton | None':
    """The rig of project `project` (its first character's rigName); None when read() lacks a file."""
    folder = str(PureWindowsPath(project).parent)
    character = _strings(read(project), 'hkbProjectStringData', 'characterFilenames')
    rig = _strings(read(str(PureWindowsPath(folder, character[0]))), 'hkbCharacterStringData', 'rigName') \
        if character else None
    raw = read(str(PureWindowsPath(folder, rig).with_suffix('.hkx'))) if rig else None
    return fo4_skeleton(raw)[0] if raw else None


def _strings(raw: 'bytes | None', cls: str, name: str):
    """Field `name` of the `cls` object in packfile `raw`; None without either."""
    found = [o['fields'] for o in packfile.read(raw).objects if o['class'] == cls] if raw else []
    return found[0].get(name) if found else None


def _transform(world) -> bytes:
    """A row-vector world matrix as a stance stores it: rotation w x y z, translation."""
    return struct.pack('<7f', *mat_to_quat_wxyz(world[:3, :3]), *world[3, :3])


def armed_pose(project: str, objs: dict, events: list, read) -> dict:
    """{bone: 4x4 row-vector world matrix} of a creature project's rig at frame 0 of the clip its root graph
    (objects `objs`, event names `events`) plays with a weapon out; empty without the rig or clip."""
    path = armed_clip(str(PureWindowsPath(project).parent), objs, events)
    skeleton, raw = _skeleton(project, read), read(path) if path else None
    clip = parse_fo4_animation(raw) if raw else None
    if clip is None or skeleton is None:
        return {}
    local = skeleton.local.copy()
    for track, bone in zip(clip.tracks, clip.track_to_bone_indices):
        if track.rotations:
            x, y, z, w = track.rotations[0]
            local[bone] = compose(track.translations[0][:3], quat_wxyz_to_mat((w, x, y, z)))
    return dict(zip(skeleton.names, skeleton.fk(local)))


def stance(race: Race, pose: dict, parts: dict) -> 'bytes | None':
    """A creature `race`'s AnimationStanceData: one standing unsighted pose of its head and torso nodes (parts:
    {BPND part type: node}) in `pose` (armed_pose), and an unaimed fire record per equip slot naming a node, posed for
    the first slot (the one that holds a weapon); None without the nodes.
    See: docs/fork/research/anim_text_data.md#stance
    """
    if not {parts.get(HEAD), parts.get(TORSO)} <= set(pose):
        return None
    fire = [struct.pack('<4B', 0, 0, 0, slot) + (_transform(pose[node]) if slot == 0 and node in pose else IDENTITY)
            + bytes(18) for slot, node in race.slots]
    return STANCE_START + bytes(4) + _transform(pose[parts[HEAD]]) + _transform(pose[parts[TORSO]]) + IDENTITY + \
        struct.pack('<I', len(fire)) + b''.join(fire)


def _motion(raw: 'bytes | None') -> 'anim_offsets.Motion | None':
    """A clip's root motion; None without the clip."""
    return anim_offsets.motion(raw) if raw else None


def race_fields(body: bytes) -> Race:
    """A RACE record's (subrecords `body`) Race."""
    out, behavior, subs, slots = Race(), False, list(subrecords(body)), 0
    for sig, data in subs:
        text = data.rstrip(b'\0').decode('cp1252') if sig in (b'MODL', b'SGNM', b'ATKE') else ''
        out.project = text if sig == b'MODL' and behavior and not out.project else out.project
        behavior = behavior or sig == b'NAM3'
        out.graphs += [text] if sig == b'SGNM' else []
        out.attack |= {text.lower()} if sig == b'ATKE' else set()
        out.body = struct.unpack('<I', data)[0] if sig == b'GNAM' and len(data) == 4 else out.body
        slots += sig == b'QNAM'
        out.slots += [(slots - 1, data.rstrip(b'\0').decode('cp1252'))] if sig == b'ZNAM' and slots else []
    root = out.graphs[0].lower() if out.graphs else None
    out.entries = sorted({entry_id(e['paths'], e['graph']) for e in subgraph_entries(subs)
                          if e.get('graph', '').lower() == root})
    return out


def body_parts(records: list) -> dict:
    """{BPTD form id: {BPND part type: node (BPNN)}} of packed BPTD records (the first node of a type wins)."""
    out = {}
    for rec in records:
        parts, node = out.setdefault(struct.unpack_from('<I', rec, 12)[0], {}), ''
        for sig, data in subrecords(rec[HEADER_SIZE:]):
            node = data.rstrip(b'\0').decode('cp1252') if sig == b'BPNN' else node
            if sig == b'BPND' and len(data) > PART_TYPE:
                parts.setdefault(data[PART_TYPE], node)
    return out


def creatures(races: list, read, k: Known, parts: dict) -> dict:
    """{Data path under AnimTextData: bytes} of every race in `races` (packed) with a project whose root graph read()
    finds (give it only the data folder's files, so races on vanilla graphs are left out); parts: body_parts."""
    out = {}
    for rec in races:
        race = race_fields(rec[HEADER_SIZE:])
        if race.graphs and read(race.graphs[0]) is not None:
            out.update(creature(race, read, k, parts.get(race.body, {})))
    return out


# ---------------------------------------------------------------------------
# Entries playing their own clips
# ---------------------------------------------------------------------------

def own_clips(races: list, vanilla: Vanilla, copies: dict) -> dict:
    """{entry id: (graph, template id or None)} of the subgraph entries in `races` (packed) that vanilla has no file
    or persistent line for and the copier (gun_anim_text.copied_entries: `copies`) leaves."""
    have, out = {e for _, e in vanilla.files} | vanilla.persistent | set(copies), {}
    for rec in races:
        for e in subgraph_entries(subrecords(rec[HEADER_SIZE:])):
            entry = entry_id(e['paths'], e['graph']) if 'graph' in e else None
            if entry is not None and entry not in have:
                kept = template_paths(e['paths'])
                out.setdefault(entry, (e['graph'], entry_id(kept, e['graph']) if kept else None))
    return out


def file_data_names(text: str) -> dict:
    """{clip name: path without extension} of an entry's AnimationFileData: its clip files, not behavior graphs,
    each named by its file stem (the first wins)."""
    names = {}
    for line in text.splitlines()[4:]:
        if line.lower().endswith('.hkx') and '\\behaviors\\' not in line.lower():
            names.setdefault(_stem(line), line[:-4])
    return names


def entry_files(entries: dict, read, k: Known) -> dict:
    """{Data path under AnimTextData: bytes}: each own_clips entry's offsets, from its file data, and an entry
    without a template's dynamic idle data. Every entry's clips are compute()d at once, each spelled as the
    first entry naming it spells it."""
    named, clips, out = {}, {}, {}
    for entry, (graph, template) in sorted(entries.items()):
        listed = read(f'AnimTextData\\AnimationFileData\\{entry}.txt')
        if listed is not None:
            named[entry] = graph, template, file_data_names(listed.decode('cp1252'))
            for key, path in {path.lower(): path for path in named[entry][2].values()}.items():
                clips.setdefault(key, path)
    compute(list(clips.values()), read, k)
    for entry, (graph, template, names) in named.items():
        out[f'AnimationOffsets\\{entry}.txt'] = offsets(graph, names, read, k)
        out.update({f'DynamicIdleData\\{entry}.txt': DYNAMIC_IDLE} if template is None else {})
    return out


def sync_data(plugin: str) -> dict:
    """{Data path under AnimTextData: bytes}: the plugin's resolved sync data, empty."""
    return {f'SyncAnimData\\ResolvedSyncAnimData{PureWindowsPath(plugin).stem}.txt': SYNC_DATA}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def reader(*data_dirs):
    """read(path under Meshes, backslashes) -> bytes or None: the first of `data_dirs` holding it (data_file) or an
    Archives over the game's."""
    def read(rel: str) -> 'bytes | None':
        """The file at Meshes path `rel`."""
        return next((found for place in data_dirs if (found := _read(place, rel)) is not None), None)
    return read


def _read(place, rel: str) -> 'bytes | None':
    """Meshes path `rel` from a data folder (loose or its archives) or an Archives; None when it lacks it."""
    if isinstance(place, Archives):
        key = f'meshes\\{rel}'.lower()
        return place.read(key) if key in place.by_name else None
    return data_file(place, f'Meshes/{_posix(rel)}')


def _posix(rel: str) -> str:
    """A backslash path with forward slashes."""
    return rel.replace('\\', '/')


def write(data_dir: Path, files: dict) -> list:
    """Each {path under AnimTextData: bytes} into `data_dir` (unchanged files touched); their paths."""
    out = []
    for rel, data in sorted(files.items()):
        out.append(data_dir / ANIM_TEXT / _posix(rel))
        write_new(out[-1], data)
    return out


def prune(data_dir: Path, written: list) -> int:
    """Remove `data_dir`'s AnimTextData files of the kinds the build writes (OWNED) that this run did not write:
    entries gone since, and what the Creation Kit left; how many."""
    keep, gone = {Path(p).resolve() for p in written}, 0
    for kind in OWNED:
        for path in (data_dir / ANIM_TEXT / kind).glob('*.txt'):
            if path.name != PERSISTENT.name and path.resolve() not in keep:
                path.unlink()
                gone += 1
    return gone
