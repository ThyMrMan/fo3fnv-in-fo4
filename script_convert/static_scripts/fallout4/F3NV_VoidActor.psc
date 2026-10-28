ScriptName F3NV_VoidActor extends Actor Hidden
{FNV's void creatures (CRVoid, VCrILikeOblivionChancedSpawns) on Fallout 4: a leveled list's chance of nothing is an actor that removes itself as it loads, as FNV's kills and destroys itself. On the void actor VoidRace is None; a template actor whose list can draw the void checks its race, which the drawn entry gives.}

Race Property VoidRace Auto Const
{The void actor's race; None on the void actor itself.}

Event OnLoad()
  If !VoidRace || GetRace() == VoidRace
    Disable()
    Delete()
  EndIf
EndEvent
