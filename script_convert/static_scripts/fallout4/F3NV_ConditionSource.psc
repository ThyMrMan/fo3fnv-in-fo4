ScriptName F3NV_ConditionSource extends Quest Const
{One plugin's FO3/FNV item condition rows, on a start-game quest of that plugin (the game's own condition quest holds the game's). On start it adds itself to Sources, the game's registry of every plugin's rows, which F3NV_ConditionPlayer reads, and gives the F3NV plugin its items; plugins and mods stack in any load order, none overriding another's records. See docs/fork/fo4_condition.md#sources}

Form[] Property Weapons Auto Const
Float[] Property MaxHealth Auto Const
{Each weapon's FNV health, parallel to Weapons.}
Float[] Property JamTimes Auto Const
{Each weapon's FNV reload jam time in seconds, parallel to Weapons; -1 for one that never jams (No Jam After Reload).}
Form[] Property AmmoMarks Auto Const
Float[] Property AmmoWear Auto Const
{The condition wear multiplier of the round whose ammo mod adds AmmoMarks[i].}
Form[] Property WearPerks Auto Const
Float[] Property WearPerkMults Auto Const
Form[] Property Armors Auto Const
Float[] Property ArmorMax Auto Const
Int[] Property ArmorGroup Auto Const
{Armors[i]'s condition mods are ArmorTiers[ArmorGroup[i] * 11 + t].}
Form[] Property ArmorTiers Auto Const
Form[] Property RepairLists Auto Const
{Each item's repair list (a FormList, or None): Weapons' first, then Armors'.}
Int[] Property JuryGroups Auto Const
{Each item's Jury Rigging group, parallel to RepairLists; 0 for none.}
ActorValue Property Repair Auto Const
FormList Property Sources Auto Const
{The game's registry of every plugin's condition rows.}

Event OnQuestInit()
  Register()
EndEvent

Function Register()
  {Be in Sources, and give the plugin these items that wear and their repair lists (it forgets them each game start).}
  If Sources.Find(Self) < 0
    Sources.AddForm(Self)
  EndIf
  CRUI_Condition.Track(Weapons)
  CRUI_Condition.Track(Armors)
  CRUI_Condition.TrackRepair(Weapons, Armors, RepairLists, JuryGroups, Repair)
EndFunction

Float Function WeaponMax(Form akItem)
  {akItem's FNV health when it is one of these weapons; 0 otherwise.}
  Int i = Weapons.Find(akItem)
  If i < 0
    Return 0.0
  EndIf
  Return MaxHealth[i]
EndFunction

Float Function ArmorHealth(Form akItem)
  {akItem's FNV health when it is one of these armors; 0 otherwise.}
  Int i = Armors.Find(akItem)
  If i < 0
    Return 0.0
  EndIf
  Return ArmorMax[i]
EndFunction

Form Function ArmorTier(Form akItem, Int aiTier)
  {The condition mod of tier aiTier for akItem when it is one of these armors; None otherwise.}
  Int i = Armors.Find(akItem)
  If i < 0
    Return None
  EndIf
  Return ArmorTiers[ArmorGroup[i] * 11 + aiTier]
EndFunction

Float Function JamTime(Form akItem)
  {akItem's reload jam time when it is one of these weapons; -1 when it never jams or is not one.}
  Int i = Weapons.Find(akItem)
  If i < 0
    Return -1.0
  EndIf
  Return JamTimes[i]
EndFunction

Float Function WearOf(Actor akPlayer)
  {The wear multiplier these rows give akPlayer's shot: the first loaded round's, times each held wear perk's.}
  Float wear = 1.0
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
