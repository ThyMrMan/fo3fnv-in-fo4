ScriptName F3NV_DoorCloser extends ObjectReference Hidden
{An FNV door: one an NPC opens closes again once that NPC is Clear units away, as FNV's engine closes doors behind actors (Fallout 4 leaves them open); the player's stay as left. See docs/fork/fo4_pipeline.md#door-closer.}

Float Clear = 200.0

Event OnOpen(ObjectReference akActionRef)
  Actor who = akActionRef as Actor
  If who && who != Game.GetPlayer()
    RegisterForDistanceGreaterThanEvent(who, Self, Clear)
  EndIf
EndEvent

; Open state 1 is Open (0 None, 2 Opening, 3 Closed, 4 Closing).
Event OnDistanceGreaterThan(ObjectReference akObj1, ObjectReference akObj2, Float afDistance)
  If GetOpenState() == 1
    SetOpen(False)
  EndIf
EndEvent
