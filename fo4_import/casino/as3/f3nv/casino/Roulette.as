package f3nv.casino
{
   // FNV's roulette rules, line for line with tests/casino/roulette.py (FalloutNV.exe roulettemenu.cpp): the 159 spots,
   // one bet a spot and ten a spin under the max, the bet steps, one draw of 38 pockets (37 is 00), the payout.
   public class Roulette
   {
      public static const POCKETS:int = 38;
      public static const SPOTS:int = 159;
      public static const MOST_BETS:int = 10;
      public static const DOUBLE_ZERO:int = 37;
      public static const FAIR_LUCK:int = 5;
      // The wheel from the pocket FNV starts at; red pockets sit at even places (0 and 00 included, as FNV).
      public static const WHEEL:Array = [14, 2, 0, 28, 9, 26, 30, 11, 7, 20, 32, 17, 5, 22, 34, 15, 3, 24, 36,
                                         13, 1, 37, 27, 10, 25, 29, 12, 8, 19, 31, 18, 6, 21, 33, 16, 4, 23, 35];

      public var chips:int;
      public var bet:int;
      public var low:int;
      public var high:int;
      // Spot index -> chips on it, and the spots in the order bet.
      public var bets:Object = {};
      public var order:Array = [];
      private var rng:Rng;

      public function Roulette(chipCount:int, minBet:int, maxBet:int, random:Rng)
      {
         chips = chipCount;
         low = minBet;
         high = maxBet;
         bet = minBet;
         rng = random;
         fit();
      }

      // [numbers as FNV names them, odds] of spot k (0-23) in board row `row` (0 the street edge .. 5 the 3s).
      private static function rowSpot(row:int, k:int) : Array
      {
         var base:int = int((row + 1) / 2);
         var first:int;
         if (row == 0)
         {
            if (k == 0)
            {
               return [[0, DOUBLE_ZERO, 1, 2, 3], 6];
            }
            first = k % 2 ? int(k / 2) * 3 + 1 : int((k - 1) / 2) * 3 + 1;
            return k % 2 ? [run(first, 3), 11] : [run(first, 6), 5];
         }
         if (row % 2)
         {
            if (k % 2)
            {
               return [[base + int(k / 2) * 3], 35];
            }
            if (k)
            {
               first = base + int((k - 1) / 2) * 3;
               return [[first, first + 3], 17];
            }
            return row == 1 ? [[0, 1], 17] : row == 3 ? [[DOUBLE_ZERO, 0, 2], 11] : [[DOUBLE_ZERO, 3], 17];
         }
         if (k % 2)
         {
            first = base + int(k / 2) * 3;
            return [[first, first + 1], 17];
         }
         if (k)
         {
            first = base + int((k - 1) / 2) * 3;
            return [[first, first + 1, first + 3, first + 4], 8];
         }
         return row == 2 ? [[1, 2, 0], 11] : [[2, 3, DOUBLE_ZERO], 11];
      }

      private static function run(first:int, count:int) : Array
      {
         var out:Array = [];
         for (var i:int = 0; i < count; i++)
         {
            out.push(first + i);
         }
         return out;
      }

      // [numbers as named, odds] of spot `index`; an outside spot (147 on) names no numbers.
      public static function spot(index:int) : Array
      {
         if (index < 144)
         {
            return rowSpot(int(index / 24), index % 24);
         }
         if (index == 144)
         {
            return [[DOUBLE_ZERO], 35];
         }
         if (index == 145)
         {
            return [[DOUBLE_ZERO, 0], 17];
         }
         if (index == 146)
         {
            return [[0], 35];
         }
         return [[], index == 147 || index == 150 || index == 153 || index >= 156 ? 2 : 1];
      }

      public static function odds(index:int) : int
      {
         return int(spot(index)[1]);
      }

      private static function wheelPlace(result:int) : int
      {
         return WHEEL.indexOf(result);
      }

      // Whether spot `index` wins on `result`: its numbers less 0 (FNV's list skips 0; an empty one reads 0), or the
      // outside spot's rule.
      public static function wins(index:int, result:int) : Boolean
      {
         switch (index)
         {
            case 147: return result > 0 && result < 13;
            case 150: return result > 12 && result < 25;
            case 153: return result > 24 && result < 37;
            case 148: return result > 0 && result < 19;
            case 155: return result > 18 && result < 37;
            case 149: return result % 2 == 0;
            case 154: return result % 2 == 1;
            case 151: return wheelPlace(result) % 2 == 0;
            case 152: return wheelPlace(result) % 2 == 1;
            case 156: return (result - 1) % 3 == 0;
            case 157: return (result - 2) % 3 == 0;
            case 158: return result % 3 == 0;
         }
         var paying:Array = [];
         for each (var n:int in spot(index)[0])
         {
            if (n != 0)
            {
               paying.push(n);
            }
         }
         return paying.length ? paying.indexOf(result) >= 0 : result == 0;
      }

      public function total() : int
      {
         var sum:int = 0;
         for each (var i:int in order)
         {
            sum += int(bets[i]);
         }
         return sum;
      }

      // FNV's every-frame rule: the chip size never takes more than the chips left after the table's.
      private function fit() : void
      {
         if (chips < bet + total())
         {
            bet = chips - total();
         }
      }

      public function place(index:int) : Boolean
      {
         if (order.length >= MOST_BETS || index < 0 || index >= SPOTS || bet == 0 || order.indexOf(index) >= 0)
         {
            return false;
         }
         if (total() >= high)
         {
            return false;
         }
         bets[index] = bet;
         order.push(index);
         if (total() + bet > chips)
         {
            bet = chips - total();
         }
         if (total() + bet >= high)
         {
            bet = high - total();
         }
         if (order.length == MOST_BETS)
         {
            bet = 0;
         }
         fit();
         return true;
      }

      public function remove(index:int) : Boolean
      {
         var at:int = order.indexOf(index);
         if (at < 0)
         {
            return false;
         }
         order.splice(at, 1);
         delete bets[index];
         return true;
      }

      public function betUp() : void
      {
         bet = Math.min(Slots.betUp(bet), chips - total(), high - total());
         fit();
      }

      public static function betDown(value:int) : int
      {
         if (value <= 10)
         {
            return value - 1;
         }
         var limits:Array = [40, 100, 500];
         var steps:Array = [5, 10, 25];
         for (var i:int = 0; i < 3; i++)
         {
            if (value <= limits[i])
            {
               return value % steps[i] ? int(value / steps[i]) * steps[i] : value - steps[i];
            }
         }
         return value % 100 ? int(value / 100) * 100 : value - 100;
      }

      public function lower() : void
      {
         bet = betDown(bet);
         if (bet <= low && low + total() < high)
         {
            bet = low;
         }
         bet = Math.max(bet, 0);
         fit();
      }

      // [result, net chips]: each winning bet returns (odds + 1) x its chips, less the table's; null without bets.
      public function spin() : Array
      {
         if (order.length == 0)
         {
            return null;
         }
         var result:int = rng.below(POCKETS);
         var won:int = 0;
         for each (var i:int in order)
         {
            if (wins(i, result))
            {
               won += (odds(i) + 1) * int(bets[i]);
            }
         }
         var net:int = won - total();
         chips += net;
         bets = {};
         order = [];
         bet = low;
         fit();
         return [result, net];
      }

      // Each spot's odds and the results it wins on (bit r), `odds:hex`, comma-joined: tests/casino/roulette.py's
      // spot_masks, so the self-test checks this table against the model's.
      public static function spotMasks() : String
      {
         var out:Array = [];
         for (var i:int = 0; i < SPOTS; i++)
         {
            var top:uint = 0;
            var lowBits:uint = 0;
            for (var r:int = 0; r < POCKETS; r++)
            {
               if (wins(i, r))
               {
                  if (r < 32)
                  {
                     lowBits |= uint(1) << r;
                  }
                  else
                  {
                     top |= uint(1) << (r - 32);
                  }
               }
            }
            out.push(odds(i) + ":" + hex(top, lowBits));
         }
         return out.join(",");
      }

      // A 38-bit mask as Python's `%x` writes it (no leading zeros; "0" when empty).
      private static function hex(high:uint, lowBits:uint) : String
      {
         if (high == 0)
         {
            return lowBits.toString(16);
         }
         var tail:String = lowBits.toString(16);
         while (tail.length < 8)
         {
            tail = "0" + tail;
         }
         return high.toString(16) + tail;
      }
   }
}
