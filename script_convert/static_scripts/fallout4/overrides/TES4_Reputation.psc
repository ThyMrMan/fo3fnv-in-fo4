; Fallout 4 overrides for TES4_Reputation.psc: a reputation's list also holds the actor value its Pip-Boy
; page row shows (slot 6, set on the player to the title, infamy range * 4 + fame range) and the global
; showing that row (slot 7, 1 once there is fame or infamy), as FNV lists a faction only after the first.
; See docs/fork/fo4_pipeline.md#reputation

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
