ScriptName F3NV_SkillBook extends ObjectReference Hidden
{An FNV skill book (BOOK DATA Teaches): reading it raises its skill by Points, plus Bonuses[i] for each BonusPerks[i] the player has (FNV's Adjust Book Skill Points perks: Comprehension's +1), for good and uses the copy up, as FNV does with every copy read. Fallout 4's own teach-on-read (DNAM Add Perk) gives a perk once per book record, so it cannot count copies.
See: docs/fork/fo4_pipeline.md#skill-books}

ActorValue Property Skill Auto Const
Float Property Points Auto Const
Perk[] Property BonusPerks Auto Const
{FNV's perks adding to a skill book's points.}
Float[] Property Bonuses Auto Const
{The points each of BonusPerks adds.}

Event OnRead()
  Actor player = Game.GetPlayer()
  player.ModValue(Skill, Points + Bonus(player))
  If GetContainer() == player
    player.RemoveItem(GetBaseObject(), 1, true)
  Else
    Disable()
    Delete()
  EndIf
EndEvent

Float Function Bonus(Actor akReader)
  {The points akReader's book perks add.}
  Float total = 0.0
  Int i = 0
  While i < BonusPerks.Length
    If akReader.HasPerk(BonusPerks[i])
      total += Bonuses[i]
    EndIf
    i += 1
  EndWhile
  Return total
EndFunction
