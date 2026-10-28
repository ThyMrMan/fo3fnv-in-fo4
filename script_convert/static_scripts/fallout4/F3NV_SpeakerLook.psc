ScriptName F3NV_SpeakerLook extends ObjectReference
{The look of an FNV talking machine (Mr. House's screen, Yes Man, Festus): FNV's creature was the screen itself, so
activating the look activates its unseen speaker, which starts the conversation.
See: docs/fork/fo4_creature_audit.md#talking-machines}

Actor Property Speaker Auto Const

Event OnActivate(ObjectReference akActionRef)
  If Speaker
    Speaker.Activate(akActionRef)
  EndIf
EndEvent
