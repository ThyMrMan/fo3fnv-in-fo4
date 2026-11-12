ScriptName F3NV_State extends Quest
{Source-game state Fallout 4 does not keep, written by one script and read by others: which actors ignore crime (IgnoreCrime) with the crime faction each had, and whether the source game's character generation is on (SetInCharGen). The helper plugin's start-game quest; TES4Polyfill.IgnoreCrime, GetIgnoreCrime, SetInCharGen and GetInCharGen use it. The oldest of 128 ignoring actors gives way. See docs/fork/fo4_plan_script_functions.md#ignore-crime}

Bool Property InCharGen Auto

Actor[] Ignoring
Faction[] CrimeFactions

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
