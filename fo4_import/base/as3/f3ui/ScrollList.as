package f3ui
{
   import flash.display.Graphics;
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   import flash.text.TextField;

   // The selectable, scrolling list: a window of rows over the items, a marker on the selected one, and scroll
   // marks when there are more. Items are {text, value, dim}: the text on the left, an optional value on the right,
   // `dim` drawn fainter. It takes Input's actions (up and down move round, accept and a digit pick) and the mouse
   // (over selects, a click picks); `onPick(index)` gets the pick.
   // A row is a real child only while it shows: a hidden row would still count in a parent's bounds (the dialogue's
   // shaded backdrop is sized by them).
   // See docs/fork/swf_framework.md#scroll-list
   public class ScrollList extends Sprite
   {
      // Marker styles: a translucent bar behind the row, or an outline round it.
      public static const BAR:String = "bar";
      public static const FRAME:String = "frame";

      // Rows at most; the list's width; text size, font and extra line spacing; whether rows wrap (each as tall as
      // its text, `gap` apart) or are `line` high; the text's left and width (0: the list's less textX each side);
      // padding above and below; the marker's style, left and right insets; the scroll marks' column (0 for none)
      // and their tips' distance from the top and bottom; upper case; alphas of the selected, other and dim rows;
      // whether the selection stays centered (else the window moves only as far as it must).
      public var rows:int = 8;
      public var listWidth:Number = 400;
      public var size:int = 20;
      public var font:String = Text.FONT;
      public var leading:Object = null;
      public var wrap:Boolean = false;
      public var gap:Number = 0;
      public var line:Number = 30;
      public var textX:Number = 14;
      public var textWidth:Number = 0;
      public var padTop:Number = 0;
      public var padBottom:Number = 0;
      public var marker:String = BAR;
      public var markerLeft:Number = 4;
      public var markerRight:Number = 4;
      public var marksX:Number = 0;
      public var marksInset:Number = 0;
      public var upper:Boolean = false;
      public var alphas:Array = [1, 1, 0.45];
      public var centered:Boolean = false;
      // function(item):Sprite, the layer an item's row goes in (its marker too) when not this list; null for none.
      public var layerOf:Function;
      // function(index:int):void, an item picked.
      public var onPick:Function;
      // function():void, after each draw (a selection change may scroll other rows in and change the height).
      public var onDraw:Function;

      private var items:Array = [];
      private var chosen:int = 0;
      private var first:int = 0;
      private var texts:Vector.<TextField>;
      private var values:Vector.<TextField>;
      private var madeColor:uint;
      private var madeWidth:Number = -1;
      private var tall:Number = 0;
      // The layers the last draw drew a marker or rows in, cleared on the next.
      private var layers:Array = [];

      private static const LINE:Number = 2;
      private static const MARK:Number = 8;

      public function ScrollList()
      {
         super();
      }

      // Show `list` with item `selected` selected (kept in range), and draw.
      public function show(list:Array, selected:int) : void
      {
         items = list;
         chosen = Math.max(0, Math.min(selected, items.length - 1));
         draw();
      }

      public function get selected() : int
      {
         return chosen;
      }

      // The first item shown.
      public function get top() : int
      {
         return first;
      }

      public function get count() : int
      {
         return items.length;
      }

      // The list's height as last drawn, padding included.
      public function get listHeight() : Number
      {
         return tall;
      }

      // Move the selection `by` items, round the ends, and draw.
      public function move(by:int) : void
      {
         if (items.length > 0)
         {
            chosen = (chosen + by + items.length) % items.length;
            draw();
         }
      }

      // One of Input's actions: true when the list used it.
      public function action(action:String, digit:int) : Boolean
      {
         if (action == Input.UP || action == Input.DOWN)
         {
            move(action == Input.UP ? -1 : 1);
         }
         else if (action == Input.ACCEPT)
         {
            pick(chosen);
         }
         else if (action == Input.DIGIT)
         {
            pick(first + digit);
         }
         else
         {
            return false;
         }
         return true;
      }

      // Lay out the window round the selection: each shown row's text, alpha and place, the marker, the marks.
      public function draw() : void
      {
         makeRows();
         var shown:int = Math.min(rows, items.length);
         scroll(shown);
         for each (var old:Sprite in layers)
         {
            old.graphics.clear();
         }
         layers = [this];
         graphics.clear();
         var y:Number = padTop;
         for (var i:int = 0; i < rows; i++)
         {
            var layer:Sprite = i < shown ? layerFor(items[first + i]) : null;
            place(texts[i], layer);
            place(values[i], values[i] != null ? layer : null);
            if (layer != null && layers.indexOf(layer) < 0)
            {
               layer.graphics.clear();
               layers.push(layer);
            }
         }
         for (i = 0; i < shown; i++)
         {
            y = row(i, y);
         }
         tall = (shown > 0 ? y - gap : y) + padBottom;
         drawMarks(shown);
         if (onDraw != null)
         {
            onDraw();
         }
      }

      // `index`'s item to onPick, when there is one.
      public function pick(index:int) : void
      {
         if (index >= 0 && index < items.length && onPick != null)
         {
            onPick(index);
         }
      }

      // The window's first item: centered on the selection, or moved only as far as it must to show it.
      private function scroll(shown:int) : void
      {
         if (centered)
         {
            first = Math.max(0, Math.min(chosen - rows / 2, items.length - shown));
            return;
         }
         first = Math.max(0, Math.min(first, items.length - shown));
         first = chosen < first ? chosen : (chosen >= first + shown ? chosen - shown + 1 : first);
      }

      // Row `i` (item first + i) at `y`: its text and value, alpha and marker; the next row's y.
      private function row(i:int, y:Number) : Number
      {
         var item:Object = items[first + i];
         var at:int = first + i;
         var text:TextField = texts[i];
         Text.show(text, upper ? String(item.text).toUpperCase() : String(item.text));
         text.alpha = at == chosen ? alphas[0] : (item.dim ? alphas[2] : alphas[1]);
         text.y = wrap ? y : y + 2;
         if (values[i] != null)
         {
            Text.show(values[i], item.value != null ? String(item.value) : "");
            values[i].alpha = text.alpha;
            values[i].y = text.y;
         }
         var high:Number = wrap ? text.height : line;
         if (at == chosen)
         {
            mark(Sprite(text.parent).graphics, wrap ? text.y - 3 : y, wrap ? text.height + 6 : line);
         }
         return y + high + gap;
      }

      // The selection marker over `high` from `y`, in `g` (the selected row's layer).
      private function mark(g:Graphics, y:Number, high:Number) : void
      {
         var wide:Number = listWidth - markerLeft - markerRight;
         if (marker == BAR)
         {
            g.beginFill(Theme.color, 0.25);
            g.drawRect(markerLeft, y, wide, high);
            g.endFill();
            return;
         }
         Draw.outline(g, markerLeft, y, wide, high, LINE, 0.9);
      }

      // When the items run past the window: an up and a down mark in the marks column joined by a line, each dim
      // when there is nothing more that way.
      private function drawMarks(shown:int) : void
      {
         if (marksX <= 0 || items.length <= shown)
         {
            return;
         }
         graphics.beginFill(Theme.color, 0.5);
         graphics.drawRect(marksX - LINE / 2, marksInset + 12, LINE, tall - 2 * marksInset - 24);
         graphics.endFill();
         arrow(marksInset, -1, first > 0 ? 1 : 0.3);
         arrow(tall - marksInset, 1, first + shown < items.length ? 1 : 0.3);
      }

      // A scroll mark centered on the marks column, its tip at `y`, pointing up (-1) or down (1).
      private function arrow(y:Number, way:int, alpha:Number) : void
      {
         graphics.beginFill(Theme.color, alpha);
         graphics.moveTo(marksX - MARK, y - way * MARK);
         graphics.lineTo(marksX + MARK, y - way * MARK);
         graphics.lineTo(marksX, y);
         graphics.lineTo(marksX - MARK, y - way * MARK);
         graphics.endFill();
      }

      // The rows' fields, made on the first draw and again when Theme.color or the width changed (a field keeps
      // the color it was made with).
      private function makeRows() : void
      {
         if (texts != null && texts.length == rows && madeColor == Theme.color && madeWidth == listWidth)
         {
            return;
         }
         for each (var old:TextField in (texts || new Vector.<TextField>()).concat(values || new Vector.<TextField>()))
         {
            place(old, null);
         }
         madeColor = Theme.color;
         madeWidth = listWidth;
         texts = new Vector.<TextField>();
         values = new Vector.<TextField>();
         for (var i:int = 0; i < rows; i++)
         {
            texts.push(field(i, null));
            values.push(wrap ? null : field(i, "right"));
         }
      }

      // Row `i`'s text field (`align` "right" for its value): wrapping to the list's width, or one line high.
      private function field(i:int, align:String) : TextField
      {
         var out:TextField = Text.field(size, align, font, leading);
         out.name = String(i);
         out.x = align == null ? textX : listWidth / 2;
         out.width = align != null ? listWidth / 2 - textX : (textWidth > 0 ? textWidth : listWidth - 2 * textX);
         if (wrap)
         {
            out.multiline = true;
            out.wordWrap = true;
            out.autoSize = "left";
         }
         else
         {
            out.height = line;
         }
         out.addEventListener(MouseEvent.MOUSE_OVER, onOver);
         out.addEventListener(MouseEvent.CLICK, onClick);
         return out;
      }

      private function layerFor(item:Object) : Sprite
      {
         var layer:Sprite = layerOf != null ? layerOf(item) : null;
         return layer || this;
      }

      // `field` in `layer`, or out of every parent for null.
      private static function place(field:TextField, layer:Sprite) : void
      {
         if (field == null || field.parent == layer)
         {
            return;
         }
         if (field.parent != null)
         {
            field.parent.removeChild(field);
         }
         if (layer != null)
         {
            layer.addChild(field);
         }
      }

      private function onOver(e:MouseEvent) : void
      {
         var at:int = first + int(e.currentTarget.name);
         if (at != chosen && at < items.length)
         {
            chosen = at;
            draw();
         }
      }

      private function onClick(e:MouseEvent) : void
      {
         pick(first + int(e.currentTarget.name));
      }
   }
}
