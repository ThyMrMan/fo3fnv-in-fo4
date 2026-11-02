ScriptName F3NV_PatrolSay extends TopicInfo Hidden
{The silent arrival line of an FNV patrol point that names only a topic: once it ends, the patroller says that topic, as FNV's patroller said it on arriving.}

Topic Property Arrival Auto Const

; Fragment_0: OnEnd.
Function Fragment_0(ObjectReference akSpeakerRef)
  TES4Polyfill.SayWhenFree(akSpeakerRef, Arrival, None)
EndFunction
