ScriptName F3NV_HardcoreNative Native Hidden
{FNV Hardcore's F3NV.dll parts: ammo weight and the HUD's H2O, FOD and SLP. See docs/fork/fo4_hardcore.md#dll}

Function Track(GlobalVariable akOn, ActorValue[] akNeeds) Global Native
{While akOn is not 0, ammo weighs its record's weight and the HUD shows the needs akNeeds (Dehydration, Hunger, Sleep Deprivation). Called on start and on each load.}
