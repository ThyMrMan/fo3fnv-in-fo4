"""A dependent plugin's records that are a master's: kept only where they change what the master plugin holds.

A build of a source plugin with masters (an FNV DLC on FalloutNV.esm) converts through the layered source, so its
makers also remake master records they reach (a base-game gun in a DLC leveled list, the game-wide settings). A
top-level record whose FormID is a built master's is kept when it differs from the latest built master plugin's
copy and the DLC changed it: the DLC holds that record (its override in the source), or it names one of the DLC's
own records (DLC content flowing into it: a base gun's ammo mods once GRA adds ammo to its ammo list). Such a
record built over the whole game (a list of every gun) is remade from what this build reached, so a form list is
merged (the master's entries, then the DLC's) and any other kind is kept only if it loses none of the master's
subrecords, else dropped and counted. One
identical to it is dropped; so is one the master plugin does not hold (the source master's record its build left
out: nothing to override), and one that differs without either (the dependent build's context changed it, not
the DLC). A record of a master the build did not make (Fallout4.esm) no built master overrides is kept.

See: docs/fork/fo4_plugin_layout.md#dlc
"""

import collections
import struct
from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.quest_merge import merged_quest
from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, decompress, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: A record's header size; its data size, flags and FormID offsets.
REC_HDR, SIZE_AT, FLAGS_AT, FID_AT = 24, 4, 8, 12
#: The kinds of master record a dependent build keeps, and the types it may write merged.
KEPT = ('override', 'override naming DLC records', 'form list merged', 'quest rows merged', 'new override')
MERGED = ('FLST', 'QUST')


def _header(blob: bytes) -> tuple:
    """(signature, data size, flags, FormID) of the record at the start of `blob`."""
    return (blob[:4],) + struct.unpack_from('<3I', blob, SIZE_AT)


def _master_group(blob: bytes, held: bool, indexes: tuple, counts: collections.Counter) -> bool:
    """Whether a record with its children (a quest and its dialogue) is all a built master's (`indexes`: own
    index, built masters' indexes) and its record not `held`: the build made it, not the DLC; counted."""
    own, built = indexes
    fids = [rec.form_id for rec, _ in walk(blob, bodies=(), span=(0, len(blob)))]
    if held or fids[0] >> 24 not in built or any(f >> 24 >= own for f in fids):
        return False
    counts[f'master record groups changed by the build alone ({blob[:4].decode()})'] += 1
    return True


def _own_ids(writer) -> frozenset:
    """`writer`'s own top-level FormIDs, as a reference's 4 bytes."""
    fids = (_header(blob)[3] for blob in writer.top_records())
    return frozenset(fid.to_bytes(4, 'little') for fid in fids if fid >> 24 == writer.own_index)


def _names_any(body: bytes, ids: frozenset) -> bool:
    """Whether `body` holds any of `ids` (4-byte FormIDs) at any offset."""
    return any(body[i:i + 4] in ids for i in range(len(body) - 3))


def held_by(paths: list) -> frozenset:
    """The FormIDs of every record in built master plugins `paths`."""
    return frozenset(rec.form_id for path in paths for rec, _ in walk(Path(path).read_bytes(), bodies=()))


def master_records(paths: list, wanted: dict, masters: list) -> dict:
    """{FormID: (flags, body)} of the `wanted` records ({FormID: signature}) in built master plugins `paths`, the
    last one holding each; each plugin's masters must lead the build's `masters`, so its FormIDs read alike."""
    out = {}
    for path in paths:
        theirs = file_masters(path)
        if masters[:len(theirs) + 1] != theirs + [path.name]:
            raise ValueError(f'{path.name} masters {theirs} do not lead the build masters {masters}')
        for rec, _ in walk(path.read_bytes(), *set(wanted.values())):
            if rec.form_id in wanted:
                out[rec.form_id] = (rec.flags & ~FLAG_COMPRESSED, rec.body)
    return out


def drop_unchanged(writer, paths: list, held: set, rules: 'dict | None' = None) -> collections.Counter:
    """Remove `writer`'s top-level master records that change nothing in the built master plugins `paths`; `held`
    are the FO4 FormIDs of the records the DLC holds (module notes), `rules` quest_merge's script rules; counts by
    kind and signature."""
    own, built = writer.own_index, {writer.masters.index(Path(p).name) for p in paths}
    candidates = {}
    for blob in writer.top_records():
        sig, size, _, fid = _header(blob)
        if fid >> 24 < own and len(blob) == REC_HDR + size:
            candidates[fid] = sig
    found = master_records(paths, candidates, writer.masters)
    counts, dlc = collections.Counter(), _own_ids(writer)

    def unwanted(blob: bytes) -> bool:
        """Whether a top-level record changes nothing in the masters; counted."""
        sig, size, flags, fid = _header(blob)
        if len(blob) != REC_HDR + size:
            return _master_group(blob, fid in held, (own, built), counts)
        if candidates.get(fid) != sig:
            return False
        kept, body = found.get(fid), decompress(blob[REC_HDR:], flags)
        if kept is None:
            kind = 'not in its master' if fid >> 24 in built else 'new override'
        elif kept == (flags & ~FLAG_COMPRESSED, body):
            kind = 'same as master'
        elif fid in held:
            kind = 'override'
        elif not _names_any(body, dlc):
            kind = 'changed by the build alone'
        else:
            kind, merged[fid] = _carrying(sig, fid, body, kept, rules or {})
        counts[f'master records {kind} ({sig.decode()})'] += 1
        return kind not in KEPT
    merged = {}
    writer.remove_records(unwanted)
    for sig in MERGED:
        writer.patch_records(sig, lambda blob: merged.get(_header(blob)[3]) or blob)
    return counts


def _carrying(sig: bytes, fid: int, body: bytes, kept: tuple, rules: dict) -> tuple:
    """(kind, merged record or None) of master record `fid` naming DLC records, `kept` the master's (flags, body):
    a form list as the master's entries then the DLC's new ones; a quest with its scripts' rows merged
    (quest_merge); another kind kept only when it loses none of the master's subrecords (a whole-record override
    would drop what the dependent build did not remake)."""
    mine, theirs = subrecords(body), subrecords(kept[1])
    if sig == b'FLST':
        old = {data for tag, data in theirs if tag == b'LNAM'}
        new = [pack_subrecord('LNAM', data) for tag, data in mine if tag == b'LNAM' and data not in old]
        return 'form list merged', pack_fo4_record('FLST', fid, kept[0], kept[1] + b''.join(new))
    quest = merged_quest(kept[1], body, rules) if sig == b'QUST' else None
    if quest is not None:
        return 'quest rows merged', pack_fo4_record('QUST', fid, kept[0], quest)
    lost = collections.Counter(theirs) - collections.Counter(mine)
    return ('override naming DLC records' if not lost else 'dropped: would lose master entries'), None
