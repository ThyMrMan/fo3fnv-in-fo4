"""A dependent plugin's records that are a master's: kept only where they change what the master plugin holds.

A build of a source plugin with masters (an FNV DLC on FalloutNV.esm) converts through the layered source, so its
makers also remake master records they reach (a base-game gun in a DLC leveled list, the game-wide settings). A
top-level record whose FormID is a built master's is kept when it differs from the latest built master plugin's
copy and the DLC changed it: the DLC holds that record (its override in the source), or it names one of the DLC's
own records (DLC content flowing into it: a base gun's ammo mods once GRA adds ammo to its ammo list). A form
list the DLC only adds to is not overridden: its additions are made at run time (F3NV_FormListAdds), which
stack across plugins. Any other kind is kept only if it loses none of the master's subrecords, else dropped and
counted. One
identical to it is dropped; so is one the master plugin does not hold (the source master's record its build left
out: nothing to override), and one that differs without either (the dependent build's context changed it, not
the DLC). A record of a master the build did not make (Fallout4.esm) no built master overrides is kept. Records
inside a group (a quest's topics, lines and scenes) are judged alike; a master record heading a kept children
group (the game quest and topic a DLC line sits under) stays, as the master's own copy when it changes nothing.
A built master is read in the build's FormID numbering (built_bytes): a mod on several DLC lists them after the
game, so each DLC's own index moves (master_space.byte_map; its bodies by data/fo4_subrecord_formids.json).

See: docs/fork/fo4_plugin_layout.md#dlc
"""

import collections
import functools
import struct
from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.build_inputs import MASTERS, Held
from fo4_import.pipeline.master_plugin import renumbered
from fo4_import.pipeline.master_space import byte_map, identity
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, decompress, subrecords, walk, zstr

#: A record's header size; its data size, flags and FormID offsets.
REC_HDR, SIZE_AT, FLAGS_AT, FID_AT = 24, 4, 8, 12
#: The kinds of master record a dependent build keeps.
KEPT = ('override', 'override naming DLC records', 'new override')


def _header(blob: bytes) -> tuple:
    """(signature, data size, flags, FormID) of the record at the start of `blob`."""
    return (blob[:4],) + struct.unpack_from('<3I', blob, SIZE_AT)


def _pruned(data: bytes, keep) -> bytes:
    """`data` (records and groups at one level) with each record as `keep(record, heads)` gives it (b'' drops it;
    `heads`: its children group survived, so it must stay) and each group pruned alike, gone when emptied."""
    items, pos = [], 0
    while pos < len(data):
        sig, size = struct.unpack_from('<4sI', data, pos)
        end = pos + (size if sig == b'GRUP' else REC_HDR + size)
        items.append((sig == b'GRUP', data[pos:end]))
        pos = end
    groups = [_pruned(blob[REC_HDR:], keep) if group else b'' for group, blob in items]
    out = []
    for i, (group, blob) in enumerate(items):
        if group:
            inner = groups[i]
            out.append(blob[:SIZE_AT] + struct.pack('<I', REC_HDR + len(inner)) + blob[FLAGS_AT:REC_HDR] + inner
                       if inner else b'')
        else:
            out.append(keep(blob, i + 1 < len(items) and items[i + 1][0] and bool(groups[i + 1])))
    return b''.join(out)


def _own_ids(writer) -> frozenset:
    """`writer`'s own top-level FormIDs, as a reference's 4 bytes."""
    fids = (_header(blob)[3] for blob in writer.top_records())
    return frozenset(fid.to_bytes(4, 'little') for fid in fids if fid >> 24 == writer.own_index)


def _names_any(body: bytes, ids: frozenset) -> bool:
    """Whether `body` holds any of `ids` (4-byte FormIDs) at any offset."""
    return any(body[i:i + 4] in ids for i in range(len(body) - 3))


@functools.cache
def _built(path: str, masters: tuple) -> bytes:
    """built_bytes, cached per plugin and master list."""
    mapping = byte_map(list(masters), Path(path).name, file_masters(Path(path)))
    raw = Path(path).read_bytes()
    return raw if identity(mapping) else renumbered(raw, mapping, 'fo4')


def read_built(path, masters: list) -> bytes:
    """built_bytes read from disk now, not cached."""
    return _built.__wrapped__(str(path), tuple(masters))


def built_bytes(path, masters: list) -> bytes:
    """A built master's bytes, FormIDs as a build mastering `masters` reads them.
    See: docs/fork/fo4_plugin_layout.md#multi-master
    """
    return _built(str(path), tuple(masters))


def held_by(paths: list, masters: list) -> frozenset:
    """FormIDs (build numbering) of every record in built master plugins `paths` (questions logged: Held)."""
    return Held(rec.form_id for path in paths for rec, _ in walk(built_bytes(path, masters), bodies=()))


def master_records(paths: list, wanted: dict, masters: list) -> dict:
    """{FormID: (flags, body)} of the `wanted` records ({FormID: signature}) in built master plugins `paths`, the
    last one holding each, read in the numbering of the build's `masters` (built_bytes)."""
    out = {}
    for path in paths:
        for rec, _ in walk(built_bytes(path, masters), bodies=frozenset(wanted.values())):
            if wanted.get(rec.form_id) == rec.sig:
                out[rec.form_id] = (rec.flags & ~FLAG_COMPRESSED, rec.body)
    for fid, sig in wanted.items():
        MASTERS.record(fid, sig, out[fid][1] if fid in out else None)
    return out


def _candidates(writer) -> dict:
    """{FormID: signature} of `writer`'s master records, groups included."""
    return {rec.form_id: rec.sig for blob in (*writer.top_records(), *writer.raw_groups())
            for rec, _ in walk(blob, bodies=(), span=(0, len(blob))) if rec.form_id >> 24 < writer.own_index}


def drop_unchanged(writer, paths: list, held: set, adds: 'dict | None' = None) -> collections.Counter:
    """Remove `writer`'s master records, top-level, nested, or in a pre-built group (worldspaces, cells: placed
    refs, navmeshes), that change nothing in the built master plugins `paths`; one whose children group keeps a
    record stays as the master's copy. A master form list or perk the DLC only adds to goes too, its additions
    in `adds` ({FormID: (signature, EditorID, [forms or perk entries])}) for list_adds. `held`: FormIDs of the
    records the DLC holds. Counts by kind and signature.
    See: docs/fork/fo4_plugin_layout.md#dlc-dialogue
    """
    candidates = _candidates(writer)
    found = master_records(paths, candidates, writer.masters)
    counts, adds = collections.Counter(), {} if adds is None else adds
    context = (held, {writer.masters.index(Path(p).name) for p in paths}, _own_ids(writer), writer.own_index)

    def unwanted(blob: bytes) -> bool:
        """Whether a record changes nothing in the masters; counted, a list's or perk's additions kept in `adds`."""
        sig, _, flags, fid = _header(blob)
        if candidates.get(fid) != sig:
            return False
        kind, items = _kind(sig, fid, (flags, decompress(blob[REC_HDR:], flags)), found.get(fid), context)
        if items:
            edid = zstr(dict(subrecords(found[fid][1])).get(b'EDID', b''))
            known = adds.setdefault(fid, (sig, edid, []))[2]
            known += [item for item in items if item not in known]
        counts[f'master records {kind} ({sig.decode()})'] += 1
        return kind not in KEPT

    def keep(blob: bytes, heads: bool) -> bytes:
        """A record as written (b'': dropped); one heading kept children stays, as the master's copy if unwanted."""
        sig, _, _, fid = _header(blob)
        if not unwanted(blob):
            return blob
        if heads and fid in found:
            return pack_fo4_record(sig.decode(), fid, *found[fid])
        return blob if heads else b''
    for sig in {_header(blob)[0].decode() for blob in writer.top_records()}:
        writer.patch_records(sig, lambda blob: _pruned(blob, keep))
    writer.remove_records(lambda blob: not blob)
    writer.patch_groups(lambda blob: _pruned(blob, keep))
    return counts


def _kind(sig: bytes, fid: int, record: tuple, kept: 'tuple | None', context: tuple) -> tuple:
    """(kind, additions) of master record `fid` as written, `record` (flags, body), against the master's `kept`
    (flags, body) or None; `context` (held FormIDs, built master indexes, own FormIDs as bytes, own index)."""
    held, built, dlc, own = context
    flags, body = record
    if kept is None:
        return ('not in its master' if fid >> 24 in built else 'new override'), []
    if kept == (flags & ~FLAG_COMPRESSED, body):
        return 'same as master', []
    forms = added_forms(body, kept[1], (own, dlc)) if sig == b'FLST' else []
    if forms:
        return 'list entries added at run time', forms
    entries = added_perk_entries(body, kept[1]) if sig == b'PERK' else []
    if entries:
        return "perk entries moved to the plugin's own perk", entries
    if fid in held:
        return 'override', []
    return ('changed by the build alone' if not _names_any(body, dlc) else _carrying(body, kept)), []


def added_forms(body: bytes, master: bytes, ours: tuple = (None, frozenset())) -> list:
    """The FormIDs form list `body` adds to the master's `master` (new LNAMs, in order), none of plugin `ours` (load
    byte, written FormIDs as 4 bytes) it never wrote; [] unless every other subrecord matches.
    See: docs/fork/fo4_plugin_layout.md#dlc-lists
    """
    mine, theirs = subrecords(body), subrecords(master)
    if [s for s in mine if s[0] != b'LNAM'] != [s for s in theirs if s[0] != b'LNAM']:
        return []
    have = {data for tag, data in theirs if tag == b'LNAM'}
    new = dict.fromkeys(d for t, d in mine if t == b'LNAM' and d not in have and not _unwritten(d, ours))
    return [struct.unpack('<I', d)[0] for d in new]


def perk_entries(subs: list) -> tuple:
    """(head subrecords, [entry]) of a perk's subrecords `subs`: an entry is a PRKE through its PRKF, as a tuple."""
    first = next((i for i, (tag, _) in enumerate(subs) if tag == b'PRKE'), len(subs))
    entries, current = [], []
    for sub in subs[first:]:
        current.append(sub)
        if sub[0] == b'PRKF':
            entries.append(tuple(current))
            current = []
    return tuple(subs[:first]), entries + ([tuple(current)] if current else [])


def added_perk_entries(body: bytes, master: bytes) -> list:
    """The entries (perk_entries) perk `body` adds to the master's `master`, in order; [] unless its head matches and
    it keeps every master entry.
    See: docs/fork/fo4_plugin_layout.md#dlc-perks
    """
    (head, mine), (their_head, theirs) = perk_entries(subrecords(body)), perk_entries(subrecords(master))
    left = collections.Counter(_numberless(e) for e in theirs)
    if head != their_head or left - collections.Counter(_numberless(e) for e in mine):
        return []
    out = []
    for entry in mine:
        if left[_numberless(entry)]:
            left[_numberless(entry)] -= 1
        else:
            out.append(entry)
    return out


def _numberless(entry: tuple) -> tuple:
    """Perk `entry` without EPFB, its number, which additions shift."""
    return tuple(sub for sub in entry if sub[0] != b'EPFB')


def _unwritten(data: bytes, ours: tuple) -> bool:
    """Whether `data` is a FormID of plugin `ours` (byte, written) not written."""
    return len(data) == 4 and data[3] == ours[0] and data not in ours[1]


def _carrying(body: bytes, kept: tuple) -> str:
    """A master record naming DLC records: kept unless it loses a `kept` subrecord."""
    lost = collections.Counter(subrecords(kept[1])) - collections.Counter(subrecords(body))
    return 'override naming DLC records' if not lost else 'dropped: would lose master entries'


