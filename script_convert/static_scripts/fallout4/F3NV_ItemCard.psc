ScriptName F3NV_ItemCard Native Hidden
{Lines of your own on the Pip-Boy's inventory item card, from the F3NV F4SE plugin (tes_runtime/fo4_condition/card.cpp), drawn by F3NV's Pip-Boy movie under any Pip-Boy that keeps the vanilla item card. Lines are forgotten when a save loads or a new game starts: set them again on each game load (OnPlayerLoadGame). See docs/fork/swf_framework.md#card-lines}

Function SetLine(Form akItem, String asLabel, String asValue) Global Native
{Show asLabel with asValue on akItem's item card (a Keyword: on the card of every item carrying it), replacing that item's line of the same label. An empty asValue removes the line.}
