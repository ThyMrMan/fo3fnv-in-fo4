"""FO4 forms for what the built quests' dialogue lines and NPCs' packages test, beyond the build's own references.

A line may count or check worn an item no reference places (GetItemCount,
GetEquipped, GetHasNote, which counts the note: FNV's notes are inventory
items on Fallout 4), or a form list of them, or test a form list's members
(IsInList, of a list a script may fill); those are converted on demand,
as script properties are. A line may also test a voice type, a map region
(PlayerInRegion, its location) or a cell or worldspace the build has. What
none of these covers is settled as never there (conditions.without_absent).
Packages and lines see the same forms (condition_map).

See: docs/fork/fo4_pipeline.md#dialogue-conditions
"""

from fo4_import.spike import conditions as C
from fo4_import.spike.say_topics import actor_values
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS

#: FNV functions whose first parameter is an item or form list, made on demand (IsInList's may be script-filled).
ITEM_TESTS = frozenset({'GetItemCount', 'GetEquipped', 'GetHasNote', 'IsInList'})


def condition_map(builder, base: dict, lines: list, helper_index: int) -> dict:
    """FNV to FO4 forms a line's or package's conditions may name: `base` over the items FO4 shares and the actor
    values (helper plugin `helper_index`), then NPC and creature bases, `lines`' items and the built cells
    (condition_forms), perks, radio stations, region globals and type keywords.
    See: docs/fork/fo4_pipeline.md#package-conditions
    """
    return {**builder.items.shared, **actor_values(helper_index), **base, **builder.npc_ids,
            **builder.creatures.made, **condition_forms(builder, lines), **builder.perks.form_map(),
            **builder.radio.form_map(), **builder.region_watch.form_map(), TYPE_KEYWORDS: builder.type_keywords}


def condition_forms(builder, lines: list) -> dict:
    """{FNV form: FO4 form} for `lines`' conditions: items and item lists (made now), voice types, races and tested
    classes (Npcs.trait_forms), map regions' locations, the built cells and worldspace."""
    npcs = getattr(builder, 'npcs', None)
    voices = getattr(npcs, 'voices', None)
    out = {**getattr(builder, 'cell_ids', {}), **{k: v for k, v in getattr(voices, 'ids', {}).items() if v}}
    out.update(npcs.trait_forms() if npcs else {})
    out.update(getattr(builder, 'regions', {}))
    out.update(condition_items(builder, lines, out))
    builder.counts['condition forms'] = len(out)
    return out


def condition_items(builder, lines: list, known: dict) -> dict:
    """{FNV item or item list: FO4 form} made now for `lines`' item tests (ITEM_TESTS) of forms `known` lacks;
    {(C.UNMADE, item): 0} for one the build cannot make, which no one can hold.
    See: docs/fork/fo4_dialogue_gaps.md#unmade-items
    """
    out = {}
    for line in lines:
        for cond in (C.parse(line[f'Condition[{i}].Raw']) for i in range(int(line.get('ConditionCount', 0) or 0))):
            item = cond['p1']
            if cond['func'] in ITEM_TESTS and item and not any(k in known or k in out for k in (item, (C.UNMADE, item))):
                made = builder.items.item(item)
                out[item if made else (C.UNMADE, item)] = made or 0
    return out
