ScriptName F3NV_State extends Quest
{Source-game state Fallout 4 does not keep, written by one script and read by others: which actors ignore crime (IgnoreCrime) with the crime faction each had, whether the source game's character generation is on (SetInCharGen), and whether a script is still asking for lines (SayAsked, SaysPending). The helper plugin's start-game quest; TES4Polyfill.IgnoreCrime, GetIgnoreCrime, SetInCharGen and GetInCharGen use it. The oldest of 128 ignoring actors gives way. See docs/fork/fo4_plan_script_functions.md#ignore-crime}

Bool Property InCharGen Auto
Bool Property SexChosen Auto
{A script set the player's sex (TES4Polyfill.SetSex) since the last race menu, which then skips its own sex box.}

Actor[] Ignoring
Faction[] CrimeFactions
Int Asking
Float LastAsked

Function SayAsked(Int aiChange)
  {A TES4Polyfill.SayWhenFree call began (1) or returned (-1).}
  Asking += aiChange
  If aiChange > 0
    LastAsked = Utility.GetCurrentGameTime()
  EndIf
EndFunction

Bool Function SaysPending(Float afWithinDays)
  {Whether a SayWhenFree call is still running, the last one asked within afWithinDays (a count a save cut short ages out).}
  Return Asking > 0 && Utility.GetCurrentGameTime() - LastAsked < afWithinDays
EndFunction

Function IgnoreCrime(Actor akActor, Bool abIgnore)
  {akActor stops reporting the player's crimes (its crime faction cleared and remembered), or resumes (restored).}
  If !Ignoring
    Ignoring = new Actor[0]
    CrimeFactions = new Faction[0]
  EndIf
  Int i = Ignoring.Find(akActor)
  If abIgnore && i < 0
    If Ignoring.Length >= 128
      Ignoring.Remove(0)
      CrimeFactions.Remove(0)
    EndIf
    Ignoring.Add(akActor)
    CrimeFactions.Add(akActor.GetCrimeFaction())
    akActor.SetCrimeFaction(None)
  ElseIf !abIgnore && i >= 0
    akActor.SetCrimeFaction(CrimeFactions[i])
    Ignoring.Remove(i)
    CrimeFactions.Remove(i)
  EndIf
EndFunction

Bool Function IgnoresCrime(Actor akActor)
  {Whether akActor ignores crime (IgnoreCrime).}
  Return Ignoring && Ignoring.Find(akActor) >= 0
EndFunction
