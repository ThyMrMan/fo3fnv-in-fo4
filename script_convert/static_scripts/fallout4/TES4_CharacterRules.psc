ScriptName TES4_CharacterRules extends Quest
{Fallout 4 only. FO3/FNV's character rules on LevelUpMenuEx (PRKF): answers TES4_CharacterEvents' CharacterMenu
(SPECIAL, tag skills, traits), sets each skill's starting value once SPECIAL is chosen, and at each level-up
tops LevelUpMenuEx's skill and perk points up to the source game's rates. The importer fills the lists and
rates from the game. See docs/fork/research/fo4_target.md#decisions}

TES4_CharacterEvents Property TES4CharacterEvents Auto
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

Event OnInit()
  RegisterForCustomEvent(TES4CharacterEvents, "CharacterMenu")
  RegisterForMenuOpenCloseEvent("SPECIALMenu")
  RegisterForMenuOpenCloseEvent("LevelUpMenu")
  LastLevel = Game.GetPlayer().GetLevel()
  LastPP = PRKF:PRKF.GetPP()
  LastSP = PRKF:PRKF.GetSP()
EndEvent

Event TES4_CharacterEvents.CharacterMenu(TES4_CharacterEvents akSender, Var[] akArgs)
  String kind = akArgs[0] as String
  If kind == "special"
    Game.ShowSPECIALMenu()
  ElseIf kind == "tags"
    PRKF:PRKF.OpenTagSkillsMenu((akArgs[1] as Float) as Int, TagBonus, False)
  ElseIf kind == "traits"
    PRKF:PRKF.OpenTraitsMenuFL(Traits, TraitCount, True)
  EndIf
EndEvent

Event OnMenuOpenCloseEvent(string asMenuName, bool abOpening)
  If asMenuName == "SPECIALMenu" && !abOpening
    SetSkillBases()
  ElseIf asMenuName == "LevelUpMenu" && abOpening
    TopUp()
  ElseIf asMenuName == "LevelUpMenu"
    LastPP = PRKF:PRKF.GetPP()
    LastSP = PRKF:PRKF.GetSP()
  EndIf
EndEvent

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
