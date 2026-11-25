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
String[] Property GameStats Auto Const
{FNV's misc stats Fallout 4 has none of (the casino's and Caravan's games), each in group GameGroups[k]: CountGame counts them.}
Int[] Property GameGroups Auto Const
Weapon Property Fists Auto Const
String Property CompletedText Auto Const
String Property ProgressText Auto Const

Float Property BlastSeconds = 3.0 AutoReadOnly
{How long after an explosion catches an actor a kill of it is credited to the explosion's weapons.}
Int Property BlastSlots = 16 AutoReadOnly

Int[] Seen
Actor[] BlastVictims
FormList[] BlastWeapons
Float[] BlastTimes
Int BlastNext

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
  {Hand aiEvent (a stat event: of group aiGroup) to every plugin's challenges, with the player's weapon, akVictim and akItem.}
  Hand(aiEvent, aiGroup, aiAmount, akVictim, akItem, Held())
EndFunction

Form Function Held()
  {The player's weapon, the fists when none.}
  Weapon held = Game.GetPlayer().GetEquippedWeapon()
  If !held
    Return Fists
  EndIf
  Return held
EndFunction

Function Killed(Actor akVictim)
  {The player killed akVictim: a kill with the weapons of an explosion that caught it (F3NV_ExplosiveHit, given a moment to arrive), else with the weapon held.}
  Form held = Held()
  FormList blast = BlastOf(akVictim)
  If !blast
    Utility.Wait(0.3)
    blast = BlastOf(akVictim)
  EndIf
  If blast
    held = blast
  EndIf
  Hand(KillEvent, -1, 1, akVictim, None, held)
EndFunction

Function Blasted(Actor akVictim, FormList akWeapons)
  {An explosion set off by akWeapons caught akVictim (F3NV_ExplosiveHit); kept BlastSeconds, the oldest of BlastSlots giving way.}
  If !BlastVictims
    BlastVictims = new Actor[16]
    BlastWeapons = new FormList[16]
    BlastTimes = new Float[16]
  EndIf
  Int i = BlastVictims.Find(akVictim)
  If i < 0
    i = BlastNext
    BlastNext = (BlastNext + 1) % BlastSlots
  EndIf
  BlastVictims[i] = akVictim
  BlastWeapons[i] = akWeapons
  BlastTimes[i] = Utility.GetCurrentRealTime()
EndFunction

FormList Function BlastOf(Actor akVictim)
  {The weapons of the explosion that caught akVictim within BlastSeconds, else None.}
  Int i = -1
  If BlastVictims && akVictim
    i = BlastVictims.Find(akVictim)
  EndIf
  If i < 0
    Return None
  EndIf
  Float age = Utility.GetCurrentRealTime() - BlastTimes[i]
  If age < 0.0 || age > BlastSeconds
    Return None
  EndIf
  Return BlastWeapons[i]
EndFunction

Function Hand(Int aiEvent, Int aiGroup, Int aiAmount, Actor akVictim, Form akItem, Form akHeld)
  {Hand aiEvent to every plugin's challenges with akHeld: a weapon, or an explosion's list of weapons.}
  Ready()
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ChallengeSource rows = Sources.GetAt(k) as F3NV_ChallengeSource
    If rows
      rows.Note(aiEvent, aiGroup, aiAmount, akVictim, akItem, akHeld)
    EndIf
    k += 1
  EndWhile
EndFunction

Function CountGame(String asStat)
  {One game of FNV misc stat asStat (one of GameStats) finished, as the casino menu reports it: count it as that stat's event.}
  Int k = GameStats.Find(asStat)
  If k >= 0
    Note(StatEvent, GameGroups[k], 1, None, None)
  EndIf
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
