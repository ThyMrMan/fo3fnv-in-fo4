ScriptName TES4_NewGame extends Quest Hidden
{The FO3/FNV opening on Fallout 4, run once as this start-game quest starts. A new game first runs Fallout 4's own opening, MQ101 stage 0: its intro movie, then the character creation state. Once the movie is over that state is undone with the calls vanilla undoes it with (TimeScale 20 as vaultExitCommonWealthSCRIPT, SetInCharGen, the chargen skeleton, the mirror sequence flag ending MQ101's lighting timer, directional light and the camera imod as MQ101PlayerScript and MQ101QuestScript, ambient particles as a later MQ101 stage, the HUD mode as MQ03QuestScript, MQ101's and MQ03's input layers deleted), Fallout 4's opening quests are stopped and the source game's first stage (StartQuest, StartStage) is set. A coc from the main menu runs no MQ101 stage 0: the source game starts at once. A save where the source game, or Fallout 4's own game, is already under way is left alone.}

Quest Property MQ101 Auto Const
Quest Property MQ102 Auto Const
Quest[] Property OpeningQuests Auto Const
GlobalVariable Property TimeScale Auto Const
Quest Property StartQuest Auto Const
Int Property StartStage = 0 Auto Const
ImageSpaceModifier Property CharGenCameraImod Auto Const
ImageSpaceModifier Property CharGenMirrorImod Auto Const
{MQ101 stage 0's mirror camera effects: the camera one holds until removed (as MQ101PlayerScript removes it).}
; MQ101QuestScript's timer re-disabling directional light, SSR and god rays each second until var_MirrorSequenceDone.
Int MirrorTimer = 50

Event OnQuestInit()
  TracePlayerHits(Game.GetPlayer())
  RegisterForRemoteEvent(Game.GetPlayer(), "OnPlayerLoadGame")
  If StartQuest.IsRunning() || StartQuest.IsCompleted() || MQ101.IsCompleted() || MQ101.GetStageDone(10)
    Return
  EndIf
  Float waited = 0.0
  While !MQ101.GetStageDone(0) && waited < 5.0
    Utility.Wait(0.5)
    waited += 0.5
  EndWhile
  If MQ101.GetStageDone(0)
    LeaveOpening()
  EndIf
  StartQuest.SetStage(StartStage)
  Game.FadeOutGame(False, True, 0.0, 1.0)
EndEvent

Function LeaveOpening()
  {Wait out MQ101 stage 0 (its movie, then the rest of its fragment), then undo what it set up and stop its quests.}
  Utility.Wait(1.0)
  While UI.IsMenuOpen("BinkMenu") || UI.IsMenuOpen("LoadingMenu")
    Utility.Wait(0.5)
  EndWhile
  Utility.Wait(2.0)
  Game.FadeOutGame(True, True, 0.0, 0.5, True)
  MQ101QuestScript opening = MQ101 as MQ101QuestScript
  opening.var_MirrorSequenceDone = 1
  opening.CancelTimer(MirrorTimer)
  Game.ForceDisableSSRGodraysDirLight(False, False, False)
  Weather.EnableAmbientParticles()
  CharGenCameraImod.Remove()
  CharGenMirrorImod.Remove()
  If opening.MQ101EnableLayer
    opening.MQ101EnableLayer.Delete()
    opening.MQ101EnableLayer = None
  EndIf
  MQ03QuestScript slice = MQ102 as MQ03QuestScript
  If slice.VSEnableLayer
    slice.VSEnableLayer.Delete()
    slice.VSEnableLayer = None
  EndIf
  Actor player = Game.GetPlayer()
  Game.SetInCharGen(False, False, False)
  Game.PrecacheCharGenClear()
  Game.SetCharGenHUDMode(0)
  TimeScale.SetValueInt(20)
  player.SetHasCharGenSkeleton(False)
  player.RemoveAllItems()
  Int i = 0
  While i < OpeningQuests.Length
    OpeningQuests[i].Stop()
    i += 1
  EndWhile
  MQ101.Stop()
EndFunction

Function TracePlayerHits(Actor akPlayer)
  {Hits on the player go to the trace (TES4Polyfill.TraceHit); registered again after each hit and on every load.}
  RegisterForHitEvent(akPlayer)
EndFunction

Event Actor.OnPlayerLoadGame(Actor akSender)
  TracePlayerHits(akSender)
EndEvent

Event OnHit(ObjectReference akTarget, ObjectReference akAggressor, Form akSource, Projectile akProjectile, bool abPowerAttack, bool abSneakAttack, bool abBashAttack, bool abHitBlocked, string apMaterial)
  TES4Polyfill.TraceHit(akTarget, akAggressor, akSource)
  TracePlayerHits(akTarget as Actor)
EndEvent
