ScriptName F3NV_Condition Native Hidden
{FO3/FNV item condition: the engine's own item health (0 to 1) on an inventory item, which the save keeps. The natives come from the F3NV F4SE plugin; the rules live in F3NV_ConditionPlayer.}

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

Function TrackRepair(Form[] akWeapons, Form[] akArmors, Form[] akRepairLists, Int[] aiJuryGroups, ActorValue akRepair) Global Native
{The FNV repair lists (akRepairLists: akWeapons' first, then akArmors'; a FormList or None each), the Jury Rigging groups (parallel; 0 for none) and the Repair skill, for repair and the Pip-Boy's repair list.}

Function SetJuryRigging(Bool abHas) Global Native
{Whether the player has Jury Rigging: a spare of the item's Jury Rigging group repairs it too.}

Float Function RepairWith(Actor akHolder, Form akItem, Int aiStack, Form akSpare, Int aiSpareStack) Global Native
{Repair stack aiStack of akItem (-1: its equipped, else first) from one copy of akSpare's stack aiSpareStack (-1: its worst; akSpare None: the default spare, the worst that still gives the best result), by FNV's rule, using that copy up: the new health (0 to 1), or -1 with no such spare.}

Int Function SpareCount(Actor akHolder, Form akItem, Int aiStack) Global Native
{How many spare stacks akHolder carries for stack aiStack of akItem (the same item, its repair list, and its Jury Rigging group while the player has the perk).}

Float Function PipboyRepair(Actor akHolder) Global Native
{Carry out the repair chosen in the Pip-Boy's repair list or vendor offer (on PipboySelection's item), paying the vendor's price: the new health, -1 with none chosen, -2 short of caps.}

Function SetVendor(Actor akVendor) Global Native
{Offer akVendor's repair services (FNV's ShowRepairMenu) on the Pip-Boy's repair card (G) until the Pip-Boy closes: the condition its Repair skill reaches, for caps. None stops.}

Function SetServiceRules(Float afSkillBase, Float afSkillMax, Float afCostMult) Global Native
{FNV's vendor repair GMSTs: fRepairSkillBase and fRepairSkillMax (the condition reached in tenths at Repair 0 and 100) and fItemRepairCostMult.}
