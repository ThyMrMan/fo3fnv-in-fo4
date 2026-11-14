ScriptName F3NV_Items Hidden
{FO3/FNV item commands Fallout 4's natives refuse. See docs/fork/fo4_pipeline.md#form-list-items}

Function AddList(ObjectReference akTarget, FormList akList, Int aiCount, Bool abSilent = False) Global
  {AddItem with a form list, as FNV runs it: akTarget gets aiCount of every form in akList (FO4's AddItem rejects a list).}
  Int i = 0
  While akTarget && akList && i < akList.GetSize()
    akTarget.AddItem(akList.GetAt(i), aiCount, abSilent)
    i += 1
  EndWhile
EndFunction

Armor Function EquippedIn(Actor akActor, Keyword akSlot) Global
  {FNV GetEquippedObject for a biped slot: the armor akActor wears marked with that FNV slot's keyword (the build stamps FNV_BipedSlot<n> from its biped flags), else None. See docs/fork/fo4_perks.md#biped-slots}
  Int slot = 0
  While akActor && akSlot && slot < 32
    Armor item = akActor.GetWornItem(slot).item as Armor
    If item && item.HasKeyword(akSlot)
      Return item
    EndIf
    slot += 1
  EndWhile
  Return None
EndFunction
