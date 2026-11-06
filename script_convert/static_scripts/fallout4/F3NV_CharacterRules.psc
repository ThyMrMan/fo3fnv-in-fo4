ScriptName F3NV_CharacterRules extends Quest
{Fallout 4 only. FO3/FNV's character rules on LevelUpMenuEx (PRKF): answers F3NV_CharacterEvents' CharacterMenu
(SPECIAL, tag skills, traits), sets each skill's starting value once SPECIAL is chosen, and at each level-up
tops LevelUpMenuEx's skill and perk points up to the source game's rates. The importer fills the lists and
rates from the game. See docs/fork/research/fo4_target.md#decisions}

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

Int LastLevel
Int LastPP
Int LastSP
Float SkillPointCarry
Float[] TagBases

Event OnInit()
  RegisterForCustomEvent(TES4CharacterEvents, "CharacterMenu")
  RegisterForMenuOpenCloseEvent("SPECIALMenu")
  RegisterForMenuOpenCloseEvent("LevelUpMenu")
  LastLevel = Game.GetPlayer().GetLevel()
  LastPP = PRKF:PRKF.GetPP()
  LastSP = PRKF:PRKF.GetSP()
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
    PRKF:PRKF.OpenTraitsMenuFL(Traits, TraitCount, True)
  EndIf
EndEvent

Event OnMenuOpenCloseEvent(string asMenuName, bool abOpening)
  If asMenuName == "SPECIALMenu"
    TraceSpecial(abOpening)
  EndIf
  If asMenuName == "SPECIALMenu" && !abOpening
    SetSkillBases()
  ElseIf asMenuName == "LevelUpMenu" && abOpening
    TopUp()
  ElseIf asMenuName == "LevelUpMenu"
    LastPP = PRKF:PRKF.GetPP()
    LastSP = PRKF:PRKF.GetSP()
  EndIf
EndEvent

Function OpenTags(Int count)
  {The tag menu for `count` skills in all. Skills SetPlayerTagSkill suggested are already tagged and count toward
  them; the player may untag one to pick another, and OnTagsFinished squares each skill's bonus once it closes.}
  Int tagged = 0
  If TES4CharacterEvents.Suggested
    tagged = TES4CharacterEvents.Suggested.Length
  EndIf
  If tagged > 0
    TagBases = SkillValues()
    RegisterForExternalEvent("PRKF::TagSkills::Finish", "OnTagsFinished")
  EndIf
  Int left = count - tagged
  If left < 0
    left = 0
  EndIf
  PRKF:PRKF.OpenTagSkillsMenu(left, TagBonus, tagged > 0)
EndFunction

Function OnTagsFinished()
  {Each skill at its value before the tag menu plus TagBonus when it ends tagged, whatever the menu added or took
  for a skill tagged before it opened; the suggestions are cleared.}
  UnregisterForExternalEvent("PRKF::TagSkills::Finish")
  Actor player = Game.GetPlayer()
  ActorValue[] skills = Skills()
  Int i = 0
  While i < skills.Length && i < TagBases.Length
    Float bonus = 0.0
    If PRKF:PRKF.IsTagSkillAV(skills[i])
      bonus = TagBonus
    EndIf
    player.SetValue(skills[i], TagBases[i] + bonus)
    i += 1
  EndWhile
  TES4CharacterEvents.Suggested = new ActorValue[0]
EndFunction

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

Float[] Function SkillValues()
  {The player's value of each of Skills().}
  ActorValue[] skills = Skills()
  Float[] out = new Float[skills.Length]
  Int i = 0
  While i < skills.Length
    out[i] = Game.GetPlayer().GetValue(skills[i])
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
  {FO3/FNV AddSpecialPoints (Intense Training): for each point, the player picks a SPECIAL stat below 10 in the
  SpecialPoint box and its base rises by 1, raising the skills it governs by 2 (and every skill when Luck's half,
  rounded up, rises), as their starting value (SetSkillBases) counts it. See docs/fork/fo4_pipeline.md#intense-training}
  Actor player = Game.GetPlayer()
  Message box = TES4CharacterEvents.SpecialPoint
  While aiPoints > 0 && box
    Int pick = box.Show()
    ActorValue stat = SpecialStats.GetAt(pick) as ActorValue
    Float before = player.GetBaseValue(stat)
    If stat && before < 10.0
      player.SetValue(stat, before + 1.0)
      RaiseSkills(pick, before)
      aiPoints -= 1
    EndIf
  EndWhile
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
  {Each skill's base: SkillBase + 2 x its governing stat + Luck / 2, rounded up (FO3/FNV's starting value).}
  Actor player = Game.GetPlayer()
  Int luck = Math.Ceiling(player.GetValue(SpecialStats.GetAt(6) as ActorValue) / 2.0)
  Int i = 0
  While i < GovernedSkills.GetSize()
    Float stat = player.GetValue(SpecialStats.GetAt(i) as ActorValue)
    FormList governed = GovernedSkills.GetAt(i) as FormList
    Int k = 0
    While k < governed.GetSize()
      player.SetValue(governed.GetAt(k) as ActorValue, SkillBase + 2.0 * stat + luck)
      k += 1
    EndWhile
    i += 1
  EndWhile
EndFunction

Function TopUp()
  {For the levels gained since the last top-up: SkillPointsBase + Intelligence x SkillPointsPerIntelligence skill
  points each (a fraction carries over), a perk point every LevelsPerPerk levels; whatever LevelUpMenuEx itself
  added since is subtracted.}
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
  PRKF:PRKF.AddSP(whole - (PRKF:PRKF.GetSP() - LastSP))
  PRKF:PRKF.AddPP(pp - (PRKF:PRKF.GetPP() - LastPP))
  LastLevel = level
  PRKF:PRKF.UpdateMenu()
EndFunction
