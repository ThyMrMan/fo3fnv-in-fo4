"""What an FO4 build left out of FNV: references dropped from the cells it built, and FNV fields its records never
carry. Records made one to one keep FNV's object id, so each FNV record is paired with the plugin's.

    py -3.14 -m tools.validate.fo4_coverage <plugin.esp> [--fnv FalloutNV.esm] [--all]

Prints (1) per FNV base type, the references in built cells that the plugin lacks, and (2) per FNV record type,
each subrecord FNV sets with how many of the paired records carry the same tag; tags carried by none come first
(--all also lists the fully carried ones). A tag FO4 names differently shows as dropped: read the list, don't
gate on it.
"""

import argparse
import collections
import math
import struct
from pathlib import Path

from fo4_import.base.install import FALLOUTNV_ESM
from tes5_import.base.tes5_reader import subrecords, walk

#: FNV signatures of placed references.
PLACED = (b'REFR', b'ACHR', b'ACRE', b'PGRE', b'PMIS')
#: Tags every record has or that hold no game data.
IGNORED = {b'EDID', b'OBND'}
#: Units per exterior grid cell.
CELL_SIZE = 4096
#: GRUP type of a cell's persistent children.
PERSISTENT_CHILDREN = 8


def own_index(raw: bytes) -> int:
    """The plugin's own load index in its FormIDs: its master count."""
    size = int.from_bytes(raw[4:8], 'little')
    return sum(1 for t, _ in subrecords(raw[24:24 + size]) if t == b'MAST')


def plugin_records(path: Path) -> tuple:
    """({object id: tag set} of the plugin's own records, {object id} of its cells, {grid (x, y)} of its exterior
    cells)."""
    raw = path.read_bytes()
    own = own_index(raw)
    tags, cells, grids = {}, set(), set()
    for rec, _ in walk(raw):
        if rec.form_id >> 24 == own:
            subs = dict(subrecords(rec.body))
            tags[rec.form_id & 0xFFFFFF] = set(subs)
            if rec.sig == b'CELL':
                cells.add(rec.form_id & 0xFFFFFF)
                if b'XCLC' in subs:
                    grids.add(struct.unpack_from('<2i', subs[b'XCLC']))
    return tags, cells, grids


def _in_scope(stack, subs: dict, cells: set, grids: set) -> bool:
    """Whether an FNV placed reference stands in a cell the plugin built (a world's persistent reference: in a
    built grid cell by position)."""
    cell = stack.cell
    if cell is None or cell & 0xFFFFFF not in cells:
        return False
    if stack.worldspace is None or stack.of_type(PERSISTENT_CHILDREN) is None or b'DATA' not in subs:
        return True
    x, y = struct.unpack_from('<2f', subs[b'DATA'])
    return (math.floor(x / CELL_SIZE), math.floor(y / CELL_SIZE)) in grids


def fnv_scan(esm: Path, tags: dict, cells: set, grids: set) -> tuple:
    """(Counter of (sig, tag, carried), Counter of FNV records per sig, Counter of dropped refs by base sig)."""
    fields, records, dropped = collections.Counter(), collections.Counter(), collections.Counter()
    base_sig, missing = {}, []
    for rec, stack in walk(esm.read_bytes()):
        base_sig[rec.form_id] = rec.sig
        oid = rec.form_id & 0xFFFFFF
        subs = dict(subrecords(rec.body))
        if oid in tags:
            records[rec.sig] += 1
            for tag in set(subs) - IGNORED:
                fields[rec.sig, tag, tag in tags[oid]] += 1
        elif rec.sig in PLACED and _in_scope(stack, subs, cells, grids):
            missing.append(subs.get(b'NAME', b'\0\0\0\0'))
    for name in missing:
        dropped[base_sig.get(int.from_bytes(name, 'little'), b'????')] += 1
    return fields, records, dropped


def report(fields: collections.Counter, records: collections.Counter, dropped: collections.Counter, full: bool):
    """Print the dropped references and the field coverage table."""
    print('References in built cells not in the plugin, by FNV base type:')
    for sig, count in dropped.most_common():
        print(f'  {sig.decode("latin1")}: {count}')
    print('\nFNV fields and how often the paired record carries them (records paired per type):')
    for sig in sorted(records):
        rows = []
        for tag in sorted({t for s, t, _ in fields if s == sig}):
            have, lack = fields[sig, tag, True], fields[sig, tag, False]
            if lack:
                rows.append((have > 0, -lack, f'    {tag.decode("latin1")}: FNV {have + lack}, carried {have}'))
            elif full:
                rows.append((True, 0, f'    {tag.decode("latin1")}: FNV {have}, carried {have}'))
        if rows:
            print(f'  {sig.decode("latin1")} ({records[sig]} paired)')
            print('\n'.join(r for *_, r in sorted(rows)))


def main():
    """Run the census on the command line's plugin."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--fnv', type=Path, default=FALLOUTNV_ESM, help='The FNV master the plugin was built from')
    ap.add_argument('--all', action='store_true', help='Also list fields every paired record carries')
    args = ap.parse_args()
    tags, cells, grids = plugin_records(args.plugin)
    report(*fnv_scan(args.fnv, tags, cells, grids), args.all)


if __name__ == '__main__':
    main()
