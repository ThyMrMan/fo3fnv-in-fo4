ScriptName F3NV_FormListAdds extends Quest Const
{A plugin's additions to its masters' form lists and perks, made at run time on a start-game quest of that plugin: Forms[i] goes into Lists[i] (FormList.AddForm, kept by the save), and the player gets Perks (the plugin's own, holding the entries it adds to a master perk, each gated on that perk). Additions stack, so any number of plugins can add to one list or perk in any load order, none overriding it. See docs/fork/fo4_plugin_layout.md#dlc-lists}

FormList[] Property Lists Auto Const
Form[] Property Forms Auto Const
{Parallel to Lists: the form added to each.}
Perk[] Property Perks Auto Const

Event OnQuestInit()
  Int i = 0
  While i < Lists.Length
    If Lists[i] && Forms[i] && !Lists[i].HasForm(Forms[i])
      Lists[i].AddForm(Forms[i])
    EndIf
    i += 1
  EndWhile
  Actor player = Game.GetPlayer()
  i = 0
  While i < Perks.Length
    If Perks[i] && !player.HasPerk(Perks[i])
      player.AddPerk(Perks[i])
    EndIf
    i += 1
  EndWhile
EndEvent
