ScriptName F3NV_SkillBook extends ObjectReference Hidden
{An FNV skill book (BOOK DATA Teaches): reading it raises its skill by Points for good and uses the copy up, as FNV does with every copy read. Fallout 4's own teach-on-read (DNAM Add Perk) gives a perk once per book record, so it cannot count copies.
See: docs/fork/fo4_pipeline.md#skill-books}

ActorValue Property Skill Auto Const
Float Property Points Auto Const

Event OnRead()
  Actor player = Game.GetPlayer()
  player.ModValue(Skill, Points)
  If GetContainer() == player
    player.RemoveItem(GetBaseObject(), 1, true)
  Else
    Disable()
    Delete()
  EndIf
EndEvent
