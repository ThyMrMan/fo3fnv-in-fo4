ScriptName TES4_KarmaPage extends TES4_PipboyTab Hidden
{The Pip-Boy's KARMA tab: each time it is given to the plugin (TES4_PipboyTab), the player's Alignment row is set to FNV's karma level (0 very evil to 4 very good, by FNV's fAlign thresholds) and the Title row to FNV's karmic title for that alignment and the player's level (5 + kind * 30 + level - 1; kind 0 evil, 1 neutral, 2 good; levels past 30 take 30's). See docs/fork/fo4_pipeline.md#karma-page}

GlobalVariable Property TES4Karma Auto Const
ActorValue Property AlignmentValue Auto Const
ActorValue Property TitleValue Auto Const
Float Property VeryEvilMax Auto Const
Float Property EvilMax Auto Const
Float Property GoodMin Auto Const
Float Property VeryGoodMin Auto Const

Function Send()
  {Set the rows, then give the plugin the tab.}
  Refresh()
  Parent.Send()
EndFunction

Function Refresh()
  {Set the Alignment and Title rows from the karma global and the player's level.}
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
