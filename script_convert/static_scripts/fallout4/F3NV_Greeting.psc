ScriptName F3NV_Greeting extends TopicInfo Hidden
{An FO3/FNV conversation opening on Fallout 4: as the silent Greeting line begins, its speaker opens the shared GREETING scene, as StartConversation does. A GREETING scene still playing (a talk cut off, or one saved mid-talk) is stopped first: a scene start from the line (TSCE) would leave it playing and the menu empty, showing only "dialogueentry". The speaker's script package that is an FO3/FNV Dialogue package is done now that it talks (F3NV_ScriptPackages.Talked); a force greet of its own package list is marked spoken (DialogueDone), so it parks instead of greeting again. See docs/fork/fo4_pipeline.md#greet-once}

Scene Property Greeting Auto Const
{The GREETING scene every NPC's talk opens with.}
F3NV_ScriptPackages Property ScriptPackages Auto Const
{The script-package quest: a force greet a script gave the speaker ends as the talk opens.}
FormList Property Greets Auto Const
{The numbered force greets (GreetOnce), in number order: the speaker's current one is marked spoken.}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  If Greeting.IsPlaying()
    Greeting.Stop()
    Float waited = 0.0
    While Greeting.IsPlaying() && waited < 1.0
      Utility.Wait(0.1)
      waited += 0.1
    EndWhile
  EndIf
  TES4Polyfill.StartConversation(Greeting, akSpeakerRef)
  Actor speaker = akSpeakerRef as Actor
  If ScriptPackages && ScriptPackages.Talked(speaker)
    Return
  EndIf
  Int number = -1
  If speaker && Greets
    number = Greets.Find(speaker.GetCurrentPackage())
  EndIf
  If number >= 0
    speaker.SetValue(TES4Polyfill.AV("dialoguedone"), (number + 1) as Float)
    If TES4Polyfill.Tracing()
      TES4Polyfill.TraceWrite("dialoguedone", TES4Polyfill.TraceName(speaker) + "|" + (number + 1) + "|spoken")
    EndIf
  EndIf
EndEvent
