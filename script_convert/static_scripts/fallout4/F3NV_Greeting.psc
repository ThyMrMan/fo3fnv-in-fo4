ScriptName F3NV_Greeting extends TopicInfo Hidden
{An FO3/FNV conversation opening on Fallout 4: as the silent Greeting line begins, its speaker opens the shared GREETING scene, as StartConversation does, once another actor's conversation in that quest's Speaker alias has ended (TES4Polyfill.SpeakerFree), so it never takes over a conversation still going; it is dropped when that one never ends. A GREETING scene still playing (a talk cut off, or one saved mid-talk) is stopped first: a scene start from the line (TSCE) would leave it playing and the menu empty, showing only "dialogueentry". The speaker's script package that is an FO3/FNV Dialogue package is done now that it talks (F3NV_ScriptPackages.Talked); otherwise a numbered force greet that is its current package is marked spoken (DialogueDone holds the package's object id, GreetOnce's number), so it parks instead of greeting again. See docs/fork/fo4_pipeline.md#greet-once}

Scene Property Greeting Auto Const
{The GREETING scene every NPC's talk opens with.}
F3NV_ScriptPackages Property ScriptPackages Auto Const
{The script-package quest: a force greet a script gave the speaker ends as the talk opens.}
FormList Property Greets Auto Const
{The numbered force greets (GreetOnce): the speaker's current one is marked spoken.}

Event OnBegin(ObjectReference akSpeakerRef, bool abHasBeenSaid)
  If !TES4Polyfill.SpeakerFree(Greeting, akSpeakerRef)
    Return
  EndIf
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
  If !speaker || ScriptPackages && ScriptPackages.Talked(speaker)
    Return
  EndIf
  Package current = speaker.GetCurrentPackage()
  If current && Greets && Greets.HasForm(current)
    Int number = ObjectId(current)
    speaker.SetValue(TES4Polyfill.AV("dialoguedone"), number as Float)
    If TES4Polyfill.Tracing()
      TES4Polyfill.TraceWrite("dialoguedone", TES4Polyfill.TraceName(speaker) + "|" + number + "|spoken")
    EndIf
  EndIf
EndEvent

Int Function ObjectId(Form akForm) Global
  {akForm's FormID without its load-order slot: the low 24 bits, or 12 in a light plugin (slot FE), as GreetOnce numbers it.}
  Int id = akForm.GetFormID()
  If Math.LogicalAnd(Math.RightShift(id, 24), 0xFF) == 0xFE
    Return Math.LogicalAnd(id, 0xFFF)
  EndIf
  Return Math.LogicalAnd(id, 0xFFFFFF)
EndFunction
