ScriptName TES4_ConditionPlayer extends ReferenceAlias Hidden
{FO3/FNV item condition for the player, on the condition quest's player alias. Each shot (weaponFire) or melee swing (HitFrame) wears the equipped weapon by WearPerShot (FNV's fDamageToWeaponValue) times the loaded round's condition effect (AmmoWear, its AmmoMarks keyword on the gun) times each held wear perk (WearPerkMults), over the weapon's FNV health (MaxHealth[i] for Weapons[i]). Each weapon hit taken wears every worn armor piece by the hit's damage times the share the armor stopped (Absorbed) times ArmorWear (fDamageToArmorPercentage), over its FNV health (ArmorMax). An item carries the condition mod of its condition in tenths (FNV's damage, DT and value curves), changed as it crosses a tenth. A weapon at 0 breaks and is unequipped, and a broken weapon cannot be equipped; armor at 0 stays on at half DT. Equipping shows the condition. The player is given the Repair hotkey item once. Seen/SeenTier keep the tier last attached to each item, recorded before attaching: attaching re-equips the item, and that equip must find it done.}

Form[] Property Weapons Auto Const
Float[] Property MaxHealth Auto Const
Form[] Property Tiers Auto Const
{Eleven weapon condition mods: Tiers[t] for t tenths of condition, Tiers[10] (whole) with no effect.}
Float Property WearPerShot = 0.2 Auto Const
Form[] Property AmmoMarks Auto Const
Float[] Property AmmoWear Auto Const
Form[] Property WearPerks Auto Const
Float[] Property WearPerkMults Auto Const
Form[] Property Armors Auto Const
Float[] Property ArmorMax Auto Const
Int[] Property ArmorGroup Auto Const
{Armors[i]'s condition mods are ArmorTiers[ArmorGroup[i] * 11 + t].}
Form[] Property ArmorTiers Auto Const
Float Property ArmorWear = 0.35 Auto Const
Float Property MaxAbsorb = 0.85 Auto Const
{The largest share of a hit armor wears for (FNV's fMaxArmorRating, as a fraction).}
Float Property PhysicalFactor = 0.15 Auto Const
{Fallout 4's fPhysicalDamageFactor, in its armor formula.}
ActorValue Property DamageResist Auto Const
Message Property ConditionNote Auto Const
{"Condition %.0f%%".}
Message Property BrokenNote Auto Const
Potion Property RepairHotkey Auto Const
{The Repair hotkey item, given once.}
Form[] Property RepairLists Auto Const
{Each item's repair list (a FormList, or None): Weapons' first, then Armors'.}
ActorValue Property Repair Auto Const
Int[] Property JuryGroups Auto Const
{Each item's Jury Rigging group (FNV's weapon animation type and skill, armor weight class and equipment type), parallel to RepairLists; 0 for none.}
Perk Property JuryRigging Auto Const
Float[] Property JamTimes Auto Const
{Each weapon's FNV reload jam time in seconds, parallel to Weapons; -1 for one that never jams (No Jam After Reload).}
Float[] Property JamChances Auto Const
{FNV's reload jam chance by condition index (fWeaponConditionReloadJam1..10).}
Idle Property JamInterrupt1st Auto Const
Idle Property JamInterrupt3rd Auto Const
Idle Property JamReload1st Auto Const
Idle Property JamReload3rd Auto Const
Sound Property DryFire Auto Const
{FNV's Jury Rigging: while held, a spare of the item's group repairs it too.}
Float Property RepairSkillBase = 4.0 Auto Const
Float Property RepairSkillMax = 10.0 Auto Const
Float Property RepairCostMult = 2.0 Auto Const
{FNV's vendor repair: fRepairSkillBase, fRepairSkillMax (tenths of condition at Repair 0 and 100), fItemRepairCostMult.}
Int Property RepairKey = 34 Auto Const
{G: repairs the item highlighted in the Pip-Boy (its REPAIR button hint). The Pip-Boy's T is Grid View.}

Form[] Seen
Int[] SeenTier
Form[] Pending
Float RepairedAt
Bool JamClearing
Form Noted
Float NotedAt

Event OnAliasInit()
  Listen()
  ListenHits()
  ListenPipboy()
  If GetActorReference().GetItemCount(RepairHotkey) == 0
    GetActorReference().AddItem(RepairHotkey, 1, True)
  EndIf
EndEvent

Event OnPlayerLoadGame()
  Listen()
  UnregisterForHitEvent(GetReference())
  ListenHits()
  ListenPipboy()
EndEvent

Function ListenPipboy()
  {Give the plugin the items that wear (it forgets them each game start) and hear the Pip-Boy's repair requests.}
  TES4_Condition.Track(Weapons)
  TES4_Condition.Track(Armors)
  TES4_Condition.TrackRepair(Weapons, Armors, RepairLists, JuryGroups, Repair)
  TES4_Condition.SetServiceRules(RepairSkillBase, RepairSkillMax, RepairCostMult)
  TellJuryRigging()
  RegisterForMenuOpenCloseEvent("PipboyMenu")
  RegisterForExternalEvent("FNVConditionRepair", "OnPipboyRepair")
EndFunction

Event OnMenuOpenCloseEvent(String asMenuName, Bool abOpening)
  Debug.Trace("TES4Condition|menu|" + asMenuName + "|" + abOpening)
  If abOpening
    TellJuryRigging()
    ApplyPending()
    RegisterForKey(RepairKey)
  Else
    UnregisterForKey(RepairKey)
  EndIf
EndEvent

Event OnKeyDown(Int aiKeyCode)
  Debug.Trace("TES4Condition|key|" + aiKeyCode + "|Pip-Boy open " + UI.IsMenuOpen("PipboyMenu"))
  If UI.IsMenuOpen("PipboyMenu")
    OnPipboyRepair()
  EndIf
EndEvent

Function OnPipboyRepair()
  {Carry out the repair chosen in the Pip-Boy's repair list (the plugin sends FNVConditionRepair as it is confirmed), then show the item's new condition there; a second request within 0.3 s is the same press.}
  Float now = Utility.GetCurrentRealTime()
  If now >= RepairedAt && now - RepairedAt < 0.3
    Return
  EndIf
  RepairedAt = now
  Form item = TES4_Condition.PipboySelection()
  Float health = TES4_Condition.PipboyRepair(GetActorReference())
  Debug.Trace("TES4Condition|Pip-Boy repair|" + item + "|" + health)
  If item && health >= 0.0
    Refresh(item)
  ElseIf item && health < -1.5
    Debug.MessageBox("You don't have enough caps.")
  ElseIf item
    Debug.MessageBox("No spare to repair " + item.GetName() + " with.")
  EndIf
  TES4_Condition.PipboyRefresh()
EndFunction

Function TellJuryRigging()
  {Tell the plugin whether the player has Jury Rigging (it can be taken at any level-up).}
  TES4_Condition.SetJuryRigging(JuryRigging && GetActorReference().HasPerk(JuryRigging))
EndFunction

Function RepairFromHotkey()
  {The Repair hotkey: repair the equipped weapon when it is below whole and has a spare, else the worn armor piece in the worst condition that has one.}
  TellJuryRigging()
  Actor player = GetActorReference()
  Form item = player.GetEquippedWeapon()
  If !Repairable(item, -1)
    item = None
    Float lowest = 1.0
    Form[] worn = TES4_ConditionCalls.WornOf(player, Armors)
    Int k = 0
    While k < worn.Length
      Float health = TES4_ConditionCalls.Whole(TES4_Condition.GetHealth(player, worn[k]))
      If health < lowest && Repairable(worn[k], -1)
        item = worn[k]
        lowest = health
      EndIf
      k += 1
    EndWhile
  EndIf
  If item
    RepairItem(item, -1)
  Else
    Debug.Notification("Nothing worn needs repair, or there is no spare to repair it with.")
  EndIf
EndFunction

Function RepairItem(Form akItem, Int aiStack)
  {Repair stack aiStack of akItem from a spare and put its condition mod on, naming the result (the Repair hotkey).}
  Actor player = GetActorReference()
  If TES4_ConditionCalls.Whole(TES4_Condition.GetStackHealth(player, akItem, aiStack)) >= 1.0
    Debug.Notification(akItem.GetName() + " needs no repair.")
  ElseIf TES4_ConditionCalls.RepairWithSpare(player, akItem, aiStack)
    Refresh(akItem)
    Int percent = Math.Floor(TES4_ConditionCalls.Whole(TES4_Condition.GetStackHealth(player, akItem, aiStack)) * 100.0 + 0.5)
    Debug.Notification(akItem.GetName() + " repaired: " + percent + "%")
  Else
    Debug.Notification("No spare to repair " + akItem.GetName() + " with.")
  EndIf
EndFunction

Bool Function Repairable(Form akItem, Int aiStack)
  {Whether akItem wears, is below whole and the player carries a spare for it.}
  Actor player = GetActorReference()
  If !akItem || (Weapons.Find(akItem) < 0 && Armors.Find(akItem) < 0)
    Return False
  EndIf
  If TES4_ConditionCalls.Whole(TES4_Condition.GetStackHealth(player, akItem, aiStack)) >= 1.0
    Return False
  EndIf
  Return TES4_Condition.SpareCount(player, akItem, aiStack) > 0
EndFunction

Function Listen()
  {Hear the player's shots and swings; it fails while the player's 3D is not loaded, so equipping retries.}
  RegisterForAnimationEvent(GetReference(), "weaponFire")
  RegisterForAnimationEvent(GetReference(), "HitFrame")
  RegisterForAnimationEvent(GetReference(), "weaponSheathe")
  RegisterForAnimationEvent(GetReference(), "reloadStateExit")
  RegisterForAnimationEvent(GetReference(), "reloadStateEnter")
EndFunction

Function ListenHits()
  {Hear the next hit the player takes (a hit registration serves one hit).}
  RegisterForHitEvent(GetReference())
EndFunction

Event OnItemEquipped(Form akBaseObject, ObjectReference akReference)
  Actor player = GetActorReference()
  Weapon gun = akBaseObject as Weapon
  If gun && Weapons.Find(gun) >= 0
    Listen()
    Float health = Health(player, gun)
    If health <= 0.0
      Break(player, gun)
      Return
    EndIf
    Refresh(gun)
    Note(gun, health)
    TES4_Condition.PipboyRefresh()
  ElseIf Armors.Find(akBaseObject) >= 0
    Refresh(akBaseObject)
    Note(akBaseObject, Health(player, akBaseObject))
    TES4_Condition.PipboyRefresh()
  EndIf
EndEvent

Event OnItemUnequipped(Form akBaseObject, ObjectReference akReference)
  {An item that wears coming off: the Pip-Boy redraws its lines' equipped marks.}
  If Weapons.Find(akBaseObject) >= 0 || Armors.Find(akBaseObject) >= 0
    TES4_Condition.PipboyRefresh()
  EndIf
EndEvent

Event OnAnimationEvent(ObjectReference akSource, String asEventName)
  If asEventName == "weaponSheathe" || asEventName == "reloadStateExit"
    ApplyPending()
    Return
  ElseIf asEventName == "reloadStateEnter"
    Reloading()
    Return
  EndIf
  Actor player = GetActorReference()
  Weapon gun = player.GetEquippedWeapon()
  Int i = Weapons.Find(gun)
  If !gun || i < 0
    Return
  EndIf
  Float health = Health(player, gun) - Wear(player) / MaxHealth[i]
  If health <= 0.0
    TES4_Condition.SetHealth(player, gun, 0.0)
    Break(player, gun)
    Return
  EndIf
  TES4_Condition.SetHealth(player, gun, health)
  Refresh(gun, False)
EndEvent

Event OnHit(ObjectReference akTarget, ObjectReference akAggressor, Form akSource, Projectile akProjectile, Bool abPowerAttack, Bool abSneakAttack, Bool abBashAttack, Bool abHitBlocked, String apMaterial)
  ListenHits()
  Float damage = HitDamage(akAggressor as Actor, akSource as Weapon)
  If damage <= 0.0
    Return
  EndIf
  Actor player = GetActorReference()
  Float wear = damage * Absorbed(damage, player.GetValue(DamageResist)) * ArmorWear
  Form[] worn = TES4_ConditionCalls.WornOf(player, Armors)
  Int k = 0
  While k < worn.Length
    Float health = Health(player, worn[k]) - wear / ArmorMax[Armors.Find(worn[k])]
    TES4_Condition.SetHealth(player, worn[k], Math.Max(health, 0.0))
    Refresh(worn[k], False)
    k += 1
  EndWhile
EndEvent

Float Function HitDamage(Actor akAttacker, Weapon akWeapon)
  {The damage of a hit by akAttacker's akWeapon: its equipped instance's (with its mods), else the weapon's own; 0 for anything else.}
  If !akWeapon
    Return 0.0
  EndIf
  Int damage = 0
  If akAttacker
    damage = InstanceData.GetAttackDamage(akAttacker.GetInstanceOwner(32 + akAttacker.GetEquippedItemType(0)))
  EndIf
  If damage <= 0
    InstanceData:Owner base = new InstanceData:Owner
    base.owner = akWeapon
    damage = InstanceData.GetAttackDamage(base)
  EndIf
  Return damage as Float
EndFunction

Float Function Absorbed(Float afDamage, Float afResist)
  {The share of afDamage armor of afResist stops, by Fallout 4's armor formula, up to MaxAbsorb.}
  If afResist <= 0.0
    Return 0.0
  EndIf
  Float taken = Math.Pow(afDamage * PhysicalFactor / afResist, 0.365)
  taken = Math.Max(0.01, Math.Min(taken, 0.99))
  Return Math.Min(1.0 - taken, MaxAbsorb)
EndFunction

Function Refresh(Form akItem, Bool abNow = True)
  {Give the player's akItem the condition mod of its condition (after wear, repair or equipping). Attaching re-equips the item, so wear (abNow False) only marks it Pending, put on at a quiet moment: holstering, the end of a reload, opening the Pip-Boy, or equipping. From 90% up an item takes no mod (whole), so the first shots attach nothing.}
  Actor player = GetActorReference()
  Int t = Math.Floor(Health(player, akItem) * 10.0)
  If t >= 9
    t = 10
  EndIf
  If !abNow
    If TierOf(akItem) != t && (!Pending || Pending.Find(akItem) < 0)
      If !Pending
        Pending = new Form[0]
      EndIf
      Pending.Add(akItem)
    EndIf
    Return
  EndIf
  Int i = Armors.Find(akItem)
  If i >= 0
    Apply(player, akItem, t, ArmorTiers[ArmorGroup[i] * 11 + t])
  ElseIf Weapons.Find(akItem) >= 0
    Apply(player, akItem, t, Tiers[t])
  EndIf
EndFunction

Function ApplyPending()
  {Put on the condition mods wear has changed since the last quiet moment.}
  If !Pending || Pending.Length == 0
    Return
  EndIf
  Form[] items = Pending
  Pending = new Form[0]
  Int k = 0
  While k < items.Length
    If GetActorReference().GetItemCount(items[k]) > 0
      Refresh(items[k])
    EndIf
    k += 1
  EndWhile
EndFunction

Function Reloading()
  {A reload began: roll FNV's reload jam for the equipped weapon (not the reload that clears a jam).}
  If JamClearing
    JamClearing = False
    Return
  EndIf
  Actor player = GetActorReference()
  Weapon gun = player.GetEquippedWeapon()
  Int i = Weapons.Find(gun)
  If !gun || i < 0 || JamTimes[i] < 0.0
    Return
  EndIf
  If Utility.RandomFloat(0.0, 1.0) < JamChance(Health(player, gun))
    Jam(player, JamTimes[i])
  EndIf
EndFunction

Float Function JamChance(Float afHealth)
  {FNV's reload jam chance at condition afHealth: index ceil(percent / 10), less one above 1, into JamChances (index 0 is the first).}
  Int i = Math.Ceiling(afHealth * 10.0)
  If i > 1
    i -= 1
  EndIf
  If i >= JamChances.Length
    Return 0.0
  EndIf
  Return JamChances[i]
EndFunction

Function Jam(Actor akPlayer, Float afTime)
  {Jam the reload: stop it with the hand-interrupt idle, click the dry fire, then reload again after afTime seconds (FNV's jam time).}
  Bool first = akPlayer.GetAnimationVariableBool("IsFirstPerson")
  If first
    akPlayer.PlayIdle(JamInterrupt1st)
  Else
    akPlayer.PlayIdle(JamInterrupt3rd)
  EndIf
  DryFire.Play(akPlayer)
  Debug.Notification("Your weapon jammed.")
  Utility.Wait(Math.Max(afTime, 0.5))
  DryFire.Play(akPlayer)
  JamClearing = True
  If first
    akPlayer.PlayIdle(JamReload1st)
  Else
    akPlayer.PlayIdle(JamReload3rd)
  EndIf
EndFunction

Int Function TierOf(Form akItem)
  {The condition tier last attached to akItem; 10 (whole) for one never given a mod.}
  If !Seen || Seen.Find(akItem) < 0
    Return 10
  EndIf
  Return SeenTier[Seen.Find(akItem)]
EndFunction

Float Function Health(Actor akPlayer, Form akItem)
  {akItem's condition, set whole (1) the first time it has none.}
  Float health = TES4_Condition.GetHealth(akPlayer, akItem)
  If health < 0.0
    health = 1.0
    TES4_Condition.SetHealth(akPlayer, akItem, health)
  EndIf
  Return health
EndFunction

Float Function Wear(Actor akPlayer)
  {One shot's or swing's wear in health points: the loaded round's and the held perks' multipliers applied.}
  Float wear = WearPerShot
  Int i = 0
  While i < AmmoMarks.Length
    If akPlayer.WornHasKeyword(AmmoMarks[i] as Keyword)
      wear *= AmmoWear[i]
      i = AmmoMarks.Length
    EndIf
    i += 1
  EndWhile
  i = 0
  While i < WearPerks.Length
    If akPlayer.HasPerk(WearPerks[i] as Perk)
      wear *= WearPerkMults[i]
    EndIf
    i += 1
  EndWhile
  Return wear
EndFunction

Function Apply(Actor akPlayer, Form akItem, Int aiTier, Form akMod)
  {Attach condition mod akMod (tier aiTier) to akItem when that tier differs from the one last attached; an item never worn needs none.}
  If !Seen
    Seen = new Form[0]
    SeenTier = new Int[0]
  EndIf
  Int i = Seen.Find(akItem)
  If i < 0
    Seen.Add(akItem)
    SeenTier.Add(10)
    i = Seen.Length - 1
  EndIf
  If SeenTier[i] == aiTier
    Return
  EndIf
  SeenTier[i] = aiTier
  akPlayer.AttachModToInventoryItem(akItem, akMod as ObjectMod)
EndFunction

Function Note(Form akItem, Float afHealth)
  {Show akItem's condition, once per equip: attaching re-equips it within moments.}
  Float now = Utility.GetCurrentRealTime()
  If akItem != Noted || now - NotedAt > 2.0
    ConditionNote.Show(afHealth * 100.0)
  EndIf
  Noted = akItem
  NotedAt = now
EndFunction

Function Break(Actor akPlayer, Weapon akGun)
  {A weapon at no condition: unequipped, with FNV's broken message.}
  akPlayer.UnequipItem(akGun, False, True)
  BrokenNote.Show()
EndFunction
