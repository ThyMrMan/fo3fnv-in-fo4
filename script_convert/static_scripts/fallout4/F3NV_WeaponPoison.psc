ScriptName F3NV_WeaponPoison extends ActiveMagicEffect
{FO3/FNV weapon poison: using it coats the equipped melee or unarmed weapon (FNV's Melee Weapons or Unarmed skill, its keyword) for one hit, as FNV's Pip-Boy does, by giving the poison's coat perk; with no such weapon, or a coat already on, FNV's message shows and the item comes back.
See: docs/fork/fo4_pipeline.md#weapon-poisons}

Perk Property Coat Auto Const
{The hidden perk casting this poison on the next hit (F3NV_PoisonSpent removes it).}
FormList Property Coats Auto Const
{Every poison's coat perk: one coat at a time.}
Potion Property Poison Auto Const
{The poison item, given back when refused.}
Keyword[] Property Poisonable Auto Const
{The FNV skill keywords of a weapon FNV lets the player poison.}
String Property NoWeapon Auto Const
{FNV's sPoisonNoWeaponMessage.}
String Property Already Auto Const
{FNV's sPoisonAlreadyPoisonedMessage.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If !Takes(akTarget.GetEquippedWeapon())
    Refuse(akTarget, NoWeapon)
  ElseIf Coated(akTarget)
    Refuse(akTarget, Already)
  Else
    akTarget.AddPerk(Coat)
  EndIf
EndEvent

Bool Function Takes(Weapon akWeapon)
  {Whether akWeapon carries one of the Poisonable keywords.}
  Int i = 0
  While akWeapon && i < Poisonable.Length
    If akWeapon.HasKeyword(Poisonable[i])
      Return True
    EndIf
    i += 1
  EndWhile
  Return False
EndFunction

Bool Function Coated(Actor akActor)
  {Whether akActor already holds a poison's coat perk.}
  Int i = 0
  While i < Coats.GetSize()
    If akActor.HasPerk(Coats.GetAt(i) as Perk)
      Return True
    EndIf
    i += 1
  EndWhile
  Return False
EndFunction

Function Refuse(Actor akActor, String asMessage)
  {Show asMessage and give the poison back, as FNV leaves it unused.}
  Debug.MessageBox(asMessage)
  akActor.AddItem(Poison, 1, True)
EndFunction
