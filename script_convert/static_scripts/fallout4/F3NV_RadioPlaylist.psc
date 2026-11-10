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
String[] Property StepTopics Auto Const
{The FO3/FNV EditorID of each step's first topic, in step order: where StartRadioConversation starts.}
Bool Property OnDemand Auto Const
{Only a script starts the program (StartRadioConversation); it neither starts with its quest nor restarts.}
ObjectReference[] Property Receivers Auto Const
{An on-demand program's receivers, switched on as it starts: an FO4 transmitter is heard only through one.}
Activator Property NPCReceiver Auto Const
{A receiver on the station's frequency (an invisible marker) that SetNPCRadio places at an actor: FO3/FNV plays a station through an NPC (Lily's recording, ED-E).}

ObjectReference NPCRadio = None

Int NextStep = 0
Float Restart = 5.0
Float LineStart = 0.0
Float MinStep = 1.0

Int HostAlias = 2000

Event OnQuestInit()
  F3NV_RadioStation station = (GetAlias(HostAlias) as ReferenceAlias).GetReference() as F3NV_RadioStation
  If station
    station.Playlist = Self
  EndIf
  If !OnDemand
    Begin()
    StartTimer(Restart)
  EndIf
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

Function StartAt(String asTopic)
  {Start the program at the step whose first topic is asTopic (StartRadioConversation), stopping any step running; an on-demand program switches its receivers on first.}
  int step = StepTopics.Find(asTopic)
  If step < 0
    Debug.Trace("TES4Radio|" + Utility.GetCurrentRealTime() + "|no step|" + asTopic + "|" + Program)
    Return
  EndIf
  int i = 0
  While Receivers && i < Receivers.Length
    Receivers[i].SetRadioOn(True)
    i += 1
  EndWhile
  i = 0
  While i < Steps.Length
    Steps[i].Stop()
    i += 1
  EndWhile
  Said = 0
  CurrentSong = 0
  Steps[step].Start()
EndFunction

Function SetNPCRadio(Actor akActor, Bool abOn)
  {FO3/FNV SetNPCRadio: the station plays at akActor through an NPCReceiver placed there and switched on; off removes it. A new call replaces the last one's.}
  If NPCRadio
    NPCRadio.SetRadioOn(False)
    NPCRadio.Delete()
    NPCRadio = None
  EndIf
  If !abOn || !akActor || !NPCReceiver
    Return
  EndIf
  NPCRadio = akActor.PlaceAtMe(NPCReceiver)
  NPCRadio.SetRadioOn(True)
  Debug.Trace("TES4Radio|" + Utility.GetCurrentRealTime() + "|npc radio|" + akActor + "|" + Program)
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
