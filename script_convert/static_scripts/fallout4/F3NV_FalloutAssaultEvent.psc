ScriptName F3NV_FalloutAssaultEvent extends Quest Hidden
{Started by the Story Manager on an assault (event ASSU); it stops first, so the next assault finds it free, then hands the assault to F3NV_FalloutStandings.}

F3NV_FalloutStandings Property Standings Auto Const

Event OnStoryAssaultActor(ObjectReference akVictim, ObjectReference akAttacker, Location akLocation, int aiCrime)
  Stop()
  Standings.NoteAssault(akVictim as Actor, akAttacker as Actor, aiCrime)
EndEvent
