"""FNV's Caravan as the menu runs it, line for line with as3/f3nv/casino/Caravan.as.

From FalloutNV.exe's caravanmenu.cpp: the placement rule (CanPlaceCard 0x0074f6c0), a caravan's value, suit and
direction (UpdateHandStats 0x0074ee70), the result (CheckCaravanResult 0x00752e20), the deal and draws (0x0073ea90),
the turn's states (0x00741500) with the Jack and the Joker, the deck builder's Randomize (0x00747d30), and the
ante, raise cap and payout (0x0073d020, 0x0074a090, 0x0074cc70). The AI is caravan_ai.py.

See: docs/fork/fo4_casino_plan.md#caravan-built
"""

from tests.casino import caravan_ai as AI
from tests.casino.model import Rng

#: Card values (CCRD's second INTV): 1 the ace to 10, then Jack, Queen, King, Joker; the Joker's suit.
ACE, JACK, QUEEN, KING, JOKER, JOKER_SUIT = 1, 12, 13, 14, 15, 5
#: Six caravans (0-2 the player's, 3-5 the opponent's, k facing 5 - k) of seven cards; a hand of eight.
LANES, ROWS, HAND = 6, 7, 8
#: A sold caravan; a hand's most face cards on one card; FNV's smallest and largest deck.
LOW, HIGH, MOST_FACES, SMALLEST_DECK, LARGEST_DECK = 21, 26, 3, 30, 108
#: Results (FNV's flag 0x400): the player won or lost.
WON, LOST = 1, 2


def band(total: int) -> int:
    """-1 under 21, 1 over 26, 0 for a caravan that sells (0x00752df0)."""
    return -1 if total < LOW else 1 if total > HIGH else 0


def row_value(cell: list) -> int:
    """A card's points with its face cards: its value doubled once per King (0x0074f600)."""
    value = cell[0][0] if cell else 0
    for card in cell[1:]:
        value = value * 2 if card[0] == KING else value
    return value


def laid(lane: list) -> int:
    """How many cards a caravan has: its cells up to the first empty one."""
    return next((r for r, cell in enumerate(lane) if not cell), ROWS)


def lane_total(lane: list) -> int:
    """A caravan's points."""
    return sum(row_value(cell) for cell in lane[:laid(lane)])


def lane_stats(lane: list) -> tuple:
    """(direction, suit, total): no cards suit 5 and no direction; one card its suit (a Queen's on it); more, up if
    the last card is higher than the one before, the last card's suit, each Queen on it its suit and turns it."""
    count, total = laid(lane), lane_total(lane)
    if count == 0:
        return 0, JOKER_SUIT, total
    last = lane[count - 1]
    direction = 0 if count == 1 else 1 if last[0][0] > lane[count - 2][0][0] else -1
    suit = last[0][1]
    for card in last[1:]:
        if card[0] == QUEEN:
            suit, direction = card[1], -direction
    return direction, suit, total


def can_place(lanes: list, opening: bool, side: int, lane: int, row: int, card: tuple) -> bool:
    """FNV's placement rule for `side` (1 the opponent): at the opening a number on an empty cell; a face card on a
    card with under 3 faces (a Queen on the last card only); a number on its own side's next cell, never the last
    card's value, going the caravan's way unless it matches its suit."""
    if not (0 <= lane < LANES and 0 <= row < ROWS):
        return False
    value, cell = card[0], lanes[lane][row]
    if opening:
        return not cell and value <= 10
    if value > 10:
        return 1 <= len(cell) <= MOST_FACES and not (value == QUEEN and row < ROWS - 1 and lanes[lane][row + 1])
    if cell or (side == 1 and lane < 3) or (side == 0 and lane > 2):
        return False
    return row == 0 or _follows(lanes[lane], row, card)


def _follows(lane: list, row: int, card: tuple) -> bool:
    """A number after the card before it: not its value, and the caravan's way unless it is its suit."""
    if not lane[row - 1]:
        return False
    before = lane[row - 1][0][0]
    direction, suit, _ = lane_stats(lane)
    if before == card[0]:
        return False
    if direction == 1 and before >= card[0] and suit != card[1]:
        return False
    return not (direction == -1 and before <= card[0] and suit != card[1])


def outcome(lanes: list, hands: list, decks: list) -> 'int | None':
    """WON or LOST when each pair is decided (a sold caravan beats an unsold or lower one; equal ones wait), or a side
    has no cards left (the player's checked first); None while the game goes on."""
    totals = [lane_total(lane) for lane in lanes]
    mine = theirs = 0
    for pair in range(3):
        own, other = totals[pair], totals[LANES - 1 - pair]
        mine += band(own) == 0 and (band(other) != 0 or own > other)
        theirs += band(other) == 0 and (band(own) != 0 or own < other)
    if mine + theirs == 3:
        return WON if mine > theirs else LOST
    if not hands[0] and not decks[0]:
        return LOST
    return WON if not hands[1] and not decks[1] else None


def cut(lane: list, row: int) -> None:
    """A Jack's cut: the card at `row` and its faces go; later cards move up."""
    del lane[row]
    lane.append([])


def joker_targets(lanes: list, lane: int, row: int) -> list:
    """Per caravan, the rows a Joker on (lane, row) takes: on an ace every other card of its suit, else every other
    card of its value, on both sides (state 13)."""
    value, suit = lanes[lane][row][0][0], lanes[lane][row][0][1]
    out = []
    for i, cells in enumerate(lanes):
        hits = []
        for j, cell in enumerate(cells[:laid(cells)]):
            matched = cell[0][1] == suit if value == ACE else cell[0][0] == value
            if matched and (i, j) != (lane, row):
                hits.append(j)
        out.append(hits)
    return out


def joker(lanes: list, lane: int, row: int) -> None:
    """Take the Joker's targets as FNV does (states 17-19): each caravan's rows in turn, every later row moving up
    over it with the last row left in place, and only one step's correction for the rows already gone."""
    for cells, hits in zip(lanes, joker_targets(lanes, lane, row)):
        at = hits[0] if hits else 0
        while hits:
            cells[at:ROWS - 1] = [list(cell) for cell in cells[at + 1:ROWS]]
            hits.pop(0)
            at = hits[0] - (hits[0] > at) if hits else at


class Game:
    """One Caravan game: each side's deck and hand, the six caravans; the opponent (mode 0-3) moves first."""

    def __init__(self, player_deck: list, opponent_deck: list, mode: int, rng: Rng):
        """Deal eight cards each, one each in turn from a random place (the last card takes its place)."""
        self.mode, self.rng = mode, rng
        self.decks, self.hands = [list(player_deck), list(opponent_deck)], [[], []]
        self.lanes = [[[] for _ in range(ROWS)] for _ in range(LANES)]
        for _ in range(HAND):
            for side in (0, 1):
                deck = self.decks[side]
                at = rng.below(len(deck))
                self.hands[side].append(deck[at])
                deck[at] = deck[-1]
                deck.pop()
        self.picks = [self._pick(0), self._pick(1)]
        self.opening, self.result, self.waiting, self.moves = True, None, True, 0

    def _pick(self, side: int) -> int:
        """The next card `side` draws: a random place in its deck, -1 when empty."""
        return self.rng.below(len(self.decks[side])) if self.decks[side] else -1

    def _draw(self, side: int) -> None:
        """Draw `side`'s picked card to the end of its hand."""
        if self.picks[side] != -1:
            self.hands[side].append(self.decks[side].pop(self.picks[side]))
            self.picks[side] = self._pick(side)

    def opening_lane(self, side: int) -> int:
        """An opening card's caravan: the first empty from 0, or from 5 down."""
        order = (0, 1, 2) if side == 0 else (5, 4, 3)
        return next((lane for lane in order if not self.lanes[lane][0]), order[-1])

    def legal(self, index: int, lane: int, row: int) -> bool:
        """Whether the player may play hand card `index` at (lane, row) now."""
        if self.result or self.waiting or not 0 <= index < len(self.hands[0]):
            return False
        if self.opening:
            lane, row = self.opening_lane(0), 0
        return can_place(self.lanes, self.opening, 0, lane, row, self.hands[0][index])

    def play(self, index: int, lane: int, row: int) -> bool:
        """Play hand card `index` at (lane, row) (at the opening, on the next caravan); whether it was legal."""
        if not self.legal(index, lane, row):
            return False
        if self.opening:
            self.lanes[self.opening_lane(0)][0].append(self.hands[0].pop(index))
        else:
            self._place(0, index, lane, row)
        self._ended(0, True)
        return True

    def discard(self, index: int) -> bool:
        """Discard hand card `index` for a new one (needs a card to draw); free at the opening."""
        if self.result or self.waiting or not self.decks[0] or not 0 <= index < len(self.hands[0]):
            return False
        self.hands[0].pop(index)
        self._draw(0)
        self._ended(0, not self.opening)
        return True

    def discard_lane(self, lane: int) -> bool:
        """Clear one of the player's caravans (not at the opening; one of them must have cards)."""
        own = any(self.lanes[k][0] for k in range(3))
        if self.result or self.waiting or self.opening or not own or not 0 <= lane < 3:
            return False
        self.lanes[lane] = [[] for _ in range(ROWS)]
        self._ended(0, True)
        return True

    def forfeit(self) -> None:
        """Give up: a loss (FNV's forfeit, flag 0x20000)."""
        self.result = self.result or LOST

    def _place(self, side: int, index: int, lane: int, row: int) -> None:
        """Play a card from the hand (the hand draws first), then its effect: a Jack cuts, a Joker takes its targets."""
        card = self.hands[side].pop(index)
        self._draw(side)
        self.lanes[lane][row].append(card)
        if card[0] == JACK:
            cut(self.lanes[lane], row)
        elif card[0] == JOKER:
            joker(self.lanes, lane, row)

    def _ended(self, side: int, passes: bool) -> None:
        """After an action: the opening ends once every caravan has a card, the result is checked, the turn passes."""
        self.moves += 1
        if self.opening and all(self.lanes[lane][0] for lane in range(LANES)):
            self.opening = False
        self.result = self.result or outcome(self.lanes, self.hands, self.decks)
        if passes and not self.result:
            self.waiting = side == 0

    def opponent(self) -> None:
        """The opponent's move (caravan_ai.decide), then the player's turn."""
        if self.waiting and not self.result:
            self.auto(1)
            self.waiting = False
            self._ended(1, False)

    def auto_player(self) -> None:
        """The player's move by the AI's rules (simulations, the self-test); an opening discard is free."""
        if not self.waiting and not self.result:
            opening = self.opening
            action = self.auto(0)
            self._ended(0, not (opening and action == AI.DISCARD))

    def auto(self, side: int) -> int:
        """Make `side`'s move with the AI's rules (the player's side seen mirrored: caravan k as 5 - k); its action."""
        view = self.lanes if side == 1 else self.lanes[::-1]
        choice = AI.decide(view, self.hands[side], self.decks[side], self.mode, self.opening)
        lane = choice.lane if side == 1 else LANES - 1 - choice.lane
        if choice.action == AI.DISCARD:
            self.hands[side].pop(choice.card)
            self._draw(side)
        elif self.opening:
            self.lanes[self.opening_lane(side)][0].append(self.hands[side].pop(choice.card))
        elif choice.action == AI.DISCARD_LANE:
            self.lanes[lane] = [[] for _ in range(ROWS)]
        else:
            self._place(side, choice.card, lane, choice.row)
        return choice.action


def autoplay(game: Game, most: int = 400) -> int:
    """Play a game out, the player's side by the AI's rules at the same mode; WON or LOST (LOST past `most` moves)."""
    while not game.result and game.moves < most:
        if game.waiting:
            game.opponent()
        else:
            game.auto_player()
    return game.result or LOST


def standard_deck(first_id: int) -> list:
    """54 (value, suit, id) cards: ace to king in four suits, two Jokers."""
    kinds = [(v, s) for s in range(1, 5) for v in list(range(1, 11)) + [JACK, QUEEN, KING]] + [(JOKER, JOKER_SUIT)] * 2
    return [(v, s, first_id + i) for i, (v, s) in enumerate(kinds)]


def game_text(game: Game, result: int) -> str:
    """A game as the self-test logs it: W or L, the moves, the six caravans' points."""
    totals = '.'.join(str(lane_total(lane)) for lane in game.lanes)
    return f"{'W' if result == WON else 'L'}:{game.moves}:{totals}"


def caravan_trace(seeds: tuple, mode: int) -> str:
    """The line the movie's SelfTest logs: `caravan <mode>`, then a game per seed (two standard decks)."""
    games = []
    for seed in seeds:
        game = Game(standard_deck(0), standard_deck(54), mode, Rng(seed))
        games.append(game_text(game, autoplay(game)))
    return f'caravan {mode} ' + ' '.join(games)


def randomize(total: int, rng: Rng) -> list:
    """FNV's Randomize: a deck of 30 cards, or a random size from 30 to one under the collection; the chosen
    collection places, ascending (each a random pick of those left)."""
    size = SMALLEST_DECK if total <= SMALLEST_DECK else SMALLEST_DECK + rng.below(total - SMALLEST_DECK)
    left, chosen = list(range(total)), []
    for _ in range(min(size, total)):
        chosen.append(left.pop(rng.below(len(left))))
    return sorted(chosen)


def ante(funds: int, share: float) -> int:
    """The opponent's opening bet: its funds x the ante share, truncated (0x0073d020)."""
    return int(funds * share)


def raise_cap(funds: int, share: float, barter: int) -> int:
    """The opponent's most: funds x share x (1 + Barter / 100), truncated."""
    return min(int(funds * share + funds * share * (barter / 100.0)), funds)


def raise_step(room: int) -> int:
    """FNV's quantity step: a twentieth (at least 1), whole tens above 10."""
    step = max(room // 20, 1)
    return step // 10 * 10 if step > 10 else step


class Wager:
    """The bet screen: the player's bet, the opponent's (its ante, matching raises to its cap), the player's funds."""

    def __init__(self, funds: int, opponent_funds: int, share: float, barter: int):
        """The player's bet starts at 0, the opponent's at its ante."""
        self.funds, self.bet = funds, 0
        self.ante, self.cap = ante(opponent_funds, share), raise_cap(opponent_funds, share, barter)

    def match(self) -> None:
        """Auto-Match: the opponent's bet, or all the player's funds."""
        self.bet = min(self.ante, self.funds)

    def raise_by(self, amount: int) -> None:
        """Raise by `amount` (up to the funds left); the opponent matches up to its cap."""
        self.bet += max(0, min(amount, self.funds - self.bet))
        if self.bet > self.ante:
            self.ante = min(self.cap, self.bet)

    def ready(self) -> bool:
        """Whether the game can start: a bet, or nothing to match."""
        return self.bet > 0 or self.ante == 0

    def stake(self) -> int:
        """What each side risks: the smaller bet (the pot is twice it)."""
        return min(self.bet, self.ante)


def payout(stacks: list, stake: int) -> tuple:
    """The loser's payment of `stake`: from its Caravan money stacks [(value, count)] in order, each as many as fit
    in what is left, then caps for the rest; ([count moved per stack], caps)."""
    left, moved = stake, []
    for value, count in stacks:
        n = count if value * count <= left else left // value
        moved.append(n)
        left -= n * value
    return moved, left
