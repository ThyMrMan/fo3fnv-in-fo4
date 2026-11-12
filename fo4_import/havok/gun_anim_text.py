"""AnimTextData for converted guns' third-person subgraph entries, copied from vanilla.

An entry whose FNV folders supply none of its graph's clips plays what its template plays: the same folder list
without FNV's. So the template's offsets, speed, stance and dynamic idle files go under the entry's own id, and
the entry joins the persistent list when its template is on it. First-person entries and entries playing an FNV
clip are left to the Creation Kit (rig/anim_info).

See: docs/fork/research/anim_text_data.md#writer
"""

import zlib
from dataclasses import dataclass, field
from pathlib import Path

from fo4_import.base.ba2 import Archive
from fo4_import.base.ba2_pack import data_file
from fo4_import.havok.gun_clips import subgraph_entries
from fo4_import.pipeline.elric_cache import write_new
from tes5_import.base.tes5_reader import subrecords

#: The AnimTextData folder under a data folder.
ANIM_TEXT = Path('Meshes') / 'AnimTextData'
#: The kinds copied from the template, as folder names.
COPIED = ('AnimationOffsets', 'AnimationSpeedInfo', 'AnimationStanceData', 'DynamicIdleData')
#: The list of entries with persistent subgraph data, under the data folder.
PERSISTENT = ANIM_TEXT / 'AnimationOffsets' / 'PersistantSubgraphInfoAndOffsetData.txt'
#: The folders converted guns' clips go in (lower case), and the part of a first-person graph's path.
FNV, FIRST_PERSON = 'actors\\fnv\\', '\\_1stperson\\'
#: A packed record's header size, before its subrecords.
HEADER_SIZE = 24
SEP = '\\'


# ---------------------------------------------------------------------------
# Ids and file layout
# ---------------------------------------------------------------------------

def _crc(text: str) -> int:
    """AnimTextData's CRC-32 of `text` as given: zero start, no final inversion."""
    return zlib.crc32(text.encode('cp1252'), 0xFFFFFFFF) ^ 0xFFFFFFFF


def entry_id(paths: list, graph: str) -> int:
    """A subgraph entry's AnimTextData id (several folders: lower-cased).
    See: docs/fork/research/anim_text_data.md#ids
    """
    joined = '|'.join(paths)
    return _crc(joined if len(paths) == 1 else joined.lower()) << 32 | _crc(graph.lower())


def template_paths(paths: list) -> 'list | None':
    """`paths` without the FNV folders; None unless both kinds are there."""
    kept = [p for p in paths if not p.lower().startswith(FNV)]
    return kept if 0 < len(kept) < len(paths) else None


def clip_names(offsets: bytes) -> tuple:
    """(graph, lower case; [clip name, lower case]) of an AnimationOffsets file."""
    graph, i = offsets[4:3 + offsets[3]].decode('cp1252').lower(), 4 + offsets[3]
    count, names = int.from_bytes(offsets[i:i + 4], 'little'), []
    i += 4
    for _ in range(count):
        names.append(offsets[i + 1:i + offsets[i]].decode('cp1252').lower())
        i += 1 + offsets[i]
        i += 1 + offsets[i]
    return graph, names


def persistent_ids(text: str) -> set:
    """The ids of a persistent list's `<id>.txt` lines."""
    return {int(line[:-4]) for line in text.split() if line[:-4].isdigit()}


# ---------------------------------------------------------------------------
# Vanilla's files
# ---------------------------------------------------------------------------

@dataclass
class Vanilla:
    """Vanilla's AnimTextData: each graph's clip names (from every offsets file of it), the persistent list (every
    archive's, joined) and the per-id files, {(kind folder, lower case; id): bytes reader}."""
    clips: dict = field(default_factory=dict)
    persistent: set = field(default_factory=set)
    files: dict = field(default_factory=dict)

    def read(self, kind: str, entry: int) -> 'bytes | None':
        """The file of `kind` (folder name) for `entry`; None without one."""
        reader = self.files.get((kind.lower(), entry))
        return reader() if reader else None


def load_vanilla(data: Path) -> Vanilla:
    """Vanilla's AnimTextData from the general BA2s in game folder `data` (no id is in two archives)."""
    out, prefix = Vanilla(), 'meshes\\animtextdata\\'
    for path in sorted(data.glob('*.ba2')):
        archive = Archive(path)
        if archive.kind != b'GNRL':
            continue
        for name in archive.entries:
            if not name.startswith(prefix):
                continue
            kind, stem = name[len(prefix):].split(SEP)[0], name.rsplit(SEP, 1)[1][:-4]
            if stem.isdigit():
                out.files[(kind, int(stem))] = lambda a=archive, n=name: a.read(n)
            elif name == prefix + str(PERSISTENT.relative_to(ANIM_TEXT)).lower():
                out.persistent |= persistent_ids(archive.read(name).decode('cp1252'))
    for (kind, entry), reader in out.files.items():
        if kind == 'animationoffsets':
            graph, names = clip_names(reader())
            out.clips.setdefault(graph, set()).update(names)
    return out


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _fnv_clips(data_dir: Path, entry: int) -> 'set | None':
    """The clip names (lower case) gun_clips pointed at an FNV folder in `entry`'s file data; None without it."""
    path = data_dir / ANIM_TEXT / 'AnimationFileData' / f'{entry}.txt'
    if not path.is_file():
        return None
    lines = path.read_text(encoding='cp1252').splitlines()[4:]
    return {line.rsplit(SEP, 1)[-1][:-4].lower() for line in lines if line[:len(FNV)].lower() == FNV}


def copied_entries(races, data_dir: Path, vanilla: Vanilla) -> dict:
    """{entry id: template id} of the third-person entries in `races` (packed RACE records) that play only vanilla
    clips: FNV and vanilla folders, a graph vanilla has offsets for, and none of the FNV clips in its file data
    (gun_clips) named by that graph."""
    out = {}
    for rec in races:
        for e in subgraph_entries(subrecords(rec[HEADER_SIZE:])):
            kept = template_paths(e['paths']) if 'graph' in e else None
            graph = e.get('graph', '').lower()
            if kept is None or FIRST_PERSON in graph or graph not in vanilla.clips:
                continue
            entry = entry_id(e['paths'], e['graph'])
            if entry in out:
                continue
            fnv = _fnv_clips(data_dir, entry)
            if fnv is not None and not fnv & vanilla.clips[graph]:
                out[entry] = entry_id(kept, e['graph'])
    return out


def write(data_dir: Path, copies: dict, vanilla: Vanilla) -> list:
    """Each entry's template files of the COPIED kinds under its own id in `data_dir` (unchanged files touched);
    their paths."""
    out = []
    for entry, template in sorted(copies.items()):
        for kind in COPIED:
            data = vanilla.read(kind, template)
            if data is not None:
                out.append(data_dir / ANIM_TEXT / kind / f'{entry}.txt')
                write_new(out[-1], data)
    return out


def merge_persistent(data_dir: Path, copies: dict, vanilla: Vanilla, masters=()) -> int:
    """Add each copied entry whose template is on vanilla's persistent list, and the lists of the master builds'
    data folders `masters` (a loose list hides every other), to `data_dir`'s list (the Creation Kit's, else
    vanilla's); how many ids were added."""
    path = data_dir / PERSISTENT
    listed = persistent_ids(path.read_text(encoding='cp1252')) if path.is_file() else set(vanilla.persistent)
    added = {entry for entry, template in copies.items() if template in vanilla.persistent}
    for master in masters:
        theirs = data_file(master, PERSISTENT.as_posix())
        added |= persistent_ids(theirs.decode('cp1252')) if theirs is not None else set()
    added -= listed
    if added or not path.is_file():
        write_new(path, ''.join(f'{entry}.txt\n' for entry in sorted(listed | added)).encode('cp1252'))
    return len(added)
