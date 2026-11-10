ScriptName F3NV_VoidActor extends Actor Hidden
{FNV's void creatures (CRVoid, VCrILikeOblivionChancedSpawns) on Fallout 4: a leveled list's chance of nothing is an actor that removes itself as it loads, as FNV's kills and destroys itself. On the void actor VoidRace is None; a template actor whose list can draw the void checks its race, which the drawn entry gives. It acts when its script starts and when its cell attaches too: wearing an empty skin, it may never load 3D, and one spawned into a loaded cell gets no attach, so OnLoad alone can miss it.}

Race Property VoidRace Auto Const
{The void actor's race; None on the void actor itself.}

Event OnInit()
  Vanish()
EndEvent

Event OnCellAttach()
  Vanish()
EndEvent

Event OnLoad()
  Vanish()
EndEvent

Function Vanish()
  {Disable and delete this actor when it is the void actor or wears the void race.}
  If !VoidRace || GetRace() == VoidRace
    Disable()
    Delete()
  EndIf
EndFunction
