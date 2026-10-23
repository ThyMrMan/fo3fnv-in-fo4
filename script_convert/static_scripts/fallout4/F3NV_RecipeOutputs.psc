ScriptName F3NV_RecipeOutputs extends ReferenceAlias Hidden Const
{FNV recipes with more than one output, on the player alias of the plugin's recipe outputs quest. Crafting one makes its token (Tokens); the token is swapped at once for its outputs: the leveled list at the same index of Outputs, which gives every entry. Vanilla's player-alias inventory filter (BoS301PlayerAliasScript).}

FormList Property Tokens Auto Const
FormList Property Outputs Auto Const

Event OnAliasInit()
  AddInventoryEventFilter(Tokens)
EndEvent

Event OnItemAdded(Form akBaseItem, int aiItemCount, ObjectReference akItemReference, ObjectReference akSourceContainer)
  Int i = Tokens.Find(akBaseItem)
  If i < 0
    Return
  EndIf
  ObjectReference player = GetReference()
  player.RemoveItem(akBaseItem, aiItemCount, True)
  player.AddItem(Outputs.GetAt(i), aiItemCount)
EndEvent
