"""FNV GetInCell name groups as FO4 tests.

FNV's GetInCell is true in every cell whose EditorID starts with the named
cell's (the GECK: an empty "dummy" interior often names a group of interiors
and exteriors); FO4's tests one interior cell, and an exterior cell is never a
condition parameter. A test of a group becomes an OR of an exact test of each
interior member and LocationHasKeyword of the group's keyword, which the own
location of each built exterior member carries (Locations.of_cell); "not in
the group" becomes the AND of the same tests, per OR group.

See: docs/fork/fo4_pipeline.md#cell-families
"""

import bisect
import itertools
import struct

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike.records import RUN_REFERENCE, pack_kywd

#: FNV's test of a cell, and the FO4 test an exterior member becomes.
GET_IN_CELL, LOCATION_KEYWORD = 'GetInCell', 'LocationHasKeyword'
#: FNV's test of a cell a reference (parameter 2) is in, named the same way.
IN_CELL_PARAM = 'GetInCellParam'
#: Form map key head of a named group: (FAMILY, FNV anchor cell) -> (FNV interior members, FO4 keyword or 0).
FAMILY = 'cell family'
#: derive_formid site of a group's keyword (key: the FNV anchor cell).
KEYWORD_SITE = 'FNV KYWD cell family'
#: FNV record types whose conditions may name a group (all 701 of FO3's GetInCell tests are on these).
CONDITIONED = ('INFO', 'PACK', 'QUST', 'IDLE', 'PERK', 'MGEF', 'SPEL', 'ENCH', 'NOTE', 'TERM', 'MESG', 'CHAL',
               'RCPE', 'LSCR', 'CPTH')
#: FNV CELL DATA flag Is Interior Cell.
INTERIOR = 0x1


def cell_families(builder, export_dir) -> dict:
    """{(FAMILY, anchor): (interior members, keyword)} of the GetInCell anchors `export_dir`'s conditions name
    whose group is more than the one interior; writes each keyword a built exterior member (in
    `builder.cell_ids`) carries, and sets `builder.family_cells` {FNV exterior cell: [its keywords]}.
    See: docs/fork/fo4_pipeline.md#cell-families
    """
    cells = {int(r['FormID'], 16): r for r in export_records(export_dir, 'CELL') if r.get('EditorID')}
    names = sorted((r['EditorID'].lower(), fid) for fid, r in cells.items())
    out, builder.family_cells = {}, {}
    for anchor in sorted(_anchors(export_dir) & cells.keys()):
        stem = cells[anchor]['EditorID'].lower()
        members = [fid for _, fid in names[bisect.bisect_left(names, (stem,)):bisect.bisect_left(names, (stem + '￿',))]]
        inner = tuple(fid for fid in members if _interior(cells[fid]))
        outer = [fid for fid in members if not _interior(cells[fid]) and fid in builder.cell_ids]
        if len(members) < 2 and not outer:
            continue
        keyword = builder.writer.derive_formid(KEYWORD_SITE, anchor) if outer else 0
        if keyword:
            builder.writer.add_record('KYWD', pack_kywd(keyword, f'FNV_InCell{cells[anchor]["EditorID"]}', 0))
            builder.counts['KYWD (GetInCell group)'] += 1
        for fid in outer:
            builder.family_cells.setdefault(fid, []).append(keyword)
        out[(FAMILY, anchor)] = (inner, keyword)
    return out


def _interior(cell: dict) -> bool:
    """Whether FNV cell `cell` is an interior (no worldspace, or flagged)."""
    return 'ParentWRLD' not in cell or bool(int(cell.get('DATA.Flags', 0) or 0) & INTERIOR)


def _anchors(export_dir) -> set:
    """The FNV cells GetInCell and GetInCellParam tests in `export_dir`'s CONDITIONED records name."""
    funcs = {struct.pack('<H', C.FNV.index(name)).hex() for name in (GET_IN_CELL, IN_CELL_PARAM)}
    out = set()
    for sig in CONDITIONED:
        for rec in export_records(export_dir, sig):
            out.update(struct.unpack('<I', bytes.fromhex(raw[24:32]))[0] for key, raw in rec.items()
                       if key.endswith('.Raw') and 'Condition[' in key and raw[16:20] in funcs)
    return out


def in_families(conds: list, form_map: dict) -> list:
    """`conds` with each test of a cell_families group expanded over its members.
    See: docs/fork/fo4_pipeline.md#cell-families
    """
    return [cond for group in C.groups(conds) for cond in _expanded(group, form_map)]


def _expanded(group: list, form_map: dict) -> list:
    """OR group `group` as AND-joined OR groups over its groups' members: "in F" is an OR of F's member tests, and
    (A or not-in-F) the AND over each member m of (A or not-in-m)."""
    tested = [(cond, _member_tests(cond, form_map)) for cond in group]
    if all(tests is None for _, tests in tested):
        return group
    any_of, none_of = [], []
    for cond, tests in tested:
        if tests is None:
            any_of.append(cond)
        elif C.compare(cond, 1.0):
            any_of += tests
        else:
            none_of.append(tests)
    return [cond for pick in itertools.product(*none_of) for cond in _chained([*any_of, *pick])]


def _member_tests(cond: dict, form_map: dict) -> 'list | None':
    """`cond`'s comparison applied to each interior member of the group it tests and to the group's keyword (of
    the location of GetInCellParam's reference); None for a test of no group, against a global, or whose outcome
    is the same in and out of the group."""
    family = form_map.get((FAMILY, cond['p1'])) if cond['func'] in (GET_IN_CELL, IN_CELL_PARAM) else None
    if family is None or cond['op_flags'] & C.USE_GLOBAL or C.compare(cond, 1.0) == C.compare(cond, 0.0):
        return None
    inner, keyword = family
    tests = [{**cond, 'p1': member} for member in inner]
    on = {'run_on': RUN_REFERENCE, 'ref': cond['p2']} if cond['func'] == IN_CELL_PARAM else {}
    return tests + ([{**cond, 'func': LOCATION_KEYWORD, 'p1': keyword, 'p2': 0, **on}] if keyword else [])


def _chained(clause: list) -> list:
    """`clause` as one OR group: OR with the next on all but the last."""
    last = len(clause) - 1
    return [{**c, 'op_flags': c['op_flags'] & ~C.OR_NEXT | (C.OR_NEXT if i < last else 0)} for i, c in enumerate(clause)]
