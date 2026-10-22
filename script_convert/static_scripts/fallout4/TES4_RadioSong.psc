ScriptName TES4_RadioSong extends TopicInfo Hidden
{A songs-only radio station's pick line on Fallout 4: as it begins, it sets its station's CurrentSong, so the playlist scene plays this line's song next.}

TES4_RadioPlaylist Property Playlist Auto Const
{The station quest.}
Int Property Song Auto Const
{This line's song: its phase in the playlist scene.}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  Playlist.CurrentSong = Song
EndEvent
