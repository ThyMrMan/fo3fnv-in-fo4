package
{
   import f3nv.casino.Rng;
   import f3nv.casino.Roulette;
   import f3nv.casino.RouletteScreen;
   import f3nv.casino.Slots;
   import f3nv.casino.SlotsScreen;
   import f3nv.casino.Ui;
   import flash.display.Loader;
   import flash.display.LoaderInfo;
   import flash.display.MovieClip;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.events.KeyboardEvent;
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

      public var f4se:Object;
      private var screen:Sprite;
      private var slots:SlotsScreen;
      private var roulette:RouletteScreen;
      private var statusText:TextField;
      private var pings:int = 0;

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
         f4se = codeObject;
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
            if (f4se != null && f4se.MountImage(MENU, paths[i], name))
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
         newScreen();
         Ui.label(screen, 40, 30, 32).text = title;
         statusText = Ui.label(screen, 40, 80, 20);
         Ui.button(screen, "Ping", 40, 620, ping);
         Ui.button(screen, "Close", 260, 620, close);
         paths = Ui.plain(paths);
         for (var i:int = 0; i < paths.length; i++)
         {
            var name:String = "F3NV_Spike" + i;
            var mounted:Boolean = f4se != null && f4se.MountImage(MENU, paths[i], name);
            Ui.label(screen, 40 + i * 400, 130, 16).text = paths[i] + (mounted ? "" : " (not mounted)");
            send("F3NV_CasinoSpikeImage", paths[i] + (mounted ? " mounted as " + name : " not mounted"));
            if (mounted)
            {
               var image:Loader = new Loader();
               image.x = 40 + i * 400;
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
         newScreen();
         slots = new SlotsScreen(send);
         screen.addChild(slots);
         slots.open(name, chips, low, high, earnings, luck, seed, Ui.plain(stops),
                    MountAll(Ui.plain(symbols), "F3NV_Symbol"), Ui.plain(texts));
      }

      // The roulette table (F3NV_Casino.psc's OpenRoulette): see RouletteScreen.open.
      public function OpenRoulette(name:String, chips:int, low:int, high:int, earnings:int, luck:int, seed:uint,
                                   texts:Array) : void
      {
         newScreen();
         roulette = new RouletteScreen(send);
         screen.addChild(roulette);
         roulette.open(name, chips, low, high, earnings, luck, seed, Ui.plain(texts));
      }

      // Replay `spins` slot spins per seed at `luck` on FNV's default reel and log them, then the roulette results
      // and spot table: the lines tests/casino/model.py's slot_trace and roulette.py's roulette_trace make.
      public function SelfTest(seeds:Array, spins:int, luck:int) : void
      {
         var out:Array = [];
         seeds = Ui.plain(seeds);
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

      // FO4's menu input: the controls the game maps keys and gamepad buttons to.
      public function ProcessUserEvent(control:String, down:Boolean) : Boolean
      {
         if (down)
         {
            return false;
         }
         send("F3NV_CasinoInput", "control " + control);
         if (control == "Cancel")
         {
            close();
            return true;
         }
         if (slots != null)
         {
            return slots.control(control);
         }
         if (roulette != null)
         {
            return roulette.control(control);
         }
         if (control == "Accept")
         {
            ping();
            return true;
         }
         return false;
      }

      private function newScreen() : void
      {
         if (screen != null)
         {
            removeChild(screen);
         }
         screen = new Sprite();
         slots = null;
         roulette = null;
         addChild(screen);
      }

      private function onStage(e:Event) : void
      {
         stage.addEventListener(KeyboardEvent.KEY_DOWN, onKey);
         stage.focus = this;
      }

      private function onKey(e:KeyboardEvent) : void
      {
         send("F3NV_CasinoInput", "key " + e.keyCode);
         var controls:Object = {27: "Cancel", 9: "Cancel", 13: "Accept", 32: "Accept", 37: "Left", 39: "Right"};
         if (controls[e.keyCode] != undefined)
         {
            ProcessUserEvent(controls[e.keyCode], false);
         }
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
         if (f4se != null)
         {
            f4se.SendExternalEvent.apply(null, [event].concat(args));
         }
      }
   }
}
