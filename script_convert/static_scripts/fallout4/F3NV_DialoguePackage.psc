ScriptName F3NV_DialoguePackage extends Package Hidden
{Fragments of an FNV Dialogue package aimed at an NPC, which FO4 runs as a Travel to that NPC: on arrival the actor and its target play the package topic's chat scene, once each time the package starts, as FO4 repeats a current package's OnEnd.}

Scene Property Chat Auto Const
ObjectReference Property Target Auto Const
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
    TES4Polyfill.StartConversation(Chat, akActor, Target)
  EndIf
EndFunction
