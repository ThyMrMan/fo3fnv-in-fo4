ScriptName F3NV_CowerPackage extends Package Hidden
{Fragments of an FNV Flee Not Combat with no location or target, which cowers where it runs: while it runs the actor's Confidence is set to 0 (Cowardly), so FO4's combat AI flees and cowers; its end sets back the value it had. FO4 refuses ModValue on Confidence, and vanilla only calls SetValue on it. Each actor is lowered once, as FO4 repeats a current package's OnEnd.}

ActorValue Property Confidence Auto Const
Actor[] Cowering
Float[] Before

; Fragment_0: OnBegin.
Function Fragment_0(Actor akActor)
  If !Cowering
    Cowering = new Actor[0]
    Before = new Float[0]
  EndIf
  If Cowering.Find(akActor) < 0
    Cowering.Add(akActor)
    Before.Add(akActor.GetBaseValue(Confidence))
    akActor.SetValue(Confidence, 0.0)
  EndIf
EndFunction

; Fragment_1: OnEnd.
Function Fragment_1(Actor akActor)
  If !Cowering
    Return
  EndIf
  Int i = Cowering.Find(akActor)
  If i >= 0
    akActor.SetValue(Confidence, Before[i])
    Cowering.Remove(i)
    Before.Remove(i)
  EndIf
EndFunction
