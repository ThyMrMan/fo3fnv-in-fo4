ScriptName F3NV_GestureIdle extends TopicInfo Hidden
{On the last part of an FO3/FNV line whose speaker idle loops a count on the Special Idle group (the group FO3/FNV's own line gestures play on): the count is baked into one long clip, so as the line ends the gesture stops (TES4Polyfill.EndGesture) instead of outlasting the line. See docs/fork/fo4_idles.md#line-gestures}

Event OnEnd(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  TES4Polyfill.EndGesture(akSpeakerRef as Actor)
EndEvent
