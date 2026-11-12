package f3ui
{
   // The movie's link to the game: F4SE's root object (handed over in onF4SEObjCreated) and our DLL's natives.
   // See docs/fork/swf_framework.md#design
   public class Bridge
   {
      public var f4se:Object;

      // F4SE hands each item of a Papyrus Var array over wrapped as {__var__: value}: the plain values.
      public static function plain(items:Array) : Array
      {
         var out:Array = [];
         for each (var item:* in items)
         {
            out.push(item != null && typeof item == "object" && "__var__" in item ? item["__var__"] : item);
         }
         return out;
      }

      // The natives a plugin registered on every movie (f4se.plugins.<name>); null without F4SE or the plugin.
      public function natives(plugin:String) : Object
      {
         return f4se != null && f4se.plugins != null ? f4se.plugins[plugin] : null;
      }

      // Send an F4SE external event (Papyrus RegisterForExternalEvent); nothing before F4SE is there.
      public function send(event:String, ... args) : void
      {
         if (f4se != null)
         {
            f4se.SendExternalEvent.apply(null, [event].concat(args));
         }
      }

      // Mount a DDS under Textures (path without that folder) as img://<name>; false without F4SE.
      // MountImage returns true even for a missing file, and images drop when the menu closes.
      public function mount(menu:String, path:String, name:String) : Boolean
      {
         return f4se != null && f4se.MountImage(menu, path, name);
      }
   }
}
