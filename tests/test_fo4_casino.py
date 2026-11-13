"""FNV's casino on Fallout 4: the menu movie's toolchain, the bank's Papyrus, the casino records and script rows.

See: docs/fork/fo4_casino_plan.md#phases
"""

import re
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_convert.ui.swf import Swf, Tag
from fo4_import.base.papyrus import FO4_COMPILER, compile_folder, header_dirs
from fo4_import.base import mxmlc
from fo4_import.casino import movie as M
from fo4_import.casino import records as R
from fo4_import.base.install import source_walk, use_source
from fo4_import.base.source import source_plugin
from fo4_import.spike import conditions as C
from fo4_import.spike import level_up_icons as LUI
from fo4_import.spike import say_topics as ST
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from tes5_import.base.tes5_reader import subrecords
from tests.casino import model
from tests.casino import roulette

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
needs_flex = pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
needs_compiler = pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')


# ---------------------------------------------------------------------------
# Phase 0: the menu movie and the bank's scripts
# ---------------------------------------------------------------------------


def test_the_build_date_tags_are_dropped_and_the_metadata_flag_cleared():
    """undated(): no ProductInfo (41) or Metadata (77), FileAttributes keeps AS3 without HasMetadata.
    See: docs/fork/swf_framework.md#mxmlc-setup
    """
    tags = [Tag(69, struct.pack('<I', 0x18)), Tag(77, b'<rdf/>'), Tag(41, b'\x00' * 26), Tag(1, b''), Tag(0, b'')]
    raw = mxmlc.undated(Swf(15, b'\x00', 30 << 8, 1, tags).serialize(compress=False))
    kept = Swf.parse(raw).tags
    assert [t.code for t in kept] == [69, 1, 0] and kept[0].data == struct.pack('<I', 0x08)


@needs_flex
def test_the_movie_builds_to_the_same_bytes_twice_with_its_entry_points(tmp_path):
    """Two builds are identical, undated and uncompressed; the root class carries what F4SE and Papyrus call, the
    library is in."""
    first, second = M.compile_movie(tmp_path / 'a.swf'), M.compile_movie(tmp_path / 'b.swf')
    raw = first.read_bytes()
    assert raw == second.read_bytes() and raw[:3] == b'FWS'
    assert not {t.code for t in Swf.parse(raw).tags} & set(mxmlc.DATED)
    body = raw[8:]
    for name in (b'F3NV_Casino', b'onF4SEObjCreated', b'ProcessUserEvent', b'SendExternalEvent', b'MountImage',
                 b'f3ui', b'HudColor'):
        assert name in body
    assert b'$F3UI_Translation' not in body


@needs_flex
@pytest.mark.parametrize('body', ['var a:int = 1; a++ +;', 'var a:int = "one";'])
def test_a_source_that_does_not_compile_fails_the_build(tmp_path, body):
    """A syntax error, and a type error FFDec let through, are raised, never shipped."""
    (tmp_path / 'src').mkdir()
    source = f'package {{ import flash.display.MovieClip; public class F3NV_Casino extends MovieClip {{ ' \
             f'public function f():void {{ {body} }} }} }}'
    (tmp_path / 'src' / 'F3NV_Casino.as').write_text(source, encoding='utf-8')
    with pytest.raises(RuntimeError, match='mxmlc failed'):
        M.compile_movie(tmp_path / 'out.swf', tmp_path / 'src')


@needs_compiler
def test_the_casino_scripts_compile(tmp_path):
    """F3NV_Casino*.psc compile against Fallout 4's and F4SE's headers."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    names = sorted(p.stem for p in STATIC.glob('F3NV_Casino*.psc'))
    for name in names:
        shutil.copy(STATIC / f'{name}.psc', src)
    log = compile_folder(src, out, f'{src};{header_dirs()}')
    assert sorted(p.stem for p in out.glob('*.pex')) == names, log


#: F4SE menu flags: pauses, uses cursor, modal; Custom Rendering and Assign Cursor To Renderer.
PAUSES, CURSOR, MODAL, CUSTOM_RENDERING, CURSOR_TO_RENDERER = 0x1, 0x4, 0x10, 0x8000, 0x10000


def test_the_menu_registers_without_the_shader_render_path():
    """The menu draws through Scaleform itself: Custom Rendering redrew only around the cursor (played)."""
    source = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    flags = int(re.search(r'Int Property MenuFlags = (0x[0-9A-Fa-f]+)', source)[1], 16)
    assert 'data.menuFlags = MenuFlags' in source
    assert flags & (PAUSES | CURSOR | MODAL) == PAUSES | CURSOR | MODAL
    assert not flags & (CUSTOM_RENDERING | CURSOR_TO_RENDERER)


def test_the_menu_events_match_what_as3_sends():
    """AS3 ints arrive as Papyrus Ints (a Float callback logged "Type mismatch for argument 1"), and every Papyrus
    array the movie reads is unwrapped from F4SE's {__var__: value} (it showed "[object Object]")."""
    source = (STATIC / 'F3NV_Casino.psc').read_text()
    assert 'Function OnMenuPing(Int ' in source and 'Function OnMenuRound(Int ' in source
    document = (Path(M.SOURCES) / 'F3NV_Casino.as').read_text()
    for array in ('paths', 'stops', 'symbols', 'texts', 'seeds'):
        assert f'Bridge.plain({array})' in document, array


RUNTIME = Path(__file__).resolve().parents[1] / 'tes_runtime' / 'fo4_condition'
LIBRARY = mxmlc.LIBRARY / 'f3ui'


def test_the_menu_draws_in_the_hud_color_from_the_dll():
    """No white in the casino or the library but Theme's default; each screen reads F3NV.dll's HudColor native,
    which reads the shared HudColor (condition.h) on every call.
    See: docs/fork/fo4_casino_plan.md#hud-color
    """
    sources = [*AS3.rglob('*.as'), *LIBRARY.glob('*.as')]
    assert [p.name for p in sources if '0XFFFFFF' in p.read_text(encoding='utf-8').upper()] == ['Theme.as']
    theme = (LIBRARY / 'Theme.as').read_text(encoding='utf-8')
    assert 'color = dll != null && dll.HudColor != null ? uint(dll.HudColor()) : WHITE;' in theme
    assert 'Theme.fromHud(dll)' in (AS3 / 'F3NV_Casino.as').read_text(encoding='utf-8')
    dialogue = (RUNTIME / 'dialogue.cpp').read_text(encoding='utf-8')
    assert 'RegisterFunction<HudColorNative>(plugin, movie, "HudColor");' in dialogue
    assert 'args->result->SetUInt(HudColor("iHUDColor"));' in dialogue
    assert 'UInt32 HudColor(const char *prefix);' in (RUNTIME / 'condition.h').read_text(encoding='utf-8')


def test_no_focus_frame_and_no_hud_behind_the_menu():
    """The movie turns off Flash's yellow focus rectangle; the bank hides the HUD while the menu is open.
    See: docs/fork/fo4_casino_plan.md#hud-hidden
    """
    host = (LIBRARY / 'Host.as').read_text(encoding='utf-8')
    assert 'menu.stage.stageFocusRect = false;' in host and 'menu.focusRect = false;' in host
    assert 'Host.focus(this);' in (AS3 / 'F3NV_Casino.as').read_text(encoding='utf-8')
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'UI.Set("HUDMenu", "root1.visible", abShow)' in bank and 'ShowHud(!abOpening)' in bank


def test_images_mount_by_their_path_under_textures():
    """MountImage loads the bare path under Textures (played 1108d): the records write it, f3ui's Images puts any
    form that way, and MountAll and the spike mount through Images."""
    assert R.fo4_path(R.SPIKE_TEXTURE) == 'fnv/terminals/nv_playingcards/deckt/cardt_c01.dds'
    document = (Path(M.SOURCES) / 'F3NV_Casino.as').read_text()
    assert 'images.mount(paths[i], prefix + i)' in document and 'images.mount(paths[i], "F3NV_Spike" + i)' in document
    assert 'bridge.mount(' not in document and 'Textures/' not in document
    images = (LIBRARY / 'Images.as').read_text(encoding='utf-8')
    assert 'bridge.mount(menu, at, name)' in images and 'indexOf("textures/") == 0' in images
    assert 'f4se.MountImage(menu, path, name)' in (LIBRARY / 'Bridge.as').read_text(encoding='utf-8')
    assert 'Textures/' not in (STATIC / 'F3NV_Casino.psc').read_text()


@pytest.mark.skipif(not (EXPORT_FNV := Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm').is_dir(),
                    reason='no FalloutNV.esm export')
def test_spike_shows_staged_level_up_images():
    """The spike's level-up images are ones level_up_icons stages, passed to the screen space and all.

    See: docs/fork/swf_framework.md#level-up
    """
    assert set(R.SPIKE_LEVEL_UP) <= set(LUI.icons(EXPORT_FNV))
    assert R.fo4_path(R.SPIKE_LEVEL_UP[2]) == 'fnv/interface/icons/pipboyimages/perks/perk_action boy.dds'
    assert 'String[] Property SpikeImages' in (STATIC / 'F3NV_Casino.psc').read_text()


# ---------------------------------------------------------------------------
# Phase 1: records, conditions and script rows
# ---------------------------------------------------------------------------

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'


def _source_records() -> dict:
    """{signature: [(FormID, subrecords)]} of FalloutNV.esm's casino records; skipped without the plugin."""
    try:
        use_source(source_plugin(EXPORT))
    except SystemExit:
        pytest.skip('no FalloutNV.esm registered for the export')
    return {sig: [(rec.form_id, subrecords(rec.body)) for rec, _ in source_walk(sig)]
            for sig in (b'CSNO', b'CDCK', b'CCRD')}


def test_falloutnv_has_five_casinos_thirteen_decks_and_270_cards():
    """FalloutNV.esm's casino records, counted from the plugin."""
    found = _source_records()
    assert [len(found[sig]) for sig in (b'CSNO', b'CDCK', b'CCRD')] == [5, 13, 270]


def test_casino_fields_read_the_house_rules():
    """The Atomic Wrangler pays blackjack 6:5 from one deck and bans at 5,000; Gomorrah's dealer hits soft 17."""
    casinos = {fid: R.casino_fields(subs) for fid, subs in _source_records()[b'CSNO']}
    wrangler, gomorrah = casinos[0x00144C42], casinos[0x00140521]
    assert (wrangler['decks'], round(wrangler['payout'], 2), wrangler['max']) == (1, 1.2, 5000)
    assert (wrangler['chip'], wrangler['quest'], wrangler['soft17_stays']) == (0x00144C3E, 0x001614E9, True)
    assert round(wrangler['share'], 2) == 0.35 and wrangler['stops'] == [2] * 7
    assert (gomorrah['decks'], gomorrah['max'], gomorrah['soft17_stays']) == (3, 9000, False)
    assert len(wrangler['symbols']) == 7 and len(wrangler['backs']) == 4


def test_deck_cards_count_the_card_list_not_the_data_count():
    """No-bark's deck lists 41 cards; Lacey's 60."""
    decks = {fid: R.deck_cards(subs) for fid, subs in _source_records()[b'CDCK']}
    assert (len(decks[0x0017B41B]), len(decks[0x0016ACE9])) == (41, 60)
    assert all(len(cards) == len(set(cards)) for cards in decks.values())


def test_every_card_names_a_face_and_a_back():
    """Each CCRD has TX00 and TX01."""
    assert all(len(R.card_textures(subs)) == 2 for _, subs in _source_records()[b'CCRD'])


def test_a_casino_stage_condition_reads_its_level_global():
    """GetCasinoWinningStage <casino> == 2 is GetGlobalValue of the casino's level global."""
    level = 0x05000123
    cond = {'func': 'GetCasinoWinningStage', 'p1': 0x00140521, 'p2': 0, 'op_flags': 0, 'value': 2.0}
    found = ST._form_value(cond['func'], cond, {(ST.CASINO_KEY, 0x00140521): level}, None)
    assert found == (C.FO4.index(ST.GLOBAL_VALUE), level)


def _convert(monkeypatch, body: str, extends: str = 'ObjectReference') -> str:
    """A one-block FNV script as its Fallout 4 conversion."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    return ScriptConverter(CrossRefGraph()).convert_standalone('T', f'scn T\n{body}\n', extends, 'T')


def test_the_openers_call_the_bank_with_the_casinos_data_quest(monkeypatch):
    """ShowSlotMachineMenuParams/ShowBlackjackMenuParams/ShowRouletteMenuParams open games 3, 1 and 2."""
    out = _convert(monkeypatch, 'begin OnActivate\nShowSlotMachineMenuParams GomorrahCasinoData 1 60 0\n'
                                'ShowBlackjackMenuParams GomorrahCasinoData 1 200 0\n'
                                'ShowRouletteMenuParams GomorrahCasinoData 1 200 0\nend')
    assert 'F3NV_CasinoData Property GomorrahCasinoData' in out and 'F3NV_Casino Property TES4Casino' in out
    for game, top in ((3, 60), (1, 200), (2, 200)):
        assert f'TES4Casino.Open({game}, GomorrahCasinoData, 1, {top}, 0)' in out


def test_the_comp_level_is_the_casinos_own(monkeypatch):
    """GetCasinoWinningsLevel <casino> reads the data quest's level."""
    out = _convert(monkeypatch, 'short x\nbegin GameMode\nif GetCasinoWinningsLevel GomorrahCasinoData == 1\n'
                                'set x to 1\nendif\nend', 'Quest')
    assert 'GomorrahCasinoData.GetLevel() == 1' in out


def test_a_picked_up_card_joins_the_collection_only_from_the_player(monkeypatch):
    """CardAddToPlayerScript: AddCardToPlayer is the bank's AddCard, and GetContainer != player is FO4's own."""
    out = _convert(monkeypatch, 'begin OnAdd\nif GetContainer != player\nreturn\nelse\nAddCardToPlayer\nRemoveMe\n'
                                'endif\nend')
    assert 'TES4Casino.AddCard(Self)' in out and '(GetContainer() != Game.GetPlayer())' in out
    assert 'If False' not in out


def test_caravan_is_played_against_the_speaker_with_the_opponents_deck(monkeypatch):
    """ShowCaravanMenu <deck> <mode> <ante> -> OpenCaravan(ref, deck, mode, ante)."""
    out = _convert(monkeypatch, 'begin OnActivate\nGSRingoREF.ShowCaravanMenu CaravanDeckRingo 0 .25\nend')
    assert 'FormList Property CaravanDeckRingo' in out
    assert 'TES4Casino.OpenCaravan(GSRingoREF, CaravanDeckRingo, 0, 0.25' in out


def test_the_bank_names_its_forms_for_converted_scripts():
    """named(): the bank quest as TES4Casino and each casino and deck by its FNV EditorID; form_map: the level."""
    casino = R.Casino.__new__(R.Casino)
    casino.quest, casino.quests, casino.decks = 0x05000001, {0x00140521: 0x05000002}, {0x0015D7A2: 0x05000003}
    casino.levels = {0x00140521: 0x05000004}
    casino.edids = {0x00140521: 'GomorrahCasinoData', 0x0015D7A2: 'CaravanDeckRingo'}
    assert casino.named() == {'TES4Casino': 0x05000001, 'GomorrahCasinoData': 0x05000002,
                              'CaravanDeckRingo': 0x05000003}
    assert casino.form_map()[(ST.CASINO_KEY, 0x00140521)] == 0x05000004


def test_a_dlc_uses_its_masters_casinos_and_bank():
    """A DLC build's own casino is derived; FalloutNV's casino and the bank are the master's ids, never copies
    (five banks registered every menu event five times, played 2026-11-08)."""
    master = {(R.SITE, 'GomorrahCasinoData'): 0x03000002, (R.SITE, R.QUEST): 0x03000001}
    writer = SimpleNamespace(own_index=5, from_master=lambda site, key: master.get((site, key)),
                             derive_formid=lambda site, key: 0x05000000 | len(key))
    casino = R.Casino.__new__(R.Casino)
    casino.builder = SimpleNamespace(writer=writer, built=['FalloutNV.esm'],
                                     ids=SimpleNamespace(is_own=lambda fid: fid >> 24 == 1))
    casino.records = {b'CSNO': [(0x00140521, []), (0x01000ABC, [])]}
    casino.edids = {0x00140521: 'GomorrahCasinoData', 0x01000ABC: 'SierraMadreCasinoData'}
    assert casino._forms(b'CSNO', '') == {0x00140521: 0x03000002, 0x01000ABC: 0x05000015}
    assert casino._forms(b'CSNO', 'Level') == {0x01000ABC: 0x0500001A}
    assert casino._form(False, R.QUEST) == 0x03000001 and not casino.mine(0x03000001)


def test_the_texts_are_falloutnvs_engine_defaults():
    """FalloutNV.esm sets no casino text: the bank gets the exe's, and 60 s."""
    values = R.texts(EXPORT)
    assert values['BannedText'] == ('string', 'You have been banned from gambling at this casino.')
    assert values['AntiCheatSeconds'] == ('float', 60.0) and len(values['AntiCheatTexts'][1]) == 3


# ---------------------------------------------------------------------------
# Phase 2: slots (the reference model, and the AS3 and Papyrus that follow it)
# ---------------------------------------------------------------------------

AS3 = Path(M.SOURCES)


def test_xorshift32_gives_the_textbook_sequence():
    """Seed 1 gives the textbook numbers; seed 0 is replaced (it never leaves 0)."""
    rng = model.Rng(1)
    assert [rng.next() for _ in range(3)] == [270369, 67634689, 2647435461]
    assert model.Rng(0).state == model.SEED_ZERO


def test_a_reel_is_fnvs_symbol_and_blank_pairs_round_by_round():
    """Stops 2 each: the 14 values twice; a kind with no stops is skipped."""
    assert model.reel([2] * 7) == list(range(14)) * 2
    assert model.reel([1, 0, 1, 0, 0, 0, 0]) == [0, 1, 4, 5]


@pytest.mark.parametrize('values, kind, times', [
    ([12, 12, 12], model.THREE, 10), ([0, 0, 0], model.THREE, 10), ([10, 10, 10], model.THREE, 100),
    ([12, 12, 3], model.TWO_WILDS, 5), ([4, 12, 7], model.ONE_WILD, 2), ([4, 4, 7], model.PAIR, 0),
    ([1, 1, 1], model.NOTHING, 0), ([0, 2, 4], model.NOTHING, 0)])
def test_slot_results_pay_as_fnv(values, kind, times):
    """Three of a kind by symbol, two wilds x5, one wild x2; blanks never count."""
    assert (model.classify(values), model.pays(values)) == (kind, times)


def test_bet_steps_follow_fnv():
    """+1 below 10, +5 below 40, +10 below 100, +25 below 500, then +100; down retraces."""
    bets = [1]
    while bets[-1] < 700:
        bets.append(model.bet_up(bets[-1]))
    assert bets[9:12] == [10, 15, 20] and bets[-2:] == [600, 700]
    assert all(model.bet_down(b) == a for a, b in zip(bets, bets[1:]))


def _mean_net(luck: int, spins: int = 60000) -> float:
    """The mean net (in bets) of `spins` spins at `luck`, seeded."""
    slots = model.Slots([2] * 7, luck, model.Rng(luck * 7919 + 1))
    total = 0
    for _ in range(spins):
        values, _lucky = slots.spin()
        times = model.pays(values)
        total += times if times else -1
    return total / spins


def test_the_house_keeps_about_a_quarter_at_luck_5_and_luck_moves_it():
    """Luck 5 returns -0.2595 a bet (exact: (1479 - 2191) / 2744); 1 less, 10 more."""
    fair = _mean_net(5)
    assert abs(fair - (1479 - 2191) / 2744) < 0.03
    assert _mean_net(1) < fair < _mean_net(10)


def test_the_as3_rules_carry_the_models_numbers():
    """Slots.as's pay table and constants are the model's (the AS3 can't run in the suite)."""
    source = (AS3 / 'f3nv' / 'casino' / 'Slots.as').read_text(encoding='utf-8')
    table = [model.THREE_PAYS.get(v, 0) for v in range(model.WILD + 1)]
    assert f'[{", ".join(map(str, table))}]' in source
    for name in ('WILD', 'WILD_BLANK', 'NOTHING', 'PAIR', 'ONE_WILD', 'TWO_WILDS', 'THREE', 'FAIR_LUCK'):
        assert f'public static const {name}:int = {getattr(model, name)};' in source


def test_the_slot_texts_are_in_the_screens_order():
    """records.SLOT_TEXTS has one text per SlotsScreen index, the last index its last."""
    source = (AS3 / 'f3nv' / 'casino' / 'SlotsScreen.as').read_text(encoding='utf-8')
    indexes = [int(n) for n in re.findall(r'public static const [A-Z_]+:int = (\d+);', source)]
    assert indexes == list(range(len(R.SLOT_TEXTS)))


#: The Papyrus.0.log lines of `cqf FNV_Casino SelfTest <luck>`, each pasted after "selftest " (absent until captured).
CAPTURED = Path(__file__).resolve().parent / 'casino' / 'selftest.txt'


def _captured(game: str) -> list:
    """The captured self-test lines of `game` (slots, roulette)."""
    lines = CAPTURED.read_text(encoding='utf-8').split('\n') if CAPTURED.is_file() else []
    return [line.strip() for line in lines if line.startswith(game + ' ')]


def test_the_self_test_line_is_the_models_per_seed_spins():
    """slot_trace: 'slots <luck>' then 20 spins a seed, three values each."""
    line = model.slot_trace((1, 2, 3), 20, 5).split(' ')
    assert line[:2] == ['slots', '5'] and len(line) == 62 and all(len(s.split(',')) == 3 for s in line[2:])


@pytest.mark.skipif(not _captured('slots'), reason='no in-game self-test captured yet')
def test_the_movies_spins_match_the_model():
    """Each captured slots line is the model's for seeds 1-3, at its Luck."""
    for line in _captured('slots'):
        assert line == model.slot_trace((1, 2, 3), 20, int(line.split(' ')[1]))


# ---------------------------------------------------------------------------
# Phase 3: roulette
# ---------------------------------------------------------------------------


def test_the_board_has_fnvs_159_spots_by_kind():
    """InitRouletteWheel: 38 straights, 60 splits, 15 streets and baskets, 22 corners, the top line, 11 lines and
    12 outside spots."""
    kinds = {}
    for i in range(roulette.SPOTS):
        named, odds = roulette.spot(i)
        kinds[(len(named), odds)] = kinds.get((len(named), odds), 0) + 1
    assert kinds == {(1, 35): 38, (2, 17): 60, (3, 11): 15, (4, 8): 22, (5, 6): 1, (6, 5): 11, (0, 2): 6, (0, 1): 6}
    straights = [roulette.spot(i)[0][0] for i in range(roulette.SPOTS) if roulette.spot(i)[1] == 35]
    assert sorted(straights) == list(range(38))


@pytest.mark.parametrize('index, named, odds', [
    (25, (1,), 35), (26, (1, 4), 17), (49, (1, 2), 17), (50, (1, 2, 4, 5), 8), (1, (1, 2, 3), 11),
    (2, (1, 2, 3, 4, 5, 6), 5), (0, (0, 37, 1, 2, 3), 6), (72, (37, 0, 2), 11), (143, (36,), 35), (144, (37,), 35)])
def test_spots_name_fnvs_numbers(index, named, odds):
    """Rows of 24, street edge to the 3s: odd places numbers, even the lines."""
    assert roulette.spot(index) == (named, odds)


def test_zero_pays_only_on_its_own_spot_red_even_and_the_third_column():
    """0 wins straight, red, even, column 3; 00 black, odd, column 1.
    See: docs/fork/fo4_casino_plan.md#roulette-built
    """
    assert {i for i in range(roulette.SPOTS) if roulette.wins(i, 0)} == {146, 149, 151, 158}
    assert {i for i in range(147, 159) if roulette.wins(i, 37)} == {152, 154, 156}
    assert roulette.wins(145, 37) and not roulette.wins(24, 0) and roulette.wins(24, 1)


@pytest.mark.parametrize('index, edge', [(146, -2), (25, -2), (151, 0), (149, 0), (156, 1), (157, -2), (147, -2),
                                         (145, -20), (0, -10)])
def test_each_bets_return_follows_from_fnvs_rules(index, edge):
    """One chip's exact return in 38ths of a chip, from FNV's rules.
    See: docs/fork/fo4_casino_plan.md#roulette-built
    """
    won = sum(roulette.spot(index)[1] + 1 for r in range(roulette.POCKETS) if roulette.wins(index, r))
    assert won - roulette.POCKETS == edge


def test_a_spin_pays_odds_plus_one_on_each_winner_less_the_table():
    """A straight on the result returns 36x, red 2x; the net takes the table back; the bet returns to the min."""
    table = roulette.Table(100, 5, 200, model.Rng(1))
    result = model.Rng(1).below(roulette.POCKETS)
    straight = next(i for i in range(roulette.SPOTS) if roulette.spot(i) == ((result,), 35))
    table.place(straight)
    table.bet_up()
    table.place(151)
    red = roulette.wins(151, result)
    assert table.spin() == (result, 36 * 5 + (2 * 6 if red else 0) - 11) and table.bet == 5


def test_the_max_covers_every_bet_on_a_spin():
    """The bet shrinks to the max left; ten bets at most; one bet a spot; removing one frees its chips."""
    table = roulette.Table(1000, 1, 200, model.Rng(1))
    while table.bet < 60:
        table.bet_up()
    assert table.bet == 60
    assert table.place(25) and table.place(27) and table.place(29) and table.bet == 20 and table.total == 180
    assert table.place(31) and table.total == 200 and table.bet == 0 and not table.place(33)
    assert not table.place(25) and table.remove(31) and table.total == 180
    small = roulette.Table(1000, 1, 1000, model.Rng(1))
    assert all(small.place(i) for i in range(10)) and small.bet == 0 and not small.place(10)


def test_the_bet_never_takes_more_than_the_chips_left():
    """FNV's frame rule: chips 12, two bets of 5: the bet is 2."""
    table = roulette.Table(12, 5, 200, model.Rng(1))
    assert table.place(25) and table.place(27) and table.bet == 2


def test_roulette_bet_steps_go_down_to_the_steps_multiple():
    """Down: -1 to 10, then to the multiple of 5, 10, 25, 100, or a step."""
    assert [roulette.bet_down(b) for b in (10, 11, 13, 15, 40, 43, 100, 120, 130, 510, 600)] == \
        [9, 10, 10, 10, 35, 40, 90, 100, 125, 500, 500]


def test_the_min_holds_while_the_max_leaves_room():
    """Down from the min stays at the min unless the table already fills the max."""
    table = roulette.Table(1000, 5, 200, model.Rng(1))
    table.bet_down()
    assert table.bet == 5


def test_a_long_run_returns_what_the_rules_say():
    """60,000 seeded spins of one chip on 11 and one on red: -2/38 a spin, within noise."""
    rng, total = model.Rng(4242), 0
    for _ in range(60000):
        result = rng.below(roulette.POCKETS)
        total += (36 if roulette.wins(79, result) else 0) + (2 if roulette.wins(151, result) else 0) - 2
    assert roulette.spot(79) == ((11,), 35) and abs(total / 60000 - (-2 / 38)) < 0.05


def test_the_as3_roulette_carries_the_models_numbers():
    """Roulette.as's wheel and limits are the model's (the AS3 can't run in the suite; the self-test checks the rest)."""
    source = (AS3 / 'f3nv' / 'casino' / 'Roulette.as').read_text(encoding='utf-8')
    assert ', '.join(map(str, roulette.WHEEL[:19])) in source and ', '.join(map(str, roulette.WHEEL[19:])) in source
    for name in ('POCKETS', 'SPOTS', 'MOST_BETS', 'DOUBLE_ZERO'):
        assert f'public static const {name}:int = {getattr(roulette, name)};' in source


def test_the_roulette_texts_are_in_the_screens_order():
    """records.ROULETTE_TEXTS has one text per RouletteScreen index, and the bank and menu pass them."""
    source = (AS3 / 'f3nv' / 'casino' / 'RouletteScreen.as').read_text(encoding='utf-8')
    indexes = [int(n) for n in re.findall(r'public static const [A-Z_]+:int = (\d+);', source)]
    assert indexes == list(range(len(R.ROULETTE_TEXTS)))
    assert len(R.texts(EXPORT)['RouletteTexts'][1]) == len(R.ROULETTE_TEXTS)
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'StringsAsVar(RouletteTexts)' in bank and '"root1.OpenRoulette"' in bank


def test_every_table_game_opens():
    """Open lets blackjack, roulette and slots through (Caravan has OpenCaravan)."""
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'If aiGame != Slots' not in bank and 'Int Property Roulette = 2' in bank and 'Int Property Blackjack = 1' in bank


def test_the_roulette_self_test_line_is_the_models():
    """roulette_trace: 'roulette', 60 results, then the 159 spots' odds and win masks."""
    line = roulette.roulette_trace((1, 2, 3), 20).split(' ')
    assert line[0] == 'roulette' and len(line) == 62 and len(line[61].split(',')) == roulette.SPOTS
    assert line[61].split(',')[146] == '35:1'


@pytest.mark.skipif(not _captured('roulette'), reason='no in-game self-test captured yet')
def test_the_movies_roulette_matches_the_model():
    """Each captured roulette line is the model's for seeds 1-3."""
    for line in _captured('roulette'):
        assert line == roulette.roulette_trace((1, 2, 3), 20)
