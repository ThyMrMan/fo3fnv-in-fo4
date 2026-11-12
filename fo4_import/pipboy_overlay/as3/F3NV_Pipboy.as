package
{
   import f3ui.Bridge;
   import flash.display.MovieClip;
   import flash.events.Event;

   // Spike 4: our own movie inside the Pip-Boy. F3NV.dll loads it into the Pip-Boy menu (root.Menu_mc) with a
   // Loader when the menu opens (pipboy.cpp LoadOverlay). It keeps one line of its own on the inventory item card
   // (CurrentPage.ItemCard_mc.InfoObj), which the game refills on every selection, under any Pip-Boy movie that
   // keeps the vanilla item card. It draws nothing and takes no input.
   // See docs/fork/swf_framework.md#spikes
   public class F3NV_Pipboy extends MovieClip
   {
      public static const LABEL:String = "F3UI";
      public static const VALUE:String = "SPIKE 4";

      private var bridge:Bridge = new Bridge();
      private var menu:Object;
      private var seen:Object = {};

      public function F3NV_Pipboy()
      {
         super();
         mouseEnabled = false;
         mouseChildren = false;
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

      // Each frame: put our line back on the item card when the game's refill dropped it, and redraw the card.
      private function onFrame(e:Event) : void
      {
         var card:Object = itemCard();
         var lines:Array = card != null ? card.InfoObj as Array : null;
         if (lines == null)
         {
            return;
         }
         for each (var line:Object in lines)
         {
            if (line != null && line.text == LABEL)
            {
               return;
            }
         }
         lines.push({text: LABEL, value: VALUE});
         card.onDataChange();
         once("added our line to an item card (" + lines.length + " lines)");
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
