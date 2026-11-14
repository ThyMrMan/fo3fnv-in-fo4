"""FNV head parts become facial hair or brows only when FNV draws them as hair (their mesh names a hair layer): the
eyepatch, whose strap sits above the eyes, is worn as its own part, not painted onto the face as a brow.

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fo4_import.face import sculpt
from fo4_import.face.bake import face_shape
from fo4_import.spike import fnv_npc

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
needs_export = pytest.mark.skipif(not (EXPORT / 'NPC_.txt').exists(), reason='needs the FNV export')


def test_a_part_not_drawn_as_hair_is_unmapped_wherever_it_sits(monkeypatch):
    """Above, below and between the eyes: a hair-layer part is a brow, facial hair, unmapped; any other unmapped."""
    heights = {'brow': 5.0, 'beard': -3.0, 'mid': 2.5, 'patch': 4.0, 'chin_patch': -3.0}
    monkeypatch.setattr(fnv_npc, 'head_parts', lambda d, fid: [(name, name) for name in heights])
    monkeypatch.setattr(fnv_npc, 'asset', lambda d, folder, rel: rel)
    monkeypatch.setattr(fnv_npc, 'hair_drawn', lambda mesh: 'patch' not in mesh)
    monkeypatch.setattr(fnv_npc.hair, 'fnv_shape', lambda mesh: (np.array([[0.0, 0.0, heights[mesh]]]),))
    at = SimpleNamespace(npc={'FormID': '00000001'}, to_fo4=lambda p: p, eyes=(2.0, 3.0))
    assert fnv_npc.sorted_parts(None, at) == (['beard'], ['brow'], ['mid', 'patch', 'chin_patch'])


@needs_export
def test_only_the_eyepatch_of_the_game_head_parts_is_not_drawn_as_hair():
    """Of FalloutNV.esm's head part meshes, every beard and brow names a hair layer; the eyepatch alone does not."""
    _, parts = fnv_npc._head_chain(str(EXPORT))
    meshes = {model.lower(): edid for edid, model in parts.values() if model}
    plain = sorted(edid for model, edid in meshes.items()
                   if not fnv_npc.hair_drawn(fnv_npc.asset(EXPORT, 'meshes', model)))
    assert plain == ['Eyepatch'] and len(meshes) > 15


@needs_export
def test_tommy_torinis_eyepatch_is_not_a_brow():
    """VMSTopsTommyTorini: the mustache stays facial hair; the eyepatch, centred above his eyes, is no brow."""
    if sculpt.load_basis(False) is None:
        pytest.skip('needs the male sculpt basis')
    at = fnv_npc.frame(EXPORT, 'VMSTopsTommyTorini', face_shape(sculpt.load_basis(False)[2])[0])
    facial, brows, unmapped = fnv_npc.sorted_parts(EXPORT, at)
    assert [p.name for p in facial] == ['beardmustache.nif'] and brows == [] and unmapped == ['Eyepatch']


@needs_export
def test_tommy_torini_wears_the_eyepatch_as_his_own_part():
    """worn_parts gives his eyepatch (FNV HDPT 00073D56) and not his mustache."""
    assert fnv_npc.worn_parts(EXPORT, 0x1164FC) == [(0x73D56, 'Eyepatch', 'Characters\\Hair\\Eyepatch.NIF')]
