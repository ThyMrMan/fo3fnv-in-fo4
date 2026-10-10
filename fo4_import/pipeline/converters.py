"""The pipeline's per-type converters for placed bases: which cell-builder method makes an FNV base of each type.

`PLACED` is the table CellBuilder.base() dispatches on, and the census reads
the same table, so its column of what converts cannot drift from the code.
A type in `STATIC_STAND_INS` is placed as a static of its mesh until it has
a converter of its own; its route (record_routes) names where it belongs.

See: docs/fork/fo4_pipeline.md#converters
"""

#: FNV base type -> the CellBuilder method making a placed base of it, in the order bases are read.
PLACED = {
    'STAT': 'record', 'MSTT': 'record', 'SCOL': 'record', 'ALCH': 'pickup', 'WEAP': 'pickup', 'ARMO': 'pickup',
    'BOOK': 'record', 'KEYM': 'record', 'NOTE': 'record', 'AMMO': 'pickup', 'TERM': 'record', 'IDLM': 'record',
    'LIGH': 'record', 'DOOR': 'record', 'FURN': 'record', 'ACTI': 'record', 'TREE': 'tree', 'SOUN': 'sound',
    'MISC': 'item', 'CONT': 'item',
}
#: Placed types written as a static of their mesh until they get a converter of their own.
STATIC_STAND_INS = frozenset({'BOOK', 'KEYM', 'NOTE', 'TERM', 'IDLM'})


def placed_types(*methods: str) -> tuple:
    """Placed types `methods` make (all when none named), in PLACED's order."""
    return tuple(sig for sig, method in PLACED.items() if not methods or method in methods)
