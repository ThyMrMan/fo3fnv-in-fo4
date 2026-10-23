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

Float Function GetStackHealth(ObjectReference akHolder, Form akItem, Int aiStack) Global Native
{GetHealth on stack aiStack of akItem (-1, or a stack it lacks: its equipped copy, else its first).}

Bool Function SetStackHealth(ObjectReference akHolder, Form akItem, Int aiStack, Float afHealth) Global Native
{SetHealth on stack aiStack of akItem, chosen as GetStackHealth chooses it.}

Function Track(Form[] akItems) Global Native
{akItems wear: the Pip-Boy shows their condition (CND) on the item card.}

Form Function PipboySelection() Global Native
{The item highlighted in the Pip-Boy's inventory when it wears; None otherwise.}

Int Function PipboyStack() Global Native
{The stack index of PipboySelection's item; -1 with none.}

Function PipboyRefresh() Global Native
{Show the highlighted item's condition again on the Pip-Boy's item card (after a repair).}

Function TrackRepair(Form[] akWeapons, Form[] akArmors, Form[] akRepairLists, ActorValue akRepair) Global Native
{The FNV repair lists (akRepairLists: akWeapons' first, then akArmors'; a FormList or None each) and the Repair skill, for repair and the Pip-Boy's repair list.}

Float Function RepairWith(Actor akHolder, Form akItem, Int aiStack, Form akSpare, Int aiSpareStack) Global Native
{Repair stack aiStack of akItem (-1: its equipped, else first) from one copy of akSpare's stack aiSpareStack (-1: its worst), by FNV's rule, using that copy up: the new health (0 to 1), or -1 with no such spare.}

Float Function PipboyRepair(Actor akHolder) Global Native
{Carry out the repair chosen in the Pip-Boy's repair list (on PipboySelection's item): the new health, or -1 with none chosen.}
