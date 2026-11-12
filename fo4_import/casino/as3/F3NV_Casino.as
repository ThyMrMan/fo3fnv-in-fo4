package
{
   import f3nv.casino.Rng;
   import f3nv.casino.Roulette;
   import f3nv.casino.RouletteScreen;
   import f3nv.casino.Slots;
   import f3nv.casino.SlotsScreen;
   import f3ui.Bridge;
   import f3ui.Draw;
   import f3ui.HintBar;
   import f3ui.Host;
   import f3ui.Input;
   import f3ui.Text;
   import f3ui.Theme;
   import flash.display.Loader;
   import flash.display.LoaderInfo;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.net.URLRequest;
   import flash.text.TextField;

   // The casino menu's document class (F3NV_Casino.psc opens it through F4SE and calls these by UI.Invoke).
   // One screen at a time: the phase 0 spike or a game.
   // See docs/fork/fo4_casino_plan.md#design
   public class F3NV_Casino extends MovieClip
   {
      public static const MENU:String = "F3NV_Casino";
      public static const WIDTH:Number = 1280;
      public static const HEIGHT:Number = 720;
      // The spike screen's images, one every this many pixels across (four 256-pixel images fit).
      public static const SPIKE_STEP:Number = 300;

      private var bridge:Bridge = new Bridge();
      private var screen:Sprite;
      private var slots:SlotsScreen;
      private var roulette:RouletteScreen;
      private var statusText:TextField;
      private var pings:int = 0;
      private var input:Input;
      private var hints:HintBar;

      public function F3NV_Casino()
      {
         super();
         var back:Sprite = new Sprite();
         back.graphics.beginFill(0, 0.85);
         back.graphics.drawRect(0, 0, WIDTH, HEIGHT);
         back.graphics.endFill();
         addChild(back);
         addEventListener(Event.ADDED_TO_STAGE, onStage);
      }

      // F4SE hands the menu its f4se object (MountImage, SendExternalEvent).
      public function onF4SEObjCreated(codeObject:Object) : void
      {
         bridge.f4se = codeObject;
         send("F3NV_CasinoReady");
      }

      // Mount each texture path as `prefix<i>`; the names mounted (a failed one is logged, "").
      // MountImage takes the path under Textures without the folder (played 2026-11-08, build 1108d).
      public function MountAll(paths:Array, prefix:String) : Array
      {
         var names:Array = [];
         for (var i:int = 0; i < paths.length; i++)
         {
            var name:String = prefix + i;
            if (bridge.mount(MENU, paths[i], name))
            {
               names.push(name);
            }
            else
            {
               send("F3NV_CasinoInput", "not mounted " + paths[i]);
               names.push("");
            }
         }
         return names;
      }

      // Phase 0: a title, and the same texture under each path form to try, side by side: each mounted
      // one is loaded and shown under its path, and the log says which loaded at what size.
      public function Spike(title:String, paths:Array) : void
      {
         newScreen([[Input.ACCEPT, "Ping"], [Input.BACK, "Close"]]);
         Text.label(screen, 40, 30, 32).text = title;
         statusText = Text.label(screen, 40, 80, 20);
         Draw.button(screen, "Ping", 40, 620, ping);
         Draw.button(screen, "Close", 260, 620, close);
         paths = Bridge.plain(paths);
         for (var i:int = 0; i < paths.length; i++)
         {
            var name:String = "F3NV_Spike" + i;
            var mounted:Boolean = bridge.mount(MENU, paths[i], name);
            var file:String = String(paths[i]).split("/").pop();
            Text.label(screen, 40 + i * SPIKE_STEP, 130, 16).text = file + (mounted ? "" : " (not mounted)");
            send("F3NV_CasinoSpikeImage", paths[i] + (mounted ? " mounted as " + name : " not mounted"));
            if (mounted)
            {
               var image:Loader = new Loader();
               image.x = 40 + i * SPIKE_STEP;
               image.y = 160;
               image.contentLoaderInfo.addEventListener(Event.COMPLETE, onImage);
               image.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, onImageError);
               screen.addChild(image);
               image.load(new URLRequest("img://" + name));
            }
         }
      }

      // The slot machine (F3NV_Casino.psc's OpenSlots): see SlotsScreen.open.
      public function OpenSlots(name:String, chips:int, low:int, high:int, earnings:int, luck:int, seed:uint,
                                stops:Array, symbols:Array, texts:Array) : void
      {
         newScreen(null);
         slots = new SlotsScreen(send);
         screen.addChild(slots);
         slots.open(name, chips, low, high, earnings, luck, seed, Bridge.plain(stops),
                    MountAll(Bridge.plain(symbols), "F3NV_Symbol"), Bridge.plain(texts));
         hints.show(slots.hints());
      }

      // The roulette table (F3NV_Casino.psc's OpenRoulette): see RouletteScreen.open.
      public function OpenRoulette(name:String, chips:int, low:int, high:int, earnings:int, luck:int, seed:uint,
                                   texts:Array) : void
      {
         newScreen(null);
         roulette = new RouletteScreen(send);
         screen.addChild(roulette);
         roulette.open(name, chips, low, high, earnings, luck, seed, Bridge.plain(texts));
         hints.show(roulette.hints());
      }

      // Replay `spins` slot spins per seed at `luck` on FNV's default reel and log them, then the roulette results
      // and spot table: the lines tests/casino/model.py's slot_trace and roulette.py's roulette_trace make.
      public function SelfTest(seeds:Array, spins:int, luck:int) : void
      {
         var out:Array = [];
         seeds = Bridge.plain(seeds);
         for (var s:int = 0; s < seeds.length; s++)
         {
            var machine:Slots = new Slots([2, 2, 2, 2, 2, 2, 2], luck, new Rng(uint(seeds[s])));
            for (var i:int = 0; i < spins; i++)
            {
               out.push(machine.spin().join(","));
            }
         }
         send("F3NV_CasinoSelfTest", "slots " + luck + " " + out.join(" "));
         var results:Array = [];
         for (s = 0; s < seeds.length; s++)
         {
            var wheel:Rng = new Rng(uint(seeds[s]));
            for (i = 0; i < spins; i++)
            {
               results.push(wheel.below(Roulette.POCKETS));
            }
         }
         send("F3NV_CasinoSelfTest", "roulette " + results.join(" ") + " " + Roulette.spotMasks());
      }

      // FO4's menu input: the controls the game maps keys and gamepad buttons to, as actions (Input).
      public function ProcessUserEvent(control:String, down:Boolean) : Boolean
      {
         if (!down)
         {
            send("F3NV_CasinoInput", "control " + control);
         }
         return input != null && input.control(control, down);
      }

      // The game's input device, when it says (Input follows the keys and controls otherwise).
      public function SetPlatform(platform:uint, ps3Switch:Boolean) : void
      {
         if (input != null)
         {
            input.setPlatform(platform);
         }
      }

      // One action from a key, a control or a hint: Back closes, the rest go to the open game; on the spike
      // screen Accept pings.
      private function onAction(action:String, digit:int) : Boolean
      {
         if (action == Input.BACK)
         {
            close();
            return true;
         }
         if (slots != null)
         {
            return slots.control(action);
         }
         if (roulette != null)
         {
            return roulette.control(action);
         }
         if (action == Input.ACCEPT)
         {
            ping();
            return true;
         }
         return false;
      }

      // A fresh screen, drawn in the player's HUD color (Theme.fromHud: F3NV.dll's HudColor, white without it),
      // with the hint bar along the bottom showing `hintList` (the games set theirs once open).
      private function newScreen(hintList:Array) : void
      {
         var dll:Object = bridge.natives("F3NV");
         var color:uint = Theme.fromHud(dll);
         send("F3NV_CasinoInput", "hud color " + color.toString(16) + (dll != null ? "" : " (no F3NV.dll)"));
         if (screen != null)
         {
            removeChild(screen);
         }
         screen = new Sprite();
         slots = null;
         roulette = null;
         addChild(screen);
         if (input != null)
         {
            input.open();
            addChild(hints);
            hints.show(hintList || []);
         }
      }

      private function onStage(e:Event) : void
      {
         input = new Input(stage, onAction);
         input.log = function(text:String) : void { send("F3NV_CasinoInput", text); };
         hints = new HintBar(input);
         hints.x = 40;
         hints.y = HEIGHT - 36;
         Host.focus(this);
      }

      private function onImage(e:Event) : void
      {
         var info:LoaderInfo = LoaderInfo(e.target);
         send("F3NV_CasinoSpikeImage", info.url + " shown " + info.width + "x" + info.height);
      }

      private function onImageError(e:IOErrorEvent) : void
      {
         send("F3NV_CasinoSpikeImage", LoaderInfo(e.target).url + " load failed: " + e.text);
      }

      private function ping(e:Event = null) : void
      {
         pings++;
         statusText.text = "ping " + pings;
         send("F3NV_CasinoPing", pings);
      }

      private function close(e:Event = null) : void
      {
         send("F3NV_CasinoClose");
      }

      private function send(event:String, ... args) : void
      {
         bridge.send.apply(null, [event].concat(args));
      }
   }
}
