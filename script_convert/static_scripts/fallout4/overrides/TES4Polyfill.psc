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

; fallout4: new
Function PushActorAway(ObjectReference akSource, Actor akTarget, Float afForce) Global
  {FNV's PushActorAway. Fallout 4 never ragdolls the player by script (every vanilla push is the player's on an NPC) and its get-up can drop the player through the ground, so the player is staggered as Fallout4.esm's PerkStagger (0x1D33D6) does; anyone else is pushed. See docs/fork/fo4_pipeline.md#attack-spells}
  If akSource == None || akTarget == None
    Return
  EndIf
  Bool staggered = akTarget == Game.GetPlayer()
  If Tracing()
    TraceWrite("push", TraceName(akSource) + "|" + TraceName(akTarget) + "|" + afForce + "|staggered " + staggered)
  EndIf
  If staggered
    (Game.GetFormFromFile(0x001D33D6, "Fallout4.esm") as Spell).Cast(akSource, akTarget)
  Else
    akSource.PushActorAway(akTarget, afForce)
  EndIf
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
  {Whether the empty F3NV_Trace.esl is enabled (MO2's F3NV - Trace mod): the Trace* functions below write only then. Not the TES4Trace global: setting it from the console froze the main menu 85 s, and a save keeps its value. See docs/fork/fo4_pipeline.md#trace}
  Return Game.IsPluginInstalled("F3NV_Trace.esl")
EndFunction

; fallout4: new
Bool Function InMenuMode() Global
  {FO3/FNV menu mode: a pausing menu is open (our level-up, tag and trait menu pauses), or a character menu (SPECIAL, LevelUpMenu before ours replaces it, the face) that FO4 does not count as one.}
  Return Utility.IsInMenuMode() || UI.IsMenuOpen("SPECIALMenu") || UI.IsMenuOpen("LevelUpMenu") || UI.IsMenuOpen("LooksMenu")
EndFunction

; fallout4: new
Bool Function MenuMode(Int aiMenu = 0) Global
  {FO3/FNV MenuMode <id>: the dialogue menu (1009) while the player talks, else any menu (InMenuMode); Papyrus cannot tell the other menus apart.}
  If aiMenu == 1009
    Return PlayerIsInDialogue()
  EndIf
  Return InMenuMode()
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
  {A converted line beginning or ending (asWhen: begin, end, or end goodbye for an FNV Goodbye line): the speaker, the FNV INFO's FormID, the speaker's current scene and whether it is in dialogue with the player.
  See: docs/fork/fo4_pipeline.md#dialogue-trace}
  If Tracing()
    Actor a = akSpeaker as Actor
    String talk = ""
    If a
      talk = "|scene " + a.GetCurrentScene() + "|talking " + a.IsInDialogueWithPlayer()
    EndIf
    TraceWrite("line", TraceName(akSpeaker) + "|" + asInfo + "|" + asWhen + talk)
  EndIf
EndFunction

; fallout4: new
Bool Function InRegion(GlobalVariable akRegion) Global
  {FO3/FNV IsPlayerInRegion: the region's global, which F3NV_RegionWatch keeps at 1 while the player is inside its polygons; False for a region not watched.
  See: docs/fork/fo4_regions.md#built}
  Return akRegion && akRegion.GetValue() != 0.0
EndFunction

; fallout4: new
Function Greeted(ObjectReference akSpeaker) Global
  {An FO3/FNV GREETING line beginning: its speaker has now talked to the player (helper actor value TalkedToPC, which converted GetTalkedToPC conditions read). Fallout 4's own flag is already set by the silent line opening the talk.
  See: docs/fork/fo4_pipeline.md#talked-to-pc}
  Actor a = akSpeaker as Actor
  If a && a.GetValue(AV("talkedtopc")) == 0.0
    a.SetValue(AV("talkedtopc"), 1.0)
  EndIf
EndFunction

; fallout4: new
Function TraceTopicInfo(TopicInfo akInfo, ObjectReference akSpeaker) Global
  {A line with no converted script beginning: a player's menu choice (its prompt INFO), a pad, or the Tab exit line; the INFO, its speaker and the speaker's current scene.
  See: docs/fork/fo4_pipeline.md#dialogue-trace}
  If Tracing()
    Actor a = akSpeaker as Actor
    String playing = ""
    If a
      playing = "|scene " + a.GetCurrentScene()
    EndIf
    TraceWrite("choice", akInfo + "|" + TraceName(akSpeaker) + playing)
  EndIf
EndFunction

; fallout4: new
Function TraceScene(Scene akScene, String asWhen) Global
  {A dialogue scene beginning, ending, or one of its phases starting or completing (asWhen: begin, end, phase N start, phase N done).
  See: docs/fork/fo4_pipeline.md#dialogue-trace}
  If Tracing()
    TraceWrite("scenestep", akScene + "|" + asWhen)
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
  PackageState().Ended(akActor, akPackage)
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
Bool Function LimbGone(Actor akActor, Int aiLimb) Global
  {FO3/FNV IsLimbGone: whether akActor's body part aiLimb (FNV's GetHitLocation numbers, 0 Torso to 13 Brain) is dismembered, as Fallout 4's body part of that name.
  See: docs/fork/fo4_pipeline.md#ai-procedure}
  String[] parts = new String[14]
  parts[0] = "Torso"
  parts[1] = "Head1"
  parts[2] = "Head2"
  parts[3] = "LeftArm1"
  parts[4] = "LeftArm2"
  parts[5] = "RightArm1"
  parts[6] = "RightArm2"
  parts[7] = "LeftLeg1"
  parts[8] = "LeftLeg2"
  parts[9] = "LeftLeg3"
  parts[10] = "RightLeg1"
  parts[11] = "RightLeg2"
  parts[12] = "RightLeg3"
  parts[13] = "Brain"
  Return akActor && aiLimb >= 0 && aiLimb < 14 && akActor.IsDismembered(parts[aiLimb])
EndFunction

; fallout4: new
F3NV_PackageState Function PackageState() Global
  {The helper plugin's package state quest (F3NV_PackageState).}
  Return Game.GetFormFromFile(0x902, "FalloutHelpers.esl") as F3NV_PackageState
EndFunction

; fallout4: new
Int Function AIProcedure(Actor akActor) Global
  {FO3/FNV GetCurrentAIProcedure, as far as Fallout 4 can tell: 17 (Done) while the package whose end fragment last ran is still akActor's current one, 8 (Sleep) while asleep, 21 (Get Up) while getting out of a seat, else -1.
  See: docs/fork/fo4_pipeline.md#ai-procedure}
  If !akActor
    Return -1
  ElseIf PackageState().Done(akActor)
    Return 17
  ElseIf akActor.GetSleepState() >= 3
    Return 8
  ElseIf akActor.GetSitState() == 4
    Return 21
  EndIf
  Return -1
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
Function TraceActivate(ObjectReference akRef, ObjectReference akActionRef) Global
  {A scripted actor's OnActivate: who activated it.}
  If Tracing()
    TraceWrite("activate", TraceName(akRef) + "|" + TraceName(akActionRef))
  EndIf
EndFunction

; fallout4: new
Function TraceTrigger(ObjectReference akRef, ObjectReference akActionRef) Global
  {A scripted trigger's OnTriggerEnter: who entered, and how many references it holds.}
  If Tracing()
    TraceWrite("trigger", TraceName(akRef) + "|entered by " + TraceName(akActionRef) + "|inside " + akRef.GetTriggerObjectCount())
  EndIf
EndFunction

; fallout4: new
Function TraceTriggerAttach(ObjectReference akRef) Global
  {A scripted trigger's cell attaching: how many references it holds and the player's distance, now and (TraceTriggerLater) 3 s later.}
  If Tracing()
    TraceWrite("trigger", TraceTriggerCount(akRef, "attached"))
    Var[] args = new Var[1]
    args[0] = akRef
    Utility.CallGlobalFunctionNoWait("TES4Polyfill", "TraceTriggerLater", args)
  EndIf
EndFunction

; fallout4: new
Function TraceTriggerLater(ObjectReference akRef) Global
  {TraceTriggerAttach's second sample, 3 s after the attach.}
  Utility.Wait(3.0)
  TraceWrite("trigger", TraceTriggerCount(akRef, "3 s later"))
EndFunction

; fallout4: new
String Function TraceTriggerCount(ObjectReference akRef, String asWhen) Global
  {A trace line's trigger, the references inside it, the player's distance and moment.}
  Return TraceName(akRef) + "|" + asWhen + "|inside " + akRef.GetTriggerObjectCount() + "|player at " + Game.GetPlayer().GetDistance(akRef)
EndFunction

; fallout4: new
Function TraceAnimEvents(ScriptObject akListener, ObjectReference akRef) Global
  {While tracing, `akListener` hears `akRef`'s combat graph events (TraceAnim): the attack, ready and fire events FO4 fires a gun on.}
  If !Tracing()
    Return
  EndIf
  String[] names = new String[18]
  names[0] = "rangedAttackStart"
  names[1] = "weaponFire"
  names[2] = "AttackState0"
  names[3] = "attackState"
  names[4] = "ReadyState"
  names[5] = "AttackEnd"
  names[6] = "attackStop"
  names[7] = "weaponDraw"
  names[8] = "HitFrame"
  names[9] = "weaponSheathe"
  names[10] = "attackStart"
  names[11] = "AttackState1"
  names[12] = "AttackState2"
  names[13] = "AttackState3"
  names[14] = "AttackState4"
  names[15] = "reloadComplete"
  names[16] = "reloadEnd"
  names[17] = "initiateStart"
  Int i = 0
  While i < names.Length
    akListener.RegisterForAnimationEvent(akRef, names[i])
    i += 1
  EndWhile
  TraceEquipped(akRef as Actor)
EndFunction

; fallout4: new
Function TraceEquipped(Actor akActor) Global
  {While tracing, `akActor`'s equipped weapon in each of equip indices 0-4 (a robot's slots in its race's QNAM order).}
  If !Tracing() || !akActor
    Return
  EndIf
  String found = ""
  Int slot = 0
  While slot < 5
    found += "|" + akActor.GetEquippedWeapon(slot)
    slot += 1
  EndWhile
  TraceWrite("equipped", TraceName(akActor) + found)
EndFunction

; fallout4: new
Function TraceAnim(ObjectReference akSource, String asEventName) Global
  {One graph event TraceAnimEvents registered for.}
  If Tracing()
    TraceWrite("anim", TraceName(akSource) + "|" + asEventName)
  EndIf
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

; fallout4: replaces SetDestroyed f6bdab428e21960a27fdcf1a055b2e7cf85edc33
Function SetDestroyed(ObjectReference akRef, FormList akDestroyed, Bool abDestroyed = True) Global
  {FO3/FNV SetDestroyed: FO4's destroyed state and the destroyed list GetDestroyed reads. FNV's destroyed door cannot be used, by the player or by NPCs' paths; FO4's still opens, so a destroyed unlocked door is also locked Inaccessible, and a door locked that way unlocks when it is no longer destroyed.
  See: docs/fork/fo4_pipeline.md#destroyed-doors}
  If akRef == None
    Return
  EndIf
  akRef.SetDestroyed(abDestroyed)
  If akRef.GetBaseObject() as Door
    If abDestroyed && !akRef.IsLocked()
      akRef.SetLockLevel(254)
      akRef.Lock(true)
    ElseIf !abDestroyed && akRef.IsLocked() && akRef.GetLockLevel() == 254
      akRef.Lock(false)
    EndIf
  EndIf
  If akDestroyed == None
    Return
  EndIf
  If abDestroyed
    If !akDestroyed.HasForm(akRef)
      akDestroyed.AddForm(akRef)
    EndIf
  Else
    While akDestroyed.HasForm(akRef)
      akDestroyed.RemoveAddedForm(akRef)
    EndWhile
  EndIf
EndFunction

; fallout4: new
Function Restrain(ObjectReference akActor, Bool abRestrained) Global
  {FO3/FNV SetRestrained: FO4's, then, when the state changed, the actor re-evaluates its packages, which FO4 does not do by itself (vanilla frees a captive with SetRestrained(false), then EvaluatePackage); a GameMode block repeating it changes nothing. Traced with whether the state changed, the package chosen and the sit state.
  See: docs/fork/fo4_pipeline.md#restrained}
  Actor a = akActor as Actor
  If !a
    Return
  EndIf
  Bool changed = a.SetRestrained(abRestrained)
  If changed
    a.EvaluatePackage()
  EndIf
  If changed && Tracing()
    TraceWrite("restrained", TraceName(a) + "|" + abRestrained + "|changed " + changed + "|" + a.GetCurrentPackage() + "|sit " + a.GetSitState())
  EndIf
EndFunction

; fallout4: new
Function SetSex(ObjectReference akActor, String asSex) Global
  {FO3/FNV SexChange [0/1]: FO4 Papyrus has no sex setter, so the F3NV plugin runs the game's SexChange, which toggles; only when the sex differs. male/0, female/1, else toggle.}
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
    F3NV_Sex.ChangeSex(a)
  EndIf
EndFunction

; fallout4: new
Function ChangeFatigue(Actor akActor, ActorValue akFatigue, Int aiOp, Float afValue) Global
  {FO3/FNV Fatigue, a helper actor value on Fallout 4: aiOp 0 sets its base (SetAV), 1 mods it, 2 damages it, 3 restores it, 4 forces its current value, base kept (ForceAV: the thugs' get-up trick, ForceAV -1 under a base of 280). At 0 or below the actor is knocked out and recovers 1 a second (fFatigueReturnBase) toward its base, as FO3/FNV's engine does; above 0 it wakes. See docs/fork/fo4_pipeline.md#fatigue}
  If !akActor || !akFatigue || akActor.IsDead()
    Return
  EndIf
  If aiOp == 0
    akActor.SetValue(akFatigue, afValue)
  ElseIf aiOp == 1
    akActor.ModValue(akFatigue, afValue)
  ElseIf aiOp == 2
    akActor.DamageValue(akFatigue, afValue)
  ElseIf aiOp == 3
    akActor.RestoreValue(akFatigue, afValue)
  ElseIf afValue < akActor.GetValue(akFatigue)
    akActor.DamageValue(akFatigue, akActor.GetValue(akFatigue) - afValue)
  Else
    akActor.RestoreValue(akFatigue, afValue - akActor.GetValue(akFatigue))
  EndIf
  If akActor.GetValue(akFatigue) > 0.0
    If akActor.IsUnconscious()
      akActor.SetUnconscious(False)
    EndIf
  ElseIf !akActor.IsUnconscious()
    akActor.SetUnconscious(True)
    Var[] args = new Var[2]
    args[0] = akActor
    args[1] = akFatigue
    Utility.CallGlobalFunctionNoWait("TES4Polyfill", "RecoverFatigue", args)
  EndIf
EndFunction

; fallout4: replaces GetIsCreature 16dd36686d4329c258758ec7ad2f645bac82d363
Bool Function GetIsCreature(Actor akActor) Global
  {FO3/FNV GetIsCreature: whether akActor is a creature, not a person. Fallout 4 marks people's races ActorTypeNPC (HumanRace, GhoulRace) and super mutants', NPCs in FO3/FNV, ActorTypeSuperMutant; a creature's race carries neither. See docs/fork/fo4_pipeline.md#script-casts}
  If akActor == None
    Return False
  EndIf
  Keyword npc = Game.GetFormFromFile(0x13794, "Fallout4.esm") as Keyword
  Keyword mutant = Game.GetFormFromFile(0x6D7B6, "Fallout4.esm") as Keyword
  Return !akActor.HasKeyword(npc) && !akActor.HasKeyword(mutant)
EndFunction

; fallout4: new
Int Function GetBroadcastState(ObjectReference akStation) Global
  {FNV GetBroadcastState on a radio station: 1 while its reference is enabled (a disabled transmitter broadcasts nothing), else 0. See docs/fork/fo4_radio.md#broadcast-state}
  If akStation && !akStation.IsDisabled()
    Return 1
  EndIf
  Return 0
EndFunction

; fallout4: new
Function SetBroadcastState(ObjectReference akStation, Bool abOn) Global
  {FNV SetBroadcastState on a radio station: enables its reference to broadcast, disables it to stop. See docs/fork/fo4_radio.md#broadcast-state}
  If !akStation
    Return
  ElseIf abOn
    akStation.Enable()
  Else
    akStation.Disable()
  EndIf
EndFunction

; fallout4: new
Function StartRadioConversation(ObjectReference akStation, String asTopic) Global
  {FO3/FNV StartRadioConversation on a radio station: its program (the playlist that named itself on the station) starts at the step whose first topic is asTopic. See docs/fork/fo4_radio.md#start-radio-conversation}
  F3NV_RadioStation station = akStation as F3NV_RadioStation
  If station && station.Playlist
    station.Playlist.StartAt(asTopic)
  Else
    Debug.Trace("TES4Radio|no program|" + akStation + "|" + asTopic)
  EndIf
EndFunction

; fallout4: new
Function SetNPCRadio(Actor akActor, Bool abOn, ObjectReference akStation) Global
  {FO3/FNV SetNPCRadio: akActor plays akStation's program (a receiver placed at the actor), or stops. See docs/fork/fo4_radio.md#npc-radio}
  F3NV_RadioStation station = akStation as F3NV_RadioStation
  If station && station.Playlist
    station.Playlist.SetNPCRadio(akActor, abOn)
  Else
    Debug.Trace("TES4Radio|no program|" + akStation + "|SetNPCRadio")
  EndIf
EndFunction

; fallout4: new
Function SetNightEye(Actor akActor, Float afValue) Global
  {FO3/FNV SetAV NightEye on the player (Cateye, Dead Money's Ghost Sight): Fallout 4 has no Night Eye, so above 0 it plays the Night Person perk's night vision as that perk's effect does (NightPersonperkImodOn, then NightPersonperkImod), and 0 or below ends it (NightPersonperkImodOff). Nothing for another actor. See docs/fork/fo4_pipeline.md#night-eye}
  If akActor != Game.GetPlayer()
    Return
  EndIf
  ImageSpaceModifier intro = Game.GetFormFromFile(0x1E5DC3, "Fallout4.esm") as ImageSpaceModifier
  ImageSpaceModifier vision = Game.GetFormFromFile(0x1D16EA, "Fallout4.esm") as ImageSpaceModifier
  ImageSpaceModifier outro = Game.GetFormFromFile(0x1E5DC2, "Fallout4.esm") as ImageSpaceModifier
  If !intro || !vision || !outro
    Return
  EndIf
  intro.Remove()
  If afValue > 0.0
    vision.Remove()
    outro.Remove()
    intro.Apply(1.0)
    Utility.Wait(0.83)
    intro.PopTo(vision, 1.0)
  Else
    vision.PopTo(outro, 1.0)
  EndIf
EndFunction

; fallout4: new
Function RemoveMe(ObjectReference akItem, ObjectReference akTarget = None) Global
  {FO3/FNV RemoveMe: a scripted item leaves the inventory holding it (into akTarget when given), as vanilla's PAFramePurchaseScript removes itself; one placed in the world is deleted, or moved into akTarget. Delete alone leaves an inventory item in place, so FNV's ammo boxes paid out every pass. See docs/fork/fo4_pipeline.md#remove-me}
  ObjectReference holder = akItem.GetContainer()
  If holder
    holder.RemoveItem(akItem, 1, True, akTarget)
  ElseIf akTarget
    akTarget.AddItem(akItem, 1, True)
  Else
    akItem.Delete()
  EndIf
EndFunction

; fallout4: new
Function RecoverFatigue(Actor akActor, ActorValue akFatigue) Global
  {A knocked-out actor's Fatigue returning 1 a second until it is above 0, then the actor wakes; while its base is 0 or below (a script's SetAV) it stays down until a script restores or sets it.}
  While akActor && !akActor.IsDead() && akActor.IsUnconscious() && akActor.GetValue(akFatigue) <= 0.0 && akActor.GetBaseValue(akFatigue) > 0.0
    Utility.Wait(1.0)
    akActor.RestoreValue(akFatigue, 1.0)
  EndWhile
  If akActor && !akActor.IsDead() && akActor.IsUnconscious() && akActor.GetValue(akFatigue) > 0.0
    akActor.SetUnconscious(False)
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
Function TalkerActivate(Scene akGreeting, ObjectReference akTalker, ObjectReference akActionRef) Global
  {FO3/FNV default activation of a talking activator (an intercom): by the player it opens the talker's GREETING, as StartConversation does, said as whoever SetTalkingActivatorActor named; by anyone else, the game's own activation. Fallout 4's own activation of a talking activator opens no greeting.}
  If akActionRef == Game.GetPlayer()
    StartConversation(akGreeting, akTalker)
  Else
    akTalker.Activate(akActionRef, true)
  EndIf
EndFunction


; fallout4: new
Function ShowBarterMenu(Actor akVendor) Global
  {FNV ShowBarterMenu, usually run as a line ends: the vendor's talk scene stopped (its dialogue menu closes), then the barter menu once that menu has closed (2 s at most), so barter does not open over the talk.}
  Scene talk = akVendor.GetCurrentScene()
  If talk
    talk.Stop()
  EndIf
  Float waited = 0.0
  While UI.IsMenuOpen("DialogueMenu") && waited < 2.0
    Utility.WaitMenuMode(0.1)
    waited += 0.1
  EndWhile
  akVendor.ShowBarterMenu()
EndFunction


; fallout4: new
Function RemoveNativeTyped(ObjectReference akFrom, ObjectReference akTo, Bool abSilent, Int aiType) Global
  {The rest of RemoveAllTypedItems for a weapon (40) or ammo (41) code: every item of that Papyrus type akFrom holds, whatever plugin made it (a pack's weapon, Fallout 4's own), as FNV's command takes every WEAP or AMMO. See docs/fork/script_markers.md#removealltypeditems}
  If aiType != 40 && aiType != 41
    Return
  EndIf
  Form[] items = akFrom.GetInventoryItems()
  Int i = 0
  While items && i < items.Length
    If aiType == 40 && items[i] as Weapon || aiType == 41 && items[i] as Ammo
      akFrom.RemoveItem(items[i], -1, abSilent, akTo)
    EndIf
    i += 1
  EndWhile
EndFunction

; fallout4: new
Function RemoveAllTypedItems(ObjectReference akFrom, ObjectReference akTo, Bool abKeepOwner, Bool abSilent, Int aiType, FormList akType, FormList akExcept) Global
  {FNV RemoveAllTypedItems: akFrom's items of type code aiType (akType, the build's list of that type's items; type 0 is every item) move to akTo, or are destroyed without one, except akExcept's. The ownership flag holds only for type 0 (FO4's RemoveItem has none).}
  If akFrom == None || (aiType != 0 && akType == None)
    Return
  EndIf
  Int n = 0
  If akExcept
    n = Math.Min(akExcept.GetSize(), 128) as Int
  EndIf
  Int[] held = new Int[n]
  Int i = 0
  While i < n
    held[i] = akFrom.GetItemCount(akExcept.GetAt(i))
    i += 1
  EndWhile
  If aiType == 0
    akFrom.RemoveAllItems(akTo, abKeepOwner)
  Else
    akFrom.RemoveItem(akType, -1, abSilent, akTo)
    RemoveNativeTyped(akFrom, akTo, abSilent, aiType)
  EndIf
  i = 0
  While i < n
    Form kept = akExcept.GetAt(i)
    Int taken = held[i] - akFrom.GetItemCount(kept)
    If taken > 0 && akTo
      akTo.RemoveItem(kept, taken, True, akFrom)
    ElseIf taken > 0
      akFrom.AddItem(kept, taken, True)
    EndIf
    i += 1
  EndWhile
EndFunction
