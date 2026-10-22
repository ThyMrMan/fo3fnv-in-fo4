ScriptName TES4_ConditionRepairItem extends ActiveMagicEffect Hidden
{The Repair hotkey item's effect: gives the item back, so it stays on the Favorites wheel, and repairs the equipped weapon from a spare (TES4_ConditionCalls.RepairWithSpare), showing the result; with no spare it shows the weapon's condition.}

Potion Property Hotkey Auto Const
Form[] Property Weapons Auto Const
Form[] Property RepairLists Auto Const
ActorValue Property Repair Auto Const
Message Property RepairedNote Auto Const
{"Repaired: %.0f%%".}
Message Property NoSpareNote Auto Const
{"No spare to repair with. Condition %.0f%%".}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  akCaster.AddItem(Hotkey, 1, True)
  Bool repaired = TES4_ConditionCalls.RepairWithSpare(akCaster, Weapons, RepairLists, Repair)
  Float percent = TES4_ConditionCalls.WeaponPercent(akCaster)
  If repaired
    RepairedNote.Show(percent)
  Else
    NoSpareNote.Show(percent)
  EndIf
EndEvent
