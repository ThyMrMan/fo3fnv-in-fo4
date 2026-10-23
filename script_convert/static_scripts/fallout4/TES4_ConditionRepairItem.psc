ScriptName TES4_ConditionRepairItem extends ActiveMagicEffect Hidden
{The Repair hotkey item's effect: gives the item back, so it stays on the Favorites wheel, and has the condition quest's player alias repair the equipped weapon or the most worn armor piece (TES4_ConditionPlayer.RepairFromHotkey).}

Potion Property Hotkey Auto Const
Quest Property Owner Auto Const
{The condition quest; its player alias has ID 0.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  akCaster.AddItem(Hotkey, 1, True)
  (Owner.GetAlias(0) as TES4_ConditionPlayer).RepairFromHotkey()
EndEvent
