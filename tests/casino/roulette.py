"""FNV's roulette as the menu runs it, line for line with as3/f3nv/casino/Roulette.as.

From FalloutNV.exe's roulettemenu.cpp: the 159 bet spots and their odds
(InitRouletteWheel 0x007b9c40), placing, removing and the bet steps
(HandleRouletteInput 0x007bc870, 0x007bed70, 0x007bf150), the spin (one
draw of 38 pockets, 37 being 00: 0x007bf670) and the payout (0x007bd2a0).
A spot's numbers are a BSSimpleList whose AddHead skips 0, so 0 pays only
on its own spot (the empty list's head reads 0), and the outside bets test
the result by rule, which lets 0 win red, even and the third column and 00
black, odd and the first column.

See: docs/fork/fo4_casino_plan.md#roulette-built
"""

from tests.casino.model import Rng, bet_up

#: Pockets: 0-36 and 37 for 00; the bet spots; FNV's limit of bets on one spin.
POCKETS, SPOTS, MOST_BETS = 38, 159, 10
DOUBLE_ZERO = 37
#: The wheel's pockets in order from the one FNV starts at (its strip); red sit at even places, 0 and 00 included.
WHEEL = (14, 2, 0, 28, 9, 26, 30, 11, 7, 20, 32, 17, 5, 22, 34, 15, 3, 24, 36,
         13, 1, 37, 27, 10, 25, 29, 12, 8, 19, 31, 18, 6, 21, 33, 16, 4, 23, 35)
#: The outside spots (147-158) by index: (name's text index, odds, the results that win).
OUTSIDE = {
    147: ('FIRST_DOZEN', 2, lambda r: 0 < r < 13), 150: ('SECOND_DOZEN', 2, lambda r: 12 < r < 25),
    153: ('THIRD_DOZEN', 2, lambda r: 24 < r < 37), 148: ('LOW', 1, lambda r: 0 < r < 19),
    155: ('HIGH', 1, lambda r: 18 < r < 37), 149: ('EVEN', 1, lambda r: r % 2 == 0),
    154: ('ODD', 1, lambda r: r % 2 == 1), 151: ('RED', 1, lambda r: WHEEL.index(r) % 2 == 0),
    152: ('BLACK', 1, lambda r: WHEEL.index(r) % 2 == 1), 156: ('COLUMN', 2, lambda r: (r - 1) % 3 == 0),
    157: ('COLUMN', 2, lambda r: (r - 2) % 3 == 0), 158: ('COLUMN', 2, lambda r: r % 3 == 0)}


def _row_spot(row: int, k: int) -> tuple:
    """(numbers as FNV names them, odds) of spot k (0-23) in board row `row` (0 the street edge .. 5 the 3s)."""
    base = (row + 1) // 2
    if row == 0:
        if k == 0:
            return (0, DOUBLE_ZERO, 1, 2, 3), 6
        first = (k // 2) * 3 + 1 if k % 2 else ((k - 1) // 2) * 3 + 1
        return (tuple(range(first, first + 3)), 11) if k % 2 else (tuple(range(first, first + 6)), 5)
    if row % 2:
        if k % 2:
            return (base + (k // 2) * 3,), 35
        if k:
            first = base + ((k - 1) // 2) * 3
            return (first, first + 3), 17
        return {1: ((0, 1), 17), 3: ((DOUBLE_ZERO, 0, 2), 11), 5: ((DOUBLE_ZERO, 3), 17)}[row]
    if k % 2:
        first = base + (k // 2) * 3
        return (first, first + 1), 17
    if k:
        first = base + ((k - 1) // 2) * 3
        return (first, first + 1, first + 3, first + 4), 8
    return ((1, 2, 0), 11) if row == 2 else ((2, 3, DOUBLE_ZERO), 11)


def spot(index: int) -> tuple:
    """(numbers as named, odds) of spot `index`; an outside spot names no numbers."""
    if index < 144:
        return _row_spot(index // 24, index % 24)
    if index < 147:
        return ((DOUBLE_ZERO,), 35) if index == 144 else ((DOUBLE_ZERO, 0), 17) if index == 145 else ((0,), 35)
    return (), OUTSIDE[index][1]


def wins(index: int, result: int) -> bool:
    """Whether a bet on spot `index` wins on `result`: its numbers without 0 (an empty list reads 0), or its rule."""
    if index in OUTSIDE:
        return OUTSIDE[index][2](result)
    paying = tuple(n for n in spot(index)[0] if n) or (0,)
    return result in paying


def bet_down(bet: int) -> int:
    """FNV's roulette step down: -1 to 10, then down to the step's multiple (or a step) by 5, 10, 25, 100."""
    if bet <= 10:
        return bet - 1
    for limit, step in ((40, 5), (100, 10), (500, 25)):
        if bet <= limit:
            return (bet // step) * step if bet % step else bet - step
    return (bet // 100) * 100 if bet % 100 else bet - 100


class Table:
    """One sitting at a roulette table: chips held, the bet range, the chip size to place, the spot bets."""

    def __init__(self, chips: int, low: int, high: int, rng: Rng):
        """A table with `chips` held, bets `low` to `high` (all bets on a spin)."""
        self.chips, self.low, self.high, self.rng = chips, low, high, rng
        self.bet, self.bets = low, {}
        self._fit()

    @property
    def total(self) -> int:
        """The chips on the table."""
        return sum(self.bets.values())

    def _fit(self) -> None:
        """FNV every frame: the chip size never passes the chips left."""
        if self.chips < self.bet + self.total:
            self.bet = self.chips - self.total

    def place(self, index: int) -> bool:
        """Put the chip size on spot `index`: one bet a spot, ten at most, the table's total under the max."""
        if len(self.bets) >= MOST_BETS or not 0 <= index < SPOTS or not self.bet or index in self.bets:
            return False
        if self.total >= self.high:
            return False
        self.bets[index] = self.bet
        if self.total + self.bet > self.chips:
            self.bet = self.chips - self.total
        if self.total + self.bet >= self.high:
            self.bet = self.high - self.total
        if len(self.bets) == MOST_BETS:
            self.bet = 0
        self._fit()
        return True

    def remove(self, index: int) -> bool:
        """Take the bet off spot `index`."""
        return self.bets.pop(index, None) is not None

    def bet_up(self) -> None:
        """A step up, held under the chips and the max left."""
        self.bet = min(bet_up(self.bet), self.chips - self.total, self.high - self.total)
        self._fit()

    def bet_down(self) -> None:
        """A step down, held at the min while the max leaves room for it, never below 0."""
        self.bet = bet_down(self.bet)
        if self.bet <= self.low and self.low + self.total < self.high:
            self.bet = self.low
        self.bet = max(self.bet, 0)
        self._fit()

    def spin(self) -> tuple:
        """(result, net chips): every winning bet returns (odds + 1) x its chips, less the table; None without bets."""
        if not self.bets:
            return None
        result = self.rng.below(POCKETS)
        won = sum((spot(i)[1] + 1) * amount for i, amount in self.bets.items() if wins(i, result))
        net = won - self.total
        self.chips += net
        self.bets, self.bet = {}, self.low
        self._fit()
        return result, net


def spot_masks() -> str:
    """Each spot as odds:hex of the results it wins on (bit r), comma-joined."""
    return ','.join(f'{spot(i)[1]}:{sum(1 << r for r in range(POCKETS) if wins(i, r)):x}' for i in range(SPOTS))


def roulette_trace(seeds: tuple, spins: int) -> str:
    """The line the movie's SelfTest logs: `roulette`, each seed's results, then spot_masks()."""
    out = []
    for seed in seeds:
        rng = Rng(seed)
        out += [str(rng.below(POCKETS)) for _ in range(spins)]
    return 'roulette ' + ' '.join(out) + ' ' + spot_masks()
