ScriptName F3NV_Challenges extends Quest Hidden
{FNV's challenges: counts each one's event into its progress actor value on the player, shows it (its state global) and casts its reward on completion. State: -2/-1 locked (hidden/shown once unlocked), 0 counting but hidden, 1 shown, 2 shown and no longer recurring, 3 and 4 as 1 and 2 once completed. See docs/fork/fo4_pipeline.md#challenges}

Int Property KillEvent = 0 AutoReadOnly
Int Property StatEvent = 1 AutoReadOnly
Int Property UseEvent = 2 AutoReadOnly
Int Property MarkerEvent = 3 AutoReadOnly
Int Property CrippledEvent = 4 AutoReadOnly
Int Property CompletedEvent = 5 AutoReadOnly

ActorValue[] Property Rows Auto Const
GlobalVariable[] Property States Auto Const
String[] Property Names Auto Const
Int[] Property Events Auto Const
Int[] Property Thresholds Auto Const
Int[] Property Intervals Auto Const
Int[] Property Recurring Auto Const
Int[] Property Groups Auto Const
{The stat group a stat or marker challenge counts (-1: none).}
FormList[] Property Weapons Auto Const
{The weapons a kill or critical must be made with (None: any).}
FormList[] Property Victims Auto Const
FormList[] Property Items Auto Const
ObjectReference[] Property Markers Auto Const
Spell[] Property Rewards Auto Const
String[] Property StatNames Auto Const
{The Fallout 4 tracked stats counted, each in group StatGroups[k].}
Int[] Property StatGroups Auto Const
Weapon Property Fists Auto Const
String Property CompletedText Auto Const
String Property ProgressText Auto Const

Int[] Seen

Event OnQuestInit()
  Seen = new Int[StatNames.Length]
  Int k = 0
  While k < StatNames.Length
    Seen[k] = Game.QueryStat(StatNames[k])
    RegisterForTrackedStatsEvent(StatNames[k], Seen[k] + 1)
    k += 1
  EndWhile
EndEvent

Event OnTrackedStatsEvent(String asStat, Int aiStatValue)
  Int k = StatNames.Find(asStat)
  If k < 0
    Return
  EndIf
  Int delta = aiStatValue - Seen[k]
  Seen[k] = aiStatValue
  RegisterForTrackedStatsEvent(asStat, aiStatValue + 1)
  If delta > 0
    Note(StatEvent, StatGroups[k], delta, None, None)
  EndIf
  If asStat == "Locations Discovered"
    CheckMarkers()
  EndIf
EndEvent

Function Note(Int aiEvent, Int aiGroup, Int aiAmount, Actor akVictim, Form akItem)
  {Add aiAmount to every challenge counting aiEvent (a stat event: of group aiGroup) whose filters match the player's weapon, akVictim and akItem.}
  Weapon held = Game.GetPlayer().GetEquippedWeapon()
  If !held
    held = Fists
  EndIf
  Int i = Events.Find(aiEvent)
  While i >= 0
    If (aiEvent != StatEvent || Groups[i] == aiGroup) && Matches(i, held, akVictim, akItem)
      Add(i, aiAmount)
    EndIf
    i = Events.Find(aiEvent, i + 1)
  EndWhile
EndFunction

Bool Function Matches(Int i, Weapon akHeld, Actor akVictim, Form akItem)
  {Whether challenge i's weapon, victim and item lists (None: any) hold akHeld, akVictim's base and akItem.}
  If Weapons[i] && !Weapons[i].HasForm(akHeld)
    Return False
  EndIf
  If Items[i] && !Items[i].HasForm(akItem)
    Return False
  EndIf
  Return !Victims[i] || (akVictim && (Victims[i].HasForm(akVictim.GetLeveledActorBase()) || Victims[i].HasForm(akVictim.GetActorBase())))
EndFunction

Function CheckMarkers()
  {Count each discovery challenge whose map marker the player can now travel to.}
  Actor player = Game.GetPlayer()
  Int i = Events.Find(MarkerEvent)
  While i >= 0
    If Markers[i] && Markers[i].CanFastTravelToMarker() && player.GetValue(Rows[i]) == 0
      Add(i, 1)
    EndIf
    i = Events.Find(MarkerEvent, i + 1)
  EndWhile
EndFunction

Function Add(Int i, Int aiAmount)
  {Add aiAmount to challenge i's progress unless it is locked or done; show it, report progress each interval and complete it at each threshold (once unless recurring).}
  Float level = States[i].GetValue()
  Actor player = Game.GetPlayer()
  Int before = player.GetValue(Rows[i]) as Int
  Int goal = Thresholds[i]
  Bool repeats = Recurring[i] && level != 2 && level != 4
  If level < 0 || (!repeats && before >= goal)
    Return
  EndIf
  Int after = before + aiAmount
  If !repeats && after > goal
    after = goal
  EndIf
  player.SetValue(Rows[i], after as Float)
  If level == 0
    States[i].SetValue(1)
  EndIf
  Int done = 0
  If goal > 0
    done = after / goal - before / goal
  EndIf
  If done > 0
    While done > 0
      Complete(i)
      done -= 1
    EndWhile
  ElseIf Intervals[i] > 0 && after / Intervals[i] > before / Intervals[i]
    Int shown = after
    If repeats && goal > 0
      shown = after % goal
    EndIf
    Debug.Notification(ProgressText + ": " + Names[i] + " " + shown + "/" + goal)
  EndIf
EndFunction

Function Complete(Int i)
  {Mark challenge i completed (state 1 or 2 becomes 3 or 4), report it, cast its reward on the player and count it for the challenges counting completions.}
  Float level = States[i].GetValue()
  If level == 1 || level == 2
    States[i].SetValue(level + 2)
  EndIf
  Debug.Notification(CompletedText + ": " + Names[i])
  If Rewards[i]
    Rewards[i].Cast(Game.GetPlayer(), Game.GetPlayer())
  EndIf
  Note(CompletedEvent, -1, 1, None, None)
EndFunction

Function Unlock(GlobalVariable akState) Global
  {UnlockChallenge: a locked challenge (state -2 or -1) starts counting, hidden (0) or shown (1).}
  If akState && akState.GetValue() < 0
    akState.SetValue(akState.GetValue() + 2)
  EndIf
EndFunction

Function StopRecurring(GlobalVariable akState) Global
  {RemoveRecurringFromChallenge: an unlocked challenge completes no more once at its threshold (state 2, or 4 once completed).}
  If akState && akState.GetValue() >= 0 && akState.GetValue() < 2
    akState.SetValue(2)
  ElseIf akState && akState.GetValue() == 3
    akState.SetValue(4)
  EndIf
EndFunction

Bool Function Completed(GlobalVariable akState) Global
  {GetChallengeCompleted: whether the challenge has completed at least once (state 3 or 4).}
  Return akState && akState.GetValue() >= 3
EndFunction
