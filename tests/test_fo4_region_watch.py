"""FNV region tests on Fallout 4: the polygons, the watch quest's arrays, conditions and script calls.

See: docs/fork/fo4_regions.md#built
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import region_watch as W
from fo4_import.spike.say_topics import conditions_of
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'


def _region(fid: int, polys: list, world: str = '000DA726') -> dict:
    """An export REGN with `polys` [[(x, y)]] as Area[i].PointsHex."""
    rec = {'FormID': f'{fid:08X}', 'EditorID': f'R{fid}', 'WNAM.Worldspace': world, 'AreaCount': str(len(polys))}
    for i, poly in enumerate(polys):
        rec[f'Area[{i}].PointsHex'] = b''.join(struct.pack('<2f', *p) for p in poly).hex().upper()
    return rec


def _watch(regions: list) -> W.RegionWatch:
    """A RegionWatch over `regions` with a fake builder (FormIDs 0x01000000 + FNV's, the build's own)."""
    watch = W.RegionWatch.__new__(W.RegionWatch)
    writer = SimpleNamespace(own_index=1, derive_formid=lambda site, key: 0x01000000 | hash(key) & 0xFFFF,
                             add_record=lambda sig, rec: None)
    watch.builder = SimpleNamespace(writer=writer, fnv_id=lambda w: int(w, 16), counts=Counter())
    watch.made, watch.regions = {}, {int(r['FormID'], 16): r for r in regions}
    watch.names = {r['EditorID'].lower(): int(r['FormID'], 16) for r in regions}
    return watch


@pytest.mark.skipif(not (EXPORT / 'REGN.txt').exists(), reason='needs the FalloutNV.esm export')
def test_the_ncr_support_area_decodes_to_its_three_polygons():
    """vMapCanSupportPCHere: 3 polygons of 21, 6 and 4 points; its first point near (67399, -13820)."""
    rec = next(r for r in export_records(EXPORT, 'REGN') if r.get('EditorID') == 'vMapCanSupportPCHere')
    polys = W.polygons(rec)
    assert [len(p) for p in polys] == [21, 6, 4]
    assert polys[0][0] == pytest.approx((67399.8, -13820.8), abs=1)


def test_the_watch_arrays_index_regions_polygons_and_points():
    """RegionFirst and PolyFirst end one past the last; points split into 128-point chunks; bounds per region."""
    big = [(float(i), float(i % 7)) for i in range(130)]
    watch = _watch([_region(0x10, [[(0, 0), (10, 0), (0, 10)], [(20, 20), (30, 20), (20, 30)]]), _region(0x20, [big])])
    for fid in (0x10, 0x20):
        watch.global_of(fid)
    props = watch.properties(sorted(watch.made))
    assert props['RegionFirst'] == ('ints', [0, 2, 3]) and props['PolyFirst'] == ('ints', [0, 3, 6, 136])
    assert len(props['X0'][1]) == 128 and props['X1'][1] == [float(i) for i in range(122, 130)]
    assert props['Y2'] == ('floats', [])
    assert props['MaxX'] == ('floats', [30.0, 129.0]) and props['Worlds'][1] == [0xDA726, 0xDA726]


def test_player_in_region_reads_the_watch_global_and_scripts_call_the_polyfill(monkeypatch):
    """A condition on a watched region is GetGlobalValue of its global; IsPlayerInRegion becomes InRegion."""
    raw = struct.pack('<B3xfIIIII', 0, 1.0, C.FNV.index('PlayerInRegion'), 0x15F432, 0, 0, 0).hex()
    ctda = conditions_of({'ConditionCount': '1', 'Condition[0].Raw': raw}, {(W.REGION_KEY, 0x15F432): 0x1000ABC}, {})
    func, p1 = struct.unpack_from('<H2xI', ctda, 6 + 8)
    assert func == C.FO4.index('GetGlobalValue') and p1 == 0x1000ABC
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = 'scn T\nbegin GameMode\n  if IsPlayerInRegion vMapCanAttackPCHere == 1\n    set x to 1\n  endif\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Quest', 'T')
    assert 'TES4Polyfill.InRegion(vMapCanAttackPCHere)' in out and 'GlobalVariable Property vMapCanAttackPCHere' in out
