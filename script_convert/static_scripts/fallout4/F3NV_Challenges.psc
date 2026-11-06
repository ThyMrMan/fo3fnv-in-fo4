ScriptName F3NV_Challenges extends Quest Hidden
{FNV's challenges: hears each event (its player alias's kills, uses and crippled limbs, Fallout 4's tracked stats, completions) and hands it to every plugin's challenges (F3NV_ChallengeSource, the game's on this quest), registered in Sources; each counts it into its progress actor value on the player, shows it (its state global) and casts its reward on completion. State: -2/-1 locked (hidden/shown once unlocked), 0 counting but hidden, 1 shown, 2 shown and no longer recurring, 3 and 4 as 1 and 2 once completed. See docs/fork/fo4_pipeline.md#challenges}

Int Property KillEvent = 0 AutoReadOnly
Int Property StatEvent = 1 AutoReadOnly
Int Property UseEvent = 2 AutoReadOnly
Int Property MarkerEvent = 3 AutoReadOnly
Int Property CrippledEvent = 4 AutoReadOnly
Int Property CompletedEvent = 5 AutoReadOnly

FormList Property Sources Auto Const
{Every plugin's challenges (F3NV_ChallengeSource quests), each added by its quest as it starts.}
String[] Property StatNames Auto Const
{The Fallout 4 tracked stats counted, each in group StatGroups[k] (one fixed numbering for every plugin).}
Int[] Property StatGroups Auto Const
Weapon Property Fists Auto Const
String Property CompletedText Auto Const
String Property ProgressText Auto Const

Int[] Seen

Event OnQuestInit()
  Ready()
EndEvent

Function Ready()
  {Have this quest's own challenges registered and every stat of StatNames tracked; a save from before either (the quest already running) catches up here.}
  F3NV_ChallengeSource own = (Self as Quest) as F3NV_ChallengeSource
  If own && Sources.Find(own) < 0
    Sources.AddForm(own)
  EndIf
  If Seen && Seen.Length == StatNames.Length
    Return
  EndIf
  Seen = new Int[StatNames.Length]
  Int k = 0
  While k < StatNames.Length
    Seen[k] = Game.QueryStat(StatNames[k])
    RegisterForTrackedStatsEvent(StatNames[k], Seen[k] + 1)
    k += 1
  EndWhile
EndFunction

Event OnTrackedStatsEvent(String asStat, Int aiStatValue)
  Ready()
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
  {Hand aiEvent (a stat event: of group aiGroup) to every plugin's challenges, with the player's weapon (fists when none), akVictim and akItem.}
  Ready()
  Weapon held = Game.GetPlayer().GetEquippedWeapon()
  If !held
    held = Fists
  EndIf
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ChallengeSource rows = Sources.GetAt(k) as F3NV_ChallengeSource
    If rows
      rows.Note(aiEvent, aiGroup, aiAmount, akVictim, akItem, held)
    EndIf
    k += 1
  EndWhile
EndFunction

Function CheckMarkers()
  {Count each plugin's discovery challenges whose map marker the player can now travel to.}
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ChallengeSource rows = Sources.GetAt(k) as F3NV_ChallengeSource
    If rows
      rows.CheckMarkers()
    EndIf
    k += 1
  EndWhile
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
