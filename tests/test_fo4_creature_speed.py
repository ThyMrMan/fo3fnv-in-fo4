"""FNV creatures' run speed on their FO4 stand-ins through SpeedMult.

See: docs/fork/fo4_pipeline.md#creature-speed
"""

import struct
from pathlib import Path

import pytest

from fo4_import.spike import creature_speed as CS
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def test_forward_run_reads_each_sped_layout():
    """112 bytes (form version 104+): float 10; older 40 to 68 bytes: float 5 (Fallout4.exe 0x620ce0)."""
    new = struct.pack('<28f', *[float(i) for i in range(28)])
    old = struct.pack('<17f', *[float(i) for i in range(17)])
    assert CS.forward_run(new) == 10.0 and CS.forward_run(old) == 5.0


def test_fnv_run_is_the_clip_speed_truncated_by_the_multiplier_and_scale(monkeypatch):
    """One FastForward clip: int(root speed) x multiplier / 100 x scale; several: their mean at rate 1."""
    monkeypatch.setattr(CS, 'run_clip_speeds', lambda export_dir, folder: (600.7,))
    assert CS.fnv_run_speed(Path('.'), 'creatures\\deathclaw', {'ACBS.SpeedMultiplier': '150'}, 1.2) == \
        pytest.approx(600 * 1.5 * 1.2)
    monkeypatch.setattr(CS, 'run_clip_speeds', lambda export_dir, folder: (300.0, 500.0))
    assert CS.fnv_run_speed(Path('.'), 'x', {'ACBS.SpeedMultiplier': '200'}, 1.0) == 400.0
    monkeypatch.setattr(CS, 'run_clip_speeds', lambda export_dir, folder: ())
    assert CS.fnv_run_speed(Path('.'), 'x', {}, 1.0) is None


def test_the_movement_type_is_the_one_the_graph_names():
    """The race's own when the graph names it or names none; else the base state (DogDefault over DogSwim), the
    root name (FeralGhoul over FeralGhoulSprint) or the single named one; else the default."""
    by_name = {'deathclawdefault': 1, 'deathclawhardturn': 2, 'molerat': 3, 'feralghoul': 4, 'feralghoulsprint': 5,
               'dogdefault': 6, 'dogswim': 8}
    assert CS.movement_type({'dogswim', 'dogdefault'}, by_name, '', 0, 9) == 6
    assert CS.movement_type({'dogswim', 'molerat'}, by_name, '', 0, 9) == 9
    assert CS.movement_type({'deathclawdefault', 'deathclawhardturn'}, by_name, 'deathclawdefault', 1, 9) == 1
    assert CS.movement_type({'molerat'}, by_name, '', 0, 9) == 3
    assert CS.movement_type({'feralghoul', 'feralghoulsprint'}, by_name, '', 0, 9) == 4
    assert CS.movement_type(set(), by_name, 'x', 7, 9) == 7 and CS.movement_type(set(), by_name, '', 0, 9) == 9


def test_fo4_scale_is_the_middle_of_the_height_range_times_the_race_height():
    """NAM6 0.9, NAM4 1.2, race 1.0: 1.05; no heights: the race's."""
    subs = {b'NAM6': struct.pack('<f', 0.9), b'NAM4': struct.pack('<f', 1.2)}
    assert CS.fo4_scale(subs, 1.0) == pytest.approx(1.05) and CS.fo4_scale({}, 1.03) == pytest.approx(1.03)


def test_speed_mult_is_set_in_prps_or_added_before_aidt():
    """An existing PRPS keeps its other values; without one, PRPS goes before AIDT."""
    with_prps = pack_subrecord('PRPS', struct.pack('<If', 0x2D4, 50.0)) + pack_subrecord('AIDT', b'\0' * 4)
    out = dict(subrecords(CS.with_speed_mult(115.5)(with_prps)))
    assert dict(struct.unpack_from('<If', out[b'PRPS'], i) for i in range(0, len(out[b'PRPS']), 8)) == \
        {0x2D4: 50.0, CS.SPEED_MULT: 115.5}
    bare = [t for t, _ in subrecords(CS.with_speed_mult(80.0)(pack_subrecord('AIDT', b'\0' * 4)))]
    assert bare == [b'PRPS', b'AIDT']
