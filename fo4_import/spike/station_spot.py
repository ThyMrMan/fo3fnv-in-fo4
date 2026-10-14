"""Where the player stands at a converted crafting station: the open side of the FNV model.

A converted station copies a vanilla workbench FURN whose model carries its
furniture markers; an FNV model carries none, so the copy's marker sits at the
model's origin (inside the bench, or behind it against a wall). Its marker
(SNAM: offset, heading, entry sides) is instead put just outside the model's
bounds on the side FNV leaves walkable: for each of the model's four sides,
how many of its FNV placements have FNV navmesh under that point; the best
side wins, the player facing the bench.
"""

import math
import struct

from fo4_import.spike.navmesh import read

#: Units past the model's bounds the player stands (a character's radius and a little).
CLEARANCE = 40.0
#: Height above or below the bench's foot within which navmesh counts as the floor there.
FLOOR_REACH = 64.0
#: SNAM entry sides: front only (the marker faces the bench).
FRONT = 0x01
#: An exterior cell's width in units.
CELL_SIZE = 4096


def sides(bounds: tuple) -> list:
    """[(local x, y, heading to the bench)] outside each side of `bounds`."""
    x1, y1, _, x2, y2, _ = bounds
    return [(0.0, y2 + CLEARANCE, math.pi), (0.0, y1 - CLEARANCE, 0.0),
            (x2 + CLEARANCE, 0.0, -math.pi / 2), (x1 - CLEARANCE, 0.0, math.pi / 2)]


def world(ref: dict, x: float, y: float) -> tuple:
    """Local point (x, y) of placed FNV `ref` as world x, y (yaw only)."""
    yaw = float(ref.get('RotZ', 0.0))
    return (float(ref['PosX']) + x * math.cos(yaw) + y * math.sin(yaw),
            float(ref['PosY']) - x * math.sin(yaw) + y * math.cos(yaw))


def on_navmesh(point: tuple, z: float, triangles: list) -> bool:
    """Whether (x, y) lies on one of `triangles` [(a, b, c) vertices] within FLOOR_REACH of `z`."""
    px, py = point
    for a, b, c in triangles:
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-6:
            continue
        u = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
        v = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
        if min(u, v, 1 - u - v) >= 0 and abs(u * a[2] + v * b[2] + (1 - u - v) * c[2] - z) <= FLOOR_REACH:
            return True
    return False


def triangles_by_cell(navmeshes: list) -> dict:
    """{FNV cell FormID: [(a, b, c) vertices]} of FNV NAVM records."""
    out = {}
    for rec in navmeshes:
        verts, tris, _ = read(rec)
        out.setdefault(rec.get('DATA.Cell'), []).extend((verts[t[0]], verts[t[1]], verts[t[2]]) for t in tris)
    return out


def cell_of(ref: dict, grid: dict) -> str:
    """The FNV cell placed `ref` stands in: by position in its worldspace's `grid` {(world, x, y): cell}, as a
    persistent reference is filed under the worldspace's persistent cell; else its own cell."""
    if not ref.get('ParentWRLD'):
        return ref.get('ParentCELL')
    key = (ref['ParentWRLD'], math.floor(float(ref['PosX']) / CELL_SIZE), math.floor(float(ref['PosY']) / CELL_SIZE))
    return grid.get(key, ref.get('ParentCELL'))


def spot(bounds: tuple, placements: list, triangles: dict, grid: dict) -> 'bytes | None':
    """The SNAM of a station with model `bounds` placed at FNV `placements`: its marker on the side with
    navmesh at the most placements (cells by cell_of), at the model's foot, facing it; None when none has any."""
    best, score = None, 0
    for x, y, heading in sides(bounds):
        hits = sum(on_navmesh(world(ref, x, y), float(ref['PosZ']) + bounds[2], triangles.get(cell_of(ref, grid), ()))
                   for ref in placements)
        if hits > score:
            best, score = (x, y, heading), hits
    if best is None:
        return None
    x, y, heading = best
    return struct.pack('<4fIB3x', x, y, float(bounds[2]), heading, 0, FRONT)
