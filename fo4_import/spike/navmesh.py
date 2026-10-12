"""FNV navmeshes as FO4 NAVM records, for the cell spike.

FNV's navmesh is authored: vertices, triangles with their adjacency, flags
(the same bits in both games), cover flags, door links and edge links to
neighbouring navmeshes carry over; only the container changes, to FO4's
NVNM version 15. A triangle's Height (the clearance above it) is FLT_MAX, as
vanilla writes for an unbounded one; cover and waypoints are empty. An edge
link gains the edge of the linked triangle that faces back (`facing`); a link
to a navmesh outside the build is dropped (the edge left open). The navmeshes
are registered in an override of Fallout4.esm's NAVI singleton, which carries
vanilla's precomputed paths.

See: docs/fork/fo4_spikes.md#spike-2-navmesh
See: docs/fork/fo4_pipeline.md#exterior-navmesh
"""

import math
import struct

from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.text_reader import get_hex_bytes
from tes5_import.base.writer import pack_subrecord
from tes5_import.navmesh.from_pgrd import choose_divisor
from tes5_import.navmesh.lookup_grid import build_navmesh_grid
from tes5_import.navmesh.navi import PATHING_CELL_CRC, PATHING_DOOR_CRC
from tes5_import.record_types.navm_falloutnv import parse_vertices

#: FO4's NVNM and NAVI versions, and its NAVI singleton in Fallout4.esm.
NVNM_VERSION, NAVI_VERSION, NAVI_SINGLETON = 15, 15, 0xFF1
#: FNV triangle (NVTR): 3 vertices, 3 edges, flags, cover flags.
FNV_TRIANGLE = struct.Struct('<3H3hHH')
#: FO4 triangle: FNV's fields with the clearance above it and a byte vanilla leaves 0.
FO4_TRIANGLE = struct.Struct('<3H3hfBHH')
#: Clearance of a triangle with nothing above it, as vanilla writes it.
NO_CEILING = struct.unpack('<f', b'\xff\xff\x7f\x7f')[0]
#: Triangle flag bits marking an edge that holds an edge-link index (edges 0-1, 1-2, 2-0).
EDGE_LINK_BITS = (0x1, 0x2, 0x4)
#: FNV door link (NVDP): door reference, triangle.
FNV_DOOR = struct.Struct('<IH2x')
#: FNV edge link (NVEX): type, navmesh, triangle; FO4's adds the linked triangle's edge.
FNV_EDGE, FO4_EDGE = struct.Struct('<IIH'), struct.Struct('<IIhB')


def grid_parent(x: int, y: int) -> int:
    """An exterior pathing cell's parent field: its grid, Y then X."""
    return struct.unpack('<I', struct.pack('<hh', y, x))[0]


def read(rec: dict) -> tuple:
    """FNV NAVM `rec` -> (vertices, triangles as FNV_TRIANGLE lists, edge links [(type, FNV navmesh, triangle)])."""
    tris, raw = get_hex_bytes(rec, 'NVTR'), get_hex_bytes(rec, 'NVEX')
    links = [FNV_EDGE.unpack_from(raw, i * FNV_EDGE.size) for i in range(len(raw) // FNV_EDGE.size)]
    return (parse_vertices(get_hex_bytes(rec, 'NVVX')),
            [list(FNV_TRIANGLE.unpack_from(tris, i * FNV_TRIANGLE.size)) for i in range(len(tris) // FNV_TRIANGLE.size)],
            [(kind, f'{navm:08X}', tri) for kind, navm, tri in links])


def _seg_dist(p: tuple, a: tuple, b: tuple) -> float:
    """Distance in x, y from `p` to the segment `a`-`b`."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) if length else 0.0
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def facing(edge: tuple, verts: list, tri: list) -> int:
    """The slot of `tri`'s edge nearest the middle of `edge` (two points)."""
    mid = ((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2)
    return min(range(3), key=lambda s: _seg_dist(mid, verts[tri[s]], verts[tri[(s + 1) % 3]]))


def linked(meshes: dict) -> dict:
    """{FNV navmesh: (vertices, triangles, edge links)} with each link kept when it reaches a navmesh in `meshes`.

    `meshes` is read()'s output by FNV navmesh FormID. A kept link is
    (type, FNV navmesh, triangle, facing edge); a triangle's linked edge holds
    its index in the new list. Any other link is dropped and its edge opened.
    """
    out = {}
    for fid, (verts, tris, targets) in meshes.items():
        links = []
        out[fid] = verts, [_relink(list(tri), verts, meshes, targets, links) for tri in tris], links
    return out


def _relink(tri: list, verts: list, meshes: dict, targets: list, links: list) -> list:
    """`tri` with each linked edge pointing at its link appended to `links`, or opened when it leaves `meshes`."""
    for slot, bit in enumerate(EDGE_LINK_BITS):
        if not tri[6] & bit:
            continue
        link = _link(meshes, targets, tri[3 + slot], (verts[tri[slot]], verts[tri[(slot + 1) % 3]]))
        if link:
            tri[3 + slot] = len(links)
            links.append(link)
        else:
            tri[3 + slot], tri[6] = -1, tri[6] & ~bit
    return tri


def _link(meshes: dict, targets: list, index: int, edge: tuple) -> 'tuple | None':
    """FNV edge link `index` of `targets` as (type, navmesh, triangle, facing edge); None if it leaves `meshes`."""
    if not 0 <= index < len(targets) or targets[index][1] not in meshes:
        return None
    kind, other, tri = targets[index]
    verts, tris, _ = meshes[other]
    return (kind, other, tri, facing(edge, verts, tris[tri])) if tri < len(tris) else None


def door_links(raw: bytes, ids: dict) -> list:
    """FNV NVDP -> sorted [(triangle, FO4 door ref)] for the doors in `ids`."""
    links = [FNV_DOOR.unpack_from(raw, i * FNV_DOOR.size) for i in range(len(raw) // FNV_DOOR.size)]
    return sorted((tri, ids[f'{ref:08X}']) for ref, tri in links if f'{ref:08X}' in ids)


def _grid(verts: list, tris: list) -> bytes:
    """The NVNM tail: grid divisor, cell size, bounds and each cell's triangles."""
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    span_x, span_y = max(hi[0] - lo[0], 1.0), max(hi[1] - lo[1], 1.0)
    divisor = choose_divisor(span_x, span_y)
    out = struct.pack('<I2f6f', divisor, span_x / divisor, span_y / divisor, *lo, *hi)
    for cell in build_navmesh_grid(verts, [t[:3] for t in tris], lo[0], lo[1], hi[0], hi[1], divisor):
        out += struct.pack(f'<I{len(cell)}h', len(cell), *cell)
    return out


def pack_nvnm(pathing: tuple, verts: list, tris: list, links: list, doors: list) -> bytes:
    """An NVNM in pathing cell `pathing` (world, parent): vertices, triangles, FO4 edge links, `doors`
    [(triangle, door)], no cover or waypoints."""
    out = struct.pack('<4I', NVNM_VERSION, PATHING_CELL_CRC, *pathing)
    out += struct.pack('<I', len(verts)) + b''.join(struct.pack('<3f', *v) for v in verts)
    out += struct.pack('<I', len(tris)) + b''.join(FO4_TRIANGLE.pack(*t[:6], NO_CEILING, 0, *t[6:]) for t in tris)
    out += struct.pack('<I', len(links)) + b''.join(FO4_EDGE.pack(*link) for link in links)
    out += struct.pack('<I', len(doors)) + b''.join(struct.pack('<hII', t, PATHING_DOOR_CRC, d) for t, d in doors)
    return out + struct.pack('<3I', 0, 0, 0) + _grid(verts, tris)


def navmeshes(recs: list, pathing: dict, ids: dict, fid_of) -> tuple:
    """({FNV cell: NAVM records}, NVMI subrecords, {FO4 door: (navmesh, triangle)}) of FNV navmeshes `recs`,
    linked among themselves; each door's link is the inverse of its navmesh's (vanilla's XNDP).

    `pathing` gives each FNV cell's pathing cell (world, parent), `ids` the
    FO4 door references, `fid_of(FNV FormID)` each navmesh's FormID.
    """
    recs = {r['FormID']: r for r in recs}
    meshes = linked({fid: m for fid, m in ((fid, read(r)) for fid, r in recs.items()) if m[0] and m[1]})
    records, infos, at_door = {}, b'', {}
    for fnv, (verts, tris, links) in meshes.items():
        rec, fid = recs[fnv], fid_of(fnv)
        cell, doors = pathing[rec['DATA.Cell']], door_links(get_hex_bytes(rec, 'NVDP'), ids)
        fo4_links = [(kind, fid_of(other), tri, edge) for kind, other, tri, edge in links]
        nvnm = pack_nvnm(cell, verts, tris, fo4_links, doors)
        for tri, door in doors:
            at_door.setdefault(door, (fid, tri))
        records[rec['DATA.Cell']] = records.get(rec['DATA.Cell'], b'') + pack_fo4_record(
            'NAVM', fid, 0, pack_subrecord('NVNM', nvnm) + pack_subrecord('MNAM', b''))
        reached = sorted({link[1] for link in fo4_links} - {fid})
        infos += pack_subrecord('NVMI', _info(fid, cell, verts, reached, sorted({d for _, d in doors})))
    return records, infos, at_door


def _info(fid: int, pathing: tuple, verts: list, reached: list, doors: list) -> bytes:
    """An NVMI body: navmesh, flags, centre, the navmeshes it links to, its door refs, no island, pathing cell."""
    centre = [sum(v[i] for v in verts) / len(verts) for i in range(3)]
    out = struct.pack('<2I4fI', fid, 0, *centre, 0.0, len(reached)) + struct.pack(f'<{len(reached)}I', *reached)
    out += struct.pack('<2I', 0, len(doors)) + b''.join(struct.pack('<II', PATHING_DOOR_CRC, d) for d in doors)
    return out + struct.pack('<B3I', 0, PATHING_CELL_CRC, *pathing)


def navi(fo4: bytes, infos: bytes) -> bytes:
    """The NAVI singleton override with `infos` and Fallout4.esm's NVPP."""
    nvpp = next(first_sub(r.body, b'NVPP') for r, _ in walk(fo4, b'NAVI') if r.form_id == NAVI_SINGLETON)
    subs = pack_subrecord('NVER', struct.pack('<I', NAVI_VERSION)) + infos + pack_subrecord('NVPP', nvpp)
    return pack_fo4_record('NAVI', NAVI_SINGLETON, 0, subs)
