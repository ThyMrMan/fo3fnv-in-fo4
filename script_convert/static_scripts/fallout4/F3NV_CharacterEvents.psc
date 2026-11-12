ScriptName F3NV_CharacterEvents extends Quest
{Fallout 4 only. FO3/FNV's character menus (SPECIAL, tag skills, traits) as one
custom event, CharacterMenu(kind, value), for the character rules to answer, and
the player's tagged skills, which converted scripts (IsPlayerTagSkill,
SetPlayerTagSkill), the rules and our level-up menu share. Skyrim sends the
TESCharacterMenu mod event instead. A custom event can only be sent by the script
declaring it, so converted scripts call Menu(). See docs/fork/fo4_level_up_plan.md#tags}

CustomEvent CharacterMenu
CustomEvent SkillTagged
CustomEvent SkillUntagged

Message Property SpecialPoint Auto Const
{Intense Training's box: one button per SPECIAL stat, in SpecialStats' order (the "addspecial" menu).}
ActorValue[] Property Suggested Auto Hidden
{Skills SetPlayerTagSkill tagged ahead of the next tag menu (the psych test's picks), which the player may still
change there; the rules clear it after.}

ActorValue[] Tagged

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
  EndIf
  Tag(akSkill)
EndFunction

Bool Function IsTagged(ActorValue akSkill)
  {FO3/FNV IsPlayerTagSkill.}
  Return akSkill && Tagged != None && Tagged.Find(akSkill) >= 0
EndFunction

Bool Function IsSuggested(ActorValue akSkill)
  {Whether akSkill is tagged only as SetPlayerTagSkill's suggestion, so the tag menu may untag it.}
  Return akSkill && Suggested != None && Suggested.Find(akSkill) >= 0
EndFunction

Bool Function Tag(ActorValue akSkill)
  {Tags akSkill and sends SkillTagged; False when it already was. The tag bonus is the character rules' to give.}
  If !akSkill || IsTagged(akSkill)
    Return False
  EndIf
  If Tagged == None
    Tagged = new ActorValue[0]
  EndIf
  Tagged.Add(akSkill)
  SendCustomEvent("SkillTagged", SkillArgs(akSkill))
  Return True
EndFunction

Bool Function Untag(ActorValue akSkill)
  {Untags akSkill and sends SkillUntagged; False when it was not tagged.}
  If !IsTagged(akSkill)
    Return False
  EndIf
  Tagged.Remove(Tagged.Find(akSkill))
  SendCustomEvent("SkillUntagged", SkillArgs(akSkill))
  Return True
EndFunction

Var[] Function SkillArgs(ActorValue akSkill)
  {A tag event's arguments: akSkill alone.}
  Var[] args = new Var[1]
  args[0] = akSkill
  Return args
EndFunction
