ScriptName F3NV_RadioPlaylist extends Quest Conditional
{An FO3/FNV radio station's program on Fallout 4: a scene per step (the topics a line's Choices name), run in turn. A line tells it, as it begins (F3NV_RadioLine), that it was said, its song and the step that follows; a step scene's end fragment (F3NV_RadioScene) starts that step. A step with nothing to say ends the run, and the timer starts the first step again, as RadioFailsafeScript does. Each restart is traced (TES4Radio).}

Int Property CurrentSong Auto Conditional
{The song the last line played; each song phase's start condition reads it.}
Int Property Said Auto Conditional
{1 once a line of the current step is said; a step's later topics are tried only while it is 0.}
Scene Property Program Auto Const
{The first step's scene (RadioHello).}
Scene[] Property Steps Auto Const
{Every step's scene, in step order (Program first).}

Int NextStep = 0
Float Restart = 5.0
Float LineStart = 0.0
Float MinStep = 1.0

Event OnQuestInit()
  Begin()
  StartTimer(Restart)
EndEvent

Event OnTimer(int aiTimerID)
  If !Playing()
    Debug.Trace("TES4Radio|" + Utility.GetCurrentRealTime() + "|restart|" + Program)
    Begin()
  EndIf
  StartTimer(Restart)
EndEvent

Function Begin()
  {Start the program at its first step.}
  Said = 0
  CurrentSong = 0
  Program.Start()
EndFunction

Bool Function Playing()
  {Whether any step's scene is running.}
  int i = 0
  While i < Steps.Length
    If Steps[i].IsPlaying()
      Return True
    EndIf
    i += 1
  EndWhile
  Return False
EndFunction

Function LineBegan(Int aiSong, Int aiNextStep)
  {A line of the current step began: its song (0 for none) and the step its Choices make (1-based).}
  Said = 1
  CurrentSong = aiSong
  NextStep = aiNextStep
  LineStart = Utility.GetCurrentRealTime()
EndFunction

Function SceneEnded()
  {A step's scene ended: start the step its line chose; nothing when no line was said, or when the step lasted under MinStep (a line with no audio ends at once: the timer restarts, so nothing loops faster than it).}
  If Said == 0
    Return
  EndIf
  Said = 0
  CurrentSong = 0
  If Utility.GetCurrentRealTime() - LineStart < MinStep
    Debug.Trace("TES4Radio|" + LineStart + "|short step|" + Program)
    Return
  EndIf
  If NextStep > 0 && NextStep <= Steps.Length
    Steps[NextStep - 1].Start()
  EndIf
EndFunction
