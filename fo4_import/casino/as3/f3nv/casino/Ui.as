package f3nv.casino
{
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.text.TextFormat;

   // Text fields and buttons in FO4's own font, drawn white (the menu registers without the HUD color shader).
   public class Ui
   {
      public static const FONT:String = "$MAIN_Font";

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

      public static function label(parent:Sprite, x:Number, y:Number, size:int) : TextField
      {
         var field:TextField = new TextField();
         field.defaultTextFormat = new TextFormat(FONT, size, 0xFFFFFF);
         field.embedFonts = true;
         field.selectable = false;
         field.autoSize = TextFieldAutoSize.LEFT;
         field.x = x;
         field.y = y;
         parent.addChild(field);
         return field;
      }

      public static function button(parent:Sprite, text:String, x:Number, y:Number, handler:Function,
                                    width:Number = 200) : Sprite
      {
         var box:Sprite = new Sprite();
         box.graphics.lineStyle(2, 0xFFFFFF);
         box.graphics.beginFill(0xFFFFFF, 0.1);
         box.graphics.drawRect(0, 0, width, 50);
         box.graphics.endFill();
         var field:TextField = new TextField();
         field.defaultTextFormat = new TextFormat(FONT, 24, 0xFFFFFF, null, null, null, null, null, "center");
         field.embedFonts = true;
         field.selectable = false;
         field.width = width;
         field.height = 40;
         field.y = 10;
         field.text = text;
         box.addChild(field);
         box.mouseChildren = false;
         box.buttonMode = true;
         box.x = x;
         box.y = y;
         box.addEventListener(MouseEvent.CLICK, handler);
         parent.addChild(box);
         return box;
      }

      public static function panel(parent:Sprite, x:Number, y:Number, width:Number, height:Number,
                                   alpha:Number) : Sprite
      {
         var box:Sprite = new Sprite();
         box.graphics.lineStyle(2, 0xFFFFFF);
         box.graphics.beginFill(0, alpha);
         box.graphics.drawRect(0, 0, width, height);
         box.graphics.endFill();
         box.x = x;
         box.y = y;
         parent.addChild(box);
         return box;
      }
   }
}
