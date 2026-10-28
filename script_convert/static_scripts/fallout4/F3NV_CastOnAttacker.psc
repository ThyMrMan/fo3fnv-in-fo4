ScriptName F3NV_CastOnAttacker extends ActiveMagicEffect
{An FNV creature's Self-range unarmed attack effect (a knockdown, a burst): FO4 casts an attack's spell on the
actor it hits, so this touch effect casts FNV's self spell on its caster, the attacker, where FNV ran it.
See: docs/fork/fo4_pipeline.md#attack-spells}

Spell Property AttackerSpell Auto Const

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If akCaster && AttackerSpell
    If TES4Polyfill.Tracing()
      TES4Polyfill.TraceWrite("attack", TES4Polyfill.TraceName(akCaster) + "|hit " + TES4Polyfill.TraceName(akTarget) + "|casts " + AttackerSpell)
    EndIf
    AttackerSpell.Cast(akCaster, akCaster)
  EndIf
EndEvent
