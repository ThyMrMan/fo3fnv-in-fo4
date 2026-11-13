ScriptName F3NV_CharacterRules extends Quest
{Fallout 4 only. FO3/FNV's character rules: answers F3NV_CharacterEvents' CharacterMenu (SPECIAL, and our menu as the
tag skill and trait menus), sets each skill's starting value once SPECIAL is chosen (a tagged skill's bonus kept),
gives each tagged skill its bonus once, gives each level-up's skill and perk points at the source game's rates to
CRUI_LevelUp (on this quest), and opens our level-up menu in place of LevelUpMenu. The importer fills the lists and
rates from the game. See docs/fork/research/fo4_target.md#decisions, docs/fork/fo4_level_up_plan.md#open}

F3NV_CharacterEvents Property TES4CharacterEvents Auto
FormList Property SpecialStats Auto
{The seven SPECIAL actor values in order; Intelligence is the fifth, Luck the seventh.}
FormList Property GovernedSkills Auto
{One form list per SPECIAL stat, in SpecialStats' order: the skills it governs.}
FormList Property Traits Auto
Int Property SkillPointsBase = 10 Auto
Float Property SkillPointsPerIntelligence = 1.0 Auto
Int Property LevelsPerPerk = 1 Auto
Int Property TagBonus = 15 Auto
Int Property TraitCount = 2 Auto
Float Property SkillBase = 2.0 Auto
Perk[] Property StagePerks Auto
{Each perk rank with a quest stage effect, once per effect; StageQuests and StageIndexes give its quest and stage.}
Quest[] Property StageQuests Auto
Int[] Property StageIndexes Auto
String[] Property StageScripts Auto
{Each stage's quest fragment script, whose Fragment_Stage_NNNN_Item_0 runs a stage already done.}

Bool[] HeldAtOpen
Bool[] StageSeen
Int LastLevel
Float SkillPointCarry
ActorValue[] Bonused
Bool Migrated
Bool HostMoved

Event OnInit()
  HostMoved = True
  RegisterForCustomEvent(TES4CharacterEvents, "CharacterMenu")
  RegisterForMenuOpenCloseEvent("SPECIALMenu")
  RegisterForMenuOpenCloseEvent("LevelUpMenu")
  LastLevel = Game.GetPlayer().GetLevel()
  LevelUp().Announce()
EndEvent

Event F3NV_CharacterEvents.CharacterMenu(F3NV_CharacterEvents akSender, Var[] akArgs)
  String kind = akArgs[0] as String
  If kind == "special"
    Game.ShowSPECIALMenu()
  ElseIf kind == "addspecial"
    AddSpecialPoints((akArgs[1] as Float) as Int)
  ElseIf kind == "tags"
    OpenTags((akArgs[1] as Float) as Int)
  ElseIf kind == "traits"
    OpenTraits(0)
  EndIf
EndEvent

Event OnMenuOpenCloseEvent(string asMenuName, bool abOpening)
  If asMenuName == "SPECIALMenu"
    TraceSpecial(abOpening)
  EndIf
  String ours = LevelUp().MenuName
  If asMenuName == "SPECIALMenu" && !abOpening
    SetSkillBases()
  ElseIf asMenuName == "LevelUpMenu" && abOpening
    OpenLevelUp()
  ElseIf asMenuName == ours && abOpening
    WatchStages()
  ElseIf asMenuName == ours
    RunPerkStages()
  EndIf
EndEvent

CRUI_LevelUp Function LevelUp()
  {Our level-up state and menu, on this quest. First, once on a save from before CRUI_LevelUp (OnInit ran before it,
  so HostMoved is unset), the state F3NV_LevelUp kept is moved to it. See docs/fork/fo4_level_up_plan.md#crui}
  CRUI_LevelUp host = (Self as Quest) as CRUI_LevelUp
  If !HostMoved
    HostMoved = True
    F3NV_LevelUp old = (Self as Quest) as F3NV_LevelUp
    If old
      old.MoveTo(host)
    EndIf
  EndIf
  Return host
EndFunction

Function OpenLevelUp()
  {In place of LevelUpMenu (from the Pip-Boy, LevelUpMenuEx's hotkey or anything else): this level-up's points, then
  our menu once LevelUpMenu and the Pip-Boy have closed, as FNV's level-up is not part of its Pip-Boy.
  See docs/fork/fo4_level_up_plan.md#open}
  UI.CloseMenu("LevelUpMenu")
  If UI.IsMenuOpen("PipboyMenu")
    UI.CloseMenu("PipboyMenu")
  EndIf
  TopUp()
  ShowOurs(LevelUp().LevelUpMode, 0, 0)
EndFunction

Function ShowOurs(Int aiMode, Int aiCount, Int aiBonus)
  {Our menu in mode aiMode (CRUI_LevelUp.Open) once no menu is open, LevelUpMenuEx's state moved over first. Its data
  is gathered (Prepare, which registers the menu with F4SE before we listen for it) while the Pip-Boy closes, and it
  opens as soon as no menu is open, without the settling a message box needs.
  See docs/fork/fo4_level_up_plan.md#open-delay}
  Float asked = Utility.GetCurrentRealTime()
  MovePrkf()
  LevelUp().Prepare(aiMode, aiCount, aiBonus)
  Float prepared = Utility.GetCurrentRealTime()
  RegisterForMenuOpenCloseEvent(LevelUp().MenuName)
  String held = MenusHeld()
  WaitOutOfMenus(False)
  Float free = Utility.GetCurrentRealTime()
  LevelUp().Open(aiMode, aiCount, aiBonus)
  If TES4Polyfill.Tracing()
    TES4Polyfill.TraceWrite("levelup", "mode " + aiMode + "|asked " + asked + "|prepared +" + (prepared - asked) \
        + "|held " + held + "|free +" + (free - asked) + "|opened +" + (Utility.GetCurrentRealTime() - asked))
  EndIf
EndFunction

String Function MenusHeld()
  {When tracing: what WaitOutOfMenus waits on now (menu mode, the Pip-Boy, ours), and whether dialogue is up.}
  If !TES4Polyfill.Tracing()
    Return ""
  EndIf
  Return "menumode " + Utility.IsInMenuMode() + ", pipboy " + UI.IsMenuOpen("PipboyMenu") + ", ours " \
      + UI.IsMenuOpen(LevelUp().MenuName) + ", dialogue " + UI.IsMenuOpen("DialogueMenu")
EndFunction

Function MovePrkf()
  {Once, on a save from before our menu while LevelUpMenuEx is still loaded: the perk and skill points it banked, and
  its tagged skills (each already given its bonus by its tag menu), moved to ours. Called by name (Prkf), so nothing
  compiles against LevelUpMenuEx; without PRKF.dll it waits, in case LevelUpMenuEx comes back.
  See docs/fork/fo4_level_up_plan.md#dropped}
  If Migrated || F4SE.GetPluginVersion("PRKF") < 0
    Return
  EndIf
  Migrated = True
  CRUI_LevelUp ours = LevelUp()
  Int perks = Prkf("GetPP", new Var[0]) as Int
  Int points = Prkf("GetSP", new Var[0]) as Int
  ours.AddPerkPoints(perks)
  ours.AddSkillPoints(points)
  Prkf("AddPP", OneArg(-perks))
  Prkf("AddSP", OneArg(-points))
  ActorValue[] skills = Skills()
  Int i = 0
  While i < skills.Length
    If Prkf("IsTagSkillAV", OneArg(skills[i])) as Bool
      TES4CharacterEvents.Tag(skills[i])
      If !TES4CharacterEvents.IsSuggested(skills[i])
        MarkBonused(skills[i])
      EndIf
    EndIf
    i += 1
  EndWhile
EndFunction

Var Function Prkf(String asFunction, Var[] akArgs)
  {LevelUpMenuEx's global function asFunction (script PRKF:PRKF), called by name with akArgs.}
  Return Utility.CallGlobalFunction("PRKF:PRKF", asFunction, akArgs)
EndFunction

Var[] Function OneArg(Var akArg)
  {akArg as a call's only argument.}
  Var[] args = new Var[1]
  args[0] = akArg
  Return args
EndFunction

Function MarkBonused(ActorValue akSkill)
  {akSkill has its tag bonus.}
  If !Bonused
    Bonused = new ActorValue[0]
  EndIf
  If Bonused.Find(akSkill) < 0
    Bonused.Add(akSkill)
  EndIf
EndFunction

Bool Function HasBonus(ActorValue akSkill)
  Return Bonused && Bonused.Find(akSkill) >= 0
EndFunction

Function WatchStages()
  {As the level-up menu opens: which stage perks the player holds, and a watch on their quests' stages, so
  RunPerkStages knows a perk taken in the menu whose stage did not run.}
  If !StagePerks
    Return
  EndIf
  Actor player = Game.GetPlayer()
  HeldAtOpen = new Bool[StagePerks.Length]
  StageSeen = new Bool[StagePerks.Length]
  Int i = 0
  While i < StagePerks.Length
    HeldAtOpen[i] = player.HasPerk(StagePerks[i])
    RegisterForRemoteEvent(StageQuests[i], "OnStageSet")
    i += 1
  EndWhile
EndFunction

Event Quest.OnStageSet(Quest akSender, int auiStageID, int auiItemID)
  Int i = 0
  While StageSeen && i < StageSeen.Length && i < StageQuests.Length
    If StageQuests[i] == akSender && StageIndexes[i] == auiStageID
      StageSeen[i] = True
    EndIf
    i += 1
  EndWhile
EndEvent

Function RunPerkStages()
  {Once the game resumes after the level-up menu, each held perk rank's quest stage effect runs if the engine
  skipped it: a stage not done is set; a perk taken in the menu whose stage was already done (and so not rerun, as
  on a save whose quest lacks repeated stages) runs its fragment. See docs/fork/fo4_pipeline.md#intense-training}
  Utility.Wait(1.0)
  Actor player = Game.GetPlayer()
  Int i = 0
  While StagePerks && i < StagePerks.Length
    If player.HasPerk(StagePerks[i])
      Bool done = StageQuests[i].GetStageDone(StageIndexes[i])
      Bool taken = HeldAtOpen && i < HeldAtOpen.Length && !HeldAtOpen[i] && !StageSeen[i]
      If TES4Polyfill.Tracing() && (!done || taken)
        TES4Polyfill.TraceWrite("perkstage", "" + StagePerks[i] + "|" + StageQuests[i] + "|" + StageIndexes[i] + "|" + done)
      EndIf
      If !done
        StageQuests[i].SetStage(StageIndexes[i])
      ElseIf taken
        RunFragment(i)
      EndIf
    EndIf
    i += 1
  EndWhile
  HeldAtOpen = None
EndFunction

Function RunFragment(Int i)
  {Stage effect `i`'s stage fragment, called on its quest's fragment script.}
  If !StageScripts || i >= StageScripts.Length
    Return
  EndIf
  ScriptObject fragments = StageQuests[i].CastAs(StageScripts[i])
  Int stage = StageIndexes[i]
  String pad = ""
  If stage < 10
    pad = "000"
  ElseIf stage < 100
    pad = "00"
  ElseIf stage < 1000
    pad = "0"
  EndIf
  If fragments
    fragments.CallFunction("Fragment_Stage_" + pad + stage + "_Item_0", new Var[0])
  EndIf
EndFunction

Function OpenTags(Int count)
  {Our menu as the tag menu, for `count` skills tagged in all (FNV's 3 at Doc Mitchell's, one more for Tag!). Skills
  SetPlayerTagSkill suggested are tagged already and count toward them, and the player may untag them; skills tagged
  before stay. OnTagsChosen gives the bonus.}
  RegisterForCustomEvent(LevelUp(), "TagsChosen")
  ShowOurs(LevelUp().TagsMode, count, TagBonus)
EndFunction

Function OpenTraits(Int count)
  {Our menu as the trait menu, for up to `count` traits (0: TraitCount, the game's).}
  If count <= 0
    count = TraitCount
  EndIf
  ShowOurs(LevelUp().TraitsMode, count, 0)
EndFunction

Event CRUI_LevelUp.TagsChosen(CRUI_LevelUp akSender, Var[] akArgs)
  {The tag menu's picks are set: each tagged skill without its bonus gets TagBonus, a skill untagged loses it; the
  suggestions are done with.}
  Actor player = Game.GetPlayer()
  ActorValue[] skills = Skills()
  Int i = 0
  While i < skills.Length
    Bool tagged = TES4CharacterEvents.IsTagged(skills[i])
    If tagged && !HasBonus(skills[i])
      player.SetValue(skills[i], player.GetBaseValue(skills[i]) + TagBonus)
      MarkBonused(skills[i])
    ElseIf !tagged && HasBonus(skills[i])
      player.SetValue(skills[i], player.GetBaseValue(skills[i]) - TagBonus)
      Bonused.Remove(Bonused.Find(skills[i]))
    EndIf
    i += 1
  EndWhile
  TES4CharacterEvents.Suggested = new ActorValue[0]
EndEvent

ActorValue[] Function Skills()
  {Every governed skill, in GovernedSkills' order.}
  ActorValue[] out = new ActorValue[0]
  Int i = 0
  While i < GovernedSkills.GetSize()
    FormList governed = GovernedSkills.GetAt(i) as FormList
    Int k = 0
    While k < governed.GetSize()
      out.Add(governed.GetAt(k) as ActorValue)
      k += 1
    EndWhile
    i += 1
  EndWhile
  Return out
EndFunction

Function TraceSpecial(Bool abOpening)
  {When tracing: the player's seven SPECIAL values as the SPECIAL menu opens or closes.}
  If !TES4Polyfill.Tracing()
    Return
  EndIf
  String text = "closed"
  If abOpening
    text = "opened"
  EndIf
  Int i = 0
  While i < SpecialStats.GetSize()
    text += "|" + Game.GetPlayer().GetValue(SpecialStats.GetAt(i) as ActorValue)
    i += 1
  EndWhile
  TES4Polyfill.TraceWrite("special", text)
EndFunction

Function AddSpecialPoints(Int aiPoints)
  {FO3/FNV AddSpecialPoints (Intense Training): once every menu, the Pip-Boy included, has closed, for each point the
  player picks a SPECIAL stat below 10 in the SpecialPoint box and its base rises by 1, raising the skills it governs
  by 2 (and every skill when Luck's half, rounded up, rises), as their starting value (SetSkillBases) counts it.
  See docs/fork/fo4_pipeline.md#intense-training}
  Actor player = Game.GetPlayer()
  Message box = TES4CharacterEvents.SpecialPoint
  If TES4Polyfill.Tracing()
    TES4Polyfill.TraceWrite("addspecial", "" + aiPoints + "|" + box)
  EndIf
  While aiPoints > 0 && box
    WaitOutOfMenus()
    Int pick = box.Show()
    ActorValue stat = SpecialStats.GetAt(pick) as ActorValue
    Float before = player.GetBaseValue(stat)
    If TES4Polyfill.Tracing()
      TES4Polyfill.TraceWrite("addspecial", "pick " + pick + "|" + stat + "|" + before)
    EndIf
    If stat && before < 10.0
      player.SetValue(stat, before + 1.0)
      RaiseSkills(pick, before)
      aiPoints -= 1
    EndIf
  EndWhile
EndFunction

Function WaitOutOfMenus(Bool abSettle = True)
  {Returns once no menu is open, our level-up menu named too, and the Pip-Boy has finished closing, then (abSettle)
  0.5 s of game time more: a box shown while the Pip-Boy closes never appears.
  See docs/fork/fo4_pipeline.md#intense-training}
  While Utility.IsInMenuMode() || UI.IsMenuOpen("PipboyMenu") || UI.IsMenuOpen(LevelUp().MenuName)
    Utility.WaitMenuMode(0.25)
  EndWhile
  If abSettle
    Utility.Wait(0.5)
  EndIf
EndFunction

Function RaiseSkills(Int aiStat, Float afBefore)
  {The skills stat `aiStat` governs up 2, and on a Luck rise every skill by its half's change, rounded up.}
  Actor player = Game.GetPlayer()
  Float luck = 0.0
  If aiStat == 6
    luck = Math.Ceiling((afBefore + 1.0) / 2.0) - Math.Ceiling(afBefore / 2.0)
  EndIf
  Int i = 0
  While i < GovernedSkills.GetSize()
    FormList governed = GovernedSkills.GetAt(i) as FormList
    Float gain = luck
    If i == aiStat
      gain += 2.0
    EndIf
    Int k = 0
    While k < governed.GetSize() && gain > 0.0
      ActorValue skill = governed.GetAt(k) as ActorValue
      player.SetValue(skill, player.GetBaseValue(skill) + gain)
      k += 1
    EndWhile
    i += 1
  EndWhile
EndFunction

Function SetSkillBases()
  {Each skill's base: SkillBase + 2 x its governing stat + Luck / 2, rounded up (FO3/FNV's starting value), plus
  TagBonus when it has its tag bonus (SPECIAL chosen again after the tags).}
  Actor player = Game.GetPlayer()
  Int luck = Math.Ceiling(player.GetValue(SpecialStats.GetAt(6) as ActorValue) / 2.0)
  Int i = 0
  While i < GovernedSkills.GetSize()
    Float stat = player.GetValue(SpecialStats.GetAt(i) as ActorValue)
    FormList governed = GovernedSkills.GetAt(i) as FormList
    Int k = 0
    While k < governed.GetSize()
      ActorValue skill = governed.GetAt(k) as ActorValue
      Float tag = 0.0
      If HasBonus(skill)
        tag = TagBonus
      EndIf
      player.SetValue(skill, SkillBase + 2.0 * stat + luck + tag)
      k += 1
    EndWhile
    i += 1
  EndWhile
EndFunction

Function TopUp()
  {For the levels gained since the last top-up, to CRUI_LevelUp: SkillPointsBase + Intelligence x
  SkillPointsPerIntelligence skill points each (a fraction carries over), a perk point every LevelsPerPerk levels.}
  Actor player = Game.GetPlayer()
  Int level = player.GetLevel()
  If level <= LastLevel
    Return
  EndIf
  Float sp = SkillPointCarry
  Int pp = 0
  Int l = LastLevel + 1
  While l <= level
    sp += SkillPointsBase + player.GetValue(SpecialStats.GetAt(4) as ActorValue) * SkillPointsPerIntelligence
    If l % LevelsPerPerk == 0
      pp += 1
    EndIf
    l += 1
  EndWhile
  Int whole = Math.Floor(sp)
  SkillPointCarry = sp - whole
  LevelUp().AddSkillPoints(whole)
  LevelUp().AddPerkPoints(pp)
  LastLevel = level
EndFunction
