ScriptName F3NV_SwitchIdle extends TopicInfo Hidden
{On an FO3/FNV line whose speaker idle replaces an idle an earlier line of its topic left running (a counted or forever loop): FO4 starts no idle over a playing one, so as the line begins Bridge (Played on FO4's looping event) leaves the running idle and Played starts from it (TES4Polyfill.SwitchIdle), as FO3/FNV go straight from one idle to the next. See docs/fork/fo4_idles.md#idle-switch}

Idle Property Played Auto Const
Idle Property Bridge Auto Const

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  Var[] args = new Var[3]
  args[0] = akSpeakerRef as Actor
  args[1] = Played
  args[2] = Bridge
  Utility.CallGlobalFunctionNoWait("TES4Polyfill", "SwitchIdle", args)
EndEvent
