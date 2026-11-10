ScriptName F3NV_Hardcore extends Quest
{FNV's Hardcore mode on Fallout 4, in place of Survival's needs, on a start-game quest of the game plugin. Needs (Dehydration, Hunger, Sleep Deprivation, FNV's 0 to 1000) rise at FNV's rates per game hour while it is on, sleep lowers Sleep Deprivation and does not mend limbs, a stage change shows FNV's message and its effects (Stages, conditioned on the need's range), the last stage kills. F3NV.dll (F3NV_HardcoreNative.Track) weighs ammo and shows the needs on the HUD while the Hardcore global is on. Converted scripts call SetHardcore, IsOn and IsAlways; need effects call Need. A character who picks Survival after FNV's choice gets Hardcore instead of Survival's needs. See docs/fork/fo4_hardcore.md#built}

GlobalVariable Property Hardcore Auto Const Mandatory
{1 while Hardcore mode is on; record conditions read it for FNV's IsHardcore.}
GlobalVariable Property Always Auto Const Mandatory
{1 while Hardcore mode has been on since the start (FNV's IsAlwaysHardcore, the ending's reward).}
ActorValue[] Property Needs Auto Const
{Dehydration, Hunger, Sleep Deprivation.}
Float[] Property PerHour Auto Const
{Points each need gains per game hour (FNV's rate settings and TimeScale).}
Float[] Property Thresholds Auto Const
{Each need's five stage thresholds, need * 5 + stage (FNV's DEHY, HUNG and SLPD records); the fifth kills.}
Potion[] Property Stages Auto Const
{Each need's first four stages, need * 4 + stage - 1: FNV's stage effects, each conditioned on the need's range.}
Float Property SleepRestore = 60.0 Auto Const
{Sleep Deprivation lost per hour slept (fHCSleepRestorationMod).}
Message[] Property Raised Auto Const
Message[] Property Lowered Auto Const
Message Property MenuOn Auto Const
{The Hardcore item's box while on: the three needs, then Keep it on / Turn it off.}
Message Property MenuOff Auto Const
{The Hardcore item's box while off: Turn it on / Keep it off.}
Message Property SurvivalOff Auto Const
Potion Property Hotkey Auto Const
{The Hardcore item, given with FNV's choice.}
ActorValue[] Property Limbs Auto Const
Hardcore:HC_ManagerScript Property HC_Manager Auto Const
GlobalVariable[] Property SurvivalRules Auto Const
{Survival's sustenance, sleep, disease and adrenaline rules, turned off for a character on Hardcore.}

Int Property TickTimer = 1 AutoReadOnly
Float Property TickHours = 0.1 AutoReadOnly
Int Property SleepNeed = 2 AutoReadOnly
Int Property SurvivalDifficulty = 6 AutoReadOnly

Bool Offered
Bool EverOff
Bool Sleeping
Float LastTime
Int[] Stage
Float[] LimbCache

Event OnQuestInit()
  F3NV_HardcoreNative.Track(Hardcore, Needs)
  Stage = new Int[3]
  LimbCache = new Float[6]
  Actor player = Game.GetPlayer()
  RegisterForRemoteEvent(player, "OnPlayerLoadGame")
  RegisterForRemoteEvent(player, "OnDifficultyChanged")
  RegisterForPlayerSleep()
EndEvent

Event Actor.OnPlayerLoadGame(Actor akSender)
  F3NV_HardcoreNative.Track(Hardcore, Needs)
  If Offered && Game.GetDifficulty() == SurvivalDifficulty
    TurnSurvivalOff()
  EndIf
EndEvent

Event Actor.OnDifficultyChanged(Actor akSender, Int aOldDifficulty, Int aNewDifficulty)
  If Offered && aNewDifficulty == SurvivalDifficulty
    Utility.Wait(1.0)
    TurnSurvivalOff()
    SurvivalOff.Show()
    SetHardcore(True)
  EndIf
EndEvent

Bool Function IsOn()
  Return Hardcore.GetValue() != 0.0
EndFunction

Bool Function IsAlways()
  Return Always.GetValue() != 0.0
EndFunction

Function SetHardcore(Bool on)
  {FNV's SetHardcore: the intro's choice, the Hardcore item, or Survival picked. Turning it off resets the needs and loses the ending's reward for good; the first call gives the Hardcore item.}
  Actor player = Game.GetPlayer()
  If !Offered
    Offered = True
    If player.GetItemCount(Hotkey) == 0
      player.AddItem(Hotkey, 1, True)
    EndIf
  EndIf
  If !on
    EverOff = True
    Always.SetValue(0.0)
  EndIf
  If on == IsOn()
    Return
  EndIf
  If on
    Hardcore.SetValue(1.0)
    If !EverOff
      Always.SetValue(1.0)
    EndIf
    StartNeeds()
  Else
    Hardcore.SetValue(0.0)
    StopNeeds()
  EndIf
EndFunction

Function Need(Int need, Float amount)
  {An FNV need effect: change need `need` by `amount` while Hardcore mode is on.}
  If IsOn()
    ModNeed(need, amount)
  EndIf
EndFunction

Function Menu()
  {The Hardcore item: the needs and a switch.}
  Actor player = Game.GetPlayer()
  If IsOn()
    Advance()
    If MenuOn.Show(player.GetValue(Needs[0]), player.GetValue(Needs[1]), player.GetValue(Needs[2])) == 1
      SetHardcore(False)
    EndIf
  ElseIf MenuOff.Show() == 0
    SetHardcore(True)
  EndIf
EndFunction

Function StartNeeds()
  Actor player = Game.GetPlayer()
  LastTime = Utility.GetCurrentGameTime()
  Int i = 0
  While i < Needs.Length
    Stage[i] = StageOf(i, player.GetValue(Needs[i]))
    ApplyStage(i)
    i += 1
  EndWhile
  StartTimerGameTime(TickHours, TickTimer)
EndFunction

Function StopNeeds()
  {Needs back to 0 (the stage effects stop by their conditions).}
  Actor player = Game.GetPlayer()
  CancelTimerGameTime(TickTimer)
  Int i = 0
  While i < Needs.Length
    player.SetValue(Needs[i], 0.0)
    Stage[i] = 0
    i += 1
  EndWhile
EndFunction

Event OnTimerGameTime(Int aiTimerID)
  If IsOn()
    Advance()
    StartTimerGameTime(TickHours, TickTimer)
  EndIf
EndEvent

Function Advance()
  {Each need's gain since the last call; Sleep Deprivation holds while sleeping.}
  Float now = Utility.GetCurrentGameTime()
  Float hours = (now - LastTime) * 24.0
  LastTime = now
  If hours <= 0.0
    Return
  EndIf
  Int i = 0
  While i < Needs.Length
    If i != SleepNeed || !Sleeping
      ModNeed(i, PerHour[i] * hours)
    EndIf
    i += 1
  EndWhile
EndFunction

Function ModNeed(Int need, Float amount)
  {Change need `need` by `amount`, kept from 0 to its last threshold; a new stage shows FNV's message and its effects.}
  Actor player = Game.GetPlayer()
  Float value = player.GetValue(Needs[need]) + amount
  Float top = Thresholds[need * 5 + 4]
  If value < 0.0
    value = 0.0
  ElseIf value > top
    value = top
  EndIf
  player.SetValue(Needs[need], value)
  Int now = StageOf(need, value)
  If now == Stage[need]
    Return
  ElseIf now > Stage[need]
    Raised[need].Show()
  Else
    Lowered[need].Show()
  EndIf
  Stage[need] = now
  ApplyStage(need)
EndFunction

Int Function StageOf(Int need, Float value)
  Int reached = 0
  While reached < 5 && value >= Thresholds[need * 5 + reached]
    reached += 1
  EndWhile
  Return reached
EndFunction

Function ApplyStage(Int need)
  {The stage's effects (its potion, conditioned on the need's range, as Survival's stages); the last stage kills.}
  Int reached = Stage[need]
  If reached >= 5
    Game.GetPlayer().Kill()
  ElseIf reached > 0
    Game.GetPlayer().EquipItem(Stages[need * 4 + reached - 1], False, True)
  EndIf
EndFunction

Event OnPlayerSleepStart(Float afSleepStartTime, Float afDesiredSleepEndTime, ObjectReference akBed)
  If !IsOn()
    Return
  EndIf
  Advance()
  Sleeping = True
  Actor player = Game.GetPlayer()
  Int i = 0
  While i < Limbs.Length
    LimbCache[i] = player.GetValue(Limbs[i])
    i += 1
  EndWhile
EndEvent

Event OnPlayerSleepStop(Bool abInterrupted, ObjectReference akBed)
  {The hours slept raise thirst and hunger, lower Sleep Deprivation by SleepRestore each; limbs stay as they were.}
  If !Sleeping
    Return
  EndIf
  Float slept = (Utility.GetCurrentGameTime() - LastTime) * 24.0
  Advance()
  Sleeping = False
  ModNeed(SleepNeed, -SleepRestore * slept)
  Actor player = Game.GetPlayer()
  Int i = 0
  While i < Limbs.Length
    Float healed = player.GetValue(Limbs[i]) - LimbCache[i]
    If healed > 0.0
      player.DamageValue(Limbs[i], healed)
    EndIf
    i += 1
  EndWhile
EndEvent

Function TurnSurvivalOff()
  {Survival's own shutdown, then its need, disease and adrenaline rules off; its engine rules (saves, damage) stay.}
  HC_Manager.ShutdownHardcore()
  Int i = 0
  While i < SurvivalRules.Length
    SurvivalRules[i].SetValue(0.0)
    i += 1
  EndWhile
EndFunction
