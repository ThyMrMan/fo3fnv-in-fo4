"""Where the player stands at a converted crafting station: the open side of the FNV model.

A converted station copies a vanilla workbench FURN whose model carries its
furniture markers; an FNV model carries none, so the copy's marker sits at the
model's origin, facing a side that may be against a wall. Its marker (SNAM:
offset, heading) is instead put on a side FNV leaves walkable: for each of
the model's four sides, how many of its FNV placements have FNV navmesh just
outside it. The best side is the front; a placement whose front is blocked
(a bench turned to the wall) gets its own best open side, so every placement
has one marker it can reach, the player facing the bench (FO4 may take any
marker a record has, so each side is its own record). A marker sits the
caller's inset from that edge. Its keyword and entry sides stay the vanilla
template's.
"""

import math
import struct

from fo4_import.spike.navmesh import read

#: Units past the model's bounds the player stands (a character's radius and a little).
CLEARANCE = 40.0
#: Height above or below the bench's foot within which navmesh counts as the floor there.
FLOOR_REACH = 64.0
#: An exterior cell's width in units.
CELL_SIZE = 4096


def sides(bounds: tuple, reach: float = CLEARANCE) -> list:
    """[(local x, y, heading to the bench)] `reach` outside each side of `bounds`."""
    x1, y1, _, x2, y2, _ = bounds
    return [(0.0, y2 + reach, math.pi), (0.0, y1 - reach, 0.0),
            (x2 + reach, 0.0, -math.pi / 2), (x1 - reach, 0.0, math.pi / 2)]


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


def spots(bounds: tuple, placements: list, triangles: dict, grid: dict, inset: float = -CLEARANCE) -> list:
    """[(side index, SNAM placement (offset, heading), the `placements` it serves)] for model `bounds` placed at FNV
    `placements`: `inset` units inside the side open (navmesh outside it, cells by cell_of) at the most placements,
    then the best open side of each placement where that one is not; at the model's foot, facing it. Each placement
    is served by the first such side open there, one open nowhere by the first. Empty when no side is ever open.
    See: docs/fork/fo4_pipeline.md#station-entry
    """
    open_at = [[on_navmesh(world(ref, x, y), float(ref['PosZ']) + bounds[2], triangles.get(cell_of(ref, grid), ()))
                for x, y, _ in sides(bounds)] for ref in placements]
    score = [sum(row[side] for row in open_at) for side in range(4)]
    chosen = []
    for row in sorted(open_at, key=lambda row: not row[max(range(4), key=score.__getitem__)]):
        if any(row) and not any(row[side] for side in chosen):
            chosen.append(max((side for side in range(4) if row[side]), key=score.__getitem__))
    served = [[] for _ in chosen]
    for ref, row in zip(placements, open_at):
        if chosen:
            served[next((i for i, side in enumerate(chosen) if row[side]), 0)].append(ref)
    marks = sides(bounds, -inset)
    return [(side, struct.pack('<4f', marks[side][0], marks[side][1], float(bounds[2]), marks[side][2]), refs)
            for side, refs in zip(chosen, served)]
