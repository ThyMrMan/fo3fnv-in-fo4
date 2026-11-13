ScriptName F3NV_LevelUpHolder extends Quest
{The level-up host's partner: where F3NV_LevelUp.Get() finds the running host, the player's tagged skills, and what
opening each menu does. Every function here works as written; a mod with rules of its own extends this script and
overrides the functions it needs (the FO3/FNV conversion's F3NV_CharacterEvents keeps its tags and opens the menus
through its character rules). The host reads it from its Events property, else from a holder on its own quest.
See docs/fork/fo4_level_up_plan.md#holder}

Quest Property Host Auto Hidden
{The running host (F3NV_LevelUp), set by Hold.}

ActorValue[] tags
ActorValue[] suggestions

; ---------------------------------------------------------------------------
; The running host
; ---------------------------------------------------------------------------

F3NV_LevelUpHolder Function Shared() Global
  {The holder quest of Cleanroom UI's own plugin (CleanroomUI.esl 0x800, crui/plugin.py), which every host announces
  itself to; None when the plugin is not loaded.}
  If !Game.IsPluginInstalled("CleanroomUI.esl")
    Return None
  EndIf
  Return Game.GetFormFromFile(0x800, "CleanroomUI.esl") as F3NV_LevelUpHolder
EndFunction

F3NV_LevelUp Function Running()
  {The running host Get() hands to other mods; None before it registers.}
  Return Host as F3NV_LevelUp
EndFunction

Function Hold(F3NV_LevelUp akHost)
  {Remember akHost as the running host.}
  Host = akHost as Quest
EndFunction

; ---------------------------------------------------------------------------
; Tagged skills
; ---------------------------------------------------------------------------

Bool Function IsTagged(ActorValue akSkill)
  Return akSkill && tags != None && tags.Find(akSkill) >= 0
EndFunction

Bool Function IsSuggested(ActorValue akSkill)
  {Whether akSkill is tagged only as a suggestion, so the tag menu shows it picked but lets the player change it.}
  Return akSkill && suggestions != None && suggestions.Find(akSkill) >= 0
EndFunction

Bool Function Tag(ActorValue akSkill)
  {Tag akSkill; False when it already was.}
  If !akSkill || IsTagged(akSkill)
    Return False
  ElseIf tags == None
    tags = new ActorValue[0]
  EndIf
  tags.Add(akSkill)
  Return True
EndFunction

Bool Function Untag(ActorValue akSkill)
  {Untag akSkill; False when it was not tagged.}
  If !IsTagged(akSkill)
    Return False
  EndIf
  tags.Remove(tags.Find(akSkill))
  Return True
EndFunction

Function SuggestTag(ActorValue akSkill)
  {Tag akSkill ahead of the next tag menu as a suggestion the player may change there.}
  If !akSkill
    Return
  ElseIf suggestions == None
    suggestions = new ActorValue[0]
  EndIf
  If suggestions.Find(akSkill) < 0
    suggestions.Add(akSkill)
  EndIf
  Tag(akSkill)
EndFunction

; ---------------------------------------------------------------------------
; Opening the menus (F3NV_LevelUp's OpenLevelUpMenu, OpenTagMenu, OpenTraitMenu)
; ---------------------------------------------------------------------------

Function OpenLevelUp()
  {The level-up menu (skills, perks, taken) once no menu is open, with the points the player has.}
  Running().Show(Running().LevelUpMode, 0, 0)
EndFunction

Function OpenTags(Int aiCount)
  {The tag skill menu for aiCount skills tagged in all, no bonus shown.}
  Running().Show(Running().TagsMode, aiCount, 0)
EndFunction

Function OpenTraits(Int aiCount)
  {The trait menu for up to aiCount traits (0: two, as FO3 and FNV allow).}
  If aiCount <= 0
    aiCount = 2
  EndIf
  Running().Show(Running().TraitsMode, aiCount, 0)
EndFunction
