package f3nv.casino
{
   // FNV's Caravan AI (CaravanOwner 0x0074fdc0), line for line with tests/casino/caravan_ai.py: it scores every move
   // it knows from the opponent's side into a list and plays the first after the C runtime's qsort by score, highest
   // first, FNV's quirks kept. A choice is {total, band, action, lane, row, card, score}.
   public class CaravanAi
   {
      public static const PLACE:int = 0;
      public static const CUT:int = 2;
      public static const JOKER_PLAY:int = 3;
      public static const OPEN:int = 4;
      public static const DISCARD_LANE:int = 5;
      public static const DISCARD:int = 6;
      public static const ATTACK:int = 7;
      public static const SHORT_SORT:int = 8;

      private var lanes:Array;
      private var hand:Array;
      private var deck:Array;
      private var mode:int;
      private var totals:Array = [];
      private var cur:Object = fresh();
      private var choices:Array = [];

      public function CaravanAi(boardLanes:Array, aiHand:Array, aiDeck:Array, aiMode:int)
      {
         lanes = boardLanes;
         hand = aiHand;
         deck = aiDeck;
         mode = aiMode;
         for each (var lane:Array in lanes)
         {
            totals.push(Caravan.laneTotal(lane));
         }
      }

      public static function fresh() : Object
      {
         return {total: 0, band: 0, action: 0, lane: 0, row: 0, card: 0, score: 0};
      }

      private static function copy(choice:Object) : Object
      {
         return {total: choice.total, band: choice.band, action: choice.action, lane: choice.lane, row: choice.row,
                 card: choice.card, score: choice.score};
      }

      public static function decide(boardLanes:Array, aiHand:Array, aiDeck:Array, aiMode:int, opening:Boolean) : Object
      {
         if (opening)
         {
            var ranks:Array = [];
            for each (var card:Array in aiHand)
            {
               ranks.push(card[0]);
            }
            var move:Array = openingMove(ranks, aiMode);
            var choice:Object = fresh();
            choice.action = move[0];
            choice.card = move[1];
            return choice;
         }
         return new CaravanAi(boardLanes, aiHand, aiDeck, aiMode).choose();
      }

      // [OPEN or DISCARD, hand index] at the opening: tests/casino/caravan_ai.py's opening_move.
      public static function openingMove(ranks:Array, aiMode:int) : Array
      {
         var n:int = ranks.length;
         var numbers:Array = [];
         var faces:Array = [];
         var mid:int = 0;
         var low:int = 0;
         for (var i:int = 0; i < n; i++)
         {
            (ranks[i] <= 10 ? numbers : faces).push(i);
            mid += ranks[i] > 5 && ranks[i] <= 10 ? 1 : 0;
            low += ranks[i] < 4 ? 1 : 0;
         }
         var fallback:Array = [OPEN, numbers.length ? numbers[0] : 0];
         if (aiMode < 1)
         {
            return n - numbers.length > 5 ? [DISCARD, faces[faces.length - 1]]
                                          : [OPEN, numbers.length ? numbers[numbers.length - 1] : 0];
         }
         if (aiMode < 3)
         {
            if ((n - low) - mid > 5)
            {
               return facePick(ranks) || fallback;
            }
            for (i = 0; i < n; i++)
            {
               if ((mid > low && ranks[i] > 5 && ranks[i] <= 10) || (mid <= low && low && ranks[i] < 4))
               {
                  return [OPEN, i];
               }
            }
            return fallback;
         }
         if (n - numbers.length > 5)
         {
            return facePick(ranks) || fallback;
         }
         var best:int = 0;
         for (i = 0; i < n; i++)
         {
            best = Math.abs(ranks[i] - 6) < Math.abs(ranks[best] - 6) ? i : best;
         }
         return [OPEN, best];
      }

      public static function facePick(ranks:Array) : Array
      {
         var best:int = 0;
         var card:int = -1;
         for (var i:int = 0; i < ranks.length; i++)
         {
            var r:int = ranks[i];
            if (r <= 10)
            {
               continue;
            }
            if (r == Caravan.JOKER)
            {
               return [DISCARD, i];
            }
            if (best == 0 || best == Caravan.JACK || (best == Caravan.KING && r != Caravan.JACK))
            {
               best = r;
               card = i;
            }
         }
         return card < 0 ? null : [DISCARD, card];
      }

      public static function aceLoss(lane:Array, value:int) : int
      {
         var count:int = 0;
         var n:int = Caravan.laid(lane);
         for (var r:int = 0; r < n; r++)
         {
            count += lane[r][0][0] == value ? 1 : 0;
         }
         return count * value;
      }

      public static function suitLoss(lane:Array, suit:int) : int
      {
         var sum:int = 0;
         var n:int = Caravan.laid(lane);
         for (var r:int = 0; r < n; r++)
         {
            sum += lane[r][0][1] == suit ? lane[r][0][0] : 0;
         }
         return sum;
      }

      public static function firstEmpty(lane:Array) : int
      {
         for (var r:int = 0; r < Caravan.ROWS; r++)
         {
            if (!lane[r].length)
            {
               return r;
            }
         }
         return Caravan.ROWS;
      }

      private function can(lane:int, row:int, index:int) : Boolean
      {
         return Caravan.canPlace(lanes, false, 1, lane, row, hand[index]);
      }

      // Keep the scratch record as a choice; the next starts from 0 but keeps its caravan, row and card.
      private function push(action:int, score:int, total:Object = null) : void
      {
         cur.action = action;
         cur.score = score;
         if (total != null)
         {
            cur.total = int(total);
            cur.band = Caravan.band(int(total));
         }
         keep();
      }

      private function keep() : void
      {
         choices.push(copy(cur));
         cur.total = 0;
         cur.band = 0;
         cur.action = 0;
         cur.score = 0;
      }

      public function choose() : Object
      {
         for (var lane:int = 3; lane <= 5; lane++)
         {
            cur.lane = lane;
            var own:int = totals[lane];
            var other:int = totals[Caravan.LANES - 1 - lane];
            if (Caravan.band(own) < 0)
            {
               building(lane, own);
            }
            else if (Caravan.band(own) == 0 && own < other && other < 27)
            {
               behind(lane, own, other);
            }
            else if (Caravan.band(own) == 0)
            {
               ahead(lane, own);
            }
            else
            {
               bust(lane, own);
            }
         }
         for (lane = 0; lane <= 2; lane++)
         {
            attack(lane);
         }
         if (!choices.length)
         {
            giveUp();
         }
         msvcQsort(choices, byScore);
         return choices[0];
      }

      private function building(lane:int, own:int) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            cur.card = i;
            var value:int = hand[i][0];
            if (value == Caravan.KING)
            {
               kings(lane, own, i);
            }
            else if (value <= 10)
            {
               var row:int = firstEmpty(lanes[lane]);
               cur.row = row;
               if (row < Caravan.ROWS && Caravan.band(value + own) < 1 && can(lane, row, i))
               {
                  push(PLACE, value + own, value + own);
               }
            }
         }
      }

      private function kings(lane:int, own:int, index:int) : void
      {
         for (var row:int = 0; row < Caravan.ROWS && lanes[lane][row].length; row++)
         {
            cur.row = row;
            var value:int = Caravan.rowValue(lanes[lane][row]) + own;
            if (lanes[lane][row].length <= 3 && Caravan.band(value) < 1 && can(lane, row, index))
            {
               push(PLACE, value + (mode == 2 ? -5 : 1), value);
            }
         }
      }

      private function behind(lane:int, own:int, other:int) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            cur.card = i;
            var value:int = hand[i][0];
            if (value == Caravan.JACK)
            {
               jackBack(lane, own, other, i);
            }
            else if (mode >= 1 && value == Caravan.JOKER)
            {
               joker(lane, i);
            }
            else if (value <= 10)
            {
               catchUp(lane, own, other, i);
            }
         }
      }

      private function jackBack(lane:int, own:int, other:int, index:int) : void
      {
         var mirror:Array = lanes[Caravan.LANES - 1 - lane];
         for (var row:int = 0; row < Caravan.ROWS; row++)
         {
            cur.row = row;
            if (!mirror[row].length)
            {
               break;
            }
            var value:int = Caravan.rowValue(mirror[row]);
            if (value > other - own)
            {
               var gap:int = own - (other - value);
               cur.score = other - value > 21 ? 100 - gap : gap + 75;
               if (can(lane, row, index))
               {
                  push(ATTACK, cur.score, own);
               }
            }
         }
      }

      private function catchUp(lane:int, own:int, other:int, index:int) : void
      {
         var row:int = firstEmpty(lanes[lane]);
         cur.row = row;
         var value:int = hand[index][0] + own;
         if (value < 27)
         {
            cur.score = value > other ? 100 - (value - other) : value == other ? 50 : value - 1;
            cur.action = PLACE;
         }
         if (can(lane, row, index))
         {
            push(cur.action, cur.score, value);
         }
      }

      private function joker(lane:int, index:int) : void
      {
         for (var row:int = 0; row < Caravan.ROWS; row++)
         {
            cur.row = row;
            if (!lanes[lane][row].length)
            {
               break;
            }
            if (!can(lane, row, index))
            {
               continue;
            }
            var base:int = lanes[lane][row][0][0];
            var loss:Array = [];
            for each (var cells:Array in lanes)
            {
               loss.push(base == Caravan.ACE ? aceLoss(cells, 1) : suitLoss(cells, base));
            }
            loss[lane] += base;
            var score:int = jokerScore(lane, loss);
            if (score > 0)
            {
               cur.score = score + (mode < 3 ? 50 : 0);
               cur.action = JOKER_PLAY;
               keep();
            }
         }
      }

      private function jokerScore(lane:int, loss:Array) : int
      {
         var t:Array = totals;
         if (mode < 3)
         {
            var other:int = Caravan.LANES - 1 - lane;
            return ((t[lane] - loss[lane]) - t[other]) - loss[other];
         }
         var lead:Array = [];
         for (var k:int = 0; k < 3; k++)
         {
            lead.push(((t[k + 3] - loss[k + 3]) - t[k]) - loss[k]);
         }
         var score:int = lead[Caravan.LANES - 1 - lane] > 0 ? 75 : 0;
         for (k = 0; k < 3; k++)
         {
            score += pairScore(t[k + 3], loss[k + 3], t[k], loss[k], lead[k]);
         }
         return score;
      }

      private function ahead(lane:int, own:int) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            cur.card = i;
            var value:int = hand[i][0];
            if (value == Caravan.KING)
            {
               for (var row:int = 0; row < Caravan.ROWS; row++)
               {
                  cur.row = row;
                  var doubled:int = own + 2 * Caravan.rowValue(lanes[lane][row]);
                  if (Caravan.band(doubled) < 1 && can(lane, row, i))
                  {
                     push(PLACE, doubled, doubled);
                  }
               }
            }
            else if (value <= 10)
            {
               row = firstEmpty(lanes[lane]);
               cur.row = row;
               var total:int = value + totals[lane];
               if (can(lane, row, i) && Caravan.band(total) < 1)
               {
                  push(PLACE, total, total);
               }
            }
         }
      }

      private function bust(lane:int, own:int) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            cur.card = i;
            if (hand[i][0] != Caravan.JACK)
            {
               continue;
            }
            for (var row:int = 0; row < Caravan.ROWS; row++)
            {
               cur.row = row;
               var value:int = Caravan.rowValue(lanes[lane][row]);
               if (own - value < 27 && can(lane, row, i))
               {
                  push(CUT, 100 - ((26 - own) + value), own - value);
               }
            }
         }
      }

      private function attack(lane:int) : void
      {
         cur.lane = lane;
         var total:int = totals[lane];
         for (var i:int = 0; i < hand.length; i++)
         {
            cur.card = i;
            var rank:int = hand[i][0];
            for (var row:int = 0; rank > 10 && row < Caravan.ROWS && lanes[lane][row].length; row++)
            {
               cur.row = row;
               var value:int = Caravan.rowValue(lanes[lane][row]);
               var room:Boolean = lanes[lane][row].length <= 3;
               if (room && rank == Caravan.JACK && Caravan.band(total) <= 0)
               {
                  push(ATTACK, (26 - (total - value)) + (Caravan.band(total) == 0 ? 25 : 0));
               }
               else if (room && rank == Caravan.KING && Caravan.band(total + value) == 1)
               {
                  push(ATTACK, total + value - 1);
               }
            }
         }
      }

      private function giveUp() : void
      {
         var best:int = 0;
         for (var i:int = 0; i < hand.length; i++)
         {
            best = hand[i][0] > hand[best][0] ? i : best;
         }
         cur.card = best;
         push(DISCARD, best);
         var jacks:int = 0;
         for each (var card:Array in deck)
         {
            jacks += card[0] == Caravan.JACK ? 1 : 0;
         }
         for (var lane:int = 3; lane <= 5; lane++)
         {
            var total:int = totals[lane];
            if (Caravan.band(total) != 0)
            {
               cur.lane = lane;
               push(DISCARD_LANE, mode < 1 ? total - 26 : 2 * total - 52 - (mode >= 3 ? 5 * jacks : 0));
            }
         }
      }

      public static function pairScore(ai:int, aiLoss:int, player:int, playerLoss:int, lead:int) : int
      {
         var left:int = ai - aiLoss;
         var playerLeft:int = player - playerLoss;
         var score:int = 0;
         if (20 < ai && ai < 27 && left < 21)
         {
            score -= 25 - (21 - left);
         }
         if (Caravan.band(ai) >= 0)
         {
            if (ai < 27 && left < 21)
            {
               score -= (21 - ai) - aiLoss;
            }
            if (ai < 27 && lead < 0 && Caravan.band(playerLeft) == 0)
            {
               score -= lead + 25;
            }
            if (Caravan.band(ai) > 0 && Caravan.band(left) <= 0)
            {
               score += left;
            }
         }
         if (Caravan.band(ai) > 0 && aiLoss > 0)
         {
            score += Caravan.band(left) == 0 ? 25 + left : Caravan.band(left) < 0 ? left : aiLoss;
         }
         if (Caravan.band(player) == 0 && Caravan.band(playerLeft) < 0)
         {
            score += (46 - player) + playerLoss;
         }
         return score;
      }

      public static function byScore(a:Object, b:Object) : int
      {
         return (b.score > a.score ? 1 : 0) - (b.score < a.score ? 1 : 0);
      }

      // The C runtime's qsort (not stable): tests/casino/caravan_ai.py's msvc_qsort.
      public static function msvcQsort(items:Array, compare:Function) : void
      {
         var stack:Array = [];
         var lo:int = 0;
         var hi:int = items.length - 1;
         while (hi > lo || stack.length)
         {
            if (hi - lo + 1 <= SHORT_SORT)
            {
               shortSort(items, lo, hi, compare);
            }
            else
            {
               var parts:Array = partition(items, lo, hi, compare);
               var low:Array = [lo, parts[0]];
               var high:Array = [parts[1], hi];
               var ordered:Array = low[1] - low[0] >= high[1] - high[0] ? [low, high] : [high, low];
               for each (var part:Array in ordered)
               {
                  if (part[0] < part[1])
                  {
                     stack.push(part);
                  }
               }
            }
            if (!stack.length)
            {
               return;
            }
            var next:Array = stack.pop();
            lo = next[0];
            hi = next[1];
         }
      }

      private static function shortSort(items:Array, lo:int, hi:int, compare:Function) : void
      {
         while (hi > lo)
         {
            var top:int = lo;
            for (var p:int = lo + 1; p <= hi; p++)
            {
               top = compare(items[p], items[top]) > 0 ? p : top;
            }
            var held:Object = items[top];
            items[top] = items[hi];
            items[hi] = held;
            hi--;
         }
      }

      private static function swap(items:Array, a:int, b:int) : void
      {
         var held:Object = items[a];
         items[a] = items[b];
         items[b] = held;
      }

      // [end of the low part, start of the high part] after the runtime's partition around the median of three.
      private static function partition(items:Array, lo:int, hi:int, compare:Function) : Array
      {
         var mid:int = lo + int((hi - lo + 1) / 2);
         for each (var pair:Array in [[lo, mid], [lo, hi], [mid, hi]])
         {
            if (compare(items[pair[0]], items[pair[1]]) > 0)
            {
               swap(items, pair[0], pair[1]);
            }
         }
         var low:int = lo;
         var high:int = hi;
         while (true)
         {
            if (mid > low)
            {
               low++;
               while (low < mid && compare(items[low], items[mid]) <= 0)
               {
                  low++;
               }
            }
            if (mid <= low)
            {
               low++;
               while (low <= hi && compare(items[low], items[mid]) <= 0)
               {
                  low++;
               }
            }
            high--;
            while (high > mid && compare(items[high], items[mid]) > 0)
            {
               high--;
            }
            if (high < low)
            {
               break;
            }
            swap(items, low, high);
            mid = mid == high ? low : mid;
         }
         return [equalRun(items, lo, high + 1, mid, compare), low];
      }

      private static function equalRun(items:Array, lo:int, high:int, mid:int, compare:Function) : int
      {
         if (mid < high)
         {
            high--;
            while (high > mid && compare(items[high], items[mid]) == 0)
            {
               high--;
            }
         }
         if (mid >= high)
         {
            high--;
            while (high > lo && compare(items[high], items[mid]) == 0)
            {
               high--;
            }
         }
         return high;
      }
   }
}
