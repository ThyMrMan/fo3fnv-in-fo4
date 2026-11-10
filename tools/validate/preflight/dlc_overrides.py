"""What a DLC build (a plugin with built masters) holds that is its master's.

- An override byte-identical to the master's record (flags without compression, data), unless it heads a children
  group that still holds a record (the game topic or quest a DLC line sits under). One the DLC's source also
  overrides is a review: the source authored it.
- An own INFO that copies a master line: its ledger key names a source line a master holds, which the DLC's source
  does not change (say_topics.dlc_lines).
- A voice file under `Sound/Voice/<plugin>/` whose INFO the DLC does not own.
- A copy of a master's own-rig creature file (a `Meshes/Actors/<rig>` folder holding `CharacterAssets/skeleton.nif` in the
  master's folder and not in Fallout 4) or a master worldspace's LOD (`LODSettings`, `Meshes/Terrain`,
  `Textures/Terrain`).
- A master record this build and another finished DLC build beside it (a sibling profile or mod folder) both
  override: overrides do not stack, so the plugin loaded last wins. A review when both DLCs' sources override it.
- A file under the folders the build lists (stale_files.roots) that no file list names: stale when older than the
  build, else made by it but left off its list (a review: no later build prunes it).

See: docs/fork/fo4_preflight.md#dlc-overrides
"""

import re
import time
from collections import defaultdict
from pathlib import Path

from fo4_import.app.files import Files
from fo4_import.base.install import FALLOUT4_DIR, file_masters
from fo4_import.base.ledger import ledger_path
from fo4_import.base.master_overrides import master_records
from fo4_import.pipeline.export_index import export_masters, own_records
from fo4_import.pipeline.stale_files import LIST_SUFFIX, SLACK, listed, roots
from fo4_import.spike.say_topics import dlc_lines
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, walk
from tools.validate.preflight.build_diff import sample
from tools.validate.preflight.build_history import read_stamp
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.fo4_dialogue import line_parts

#: Group types whose label is the FormID of the record heading them (world, cell, topic and quest children).
HEADED_GROUPS = (1, 6, 7, 8, 9, 10)

#: A voice file: `<INFO object id>_<response>.fuz` (or .xwm, .lip).
VOICE = re.compile(r'sound\\voice\\[^\\]+\\[^\\]+\\([0-9a-f]{8})_\d+\.\w+$')

#: An own-rig skeleton's Data path, loose or archived (the Main BA2 holds a deployed build's meshes); group 1 the rig.
SKELETON = re.compile(r'meshes\\actors\\([^\\]+)\\characterassets\\skeleton\.nif')

#: Folders holding a worldspace's LOD, by its EditorID.
LOD_FOLDERS = ('lodsettings\\{}.lod', 'meshes\\terrain\\{}\\', 'textures\\terrain\\{}\\')

#: FO4 signatures whose source records went by another signature too.
SOURCE_SIGS = {'ACHR': ('ACHR', 'ACRE'), 'NPC_': ('NPC_', 'CREA')}

#: The build stamp's time format.
STAMP_TIME = '%Y-%m-%d %H:%M:%S'


def identical_overrides(plugin: Path, index, masters: list) -> tuple:
    """({signature: [FormID]} of overrides identical to their master's record, count of identical ones kept as
    the head of a children group)."""
    held = {index.masters.index(p.name) for p in masters}
    wanted = {r.form_id: r.type.encode() for r in index.by_fid.values() if r.form_id >> 24 in held}
    theirs = master_records(masters, wanted, list(index.masters))
    same, headed = [], set()
    for rec, stack in walk(Path(plugin).read_bytes()):
        headed |= {g.label_fid for g in stack.groups if g.type in HEADED_GROUPS}
        if theirs.get(rec.form_id) == (rec.flags & ~FLAG_COMPRESSED, rec.body):
            same.append((rec.sig.decode(), rec.form_id))
    out = defaultdict(list)
    for sig, fid in same:
        if fid not in headed:
            out[sig].append(fid)
    return out, sum(1 for _s, fid in same if fid in headed)


def source_keys(export_dir: Path, sig: str) -> set:
    """{(master name, object id)} of the master records of FO4 type `sig` a DLC's source export overrides."""
    if not Path(export_dir).is_dir():
        return set()
    names = [Path(f).name for f in export_masters(str(export_dir))]
    return {(names[fid >> 24], fid & 0xFFFFFF) for kind in SOURCE_SIGS.get(sig, (sig,))
            for fid in (int(r['FormID'], 16) for r in own_records(export_dir, kind)) if fid >> 24 < len(names)}


def source_overrides(index, export_dir: Path, sig: str) -> set:
    """The build's FormIDs of the `sig` master records its source overrides."""
    return {index.masters.index(name) << 24 | oid for name, oid in source_keys(export_dir, sig)
            if name in index.masters}


def plugin_overrides(path: Path, names: set) -> dict:
    """{(master name, object id): signature} of the records plugin `path` overrides from masters `names`."""
    masters = file_masters(path)
    return {(masters[r.form_id >> 24], r.form_id & 0xFFFFFF): r.sig.decode()
            for r, _ in walk(Path(path).read_bytes(), bodies=())
            if r.form_id >> 24 < len(masters) and masters[r.form_id >> 24] in names}


def sibling_builds(plugin: Path, names: set) -> list:
    """Other finished builds beside `plugin`'s folder (profile folders, mod folders) with a master in `names`."""
    folder = Path(plugin).parent
    found = (p for d in folder.parent.iterdir() if d.is_dir() and d != folder for p in d.glob('*.es[mpl]'))
    return sorted(p for p in found if p.name != Path(plugin).name and p.name not in names
                  and read_stamp(p).get('status') == 'finished' and names & set(file_masters(p)))


def record_bodies(path: Path, keys: set) -> dict:
    """{(plugin name, object id): (flags without compression, data)} of plugin `path`'s records in `keys` (its
    overrides and its own)."""
    names = [*file_masters(path), Path(path).name]
    out = {}
    for rec, _ in walk(Path(path).read_bytes()):
        key = (names[rec.form_id >> 24], rec.form_id & 0xFFFFFF) if rec.form_id >> 24 < len(names) else None
        if key in keys:
            out[key] = (rec.flags & ~FLAG_COMPRESSED, rec.body)
    return out


def shared_with(game: str, index, other: Path, keys: list, sig: str, kinds: dict) -> list:
    """The findings for master records of type `sig` (`keys`) this build and `other` both override: an error, or a
    review of each kind in `kinds` ({kind: keys}: identical to the master in both, authored by both sources)."""
    out, left = [], set(keys)
    for kind, rows in [*kinds.items(), ('shared', keys)]:
        rows = sorted(k for k in rows if k in left)
        left -= set(rows)
        text = [f'{name} {oid:06X} {index.edid(index.masters.index(name) << 24 | oid)}'.rstrip() for name, oid in rows]
        out += [Finding('dlc', f'dlc|{game}|{kind}|{other.name}|{sig}', 'error' if kind == 'shared' else 'review',
                        f'{len(rows)} {sig} master records are overridden here and by {other.name} too ({kind}): '
                        f'only the plugin loaded last counts', sample(text))] if rows else []
    return out


def shared_findings(game: str, index, plugin: Path, masters: list, export_dir: Path) -> list:
    """Per other DLC build beside this one and signature: master records both override (overrides do not stack);
    an error unless both copies are byte-identical to the master's or both DLCs' sources override the record."""
    names = {p.name for p in masters}
    ours = plugin_overrides(plugin, names)
    pairs = {other: [k for k, s in plugin_overrides(other, names).items() if ours.get(k) == s]
             for other in sibling_builds(plugin, names)}
    keys = set().union(set(), *pairs.values())
    fid = {k: index.masters.index(k[0]) << 24 | k[1] for k in keys}
    master = master_records(masters, {fid[k]: ours[k].encode() for k in keys}, list(index.masters))
    mine, out = record_bodies(plugin, keys), []
    for other, shared in pairs.items():
        theirs, source = record_bodies(other, set(shared)), Path(export_dir).parent / f'{other.stem}.esm'
        same = {k for k in shared if mine.get(k) == theirs.get(k) == master.get(fid[k])}
        for sig in sorted({ours[k] for k in shared}):
            rows = [k for k in shared if ours[k] == sig]
            kinds = {'shared-identical': same, 'shared-authored': source_keys(export_dir, sig) & source_keys(source, sig)}
            out += shared_with(game, index, other, rows, sig, kinds)
    return out


def identical_findings(game: str, index, same: dict, export_dir: Path) -> list:
    """Per signature: an error for unauthored identical overrides, a review for those the DLC's source holds."""
    out = []
    for sig, fids in sorted(same.items()):
        authored = source_overrides(index, export_dir, sig)
        for kind, rows, severity in (('identical', [f for f in fids if f not in authored], 'error'),
                                     ('identical-authored', [f for f in fids if f in authored], 'review')):
            text = [f'{f:08X} {index.edid(f)}'.rstrip() for f in rows]
            why = ', as the DLC\'s source overrides them' if severity == 'review' else ''
            out += [Finding('dlc', f'dlc|{game}|{kind}|{sig}', severity,
                            f'{len(rows)} {sig} overrides are byte-identical to their master\'s record{why}',
                            sample(text))] if rows else []
    return out


def copied_lines(plugin: Path, index, export_dir: Path) -> list:
    """The build's own INFOs copying a master's source line the DLC's source does not change."""
    source_own = len(export_masters(str(export_dir)))
    changed = {int(f, 16) for f in dlc_lines(export_dir) or ()}
    parts = line_parts(index, ledger_path(plugin), ())
    return sorted(f'{fid:08X} {index.edid(fid)} (copies source {line:08X})'.rstrip()
                  for line, by_part in parts.items() if line >> 24 < source_own and line not in changed
                  for fids in by_part.values() for fid in fids)


def foreign_voice(index, files: Files, plugin: Path) -> list:
    """Voice files under the build's own voice folder whose INFO it does not own."""
    own = len(index.masters) << 24
    folder = f'sound\\voice\\{Path(plugin).name.lower()}\\'
    out = []
    for path in sorted({*files.loose(), *files.archived()}):
        match = VOICE.match(path) if path.startswith(folder) else None
        rec = index.by_fid.get(own | int(match.group(1), 16) & 0xFFFFFF) if match else None
        if match and getattr(rec, 'type', '') != 'INFO':
            out.append(path)
    return out


def master_prefixes(masters: list, game: Files) -> tuple:
    """(Data path prefixes of the masters' own-rig folders, a skeleton Fallout 4 does not ship; of their worldspace
    LOD)."""
    rigs, lods = [], []
    for path in masters:
        own = Files([Path(path).parent])
        names = {m.group(1) for p in {*own.loose(), *own.archived()} for m in [SKELETON.fullmatch(p)] if m}
        rigs += [f'meshes\\actors\\{r}\\' for r in sorted(names)
                 if game.where(f'meshes\\actors\\{r}\\characterassets\\skeleton.nif') is None]
        worlds = {rec.string(b'EDID').lower() for rec, _ in walk(Path(path).read_bytes(), b'WRLD')} - {''}
        lods += [f.format(w) for w in worlds for f in LOD_FOLDERS]
    return tuple(rigs), tuple(lods)


def master_files(files: Files, rigs: tuple, lods: tuple, theirs: set) -> list:
    """Files under `lods`, or under `rigs` at a path in `theirs`."""
    return sorted(p for p in {*files.loose(), *files.archived()}
                  if p.startswith(lods) or p.startswith(rigs) and p in theirs)


def unlisted_files(plugin: Path) -> tuple:
    """([stale], [made by the build]): files under the listed folders no file list beside the plugin names, older
    than the build's start or not."""
    folder = Path(plugin).parent
    named = set().union(*(listed(p.with_name(p.name[:-len(LIST_SUFFIX)])) for p in folder.glob('*' + LIST_SUFFIX)))
    started = read_stamp(plugin).get('started')
    start = time.mktime(time.strptime(started, STAMP_TIME)) - SLACK if started else float('inf')
    stale, made = [], []
    for root in roots('', True):
        base = folder / root
        for path in (p for p in base.rglob('*') if p.is_file()) if base.is_dir() else ():
            rel = path.relative_to(folder).as_posix()
            if rel not in named:
                (made if path.stat().st_mtime >= start else stale).append(rel)
    return sorted(set(stale)), sorted(set(made))


def _finding(game: str, kind: str, summary: str, rows: list, severity: str = 'error') -> list:
    """One finding of `kind` when `rows` is not empty."""
    return [Finding('dlc', f'dlc|{game}|{kind}', severity, f'{len(rows)} {summary}', sample(rows))] if rows else []


def audit(game: str, index, plugin: Path, masters: list, export_dir: Path) -> list:
    """The DLC override findings for one Fallout 4 build; none without built masters."""
    if not masters:
        return []
    same, kept = identical_overrides(plugin, index, masters)
    print(f'  dlc: masters {", ".join(p.name for p in masters)}; {kept} identical overrides kept as group heads')
    files, shipped = Files([Path(plugin).parent]), Files([Path(p).parent for p in masters])
    theirs = {*shipped.loose(), *shipped.archived()}
    out = identical_findings(game, index, same, export_dir)
    out += _finding(game, 'copied-lines', 'own INFOs copy a master\'s line the DLC does not change',
                    copied_lines(plugin, index, export_dir))
    out += _finding(game, 'voice', 'voice files are for INFOs the DLC does not own', foreign_voice(index, files, plugin))
    out += _finding(game, 'master-files', 'files are a master\'s own-rig creature or worldspace LOD files',
                    master_files(files, *master_prefixes(masters, Files([FALLOUT4_DIR / 'Data'])), theirs))
    out += shared_findings(game, index, plugin, masters, export_dir)
    stale, made = unlisted_files(plugin)
    out += _finding(game, 'stale', 'files in the listed folders predate the build and are on no file list', stale)
    return out + _finding(game, 'unlisted', 'files the build made are not on its file list, so no build prunes them',
                          made, 'review')
