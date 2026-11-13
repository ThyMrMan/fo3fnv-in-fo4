package f3nv.casino
{
   import f3ui.Draw;
   import f3ui.Input;
   import f3ui.Text;
   import f3ui.Theme;
   import flash.display.Loader;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.MouseEvent;
   import flash.net.URLRequest;
   import flash.text.TextField;
   import flash.utils.setTimeout;

   // Caravan, FNV's four screens in its order: the bet (Auto-Match, Raise, Accept), the deck builder (click a card to
   // add or remove it, Randomize, Play Caravan from 30 cards), the table (click a hand card, then a caravan's next
   // row or a card; Discard Card, Discard Caravan, Forfeit) and the result. The deck goes to Papyrus as bit chunks
   // (`F3NV_CaravanDeck`, 30 cards each) when play starts, the result as `F3NV_CaravanResult(won, stake)`; Papyrus
   // moves the money. See docs/fork/fo4_casino_plan.md#caravan-built
   public class CaravanScreen extends Sprite
   {
      // Indexes into the texts Papyrus passes (F3NV_Casino.psc's CaravanTexts: FNV's settings and menu strings).
      public static const PLAY_CARAVAN:int = 0;
      public static const TOTAL_FUNDS:int = 1;
      public static const CURRENT_ANTE:int = 2;
      public static const YOUR_ANTE:int = 3;
      public static const ANTE_POT:int = 4;
      public static const AUTO_MATCH:int = 5;
      public static const RAISE:int = 6;
      public static const ACCEPT:int = 7;
      public static const EXIT:int = 8;
      public static const CARAVAN_DECK:int = 9;
      public static const ALL_CARDS:int = 10;
      public static const CARDS_IN_DECK:int = 11;
      public static const TOTAL_CARDS:int = 12;
      public static const ADD:int = 13;
      public static const REMOVE:int = 14;
      public static const RANDOMIZE:int = 15;
      public static const PLACE_CARD:int = 16;
      public static const DISCARD_CARD:int = 17;
      public static const DISCARD_CARAVAN:int = 18;
      public static const FORFEIT:int = 19;
      public static const QUIT:int = 20;
      public static const YES:int = 21;
      public static const NO:int = 22;
      public static const YOU_WIN:int = 23;
      public static const YOU_LOSE:int = 24;
      public static const WINNINGS:int = 25;
      public static const LOSSES:int = 26;
      public static const WIN_LOSS:int = 27;
      public static const BIGGEST:int = 28;
      public static const PRESS_ANY:int = 29;
      public static const SELECT_CARD:int = 30;

      // Cards per deck chunk Papyrus reads (bits 0-29 of an int).
      public static const CHUNK:int = 30;
      public static const CARD_W:Number = 64;
      public static const CARD_H:Number = 90;
      public static const ROW_STEP:Number = 24;
      public static const FACE_STEP:Number = 14;
      public static const LANE_X:Array = [90, 330, 570];
      public static const MIDDLE:Number = 330;
      public static const PAGE:int = 60;
      public static const NAMES:Array = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "", "J", "Q", "K", "Jk"];
      public static const SUIT_NAMES:Array = ["", "H", "S", "D", "C", ""];
      public static const OPPONENT_MS:int = 500;

      // The hint bar's show (F3NV_Casino sets it): each screen shows its own hints.
      public var showHints:Function;
      private var send:Function;
      private var mount:Function;
      private var texts:Array;
      private var opponentName:String;
      private var table:Array = [];
      private var collection:Array = [];
      private var inDeck:Object = {};
      private var opponentCards:Array = [];
      private var stats:Array;
      private var mode:int;
      private var rng:Rng;
      private var funds:int;
      private var bet:int = 0;
      private var ante:int;
      private var cap:int;
      private var game:Caravan;
      private var step:String = "";
      private var page:int = 0;
      private var selected:int = -1;
      private var choosingLane:Boolean = false;
      private var asking:Boolean = false;
      private var view:Sprite;
      private var images:Object = {};
      private var imageCount:int = 0;

      public function CaravanScreen(sender:Function)
      {
         super();
         send = sender;
      }

      // Papyrus's data (F3NV_Casino.OpenCaravanMenu): the opponent, both sides' funds, ante share, Barter, AI mode,
      // a seed, the card table ("suit,value,face,back" joined by "|", per chunk), the player's owned and deck cards
      // and the opponent's deck (card table places), FNV's five results to date and the texts.
      public function open(name:String, playerFunds:int, opponentFunds:int, share:Number, barter:int, aiMode:int,
                           seed:uint, cardTable:Array, ownedMasks:Array, deckMasks:Array, opponentDeck:Array,
                           results:Array, menuTexts:Array, mounter:Function) : void
      {
         opponentName = name;
         funds = playerFunds;
         ante = Caravan.ante(opponentFunds, share);
         cap = Caravan.raiseCap(opponentFunds, share, barter);
         mode = aiMode;
         rng = new Rng(seed);
         texts = menuTexts;
         stats = results;
         mount = mounter;
         readTable(cardTable);
         readCollection(ownedMasks, deckMasks);
         for each (var index:int in opponentDeck)
         {
            if (index >= 0 && index < table.length)
            {
               opponentCards.push(card(index));
            }
         }
         showBet();
      }

      private function readTable(chunks:Array) : void
      {
         for each (var chunk:String in chunks)
         {
            for each (var entry:String in chunk.split("|"))
            {
               var parts:Array = entry.split(",");
               if (parts.length >= 4)
               {
                  table.push({suit: int(parts[0]), value: int(parts[1]), face: parts[2], back: parts[3]});
               }
            }
         }
      }

      public static function hasBit(masks:Array, index:int) : Boolean
      {
         var chunk:int = int(index / CHUNK);
         return chunk < masks.length && ((int(masks[chunk]) >> (index % CHUNK)) & 1) == 1;
      }

      // Every card the player has, by value as FNV sorts them (then by table place), and which are in the deck.
      private function readCollection(ownedMasks:Array, deckMasks:Array) : void
      {
         for (var i:int = 0; i < table.length; i++)
         {
            var deck:Boolean = hasBit(deckMasks, i);
            if (deck || hasBit(ownedMasks, i))
            {
               collection.push(i);
               inDeck[i] = deck;
            }
         }
         collection.sort(function(a:int, b:int) : int
         {
            return table[a].value != table[b].value ? table[a].value - table[b].value : a - b;
         });
      }

      private function card(index:int) : Array
      {
         return [table[index].value, table[index].suit, index];
      }

      private function text(index:int) : String
      {
         return index < texts.length ? String(texts[index]) : "";
      }

      private function fresh() : void
      {
         if (view != null)
         {
            removeChild(view);
         }
         view = new Sprite();
         addChild(view);
         if (showHints != null)
         {
            showHints(hints());
         }
         Text.label(view, 40, 20, 30).text = opponentName;
      }

      // ---- The bet

      private function showBet() : void
      {
         step = "bet";
         fresh();
         Draw.panel(view, 40, 80, 700, 300, 0.6);
         var lines:Array = [text(TOTAL_FUNDS) + funds, text(CURRENT_ANTE) + ante, text(YOUR_ANTE) + bet,
                            text(ANTE_POT) + 2 * Math.min(bet, ante)];
         Text.label(view, 70, 110, 26).text = lines.join("\n");
         var match:Sprite = Draw.button(view, text(AUTO_MATCH), 40, 420, onMatch, 220);
         var raising:Sprite = Draw.button(view, text(RAISE), 280, 420, onRaise, 220);
         var accept:Sprite = Draw.button(view, text(ACCEPT), 520, 420, onAccept, 220);
         Draw.button(view, text(EXIT), 760, 420, onExit, 220);
         match.alpha = funds == 0 || (bet > 0 && (bet >= ante || bet >= funds)) ? 0.35 : 1;
         raising.alpha = funds == 0 || bet >= funds ? 0.35 : 1;
         accept.alpha = ready() ? 1 : 0.35;
      }

      private function ready() : Boolean
      {
         return bet > 0 || ante == 0;
      }

      private function onMatch(e:Event = null) : void
      {
         bet = Math.min(ante, funds);
         showBet();
      }

      // FNV's Raise opens a quantity menu; here each press raises by its small step, the opponent matching to its cap.
      private function onRaise(e:Event = null) : void
      {
         bet += Math.max(0, Math.min(Caravan.raiseStep(funds - bet), funds - bet));
         if (bet > ante)
         {
            ante = Math.min(cap, bet);
         }
         showBet();
      }

      private function onAccept(e:Event = null) : void
      {
         if (ready())
         {
            showDeck();
         }
      }

      private function onExit(e:Event = null) : void
      {
         send("F3NV_CasinoClose");
      }

      // ---- The deck builder

      private function deckSize() : int
      {
         var n:int = 0;
         for each (var index:int in collection)
         {
            n += inDeck[index] ? 1 : 0;
         }
         return n;
      }

      private function showDeck() : void
      {
         step = "deck";
         fresh();
         Text.label(view, 40, 64, 22).text = text(CARAVAN_DECK) + " / " + text(ALL_CARDS) + "    "
            + text(CARDS_IN_DECK) + deckSize() + "    " + text(TOTAL_CARDS) + collection.length;
         var first:int = page * PAGE;
         for (var i:int = first; i < Math.min(first + PAGE, collection.length); i++)
         {
            tile(collection[i], 40 + ((i - first) % 12) * 78, 100 + int((i - first) / 12) * 96);
         }
         var pages:int = Math.max(1, Math.ceil(collection.length / PAGE));
         Draw.button(view, "<", 40, 600, onPrevious, 60);
         Text.label(view, 120, 612, 24).text = (page + 1) + "/" + pages;
         Draw.button(view, ">", 220, 600, onNext, 60);
         Draw.button(view, text(RANDOMIZE), 300, 600, onRandomize, 220);
         Draw.button(view, text(PLAY_CARAVAN), 540, 600, onPlay, 220).alpha = deckSize() >= Caravan.SMALLEST_DECK ? 1 : 0.35;
         Draw.button(view, text(EXIT), 780, 600, onExit, 220);
      }

      private function tile(index:int, x:Number, y:Number) : void
      {
         var box:Sprite = Draw.panel(view, x, y, 70, 88, inDeck[index] ? 0.2 : 0.7);
         box.alpha = inDeck[index] ? 1 : 0.5;
         showImage(box, table[index].face, 3, 3, 64, 82);
         var label:TextField = Text.label(box, 4, 62, 16);
         label.text = NAMES[table[index].value] + SUIT_NAMES[table[index].suit];
         box.buttonMode = true;
         box.mouseChildren = false;
         box.addEventListener(MouseEvent.CLICK, function(e:Event) : void
         {
            toggle(index);
         });
      }

      // FNV's Add (under 108 in the deck) and Remove.
      private function toggle(index:int) : void
      {
         if (inDeck[index] || deckSize() < Caravan.LARGEST_DECK)
         {
            inDeck[index] = !inDeck[index];
         }
         showDeck();
      }

      private function onPrevious(e:Event = null) : void
      {
         page = Math.max(0, page - 1);
         showDeck();
      }

      private function onNext(e:Event = null) : void
      {
         page = Math.min(Math.max(0, Math.ceil(collection.length / PAGE) - 1), page + 1);
         showDeck();
      }

      private function onRandomize(e:Event = null) : void
      {
         for each (var index:int in collection)
         {
            inDeck[index] = false;
         }
         for each (var place:int in Caravan.randomize(collection.length, rng))
         {
            inDeck[collection[place]] = true;
         }
         showDeck();
      }

      // Play Caravan: the deck to Papyrus (every chunk, so it is kept as FNV keeps it), then the game.
      private function onPlay(e:Event = null) : void
      {
         if (deckSize() < Caravan.SMALLEST_DECK)
         {
            return;
         }
         var chunks:int = Math.ceil(table.length / CHUNK);
         var deck:Array = [];
         for (var chunk:int = 0; chunk < chunks; chunk++)
         {
            var bits:int = 0;
            for (var k:int = 0; k < CHUNK; k++)
            {
               bits |= inDeck[chunk * CHUNK + k] ? 1 << k : 0;
            }
            send("F3NV_CaravanDeck", chunk, bits);
         }
         for each (var index:int in collection)
         {
            if (inDeck[index])
            {
               deck.push(card(index));
            }
         }
         game = new Caravan(deck, opponentCards, mode, rng);
         showTable();
         later();
      }

      // ---- The table

      private function later() : void
      {
         if (game.waiting && !game.result)
         {
            setTimeout(function() : void
            {
               game.opponent();
               showTable();
               later();
            }, OPPONENT_MS);
         }
      }

      private function laneX(lane:int) : Number
      {
         return LANE_X[lane < 3 ? lane : Caravan.LANES - 1 - lane];
      }

      private function cellY(lane:int, row:int) : Number
      {
         return lane < 3 ? MIDDLE + 30 + row * ROW_STEP : MIDDLE - 30 - CARD_H - row * ROW_STEP;
      }

      private function showTable() : void
      {
         if (game.result)
         {
            if (step != "result")
            {
               finished();
            }
            return;
         }
         step = "table";
         fresh();
         for (var lane:int = 0; lane < Caravan.LANES; lane++)
         {
            showLane(lane);
         }
         var hand:Array = game.hands[0];
         for (var i:int = 0; i < hand.length; i++)
         {
            handCard(i, 90 + i * 72, 610);
         }
         Text.label(view, 820, 64, 22).text = text(ANTE_POT) + 2 * Math.min(bet, ante) + "\n" + opponentName + ": "
            + text(CARDS_IN_DECK) + game.decks[1].length + "\n" + text(CARDS_IN_DECK) + game.decks[0].length;
         var buttons:Array = [[PLACE_CARD, onPlace], [DISCARD_CARD, onDiscard], [DISCARD_CARAVAN, onDiscardLane],
                              [FORFEIT, onForfeit]];
         for (i = 0; i < buttons.length; i++)
         {
            Draw.button(view, text(buttons[i][0]), 1000, 330 + i * 60, buttons[i][1], 240);
         }
         if (asking)
         {
            askForfeit();
         }
      }

      private function showLane(lane:int) : void
      {
         var cells:Array = game.lanes[lane];
         var total:int = Caravan.laneTotal(cells);
         var label:TextField = Text.label(view, laneX(lane), lane < 3 ? MIDDLE + 4 : MIDDLE - 28, 20);
         label.text = String(total);
         label.textColor = Caravan.band(total) == 0 ? 0x66FF66 : Caravan.band(total) > 0 ? 0xFF6666 : Theme.color;
         var count:int = Caravan.laid(cells);
         for (var row:int = 0; row <= Math.min(count, Caravan.ROWS - 1); row++)
         {
            var full:Boolean = row >= count - 1;
            var spot:Sprite = new Sprite();
            spot.graphics.lineStyle(1, Theme.color, row == count ? 0.4 : 0);
            spot.graphics.beginFill(0, 0.01);
            spot.graphics.drawRect(0, 0, CARD_W + 3 * FACE_STEP, full ? CARD_H : ROW_STEP);
            spot.graphics.endFill();
            spot.x = laneX(lane);
            spot.y = cellY(lane, row) + (!full && lane >= 3 ? CARD_H - ROW_STEP : 0);
            view.addChild(spot);
            for (var f:int = 0; row < count && f < cells[row].length; f++)
            {
               showImage(view, table[cells[row][f][2]].face, laneX(lane) + f * FACE_STEP, cellY(lane, row), CARD_W, CARD_H);
            }
            spot.buttonMode = true;
            spot.addEventListener(MouseEvent.CLICK, onCell(lane, row));
            view.setChildIndex(spot, view.numChildren - 1);
         }
      }

      private function handCard(index:int, x:Number, y:Number) : void
      {
         var box:Sprite = new Sprite();
         box.x = x;
         box.y = index == selected ? y - 16 : y;
         view.addChild(box);
         showImage(box, table[game.hands[0][index][2]].face, 0, 0, CARD_W, CARD_H);
         if (index == selected)
         {
            Draw.panel(box, -2, -2, CARD_W + 4, CARD_H + 4, 0);
         }
         box.buttonMode = true;
         box.mouseChildren = false;
         box.addEventListener(MouseEvent.CLICK, function(e:Event) : void
         {
            selected = index;
            choosingLane = false;
            showTable();
         });
      }

      private function onCell(lane:int, row:int) : Function
      {
         return function(e:Event) : void
         {
            if (choosingLane)
            {
               choosingLane = false;
               game.discardLane(lane);
            }
            else if (selected >= 0 && game.play(selected, lane, aimed(lane, row)))
            {
               selected = -1;
            }
            showTable();
            later();
         };
      }

      // A face card clicked on the next row means the last card (the two overlap on screen).
      private function aimed(lane:int, row:int) : int
      {
         var face:Boolean = game.hands[0][selected][0] > 10;
         return face && row > 0 && !game.lanes[lane][row].length ? row - 1 : row;
      }

      // Place Card: at the opening the selected number opens the next caravan; else pick a caravan's row.
      private function onPlace(e:Event = null) : void
      {
         if (game.opening && selected >= 0 && game.play(selected, 0, 0))
         {
            selected = -1;
         }
         showTable();
         later();
      }

      private function onDiscard(e:Event = null) : void
      {
         if (selected >= 0 && game.discard(selected))
         {
            selected = -1;
         }
         showTable();
         later();
      }

      private function onDiscardLane(e:Event = null) : void
      {
         choosingLane = !game.opening && !game.waiting;
      }

      private function onForfeit(e:Event = null) : void
      {
         asking = true;
         showTable();
      }

      private function askForfeit() : void
      {
         Draw.panel(view, 240, 220, 800, 260, 0.9);
         var question:TextField = Text.label(view, 270, 240, 22);
         question.wordWrap = true;
         question.width = 740;
         question.text = text(QUIT);
         Draw.button(view, text(YES), 400, 400, onYes, 200);
         Draw.button(view, text(NO), 680, 400, onNo, 200);
      }

      private function onYes(e:Event = null) : void
      {
         asking = false;
         game.forfeit();
         showTable();
      }

      private function onNo(e:Event = null) : void
      {
         asking = false;
         showTable();
      }

      // ---- The result

      private function finished() : void
      {
         step = "result";
         var won:Boolean = game.result == Caravan.WON;
         var stake:int = Math.min(bet, ante);
         send("F3NV_CaravanResult", won, stake);
         stats[won ? 0 : 1] += stake;
         stats[won ? 2 : 3] += 1;
         stats[4] = won ? Math.max(stats[4], stake) : stats[4];
         fresh();
         Draw.panel(view, 240, 160, 800, 360, 0.8);
         Text.label(view, 280, 190, 36).text = text(won ? YOU_WIN : YOU_LOSE);
         Text.label(view, 280, 260, 24).text = [text(WINNINGS) + (stats[0] - stats[1]), text(LOSSES) + stats[1],
            text(WIN_LOSS) + stats[2] + "/" + stats[3], text(BIGGEST) + stats[4], "", text(PRESS_ANY)].join("\n");
         addEventListener(MouseEvent.CLICK, onExit);
      }

      // Input's actions: at the bet Accept goes on, X Auto-Match, Y Raise; at the deck Accept plays, Y randomizes,
      // left and right page; at the table Back asks to forfeit (before play F3NV_Casino's Back leaves); any at the end.
      public function control(action:String) : Boolean
      {
         var steps:Object = {bet: {accept: onAccept, x: onMatch, y: onRaise},
                             deck: {accept: onPlay, y: onRandomize, left: onPrevious, right: onNext},
                             table: {back: onForfeit}};
         if (step == "result")
         {
            onExit();
            return true;
         }
         var handler:Function = steps[step] != null ? steps[step][action] : null;
         if (handler == null)
         {
            return false;
         }
         handler();
         return true;
      }

      // The hint bar's hints for the screen showing.
      public function hints() : Array
      {
         if (step == "bet")
         {
            return [[Input.ACCEPT, text(ACCEPT)], [Input.X, text(AUTO_MATCH)], [Input.Y, text(RAISE)],
                    [Input.BACK, text(EXIT)]];
         }
         if (step == "deck")
         {
            return [[Input.ACCEPT, text(PLAY_CARAVAN)], [Input.Y, text(RANDOMIZE)], [[Input.LEFT, Input.RIGHT], "<>"],
                    [Input.BACK, text(EXIT)]];
         }
         return step == "table" ? [[Input.BACK, text(FORFEIT)]] : [[Input.ACCEPT, text(PRESS_ANY)]];
      }

      // Leaving is free before the game; in it, Cancel asks to forfeit (FNV's sQuitCaravanText).
      public function canLeave() : Boolean
      {
         return step == "bet" || step == "deck" || step == "result";
      }

      private function showImage(parent:Sprite, path:String, x:Number, y:Number, w:Number, h:Number) : void
      {
         var name:String = images[path];
         if (name == null)
         {
            var urls:Array = mount([path], "F3NV_CaravanImage" + imageCount + "_");
            imageCount++;
            name = urls.length ? urls[0] : "";
            images[path] = name;
         }
         var loader:Loader = new Loader();
         loader.contentLoaderInfo.addEventListener(Event.COMPLETE, function(e:Event) : void
         {
            loader.width = w;
            loader.height = h;
         });
         loader.x = x;
         loader.y = y;
         parent.addChild(loader);
         if (name)
         {
            loader.load(new URLRequest(name));
         }
      }
   }
}
