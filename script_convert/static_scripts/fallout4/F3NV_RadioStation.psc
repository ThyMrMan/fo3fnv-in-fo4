ScriptName F3NV_RadioStation extends ObjectReference Hidden
{An FO3/FNV radio station's transmitter on Fallout 4: the frequency its reference broadcasts on (its XRDO), which Papyrus cannot read from a transmitter, and the program it plays.}

Float Property Frequency Auto Const
{The station's Pip-Boy frequency.}

F3NV_RadioPlaylist Property Playlist Auto
{The station's program, set by the playlist as its quest starts; StartRadioConversation starts it.}
