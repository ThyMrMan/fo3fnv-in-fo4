package f3nv.casino
{
   import f3ui.Draw;
   import f3ui.Text;
   import flash.display.Loader;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.net.URLRequest;
   import flash.text.TextField;

   // The blackjack table: the dealer's hand (the first card face down until the round ends), the player's hand and a
   // split hand on the felt, FNV's buttons for betting (Deal, Increase and Decrease Bet, Bet Max, Exit) and for play
   // (Hit, Double Down, Split, Switch Hands, Surrender, Stay). Each round is settled at once through
   // `send("F3NV_CasinoRound", net)`; Papyrus moves the chips.
   // See docs/fork/fo4_casino_plan.md#blackjack-built
   public class BlackjackScreen extends Sprite
   {
      // Indexes into the texts Papyrus passes (F3NV_Casino.psc's BlackjackTexts, FNV's settings).
      public static const DEAL:int = 0;
      public static const INCREASE_BET:int = 1;
      public static const DECREASE_BET:int = 2;
      public static const BET_MAX:int = 3;
      public static const EXIT:int = 4;
      public static const HIT:int = 5;
      public static const DOUBLE_DOWN:int = 6;
      public static const SPLIT:int = 7;
      public static const SWITCH_HANDS:int = 8;
      public static const SURRENDER:int = 9;
      public static const STAY:int = 10;
      public static const CHIPS:int = 11;
      public static const CURRENT_BET:int = 12;
      public static const EARNINGS:int = 13;
      public static const YOU_WIN:int = 14;
      public static const LUCKY_WIN:int = 15;
      public static const YOU_LOSE:int = 16;
      public static const UNLUCKY_LOSE:int = 17;
      public static const BREAK_EVEN:int = 18;
      public static const CHIP:int = 19;
      public static const PLURAL:int = 20;

      public static const SUITS:String = "hcds";
      public static const CARD_W:Number = 96;
      public static const CARD_H:Number = 134;
      public static const CARD_STEP:Number = 56;
      public static const DEALER_Y:Number = 100;
      public static const HAND_Y:Number = 320;
      public static const HAND_X:Array = [80, 700];
      public static const FELT:uint = 0x1B5E2A;

      private var send:Function;
      private var texts:Array;
      private var table:Blackjack;
      private var earnings:int;
      // Mounted image names: faces[deck][suit * 13 + rank] and backs[deck].
      private var faces:Array = [];
      private var backs:Array = [];
      private var cardsShown:Sprite;
      private var status:TextField;
      private var result:TextField;
      private var totals:Array = [];
      private var betRow:Array = [];
      private var playRow:Array = [];

      public function BlackjackScreen(sender:Function)
      {
         super();
         send = sender;
      }

      // Each deck's card face paths in mount order (suit by suit, rank 0-12), from its back's path as FNV makes them:
      // the back's name up to its last "_", then the suit letter and the card's number (01 the ace, 13 the king).
      public static function facePaths(back:String) : Array
      {
         var stem:String = back.substring(0, back.lastIndexOf("_") + 1);
         var out:Array = [];
         for (var suit:int = 0; suit < 4; suit++)
         {
            for (var rank:int = 0; rank < 13; rank++)
            {
               var number:int = (rank + 1) % 13 + 1;
               out.push(stem + SUITS.charAt(suit) + (number < 10 ? "0" : "") + number + ".dds");
            }
         }
         return out;
      }

      // Papyrus's data (F3NV_Casino.OpenBlackjack); `mount(paths, prefix)` mounts textures and names them.
      public function open(name:String, chipCount:int, low:int, high:int, won:int, luck:int, seed:uint, decks:int,
                           share:Number, payout:Number, stays:Boolean, backPaths:Array, menuTexts:Array,
                           mount:Function) : void
      {
         texts = menuTexts;
         earnings = won;
         table = new Blackjack(chipCount, low, high, decks, share, payout, stays, luck, new Rng(seed));
         mountDecks(backPaths, Math.max(decks, 1), mount);
         Draw.panel(this, 40, 80, 1200, 420, 0);
         graphics.beginFill(FELT, 0.6);
         graphics.drawRect(40, 80, 1200, 420);
         graphics.endFill();
         Text.label(this, 40, 30, 32).text = name;
         cardsShown = new Sprite();
         addChild(cardsShown);
         totals = [Text.label(this, 80, 250, 22), Text.label(this, 80, 466, 22), Text.label(this, 700, 466, 22)];
         status = Text.label(this, 40, 520, 22);
         result = Text.label(this, 480, 530, 28);
         var bets:Array = [[DEAL, deal], [INCREASE_BET, raise], [DECREASE_BET, lower], [BET_MAX, most], [EXIT, exit]];
         var plays:Array = [[HIT, hit], [DOUBLE_DOWN, doubleDown], [SPLIT, split], [SWITCH_HANDS, switchHand],
                            [SURRENDER, surrender], [STAY, stand]];
         betRow = buttons(bets);
         playRow = buttons(plays);
         update();
      }

      private function mountDecks(backPaths:Array, decks:int, mount:Function) : void
      {
         var byPath:Object = {};
         for (var d:int = 0; d < decks; d++)
         {
            var back:String = String(backPaths[Math.min(d, backPaths.length - 1)]);
            if (byPath[back] == undefined)
            {
               var n:int = 0;
               for (var key:String in byPath)
               {
                  n++;
               }
               byPath[back] = [mount(facePaths(back), "F3NV_Card" + n + "_"), mount([back], "F3NV_Back" + n + "_")[0]];
            }
            faces.push(byPath[back][0]);
            backs.push(byPath[back][1]);
         }
      }

      private function buttons(row:Array) : Array
      {
         var out:Array = [];
         for (var i:int = 0; i < row.length; i++)
         {
            out.push(Draw.button(this, text(row[i][0]), 40 + i * 205, 620, row[i][1], 190));
         }
         return out;
      }

      // FO4's controls and keys: Accept or Enter deals, then hits; left and right change the bet; Cancel leaves.
      public function control(name:String) : Boolean
      {
         if (name == "Accept")
         {
            if (table.betting) { deal(); } else { hit(); }
         }
         else if (name == "Left")
         {
            lower();
         }
         else if (name == "Right")
         {
            raise();
         }
         else
         {
            return false;
         }
         return true;
      }

      private function text(index:int) : String
      {
         return index < texts.length ? String(texts[index]) : "";
      }

      // ---- The cards

      private function showHand(hand:Array, x:Number, y:Number, hideFirst:Boolean) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            var card:Array = hand[i];
            var image:String = i == 0 && hideFirst ? backs[card[2]] : faces[card[2]][card[1] * 13 + card[0]];
            var loader:Loader = new Loader();
            loader.contentLoaderInfo.addEventListener(Event.COMPLETE, fit(loader));
            loader.x = x + i * CARD_STEP;
            loader.y = y;
            cardsShown.addChild(loader);
            if (image)
            {
               loader.load(new URLRequest("img://" + image));
            }
         }
      }

      private static function fit(image:Loader) : Function
      {
         return function(e:Event) : void
         {
            image.width = CARD_W;
            image.height = CARD_H;
         };
      }

      private function update() : void
      {
         removeChild(cardsShown);
         cardsShown = new Sprite();
         addChildAt(cardsShown, 1);
         var playing:Boolean = !table.betting;
         showHand(table.dealer, HAND_X[0], DEALER_Y, playing);
         showHand(table.hands[0], HAND_X[0], HAND_Y, false);
         showHand(table.hands[1], HAND_X[1], HAND_Y, false);
         if (playing && table.has("split hand"))
         {
            var at:int = table.active();
            Draw.panel(cardsShown, HAND_X[at] - 10, HAND_Y - 10, CARD_W + 6 * CARD_STEP + 20, CARD_H + 20, 0);
         }
         Text.show(totals[0], table.dealer.length && !playing ? String(Blackjack.handValue(table.dealer)) : "");
         Text.show(totals[1], table.hands[0].length ? String(Blackjack.handValue(table.hands[0])) : "");
         Text.show(totals[2], table.hands[1].length ? String(Blackjack.handValue(table.hands[1])) : "");
         Text.show(status, text(CHIPS) + table.chips + "\n" + text(CURRENT_BET) + (playing ? table.bets[0] + table.bets[1]
                   : table.bet) + "\n" + text(EARNINGS) + earnings);
         var allowed:Array = [true, table.has("double"), table.has("split"), table.has("split hand"),
                              !table.has("acted"), true];
         for (var i:int = 0; i < playRow.length; i++)
         {
            playRow[i].visible = playing;
            playRow[i].alpha = allowed[i] ? 1 : 0.35;
         }
         for each (var button:Sprite in betRow)
         {
            button.visible = !playing;
         }
      }

      // ---- Betting and play

      private function raise(e:Event = null) : void
      {
         table.raise();
         update();
      }

      private function lower(e:Event = null) : void
      {
         table.lower();
         update();
      }

      private function most(e:Event = null) : void
      {
         table.most();
         update();
      }

      private function deal(e:Event = null) : void
      {
         if (table.bet > 0)
         {
            Text.show(result, "");
            ended(table.deal());
         }
      }

      private function hit(e:Event = null) : void
      {
         ended(table.hit());
      }

      private function doubleDown(e:Event = null) : void
      {
         ended(table.doubleDown());
      }

      private function split(e:Event = null) : void
      {
         ended(table.split());
      }

      private function switchHand(e:Event = null) : void
      {
         table.switchHand();
         update();
      }

      private function surrender(e:Event = null) : void
      {
         ended(table.surrender());
      }

      private function stand(e:Event = null) : void
      {
         ended(table.stand());
      }

      // After an action: a finished round (`net` not null) shows FNV's result text and is settled through Papyrus.
      private function ended(net:Object) : void
      {
         if (net != null)
         {
            var chips:int = int(net);
            earnings += chips;
            var amount:String = " " + Math.abs(chips) + " " + text(CHIP) + text(PLURAL);
            if (chips > 0)
            {
               Text.show(result, (table.lucky ? text(LUCKY_WIN) : text(YOU_WIN)) + amount);
            }
            else
            {
               Text.show(result, chips < 0 ? (table.unlucky ? text(UNLUCKY_LOSE) : text(YOU_LOSE)) + amount
                                           : text(BREAK_EVEN));
            }
            send("F3NV_CasinoRound", chips);
         }
         update();
      }

      // Leaving is only between rounds, as FNV's Exit: mid-round the bet is on the table.
      public function canLeave() : Boolean
      {
         return table == null || table.betting;
      }

      private function exit(e:Event = null) : void
      {
         if (canLeave())
         {
            send("F3NV_CasinoClose");
         }
      }
   }
}
