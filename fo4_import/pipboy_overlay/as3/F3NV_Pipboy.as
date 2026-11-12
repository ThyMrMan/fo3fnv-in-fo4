package
{
   import f3ui.Bridge;
   import f3ui.Theme;
   import flash.display.DisplayObject;
   import flash.display.MovieClip;
   import flash.events.Event;

   // Our movie inside the Pip-Boy. F3NV.dll loads it into the Pip-Boy menu (root.Menu_mc) with a Loader when the
   // menu opens (pipboy.cpp LoadOverlay). Each frame it keeps the lines F3NV.dll gives (PipboyCardLines: the CND
   // line of an item that wears, why a list did not open, other mods' lines) on the inventory item card
   // (CurrentPage.ItemCard_mc.InfoObj), which the game refills on every selection, under any Pip-Boy movie that
   // keeps the vanilla item card. While F3NV's repair or ammo list is open (PipboyList) it draws that list over
   // the card instead (ListPanel), in white for the game's own screen tint, or in FallUI's Pip-Boy color when
   // FallUI draws the Pip-Boy (it turns the tint off). It takes no input: F3NV.dll keeps the keys.
   // See docs/fork/swf_framework.md#pipboy
   public class F3NV_Pipboy extends MovieClip
   {
      private var bridge:Bridge = new Bridge();
      private var menu:Object;
      private var seen:Object = {};
      private var panel:ListPanel = new ListPanel();

      public function F3NV_Pipboy()
      {
         super();
         mouseEnabled = false;
         mouseChildren = false;
         panel.hide();
         addChild(panel);
         addEventListener(Event.ADDED_TO_STAGE, onStage);
      }

      // Our Loader's parent is the Pip-Boy menu; F4SE's object is on the Pip-Boy movie's own root.
      private function onStage(e:Event) : void
      {
         menu = parent != null ? parent.parent : null;
         try
         {
            bridge.f4se = Object(stage.getChildAt(0)).f4se;
         }
         catch (error:Error)
         {
            bridge.f4se = null;
         }
         log("loaded into " + (menu != null ? String(menu) : "nothing") + " (F3NV.dll "
             + (bridge.natives("F3NV") != null ? "found" : "not found") + ")");
         addEventListener(Event.ENTER_FRAME, onFrame);
      }

      // Each frame: draw F3NV.dll's open list, or else keep its lines on the item card.
      private function onFrame(e:Event) : void
      {
         var dll:Object = bridge.natives("F3NV");
         var list:Object = dll != null && dll.PipboyList != null ? dll.PipboyList() : null;
         var card:Object = itemCard();
         if (list != null && card != null)
         {
            raise();
            Theme.color = pipboyColor();
            panel.draw(list, DisplayObject(card).getBounds(this));
            once("drew a list of F3NV's");
            return;
         }
         panel.hide();
         keepLines(dll, card);
      }

      // Put F3NV.dll's lines on item card `card`, adding the ones the game's refill dropped and updating changed
      // values, and redraw the card when anything changed. Nothing while a list of F3NV's has the card.
      private function keepLines(dll:Object, card:Object) : void
      {
         var wanted:Array = dll != null && dll.PipboyCardLines != null ? dll.PipboyCardLines() as Array : null;
         var lines:Array = wanted != null && card != null ? card.InfoObj as Array : null;
         if (lines == null)
         {
            return;
         }
         var changed:Boolean = false;
         for each (var line:Object in wanted)
         {
            changed = keep(lines, line) || changed;
         }
         if (changed)
         {
            card.onDataChange();
            once("drew F3NV's lines on an item card (" + lines.length + " lines)");
         }
      }

      // Put `line` in item card `lines` (matched by its text), or update its value; true when either was needed.
      private static function keep(lines:Array, line:Object) : Boolean
      {
         for each (var shown:Object in lines)
         {
            if (shown != null && shown.text == line.text)
            {
               if (shown.value == line.value)
               {
                  return false;
               }
               shown.value = line.value;
               return true;
            }
         }
         lines.push(line);
         return true;
      }

      // FallUI's Pip-Boy color (M8r.Mods.config.stdColor in the Pip-Boy's classes, as FallUI's own add-on API reads
      // it), else white: the game tints the vanilla Pip-Boy's white art itself.
      // See docs/fork/swf_framework.md#pipboy
      private function pipboyColor() : uint
      {
         try
         {
            var mods:Object = menu.loaderInfo.applicationDomain.getDefinition("M8r.Mods");
            if (mods.configLoaded && mods.config != null)
            {
               return uint(mods.config.stdColor);
            }
         }
         catch (error:Error)
         {
            once("no FallUI colors: " + error.message);
         }
         return Theme.WHITE;
      }

      // Our Loader to the top of the Pip-Boy menu, over the page and its fade, when something covered it.
      private function raise() : void
      {
         try
         {
            if (menu.getChildIndex(parent) != menu.numChildren - 1)
            {
               menu.setChildIndex(parent, menu.numChildren - 1);
            }
         }
         catch (error:Error)
         {
            once("could not raise our movie: " + error.message);
         }
      }

      // The shown page's item card, or null on a page without one.
      private function itemCard() : Object
      {
         try
         {
            var page:Object = menu.CurrentPage;
            return page != null && page.hasOwnProperty("ItemCard_mc") ? page.ItemCard_mc : null;
         }
         catch (error:Error)
         {
            once("no item card: " + error.message);
         }
         return null;
      }

      private function once(what:String) : void
      {
         if (seen[what] == null)
         {
            seen[what] = true;
            log(what);
         }
      }

      private function log(text:String) : void
      {
         var dll:Object = bridge.natives("F3NV");
         if (dll != null && dll.Log != null)
         {
            dll.Log("Pip-Boy movie: " + text);
         }
      }
   }
}
