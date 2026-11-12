"""Phase 4: FNV's blackjack on Fallout 4 (the reference model, and the AS3, Papyrus and records that follow it).

See: docs/fork/fo4_casino_plan.md#blackjack-built
"""

import re

import pytest

from fo4_import.casino import records as R
from tests.casino import blackjack as B
from tests.casino.model import Rng
from tests.test_fo4_casino import AS3, EXPORT, STATIC, _captured

#: The Tops' rules: 4 decks, reshuffle under 35%, naturals 3:2, the dealer stands on soft 17.
TOPS = {'decks': 4, 'share': 0.35, 'payout': 1.5, 'stays': True}
TWO, NINE, TEN, JACK, QUEEN, KING, ACE = 0, 7, 8, 9, 10, 11, 12


def _table(ranks: list, bet: int = 10, chips: int = 1000, **rules) -> B.Table:
    """A table whose shoe deals `ranks` in order (the deal goes dealer, player, dealer, player)."""
    table = B.Table(chips, 5, 100, {**TOPS, **rules}, 5, Rng(1))
    cards = [(rank, 0, 0) for rank in ranks]
    table.shoe.draw = lambda hand, skill, dealer: cards.pop(0)
    table.bet = bet
    return table


@pytest.mark.parametrize('ranks, total', [
    ([ACE, KING], 21), ([ACE, ACE], 12), ([ACE, ACE, NINE], 21), ([KING, QUEEN, TWO], 22), ([ACE, 4, KING], 17)])
def test_aces_drop_to_one_only_while_the_hand_is_over_21(ranks, total):
    """hand_value: faces 10, aces 11 until the total passes 21."""
    assert B.hand_value([(rank, 0, 0) for rank in ranks]) == total


def test_bet_steps_follow_fnvs_blackjack():
    """Up 1, 5, 10, 25, 100, 500 by size; down to the step's multiple, or a step."""
    assert [B.bet_up(b) for b in (9, 10, 40, 100, 400, 1500)] == [10, 15, 50, 125, 500, 2000]
    assert [B.bet_down(b) for b in (10, 11, 15, 37, 50, 125, 450, 2000)] == [9, 10, 10, 35, 40, 100, 400, 1500]


def test_a_plain_draw_passes_over_a_card():
    """FNV's double decrement: each plain draw takes two cards from the count."""
    shoe = B.Shoe(1, 5, Rng(1))
    shoe.draw(None, False, False)
    assert shoe.count == 50


@pytest.mark.parametrize('left, after', [(18, 44), (19, 11)])
def test_the_deal_reshuffles_below_the_casinos_share(left, after):
    """One deck at 35%: 18 cards left is under 18.2, so the shoe is full again before four plain draws."""
    table = B.Table(1000, 5, 100, {**TOPS, 'decks': 1}, 5, Rng(1))
    table.shoe.count = left
    table.deal()
    assert table.shoe.count == after


@pytest.mark.parametrize('payout, bet, net', [(1.5, 10, 15), (1.2, 5, 6), (1.5, 5, 8)])
def test_a_natural_pays_the_casinos_payout_rounded(payout, bet, net):
    """Ace-king against 16 pays bet x payout + 0.5, truncated, on the deal."""
    table = _table([NINE, ACE, 5, KING], bet, payout=payout)
    assert table.deal() == net and table.betting and table.results[0] == B.NATURAL


@pytest.mark.parametrize('ranks, net, result', [([ACE, TEN, KING, NINE], -10, B.LOSE), ([ACE, ACE, KING, KING], 0, B.PUSH)])
def test_the_dealer_peeks_for_a_natural(ranks, net, result):
    """A dealer 21 ends the deal: a loss, or a push on the player's natural."""
    table = _table(ranks)
    assert table.deal() == net and table.results[0] == result and len(table.dealer) == 2


@pytest.mark.parametrize('pair, chips, splits', [((KING, KING), 1000, True), ((JACK, QUEEN), 1000, False),
                                                 ((KING, KING), 19, False)])
def test_a_split_needs_one_rank_and_chips_for_two_bets(pair, chips, splits):
    """Same rank (not just ten points) and chips for twice the bet."""
    table = _table([5, pair[0], 6, pair[1]], chips=chips)
    table.deal()
    assert ('split' in table.flags) == splits


def test_a_split_first_hand_of_21_pays_both_as_naturals():
    """FNV tests hand one's 21 for both split hands: both pay as naturals."""
    table = _table([5, KING, 6, KING, ACE, 3])
    table.deal()
    assert table.split() == 30 and table.results == [B.NATURAL, B.NATURAL] and len(table.dealer) == 2


def test_double_down_is_only_the_first_action():
    """A hit clears the double; doubling takes one card on twice the bet and ends the hand."""
    table = _table([5, 4, 6, 3, TWO])
    table.deal()
    table.hit()
    assert table.double() is None
    table = _table([5, 4, 6, 3, KING, 5, TWO])
    table.deal()
    assert table.double() == 20 and table.bet == 10 and len(table.hands[0]) == 3


def test_after_a_split_double_down_doubles_the_first_hand():
    """FNV doubles hand one even while the split hand is in play; the split hand plays on."""
    table = _table([5, TEN, 6, TEN, TWO, 3, NINE])
    table.deal()
    table.split()
    table.switch()
    assert table.double() is None and table.bets == [20, 10]
    assert len(table.hands[0]) == 3 and len(table.hands[1]) == 2 and 'done 1' not in table.flags


def test_surrender_gives_up_half_the_bet_before_acting():
    """Half the bet rounded up (5 loses 3); never after a hit."""
    table = _table([5, TEN, 6, 4], bet=5)
    table.deal()
    assert table.surrender() == -3
    table = _table([5, TEN, 6, 4, TWO], bet=5)
    table.deal()
    table.hit()
    assert table.surrender() is None


def test_stay_ends_both_split_hands():
    """Stay settles the whole turn: each split hand against the dealer's 20."""
    table = _table([KING, TEN, QUEEN, TEN, NINE, 3])
    table.deal()
    table.split()
    assert table.stand() == -20 and table.betting and table.results == [B.LOSE, B.LOSE]


@pytest.mark.parametrize('stays, net, cards', [(True, 10, 2), (False, 0, 4)])
def test_the_dealer_hits_17_with_any_ace_unless_the_casino_stands(stays, net, cards):
    """Ace-six stands or hits; ace-six-king (17 with an ace) hits again."""
    table = _table([ACE, TEN, 4, NINE, KING, TWO], stays=stays)
    table.deal()
    assert table.stand() == net and len(table.dealer) == cards


def test_the_dealer_stops_at_seven_cards():
    """Seven twos are 14 and the dealer stops: the player's 20 wins."""
    table = _table([TWO, TEN, TWO, TEN] + [TWO] * 6)
    table.deal()
    assert table.stand() == 10 and len(table.dealer) == 7


def test_luck_moves_the_return_both_ways():
    """Over 4000 rounds of the self-test's play: Luck 10 beats Luck 5, which beats Luck 1."""
    returns = []
    for luck in (1, 5, 10):
        table = B.Table(10 ** 6, 5, 5, TOPS, luck, Rng(7))
        returns.append(sum(B.play(table) for _ in range(4000)) / 4000 / 5)
    assert returns[0] < returns[1] - 0.2 < returns[2] - 0.4


def test_the_as3_blackjack_carries_the_models_numbers():
    """Blackjack.as's constants are the model's (the self-test checks the rest in game)."""
    source = (AS3 / 'f3nv' / 'casino' / 'Blackjack.as').read_text(encoding='utf-8')
    for name in ('ACE', 'LOSE', 'PUSH', 'WIN', 'BUST', 'NATURAL', 'SURRENDER', 'FAIR_LUCK', 'MOST_CANDIDATES',
                 'MOST_CARDS'):
        assert f'public static const {name}:int = {getattr(B, name)};' in source


def test_the_blackjack_texts_are_in_the_screens_order():
    """records.BLACKJACK_TEXTS has one text per BlackjackScreen index, and the bank and menu pass them."""
    source = (AS3 / 'f3nv' / 'casino' / 'BlackjackScreen.as').read_text(encoding='utf-8')
    indexes = [int(n) for n in re.findall(r'public static const [A-Z_]+:int = (\d+);', source)]
    assert indexes == list(range(len(R.BLACKJACK_TEXTS)))
    assert len(R.texts(EXPORT)['BlackjackTexts'][1]) == len(R.BLACKJACK_TEXTS)


def test_card_faces_follow_the_back_by_suit_then_rank():
    """Faces sit beside the back: suit and number, the twos first in rank order, so face index = suit x 13 + rank."""
    faces = R.face_textures('terminals\\NV_PlayingCards\\DeckT\\cardT_Back.dds')
    assert len(faces) == 52 and faces[0].endswith('cardT_h02.dds') and faces[ACE].endswith('cardT_h01.dds')
    assert faces[50].endswith('cardT_s13.dds') and faces[51].endswith('cardT_s01.dds')
    screen = (AS3 / 'f3nv' / 'casino' / 'BlackjackScreen.as').read_text(encoding='utf-8')
    assert f'SUITS:String = "{R.SUITS}"' in screen and '(rank + 1) % 13 + 1' in screen


@pytest.mark.parametrize('deck', 'bgtu')
def test_every_face_is_in_the_export(deck):
    """The export has all 52 faces of each deck a casino names."""
    folder = EXPORT / 'textures' / 'terminals' / 'nv_playingcards' / f'deck{deck}'
    if not folder.is_dir():
        pytest.skip('no FalloutNV.esm export')
    have = {p.name.lower() for p in folder.iterdir()}
    assert {f.lower() for f in R.face_textures(f'card{deck}_back.dds')} <= have


def test_the_bank_opens_blackjack_with_the_casinos_rules():
    """OpenBlackjack hands the menu 13 values, the casino's rules among them; the broke check covers blackjack."""
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'Var[] args = new Var[13]' in bank and '"root1.OpenBlackjack"' in bank
    assert 'StringsAsVar(BlackjackTexts)' in bank and 'playing.DealerStaysOnSoft17' in bank
    assert 'If playingGame != Slots && Game.GetPlayer()' in bank
    menu = (AS3 / 'F3NV_Casino.as').read_text(encoding='utf-8')
    assert 'public function OpenBlackjack(' in menu and 'blackjack.canLeave()' in menu


def test_the_blackjack_self_test_line_is_the_models():
    """blackjack_trace: 'blackjack <luck>', then 20 rounds a seed as ranks=net."""
    line = B.blackjack_trace((1, 2, 3), 20, 5).split(' ')
    assert line[:2] == ['blackjack', '5'] and len(line) == 62
    assert all(re.fullmatch(r'[\d.]+(/[\d.]+){1,2}=-?\d+', r) for r in line[2:])


@pytest.mark.skipif(not _captured('blackjack'), reason='no in-game self-test captured yet')
def test_the_movies_blackjack_matches_the_model():
    """Each captured blackjack line is the model's for seeds 1-3, at its Luck."""
    for line in _captured('blackjack'):
        assert line == B.blackjack_trace((1, 2, 3), 20, int(line.split(' ')[1]))
