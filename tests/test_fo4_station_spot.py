"""Converted crafting stations' standing marker: measured offset and heading, vanilla template's entry sides.

See: docs/fork/fo4_pipeline.md#station-entry
"""

import collections
import math
import struct
from types import SimpleNamespace

from fo4_import.spike import crafting as CR
from fo4_import.spike import station_spot as S

BOUNDS = (-56, -44, 0, 63, 27, 147)
CHEM_SNAM = bytes(16) + bytes(4) + b'\xff\xff\xff\xff'


FRONT = [((-500.0, -500.0, 0.0), (500.0, -500.0, 0.0), (0.0, -60.0, 0.0))]
BACK = [((-500.0, 500.0, 0.0), (500.0, 500.0, 0.0), (0.0, 60.0, 0.0))]


def _ref(cell: str, fid: str = '1') -> dict:
    """An unturned placement at the origin of `cell`."""
    return {'PosX': '0', 'PosY': '0', 'PosZ': '0', 'RotZ': '0', 'ParentCELL': cell, 'FormID': fid}


def test_spots_give_the_open_sides_offset_and_heading_only():
    """Navmesh only in front (-y): one 16-byte marker there, facing the bench."""
    placed = S.spots(BOUNDS, [_ref('C')], {'C': FRONT}, {})
    assert [struct.unpack('<4f', p) for _, p, _ in placed] == [(0.0, BOUNDS[1] - S.CLEARANCE, 0.0, 0.0)]


def test_a_bench_marker_stands_on_its_models_edge():
    """A chem-station copy's marker stands on its model's bounds edge."""
    placed = S.spots(BOUNDS, [_ref('C')], {'C': FRONT}, {}, CR.INSETS['WorkbenchChemistryA'])
    assert [struct.unpack('<4f', p) for _, p, _ in placed] == [(0.0, float(BOUNDS[1]), 0.0, 0.0)]


def test_a_bench_turned_to_the_wall_is_served_by_its_back():
    """Open in front twice, once only behind (Gun Runners): the front serves the two, the back the one."""
    refs = [_ref('A', '1'), _ref('A', '2'), _ref('B', '3')]
    placed = S.spots(BOUNDS, refs, {'A': FRONT, 'B': BACK}, {}, 0.0)
    back = struct.unpack('<f', struct.pack('<f', math.pi))[0]
    assert [struct.unpack('<4f', p) for _, p, _ in placed] == [(0.0, -44.0, 0.0, 0.0), (0.0, 27.0, 0.0, back)]
    assert [(side, [r['FormID'] for r in served]) for side, _, served in placed] == [(1, ['1', '2']), (0, ['3'])]


def _crafting(marks: list) -> CR.Crafting:
    """A Crafting over one station category whose placements measure `marks`."""
    crafting = CR.Crafting.__new__(CR.Crafting)
    writer = SimpleNamespace(records=[], derive_formid=lambda site, key: hash((site, key)) & 0xFFFFFF)
    writer.add_record = lambda sig, rec: writer.records.append(rec)
    crafting.builder = SimpleNamespace(writer=writer, counts=collections.Counter())
    crafting.sides, crafting.menus, crafting.keywords = {}, {7: 5}, {}
    crafting.categories = {5: {'EditorID': 'ReloadingBenchRecipes'}}
    crafting.templates = {'WorkbenchChemistryA': [(b'EDID', b'x\0'), (b'SNAM', CHEM_SNAM)]}
    crafting._spots = lambda rec, bounds: marks
    return crafting


def test_each_open_side_is_its_own_station_record_with_one_marker():
    """The first side's marker on the station itself; the back's on a copy the Gun Runners placement uses. Each
    SNAM keeps the template's keyword and every entry side."""
    front, back = struct.pack('<4f', 0.0, -44.0, 0.0, 0.0), struct.pack('<4f', 0.0, 27.0, 0.0, 3.0)
    crafting = _crafting([(1, front, [_ref('A', '1')]), (0, back, [_ref('B', '3')])])
    rec = {'FormID': '00000009', 'EditorID': 'ReloadingBench', 'SCRI': '7'}
    main = crafting.station(0x10, rec, 'm.nif', BOUNDS)
    (copy,) = crafting.builder.writer.records
    assert main.count(b'SNAM') == copy.count(b'SNAM') == 1
    assert front + CHEM_SNAM[16:] in main and back + CHEM_SNAM[16:] in copy and b'FNV_ReloadingBench_Back' in copy
    copy_id = struct.unpack_from('<I', copy, 12)[0]
    assert crafting.base_of({'FormID': '3'}, 0x10) == copy_id and crafting.base_of({'FormID': '1'}, 0x10) == 0x10


def test_a_station_no_side_measures_keeps_the_templates_marker():
    """No open side: one record, the template's SNAM."""
    crafting = _crafting([])
    main = crafting.station(0x10, {'FormID': '9', 'EditorID': 'Bench', 'SCRI': '7'}, 'm.nif', BOUNDS)
    assert CHEM_SNAM in main and not crafting.builder.writer.records
