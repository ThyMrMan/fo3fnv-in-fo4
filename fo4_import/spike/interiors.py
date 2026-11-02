"""The FNV interior cells a build reaches: its named cell, then every interior a built door or script leads into.

A door of the exterior block or of an interior already reached leads into
the cell holding its partner door; so does a placed object whose base's
script names a reference in another interior (the Lucky 38's elevator
doors MoveTo markers on its other floors). A `player.MoveTo` in a quest
script or a stage or line result leads into its marker's cell from anywhere
(the ending slides' Endgame cell). An interior found any of these ways is
built too, and its references are followed in turn. Exterior cells outside
the block are not followed.

See: docs/fork/fo4_pipeline.md#interiors
"""

import collections
import re
from pathlib import Path

from fo4_import.pipeline.export_index import export_records

#: FNV CELL DATA flag of an interior cell.
INTERIOR = 0x1
#: FNV base types placed in cells whose scripts (SCRI) may move the player: doors, activators, terminals, actors.
SCRIPTED_BASES = ('DOOR', 'ACTI', 'TACT', 'TERM', 'FURN', 'CONT', 'NPC_', 'CREA', 'MISC', 'BOOK', 'NOTE')
#: `player.MoveTo <reference>` in FO3/FNV script text.
PLAYER_MOVE = re.compile(r'(?i)\b(?:player|playerref)[ \t]*\.[ \t]*moveto[ \t]+(\w+)')
#: Record field name endings holding quest stage and line result scripts.
RESULT_SCRIPTS = ('ResultScript', 'ResultScriptEnd')


def by_cell(refs: list) -> dict:
    """{FNV cell FormID: its references}, in `refs`' order."""
    out = collections.defaultdict(list)
    for ref in refs:
        out[ref.get('ParentCELL')].append(ref)
    return out


def scope(export_dir: Path, all_refs: list, start: dict, outside: list) -> tuple:
    """(reached() interiors, their references in `all_refs` order)."""
    cells = {r['FormID']: r for r in export_records(export_dir, 'CELL') if int(r.get('DATA.Flags', 0)) & INTERIOR}
    links = script_links(export_dir, all_refs)
    seeds = moved_to(export_dir, all_refs)
    inside, interiors = by_cell(all_refs), reached(cells, all_refs, start, outside, links, seeds)
    return interiors, [r for cell in interiors for r in inside[cell['FormID']]]


def moved_to(export_dir: Path, all_refs: list) -> set:
    """The cells of the references `player.MoveTo` names in script text tied to no placed object: quest and
    effect scripts, quest stage and line results (the VEnding quest moves the player to the Endgame cell).
    See: docs/fork/fo4_pipeline.md#interiors
    """
    cell_of = {r['EditorID'].lower(): r.get('ParentCELL') for r in all_refs if r.get('EditorID')}
    texts = [r.get('SCTX', '') for r in export_records(export_dir, 'SCPT') if r.get('SCHR.Type', '0') != '0']
    texts += [text for sig in ('QUST', 'INFO') for r in export_records(export_dir, sig)
              for key, text in r.items() if key.endswith(RESULT_SCRIPTS)]
    return {cell_of[name.lower()] for text in texts for name in PLAYER_MOVE.findall(text) if name.lower() in cell_of}


def script_links(export_dir: Path, all_refs: list) -> dict:
    """{FNV reference FormID: the cells of the references its base's script names (SCRO)}: where a script on a
    placed object can send the player (the Lucky 38 elevator's MoveTo markers), for reached().
    See: docs/fork/fo4_pipeline.md#interiors
    """
    placed = {r['FormID']: r.get('ParentCELL') for sig in ('REFR', 'ACHR', 'ACRE') for r in export_records(export_dir, sig)}
    named = {r['FormID']: {v for k, v in r.items() if 'SCRO' in k} for r in export_records(export_dir, 'SCPT')}
    scripted = {r['FormID']: r['SCRI'] for sig in SCRIPTED_BASES for r in export_records(export_dir, sig) if r.get('SCRI')}
    out = {}
    for ref in all_refs:
        cells = {placed.get(target) for target in named.get(scripted.get(ref.get('NAME')), ())} - {None}
        if cells:
            out[ref['FormID']] = cells
    return out


def reached(cells: dict, all_refs: list, start: 'dict | None', outside: list, links: dict = None,
            seeds: set = frozenset()) -> list:
    """The interior CELLs of `cells` {FormID: CELL} connected to `start` (None: no named cell), to `outside` (an
    exterior block's references) or among `seeds` (cells reached from anywhere), through other interiors: by doors,
    and by `links` ({reference: cells its script names}); `start` first, the rest by FormID."""
    links = links or {}
    doors = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    inside = by_cell(all_refs)
    first = {start['FormID']} if start else set()
    found = first | (set(seeds) & set(cells))
    todo = list(outside) + [r for c in sorted(found) for r in inside[c]]
    while todo:
        ref = todo.pop()
        targets = {doors.get(ref.get('XTEL.Door'), {}).get('ParentCELL')} | links.get(ref['FormID'], set())
        for cell in sorted(c for c in targets if c in cells and c not in found):
            found.add(cell)
            todo += inside[cell]
    return ([start] if start else []) + sorted((cells[c] for c in found - first), key=lambda c: c['FormID'])
