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

Bool CamSwitchLifted
Message Property ChooseSex Auto
{Male or Female, asked before the appearance edit: FO4's remake menu cannot change sex, FO3/FNV's race menu could.}

Function ShowRaceMenu()
  {FO3/FNV ShowRaceMenu: the sex (ChooseSex, set through TES4Polyfill.SetSex), then FO4's full appearance edit
  as the vault exit elevator opens it (chargen skeleton, neutral face, third person, the player turned to the
  camera, LooksMenu mode 1). The menu needs third person, so a camera switch this layer disabled is enabled
  until the menu closes; then first person again.}
  If ChooseSex
    TES4Polyfill.SetSex(Game.GetPlayer(), ChooseSex.Show() as String)
  EndIf
  CamSwitchLifted = Layer && !Layer.IsCamSwitchEnabled()
  If CamSwitchLifted
    Layer.EnableCamSwitch(true)
  EndIf
  Actor player = Game.GetPlayer()
  player.SetHasCharGenSkeleton()
  player.ChangeAnimFaceArchetype(None)
  Game.ForceThirdPerson()
  Utility.Wait(1.0)
  player.PlayIdle(Game.GetFormFromFile(0x1A9EE, "Fallout4.esm") as Idle)
  Utility.Wait(1.0)
  RegisterForMenuOpenCloseEvent("LooksMenu")
  Game.ShowRaceMenu(uiMode = 1)
EndFunction

Event OnMenuOpenCloseEvent(string asMenuName, bool abOpening)
  If asMenuName == "LooksMenu" && !abOpening
    UnregisterForMenuOpenCloseEvent("LooksMenu")
    Game.ForceFirstPerson()
    If CamSwitchLifted
      Layer.EnableCamSwitch(false)
      CamSwitchLifted = false
    EndIf
  EndIf
EndEvent

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
