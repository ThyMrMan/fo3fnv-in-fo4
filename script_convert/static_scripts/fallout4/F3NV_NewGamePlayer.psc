ScriptName F3NV_NewGamePlayer extends ReferenceAlias Hidden
{On F3NV_NewGame's Player alias (forced to the player): starts the player-hit trace when bound and on every load, so a save whose F3NV_NewGame ran before the trace existed traces too.}

Event OnInit()
  (GetOwningQuest() as F3NV_NewGame).TracePlayerHits(GetActorReference())
EndEvent

Event OnPlayerLoadGame()
  (GetOwningQuest() as F3NV_NewGame).TracePlayerHits(GetActorReference())
EndEvent
