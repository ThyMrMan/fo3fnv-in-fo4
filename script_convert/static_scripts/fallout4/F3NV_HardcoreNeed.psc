ScriptName F3NV_HardcoreNeed extends ActiveMagicEffect Hidden
{An FNV Hardcore need effect on a consumable: changes need Need (0 Dehydration, 1 Hunger, 2 Sleep Deprivation) by Amount, FNV's own points (raising it when positive), while Hardcore mode is on. See docs/fork/fo4_hardcore.md#built}

F3NV_Hardcore Property Manager Auto Const Mandatory
Int Property Need Auto Const
Float Property Amount Auto Const
{FNV's magnitude, as vanilla's AddictionOddsScript carries its Magnitude: FO4 effects cannot read their own.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If akTarget == Game.GetPlayer()
    Manager.Need(Need, Amount)
  EndIf
EndEvent
