package
{
   import f3ui.Bridge;
   import f3ui.HintBar;
   import f3ui.Input;
   import f3ui.Text;
   import flash.display.DisplayObject;
   import flash.display.Graphics;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.MouseEvent;
   import flash.geom.Point;
   import flash.geom.Rectangle;
   import flash.system.ApplicationDomain;
   import flash.text.TextField;
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

      // The list: {text, said, failed, ours, index}; index is F3NV.dll's option or the game's button.
      private var entries:Array = [];

      private var selected:int = 0;

      private var top:int = 0;

      private var list:Sprite;

      private var rows:Vector.<TextField>;

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
         var i:int = 0;
         while(i < ROWS)
         {
            var row:TextField = Text.field(18, null, Text.BOLD, -2);
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
         if(this.input != null)
         {
            this.hints = new HintBar(this.input, HINT_SIZE);
            this.hints.show([[Input.ACCEPT, "$F3NV_HINT_SELECT"], [Input.BACK, "$F3NV_HINT_LEAVE"]]);
            list.addChild(this.hints);
         }
         host.addChild(list);
         this.failedRows = new Sprite();
         this.failedRows.visible = false;
         this.FadeHolder_mc.Negative.addChild(this.failedRows);
         this.list = list;
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
         var options:Object = this.dll != null ? this.dll.GetDialogueOptions() : null;
         var i:int = 0;
         if(options != null && options.length > 0)
         {
            while(i < options.length)
            {
               this.entries.push({"text":this.unescaped(String(options[i].text)), "said":options[i].said, "failed":options[i].failed == true, "ours":true, "index":i});
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
         var failed:int = 0;
         var i:int = 0;
         while(i < ROWS)
         {
            var row:TextField = this.rows[i];
            var at:int = this.top + i;
            row.visible = i < count;
            // A hidden row still counts in its holder's bounds, which size the shaded background: an unused row
            // leaves the holder, or the backdrop stays as tall as the last longer menu.
            if(i >= count && row.parent != null)
            {
               row.parent.removeChild(row);
            }
            if(i < count)
            {
               var entry:Object = this.entries[at];
               var layer:Sprite = entry.failed == true ? this.failedRows : this.list;
               if(row.parent != layer)
               {
                  layer.addChild(row);
               }
               failed = failed + (entry.failed == true ? 1 : 0);
               Text.show(row, String(entry.text).toUpperCase());
               row.alpha = at == this.selected ? 1 : (entry.said ? 0.45 : 0.75);
               row.y = y;
               y = y + row.height + GAP;
            }
            i++;
         }
         var high:Number = y - GAP + PAD + LINE;
         if(this.hints != null)
         {
            this.hints.x = (BOX_WIDTH - this.hints.width) / 2;
            this.hints.y = high + HINT_GAP;
         }
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
         this.overlay(failed > 0);
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
         this.failedRows.graphics.clear();
         this.frame(g, 0, 0, BOX_WIDTH, high, 0.9);
         var row:TextField = this.rows[this.selected - this.top];
         var around:Graphics = row.parent == this.failedRows ? this.failedRows.graphics : g;
         this.frame(around, GUTTER + PAD, row.y - 3, BOX_WIDTH - GUTTER - 2 * PAD, row.height + 6, 0.9);
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

      // One action while the list is up (Input): up and down move (the wheel too), accept picks, back leaves, a
      // number key picks that row.
      private function onAction(action:String, digit:int) : Boolean
      {
         if(!this.listShown)
         {
            return false;
         }
         this.seenOnce("action " + action);
         if(action == Input.UP || action == Input.DOWN)
         {
            this.move(action == Input.UP ? -1 : 1);
         }
         else if(action == Input.ACCEPT)
         {
            this.pick(this.selected);
         }
         else if(action == Input.BACK && this.dll != null)
         {
            this.leave(action);
         }
         else if(action == Input.DIGIT)
         {
            this.pick(this.top + digit);
         }
         else
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
