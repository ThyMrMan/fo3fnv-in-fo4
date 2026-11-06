ScriptName F3NV_AmmoSwitch extends Quest Hidden
{FNV's Ammo Type hotkey on Fallout 4. Cycle() loads the equipped gun's next round of its FNV ammo list that the player carries, wrapping around, by attaching that round's ammo mod to the gun (AttachModToInventoryItem, vanilla Papyrus), and shows the round's name. The lists come from every plugin's rows (F3NV_AmmoSwitchSource, the game's on this quest), registered in Sources; Gather() merges them by list keyword into Lists/Starts/Rounds/Mods/Loaded/Notes (a group g's rounds are Rounds[Starts[g]] to [Starts[g + 1] - 1]) at start, on each game load and when a plugin registers. The quest gives the player the hotkey item once, and hands the lists to the F3NV plugin for the Pip-Boy's ammo list (F3NV_PipboyAmmo), whose choice it loads. See docs/fork/fo4_pipeline.md#ammo-switch-sources}

FormList Property Sources Auto Const
{Every plugin's ammo lists (F3NV_AmmoSwitchSource quests), each added by its quest as it starts.}
Message Property NoOtherAmmo Auto Const
Message Property SingleAmmo Auto Const
Message Property TwoCopies Auto Const
Potion Property Hotkey Auto Const
Int Property MaxRounds = 128 AutoReadOnly
{The most rounds a script array holds; rounds past it are left out of the hotkey, logged.}

Form[] Lists
Int[] Starts
Form[] Rounds
Form[] Mods
Form[] Loaded
Form[] Notes

Event OnQuestInit()
  Actor player = Game.GetPlayer()
  If player.GetItemCount(Hotkey) == 0
    player.AddItem(Hotkey, 1, True)
  EndIf
  RegisterForRemoteEvent(player, "OnPlayerLoadGame")
  RegisterForExternalEvent("FNVAmmoSwitch", "OnPipboyAmmo")
  Gather()
EndEvent

Event Actor.OnPlayerLoadGame(Actor akSender)
  RegisterForExternalEvent("FNVAmmoSwitch", "OnPipboyAmmo")
  Gather()
EndEvent

Function Gather()
  {Merge every registered plugin's lists (this quest's own first) by list keyword, and give them to the plugin (it forgets them each game start).}
  F3NV_AmmoSwitchSource own = (Self as Quest) as F3NV_AmmoSwitchSource
  If own && Sources.Find(own) < 0
    Sources.AddForm(own)
  EndIf
  Form[] keywords = new Form[0]
  Int k = 0
  While k < Sources.GetSize()
    F3NV_AmmoSwitchSource rows = Sources.GetAt(k) as F3NV_AmmoSwitchSource
    Int g = 0
    While rows && g < rows.Lists.Length
      If keywords.Find(rows.Lists[g]) < 0 && keywords.Length < MaxRounds
        keywords.Add(rows.Lists[g])
      EndIf
      g += 1
    EndWhile
    k += 1
  EndWhile
  Lists = new Form[0]
  Starts = new Int[0]
  Rounds = new Form[0]
  Mods = new Form[0]
  Loaded = new Form[0]
  Notes = new Form[0]
  Int i = 0
  While i < keywords.Length
    Lists.Add(keywords[i])
    Starts.Add(Rounds.Length)
    GatherList(keywords[i])
    i += 1
  EndWhile
  Starts.Add(Rounds.Length)
  F3NV_PipboyAmmo.SetLists(Lists, Starts, Rounds, Mods)
EndFunction

Function GatherList(Form akList)
  {Append every plugin's rounds of list akList, each round once, up to MaxRounds.}
  Int k = 0
  While k < Sources.GetSize()
    F3NV_AmmoSwitchSource rows = Sources.GetAt(k) as F3NV_AmmoSwitchSource
    Int g = -1
    If rows
      g = rows.Lists.Find(akList)
    EndIf
    If g >= 0
      Int m = rows.Starts[g]
      While m < rows.Starts[g + 1]
        If Rounds.Length >= MaxRounds
          Debug.Trace("TES4AmmoSwitch|over " + MaxRounds + " rounds; " + rows.Rounds[m] + " left out")
        ElseIf Rounds.Find(rows.Rounds[m], Starts[Starts.Length - 1]) < 0
          Rounds.Add(rows.Rounds[m])
          Mods.Add(rows.Mods[m])
          Loaded.Add(rows.Loaded[m])
          Notes.Add(rows.Notes[m])
        EndIf
        m += 1
      EndWhile
    EndIf
    k += 1
  EndWhile
EndFunction

Function OnPipboyAmmo()
  {Load the round chosen in the Pip-Boy's ammo list (the plugin sends FNVAmmoSwitch as it is confirmed).}
  Weapon gun = F3NV_PipboyAmmo.ChosenGun() as Weapon
  Int m = F3NV_PipboyAmmo.TakeChoice()
  Debug.Trace("TES4AmmoSwitch|Pip-Boy|" + gun + "|round " + m)
  If gun && m >= 0
    Load(Game.GetPlayer(), gun, m)
  EndIf
EndFunction

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
      Load(player, gun, m)
      Return
    EndIf
    step += 1
  EndWhile
  NoOtherAmmo.Show()
EndFunction

Function Load(Actor player, Weapon gun, Int m)
  {Load round m (an index into Rounds) into the player's gun by attaching its mod, and show its name; refused with two copies of the gun (the mod goes on the form, not one copy).}
  If player.GetItemCount(gun) > 1
    TwoCopies.Show()
  ElseIf player.AttachModToInventoryItem(gun, Mods[m] as ObjectMod)
    If player.GetEquippedWeapon() == gun
      player.EquipItem(Rounds[m], False, True)
    EndIf
    (Notes[m] as Message).Show()
  EndIf
EndFunction

Int Function ListOf(Weapon gun)
  {The group of `gun` (the list keyword on its weapon record), or -1; -1 for no gun or a list with one round.}
  If !gun || !Lists
    Return -1
  EndIf
  Int g = 0
  While g < Lists.Length
    If gun.HasKeyword(Lists[g] as Keyword) && Starts[g + 1] - Starts[g] > 1
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
