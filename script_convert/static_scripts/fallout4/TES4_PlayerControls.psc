ScriptName TES4_PlayerControls extends Quest
{Fallout 4 only. The one InputEnableLayer every converted script shares (controls, fast travel): FO3/FNV
scripts disable the player's controls in one script and enable them in another,
and a Fallout 4 layer only lifts what that same layer set. The arguments are
Skyrim's first eight flags, which Fallout 4's layer takes in the same order.}

InputEnableLayer Layer

Function Disable(bool abMovement = true, bool abFighting = true, bool abCamSwitch = false, bool abLooking = false, \
                 bool abSneaking = false, bool abMenu = true, bool abActivate = true, bool abJournalTabs = false)
  If !Layer
    Layer = InputEnableLayer.Create()
  EndIf
  Layer.DisablePlayerControls(abMovement, abFighting, abCamSwitch, abLooking, abSneaking, abMenu, abActivate, abJournalTabs)
EndFunction

Function FastTravel(bool abEnable)
  {FO3/FNV EnableFastTravel; Fallout 4 sets it on an input layer.}
  If !Layer
    Layer = InputEnableLayer.Create()
  EndIf
  Layer.EnableFastTravel(abEnable)
EndFunction

Function Enable(bool abMovement = true, bool abFighting = true, bool abCamSwitch = true, bool abLooking = true, \
                bool abSneaking = true, bool abMenu = true, bool abActivate = true, bool abJournalTabs = true)
  If Layer
    Layer.EnablePlayerControls(abMovement, abFighting, abCamSwitch, abLooking, abSneaking, abMenu, abActivate, abJournalTabs)
  EndIf
EndFunction
