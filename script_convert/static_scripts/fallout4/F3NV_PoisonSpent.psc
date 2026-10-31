ScriptName F3NV_PoisonSpent extends ActiveMagicEffect
{Part of an FO3/FNV weapon poison's spell, which the poison's coat perk casts on the actor hit: the coat lasts one hit, as FNV's does, so the attacker loses the perk.
See: docs/fork/fo4_pipeline.md#weapon-poisons}

Perk Property Coat Auto Const
{The coat perk casting this spell.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If akCaster && Coat
    akCaster.RemovePerk(Coat)
  EndIf
EndEvent
