"""The FNV interior cells a build reaches: its named cell, then every interior a built door leads into.

A door of the exterior block or of an interior already reached leads into
the cell holding its partner door; an interior found that way is built
too, and its doors are followed in turn. Doors into other worldspaces or
exterior cells outside the block are not followed.

See: docs/fork/fo4_pipeline.md#interiors
"""

import collections
from pathlib import Path

from fo4_import.pipeline.export_index import export_records

#: FNV CELL DATA flag of an interior cell.
INTERIOR = 0x1


def by_cell(refs: list) -> dict:
    """{FNV cell FormID: its references}, in `refs`' order."""
    out = collections.defaultdict(list)
    for ref in refs:
        out[ref.get('ParentCELL')].append(ref)
    return out


def scope(export_dir: Path, all_refs: list, start: dict, outside: list) -> tuple:
    """(reached() interiors, their references in `all_refs` order)."""
    cells = {r['FormID']: r for r in export_records(export_dir, 'CELL') if int(r.get('DATA.Flags', 0)) & INTERIOR}
    inside, interiors = by_cell(all_refs), reached(cells, all_refs, start, outside)
    return interiors, [r for cell in interiors for r in inside[cell['FormID']]]


def reached(cells: dict, all_refs: list, start: dict, outside: list) -> list:
    """The interior CELLs of `cells` {FormID: CELL} connected by doors to `start` or to `outside` (an exterior
    block's references), through other interiors: `start` first, the rest by FormID."""
    doors = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    cell_doors = by_cell(doors.values())
    found, todo = {start['FormID']}, [r for r in outside if 'XTEL.Door' in r] + cell_doors[start['FormID']]
    while todo:
        cell = doors.get(todo.pop()['XTEL.Door'], {}).get('ParentCELL')
        if cell in cells and cell not in found:
            found.add(cell)
            todo += cell_doors[cell]
    return [start] + sorted((cells[c] for c in found - {start['FormID']}), key=lambda c: c['FormID'])
