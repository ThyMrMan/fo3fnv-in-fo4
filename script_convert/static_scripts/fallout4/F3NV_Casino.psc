ScriptName F3NV_Casino extends Quest
{FNV's casino games and Caravan, the bank: opens the casino menu (F3NV_Casino.swf, registered with F4SE) for the converted openers after FNV's refusals, settles each round's chips into the casino's earnings and level, and keeps the player's Caravan cards (FNV's two lists: owned and deck). Spike() opens the phase 0 test screen (cqf FNV_Casino Spike). See docs/fork/fo4_casino_plan.md#design}

String Property MenuName = "F3NV_Casino" AutoReadOnly Hidden
{The menu's name, also its movie's name under Interface.}
FormList Property Owned Auto Const
{The player's Caravan cards out of the deck (card MISCs).}
FormList Property Deck Auto Const
{The player's Caravan deck.}
FormList Property CaravanCards Auto Const
{Every Caravan card (MISCs); CardTable describes them in this order.}
FormList Property CaravanMoney Auto Const
{Every Caravan money item (MISCs worth FNV's value), counted with caps as Caravan funds.}
String[] Property CardTable Auto Const
{Each Caravan card's "suit,value,face texture,back texture", joined by "|", CardChunk cards to a string.}
ActorValue Property Barter Auto Const
{FNV's Barter skill: it raises how much a Caravan opponent matches.}
String[] Property CaravanTexts Auto Const
{The Caravan screens' texts (FNV's settings and menu strings), in CaravanScreen.as's order.}
String Property BannedText Auto Const
String Property BrokeText Auto Const
String Property MinWinText Auto Const
String Property CardCountText Auto Const
String Property TimeLeftText Auto Const
String[] Property AntiCheatTexts Auto Const
{Per game (1 blackjack, 2 roulette, 3 slots): FNV's anti-cheat text.}
Float Property AntiCheatSeconds Auto Const
{FNV's iAntiCheatDuration: games refuse this long after a load.}
String[] Property SlotTexts Auto Const
{The slot screen's labels and results (FNV's settings), in SlotsScreen.as's order.}
String[] Property RouletteTexts Auto Const
{The roulette screen's labels, bet names and results (FNV's settings), in RouletteScreen.as's order.}
String[] Property BlackjackTexts Auto Const
{The blackjack screen's buttons, labels and results (FNV's settings), in BlackjackScreen.as's order.}
String Property SpikeImage Auto Const
{Spike: the converted card face the test screen mounts (under Textures).}

Int Property MenuFlags = 0x800049D AutoReadOnly Hidden
{F4SE's default menu flags (0x801849D: pauses, cursor, menu context, modal, no pause menu) without Custom Rendering (0x8000) and Assign Cursor To Renderer (0x10000): with those the menu drew only around the cursor (played 2026-11-08).}
Int Property ExtendedFlags = 2 AutoReadOnly Hidden
{F4SE extended flags: drop the cursor when a gamepad is in use; no HUD color (it needs Custom Rendering).}
Int Property CaravanMinimum = 30 AutoReadOnly Hidden
{FNV's smallest deck: the menu won't open with fewer cards.}
Int Property CardChunk = 30 AutoReadOnly Hidden
{Cards per CardTable string and per deck chunk the menu sends (bits 0-29 of an Int).}
Int Property CaravanGame = 4 AutoReadOnly Hidden
{Caravan's game number while its menu is open.}

Int Property Blackjack = 1 AutoReadOnly Hidden
{The blackjack table's game number (Open's aiGame).}
Int Property Roulette = 2 AutoReadOnly Hidden
{The roulette table's game number (Open's aiGame).}
Int Property Slots = 3 AutoReadOnly Hidden
{The slot machine's game number (Open's aiGame).}

Float loadedAt = -1000.0
String spikeTitle
Bool spiking
F3NV_CasinoData playing
Int playingGame
Int betLow
Int betHigh
Int selfTestLuck
ObjectReference opponent
FormList opponentDeck
Int caravanMode
Float anteShare
Int caravanWinnings
Int caravanLosses
Int caravanWins
Int caravanLossCount
Int caravanBiggest

Event OnInit()
  Register()
EndEvent

Function Loaded()
  {A save was loaded: register again and start FNV's anti-cheat wait.}
  loadedAt = Utility.GetCurrentRealTime()
  Register()
  ShowHud(True)
EndFunction

Function ShowHud(Bool abShow)
  {Show or hide the game's HUD (HUDMenu's root clip) behind the casino menu, as FO4's own menus do; the menu flags stay as they are (changing them kept the menu from opening, spike 2a). See docs/fork/fo4_casino_plan.md#hud-hidden}
  If UI.IsMenuOpen("HUDMenu")
    UI.Set("HUDMenu", "root1.visible", abShow)
  EndIf
EndFunction

Function Register()
  {Register the menu with F4SE (each game load: registrations do not persist) and the menu's events, each once: earlier registrations are dropped first, as copies built up across save loads and each event arrived five times. See docs/fork/fo4_casino_plan.md#toolchain-found}
  If !UI.IsMenuRegistered(MenuName)
    UI:MenuData data = new UI:MenuData
    data.menuFlags = MenuFlags
    data.extendedFlags = ExtendedFlags
    UI.RegisterCustomMenu(MenuName, MenuName, "root1", data)
  EndIf
  UnregisterForMenuOpenCloseEvent(MenuName)
  String[] events = new String[9]
  events[0] = "F3NV_CasinoClose"
  events[1] = "F3NV_CasinoReady"
  events[2] = "F3NV_CasinoRound"
  events[3] = "F3NV_CasinoPing"
  events[4] = "F3NV_CasinoInput"
  events[5] = "F3NV_CasinoSpikeImage"
  events[6] = "F3NV_CasinoSelfTest"
  events[7] = "F3NV_CaravanDeck"
  events[8] = "F3NV_CaravanResult"
  Int i = 0
  While i < events.Length
    UnregisterForExternalEvent(events[i])
    i += 1
  EndWhile
  RegisterForMenuOpenCloseEvent(MenuName)
  RegisterForExternalEvent("F3NV_CasinoClose", "OnMenuClose")
  RegisterForExternalEvent("F3NV_CasinoReady", "OnMenuReady")
  RegisterForExternalEvent("F3NV_CasinoRound", "OnMenuRound")
  RegisterForExternalEvent("F3NV_CasinoPing", "OnMenuPing")
  RegisterForExternalEvent("F3NV_CasinoInput", "OnMenuInput")
  RegisterForExternalEvent("F3NV_CasinoSpikeImage", "OnMenuImage")
  RegisterForExternalEvent("F3NV_CasinoSelfTest", "OnMenuSelfTest")
  RegisterForExternalEvent("F3NV_CaravanDeck", "OnCaravanDeck")
  RegisterForExternalEvent("F3NV_CaravanResult", "OnCaravanResult")
EndFunction

; ---- Openers (the converted scripts' ShowBlackjackMenuParams, ShowRouletteMenuParams, ShowSlotMachineMenuParams, ShowCaravanMenu)

Function Open(Int aiGame, F3NV_CasinoData akCasino, Int aiMin, Int aiMax, Int aiMinWinnings)
  {Open game aiGame (1 blackjack, 2 roulette, 3 slots) at akCasino with bets aiMin to aiMax, after FNV's refusals.}
  If akCasino == None
    Return
  EndIf
  String refusal = Refusal(aiGame, akCasino, aiMin, aiMinWinnings)
  If refusal != ""
    Debug.MessageBox(refusal)
    Return
  EndIf
  spiking = False
  playing = akCasino
  playingGame = aiGame
  betLow = aiMin
  betHigh = aiMax
  Register()
  UI.OpenMenu(MenuName)
EndFunction

Function OpenSlots()
  {Hand the open menu the slot machine: the casino, the player's chips, bets, earnings, Luck, a seed, the reel stops, symbols and texts.}
  Actor player = Game.GetPlayer()
  Var[] args = new Var[10]
  args[0] = playing.CasinoName
  args[1] = player.GetItemCount(playing.Chip)
  args[2] = betLow
  args[3] = betHigh
  args[4] = playing.GetEarnings()
  args[5] = player.GetValue(Game.GetLuckAV()) as Int
  args[6] = Utility.RandomInt(1, 2147483647)
  args[7] = IntsAsVar(playing.ReelStops)
  args[8] = StringsAsVar(playing.Symbols)
  args[9] = StringsAsVar(SlotTexts)
  UI.Invoke(MenuName, "root1.OpenSlots", args)
EndFunction

Function OpenRoulette()
  {Hand the open menu the roulette table: the casino, the player's chips, bets (the max covers all bets on a spin), earnings, Luck, a seed and texts.}
  Actor player = Game.GetPlayer()
  Var[] args = new Var[8]
  args[0] = playing.CasinoName
  args[1] = player.GetItemCount(playing.Chip)
  args[2] = betLow
  args[3] = betHigh
  args[4] = playing.GetEarnings()
  args[5] = player.GetValue(Game.GetLuckAV()) as Int
  args[6] = Utility.RandomInt(1, 2147483647)
  args[7] = StringsAsVar(RouletteTexts)
  UI.Invoke(MenuName, "root1.OpenRoulette", args)
EndFunction

Function OpenBlackjack()
  {Hand the open menu the blackjack table: the casino, the player's chips, bets, earnings, Luck, a seed, the casino's decks, reshuffle share, natural payout, soft-17 rule, card backs and texts.}
  Actor player = Game.GetPlayer()
  Var[] args = new Var[13]
  args[0] = playing.CasinoName
  args[1] = player.GetItemCount(playing.Chip)
  args[2] = betLow
  args[3] = betHigh
  args[4] = playing.GetEarnings()
  args[5] = player.GetValue(Game.GetLuckAV()) as Int
  args[6] = Utility.RandomInt(1, 2147483647)
  args[7] = playing.Decks
  args[8] = playing.ReshuffleShare
  args[9] = playing.Payout
  args[10] = playing.DealerStaysOnSoft17
  args[11] = StringsAsVar(playing.CardBacks)
  args[12] = StringsAsVar(BlackjackTexts)
  UI.Invoke(MenuName, "root1.OpenBlackjack", args)
EndFunction

Var Function IntsAsVar(Int[] aiValues)
  {An Int array as one Var for UI.Invoke.}
  Var[] out = new Var[aiValues.Length]
  Int i = 0
  While i < aiValues.Length
    out[i] = aiValues[i]
    i += 1
  EndWhile
  Return Utility.VarArrayToVar(out)
EndFunction

Var Function StringsAsVar(String[] asValues)
  {A String array as one Var for UI.Invoke.}
  Var[] out = new Var[asValues.Length]
  Int i = 0
  While i < asValues.Length
    out[i] = asValues[i]
    i += 1
  EndWhile
  Return Utility.VarArrayToVar(out)
EndFunction

String Function Refusal(Int aiGame, F3NV_CasinoData akCasino, Int aiMin, Int aiMinWinnings)
  {FNV's refusals in its order: the anti-cheat wait after a load, the ban, too few chips, too little won; "" to play.}
  Float left = AntiCheatSeconds - (Utility.GetCurrentRealTime() - loadedAt)
  If left > 0.0 && aiGame >= 1 && aiGame <= AntiCheatTexts.Length
    Return AntiCheatTexts[aiGame - 1] + "\n" + TimeLeftText + Math.Ceiling(left) + "s"
  ElseIf akCasino.GetLevel() >= 4
    Return BannedText
  ElseIf Game.GetPlayer().GetItemCount(akCasino.Chip) < aiMin
    Return BrokeText
  ElseIf aiMinWinnings != 0 && akCasino.GetEarnings() < aiMinWinnings
    Return MinWinText
  EndIf
  Return ""
EndFunction

Function OpenCaravan(ObjectReference akOpponent, FormList akOpponentDeck, Int aiMode, Float afAnte)
  {Play Caravan against akOpponent's deck (mode 0-3 the AI, afAnte its ante share), after FNV's 30-card check.}
  If Deck.GetSize() + Owned.GetSize() < CaravanMinimum
    Debug.MessageBox(CardCountText)
    Return
  EndIf
  If !akOpponent || !akOpponentDeck
    Return
  EndIf
  spiking = False
  playing = None
  playingGame = CaravanGame
  opponent = akOpponent
  opponentDeck = akOpponentDeck
  caravanMode = aiMode
  anteShare = afAnte
  Register()
  UI.OpenMenu(MenuName)
EndFunction

Function OpenCaravanMenu()
  {Hand the open menu Caravan: the opponent's name, both sides' funds, the ante share, Barter, the AI mode, a seed, the card table, the player's owned and deck cards (bit chunks), the opponent's deck (card places), FNV's five results to date and the texts.}
  Actor player = Game.GetPlayer()
  Int chunks = (CaravanCards.GetSize() + CardChunk - 1) / CardChunk
  If chunks < 1
    chunks = 1
  EndIf
  Int[] results = new Int[5]
  results[0] = caravanWinnings
  results[1] = caravanLosses
  results[2] = caravanWins
  results[3] = caravanLossCount
  results[4] = caravanBiggest
  Var[] args = new Var[13]
  args[0] = opponent.GetDisplayName()
  args[1] = Funds(player)
  args[2] = Funds(opponent)
  args[3] = anteShare
  args[4] = 0
  If Barter
    args[4] = player.GetValue(Barter) as Int
  EndIf
  args[5] = caravanMode
  args[6] = Utility.RandomInt(1, 2147483647)
  args[7] = StringsAsVar(CardTable)
  args[8] = IntsAsVar(Masks(Owned, chunks))
  args[9] = IntsAsVar(Masks(Deck, chunks))
  args[10] = IntsAsVar(Places(opponentDeck))
  args[11] = IntsAsVar(results)
  args[12] = StringsAsVar(CaravanTexts)
  UI.Invoke(MenuName, "root1.OpenCaravan", args)
EndFunction

Int Function Funds(ObjectReference akWho)
  {FNV's Caravan funds: caps plus each Caravan money item's value times how many akWho holds.}
  Int total = akWho.GetItemCount(Game.GetCaps())
  Int i = 0
  While i < CaravanMoney.GetSize()
    Form money = CaravanMoney.GetAt(i)
    total += akWho.GetItemCount(money) * money.GetGoldValue()
    i += 1
  EndWhile
  Return total
EndFunction

Int Function Bit(Int aiPlace)
  {2 to the power aiPlace.}
  Int out = 1
  While aiPlace > 0
    out *= 2
    aiPlace -= 1
  EndWhile
  Return out
EndFunction

Int[] Function Masks(FormList akCards, Int aiChunks)
  {akCards as bits of CaravanCards places, CardChunk to an Int.}
  Int[] out = new Int[aiChunks]
  Int i = 0
  While i < akCards.GetSize()
    Int place = CaravanCards.Find(akCards.GetAt(i))
    If place >= 0 && place / CardChunk < aiChunks
      out[place / CardChunk] = out[place / CardChunk] + Bit(place % CardChunk)
    EndIf
    i += 1
  EndWhile
  Return out
EndFunction

Int[] Function Places(FormList akCards)
  {akCards' places in CaravanCards (-1 for a card not there), at most 128.}
  Int size = akCards.GetSize()
  If size > 128
    size = 128
  ElseIf size < 1
    size = 1
  EndIf
  Int[] out = new Int[size]
  Int i = 0
  While i < size
    out[i] = CaravanCards.Find(akCards.GetAt(i))
    i += 1
  EndWhile
  Return out
EndFunction

Function OnCaravanDeck(Int aiChunk, Int aiBits)
  {The menu's deck for one chunk of CaravanCards (bit k the card at aiChunk * CardChunk + k): an owned card in it moves to Deck, a deck card out of it back to Owned, as FNV rewrites its two lists when play starts.}
  Int bits = aiBits
  Int k = 0
  While k < CardChunk
    Int place = aiChunk * CardChunk + k
    If place < CaravanCards.GetSize()
      Form card = CaravanCards.GetAt(place)
      If bits % 2 == 1 && Owned.HasForm(card)
        Owned.RemoveAddedForm(card)
        Deck.AddForm(card)
      ElseIf bits % 2 == 0 && Deck.HasForm(card)
        Deck.RemoveAddedForm(card)
        Owned.AddForm(card)
      EndIf
    EndIf
    bits = bits / 2
    k += 1
  EndWhile
EndFunction

Function OnCaravanResult(Bool abWon, Int aiStake)
  {A finished Caravan game: the loser pays the stake (TransferBarterItems 0x0074cc70) and FNV's results to date count it.}
  If !opponent
    Return
  EndIf
  Actor player = Game.GetPlayer()
  If abWon
    Pay(opponent, player, aiStake)
    caravanWinnings += aiStake
    caravanWins += 1
    If aiStake > caravanBiggest
      caravanBiggest = aiStake
    EndIf
  Else
    Pay(player, opponent, aiStake)
    caravanLosses += aiStake
    caravanLossCount += 1
  EndIf
EndFunction

Function Pay(ObjectReference akFrom, ObjectReference akTo, Int aiStake)
  {akFrom pays akTo aiStake as FNV does: each Caravan money item in turn, as many as fit in what is left, then caps for the rest (akTo gets all of it).}
  Int left = aiStake
  Int i = 0
  While i < CaravanMoney.GetSize() && left > 0
    Form money = CaravanMoney.GetAt(i)
    Int value = money.GetGoldValue()
    Int count = akFrom.GetItemCount(money)
    Int moved = count
    If value * count > left
      moved = left / value
    EndIf
    If moved > 0
      akFrom.RemoveItem(money, moved, True, akTo)
      left -= moved * value
    EndIf
    i += 1
  EndWhile
  If left > 0
    Form caps = Game.GetCaps()
    Int held = akFrom.GetItemCount(caps)
    If held > left
      held = left
    EndIf
    If held > 0
      akFrom.RemoveItem(caps, held, True)
    EndIf
    akTo.AddItem(caps, left, True)
  EndIf
EndFunction

; ---- The bank

Function Settle(F3NV_CasinoData akCasino, Int aiNet)
  {A finished round at akCasino: aiNet chips to or from the player, then the earnings; a new level closes the menu.}
  Actor player = Game.GetPlayer()
  If aiNet > 0
    player.AddItem(akCasino.Chip, aiNet, True)
  ElseIf aiNet < 0
    player.RemoveItem(akCasino.Chip, -aiNet, True)
  EndIf
  If akCasino.AddResult(aiNet)
    UI.CloseMenu(MenuName)
  EndIf
EndFunction

Function OnMenuRound(Int aiNet)
  {The menu's report of a finished round at the open casino (an AS3 int arrives as an Int). At roulette and blackjack, chips under the min bet close the table with FNV's broke text (RouletteMenu 0x007bd2a0, BlackjackMenu 0x00734db0).}
  F3NV_CasinoData casino = playing
  If !casino
    Return
  EndIf
  Settle(casino, aiNet)
  If playingGame != Slots && Game.GetPlayer().GetItemCount(casino.Chip) < betLow
    Debug.Notification(BrokeText)
    UI.CloseMenu(MenuName)
  EndIf
EndFunction

; ---- Caravan cards (FNV's AddCardToPlayer)

Bool Function AddCard(ObjectReference akCard)
  {Add akCard's card to the player's owned cards unless the same card is owned or in the deck already, as FNV; whether it was added.}
  Form card = None
  If akCard
    card = akCard.GetBaseObject()
  EndIf
  If card == None || Owned.HasForm(card) || Deck.HasForm(card)
    Return False
  EndIf
  Owned.AddForm(card)
  Return True
EndFunction

; ---- The menu

Function Spike(String asTitle = "F3NV casino spike")
  {Phase 0: open the test screen showing asTitle and SpikeImage.}
  Register()
  spikeTitle = asTitle
  spiking = True
  UI.OpenMenu(MenuName)
EndFunction

Function SelfTest(Int aiLuck = 5)
  {Replay the slot rules for seeds 1-3, 20 spins each, at aiLuck, then the roulette draws and spot table, and log them ("F3NV_Casino: selftest"), to compare with tests/casino/model.py's slot_trace and roulette.py's roulette_trace.}
  Register()
  selfTestLuck = aiLuck
  spiking = False
  playing = None
  UI.OpenMenu(MenuName)
EndFunction

Function RunSelfTest()
  {Hand the open menu the self-test's seeds, spins and Luck.}
  Var[] seeds = new Var[3]
  seeds[0] = 1
  seeds[1] = 2
  seeds[2] = 3
  Var[] args = new Var[3]
  args[0] = Utility.VarArrayToVar(seeds)
  args[1] = 20
  args[2] = selfTestLuck
  selfTestLuck = 0
  UI.Invoke(MenuName, "root1.SelfTest", args)
EndFunction

Function OnMenuSelfTest(String asTrace)
  Debug.Trace("F3NV_Casino: selftest " + asTrace)
EndFunction

Event OnMenuOpenCloseEvent(String asMenuName, Bool abOpening)
  If asMenuName != MenuName
    Return
  EndIf
  Debug.Trace("F3NV_Casino: menu " + abOpening)
  ShowHud(!abOpening)
  If abOpening && selfTestLuck > 0
    RunSelfTest()
  ElseIf abOpening && spiking
    Var[] paths = new Var[1]
    paths[0] = SpikeImage
    Var[] args = new Var[2]
    args[0] = spikeTitle
    args[1] = Utility.VarArrayToVar(paths)
    UI.Invoke(MenuName, "root1.Spike", args)
  ElseIf abOpening && playing && playingGame == Slots
    OpenSlots()
  ElseIf abOpening && playing && playingGame == Roulette
    OpenRoulette()
  ElseIf abOpening && playing && playingGame == Blackjack
    OpenBlackjack()
  ElseIf abOpening && opponent && playingGame == CaravanGame
    OpenCaravanMenu()
  ElseIf !abOpening
    spiking = False
    playing = None
    opponent = None
    opponentDeck = None
  EndIf
EndEvent

Function OnMenuReady()
  Debug.Trace("F3NV_Casino: menu ready")
EndFunction

Function OnMenuClose()
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuPing(Int aiCount)
  Debug.Notification("Casino menu ping " + aiCount)
EndFunction

Function OnMenuInput(String asWhat)
  Debug.Trace("F3NV_Casino: input " + asWhat)
EndFunction

Function OnMenuImage(String asResult)
  Debug.Trace("F3NV_Casino: image " + asResult)
EndFunction
