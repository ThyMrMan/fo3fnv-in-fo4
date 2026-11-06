ScriptName F3NV_ReputationTab extends F3NV_PipboyTab Hidden
{The Pip-Boy REPUTATION tab, which also holds what FNV shows as a reputation changes (TES4_Reputation.Announce): its texts (FalloutNV.esm's sRepPositiveGain, sRepPositiveLoss, sRepNegativeGain, sRepNegativeLoss), the titles (Values) and its sounds (sRepChangePosSound, sRepChangeNegSound). See docs/fork/fo4_pipeline.md#reputation-messages}

String Property FameGained Auto Const
String Property FameReduced Auto Const
String Property InfamyGained Auto Const
String Property InfamyReduced Auto Const
Sound Property TitleUp Auto Const
{UIRepGood: a fame change moved the title.}
Sound Property TitleDown Auto Const
{UIRepBad: an infamy change moved the title.}

String Function Change(Int aiKind, Bool abGained)
  {The text for points of `aiKind` (1 fame, else infamy) gained or reduced.}
  If aiKind == 1
    If abGained
      Return FameGained
    EndIf
    Return FameReduced
  ElseIf abGained
    Return InfamyGained
  EndIf
  Return InfamyReduced
EndFunction
