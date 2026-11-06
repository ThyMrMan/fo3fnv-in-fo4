ScriptName F3NV_ScriptPackages extends Quest Hidden
{FO3/FNV script packages (AddScriptPackage, RemoveScriptPackage) on Fallout 4. Alias i of this quest is a collection alias whose package list runs Packages[i], ahead of its members' own packages. An actor stands in at most one, as FO3/FNV keep one script package per actor: adding another replaces it. A Dialogue package ends once its actor talks (Talked). Each plugin has its own such quest; a plugin's names the game's (Hub), which every one registers with at start, and Add, Remove and Talked look across them all, so an actor stands in one alias of all of them.}

Package[] Property Packages Auto Const
Package[] Property Talks Auto Const
{The packages among Packages that are FO3/FNV Dialogue packages, done once their actor has talked.}
Int Property Holds Auto Const
{How many aliases follow the package aliases, each holding one actor at its placed spot until it gets a script package.}
F3NV_ScriptPackages Property Hub Auto Const
{The game's script-package quest, on a plugin's own one; None on the game's, which is the hub.}
Keyword Property InPackage Auto Const
{The keyword this quest's package aliases put on their actors: an actor without it is in none of them.}

F3NV_ScriptPackages[] Sources

Actor[] Held
Int[] HeldAlias

Event OnQuestInit()
  Quests()
EndEvent

F3NV_ScriptPackages[] Function Quests()
  {Every loaded plugin's script-package quest, this one first; a plugin's own registers with the hub on the way.}
  If !Hub
    Return All()
  EndIf
  Hub.Register(Self)
  F3NV_ScriptPackages[] quests = Hub.All()
  Int at = quests.Find(Self)
  If at > 0
    quests.Remove(at)
    quests.Insert(Self, 0)
  EndIf
  Return quests
EndFunction

Function Register(F3NV_ScriptPackages akQuest)
  {On the hub: `akQuest`, a plugin's own script-package quest, is one of Sources.}
  If !Sources
    Sources = new F3NV_ScriptPackages[0]
  EndIf
  If akQuest && akQuest != Self && Sources.Find(akQuest) < 0
    Sources.Add(akQuest)
  EndIf
EndFunction

F3NV_ScriptPackages[] Function All()
  {On the hub: itself, then every registered plugin's quest still loaded.}
  F3NV_ScriptPackages[] quests = new F3NV_ScriptPackages[1]
  quests[0] = Self
  Int i = 0
  While Sources && i < Sources.Length
    If Sources[i]
      quests.Add(Sources[i])
    EndIf
    i += 1
  EndWhile
  Return quests
EndFunction

Function Add(Actor akActor, Package akPackage)
  {FNV AddScriptPackage: `akActor` runs `akPackage`, in the alias of the first quest (this one, then the other plugins') whose Packages holds it (a package none runs leaves it to its own packages). Adding the package an actor already runs only re-evaluates it.}
  If akActor == None
    Return
  EndIf
  F3NV_ScriptPackages[] quests = Quests()
  F3NV_ScriptPackages owner = Self
  Int i = Packages.Find(akPackage)
  Int q = 1
  While i < 0 && q < quests.Length
    i = quests[q].Packages.Find(akPackage)
    owner = quests[q]
    q += 1
  EndWhile
  If i < 0
    owner = Self
  EndIf
  If TES4Polyfill.Tracing()
    TES4Polyfill.TraceWrite("scriptpackage", TES4Polyfill.TraceName(akActor) + "|" + akPackage + "|" + owner + " alias " + i)
  EndIf
  q = 0
  While q < quests.Length
    quests[q].Unhold(akActor)
    q += 1
  EndWhile
  RefCollectionAlias target = None
  If i >= 0
    target = owner.GetAlias(i) as RefCollectionAlias
  EndIf
  If !target || target.Find(akActor) < 0
    ReleaseAll(quests, akActor)
    If target
      target.AddRef(akActor)
      owner.Hold(akActor, i)
    EndIf
  EndIf
  akActor.EvaluatePackage()
  If TES4Polyfill.Tracing() && i >= 0
    Var[] args = new Var[2]
    args[0] = akActor
    args[1] = i
    owner.CallFunctionNoWait("TraceLater", args)
  EndIf
EndFunction

Function ReleaseAll(F3NV_ScriptPackages[] akQuests, Actor akActor)
  {Take `akActor` out of its script-package alias in any of `akQuests` (this one first): this quest's as Release does, the others' only where they recorded it, as a plugin's quest is newer than any save that holds unrecorded actors.}
  Release(akActor)
  Int q = 1
  While q < akQuests.Length
    akQuests[q].ReleaseHeld(akActor)
    q += 1
  EndWhile
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
  F3NV_ScriptPackages[] quests = Quests()
  Int q = 0
  While q < quests.Length
    quests[q].Unhold(akActor)
    q += 1
  EndWhile
  ReleaseAll(quests, akActor)
  akActor.EvaluatePackage()
EndFunction

Function Talked(Actor akActor)
  {`akActor` opens a talk (F3NV_Greeting): its script package ends in whichever plugin's quest runs it (TalkedHere).}
  If akActor == None
    Return
  EndIf
  F3NV_ScriptPackages[] quests = Quests()
  Int q = 0
  While q < quests.Length
    If quests[q].TalkedHere(akActor)
      Return
    EndIf
    q += 1
  EndWhile
EndFunction

Bool Function TalkedHere(Actor akActor)
  {`akActor` opens a talk. An FO3/FNV Dialogue package is done once its actor has talked, so a script package of `akActor` that is one (Talks) ends: the actor leaves its alias, and re-evaluates its own packages once out of the talk's scenes. Fallout 4's force greet that stands in for it never ends by itself, so without this the actor follows and greets again.}
  If akActor == None || !Talks || InPackage && !akActor.HasKeyword(InPackage)
    Return False
  EndIf
  Int t = 0
  While t < Talks.Length
    Int i = Packages.Find(Talks[t])
    If i >= 0 && (GetAlias(i) as RefCollectionAlias).Find(akActor) >= 0
      If TES4Polyfill.Tracing()
        TES4Polyfill.TraceWrite("scriptpackage", TES4Polyfill.TraceName(akActor) + "|" + Talks[t] + "|talked, alias " + i)
      EndIf
      Release(akActor)
      Var[] args = new Var[1]
      args[0] = akActor
      CallFunctionNoWait("EvaluateAfterTalk", args)
      Return True
    EndIf
    t += 1
  EndWhile
  Return False
EndFunction

Function EvaluateAfterTalk(Actor akActor)
  {Once `akActor` is in no scene (5 min at most), it re-evaluates its packages: its own, now its talk's script package is gone.}
  Int waited = 0
  While akActor.GetCurrentScene() && waited < 600
    Utility.Wait(0.5)
    waited += 1
  EndWhile
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

Bool Function ReleaseHeld(Actor akActor)
  {Take `akActor` out of the alias Hold recorded; whether one was.}
  Int at = -1
  If Held
    at = Held.Find(akActor)
  EndIf
  If at < 0
    Return False
  EndIf
  (GetAlias(HeldAlias[at]) as RefCollectionAlias).RemoveRef(akActor)
  Held.Remove(at)
  HeldAlias.Remove(at)
  Return True
EndFunction

Function Release(Actor akActor)
  {Take `akActor` out of the alias Hold recorded; an actor not recorded (an older save, a full list) out of every alias, unless it lacks InPackage (in no alias): that search is one call per alias, about 10 s for the game's 449. See docs/fork/fo4_pipeline.md#script-package-release}
  If ReleaseHeld(akActor)
    Return
  EndIf
  If InPackage && !akActor.HasKeyword(InPackage)
    Return
  EndIf
  Int i = 0
  While i < Packages.Length
    (GetAlias(i) as RefCollectionAlias).RemoveRef(akActor)
    i += 1
  EndWhile
EndFunction
