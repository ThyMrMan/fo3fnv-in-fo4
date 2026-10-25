"""FNV vendors as Fallout 4's: a vendor faction per vendor NPC, stocked from FNV's merchant container.

FNV names a vendor's merchant container on its placed reference (ACHR
XMRC; the chests stand in a holding cell, NVVendorChestsCell) and what it
trades in its AI services (AIDT.Services, its template's when it takes AI
data from one). FO4 keeps both on a vendor
faction, built in vanilla's shape (57 of 92 vendor factions): the merchant
container (VENC), a buy/sell list (VEND), vendor values (VENV: all day,
radius 500, buys stolen and non-stolen items) and the location (PLVD). A
vendor trading more than consumables is a general store as vanilla's are
(everything but VendorItemsMisc's no-sale and key items); one trading only
consumables lists their FO4 keywords. The build places each built vendor's
chest, and only it, in the holding cell.

See: docs/fork/fo4_pipeline.md#vendors
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.factions import CAN_BE_OWNER, CRIME_VALUES
from fo4_import.spike.interiors import INTERIOR
from fo4_import.spike.npcs import USE_AI_DATA, template_source
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV AI services bits of consumables -> the FO4 keywords of what they cover (wbServiceFlags, FO3/FNV names).
CONSUMABLES = {0x04: ('ObjectTypeAlcohol',), 0x10: ('ObjectTypeFood', 'ObjectTypeDrink', 'ObjectTypeWater'),
               0x20: ('ObjectTypeChem',), 0x40: ('ObjectTypeStimpak',)}
#: FNV AI services bits of goods: weapons, armor, books, miscellaneous (wbServiceFlags 0, 1, 3, 10).
GOODS = 0x1 | 0x2 | 0x8 | 0x400
#: Vanilla general vendors' buy/sell list (61 of 92): what they do not trade, with Everything Not In List.
GENERAL_LIST = 'VendorItemsMisc'
#: FO4 FACT DATA flag Vendor.
VENDOR = 0x4000
#: Vanilla vendor PLVD (all 92): location type 12, no reference.
LOCATION = bytes([12]) + bytes(15)
SITE = 'FNV vendor'


def merchants(export_dir: Path, cell_of) -> list:
    """[(FNV actor reference, its merchant container REFR)] of the actors `cell_of` places in the build."""
    refs = {r['FormID']: r for r in export_records(export_dir, 'REFR')}
    return [(actor, refs[actor['XMRC.MerchantContainer']]) for sig in ('ACHR', 'ACRE')
            for actor in export_records(export_dir, sig)
            if actor.get('XMRC.MerchantContainer') in refs and cell_of(actor)]


def with_chests(export_dir: Path, interiors: list, every: list, chests: list) -> tuple:
    """(`interiors`, `every`) with merchant containers `chests` in interior holding cells, and those cells; a chest
    in an exterior cell is placed with its worldspace instead."""
    cells = {r['FormID']: r for r in export_records(export_dir, 'CELL') if int(r.get('DATA.Flags', 0)) & INTERIOR}
    chests = [c for c in chests if c['ParentCELL'] in cells]
    built = {c['FormID'] for c in interiors}
    held = [cells[cell] for cell in dict.fromkeys(c['ParentCELL'] for c in chests) if cell not in built]
    placed = {r['FormID'] for r in every}
    return interiors + held, every + [c for c in chests if c['FormID'] not in placed]


def write_vendors(builder, export_dir: Path, sold: list) -> dict:
    """{FNV NPC base: FO4 vendor faction} of `sold` (merchants()), each faction written once."""
    npcs = {int(r['FormID'], 16): r for r in export_records(export_dir, 'NPC_')}
    lists, out = _vanilla(builder.fo4), {}
    for actor, chest in sold:
        base = npcs.get(int(actor['NAME'], 16))
        if base is None or int(base['FormID'], 16) in out:
            continue
        fid = builder.writer.derive_formid(SITE, base['FormID'])
        builder.writer.add_record('FACT', _faction(builder, fid, base, services(npcs, base),
                                                   builder.fnv_id(chest['FormID']), lists))
        builder.counts['vendor FACT'] += 1
        out[int(base['FormID'], 16)] = fid
    return out


def services(npcs: dict, npc: dict) -> int:
    """`npc`'s AI services, from its AI data's template (else its own)."""
    found, left = template_source(npcs, npc, USE_AI_DATA)
    return int((npc if left else found).get('AIDT.Services', 0) or 0)


def _faction(builder, fid: int, npc: dict, trades: int, chest: int, vanilla: dict) -> bytes:
    """Vendor faction `fid` of FNV NPC `npc` trading in AI services `trades`, selling from FO4 container `chest`."""
    general = bool(trades & GOODS) or not trades & sum(CONSUMABLES)
    stock = vanilla[GENERAL_LIST] if general else _keywords(builder, npc, trades, vanilla)
    body = pack_subrecord('EDID', f'FNV_{npc["EditorID"]}VendorFaction\0'.encode())
    body += pack_subrecord('DATA', struct.pack('<I', VENDOR | CAN_BE_OWNER)) + pack_subrecord('CRVA', CRIME_VALUES[False])
    body += pack_subrecord('VEND', struct.pack('<I', stock)) + pack_subrecord('VENC', struct.pack('<I', chest))
    body += pack_subrecord('VENV', struct.pack('<HHHHBBBB', 0, 24, 500, 0, 1, int(general), 1, 0))
    return pack_fo4_record('FACT', fid, 0, body + pack_subrecord('PLVD', LOCATION))


def _keywords(builder, npc: dict, services: int, vanilla: dict) -> int:
    """A form list, written, of the FO4 keywords of the consumables FNV `services` bits cover."""
    words = [vanilla[k] for bit, names in CONSUMABLES.items() if services & bit for k in names if k in vanilla]
    fid = builder.writer.derive_formid(SITE, f'{npc["FormID"]} list')
    body = pack_subrecord('EDID', f'FNV_{npc["EditorID"]}VendorList\0'.encode())
    body += b''.join(pack_subrecord('LNAM', struct.pack('<I', k)) for k in words)
    builder.writer.add_record('FLST', pack_fo4_record('FLST', fid, 0, body))
    return fid


def _vanilla(fo4: bytes) -> dict:
    """{EditorID: FormID} of the Fallout4.esm keywords and list the vendor factions name."""
    wanted = {GENERAL_LIST, *(k for names in CONSUMABLES.values() for k in names)}
    out = {}
    for rec, _ in walk(fo4, b'KYWD', b'FLST'):
        edid = dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode()
        if edid in wanted:
            out[edid] = rec.form_id
    return out
