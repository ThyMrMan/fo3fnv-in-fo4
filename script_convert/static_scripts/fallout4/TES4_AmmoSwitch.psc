ScriptName TES4_AmmoSwitch extends Quest Hidden
{FNV's Ammo Type hotkey on Fallout 4. Cycle() loads the equipped gun's next round of its FNV ammo list that the player carries, wrapping around, by attaching that round's ammo mod to the gun (AttachModToInventoryItem, vanilla Papyrus), and shows the round's name. A group is one ammo list: Lists[g] the keyword its guns carry, Rounds/Mods/Loaded/Notes[Starts[g]] to [Starts[g + 1] - 1] its rounds, their mods, the keyword each mod adds (the loaded round) and its notification. The quest gives the player the hotkey item once.}

Form[] Property Lists Auto Const
Int[] Property Starts Auto Const
Form[] Property Rounds Auto Const
Form[] Property Mods Auto Const
Form[] Property Loaded Auto Const
Form[] Property Notes Auto Const
Message Property NoOtherAmmo Auto Const
Message Property SingleAmmo Auto Const
Message Property TwoCopies Auto Const
Potion Property Hotkey Auto Const

Event OnQuestInit()
  Actor player = Game.GetPlayer()
  If player.GetItemCount(Hotkey) == 0
    player.AddItem(Hotkey, 1, True)
  EndIf
EndEvent

Function Cycle()
  {Load the equipped gun's next carried round, or say why not.}
  Actor player = Game.GetPlayer()
  Weapon gun = player.GetEquippedWeapon()
  Int g = ListOf(gun)
  Debug.Trace("TES4AmmoSwitch|" + gun + "|list " + g)
  If g < 0
    SingleAmmo.Show()
    Return
  EndIf
  Int first = Starts[g]
  Int count = Starts[g + 1] - first
  Int now = Current(player, first, count)
  Int step = 1
  While step < count
    Int m = first + (now + step) % count
    If player.GetItemCount(Rounds[m]) > 0
      If player.GetItemCount(gun) > 1
        TwoCopies.Show()
      ElseIf player.AttachModToInventoryItem(gun, Mods[m] as ObjectMod)
        player.EquipItem(Rounds[m], False, True)
        (Notes[m] as Message).Show()
      EndIf
      Return
    EndIf
    step += 1
  EndWhile
  NoOtherAmmo.Show()
EndFunction

Int Function ListOf(Weapon gun)
  {The group of `gun` (the list keyword on its weapon record), or -1; -1 for no gun.}
  If !gun
    Return -1
  EndIf
  Int g = 0
  While g < Lists.Length
    If gun.HasKeyword(Lists[g] as Keyword)
      Return g
    EndIf
    g += 1
  EndWhile
  Return -1
EndFunction

Int Function Current(Actor player, Int first, Int count)
  {Which of a group's rounds the gun holds (its mod's keyword); the first when none says.}
  Int i = 0
  While i < count
    If player.WornHasKeyword(Loaded[first + i] as Keyword)
      Return i
    EndIf
    i += 1
  EndWhile
  Return 0
EndFunction
