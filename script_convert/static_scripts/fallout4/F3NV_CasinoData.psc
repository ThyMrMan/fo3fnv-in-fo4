ScriptName F3NV_CasinoData extends Quest
{One FNV casino (CSNO): its house rules and art as properties, the player's earnings and comp level there as state. FNV kept casino, earnings and level on the player; levels 1-4 come at 25, 50, 75 and 100% of the casino's max winnings, 4 is the ban. See docs/fork/fo4_casino_plan.md#rules-bank}

String Property CasinoName Auto Const
Int Property Decks Auto Const
Float Property ReshuffleShare Auto Const
Float Property Payout Auto Const
Bool Property DealerStaysOnSoft17 Auto Const
Int[] Property ReelStops Auto Const
Int Property MaxWinnings Auto Const
MiscObject Property Chip Auto Const
Quest Property WinningsQuest Auto Const
{FNV's comps quest, started when a new level is reached (FNV's menu enabled it).}
GlobalVariable Property LevelGlobal Auto Const
{The level, for dialogue conditions (FNV's GetCasinoWinningStage).}
String[] Property Symbols Auto Const
String[] Property CardBacks Auto Const

Int earnings
Int level

Int Function GetEarnings()
  Return earnings
EndFunction

Int Function GetLevel()
  {FNV's GetCasinoWinningsLevel: 0 to 4.}
  Return level
EndFunction

Int Function LevelFor(Int aiEarnings)
  {The level earnings of aiEarnings reach: 1-4 at 25, 50, 75, 100% of MaxWinnings.}
  If MaxWinnings <= 0
    Return 0
  EndIf
  Int reached = 0
  While reached < 4 && aiEarnings * 4 >= MaxWinnings * (reached + 1)
    reached += 1
  EndWhile
  Return reached
EndFunction

Bool Function AddResult(Int aiNet)
  {Add a round's net chips to the earnings; True when that reaches a new level (its comps quest is started).}
  earnings += aiNet
  Int reached = LevelFor(earnings)
  If reached <= level
    Return False
  EndIf
  level = reached
  If LevelGlobal
    LevelGlobal.SetValue(level as Float)
  EndIf
  If WinningsQuest && !WinningsQuest.IsRunning()
    WinningsQuest.Start()
  EndIf
  Return True
EndFunction
