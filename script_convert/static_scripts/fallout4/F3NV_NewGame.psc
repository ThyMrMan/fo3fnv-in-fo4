ScriptName F3NV_NewGame extends Quest Hidden
{The FO3/FNV opening on Fallout 4, run once as this start-game quest starts. A new game first runs Fallout 4's own opening, MQ101 stage 0: its intro movie, then the character creation at the mirror (CreateCharacter), which stands in for the source game's. Once the player leaves the sink the opening's state is undone with the calls vanilla undoes it with (TimeScale 20 as vaultExitCommonWealthSCRIPT, SetInCharGen, the chargen skeleton, the mirror sequence flag ending MQ101's lighting timer, directional light and the camera imod as MQ101PlayerScript and MQ101QuestScript, ambient particles as a later MQ101 stage, the HUD mode as MQ03QuestScript, MQ101's and MQ03's input layers deleted), Fallout 4's opening quests are stopped and the source game's first stage (StartQuest, StartStage) is set. A coc from the main menu runs no MQ101 stage 0, so the source game does not start; setting this quest's stage 5 (F3NV_NewGameStart) runs the opening and character creation by hand, stage 10 starts the source game at once. A save where the source game, or Fallout 4's own game, is already under way is left alone.}

Quest Property MQ101 Auto Const
Quest Property MQ102 Auto Const
Quest[] Property OpeningQuests Auto Const
GlobalVariable Property TimeScale Auto Const
Quest Property StartQuest Auto Const
Int Property StartStage = 0 Auto Const
ActorValue[] Property Special Auto Const
{Fallout4.esm's seven SPECIAL actor values, in order.}
Float[] Property SpecialStart Auto Const
{Each one's value in the source game's player record.}
Keyword Property AnimArchetypePlayer Auto Const
{The player's own movement archetype, which MQ101 stage 400 gives back after stage 10's fast walk (walk only while holstered).}
ImageSpaceModifier Property CharGenCameraImod Auto Const
ImageSpaceModifier Property CharGenMirrorImod Auto Const
{MQ101 stage 0's mirror camera effects: the camera one holds until removed (as MQ101PlayerScript removes it).}
Perk Property SkillGates Auto Const
{The hidden perk opening FO4's lock and terminal tiers by the source game's Lockpick and Science skills.}
Perk Property CombatRules Auto Const
{The hidden perk carrying the source game's combat rules: critical hit chance, weapon skill damage and spread.}
ActorValue Property DamageResist Auto Const
{The source game's damage resistance (a percentage; the helper plugin's FalloutDamageResist).}
ActorValue Property DamageThreshold Auto Const
{The source game's damage threshold (FO4's DamageResist).}
ActorValue Property EnergyResist Auto Const
{FO4's EnergyResist, whose damage the source game's threshold also stops.}
Float Property MinDamage Auto Const
{fMinDamMultiplier: the smallest share of a hit that gets through.}
Float Property MaxResist Auto Const
{fMaxArmorRating / 100: the damage resistance cap.}
Spell Property PlayerRules Auto Const
{The source game's base health and run speed against Fallout 4's, as an ability.}
ActorValue Property CarryWeight Auto Const
{Nudged when the ability is added, so the engine takes up the new SpeedMult.}
; MQ101QuestScript's timer re-disabling directional light, SSR and god rays each second until var_MirrorSequenceDone.
Int MirrorTimer = 50
Bool Creating = False

Event OnQuestInit()
  TracePlayerHits(Game.GetPlayer())
  GivePerks(Game.GetPlayer())
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
    CreateCharacter()
  Else
    Debug.Trace("TES4NewGame|no New Game opening (a coc): the source game waits for setstage FNV_NewGame 5 or 10")
  EndIf
EndEvent

Function RunOpening()
  {Stage 5, for a game begun by a coc: Fallout 4's New Game opening by hand (MQ101 stage 0), then CreateCharacter.}
  If StartQuest.IsRunning() || StartQuest.IsCompleted()
    Return
  EndIf
  MQ101.SetStage(0)
  CreateCharacter()
EndFunction

Function CreateCharacter()
  {Fallout 4's character creation stands in for the source game's: MQ101 stage 0's movie, then its mirror (the
  sex between the two spouses, the face, the body) until the player leaves the sink (MQ101PlayerScript sets
  var_MirrorSequenceDone as it undoes the mirror); then the opening is left and the source game begun.
  Once only: stage 5 and OnQuestInit's wait for MQ101 stage 0 can both call it, and a second Begin racing the
  first restarts the source game's first quest under its running stage fragment.
  See: docs/fork/fo4_pipeline.md#character-creation}
  If Creating
    Return
  EndIf
  Creating = True
  Utility.Wait(1.0)
  While UI.IsMenuOpen("PlayBinkMenu") || UI.IsMenuOpen("LoadingMenu")
    Utility.Wait(0.5)
  EndWhile
  MQ101QuestScript opening = MQ101 as MQ101QuestScript
  While opening.var_MirrorSequenceDone == 0
    Utility.Wait(0.5)
  EndWhile
  Debug.Trace("TES4NewGame|character created: female " + (Game.GetPlayer().GetLeveledActorBase().GetSex() == 1))
  LeaveOpening()
  Begin()
EndFunction

Function Begin()
  {Start the source game: the player's SPECIAL, then its first stage, whose race menu Fallout 4's character
  creation stood in for (F3NV_PlayerControls.RaceMenuDone). Once only; stage 10 calls it by hand, skipping the creation.}
  If StartQuest.IsRunning() || StartQuest.IsCompleted()
    Return
  EndIf
  SetStartSpecial()
  TES4Polyfill.Controls().RaceMenuDone = true
  StartQuest.SetStage(StartStage)
  Game.FadeOutGame(False, True, 0.0, 1.0)
EndFunction

Function LeaveOpening()
  {Undo what MQ101 set up (stage 0, and stage 10's fast walk as the player leaves the sink) and stop its quests,
  faded out.}
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
  player.ChangeAnimArchetype(AnimArchetypePlayer)
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

Function SetStartSpecial()
  {The player's SPECIAL as the source game's player record has it (Special[i] at SpecialStart[i]).}
  Actor player = Game.GetPlayer()
  Int i = 0
  While i < Special.Length && i < SpecialStart.Length
    player.SetValue(Special[i], SpecialStart[i])
    i += 1
  EndWhile
EndFunction

Function TracePlayerHits(Actor akPlayer)
  {Hits on the player go to the trace (TES4Polyfill.TraceHit); registered again after each hit and on every load, replacing any registration still pending, so calls from more than one hook keep one.}
  UnregisterForAllHitEvents(akPlayer)
  RegisterForHitEvent(akPlayer)
EndFunction

Event Actor.OnPlayerLoadGame(Actor akSender)
  TracePlayerHits(akSender)
  GivePerks(akSender)
  If StartQuest.IsRunning() || StartQuest.IsCompleted()
    akSender.ChangeAnimArchetype(AnimArchetypePlayer)
  EndIf
EndEvent

Function GivePerks(Actor akPlayer)
  {The player's always-on perks (SkillGates, CombatRules) and ability (PlayerRules), given when this quest starts and on every load, so a save from before a perk existed gets it; and the source game's damage rules handed to the F3NV plugin, which forgets them each session.}
  If DamageThreshold
    F3NV_Damage.SetRules(MinDamage, MaxResist, DamageResist, DamageThreshold, EnergyResist)
  EndIf
  If SkillGates && !akPlayer.HasPerk(SkillGates)
    akPlayer.AddPerk(SkillGates)
  EndIf
  If CombatRules && !akPlayer.HasPerk(CombatRules)
    akPlayer.AddPerk(CombatRules)
  EndIf
  If PlayerRules && !akPlayer.HasSpell(PlayerRules)
    akPlayer.AddSpell(PlayerRules, False)
    akPlayer.ModValue(CarryWeight, 1.0)
    akPlayer.ModValue(CarryWeight, -1.0)
  EndIf
EndFunction

Event OnHit(ObjectReference akTarget, ObjectReference akAggressor, Form akSource, Projectile akProjectile, bool abPowerAttack, bool abSneakAttack, bool abBashAttack, bool abHitBlocked, string apMaterial)
  TES4Polyfill.TraceHit(akTarget, akAggressor, akSource)
  TracePlayerHits(akTarget as Actor)
EndEvent
