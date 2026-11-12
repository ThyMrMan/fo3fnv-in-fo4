package f3ui
{
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;

   // A row of button hints, each an action's button and a label: on a keyboard the key's name ("ENTER) SPIN"), on a
   // gamepad the button's glyph from the game's controller font, Xbox or PlayStation as Input says. It redraws when
   // the device changes; clicking a hint fires its action.
   // See docs/fork/swf_framework.md#input
   public class HintBar extends Sprite
   {
      // The game's controller font (fontconfig.txt maps it, fonts_console.swf has it).
      public static const GLYPHS:String = "$Controller_Buttons";
      // Each action's glyph in that font: Xbox (a PC gamepad too) and PlayStation.
      private static const XBOX:Object = {accept: "A", back: "B", x: "C", y: "D", prev: "G", next: "L",
                                          up: "W", down: "V", left: "T", right: "U"};
      private static const PLAYSTATION:Object = {accept: "a", back: "d", x: "c", y: "b", prev: "g", next: "m",
                                                 up: "w", down: "v", left: "t", right: "u"};
      private static const GAP:Number = 24;

      private var input:Input;
      private var size:int;
      private var hints:Array = [];

      // A bar of `size` text over `input`'s device.
      public function HintBar(input:Input, size:int = 18)
      {
         super();
         this.input = input;
         this.size = size;
         input.watch(draw);
      }

      // Show `hints`: [actions, label] each, actions one action or an array of them shown together ([LEFT, RIGHT]),
      // the label text or a $KEY.
      public function show(hints:Array) : void
      {
         this.hints = hints;
         draw();
      }

      // The button `actions` show on the current device: key names joined by "/" and ")", or glyphs.
      public function buttons(actions:Array) : String
      {
         var glyphs:Object = input.platform == Input.PLAYSTATION ? PLAYSTATION : XBOX;
         var out:Array = [];
         for each (var action:String in actions)
         {
            out.push(input.gamepad ? glyphs[action] || "" : input.keyName(action));
         }
         return input.gamepad ? out.join("") : out.join("/") + ")";
      }

      private function draw() : void
      {
         while (numChildren > 0)
         {
            removeChildAt(0);
         }
         var x:Number = 0;
         for each (var hint:Array in hints)
         {
            var actions:Array = hint[0] is Array ? hint[0] : [hint[0]];
            var item:Sprite = new Sprite();
            var button:TextField = part(item, buttons(actions), input.gamepad ? GLYPHS : Text.BOLD, 0);
            part(item, String(hint[1]), Text.BOLD, button.width + size / 3);
            item.x = x;
            item.name = actions[0];
            item.mouseChildren = false;
            item.buttonMode = true;
            item.addEventListener(MouseEvent.CLICK, onClick);
            addChild(item);
            x += item.width + GAP;
         }
      }

      // A field in `font` showing `text` at `x` in `item`.
      private function part(item:Sprite, text:String, font:String, x:Number) : TextField
      {
         var field:TextField = Text.field(size, null, font);
         field.autoSize = TextFieldAutoSize.LEFT;
         field.x = x;
         item.addChild(Text.show(field, text));
         return field;
      }

      private function onClick(e:MouseEvent) : void
      {
         input.press(e.currentTarget.name);
      }
   }
}
