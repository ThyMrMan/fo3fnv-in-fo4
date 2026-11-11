"""The source game's new game quest: its scripts, and stage 10 starting the source game by hand.

See: docs/fork/fo4_pipeline.md#new-game
"""
import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import new_game
from fo4_import.spike import script as spike_script
from tes5_import.base.tes5_reader import subrecords


def test_the_new_game_quest_has_a_hand_start_stage(monkeypatch):
    """FNV_NewGame carries F3NV_NewGame and a stage 10 whose fragment (F3NV_NewGameStart) starts FNV by hand."""
    written = []
    builder = SimpleNamespace(writer=SimpleNamespace(derive_formid=lambda site, key: 0x01000800,
                                                     add_record=lambda sig, rec: written.append((sig, rec))),
                              perks=SimpleNamespace(gates=0x01000900), combat=SimpleNamespace(fid=0x01000901, damage_rules=({}, {}), settings={}),
                              counts=Counter(),
                              scripts=SimpleNamespace(used=[]))
    monkeypatch.setattr(new_game, 'start_special', lambda export_dir: [5.0] * 7)
    monkeypatch.setattr(new_game, 'PlayerRules', lambda *args: SimpleNamespace(write=lambda: None))
    new_game.build(builder, Path('export/FalloutNV.esm'), {'VCG00': 0x0100A000})
    (sig, rec), = written
    subs = list(subrecords(rec[24:]))
    vmad = dict(subs)[b'VMAD']
    assert sig == 'QUST' and builder.scripts.used == [new_game.FRAGMENTS]
    assert (b'INDX', struct.pack('<HBB', new_game.START_BY_HAND, 0, 0)) in subs
    assert all(name in vmad for name in (b'F3NV_NewGame', b'F3NV_NewGameStart', b'Fragment_Stage_0010_Item_00'))


def test_fallout3_opens_at_cg00_with_its_own_script_names():
    """FO3's opening is CG00 stage 0, and its build names converted scripts FALLOUT3_; FNV's stay FALLOUTNV_."""
    assert new_game.START['Fallout3.esm'] == ('CG00', 0)
    try:
        spike_script.use_prefix(Path('export/Fallout3.esm'))
        assert spike_script.prefix(spike_script.QUEST) == 'FALLOUT3_QF_'
        spike_script.use_prefix(Path('export/DeadMoney.esm'))
        assert spike_script.prefix(spike_script.FRAGMENT) == 'FALLOUTNV_TIF__'
    finally:
        spike_script.use_prefix(Path('export/FalloutNV.esm'))


def test_fallout3_names_its_own_actor_values():
    """An FO3 build names actor value 41 Small Guns (the helper's SmallGuns, as its scripts use); FNV's is Guns."""
    try:
        C.use_actor_values(Path('export/Fallout3.esm'))
        assert C.fnv_av_name(41) == 'SmallGuns' and C.FNV_AV_NAMES.index('Big Guns') == 33
    finally:
        C.use_actor_values(Path('export/FalloutNV.esm'))
    assert C.fnv_av_name(41) == 'Guns'
