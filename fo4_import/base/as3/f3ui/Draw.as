package f3ui
{
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   import flash.text.TextField;

   // Buttons and panels outlined in Theme.color.
   public class Draw
   {
      // A clickable box with centered text; `handler` gets the click.
      public static function button(parent:Sprite, text:String, x:Number, y:Number, handler:Function,
                                    width:Number = 200) : Sprite
      {
         var box:Sprite = new Sprite();
         box.graphics.lineStyle(2, Theme.color);
         box.graphics.beginFill(Theme.color, 0.1);
         box.graphics.drawRect(0, 0, width, 50);
         box.graphics.endFill();
         var caption:TextField = Text.field(24, "center");
         caption.width = width;
         caption.height = 40;
         caption.y = 10;
         Text.show(caption, text);
         box.addChild(caption);
         box.mouseChildren = false;
         box.buttonMode = true;
         box.x = x;
         box.y = y;
         box.addEventListener(MouseEvent.CLICK, handler);
         parent.addChild(box);
         return box;
      }

      // An outlined box filled black at `alpha`.
      public static function panel(parent:Sprite, x:Number, y:Number, width:Number, height:Number,
                                   alpha:Number) : Sprite
      {
         var box:Sprite = new Sprite();
         box.graphics.lineStyle(2, Theme.color);
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
