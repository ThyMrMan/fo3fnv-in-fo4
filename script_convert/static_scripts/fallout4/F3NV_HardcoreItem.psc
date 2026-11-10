ScriptName F3NV_HardcoreItem extends ActiveMagicEffect Hidden
{The Hardcore item's effect: gives the item back, then shows the needs and the Hardcore switch (F3NV_Hardcore.Menu), FNV's Gameplay setting. See docs/fork/fo4_hardcore.md#built}

F3NV_Hardcore Property Manager Auto Const Mandatory
Potion Property Hotkey Auto Const

Event OnEffectStart(Actor akTarget, Actor akCaster)
  akCaster.AddItem(Hotkey, 1, True)
  Manager.Menu()
EndEvent
