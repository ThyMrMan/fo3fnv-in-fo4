ScriptName TES4_CharacterEvents extends Quest
{Fallout 4 only. FO3/FNV's character menus (SPECIAL, tag skills, traits) as one
custom event, CharacterMenu(kind, value), for the character rules to answer.
Skyrim sends the TESCharacterMenu mod event instead. A custom event can only be
sent by the script declaring it, so converted scripts call Menu().}

CustomEvent CharacterMenu

Function Menu(string asKind, float afValue)
  Var[] args = new Var[2]
  args[0] = asKind
  args[1] = afValue
  SendCustomEvent("CharacterMenu", args)
EndFunction
