ScriptName F3NV_ConditionPlayer extends ReferenceAlias Hidden
{FO3/FNV item condition for the player, on the condition quest's player alias. The items, their FNV health, rounds and perks come from every plugin's rows (F3NV_ConditionSource), registered in Sources. Each shot (weaponFire) or melee swing (HitFrame) wears the equipped weapon by WearPerShot (FNV's fDamageToWeaponValue) times the loaded round's condition effect times each held wear perk, over the weapon's FNV health. Each weapon hit taken wears every worn armor piece by the hit's damage times the share the armor stopped (Absorbed) times ArmorWear (fDamageToArmorPercentage), over its FNV health. An item carries the condition mod of its condition in tenths (FNV's damage, DT and value curves), changed as it crosses a tenth. A weapon at 0 breaks and is unequipped, and a broken weapon cannot be equipped; armor at 0 stays on at half DT. Equipping shows the condition. The player is given the Repair hotkey item once. Seen/SeenTier keep the tier last attached to each item, recorded before attaching: attaching re-equips the item, and that equip must find it done.}

FormList Property Sources Auto Const
{Every plugin's condition rows (F3NV_ConditionSource quests), each added by its quest as it starts.}
Form[] Property Tiers Auto Const
{Eleven weapon condition mods: Tiers[t] for t tenths of condition, Tiers[10] (whole) with no effect.}
Float Property WearPerShot = 0.2 Auto Const
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
Perk Property JuryRigging Auto Const
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
  {Register every plugin's rows again (the plugin forgets their items each game start; the game's own rows are on this quest) and hear the Pip-Boy's repair requests.}
  (GetOwningQuest() as F3NV_ConditionSource).Register()
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ConditionSource rows = Sources.GetAt(k) as F3NV_ConditionSource
    If rows
      rows.Register()
    EndIf
    k += 1
  EndWhile
  F3NV_Condition.SetServiceRules(RepairSkillBase, RepairSkillMax, RepairCostMult)
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
  Form item = F3NV_Condition.PipboySelection()
  Float health = F3NV_Condition.PipboyRepair(GetActorReference())
  Debug.Trace("TES4Condition|Pip-Boy repair|" + item + "|" + health)
  If item && health >= 0.0
    Refresh(item)
  ElseIf item && health < -1.5
    Debug.MessageBox("You don't have enough caps.")
  ElseIf item
    Debug.MessageBox("No spare to repair " + item.GetName() + " with.")
  EndIf
  F3NV_Condition.PipboyRefresh()
EndFunction

Function TellJuryRigging()
  {Tell the plugin whether the player has Jury Rigging (it can be taken at any level-up).}
  F3NV_Condition.SetJuryRigging(JuryRigging && GetActorReference().HasPerk(JuryRigging))
EndFunction

Function RepairFromHotkey()
  {The Repair hotkey: repair the equipped weapon when it is below whole and has a spare, else the worn armor piece in the worst condition that has one.}
  TellJuryRigging()
  Actor player = GetActorReference()
  Form item = player.GetEquippedWeapon()
  If !Repairable(item, -1)
    item = None
    Float lowest = 1.0
    Form[] worn = Worn(player)
    Int k = 0
    While k < worn.Length
      Float health = F3NV_ConditionCalls.Whole(F3NV_Condition.GetHealth(player, worn[k]))
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
  If F3NV_ConditionCalls.Whole(F3NV_Condition.GetStackHealth(player, akItem, aiStack)) >= 1.0
    Debug.Notification(akItem.GetName() + " needs no repair.")
  ElseIf F3NV_ConditionCalls.RepairWithSpare(player, akItem, aiStack)
    Refresh(akItem)
    Int percent = Math.Floor(F3NV_ConditionCalls.Whole(F3NV_Condition.GetStackHealth(player, akItem, aiStack)) * 100.0 + 0.5)
    Debug.Notification(akItem.GetName() + " repaired: " + percent + "%")
  Else
    Debug.Notification("No spare to repair " + akItem.GetName() + " with.")
  EndIf
EndFunction

Bool Function Repairable(Form akItem, Int aiStack)
  {Whether akItem wears, is below whole and the player carries a spare for it.}
  Actor player = GetActorReference()
  If !akItem || (!WeaponSource(akItem) && !ArmorSource(akItem))
    Return False
  EndIf
  If F3NV_ConditionCalls.Whole(F3NV_Condition.GetStackHealth(player, akItem, aiStack)) >= 1.0
    Return False
  EndIf
  Return F3NV_Condition.SpareCount(player, akItem, aiStack) > 0
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
  If gun && WeaponSource(gun)
    Listen()
    Float health = Health(player, gun)
    If health <= 0.0
      Break(player, gun)
      Return
    EndIf
    Refresh(gun)
    Note(gun, health)
    F3NV_Condition.PipboyRefresh()
  ElseIf ArmorSource(akBaseObject)
    Refresh(akBaseObject)
    Note(akBaseObject, Health(player, akBaseObject))
    F3NV_Condition.PipboyRefresh()
  EndIf
EndEvent

Event OnItemUnequipped(Form akBaseObject, ObjectReference akReference)
  {An item that wears coming off: the Pip-Boy redraws its lines' equipped marks.}
  If WeaponSource(akBaseObject) || ArmorSource(akBaseObject)
    F3NV_Condition.PipboyRefresh()
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
  F3NV_ConditionSource rows = WeaponSource(gun)
  If !rows
    Return
  EndIf
  Float health = Health(player, gun) - Wear(player) / rows.WeaponMax(gun)
  If health <= 0.0
    F3NV_Condition.SetHealth(player, gun, 0.0)
    Break(player, gun)
    Return
  EndIf
  F3NV_Condition.SetHealth(player, gun, health)
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
  Form[] worn = Worn(player)
  Int k = 0
  While k < worn.Length
    Float health = Health(player, worn[k]) - wear / ArmorSource(worn[k]).ArmorHealth(worn[k])
    F3NV_Condition.SetHealth(player, worn[k], Math.Max(health, 0.0))
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
  F3NV_ConditionSource rows = ArmorSource(akItem)
  If rows
    Apply(player, akItem, t, rows.ArmorTier(akItem, t))
  ElseIf WeaponSource(akItem)
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
  F3NV_ConditionSource rows = WeaponSource(gun)
  If !rows || rows.JamTime(gun) < 0.0
    Return
  EndIf
  If Utility.RandomFloat(0.0, 1.0) < JamChance(Health(player, gun))
    Jam(player, rows.JamTime(gun))
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
  Float health = F3NV_Condition.GetHealth(akPlayer, akItem)
  If health < 0.0
    health = 1.0
    F3NV_Condition.SetHealth(akPlayer, akItem, health)
  EndIf
  Return health
EndFunction

Float Function Wear(Actor akPlayer)
  {One shot's or swing's wear in health points: every plugin's loaded-round and held-perk multipliers applied.}
  Float wear = WearPerShot
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ConditionSource rows = Sources.GetAt(k) as F3NV_ConditionSource
    If rows
      wear *= rows.WearOf(akPlayer)
    EndIf
    k += 1
  EndWhile
  Return wear
EndFunction

F3NV_ConditionSource Function WeaponSource(Form akItem)
  {The plugin rows holding weapon akItem; None when it does not wear.}
  Int k = 0
  While akItem && k < Sources.GetSize()
    F3NV_ConditionSource rows = Sources.GetAt(k) as F3NV_ConditionSource
    If rows && rows.Weapons.Find(akItem) >= 0
      Return rows
    EndIf
    k += 1
  EndWhile
  Return None
EndFunction

F3NV_ConditionSource Function ArmorSource(Form akItem)
  {The plugin rows holding armor akItem; None when it does not wear.}
  Int k = 0
  While akItem && k < Sources.GetSize()
    F3NV_ConditionSource rows = Sources.GetAt(k) as F3NV_ConditionSource
    If rows && rows.Armors.Find(akItem) >= 0
      Return rows
    EndIf
    k += 1
  EndWhile
  Return None
EndFunction

Form[] Function Worn(Actor akPlayer)
  {The armor akPlayer wears that wears out, from every plugin's rows.}
  Form[] out = new Form[0]
  Int k = 0
  While k < Sources.GetSize()
    F3NV_ConditionSource rows = Sources.GetAt(k) as F3NV_ConditionSource
    If rows
      Form[] worn = F3NV_ConditionCalls.WornOf(akPlayer, rows.Armors)
      Int j = 0
      While j < worn.Length
        If out.Find(worn[j]) < 0
          out.Add(worn[j])
        EndIf
        j += 1
      EndWhile
    EndIf
    k += 1
  EndWhile
  Return out
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
