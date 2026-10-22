ScriptName TES4_AmmoSwitchItem extends ActiveMagicEffect Hidden
{The Ammo Type hotkey item's effect: gives the item back, so it stays on the Favorites wheel, and cycles the equipped gun's ammo (TES4_AmmoSwitch).}

TES4_AmmoSwitch Property Switch Auto Const
Potion Property Hotkey Auto Const

Event OnEffectStart(Actor akTarget, Actor akCaster)
  akCaster.AddItem(Hotkey, 1, True)
  Switch.Cycle()
EndEvent
