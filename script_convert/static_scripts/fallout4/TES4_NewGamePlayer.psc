ScriptName TES4_NewGamePlayer extends ReferenceAlias Hidden
{On TES4_NewGame's Player alias (forced to the player): starts the player-hit trace when bound and on every load, so a save whose TES4_NewGame ran before the trace existed traces too.}

Event OnInit()
  (GetOwningQuest() as TES4_NewGame).TracePlayerHits(GetActorReference())
EndEvent

Event OnPlayerLoadGame()
  (GetOwningQuest() as TES4_NewGame).TracePlayerHits(GetActorReference())
EndEvent
