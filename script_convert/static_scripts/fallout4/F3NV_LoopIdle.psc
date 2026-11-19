ScriptName F3NV_LoopIdle extends TopicInfo Hidden
{On an FO3/FNV line whose speaker idle outlasts the line (loop count 255, played on FO4's looping dynamic idle until something stops it, or a counted loop baked into one long clip): as the line begins, the speaker's idle is released once its AI package changes, as FO3/FNV end a forever-looping idle when the actor's package moves it on (TES4Polyfill.ReleaseLoopIdle). See docs/fork/fo4_idles.md#loop-release}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  Var[] args = new Var[1]
  args[0] = akSpeakerRef as Actor
  Utility.CallGlobalFunctionNoWait("TES4Polyfill", "ReleaseLoopIdle", args)
EndEvent
