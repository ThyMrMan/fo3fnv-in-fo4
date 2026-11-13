package
{
   import crui.levelup.Character;
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

   // Our level-up menu's document class: CRUI_LevelUp.psc opens it in place of LevelUpMenu, and as the tag skill and
   // trait menus, and calls these by UI.Invoke. A list on the left and the highlighted entry on the right (its image,
   // name, ranks, requirements and description). A level-up has three pages: SKILLS, where points are set (Accept or
   // Right adds, Left takes back; Y resets) and spent together (X); PERKS, the perks with a rank left (X shows all or
   // only those that can be taken now; Accept takes one, once confirmed); TAKEN, the perks held. Points left unspent
   // stay for later. The tag menu (TAGS) tags skills up to the count asked, X once all are picked; the trait menu
   // (TRAITS) picks up to the count, X to keep them, Back to leave them as they were.
   // See docs/fork/fo4_level_up_plan.md#menu
   public class CRUI_LevelUp extends MovieClip
   {
      public static const MENU:String = "CRUI_LevelUp";
      public static const WIDTH:Number = 1280;
      public static const HEIGHT:Number = 720;
      public static const SKILLS:int = 0;
      public static const PERKS:int = 1;
      public static const TAKEN:int = 2;
      public static const TAGS:int = 3;
      public static const TRAITS:int = 4;
      // Each page's title, by page.
      private static const TITLES:Array = ["$CRUI_LU_SKILLS", "$CRUI_LU_PERKS", "$CRUI_LU_TAKEN", "$CRUI_LU_TAGS",
                                           "$CRUI_LU_TRAITS"];
      private static const LIST_X:Number = 40;
      private static const TOP:Number = 80;
      private static const LINE:Number = 30;
      private static const IMAGE:Number = 200;
      private static const DIM:Number = 0.45;
      // The tag and trait menus' panel: its width and where its detail starts.
      private static const PANEL_WIDTH:Number = 1000;
      private static const PANEL_DETAIL_X:Number = 520;

      // This open's size and detail column: the whole screen for a level-up, a centered panel for the tag and
      // trait menus.
      private var wide:Number = WIDTH;
      private var high:Number = HEIGHT;
      private var detailX:Number = 620;
      private var textX:Number;

      private var bridge:Bridge = new Bridge();
      private var images:Images = new Images(bridge, MENU);
      private var urls:Object = {};
      private var who:Character;
      // This open's pages, and the one shown.
      private var pages:Array = [SKILLS, PERKS, TAKEN];
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

      public function CRUI_LevelUp()
      {
         super();
         addEventListener(Event.ADDED_TO_STAGE, onStage);
      }

      // F4SE hands the menu its f4se object (MountImage, SendExternalEvent).
      public function onF4SEObjCreated(codeObject:Object) : void
      {
         bridge.f4se = codeObject;
         images.log = log;
      }

      // CRUI_LevelUp.psc's Send: everything the menu shows (Character's order). A level-up opens on SKILLS when
      // there are skill points, else on PERKS; the tag and trait menus have their one page.
      public function Open(... args) : void
      {
         Theme.fromHud(bridge.natives("F3NV"));
         who = new Character(args);
         showAll = who.showAll;
         log("open: mode " + who.mode + ", " + who.perks.length + " perks, " + who.skills.length + " skills, "
             + who.traits.length + " traits, " + who.rows.length + " requirement rows, " + who.perkPoints
             + " perk and " + who.skillPoints + " skill points");
         pages = who.mode == Character.TAGS ? [TAGS] : (who.mode == Character.TRAITS ? [TRAITS] : [SKILLS, PERKS, TAKEN]);
         build();
         page = pages.length == 1 ? pages[0] : (who.skillPoints > 0 || who.perkPoints == 0 ? SKILLS : PERKS);
         if (input != null)
         {
            input.open();
         }
         showPage(0);
      }

      // CRUI_LevelUp.psc's answer to a Take: whether perk `index` was taken, the ranks now held, the points left.
      public function Taken(index:int, taken:Boolean, held:int, perkPoints:int) : void
      {
         who.perks[index].held = held;
         who.perkPoints = perkPoints;
         say(taken ? "" : "$CRUI_LU_CANNOT_TAKE");
         showPage(list.selected);
      }

      // CRUI_LevelUp.psc's answer to a Raise: skill `index` took `spent` points to `value`; the points left. The
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
         Host.focus(this);
      }

      // The screen's parts, in the HUD color read on this open: the whole screen for a level-up; for the tag and
      // trait menus, one row per entry in a centered panel, the game showing faded round it.
      private function build() : void
      {
         while (numChildren > 0)
         {
            removeChildAt(0);
         }
         var panel:Boolean = pages.length == 1;
         var rows:int = panel ? Math.min(18, Math.max(1, pages[0] == TAGS ? who.skills.length : who.traits.length)) : 18;
         wide = panel ? PANEL_WIDTH : WIDTH;
         high = panel ? Math.max(560, TOP + rows * LINE + 80) : HEIGHT;
         detailX = panel ? PANEL_DETAIL_X : 620;
         textX = detailX + IMAGE + 24;
         backdrop(panel);
         tabs = [];
         for (var i:int = 0; i < pages.length; i++)
         {
            tabs.push(Text.show(Text.label(this, LIST_X + i * 170, 24, 28), TITLES[pages[i]]));
         }
         points = Text.label(this, detailX, 30, 20);
         list = new ScrollList();
         list.rows = rows;
         list.listWidth = detailX - LIST_X - 30;
         list.line = LINE;
         list.x = LIST_X;
         list.y = TOP;
         list.onPick = function(index:int) : void { onAction(Input.ACCEPT, 0); };
         list.onDraw = showDetail;
         addChild(list);
         detail = new Sprite();
         addChild(detail);
         title = Text.label(detail, textX, TOP, 30);
         sub = Text.label(detail, textX, TOP + 44, 20);
         needs = wrapped(detail, textX, TOP + 80, wide - 40 - textX, 18);
         about = wrapped(detail, detailX, TOP + IMAGE + 30, wide - 40 - detailX, 20);
         status = wrapped(this, detailX, high - 110, wide - 40 - detailX, 20);
         question = wrapped(null, 20, 20, 560, 22);
         modal = new Modal();
         modal.fade = 0.5;
         modal.x = (wide - 600) / 2;
         modal.y = (high - 140) / 2;
         modal.handler = onModal;
         addChild(modal);
         if (hints != null)
         {
            hints.y = high - 36;
            addChild(hints);
         }
      }

      // The menu's ground: a level-up darkens the whole screen; a panel sits centered (this clip moved there) over a
      // lighter fade, framed in the HUD color.
      private function backdrop(panel:Boolean) : void
      {
         x = (WIDTH - wide) / 2;
         y = (HEIGHT - high) / 2;
         graphics.clear();
         graphics.beginFill(0, panel ? 0.5 : 0.85);
         graphics.drawRect(-x, -y, WIDTH, HEIGHT);
         graphics.endFill();
         if (panel)
         {
            graphics.lineStyle(2, Theme.color);
            graphics.beginFill(0, 0.85);
            graphics.drawRect(0, 0, wide, high);
            graphics.endFill();
            graphics.lineStyle();
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

      // The current page's list with entry `selected` highlighted, the tabs, the count line and hints.
      private function showPage(selected:int) : void
      {
         for (var i:int = 0; i < tabs.length; i++)
         {
            tabs[i].alpha = pages[i] == page ? 1 : DIM;
         }
         Text.show(points, counts());
         shown = [];
         var items:Array = page == SKILLS || page == TAGS ? skillItems() : (page == TRAITS ? traitItems() : perkItems());
         list.show(items, selected);
         showHints();
      }

      // The line over the detail: the points left, or the tags or traits picked of those asked.
      private function counts() : String
      {
         if (page == TAGS)
         {
            return Text.fill("$CRUI_LU_TAGS_PICKED\t" + who.tagCount() + "\t" + who.wanted);
         }
         if (page == TRAITS)
         {
            return Text.fill("$CRUI_LU_TRAITS_PICKED\t" + who.traitCount() + "\t" + who.wanted);
         }
         return Text.fill("$CRUI_LU_POINTS\t" + (who.skillPoints - who.pendingPoints()) + "\t" + who.perkPoints);
      }

      // `name`, marked with `mark` (a $KEY) when `marked`.
      private static function marked(name:String, marked:Boolean, mark:String) : String
      {
         return marked ? name + " (" + Text.translate(mark) + ")" : name;
      }

      // The skills, each with its value ("45 > 50" with points set, or with the tag bonus in the tag menu).
      private function skillItems() : Array
      {
         var items:Array = [];
         for (var i:int = 0; i < who.skills.length; i++)
         {
            var skill:Object = who.skills[i];
            var value:String = String(who.skillValue(i));
            var after:Number = page == TAGS ? who.skillValue(i) + tagGain(skill) : who.skillValue(i, true);
            shown.push(i);
            items.push({text: marked(skill.name, skill.tagged, "$CRUI_LU_TAG_MARK"),
                        value: after != who.skillValue(i) ? value + " > " + after : value,
                        dim: page == TAGS && skill.tag == Character.TAGGED});
         }
         return items;
      }

      // The tag bonus skill `skill` would get as the tag menu stands: a new tag's (a suggestion has none yet).
      private function tagGain(skill:Object) : int
      {
         return skill.tagged && skill.tag != Character.TAGGED ? who.bonus : 0;
      }

      private function traitItems() : Array
      {
         var items:Array = [];
         for (var i:int = 0; i < who.traits.length; i++)
         {
            shown.push(i);
            items.push({text: marked(who.traits[i].name, who.traits[i].picked, "$CRUI_LU_CHOSEN_MARK")});
         }
         return items;
      }

      // PERKS: those with a rank left the player can take now (all of them, the rest dimmed, with showAll); TAKEN:
      // those held.
      private function perkItems() : Array
      {
         var items:Array = [];
         for (var i:int = 0; i < who.perks.length; i++)
         {
            var perk:Object = who.perks[i];
            var listed:Boolean = page == TAKEN ? perk.held > 0 : perk.held < perk.ranks && (showAll || who.eligible(i));
            if (listed)
            {
               shown.push(i);
               items.push({text: perk.name, value: perk.ranks > 1 ? perk.held + "/" + perk.ranks : "",
                           dim: page == PERKS && !who.eligible(i)});
            }
         }
         return items;
      }

      private function showHints() : void
      {
         if (hints == null)
         {
            return;
         }
         var out:Array = pages.length > 1 ? [[[Input.PREV, Input.NEXT], "$CRUI_LU_PAGE"]] : [];
         if (page == SKILLS)
         {
            out.push([[Input.LEFT, Input.RIGHT], "$CRUI_LU_SET"], [Input.X, "$CRUI_LU_DONE"], [Input.Y, "$CRUI_LU_RESET"]);
         }
         else if (page == PERKS)
         {
            out.push([Input.ACCEPT, "$CRUI_LU_TAKE"], [Input.X, showAll ? "$CRUI_LU_SHOW_AVAILABLE" : "$CRUI_LU_SHOW_ALL"]);
         }
         else if (page == TAGS || page == TRAITS)
         {
            out.push([Input.ACCEPT, page == TAGS ? "$CRUI_LU_TAG" : "$CRUI_LU_PICK"], [Input.X, "$CRUI_LU_DONE"]);
         }
         if (page != TAGS)
         {
            out.push([Input.BACK, "$CRUI_HINT_LEAVE"]);
         }
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
         var skills:Boolean = page == SKILLS || page == TAGS;
         var entry:Object = skills ? who.skills[index] : (page == TRAITS ? who.traits[index] : who.perks[index]);
         var kind:String = skills ? "S" : (page == TRAITS ? "T" : "P");
         image = images.show(detail, imageUrl(kind, index, entry.image), detailX, TOP, IMAGE);
         Text.show(title, entry.name);
         Text.show(about, entry.text);
         if (page == TRAITS)
         {
            Text.show(sub, "");
            Text.show(needs, "");
            return;
         }
         if (skills)
         {
            var after:Number = page == TAGS ? who.skillValue(index) + tagGain(entry) : who.skillValue(index, true);
            Text.show(sub, who.skillValue(index) + (after != who.skillValue(index) ? " > " + after : ""));
            Text.show(needs, entry.tagged ? Text.translate("$CRUI_LU_TAGGED") : "");
            var opens:Array = page == SKILLS ? who.unlocked() : [];
            say(opens.length > 0 ? Text.fill("$CRUI_LU_OPENS\t" + opens.join(", ")) : "");
            return;
         }
         Text.show(sub, entry.ranks > 1 ? Text.fill("$CRUI_LU_RANK\t" + entry.held + "\t" + entry.ranks) : "");
         var lines:Array = [];
         for each (var line:Array in who.requirements(index))
         {
            lines.push(line[0]);
         }
         Text.show(needs, lines.join("\n"));
      }

      // The image of entry `index` of kind `kind` (S skill, P perk, T trait), mounted once per open; "" for none.
      private function imageUrl(kind:String, index:int, path:String) : String
      {
         var key:String = kind + index;
         if (!(key in urls))
         {
            urls[key] = path != "" ? images.mount(path, "CRUI_LU_" + key) : "";
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
            if (page == TAGS)
            {
               return true;
            }
            return who.pendingPoints() > 0 ? ask("$CRUI_LU_KEEP_POINTS", leaveKeeping, leaveDropping) : close();
         }
         if ((action == Input.PREV || action == Input.NEXT) && pages.length > 1)
         {
            var at:int = pages.indexOf(page);
            page = pages[(at + (action == Input.NEXT ? 1 : pages.length - 1)) % pages.length];
            say("");
            showPage(0);
            return true;
         }
         if (page == TAGS || page == TRAITS)
         {
            return pickAction(action);
         }
         return page == SKILLS ? skillAction(action) : (page == PERKS ? perkAction(action) : move(action));
      }

      // The tag and trait menus: Accept tags or picks the highlighted entry (within the count); X keeps the picks,
      // once all the tags asked are picked; then the menu closes.
      private function pickAction(action:String) : Boolean
      {
         var tags:Boolean = page == TAGS;
         if (action == Input.ACCEPT)
         {
            var index:int = shown[list.selected];
            var changed:Boolean = tags ? who.toggleTag(index) : who.toggleTrait(index);
            say(changed ? "" : (tags && who.skills[index].tag == Character.TAGGED ? "$CRUI_LU_TAG_KEPT"
                                                                                : "$CRUI_LU_PICK_FULL"));
            showPage(list.selected);
            return true;
         }
         if (action != Input.X)
         {
            return move(action);
         }
         if (tags && who.tagCount() < who.wanted)
         {
            say(Text.fill("$CRUI_LU_TAG_MORE\t" + (who.wanted - who.tagCount())));
            return true;
         }
         if (tags)
         {
            send("CRUI_LevelUpTags", Character.mask(who.skills, "tagged"));
         }
         else
         {
            send("CRUI_LevelUpTraits", Character.mask(who.traits, "picked"), who.traits.length);
         }
         return true;
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
            say("$CRUI_LU_NO_PERK_POINTS");
         }
         else if (!who.eligible(index))
         {
            say("$CRUI_LU_CANNOT_TAKE");
         }
         else
         {
            ask("$CRUI_LU_CONFIRM_TAKE\t" + who.perks[index].name, function() : void { take(index); }, null);
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
         choices.show([[Input.ACCEPT, "$CRUI_LU_YES"], [Input.BACK, "$CRUI_LU_NO"]]);
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
         send("CRUI_LevelUpTake", index);
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
            send("CRUI_LevelUpRaise", index, who.skills[index].pending);
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
         send("CRUI_LevelUpClose");
         return true;
      }

      private function log(text:String) : void
      {
         send("CRUI_LevelUpLog", text);
      }

      private function send(event:String, ... args) : void
      {
         bridge.send.apply(null, [event].concat(args));
      }
   }
}
