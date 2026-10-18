"""FO4 forms for what the built quests' dialogue lines test, beyond the build's own references and actors.

A line may count or check worn an item no reference places (GetItemCount,
GetEquipped, GetHasNote, which counts the note: FNV's notes are inventory
items on Fallout 4), or a form list of them; those are converted on demand,
as script properties are. A line may also test a voice type, a map region
(PlayerInRegion, its location) or a cell or worldspace the build has. What
none of these covers is settled as never there (conditions.without_absent).

See: docs/fork/fo4_pipeline.md#dialogue-conditions
"""

from fo4_import.spike import conditions as C

#: FNV functions whose first parameter is an inventory item (or a form list of items) the player may carry.
ITEM_TESTS = frozenset({'GetItemCount', 'GetEquipped', 'GetHasNote'})


def condition_forms(builder, lines: list) -> dict:
    """{FNV form: FO4 form} for `lines`' conditions: items and item lists (made now), voice types, map regions'
    locations, the built cells and worldspace."""
    voices = getattr(getattr(builder, 'npcs', None), 'voices', None)
    out = {**getattr(builder, 'cell_ids', {}), **{k: v for k, v in getattr(voices, 'ids', {}).items() if v}}
    out.update(getattr(builder, 'regions', {}))
    for line in lines:
        for cond in (C.parse(line[f'Condition[{i}].Raw']) for i in range(int(line.get('ConditionCount', 0) or 0))):
            if cond['func'] in ITEM_TESTS and cond['p1'] not in out:
                made = builder.items.item(cond['p1'])
                out.update({cond['p1']: made} if made else {})
    builder.counts['condition forms'] = len(out)
    return out
