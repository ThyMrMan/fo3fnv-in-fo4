package f3ui
{
   import flash.display.Sprite;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.text.TextFormat;
   import flash.utils.Dictionary;

   // Text in FO4's own font, by name (the game maps it per language; no font library is imported).
   public class Text
   {
      public static const FONT:String = "$MAIN_Font";
      public static const BOLD:String = "$MAIN_Font_Bold";

      // Each field's format as field() made it, kept here: assigning a "$KEY" replaced the field's own default
      // format with Times New Roman, which the game has no letters for (spike 5).
      private static var formats:Dictionary = new Dictionary(true);
      // The field templates' keys are translated through (translate()).
      private static var scratch:TextField;

      // A non-selectable field in the game font and Theme.color; `leading` the extra space between lines.
      public static function field(size:int, align:String = null, font:String = FONT, leading:Object = null) : TextField
      {
         var out:TextField = new TextField();
         var format:TextFormat = new TextFormat(font, size, Theme.color, null, null, null, null, null, align, null,
                                                null, null, leading);
         formats[out] = format;
         out.defaultTextFormat = format;
         out.embedFonts = true;
         out.selectable = false;
         return out;
      }

      // `text` in `field` (a template "$KEY<tab>slot0<tab>slot1" filled first), then field()'s format put back as its
      // default and over all of the text.
      // See docs/fork/swf_framework.md#spikes
      public static function show(field:TextField, text:String) : TextField
      {
         var format:TextFormat = formats[field] || field.defaultTextFormat;
         field.text = fill(text);
         field.defaultTextFormat = format;
         field.setTextFormat(format);
         return field;
      }

      // `text` with a template's slots filled: "$KEY<tab>a<tab>b" is $KEY's translation with {0} as a and {1} as b.
      // Anything else is returned as it is, for the game to translate as it is shown.
      // See docs/fork/swf_framework.md#translations
      public static function fill(text:String) : String
      {
         var parts:Array = text != null ? text.split("\t") : [];
         if (parts.length < 2)
         {
            return text;
         }
         var out:String = translate(parts[0]);
         for (var i:int = 1; i < parts.length; i++)
         {
            out = out.split("{" + (i - 1) + "}").join(parts[i]);
         }
         return out;
      }

      // The game's translation of `key` ("$KEY"), read back from a field it was put in; the key itself when no file
      // has it.
      public static function translate(key:String) : String
      {
         scratch = scratch || new TextField();
         scratch.text = key;
         return scratch.text;
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
