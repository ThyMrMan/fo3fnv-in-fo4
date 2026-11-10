ScriptName F3NV_CasinoPlayer extends ReferenceAlias Hidden
{The player's alias on the casino quest: registers the menu again on each load (F4SE forgets it) and starts FNV's anti-cheat wait. See docs/fork/fo4_casino_plan.md#design-persist}

Event OnPlayerLoadGame()
  (GetOwningQuest() as F3NV_Casino).Loaded()
EndEvent
