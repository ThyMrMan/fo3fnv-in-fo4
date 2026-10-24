ScriptName F3NV_ChallengesPlayer extends ReferenceAlias Hidden
{The player's alias on the challenges quest: hands F3NV_Challenges the player's kills, the potions and chems used and the player's limbs crippled. See docs/fork/fo4_pipeline.md#challenges}

Event OnKill(Actor akVictim)
  Challenges().Note(0, -1, 1, akVictim, None)
EndEvent

Event OnItemEquipped(Form akBaseObject, ObjectReference akReference)
  If akBaseObject as Potion
    Challenges().Note(2, -1, 1, None, akBaseObject)
  EndIf
EndEvent

Event OnCripple(ActorValue akActorValue, Bool abCrippled)
  If abCrippled
    Challenges().Note(4, -1, 1, None, None)
  EndIf
EndEvent

F3NV_Challenges Function Challenges()
  {The challenges quest.}
  Return GetOwningQuest() as F3NV_Challenges
EndFunction
