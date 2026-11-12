package f3ui
{
   import flash.display.Loader;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.net.URLRequest;

   // Textures shown in a menu through f4se.MountImage. Any form of a texture's path is put the way MountImage takes
   // it (under Textures, without that folder: played 2026-11-08); a missing file is caught first by F3NV.dll's
   // TextureExists, since MountImage reports true for one; and an image shows in a Loader, scaled to a square.
   // See docs/fork/swf_framework.md#images
   public class Images
   {
      // Log a line (a missing texture, a failed load); null for none.
      public var log:Function;

      private var bridge:Bridge;
      private var menu:String;

      // Images mounted in menu `menu` (its registered name) through `bridge`.
      public function Images(bridge:Bridge, menu:String)
      {
         this.bridge = bridge;
         this.menu = menu;
      }

      // `path` as MountImage takes it: forward slashes, no leading Data/ or Textures/ (any case), spaces kept.
      public static function texturePath(path:String) : String
      {
         var out:String = path.split("\\").join("/");
         if (out.toLowerCase().indexOf("data/") == 0)
         {
            out = out.substr(5);
         }
         if (out.toLowerCase().indexOf("textures/") == 0)
         {
            out = out.substr(9);
         }
         return out;
      }

      // Whether the game has the texture at `path`: F3NV.dll's answer, or true without it (none, or an older one).
      public function exists(path:String) : Boolean
      {
         var dll:Object = bridge.natives("F3NV");
         return dll == null || dll.TextureExists == null || dll.TextureExists(texturePath(path)) == true;
      }

      // Mount the texture at `path` as `name`: its img:// URL, or "" when it is missing or F4SE did not mount it.
      public function mount(path:String, name:String) : String
      {
         var at:String = texturePath(path);
         if (!exists(at))
         {
            say("missing texture " + at);
            return "";
         }
         if (!bridge.mount(menu, at, name))
         {
            say("not mounted " + at);
            return "";
         }
         return "img://" + name;
      }

      // A Loader at (x, y) in `parent` showing `url`, scaled to `size` square once loaded (0: as it is), then
      // `done(loader, loaded)` (null for none). For an empty url the Loader stays empty.
      public function show(parent:Sprite, url:String, x:Number, y:Number, size:Number = 0,
                           done:Function = null) : Loader
      {
         var image:Loader = new Loader();
         image.x = x;
         image.y = y;
         parent.addChild(image);
         if (url == "")
         {
            return image;
         }
         image.contentLoaderInfo.addEventListener(Event.COMPLETE, function(e:Event) : void
         {
            if (size > 0)
            {
               image.width = size;
               image.height = size;
            }
            if (done != null)
            {
               done(image, true);
            }
         });
         image.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, function(e:IOErrorEvent) : void
         {
            say("load failed " + url + ": " + e.text);
            if (done != null)
            {
               done(image, false);
            }
         });
         image.load(new URLRequest(url));
         return image;
      }

      private function say(text:String) : void
      {
         if (log != null)
         {
            log(text);
         }
      }
   }
}
