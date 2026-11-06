ScriptName F3NV_AmmoSwitchSource extends Quest Const
{One plugin's FNV ammo lists for the Ammo Type hotkey, on a start-game quest of that plugin (the game's own ammo switch quest holds the game's). A group is one ammo list: Lists[g] the keyword its guns carry, Rounds/Mods/Loaded/Notes[Starts[g]] to [Starts[g + 1] - 1] its rounds, their mods, the keyword each mod adds and its notification. A list keyword another plugin also has gains these rounds after that plugin's. On start it adds itself to Sources, the game's registry, and has the game's F3NV_AmmoSwitch gather every plugin's lists again. See docs/fork/fo4_pipeline.md#ammo-switch-sources}

Form[] Property Lists Auto Const
Int[] Property Starts Auto Const
Form[] Property Rounds Auto Const
Form[] Property Mods Auto Const
Form[] Property Loaded Auto Const
Form[] Property Notes Auto Const
FormList Property Sources Auto Const
{The game's registry of every plugin's ammo lists.}
Quest Property Switch Auto Const
{The game's ammo switch quest (F3NV_AmmoSwitch).}

Event OnQuestInit()
  If Sources.Find(Self) < 0
    Sources.AddForm(Self)
  EndIf
  (Switch as F3NV_AmmoSwitch).Gather()
EndEvent
