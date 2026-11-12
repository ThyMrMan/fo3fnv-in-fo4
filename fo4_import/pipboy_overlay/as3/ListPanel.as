package
{
   import f3ui.Modal;
   import f3ui.ScrollList;
   import f3ui.Text;
   import f3ui.Theme;
   import flash.display.Sprite;
   import flash.geom.Rectangle;
   import flash.text.TextField;

   // A repair or ammo list of F3NV.dll's (its PipboyList native: {heading, rows, chosen, notes, keys}) drawn as a
   // pop-up over the item card (f3ui's Modal): the heading, a window of rows round the highlighted one (a
   // ScrollList), the notes and the keys, each a label on the left and its value on the right. White, as the
   // Pip-Boy's own art is; the game tints the screen. The DLL keeps the list's state and keys; this only draws it.
   // See docs/fork/swf_framework.md#pipboy
   public class ListPanel extends Sprite
   {
      public static const ROWS:int = 8;
      public static const LINE:Number = 30;
      public static const SIZE:int = 20;
      public static const MARGIN:Number = 14;
      public static const WIDTH:Number = 440;

      private var shown:String = "";
      private var modal:Modal = new Modal();
      private var body:Sprite = new Sprite();
      private var rows:ScrollList = new ScrollList();

      public function ListPanel()
      {
         super();
         mouseEnabled = false;
         mouseChildren = false;
         rows.rows = ROWS;
         rows.line = LINE;
         rows.size = SIZE;
         rows.textX = MARGIN;
         rows.centered = true;
         rows.alphas = [1, 1, 1];
         addChild(modal);
      }

      // Draw `list` with its bottom left at the card's (`card`, in this panel's parent's space); nothing when it
      // is the list already drawn.
      public function draw(list:Object, card:Rectangle) : void
      {
         var key:String = signature(list);
         visible = true;
         if (key == shown)
         {
            return;
         }
         shown = key;
         while (body.numChildren > 0)
         {
            body.removeChildAt(0);
         }
         body.graphics.clear();
         var notes:Array = list.notes as Array;
         var width:Number = Math.max(WIDTH, card.width);
         var at:Number = rule(line(list.heading, MARGIN, width), width);
         rows.listWidth = width;
         rows.y = at;
         body.addChild(rows);
         rows.show(list.rows as Array, int(list.chosen));
         at = rule(at + rows.listHeight, width);
         for each (var note:Object in notes)
         {
            at = line(note, at, width);
         }
         var height:Number = line(list.keys, at + MARGIN, width);
         x = card.x;
         y = card.bottom - height;
         modal.open(body, width, height);
      }

      // Hide the panel and forget what it drew.
      public function hide() : void
      {
         visible = false;
         shown = "";
      }

      // `row`'s text on the left and value on the right at `at`; the next line's y.
      private function line(row:Object, at:Number, width:Number) : Number
      {
         var left:TextField = Text.field(SIZE);
         var right:TextField = Text.field(SIZE, "right");
         left.x = MARGIN;
         right.x = width / 2;
         left.width = width - 2 * MARGIN;
         right.width = width / 2 - MARGIN;
         left.y = right.y = at + 2;
         left.height = right.height = LINE;
         Text.show(left, String(row.text));
         Text.show(right, String(row.value));
         body.addChild(left);
         body.addChild(right);
         return at + LINE;
      }

      // A rule across the panel under `at`; the next line's y.
      private function rule(at:Number, width:Number) : Number
      {
         body.graphics.lineStyle(1, Theme.color, 0.6);
         body.graphics.moveTo(MARGIN, at + MARGIN / 2);
         body.graphics.lineTo(width - MARGIN, at + MARGIN / 2);
         return at + MARGIN;
      }

      // Everything `list` shows, as one string, to tell a changed list from the one drawn.
      private static function signature(list:Object) : String
      {
         var parts:Array = [list.heading.text, list.heading.value, list.chosen, list.keys.text, list.keys.value];
         for each (var row:Object in (list.rows as Array).concat(list.notes as Array))
         {
            parts.push(row.text, row.value);
         }
         return parts.join("\n");
      }
   }
}
