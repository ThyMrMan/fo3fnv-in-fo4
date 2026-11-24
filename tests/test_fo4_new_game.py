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


def _quest(monkeypatch, plugin: str, quests: dict, movie: str = '') -> tuple:
    """(builder, the new game QUST's subrecords, its VMAD) built for `plugin` with intro_movie() giving `movie`."""
    written = []
    builder = SimpleNamespace(writer=SimpleNamespace(derive_formid=lambda site, key: 0x01000800,
                                                     add_record=lambda sig, rec: written.append((sig, rec))),
                              perks=SimpleNamespace(gates=0x01000900), combat=SimpleNamespace(fid=0x01000901, damage_rules=({}, {}), settings={}),
                              counts=Counter(),
                              scripts=SimpleNamespace(used=[]))
    monkeypatch.setattr(new_game, 'start_special', lambda export_dir: [5.0] * 7)
    monkeypatch.setattr(new_game, 'PlayerRules', lambda *args: SimpleNamespace(write=lambda: None))
    monkeypatch.setattr(new_game, 'intro_movie', lambda export_dir: movie)
    new_game.build(builder, Path('export') / plugin, quests)
    (sig, rec), = written
    assert sig == 'QUST'
    subs = list(subrecords(rec[24:]))
    return builder, subs, dict(subs)[b'VMAD']


def test_the_new_game_quest_has_a_hand_start_stage(monkeypatch):
    """FNV_NewGame carries F3NV_NewGame and stages 5 (the opening and character creation) and 10 (FNV at once),
    run by hand through F3NV_NewGameStart's fragments."""
    builder, subs, vmad = _quest(monkeypatch, 'FalloutNV.esm', {'VCG00': 0x0100A000})
    assert builder.scripts.used == [new_game.FRAGMENTS]
    assert all((b'INDX', struct.pack('<HBB', s, 0, 0)) in subs for s in (new_game.OPEN_BY_HAND, new_game.START_BY_HAND))
    assert all(name in vmad for name in (b'F3NV_NewGame', b'F3NV_NewGameStart', b'Fragment_Stage_0005_Item_00',
                                         b'Fragment_Stage_0010_Item_00'))
    assert b'AnimArchetypePlayer' in vmad and struct.pack('<I', new_game.ANIM_PLAYER) in vmad
    assert b'IntroMovie' not in vmad


def test_fallout3_plays_its_new_game_movie(monkeypatch):
    """FO3's intro (shipped sIntroMovie) is F3NV_NewGame's IntroMovie."""
    _, _, vmad = _quest(monkeypatch, 'Fallout3.esm', {'CG00': 0x0100A000}, 'Fallout INTRO Vsk.bik')
    assert b'IntroMovie' in vmad and b'Fallout INTRO Vsk.bik' in vmad


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
