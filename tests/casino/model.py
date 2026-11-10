"""The casino games' rules as the menu runs them, line for line with as3/f3nv/casino/*.as: the shared RNG and slots.

Slots follow FalloutNV.exe (slotmachinemenu.cpp): a reel is FNV's 28 stops
of (symbol, blank) pairs, each kind repeated by its CSNO stop count (InitReels
0x007c16b0); a value is 2 x symbol (12 the wild), odd for a blank. Each reel
lands on one of the first 2 x kinds stops (0x007c56e0). The result class is
0x007c5760's; Luck nudges the reels (AdjustReels 0x007c58f0), and a three
of a kind pays by symbol, two wilds x5, one wild x2 (0x007c2c70).

See: docs/fork/fo4_casino_plan.md#slots-built
"""

#: The RNG's seed when 0 is given (xorshift32 never leaves 0).
SEED_ZERO = 0x2545F491
MASK = 0xFFFFFFFF
#: The wild's value and the blank after it; a three of a kind's multiplier by its value (FNV's switch).
WILD, WILD_BLANK = 12, 13
THREE_PAYS = {12: 10, 0: 10, 2: 20, 4: 30, 6: 40, 8: 60, 10: 100}
TWO_WILDS_PAY, ONE_WILD_PAY = 5, 2
#: Result classes (0x007c5760): nothing, a pair, one wild, two wilds, three of a kind.
NOTHING, PAIR, ONE_WILD, TWO_WILDS, THREE = 0, 1, 4, 5, 6
#: Luck that changes nothing; each point away is 10% chance of a nudge.
FAIR_LUCK = 5


class Rng:
    """xorshift32: the same numbers in Python and AS3 (shifts and xor on 32-bit unsigned)."""

    def __init__(self, seed: int):
        self.state = seed & MASK or SEED_ZERO

    def next(self) -> int:
        """The next 32-bit number."""
        x = self.state
        x ^= (x << 13) & MASK
        x ^= x >> 17
        x ^= (x << 5) & MASK
        self.state = x
        return x

    def below(self, n: int) -> int:
        """A number from 0 to n - 1."""
        return self.next() % n


def reel(stops: list) -> list:
    """FNV's reel: round after round, each kind with stops left adds its (symbol, blank) values; 28 stops."""
    left, out = list(stops), []
    while any(left) and len(out) < 28:
        for kind, count in enumerate(left):
            if count:
                out += [kind * 2, kind * 2 + 1]
                left[kind] -= 1
    return out


def classify(values: list) -> int:
    """The result class of three reel values."""
    wilds = values.count(WILD)
    if values[0] == values[1] == values[2] and values[1] % 2 == 0:
        return THREE
    if wilds in (1, 2):
        return ONE_WILD if wilds == 1 else TWO_WILDS
    pairs = ((values[1], values[2]), (values[0], values[2]), (values[1], values[0]))
    return PAIR if any(a == b and a % 2 == 0 for a, b in pairs) else NOTHING


def pays(values: list) -> int:
    """The multiple of the bet a spin wins; 0 when it loses."""
    kind = classify(values)
    if kind == THREE:
        return THREE_PAYS.get(values[0], 0)
    return {TWO_WILDS: TWO_WILDS_PAY, ONE_WILD: ONE_WILD_PAY}.get(kind, 0)


class Slots:
    """One casino's machine: its reel, the player's Luck, the shared RNG."""

    def __init__(self, stops: list, luck: int, rng: Rng):
        self.stops, self.luck, self.rng = reel(stops), luck, rng
        self.kinds = sum(1 for s in stops if s)

    def land(self) -> list:
        """Three reels each on one of the first 2 x kinds stops."""
        return [self.stops[self.rng.below(self.kinds * 2)] for _ in range(3)]

    def nudged(self) -> bool:
        """Whether Luck moves the reels this time: |Luck - 5| x 10% chance."""
        return self.rng.below(101) + abs(self.luck - FAIR_LUCK) * 10 > 100

    def spin(self) -> tuple:
        """(three values, whether Luck changed them)."""
        values = self.land()
        lucky = False
        while self.nudged():
            values, again, changed = self._nudge(values)
            lucky = lucky or changed
            if not again:
                break
        return values, lucky

    def _nudge(self, values: list) -> tuple:
        """(values, spin again, changed): Luck above 5 pushes a near miss to a win, below 5 a win away."""
        kind, values = classify(values), list(values)
        if self.luck < FAIR_LUCK:
            if kind == THREE:
                value = 0 if values[0] + 1 > 6 else values[0] + 1
                return [value] * 3, False, True
            if kind in (ONE_WILD, TWO_WILDS):
                return [WILD_BLANK if v == WILD else v for v in values], False, True
            return values, False, False
        if kind == NOTHING:
            return self.land(), True, False
        if kind == ONE_WILD:
            return self._wild_pair(values)
        if kind in (PAIR, TWO_WILDS):
            return self._third(values)
        return values, False, False

    def _wild_pair(self, values: list) -> tuple:
        """One wild: the two reels around it made equal when within Luck (FNV's neighbors, as it picks them)."""
        wild = values.index(WILD)
        blank = max((i for i, v in enumerate(values) if v % 2), default=-1)
        before = wild - 1 if wild - 1 >= 0 else 2
        after = wild + 1 if wild + 1 < 2 else 0
        if abs(values[before] - values[after]) > self.luck:
            return values, False, False
        if blank < 0 or before == blank:
            values[before] = values[after]
        else:
            values[after] = values[before]
        return values, False, True

    def _third(self, values: list) -> tuple:
        """A pair (or two wilds): the odd reel made the pair's when (difference)^2 is within Luck."""
        if values[0] == values[1]:
            pair, odd = 0, 2
        elif values[0] == values[2]:
            pair, odd = 0, 1
        else:
            pair, odd = 1, 0
        if (values[pair] - values[odd]) ** 2 > self.luck:
            return values, False, False
        values[odd] = values[pair]
        return values, False, True


def slot_trace(seeds: tuple, spins: int, luck: int) -> str:
    """The line the movie's SelfTest logs: `slots <luck>` then each spin's three values, `a,b,c`."""
    out = []
    for seed in seeds:
        machine = Slots([2] * 7, luck, Rng(seed))
        out += [','.join(map(str, machine.spin()[0])) for _ in range(spins)]
    return f'slots {luck} ' + ' '.join(out)


def bet_up(bet: int) -> int:
    """FNV's slot bet steps up: +1 below 10, +5 below 40, +10 below 100, +25 below 500, then +100."""
    for limit, step in ((10, 1), (40, 5), (100, 10), (500, 25)):
        if bet < limit:
            return bet + step
    return bet + 100


def bet_down(bet: int) -> int:
    """The step back down: the step that bet_up took to reach `bet`."""
    for limit, step in ((10, 1), (40, 5), (100, 10), (500, 25)):
        if bet <= limit:
            return bet - step
    return bet - 100
