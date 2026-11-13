package f3ui
{
   import flash.display.DisplayObject;
   import flash.display.Sprite;
   import flash.geom.Point;

   // A pop-up over a menu: a panel outlined in Theme.color and filled black round its content, with an optional
   // fade over the screen behind it. Back closes it; its other actions go to `handler` (the content's). Place it
   // (x, y) before opening it: the fade is drawn from there.
   // See docs/fork/swf_framework.md#modal
   public class Modal extends Sprite
   {
      // The fade's alpha over the whole screen (0 for none) and the panel's fill alpha.
      public var fade:Number = 0;
      public var fill:Number = 0.9;
      // function(action:String, digit:int):Boolean, the content's input while open.
      public var handler:Function;
      // function():void, once closed by Back or close().
      public var onClose:Function;

      private var content:DisplayObject;
      private var panel:Sprite = new Sprite();

      public function Modal()
      {
         super();
         visible = false;
         addChild(panel);
      }

      public function get isOpen() : Boolean
      {
         return visible;
      }

      // Show `body` in a `wide` by `high` panel with its top left at this pop-up's origin, in place of what it
      // showed before.
      public function open(body:DisplayObject, wide:Number, high:Number) : void
      {
         if (content != null && content != body && content.parent == this)
         {
            removeChild(content);
         }
         content = body;
         graphics.clear();
         if (fade > 0 && stage != null)
         {
            var corner:Point = globalToLocal(new Point(0, 0));
            graphics.beginFill(0, fade);
            graphics.drawRect(corner.x, corner.y, stage.stageWidth, stage.stageHeight);
            graphics.endFill();
         }
         panel.graphics.clear();
         Draw.box(panel.graphics, wide, high, fill);
         addChild(body);
         visible = true;
      }

      // Hide it, and tell onClose.
      public function close() : void
      {
         if (!visible)
         {
            return;
         }
         visible = false;
         if (onClose != null)
         {
            onClose();
         }
      }

      // One of Input's actions while open: Back closes, the rest go to `handler`; false when closed.
      public function action(action:String, digit:int) : Boolean
      {
         if (!visible)
         {
            return false;
         }
         if (action == Input.BACK)
         {
            close();
            return true;
         }
         return handler != null && handler(action, digit);
      }
   }
}
