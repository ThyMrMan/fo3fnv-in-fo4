"""FNV weather modifiers on the worldspace imagespace (tints averaged by alpha) and FNV's cloud colours.

See: docs/fork/fo4_look.md#weather-imagespace
"""
import struct

import pytest

from fo4_import.spike import weather_clouds as C, weather_imagespace as W
from fo4_import.spike.imagespace import Cinematic

BASE = Cinematic(saturation=0.9, pivot=0.2, contrast=1.1, brightness=1.0, tint=(0.5, 0.5, 0.5), tint_amount=0.2)


#: NVDefaultExterior's own tint (orange at 0.33, its flags off).
OWN = ((0.98, 0.57, 0.0), 0.33)


def _tnam(r, g, b, a) -> bytes:
    """A modifier's tint keys: (r, g, b, a) first, then FNV's usual second key."""
    return struct.pack('<5f', 0, r, g, b, a) + struct.pack('<5f', 1, 1, 1, 1, 0)


def test_night_tint_averages_to_near_neutral():
    """FNV's night blue at 0.627 with the orange at 0.33: near-neutral."""
    graded = W.tinted(BASE, OWN, {b'TNAM': _tnam(0.216, 0.467, 0.925, 0.627)})
    assert graded.tint_amount == pytest.approx(0.627)
    assert [round(c, 2) for c in graded.tint] == [0.48, 0.50, 0.61]


def test_only_the_tint_carries():
    """A modifier's brightness is ignored; no tint keeps the own one."""
    graded = W.tinted(BASE, OWN, {bytes([0x14]) + b'IAD': struct.pack('<2f', 0, 1.3)})
    assert (graded.saturation, graded.contrast, graded.brightness) == (0.9, 1.1, 1.0)
    assert graded.tint == pytest.approx(OWN[0]) and graded.tint_amount == pytest.approx(0.33)


def test_fo4_cloud_layers_take_fnv_layer_colours():
    """FNV's clear weather draws layer 3 (BNAM); every FO4 layer takes its colour per FO4 time (day: FNV time 1)."""
    source = {b'DNAM': b'sky\\alpha.dds\0', b'BNAM': b'sky\\NVCloudlight.dds\0', b'PNAM': bytes(range(96))}
    assert C.fnv_layers(source) == [(3, 'sky\\NVCloudlight.dds')]
    times = (0, 1, 2, 3, 0, 0, 2, 2)
    pnam = C.cloud_colours(source, 3, times)
    assert len(pnam) == C.FO4_LAYERS * len(times) * 4
    day = (3 * C.FNV_TIMES + 1) * 4
    assert pnam[4:8] == bytes(range(96))[day:day + 4] == pnam[36:40]
