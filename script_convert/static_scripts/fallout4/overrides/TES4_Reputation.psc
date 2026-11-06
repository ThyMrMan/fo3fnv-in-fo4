; Fallout 4 overrides for TES4_Reputation.psc: a reputation's list also holds the actor value its Pip-Boy
; page row shows (slot 6, set on the player to the title, infamy range * 4 + fame range) and the global
; showing that row (slot 7, 1 once there is fame or infamy), as FNV lists a faction only after the first,
; and the REPUTATION tab's quest (slot 8, F3NV_ReputationTab), which holds the texts a change shows.
; See docs/fork/fo4_pipeline.md#reputation

; fallout4: replaces Set 155bfa0735c4693e7c138aa22a36b79f11bd8de6
Function Set(FormList rep, Int kind, Float value) global
  If !rep
    Return
  EndIf
  If value < 0.0
    value = 0.0
  EndIf
  Float before = Points(rep, kind)
  Int title = TitleIndex(rep)
  (rep.GetAt(Slot(kind)) as GlobalVariable).SetValue(value)
  Refresh(rep)
  If value != before
    Var[] args = new Var[4]
    args[0] = rep
    args[1] = kind
    args[2] = value > before
    args[3] = title
    Utility.CallGlobalFunctionNoWait("TES4_Reputation", "Announce", args)
  EndIf
EndFunction

; fallout4: new
Int Function TitleIndex(FormList rep) global
  {The title as infamy range * 4 + fame range, the order of the REPUTATION tab's titles.}
  Float top = (rep.GetAt(5) as GlobalVariable).GetValue()
  Return Range(Points(rep, 0), top) * 4 + Range(Points(rep, 1), top)
EndFunction

; fallout4: new
Function Announce(FormList rep, Int kind, Bool gained, Int titleBefore) global
  {What FNV's reputation change shows (FalloutNV.exe 0x615730): the reputation's name and its Fame or Infamy Gained or Reduced text for 2 s, and when the title moved, once no menu is open, a message box with the new title and the title sound (fame's UIRepGood, infamy's UIRepBad). See docs/fork/fo4_pipeline.md#reputation-messages}
  F3NV_ReputationTab texts = rep.GetAt(8) as F3NV_ReputationTab
  ActorValue page = rep.GetAt(6) as ActorValue
  If !texts || !page
    Return
  EndIf
  String name = page.GetName()
  Debug.Notification(name + ": " + texts.Change(kind, gained))
  Int title = TitleIndex(rep)
  If title == titleBefore
    Return
  EndIf
  While Utility.IsInMenuMode() || UI.IsMenuOpen("DialogueMenu")
    Utility.WaitMenuMode(0.5)
  EndWhile
  Sound cue = texts.TitleDown
  If kind == 1
    cue = texts.TitleUp
  EndIf
  If cue
    cue.Play(Game.GetPlayer())
  EndIf
  Debug.MessageBox(name + "\n" + texts.Values[title])
EndFunction

; fallout4: replaces Refresh 00fee2dc87bfd8aec21ab73d6595885ecba30b86
Function Refresh(FormList rep) global
  Float top = (rep.GetAt(5) as GlobalVariable).GetValue()
  Int fame = Range(Points(rep, 1), top)
  Int infamy = Range(Points(rep, 0), top)
  Int title = Title(fame, infamy)
  Int axis = 0
  While axis < 3
    Int value = 0
    If title == 0
      value = 1
    ElseIf title / 10 == axis
      value = title % 10
    EndIf
    (rep.GetAt(2 + axis) as GlobalVariable).SetValue(value as Float)
    axis += 1
  EndWhile
  ActorValue page = rep.GetAt(6) as ActorValue
  If page
    Game.GetPlayer().SetValue(page, (infamy * 4 + fame) as Float)
  EndIf
  GlobalVariable shown = rep.GetAt(7) as GlobalVariable
  If shown && (Points(rep, 0) > 0.0 || Points(rep, 1) > 0.0)
    shown.SetValue(1.0)
  EndIf
  If TES4Polyfill.Tracing()
    TES4Polyfill.TraceWrite("rep", rep + "|" + Points(rep, 1) + "|" + Points(rep, 0) + "|" + (infamy * 4 + fame))
  EndIf
EndFunction
