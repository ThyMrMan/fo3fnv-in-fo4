ScriptName TES4_ConditionCalls Hidden
{FO3/FNV's condition commands on Fallout 4, over TES4_Condition's natives: weapon percents run 0 to 100 and an item's health 0 to 1, as FNV's do. An item with no health set yet is whole.}

Float Function WeaponPercent(Actor akActor) Global
  {GetWeaponHealthPerc: the equipped weapon's condition, 0 to 100.}
  Float health = TES4_Condition.GetEquippedWeaponHealth(akActor)
  If health < 0.0
    Return 100.0
  EndIf
  Return health * 100.0
EndFunction

Function SetWeaponPercent(Actor akActor, Float afPercent) Global
  {SetWeaponHealthPerc: set the equipped weapon's condition, 0 to 100.}
  Weapon gun = akActor.GetEquippedWeapon()
  If gun
    TES4_Condition.SetHealth(akActor, gun, afPercent / 100.0)
  EndIf
EndFunction

Function ModWeaponPercent(Actor akActor, Float afPercent) Global
  {ModWeaponHealthPerc: change the equipped weapon's condition by afPercent points (Miss Fortune's -100 breaks it).}
  SetWeaponPercent(akActor, WeaponPercent(akActor) + afPercent)
EndFunction

Function AddWithHealth(ObjectReference akTarget, Form akItem, Int aiCount, Float afHealth, Bool abSilent = False) Global
  {AddItemHealthPercent: give akTarget aiCount of akItem at health afHealth (0 to 1).}
  akTarget.AddItem(akItem, aiCount, abSilent)
  TES4_Condition.SetHealth(akTarget, akItem, afHealth)
EndFunction

Bool Function RepairWithSpare(Actor akActor, Form akItem, Int aiStack) Global
  {Repair stack aiStack of akActor's akItem (-1: its equipped, else first) from a spare it carries, chosen as the Pip-Boy's repair list chooses it (the worst that still gives the best result; repair list and Jury Rigging included), by FNV's rule (TES4_Condition.RepairWith); the spare is used up. False with no spare.}
  Return akItem && TES4_Condition.RepairWith(akActor, akItem, aiStack, None, -1) >= 0.0
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
