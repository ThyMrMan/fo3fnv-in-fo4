ScriptName TES4_Condition Native Hidden
{FO3/FNV item condition: the engine's own item health (0 to 1) on an inventory item, which the save keeps. The natives come from the FalloutCondition F4SE plugin; the rules live in TES4_ConditionPlayer.}

Float Function GetHealth(ObjectReference akHolder, Form akItem) Global Native
{The health of akItem in akHolder (its equipped copy first); -1 when not held or none set yet.}

Bool Function SetHealth(ObjectReference akHolder, Form akItem, Float afHealth) Global Native
{Set akItem's health in akHolder (0 to 1), adding it when it has none; False when not held.}

Float Function GetEquippedWeaponHealth(Actor akActor) Global Native
{The health of akActor's equipped weapon; -1 with none or none set yet.}

Int Function StackCount(ObjectReference akHolder, Form akItem) Global Native
{How many of akItem share the stack its health sits on (they share one condition).}
