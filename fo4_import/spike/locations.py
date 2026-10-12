"""Fallout 4 locations for FNV's places, and FNV's encounter zones.

FNV has no location records. Its authored places are the regions with a map
name (RDMP: the name FNV shows for where the player stands), drawn as
polygons over a worldspace (RPLD points). Each becomes a location under a
root location for the worldspace, its map marker the built marker of the
same name; an exterior cell takes the region whose polygon holds its centre
(else the root), and an interior the location of the exterior door that
leads into it, passed on through interiors. Encounter zones convert one to
one (owner, rank, minimum level, flags: FO4 adds a location and a maximum).

See: docs/fork/fo4_pipeline.md#locations
"""

import collections
import struct

from fo4_import.base.install import fnv_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.interiors import by_cell
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of the generated locations (key: the FNV region's or worldspace's FormID).
SITE = 'FNV LCTN'
#: Units per exterior grid cell.
CELL_UNITS = 4096.0
#: LCTN ANAM (actor fade multiplier), vanilla's on every location.
FADE = struct.pack('<f', 1.0)


def inside(polygon: list, x: float, y: float) -> bool:
    """Whether point (x, y) lies in `polygon` [(x, y)] (even-odd rule)."""
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def map_regions(world: int) -> list:
    """[(FormID, EditorID, map name, [polygon])] of FalloutNV.esm's regions in `world` that have a map name."""
    out = []
    for rec, _ in walk(fnv_esm(), b'REGN'):
        subs = list(subrecords(rec.body))
        found = dict(subs)
        if b'RDMP' not in found or struct.unpack('<I', found.get(b'WNAM', bytes(4)))[0] != world:
            continue
        polygons = [list(struct.iter_unpack('<2f', d)) for t, d in subs if t == b'RPLD']
        out.append((rec.form_id, found[b'EDID'].rstrip(b'\0').decode('cp1252'),
                    found[b'RDMP'].rstrip(b'\0').decode('cp1252'), polygons))
    return out


def pack_lctn(fid: int, edid: str, name: str, parent: int, marker: int) -> bytes:
    """A location: name, parent location and map marker (0 for none), radius 0, actor fade 1."""
    subs = pack_subrecord('EDID', f'{edid}\0'.encode('cp1252')) + pack_subrecord('FULL', f'{name}\0'.encode('cp1252'))
    subs += pack_subrecord('PNAM', struct.pack('<I', parent)) if parent else b''
    subs += pack_subrecord('MNAM', struct.pack('<I', marker)) if marker else b''
    return pack_fo4_record('LCTN', fid, 0, subs + pack_subrecord('RNAM', bytes(4)) + pack_subrecord('ANAM', FADE))


class Locations:
    """A worldspace's root location and its map regions' locations, written once; at() finds a point's."""

    def __init__(self, builder, world: dict, markers: dict):
        """Write the locations of FNV worldspace `world` (its export record); `markers` {map name: FO4 marker}."""
        fnv = int(world['FormID'], 16)
        self.root = builder.writer.derive_formid(SITE, fnv)
        builder.writer.add_record('LCTN', pack_lctn(self.root, f'FNV_{world["EditorID"]}Location',
                                                    world.get('FULL', world['EditorID']), 0, 0))
        self.regions = []
        for region, edid, name, polygons in map_regions(fnv):
            fid = builder.writer.derive_formid(SITE, region)
            builder.writer.add_record('LCTN', pack_lctn(fid, f'FNV_{edid}Location', name, self.root,
                                                        markers.get(name, 0)))
            self.regions.append((fid, polygons))
        builder.counts['LCTN'] += 1 + len(self.regions)

    def at(self, x: float, y: float) -> int:
        """The first region (by FormID) holding point (x, y), else the root."""
        return next((fid for fid, polygons in self.regions if any(inside(p, x, y) for p in polygons)), self.root)

    def of_grid(self, grid: tuple) -> int:
        """The location of grid cell `grid` (x, y), by its centre."""
        return self.at((grid[0] + 0.5) * CELL_UNITS, (grid[1] + 0.5) * CELL_UNITS)

    def interiors(self, all_refs: list, outside: list, interiors: list) -> dict:
        """{FNV interior FormID (hex): location}: the location of the exterior door (of `outside`, by FormID)
        leading into it, passed on through interior doors; nearest door first."""
        doors = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
        cell_doors, wanted, out = by_cell(doors.values()), {c['FormID'] for c in interiors}, {}
        todo = collections.deque((d, self.at(float(d['PosX']), float(d['PosY'])))
                                 for d in sorted(outside, key=lambda r: r['FormID']) if 'XTEL.Door' in d)
        while todo:
            door, location = todo.popleft()
            cell = doors.get(door['XTEL.Door'], {}).get('ParentCELL')
            if cell in wanted and cell not in out:
                out[cell] = location
                todo.extend((d, location) for d in cell_doors[cell])
        return out


def encounter_zones(builder, export_dir, owners: dict) -> dict:
    """Write every FNV encounter zone on FNV's FormID; {FNV FormID: FO4}. An owner maps through `owners`."""
    out = {}
    for rec in export_records(export_dir, 'ECZN'):
        out[int(rec['FormID'], 16)] = fid = builder.fnv_id(rec['FormID'])
        owner = owners.get(int(rec.get('DATA.Owner', '0'), 16), 0)
        data = struct.pack('<IIbbBb', owner, 0, int(rec.get('DATA.Rank', 0)), int(rec.get('DATA.MinLevel', 0)),
                           int(rec.get('DATA.Flags', 0)), 0)
        body = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}\0'.encode('cp1252')) + pack_subrecord('DATA', data)
        builder.writer.add_record('ECZN', pack_fo4_record('ECZN', fid, 0, body))
        builder.counts['ECZN'] += 1
    return out
