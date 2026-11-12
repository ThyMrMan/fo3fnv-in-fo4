"""FNV's blackjack as the menu runs it, line for line with as3/f3nv/casino/Blackjack.as.

From FalloutNV.exe's blackjackmenu.cpp: the shoe and its Luck-weighted draw
(BJDeck::DrawCard 0x00739090, read in the exe too), the hand value
(0x00738ff0), the deal (0x007393f0), the actions (HandleAction 0x00733ff0),
the split test (0x007395a0), the double test after a split (0x00739650) and
the update's states for the deal's end, the dealer and the payout
(0x00734db0). Animations are left out; their state changes are kept.

See: docs/fork/fo4_casino_plan.md#blackjack-built
"""

from tests.casino.model import Rng

#: Card ranks: 0-8 the twos to tens, 9-11 jack, queen, king, 12 the ace; 13 ranks and 4 suits a deck.
ACE, RANKS, SUITS = 12, 13, 4
#: Hand results (FNV's codes): lose, push, win, bust, natural, surrender.
LOSE, PUSH, WIN, BUST, NATURAL, SURRENDER = 1, 2, 3, 4, 5, 6
#: Luck that leaves the draw fair; FNV's candidate array holds 5; a hand's most cards.
FAIR_LUCK, MOST_CANDIDATES, MOST_CARDS = 5, 5, 7


def card_value(rank: int) -> int:
    """A rank's points: 2-10, 10 for faces, 11 for the ace (0x00738fb0)."""
    return 10 if 9 <= rank <= 11 else 11 if rank == ACE else rank + 2


def hand_value(hand: list) -> int:
    """A hand's total: aces count 1 while the total is over 21."""
    total = sum(card_value(card[0]) for card in hand)
    aces = sum(1 for card in hand if card[0] == ACE)
    while total > 21 and aces:
        total, aces = total - 10, aces - 1
    return total


def bet_up(bet: int) -> int:
    """FNV's blackjack step up: +1 below 10, +5 below 40, +10 below 100, +25 below 400, +100 below 1500, +500."""
    for limit, step in ((10, 1), (40, 5), (100, 10), (400, 25), (1500, 100)):
        if bet < limit:
            return bet + step
    return bet + 500


def bet_down(bet: int) -> int:
    """The step down: -1 to 10, then to the step's multiple (or a step) by 5, 10, 25, 100, 500."""
    if bet <= 10:
        return bet - 1
    for limit, step in ((40, 5), (100, 10), (400, 25), (1500, 100)):
        if bet <= limit:
            return bet // step * step if bet % step else bet - step
    return bet // 500 * 500 if bet % 500 else bet - 500


class Shoe:
    """FNV's shoe: decks x 52 (rank, suit, deck) in its load order, `count` of them left; drawn cards swap to the end."""

    def __init__(self, decks: int, luck: int, rng: Rng):
        """`decks` decks (at least 1), the player's Luck, the shared RNG."""
        self.cards = [((m + 12) % 13, m // 13, d) for d in range(max(decks, 1)) for m in range(52)]
        self.count, self.luck, self.rng = len(self.cards), luck, rng
        self.lucky = self.unlucky = False

    def shuffle(self) -> None:
        """Every card back in the shoe (FNV resets the count; the order stays)."""
        self.count = len(self.cards)

    def draw(self, hand: 'list | None', skill: bool, dealer: bool) -> tuple:
        """A card for `hand`: random, or with Luck the best of |Luck - 5| candidates (the player's above 5, the
        dealer's below 5). A random draw passes over the next card unseen, as FNV's double decrement does."""
        if self.count < 5:
            self.shuffle()
        if hand is None or not skill or (dealer and self.luck > 4) or (not dealer and self.luck < 6):
            self.count -= 1
            chosen = self.rng.below(self.count + 1)
        else:
            chosen = self._candidate(hand, dealer)
        self.cards[chosen], self.cards[self.count] = self.cards[self.count], self.cards[chosen]
        self.count -= 1
        return self.cards[self.count + 1]

    def _candidate(self, hand: list, dealer: bool) -> int:
        """The card FNV's Luck picks: toward 21 from above 9, toward 21 or 11 from 9 or less (0x00739090)."""
        total = hand_value(hand)
        trials = min(abs(self.luck - FAIR_LUCK), MOST_CANDIDATES)
        picks = [self.rng.below(self.count) for _ in range(trials)]
        best, low, best_at, low_at, chosen = total, total, 0, 0, 0
        for scan in range(trials):
            value = card_value(self.cards[picks[scan]][0])
            value = (1 if value + total > 21 else 11) if value == 11 else value
            reach = value + total
            if total > 9:
                if best < reach < 22:
                    best, best_at = reach, scan
            else:
                if 21 - reach < best and reach < 22:
                    best, best_at = 21 - reach, scan
                if 11 - reach < low and reach < 12:
                    low, low_at = 11 - reach, scan
            if best < 4:
                chosen = picks[best_at]
                self._helped(dealer, best_at)
            elif low < best and low < 2:
                chosen = picks[low_at]
                self._helped(dealer, low_at)
            else:
                chosen = picks[best_at]
        return chosen

    def _helped(self, dealer: bool, at: int) -> None:
        """Luck changed the card (not the first candidate): the lucky or unlucky text."""
        if at:
            self.unlucky = self.unlucky or dealer
            self.lucky = self.lucky or not dealer


class Table:
    """One sitting at a casino's table: chips held, the bet range, the casino's shoe and rules."""

    def __init__(self, chips: int, low: int, high: int, rules: dict, luck: int, rng: Rng):
        """`rules`: decks, share (reshuffle), payout (natural), stays (dealer stands on soft 17)."""
        self.chips, self.low, self.high, self.rules = chips, low, high, rules
        self.shoe = Shoe(rules['decks'], luck, rng)
        self.bet, self.betting = low, True
        self.dealer, self.hands, self.results, self.bets = [], [[], []], [0, 0], [low, 0]
        self.flags = set()
        self._fit()

    def _fit(self) -> None:
        """Between rounds the bet is never more than the chips held."""
        if self.chips < self.bet:
            self.bet = self.chips


    def bet_up(self) -> None:
        """A step up, held under the chips and the max."""
        if self.betting:
            self.bet = min(bet_up(self.bet), self.chips, self.high)

    def bet_down(self) -> None:
        """A step down, never under the min."""
        if self.betting:
            self.bet = max(bet_down(self.bet), self.low)

    def bet_max(self) -> None:
        """The max, or the chips held."""
        if self.betting:
            self.bet = min(self.high, self.chips)

    def deal(self) -> 'int | None':
        """Deal a round (reshuffling below the casino's share first); the net when a natural ends it at once."""
        if not self.betting:
            return None
        if self.shoe.count < len(self.shoe.cards) * self.rules['share']:
            self.shoe.shuffle()
        self.betting, self.flags, self.results = False, {'double'}, [0, 0]
        self.dealer, self.hands, self.bets = [], [[], []], [self.bet, 0]
        self.shoe.lucky = self.shoe.unlucky = False
        self.dealer.append(self.shoe.draw(None, False, False))
        self.hands[0].append(self.shoe.draw(None, False, False))
        self.dealer.append(self.shoe.draw(self.dealer, True, True))
        self.hands[0].append(self.shoe.draw(self.hands[0], True, False))
        return self._dealt()

    def _dealt(self) -> 'int | None':
        """The deal's end: naturals (the dealer's peeked), then what the funds allow."""
        value = hand_value(self.hands[0])
        if value == 21:
            self.results[0] = NATURAL
            self.flags.add('natural')
        if hand_value(self.dealer) == 21:
            self.flags.add('natural')
            self.results[0] = PUSH if self.results[0] == NATURAL else LOSE
        if self.chips >= self.bet * 2:
            if value != 11:
                self._split_test()
        else:
            self.flags -= {'double', 'split'}
        return self._finish() if 'natural' in self.flags else None

    def _split_test(self) -> None:
        """Split: two cards of one rank, and chips for twice the bet (0x007395a0)."""
        hand = self.hands[0]
        if len(hand) == 2 and hand[0][0] == hand[1][0] and self.chips >= self.bets[0] * 2:
            self.flags.add('split')


    @property
    def playing(self) -> bool:
        """Whether the player's turn is on."""
        return not self.betting

    def _active(self) -> int:
        """The hand the actions take: 1 the split hand."""
        return 1 if 'on split' in self.flags else 0

    def hit(self) -> 'int | None':
        """A card on the active hand unless it is done; 21 or 7 cards ends it, over 21 busts."""
        if not self.playing:
            return None
        self.flags |= {'acted'}
        self.flags -= {'double', 'split'}
        at = self._active()
        if f'done {at}' not in self.flags:
            hand = self.hands[at]
            hand.append(self.shoe.draw(hand, True, False))
            value = hand_value(hand)
            if value >= 21 or len(hand) >= MOST_CARDS:
                self.flags.add(f'done {at}')
            if value > 21:
                self.results[at] = BUST
        return self._next()

    def double(self) -> 'int | None':
        """Double the first hand's bet for one card (FNV doubles the first hand even from the split hand)."""
        if not self.playing or 'double' not in self.flags:
            return None
        self.bets[0] *= 2
        self.flags |= {'doubled', 'done 0', 'acted'}
        self.hands[0].append(self.shoe.draw(self.hands[0], True, False))
        if hand_value(self.hands[0]) > 21:
            self.results[0] = BUST
        self.flags.discard('double')
        return self._next()

    def split(self) -> 'int | None':
        """The second card to a split hand on the same bet, a card to each (no Luck); FNV tests the first hand's
        21 for both."""
        if not self.playing or 'split' not in self.flags:
            return None
        self.flags = (self.flags - {'double', 'split'}) | {'acted', 'split hand'}
        self.bets[1] = self.bets[0]
        self.hands[1] = [self.hands[0].pop()]
        self.hands[0].append(self.shoe.draw(self.hands[0], False, False))
        self.hands[1].append(self.shoe.draw(self.hands[1], False, False))
        if hand_value(self.hands[0]) == 21:
            self.results = [NATURAL, NATURAL]
            self.flags |= {'done 0', 'done 1'}
        if self.chips >= self.bets[1] + self.bets[0] * 2:
            self.flags.add('double')
        if self.results == [NATURAL, NATURAL]:
            return self._settle()
        return None

    def switch(self) -> None:
        """Play the other split hand, if it isn't done."""
        if self.playing and 'split hand' in self.flags:
            if 'on split' in self.flags and 'done 0' not in self.flags:
                self.flags.discard('on split')
            elif 'on split' not in self.flags and 'done 1' not in self.flags:
                self.flags.add('on split')

    def surrender(self) -> 'int | None':
        """Give up half the bet, before any other action."""
        if not self.playing or 'acted' in self.flags:
            return None
        self.results[0] = SURRENDER
        return self._finish()

    def stand(self) -> 'int | None':
        """End the turn: every hand stands."""
        return self._finish() if self.playing else None

    def _next(self) -> 'int | None':
        """After a card: the turn ends when every hand in play is done."""
        hands = 2 if 'split hand' in self.flags else 1
        if all(f'done {i}' in self.flags for i in range(hands)):
            return self._finish()
        return None


    def _finish(self) -> int:
        """The dealer's turn unless no hand is left to beat, then the payout."""
        split = 'split hand' in self.flags
        lost = self.results == [BUST, BUST] if split else self.results[0] in (BUST, SURRENDER)
        if not lost and 'natural' not in self.flags:
            while self._dealer_hits():
                self.dealer.append(self.shoe.draw(self.dealer, True, True))
                if hand_value(self.dealer) > 21:
                    break
        return self._settle()

    def _dealer_hits(self) -> bool:
        """Below 17, or 17 with an ace in hand unless the casino stands on soft 17; 7 cards at most."""
        total = hand_value(self.dealer)
        soft = any(card[0] == ACE for card in self.dealer)
        hits = total < 17 or (total == 17 and soft and not self.rules['stays'])
        return hits and len(self.dealer) < MOST_CARDS

    def _result(self, hand: list) -> int:
        """A hand's result against the dealer's."""
        mine, theirs = hand_value(hand), hand_value(self.dealer)
        if (theirs < mine < 22) or (mine < 22 and theirs > 21):
            return WIN
        if (mine < theirs < 22) or mine > 21:
            return LOSE
        return PUSH

    def _settle(self) -> int:
        """Each hand's chips by its result; natural pays bet x the casino's payout, rounded; surrender half."""
        hands = 2 if 'split hand' in self.flags else 1
        net = 0
        for at in range(hands):
            self.results[at] = self.results[at] or self._result(self.hands[at])
            net += self._pays(self.results[at], self.bets[at], at)
        self.chips += net
        if 'doubled' in self.flags:
            self.bets[0] //= 2
        self.bet, self.betting = self.bets[0], True
        self._fit()
        return net

    def _pays(self, result: int, bet: int, at: int) -> int:
        """One hand's chips (FNV pays no surrender on the split hand)."""
        if result in (LOSE, BUST):
            return -bet
        if result == WIN:
            return bet
        if result == NATURAL:
            return int(bet * self.rules['payout'] + 0.5)
        if result == SURRENDER and at == 0:
            return -int(bet / 2.0 + 0.5)
        return 0


def play(table: Table) -> tuple:
    """The self-test's fixed play of one round: split a pair, double on 10 or 11, hit each hand below 17."""
    net = table.deal()
    if net is not None:
        return net
    if 'split' in table.flags:
        net = table.split()
    elif 'double' in table.flags and hand_value(table.hands[0]) in (10, 11):
        net = table.double()
    for at in (0, 1):
        if net is not None:
            break
        if at and 'split hand' not in table.flags:
            net = table.stand()
            break
        if at:
            table.switch()
        while net is None and f'done {at}' not in table.flags and hand_value(table.hands[at]) < 17:
            net = table.hit()
        if net is None and at == 1:
            net = table.stand()
    return net


def round_text(table: Table, net: int) -> str:
    """A round as the self-test logs it: dealer/hand/split ranks, =net."""
    hands = [table.dealer] + [h for h in table.hands if h]
    return '/'.join('.'.join(str(card[0]) for card in hand) for hand in hands) + f'={net}'


def blackjack_trace(seeds: tuple, rounds: int, luck: int) -> str:
    """The line the movie's SelfTest logs: `blackjack <luck>`, then each seed's rounds on the Tops' rules."""
    out = []
    for seed in seeds:
        table = Table(100000, 5, 5, {'decks': 4, 'share': 0.35, 'payout': 1.5, 'stays': False}, luck, Rng(seed))
        out += [round_text(table, play(table)) for _ in range(rounds)]
    return f'blackjack {luck} ' + ' '.join(out)
