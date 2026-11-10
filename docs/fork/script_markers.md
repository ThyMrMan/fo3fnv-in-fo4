# Unconverted FNV functions in converted scripts

When `script_convert` meets an FNV function it has no row or handler for, it
writes an inert value plus a `;NE:` (or `;NE: TODO:`) marker. A statement
becomes a comment and does nothing. A read becomes `0`, or, inside an `&&`
chain, drops out of the chain, which makes the guard pass more often
([why](../commentary/script_convert.md#comparing-an-inert-operand)).

That last case is how the casino comp quests broke. FNV writes
`if GetCasinoWinningsLevel GomorrahCasinoData == 1 && SmallFry == 0`; the
converted guard was `If SmallFry == 0`, so the comp branch ran on every poll.
Those passes piled up behind Ringo's trigger on 2026-10-31
([poll overlap](performance.md#poll-overlap)).

- [Census](#census)
- [Ranking](#ranking)
- [Built](#built)
- [Not built](#not-built)
- [Measuring again](#measuring)

## <a id="census"></a>Census (2026-10-31)

Taken over a fresh `python -m script_convert.pipeline export/FalloutNV.esm
--target fallout4` run, before the changes below: **2,156 markers in 740 of
17,482 scripts, naming 134 functions.** "After" is the same run with the
changes below. "In a condition" counts markers on an `If`/`ElseIf` line.
"Where" is the script kind: QS quest script, QF quest stage fragment, TIF topic
info fragment, obj object script, PF package fragment, TM terminal, PM patrol
marker. The last column names the quests a QS/QF/TIF script belongs to, and
for an object script the records carrying it (`ACTI:`, `NPC_:`, `CREA:`).

[Measuring again](#measuring) reproduces the table and the full per-function
script lists.

Built after this census, so not in its "After" column:
[GetAnimAction](#getanimaction) (all 5 markers) and `SetForceSneak 1`
([SetForceSneak](#setforcesneak)); only the `0` form stays a note.

| Function | Markers | After | Scripts | In a condition | Where | Quests or records (first 6) |
|---|---:|---:|---:|---:|---|---|
| removealltypeditems | 273 | 0 | 36 | 0 | obj 173 TIF 92 QS 8 | ACTI:TopsFriskingTrigger, ArcadeRetrieveArmorTimer, CREA:FortLupaGladiator, NPC_:vFortGladiatorSlaveAAM, NPC_:vFortGladiatorSlaveCM, VDialogueArcadeGannon (+4) |
| movetomarkerwithfade | 236 | 0 | 80 | 0 | obj 104 QS 68 PF 29 TIF 24 PM 11 | ACTI:VMS38LucyToRoomTrigger01Volume, ACTI:VMS38RedLucyRoomCodeHolder, ACTI:VMS38RedLucyThornCodeHolder, ACTI:VPitFightScriptHolder, ACTI:VStripNorthCodeHolder, ACTI:VVMS21aJoanaFirstTimeCodeHolder (+26) |
| ignorecrime | 185 | 185 | 66 | 0 | obj 145 TIF 33 PF 4 QF 2 QS 1 | ACTI:FortArrivalTrigger, ACTI:VMS35AutoDoc, ACTI:VPitPlayerPositionFight, ACTI:VPitPositionFight, CREA:GSVictorDisabled, NPC_:BCTrooperHostageAAM (+48) |
| killactor | 143 | 0 | 68 | 0 | obj 130 TIF 8 PF 3 QS 2 | ACTI:ControlPanelHeliosTower, ACTI:EdwardsScorpionAttack, ACTI:GenericRandomDismember, ACTI:HeadshotActivator, ACTI:LeftLegDismemberActivator, ACTI:MicroclineRock (+46) |
| setplayerteammate | 139 | 0 | 97 | 0 | TIF 88 QS 29 obj 22 | ACTI:HVBunkerExplosionTrigger, ACTI:VMS18TedReturnTrigger, ACTI:VULPenthouseIntTrigger, CREA:Lily, NPC_:RoseofSharonCassidy, NPC_:VMS18TedGunderson (+14) |
| addachievement | 111 | 111 | 81 | 0 | obj 69 QF 25 TIF 9 QS 8 | ACTI:ControlPanelHeliosTower, AchievementQuest, CREA:DCWorld05Behemoth, CREA:EvergreenMillsBehemoth, CREA:FFMutantCamp01Behemoth, CREA:LDCrSuperMutantBehemothCapitolBuilding (+52) |
| entertrigger | 99 | 5 | 95 | 0 | TIF 92 QS 5 PM 2 | VFactionSquad, VFreeformTheStreet01, VMS30, VMS38, vFreeformForlornHope03 |
| do | 68 | 0 | 26 | 0 | obj 68 | ACTI:ExplosionOffsetZ64Act, ACTI:HVRangerGoBoomTrigger, ACTI:HVRangerRadio, ACTI:SprungTrapBearTrap, ACTI:TrapBabyCarriage, ACTI:TrapBearTrap (+9) |
| setcombatstyle | 54 | 54 | 40 | 0 | TIF 37 obj 17 | CREA:CrSporeCarrierFD4, CREA:CrSporeCarrierFU, CREA:CrSporeCarrierFU2, CREA:CrSporeCarrierFU3, CREA:CrSporeCarrierFU4, CREA:Lily (+9) |
| addformtoformlist | 35 | 0 | 21 | 0 | TIF 35 | VFreeformNellis |
| isimagespaceactive | 32 | 0 | 16 | 32 | obj 26 QS 6 | ArcadeRetrieveArmorTimer, AutoDocTimerQuest, FriendOfTheNightQuest, ImplantTimerQuest, NPC_:1EBertGunnarsson, NPC_:2CDocSawbones (+12) |
| setsecuritronexpression | 32 | 32 | 5 | 0 | TIF 24 obj 7 PM 1 | ACTI:SVMainConsole, CREA:VFSSecuritronGreeter, VDialogueMrHouse, VMQTops |
| forceterminalback | 30 | 30 | 18 | 0 | TM 30 |  |
| movetofade | 27 | 0 | 6 | 0 | TIF 20 obj 6 QS 1 | ACTI:REPCONTopIntercomTrigger, ACTI:vHDVertiBirdEncounter02, NPC_:REPCONGhoul2F, NPC_:REPCONGhoul3F, NPC_:REPCONGhoul4m, NPC_:REPCONGhoul5m (+2) |
| showcaravanmenu | 27 | 27 | 18 | 0 | TIF 27 | VFreeformGoodsprings, vCaravanQuest, vDialogueVegasEast2, vMojave |
| setobjectivedisplayed | 26 | 26 | 20 | 0 | QF 13 obj 8 TIF 3 QS 2 | NPC_:NVNelsonRangerMilo, NPC_:PrimmDeputy, NPC_:PrimmResidentFemale1TEMPLATE, NPC_:PrimmResidentFemale2, NPC_:PrimmResidentMale3, NPC_:PrimmResidentMale4 (+13) |
| setbroadcaststate | 24 | 24 | 16 | 0 | obj 17 TIF 7 | ACTI:BMDJBoothEntryTrigger, ACTI:NVCGRadioActivator, ACTI:nvRepconLaunchButton, NPC_:VMSTopsBillyKnight, NPC_:VMSTopsBruceIsaac, NPC_:VMSTopsLonesomeDrifter (+8) |
| setobjectivecompleted | 21 | 21 | 19 | 0 | QF 6 obj 5 TIF 5 TM 3 QS 2 | ACTI:VCG01SkullBrahminActivator, MISC:VCG01SkullBrahmin, NPC_:AliceMcLafferty, NPC_:PrimmDeputy, NPC_:PrimmResidentFemale1TEMPLATE, NPC_:PrimmResidentFemale2 (+12) |
| pcb | 21 | 21 | 13 | 0 | obj 21 | ACTI:EndingTrigger, ACTI:GenericPurgeCellBufferTrigger, ACTI:VHDIndependentStartTrigger, ACTI:VStripMQEventHolder, ACTI:VStripNorthCodeHolder, ACTI:VStripSouthCodeHolder |
| removefromallfactions | 19 | 0 | 12 | 0 | TIF 18 obj 1 | NPC_:RoseofSharonCassidy, vDialogueGomorrah |
| openteammatecontainer | 19 | 0 | 19 | 0 | TIF 14 obj 5 | NPC_:VMS18HeadWaiter, NPC_:VMS18Marjorie, NPC_:VMS18Mortimer, NPC_:VMS18WhiteGloveAF, NPC_:VMS18WhiteGloveBartender, NPC_:VMS18WhiteGloveCF (+5) |
| resurrectactor | 19 | 0 | 3 | 0 | obj 19 |  |
| setactorfullname | 17 | 17 | 12 | 0 | TIF 11 obj 6 | ACTI:HVDeathTrackerTrigger, ACTI:SVEntranceTrigger, CREA:BMRhonda, CREA:V22Koch, VFreeformFreeside, VMS02 (+1) |
| getcurrentaiprocedure | 17 | 17 | 9 | 17 | PF 16 obj 1 | ACTI:VFSOrrisConcernedTrigger |
| resetinventory | 17 | 17 | 3 | 0 | QS 15 obj 2 | CONT:SafehouseRefrigerator, VEFR00LegionMix2CaesarsHire, VEFR01LegionGood2CaesarsFavor |
| setpackduration | 12 | 12 | 12 | 0 | PF 11 obj 1 | ACTI:HVBathroomStallTrigger |
| getisalerted | 12 | 0 | 1 | 12 | obj 12 |  |
| setrumble | 10 | 10 | 1 | 0 | QS 10 | ControlRumble |
| addspecialpoints | 10 | 10 | 1 | 0 | QF 10 | Generic |
| setcellpublicflag | 10 | 10 | 3 | 0 | obj 8 TIF 2 | ACTI:NVCCSetInteriorsActivator, DOOR:vCCHQDoor, VMS18 |
| startradioconversation | 9 | 9 | 7 | 0 | obj 6 QS 2 TIF 1 | ACTI:HanlonSuicideScript, ACTI:TopsPerformerActivator, ACTI:nvRepconLaunchButton, Lilysmedicinetimer, TACT:FFEU07RadioBeacon, VDialogueRaul (+1) |
| playmusic | 9 | 9 | 9 | 0 | obj 5 QS 2 QF 1 TIF 1 | ACTI:ControlPanelHeliosTower, ACTI:VStripStingerTrigger, FadeToCreditsTimer, VCG00, VEnding, VHDKimballSpeech |
| isplayerinregion | 9 | 9 | 9 | 9 | obj 6 QS 3 | NPC_:VHDCatoHostilius, VEFR00LegionMix2CaesarsHire, VEFR01LegionGood2CaesarsFavor, VMQ03a |
| damageobject | 8 | 0 | 5 | 0 | obj 8 | ACTI:VHDVertibirdKimballEncount01, ACTI:VMS08TrainExitTrigger |
| getfurnituremarkerid | 8 | 8 | 3 | 7 | obj 8 | NPC_:DocMitchell, NPC_:VFSJulieFarkas |
| useweapon | 8 | 8 | 8 | 0 | obj 7 TIF 1 | ACTI:ControlPanelHeliosTower, ACTI:trapDukeNeonFactory01, ACTI:trapDukeNeonFactory02, ACTI:trapDukeNeonFactory03, ACTI:trapDukeNeonFactory04, NPC_:VMS21BigSal (+2) |
| triggerscreensplatter | 8 | 8 | 1 | 0 | QF 8 | VCG00 |
| isdlcinstalled | 8 | 8 | 1 | 8 | QS 8 | VDLCPackQuest |
| getpermanentactorvalue | 7 | 0 | 7 | 7 | obj 7 | MISC:BobbleheadAGL, MISC:BobbleheadCHA, MISC:BobbleheadEND, MISC:BobbleheadINT, MISC:BobbleheadLUK, MISC:BobbleheadPER (+1) |
| islimbgone | 7 | 7 | 4 | 7 | obj 7 | CREA:NVCrGiantMantis, CREA:NVCrGiantMantisEssential, NPC_:1ECookCook, NPC_:1EDriverNephi, NPC_:1EFiendViolet |
| gettalkedtopc | 7 | 7 | 5 | 7 | TIF 4 QS 2 obj 1 | ACTI:FortCaesarTentTrigger, VMQTops, VMQYesMan02, VMS07 |
| getobjectivedisplayed | 7 | 7 | 6 | 7 | obj 5 QS 1 QF 1 | ACTI:VCG01SkullBrahminActivator, MISC:VCG01SkullBrahmin, VMS16b, nVPrimmDeputyConv |
| setquestobject | 7 | 7 | 2 | 0 | QF 6 obj 1 | NPC_:VFSGloriaVanGraff, VMS29a |
| setvatstarget | 7 | 7 | 7 | 0 | obj 7 | ACTI:TrapBabyCarriage, ACTI:TrapComputerBack, ACTI:TrapGrenadeBunch, ACTI:TrapMailboxBomb01, ACTI:TrapTripwire01, ACTI:VHeliosTrapLaserTripwire |
| isweaponinlist | 7 | 0 | 7 | 7 | obj 7 | ACTI:TrapGasFire01, ACTI:V22Cave2DoorBusterTrap, ACTI:V22TrapGasFire01 |
| setcriticalstage | 6 | 6 | 3 | 0 | obj 6 |  |
| sendtrespassalarm | 6 | 0 | 6 | 0 | obj 3 QS 3 | ACTI:VFSAWOffLimitsTrigger, ACTI:VULCashierTrigger, VTopsSecurity, VUltraLuxeSecurity, vDialogueGomorrah |
| getcontainer | 6 | 6 | 3 | 1 | obj 6 | ARMO:NVLegionExplorerAuraToken |
| showblackjackmenuparams | 5 | 5 | 5 | 0 | obj 5 | ACTI:BlackjackTableGomorrah, ACTI:BlackjackTableTheTops |
| getownerlasttarget | 5 | 5 | 5 | 0 | obj 5 | WEAP:WeapCattleProd, WEAP:WeapNVBoxingTape |
| getiscreaturetype | 5 | 5 | 5 | 5 | obj 5 | WEAP:WeapNVBoxingTape |
| ishardcore | 5 | 5 | 5 | 5 | obj 2 QS 2 QF 1 | ACTI:HVBunkerExplosionTrigger, CGTutorial, VNPCFollowers |
| isps3 | 5 | 5 | 5 | 5 | TIF 2 obj 2 QS 1 | ACTI:VERT2NiptonCaravanCodeHolder, ComplexSceneScriptPS3, VDialogueMrHouse, VMQTops |
| getanimaction | 5 | 5 | 5 | 5 | obj 5 | CREA:BMNightkinMobPatrol, CREA:BMNightkinRoadAmbusher, CREA:CrSuperMutant3NightkinGunA, CREA:CrTestSuperMutant1NightkinGunA, CREA:CrTestSuperMutant2Nightkin, CREA:CrTestSuperMutant3Nightkin (+3) |
| showrecipemenu | 5 | 5 | 5 | 0 | obj 4 TIF 1 | VDialogueVeronica |
| isgoredisabled | 5 | 5 | 5 | 5 | obj 5 |  |
| isplayermovingintonewspace | 5 | 5 | 4 | 5 | obj 3 QS 2 | ACTI:EuclidTarget, ACTI:VCCBarkActivator, VEuclidQuest, VMQ03a |
| systemsave | 5 | 5 | 5 | 0 | obj 5 | CREA:L38YesMan, CREA:MrHouse, CREA:NVTESTSYesMan, CREA:VHDYesMan, CREA:YesManMainframe, NPC_:FortCaesar (+2) |
| getshouldattack | 5 | 5 | 4 | 5 | obj 4 QF 1 | ACTI:GSJoeCobbTrigger, ACTI:VMS18TedReturnTrigger, ACTI:VMS33OmertaThugTrigger, VMS13 |
| placeleveledactoratme | 5 | 5 | 2 | 0 | obj 5 |  |
| showroulettemenuparams | 5 | 5 | 5 | 0 | obj 5 | ACTI:GomorrahRouletteTable, ACTI:RouletteTableTheTops, ACTI:RouletteTableUltraLuxe |
| hasbeeneaten | 5 | 5 | 2 | 5 | QS 4 obj 1 | MeatOfChampions, NPC_:VMS18CarlyleStClair |
| setlevel | 5 | 5 | 2 | 0 | QS 4 obj 1 | ACTI:VCG04Activator, PressDemoQuest |
| fireweapon | 5 | 5 | 5 | 0 | obj 5 | ACTI:TrapPitchingMachine01, ACTI:trapShotgun |
| setsecexp | 5 | 5 | 5 | 0 | TIF 5 | vFreeformTheStreet02 |
| sgtm | 5 | 5 | 1 | 0 | obj 5 |  |
| flip | 5 | 5 | 1 | 5 | obj 5 | ACTI:ControlPanelHeliosTower |
| getcasinowinningslevel | 5 | 0 | 5 | 5 | QS 3 obj 2 | VCasinoCompsUltraLuxe, vCasinoCompsGomorrah, vCasinoCompsTheTops |
| getpcmiscstat | 4 | 4 | 2 | 4 | obj 2 QS 2 | CGTutorial |
| isinlist | 4 | 4 | 4 | 4 | obj 4 | ACTI:TrapGasCloudTrigger |
| setnpcradio | 4 | 4 | 3 | 0 | obj 3 QS 1 | CREA:Lily, Lilysmedicinetimer |
| behemoth | 4 | 4 | 4 | 4 | QF 4 | VHDHouseBattle, VHDIndependentBattle, VHDLegionBattle, vHDBattleController |
| getobjectivecompleted | 4 | 4 | 2 | 4 | QF 4 | VMS16b, VMS41 |
| enablenavmesh | 4 | 4 | 1 | 0 | obj 4 |  |
| showslotmachinemenuparams | 4 | 4 | 4 | 0 | obj 4 | ACTI:vGomorrahSlot01, ACTI:vTopsSlot01, ACTI:vVikkiAndVanceSlot01, ACTI:vVikkiAndVanceSlot02, ACTI:vWranglerSlot01, ACTI:vWranglerSlot02 |
| setcs | 4 | 4 | 4 | 0 | obj 3 TIF 1 | NPC_:vHDLVLCLCenturionPowerStation, NPC_:vHDLVLCLLegionaryPowerStation, NPC_:vHDLVLNCRRangerPowerStation, VNPCFollowers |
| addtopic | 4 | 4 | 4 | 0 | TIF 2 obj 1 QS 1 | ACTI:VMS21SalsTrigger, VMS21, vDialogueEDE |
| isincriticalstage | 4 | 4 | 2 | 4 | TIF 4 | VMS29a |
| resetquest | 4 | 0 | 4 | 0 | QS 2 obj 2 | VEFR00LegionMix2CaesarsHire, VEFR01LegionGood2CaesarsFavor |

Under 4 markers each (52 functions, 96 markers): attachashpile 3, setallvisible 3, setnoavoidance 3, placeatreticle 3, getignorecrime 3, playbink 3, setforcesneak 3, pipboyradio 3, setpcsleephours 3, isplayergrabbedref 3, getcurrentaipackage 3, wakeuppc 3, getcontainerinventorycount 3, ispc1stperson 2, addcardtoplayer 2, setallreachable 2, setsceneiscomplex 2, forcesave 2, enableloadingmenu 2, setitemvalue 2, showtutorialmenu 2, agerace 2, setglobaltimemultiplier 2, setscreensplatterfade 2, getplayername 2, autodisplayobjectives 2, showbarbermenu 2, sethardcore 2, setpublic 2, getfriendhit 2, cleardestruction 2, detonateplacedexplosives 1, preloadmagiceffect 1, exitgame 1, setdisposition 1, isidleplaying 1, purgecellbuffers 1, getxpfornextlevel 1, addtagskills 1, showallmapmarkers 1, setpccanusepowerarmor 1, clearscreensplatter 1, resetpipboymanager 1, trapupdate 1, resetxp 1, pipboyradiooff 1, setinchargen 1, setminimaluse 1, isspelltarget 1, ne 1, gethitlocation 1, createdetectionevent 1.

Prose notes, not functions: the source compiler 18, unreachable after Return 13, undeclared var 6.

## <a id="ranking"></a>Ranking by gameplay effect

Ranked by what a player loses, then by count. Tier 1 breaks a quest, a
companion or a reward; tier 2 changes how a scene plays; tier 3 is cosmetic or
has nothing to change on Fallout 4.

| # | Function | Effect while inert | State |
|---|---|---|---|
| 1 | SetPlayerTeammate | Hired companions never become teammates: no command wheel, no shared combat or sneaking. 139 sites, mostly hire/fire lines | [Built](#built) |
| 2 | MoveToMarkerWithFade, MoveToFade | Scripted moves never happen: Pit and Thorn fighters, Strip escorts, Hoover Dam pre-battle Rangers, companions sent to wait. 263 sites | Built |
| 3 | KillActor | Scripted deaths never happen: executions, quest outcomes, gib scenes. 143 sites | Built |
| 4 | EnterTrigger | Code-box scripts never run: the Pit fighter prep (81 sites), Sarah's cash count, the hit-squad boxes. 99 sites | Built for 94 |
| 5 | GetCasinoWinningsLevel | The comp guard lost its winnings term, so comps ran every poll (the Ringo stall) | Reads 0 until the [casino work](fo4_build_next.md#casino) |
| 6 | RemoveAllTypedItems | Weapons are not taken at the Tops, Ultra-Luxe, Gomorrah, Silver Rush and the Fort, and companions' "give back my gear" does nothing. 273 sites | [Built](#removealltypeditems) (Fallout 4) |
| 7 | GetPermanentActorValue | Bobbleheads never raise their S.P.E.C.I.A.L. (the `< 10` guard read `false`) | Built |
| 8 | AddFormToFormList | Nellis boomer-kid gift and grudge lists never fill. 35 sites | Built |
| 9 | OpenTeammateContainer | The companion "let's trade" line opens nothing. 19 sites | Built |
| 10 | RemoveFromAllFactions | VMS21 (Nero, Big Sal) and Cass keep their old factions. 19 sites | Built |
| 11 | ResurrectActor | Resurrected NCR support and quest NPCs stay dead. 19 sites | Built |
| 12 | DamageObject (`do`) | Hoover Dam generators, Tesla chains and traps take no damage. 76 sites | Built |
| 13 | IsImagespaceActive | Fade waits; already passing, now an explicit 0. 32 conditions | Built |
| 14 | IsWeaponInList, GetIsAlerted, SendTrespassAlarm, ResetQuest | Gas traps, Goodsprings gecko checks, casino alarms, emergency-radio quest resets. 29 sites | Built |
| 15 | IgnoreCrime | Fallout 4's IgnoreCrime is a stub ([R8](research/fo4_target.md)); 185 sites | Nothing to build |
| 16 | SetObjectiveDisplayed/Completed | The source names objectives its quest never authors (47 sites); correct as inert | Nothing to build |
| 17 | ShowCaravanMenu, Show*MenuParams | Caravan and casino games; need their own UI (41 sites) | Not built |
| 18 | SetCombatStyle, SetPackDuration, GetCurrentAIProcedure, SetActorFullName, ResetInventory | No Papyrus counterpart on Fallout 4 (117 sites) | Not built |
| 19 | SetBroadcastState, StartRadioConversation, PlayMusic | Radio and music cues (42 sites); need the F3NV radio helper to expose a switch | Not built |
| 20 | AddAchievement, SetSecuritronExpression, setRumble, PCB, ForceTerminalBack | Achievements, face screens, controller rumble, cell buffers, terminal menus (204 sites) | Tier 3 |

## <a id="built"></a>Built

Rows live in `constants_falloutnv.FALLOUT_COMMAND_ROWS` (FO3/FNV spellings)
and `command_rows.COMMAND_ROWS` (shared). All are vanilla natives that both
Fallout 4 and Skyrim declare, so the Skyrim target gets them too. Markers fall
from 2,156 to 1,276; the casino-style dropped `&&` term from 82 lines (57
scripts) to 45 (37).

| FNV | Papyrus | Notes |
|---|---|---|
| <a id="killactor"></a>KillActor | `Actor.Kill(killer)` | Kill's long name; same row as `kill` (killer only) |
| ResurrectActor | `Actor.Resurrect()` | Same row as `resurrect` |
| SetPlayerTeammate *n* | `Actor.SetPlayerTeammate(n)` | Default 1; FO4's favor flag stays on |
| <a id="moves"></a>MoveToMarkerWithFade, MoveToFade | `MoveTo(marker)` | The MoveTo handler. FNV fades only the player's screen; the move itself is the same |
| IsImagespaceActive | `0` | Only waited on the fade above, which no longer plays |
| <a id="entertrigger"></a>*trigger*.EnterTrigger *actor* | `(trigger as <its script>).OnTriggerEnter(actor)` | Only when the trigger's script authors `OnTriggerEnter` and no `OnTrigger`. On Fallout 4 an `OnTrigger` body becomes a loop that runs until a leave event, which a forced entry never sends. The other 5 sites stay markers |
| <a id="casino"></a>GetCasinoWinningsLevel | `0` | No casino game runs in the converted build, so no comp is owed. The guard now reads `If 0 == 1 && SmallFry == 0`. A stopgap: the real read waits on the [casino work](fo4_build_next.md#casino), which tracks winnings per casino against the CSNO Max Winnings |
| <a id="permanent-av"></a>GetPermanentActorValue, GetPermAV | the AV handler's base read | S.P.E.C.I.A.L. reads through `TES4Polyfill.GetTES4ActorValue`, which on Fallout 4 is the actor value itself |
| AddFormToFormList *list* *form* | `list.AddForm(form)` | |
| OpenTeammateContainer | `Actor.OpenInventory(True)` | On the speaker in a topic info |
| RemoveFromAllFactions | `Actor.RemoveFromAllFactions()` | |
| DamageObject, `do` | `DamageObject(n)` | `do` is DamageObject's short name |
| SendTrespassAlarm *actor* | `Actor.SendTrespassAlarm(actor)` | |
| ResetQuest *quest* | `Quest.Reset()` | |
| IsWeaponInList *list* | `(list.HasForm(actor.GetEquippedWeapon()) as Int)` | Bare-handed reads None, which no list holds |
| GetIsAlerted | `Actor.IsAlerted()` | |

EnterTrigger needed the source's trigger blocks: `cross_ref` now records the
blocks each script authors (`trigger_blocks`, from `authored_trigger_blocks`),
and `record_script_edid` gives a record's script EditorID (placed refs fall
back to their base), which `get_record_script_type` now uses too.

KillActor exposed one older bug: assigning `Self` to an `Actor` variable
emitted `Self as Actor`, which Fallout 4's compiler rejects from a script that
extends ObjectReference. `ScriptConverter._cast` now uses `self_as_actor()`
(`(Self as ObjectReference) as Actor`), which also fixed `GenericKillSCRIPT`.

Checked on the full corpus (scratch output, not `temp/fo4_scripts`):

- **Compile** (`tools/script/compile_papyrus.py --game fallout4`): 16 of 17,482
  scripts fail, down from 17. All 16 are older error kinds (native-only events,
  an Enchantment cast).
- **Blast radius:** 445 scripts change. Every changed line is one of the calls
  above, the property retype that goes with it (`Actor Property linkedRef`,
  `GetLinkedRef() as Actor`), a folded `0` guard, or the `extends Actor` that
  bare KillActor gives `DeadNCRSoldierScript` and
  `CrimsonCaravanTraderBrahminScript`. No record carries either script.

Tests: `tests/test_script_markers_falloutnv.py`.

### <a id="removealltypeditems"></a>RemoveAllTypedItems (Fallout 4 only)

`[from.]RemoveAllTypedItems <to> [keepOwner] [silent] [type] [except]` moves
every item of one form type from the caller to `<to>` (none: destroyed),
except the items in a FormList. The third argument suppresses the
"item added" message (the GECK wiki); it is not a quest-item flag. With no
type code FNV moves everything: the Fort strips the player with
`player.RemoveAllTypedItems FortPlayerEquipmentContainerRef` and gives it back
the same way.

The type codes are FNV's form types (`kFormType` in xNVSE's `GameForms.h`):
24 armor, 25 book, 26 clothing, 31 misc, 40 weapon, 41 ammo, 46 key,
47 ingestible, 49 note, 103 weapon mod. Of FNV's 273 live lines, 113 pass 40,
63 no type, 37 pass 47, and 15 each pass 24, 26, 31 and 41 (the Arcade gear
swap). FNV
has no clothing records, so 26 moved nothing there and its list here is empty.

Vanilla Fallout 4 Papyrus cannot walk an inventory by type, but `RemoveItem`
takes a FormList and moves every listed item with a count of -1. So:

- `script_convert` (`commands_falloutnv.remove_all_typed_items`) emits
  `TES4Polyfill.RemoveAllTypedItems(from, to, keepOwner, silent, code,
  TES4ItemType<code>, except)`. `ITEM_TYPE_LISTS` in `constants_falloutnv`
  names each code's FormList property. A type code that is not a literal
  inventory code stays a `;NE:` note. Skyrim keeps the old line: it has no
  type lists.
- The Fallout 4 build (`spike.items.Items.type_list`) binds that property
  while filling script properties and writes the list at the end of the build
  (`write_type_lists`, from `build_finish._lists`). The list holds the FO4 form
  made for every FNV item of that type (`items.made`), plus shared stand-ins.
  Its FormID is `derive_formid('FLST', 'TES4ItemType<code>')`, the same scheme
  as the weapon animation lists. Only lists a script names are written.
- The polyfill (`static_scripts/fallout4/overrides/TES4Polyfill.psc`) counts
  the exception items first, moves the type list (`RemoveItem(list, -1,
  silent, to)`, or `RemoveAllItems(to, keepOwner)` for type 0), then moves back
  only what it took of each exception (`AddItem` when there is no target).

Drift from FNV: ownership is kept only for type 0, because Fallout 4's
`RemoveItem` has no ownership flag. Items the build never made (none can be
in an inventory) are not in a list.

Checked on a scratch reconversion: all 273 sites in 36 scripts now call the
polyfill and no RemoveAllTypedItems marker is left. The Fallout 4 compile
gate still fails the same 16 of 17,482 scripts, all older error kinds.

Tests: `tests/test_script_markers_falloutnv.py`,
`tests/test_fo4_items_audit.py`.

### <a id="getanimaction"></a>GetAnimAction (Fallout 4 only)

FNV's `GetAnimAction` reads what special action an actor is animating
(GECK: -1 none, 0 equip, 1 unequip, 2 attack, 3 to 5 attack follow-through
and throws, 6 block, 7 recoil, 8 reload, and more). All 5 FNV scripts use it
to ask "is this actor attacking":
- **Nightkin.** `CrNightkinSCRIPT` and `CrNightkinCloakUntilFireScript` test
  `== 2`. `CrNightkinGunScript` tests `>= 2 && <= 6`, and in its `ElseIf`
  `< 2 || > 6`. The nightkin decloak while attacking.
- **Lily.** `LilyScript` tests `== 2` and drops her Stealth Boy.
- **Pew Pew.** `WeapPewPewScript` tests `Owner.GetAnimAction == 2` and fires
  a second shot.

The read used to be an inert 0 that dropped out of its `&&`. So the nightkin
decloaked on every poll, and the gun nightkin toggled every pass (the
[creatures spike](fo4_spikes.md#spike-4-creatures)).

Fallout 4 has no anim-action read, but an actor's behavior graph sends attack
events a script can register for. In a play log (2026-10-31) the player sent
`attackState`, `WeaponFire` and `attackStop`, and nightkin sent `HitFrame`,
`weaponDraw` and `attackStop`. So on Fallout 4:
- **The read.** `anim_action_falloutnv.anim_action` turns the call into
  `TES4_AnimAction(<actor>)`, with the implicit actor resolved as for any
  reference call.
- **The helper.** `anim_action_falloutnv.listen` writes `TES4_AnimAction`
  into the script and its lines into the script's `OnAnimationEvent`, beside
  an OnFire body if there is one.
  - It registers on the actor for the starts `weaponFire`, `HitFrame` and
    `weaponSwing`, and for the ends `attackStop`, `AttackEnd` and
    `readyState`. It registers again whenever the actor or its 3D load state
    changes.
  - It reads 2 from a start until an end, or until 2 s after the last start
    when no end comes, else -1. Each shot of a held trigger is a new start,
    so a minigun keeps reading 2.
  - An attack that starts and stops between two reads still reads 2 for
    one pass: 0.1 s from the first read that sees it. So a script polling
    every 0.5 s doesn't miss a melee swing, and a condition that reads it
    twice (the gun nightkin's `>= 2 && <= 6`) gets the same answer both times.

<a id="attack-event-order"></a>**Which events start and end an attack
(changed 2026-11-01).** The first set also counted `attackState`,
`attackStart` and `rangedAttackStart` as starts, and ended only on
`attackStop` and `AttackEnd`. On the 13:25 build a gun nightkin then read as
attacking for good, so it never re-cloaked. Evidence, from `TES4TRACE|Anim`
lines in Papyrus logs:
- **A gun** (gun nightkin, 13:25 build): all 7 `WeaponFire` events were
  followed by `readyState`, 0.05 to 1.8 s later (median 0.12). There was
  1 `AttackEnd` against 16 `readyState`.
- **`attackState`** came in pairs, in and out of an attack, followed by
  `initiateStart`, so it marks no start.
- **Melee** (that nightkin unarmed, 2026-10-31 build): all 3 `HitFrame`
  events ended in `attackStop` 0.85 to 1.0 s later, with no `readyState`.
- **Vanilla:** no script registers for `attackState`, `attackStart`,
  `rangedAttackStart` or `attackStop`. Of the vanilla scripts that track
  attacks, 14 use `WeaponFire` and 3 use `weaponSwing`. The closest case,
  `AssaultronHeadModStealthScript`, drops its cloak on `weaponSwing` and
  re-cloaks 0.75 s later with no end event, so a timed end is vanilla's
  pattern too.

No log covers a flamer, a thrown weapon or a creature's natural attack. For
those, the 2 s end applies when no end event comes.

Drift from FNV: block (6), recoil, reload and the other actions read -1.
Skyrim keeps the inert 0.

Tests: `tests/test_script_markers_falloutnv.py`.

### <a id="effect-shaders"></a>Effect shader properties (Fallout 4 only)

The build writes no FNV effect shader (EFSH) record. Fallout 4's EFSH (form
version 106) has no particle shader, and FNV's effect textures (`Effects\FX*`)
don't ship. So every converted `EffectShader` property was empty. In FNV's
scripts, 38 properties in 29 scripts name 15 shaders, through 61 `Play` and
`Stop` calls. A call on an empty property fails. `CrNightkinGunScript` plays
`NightkinCloakFXShader` before re-adding `StealthBoyInvisibilitySpell`, so a
gun nightkin that uncloaked to fire never cloaked again
([creatures spike](fo4_spikes.md#spike-4-creatures)).

`fo4_import/data/effect_shaders.json` names the Fallout4.esm shader each FNV
shader plays as. `spike.effect_shaders` resolves it when the attach step fills
an `EffectShader` property, matching the property's name to FNV's shader
ignoring case. A shader the table leaves out stays empty and is counted
(`EffectShader not mapped`).

| FNV shaders | Fallout 4 shader |
|---|---|
| `NightkinCloakFXShader` | `StealthBoyInvisibilityEffect` (vanilla's stealth boy) |
| `PulseDisableFXShader`, `DLC03TeslaFXShader`, `MQ11FFDisableFXShader`, `MQ11ff1` | `ShockDamageFXS` |
| `LaserCritGlowFXShader`, `effectLaserDisintegration` | `CritLaserFXS` |
| `AlienCritGlowFXShader`, `effectAlienDisintegration`, `MQ11ff2` | `CritAlienFXS` |
| `GooShader01`/`02`, `PlasmaGooification*`, `effectAtomization` | `CritPlasmaFXS` |
| `Flames01` / `SmokeFlameBurn` | `FireFXS` / `CritFireCharFXS` |
| `Smoke01`, `Smoke02pulse`, `PuffOfSmoke*`, `MQ11ff3` | `RobotFireFXS` |
| `GlowingOneFXShader`, `DLC03GhoulFXShader` | `LegendaryRadiationFXS01` |
| `NukeAtomShader` | `RadDamageFXS` |
| `fxSearchAndMark`, `fxSpotterShader`, `fxCateye`, `LifeDetected` | `DetectLifeFXS` |

All 15 shaders the scripts name now resolve. Five of FNV's 35 have no entry,
and no script names them: `VTSFadeOut`, `HaroldLiniment`, `HaroldSap`,
`effectReflect` and `effectAbsorb`.

Drift from FNV: each plays FO4's look, not FNV's, so for example the nightkin
shimmer is the stealth boy's. The table is data, so a profile can change any
entry.

Tests: `tests/test_fo4_effect_shaders.py`.

### <a id="setforcesneak"></a>SetForceSneak (Fallout 4 only)

FNV has 3 sites, all in nightkin scripts:
- `REPCONSuperMutantNightkinSCRIPT` sets `refvar.SetForceSneak 1` out of
  combat and `0` in combat.
- `VNovacChupacabraNightkinSCRIPT` sets `0` in combat.

FNV uncloaks them within 400 units of a combat target. Fallout 4 has one
native, `Actor.StartSneaking()`, and nothing that ends a sneak: no stop
function, actor value or F4SE call. Vanilla uses it for the player only, in
`DLC03MQ03` and `RoboticsExpert03`.

So on Fallout 4, `SetForceSneak 1` becomes `<actor>.StartSneaking()`
(`commands_falloutnv.force_sneak`), and `0` stays a `;NE:` note.

Drift from FNV: StartSneaking starts the sneak but doesn't hold it, so the
actor's AI can stand it up. FNV's force holds until `0`. The REPCON script
polls every 0.5 s, so it starts the sneak again on each pass out of combat.
In combat, the AI chooses the stance. Skyrim keeps the note.

Tests: `tests/test_script_markers_falloutnv.py`.

### <a id="dropped-terms"></a>Inert terms in `&&` chains

An inert comparison inside a chain drops out, which widens an `&&`
([policy](../commentary/script_convert.md#comparing-an-inert-operand)). This
made the nightkin decloak on every poll; GetAnimAction now has a real read
instead.

**Fail closed: tried and reverted (2026-10-31).** Reading such a term as
`false` whenever 0 fails its test (`== 2`, `== 1`) fixed some guards and
blocked others outright, on a scratch FNV reconversion of 26 scripts. A
guard that never fires can block a quest; one that fires early mostly
doesn't, so widening stays the default:
- **Fixed by it:** the giant mantis legs (`IsLimbGone` fired at once) and
  Cass's region barks (she said the Goodsprings line everywhere).
- **Blocked by it:**
  - Camp Golf's shooting range: 8 Misfits package fragments wait on
    `GetCurrentAIProcedure == 17`;
  - the Legion messenger (VEFR00/01, `IsPlayerInRegion vMapCanAttackPCHere`);
  - Victor at Boulder City (VES01b);
  - VMS07's `AndersSpokenTo`, Arcade's Caesar rant and two Racket lines
    (`GetTalkedToPC`).

Census on FalloutNV.esm (2026-10-31, before GetAnimAction): 45 lines in 37
scripts dropped a term from an `&&`:

| Function | Lines |
|---|---|
| `;NE: TODO:` (IsLimbGone, IsDLCInstalled, GetIsCreatureType) | 9 |
| GetCurrentAIProcedure | 8 |
| GetTalkedToPC | 6 |
| GetAnimAction | 5 |
| GetShouldAttack | 4 |
| IsPlayerInRegion | 3 |
| GetObjectiveDisplayed, IsPlayerMovingIntoNewSpace, GetFurnitureMarkerID, GetCurrentAIPackage | 2 each |
| GetObjectiveCompleted, IsHardcore | 1 each |

<a id="native-read-follow-ups"></a>**Follow-ups: native reads, one at a time.**
Each of these dropped out of a guard and needed its own Fallout 4 read. All
five are built 2026-11-06, not played:
- **GetCurrentAIProcedure** (8 lines): Camp Golf's shooting range started
  when any one Misfit arrived, not once all reach procedure 17
  ([AI procedure](fo4_pipeline.md#ai-procedure)).
- **IsPlayerInRegion** (3 lines, plus Cass's barks): the Legion
  messenger came anywhere outdoors, and Victor's Boulder City scene wasn't
  tied to Boulder City ([regions](fo4_regions.md#built)).
- **Cass's region barks** (`VCassTimerGeneralBarkScript`, 26 branches that dropped their region test, such as
  `bCassBarked == 0 && IsPlayerInRegion <region> == 1`): the first branch
  always passed, so she said the Goodsprings line wherever she was
  ([regions](fo4_regions.md#built)).
- **GetTalkedToPC** (6 lines): VMS07 set `AndersSpokenTo` on its first
  poll, Arcade's Caesar rant needed no talk with Caesar, and the Racket TIF
  checks passed ([AI procedure](fo4_pipeline.md#ai-procedure)).
- **IsLimbGone** (2 lines): the giant mantis marked each leg gone on its
  first pass ([AI procedure](fo4_pipeline.md#ai-procedure)).

<a id="creature-type"></a>**The last two, built 2026-11-06, not played** (the
`;NE: TODO:` row of the census above):
- **GetIsCreatureType** (3 lines: the boxing gloves and tape,
  `GetIsCreatureType 6 != 1`): their knockout hit robots too. It is now
  `<actor>.HasKeyword(FNV_CreatureType<type>)`, the keyword the build stamps
  on every converted creature for dialogue's type tests
  ([type tests](fo4_perks.md#type-tests)); the script property is filled
  with that keyword (`attach._type_keyword`). A creature in a DLC plugin
  carries the DLC's copy of the keyword, so a base-game script tests the
  base copy only.
- **IsDLCInstalled** (8 lines, the packs' `VDLCPackQuestSCRIPT`): every
  "installed" branch read 0, so the pack items were never marked given. It
  is now `Game.IsPluginInstalled("<name>.esm")`, the name with its spaces
  dropped ("Tribal Pack" is `TribalPack.esm`, as the packs build).

## <a id="not-built"></a>Not built

- **The rest** of tier 2 and 3 above have no vanilla Papyrus counterpart, or
  need a UI or helper first.

## <a id="measuring"></a>Measuring again

Reconvert into a scratch folder and count with the census tool:

```bash
python -m script_convert.pipeline export/FalloutNV.esm -o <scratch> --target fallout4
python -m tools.audit.script_marker_census <scratch> export/FalloutNV.esm --json census.json
```
