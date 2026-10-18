"""FNV's factions as Fallout 4's: every FNV faction on FNV's FormID with its name, relations, ranks and flags.

Read from FalloutNV.esm (the export keeps no rank titles). Relations and
ranks have the same layout in both games; a relation to a race is dropped.
FNV's flags map to FO4's bits (hidden, special combat, track crime; Evil
and Allow Sell have none). FO4 also requires crime and vendor values: a
crime-tracking faction takes vanilla's (no arrest, attack on sight), the
rest vanilla's commonest (both), vendor values empty. A faction FNV names
as an owner (XOWN) can be one (Can Be Owner). FNV's PlayerFaction is FO4's
(the player is in it), so it is not written.

See: docs/fork/fo4_pipeline.md#factions
"""

import struct
from pathlib import Path

from fo4_import.base.install import source_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.owned_records import FORCE_COMBAT_EDIDS
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: (FNV DATA byte, bit) -> FO4 DATA flag: hidden, special combat, track crime.
FLAGS = {(0, 0x01): 0x01, (0, 0x04): 0x02, (1, 0x01): 0x40}
#: FO4 DATA flags: Track Crime, Can Be Owner.
TRACK_CRIME, CAN_BE_OWNER = 0x40, 0x8000
#: Vanilla CRVA (arrest, attack on sight, no crime gold): crime-tracking factions' (123 of 699), the rest's (556).
CRIME_VALUES = {True: bytes([0, 1]) + bytes(18), False: bytes([1, 1]) + bytes(18)}
#: Vanilla's commonest VENV (443 of 699): no vendor.
VENDOR_VALUES = bytes(12)
#: FNV factions that are an engine faction of FO4's: PlayerFaction.
ENGINE_FACTIONS = {0x1B2A4: 0x1C21C}
#: Rank subrecords FO4 keeps (INAM, the insignia, is unused).
RANK_TAGS = (b'RNAM', b'MNAM', b'FNAM')
#: FO4 FACT DATA flag Hidden From PC; XNAM combat reaction Enemy; derive_formid site of the ForceCombat pair.
HIDDEN, ENEMY, COMBAT_SITE = 0x1, 1, 'FNV force combat FACT'


def fo4_flags(data: bytes, owner: bool) -> int:
    """FO4 DATA flags of FNV DATA `data`; Can Be Owner when the faction owns something."""
    flags = sum(fo4 for (at, bit), fo4 in FLAGS.items() if at < len(data) and data[at] & bit)
    return flags | (CAN_BE_OWNER if owner else 0)


def relations(subs: list, factions: dict) -> bytes:
    """FO4 XNAMs of FNV relations `subs`, each faction through `factions` {FNV: FO4}; others dropped."""
    out = b''
    for tag, data in subs:
        if tag == b'XNAM' and struct.unpack_from('<I', data)[0] in factions:
            faction, modifier = struct.unpack_from('<Ii', data)
            reaction = struct.unpack_from('<I', data, 8)[0] if len(data) >= 12 else 0
            out += pack_subrecord('XNAM', struct.pack('<IiI', factions[faction], modifier, reaction))
    return out


def faction_record(fid: int, subs: list, factions: dict, owner: bool) -> bytes:
    """The FO4 FACT `fid` of FNV faction subrecords `subs`."""
    found = dict(subs)
    flags = fo4_flags(found.get(b'DATA', b''), owner)
    body = pack_subrecord('EDID', b'FNV_' + found[b'EDID'])
    body += pack_subrecord('FULL', found[b'FULL']) if b'FULL' in found else b''
    body += relations(subs, factions) + pack_subrecord('DATA', struct.pack('<I', flags))
    body += pack_subrecord('CRVA', CRIME_VALUES[bool(flags & TRACK_CRIME)])
    body += b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs if tag in RANK_TAGS)
    return pack_fo4_record('FACT', fid, 0, body + pack_subrecord('VENV', VENDOR_VALUES))


def owners(export_dir: Path) -> set:
    """FNV FormIDs named as owners (XOWN) by references and cells."""
    return {int(r['XOWN.Owner'], 16) for sig in ('REFR', 'CELL') for r in export_records(export_dir, sig)
            if 'XOWN.Owner' in r}


def write_all(builder, export_dir: Path) -> tuple:
    """Write every FNV faction through `builder` (ENGINE_FACTIONS are FO4's); ({FNV FormID: FO4 FormID},
    {FNV EditorID: FO4 FormID})."""
    records = [(rec.form_id, list(subrecords(rec.body))) for rec, _ in walk(source_esm(), b'FACT')]
    factions = {fnv: ENGINE_FACTIONS.get(fnv) or builder.fnv_id(f'{fnv:08X}') for fnv, _ in records}
    owned = owners(export_dir)
    for fnv, subs in records:
        if fnv not in ENGINE_FACTIONS:
            builder.writer.add_record('FACT', faction_record(factions[fnv], subs, factions, fnv in owned))
            builder.counts['FACT'] += 1
    names = {dict(subs)[b'EDID'].rstrip(b'\0').decode(): factions[fnv] for fnv, subs in records}
    return factions, {**names, **force_combat_factions(builder)}


def force_combat_factions(builder) -> dict:
    """Write the pair TES4Polyfill.ForceCombat puts an attacker and its target in, each the other's Enemy, so a
    converted StartCombat sticks; {EditorID: FormID}.
    See: docs/commentary/tes5_import_dialogue.md#synthesized-menus-factions-and-formlists
    """
    ids = {edid: builder.writer.derive_formid(COMBAT_SITE, edid) for edid in FORCE_COMBAT_EDIDS}
    for edid, other in zip(FORCE_COMBAT_EDIDS, reversed(FORCE_COMBAT_EDIDS)):
        body = pack_subrecord('EDID', edid.encode() + b'\0')
        body += pack_subrecord('XNAM', struct.pack('<IiI', ids[other], 0, ENEMY))
        body += pack_subrecord('DATA', struct.pack('<I', HIDDEN)) + pack_subrecord('CRVA', CRIME_VALUES[False])
        builder.writer.add_record('FACT', pack_fo4_record('FACT', ids[edid], 0, body + pack_subrecord('VENV', VENDOR_VALUES)))
    return ids
