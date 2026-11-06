ScriptName F3NV_Greeting extends TopicInfo Hidden
{An FO3/FNV conversation opening on Fallout 4: as the silent Greeting line begins, its speaker opens the shared GREETING scene, as StartConversation does. A GREETING scene still playing (a talk cut off, or one saved mid-talk) is stopped first: a scene start from the line (TSCE) would leave it playing and the menu empty, showing only "dialogueentry". The speaker's script package that is an FO3/FNV Dialogue package is done now that it talks (F3NV_ScriptPackages.Talked).}

Scene Property Greeting Auto Const
{The GREETING scene every NPC's talk opens with.}
F3NV_ScriptPackages Property ScriptPackages Auto Const
{The script-package quest: a force greet a script gave the speaker ends as the talk opens.}

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
  If ScriptPackages
    ScriptPackages.Talked(akSpeakerRef as Actor)
  EndIf
EndEvent
