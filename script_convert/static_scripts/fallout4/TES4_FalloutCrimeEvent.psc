ScriptName TES4_FalloutCrimeEvent extends Quest Hidden
{Started by the Story Manager when crime gold is added (event ADCR); it stops first, so the next crime finds it free, then hands the crime to TES4_FalloutStandings.}

TES4_FalloutStandings Property Standings Auto Const

Event OnStoryCrimeGold(ObjectReference akVictim, ObjectReference akCriminal, Form akFaction, int aiGoldAmount, int aiCrime)
  Stop()
  Standings.NoteCrime(akVictim as Actor, akCriminal as Actor, aiCrime)
EndEvent
