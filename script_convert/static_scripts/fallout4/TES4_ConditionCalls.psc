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

Bool Function RepairWithSpare(Actor akActor, Form[] akWeapons, Form[] akRepairLists, ActorValue akRepair) Global
  {Repair akActor's equipped weapon from a spare it carries: another of the same weapon, else an item of its repair list (akRepairLists[i] for akWeapons[i]). FNV's rule: the better of the two conditions, plus 5, plus 0.15 per Repair point, plus 0.05 of the worse, in percent; the spare is used up. False with no spare.}
  Weapon gun = akActor.GetEquippedWeapon()
  Int i = akWeapons.Find(gun)
  If !gun || i < 0
    Return False
  EndIf
  Form spare = Spare(akActor, gun, akRepairLists[i] as FormList)
  If !spare
    Return False
  EndIf
  Float ours = Whole(TES4_Condition.GetHealth(akActor, gun)) * 100.0
  Float theirs = ours
  If spare != gun
    theirs = Whole(TES4_Condition.GetHealth(akActor, spare)) * 100.0
  EndIf
  Float better = Math.Max(ours, theirs)
  Float worse = Math.Min(ours, theirs)
  Float repaired = better + 5.0 + 0.15 * akActor.GetValue(akRepair) + 0.05 * worse
  akActor.RemoveItem(spare, 1, True)
  TES4_Condition.SetHealth(akActor, gun, Math.Min(repaired, 100.0) / 100.0)
  Return True
EndFunction

Form Function Spare(Actor akActor, Weapon akGun, FormList akList) Global
  {A spare for akGun: another akGun, else the first item of akList akActor carries; None.}
  If akActor.GetItemCount(akGun) > 1
    Return akGun
  EndIf
  If !akList
    Return None
  EndIf
  Int i = 0
  While i < akList.GetSize()
    Form item = akList.GetAt(i)
    If item != akGun && akActor.GetItemCount(item) > 0
      Return item
    EndIf
    i += 1
  EndWhile
  Return None
EndFunction

Float Function Whole(Float afHealth) Global
  {A health read as an item's condition: 1 (whole) when none is set yet.}
  If afHealth < 0.0
    Return 1.0
  EndIf
  Return afHealth
EndFunction
