package f3nv.casino
{
   // FNV's blackjack rules, line for line with tests/casino/blackjack.py (FalloutNV.exe blackjackmenu.cpp): the shoe
   // and its Luck-weighted draw, the deal and its naturals, hit, double, split, switch, surrender, stand, the dealer
   // and the payout. A card is [rank, suit]: rank 0-8 the twos to tens, 9-11 the faces, 12 the ace.
   public class Blackjack
   {
      public static const ACE:int = 12;
      public static const LOSE:int = 1;
      public static const PUSH:int = 2;
      public static const WIN:int = 3;
      public static const BUST:int = 4;
      public static const NATURAL:int = 5;
      public static const SURRENDER:int = 6;
      public static const FAIR_LUCK:int = 5;
      public static const MOST_CANDIDATES:int = 5;
      public static const MOST_CARDS:int = 7;

      public var chips:int;
      public var bet:int;
      public var low:int;
      public var high:int;
      public var betting:Boolean = true;
      public var dealer:Array = [];
      public var hands:Array = [[], []];
      public var results:Array = [0, 0];
      public var bets:Array = [0, 0];
      // FNV's state flags by name: double, split, acted, split hand, on split, done 0, done 1, doubled, natural.
      public var flags:Object = {};
      public var lucky:Boolean;
      public var unlucky:Boolean;
      private var decks:int;
      private var share:Number;
      private var payout:Number;
      private var stays:Boolean;
      private var luck:int;
      private var rng:Rng;
      private var cards:Array = [];
      private var count:int;

      public function Blackjack(chipCount:int, minBet:int, maxBet:int, deckCount:int, reshuffle:Number,
                                naturalPays:Number, staysSoft17:Boolean, playerLuck:int, random:Rng)
      {
         chips = chipCount;
         low = minBet;
         high = maxBet;
         bet = minBet;
         bets = [minBet, 0];
         decks = Math.max(deckCount, 1);
         share = reshuffle;
         payout = naturalPays;
         stays = staysSoft17;
         luck = playerLuck;
         rng = random;
         for (var d:int = 0; d < decks; d++)
         {
            for (var m:int = 0; m < 52; m++)
            {
               cards.push([(m + 12) % 13, int(m / 13), d]);
            }
         }
         count = cards.length;
         fit();
      }

      public static function cardValue(rank:int) : int
      {
         return rank >= 9 && rank <= 11 ? 10 : rank == ACE ? 11 : rank + 2;
      }

      public static function handValue(hand:Array) : int
      {
         var total:int = 0;
         var aces:int = 0;
         for each (var card:Array in hand)
         {
            total += cardValue(card[0]);
            aces += card[0] == ACE ? 1 : 0;
         }
         while (total > 21 && aces > 0)
         {
            total -= 10;
            aces--;
         }
         return total;
      }

      public static function betUp(value:int) : int
      {
         var limits:Array = [10, 40, 100, 400, 1500];
         var steps:Array = [1, 5, 10, 25, 100];
         for (var i:int = 0; i < limits.length; i++)
         {
            if (value < limits[i])
            {
               return value + steps[i];
            }
         }
         return value + 500;
      }

      public static function betDown(value:int) : int
      {
         if (value <= 10)
         {
            return value - 1;
         }
         var limits:Array = [40, 100, 400, 1500];
         var steps:Array = [5, 10, 25, 100];
         for (var i:int = 0; i < limits.length; i++)
         {
            if (value <= limits[i])
            {
               return value % steps[i] ? int(value / steps[i]) * steps[i] : value - steps[i];
            }
         }
         return value % 500 ? int(value / 500) * 500 : value - 500;
      }

      // ---- The shoe

      public function get left() : int
      {
         return count;
      }

      private function shuffle() : void
      {
         count = cards.length;
      }

      // A card for `hand`: random (passing over the next card unseen, FNV's double decrement), or with Luck the best
      // of |Luck - 5| candidates (the player's above 5, the dealer's below 5).
      private function draw(hand:Array, skill:Boolean, isDealer:Boolean) : Array
      {
         if (count < 5)
         {
            shuffle();
         }
         var chosen:int;
         if (hand == null || !skill || (isDealer && luck > 4) || (!isDealer && luck < 6))
         {
            count--;
            chosen = rng.below(count + 1);
         }
         else
         {
            chosen = candidate(hand, isDealer);
         }
         var top:Array = cards[count];
         cards[count] = cards[chosen];
         cards[chosen] = top;
         count--;
         return cards[count + 1];
      }

      private function candidate(hand:Array, isDealer:Boolean) : int
      {
         var total:int = handValue(hand);
         var trials:int = Math.min(Math.abs(luck - FAIR_LUCK), MOST_CANDIDATES);
         var picks:Array = [];
         for (var p:int = 0; p < trials; p++)
         {
            picks.push(rng.below(count));
         }
         var best:int = total;
         var lowest:int = total;
         var bestAt:int = 0;
         var lowAt:int = 0;
         var chosen:int = 0;
         for (var scan:int = 0; scan < trials; scan++)
         {
            var value:int = cardValue(cards[picks[scan]][0]);
            if (value == 11)
            {
               value = value + total > 21 ? 1 : 11;
            }
            var reach:int = value + total;
            if (total > 9)
            {
               if (reach > best && reach < 22)
               {
                  best = reach;
                  bestAt = scan;
               }
            }
            else
            {
               if (21 - reach < best && reach < 22)
               {
                  best = 21 - reach;
                  bestAt = scan;
               }
               if (11 - reach < lowest && reach < 12)
               {
                  lowest = 11 - reach;
                  lowAt = scan;
               }
            }
            if (best < 4)
            {
               chosen = picks[bestAt];
               helped(isDealer, bestAt);
            }
            else if (lowest < best && lowest < 2)
            {
               chosen = picks[lowAt];
               helped(isDealer, lowAt);
            }
            else
            {
               chosen = picks[bestAt];
            }
         }
         return chosen;
      }

      private function helped(isDealer:Boolean, at:int) : void
      {
         if (at != 0)
         {
            unlucky = unlucky || isDealer;
            lucky = lucky || !isDealer;
         }
      }

      // ---- Betting

      private function fit() : void
      {
         if (chips < bet)
         {
            bet = chips;
         }
      }

      public function raise() : void
      {
         if (betting)
         {
            bet = Math.min(betUp(bet), chips, high);
         }
      }

      public function lower() : void
      {
         if (betting)
         {
            bet = Math.max(betDown(bet), low);
         }
      }

      public function most() : void
      {
         if (betting)
         {
            bet = Math.min(high, chips);
         }
      }

      // Deal a round (reshuffling below the casino's share first); the net when a natural ends it at once, else null.
      public function deal() : Object
      {
         if (!betting)
         {
            return null;
         }
         if (count < cards.length * share)
         {
            shuffle();
         }
         betting = false;
         flags = {"double": true};
         results = [0, 0];
         dealer = [];
         hands = [[], []];
         bets = [bet, 0];
         lucky = unlucky = false;
         dealer.push(draw(null, false, false));
         hands[0].push(draw(null, false, false));
         dealer.push(draw(dealer, true, true));
         hands[0].push(draw(hands[0], true, false));
         return dealt();
      }

      private function dealt() : Object
      {
         var value:int = handValue(hands[0]);
         if (value == 21)
         {
            results[0] = NATURAL;
            flags["natural"] = true;
         }
         if (handValue(dealer) == 21)
         {
            flags["natural"] = true;
            results[0] = results[0] == NATURAL ? PUSH : LOSE;
         }
         if (chips >= bet * 2)
         {
            if (value != 11)
            {
               splitTest();
            }
         }
         else
         {
            delete flags["double"];
            delete flags["split"];
         }
         return flags["natural"] ? finish() : null;
      }

      private function splitTest() : void
      {
         var hand:Array = hands[0];
         if (hand.length == 2 && hand[0][0] == hand[1][0] && chips >= bets[0] * 2)
         {
            flags["split"] = true;
         }
      }

      // ---- The player's turn

      public function has(flag:String) : Boolean
      {
         return flags[flag] == true;
      }

      public function active() : int
      {
         return has("on split") ? 1 : 0;
      }

      public function hit() : Object
      {
         if (betting)
         {
            return null;
         }
         flags["acted"] = true;
         delete flags["double"];
         delete flags["split"];
         var at:int = active();
         if (!has("done " + at))
         {
            var hand:Array = hands[at];
            hand.push(draw(hand, true, false));
            var value:int = handValue(hand);
            if (value >= 21 || hand.length >= MOST_CARDS)
            {
               flags["done " + at] = true;
            }
            if (value > 21)
            {
               results[at] = BUST;
            }
         }
         return next();
      }

      // Double the first hand's bet for one card (FNV doubles the first hand even from the split hand).
      public function doubleDown() : Object
      {
         if (betting || !has("double"))
         {
            return null;
         }
         bets[0] *= 2;
         flags["doubled"] = flags["done 0"] = flags["acted"] = true;
         hands[0].push(draw(hands[0], true, false));
         if (handValue(hands[0]) > 21)
         {
            results[0] = BUST;
         }
         delete flags["double"];
         return next();
      }

      // The second card to a split hand on the same bet, a card to each without Luck; FNV tests the first hand's 21
      // for both hands.
      public function split() : Object
      {
         if (betting || !has("split"))
         {
            return null;
         }
         delete flags["double"];
         delete flags["split"];
         flags["acted"] = flags["split hand"] = true;
         bets[1] = bets[0];
         hands[1] = [hands[0].pop()];
         hands[0].push(draw(hands[0], false, false));
         hands[1].push(draw(hands[1], false, false));
         if (handValue(hands[0]) == 21)
         {
            results = [NATURAL, NATURAL];
            flags["done 0"] = flags["done 1"] = true;
         }
         if (chips >= bets[1] + bets[0] * 2)
         {
            flags["double"] = true;
         }
         return results[0] == NATURAL && results[1] == NATURAL ? settle() : null;
      }

      public function switchHand() : void
      {
         if (betting || !has("split hand"))
         {
            return;
         }
         if (has("on split") && !has("done 0"))
         {
            delete flags["on split"];
         }
         else if (!has("on split") && !has("done 1"))
         {
            flags["on split"] = true;
         }
      }

      public function surrender() : Object
      {
         if (betting || has("acted"))
         {
            return null;
         }
         results[0] = SURRENDER;
         return finish();
      }

      public function stand() : Object
      {
         return betting ? null : finish();
      }

      private function next() : Object
      {
         var played:int = has("split hand") ? 2 : 1;
         for (var i:int = 0; i < played; i++)
         {
            if (!has("done " + i))
            {
               return null;
            }
         }
         return finish();
      }

      // ---- The dealer and the payout

      private function finish() : Object
      {
         var lost:Boolean = has("split hand") ? results[0] == BUST && results[1] == BUST
                                              : results[0] == BUST || results[0] == SURRENDER;
         if (!lost && !has("natural"))
         {
            while (dealerHits())
            {
               dealer.push(draw(dealer, true, true));
               if (handValue(dealer) > 21)
               {
                  break;
               }
            }
         }
         return settle();
      }

      private function dealerHits() : Boolean
      {
         var total:int = handValue(dealer);
         var soft:Boolean = false;
         for each (var card:Array in dealer)
         {
            soft = soft || card[0] == ACE;
         }
         return (total < 17 || (total == 17 && soft && !stays)) && dealer.length < MOST_CARDS;
      }

      private function result(hand:Array) : int
      {
         var mine:int = handValue(hand);
         var theirs:int = handValue(dealer);
         if ((mine > theirs && mine < 22) || (mine < 22 && theirs > 21))
         {
            return WIN;
         }
         if ((mine < theirs && theirs < 22) || mine > 21)
         {
            return LOSE;
         }
         return PUSH;
      }

      private function settle() : int
      {
         var played:int = has("split hand") ? 2 : 1;
         var net:int = 0;
         for (var at:int = 0; at < played; at++)
         {
            if (results[at] == 0)
            {
               results[at] = result(hands[at]);
            }
            net += pays(results[at], bets[at], at);
         }
         chips += net;
         if (has("doubled"))
         {
            bets[0] = int(bets[0] / 2);
         }
         bet = bets[0];
         betting = true;
         fit();
         return net;
      }

      private function pays(outcome:int, stake:int, at:int) : int
      {
         if (outcome == LOSE || outcome == BUST)
         {
            return -stake;
         }
         if (outcome == WIN)
         {
            return stake;
         }
         if (outcome == NATURAL)
         {
            return int(stake * payout + 0.5);
         }
         if (outcome == SURRENDER && at == 0)
         {
            return -int(stake / 2.0 + 0.5);
         }
         return 0;
      }

      // ---- The self-test

      // The fixed play of one round (tests/casino/blackjack.py's play): split a pair, double on 10 or 11, hit each
      // hand below 17.
      public function play() : int
      {
         var net:Object = deal();
         if (net != null)
         {
            return int(net);
         }
         if (has("split"))
         {
            net = split();
         }
         else if (has("double") && (handValue(hands[0]) == 10 || handValue(hands[0]) == 11))
         {
            net = doubleDown();
         }
         for (var at:int = 0; at < 2; at++)
         {
            if (net != null)
            {
               break;
            }
            if (at == 1 && !has("split hand"))
            {
               net = stand();
               break;
            }
            if (at == 1)
            {
               switchHand();
            }
            while (net == null && !has("done " + at) && handValue(hands[at]) < 17)
            {
               net = hit();
            }
            if (net == null && at == 1)
            {
               net = stand();
            }
         }
         return int(net);
      }

      // One round as the self-test logs it: dealer ranks, each hand's ranks, the net (blackjack.py's round_text).
      public function roundText(net:int) : String
      {
         var shown:Array = [dealer, hands[0]];
         if (hands[1].length)
         {
            shown.push(hands[1]);
         }
         var parts:Array = [];
         for each (var hand:Array in shown)
         {
            var ranks:Array = [];
            for each (var card:Array in hand)
            {
               ranks.push(card[0]);
            }
            parts.push(ranks.join("."));
         }
         return parts.join("/") + "=" + net;
      }
   }
}
