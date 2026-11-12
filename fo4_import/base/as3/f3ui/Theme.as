package f3ui
{
   // The color everything we draw takes: the player's HUD color, read from F3NV.dll's HudColor native on each open
   // (white without the DLL). The menu colors itself; no engine tint.
   // See docs/fork/swf_framework.md#spikes (2b)
   public class Theme
   {
      public static const WHITE:uint = 0xFFFFFF;
      public static var color:uint = WHITE;

      // Read the HUD color again from `dll` (our natives, or null); the color now in use.
      public static function fromHud(dll:Object) : uint
      {
         color = dll != null && dll.HudColor != null ? uint(dll.HudColor()) : WHITE;
         return color;
      }
   }
}
