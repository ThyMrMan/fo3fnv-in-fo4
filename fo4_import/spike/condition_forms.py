"""FO4 forms for what the built quests' dialogue lines test, beyond the build's own references and actors.

A line may count or check worn an item no reference places (GetItemCount,
GetEquipped, GetHasNote, which counts the note: FNV's notes are inventory
items on Fallout 4), or a form list of them; those are converted on demand,
as script properties are. A line may also test a voice type, a map region
(PlayerInRegion, its location) or a cell or worldspace the build has. What
none of these covers is settled as never there (conditions.without_absent).

See: docs/fork/fo4_pipeline.md#dialogue-conditions
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: FNV functions whose first parameter is an inventory item (or a form list of items) the player may carry.
ITEM_TESTS = frozenset({'GetItemCount', 'GetEquipped', 'GetHasNote'})


def condition_forms(builder, export_dir: Path, lines: list) -> dict:
    """{FNV form: FO4 form} for `lines`' conditions: items and item lists (made now), voice types, map regions'
    locations, the built cells and worldspace."""
    voices = getattr(getattr(builder, 'npcs', None), 'voices', None)
    out = {**getattr(builder, 'cell_ids', {}), **{k: v for k, v in getattr(voices, 'ids', {}).items() if v}}
    out.update(getattr(builder.locations, 'by_region', {}) if getattr(builder, 'locations', None) else {})
    lists = {int(r['FormID'], 16): r for r in export_records(export_dir, 'FLST')}
    for line in lines:
        for cond in (C.parse(line[f'Condition[{i}].Raw']) for i in range(int(line.get('ConditionCount', 0) or 0))):
            if cond['func'] in ITEM_TESTS and cond['p1'] not in out:
                made = _item_list(builder, lists[cond['p1']]) if cond['p1'] in lists else builder.items.item(cond['p1'])
                out.update({cond['p1']: made} if made else {})
    builder.counts['condition forms'] = len(out)
    return out


def _item_list(builder, rec: dict) -> 'int | None':
    """FNV form list `rec` of items as an FO4 one on its FormID, its items converted; None with none of them."""
    items = [builder.items.item(int(rec[f'LNAM[{i}]'], 16)) for i in range(_entries(rec))]
    items = [f for f in items if f]
    if not items:
        return None
    fid = builder.fnv_id(rec['FormID'])
    subs = pack_string_subrecord('EDID', f'FNV_{rec.get("EditorID", rec["FormID"])}')
    subs += b''.join(pack_subrecord('LNAM', struct.pack('<I', f)) for f in items)
    builder.writer.add_record('FLST', pack_fo4_record('FLST', fid, 0, subs))
    return fid


def _entries(rec: dict) -> int:
    """How many LNAM[i] an FNV form list has."""
    i = 0
    while f'LNAM[{i}]' in rec:
        i += 1
    return i
