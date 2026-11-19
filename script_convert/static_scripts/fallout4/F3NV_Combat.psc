ScriptName F3NV_Combat Native Hidden
{A child a script sent into a fight keeps fighting: the F3NV F4SE plugin (version 4 and up) skips FO4's child flee for a marked actor, as FO3/FNV never make a child flee. See docs/fork/fo4_pipeline.md#child-flee}

Function KeepFighting(Actor akActor, Bool abOn) Global Native
{Mark (abOn) or unmark akActor; a marked child fights instead of fleeing. The mark lasts this session only.}
