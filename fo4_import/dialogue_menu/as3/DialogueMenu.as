package
{
   import Shared.AS3.BSButtonHint;
   import Shared.AS3.BSButtonHintData;
   import Shared.GlobalFunc;
   import Shared.IMenu;
   import flash.display.DisplayObject;
   import flash.display.Graphics;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.KeyboardEvent;
   import flash.events.MouseEvent;
   import flash.geom.Point;
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

      private static const ROWS:int = 5;

      // The box's fixed width and its bottom's height above the screen's safe bottom (it stays under the speaker's
      // face); the padding, the scroll marks' column inside the box's left edge, a row's text width (a longer prompt
      // wraps), the gap between rows and the outline's thickness. The box has no fill of its own: the game's shaded
      // background (F3NV.dll ShadeList) is its backdrop, since a fill in a HUD-colored holder draws opaque.
      private static const BOX_WIDTH:Number = 640;

      private static const BOTTOM:Number = 36;

      private static const PAD:Number = 10;

      private static const GUTTER:Number = 24;

      private static const TEXT_WIDTH:Number = BOX_WIDTH - GUTTER - 3 * PAD;

      private static const GAP:Number = 6;

      private static const LINE:Number = 2;

      // The game's shaded background is on behind the holder.
      private var shaded:Boolean = false;

      // Frames to look again for F3NV.dll's options when a menu first shows none (its scene may not be set yet).
      private static const RETRIES:int = 30;

      private var retries:int = 0;

      // The list entry that leaves the talk (LeaveDialogue), shown when a menu has no options of ours.
      private static const LEAVE:int = -1;

      private static const KEY_TAB:uint = 9;

      private static const KEY_ESCAPE:uint = 27;

      private static const KEY_UP:uint = 38;

      private static const KEY_DOWN:uint = 40;

      // The last wheel event was a press: its release does not move the list again.
      private var wheelDown:Boolean = false;

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
         this.ButtonData[button].ButtonText = this.list == null ? text.toUpperCase() : "";
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
         this.retries = RETRIES;
         this.refresh();
         this.log("menu shown: " + this.entries.length + " entries");
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
            this.shade(false);
         }
         this.log("menu hidden");
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
      // placed near the screen's safe bottom (draw), and each holder's own button art is hidden and its text
      // emptied, so the Question holder's bounds (the shaded background's size) are the box's (played 2026-11-10).
      private function makeList() : void
      {
         var host:MovieClip = this.FadeHolder_mc.Question;
         var list:Sprite = new Sprite();
         list.visible = false;
         this.rows = new Vector.<TextField>();
         var format:TextFormat = new TextFormat("$MAIN_Font_Bold", 18, 0xFFFFFF);
         format.leading = -2;
         var i:int = 0;
         while(i < ROWS)
         {
            var row:TextField = new TextField();
            row.embedFonts = true;
            row.defaultTextFormat = format;
            row.selectable = false;
            row.multiline = true;
            row.wordWrap = true;
            row.width = TEXT_WIDTH;
            row.autoSize = "left";
            row.x = GUTTER + 2 * PAD;
            row.name = String(i);
            row.addEventListener(MouseEvent.MOUSE_OVER, this.onRowOver);
            row.addEventListener(MouseEvent.CLICK, this.onRowClick);
            list.addChild(row);
            this.rows.push(row);
            i++;
         }
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
            this.ButtonData[i].ButtonText = "";
            i++;
         }
         this.log("list made");
      }

      // The list's entries again: F3NV.dll's options when it has any, else the game's buttons with text and our
      // [Leave], so a menu without options of ours never leaves the talk stuck.
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
            this.log("no options of ours: the game's " + this.entries.length + " (" + this.gameTexts.join(" | ") + "), and [Leave]");
            this.entries.push({"text":"[Leave]", "said":false, "ours":false, "index":LEAVE});
            if(this.listShown && this.retries > 0)
            {
               this.addEventListener(Event.ENTER_FRAME, this.lookAgain);
            }
         }
         this.selected = Math.max(0, Math.min(this.selected, this.entries.length - 1));
      }

      // Each frame for RETRIES frames after a menu showed none of ours: ask F3NV.dll again, and show its options
      // once it has some, before the game's own buttons are left in place.
      private function lookAgain(e:Event) : void
      {
         this.retries = this.retries - 1;
         var options:Object = this.listShown ? this.dll.GetDialogueOptions() : null;
         var found:Boolean = options != null && options.length > 0;
         if(found || !this.listShown || this.retries <= 0)
         {
            this.removeEventListener(Event.ENTER_FRAME, this.lookAgain);
            this.log(found ? "options of ours after " + (RETRIES - this.retries) + " frames" : "still none of ours");
            this.retries = 0;
         }
         if(found)
         {
            this.refresh();
         }
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
         var y:Number = PAD + LINE;
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
               row.alpha = at == this.selected ? 1 : (entry.said ? 0.45 : 0.75);
               row.y = y;
               y = y + row.height + GAP;
            }
            i++;
         }
         var high:Number = y - GAP + PAD + LINE;
         this.paint(count, high);
         var host:DisplayObject = this.list.parent;
         var middle:Point = host.parent.globalToLocal(this.localToGlobal(new Point(0, -BOTTOM - high / 2)));
         host.x = middle.x;
         host.y = middle.y;
         var base:Point = host.globalToLocal(this.localToGlobal(new Point(0, -BOTTOM)));
         this.list.x = base.x - BOX_WIDTH / 2;
         this.list.y = base.y - high;
         this.list.visible = this.listShown && count > 0;
         this.shade(this.list.visible);
         if(this.list.visible && stage != null)
         {
            stage.focus = this.list;
         }
      }

      // The box under `count` rows, `high` in all and always BOX_WIDTH wide, drawn as FNV draws its own: an
      // outline, the selected row in an outline of its own, and, when the list scrolls, an up and a down mark joined
      // by a line in the box's left column (dim where there is nothing more that way). White is tinted to the HUD
      // color by the game; the backdrop is the game's shaded background (shade).
      private function paint(count:int, high:Number) : void
      {
         var g:Graphics = this.list.graphics;
         g.clear();
         this.frame(g, 0, 0, BOX_WIDTH, high, 0.9);
         var row:TextField = this.rows[this.selected - this.top];
         this.frame(g, GUTTER + PAD, row.y - 3, BOX_WIDTH - GUTTER - 2 * PAD, row.height + 6, 0.9);
         if(this.entries.length > count)
         {
            var x:Number = PAD + GUTTER / 2;
            g.beginFill(0xFFFFFF, 0.5);
            g.drawRect(x - LINE / 2, PAD + 12, LINE, high - 2 * PAD - 24);
            g.endFill();
            this.arrow(g, x, PAD, -1, this.top > 0 ? 1 : 0.3);
            this.arrow(g, x, high - PAD, 1, this.top + count < this.entries.length ? 1 : 0.3);
         }
      }

      // The game's shaded background behind the list's holder, on or off (F3NV.dll; once per change).
      private function shade(on:Boolean) : void
      {
         if(on != this.shaded)
         {
            this.shaded = on;
            var done:Boolean = this.dll.ShadeList(on);
            this.seenOnce("shaded background " + (on ? "on" : "off") + (done ? "" : " refused"));
         }
      }

      // An outline LINE thick around the `wide` by `high` box at (`x`, `y`), as four strips that do not overlap.
      private function frame(g:Graphics, x:Number, y:Number, wide:Number, high:Number, alpha:Number) : void
      {
         g.beginFill(0xFFFFFF, alpha);
         g.drawRect(x, y, wide, LINE);
         g.drawRect(x, y + high - LINE, wide, LINE);
         g.drawRect(x, y + LINE, LINE, high - 2 * LINE);
         g.drawRect(x + wide - LINE, y + LINE, LINE, high - 2 * LINE);
         g.endFill();
      }

      // A small scroll mark centered on `x`, its tip at `y`, pointing up (-1) or down (1).
      private function arrow(g:Graphics, x:Number, y:Number, way:int, alpha:Number) : void
      {
         g.beginFill(0xFFFFFF, alpha);
         g.moveTo(x - 8, y - way * 8);
         g.lineTo(x + 8, y - way * 8);
         g.lineTo(x, y);
         g.lineTo(x - 8, y - way * 8);
         g.endFill();
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
         if(entry.index == LEAVE)
         {
            this.leave("[Leave]");
         }
         else if(entry.ours)
         {
            var taken:Boolean = this.dll.SelectDialogueOption(entry.index);
            this.log("picked " + at + (taken ? "" : " (refused)"));
            this.picking = taken;
         }
         else
         {
            this.onButtonRelease(entry.index);
         }
         if(this.picking)
         {
            this.closeList();
         }
      }

      // Hide the list after a pick until the game shows the next menu (ShowButtonHelp), and give its input back.
      private function closeList() : void
      {
         this.listShown = false;
         this._ButtonsShown = false;
         this.list.visible = false;
         this.shade(false);
      }

      // End the talk through F3NV.dll (`why` names the key or entry, for the log).
      private function leave(why:String) : void
      {
         this.log("leave by " + why);
         this.dll.LeaveDialogue();
         this.closeList();
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

      private function onKeyDown(e:KeyboardEvent) : void
      {
         if(!this.listShown)
         {
            return;
         }
         this.seenOnce("key " + e.keyCode);
         if(e.keyCode == KEY_W || e.keyCode == KEY_UP)
         {
            this.move(-1);
         }
         else if(e.keyCode == KEY_S || e.keyCode == KEY_DOWN)
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
         else if(e.keyCode == KEY_TAB || e.keyCode == KEY_ESCAPE)
         {
            this.leave("key " + e.keyCode);
         }
         else if(e.keyCode >= KEY_1 && e.keyCode <= KEY_9)
         {
            this.pick(this.top + int(e.keyCode - KEY_1));
         }
      }

      // The game's input: D-pad (Quickkey) and the mouse wheel (Zoom, kept from the camera by F3NV.dll) move, A,
      // Accept or Activate picks; the game's four dialogue keys are taken while the list is up so none picks a
      // button behind it.
      public function ProcessUserEvent(name:String, down:Boolean) : Boolean
      {
         if(!this.listShown)
         {
            return this.ProcessButtons(name, down);
         }
         this.seenOnce("event " + name + (down ? " down" : " up"));
         if(name == "ZoomIn" || name == "ZoomOut")
         {
            this.wheel(name == "ZoomIn" ? -1 : 1, down);
         }
         else if(down && name == "QuickkeyUp")
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
         else if(!down && (name == "Cancel" || (name == "MultiActivateB" && uiPlatform != 0)))
         {
            this.leave(name);
         }
         else if(name.indexOf("MultiActivate") != 0 && name.indexOf("Quickkey") != 0)
         {
            return false;
         }
         return true;
      }

      // One wheel step moves the list once, whether the game sends it as a press, a release, or both.
      private function wheel(by:int, down:Boolean) : void
      {
         if(down || !this.wheelDown)
         {
            this.move(by);
         }
         this.wheelDown = down;
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
