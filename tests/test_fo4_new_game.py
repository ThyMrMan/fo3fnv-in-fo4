"""The source game's new game quest: its scripts, and stage 10 starting the source game by hand.

See: docs/fork/fo4_pipeline.md#new-game
"""
import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fo4_import.spike import new_game
from tes5_import.base.tes5_reader import subrecords


def test_the_new_game_quest_has_a_hand_start_stage(monkeypatch):
    """FNV_NewGame carries TES4_NewGame and a stage 10 whose fragment (TES4_NewGameStart) starts FNV by hand."""
    written = []
    builder = SimpleNamespace(writer=SimpleNamespace(derive_formid=lambda site, key: 0x01000800,
                                                     add_record=lambda sig, rec: written.append((sig, rec))),
                              perks=SimpleNamespace(gates=0x01000900), counts=Counter(),
                              scripts=SimpleNamespace(used=[]))
    monkeypatch.setattr(new_game, 'start_special', lambda export_dir: [5.0] * 7)
    new_game.build(builder, Path('export/FalloutNV.esm'), {'VCG00': 0x0100A000})
    (sig, rec), = written
    subs = list(subrecords(rec[24:]))
    vmad = dict(subs)[b'VMAD']
    assert sig == 'QUST' and builder.scripts.used == [new_game.FRAGMENTS]
    assert (b'INDX', struct.pack('<HBB', new_game.START_BY_HAND, 0, 0)) in subs
    assert all(name in vmad for name in (b'TES4_NewGame', b'TES4_NewGameStart', b'Fragment_Stage_0010_Item_00'))
