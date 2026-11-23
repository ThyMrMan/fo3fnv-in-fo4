package f3nv.casino
{
   import f3ui.Draw;
   import f3ui.Input;
   import f3ui.Text;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.text.TextField;

   // Lucky Horseshoes on the blackjack table's layout (BlackjackScreen's felt, rows and card sizes): Festus's cards
   // where the dealer's go, the player's below, each total beside; Draw and Hold while playing (Festus's blue and red
   // buttons), Play Again and Exit between games (his yellow Quit leaves at any time, as Exit here). Cards are drawn
   // plain (FNV shows none). A finished game is sent as `send("F3NV_HorseshoesResult", won)`; Papyrus gives the reward.
   // See docs/fork/fo4_casino_plan.md#lucky-horseshoes
   public class HorseshoesScreen extends Sprite
   {
      // Indexes into the texts Papyrus passes (F3NV_Casino.psc's HorseshoesTexts).
      public static const TITLE:int = 0;
      public static const DRAW:int = 1;
      public static const HOLD:int = 2;
      public static const PLAY_AGAIN:int = 3;
      public static const EXIT:int = 4;
      public static const YOU_WIN:int = 5;
      public static const YOU_LOSE:int = 6;
      public static const LUCKY:int = 7;
      public static const YOU:int = 8;

      public static const CARD_FACE:uint = 0xF4F1E8;
      public static const CARD_INK:uint = 0x202020;
      public static const NAMES:Array = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

      private var send:Function;
      private var texts:Array;
      private var game:Horseshoes;
      private var dealer:String;
      private var cardsShown:Sprite;
      private var totals:Array = [];
      private var result:TextField;
      private var playRow:Array = [];
      private var endRow:Array = [];

      public function HorseshoesScreen(sender:Function)
      {
         super();
         send = sender;
      }

      // Papyrus's data (F3NV_Casino.OpenHorseshoesMenu): the dealer's name, a seed and the texts.
      public function open(name:String, seed:uint, menuTexts:Array) : void
      {
         texts = menuTexts;
         dealer = name;
         game = new Horseshoes(new Rng(seed));
         Draw.panel(this, 40, 80, 1200, 420, 0);
         graphics.beginFill(BlackjackScreen.FELT, 0.6);
         graphics.drawRect(40, 80, 1200, 420);
         graphics.endFill();
         Text.label(this, 40, 30, 32).text = text(TITLE);
         cardsShown = new Sprite();
         addChild(cardsShown);
         var x:Number = BlackjackScreen.HAND_X[0];
         totals = [Text.label(this, x, 466, 22), Text.label(this, x, 250, 22)];
         result = Text.label(this, 480, 530, 28);
         playRow = [Draw.button(this, text(DRAW), 40, 620, draw, 190), Draw.button(this, text(HOLD), 245, 620, hold, 190)];
         endRow = [Draw.button(this, text(PLAY_AGAIN), 40, 620, again, 190)];
         Draw.button(this, text(EXIT), 655, 620, exit, 190);
         update();
      }

      // Input's actions: Accept draws, or starts again after a game; Right holds.
      public function control(action:String) : Boolean
      {
         if (action == Input.ACCEPT)
         {
            if (game.result == Horseshoes.PLAYING) { draw(); } else { again(); }
         }
         else if (action == Input.RIGHT)
         {
            hold();
         }
         else
         {
            return false;
         }
         return true;
      }

      // The hint bar's hints: draw, hold, exit.
      public function hints() : Array
      {
         return [[Input.ACCEPT, text(DRAW)], [Input.RIGHT, text(HOLD)], [Input.BACK, text(EXIT)]];
      }

      private function text(index:int) : String
      {
         return index < texts.length ? String(texts[index]) : "";
      }

      private function showHand(hand:Array, y:Number) : void
      {
         for (var i:int = 0; i < hand.length; i++)
         {
            var x:Number = BlackjackScreen.HAND_X[0] + i * BlackjackScreen.CARD_STEP;
            cardsShown.graphics.lineStyle(2, CARD_INK);
            cardsShown.graphics.beginFill(CARD_FACE);
            cardsShown.graphics.drawRoundRect(x, y, BlackjackScreen.CARD_W, BlackjackScreen.CARD_H, 12, 12);
            cardsShown.graphics.endFill();
            var value:TextField = Text.label(cardsShown, x + 8, y + 6, 28);
            value.text = NAMES[hand[i][0]];
            value.textColor = CARD_INK;
         }
      }

      private function update() : void
      {
         removeChild(cardsShown);
         cardsShown = new Sprite();
         addChildAt(cardsShown, 1);
         showHand(game.hands[Horseshoes.FESTUS], BlackjackScreen.DEALER_Y);
         showHand(game.hands[Horseshoes.PLAYER], BlackjackScreen.HAND_Y);
         Text.show(totals[Horseshoes.PLAYER], text(YOU) + ": " + game.totals[Horseshoes.PLAYER]);
         Text.show(totals[Horseshoes.FESTUS], dealer + ": " + game.totals[Horseshoes.FESTUS]);
         var playing:Boolean = game.result == Horseshoes.PLAYING;
         for each (var button:Sprite in playRow)
         {
            button.visible = playing;
         }
         endRow[0].visible = !playing;
      }

      private function draw(e:Event = null) : void
      {
         if (game.result == Horseshoes.PLAYING)
         {
            ended(game.draw());
         }
      }

      private function hold(e:Event = null) : void
      {
         if (game.result == Horseshoes.PLAYING)
         {
            ended(game.hold());
         }
      }

      private function again(e:Event = null) : void
      {
         game.newGame();
         Text.show(result, "");
         update();
      }

      // After a turn: Lucky Horseshoes is called out; a finished game shows FNV's result text and goes to Papyrus.
      private function ended(state:int) : void
      {
         Text.show(result, game.nudged ? text(LUCKY) : "");
         if (state != Horseshoes.PLAYING)
         {
            Text.show(result, state == Horseshoes.WON ? text(YOU_WIN) : text(YOU_LOSE));
            send("F3NV_HorseshoesResult", state == Horseshoes.WON);
         }
         update();
      }

      private function exit(e:Event = null) : void
      {
         send("F3NV_CasinoClose");
      }
   }
}
