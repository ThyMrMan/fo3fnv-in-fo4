ScriptName F3NV_ScriptPackages extends Quest Hidden
{FO3/FNV script packages (AddScriptPackage, RemoveScriptPackage) on Fallout 4. Alias i of this quest is a collection alias whose package list runs Packages[i], ahead of its members' own packages. An actor stands in at most one, as FO3/FNV keep one script package per actor: adding another replaces it.}

Package[] Property Packages Auto Const
Int Property Holds Auto Const
{How many aliases follow the package aliases, each holding one actor at its placed spot until it gets a script package.}

Actor[] Held
Int[] HeldAlias

Function Add(Actor akActor, Package akPackage)
  {FNV AddScriptPackage: `akActor` runs `akPackage` (a package no alias runs leaves it to its own packages). Adding the package an actor already runs only re-evaluates it.}
  If akActor == None
    Return
  EndIf
  Unhold(akActor)
  Int i = Packages.Find(akPackage)
  If TES4Polyfill.Tracing()
    TES4Polyfill.TraceWrite("scriptpackage", TES4Polyfill.TraceName(akActor) + "|" + akPackage + "|alias " + i)
  EndIf
  RefCollectionAlias target = None
  If i >= 0
    target = GetAlias(i) as RefCollectionAlias
  EndIf
  If !target || target.Find(akActor) < 0
    Release(akActor)
    If target
      target.AddRef(akActor)
      Hold(akActor, i)
    EndIf
  EndIf
  akActor.EvaluatePackage()
  If TES4Polyfill.Tracing() && i >= 0
    Var[] args = new Var[2]
    args[0] = akActor
    args[1] = i
    CallFunctionNoWait("TraceLater", args)
  EndIf
EndFunction

Function TraceLater(Actor akActor, Int aiAlias)
  {Add's second trace sample, 1 s later, off the caller's stack: the package the actor runs and the alias's count.}
  Utility.Wait(1.0)
  TES4Polyfill.TraceWrite("scriptpackage", TES4Polyfill.TraceName(akActor) + "|now " + akActor.GetCurrentPackage() + "|running " + IsRunning() + "|alias holds " + (GetAlias(aiAlias) as RefCollectionAlias).GetCount())
EndFunction

Function Remove(Actor akActor)
  {FNV RemoveScriptPackage: `akActor` back on its own packages.}
  If akActor == None
    Return
  EndIf
  Unhold(akActor)
  Release(akActor)
  akActor.EvaluatePackage()
EndFunction

Function Unhold(Actor akActor)
  {Clear the hold alias keeping `akActor` at its placed spot, if one does: its script package takes over.}
  Int i = Packages.Length
  While i < Packages.Length + Holds
    ReferenceAlias hold = GetAlias(i) as ReferenceAlias
    If hold && hold.GetReference() == akActor
      hold.Clear()
    EndIf
    i += 1
  EndWhile
EndFunction

Function Hold(Actor akActor, Int aiAlias)
  {Record that `akActor` stands in alias `aiAlias` (a full list, 128 actors, records nothing: Release then searches every alias).}
  If !Held
    Held = new Actor[0]
    HeldAlias = new Int[0]
  EndIf
  If Held.Length < 128
    Held.Add(akActor)
    HeldAlias.Add(aiAlias)
  EndIf
EndFunction

Function Release(Actor akActor)
  {Take `akActor` out of the alias Hold recorded; an actor not recorded (an older save, a full list) out of every alias.}
  Int at = -1
  If Held
    at = Held.Find(akActor)
  EndIf
  If at >= 0
    (GetAlias(HeldAlias[at]) as RefCollectionAlias).RemoveRef(akActor)
    Held.Remove(at)
    HeldAlias.Remove(at)
    Return
  EndIf
  Int i = 0
  While i < Packages.Length
    (GetAlias(i) as RefCollectionAlias).RemoveRef(akActor)
    i += 1
  EndWhile
EndFunction
