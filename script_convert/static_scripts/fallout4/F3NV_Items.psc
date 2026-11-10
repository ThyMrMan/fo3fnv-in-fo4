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
