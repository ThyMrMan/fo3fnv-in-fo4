ScriptName TES4_Pipboy Native Hidden
{FO3/FNV's Pip-Boy tabs on Fallout 4's STAT page, from the FalloutCondition F4SE plugin. See docs/fork/fo4_pipboy_tabs.md}

Function SetTab(String asName, Int aiOrder, FormList akRows, String[] asValues, FormList akShown) Global Native
{Give the STAT page tab asName (placed by aiOrder among these tabs, after the page's own): a row per akRows form, an actor value on the player or a global, by its name; its value picks from asValues (none: the number shows); a row shows while its global in akShown (None: always) is at least 1. The plugin forgets tabs each game start.}
