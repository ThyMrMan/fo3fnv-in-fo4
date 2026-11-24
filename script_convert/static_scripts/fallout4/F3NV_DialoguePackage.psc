ScriptName F3NV_DialoguePackage extends Package Hidden
{Fragments of an FNV Dialogue package aimed at an NPC, which FO4 runs as a Travel to its Wait Location (with none, to that NPC): on arrival the actor waits for its target in the Trigger Location, walks up to it beyond the Activate Distance and the two play the package topic's chat scene (TES4Polyfill.ChatArrived), once each time the package starts, as FO4 repeats a current package's OnEnd. A quest-gated Once Per Day package (TES4DayDone set) is then done for good: see docs/fork/fo4_pipeline.md#once-per-day and #npc-chat-wait.}

Scene Property Chat Auto Const
ObjectReference Property TES4ChatTarget Auto Const
Int Property TES4WalkPlace = -1 Auto Const
Form Property TES4WalkTrigger Auto Const
Float Property TES4WalkReach Auto Const
Float Property TES4ChatReach = 150.0 Auto Const
Float Property TES4ChatSpeed Auto Const
Faction Property TES4DayDone Auto Const
Actor[] Spoken

; Fragment_0: OnBegin.
Function Fragment_0(Actor akActor)
  If Spoken
    Int i = Spoken.Find(akActor)
    If i >= 0
      Spoken.Remove(i)
    EndIf
  EndIf
EndFunction

; Fragment_1: OnEnd.
Function Fragment_1(Actor akActor)
  If !Spoken
    Spoken = new Actor[0]
  EndIf
  If Spoken.Find(akActor) < 0
    Spoken.Add(akActor)
    If TES4Polyfill.ChatArrived(akActor, Self, Chat, TES4ChatTarget, TES4WalkPlace, TES4WalkTrigger, TES4WalkReach, TES4ChatReach, TES4ChatSpeed)
      TES4Polyfill.PackageDone(akActor, TES4DayDone)
    EndIf
  EndIf
EndFunction
