ScriptName F3NV_Damage Native Hidden
{FO3/FNV Damage Threshold and Damage Resistance: the F3NV F4SE plugin replaces FO4's resistance curve for physical and energy damage with FNV's (damage x (1 - DR), minus DT, at least the floor).}

Function SetRules(Float afMinDamage, Float afMaxResist, ActorValue akResist, ActorValue akThreshold, ActorValue akEnergy) Global Native
{FNV's floor (fMinDamMultiplier) and DR cap (fMaxArmorRating / 100); the actor values of FNV's DR, FNV's DT (FO4's DamageResist) and FO4's EnergyResist. Until called, FO4's curve applies.}
