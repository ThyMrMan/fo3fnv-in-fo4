; Fallout 4 overrides for TES4Polyfill.psc: only the functions whose Fallout 4 body differs.
; Each sits under "; fallout4: replaces <Name> <sha1 of the shared block>" or "; fallout4: new".
; See docs/fork/fo4_spikes.md#spike-3-helpers

; fallout4: new
ActorValue Function AV(String asName) Global
  {The Fallout 4 actor value named asName, for the helpers' actor-value calls; None for one this
  does not know. Variable01-10 and the AI values are engine-made forms (ids from xEdit's
  Core/Hardcoded/Fallout4.esp); the rest are Fallout4.esm records.}
  Int id = 0
  If asName == "Variable09"
    id = 0x309
  ElseIf asName == "Variable07"
    id = 0x307
  ElseIf asName == "Variable06"
    id = 0x306
  ElseIf asName == "Variable04"
    id = 0x304
  ElseIf asName == "Variable05"
    id = 0x305
  ElseIf asName == "Variable01"
    id = 0x301
  ElseIf asName == "Variable02"
    id = 0x302
  ElseIf asName == "Variable03"
    id = 0x303
  ElseIf asName == "Variable08"
    id = 0x308
  ElseIf asName == "Variable10"
    id = 0x30A
  ElseIf asName == "Confidence"
    id = 0x2BD
  ElseIf asName == "Aggression"
    id = 0x2BC
  ElseIf asName == "Morality"
    id = 0x2BF
  ElseIf asName == "Assistance"
    id = 0x2C1
  ElseIf asName == "Health"
    id = 0x2D4
  ElseIf asName == "SpeedMult"
    id = 0x2DA
  ElseIf asName == "CarryWeight"
    id = 0x2DC
  ElseIf asName == "Strength"
    id = 0x2C2
  ElseIf asName == "Perception"
    id = 0x2C3
  ElseIf asName == "Endurance"
    id = 0x2C4
  ElseIf asName == "Charisma"
    id = 0x2C5
  ElseIf asName == "Intelligence"
    id = 0x2C6
  ElseIf asName == "Agility"
    id = 0x2C7
  ElseIf asName == "Luck"
    id = 0x2C8
  EndIf
  If id == 0
    Debug.Trace("TES4Polyfill.AV: no Fallout 4 actor value named " + asName)
    Return None
  EndIf
  Return Game.GetFormFromFile(id, "Fallout4.esm") as ActorValue
EndFunction

; fallout4: replaces HasVampireFed af5b2d65dc74ba2be98c146ce8c122f63b07248a
Bool Function HasVampireFed() Global
  {Oblivion vampirism: FO3/FNV have none.}
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
