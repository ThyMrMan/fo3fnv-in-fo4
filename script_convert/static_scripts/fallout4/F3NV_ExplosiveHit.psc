ScriptName F3NV_ExplosiveHit extends ActiveMagicEffect Const
{On an explosion's object effect: an actor it caught, unless another actor set it off, is handed to F3NV_Challenges with the weapons setting that explosion off, so the player's kill of it counts as theirs. See docs/fork/fo4_pipeline.md#challenges-explosives}

FormList Property Weapons Auto Const
{The weapons whose projectile sets this explosion off.}
Quest Property Hub Auto Const
{The game's challenges quest (F3NV_Challenges).}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If akTarget && (!akCaster || akCaster == Game.GetPlayer())
    (Hub as F3NV_Challenges).Blasted(akTarget, Weapons)
  EndIf
EndEvent
