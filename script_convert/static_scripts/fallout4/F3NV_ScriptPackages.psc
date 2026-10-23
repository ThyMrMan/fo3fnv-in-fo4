ScriptName F3NV_ScriptPackages extends Quest Hidden
{FO3/FNV script packages (AddScriptPackage, RemoveScriptPackage) on Fallout 4. Alias i of this quest is a collection alias whose package list runs Packages[i], ahead of its members' own packages. An actor stands in at most one, as FO3/FNV keep one script package per actor: adding another replaces it.}

Package[] Property Packages Auto Const

Function Add(Actor akActor, Package akPackage)
  {FNV AddScriptPackage: `akActor` runs `akPackage` (a package no alias runs leaves it to its own packages).}
  If akActor == None
    Return
  EndIf
  Release(akActor)
  Int i = Packages.Find(akPackage)
  If i >= 0
    (GetAlias(i) as RefCollectionAlias).AddRef(akActor)
  EndIf
  akActor.EvaluatePackage()
EndFunction

Function Remove(Actor akActor)
  {FNV RemoveScriptPackage: `akActor` back on its own packages.}
  If akActor == None
    Return
  EndIf
  Release(akActor)
  akActor.EvaluatePackage()
EndFunction

Function Release(Actor akActor)
  {Take `akActor` out of every alias.}
  Int i = 0
  While i < Packages.Length
    (GetAlias(i) as RefCollectionAlias).RemoveRef(akActor)
    i += 1
  EndWhile
EndFunction
