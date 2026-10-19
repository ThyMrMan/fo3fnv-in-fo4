ScriptName TES4_SayOnce extends TopicInfo Hidden
{FO3/FNV Say Once across a line's copies on Fallout 4: as one copy begins, its line's marker stage is set in the marker quest, which every copy's GetStageDone checks. The markers sit in their own quest because FO4's GetStage reads a quest's highest done stage, so a marker in the line's own quest would stand in for its story stage.}

Quest Property Marks Auto Const
{The marker quest (FNV_TES4SayOnce).}
Int Property Stage Auto Const
{This line's marker stage in it.}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  Marks.SetStage(Stage)
EndEvent
