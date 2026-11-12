ScriptName F3NV_Casino extends Quest
{FNV's casino games and Caravan, the bank: opens the casino menu (F3NV_Casino.swf, registered with F4SE) for the converted openers after FNV's refusals, settles each round's chips into the casino's earnings and level, and keeps the player's Caravan cards (FNV's two lists: owned and deck). Spike() opens the phase 0 test screen (cqf FNV_Casino Spike). See docs/fork/fo4_casino_plan.md#design}

String Property MenuName = "F3NV_Casino" AutoReadOnly Hidden
{The menu's name, also its movie's name under Interface.}
FormList Property Owned Auto Const
{The player's Caravan cards out of the deck (card MISCs).}
FormList Property Deck Auto Const
{The player's Caravan deck.}
String Property BannedText Auto Const
String Property BrokeText Auto Const
String Property MinWinText Auto Const
String Property CardCountText Auto Const
String Property TimeLeftText Auto Const
String[] Property AntiCheatTexts Auto Const
{Per game (1 blackjack, 2 roulette, 3 slots): FNV's anti-cheat text.}
Float Property AntiCheatSeconds Auto Const
{FNV's iAntiCheatDuration: games refuse this long after a load.}
String Property NotBuiltText Auto Const
String[] Property SlotTexts Auto Const
{The slot screen's labels and results (FNV's settings), in SlotsScreen.as's order.}
String[] Property RouletteTexts Auto Const
{The roulette screen's labels, bet names and results (FNV's settings), in RouletteScreen.as's order.}
String[] Property SpikeImages Auto Const
{Spike: the images the test screen mounts (under Textures): a converted card face, then level-up images.}

Int Property MenuFlags = 0x800049D AutoReadOnly Hidden
{F4SE's default menu flags (0x801849D: pauses, cursor, menu context, modal, no pause menu) without Custom Rendering (0x8000) and Assign Cursor To Renderer (0x10000): with those the menu drew only around the cursor (played 2026-11-08).}
Int Property ExtendedFlags = 2 AutoReadOnly Hidden
{F4SE extended flags: drop the cursor when a gamepad is in use; no HUD color (it needs Custom Rendering).}
Int Property CaravanMinimum = 30 AutoReadOnly Hidden
{FNV's smallest deck: the menu won't open with fewer cards.}

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
  String[] events = new String[7]
  events[0] = "F3NV_CasinoClose"
  events[1] = "F3NV_CasinoReady"
  events[2] = "F3NV_CasinoRound"
  events[3] = "F3NV_CasinoPing"
  events[4] = "F3NV_CasinoInput"
  events[5] = "F3NV_CasinoSpikeImage"
  events[6] = "F3NV_CasinoSelfTest"
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
  If aiGame != Slots && aiGame != Roulette
    Debug.MessageBox(akCasino.CasinoName + "\n\n" + NotBuiltText)
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
  Debug.MessageBox(NotBuiltText)
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
  {The menu's report of a finished round at the open casino (an AS3 int arrives as an Int). At roulette, chips under the min bet close the table with FNV's broke text (RouletteMenu 0x007bd2a0).}
  F3NV_CasinoData casino = playing
  If !casino
    Return
  EndIf
  Settle(casino, aiNet)
  If playingGame == Roulette && Game.GetPlayer().GetItemCount(casino.Chip) < betLow
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
  {Phase 0: open the test screen showing asTitle and SpikeImages.}
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
    Var[] paths = new Var[SpikeImages.Length]
    Int i = 0
    While i < SpikeImages.Length
      paths[i] = SpikeImages[i]
      i += 1
    EndWhile
    Var[] args = new Var[2]
    args[0] = spikeTitle
    args[1] = Utility.VarArrayToVar(paths)
    UI.Invoke(MenuName, "root1.Spike", args)
  ElseIf abOpening && playing && playingGame == Slots
    OpenSlots()
  ElseIf abOpening && playing && playingGame == Roulette
    OpenRoulette()
  ElseIf !abOpening
    spiking = False
    playing = None
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
