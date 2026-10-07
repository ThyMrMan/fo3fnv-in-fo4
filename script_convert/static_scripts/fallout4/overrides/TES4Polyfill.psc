; Fallout 4 overrides for TES4Polyfill.psc: only the functions whose Fallout 4 body differs.
; Each sits under "; fallout4: replaces <Name> <sha1 of the shared block>" or "; fallout4: new".
; AV(), the actor value lookup, is generated from constants.FALLOUT4_ACTOR_VALUE_IDS.
; See docs/fork/fo4_spikes.md#spike-3-helpers

; fallout4: replaces HasVampireFed af5b2d65dc74ba2be98c146ce8c122f63b07248a
Bool Function HasVampireFed() Global
  {Oblivion vampirism: FO3/FNV have none.}
  Return False
EndFunction

; fallout4: replaces IsTES4Attribute ca2195a4604fdb894dc6d6258d91bd9412d08914
Bool Function IsTES4Attribute(String avName) Global
  {Oblivion's attributes: FO3/FNV have none; their S.P.E.C.I.A.L. are Fallout 4's own actor values.}
  Return False
EndFunction

; fallout4: replaces IsPlayable aa142250f27c93fe7472da673997a6b6553f5cc1
Bool Function IsPlayable(Form akForm) Global
  {OBSE IsPlayable, which no FO3/FNV script calls; Fallout 4 has no playable flag to read.}
  Return akForm != None
EndFunction

; fallout4: replaces PlayerAttributeGlobal 0ea80737d3b6cbeffbd30fbfc83c6d6e3d969bfa
GlobalVariable Function PlayerAttributeGlobal(Actor akActor, String avName) Global
  {The Skyrim game-select plugin's attribute globals; Fallout 4 keeps SPECIAL as actor values.}
  Return None
EndFunction

; fallout4: replaces StageSet 912cbe155223e948dfb085ef917f0674e31d80fd
Function StageSet(Quest akQuest) Global
  {Nothing to send: TES4_StagePackageAlias hears the quest's native OnStageSet.}
EndFunction

; fallout4: replaces SpinAxis af43c210ef63528275d92db3ea0d9136c3965510
Function SpinAxis(ObjectReference akRef, Int aiAxis, Float afValue, Float afRate, ObjectReference[] akRefs, Float[] afGoals, Float afSeconds) Global
  {No Skyrim runtime DLL to hand the spin to: always the Papyrus glide.}
  If akRef != None
    GlideAxis(akRef, aiAxis, afValue, akRefs, afGoals, afSeconds)
  EndIf
EndFunction

; fallout4: replaces GlideAxis b14f5694b7663d7e233816ba93f43c87f17d0f37
Function GlideAxis(ObjectReference akRef, Int aiAxis, Float afValue, ObjectReference[] akRefs, Float[] afGoals, Float afSeconds) Global
  {The shared GlideAxis without the hand-off to the Skyrim runtime DLL.}
  If akRef == None
    Return
  EndIf
  Int slot = akRefs.Find(akRef)
  If slot < 0
    slot = akRefs.Find(None)
    If slot < 0
      slot = akRefs.Length - 1
    EndIf
    akRefs[slot] = akRef
    Int i = slot * 12
    afGoals[i] = akRef.GetPositionX()
    afGoals[i + 1] = akRef.GetPositionY()
    afGoals[i + 2] = akRef.GetPositionZ()
    afGoals[i + 3] = akRef.GetAngleX()
    afGoals[i + 4] = akRef.GetAngleY()
    afGoals[i + 5] = akRef.GetAngleZ()
    While i < slot * 12 + 6
      afGoals[i + 6] = afGoals[i]
      i += 1
    EndWhile
  EndIf
  Int b = slot * 12
  afGoals[b + aiAxis] = afValue
  Float x = afGoals[b]
  Float y = afGoals[b + 1]
  Float z = afGoals[b + 2]
  If !akRef.Is3DLoaded()
    akRef.SetPosition(x, y, z)
    akRef.SetAngle(afGoals[b + 3], afGoals[b + 4], afGoals[b + 5])
    Return
  EndIf
  If afSeconds < 0.05
    afSeconds = 0.05
  EndIf
  Float dx = x - afGoals[b + 6]
  Float dy = y - afGoals[b + 7]
  Float dz = z - afGoals[b + 8]
  Float distance = Math.sqrt(dx * dx + dy * dy + dz * dz)
  If distance < 0.005
    If Math.Floor(z * 100.0 + 0.5) % 2 == 0
      z += 0.01
    Else
      z -= 0.01
    EndIf
    distance = 0.01
  EndIf
  akRef.TranslateTo(x, y, z, NearAngle(afGoals[b + 9], afGoals[b + 3]), NearAngle(afGoals[b + 10], afGoals[b + 4]), NearAngle(afGoals[b + 11], afGoals[b + 5]), distance / afSeconds, 0.0)
EndFunction

; fallout4: new
Function SayWhenFree(ObjectReference akSpeaker, Topic akTopic, ObjectReference akTarget) Global
  {FO3/FNV Say/SayTo: says once the speaker's current line is over, waiting at most 3 s. FO4 drops a line said while one plays (a SayTo in a line's end result), FNV queued it.}
  Actor a = akSpeaker as Actor
  Float waited = 0.0
  While a && a.IsTalking() && waited < 3.0
    Utility.Wait(0.05)
    waited += 0.05
  EndWhile
  akSpeaker.Say(akTopic, None, False, akTarget)
EndFunction

; fallout4: new
Function SwapMaterial(ObjectReference akRef, MatSwap akSwap) Global
  {FNV SwapTexture: akSwap becomes the reference's persistent material swap (F4SE), which the game applies whenever its 3D loads; a shown reference is reloaded at once. F4SE's ApplyMaterialSwap changed the material without redrawing it.}
  If !akRef || !akSwap
    Return
  EndIf
  akRef.SetMaterialSwap(akSwap)
  If !akRef.IsDisabled()
    akRef.Disable()
    akRef.Enable()
  EndIf
EndFunction

; fallout4: new
Function SetSex(ObjectReference akActor, String asSex) Global
  {FO3/FNV SexChange [0/1]: FO4 Papyrus has no sex setter, so Garden of Eden runs the console's sexchange, which toggles; only when the sex differs. male/0, female/1, else toggle.}
  Actor a = akActor as Actor
  If !a
    Return
  EndIf
  Int target = -1
  If asSex == "male" || asSex == "0"
    target = 0
  ElseIf asSex == "female" || asSex == "1"
    target = 1
  EndIf
  If target < 0 || a.GetLeveledActorBase().GetSex() != target
    GardenOfEden3.ExecuteConsoleCommandSilent("sexchange", a)
  EndIf
EndFunction

; fallout4: new
Function StartConversation(Scene akScene, ObjectReference akSpeaker) Global
  {FO3/FNV StartConversation with the player: the speaker fills alias 0 of the scene's quest and the scene starts; its line starts the menu scene. Nothing while it plays.}
  If !akScene || !akSpeaker || akScene.IsPlaying()
    Return
  EndIf
  (akScene.GetOwningQuest().GetAlias(0) as ReferenceAlias).ForceRefTo(akSpeaker)
  akScene.Start()
EndFunction
