ScriptName TES4_RadioLine extends TopicInfo Hidden
{An FO3/FNV radio line on Fallout 4: as it begins, it tells its station (TES4_RadioPlaylist) that it was said, its song and the step its Choices make.}

TES4_RadioPlaylist Property Playlist Auto Const
{The station quest.}
Int Property Song Auto Const
{This line's song number in the station (0 for a spoken line).}
Int Property NextStep Auto Const
{The step that follows this line (1-based; 1 is RadioHello).}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  Playlist.LineBegan(Song, NextStep)
EndEvent
