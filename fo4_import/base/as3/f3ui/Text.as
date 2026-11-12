package f3ui
{
   import flash.display.Sprite;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.text.TextFormat;

   // Text in FO4's own font, by name (the game maps it per language; no font library is imported).
   public class Text
   {
      public static const FONT:String = "$MAIN_Font";
      public static const BOLD:String = "$MAIN_Font_Bold";

      // A non-selectable field in the game font and Theme.color.
      public static function field(size:int, align:String = null, font:String = FONT) : TextField
      {
         var out:TextField = new TextField();
         out.defaultTextFormat = new TextFormat(font, size, Theme.color, null, null, null, null, null, align);
         out.embedFonts = true;
         out.selectable = false;
         return out;
      }

      // A field that sizes to its text, added to `parent` at (x, y).
      public static function label(parent:Sprite, x:Number, y:Number, size:int) : TextField
      {
         var out:TextField = field(size);
         out.autoSize = TextFieldAutoSize.LEFT;
         out.x = x;
         out.y = y;
         parent.addChild(out);
         return out;
      }
   }
}
