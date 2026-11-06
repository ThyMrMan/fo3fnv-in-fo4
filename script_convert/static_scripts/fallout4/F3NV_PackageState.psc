ScriptName F3NV_PackageState extends Quest
{Each actor's last ended package, for FO3/FNV GetCurrentAIProcedure's Done (17): a package whose end fragment ran stays the actor's current package while it is done, and is no longer current once another starts. The helper plugin's start-game quest; TES4Polyfill.PackageEnded and AIProcedure use it. The oldest of 128 actors gives way. See docs/fork/fo4_pipeline.md#ai-procedure}

Actor[] Actors
Package[] Packages
Int NextSlot

Function Ended(Actor akActor, Package akPackage)
  {akActor's package akPackage ended (its end fragment ran).}
  If !Actors
    Actors = new Actor[0]
    Packages = new Package[0]
  EndIf
  Int i = Actors.Find(akActor)
  If i < 0 && Actors.Length < 128
    Actors.Add(akActor)
    Packages.Add(akPackage)
    Return
  EndIf
  If i < 0
    i = NextSlot
    NextSlot = (NextSlot + 1) % 128
    Actors[i] = akActor
  EndIf
  Packages[i] = akPackage
EndFunction

Bool Function Done(Actor akActor)
  {Whether akActor's current package is the one whose end fragment last ran for it.}
  Int i = -1
  If Actors
    i = Actors.Find(akActor)
  EndIf
  Return i >= 0 && Packages[i] && Packages[i] == akActor.GetCurrentPackage()
EndFunction
