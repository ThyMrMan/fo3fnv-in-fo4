ScriptName F3NV_LevelUp extends Quest
{DEPRECATED, remove once no save predates CRUI_LevelUp. Fallout 4 only. Our level-up's state on saves from before
it moved to Cleanroom UI's CRUI_LevelUp: the variables of the same names keep this script's saved values, which
F3NV_CharacterRules moves to CRUI_LevelUp once (MoveTo). Attached to the character rules quest so those saves keep it.
See docs/fork/fo4_level_up_plan.md#crui}

Int Property SkillCap = 100 Auto
{As saved; moved to CRUI_LevelUp.SkillCap.}
Bool Property ShowAllPerks = False Auto
{As saved; moved to CRUI_LevelUp.ShowAllPerks.}

Int PerkPoints
Int SkillPoints
Perk[] Added

Function MoveTo(CRUI_LevelUp akHost)
  {This save's perk and skill points, added perks and options into akHost, then nothing left here.}
  If !akHost
    Return
  EndIf
  akHost.AddPerkPoints(PerkPoints)
  akHost.AddSkillPoints(SkillPoints)
  akHost.SkillCap = SkillCap
  akHost.ShowAllPerks = ShowAllPerks
  Int i = 0
  While Added && i < Added.Length
    akHost.AddPerk(Added[i])
    i += 1
  EndWhile
  Debug.Trace("F3NV_LevelUp: DEPRECATED state moved to CRUI_LevelUp: " + PerkPoints + " perk and " + SkillPoints \
      + " skill points, " + i + " added perks, cap " + SkillCap)
  PerkPoints = 0
  SkillPoints = 0
  Added = None
EndFunction
