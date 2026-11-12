# Script functions Fallout 4 does not track (plan)

How the converter can finish the FNV script functions that still convert to
nothing on Fallout 4, and cut the cost of the generated poll code while it
is in the same files. Status lives in [ROADMAP](ROADMAP.md) only. Phase 1
(the decision table and the census tool) is done; the rest is design.

## Contents

- [1. Goal and rows](#goal)
- [2. What exists](#exists)
- [3. The framework](#framework)
- [4. Phases](#phases)
- [5. What the play test should tell us first](#play-test)
- [6. Open questions](#open)

## <a id="goal"></a>1. Goal and rows

Every FNV script function either does what FNV did, or is marked on
purpose as having nothing to do on Fallout 4. Each function gets one row in
one decision table, and every function that needs state Fallout 4 does not
keep uses one shared way to remember it. The poll cost fixes ride along,
because they change the same generated code.

| Issue-plan row | Size | Doc |
|---|---|---|
| [Unconverted script functions](fo4_issue_plan.md#large) | L | [not built](script_markers.md#not-built) |
| [Scripts waiting on object animations](fo4_issue_plan.md#medium) | M | [census](fo4_idles.md#census) |
| [Companion status barks (91)](fo4_issue_plan.md#medium) | M | [barks](fo4_pipeline.md#companion-barks) |
| [Crime infamy](fo4_issue_plan.md#medium) | M | [standings](fo4_pipeline.md#standings) |
| [Papyrus cost 2 to 4](fo4_issue_plan.md#medium) | M | [performance](performance.md#papyrus) |

## <a id="exists"></a>2. What exists

**The marker census, rerun.** A scratch reconversion
(`python -m script_convert.pipeline export/FalloutNV.esm -o <scratch>
--target fallout4`, then `python -m tools.audit.script_marker_census
<scratch> export/FalloutNV.esm`) gives **806 markers in 420 scripts, 96
entries**: 93 functions plus 3 prose notes (37 markers). 79 markers sit on
an `If`/`ElseIf` line. An earlier count of 365 scripts came from the
one-off `temp/` script, whose JSON kept only the first 40 scripts per
function; the 406 scripts left without the prose notes are the ones a
function row touches. The 2026-10-31
[census](script_markers.md#census) had 2,156 in 740 scripts. Gone since:
the casino openers, the radio calls, `SetSecuritronExpression`,
`IsLimbGone`, `GetTalkedToPC`, `IsPlayerInRegion`,
`GetCurrentAIProcedure`, `IsHardcore`, `IsDLCInstalled`,
`GetIsCreatureType`, `GetAnimAction`. The largest left:

| Function | Markers | In a condition |
|---|---:|---:|
| IgnoreCrime | 185 | 0 |
| AddAchievement | 111 | 0 |
| SetCombatStyle | 54 | 0 |
| ForceTerminalBack | 30 | 0 |
| SetObjectiveDisplayed / Completed | 26 / 21 | 0 |
| PCB | 21 | 0 |
| SetActorFullName, ResetInventory | 17 each | 0 |
| SetPackDuration | 12 | 0 |
| SetRumble, SetCellPublicFlag | 10 each | 0 |
| GetFurnitureMarkerID | 8 | 7 |
| GetObjectiveDisplayed / Completed | 7 / 4 | 7 / 4 |

**How a function converts.** A row in `command_rows.COMMAND_ROWS` (shared),
`constants_falloutnv.FALLOUT_COMMAND_ROWS` (FO3/FNV spellings) or
`command_rows_fallout4.FALLOUT4_ROWS` (Fallout 4's replacement for a
Skyrim row), or a handler such as `commands_falloutnv.remove_all_typed_items`.
A row with no Fallout 4 call writes `0` or a `;NE:` note.
`command_rows_fallout4.py` sets `'isanimplaying': Cmd('0')`, so it is not
counted as a marker. FNV's source has 71 `IsAnimPlaying` matches in 35
scripts (most in `DLC03TeslaChainEffectScript` 16, `VVault21LightScript`
8, `VVault11GearDoorControlSCRIPT` 3, `PortaShelter01Script` 3, and the
vertibird scripts); [fo4_idles](fo4_idles.md#census) counts 69 in 34.

**State the converter already remembers.** Three patterns exist:
- *A script's own variables.* `anim_action_falloutnv.listen` writes
  `TES4_AnimAction` and its variables into the reading script, fed by its
  `OnAnimationEvent` ([GetAnimAction](script_markers.md#getanimaction)).
- *A helper quest.* `F3NV_PackageState` (`FalloutHelpers.esl` 0x902,
  `constants.FALLOUT4_HELPER_QUESTS`) holds parallel arrays of actors and
  packages, 128 slots, the oldest giving way; `TES4Polyfill.AIProcedure`
  reads it ([AI procedure](fo4_pipeline.md#ai-procedure)).
  `F3NV_CompanionBarks` keeps per-follower arrays the same way.
- *A helper actor value.* `TalkedToPC` (0x822, `FALLOUT4_HELPER_AVS`),
  set by `TES4Polyfill.Greeted` ([first meetings](fo4_pipeline.md#talked-to-pc)).

**The poll code** (`script_convert/assemble.py`, 1,601 lines):
- `poll` arms twice per tick through `_arm`, which wraps the re-arm in
  `_gate`: `TES4Polyfill.SafeGameModeGate(Self)`, plus the holder for a
  carried item (`_carried`). The gate calls `GetParentCell`, `Is3DLoaded`
  and `IsAttached`. In the scratch run, 553 scripts carry 5,236 gate calls.
- Generated object scripts already have `OnCellAttach` and `OnLoad`
  events (for example `FALLOUTNV_1EKeithScript`), which a flag can join.
- `_dialogue_gate` calls `TES4Polyfill.PlayerIsInDialogue` on every tick of
  a speaking script (77 scripts in the scratch run). It and `LineBegan` /
  `LineEnded` keep their state in `Variable04`–`Variable09` actor values.
  On Fallout 4, `helpers_fallout4.apply_rules` turns each of those reads
  into `GetValue(TES4Polyfill.AV(...))`, so each read is two calls.
- Cost item 4 of [performance](performance.md#papyrus) is already gone
  (that doc is inherited and left unedited; this is its record): `patrol_scripts.patrol_psc`
  makes each patrol marker's script a TopicInfo fragment the patrol data's
  topic runs on arrival (101 `_PM__` scripts in the scratch run). No
  `_WATCH` poll and no `FindClosestActorFromRef` call remain in
  `script_convert/*.py`.

**Companion barks.** `fo4_import/spike/companion_barks.py` builds the
watch quest; `F3NV_CompanionBarks.psc` checks followers each second for
`HealthHalf`, `HealthQuarter`, `Wake` and `NoAmmo`. The item-condition
plugin already gives `F3NV_Condition.GetEquippedWeaponHealth`
([condition](fo4_condition.md#built)), but NPC weapons do not wear in FNV
([NPC wear](fo4_condition.md#npc-wear)).

**Crime.** `fo4_import/spike/factions.py` writes `CRIME_VALUES` for
crime-tracking factions as arrest 0, attack on sight 1 and every crime
gold value 0. `F3NV_FalloutStandings.NoteCrime` charges infamy from the
Story Manager's crime-gold (ADCR) event, which may never fire at 0 gold
([standings](fo4_pipeline.md#standings)). FNV's `IgnoreCrime` stops one
actor reporting the player's crimes (GECK wiki); Fallout 4's console
handler for it is a stub ([R8](research/fo4_target.md#ai-rules)).

**Mesh timing.** `fo4_import/nif/animation.py` already reads each
NiControllerSequence's start and stop time when it converts an animated
mesh.

## <a id="framework"></a>3. The framework

**One decision table per function.** Every remaining function gets one
row in [not built](script_markers.md#not-built), in the first route that
works, in this order:

1. **Native.** A Fallout 4 Papyrus call does the same thing. Checked in
   the offline CK wiki, these exist and are not yet used:
   `Actor.SetCombatStyle`, `Cell.SetPublic`, `Game.ShakeController`,
   `Weapon.Fire`, `Actor.SetCriticalStage`, `Quest.IsObjectiveDisplayed`,
   `Quest.IsObjectiveCompleted`, `Game.QueryStat`,
   `ObjectReference.PlaceActorAtMe`, `MusicType.Add`.
2. **Remembered state.** Fallout 4 has the event but not the read, so a
   flag is set where the event happens and read where FNV asked.
3. **Build data.** The answer is fixed at build time (a clip length, an
   inventory list), so the converter writes it as a literal or a list.
4. **Nothing to do.** Inert is correct on Fallout 4 (`IsPS3`,
   `AddAchievement`, `PCB`, objectives the quest never authors).
5. **DLL.** Last, and only with the user's approval (below).

The table is data in the doc and in the rows themselves; a test per route
checks one function of each.

**One "remember this state" pattern.** One rule picks where state lives:
- read only by the script that writes it: a script variable, as
  `TES4_AnimAction`;
- written by one script and read by others: one new helper quest,
  `F3NV_State` (`FalloutHelpers.esl` 0x903, appended to
  `FALLOUT4_HELPER_QUESTS`, so no existing id moves). It holds keyed
  arrays like `F3NV_PackageState`: a reference, a value, a time, 128
  slots, the oldest giving way. `TES4Polyfill` gets one getter and setter
  per kind.

The cost fixes use the same pattern. Dialogue state (cost item 3) moves
from actor values into `F3NV_State` variables, and the load gate (cost
item 2) becomes a script variable. So the helper is built once and serves
the barks, `IsAnimPlaying`, `IgnoreCrime` and the dialogue gate.

**Why this covers the rows.** Every row here is "Fallout 4 does not keep
what FNV asked about": an animation's end, a companion's poisoning, a
crime flag, a speaker. Each answer is either a native, a remembered event,
or build data. The cost fixes are the same move applied to state the
converter already keeps badly.

### <a id="decision-table"></a>Decision table

Every function the census names, with its route (1 native, 2 remembered
state, 3 build data, 4 nothing to do, 5 DLL) and how. Natives were checked
in the offline Fallout 4 CK wiki. "To confirm" marks a route whose
behavior match is not yet read against the GECK wiki. Markers are from the
806-marker census above.

| Function | Markers | Route | How |
|---|---:|---|---|
| SetCombatStyle, setCS | 54, 4 | 1 | `Actor.SetCombatStyle` (setCS is its short name) |
| SetRumble | 10 | 1 | `Game.ShakeController` |
| SetCellPublicFlag, SetPublic | 10, 2 | 1 | `Cell.SetPublic` |
| PlayMusic | 9 | 1 | `MusicType.Add`, once the MUSC records exist ([open](#open)) |
| GetFurnitureMarkerID | 8 | 1 | `Actor.GetFurnitureReference` against the furniture the index stood for; to confirm |
| TriggerScreenSplatter | 8 | 1 | `Game.TriggerScreenBlood` |
| UseWeapon | 8 | 1 | `Weapon.Fire` from the actor; drift: no aim target |
| SetCriticalStage | 6 | 1 | `Actor.SetCriticalStage` |
| EnterTrigger | 5 | 1 | The converter calls the trigger script's converted `OnTrigger` body once (the 5 boxes with no `OnTriggerEnter`) |
| FireWeapon | 5 | 1 | `Weapon.Fire` |
| GetContainer | 5 | 1 | `ObjectReference.GetContainer`; Fallout 4 declares it, the marker is Skyrim's note |
| PlaceLeveledActorAtMe | 5 | 1 | `ObjectReference.PlaceActorAtMe` |
| SetSecExp | 5 | 1 | SetSecuritronExpression's short name; give it that row |
| SystemSave, ForceSave | 5, 2 | 1 | `Game.RequestSave` |
| GetPCMiscStat | 4 | 1 | `Game.QueryStat` |
| IsInList | 4 | 1 | `FormList.HasForm` |
| AttachAshPile | 3 | 1 | `Actor.AttachAshPile` |
| GetContainerInventoryCount | 3 | 1 | `GetItemCount(None)` counts every item |
| GetCurrentAIPackage | 3 | 1 | `Actor.GetCurrentPackage` |
| PlayBink | 3 | 1 | `Game.PlayBink` ([Bink](bink_movies.md)) |
| ClearDestruction | 2 | 1 | `ObjectReference.ClearDestruction` |
| SetItemValue | 2 | 1 | `Form.SetGoldValue` |
| ShowBarberMenu | 2 | 1 | `Game.ShowRaceMenu`; to confirm the mode |
| CreateDetectionEvent | 1 | 1 | `ObjectReference.CreateDetectionEvent` |
| ExitGame | 1 | 1 | `Game.QuitToMainMenu` |
| GetXPForNextLevel | 1 | 1 | `Game.GetXPForLevel(level + 1)` |
| IsSpellTarget | 1 | 1 | `Actor.HasMagicEffect` of the spell's effect |
| `ne` (GetFactionRelation) | 1 | 1 | `Actor.GetFactionReaction`; to confirm. The census reads `;NE: NE:` as a function named `ne` |
| SetInChargen, GetInCharGen | 1 | 2 | **Built:** the flag in `F3NV_State`; `Game.SetInChargen` kept off ([below](#ignore-crime)) |
| ShowAllMapMarkers | 1 | 1 | `Game.ShowAllMapMarkers` |
| IgnoreCrime, GetIgnoreCrime | 185, 3 | 2 | **Built:** the actor's crime faction cleared and remembered in `F3NV_State`, read back by GetIgnoreCrime ([below](#ignore-crime)) |
| SetPackDuration | 12 | 2 | An end time in `F3NV_State`; the poll calls `EvaluatePackage` once it passes |
| HasBeenEaten | 5 | 2 | The Cannibal feed writes `F3NV_State` |
| IsPlayerMovingIntoNewSpace | 5 | 2 | A flag set from the player's `OnLocationChange` |
| IsPlayerGrabbedRef | 3 | 2 | `OnGrab` / `OnRelease` keep the held reference |
| PipBoyRadio, PipBoyRadioOff | 3, 1 | 2 | A switch on the [F3NV radio](fo4_radio.md) helper |
| GetFriendHit | 2 | 2 | An `OnHit` counter in the script's own variables |
| IsIdlePlaying | 1 | 2 | Phase 5's PlayGroup record, as IsAnimPlaying |
| ResetInventory | 17 | 3 | `RemoveAllItems`, then a build-written list of the base's inventory |
| SetActorFullName | 17 | 3 | A reference alias with a display name; unverified on a forced reference, a DLL candidate |
| SetQuestObject | 7 | 3 | The holding alias's Quest Object flag, written at build |
| ShowRecipeMenu | 5 | 3 | A build-placed hidden workbench of the recipe list's kind, activated for the player |
| sgtm, SetGlobalTimeMultiplier | 5, 2 | 3 | A build-made slow-time spell cast on the player (sgtm is the short name) |
| AddAchievement | 111 | 4 | No FNV achievements on Fallout 4 |
| ForceTerminalBack | 30 | 4 | Fallout 4 terminals have no Papyrus page control; the player backs out |
| SetObjectiveDisplayed, SetObjectiveCompleted | 26, 21 | 4 | All 47 name an objective their quest never authors |
| GetObjectiveDisplayed, GetObjectiveCompleted | 7, 4 | 4 | Likewise unauthored, so 0 is the right answer; these leave phase 2 |
| PCB | 21 | 4 | Cell buffers are the engine's own |
| SetVATSTarget | 7 | 4 | Trap activators are not VATS targets on Fallout 4 |
| GetShouldAttack | 5 | 4 | The sibling `IsInCombat` term carries the check |
| IsGoreDisabled, IsPS3 | 5, 5 | 4 | 0 is right on Fallout 4 PC |
| SetLevel | 5 | 4 | No Papyrus level write; only a DLL could |
| `flip` | 5 | 4 | The source's own `;TODO: flip check` comment, not a call |
| AddTopic | 4 | 4 | Fallout 4 topics are not gated by being added |
| EnableNavMesh | 4 | 4 | Fallout 4 navmesh has no disabled state to clear |
| IsInCriticalStage | 4 | 4 | No read of the engine's crit stage; Pacer's two lines stay unsaid |
| PlaceAtReticle | 3 | 4 | No reticle raycast; the Euclid's C-Finder pointer would need a DLL |
| SetAllVisible, SetAllReachable, SetSceneIsComplex | 3, 2, 2 | 4 | Console and PS3 scene helpers |
| SetNoAvoidance, SetMinimalUse | 3, 1 | 4 | No Papyrus counterpart; the AI's own choice |
| SetPCSleepHours, WakeUpPC | 3, 3 | 4 | No Papyrus sleep control |
| AgeRace, AddTagSkills | 2, 1 | 4 | Character creation is the [character system](character.md)'s |
| AutoDisplayObjectives, ShowTutorialMenu, EnableLoadingMenu | 2, 2, 2 | 4 | Fallout 4's HUD shows these itself |
| GetPlayerName, IsPC1stPerson | 2, 2 | 4 | No Papyrus read |
| SetForceSneak 0 | 2 | 4 | No stop-sneak ([SetForceSneak](script_markers.md#setforcesneak)) |
| SetScreenSplatterFade, ClearScreenSplatter | 2, 1 | 4 | Screen blood fades on its own |
| DetonatePlacedExplosives, GetHitLocation, GetOwnerLastTarget | 1 each | 4 | No Papyrus counterpart |
| PreloadMagicEffect, PurgeCellBuffers, ResetPipBoyManager, ResetXP, TrapUpdate | 1 each | 4 | Engine housekeeping |
| SetDisposition, SetPCCanUsePowerArmor | 1 each | 4 | Fallout 4 has no disposition or power armor training |

Prose notes, not functions: the source compiler 18, unreachable after
Return 13, undeclared var 6.

| Route | Functions | Markers |
|---|---:|---:|
| 1 native | 33 | 184 |
| 2 remembered state | 10 | 220 |
| 3 build data | 6 | 53 |
| 4 nothing to do | 44 | 312 |

No function needs route 5 outright; SetActorFullName and ResetInventory
keep a DLL candidate below. Phase 2 grows from the 111
markers it first counted to route 1's 184, and loses the objective reads.

### <a id="dll-decisions"></a>DLL decisions

Each needs the user's approval; none is in the phases unless approved.

| Candidate | Need | Alternative without a DLL |
|---|---|---|
| IsAnimPlaying | A NIF sequence's real end | A flag timed from the sequence's authored length (phase 4) |
| SetActorFullName (17) | Rename a reference | A reference alias with a display name, if Fallout 4's alias name field works on a forced reference (unverified) |
| ResetInventory (17) | Restore the base inventory | `RemoveAllItems`, then add a converter-built list of the base's inventory |

## <a id="phases"></a>4. Phases

| # | Size | Delivers | Checked by | Depends on |
|---|---|---|---|---|
| 1 | S | **Done.** The [decision table](#decision-table): all 93 functions routed. The census is `tools/audit/script_marker_census.py` (not `tools/script/`, which the build imports); test `tests/test_script_marker_census.py`. Cost item 4 found already gone (recorded here, not in the inherited [performance](performance.md#papyrus) doc) | Reran: 806 markers, 420 scripts, 93 functions plus 3 notes (37 markers), 79 on a condition line | The play test only |
| 2 | S | The native rows (route 1 of the [decision table](#decision-table)) | `tests/test_script_markers_falloutnv.py` per row; census markers fall by the rows' count (184 today); `compile_papyrus.py --game fallout4` shows no new failure over `fo4_compile_baseline.json` | 1 |
| 3 | S | Cost item 2: a load flag set in `OnCellAttach`, cleared in `OnCellDetach`, in place of `SafeGameModeGate` in both arms; the carried holder check stays | `SafeGameModeGate` calls in the scratch run fall from 5,236; a script that disables itself still reaches its next state (the reason the gate is cell-scoped, not 3D-scoped); Papyrus log load in Freeside | 1 |
| 4 | M | `F3NV_State` and cost item 3: dialogue speaker and line timing held in quest variables, written as Fallout 4 overrides of `LineBegan`, `LineEnded` and `PlayerIsInDialogue` | Helper-plugin test for id 0x903; in game, Doc Mitchell's intro and a Say-timer scene keep their pacing; the trace shows no actor-value writes from `LineBegan` | 1 |
| 5 | M | `IsAnimPlaying` (route 3 plus 2): the PlayGroup handler records the reference, group and end time; the end time comes from the mesh's sequence length, which the build writes as a table the script stage reads | All 71 source matches convert to the read; in game, the Vault 11 gear door, the Lucky 38 lights and a Hoover Dam vertibird | 4 |
| 6 | S | Companion barks: `Poisoned` and `OnFire` from the follower's active effects, `UsedDoctorBag` from the Doctor's Bag effect writing `F3NV_State`, `WeaponBroke` from `GetEquippedWeaponHealth` | `tests/test_fo4_companion_barks.py`; in game, a companion poisoned by a cazador barks once | 4 |
| 7 | M | Crime infamy: the route the play test picks (crime gold values on converted crime factions, or infamy from the standings alias and witness). IgnoreCrime is **built** ([below](#ignore-crime)) | In game, a witnessed theft in Goodsprings raises Goodsprings infamy; an `IgnoreCrime` actor (the Pit fighters' triggers, Butch at the G.O.A.T.) does not report | 4, play test |

### <a id="ignore-crime"></a>Built: IgnoreCrime and SetInCharGen

`F3NV_State` (`FalloutHelpers.esl` 0x903, appended to
`FALLOUT4_HELPER_QUESTS`, so no existing id moves) is the helper quest
phase 4 names. It holds two things today; phase 4 adds the dialogue state.

- **IgnoreCrime.** GECK wiki: `[Actor.]IgnoreCrime 1` stops the actor
  reporting the player's crimes; it still reacts to a direct attack if not
  friendly. Fallout 4's vanilla scripts do this with
  `Actor.SetCrimeFaction(None)`: an actor with no crime faction reports to
  no one. `TES4Polyfill.IgnoreCrime(actor, flag)` clears it and remembers
  the faction it had (`Actor.GetCrimeFaction`); `IgnoreCrime 0` restores
  that faction. `GetIgnoreCrime` reads the remembered flag (FO3's MS13
  collar saves it and restores it later). 128 actors, the oldest giving
  way. Every use names an actor: FO3 has 45 calls (42 set 1, 1 sets 0, 2
  restore a saved flag), FNV 185 (87 set 1, 98 set 0); none needs the
  player-wide `Game.SetPlayerReportCrime`.
- **SetInCharGen.** GECK wiki: while on, the player does not level up (XP
  still accumulates); the levels arrive when it turns off. FO3 sets it at
  the start of CG00-CG03 and clears it at CG04's end. Fallout 4's
  `Game.SetInChargen(saving, waiting, controls message)` only blocks saving
  and waiting (vanilla MQ101 clears it with "allow saving"), so it is called
  with all three off, and the flag is remembered for `GetInCharGen`.
  **Not converted:** the level hold itself. Fallout 4 has no Papyrus call
  that stops a level-up, so a level gained in the vault arrives there.

Converted scripts that change, measured on the last converted folders:
Fallout3.esm 18 (53 lines), FalloutNV.esm 67 (189), DeadMoney 7,
HonestHearts 6, OldWorldBlues 11, LonesomeRoad 4, and mods (The Frontier
49, YUP 44, NVWillow 15, Bounties II 14). In the scripts read, only the
`;NE:` lines became calls, and one guard that always read false
(`CrucifiedVictimScript`'s `If GetIgnoreCrime != 1`) now runs.
| 8 | L | The remaining rows, one function at a time, by gameplay effect (`ResetInventory`, `SetPackDuration`, `GetFurnitureMarkerID`, `HasBeenEaten`, then the rest); DLL rows only if approved | One test per function; census count per batch | 2, 4 |

## <a id="play-test"></a>5. What the play test should tell us first

- **Crime gold.** Steal in front of a Goodsprings resident. If the trace
  shows `NoteCrime`, the ADCR event fires and phase 7 is a check; if not,
  phase 7 needs its own route.
- **Script load.** The Afterburner run through Freeside and the Strip,
  with the Papyrus log. Long poll delays move phase 3 ahead of phase 2.
- **Companions.** Hire Cass or Boone and fight: whether `HealthHalf` and
  `NoAmmo` are heard tells whether the watch quest runs at all, before
  phase 6 adds more barks.
- **Animated objects.** Open a door or gate whose script waits on
  `IsAnimPlaying` (the Vault 11 gear door). If it already works because
  the guard drops out, phase 5 drops in priority.
- **Combat styles.** Lily and the spore carriers set combat styles in
  FNV; if their fights look right, phase 2's combat-style row is polish.

## <a id="open"></a>6. Open questions

- Do Fallout 4's faction ignore-crime flags stop a member reporting the
  player's crimes, or only crimes against members? Unverified; it decides
  IgnoreCrime's records route.
- Does a NIF sequence's end send any animation event Papyrus can hear
  (a text key through `OnAnimationEvent`)? Unverified; if so, phase 5
  needs no timing table.
- Can a Fallout 4 Papyrus array grow past 128 with `Add`? `F3NV_State`
  keeps the 128 cap of `F3NV_PackageState` until this is checked.
- Do the [static scripts rule](../../CLAUDE.md#static-scripts-rebuild-all)
  rebuilds still apply when only Fallout 4 overrides change? Phase 4
  keeps its changes in `static_scripts/fallout4/overrides/` for that
  reason.
- Does FNV say `WeaponBroke` for a companion at all, since NPC weapons do
  not wear? Only a scripted break (Miss Fortune) or a weapon handed over
  broken could trigger it.
- Which converted MUSC records exist for `PlayMusic` (9 sites)? Not
  checked.
- Is the poll's top 5 s insurance arm still needed once the flag replaces
  the gate? Kept until a play test says otherwise.
