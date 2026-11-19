ScriptName F3NV_NewGameStart extends Quest Hidden
{The new game quest's stage fragments, for a game begun by a coc from the main menu: stage 5 runs Fallout 4's opening and character creation, then the source game (setstage FNV_NewGame 5); stage 10 starts the source game at once.}

Function Fragment_Stage_0005_Item_00()
  Quest owner = Self
  (owner as F3NV_NewGame).RunOpening()
EndFunction

Function Fragment_Stage_0010_Item_00()
  Quest owner = Self
  (owner as F3NV_NewGame).Begin()
EndFunction
