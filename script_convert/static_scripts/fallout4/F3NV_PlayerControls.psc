ScriptName F3NV_PlayerControls extends Quest
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
  as the vault exit elevator opens it (chargen skeleton, the face data precached for the sex just set as MQ101
  precaches it, cleared when the menu closes as MQ101PlayerScript clears it, neutral face, third person, the player turned to the
  camera, LooksMenu mode 1). The menu needs third person, so a camera switch this layer disabled is enabled
  until the menu closes; then first person again. A held player stands for it and sits again after.}
  If ChooseSex
    TES4Polyfill.SetSex(Game.GetPlayer(), ChooseSex.Show() as String)
  EndIf
  CamSwitchLifted = Layer && !Layer.IsCamSwitchEnabled()
  If CamSwitchLifted
    Layer.EnableCamSwitch(true)
  EndIf
  Actor player = Game.GetPlayer()
  Resit = Seated()
  If Resit
    Stand()
  EndIf
  player.SetHasCharGenSkeleton()
  Utility.Wait(0.5)
  Game.PrecacheCharGen()
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
    Game.PrecacheCharGenClear()
    Game.ForceFirstPerson()
    If CamSwitchLifted
      Layer.EnableCamSwitch(false)
      CamSwitchLifted = false
    EndIf
    If Resit
      Resit = false
      Sit()
    EndIf
  EndIf
EndEvent

ObjectReference Seat
Bool Resit
Bool Released

Function HoldPlayer(ObjectReference akSeat)
  {FO3/FNV AddScriptPackage on the player, whose special idles Fallout 4 cannot play. With a seat (the importer
  places one, disabled, at the marker the player starts on) the player sits in it, as MQ101 activates the cryopod;
  without one the script's disabled controls hold them. A seat already sat in stays.}
  If !akSeat || (akSeat == Seat && Seated())
    Return
  EndIf
  Seat = akSeat
  Released = false
  Sit()
EndFunction

Function Sit()
  {Enables Seat and has the player activate it once its 3D is loaded, movement and activation lifted on this layer
  until they sit (3 s at most); then SnapIntoInteraction. Logs the outcome.}
  Actor player = Game.GetPlayer()
  Seat.Enable()
  RegisterForRemoteEvent(Seat, "OnExitFurniture")
  Bool moving = !Layer || Layer.IsMovementEnabled()
  Bool activating = !Layer || Layer.IsActivateEnabled()
  If Layer
    Layer.EnableMovement(true)
    Layer.EnableActivate(true)
  EndIf
  Seat.WaitFor3DLoad()
  Seat.Activate(player)
  String how = "activated"
  If !SeatTaken()
    how = "snapped"
    player.SnapIntoInteraction(Seat)
    SeatTaken()
  EndIf
  If Layer
    Layer.EnableMovement(moving)
    Layer.EnableActivate(activating)
  EndIf
  Debug.Trace("F3NV_PlayerControls.Sit " + Seat + ": " + how + ", seated " + Seated() + ", in " + player.GetFurnitureReference())
EndFunction

Bool Function SeatTaken()
  {Waits up to 3 s for the player to sit in Seat; whether they did.}
  Float waited = 0.0
  While Seat && !Seated() && waited < 3.0
    Utility.Wait(0.1)
    waited += 0.1
  EndWhile
  Return Seated()
EndFunction

Bool Function Seated()
  {Whether the player sits in Seat: the furniture says it is in use, or the player is in it (F4SE).}
  Return Seat && (Seat.IsFurnitureInUse() || Game.GetPlayer().GetFurnitureReference() == Seat)
EndFunction

Function Stand()
  {Takes the seat away (disabled), which stands the player; a MoveTo in place if they are still in it.}
  Actor player = Game.GetPlayer()
  Seat.Disable()
  If player.GetFurnitureReference() == Seat
    player.MoveTo(player)
  EndIf
  Debug.Trace("F3NV_PlayerControls.Stand " + Seat + ": in " + player.GetFurnitureReference())
EndFunction

Function ReleasePlayer()
  {FO3/FNV RemoveScriptPackage on the player. Papyrus cannot stand the player up gently, so a seat in use stays
  until the player leaves it (moving, once the controls allow) and is disabled then.}
  Released = true
  If Seat && !Seated()
    Seat.Disable()
    Seat = None
  EndIf
EndFunction

Event ObjectReference.OnExitFurniture(ObjectReference akSender, ObjectReference akActionRef)
  If akSender == Seat && Released
    UnregisterForRemoteEvent(Seat, "OnExitFurniture")
    Seat.Disable()
    Seat = None
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
