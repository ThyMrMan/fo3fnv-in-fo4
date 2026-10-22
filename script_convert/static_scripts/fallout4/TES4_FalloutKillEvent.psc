ScriptName TES4_FalloutKillEvent extends Quest Hidden
{Started by the Story Manager on a kill (event KILL); it stops first, so the next kill finds it free, then hands the kill to TES4_FalloutStandings.}

TES4_FalloutStandings Property Standings Auto Const

Event OnStoryKillActor(ObjectReference akVictim, ObjectReference akKiller, Location akLocation, int aiCrimeStatus, int aiRelationshipRank)
  Stop()
  Standings.NoteKill(akVictim as Actor, akKiller as Actor, aiCrimeStatus)
EndEvent
