package f3nv.casino
{
   // FNV's Caravan, line for line with tests/casino/caravan.py (FalloutNV.exe caravanmenu.cpp): the placement rule,
   // a caravan's points, suit and way, the result, the deal and draws, a turn with the Jack and the Joker, the
   // deck builder's Randomize, the ante, raise cap and payout. A card is [value, suit, id]: value 1 the ace to 10,
   // 12 Jack, 13 Queen, 14 King, 15 Joker; suit 1-4, 5 the Joker. Caravans 0-2 are the player's, 3-5 the opponent's,
   // caravan k facing 5 - k; each is seven cells, a cell a number card and up to three face cards on it.
   public class Caravan
   {
      public static const ACE:int = 1;
      public static const JACK:int = 12;
      public static const QUEEN:int = 13;
      public static const KING:int = 14;
      public static const JOKER:int = 15;
      public static const JOKER_SUIT:int = 5;
      public static const LANES:int = 6;
      public static const ROWS:int = 7;
      public static const HAND:int = 8;
      public static const LOW:int = 21;
      public static const HIGH:int = 26;
      public static const MOST_FACES:int = 3;
      public static const SMALLEST_DECK:int = 30;
      public static const LARGEST_DECK:int = 108;
      public static const WON:int = 1;
      public static const LOST:int = 2;

      public var mode:int;
      public var decks:Array;
      public var hands:Array = [[], []];
      public var lanes:Array = [];
      public var picks:Array;
      public var opening:Boolean = true;
      public var result:int = 0;
      // The opponent's turn (it moves first).
      public var waiting:Boolean = true;
      public var moves:int = 0;
      private var rng:Rng;

      // Deal eight cards each, one each in turn from a random place (the deck's last card takes its place).
      public function Caravan(playerDeck:Array, opponentDeck:Array, aiMode:int, random:Rng)
      {
         mode = aiMode;
         rng = random;
         decks = [playerDeck.concat(), opponentDeck.concat()];
         for (var lane:int = 0; lane < LANES; lane++)
         {
            lanes.push(emptyLane());
         }
         for (var n:int = 0; n < HAND; n++)
         {
            for (var side:int = 0; side < 2; side++)
            {
               var deck:Array = decks[side];
               var at:int = rng.below(deck.length);
               hands[side].push(deck[at]);
               deck[at] = deck[deck.length - 1];
               deck.pop();
            }
         }
         picks = [pick(0), pick(1)];
      }

      public static function emptyLane() : Array
      {
         var out:Array = [];
         for (var row:int = 0; row < ROWS; row++)
         {
            out.push([]);
         }
         return out;
      }

      // -1 under 21, 1 over 26, 0 for a caravan that sells.
      public static function band(total:int) : int
      {
         return total < LOW ? -1 : total > HIGH ? 1 : 0;
      }

      // A card's points with its face cards: its value doubled once per King.
      public static function rowValue(cell:Array) : int
      {
         var value:int = cell.length ? cell[0][0] : 0;
         for (var i:int = 1; i < cell.length; i++)
         {
            value = cell[i][0] == KING ? value * 2 : value;
         }
         return value;
      }

      public static function laid(lane:Array) : int
      {
         for (var row:int = 0; row < ROWS; row++)
         {
            if (!lane[row].length)
            {
               return row;
            }
         }
         return ROWS;
      }

      public static function laneTotal(lane:Array) : int
      {
         var total:int = 0;
         var count:int = laid(lane);
         for (var row:int = 0; row < count; row++)
         {
            total += rowValue(lane[row]);
         }
         return total;
      }

      // [direction, suit, total]: as tests/casino/caravan.py's lane_stats.
      public static function laneStats(lane:Array) : Array
      {
         var count:int = laid(lane);
         var total:int = laneTotal(lane);
         if (count == 0)
         {
            return [0, JOKER_SUIT, total];
         }
         var last:Array = lane[count - 1];
         var direction:int = count == 1 ? 0 : last[0][0] > lane[count - 2][0][0] ? 1 : -1;
         var suit:int = last[0][1];
         for (var i:int = 1; i < last.length; i++)
         {
            if (last[i][0] == QUEEN)
            {
               suit = last[i][1];
               direction = -direction;
            }
         }
         return [direction, suit, total];
      }

      // FNV's placement rule for `side` (1 the opponent): see tests/casino/caravan.py's can_place.
      public static function canPlace(lanes:Array, opening:Boolean, side:int, lane:int, row:int, card:Array) : Boolean
      {
         if (lane < 0 || lane >= LANES || row < 0 || row >= ROWS)
         {
            return false;
         }
         var value:int = card[0];
         var cell:Array = lanes[lane][row];
         if (opening)
         {
            return !cell.length && value <= 10;
         }
         if (value > 10)
         {
            return cell.length >= 1 && cell.length <= MOST_FACES
               && !(value == QUEEN && row < ROWS - 1 && lanes[lane][row + 1].length);
         }
         if (cell.length || (side == 1 && lane < 3) || (side == 0 && lane > 2))
         {
            return false;
         }
         return row == 0 || follows(lanes[lane], row, card);
      }

      private static function follows(lane:Array, row:int, card:Array) : Boolean
      {
         if (!lane[row - 1].length)
         {
            return false;
         }
         var before:int = lane[row - 1][0][0];
         var stats:Array = laneStats(lane);
         if (before == card[0])
         {
            return false;
         }
         if (stats[0] == 1 && before >= card[0] && stats[1] != card[1])
         {
            return false;
         }
         return !(stats[0] == -1 && before <= card[0] && stats[1] != card[1]);
      }

      // WON, LOST or 0: see tests/casino/caravan.py's outcome.
      public static function outcome(lanes:Array, hands:Array, decks:Array) : int
      {
         var mine:int = 0;
         var theirs:int = 0;
         for (var pair:int = 0; pair < 3; pair++)
         {
            var own:int = laneTotal(lanes[pair]);
            var other:int = laneTotal(lanes[LANES - 1 - pair]);
            mine += band(own) == 0 && (band(other) != 0 || own > other) ? 1 : 0;
            theirs += band(other) == 0 && (band(own) != 0 || own < other) ? 1 : 0;
         }
         if (mine + theirs == 3)
         {
            return mine > theirs ? WON : LOST;
         }
         if (!hands[0].length && !decks[0].length)
         {
            return LOST;
         }
         return !hands[1].length && !decks[1].length ? WON : 0;
      }

      public static function cut(lane:Array, row:int) : void
      {
         lane.splice(row, 1);
         lane.push([]);
      }

      public static function jokerTargets(lanes:Array, lane:int, row:int) : Array
      {
         var value:int = lanes[lane][row][0][0];
         var suit:int = lanes[lane][row][0][1];
         var out:Array = [];
         for (var i:int = 0; i < LANES; i++)
         {
            var hits:Array = [];
            var count:int = laid(lanes[i]);
            for (var j:int = 0; j < count; j++)
            {
               var base:Array = lanes[i][j][0];
               var matched:Boolean = value == ACE ? base[1] == suit : base[0] == value;
               if (matched && (i != lane || j != row))
               {
                  hits.push(j);
               }
            }
            out.push(hits);
         }
         return out;
      }

      // FNV's Joker: see tests/casino/caravan.py's joker (the last row stays, one step's correction).
      public static function joker(lanes:Array, lane:int, row:int) : void
      {
         var targets:Array = jokerTargets(lanes, lane, row);
         for (var i:int = 0; i < LANES; i++)
         {
            var cells:Array = lanes[i];
            var hits:Array = targets[i];
            var at:int = hits.length ? hits[0] : 0;
            while (hits.length)
            {
               for (var k:int = at; k < ROWS - 1; k++)
               {
                  cells[k] = cells[k + 1].concat();
               }
               hits.shift();
               if (hits.length)
               {
                  at = hits[0] - (hits[0] > at ? 1 : 0);
               }
            }
         }
      }

      private function pick(side:int) : int
      {
         return decks[side].length ? rng.below(decks[side].length) : -1;
      }

      private function draw(side:int) : void
      {
         if (picks[side] != -1)
         {
            hands[side].push(decks[side].splice(picks[side], 1)[0]);
            picks[side] = pick(side);
         }
      }

      public function openingLane(side:int) : int
      {
         var order:Array = side == 0 ? [0, 1, 2] : [5, 4, 3];
         for each (var lane:int in order)
         {
            if (!lanes[lane][0].length)
            {
               return lane;
            }
         }
         return order[2];
      }

      public function legal(index:int, lane:int, row:int) : Boolean
      {
         if (result || waiting || index < 0 || index >= hands[0].length)
         {
            return false;
         }
         if (opening)
         {
            lane = openingLane(0);
            row = 0;
         }
         return canPlace(lanes, opening, 0, lane, row, hands[0][index]);
      }

      public function play(index:int, lane:int, row:int) : Boolean
      {
         if (!legal(index, lane, row))
         {
            return false;
         }
         if (opening)
         {
            lanes[openingLane(0)][0].push(hands[0].splice(index, 1)[0]);
         }
         else
         {
            place(0, index, lane, row);
         }
         ended(0, true);
         return true;
      }

      public function canDiscard(index:int) : Boolean
      {
         return !result && !waiting && decks[0].length > 0 && index >= 0 && index < hands[0].length;
      }

      public function discard(index:int) : Boolean
      {
         if (!canDiscard(index))
         {
            return false;
         }
         hands[0].splice(index, 1);
         draw(0);
         ended(0, !opening);
         return true;
      }

      public function canDiscardLane(lane:int) : Boolean
      {
         var own:Boolean = lanes[0][0].length || lanes[1][0].length || lanes[2][0].length;
         return !result && !waiting && !opening && own && lane >= 0 && lane < 3;
      }

      public function discardLane(lane:int) : Boolean
      {
         if (!canDiscardLane(lane))
         {
            return false;
         }
         lanes[lane] = emptyLane();
         ended(0, true);
         return true;
      }

      public function forfeit() : void
      {
         result = result || LOST;
      }

      private function place(side:int, index:int, lane:int, row:int) : void
      {
         var card:Array = hands[side].splice(index, 1)[0];
         draw(side);
         lanes[lane][row].push(card);
         if (card[0] == JACK)
         {
            cut(lanes[lane], row);
         }
         else if (card[0] == JOKER)
         {
            joker(lanes, lane, row);
         }
      }

      private function ended(side:int, passes:Boolean) : void
      {
         moves++;
         var all:Boolean = true;
         for (var lane:int = 0; lane < LANES; lane++)
         {
            all = all && lanes[lane][0].length > 0;
         }
         if (opening && all)
         {
            opening = false;
         }
         result = result || outcome(lanes, hands, decks);
         if (passes && !result)
         {
            waiting = side == 0;
         }
      }

      // The opponent's move (CaravanAi.decide), then the player's turn.
      public function opponent() : void
      {
         if (waiting && !result)
         {
            auto(1);
            waiting = false;
            ended(1, false);
         }
      }

      // The player's move by the AI's rules (the self-test); an opening discard is free.
      public function autoPlayer() : void
      {
         if (!waiting && !result)
         {
            var wasOpening:Boolean = opening;
            var action:int = auto(0);
            ended(0, !(wasOpening && action == CaravanAi.DISCARD));
         }
      }

      // `side`'s move by the AI's rules (the player's side seen mirrored: caravan k as 5 - k); its action.
      public function auto(side:int) : int
      {
         var view:Array = side == 1 ? lanes : lanes.concat().reverse();
         var choice:Object = CaravanAi.decide(view, hands[side], decks[side], mode, opening);
         var lane:int = side == 1 ? choice.lane : LANES - 1 - choice.lane;
         if (choice.action == CaravanAi.DISCARD)
         {
            hands[side].splice(choice.card, 1);
            draw(side);
         }
         else if (opening)
         {
            lanes[openingLane(side)][0].push(hands[side].splice(choice.card, 1)[0]);
         }
         else if (choice.action == CaravanAi.DISCARD_LANE)
         {
            lanes[lane] = emptyLane();
         }
         else
         {
            place(side, choice.card, lane, choice.row);
         }
         return choice.action;
      }

      // Play out a game, both sides by the AI's rules; WON or LOST (LOST past `most` moves).
      public static function autoplay(game:Caravan, most:int = 400) : int
      {
         while (!game.result && game.moves < most)
         {
            if (game.waiting)
            {
               game.opponent();
            }
            else
            {
               game.autoPlayer();
            }
         }
         return game.result || LOST;
      }

      public static function standardDeck(firstId:int) : Array
      {
         var out:Array = [];
         var values:Array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, JACK, QUEEN, KING];
         for (var suit:int = 1; suit <= 4; suit++)
         {
            for each (var value:int in values)
            {
               out.push([value, suit, firstId + out.length]);
            }
         }
         out.push([JOKER, JOKER_SUIT, firstId + out.length]);
         out.push([JOKER, JOKER_SUIT, firstId + out.length]);
         return out;
      }

      public static function gameText(game:Caravan, ending:int) : String
      {
         var totals:Array = [];
         for each (var lane:Array in game.lanes)
         {
            totals.push(laneTotal(lane));
         }
         return (ending == WON ? "W" : "L") + ":" + game.moves + ":" + totals.join(".");
      }

      // The self-test's line: tests/casino/caravan.py's caravan_trace.
      public static function trace(seeds:Array, aiMode:int) : String
      {
         var games:Array = [];
         for each (var seed:uint in seeds)
         {
            var game:Caravan = new Caravan(standardDeck(0), standardDeck(54), aiMode, new Rng(seed));
            games.push(gameText(game, autoplay(game)));
         }
         return "caravan " + aiMode + " " + games.join(" ");
      }

      // FNV's Randomize: the chosen collection places, ascending.
      public static function randomize(total:int, random:Rng) : Array
      {
         var size:int = total <= SMALLEST_DECK ? SMALLEST_DECK : SMALLEST_DECK + random.below(total - SMALLEST_DECK);
         var left:Array = [];
         for (var i:int = 0; i < total; i++)
         {
            left.push(i);
         }
         var chosen:Array = [];
         for (var n:int = 0; n < Math.min(size, total); n++)
         {
            chosen.push(left.splice(random.below(left.length), 1)[0]);
         }
         return chosen.sort(Array.NUMERIC);
      }

      public static function ante(funds:int, share:Number) : int
      {
         return int(funds * share);
      }

      public static function raiseCap(funds:int, share:Number, barter:int) : int
      {
         return Math.min(int(funds * share + funds * share * (barter / 100.0)), funds);
      }

      public static function raiseStep(room:int) : int
      {
         var step:int = Math.max(int(room / 20), 1);
         return step > 10 ? int(step / 10) * 10 : step;
      }
   }
}
