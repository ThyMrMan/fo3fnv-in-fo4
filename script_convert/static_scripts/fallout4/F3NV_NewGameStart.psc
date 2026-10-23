ScriptName F3NV_NewGameStart extends Quest Hidden
{The new game quest's stage fragments: stage 10 starts the source game by hand (setstage FNV_NewGame 10), for a game begun by a coc from the main menu.}

Function Fragment_Stage_0010_Item_00()
  Quest owner = Self
  (owner as F3NV_NewGame).Begin()
EndFunction
