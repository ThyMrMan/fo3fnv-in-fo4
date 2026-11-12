package f3nv.casino
{
   import f3ui.Draw;
   import f3ui.Input;
   import f3ui.Text;
   import flash.display.Loader;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.net.URLRequest;
   import flash.text.TextField;

   // The slot machine screen: three reels of the casino's symbols, the bet, the payout list.
   // Each spin is settled at once through `send("F3NV_CasinoRound", net)`; Papyrus moves the chips.
   // See docs/fork/fo4_casino_plan.md#slots-built
   public class SlotsScreen extends Sprite
   {
      // Indexes into the texts Papyrus passes (F3NV_Casino.psc's SlotTexts, FNV's settings).
      public static const SPIN:int = 0;
      public static const BET_MAX:int = 1;
      public static const CHIPS:int = 2;
      public static const CURRENT_BET:int = 3;
      public static const EARNINGS:int = 4;
      public static const PAYOUTS:int = 5;
      public static const EXIT:int = 6;
      public static const YOU_WIN:int = 7;
      public static const YOU_LOSE:int = 8;
      public static const LUCKY_WIN:int = 9;
      public static const UNLUCKY_LOSE:int = 10;
      public static const CHIP:int = 11;
      public static const PLURAL:int = 12;
      public static const REEL_SIZE:Number = 200;

      private var send:Function;
      private var texts:Array;
      private var slots:Slots;
      private var reels:Array = [];
      private var chips:int;
      private var earnings:int;
      private var bet:int;
      private var minBet:int;
      private var maxBet:int;
      private var title:TextField;
      private var result:TextField;
      private var status:TextField;

      public function SlotsScreen(sender:Function)
      {
         super();
         send = sender;
      }

      // Papyrus's data (F3NV_Casino.OpenSlots); `symbols` are the mounted image names, wild last.
      public function open(name:String, chipCount:int, low:int, high:int, won:int, luck:int, seed:uint,
                           stops:Array, symbols:Array, menuTexts:Array) : void
      {
         texts = menuTexts;
         chips = chipCount;
         earnings = won;
         minBet = low;
         maxBet = high;
         bet = Math.min(low, chips);
         slots = new Slots(stops, luck, new Rng(seed));
         title = Text.label(this, 40, 30, 32);
         title.text = name;
         for (var r:int = 0; r < 3; r++)
         {
            Draw.panel(this, 240 + r * 230, 110, REEL_SIZE, REEL_SIZE, 0.5);
            reels.push(symbolImages(symbols, 240 + r * 230, 110, REEL_SIZE));
         }
         result = Text.label(this, 240, 340, 28);
         status = Text.label(this, 40, 420, 22);
         payoutList(symbols);
         Draw.button(this, "-", 40, 620, betDown, 80);
         Draw.button(this, "+", 130, 620, betUp, 80);
         Draw.button(this, text(BET_MAX), 220, 620, betMax);
         Draw.button(this, text(SPIN), 440, 620, spin);
         Draw.button(this, text(EXIT), 1040, 620, exit);
         show([0, 2, 4]);
         update();
      }

      // One action from the menu's Input: Accept spins, left and right change the bet, Y bets the most (Back is the
      // menu's own).
      public function control(action:String) : Boolean
      {
         if (action == Input.ACCEPT)
         {
            spin();
         }
         else if (action == Input.LEFT)
         {
            betDown();
         }
         else if (action == Input.RIGHT)
         {
            betUp();
         }
         else if (action == Input.Y)
         {
            betMax();
         }
         else
         {
            return false;
         }
         return true;
      }

      // The hint bar's hints: spin, the bet down and up, bet max, exit.
      public function hints() : Array
      {
         return [[Input.ACCEPT, text(SPIN)], [[Input.LEFT, Input.RIGHT], "-/+"], [Input.Y, text(BET_MAX)],
                 [Input.BACK, text(EXIT)]];
      }

      private function text(index:int) : String
      {
         return index < texts.length ? String(texts[index]) : "";
      }

      private function symbolImages(symbols:Array, x:Number, y:Number, size:Number) : Array
      {
         var images:Array = [];
         for (var i:int = 0; i < symbols.length; i++)
         {
            var image:Loader = new Loader();
            image.contentLoaderInfo.addEventListener(Event.COMPLETE, fit(image, size));
            image.load(new URLRequest("img://" + symbols[i]));
            image.x = x;
            image.y = y;
            image.visible = false;
            addChild(image);
            images.push(image);
         }
         return images;
      }

      private static function fit(image:Loader, size:Number) : Function
      {
         return function(e:Event) : void
         {
            image.width = size;
            image.height = size;
         };
      }

      private function payoutList(symbols:Array) : void
      {
         var heading:TextField = Text.label(this, 980, 110, 22);
         heading.text = text(PAYOUTS);
         var lines:Array = [[6, 6, 6, 10], [0, 0, 0, 10], [1, 1, 1, 20], [2, 2, 2, 30], [3, 3, 3, 40],
                            [4, 4, 4, 60], [5, 5, 5, 100], [6, 6, -1, 5], [6, -1, -1, 2]];
         for (var i:int = 0; i < lines.length; i++)
         {
            for (var k:int = 0; k < 3; k++)
            {
               var image:Array = lines[i][k] >= 0 ? symbolImages([symbols[lines[i][k]]], 980 + k * 34, 145 + i * 34, 30) : [];
               if (image.length)
               {
                  image[0].visible = true;
               }
            }
            var pays:TextField = Text.label(this, 1090, 145 + i * 34, 20);
            pays.text = "x" + lines[i][3];
         }
      }

      private function show(values:Array) : void
      {
         for (var r:int = 0; r < 3; r++)
         {
            for (var s:int = 0; s < reels[r].length; s++)
            {
               reels[r][s].visible = values[r] % 2 == 0 && values[r] / 2 == s;
            }
         }
      }

      private function update() : void
      {
         status.text = text(CHIPS) + chips + "\n" + text(CURRENT_BET) + bet + "\n" + text(EARNINGS) + earnings;
      }

      private function setBet(value:int) : void
      {
         bet = Math.max(Math.min(value, maxBet, chips), Math.min(minBet, chips));
         update();
      }

      private function betUp(e:Event = null) : void
      {
         setBet(Slots.betUp(bet));
      }

      private function betDown(e:Event = null) : void
      {
         setBet(Slots.betDown(bet));
      }

      private function betMax(e:Event = null) : void
      {
         setBet(maxBet);
      }

      private function spin(e:Event = null) : void
      {
         if (bet < minBet || bet > chips || bet <= 0)
         {
            return;
         }
         var values:Array = slots.spin();
         var times:int = Slots.pays(values);
         var net:int = times > 0 ? bet * times : -bet;
         show(values);
         chips += net;
         earnings += net;
         if (times > 0)
         {
            var lead:String = slots.lucky && slots.luck > Slots.FAIR_LUCK ? text(LUCKY_WIN) : text(YOU_WIN);
            result.text = lead + " " + net + " " + text(CHIP) + (net == 1 ? "" : text(PLURAL));
         }
         else
         {
            result.text = slots.lucky && slots.luck < Slots.FAIR_LUCK ? text(UNLUCKY_LOSE) : text(YOU_LOSE);
         }
         setBet(bet);
         send("F3NV_CasinoRound", net);
      }

      private function exit(e:Event = null) : void
      {
         send("F3NV_CasinoClose");
      }
   }
}
