ScriptName TES4_Radio Hidden
{FO3/FNV radio lines on Fallout 4. FNV plays a station's lines, and runs their scripts, only while the player listens; FO4's station scenes run all the time. A radio line's speaker is its station's transmitter, whose base carries TES4_RadioStation naming its frequency.}

bool Function Heard(ObjectReference akSpeaker) Global
  {Whether the player's radio is on, tuned to and in range of akSpeaker's station; true for any other speaker.}
  TES4_RadioStation station = akSpeaker as TES4_RadioStation
  If !station
    Return True
  EndIf
  Return Game.IsPlayerRadioOn() && Math.abs(Game.GetPlayerRadioFrequency() - station.Frequency) < 0.5 && Game.IsPlayerInRadioRange(station.Frequency)
EndFunction
