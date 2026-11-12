package f3ui
{
   import flash.display.InteractiveObject;

   // What every menu does once it is on the stage.
   // See docs/fork/swf_framework.md#facts
   public class Host
   {
      // Give `menu` the keyboard focus without Flash's yellow focus rectangle round the screen (FO4's own menus
      // turn it off the same way).
      public static function focus(menu:InteractiveObject) : void
      {
         menu.stage.stageFocusRect = false;
         menu.focusRect = false;
         menu.stage.focus = menu;
      }
   }
}
