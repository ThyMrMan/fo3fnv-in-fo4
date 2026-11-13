package f3nv.casino
{
   import f3ui.Draw;
   import f3ui.Input;
   import f3ui.Text;
   import f3ui.Theme;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.MouseEvent;
   import flash.text.TextField;

   // The roulette screen: FNV's board of 159 bet spots (click a spot to place the current chips on it, click it again to
   // take them off), the wheel, the bet and the last results. Each spin is settled at once through
   // `send("F3NV_CasinoRound", net)`; Papyrus moves the chips.
   // See docs/fork/fo4_casino_plan.md#roulette-built
   public class RouletteScreen extends Sprite
   {
      // Indexes into the texts Papyrus passes (F3NV_Casino.psc's RouletteTexts, FNV's settings).
      public static const PLACE_BET:int = 0;
      public static const REMOVE_BET:int = 1;
      public static const SPIN:int = 2;
      public static const INCREASE_BET:int = 3;
      public static const DECREASE_BET:int = 4;
      public static const EXIT:int = 5;
      public static const CHIPS:int = 6;
      public static const CURRENT_BET:int = 7;
      public static const TOTAL_BET:int = 8;
      public static const EARNINGS:int = 9;
      public static const BET:int = 10;
      public static const PAYOUT:int = 11;
      public static const YOU_WIN:int = 12;
      public static const LUCKY_WIN:int = 13;
      public static const YOU_LOSE:int = 14;
      public static const BREAK_EVEN:int = 15;
      public static const CHIP:int = 16;
      public static const PLURAL:int = 17;
      public static const FIRST_DOZEN:int = 18;
      public static const SECOND_DOZEN:int = 19;
      public static const THIRD_DOZEN:int = 20;
      public static const EVEN:int = 21;
      public static const RED:int = 22;
      public static const BLACK:int = 23;
      public static const ODD:int = 24;
      public static const TWO_TO_ONE:int = 25;

      // The board: number cells CELL wide, the 0/00 column left of them, rows of 3s, 2s, 1s from the top.
      public static const CELL:Number = 64;
      public static const LEFT:Number = 104;
      public static const TOP:Number = 110;
      public static const EDGE:Number = TOP + 3 * CELL;
      public static const MARKER:Number = 20;
      public static const WHEEL_X:Number = 1100;
      public static const WHEEL_Y:Number = 250;
      public static const WHEEL_R:Number = 130;
      public static const RED_FILL:uint = 0x9A1B1B;
      public static const BLACK_FILL:uint = 0x111111;
      public static const GREEN_FILL:uint = 0x1B6B2A;

      private var send:Function;
      private var texts:Array;
      private var table:Roulette;
      private var luck:int;
      private var earnings:int;
      private var chipsShown:Object = {};
      private var pockets:Array = [];
      private var history:Array = [];
      private var status:TextField;
      private var result:TextField;
      private var info:TextField;
      private var drawn:TextField;
      private var past:TextField;

      public function RouletteScreen(sender:Function)
      {
         super();
         send = sender;
      }

      // Papyrus's data (F3NV_Casino.OpenRoulette).
      public function open(name:String, chipCount:int, low:int, high:int, won:int, playerLuck:int, seed:uint,
                           menuTexts:Array) : void
      {
         texts = menuTexts;
         earnings = won;
         luck = playerLuck;
         table = new Roulette(chipCount, low, high, new Rng(seed));
         Text.label(this, 40, 30, 32).text = name;
         board();
         wheel();
         status = Text.label(this, 40, 430, 22);
         result = Text.label(this, 480, 430, 28);
         info = Text.label(this, 480, 480, 20);
         past = Text.label(this, 960, 400, 20);
         Draw.button(this, "-", 40, 620, betDown, 80);
         Draw.button(this, "+", 130, 620, betUp, 80);
         Draw.button(this, text(SPIN), 220, 620, spin);
         Draw.button(this, text(EXIT), 1040, 620, exit);
         update();
      }

      // One action from the menu's Input: Accept spins, left and right change the chips placed (Back is the menu's
      // own).
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
         else
         {
            return false;
         }
         return true;
      }

      // The hint bar's hints: spin, the bet down and up, exit.
      public function hints() : Array
      {
         return [[Input.ACCEPT, text(SPIN)], [Input.LEFT, text(DECREASE_BET)], [Input.RIGHT, text(INCREASE_BET)],
                 [Input.BACK, text(EXIT)]];
      }

      private function text(index:int) : String
      {
         return index < texts.length ? String(texts[index]) : "";
      }

      // ---- The board

      // [x, y, width, height] of spot `index` on the board: a number, 0/00 or outside spot is its cell; a split, street,
      // corner or line is a small marker where FNV's board puts it (half-cell steps along its row).
      public static function spotBox(index:int) : Array
      {
         if (index < 144)
         {
            var row:int = int(index / 24);
            var k:int = index % 24;
            var x:Number = LEFT + k * CELL / 2;
            var y:Number = EDGE - row * CELL / 2;
            return row % 2 && k % 2 ? [x - CELL / 2, y - CELL / 2, CELL, CELL] : marker(x, y);
         }
         if (index < 147)
         {
            return index == 145 ? marker(LEFT - CELL / 2, TOP + 1.5 * CELL)
                                : [LEFT - CELL, index == 144 ? TOP : TOP + 1.5 * CELL, CELL, 1.5 * CELL];
         }
         if (index >= 156)
         {
            return [LEFT + 12 * CELL, EDGE - (index - 155) * CELL, CELL, CELL];
         }
         if (index == 147 || index == 150 || index == 153)
         {
            return [LEFT + (index - 147) / 3 * 4 * CELL, EDGE + 8, 4 * CELL, 50];
         }
         var outside:Array = [148, 149, 151, 152, 154, 155];
         return [LEFT + outside.indexOf(index) * 2 * CELL, EDGE + 58, 2 * CELL, 50];
      }

      private static function marker(x:Number, y:Number) : Array
      {
         return [x - MARKER / 2, y - MARKER / 2, MARKER, MARKER];
      }

      private static function isMarker(index:int) : Boolean
      {
         return spotBox(index)[2] == MARKER;
      }

      // FNV's spot label: "Bet: <numbers or name> \nPayout: <odds>:1".
      private function label(index:int) : String
      {
         var numbers:Array = [];
         for each (var n:int in Roulette.spot(index)[0])
         {
            numbers.push(pocketName(n));
         }
         var bet:String = numbers.length ? numbers.join(",") : shortName(index);
         return text(BET) + ": " + bet + " \n" + text(PAYOUT) + ": " + Roulette.odds(index) + ":1";
      }

      private static function pocketName(n:int) : String
      {
         return n == Roulette.DOUBLE_ZERO ? "00" : String(n);
      }

      private static function fill(n:int) : uint
      {
         if (n == 0 || n == Roulette.DOUBLE_ZERO)
         {
            return GREEN_FILL;
         }
         return Roulette.WHEEL.indexOf(n) % 2 == 0 ? RED_FILL : BLACK_FILL;
      }

      // The cells first, then the markers over their edges.
      private function board() : void
      {
         for (var pass:int = 0; pass < 2; pass++)
         {
            for (var i:int = 0; i < Roulette.SPOTS; i++)
            {
               if (isMarker(i) == (pass == 1))
               {
                  spotSprite(i);
               }
            }
         }
      }

      private function spotSprite(index:int) : void
      {
         var box:Array = spotBox(index);
         var numbers:Array = Roulette.spot(index)[0];
         var straight:Boolean = Roulette.odds(index) == 35;
         var face:uint = straight ? fill(numbers[0]) : index == 151 ? RED_FILL : index == 152 ? BLACK_FILL : GREEN_FILL;
         var area:Sprite = new Sprite();
         area.graphics.lineStyle(isMarker(index) ? 1 : 2, Theme.color, isMarker(index) ? 0.6 : 1);
         area.graphics.beginFill(face, isMarker(index) ? 0.35 : 0.9);
         area.graphics.drawRect(0, 0, box[2], box[3]);
         area.graphics.endFill();
         area.x = box[0];
         area.y = box[1];
         area.buttonMode = true;
         area.mouseChildren = false;
         if (!isMarker(index))
         {
            var caption:TextField = Text.label(area, 6, box[3] / 2 - 14, 20);
            caption.text = straight ? pocketName(numbers[0]) : shortName(index);
         }
         area.addEventListener(MouseEvent.CLICK, function(e:Event) : void { toggle(index); });
         area.addEventListener(MouseEvent.ROLL_OVER, function(e:Event) : void { hover(index); });
         addChild(area);
      }

      private function shortName(index:int) : String
      {
         var names:Object = {147: FIRST_DOZEN, 150: SECOND_DOZEN, 153: THIRD_DOZEN, 149: EVEN, 151: RED, 152: BLACK,
                             154: ODD, 156: TWO_TO_ONE, 157: TWO_TO_ONE, 158: TWO_TO_ONE};
         return index == 148 ? "1-18" : index == 155 ? "19-36" : text(int(names[index]));
      }

      private function hover(index:int) : void
      {
         var action:String = table.bets[index] != undefined ? text(REMOVE_BET) : text(PLACE_BET);
         info.text = label(index) + "\n" + action;
      }

      // A click: the current chips onto an empty spot, or the bet off a spot that has one (FNV's Place and Remove Bet).
      private function toggle(index:int) : void
      {
         if (table.bets[index] != undefined)
         {
            table.remove(index);
         }
         else
         {
            table.place(index);
         }
         hover(index);
         update();
      }

      // ---- The wheel

      private function wheel() : void
      {
         for (var i:int = 0; i < Roulette.POCKETS; i++)
         {
            var n:int = Roulette.WHEEL[i];
            var angle:Number = i / Roulette.POCKETS * Math.PI * 2 - Math.PI / 2;
            var pocket:Sprite = new Sprite();
            pocket.graphics.lineStyle(1, Theme.color, 0.5);
            pocket.graphics.beginFill(fill(n));
            pocket.graphics.drawCircle(0, 0, 11);
            pocket.graphics.endFill();
            pocket.x = WHEEL_X + Math.cos(angle) * WHEEL_R;
            pocket.y = WHEEL_Y + Math.sin(angle) * WHEEL_R;
            var caption:TextField = Text.label(pocket, -9, -9, 11);
            caption.text = pocketName(n);
            addChild(pocket);
            pockets.push(pocket);
         }
         drawn = Text.label(this, WHEEL_X - 30, WHEEL_Y - 30, 48);
      }

      private function showResult(n:int) : void
      {
         for (var i:int = 0; i < pockets.length; i++)
         {
            pockets[i].scaleX = pockets[i].scaleY = Roulette.WHEEL[i] == n ? 1.6 : 1;
         }
         drawn.text = pocketName(n);
         history.unshift(pocketName(n));
         history.length = Math.min(history.length, 10);
         past.text = history.join("  ");
      }

      // ---- Bets and the spin

      private function update() : void
      {
         status.text = text(CHIPS) + table.chips + "\n" + text(CURRENT_BET) + table.bet + "\n" + text(TOTAL_BET)
                     + table.total() + "\n" + text(EARNINGS) + earnings;
         for (var key:String in chipsShown)
         {
            removeChild(chipsShown[key]);
         }
         chipsShown = {};
         for each (var index:int in table.order)
         {
            chipsShown[index] = chipStack(index, int(table.bets[index]));
         }
      }

      private function chipStack(index:int, amount:int) : Sprite
      {
         var box:Array = spotBox(index);
         var chip:Sprite = new Sprite();
         chip.graphics.lineStyle(2, Theme.color);
         chip.graphics.beginFill(0xC8A040);
         chip.graphics.drawCircle(0, 0, 14);
         chip.graphics.endFill();
         chip.x = box[0] + box[2] / 2;
         chip.y = box[1] + box[3] / 2;
         chip.mouseEnabled = false;
         chip.mouseChildren = false;
         Text.label(chip, -12, -11, 14).text = String(amount);
         addChild(chip);
         return chip;
      }

      private function betUp(e:Event = null) : void
      {
         table.betUp();
         update();
      }

      private function betDown(e:Event = null) : void
      {
         table.lower();
         update();
      }

      private function spin(e:Event = null) : void
      {
         var out:Array = table.spin();
         if (out == null)
         {
            return;
         }
         var net:int = out[1];
         showResult(out[0]);
         earnings += net;
         var amount:String = " " + Math.abs(net) + " " + text(CHIP) + text(PLURAL);
         if (net > 0)
         {
            result.text = (luck > Roulette.FAIR_LUCK ? text(LUCKY_WIN) : text(YOU_WIN)) + amount;
         }
         else
         {
            result.text = net < 0 ? text(YOU_LOSE) + amount : text(BREAK_EVEN);
         }
         update();
         send("F3NV_CasinoRound", net);
      }

      private function exit(e:Event = null) : void
      {
         send("F3NV_CasinoClose");
      }
   }
}
