ScriptName TES4_KarmaPage extends Quest Hidden
{The karma Pip-Boy page (Pip-Boy Tabs): each time the Pip-Boy opens, the player's Alignment row is set to FNV's karma level (0 very evil to 4 very good, by FNV's fAlign thresholds) and the Title row to FNV's karmic title for that alignment and the player's level (5 + kind * 30 + level - 1; kind 0 evil, 1 neutral, 2 good; levels past 30 take 30's). See docs/fork/fo4_pipeline.md#karma-page}

GlobalVariable Property TES4Karma Auto Const
ActorValue Property AlignmentValue Auto Const
ActorValue Property TitleValue Auto Const
Float Property VeryEvilMax Auto Const
Float Property EvilMax Auto Const
Float Property GoodMin Auto Const
Float Property VeryGoodMin Auto Const

Event OnQuestInit()
  RegisterForMenuOpenCloseEvent("PipboyMenu")
  Refresh()
EndEvent

Event OnMenuOpenCloseEvent(string asMenuName, bool abOpening)
  If abOpening
    Refresh()
  EndIf
EndEvent

Function Refresh()
  Float karma = TES4Karma.GetValue()
  Int alignment = 2
  If karma <= VeryEvilMax
    alignment = 0
  ElseIf karma <= EvilMax
    alignment = 1
  ElseIf karma >= VeryGoodMin
    alignment = 4
  ElseIf karma >= GoodMin
    alignment = 3
  EndIf
  Int kind = 1
  If alignment < 2
    kind = 0
  ElseIf alignment > 2
    kind = 2
  EndIf
  Actor player = Game.GetPlayer()
  Int level = player.GetLevel()
  If level > 30
    level = 30
  EndIf
  player.SetValue(AlignmentValue, alignment as Float)
  player.SetValue(TitleValue, (5 + kind * 30 + level - 1) as Float)
EndFunction
