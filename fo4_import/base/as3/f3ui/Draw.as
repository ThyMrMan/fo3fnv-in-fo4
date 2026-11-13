package f3ui
{
   import flash.display.Graphics;
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

      // An outline `thick` wide round the `wide` by `high` box at (`x`, `y`) in Theme.color at `alpha`, as four
      // strips that do not overlap (so a translucent outline has no darker corners).
      public static function outline(g:Graphics, x:Number, y:Number, wide:Number, high:Number, thick:Number,
                                     alpha:Number) : void
      {
         g.beginFill(Theme.color, alpha);
         g.drawRect(x, y, wide, thick);
         g.drawRect(x, y + high - thick, wide, thick);
         g.drawRect(x, y + thick, thick, high - 2 * thick);
         g.drawRect(x + wide - thick, y + thick, thick, high - 2 * thick);
         g.endFill();
      }

      // A `width` by `height` box at the origin of `g`, outlined in Theme.color and filled black at `alpha`.
      public static function box(g:Graphics, width:Number, height:Number, alpha:Number) : void
      {
         // Scaleform strokes a drawRect from where the pen was left: start at the box's own corner.
         g.moveTo(0, 0);
         g.lineStyle(2, Theme.color);
         g.beginFill(0, alpha);
         g.drawRect(0, 0, width, height);
         g.endFill();
      }

      // An outlined box filled black at `alpha`.
      public static function panel(parent:Sprite, x:Number, y:Number, width:Number, height:Number,
                                   alpha:Number) : Sprite
      {
         var box:Sprite = new Sprite();
         Draw.box(box.graphics, width, height, alpha);
         box.x = x;
         box.y = y;
         parent.addChild(box);
         return box;
      }
   }
}
