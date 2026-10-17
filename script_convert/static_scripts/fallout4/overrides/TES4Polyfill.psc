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
Faction Function _PlayerEnemyFaction() Global
  {Fallout4.esm's PlayerEnemyFaction (0x106C2F): its sole relation is Enemy of PlayerFaction, which returns it. Skyrim's WIPlayerEnemyFaction in the shared helpers.}
  Return Game.GetFormFromFile(0x00106C2F, "Fallout4.esm") as Faction
EndFunction

; fallout4: replaces ForceCombatNow 8c58cc5780a8af03fadc8b3d12810637906ad569
Bool Function ForceCombatNow(Actor akAttacker, Actor akTarget, Faction akAttackers, Faction akVictims, Bool abAdd = False) Global
  {The shared ForceCombatNow; a fight with the player puts the other actor in _PlayerEnemyFaction.}
  If akAttacker == None || akTarget == None || akAttacker.IsDead() || akTarget.IsDead()
    Return False
  EndIf
  Actor player = Game.GetPlayer()
  If akAttackers != None && akVictims != None
    player.RemoveFromFaction(akAttackers)
    player.RemoveFromFaction(akVictims)
  EndIf
  If akTarget == player || akAttacker == player
    If akTarget == player
      akAttacker.AddToFaction(_PlayerEnemyFaction())
    Else
      akTarget.AddToFaction(_PlayerEnemyFaction())
    EndIf
  ElseIf akAttackers != None && akVictims != None
    akAttacker.AddToFaction(akAttackers)
    akTarget.AddToFaction(akVictims)
  EndIf
  If akAttacker.GetValue(TES4Polyfill.AV("Aggression")) < 1.0
    akAttacker.SetValue(TES4Polyfill.AV("Aggression"), 1)
  EndIf
  If !abAdd && akAttacker.IsInCombat() && akAttacker.GetCombatTarget() != akTarget
    StandDown(akAttacker)
  EndIf
  akAttacker.StartCombat(akTarget)
  Return True
EndFunction

; fallout4: replaces EndCombat d99861d03328f154627388185c6ee598b4e39cea
Function EndCombat(Actor akActor, Faction akAttackers) Global
  {The shared EndCombat; the player-hating membership it clears is _PlayerEnemyFaction.}
  If akActor == None
    Return
  EndIf
  If akAttackers != None
    akActor.RemoveFromFaction(akAttackers)
  EndIf
  Faction hatesPlayer = _PlayerEnemyFaction()
  If hatesPlayer != None
    akActor.RemoveFromFaction(hatesPlayer)
  EndIf
  akActor.StopCombat()
EndFunction

; fallout4: replaces _GameDays f993f580406339b2a1b35677df01e62577eef652
Float Function _GameDays(Float afSeconds) Global
  {Real seconds as game days at the running timescale: Fallout4.esm's TimeScale (0x3A), 20 when unreadable.}
  GlobalVariable ts = Game.GetFormFromFile(0x0000003A, "Fallout4.esm") as GlobalVariable
  Float scale = 20.0
  If ts != None && ts.GetValue() > 0.0
    scale = ts.GetValue()
  EndIf
  Return afSeconds * scale / 86400.0
EndFunction

; fallout4: new
Function StartForObjective(Quest akQuest) Global
  {FO3/FNV SetObjectiveDisplayed/Completed on a quest not started yet kept the objective (a line shows it, then sets the stage that starts the quest); FO4 drops it, so the quest is started first. A completed quest is left alone.}
  If akQuest && !akQuest.IsRunning() && !akQuest.IsCompleted()
    akQuest.Start()
  EndIf
EndFunction

; fallout4: new
Function SayWhenFree(ObjectReference akSpeaker, Topic akTopic, ObjectReference akTarget) Global
  {FO3/FNV Say/SayTo: says once the speaker's current line is over, waiting at most 3 s. FO4 drops a line said while one plays (a SayTo in a line's end result), FNV queued it.
  FNV's Say began its line, begin result included, before returning; FO4's returns at once and queues every Say asked for until the line begins. So the speaker is claimed (SayLine's Variable07/08) until LineBegan marks the line begun (Variable09, 2 s at most) and its begin result has had a moment to run: a second ask meanwhile (a trigger's OnTrigger loop polling what that result settles) is the same ask and is dropped, where it would play the topic's next line.}
  Actor a = akSpeaker as Actor
  ActorValue claim = AV("Variable07")
  ActorValue deadline = AV("Variable08")
  ActorValue begun = AV("Variable09")
  If a && (a as Form).GetFormID() != 0x14
    Float now = Utility.GetCurrentGameTime()
    If a.GetValue(claim) > 0.0 && now < a.GetValue(deadline)
      TraceSay(akSpeaker, akTopic, "dropped")
      Return
    EndIf
    Float token = Utility.RandomFloat(1.0, 1000000.0)
    a.SetValue(claim, token)
    a.SetValue(deadline, now + _GameDays(5.0))
    Utility.Wait(0.0)
    If a.GetValue(claim) != token
      TraceSay(akSpeaker, akTopic, "dropped")
      Return
    EndIf
  Else
    a = None
  EndIf
  Float waited = 0.0
  While a && a.IsTalking() && waited < 3.0
    Utility.Wait(0.05)
    waited += 0.05
  EndWhile
  If a
    a.SetValue(begun, 0.0)
  EndIf
  TraceSay(akSpeaker, akTopic, "asked")
  akSpeaker.Say(akTopic, None, False, akTarget)
  If a
    waited = 0.0
    While a.GetValue(begun) == 0.0 && waited < 2.0
      Utility.Wait(0.05)
      waited += 0.05
    EndWhile
    If a.GetValue(begun) == 0.0
      TraceSay(akSpeaker, akTopic, "not started")
    Else
      TraceSay(akSpeaker, akTopic, "started")
    EndIf
    Utility.Wait(0.25)
    a.SetValue(claim, 0.0)
  EndIf
EndFunction

; fallout4: new
Bool Function Tracing() Global
  {Whether TES4Helpers.esl's TES4Trace global is on (console: set TES4Trace to 1): the Trace* functions below write only then.}
  GlobalVariable g = Game.GetFormFromFile(0xA01, "TES4Helpers.esl") as GlobalVariable
  Return g && g.GetValue() > 0.0
EndFunction

; fallout4: new
Function TraceWrite(String asKind, String asText) Global
  {One trace line for tools/validate/fo4_trace.py: TES4TRACE|real time|kind|text.}
  Debug.Trace("TES4TRACE|" + Utility.GetCurrentRealTime() + "|" + asKind + "|" + asText)
EndFunction

; fallout4: new
Function ModKarma(GlobalVariable akKarma, Float afAmount) Global
  {FO3/FNV RewardKarma (and a Karma actor value change): the karma global moved by afAmount, traced as its change and new value.}
  If !akKarma
    Return
  EndIf
  akKarma.Mod(afAmount)
  If Tracing()
    TraceWrite("karma", "" + afAmount + "|" + akKarma.GetValue())
  EndIf
EndFunction

; fallout4: new
Function SetKarma(GlobalVariable akKarma, Float afValue) Global
  {FO3/FNV setting the Karma actor value: the karma global set to afValue, traced as the change and new value.}
  If !akKarma
    Return
  EndIf
  Float before = akKarma.GetValue()
  akKarma.SetValue(afValue)
  If Tracing()
    TraceWrite("karma", "" + (afValue - before) + "|" + afValue)
  EndIf
EndFunction

; fallout4: new
Function TraceItem(String asVerb, Form akItem, Int aiCount) Global
  {A converted script giving the player an item or taking one (asVerb added/removed; aiCount -1 when not a plain number).}
  If Tracing()
    TraceWrite("item", asVerb + "|" + akItem + "|" + aiCount)
  EndIf
EndFunction

; fallout4: new
String Function TraceName(ObjectReference akRef) Global
  {A reference for a trace line: the reference with its display name (F4SE), or None.}
  If akRef == None
    Return "None"
  EndIf
  Return "" + akRef + " '" + akRef.GetDisplayName() + "'"
EndFunction

; fallout4: new
Function TraceStage(Quest akQuest, Int aiStage, Bool abSet) Global
  {A converted SetStage: the quest, the stage asked for, whether it was set, and the stage it is at after.}
  If Tracing()
    TraceWrite("stage", "" + akQuest + "|" + aiStage + "|" + abSet + "|" + akQuest.GetStage())
  EndIf
EndFunction

; fallout4: new
Function TraceValue(ScriptObject akOwner, String asVar, Float afValue) Global
  {A converted script variable after an atomic add (atomic_adds): its owner, name and new value.}
  If Tracing()
    TraceWrite("value", "" + akOwner + "|" + asVar + "|" + afValue)
  EndIf
EndFunction

; fallout4: new
Function SetMirror(GlobalVariable akGlobal, Float afValue) Global
  {A converted write of a quest variable's mirror global: when the value changes it is set and traced, and the actors near the player re-evaluate their packages, whose conditions may read it (FNV re-checks packages as they run; FO4 on EvaluatePackage).}
  If !akGlobal || akGlobal.GetValue() == afValue
    Return
  EndIf
  akGlobal.SetValue(afValue)
  If Tracing()
    TraceWrite("global", "" + akGlobal + "|" + akGlobal.GetValue())
  EndIf
  Utility.CallGlobalFunctionNoWait("TES4Polyfill", "EvaluateNearby", new Var[0])
EndFunction

; fallout4: new
Function EvaluateNearby() Global
  {EvaluatePackage on every living loaded NPC, creature, robot and super mutant (Fallout4.esm ActorType keywords) within 8192 units of the player.}
  Int[] types = new Int[4]
  types[0] = 79764
  types[1] = 79765
  types[2] = 183155
  types[3] = 448438
  Actor player = Game.GetPlayer()
  Int t = 0
  Int count = 0
  While t < types.Length
    ObjectReference[] found = player.FindAllReferencesWithKeyword(Game.GetFormFromFile(types[t], "Fallout4.esm"), 8192.0)
    Int i = 0
    While i < found.Length
      Actor a = found[i] as Actor
      If a && a != player && !a.IsDead()
        a.EvaluatePackage()
        count += 1
      EndIf
      i += 1
    EndWhile
    t += 1
  EndWhile
  If Tracing()
    TraceWrite("evaluate", "nearby|" + count + " actors")
  EndIf
EndFunction

; fallout4: new
Function EvaluateAfterScene(Scene akScene, Actor akSpeaker, Actor akListener) Global
  {Once `akScene` stops playing, both its actors re-evaluate their packages, as FNV actors resume their AI when a conversation ends.}
  Int waited = 0
  While akScene.IsPlaying() && waited < 600
    Utility.Wait(0.5)
    waited += 1
  EndWhile
  If akSpeaker
    akSpeaker.EvaluatePackage()
  EndIf
  If akListener
    akListener.EvaluatePackage()
  EndIf
  If Tracing()
    TraceWrite("evaluate", "scene ended|" + akScene + "|" + (waited * 0.5) + " s|" + akSpeaker + "|" + akListener)
  EndIf
EndFunction

; fallout4: new
Function TraceLine(ObjectReference akSpeaker, String asInfo, String asWhen) Global
  {A converted line beginning or ending: the speaker and the FNV INFO's FormID.}
  If Tracing()
    TraceWrite("line", TraceName(akSpeaker) + "|" + asInfo + "|" + asWhen)
  EndIf
EndFunction

; fallout4: new
Function TraceSay(ObjectReference akSpeaker, Topic akTopic, String asWhat) Global
  {A converted Say/SayTo: asked, started, not started (no line began in 2 s) or dropped (one already pending).}
  If Tracing()
    TraceWrite("say", TraceName(akSpeaker) + "|" + akTopic + "|" + asWhat)
  EndIf
EndFunction

; fallout4: new
Bool Function PackageEndRepeats(Package akPackage, Actor akActor, Actor[] akEnded, Float[] afEndedAt) Global
  {A package end fragment run again for akActor within 1 s while it stays on akPackage. FO4 ends a finished package again on every AI update while it stays current (Continue if PC near), where FNV ended it once. Stamps akActor's time in the arrays either way.}
  Float now = Utility.GetCurrentRealTime()
  Int i = akEnded.Find(akActor)
  If i < 0
    akEnded.Add(akActor)
    afEndedAt.Add(now)
    Return False
  EndIf
  Bool again = now - afEndedAt[i] < 1.0 && akActor.GetCurrentPackage() == akPackage
  afEndedAt[i] = now
  Return again
EndFunction

; fallout4: new
Function TracePackage(Actor akActor, String asFragment) Global
  {A converted package section running (its PF_ script's fragment): the actor and the fragment.}
  If Tracing()
    TraceWrite("package", TraceName(akActor) + "|" + asFragment + "|" + akActor.GetCurrentPackage())
  EndIf
EndFunction

; fallout4: new
Function TraceLoad(ObjectReference akRef) Global
  {A scripted actor's 3D loading: where it is now, and (TraceLoadLater) 5 s later, to tell a fall from a placement.}
  If Tracing()
    TraceWrite("load", TracePosition(akRef, "loaded"))
    Var[] args = new Var[1]
    args[0] = akRef
    Utility.CallGlobalFunctionNoWait("TES4Polyfill", "TraceLoadLater", args)
  EndIf
EndFunction

; fallout4: new
Function TraceLoadLater(ObjectReference akRef) Global
  {TraceLoad's second sample, 5 s after the load.}
  Utility.Wait(5.0)
  TraceWrite("load", TracePosition(akRef, "5 s later"))
EndFunction

; fallout4: new
String Function TracePosition(ObjectReference akRef, String asWhen) Global
  {A trace line's reference, x, y, z and moment.}
  Return TraceName(akRef) + "|" + akRef.GetPositionX() + "|" + akRef.GetPositionY() + "|" + akRef.GetPositionZ() + "|" + asWhen
EndFunction

; fallout4: new
Function TracePackageStart(ObjectReference akActor, Package akPackage) Global
  {A scripted actor starting a package (OnPackageStart).}
  If Tracing()
    TraceWrite("pkgstart", TraceName(akActor) + "|" + akPackage)
  EndIf
EndFunction

; fallout4: new
Function TraceHit(ObjectReference akTarget, ObjectReference akAggressor, Form akSource) Global
  {A scripted reference's OnHit: who was hit, by whom, with what, and the target's health after the hit over its base (actors).}
  If Tracing()
    Actor target = akTarget as Actor
    String health = ""
    If target
      health = "" + target.GetValue(AV("Health")) + "/" + target.GetBaseValue(AV("Health"))
    EndIf
    TraceWrite("hit", TraceName(akTarget) + "|" + TraceName(akAggressor) + "|" + akSource + "|" + health)
  EndIf
EndFunction

; fallout4: new
Function TraceDeath(ObjectReference akDead, Actor akKiller) Global
  {A scripted actor's OnDeath: who died and who killed them.}
  If Tracing()
    TraceWrite("death", TraceName(akDead) + "|" + TraceName(akKiller))
  EndIf
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
Function StartConversation(Scene akScene, ObjectReference akSpeaker, ObjectReference akListener = None) Global
  {FO3/FNV StartConversation: the speaker fills alias 0 (Speaker) of the scene's quest, an NPC listener other than the speaker alias 1000 (Listener), and the scene starts; with the player its line starts the menu scene. Nothing while it plays.}
  If !akScene || !akSpeaker || akScene.IsPlaying()
    Return
  EndIf
  Quest owner = akScene.GetOwningQuest()
  (owner.GetAlias(0) as ReferenceAlias).ForceRefTo(akSpeaker)
  If akListener && akListener != akSpeaker
    (owner.GetAlias(1000) as ReferenceAlias).ForceRefTo(akListener)
  EndIf
  akScene.Start()
  If Tracing()
    TraceWrite("scene", akScene + "|" + akSpeaker + "|" + akListener + "|" + akScene.IsPlaying())
  EndIf
  If akListener
    Var[] args = new Var[3]
    args[0] = akScene
    args[1] = akSpeaker as Actor
    args[2] = akListener as Actor
    Utility.CallGlobalFunctionNoWait("TES4Polyfill", "EvaluateAfterScene", args)
  EndIf
EndFunction


; fallout4: new
Function ShowBarterMenu(Actor akVendor) Global
  {FNV ShowBarterMenu, usually run as a line ends: the vendor's barter menu once the dialogue menu has closed (2 s at most), so barter does not open with the talk still on screen behind it.}
  Float waited = 0.0
  While UI.IsMenuOpen("DialogueMenu") && waited < 2.0
    Utility.WaitMenuMode(0.1)
    waited += 0.1
  EndWhile
  akVendor.ShowBarterMenu()
EndFunction
