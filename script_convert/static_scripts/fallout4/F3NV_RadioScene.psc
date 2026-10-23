ScriptName F3NV_RadioScene extends Scene Hidden Const
{An FO3/FNV radio station's step scene on Fallout 4: as it ends, its station (F3NV_RadioPlaylist) moves to the next step.}

Function Fragment_End()
  F3NV_RadioPlaylist station = GetOwningQuest() as F3NV_RadioPlaylist
  If station
    station.SceneEnded()
  EndIf
EndFunction
