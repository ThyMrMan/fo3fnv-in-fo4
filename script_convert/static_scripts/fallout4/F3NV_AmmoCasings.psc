ScriptName F3NV_AmmoCasings extends ReferenceAlias Hidden
{FNV's casings, on the player alias of the plugin's ammo casings quest. Each AmmoList entry leaves Casings[i] at Chances[i] percent per round fired. A group is a gun's ammo list: Defaults[g] its first ammo (the gun's base ammo), Members[Starts[g]] to Members[Starts[g + 1] - 1] its entries, Perks[g] (when held) multiplying its chance by PerkMults[g]. On weaponFire the equipped gun's group is noted; once firing pauses, each entry's drop in count is the rounds fired. Ammo the player gains, drops or hands over moves the counts too.}

FormList Property AmmoList Auto Const
Form[] Property Casings Auto Const
Float[] Property Chances Auto Const
Form[] Property Defaults Auto Const
Int[] Property Starts Auto Const
Int[] Property Members Auto Const
Form[] Property Perks Auto Const
Float[] Property PerkMults Auto Const

Float Property SettleSeconds = 0.5 Auto Const
{How long after the last shot a group's counts are read.}

Int[] Counts
Int Pending = -1
Weapon Unlisted

Event OnAliasInit()
  Setup()
EndEvent

Event OnPlayerLoadGame()
  Setup()
EndEvent

Function Setup()
  {Listen for shots and for the ammo moving, and read every entry's count.}
  ObjectReference player = GetReference()
  Listen()
  RemoveAllInventoryEventFilters()
  AddInventoryEventFilter(AmmoList)
  Int n = AmmoList.GetSize()
  Counts = new Int[n]
  Int i = 0
  While i < n
    Counts[i] = player.GetItemCount(AmmoList.GetAt(i))
    i += 1
  EndWhile
  Pending = -1
  Debug.Trace("TES4Casings|setup|" + player + "|" + n + " ammo|" + Defaults.Length + " groups")
EndFunction

Function Listen()
  {Register for the player's weaponFire; it fails while the player's 3D is not loaded, so equipping a weapon retries.}
  Bool registered = RegisterForAnimationEvent(GetReference(), "weaponFire")
  Debug.Trace("TES4Casings|listen|" + registered)
  TES4Polyfill.TraceAnimEvents(Self, GetReference())
EndFunction

Event OnItemEquipped(Form akBaseObject, ObjectReference akReference)
  If akBaseObject as Weapon
    Listen()
  EndIf
EndEvent

Event OnAnimationEvent(ObjectReference akSource, string asEventName)
  TES4Polyfill.TraceAnim(akSource, asEventName)
  If asEventName != "weaponFire"
    Return
  EndIf
  Weapon gun = GetActorReference().GetEquippedWeapon()
  If !gun
    Return
  EndIf
  Int g = Defaults.Find(gun.GetAmmo())
  If g < 0
    If gun != Unlisted
      Unlisted = gun
      Debug.Trace("TES4Casings|unlisted|" + gun + "|" + gun.GetAmmo())
    EndIf
    Return
  EndIf
  If Pending >= 0 && Pending != g
    Collect(Pending)
  EndIf
  Pending = g
  StartTimer(SettleSeconds)
EndEvent

Event OnTimer(Int aiTimerID)
  If Pending >= 0
    Int g = Pending
    Pending = -1
    Collect(g)
  EndIf
EndEvent

Function Collect(Int g)
  {Give group g's casings for the rounds fired since its counts were last read.}
  Actor player = GetActorReference()
  Float mult = 1.0
  Perk bonus = Perks[g] as Perk
  If bonus && player.HasPerk(bonus)
    mult = PerkMults[g]
  EndIf
  Int m = Starts[g]
  While m < Starts[g + 1]
    Int i = Members[m]
    Int now = player.GetItemCount(AmmoList.GetAt(i))
    Int fired = Counts[i] - now
    Debug.Trace("TES4Casings|collect|" + AmmoList.GetAt(i) + "|was " + Counts[i] + "|now " + now)
    Counts[i] = now
    Int made = 0
    While fired > 0
      If Utility.RandomFloat(0.0, 100.0) < Chances[i] * mult
        made += 1
      EndIf
      fired -= 1
    EndWhile
    If made > 0
      player.AddItem(Casings[i], made, True)
    EndIf
    m += 1
  EndWhile
EndFunction

Event OnItemAdded(Form akBaseItem, Int aiItemCount, ObjectReference akItemReference, ObjectReference akSourceContainer)
  Int i = AmmoList.Find(akBaseItem)
  If i >= 0 && Counts
    Counts[i] = Counts[i] + aiItemCount
  EndIf
EndEvent

Event OnItemRemoved(Form akBaseItem, Int aiItemCount, ObjectReference akItemReference, ObjectReference akDestContainer)
  {Ammo dropped, handed over or used in a menu (crafting) is not fired; ammo used up in play (fired) is left for Collect.}
  Int i = AmmoList.Find(akBaseItem)
  If i >= 0 && Counts && (akDestContainer || akItemReference || Utility.IsInMenuMode())
    Counts[i] = Counts[i] - aiItemCount
  EndIf
EndEvent
