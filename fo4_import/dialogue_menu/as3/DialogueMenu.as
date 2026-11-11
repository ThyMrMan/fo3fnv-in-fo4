package
{
   import Shared.AS3.BSButtonHint;
   import Shared.AS3.BSButtonHintData;
   import Shared.GlobalFunc;
   import Shared.IMenu;
   import flash.display.Graphics;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.KeyboardEvent;
   import flash.events.MouseEvent;
   import flash.geom.Rectangle;
   import flash.text.TextField;
   import flash.text.TextFormat;

   // F3NV's dialogue menu, compiled over the game's own DialogueMenu class (fo4_import/dialogue_menu/movie.py).
   // The game drives it as before (SetButtonText, ShowButtonHelp, BGSCodeObj); with F3NV.dll it shows one scrolling
   // list instead of the four buttons: F3NV.dll's options for its menus (any number), else the game's four.
   // See docs/fork/fo4_dialogue_menu_plan.md#test-build
   public class DialogueMenu extends IMenu
   {
      public var FadeHolder_mc:MovieClip;

      public var BGSCodeObj:Object;

      private var Buttons:Vector.<BSButtonHint>;

      private var ButtonAnimators:Vector.<MovieClip>;

      private var ButtonData:Vector.<BSButtonHintData>;

      private var LastPressedButtonIndex:uint;

      private var _ButtonsShown:Boolean;

      // f4se.plugins.F3NV: GetDialogueOptions, SelectDialogueOption, Log.
      private var dll:Object = null;

      // The game's text per button (0 Positive, 1 Negative, 2 Neutral, 3 Question).
      private var gameTexts:Array = ["", "", "", ""];

      // The list: {text, said, ours, index}; index is F3NV.dll's option or the game's button.
      private var entries:Array = [];

      private var selected:int = 0;

      private var top:int = 0;

      private var list:Sprite;

      private var rows:Vector.<TextField>;

      private var listShown:Boolean = false;

      private var picking:Boolean = false;

      // The list was tried once: a failed try leaves the game's own buttons from then on.
      private var tried:Boolean = false;

      private var seen:Object = {};

      private static const ROWS:int = 7;

      private static const ROW_HEIGHT:Number = 30;

      // The selection mark's column, left of the text.
      private static const MARK:Number = 18;

      // The four buttons' area in the list host's space, taken before their art is hidden.
      private var area:Rectangle;

      // The game's buttons in the order its menu reads them: Question, Positive, Negative, Neutral.
      private static const BUTTON_ORDER:Array = [3, 0, 1, 2];

      private static const KEY_ENTER:uint = 13;

      private static const KEY_E:uint = 69;

      private static const KEY_W:uint = 87;

      private static const KEY_S:uint = 83;

      private static const KEY_1:uint = 49;

      private static const KEY_9:uint = 57;

      // Only what the game's own constructor does: it runs inside the game's LoadMovie, where a TextField made in
      // code crashed the game (played 2026-11-10). The list is made later, on the first ShowButtonHelp.
      public function DialogueMenu()
      {
         super();
         addFrameScript(0, this.frame1, 4, this.frame5);
         this.visible = false;
         this.BGSCodeObj = new Object();
         this.Buttons = new Vector.<BSButtonHint>();
         this.Buttons.push(this.FadeHolder_mc.Positive.Holder.Button_mc);
         this.Buttons.push(this.FadeHolder_mc.Negative.Holder.Button_mc);
         this.Buttons.push(this.FadeHolder_mc.Neutral.Holder.Button_mc);
         this.Buttons.push(this.FadeHolder_mc.Question.Holder.Button_mc);
         this.ButtonAnimators = new Vector.<MovieClip>();
         this.ButtonAnimators.push(this.FadeHolder_mc.Positive);
         this.ButtonAnimators.push(this.FadeHolder_mc.Negative);
         this.ButtonAnimators.push(this.FadeHolder_mc.Neutral);
         this.ButtonAnimators.push(this.FadeHolder_mc.Question);
         this.ButtonData = new Vector.<BSButtonHintData>();
         this.ButtonData.push(new BSButtonHintData("", "Down", "PSN_A", "Xenon_A", 1, this.onPositiveRelease));
         this.ButtonData.push(new BSButtonHintData("", "Right", "PSN_B", "Xenon_B", 1, this.onNegativeRelease));
         this.ButtonData.push(new BSButtonHintData("", "Left", "PSN_X", "Xenon_X", 0, this.onNeutralRelease));
         this.ButtonData.push(new BSButtonHintData("", "Up", "PSN_Y", "Xenon_Y", 0, this.onQuestionRelease));
         this.LastPressedButtonIndex = uint.MAX_VALUE;
         this._ButtonsShown = false;
         this.FadeHolder_mc.SpeechChallengeAnim_mc.mouseEnabled = false;
         this.FadeHolder_mc.SpeechChallengeAnim_mc.mouseChildren = false;
         this.FadeHolder_mc.SpeechChallengeAnim_mc.addEventListener("OnSpeechChallengeAnimComplete", this.OnSpeechChallengeAnimComplete);
      }

      private function onPositiveRelease() : void
      {
         this.onButtonRelease(0);
      }

      private function onNegativeRelease() : void
      {
         this.onButtonRelease(1);
      }

      private function onNeutralRelease() : void
      {
         this.onButtonRelease(2);
      }

      private function onQuestionRelease() : void
      {
         this.onButtonRelease(3);
      }

      override protected function onSetSafeRect() : void
      {
         GlobalFunc.LockToSafeRect(this, "BC", SafeX, SafeY);
      }

      public function onCodeObjCreate() : *
      {
         this.BGSCodeObj.registerObjects(this.FadeHolder_mc.Positive, this.FadeHolder_mc.Negative, this.FadeHolder_mc.Neutral, this.FadeHolder_mc.Question, this.FadeHolder_mc.SpeechChallengeAnim_mc);
         var i:int = 0;
         while(i < this.Buttons.length)
         {
            this.Buttons[i].ButtonHintData = this.ButtonData[i];
            i++;
         }
      }

      // F4SE's object, once the movie has loaded: F3NV.dll's natives switch the list on at the next ShowButtonHelp.
      public function onF4SEObjCreated(f4se:Object) : void
      {
         this.dll = f4se != null && f4se.plugins != null && f4se.plugins.F3NV != null ? f4se.plugins.F3NV : null;
         this.log("menu ready");
      }

      public function SetButtonText(button:uint, text:String) : *
      {
         this.ButtonData[button].ButtonText = text.toUpperCase();
         this.gameTexts[button] = text;
         if(button == 3)
         {
            this.visible = true;
            this.refresh();
         }
      }

      public function ShowButtonHelp() : *
      {
         var i:int = 0;
         while(!this._ButtonsShown && i < this.Buttons.length)
         {
            this.Buttons[i].bButtonPressed = false;
            this.ButtonAnimators[i].gotoAndPlay("showButton");
            i++;
         }
         this._ButtonsShown = true;
         this.picking = false;
         this.listShown = this.dll != null && this.ensureList();
         this.refresh();
      }

      // The list, tried once: an error while making it leaves the game's own four buttons (they are hidden last).
      // No try/catch and no uint counters: only bytecode the game has been seen to run (see movie.py).
      private function ensureList() : Boolean
      {
         if(this.list == null && !this.tried)
         {
            this.tried = true;
            this.log("making list");
            this.makeList();
         }
         return this.list != null;
      }

      public function HideButtonHelp() : *
      {
         var i:int = 0;
         while(this._ButtonsShown && i < this.ButtonAnimators.length)
         {
            if(i == this.LastPressedButtonIndex)
            {
               this.Buttons[i].bButtonPressed = true;
               this.ButtonAnimators[i].gotoAndPlay("slowHideButton");
            }
            else
            {
               this.ButtonAnimators[i].gotoAndPlay("hideButton");
            }
            i++;
         }
         this._ButtonsShown = false;
         this.listShown = false;
         if(this.list != null)
         {
            this.list.visible = false;
         }
      }

      public function EnableMenu() : *
      {
         gotoAndPlay("showMenu");
      }

      public function DisableMenu() : *
      {
         gotoAndPlay("hideMenu");
      }

      // ---- The list ----

      // The list's rows, built once the movie is up (never in the constructor). The game draws this menu only
      // inside the objects it registered (registerObjects), so the list lives in the Question button's holder,
      // laid over the four buttons' area, and each holder's own button art is hidden (played 2026-11-10).
      private function makeList() : void
      {
         var host:MovieClip = this.FadeHolder_mc.Question;
         this.area = this.FadeHolder_mc.getBounds(host);
         var list:Sprite = new Sprite();
         list.visible = false;
         this.rows = new Vector.<TextField>();
         var format:TextFormat = new TextFormat("$MAIN_Font_Bold", 20, 0xFFFFFF);
         var i:int = 0;
         while(i < ROWS)
         {
            var row:TextField = new TextField();
            row.embedFonts = true;
            row.defaultTextFormat = format;
            row.selectable = false;
            row.multiline = false;
            row.wordWrap = false;
            row.autoSize = "left";
            row.x = MARK;
            row.y = i * ROW_HEIGHT;
            row.name = String(i);
            row.addEventListener(MouseEvent.MOUSE_OVER, this.onRowOver);
            row.addEventListener(MouseEvent.CLICK, this.onRowClick);
            list.addChild(row);
            this.rows.push(row);
            i++;
         }
         list.addEventListener(MouseEvent.MOUSE_WHEEL, this.onWheel);
         host.addChild(list);
         if(stage != null)
         {
            stage.addEventListener(KeyboardEvent.KEY_DOWN, this.onKeyDown);
            stage.addEventListener(KeyboardEvent.KEY_UP, this.onKeyUp);
         }
         this.list = list;
         i = 0;
         while(i < this.ButtonAnimators.length)
         {
            this.ButtonAnimators[i].Holder.visible = false;
            i++;
         }
         this.log("list made");
      }

      // The list's entries again: F3NV.dll's options when it has any, else the game's buttons with text.
      private function refresh() : void
      {
         if(this.list != null)
         {
            this.fill();
            this.draw();
         }
      }

      private function fill() : void
      {
         this.entries = [];
         var options:Object = this.dll.GetDialogueOptions();
         var i:int = 0;
         if(options != null && options.length > 0)
         {
            while(i < options.length)
            {
               this.entries.push({"text":options[i].text, "said":options[i].said, "ours":true, "index":i});
               i++;
            }
         }
         else
         {
            while(i < BUTTON_ORDER.length)
            {
               var button:int = BUTTON_ORDER[i];
               if(this.gameTexts[button] != null && this.gameTexts[button] != "")
               {
                  this.entries.push({"text":this.gameTexts[button], "said":false, "ours":false, "index":button});
               }
               i++;
            }
         }
         this.selected = Math.max(0, Math.min(this.selected, this.entries.length - 1));
      }

      private function draw() : void
      {
         var count:int = Math.min(ROWS, this.entries.length);
         this.top = Math.max(0, Math.min(this.top, this.entries.length - count));
         if(this.selected < this.top)
         {
            this.top = this.selected;
         }
         if(this.selected >= this.top + count)
         {
            this.top = this.selected - count + 1;
         }
         var g:Graphics = this.list.graphics;
         g.clear();
         var wide:Number = 0;
         var i:int = 0;
         while(i < ROWS)
         {
            var row:TextField = this.rows[i];
            var at:int = this.top + i;
            row.visible = i < count;
            if(i < count)
            {
               var entry:Object = this.entries[at];
               row.text = String(entry.text).toUpperCase();
               row.alpha = at == this.selected ? 1 : (entry.said ? 0.35 : 0.6);
               wide = Math.max(wide, row.width);
               if(at == this.selected)
               {
                  g.beginFill(0xFFFFFF, 1);
                  g.drawRect(0, i * ROW_HEIGHT + ROW_HEIGHT / 2 - 4, 8, 8);
                  g.endFill();
               }
            }
            i++;
         }
         if(this.entries.length > count)
         {
            g.beginFill(0xFFFFFF, 0.6);
            g.drawRect(MARK + wide + 10, count * ROW_HEIGHT * this.top / this.entries.length, 3, count * ROW_HEIGHT * count / this.entries.length);
            g.endFill();
         }
         this.list.x = this.area.x + (this.area.width - MARK - wide) / 2;
         this.list.y = this.area.y + this.area.height - count * ROW_HEIGHT;
         this.list.visible = this.listShown && count > 0;
         if(this.list.visible && stage != null)
         {
            stage.focus = this.list;
         }
      }

      private function move(by:int) : void
      {
         if(this.entries.length == 0)
         {
            return;
         }
         this.selected = (this.selected + by + this.entries.length) % this.entries.length;
         this.draw();
      }

      // Pick list entry `at`: F3NV.dll's option, or the game's button.
      private function pick(at:int) : void
      {
         if(!this.listShown || this.picking || at < 0 || at >= this.entries.length)
         {
            return;
         }
         var entry:Object = this.entries[at];
         this.picking = true;
         if(entry.ours)
         {
            var taken:Boolean = this.dll.SelectDialogueOption(entry.index);
            this.log("picked " + at + (taken ? "" : " (refused)"));
            this.picking = taken;
         }
         else
         {
            this.onButtonRelease(entry.index);
         }
      }

      private function onRowOver(e:MouseEvent) : void
      {
         var at:int = this.top + int(e.currentTarget.name);
         if(at != this.selected && at < this.entries.length)
         {
            this.selected = at;
            this.draw();
         }
      }

      private function onRowClick(e:MouseEvent) : void
      {
         this.pick(this.top + int(e.currentTarget.name));
      }

      private function onWheel(e:MouseEvent) : void
      {
         this.move(e.delta > 0 ? -1 : 1);
      }

      private function onKeyDown(e:KeyboardEvent) : void
      {
         if(!this.listShown)
         {
            return;
         }
         this.seenOnce("key " + e.keyCode);
         if(e.keyCode == KEY_W)
         {
            this.move(-1);
         }
         else if(e.keyCode == KEY_S)
         {
            this.move(1);
         }
      }

      private function onKeyUp(e:KeyboardEvent) : void
      {
         if(!this.listShown)
         {
            return;
         }
         if(e.keyCode == KEY_ENTER || e.keyCode == KEY_E)
         {
            this.pick(this.selected);
         }
         else if(e.keyCode >= KEY_1 && e.keyCode <= KEY_9)
         {
            this.pick(this.top + int(e.keyCode - KEY_1));
         }
      }

      // The game's input: arrows and D-pad move (Quickkey), A or Accept picks; the game's four dialogue keys are
      // taken while the list is up so none picks a button behind it.
      public function ProcessUserEvent(name:String, down:Boolean) : Boolean
      {
         if(!this.listShown)
         {
            return this.ProcessButtons(name, down);
         }
         this.seenOnce("event " + name);
         if(down && name == "QuickkeyUp")
         {
            this.move(-1);
         }
         else if(down && name == "QuickkeyDown")
         {
            this.move(1);
         }
         else if(!down && (name == "Accept" || name == "Activate" || (name == "MultiActivateA" && uiPlatform != 0)))
         {
            this.pick(this.selected);
         }
         else if(name.indexOf("MultiActivate") != 0 && name.indexOf("Quickkey") != 0)
         {
            return false;
         }
         return true;
      }

      // The game's four buttons, as its own menu takes them.
      private function ProcessButtons(name:String, down:Boolean) : Boolean
      {
         var names:Array = ["MultiActivateA", "MultiActivateB", "MultiActivateX", "MultiActivateY"];
         var button:int = names.indexOf(name);
         if(!this._ButtonsShown || button < 0)
         {
            return false;
         }
         if(down)
         {
            this.Buttons[button].bButtonPressed = true;
         }
         else
         {
            this.onButtonRelease(button);
         }
         return true;
      }

      private function onButtonRelease(button:uint) : void
      {
         if(button < this.Buttons.length)
         {
            this.LastPressedButtonIndex = button;
            this.Buttons[button].bButtonPressed = false;
            this.BGSCodeObj.onButtonRelease(button);
         }
      }

      private function seenOnce(what:String) : void
      {
         if(this.seen[what] == null)
         {
            this.seen[what] = true;
            this.log(what);
         }
      }

      private function log(text:String) : void
      {
         if(this.dll != null)
         {
            this.dll.Log(text);
         }
      }

      public function PlaySpeechChallengeAnim() : *
      {
         this.FadeHolder_mc.SpeechChallengeAnim_mc.gotoAndPlay("startAnim");
      }

      public function OnSpeechChallengeAnimComplete() : *
      {
         this.BGSCodeObj.OnSpeechChallengeAnimComplete();
      }

      internal function frame1() : *
      {
         stop();
      }

      internal function frame5() : *
      {
         stop();
      }
   }
}
