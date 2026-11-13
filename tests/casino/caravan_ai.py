"""FNV's Caravan AI (CaravanOwner 0x0074fdc0), line for line with as3/f3nv/casino/CaravanAi.as.

It sees the board from the opponent's side (its caravans 3-5, each facing 5 - k), scores every move it knows into
a list and plays the first after the C runtime's qsort by score, highest first; no randomness. FNV's quirks are kept:
the scratch record keeps fields between candidates, a Jack is valued on the other caravan but played on its own,
the Joker's loss counts aces or suits the wrong way round, the Queen is never played, a hand discard scores its index.

See: docs/fork/fo4_casino_plan.md#caravan-ai
"""

from tests.casino import caravan as C

#: Actions (FNV's codes): play, cut its own card, a Joker, open, discard a caravan, discard a card, play on another.
PLACE, CUT, JOKER_PLAY, OPEN, DISCARD_LANE, DISCARD, ATTACK = 0, 2, 3, 4, 5, 6, 7
#: The C runtime qsort's insertion sort size.
SHORT_SORT = 8


class Choice:
    """FNV's 28-byte decision: the caravan total it reaches, its band, the action, caravan, row, hand card, score."""

    def __init__(self):
        """All fields 0."""
        self.total = self.band = self.action = self.lane = self.row = self.card = self.score = 0

    def copy(self) -> 'Choice':
        """A copy of every field."""
        out = Choice()
        out.__dict__.update(self.__dict__)
        return out


def decide(lanes: list, hand: list, deck: list, mode: int, opening: bool) -> Choice:
    """The opponent's move: at the opening a card to open with or discard, else the best scored move."""
    if opening:
        choice = Choice()
        choice.action, choice.card = opening_move([card[0] for card in hand], mode)
        return choice
    return Mind(lanes, hand, deck, mode).choose()


def opening_move(ranks: list, mode: int) -> tuple:
    """(OPEN or DISCARD, hand index) at the opening by mode: discard a face card with over 5 of the wrong cards in
    hand; else mode 0 the last number, 1-2 the first 6-10 (or under 4, whichever kind is more), 3 the nearest 6.
    Where FNV reads an unset card (no such card), the first number card opens (our choice)."""
    n, numbers = len(ranks), [i for i, r in enumerate(ranks) if r <= 10]
    fallback = (OPEN, numbers[0] if numbers else 0)
    if mode < 1:
        faces = [i for i, r in enumerate(ranks) if r > 10]
        return (DISCARD, faces[-1]) if n - len(numbers) > 5 else (OPEN, numbers[-1] if numbers else 0)
    if mode < 3:
        mid = sum(1 for r in ranks if 5 < r <= 10)
        low = sum(1 for r in ranks if r < 4)
        if (n - low) - mid > 5:
            return face_pick(ranks) or fallback
        wanted = (lambda r: 5 < r <= 10) if mid > low else (lambda r: r < 4) if low else None
        found = [i for i, r in enumerate(ranks) if wanted and wanted(r)]
        return (OPEN, found[0]) if found else fallback
    if n - len(numbers) > 5:
        return face_pick(ranks) or fallback
    best = 0
    for i, r in enumerate(ranks):
        best = i if abs(r - 6) < abs(ranks[best] - 6) else best
    return OPEN, best


def face_pick(ranks: list) -> 'tuple | None':
    """The face card discarded at the opening: the first Joker, else FNV's replacing order; None without one."""
    best, card = 0, None
    for i, r in enumerate(ranks):
        if r <= 10:
            continue
        if r == C.JOKER:
            return DISCARD, i
        if best in (0, C.JACK) or (best == C.KING and r != C.JACK):
            best, card = r, i
    return None if card is None else (DISCARD, card)


def ace_loss(lane: list, value: int) -> int:
    """How many cards of `value` the caravan has, times `value` (0x00752cb0)."""
    return sum(1 for cell in lane[:C.laid(lane)] if cell[0][0] == value) * value


def suit_loss(lane: list, suit: int) -> int:
    """The values of the caravan's cards of suit `suit` (0x00752d40)."""
    return sum(cell[0][0] for cell in lane[:C.laid(lane)] if cell[0][1] == suit)


def first_empty(lane: list) -> int:
    """A caravan's next row, 7 when full."""
    return next((r for r in range(C.ROWS) if not lane[r]), C.ROWS)


class Mind:
    """One normal turn's search: `cur` is FNV's scratch record, pushed into `choices` as each move scores."""

    def __init__(self, lanes: list, hand: list, deck: list, mode: int):
        """The board, the AI's hand and draw deck, its mode; every caravan's points."""
        self.lanes, self.hand, self.deck, self.mode = lanes, hand, deck, mode
        self.totals = [C.lane_total(lane) for lane in lanes]
        self.cur, self.choices = Choice(), []

    def can(self, lane: int, row: int, index: int) -> bool:
        """FNV's placement rule for the opponent."""
        return C.can_place(self.lanes, False, 1, lane, row, self.hand[index])

    def push(self, action: int, score: int, total: 'int | None' = None) -> None:
        """Keep the scratch record as a choice (with `action`, `score`, and `total` and its band when given); the
        next starts from 0 but keeps its caravan, row and card."""
        cur = self.cur
        cur.action, cur.score = action, score
        if total is not None:
            cur.total, cur.band = total, C.band(total)
        self.choices.append(cur.copy())
        cur.total = cur.band = cur.action = cur.score = 0

    def choose(self) -> Choice:
        """Score the moves on its caravans, then on the player's, then (with none) a discard; the first by score."""
        for lane in (3, 4, 5):
            self.cur.lane = lane
            own, other = self.totals[lane], self.totals[C.LANES - 1 - lane]
            if C.band(own) < 0:
                self.building(lane, own)
            elif C.band(own) == 0 and own < other < 27:
                self.behind(lane, own, other)
            elif C.band(own) == 0:
                self.ahead(lane, own)
            else:
                self.bust(lane, own)
        for lane in (0, 1, 2):
            self.attack(lane)
        if not self.choices:
            self.give_up()
        msvc_qsort(self.choices, by_score)
        return self.choices[0]

    def building(self, lane: int, own: int) -> None:
        """Under 21: a King on any of its cards, or a number on the next row, that keep it at 26 or less."""
        for i, card in enumerate(self.hand):
            self.cur.card = i
            if card[0] == C.KING:
                self.kings(lane, own, i)
            elif card[0] <= 10:
                row = first_empty(self.lanes[lane])
                self.cur.row = row
                value = card[0] + own
                if row < C.ROWS and C.band(value) < 1 and self.can(lane, row, i):
                    self.push(PLACE, value, value)

    def kings(self, lane: int, own: int, index: int) -> None:
        """Each King under 21: its card's points added (scored +1, or -5 at mode 2)."""
        row = 0
        while row < C.ROWS and self.lanes[lane][row]:
            self.cur.row = row
            value = C.row_value(self.lanes[lane][row]) + own
            if len(self.lanes[lane][row]) <= 3 and C.band(value) < 1 and self.can(lane, row, index):
                self.push(PLACE, value + (-5 if self.mode == 2 else 1), value)
            row += 1

    def behind(self, lane: int, own: int, other: int) -> None:
        """Sold but behind the player's caravan: a Jack, a Joker (mode 1 up) or a number that catches up."""
        for i, card in enumerate(self.hand):
            self.cur.card = i
            if card[0] == C.JACK:
                self.jack_back(lane, own, other, i)
            elif self.mode >= 1 and card[0] == C.JOKER:
                self.joker(lane, i)
            elif card[0] <= 10:
                self.catch_up(lane, own, other, i)

    def jack_back(self, lane: int, own: int, other: int, index: int) -> None:
        """A Jack valued on the player's caravan's card that puts it behind, but played on its own row (FNV)."""
        mirror = self.lanes[C.LANES - 1 - lane]
        for row in range(C.ROWS):
            self.cur.row = row
            if not mirror[row]:
                break
            value = C.row_value(mirror[row])
            if value > other - own:
                gap = own - (other - value)
                self.cur.score = 100 - gap if other - value > 21 else gap + 75
                if self.can(lane, row, index):
                    self.push(ATTACK, self.cur.score, own)

    def catch_up(self, lane: int, own: int, other: int, index: int) -> None:
        """A number on the next row: ahead scores 100 less the lead, a tie 50, else its total less 1; over 26 the
        record keeps the scratch score and action (FNV)."""
        row = first_empty(self.lanes[lane])
        self.cur.row = row
        value = self.hand[index][0] + own
        if value < 27:
            self.cur.score = 100 - (value - other) if value > other else 50 if value == other else value - 1
            self.cur.action = PLACE
        if self.can(lane, row, index):
            self.push(self.cur.action, self.cur.score, value)

    def joker(self, lane: int, index: int) -> None:
        """A Joker on one of its cards, scored by what it would take from each caravan (FNV's estimate)."""
        for row in range(C.ROWS):
            self.cur.row = row
            if not self.lanes[lane][row]:
                break
            if not self.can(lane, row, index):
                continue
            base = self.lanes[lane][row][0][0]
            loss = [ace_loss(cells, 1) if base == C.ACE else suit_loss(cells, base) for cells in self.lanes]
            loss[lane] += base
            score = self.joker_score(lane, loss)
            if score > 0:
                self.cur.score, self.cur.action = score + (50 if self.mode < 3 else 0), JOKER_PLAY
                self.choices.append(self.cur.copy())
                self.cur.total = self.cur.band = self.cur.action = self.cur.score = 0

    def joker_score(self, lane: int, loss: list) -> int:
        """Below mode 3, its caravan's lead after the losses; mode 3, FNV's sum over the three pairs."""
        t = self.totals
        if self.mode < 3:
            other = C.LANES - 1 - lane
            return ((t[lane] - loss[lane]) - t[other]) - loss[other]
        lead = [((t[k + 3] - loss[k + 3]) - t[k]) - loss[k] for k in range(3)]
        score = 75 if lead[C.LANES - 1 - lane] > 0 else 0
        for k in range(3):
            score += pair_score(t[k + 3], loss[k + 3], t[k], loss[k], lead[k])
        return score

    def ahead(self, lane: int, own: int) -> None:
        """Sold and not behind: a King (scored as twice its card) or a number that keep it at 26 or less."""
        for i, card in enumerate(self.hand):
            self.cur.card = i
            if card[0] == C.KING:
                for row in range(C.ROWS):
                    self.cur.row = row
                    value = own + 2 * C.row_value(self.lanes[lane][row])
                    if C.band(value) < 1 and self.can(lane, row, i):
                        self.push(PLACE, value, value)
            elif card[0] <= 10:
                row = first_empty(self.lanes[lane])
                self.cur.row = row
                value = card[0] + self.totals[lane]
                if self.can(lane, row, i) and C.band(value) < 1:
                    self.push(PLACE, value, value)

    def bust(self, lane: int, own: int) -> None:
        """Over 26: a Jack on one of its cards that brings it back to 26 or less."""
        for i, card in enumerate(self.hand):
            self.cur.card = i
            if card[0] != C.JACK:
                continue
            for row in range(C.ROWS):
                self.cur.row = row
                value = C.row_value(self.lanes[lane][row])
                if own - value < 27 and self.can(lane, row, i):
                    self.push(CUT, 100 - ((26 - own) + value), own - value)

    def attack(self, lane: int) -> None:
        """On the player's caravan: a Jack on a card (more if it is sold), a King that busts it."""
        self.cur.lane = lane
        total = self.totals[lane]
        for i, card in enumerate(self.hand):
            self.cur.card = i
            row = 0
            while card[0] > 10 and row < C.ROWS and self.lanes[lane][row]:
                self.cur.row = row
                value = C.row_value(self.lanes[lane][row])
                if len(self.lanes[lane][row]) <= 3 and card[0] == C.JACK and C.band(total) <= 0:
                    self.push(ATTACK, (26 - (total - value)) + (25 if C.band(total) == 0 else 0))
                elif len(self.lanes[lane][row]) <= 3 and card[0] == C.KING and C.band(total + value) == 1:
                    self.push(ATTACK, total + value - 1)
                row += 1

    def give_up(self) -> None:
        """No move: discard the first highest card (scored by its place), or discard an unsold caravan."""
        best = 0
        for i, card in enumerate(self.hand):
            best = i if card[0] > self.hand[best][0] else best
        self.cur.card = best
        self.push(DISCARD, best)
        jacks = sum(1 for card in self.deck if card[0] == C.JACK)
        for lane in (3, 4, 5):
            total = self.totals[lane]
            if C.band(total) != 0:
                self.cur.lane = lane
                score = total - 26 if self.mode < 1 else 2 * total - 52 - (5 * jacks if self.mode >= 3 else 0)
                self.push(DISCARD_LANE, score)


def pair_score(ai: int, ai_loss: int, player: int, player_loss: int, lead: int) -> int:
    """One pair's part of the mode-3 Joker score (FNV's terms, in order)."""
    left, player_left, score = ai - ai_loss, player - player_loss, 0
    if 20 < ai < 27 and left < 21:
        score -= 25 - (21 - left)
    if C.band(ai) >= 0:
        if ai < 27 and left < 21:
            score -= (21 - ai) - ai_loss
        if ai < 27 and lead < 0 and C.band(player_left) == 0:
            score -= lead + 25
        if C.band(ai) > 0 and C.band(left) <= 0:
            score += left
    if C.band(ai) > 0 and ai_loss > 0:
        score += 25 + left if C.band(left) == 0 else left if C.band(left) < 0 else ai_loss
    if C.band(player) == 0 and C.band(player_left) < 0:
        score += (46 - player) + player_loss
    return score


def by_score(a: Choice, b: Choice) -> int:
    """FNV's comparator: the higher score first (0x0073b6e0)."""
    return (b.score > a.score) - (b.score < a.score)


def msvc_qsort(items: list, compare) -> None:
    """The C runtime's qsort (median of three, insertion sort under 9, the smaller part first); not stable, so its
    order of equal scores is FNV's."""
    stack, lo, hi = [], 0, len(items) - 1
    while hi > lo or stack:
        if hi - lo + 1 <= SHORT_SORT:
            _short_sort(items, lo, hi, compare)
        else:
            lo_end, hi_start = _partition(items, lo, hi, compare)
            parts = sorted(((lo, lo_end), (hi_start, hi)), key=lambda p: p[1] - p[0], reverse=True)
            stack += [p for p in parts if p[0] < p[1]]
        if not stack:
            return
        lo, hi = stack.pop()


def _short_sort(items: list, lo: int, hi: int, compare) -> None:
    """Selection of the largest to the end, as the runtime's shortsort."""
    while hi > lo:
        top = lo
        for p in range(lo + 1, hi + 1):
            top = p if compare(items[p], items[top]) > 0 else top
        items[top], items[hi] = items[hi], items[top]
        hi -= 1


def _partition(items: list, lo: int, hi: int, compare) -> tuple:
    """The runtime's partition around the median of three; (end of the low part, start of the high part)."""
    mid = lo + (hi - lo + 1) // 2
    for a, b in ((lo, mid), (lo, hi), (mid, hi)):
        if compare(items[a], items[b]) > 0:
            items[a], items[b] = items[b], items[a]
    low, high = lo, hi
    while True:
        if mid > low:
            low += 1
            while low < mid and compare(items[low], items[mid]) <= 0:
                low += 1
        if mid <= low:
            low += 1
            while low <= hi and compare(items[low], items[mid]) <= 0:
                low += 1
        high -= 1
        while high > mid and compare(items[high], items[mid]) > 0:
            high -= 1
        if high < low:
            break
        items[low], items[high] = items[high], items[low]
        mid = low if mid == high else mid
    return _equal_run(items, lo, high + 1, mid, compare), low


def _equal_run(items: list, lo: int, high: int, mid: int, compare) -> int:
    """Past the pivot's equal elements below the split: the end of the low part still to sort."""
    if mid < high:
        high -= 1
        while high > mid and compare(items[high], items[mid]) == 0:
            high -= 1
    if mid >= high:
        high -= 1
        while high > lo and compare(items[high], items[mid]) == 0:
            high -= 1
    return high
