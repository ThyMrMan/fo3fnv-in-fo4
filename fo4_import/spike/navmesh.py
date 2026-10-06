"""FNV navmeshes as FO4 NAVM records, for the cell spike.

FNV's navmesh is authored: vertices, triangles with their adjacency, flags
(the same bits in both games) and cover flags, and door links carry over;
only the container changes, to FO4's NVNM version 15. A triangle's Height
(the clearance above it) is FLT_MAX, as vanilla writes for an unbounded one;
cover and waypoints are empty. Links to navmeshes outside the cell are
dropped (the edge left open). The navmeshes are registered in an override of
Fallout4.esm's NAVI singleton, which carries vanilla's precomputed paths.

See: docs/fork/fo4_spikes.md#spike-2-navmesh
"""

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


def triangles(raw: bytes) -> list:
    """FNV NVTR -> [[v0, v1, v2, e01, e12, e20, flags, cover]], edge links opened (edge -1, link bit cleared)."""
    out = []
    for i in range(len(raw) // FNV_TRIANGLE.size):
        tri = list(FNV_TRIANGLE.unpack_from(raw, i * FNV_TRIANGLE.size))
        for slot, bit in enumerate(EDGE_LINK_BITS):
            if tri[6] & bit:
                tri[3 + slot], tri[6] = -1, tri[6] & ~bit
        out.append(tri)
    return out


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


def pack_nvnm(cell_fid: int, verts: list, tris: list, doors: list) -> bytes:
    """An interior NVNM: vertices, triangles, no edge links, `doors` [(triangle, door)], no cover or waypoints."""
    out = struct.pack('<4I', NVNM_VERSION, PATHING_CELL_CRC, 0, cell_fid)
    out += struct.pack('<I', len(verts)) + b''.join(struct.pack('<3f', *v) for v in verts)
    out += struct.pack('<I', len(tris)) + b''.join(FO4_TRIANGLE.pack(*t[:6], NO_CEILING, 0, *t[6:]) for t in tris)
    out += struct.pack('<II', 0, len(doors)) + b''.join(struct.pack('<hII', t, PATHING_DOOR_CRC, d) for t, d in doors)
    return out + struct.pack('<3I', 0, 0, 0) + _grid(verts, tris)


def navmeshes(rec_list: list, cell_fid: int, ids: dict, new_id) -> tuple:
    """(NAVM records, NVMI subrecords) of a cell's FNV navmeshes; `new_id()` hands out FormIDs."""
    records, infos = b'', b''
    for rec in rec_list:
        verts, tris = parse_vertices(get_hex_bytes(rec, 'NVVX')), triangles(get_hex_bytes(rec, 'NVTR'))
        if not verts or not tris:
            continue
        fid, doors = new_id(), door_links(get_hex_bytes(rec, 'NVDP'), ids)
        nvnm = pack_nvnm(cell_fid, verts, tris, doors)
        records += pack_fo4_record('NAVM', fid, 0, pack_subrecord('NVNM', nvnm) + pack_subrecord('MNAM', b''))
        infos += pack_subrecord('NVMI', _info(fid, cell_fid, verts, sorted({d for _, d in doors})))
    return records, infos


def _info(fid: int, cell_fid: int, verts: list, doors: list) -> bytes:
    """An NVMI body: navmesh, flags, centre, no edge links, its door refs, no island, pathing cell."""
    centre = [sum(v[i] for v in verts) / len(verts) for i in range(3)]
    out = struct.pack('<2I4f2I', fid, 0, *centre, 0.0, 0, 0) + struct.pack('<I', len(doors))
    out += b''.join(struct.pack('<II', PATHING_DOOR_CRC, d) for d in doors)
    return out + struct.pack('<B3I', 0, PATHING_CELL_CRC, 0, cell_fid)


def navi(fo4: bytes, infos: bytes) -> bytes:
    """The NAVI singleton override with `infos` and Fallout4.esm's NVPP."""
    nvpp = next(first_sub(r.body, b'NVPP') for r, _ in walk(fo4, b'NAVI') if r.form_id == NAVI_SINGLETON)
    subs = pack_subrecord('NVER', struct.pack('<I', NAVI_VERSION)) + infos + pack_subrecord('NVPP', nvpp)
    return pack_fo4_record('NAVI', NAVI_SINGLETON, 0, subs)
