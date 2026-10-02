ScriptName TES4_FalloutCrime extends Quest Hidden
{FO3/FNV major crimes: a reported murder, or an assault, by the player makes
every Track Crime faction the victim is in the player's enemy, as Fallout's
crime list did; theft and trespass stay the victim's own business. The Story
Manager starts this quest on the kill or assault; it stops first, so the next
event finds it free. TES4TrackCrimeFactions lists every Track Crime faction.
Skyrim keeps each faction's player-enemy flag but has no Papyrus read of it,
so every converted set also records the faction in TES4PlayerEnemyFactions,
which converted reads (GetPCEnemyOfFaction, GetActorFactionPlayerEnemy) test.
See: docs/commentary/tes5_import_actors.md#fallout-crime-factions}

FormList Property TES4TrackCrimeFactions Auto
FormList Property TES4PlayerEnemyFactions Auto

Event OnStoryKillActor(ObjectReference akVictim, ObjectReference akKiller, Location akLocation, Int aiCrimeStatus, Int aiRelationshipRank)
  Stop()
  If aiCrimeStatus == 2 && akKiller == Game.GetPlayer()
    TES4VictimFactions(akVictim as Actor)
  EndIf
EndEvent

Event OnStoryAssaultActor(ObjectReference akVictim, ObjectReference akAttacker, Location akLocation, Int aiCrime)
  Stop()
  If aiCrime && akAttacker == Game.GetPlayer()
    TES4VictimFactions(akVictim as Actor)
  EndIf
EndEvent

; Every Track Crime faction akVictim is in becomes the player's enemy.
Function TES4VictimFactions(Actor akVictim)
  If !akVictim || !TES4TrackCrimeFactions
    Return
  EndIf
  Int i = TES4TrackCrimeFactions.GetSize()
  While i > 0
    i -= 1
    Faction f = TES4TrackCrimeFactions.GetAt(i) as Faction
    If f && akVictim.IsInFaction(f)
      TES4SetEnemy(f, True, TES4PlayerEnemyFactions)
    EndIf
  EndWhile
EndFunction

; Set or clear akFaction's player-enemy flag, keeping akEnemies (the factions flagged) in step.
Function TES4SetEnemy(Faction akFaction, Bool abEnemy, FormList akEnemies) Global
  If !akFaction
    Return
  EndIf
  akFaction.SetPlayerEnemy(abEnemy)
  If akEnemies && abEnemy
    akEnemies.AddForm(akFaction)
  ElseIf akEnemies
    akEnemies.RemoveAddedForm(akFaction)
  EndIf
EndFunction

; Whether akFaction's player-enemy flag is set (GetPCEnemyOfFaction).
Bool Function TES4IsEnemy(Faction akFaction, FormList akEnemies) Global
  Return akFaction && akEnemies && akEnemies.HasForm(akFaction)
EndFunction

; Clear the flag on each flagged faction akActor is in (ClearActorsFactionsPlayerEnemyFlag).
Function TES4ClearActor(Actor akActor, FormList akEnemies) Global
  If !akActor || !akEnemies
    Return
  EndIf
  Int i = akEnemies.GetSize()
  While i > 0
    i -= 1
    Faction f = akEnemies.GetAt(i) as Faction
    If f && akActor.IsInFaction(f)
      TES4SetEnemy(f, False, akEnemies)
    EndIf
  EndWhile
EndFunction

; Whether any flagged faction holds akActor (GetActorFactionPlayerEnemy).
Bool Function TES4AnyEnemy(Actor akActor, FormList akEnemies) Global
  If !akActor || !akEnemies
    Return False
  EndIf
  Int i = akEnemies.GetSize()
  While i > 0
    i -= 1
    Faction f = akEnemies.GetAt(i) as Faction
    If f && akActor.IsInFaction(f)
      Return True
    EndIf
  EndWhile
  Return False
EndFunction
