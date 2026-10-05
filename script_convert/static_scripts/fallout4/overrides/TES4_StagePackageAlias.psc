; Fallout 4 overrides for TES4_StagePackageAlias.psc: the quest's native stage event replaces
; Skyrim's SKSE mod event, so TES4Polyfill.StageSet has nothing to send.
; See docs/fork/fo4_spikes.md#spike-3-helpers

; fallout4: replaces OnInit 667b71d0a8ed81439a72fc68a6a929819ce7439e
Event OnInit()
  RegisterForRemoteEvent(GetOwningQuest(), "OnStageSet")
EndEvent

; fallout4: replaces OnTES4StageSet c844bb892321694711dd5c749b433854ed768173
Event Quest.OnStageSet(Quest akSender, Int auiStageID, Int auiItemID)
  Recheck()
EndEvent
