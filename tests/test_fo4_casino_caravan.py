"""Phase 5: FNV's Caravan on Fallout 4 (the reference model and AI, and the AS3, Papyrus and records that follow them).

See: docs/fork/fo4_casino_plan.md#caravan-built
"""

import collections
import re

import pytest

from fo4_import.casino import records as R
from tests.casino import caravan as C
from tests.casino import caravan_ai as AI
from tests.casino.model import Rng
from tests.test_fo4_casino import AS3, EXPORT, STATIC, _captured, _source_records

HEARTS, SPADES, DIAMONDS, CLUBS = 1, 2, 3, 4


def _card(value: int, suit: int = HEARTS) -> tuple:
    """A (value, suit, id) card; the id is unused by the rules."""
    return value, suit, 0


def _board(**lanes) -> list:
    """Six empty caravans, `lane<k>=[cell, ...]` filled in (a cell a list of cards)."""
    board = [[[] for _ in range(C.ROWS)] for _ in range(C.LANES)]
    for name, cells in lanes.items():
        for row, cell in enumerate(cells):
            board[int(name[4:])][row] = list(cell)
    return board


def _values(lane: list) -> list:
    """A caravan's base card values, front to back."""
    return [cell[0][0] for cell in lane if cell]


@pytest.mark.parametrize('total, band', [(20, -1), (21, 0), (26, 0), (27, 1), (0, -1)])
def test_a_caravan_sells_from_21_to_26(total, band):
    """band: under 21, 21-26 sold, over 26 bust."""
    assert C.band(total) == band


def test_kings_double_their_card_once_each():
    """A 5 with two Kings is 20; a Queen or Jack on it adds nothing."""
    assert C.row_value([_card(5), _card(C.KING), _card(C.KING)]) == 20
    assert C.row_value([_card(5), _card(C.QUEEN)]) == 5


def test_a_caravans_way_and_suit_follow_its_last_card_and_queens():
    """Empty: suit 5, no way; one card: its suit (a Queen's on it); more: up or down, each Queen turns it."""
    assert C.lane_stats([[]] * 7) == (0, C.JOKER_SUIT, 0)
    assert C.lane_stats([[_card(4), _card(C.QUEEN, SPADES)]] + [[]] * 6)[:2] == (0, SPADES)
    up = [[_card(4)], [_card(9, CLUBS)]] + [[]] * 5
    assert C.lane_stats(up) == (1, CLUBS, 13)
    up[1].append(_card(C.QUEEN, DIAMONDS))
    assert C.lane_stats(up)[:2] == (-1, DIAMONDS)


def test_the_opening_takes_a_number_on_an_empty_caravan():
    """At the opening any empty cell takes a number; no face card."""
    board = _board()
    assert C.can_place(board, True, 0, 1, 0, _card(7))
    assert not C.can_place(board, True, 0, 1, 0, _card(C.KING))


def test_numbers_go_on_their_own_sides_next_row_only():
    """Numbers on their own side (0-2, 3-5), never past an empty row."""
    board = _board(lane0=[[_card(3)]])
    assert C.can_place(board, False, 0, 0, 1, _card(7)) and not C.can_place(board, False, 0, 0, 2, _card(7))
    assert not C.can_place(board, False, 0, 3, 0, _card(7)) and not C.can_place(board, False, 1, 0, 0, _card(7))


def test_a_number_never_repeats_the_last_and_keeps_the_way_unless_suited():
    """After 3 then 7 (up): 7 refused, 5 refused unless it is the 7's suit, 9 fine."""
    board = _board(lane0=[[_card(3)], [_card(7, CLUBS)]])
    assert not C.can_place(board, False, 0, 0, 2, _card(7, CLUBS))
    assert not C.can_place(board, False, 0, 0, 2, _card(5, HEARTS))
    assert C.can_place(board, False, 0, 0, 2, _card(5, CLUBS)) and C.can_place(board, False, 0, 0, 2, _card(9))


def test_face_cards_go_on_any_card_with_room_and_a_queen_on_the_last():
    """Any side's card with fewer than 3 faces; a Queen only on the caravan's last card."""
    board = _board(lane4=[[_card(3), _card(C.KING), _card(C.KING), _card(C.KING)], [_card(8)]])
    assert not C.can_place(board, False, 0, 4, 0, _card(C.JACK))
    assert C.can_place(board, False, 0, 4, 1, _card(C.JACK))
    board = _board(lane4=[[_card(3)], [_card(8)]])
    assert not C.can_place(board, False, 0, 4, 0, _card(C.QUEEN)) and C.can_place(board, False, 0, 4, 1, _card(C.QUEEN))


def test_a_jack_cuts_its_card_and_the_rest_move_up():
    """The Jack's card goes with its faces; later cards move up."""
    lane = _board(lane0=[[_card(3)], [_card(8), _card(C.KING)], [_card(10)]])[0]
    C.cut(lane, 1)
    assert _values(lane) == [3, 10] and len(lane) == C.ROWS


def test_a_joker_takes_every_other_card_of_its_value_on_both_sides():
    """A Joker on a 5 takes the other 5s, both sides; it stays on its own card."""
    board = _board(lane0=[[_card(5)], [_card(8)]], lane3=[[_card(5, SPADES), _card(C.JOKER, 5)]],
                   lane4=[[_card(2)], [_card(5, CLUBS)]])
    C.joker(board, 3, 0)
    assert _values(board[0]) == [8] and _values(board[3]) == [5] and _values(board[4]) == [2]


def test_a_joker_on_an_ace_takes_every_other_card_of_its_suit():
    """On an ace the Joker takes by suit."""
    board = _board(lane0=[[_card(4, SPADES)], [_card(9, HEARTS)]], lane5=[[_card(1, SPADES), _card(C.JOKER, 5)]])
    C.joker(board, 5, 0)
    assert _values(board[0]) == [9] and _values(board[5]) == [1]


def test_a_joker_with_three_targets_in_a_caravan_misses_the_third_as_fnv():
    """FNV corrects later rows once, not twice: of three 5s at rows 0, 2 and 4, the last survives."""
    board = _board(lane0=[[_card(5)], [_card(8)], [_card(5, DIAMONDS)], [_card(9)], [_card(5, SPADES)]],
                   lane3=[[_card(5, CLUBS), _card(C.JOKER, 5)]])
    C.joker(board, 3, 0)
    assert _values(board[0]) == [8, 9, 5]


def test_the_result_needs_all_three_pairs_or_an_empty_side():
    """Two sold pairs of three decide nothing; three decide by majority; a tie at 21-26 waits; no cards loses."""
    full = [[_card(1)]]
    board = _board(lane0=[[_card(10)], [_card(9)], [_card(3)]], lane5=[[_card(10)], [_card(2)]],
                   lane1=[[_card(10)], [_card(6)], [_card(7)]], lane4=[[_card(10)], [_card(9)], [_card(5)]],
                   lane2=[[_card(10)], [_card(9)], [_card(4)]], lane3=[[_card(10)], [_card(9)], [_card(4)]])
    assert C.outcome(board, [full, full], [full, full]) is None
    board[2] = _board(lane0=[[_card(10)], [_card(8)], [_card(6)]])[0]
    assert C.outcome(board, [full, full], [full, full]) == C.WON
    assert C.outcome(_board(), [[], []], [[], full]) == C.LOST
    assert C.outcome(_board(), [full, []], [full, []]) == C.WON


def _game(seed: int = 1, mode: int = 3) -> C.Game:
    """A game on two standard decks."""
    return C.Game(C.standard_deck(0), C.standard_deck(54), mode, Rng(seed))


def test_the_deal_gives_eight_each_and_the_opponent_moves_first():
    """Eight cards each, the decks 46 each, and the player waits for the opponent's first card."""
    game = _game()
    assert [len(h) for h in game.hands] == [8, 8] and [len(d) for d in game.decks] == [46, 46] and game.waiting
    game.opponent()
    assert game.lanes[5][0] or len(game.hands[1]) == 8


def test_the_opening_fills_the_caravans_in_order_and_a_discard_is_free():
    """The player's numbers open caravans 0, 1, 2 whatever is clicked; a discard keeps the turn; the opening ends
    with all six caravans started."""
    game = _game(4)
    while not game.result and game.opening:
        game.opponent()
        if not game.opening:
            break
        number = next((i for i, card in enumerate(game.hands[0]) if card[0] <= 10), None)
        if number is None:
            assert game.discard(0) and not game.waiting
            continue
        started = [bool(game.lanes[k][0]) for k in range(3)]
        assert game.play(number, 2, 5)
        assert [bool(game.lanes[k][0]) for k in range(3)].count(True) == started.count(True) + 1
        assert not game.lanes[1][0] or game.lanes[0][0]
    assert not game.opening and all(game.lanes[k][0] for k in range(6))


def test_a_caravan_is_discarded_only_after_the_opening():
    """Discard Caravan is refused at the opening, then clears one of the player's caravans."""
    game = _game(2)
    game.opponent()
    assert not game.discard_lane(0)
    while (game.opening or game.waiting) and not game.result:
        if game.waiting:
            game.opponent()
        else:
            game.auto_player()
    assert not game.result and game.discard_lane(0) and not game.lanes[0][0] and game.waiting


@pytest.mark.parametrize('ranks, mode, move', [
    ([12, 13, 14, 15, 12, 13, 2, 3], 0, (AI.DISCARD, 5)), ([12, 13, 14, 2, 5, 13, 7, 3], 0, (AI.OPEN, 7)),
    ([2, 9, 1, 7, 12, 13, 4, 3], 1, (AI.OPEN, 0)), ([7, 9, 1, 12, 6, 13, 4, 8], 2, (AI.OPEN, 0)),
    ([2, 9, 7, 4, 12, 13, 4, 3], 3, (AI.OPEN, 2)), ([12, 14, 13, 15, 12, 13, 2, 3], 3, (AI.DISCARD, 3))])
def test_the_ai_opens_by_its_mode(ranks, mode, move):
    """Mode by mode: a face discard, else the last, first or nearest-6 card."""
    assert AI.opening_move(ranks, mode) == move


def test_the_ai_discards_face_cards_in_fnvs_order():
    """The first Joker; else a Jack gives way, a King to a Queen."""
    assert AI.face_pick([12, 14, 13, 2]) == (AI.DISCARD, 2) and AI.face_pick([13, 12, 14]) == (AI.DISCARD, 0)
    assert AI.face_pick([12, 15, 13]) == (AI.DISCARD, 1) and AI.face_pick([2, 3]) is None


def test_the_ai_sells_a_caravan_when_it_can():
    """At 18 with a 3 in hand, the 3 on the next row scores 21, above every other move."""
    board = _board(lane3=[[_card(10)], [_card(8)]], lane4=[[_card(4)]], lane5=[[_card(2)]],
                   lane0=[[_card(5)]], lane1=[[_card(6)]], lane2=[[_card(7)]])
    hand = [_card(2, SPADES), _card(3, SPADES), _card(C.QUEEN)]
    choice = AI.decide(board, hand, [], 3, False)
    assert (choice.action, choice.lane, choice.row, choice.card) == (AI.PLACE, 3, 2, 1)


def test_with_no_move_the_ai_discards_its_highest_card():
    """Nothing scores: the first highest card is discarded (its score its place, as FNV)."""
    board = _board(lane3=[[_card(10)], [_card(9)], [_card(4)]], lane4=[[_card(10)], [_card(9)], [_card(4)]],
                   lane5=[[_card(10)], [_card(9)], [_card(4)]])
    choice = AI.decide(board, [_card(C.QUEEN), _card(C.QUEEN, SPADES)], [], 0, False)
    assert (choice.action, choice.card, choice.score) == (AI.DISCARD, 0, 0)


def test_fnvs_sort_puts_scores_first_and_ties_in_its_own_order():
    """The runtime qsort orders by score, highest first; three equal scores come out middle, last, first."""
    rng = Rng(9)
    items = [AI.Choice() for _ in range(50)]
    for i, item in enumerate(items):
        item.score, item.card = rng.below(20), i
    AI.msvc_qsort(items, AI.by_score)
    assert [i.score for i in items] == sorted((i.score for i in items), reverse=True)
    ties = [AI.Choice() for _ in range(3)]
    for i, item in enumerate(ties):
        item.card = i
    AI.msvc_qsort(ties, AI.by_score)
    assert [t.card for t in ties] == [1, 2, 0]


def test_games_finish_and_both_sides_win_at_every_mode():
    """100 AI-against-AI games a mode end, each side winning some."""
    for mode in range(4):
        results = collections.Counter(C.autoplay(_game(seed, mode)) for seed in range(1, 101))
        assert results[C.WON] > 20 and results[C.LOST] > 20


def test_the_bet_matches_raises_to_the_cap_and_risks_the_smaller_bet():
    """Ante: funds x share truncated; Barter lifts the cap; Auto-Match; a raise past the ante is matched to the
    cap; the stake is the smaller bet."""
    wager = C.Wager(500, 999, 0.25, 40)
    assert (wager.ante, wager.cap) == (249, 349) and not wager.ready()
    wager.match()
    assert wager.bet == 249 and wager.ready()
    wager.raise_by(200)
    assert (wager.bet, wager.ante, wager.stake()) == (449, 349, 349)
    assert C.Wager(10, 3, 0.25, 0).ready() and C.raise_cap(1000, 0.5, 100) == 1000


@pytest.mark.parametrize('room, step', [(5, 1), (100, 5), (300, 15 // 10 * 10), (1000, 50)])
def test_a_raise_steps_by_fnvs_small_quantity_step(room, step):
    """A twentieth of the room (at least 1), whole tens above 10."""
    assert C.raise_step(room) == step


def test_the_loser_pays_in_caravan_money_first_then_caps():
    """Stacks in turn, as many as fit, then caps for the rest."""
    assert C.payout([(40, 3), (8, 1), (100, 1)], 130) == ([3, 1, 0], 2)
    assert C.payout([(40, 1)], 30) == ([0], 30)


def test_randomize_picks_30_up_to_one_under_the_collection():
    """FNV's Randomize: a random size from 30 up to (not with) every card; 30 or fewer cards give them all."""
    rng = Rng(3)
    sizes = {len(C.randomize(60, rng)) for _ in range(200)}
    assert min(sizes) == 30 and max(sizes) == 59
    assert C.randomize(30, rng) == list(range(30)) and len(set(C.randomize(100, rng))) >= 30


def test_the_as3_caravan_carries_the_models_numbers():
    """Caravan.as's and CaravanAi.as's constants are the model's (the self-test checks the rest in game)."""
    rules = (AS3 / 'f3nv' / 'casino' / 'Caravan.as').read_text(encoding='utf-8')
    for name in ('ACE', 'JACK', 'QUEEN', 'KING', 'JOKER', 'JOKER_SUIT', 'LANES', 'ROWS', 'HAND', 'LOW', 'HIGH',
                 'MOST_FACES', 'SMALLEST_DECK', 'LARGEST_DECK', 'WON', 'LOST'):
        assert f'public static const {name}:int = {getattr(C, name)};' in rules
    ai = (AS3 / 'f3nv' / 'casino' / 'CaravanAi.as').read_text(encoding='utf-8')
    for name in ('PLACE', 'CUT', 'JOKER_PLAY', 'OPEN', 'DISCARD_LANE', 'DISCARD', 'ATTACK', 'SHORT_SORT'):
        assert f'public static const {name}:int = {getattr(AI, name)};' in ai


def test_the_caravan_texts_are_in_the_screens_order():
    """records.CARAVAN_TEXTS has one text per CaravanScreen index; FalloutNV's settings fill them."""
    source = (AS3 / 'f3nv' / 'casino' / 'CaravanScreen.as').read_text(encoding='utf-8')
    indexes = [int(n) for n in re.findall(r'public static const [A-Z_]+:int = (\d+);', source)]
    assert indexes[:len(R.CARAVAN_TEXTS)] == list(range(len(R.CARAVAN_TEXTS)))
    texts = R.texts(EXPORT)['CaravanTexts'][1]
    assert len(texts) == len(R.CARAVAN_TEXTS) and texts[R.CARAVAN_TEXTS.index(('sNo', 'No'))] == 'No'


def test_the_card_table_is_each_cards_suit_value_and_textures():
    """card_entry: "suit,value,face,back" from the two INTVs and TX00/TX01; card_table: 30 to a string."""
    subs = [(b'INTV', (2).to_bytes(4, 'little')), (b'INTV', (13).to_bytes(4, 'little')),
            (b'TX00', b'terminals\\NV_PlayingCards\\DeckL\\cardL_s12.dds\0'),
            (b'TX01', b'terminals\\NV_PlayingCards\\DeckL\\cardL_Back.dds\0')]
    entry = R.card_entry(subs)
    assert entry.startswith('2,13,') and entry.endswith(',fnv/terminals/nv_playingcards/deckl/cardl_back.dds') and '\\' not in entry
    table = R.card_table([str(i) for i in range(65)])
    assert len(table) == 3 and table[2] == '60|61|62|63|64'


def test_every_card_has_its_entry_and_its_textures_are_in_the_export():
    """FalloutNV's 270 cards: 9 table strings, 20 of each value and 10 Jokers, every face and back staged."""
    entries = [R.card_entry(subs) for _, subs in sorted(_source_records()[b'CCRD'])]
    values = collections.Counter(int(entry.split(',')[1]) for entry in entries)
    assert len(R.card_table(entries)) == 9 and values[C.JOKER] == 10 and values[C.ACE] == values[C.KING] == 20
    textures = {R.texture_source(t) for _, subs in _source_records()[b'CCRD'] for t in R.card_textures(subs)}
    assert all(R.export_file(EXPORT, t.replace(chr(92), '/')).is_file() for t in textures)


def test_the_bank_hands_the_menu_caravan_and_pays_the_loser():
    """OpenCaravan opens the menu (no more "not built"); OpenCaravanMenu hands it 13 values; the deck chunks and
    the result come back as events; Pay moves money then caps."""
    bank = (STATIC / 'F3NV_Casino.psc').read_text(encoding='utf-8')
    assert 'NotBuilt' not in bank and '"root1.OpenCaravan"' in bank and 'Var[] args = new Var[13]' in bank
    for event, handler in (('F3NV_CaravanDeck', 'OnCaravanDeck'), ('F3NV_CaravanResult', 'OnCaravanResult')):
        assert f'RegisterForExternalEvent("{event}", "{handler}")' in bank
    menu = (AS3 / 'F3NV_Casino.as').read_text(encoding='utf-8')
    signature = re.search(r'public function OpenCaravan\(([^)]*)\)', menu).group(1)
    assert signature.count(':') == 13 and 'Caravan.trace(seeds, 3)' in menu
    screen = (AS3 / 'f3nv' / 'casino' / 'CaravanScreen.as').read_text(encoding='utf-8')
    assert 'send("F3NV_CaravanDeck", chunk, bits)' in screen and 'send("F3NV_CaravanResult", won, stake)' in screen


def test_the_caravan_self_test_line_is_the_models():
    """caravan_trace: 'caravan <mode>', then W or L:moves:points per seed."""
    line = C.caravan_trace((1, 2, 3), 3).split(' ')
    assert line[:2] == ['caravan', '3'] and len(line) == 5
    assert all(re.fullmatch(r'[WL]:\d+:\d+(\.\d+){5}', game) for game in line[2:])


@pytest.mark.skipif(not _captured('caravan'), reason='no in-game self-test captured yet')
def test_the_movies_caravan_matches_the_model():
    """Each captured caravan line is the model's for seeds 1-3, at its mode."""
    for line in _captured('caravan'):
        assert line == C.caravan_trace((1, 2, 3), int(line.split(' ')[1]))
