ScriptName TES4_RadioPlaylist extends Quest Conditional
{An FO3/FNV songs-only radio station on Fallout 4, as vanilla's music scenes play: its pick line sets CurrentSong (TES4_RadioSong), and the scene's phase for that song plays it. Starts the scene, and restarts it on a timer when it stops, as RadioFailsafeScript does.}

Int Property CurrentSong Auto Conditional
{The song the pick line chose; each song phase's start condition reads it.}
Scene Property Program Auto Const
{The station's playlist scene.}

Float Restart = 5.0

Event OnQuestInit()
  Program.Start()
  StartTimer(Restart)
EndEvent

Event OnTimer(int aiTimerID)
  If !Program.IsPlaying()
    Program.Start()
  EndIf
  StartTimer(Restart)
EndEvent
