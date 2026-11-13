ScriptName F3NV_ConditionCalls Hidden
{FO3/FNV's condition commands on Fallout 4, over CRUI_Condition's natives: weapon percents run 0 to 100 and an item's health 0 to 1, as FNV's do. An item with no health set yet is whole.}

Float Function WeaponPercent(Actor akActor) Global
  {GetWeaponHealthPerc: the equipped weapon's condition, 0 to 100.}
  Float health = CRUI_Condition.GetEquippedWeaponHealth(akActor)
  If health < 0.0
    Return 100.0
  EndIf
  Return health * 100.0
EndFunction

Function SetWeaponPercent(Actor akActor, Float afPercent) Global
  {SetWeaponHealthPerc: set the equipped weapon's condition, 0 to 100.}
  Weapon gun = akActor.GetEquippedWeapon()
  If gun
    CRUI_Condition.SetHealth(akActor, gun, afPercent / 100.0)
  EndIf
EndFunction

Function ModWeaponPercent(Actor akActor, Float afPercent) Global
  {ModWeaponHealthPerc: change the equipped weapon's condition by afPercent points (Miss Fortune's -100 breaks it).}
  SetWeaponPercent(akActor, WeaponPercent(akActor) + afPercent)
EndFunction

Function AddWithHealth(ObjectReference akTarget, Form akItem, Int aiCount, Float afHealth, Bool abSilent = False) Global
  {AddItemHealthPercent: give akTarget aiCount of akItem at health afHealth (0 to 1).}
  akTarget.AddItem(akItem, aiCount, abSilent)
  CRUI_Condition.SetHealth(akTarget, akItem, afHealth)
EndFunction

Bool Function RepairWithSpare(Actor akActor, Form akItem, Int aiStack) Global
  {Repair stack aiStack of akActor's akItem (-1: its equipped, else first) from a spare it carries, chosen as the Pip-Boy's repair list chooses it (the worst that still gives the best result; repair list and Jury Rigging included), by FNV's rule (CRUI_Condition.RepairWith); the spare is used up. False with no spare.}
  Return akItem && CRUI_Condition.RepairWith(akActor, akItem, aiStack, None, -1) >= 0.0
EndFunction

Function ShowRepairMenu(Actor akVendor) Global
  {ShowRepairMenu: akVendor's repair services on the Pip-Boy's repair card (G) until the Pip-Boy next closes, at FNV's cap and price for akVendor's Repair skill. The player opens the Pip-Boy: UI.OpenMenu opens its menu without raising it and locks input (played 2026-10-23).}
  CRUI_Condition.SetVendor(akVendor)
  Debug.Notification("Repair services: open your Pip-Boy, highlight an item and press G.")
EndFunction

Form[] Function WornOf(Actor akActor, Form[] akArmors) Global
  {The armor of akArmors akActor wears, each once (F4SE's worn items by biped slot).}
  Form[] out = new Form[0]
  Int slot = 0
  While slot < 32
    Form item = akActor.GetWornItem(slot).item
    If item && akArmors.Find(item) >= 0 && out.Find(item) < 0
      out.Add(item)
    EndIf
    slot += 1
  EndWhile
  Return out
EndFunction

Float Function Whole(Float afHealth) Global
  {A health read as an item's condition: 1 (whole) when none is set yet.}
  If afHealth < 0.0
    Return 1.0
  EndIf
  Return afHealth
EndFunction
