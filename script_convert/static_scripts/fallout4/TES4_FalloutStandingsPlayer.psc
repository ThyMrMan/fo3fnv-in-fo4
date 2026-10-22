ScriptName TES4_FalloutStandingsPlayer extends ReferenceAlias Hidden
{On the player: tells TES4_FalloutStandings about every item taken (a theft costs karma) and every load.}

Event OnAliasInit()
  AddInventoryEventFilter(None)
  (GetOwningQuest() as TES4_FalloutStandings).Loaded()
EndEvent

Event OnPlayerLoadGame()
  AddInventoryEventFilter(None)
  (GetOwningQuest() as TES4_FalloutStandings).Loaded()
EndEvent

Event OnItemAdded(Form akBaseItem, int aiItemCount, ObjectReference akItemReference, ObjectReference akSourceContainer)
  (GetOwningQuest() as TES4_FalloutStandings).NoteItem(akSourceContainer, akItemReference)
EndEvent
