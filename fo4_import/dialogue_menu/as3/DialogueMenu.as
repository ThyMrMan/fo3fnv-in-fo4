package
{
   import f3ui.Bridge;
   import f3ui.Draw;
   import f3ui.HintBar;
   import f3ui.Input;
   import f3ui.ScrollList;
   import f3ui.Text;
   import flash.display.DisplayObject;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.geom.Point;
   import flash.geom.Rectangle;
   import flash.system.ApplicationDomain;
   import flash.utils.getDefinitionByName;

   // F3NV's dialogue menu, in a movie made only of our code (fo4_import/dialogue_menu/movie.py); the root
   // (DialogueMenuRoot) holds it at root.Menu_mc, where the game looks. The game drives it as its own menu
   // (SetButtonText, ShowButtonHelp, BGSCodeObj) and tints the five holders it registers with the HUD color. One
   // scrolling list: F3NV.dll's options for its menus (any number), else the game's four.
   // See docs/fork/fo4_dialogue_menu_plan.md#own-movie
   public class DialogueMenu extends MovieClip
   {
      public var FadeHolder_mc:MovieClip;

      public var BGSCodeObj:Object;

      // f4se.plugins.F3NV: GetDialogueOptions, SelectDialogueOption, Log, LeaveDialogue, ShadeList, TintFailed.
      private var dll:Object = null;

      // Keys and the game's controls as actions (made once the movie is on the stage), and the hints under the list.
      private var input:Input;

      private var hints:HintBar;

      // The safe-area margins the game gives (SetSafeRect).
      private var safeX:Number = 0;

      private var safeY:Number = 0;

      // The game's text per button (0 Positive, 1 Negative, 2 Neutral, 3 Question).
      private var gameTexts:Array = ["", "", "", ""];

      // The list: {text, said, dim, failed, ours, index}; index is F3NV.dll's option or the game's button, dim the
      // same as said (ScrollList draws a dim row fainter).
      private var entries:Array = [];

      // The box (its outline in its own graphics) holding the rows (f3ui's ScrollList) and the hints.
      private var list:Sprite;

      private var scroll:ScrollList;

      // The rows whose skill check fails, laid over the list inside the Negative holder, which F3NV.dll tints with
      // the game's own speech-challenge color (TintFailed) instead of the HUD color.
      private var failedRows:Sprite;

      private var listShown:Boolean = false;

      private var picking:Boolean = false;

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

      // The hint bar's text size and its gap under the box.
      private static const HINT_SIZE:int = 16;

      private static const HINT_GAP:Number = 8;

      // The game's buttons in the order its menu reads them: Question, Positive, Negative, Neutral.
      private static const BUTTON_ORDER:Array = [3, 0, 1, 2];

      // The holders the game registers and tints, in registerObjects' order.
      private static const HOLDERS:Array = ["Positive", "Negative", "Neutral", "Question", "SpeechChallengeAnim_mc"];

      // Only the holders: the constructor runs inside the game's LoadMovie, where a TextField made in code crashed
      // the game (played 2026-11-10). The list is made later, on the first ShowButtonHelp.
      public function DialogueMenu()
      {
         super();
         this.visible = false;
         this.BGSCodeObj = new Object();
         this.FadeHolder_mc = new MovieClip();
         for each (var name:String in HOLDERS)
         {
            var holder:MovieClip = new MovieClip();
            holder.name = name;
            this.FadeHolder_mc[name] = holder;
            this.FadeHolder_mc.addChild(holder);
         }
         addChild(this.FadeHolder_mc);
         addEventListener(Event.ADDED_TO_STAGE, this.onStage);
      }

      // No yellow focus frame round the menu. Input's keys and controls, with the dialogue's own: W and S move and E
      // picks, the D-pad comes as Quickkey controls, Activate picks, and on a gamepad A and B come as MultiActivate
      // (the keyboard sends those for its arrow and number keys).
      private function onStage(e:Event) : void
      {
         stage.stageFocusRect = false;
         this.input = new Input(stage, this.onAction);
         this.input.log = this.log;
         this.input.mapKey(87, Input.UP, "W");
         this.input.mapKey(83, Input.DOWN, "S");
         this.input.mapKey(69, Input.ACCEPT, "E");
         this.input.mapControl("QuickkeyUp", Input.UP);
         this.input.mapControl("QuickkeyDown", Input.DOWN);
         this.input.mapControl("Activate", Input.ACCEPT);
         this.input.mapControl("MultiActivateA", Input.ACCEPT, true);
         this.input.mapControl("MultiActivateB", Input.BACK, true);
         this.place();
      }

      public function onCodeObjCreate() : *
      {
         var h:MovieClip = this.FadeHolder_mc;
         this.BGSCodeObj.registerObjects(h.Positive, h.Negative, h.Neutral, h.Question, h.SpeechChallengeAnim_mc);
      }

      // F4SE's object, once the movie has loaded (F4SE calls root's direct children too): F3NV.dll's natives.
      public function onF4SEObjCreated(f4se:Object) : void
      {
         var bridge:Bridge = new Bridge();
         bridge.f4se = f4se;
         if(this.dll == null && bridge.natives("F3NV") != null)
         {
            this.dll = bridge.natives("F3NV");
            this.log("menu ready");
         }
      }

      public function SetPlatform(platform:uint, ps3Switch:Boolean) : *
      {
         if(this.input != null)
         {
            this.input.setPlatform(platform);
         }
      }

      public function SetSafeRect(x:Number, y:Number) : *
      {
         this.safeX = x;
         this.safeY = y;
         this.place();
      }

      // At the bottom center of the visible area, above the safe margin: Scaleform's visibleRect (the screen's
      // shape, wider than the stage on wide screens), else the stage.
      private function place() : void
      {
         if(stage == null)
         {
            return;
         }
         var area:Rectangle = new Rectangle(0, 0, stage.stageWidth, stage.stageHeight);
         var name:String = "scaleform.gfx.Extensions";
         if(ApplicationDomain.currentDomain.hasDefinition(name))
         {
            var rect:Rectangle = getDefinitionByName(name).visibleRect as Rectangle;
            area = rect != null ? rect : area;
         }
         var at:Point = this.parent.globalToLocal(new Point(area.x + area.width / 2, area.y + area.height - this.safeY));
         this.x = at.x;
         this.y = at.y;
      }

      public function SetButtonText(button:uint, text:String) : *
      {
         text = this.unescaped(text);
         this.gameTexts[button] = text;
         if(button == 3)
         {
            this.visible = true;
            this.refresh();
         }
      }

      public function ShowButtonHelp() : *
      {
         this.picking = false;
         this.listShown = this.ensureList();
         this.retries = RETRIES;
         this.refresh();
         this.log("menu shown: " + this.entries.length + " entries");
      }

      private function ensureList() : Boolean
      {
         if(this.list == null)
         {
            this.log("making list");
            this.makeList();
         }
         return this.list != null;
      }

      public function HideButtonHelp() : *
      {
         this.listShown = false;
         if(this.list != null)
         {
            this.list.visible = false;
            this.failedRows.visible = false;
            this.shade(false);
         }
         this.log("menu hidden");
      }

      public function EnableMenu() : *
      {
         this.FadeHolder_mc.visible = true;
      }

      public function DisableMenu() : *
      {
         this.FadeHolder_mc.visible = false;
      }

      // ---- The list ----

      // The list, built once the movie is up (never in the constructor). The game draws this menu only inside the
      // objects it registered (registerObjects), so the list lives in the Question button's holder, placed near the
      // screen's safe bottom (layout), and each holder's own button art is hidden and its text emptied, so the
      // Question holder's bounds (the shaded background's size) are the box's (played 2026-11-10). The rows are a
      // ScrollList with FNV's look: wrapping bold rows, the selected one outlined, said ones dim, scroll marks in
      // the box's left column; a failed skill check's row goes in the failed layer (overlay).
      private function makeList() : void
      {
         var host:MovieClip = this.FadeHolder_mc.Question;
         var list:Sprite = new Sprite();
         list.visible = false;
         this.failedRows = new Sprite();
         this.failedRows.visible = false;
         this.FadeHolder_mc.Negative.addChild(this.failedRows);
         var rows:ScrollList = new ScrollList();
         rows.rows = ROWS;
         rows.listWidth = BOX_WIDTH;
         rows.size = 18;
         rows.font = Text.BOLD;
         rows.leading = -2;
         rows.wrap = true;
         rows.gap = GAP;
         rows.textX = GUTTER + 2 * PAD;
         rows.textWidth = TEXT_WIDTH;
         rows.padTop = PAD + LINE;
         rows.padBottom = PAD + LINE;
         rows.marker = ScrollList.FRAME;
         rows.markerLeft = GUTTER + PAD;
         rows.markerRight = PAD;
         rows.marksX = PAD + GUTTER / 2;
         rows.marksInset = PAD;
         rows.upper = true;
         rows.alphas = [1, 0.75, 0.45];
         rows.layerOf = this.layerOf;
         rows.onPick = this.pick;
         rows.onDraw = this.layout;
         list.addChild(rows);
         this.scroll = rows;
         if(this.input != null)
         {
            this.hints = new HintBar(this.input, HINT_SIZE);
            this.hints.show([[Input.ACCEPT, "$F3NV_HINT_SELECT"], [Input.BACK, "$F3NV_HINT_LEAVE"]]);
            list.addChild(this.hints);
         }
         host.addChild(list);
         this.list = list;
         this.log("list made");
      }

      // A failed skill check's row goes in the failed layer, tinted apart; the rest stay in the list.
      private function layerOf(entry:Object) : Sprite
      {
         return entry.failed == true ? this.failedRows : null;
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
         var options:Object = this.dll != null ? this.dll.GetDialogueOptions() : null;
         var i:int = 0;
         if(options != null && options.length > 0)
         {
            while(i < options.length)
            {
               this.entries.push({"text":this.unescaped(String(options[i].text)), "said":options[i].said, "dim":options[i].said == true, "failed":options[i].failed == true, "ours":true, "index":i});
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
            if(this.dll != null)
            {
               this.entries.push({"text":"$F3NV_LEAVE", "said":false, "ours":false, "index":LEAVE});
            }
            if(this.dll != null && this.listShown && this.retries > 0)
            {
               this.addEventListener(Event.ENTER_FRAME, this.lookAgain);
            }
         }
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

      // The rows again (ScrollList keeps the selection in range and draws, then layout places the box).
      private function draw() : void
      {
         this.scroll.show(this.entries, this.scroll.selected);
      }

      // After each draw of the rows: the hints under the box, the box's outline (FNV's: white, tinted to the HUD
      // color by the game; the backdrop is the game's shaded background), the holder and box at the screen's safe
      // bottom, the list shown or hidden with its backdrop, and the failed layer laid over it.
      private function layout() : void
      {
         var count:int = Math.min(ROWS, this.entries.length);
         var high:Number = this.scroll.listHeight;
         var failed:int = 0;
         for(var i:int = this.scroll.top; i < this.scroll.top + count; i++)
         {
            failed = failed + (this.entries[i].failed == true ? 1 : 0);
         }
         if(this.hints != null)
         {
            this.hints.x = (BOX_WIDTH - this.hints.width) / 2;
            this.hints.y = high + HINT_GAP;
         }
         this.list.graphics.clear();
         Draw.outline(this.list.graphics, 0, 0, BOX_WIDTH, high, LINE, 0.9);
         var host:DisplayObject = this.list.parent;
         var middle:Point = host.parent.globalToLocal(this.localToGlobal(new Point(0, -BOTTOM - high / 2)));
         host.x = middle.x;
         host.y = middle.y;
         var base:Point = host.globalToLocal(this.localToGlobal(new Point(0, -BOTTOM)));
         this.list.x = base.x - BOX_WIDTH / 2;
         this.list.y = base.y - high;
         this.list.visible = this.listShown && count > 0;
         this.shade(this.list.visible);
         this.overlay(failed > 0);
         if(this.list.visible && stage != null)
         {
            stage.focus = this.list;
         }
      }

      // The game's shaded background behind the list's holder, on or off (F3NV.dll; once per change).
      private function shade(on:Boolean) : void
      {
         if(on != this.shaded && this.dll != null)
         {
            this.shaded = on;
            var done:Boolean = this.dll.ShadeList(on);
            this.seenOnce("shaded background " + (on ? "on" : "off") + (done ? "" : " refused"));
         }
      }

      // The failed rows' layer laid exactly over the list (same place and scale, from the list's corners), shown
      // with it, and their holder tinted after the game's own re-tint of it in SetButtonText (F3NV.dll TintFailed).
      private function overlay(any:Boolean) : void
      {
         var holder:DisplayObject = this.failedRows.parent;
         var left:Point = holder.globalToLocal(this.list.localToGlobal(new Point(0, 0)));
         var right:Point = holder.globalToLocal(this.list.localToGlobal(new Point(BOX_WIDTH, 0)));
         this.failedRows.x = left.x;
         this.failedRows.y = left.y;
         this.failedRows.scaleX = (right.x - left.x) / BOX_WIDTH;
         this.failedRows.scaleY = this.failedRows.scaleX;
         this.failedRows.visible = this.list.visible;
         if(any && this.list.visible)
         {
            var done:Boolean = this.dll.TintFailed();
            this.seenOnce("failed skill checks tinted" + (done ? "" : " refused"));
         }
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
         this.list.visible = false;
         this.failedRows.visible = false;
         this.shade(false);
      }

      // End the talk through F3NV.dll (`why` names the key or entry, for the log); without it, the game's own way.
      private function leave(why:String) : void
      {
         if(this.dll == null)
         {
            return;
         }
         this.log("leave by " + why);
         this.dll.LeaveDialogue();
         this.closeList();
      }

      // One action while the list is up (Input): back leaves; the rows take the rest (ScrollList: up and down move,
      // the wheel too, accept picks, a number key picks that row).
      private function onAction(action:String, digit:int) : Boolean
      {
         if(!this.listShown)
         {
            return false;
         }
         this.seenOnce("action " + action);
         if(action == Input.BACK && this.dll != null)
         {
            this.leave(action);
         }
         else if(!this.scroll.action(action, digit))
         {
            return false;
         }
         return true;
      }

      // The game's input, through Input; the game's four dialogue keys (MultiActivate, Quickkey) are taken while the
      // list is up so none picks a button behind it.
      public function ProcessUserEvent(name:String, down:Boolean) : Boolean
      {
         if(!this.listShown || this.input == null)
         {
            return false;
         }
         this.seenOnce("event " + name + (down ? " down" : " up"));
         return this.input.control(name, down) || name.indexOf("MultiActivate") == 0 || name.indexOf("Quickkey") == 0;
      }

      private function onButtonRelease(button:uint) : void
      {
         this.BGSCodeObj.onButtonRelease(button);
      }

      // A prompt as written: builds made for XDI escaped & < > in player lines, which XDI showed as HTML
      // (docs/fork/fo4_pipeline.md#xdi-html); this menu and the game's buttons show plain text. Kept for plugins
      // built before the build stopped escaping.
      private function unescaped(text:String) : String
      {
         return text.split("&lt;").join("<").split("&gt;").join(">").split("&amp;").join("&");
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

      // No animation of its own: the game waits for the end of one, so it gets it on the next frame.
      public function PlaySpeechChallengeAnim() : *
      {
         addEventListener(Event.ENTER_FRAME, this.speechDone);
      }

      private function speechDone(e:Event) : void
      {
         removeEventListener(Event.ENTER_FRAME, this.speechDone);
         this.BGSCodeObj.OnSpeechChallengeAnimComplete();
      }
   }
}
