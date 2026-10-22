ScriptName TES4_ConditionPlayer extends ReferenceAlias Hidden
{FO3/FNV weapon condition for the player, on the condition quest's player alias. Each shot (weaponFire) or melee swing (HitFrame) wears the equipped weapon by WearPerShot (FNV's fDamageToWeaponValue) times the loaded round's condition effect (AmmoWear, its AmmoMarks keyword on the gun) times each held wear perk (WearPerkMults), over the weapon's FNV health (MaxHealth[i] for Weapons[i]). The weapon carries Tiers[t] for its condition t tenths (FNV's damage and value curves), changed as it crosses a tenth; at 0 it breaks and is unequipped, and a broken weapon cannot be equipped. Equipping shows the condition. The player is given the Repair hotkey item once. Seen/SeenTier keep the tier last attached to each weapon, recorded before attaching: attaching re-equips the weapon, and that equip must find it done.}

Form[] Property Weapons Auto Const
Float[] Property MaxHealth Auto Const
Form[] Property Tiers Auto Const
{Eleven condition mods: Tiers[t] for t tenths of condition, Tiers[10] (whole) with no effect.}
Float Property WearPerShot = 0.2 Auto Const
Form[] Property AmmoMarks Auto Const
Float[] Property AmmoWear Auto Const
Form[] Property WearPerks Auto Const
Float[] Property WearPerkMults Auto Const
Message Property ConditionNote Auto Const
{"Condition %.0f%%".}
Message Property BrokenNote Auto Const
Potion Property RepairHotkey Auto Const
{The Repair hotkey item, given once.}

Form[] Seen
Int[] SeenTier
Form Noted
Float NotedAt

Event OnAliasInit()
  Listen()
  If GetActorReference().GetItemCount(RepairHotkey) == 0
    GetActorReference().AddItem(RepairHotkey, 1, True)
  EndIf
EndEvent

Event OnPlayerLoadGame()
  Listen()
EndEvent

Function Listen()
  {Hear the player's shots and swings; it fails while the player's 3D is not loaded, so equipping retries.}
  RegisterForAnimationEvent(GetReference(), "weaponFire")
  RegisterForAnimationEvent(GetReference(), "HitFrame")
EndFunction

Event OnItemEquipped(Form akBaseObject, ObjectReference akReference)
  Weapon gun = akBaseObject as Weapon
  If !gun || Weapons.Find(gun) < 0
    Return
  EndIf
  Listen()
  Actor player = GetActorReference()
  Float health = Health(player, gun)
  If health <= 0.0
    Break(player, gun)
    Return
  EndIf
  Apply(player, gun, health)
  Float now = Utility.GetCurrentRealTime()
  If gun != Noted || now - NotedAt > 2.0
    ConditionNote.Show(health * 100.0)
  EndIf
  Noted = gun
  NotedAt = now
EndEvent

Event OnAnimationEvent(ObjectReference akSource, String asEventName)
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
  Apply(player, gun, health)
EndEvent

Float Function Health(Actor akPlayer, Weapon akGun)
  {akGun's condition, set whole (1) the first time it has none.}
  Float health = TES4_Condition.GetHealth(akPlayer, akGun)
  If health < 0.0
    health = 1.0
    TES4_Condition.SetHealth(akPlayer, akGun, health)
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

Function Apply(Actor akPlayer, Weapon akGun, Float afHealth)
  {Give akGun the condition mod of its tenth when that differs from the one last attached; a weapon never worn
  needs none.}
  Int t = Math.Floor(afHealth * 10.0)
  If t > 10
    t = 10
  EndIf
  If !Seen
    Seen = new Form[0]
    SeenTier = new Int[0]
  EndIf
  Int i = Seen.Find(akGun)
  If i < 0
    Seen.Add(akGun)
    SeenTier.Add(10)
    i = Seen.Length - 1
  EndIf
  If SeenTier[i] == t
    Return
  EndIf
  SeenTier[i] = t
  akPlayer.AttachModToInventoryItem(akGun, Tiers[t] as ObjectMod)
EndFunction

Function Break(Actor akPlayer, Weapon akGun)
  {A weapon at no condition: unequipped, with FNV's broken message.}
  akPlayer.UnequipItem(akGun, False, True)
  BrokenNote.Show()
EndFunction
