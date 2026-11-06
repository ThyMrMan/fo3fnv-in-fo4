ScriptName F3NV_CharacterEvents extends Quest
{Fallout 4 only. FO3/FNV's character menus (SPECIAL, tag skills, traits) as one
custom event, CharacterMenu(kind, value), for the character rules to answer.
Skyrim sends the TESCharacterMenu mod event instead. A custom event can only be
sent by the script declaring it, so converted scripts call Menu().}

CustomEvent CharacterMenu

Message Property SpecialPoint Auto Const
{Intense Training's box: one button per SPECIAL stat, in SpecialStats' order (the "addspecial" menu).}
ActorValue[] Property Suggested Auto Hidden
{Skills SetPlayerTagSkill tagged ahead of the next tag menu (the psych test's picks); the rules clear it after.}

Function Menu(string asKind, float afValue)
  Var[] args = new Var[2]
  args[0] = asKind
  args[1] = afValue
  SendCustomEvent("CharacterMenu", args)
EndFunction

Function SuggestTag(ActorValue akSkill)
  {FO3/FNV SetPlayerTagSkill: `akSkill` tagged ahead of the tag menu, where the player may still change it.}
  If !akSkill
    Return
  EndIf
  If !Suggested
    Suggested = new ActorValue[0]
  EndIf
  If Suggested.Find(akSkill) < 0
    Suggested.Add(akSkill)
    PRKF:PRKF.AddTagSkillAV(akSkill)
  EndIf
EndFunction
