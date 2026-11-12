package
{
   import f3nv.levelup.Character;
   import f3ui.Bridge;
   import f3ui.HintBar;
   import f3ui.Host;
   import f3ui.Images;
   import f3ui.Input;
   import f3ui.Modal;
   import f3ui.ScrollList;
   import f3ui.Text;
   import f3ui.Theme;
   import flash.display.Loader;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;

   // Our level-up menu's document class: F3NV_LevelUp.psc opens it in place of LevelUpMenu and calls these by
   // UI.Invoke. Three pages, a list on the left and the highlighted entry on the right (its image, name, ranks,
   // requirements and description): SKILLS, where points are set (Accept or Right adds, Left takes back; Y resets)
   // and spent together (X); PERKS, the perks with a rank left (X shows all or only those that can be taken now;
   // Accept takes one, once confirmed); TAKEN, the perks held. Points left unspent stay for later.
   // See docs/fork/fo4_level_up_plan.md#menu
   public class F3NV_LevelUp extends MovieClip
   {
      public static const MENU:String = "F3NV_LevelUp";
      public static const WIDTH:Number = 1280;
      public static const HEIGHT:Number = 720;
      public static const SKILLS:int = 0;
      public static const PERKS:int = 1;
      public static const TAKEN:int = 2;
      private static const PAGES:Array = ["$F3NV_LU_SKILLS", "$F3NV_LU_PERKS", "$F3NV_LU_TAKEN"];
      private static const LIST_X:Number = 40;
      private static const TOP:Number = 80;
      private static const DETAIL_X:Number = 620;
      private static const IMAGE:Number = 200;
      private static const TEXT_X:Number = DETAIL_X + IMAGE + 24;
      private static const DIM:Number = 0.45;

      private var bridge:Bridge = new Bridge();
      private var images:Images = new Images(bridge, MENU);
      private var urls:Object = {};
      private var who:Character;
      private var page:int = SKILLS;
      private var showAll:Boolean = false;
      // The list's entries on the current page: indexes into who.perks or who.skills.
      private var shown:Array = [];
      // The skills still to raise, whether a Raise is waiting for its answer, and whether to close after.
      private var raising:Array = [];
      private var busy:Boolean = false;
      private var closing:Boolean = false;

      private var input:Input;
      private var hints:HintBar;
      private var list:ScrollList = new ScrollList();
      private var modal:Modal = new Modal();
      private var tabs:Array = [];
      private var points:TextField;
      private var detail:Sprite = new Sprite();
      private var image:Loader;
      private var title:TextField;
      private var sub:TextField;
      private var needs:TextField;
      private var about:TextField;
      private var status:TextField;
      private var question:TextField;

      public function F3NV_LevelUp()
      {
         super();
         graphics.beginFill(0, 0.85);
         graphics.drawRect(0, 0, WIDTH, HEIGHT);
         graphics.endFill();
         addEventListener(Event.ADDED_TO_STAGE, onStage);
      }

      // F4SE hands the menu its f4se object (MountImage, SendExternalEvent).
      public function onF4SEObjCreated(codeObject:Object) : void
      {
         bridge.f4se = codeObject;
         images.log = log;
      }

      // F3NV_LevelUp.psc's Send: everything the menu shows (Character's order). Opens on SKILLS when there are
      // skill points, else on PERKS.
      public function Open(... args) : void
      {
         Theme.fromHud(bridge.natives("F3NV"));
         who = new Character(args);
         log("open: " + who.perks.length + " perks, " + who.skills.length + " skills, " + who.rows.length
             + " requirement rows, " + who.perkPoints + " perk and " + who.skillPoints + " skill points");
         build();
         page = who.skillPoints > 0 || who.perkPoints == 0 ? SKILLS : PERKS;
         if (input != null)
         {
            input.open();
         }
         showPage(0);
      }

      // F3NV_LevelUp.psc's answer to a Take: whether perk `index` was taken, the ranks now held, the points left.
      public function Taken(index:int, taken:Boolean, held:int, perkPoints:int) : void
      {
         who.perks[index].held = held;
         who.perkPoints = perkPoints;
         say(taken ? "" : "$F3NV_LU_CANNOT_TAKE");
         showPage(list.selected);
      }

      // F3NV_LevelUp.psc's answer to a Raise: skill `index` took `spent` points to `value`; the points left. The
      // next skill set is raised, then the menu redraws (or closes, when leaving).
      public function Raised(index:int, spent:int, value:Number, skillPoints:int) : void
      {
         who.values[who.specials + index] = value;
         who.skills[index].pending = 0;
         who.skillPoints = skillPoints;
         raiseNext();
      }

      // FO4's menu input as Input's actions.
      public function ProcessUserEvent(control:String, down:Boolean) : Boolean
      {
         return input != null && input.control(control, down);
      }

      public function SetPlatform(platform:uint, ps3Switch:Boolean) : void
      {
         if (input != null)
         {
            input.setPlatform(platform);
         }
      }

      private function onStage(e:Event) : void
      {
         input = new Input(stage, onAction);
         input.log = log;
         hints = new HintBar(input);
         hints.x = LIST_X;
         hints.y = HEIGHT - 36;
         Host.focus(this);
      }

      // The screen's parts, in the HUD color read on this open.
      private function build() : void
      {
         while (numChildren > 0)
         {
            removeChildAt(0);
         }
         tabs = [];
         for (var i:int = 0; i < PAGES.length; i++)
         {
            tabs.push(Text.show(Text.label(this, LIST_X + i * 170, 24, 28), PAGES[i]));
         }
         points = Text.label(this, DETAIL_X, 30, 20);
         list = new ScrollList();
         list.rows = 18;
         list.listWidth = DETAIL_X - LIST_X - 30;
         list.line = 30;
         list.x = LIST_X;
         list.y = TOP;
         list.onPick = function(index:int) : void { onAction(Input.ACCEPT, 0); };
         list.onDraw = showDetail;
         addChild(list);
         detail = new Sprite();
         addChild(detail);
         title = Text.label(detail, TEXT_X, TOP, 30);
         sub = Text.label(detail, TEXT_X, TOP + 44, 20);
         needs = wrapped(detail, TEXT_X, TOP + 80, WIDTH - 40 - TEXT_X, 18);
         about = wrapped(detail, DETAIL_X, TOP + IMAGE + 30, WIDTH - 40 - DETAIL_X, 20);
         status = wrapped(this, DETAIL_X, HEIGHT - 110, WIDTH - 40 - DETAIL_X, 20);
         question = wrapped(null, 20, 20, 560, 22);
         modal = new Modal();
         modal.fade = 0.5;
         modal.x = (WIDTH - 600) / 2;
         modal.y = (HEIGHT - 140) / 2;
         modal.handler = onModal;
         addChild(modal);
         if (hints != null)
         {
            addChild(hints);
         }
      }

      // A wrapping field `wide` across at (x, y) in `parent` (null: none yet).
      private function wrapped(parent:Sprite, x:Number, y:Number, wide:Number, size:int) : TextField
      {
         var out:TextField = Text.field(size);
         out.multiline = true;
         out.wordWrap = true;
         out.autoSize = TextFieldAutoSize.LEFT;
         out.x = x;
         out.y = y;
         out.width = wide;
         if (parent != null)
         {
            parent.addChild(out);
         }
         return out;
      }

      // The current page's list with entry `selected` highlighted, the tabs, points and hints.
      private function showPage(selected:int) : void
      {
         for (var i:int = 0; i < tabs.length; i++)
         {
            tabs[i].alpha = i == page ? 1 : DIM;
         }
         var pending:int = who.pendingPoints();
         Text.show(points, Text.fill("$F3NV_LU_POINTS\t" + (who.skillPoints - pending) + "\t" + who.perkPoints));
         var items:Array = [];
         shown = [];
         if (page == SKILLS)
         {
            for (i = 0; i < who.skills.length; i++)
            {
               var skill:Object = who.skills[i];
               var value:String = String(who.skillValue(i));
               shown.push(i);
               items.push({text: skill.name, value: skill.pending > 0 ? value + " > " + who.skillValue(i, true) : value});
            }
         }
         else
         {
            for (i = 0; i < who.perks.length; i++)
            {
               var perk:Object = who.perks[i];
               var listed:Boolean = page == TAKEN ? perk.held > 0
                                                  : perk.held < perk.ranks && (showAll || who.eligible(i));
               if (listed)
               {
                  shown.push(i);
                  items.push({text: perk.name, value: perk.ranks > 1 ? perk.held + "/" + perk.ranks : "",
                              dim: page == PERKS && !who.eligible(i)});
               }
            }
         }
         list.show(items, selected);
         showHints();
      }

      private function showHints() : void
      {
         if (hints == null)
         {
            return;
         }
         var out:Array = [[[Input.PREV, Input.NEXT], "$F3NV_LU_PAGE"]];
         if (page == SKILLS)
         {
            out.push([[Input.LEFT, Input.RIGHT], "$F3NV_LU_SET"], [Input.X, "$F3NV_LU_DONE"], [Input.Y, "$F3NV_LU_RESET"]);
         }
         else if (page == PERKS)
         {
            out.push([Input.ACCEPT, "$F3NV_LU_TAKE"], [Input.X, showAll ? "$F3NV_LU_SHOW_AVAILABLE" : "$F3NV_LU_SHOW_ALL"]);
         }
         out.push([Input.BACK, "$F3NV_HINT_LEAVE"]);
         hints.show(out);
      }

      // The highlighted entry on the right: its image, name, rank or value, requirements, description, and on
      // SKILLS the perks the points set would open.
      private function showDetail() : void
      {
         if (image != null && image.parent != null)
         {
            image.parent.removeChild(image);
         }
         var none:Boolean = shown.length == 0;
         detail.visible = !none;
         if (none)
         {
            return;
         }
         var index:int = shown[list.selected];
         var entry:Object = page == SKILLS ? who.skills[index] : who.perks[index];
         image = images.show(detail, imageUrl(page == SKILLS ? "S" : "P", index, entry.image), DETAIL_X, TOP, IMAGE);
         Text.show(title, entry.name);
         Text.show(about, entry.text);
         if (page == SKILLS)
         {
            Text.show(sub, who.skillValue(index) + (entry.pending > 0 ? " > " + who.skillValue(index, true) : ""));
            Text.show(needs, entry.tagged ? Text.translate("$F3NV_LU_TAGGED") : "");
            var opens:Array = who.unlocked();
            say(opens.length > 0 ? Text.fill("$F3NV_LU_OPENS\t" + opens.join(", ")) : "");
            return;
         }
         Text.show(sub, entry.ranks > 1 ? Text.fill("$F3NV_LU_RANK\t" + entry.held + "\t" + entry.ranks) : "");
         var lines:Array = [];
         for each (var line:Array in who.requirements(index))
         {
            lines.push(line[0]);
         }
         Text.show(needs, lines.join("\n"));
      }

      // The image of entry `index` of kind `kind` (S skill, P perk), mounted once per open; "" for none.
      private function imageUrl(kind:String, index:int, path:String) : String
      {
         var key:String = kind + index;
         if (!(key in urls))
         {
            urls[key] = path != "" ? images.mount(path, "F3NV_LU_" + key) : "";
         }
         return urls[key];
      }

      private function say(text:String) : void
      {
         Text.show(status, text == "" ? "" : Text.fill(text));
      }

      // One action: the modal's while it is open; Back leaves (asking first when points are set and not spent);
      // Prev and Next change page; the rest go to the page.
      private function onAction(action:String, digit:int) : Boolean
      {
         if (who == null || busy)
         {
            return action == Input.BACK && close();
         }
         if (modal.isOpen)
         {
            return modal.action(action, digit);
         }
         if (action == Input.BACK)
         {
            return who.pendingPoints() > 0 ? ask("$F3NV_LU_KEEP_POINTS", leaveKeeping, leaveDropping) : close();
         }
         if (action == Input.PREV || action == Input.NEXT)
         {
            page = (page + (action == Input.NEXT ? 1 : PAGES.length - 1)) % PAGES.length;
            say("");
            showPage(0);
            return true;
         }
         return page == SKILLS ? skillAction(action) : (page == PERKS ? perkAction(action) : move(action));
      }

      // Up and Down move the highlight (a click or a number key would pick a row the highlight is not on).
      private function move(action:String) : Boolean
      {
         return (action == Input.UP || action == Input.DOWN) && list.action(action, 0);
      }

      private function skillAction(action:String) : Boolean
      {
         var index:int = shown[list.selected];
         if (action == Input.RIGHT || action == Input.ACCEPT || action == Input.LEFT)
         {
            who.setPoints(index, action == Input.LEFT ? -1 : 1);
            showPage(list.selected);
            return true;
         }
         if (action == Input.Y)
         {
            for each (var skill:Object in who.skills)
            {
               skill.pending = 0;
            }
            showPage(list.selected);
            return true;
         }
         if (action == Input.X)
         {
            spend(false);
            return true;
         }
         return move(action);
      }

      private function perkAction(action:String) : Boolean
      {
         if (action == Input.X)
         {
            showAll = !showAll;
            showPage(0);
            return true;
         }
         if (action != Input.ACCEPT)
         {
            return move(action);
         }
         if (shown.length == 0)
         {
            return true;
         }
         var index:int = shown[list.selected];
         if (who.perkPoints <= 0)
         {
            say("$F3NV_LU_NO_PERK_POINTS");
         }
         else if (!who.eligible(index))
         {
            say("$F3NV_LU_CANNOT_TAKE");
         }
         else
         {
            ask("$F3NV_LU_CONFIRM_TAKE\t" + who.perks[index].name, function() : void { take(index); }, null);
         }
         return true;
      }

      // The modal asking `text` (a $KEY or template): Accept runs `yes`, Back runs `no` (either may be null).
      private var onYes:Function;
      private var onNo:Function;

      private function ask(text:String, yes:Function, no:Function) : Boolean
      {
         onYes = yes;
         onNo = no;
         Text.show(question, Text.fill(text));
         question.width = 560;
         var body:Sprite = new Sprite();
         body.addChild(question);
         var choices:HintBar = new HintBar(input);
         choices.x = 20;
         choices.y = 90;
         choices.show([[Input.ACCEPT, "$F3NV_LU_YES"], [Input.BACK, "$F3NV_LU_NO"]]);
         body.addChild(choices);
         modal.onClose = function() : void
         {
            var after:Function = onNo;
            onYes = onNo = null;
            if (after != null)
            {
               after();
            }
         };
         modal.open(body, 600, 140);
         return true;
      }

      private function onModal(action:String, digit:int) : Boolean
      {
         if (action != Input.ACCEPT)
         {
            return false;
         }
         var after:Function = onYes;
         onNo = null;
         modal.close();
         if (after != null)
         {
            after();
         }
         return true;
      }

      private function take(index:int) : void
      {
         send("F3NV_LevelUpTake", index);
      }

      // Spend the points set on skills, one skill at a time (Raise, answered by Raised); then close when `leave`.
      private function spend(leave:Boolean) : void
      {
         closing = leave;
         raising = [];
         for (var i:int = 0; i < who.skills.length; i++)
         {
            if (who.skills[i].pending > 0)
            {
               raising.push(i);
            }
         }
         raiseNext();
      }

      // Send the next skill's Raise; once none is left, redraw or close.
      private function raiseNext() : void
      {
         busy = raising.length > 0;
         if (busy)
         {
            var index:int = raising.shift();
            send("F3NV_LevelUpRaise", index, who.skills[index].pending);
         }
         else if (closing)
         {
            close();
         }
         else
         {
            showPage(list.selected);
         }
      }

      private function leaveKeeping() : void
      {
         spend(true);
      }

      private function leaveDropping() : void
      {
         close();
      }

      private function close() : Boolean
      {
         send("F3NV_LevelUpClose");
         return true;
      }

      private function log(text:String) : void
      {
         send("F3NV_LevelUpLog", text);
      }

      private function send(event:String, ... args) : void
      {
         bridge.send.apply(null, [event].concat(args));
      }
   }
}
