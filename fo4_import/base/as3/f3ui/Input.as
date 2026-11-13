package f3ui
{
   import flash.display.Sprite;
   import flash.display.Stage;
   import flash.events.Event;
   import flash.events.KeyboardEvent;
   import flash.text.TextField;
   import flash.text.TextFieldType;
   import flash.utils.getTimer;

   // One map from keys and the game's controls (ProcessUserEvent) to actions, so a menu only ever sees actions and
   // works the same on keyboard and gamepad; and which device is in use, for HintBar.
   // Moves (up, down, left, right, prev, next) fire on the press, the rest on the release. A press that arrives as
   // both a key and a control fires once, and nothing fires just after the menu opens (the key that opened it).
   // See docs/fork/swf_framework.md#input
   public class Input
   {
      public static const UP:String = "up";
      public static const DOWN:String = "down";
      public static const LEFT:String = "left";
      public static const RIGHT:String = "right";
      public static const ACCEPT:String = "accept";
      public static const BACK:String = "back";
      public static const PREV:String = "prev";
      public static const NEXT:String = "next";
      public static const X:String = "x";
      public static const Y:String = "y";
      // The keys 1 to 9; the handler gets which (0 to 8).
      public static const DIGIT:String = "digit";

      // The game's platforms (SetPlatform): keyboard and mouse, a PC gamepad, Xbox, PlayStation.
      public static const KEYBOARD:uint = 0;
      public static const PC_GAMEPAD:uint = 1;
      public static const XBOX:uint = 2;
      public static const PLAYSTATION:uint = 3;

      // The actions that fire on the press; the rest fire on the release.
      private static const MOVES:Object = {up: true, down: true, left: true, right: true, prev: true, next: true};
      // A key and a control for the same action this close together (ms) are one press.
      private static const SAME_PRESS:int = 150;
      // Nothing fires this long (ms) after open().
      private static const SETTLE:int = 250;
      // A control with no key this close before or after it (ms) came from a gamepad.
      private static const KEY_NEAR:int = 150;
      private static const KEY_1:uint = 49;
      private static const KEY_9:uint = 57;

      // The handler: function(action:String, digit:int):Boolean, true when the menu used it.
      private var handler:Function;
      // Log a line (device changes); null for none.
      public var log:Function;
      private var keys:Object = {};
      private var keyNames:Object = {};
      private var controls:Object = {};
      private var padOnly:Object = {};
      private var watchers:Array = [];
      private var platformNow:uint = KEYBOARD;
      private var padPlatform:uint = PC_GAMEPAD;
      private var fromGame:Boolean = false;
      private var settledAt:int = 0;
      private var lastAt:Object = {};
      private var lastFrom:Object = {};
      private var lastKeyAt:int = -100000;
      private var controlAt:int = -1;
      private var wheelDown:Boolean = false;
      private var ticker:Sprite = new Sprite();

      // Keys and controls from FO4's menu-mode control map: Enter/A accept, Tab/B back, arrows/D-pad move, C and Q
      // or the shoulders page, R and T or X and Y; Esc and Space too, PageUp and PageDown, and the wheel moves.
      public function Input(stage:Stage, handler:Function)
      {
         this.handler = handler;
         mapKey(13, ACCEPT, "ENTER");
         mapKey(32, ACCEPT, "SPACE");
         mapKey(9, BACK, "TAB");
         mapKey(27, BACK, "ESC");
         mapKey(38, UP, "UP");
         mapKey(40, DOWN, "DOWN");
         mapKey(37, LEFT, "LEFT");
         mapKey(39, RIGHT, "RIGHT");
         mapKey(33, PREV, "PGUP");
         mapKey(34, NEXT, "PGDN");
         mapKey(67, PREV, "C");
         mapKey(81, NEXT, "Q");
         mapKey(82, X, "R");
         mapKey(84, Y, "T");
         var names:Object = {Accept: ACCEPT, Cancel: BACK, Up: UP, Down: DOWN, Left: LEFT, Right: RIGHT,
                             LShoulder: PREV, RShoulder: NEXT, LTrigger: PREV, RTrigger: NEXT, XButton: X, YButton: Y,
                             ZoomIn: UP, ZoomOut: DOWN};
         for (var name:String in names)
         {
            mapControl(name, names[name]);
         }
         stage.addEventListener(KeyboardEvent.KEY_DOWN, onKeyDown);
         stage.addEventListener(KeyboardEvent.KEY_UP, onKeyUp);
         open();
      }

      // Key `code` does `action`; `name` is how a hint shows it (the first key mapped to an action names it).
      public function mapKey(code:uint, action:String, name:String) : void
      {
         keys[code] = action;
         keyNames[action] = keyNames[action] || name;
      }

      // The game's control `name` does `action`; with `gamepad` only when a gamepad is in use (a control the
      // keyboard sends for other keys, as the dialogue's MultiActivate on the arrows).
      public function mapControl(name:String, action:String, gamepad:Boolean = false) : void
      {
         controls[name] = action;
         padOnly[name] = gamepad;
      }

      // The menu has (re)opened: ignore what arrives in the next moment.
      public function open() : void
      {
         settledAt = getTimer() + SETTLE;
         wheelDown = false;
      }

      // The game's SetPlatform: from now on the device is the game's word.
      public function setPlatform(platform:uint) : void
      {
         fromGame = true;
         padPlatform = platform != KEYBOARD ? platform : padPlatform;
         useDevice(platform);
      }

      public function get platform() : uint
      {
         return platformNow;
      }

      public function get gamepad() : Boolean
      {
         return platformNow != KEYBOARD;
      }

      // How a hint shows `action`'s key on a keyboard ("" for none).
      public function keyName(action:String) : String
      {
         return keyNames[action] || "";
      }

      // `watcher()` runs each time the device changes.
      public function watch(watcher:Function) : void
      {
         watchers.push(watcher);
      }

      // The menu's ProcessUserEvent(name, down): true when the control is ours and the menu used it.
      public function control(name:String, down:Boolean) : Boolean
      {
         var action:String = controls[name];
         if (action == null || (padOnly[name] && !gamepad))
         {
            return false;
         }
         if (name == "ZoomIn" || name == "ZoomOut")
         {
            var step:Boolean = down || !wheelDown;
            wheelDown = down;
            return step ? fire(action, -1, "wheel") : true;
         }
         if (!fromGame)
         {
            controlAt = getTimer();
            ticker.addEventListener(Event.ENTER_FRAME, judgeDevice);
         }
         return down == (MOVES[action] == true) ? fire(action, -1, "control") : true;
      }

      // A click on something showing `action` (a hint): fires it as the release would.
      public function press(action:String) : Boolean
      {
         return fire(action, -1, "mouse");
      }

      private function onKeyDown(e:KeyboardEvent) : void
      {
         key(e, true);
      }

      private function onKeyUp(e:KeyboardEvent) : void
      {
         key(e, false);
      }

      // A key: ignored while typing into a text box (FallUI's search); else the keyboard is in use, and its action
      // fires on the press or the release as the action does.
      private function key(e:KeyboardEvent, down:Boolean) : void
      {
         var typing:TextField = e.target as TextField;
         if (typing != null && typing.type == TextFieldType.INPUT)
         {
            return;
         }
         lastKeyAt = getTimer();
         if (!fromGame)
         {
            useDevice(KEYBOARD);
         }
         if (e.keyCode >= KEY_1 && e.keyCode <= KEY_9 && !down)
         {
            fire(DIGIT, int(e.keyCode - KEY_1), "key");
            return;
         }
         var action:String = keys[e.keyCode];
         if (action != null && down == (MOVES[action] == true))
         {
            fire(action, -1, "key");
         }
      }

      // A few frames after a control: a gamepad when no key came near it.
      private function judgeDevice(e:Event) : void
      {
         if (getTimer() - controlAt < KEY_NEAR / 2)
         {
            return;
         }
         ticker.removeEventListener(Event.ENTER_FRAME, judgeDevice);
         if (lastKeyAt < controlAt - KEY_NEAR)
         {
            useDevice(padPlatform);
         }
      }

      private function useDevice(platform:uint) : void
      {
         if (platform == platformNow)
         {
            return;
         }
         platformNow = platform;
         if (log != null)
         {
            log("input device " + platform + (fromGame ? " (the game's)" : ""));
         }
         for each (var watcher:Function in watchers)
         {
            watcher();
         }
      }

      // `action` to the menu, unless the menu has just opened or the same press already came another way.
      private function fire(action:String, digit:int, from:String) : Boolean
      {
         var now:int = getTimer();
         if (now < settledAt)
         {
            return true;
         }
         var again:Boolean = lastFrom[action] != from && now - int(lastAt[action]) < SAME_PRESS;
         lastAt[action] = now;
         lastFrom[action] = from;
         return again ? true : handler(action, digit);
      }
   }
}
