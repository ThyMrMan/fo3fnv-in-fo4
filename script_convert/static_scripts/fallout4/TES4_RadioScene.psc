ScriptName TES4_RadioScene extends Scene Hidden Const
{An FO3/FNV radio station's step scene on Fallout 4: as it ends, its station (TES4_RadioPlaylist) moves to the next step.}

Function Fragment_End()
  TES4_RadioPlaylist station = GetOwningQuest() as TES4_RadioPlaylist
  If station
    station.SceneEnded()
  EndIf
EndFunction
