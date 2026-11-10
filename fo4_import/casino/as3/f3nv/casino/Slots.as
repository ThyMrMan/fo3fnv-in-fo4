package f3nv.casino
{
   // FNV's slot machine rules, line for line with tests/casino/model.py's Slots (FalloutNV.exe slotmachinemenu.cpp).
   public class Slots
   {
      public static const WILD:int = 12;
      public static const WILD_BLANK:int = 13;
      public static const NOTHING:int = 0;
      public static const PAIR:int = 1;
      public static const ONE_WILD:int = 4;
      public static const TWO_WILDS:int = 5;
      public static const THREE:int = 6;
      public static const FAIR_LUCK:int = 5;

      public var luck:int;
      public var lucky:Boolean;
      private var stops:Array;
      private var kinds:int;
      private var rng:Rng;

      public function Slots(reelStops:Array, playerLuck:int, random:Rng)
      {
         stops = reel(reelStops);
         luck = playerLuck;
         rng = random;
         kinds = 0;
         for (var i:int = 0; i < reelStops.length; i++)
         {
            if (int(reelStops[i]) != 0)
            {
               kinds++;
            }
         }
      }

      public static function reel(reelStops:Array) : Array
      {
         var left:Array = reelStops.concat();
         var out:Array = [];
         var more:Boolean = true;
         while (more && out.length < 28)
         {
            more = false;
            for (var kind:int = 0; kind < left.length; kind++)
            {
               if (int(left[kind]) != 0)
               {
                  out.push(kind * 2, kind * 2 + 1);
                  left[kind] = int(left[kind]) - 1;
                  more = true;
               }
            }
         }
         return out;
      }

      public static function classify(v:Array) : int
      {
         var wilds:int = 0;
         for (var i:int = 0; i < 3; i++)
         {
            if (v[i] == WILD)
            {
               wilds++;
            }
         }
         if (v[0] == v[1] && v[0] == v[2] && v[1] % 2 == 0)
         {
            return THREE;
         }
         if (wilds == 1)
         {
            return ONE_WILD;
         }
         if (wilds == 2)
         {
            return TWO_WILDS;
         }
         if ((v[1] == v[2] && v[1] % 2 == 0) || (v[0] == v[2] && v[0] % 2 == 0) || (v[1] == v[0] && v[0] % 2 == 0))
         {
            return PAIR;
         }
         return NOTHING;
      }

      // The multiple of the bet three values win; 0 when they lose.
      public static function pays(v:Array) : int
      {
         var kind:int = classify(v);
         if (kind == THREE)
         {
            // By the symbol's value 0-12 (odd values are blanks and never three of a kind).
            var table:Array = [10, 0, 20, 0, 30, 0, 40, 0, 60, 0, 100, 0, 10];
            return int(table[v[0]]);
         }
         if (kind == TWO_WILDS)
         {
            return 5;
         }
         return kind == ONE_WILD ? 2 : 0;
      }

      public function land() : Array
      {
         return [stops[rng.below(kinds * 2)], stops[rng.below(kinds * 2)], stops[rng.below(kinds * 2)]];
      }

      private function nudged() : Boolean
      {
         return rng.below(101) + Math.abs(luck - FAIR_LUCK) * 10 > 100;
      }

      // Three values; `lucky` says whether Luck changed them.
      public function spin() : Array
      {
         var v:Array = land();
         lucky = false;
         while (nudged())
         {
            var kind:int = classify(v);
            if (luck >= FAIR_LUCK && kind == NOTHING)
            {
               v = land();
               continue;
            }
            lucky = nudge(v, kind) || lucky;
            break;
         }
         return v;
      }

      private function nudge(v:Array, kind:int) : Boolean
      {
         if (luck < FAIR_LUCK)
         {
            if (kind == THREE)
            {
               var value:int = v[0] + 1 > 6 ? 0 : v[0] + 1;
               v[0] = v[1] = v[2] = value;
               return true;
            }
            if (kind == ONE_WILD || kind == TWO_WILDS)
            {
               for (var i:int = 0; i < 3; i++)
               {
                  if (v[i] == WILD)
                  {
                     v[i] = WILD_BLANK;
                  }
               }
               return true;
            }
            return false;
         }
         if (kind == ONE_WILD)
         {
            return wildPair(v);
         }
         if (kind == PAIR || kind == TWO_WILDS)
         {
            return third(v);
         }
         return false;
      }

      private function wildPair(v:Array) : Boolean
      {
         var wild:int = v.indexOf(WILD);
         var blank:int = -1;
         for (var i:int = 0; i < 3; i++)
         {
            if (v[i] % 2 != 0)
            {
               blank = i;
            }
         }
         var before:int = wild - 1 >= 0 ? wild - 1 : 2;
         var after:int = wild + 1 < 2 ? wild + 1 : 0;
         if (Math.abs(v[before] - v[after]) > luck)
         {
            return false;
         }
         if (blank < 0 || before == blank)
         {
            v[before] = v[after];
         }
         else
         {
            v[after] = v[before];
         }
         return true;
      }

      private function third(v:Array) : Boolean
      {
         var pair:int = 1;
         var odd:int = 0;
         if (v[0] == v[1])
         {
            pair = 0;
            odd = 2;
         }
         else if (v[0] == v[2])
         {
            pair = 0;
            odd = 1;
         }
         var d:int = v[pair] - v[odd];
         if (d * d > luck)
         {
            return false;
         }
         v[odd] = v[pair];
         return true;
      }

      public static function betUp(bet:int) : int
      {
         var limits:Array = [10, 40, 100, 500];
         var steps:Array = [1, 5, 10, 25];
         for (var i:int = 0; i < 4; i++)
         {
            if (bet < limits[i])
            {
               return bet + steps[i];
            }
         }
         return bet + 100;
      }

      public static function betDown(bet:int) : int
      {
         var limits:Array = [10, 40, 100, 500];
         var steps:Array = [1, 5, 10, 25];
         for (var i:int = 0; i < 4; i++)
         {
            if (bet <= limits[i])
            {
               return bet - steps[i];
            }
         }
         return bet - 100;
      }
   }
}
