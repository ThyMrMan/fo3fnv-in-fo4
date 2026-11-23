package f3nv.casino
{
   // Lucky Horseshoes, Festus's card game, line for line with tests/casino/horseshoes.py (FNV's dialogue on quest
   // VFreeformSSHQ): aces (1) to tens, four of each; whoever is nearer 21 wins once the other is over 21 or holding; a
   // draw that ties the other's total pushes the other up one. A card is [value, copy]. No bet.
   // See docs/fork/fo4_casino_plan.md#lucky-horseshoes
   public class Horseshoes
   {
      public static const TARGET:int = 21;
      public static const VALUES:int = 10;
      public static const COPIES:int = 4;
      public static const REROLLS:int = 2;
      public static const FESTUS_HOLDS_UNDER:int = 5;
      public static const PLAYING:int = 0;
      public static const WON:int = 1;
      public static const LOST:int = 2;
      public static const PLAYER:int = 0;
      public static const FESTUS:int = 1;

      public var hands:Array;
      public var totals:Array;
      public var holding:Array;
      public var winning:Boolean;
      // Lucky Horseshoes this turn: bit 1 << who drew the tying card.
      public var nudged:int;
      public var result:int;
      private var used:Array;
      private var rng:Rng;

      public function Horseshoes(random:Rng)
      {
         rng = random;
         newGame();
      }

      public function newGame() : void
      {
         hands = [[], []];
         totals = [0, 0];
         holding = [false, false];
         used = [];
         for (var v:int = 0; v <= VALUES; v++)
         {
            used.push(0);
         }
         winning = false;
         nudged = 0;
         result = PLAYING;
      }

      public function distance(who:int) : int
      {
         return Math.abs(totals[who] - TARGET);
      }

      // FNV's draw: a value 1-10 alike; a value used four times is rolled again, twice at most.
      public function card() : int
      {
         var value:int = rng.below(VALUES) + 1;
         for (var i:int = 0; i < REROLLS; i++)
         {
            if (used[value] == COPIES)
            {
               value = rng.below(VALUES) + 1;
            }
         }
         return value;
      }

      // `who` draws: a tie of totals pushes the other up one; a nearer total leads, equal distances keep the lead.
      public function take(who:int) : void
      {
         var value:int = card();
         hands[who].push([value, used[value] % COPIES]);
         used[value]++;
         totals[who] += value;
         if (totals[who] == totals[1 - who])
         {
            totals[1 - who]++;
            nudged |= 1 << who;
         }
         if (distance(PLAYER) != distance(FESTUS))
         {
            winning = distance(PLAYER) < distance(FESTUS);
         }
      }

      // The win lines' conditions: the leader wins once the other is over 21 or holding.
      public function ended() : Boolean
      {
         if (winning && (totals[FESTUS] > TARGET || holding[FESTUS]))
         {
            result = WON;
         }
         else if (!winning && (totals[PLAYER] > TARGET || holding[PLAYER]))
         {
            result = LOST;
         }
         return result != PLAYING;
      }

      // The player's Draw: a card, then Festus's turn.
      public function draw() : int
      {
         if (result == PLAYING)
         {
            nudged = 0;
            take(PLAYER);
            if (!ended())
            {
               festusTurn();
            }
         }
         return result;
      }

      // The player's Hold: only while leading (a hold while behind draws, as Festus's "Let's pretend you drew");
      // Festus then draws until the game ends.
      public function hold() : int
      {
         if (result != PLAYING)
         {
            return result;
         }
         if (!winning)
         {
            return draw();
         }
         nudged = 0;
         holding[PLAYER] = true;
         festusDraws();
         return result;
      }

      private function festusTurn() : void
      {
         if (!winning && (holding[FESTUS] || distance(FESTUS) < FESTUS_HOLDS_UNDER))
         {
            holding[FESTUS] = true;
         }
         else
         {
            festusDraws();
         }
      }

      private function festusDraws() : void
      {
         take(FESTUS);
         while (!ended() && holding[PLAYER])
         {
            take(FESTUS);
         }
      }

      // The self-test's fixed play of one game: draw below 17, then hold; the game as values/values=result.
      public function playText() : String
      {
         newGame();
         while (result == PLAYING)
         {
            if (totals[PLAYER] < 17)
            {
               draw();
            }
            else
            {
               hold();
            }
         }
         return handText(hands[PLAYER]) + "/" + handText(hands[FESTUS]) + "=" + result;
      }

      private static function handText(hand:Array) : String
      {
         var values:Array = [];
         for each (var drawn:Array in hand)
         {
            values.push(drawn[0]);
         }
         return values.join(".");
      }
   }
}
