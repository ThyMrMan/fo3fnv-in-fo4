ScriptName F3NV_CowerPackage extends Package Hidden
{Fragments of an FNV Flee Not Combat with no location or target, which cowers where it runs: while it runs the actor's Confidence is lowered by 4 (Cowardly from any FO4 value, 0 to 4), so FO4's combat AI flees and cowers; its end puts it back. Each actor is lowered once, as FO4 repeats a current package's OnEnd.}

ActorValue Property Confidence Auto Const
Actor[] Cowering

; Fragment_0: OnBegin.
Function Fragment_0(Actor akActor)
  If !Cowering
    Cowering = new Actor[0]
  EndIf
  If Cowering.Find(akActor) < 0
    Cowering.Add(akActor)
    akActor.ModValue(Confidence, -4.0)
  EndIf
EndFunction

; Fragment_1: OnEnd.
Function Fragment_1(Actor akActor)
  If !Cowering
    Return
  EndIf
  Int i = Cowering.Find(akActor)
  If i >= 0
    Cowering.Remove(i)
    akActor.ModValue(Confidence, 4.0)
  EndIf
EndFunction
