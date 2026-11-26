ScriptName F3NV_FalloutStandingsPlayer extends ReferenceAlias Hidden
{On the player: tells F3NV_FalloutStandings about every item taken (a theft costs karma), every load, and every change of location (the NPCs there get their dispositions and crime counts, as they also do on each load).}

Event OnAliasInit()
  AddInventoryEventFilter(None)
  (GetOwningQuest() as F3NV_FalloutStandings).Loaded()
  (GetOwningQuest() as F3NV_FalloutStandings).Refresh()
EndEvent

Event OnPlayerLoadGame()
  AddInventoryEventFilter(None)
  (GetOwningQuest() as F3NV_FalloutStandings).Loaded()
  (GetOwningQuest() as F3NV_FalloutStandings).Refresh()
EndEvent

Event OnLocationChange(Location akOldLoc, Location akNewLoc)
  (GetOwningQuest() as F3NV_FalloutStandings).Refresh()
EndEvent

Event OnItemAdded(Form akBaseItem, int aiItemCount, ObjectReference akItemReference, ObjectReference akSourceContainer)
  (GetOwningQuest() as F3NV_FalloutStandings).NoteItem(akSourceContainer, akItemReference)
EndEvent
