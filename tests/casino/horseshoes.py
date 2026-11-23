"""Lucky Horseshoes, Festus's card game at Sunset Sarsaparilla, line for line with as3/f3nv/casino/Horseshoes.as.

FNV plays it in dialogue on quest VFreeformSSHQ: the start line's result script
(INFO 00105940), the card lines of SSHQLHPlayerDraw and SSHQLHFestusDraw, the
hold lines of SSHQLHPlayerHold, their conditions on VFreeformSSHQScript's
variables, and the order of their follow-ups. Cards are aces (1) to tens, four
of each; whoever is nearer 21 wins once the other is over 21 or holding; a draw
that ties the other's total pushes the other up one (Lucky Horseshoes). No bet.

See: docs/fork/fo4_casino_plan.md#lucky-horseshoes
"""

from tests.casino.model import Rng

#: The total both play for; card values 1 (the ace) to VALUES; copies of each value; FNV's re-rolls of a spent value.
TARGET, VALUES, COPIES, REROLLS = 21, 10, 4, 2
#: Festus holds while he leads and is fewer than this from 21 (INFO 00142835's FestusDistance < 5).
FESTUS_HOLDS_UNDER = 5
#: The game's state: still playing, the player won, Festus won.
PLAYING, WON, LOST = 0, 1, 2
#: Hands, and Lucky Horseshoes bits by who drew the tying card.
PLAYER, FESTUS = 0, 1


class Horseshoes:
    """One game against Festus: both hands, the cards used, who leads and who holds."""

    def __init__(self, rng: Rng):
        """A fresh game on the shared RNG."""
        self.rng = rng
        self.new_game()

    def new_game(self) -> None:
        """The start line's reset: no cards, nobody leading or holding, every value unused."""
        self.hands, self.totals, self.holding = [[], []], [0, 0], [False, False]
        self.used = [0] * (VALUES + 1)
        self.winning, self.nudged, self.result = False, 0, PLAYING

    def distance(self, who: int) -> int:
        """How far `who`'s total is from 21, either way."""
        return abs(self.totals[who] - TARGET)

    def card(self) -> int:
        """FNV's draw: a value 1-10 alike; a value used four times is rolled again, twice at most."""
        value = self.rng.below(VALUES) + 1
        for _ in range(REROLLS):
            if self.used[value] == COPIES:
                value = self.rng.below(VALUES) + 1
        return value

    def take(self, who: int) -> None:
        """`who` draws: a tie of totals pushes the other up one (Lucky Horseshoes); a nearer total leads, and equal
        distances leave the lead as it was."""
        value = self.card()
        self.hands[who].append((value, self.used[value] % COPIES))
        self.used[value] += 1
        self.totals[who] += value
        if self.totals[who] == self.totals[1 - who]:
            self.totals[1 - who] += 1
            self.nudged |= 1 << who
        if self.distance(PLAYER) != self.distance(FESTUS):
            self.winning = self.distance(PLAYER) < self.distance(FESTUS)

    def ended(self) -> bool:
        """The win lines' conditions: the leader wins once the other is over 21 or holding."""
        if self.winning and (self.totals[FESTUS] > TARGET or self.holding[FESTUS]):
            self.result = WON
        elif not self.winning and (self.totals[PLAYER] > TARGET or self.holding[PLAYER]):
            self.result = LOST
        return self.result != PLAYING

    def draw(self) -> int:
        """The player's Draw: a card, then Festus's turn; the game's state."""
        if self.result == PLAYING:
            self.nudged = 0
            self.take(PLAYER)
            if not self.ended():
                self._festus_turn()
        return self.result

    def hold(self) -> int:
        """The player's Hold: only while leading ("If you hold now, pardner, I'll win!" draws instead); Festus then
        draws until the game ends."""
        if self.result != PLAYING:
            return self.result
        if not self.winning:
            return self.draw()
        self.nudged, self.holding[PLAYER] = 0, True
        self._festus_draws()
        return self.result

    def _festus_turn(self) -> None:
        """Festus holds while he leads and is held or within 4 of 21; otherwise he draws."""
        if not self.winning and (self.holding[FESTUS] or self.distance(FESTUS) < FESTUS_HOLDS_UNDER):
            self.holding[FESTUS] = True
        else:
            self._festus_draws()

    def _festus_draws(self) -> None:
        """Festus draws, again while the player holds."""
        self.take(FESTUS)
        while not self.ended() and self.holding[PLAYER]:
            self.take(FESTUS)


def play(game: Horseshoes) -> int:
    """The self-test's fixed play of one game: draw below 17, then hold (a hold while behind draws)."""
    game.new_game()
    while game.result == PLAYING:
        if game.totals[PLAYER] < 17:
            game.draw()
        else:
            game.hold()
    return game.result


def game_text(game: Horseshoes) -> str:
    """A game as the self-test logs it: values, / Festus's, =result."""
    return '/'.join('.'.join(str(value) for value, _ in hand) for hand in game.hands) + f'={game.result}'


def horseshoes_trace(seeds: tuple, games: int) -> str:
    """The line the movie's SelfTest logs: `horseshoes`, then each seed's games."""
    out = []
    for seed in seeds:
        game = Horseshoes(Rng(seed))
        out += [game_text(game) for _ in range(games) if play(game)]
    return 'horseshoes ' + ' '.join(out)
