"""Lucky Horseshoes on Fallout 4: the reference model pins FNV's dialogue rules; the AS3, bank and opener follow it.

See: docs/fork/fo4_casino_plan.md#lucky-horseshoes
"""

import re

import pytest

from fo4_import.casino import records as R
from script_convert import pipeline
from script_convert.context_setup import service_menu_topics
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from tests.casino import horseshoes as H
from tests.casino.model import Rng
from tests.test_fo4_casino import AS3, STATIC, _captured


def _game(values: list) -> H.Horseshoes:
    """A game whose draws come out as `values`, in turn order."""
    game = H.Horseshoes(Rng(1))
    game.card = lambda: values.pop(0)
    return game


def _festus_holding() -> H.Horseshoes:
    """The player on 9, Festus holding on 18 (leading, 3 from 21)."""
    game = _game([10, 10, 8])
    game.draw()
    game.totals[H.PLAYER] = 9
    game.take(H.FESTUS)
    game._festus_turn()
    return game


def test_the_deck_is_aces_to_tens_four_of_each():
    """Values 1-10 alike; a value used four times rolls again, twice at most (then a fifth copy is possible)."""
    game = H.Horseshoes(Rng(3))
    assert {game.card() for _ in range(500)} == set(range(1, 11))
    game.used = [0] + [H.COPIES] * 9 + [0]
    cards = [game.card() for _ in range(1000)]
    assert 200 < cards.count(10) < 350 and set(cards) <= set(range(1, 11))


def test_the_player_draws_first_and_festus_answers():
    """Draw: a card for the player, then Festus's card."""
    game = _game([5, 7])
    assert game.draw() == H.PLAYING
    assert game.totals == [5, 7] and not game.winning


def test_a_tie_pushes_the_other_up_one():
    """Lucky Horseshoes: Festus ties the player's 6, so the player goes to 7."""
    game = _game([6, 6])
    game.draw()
    assert game.totals == [7, 6] and game.nudged == 1 << H.FESTUS and game.winning


def test_equal_distances_keep_the_lead():
    """20 and 22 are both 1 from 21: the lead stays with whoever had it."""
    game = _game([10, 9, 10, 3, 2])
    game.draw()
    game.draw()
    assert game.totals == [20, 12] and game.winning
    game.totals[H.FESTUS] = 20
    game.take(H.FESTUS)
    assert game.totals == [20, 22] and game.winning


def test_holding_while_behind_draws_instead():
    """"If you hold now, pardner, I'll win! Let's pretend you drew": a hold while behind is a draw."""
    game = _game([3, 9, 4, 2])
    game.draw()
    game.hold()
    assert not game.holding[H.PLAYER] and game.hands[H.PLAYER] == [(3, 0), (4, 0)]


def test_festus_holds_when_leading_within_four():
    """Festus on 18 leads the player's 9 and holds."""
    game = _festus_holding()
    assert game.totals == [9, 18] and game.holding[H.FESTUS] and game.result == H.PLAYING


def test_festus_draws_while_behind():
    """Festus never holds while the player leads."""
    game = _game([10, 9, 10, 2])
    game.draw()
    game.draw()
    assert game.totals == [20, 11] and not game.holding[H.FESTUS]


def test_the_leader_wins_once_the_other_holds():
    """The player holds on 20; Festus draws until he passes it: 22 is as far as 20, so the player wins."""
    game = _game([10, 5, 10, 3, 10, 4])
    game.draw()
    game.draw()
    assert game.totals == [20, 8] and game.hold() == H.WON and game.totals[H.FESTUS] == 22


def test_festus_wins_by_getting_nearer_while_the_player_holds():
    """The player holds on 18; Festus's 19 is nearer: Festus wins."""
    game = _game([9, 5, 9, 5, 9])
    game.draw()
    game.draw()
    assert game.totals == [18, 10] and game.hold() == H.LOST and game.totals[H.FESTUS] == 19


def test_going_over_behind_loses_at_once():
    """Over 21 and behind ends the game; over 21 but nearer plays on."""
    game = _game([10, 9, 10, 10, 5])
    game.draw()
    game.draw()
    assert game.totals == [20, 19] and game.draw() == H.LOST and game.totals[H.PLAYER] == 25
    game = _game([10, 2, 10, 2, 2, 3])
    game.draw()
    game.draw()
    assert game.draw() == H.PLAYING and game.totals == [22, 7] and game.winning


def test_festus_holding_loses_to_a_nearer_player():
    """Festus holds on 18; the player draws to 19 and wins."""
    game = _festus_holding()
    game.card = lambda: 10
    assert game.draw() == H.WON and game.totals == [19, 18]


def test_the_self_test_play_always_ends():
    """Every self-test game ends in a win or a loss, both seen."""
    game = H.Horseshoes(Rng(7))
    assert {H.play(game) for _ in range(500)} == {H.WON, H.LOST}


def test_the_horseshoes_self_test_line_is_the_models():
    """horseshoes_trace: 'horseshoes', then 20 games a seed as values/values=result."""
    line = H.horseshoes_trace((1, 2, 3), 20).split(' ')
    assert line[0] == 'horseshoes' and len(line) == 61
    assert all(re.fullmatch(r'[\d.]+/[\d.]+=[12]', g) for g in line[1:])


def test_the_as3_horseshoes_carries_the_models_numbers():
    """Horseshoes.as's constants are the model's (the self-test checks the rest in game)."""
    source = (AS3 / 'f3nv' / 'casino' / 'Horseshoes.as').read_text(encoding='utf-8')
    for name in ('TARGET', 'VALUES', 'COPIES', 'REROLLS', 'FESTUS_HOLDS_UNDER', 'PLAYING', 'WON', 'LOST', 'PLAYER',
                 'FESTUS'):
        assert f'public static const {name}:int = {getattr(H, name)};' in source


def test_the_bank_opens_horseshoes_and_pays_fnvs_reward():
    """OpenHorseshoes opens the menu; a win draws FNV's reward (a star cap, else cards, else caps)."""
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'Function OpenHorseshoes(ObjectReference akFestus)' in bank and '"root1.OpenHorseshoes"' in bank
    assert 'RegisterForExternalEvent("F3NV_HorseshoesResult", "OnHorseshoesResult")' in bank
    for name in R.HORSESHOES_REWARDS:
        assert f'Form Property {name} Auto Const' in bank
    assert 'public function OpenHorseshoes(' in (AS3 / 'F3NV_Casino.as').read_text(encoding='utf-8')


def test_the_start_line_ends_the_talk_and_opens_the_game(tmp_path, monkeypatch):
    """On Fallout 4, SSHQFestusLuckyHorseshoes's line ends the talk and opens the menu through the bank."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    dials = [{'FormID': '0010592F', 'EditorID': 'SSHQFestusLuckyHorseshoes'}, {'FormID': '0010592E', 'EditorID': 'X'}]
    topics = service_menu_topics({'DIAL': dials})
    assert topics == {'0010592F': 'horseshoes'}
    stats = pipeline._new_stats()
    pipeline._info_batch([{'FormID': '00105940', 'ParentDIAL': '0010592F'}], str(tmp_path), CrossRefGraph(), stats,
                         {}, topics)
    assert not stats['errors'], stats['errors']
    text = next(tmp_path.glob('*TIF__00105940.psc')).read_text(encoding='utf-8')
    assert 'F3NV_Casino Property TES4Casino Auto Const' in text and 'TES4Casino.OpenHorseshoes(akSpeakerRef)' in text
    assert text.index('EndTalk(akSpeakerRef)') < text.index('OpenHorseshoes')


@pytest.mark.skipif(not _captured('horseshoes'), reason='no in-game self-test captured yet')
def test_the_movies_horseshoes_matches_the_model():
    """The captured horseshoes line is the model's for seeds 1-3."""
    for line in _captured('horseshoes'):
        assert line == H.horseshoes_trace((1, 2, 3), 20)
