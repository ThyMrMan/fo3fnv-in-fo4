ScriptName F3NV_ChallengeSource extends Quest Const
{One plugin's FNV challenges, on a start-game quest of that plugin (the game's own challenges quest holds the game's). Each counts its event into its progress actor value on the player (Rows), shows it through its state global (States) and casts its reward on completion; the states are F3NV_Challenges'. On start it adds itself to Sources, the game's registry, whose F3NV_Challenges hands every event to each plugin's challenges. See docs/fork/fo4_pipeline.md#challenges}

ActorValue[] Property Rows Auto Const
GlobalVariable[] Property States Auto Const
String[] Property Names Auto Const
Int[] Property Events Auto Const
Int[] Property Thresholds Auto Const
Int[] Property Intervals Auto Const
Int[] Property Recurring Auto Const
Int[] Property Groups Auto Const
{The stat group a stat or marker challenge counts (-1: none), numbered as F3NV_Challenges' StatGroups.}
FormList[] Property Weapons Auto Const
{The weapons a kill or critical must be made with (None: any).}
FormList[] Property Victims Auto Const
FormList[] Property Items Auto Const
ObjectReference[] Property Markers Auto Const
Spell[] Property Rewards Auto Const
FormList Property Sources Auto Const
{The game's registry of every plugin's challenges.}
Quest Property Hub Auto Const
{The game's challenges quest (F3NV_Challenges).}
FormList Property TabRows Auto Const
FormList Property TabShown Auto Const
{The game's CHALLENGES tab lists (rows and their state globals, parallel); a plugin's challenges are added to them.}

Event OnQuestInit()
  If Sources.Find(Self) < 0
    Sources.AddForm(Self)
  EndIf
  Int i = 0
  While i < Rows.Length
    If !TabRows.HasForm(Rows[i])
      TabRows.AddForm(Rows[i])
      TabShown.AddForm(States[i])
    EndIf
    i += 1
  EndWhile
EndEvent

Function Note(Int aiEvent, Int aiGroup, Int aiAmount, Actor akVictim, Form akItem, Weapon akHeld)
  {Add aiAmount to every challenge here counting aiEvent (a stat event: of group aiGroup) whose filters match akHeld, akVictim and akItem.}
  F3NV_Challenges counter = Hub as F3NV_Challenges
  Int i = Events.Find(aiEvent)
  While i >= 0
    If (aiEvent != counter.StatEvent || Groups[i] == aiGroup) && Matches(i, akHeld, akVictim, akItem)
      Add(i, aiAmount)
    EndIf
    i = FindAfter(aiEvent, i)
  EndWhile
EndFunction

Int Function FindAfter(Int aiEvent, Int i)
  {The next index after i whose event is aiEvent, else -1 (Find logs an error when its start is past the end).}
  If i + 1 >= Events.Length
    Return -1
  EndIf
  Return Events.Find(aiEvent, i + 1)
EndFunction

Bool Function Matches(Int i, Weapon akHeld, Actor akVictim, Form akItem)
  {Whether challenge i's weapon, victim and item lists (None: any) hold akHeld, akVictim's base and akItem.}
  Return (!Weapons[i] || Weapons[i].HasForm(akHeld)) && Fits(i, akVictim, akItem)
EndFunction

Bool Function Fits(Int i, Actor akVictim, Form akItem)
  {Whether challenge i's victim and item lists (None: any) hold akVictim's base and akItem.}
  If Items[i] && !Items[i].HasForm(akItem)
    Return False
  EndIf
  Return !Victims[i] || (akVictim && (Victims[i].HasForm(akVictim.GetLeveledActorBase()) || Victims[i].HasForm(akVictim.GetActorBase())))
EndFunction

Function CheckMarkers()
  {Count each discovery challenge here whose map marker the player can now travel to.}
  Actor player = Game.GetPlayer()
  Int i = Events.Find((Hub as F3NV_Challenges).MarkerEvent)
  While i >= 0
    If Markers[i] && Markers[i].CanFastTravelToMarker() && player.GetValue(Rows[i]) == 0
      Add(i, 1)
    EndIf
    i = FindAfter((Hub as F3NV_Challenges).MarkerEvent, i)
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
    Debug.Notification((Hub as F3NV_Challenges).ProgressText + ": " + Names[i] + " " + shown + "/" + goal)
  EndIf
EndFunction

Function Complete(Int i)
  {Mark challenge i completed (state 1 or 2 becomes 3 or 4), report it, cast its reward on the player and count it for every plugin's challenges counting completions.}
  F3NV_Challenges counter = Hub as F3NV_Challenges
  Float level = States[i].GetValue()
  If level == 1 || level == 2
    States[i].SetValue(level + 2)
  EndIf
  Debug.Notification(counter.CompletedText + ": " + Names[i])
  If Rewards[i]
    Rewards[i].Cast(Game.GetPlayer(), Game.GetPlayer())
  EndIf
  counter.Note(counter.CompletedEvent, -1, 1, None, None)
EndFunction
