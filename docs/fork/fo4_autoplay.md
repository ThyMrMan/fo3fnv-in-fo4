# Plan: unattended play-test runs on the Fallout 4 build (2026-11-14)

Status: planned, nothing built. Status lives in [ROADMAP.md](ROADMAP.md).
Builds on the [build chain](fo4_chain.md), the [session trace](fo4_pipeline.md#trace)
and the [preflight audits](fo4_preflight.md).

**Goal.** One run with nobody at the keyboard finds dozens of in-game bugs,
and replaces most of the user's two-hour manual play tests. A small fix gets
a short targeted run (the cells and quests it touched, 10 to 20 minutes); a
night gets the whole sweep. The user plays to judge what a machine can't
(the [list](#manual)), not to find crashes, Papyrus errors and quests that
don't advance.

## Contents

- [What we already have](#have)
- [Launch and stop](#launch)
- [Driving the game](#drive)
- [Checks per run](#checks)
- [Results](#results)
- [What stays manual](#manual)
- [Order and effort](#order)
- [First slice: what it needs from the user](#slice-1)

## <a id="have"></a>What we already have

| Piece | What it gives the harness | Where |
|---|---|---|
| Build chain test-plugin step | Copies a test plugin into its own MO2 mod folder, unticked, after every step passed (`--kit`, `--kit-mod`) | [fo4_chain.md](fo4_chain.md#steps), `tools/release/fo4_chain.py` `copy_kit` |
| Play command | Starts F4SE through MO2's F4SE executable for a named profile: `ModOrganizer.exe -p <profile> run -e <title>` | `fo4_import/app/mo2_setup.py` `play_command` |
| Profile editing | Enables a mod and its plugins in a profile's `modlist.txt`, `plugins.txt`, `loadorder.txt` | `mo2_setup.set_up`, `enable_mod`, `enable_plugins` |
| Startup checks | Game, MO2 or CK already running; paths missing | `fo4_chain` startup checks |
| Session trace | `TES4TRACE\|time\|kind\|...` lines in `Papyrus.0.log` for every converted SetStage, line begin/end, Say, package fragment, death, scripted actor load and fall, hit, scene, rep, karma, item; on while `F3NV_Trace.esl` (MO2 mod `F3NV - Trace`) is enabled | [trace](fo4_pipeline.md#trace), `script_convert/trace_points.py` |
| Trace reader | Turns the log into a timeline and flags: a SetStage that did not set, a stage going back, a Say or scene that never started, a line said twice, a counter skipping, an actor falling 100+ units in 5 s after load, the VM's suspended-stacks warning | `tools/validate/fo4_trace.py` |
| Preflight findings and ledger | `Finding(audit, key, severity, summary)`, a committed review ledger (`ok`, `skip`, `bug`, key patterns), "new since last run" marks | `tools/validate/preflight/findings.py`, `review_ledger.json` |
| Offline audits | Quest-stage reachability (setter graph per SetStage site), quest start, dialogue, menus (one option per FNV topic), packages, behavior, assets, world links | `tools/validate/preflight/*.py` |
| Skyrim game bridge | A named-pipe control channel into the running game: console commands with their output, batches in one main-thread trip, Papyrus VM log capture, memory probes. Lessons kept in its README (the console dispatcher, the TLS print gate, the allocator) | `game_bridge/` (SKSE; not ported) |
| F3NV.dll | FNV rules on F4SE 0.7.9 (`tes_runtime/fo4_condition/`); no test hooks | [fo4_condition.md](fo4_condition.md) |
| Cleanroom UI | Our own menus on CommonLibF4 (`CleanroomUI.dll`, `CleanroomDialogue.dll`, level-up menu, Pip-Boy, dialogue menu movie), built from source we own | `cleanroom_ui/`, [spin_offs.md](spin_offs.md#move) |
| Papyrus helpers | 66 `F3NV_*` scripts: radio stations and playlists, level-up, new game, talk, packages, Say Once, trace scenes | `script_convert/static_scripts/fallout4/` |

Facts checked for this plan (2026-11-14), in the installed Fallout 4 1.11.240
and its F4SE 0.7.9 script sources:

- Vanilla Papyrus has everything the first phases need:
  `ObjectReference.MoveTo`, `SetPosition`, `IsInterior`,
  `FindAllReferencesWithKeyword`, `FindAllReferencesOfType`,
  `Actor.GetCurrentPackage`, `PathToReference`, `StartCombat`,
  `Weapon.Fire`, `ObjectReference.Say`, `Game.RewardPlayerXP`,
  `Game.IsPlayerRadioOn`, `Game.GetFormFromFile`.
- F4SE adds `Actor.GetWornItem` (the worn item and its model path) and
  `UI.IsMenuOpen`, `UI.Get`, `UI.Set` and `UI.Invoke`. Those drive our own
  menus from Papyrus: the movies are ours, so they can carry a test entry
  point.
- Neither vanilla nor F4SE Papyrus can run a console command or press a key.
  `Utility.SetINI*` is debug-only and there is no INI read. Anything needing
  the console or input goes through a DLL ([phase 2](#order)).
- `Fallout4.exe` reads `sStartingConsoleCommand` and `bAlwaysActive`.
- No crash logger is installed in the MO2 instance (no Buffout 4). The
  profiles are `Baseline`, `Fallout 3`, `Play`, `Replacements` and `Spike`.

The FNV source has 30,497 CELL records: about 30,100 exterior (WastelandNV
alone 16,397, most of them empty desert edge or water) and about 390
interiors, 7,756 teleport doors, 4,771 navmeshes, 436 quests and 18,215
topics.

## <a id="launch"></a>Launch and stop

**The test mod.** `F3NV_Autoplay.esl`, a light plugin with
`FalloutNV.esm` and `FalloutHelpers.esl` as masters, plus its compiled
scripts, in the MO2 mod `F3NV - Autoplay`. It holds:

- an empty interior, `F3NVAutoplayRoom`, where every run starts;
- the start-game-enabled quest `F3NVAutoplay` with the driver script;
- the run's work lists as FormLists (the sweep stops, quests, NPCs, items),
  written by Python from the built plugins;
- globals the harness patches between restarts (`F3NVAutoplayFrom`: the
  list index to resume at; `F3NVAutoplayMode`: which checks run);
- a test actor base (no AI packages, essential) and a target dummy.

A builder (`fo4_import/autoplay/kit.py`) writes the plugin from the built
`FalloutNV.esm` and the DLC plugins (read with the preflight's
`plugin_index`), compiles the scripts with the existing FO4 Papyrus step,
and writes one folder. The chain's test-plugin step already copies a kit
into its own mod folder; it is extended to copy a folder (plugin and
`Scripts/`), not only one file. The kit is not a game build and takes
seconds, but it is still placed by the chain run the main session owns.

**The test profile.** The harness writes the MO2 profile `Autoplay` as a
copy of `Play` at each run, then turns on `F3NV - Autoplay` and
`F3NV - Trace` and their plugins with `mo2_setup.enable_mod` /
`enable_plugins`. The user's `Play` profile is never edited. The profile
has its own INI files (MO2's profile-local INIs), so its
`Fallout4Custom.ini` can carry what only test runs want:

```ini
[General]
sStartingConsoleCommand=coc F3NVAutoplayRoom
bAlwaysActive=1
sIntroSequence=
[Papyrus]
bEnableLogging=1
bEnableTrace=1
bLoadDebugInformation=1
[Display]
bFull Screen=0
```

`coc` from the main menu starts a new game in the room, and the quest
starts with it. Whether our new-game scripts (`F3NV_NewGame*`) need a step
there, and how long the main-menu `coc` takes, is measured in phase 0: a
main-menu `set` once froze the game for 85 s
([trace switch](fo4_pipeline.md#trace)). A save-based start
(`sStartingConsoleCommand=load <save>`) is the fallback, and is also what
quest checks use when a stage needs a state no fresh game has.

**Start.** `py -3.14 -m tools.playtest.run --mode cells [--only <list>]`:

1. the chain's startup checks: Fallout 4, MO2 and the CK closed; the kit
   and the build stamps `finished`;
2. write the profile; patch `F3NVAutoplayFrom` to the resume index;
3. `play_command` with `-p Autoplay`, and keep the game's PID.

**Stop.** The driver ends with an `AUTOPLAY|done` trace line; the harness
then ends `Fallout4.exe` (no clean quit exists from Papyrus besides
`QuitToMainMenu`). The harness also stops on:

- **Crash:** the process gone with no `done` line. The last
  `AUTOPLAY|begin` without its `end` names the stop that crashed it.
- **Hang:** the game window not answering (`IsHungAppWindow`), or no new
  `AUTOPLAY` heartbeat line for 60 s while the window answers (a Papyrus
  stall). Phase 0 measures how late the Papyrus log flushes, which sets
  that limit.
- **Time cap** for the run (`--minutes`).

After a crash or hang the harness kills the game (and its MO2 if MO2 stayed
up), records the stop as crashed or hung, patches the resume index past it
and starts again, so one bad cell costs one restart, not the night.
A stop that crashes twice is skipped for the rest of the run.

## <a id="drive"></a>Driving the game

Preference order, cheapest and most engine-native first:

1. **Papyrus in the test plugin.** Moving the player, waiting for 3D,
   enumerating actors, starting quests, setting stages, firing weapons,
   equipping, Say, granting XP and perks. No new native code; uses the
   engine's own events (`OnCellLoad`, `OnPackageStart`, `OnPackageEnd`,
   `OnHit`, `OnDeath`, quest stage events). Writes results as trace lines
   in the same `TES4TRACE` format, kind `autoplay`, so `fo4_trace` reads
   them.
2. **F4SE `UI.*` into our own movies.** The level-up menu, Pip-Boy tabs and
   dialogue menu are Cleanroom UI movies. Each gets a small test entry point
   (list what is shown, pick entry *n*) that the driver calls with
   `UI.Get` and `UI.Invoke`. No vanilla movie is touched.
3. **A test DLL, `F3NVTest.dll`.** Only in the `Autoplay` profile, never
   shipped, so it does not make any feature need a DLL. Built on
   CommonLibF4 with Address Library IDs like Cleanroom UI, so one DLL works
   on every runtime. It ports the Skyrim game bridge's design (named pipe,
   console commands through the engine's own dispatcher, batches on the
   main thread, Papyrus log capture) and adds what Papyrus can't see: a
   crash handler, missing-file hooks, frame times, player input. Per
   CLAUDE.md a DLL needs the user's approval first.
4. **Console commands**, through the test DLL's pipe, only where no
   Papyrus call exists: `tcai` / `tai` to freeze AI for a screenshot,
   `tfc` for a free camera, `tm` to hide the HUD, `fw` to force a weather,
   `player.moveto` for a reference no FormList can hold.
   `coc`, `setstage` and `player.moveto` have Papyrus equivalents and the
   driver uses those.
5. **Python outside the game:** process and window watch, screenshots of
   the game window (windowed mode, `bAlwaysActive`), log collection.

Simulated mouse and keyboard from Python is ruled out: it needs the window
in focus, breaks the moment anyone touches the PC, and checks nothing.

## <a id="checks"></a>Checks per run

Each check names how the engine reports the failure; none guesses from
screenshots. Screenshots go into a review gallery, not into findings,
except as noted.

### <a id="check-cells"></a>Cells and worldspaces

**Stops.** Interiors: one stop per interior, at the arrival point of a door
leading in (door references are persistent, so a FormList can hold them).
Exteriors: per worldspace, a grid of points 5 cells apart (the loaded grid
is 5 by 5 around the player), on cells that have land or references,
reached by `MoveTo` a persistent anchor in that world (its map marker) then
`SetPosition` at the cell center, above the land height read from the
built LAND. Measured counts set the run time; the first slice measures them.

**At each stop**, after the cell loads (`OnCellLoad`, the player's `Is3DLoaded`) and a settle time:

| Check | Engine signal | Finding |
|---|---|---|
| Crash | Process gone between the stop's `begin` and `end` | error, with the stop, and the crash log from phase 2 |
| Hang | Window not answering, or no heartbeat | error |
| Papyrus errors | Lines in `Papyrus.0.log` between the stop's `begin` and `end` (the log is ordered), normalized (handles and addresses stripped) and grouped by script, function and message | error per group, listing the stops where it showed |
| VM jam | The suspended-stacks warning (already flagged by `fo4_trace`) | error |
| Actors falling | Every actor in the loaded cells (`FindAllReferencesWithKeyword` on the actor-type keywords): z at load, after 5 s, after 30 s; a drop of more than the cell's land span, or below the land height | error |
| Actors stuck in place | `OnPackageStart` / `OnPackageEnd` for each actor; a travel or patrol package that never ends and the actor's position not changing over the stop | review |
| Missing textures and meshes | Phase 2: the test DLL logs each file the resource loader fails to find, with the reference that asked | error |
| Frame time | Phase 2: frame times per stop from the test DLL | review past a limit set from Goodsprings' measured numbers |
| Screenshot | One per stop, AI frozen and HUD off from phase 2 | gallery only |

**Navmesh**, per interior and per sampled exterior stop: the test actor is
placed at each door's arrival point and sent with `PathToReference` to the
cell's other doors. A `false` return or no arrival in a time from the path
length is a navmesh gap between those two doors. This tests the navmesh the
way the engine reads it, which the offline navmesh checks can't.

**Time of day.** A second exterior pass (separate mode, nights) sets
`GameHour` to 06, 12, 18 and 00 at a subset of stops, for schedule-driven
packages and the night look in the gallery.

### <a id="check-quests"></a>Quests

Driven from the preflight's quest data, which already reads every SetStage
site in the source and the build (`quest_progression`, `quest_start`,
`quest_targets`). A new exporter writes `quest_plan.json`: per quest, its
stages in order, and per stage how the source game sets it.

| Check | How | Engine signal |
|---|---|---|
| Starts | `Start()` each quest that the source starts by script or at game start | `IsRunning()` false after `Start()`: the engine refuses a quest whose required aliases don't fill. Each alias's `GetReference()` is logged; an empty required alias names the cause |
| Stage fragments run | Set each stage in order with `SetStage` | `GetStageDone`; Papyrus errors inside the stage's window; the trace's SetStage lines |
| Automatic advance | For a stage whose setter is another stage's fragment, a quest script or a timer (no player action), set the stage before it and wait | The next stage set within the wait, from the trace; else error naming the setter site from the preflight |
| Player-action stages | Kill: `Kill()` the target. Item: `AddItem` to the player. Trigger: move the player into the trigger. Dialogue line: covered by the [dialogue sweep](#check-dialogue) | The stage set afterwards |
| Objectives | After each stage | `IsObjectiveDisplayed` matches the stage's objective set and clear lists from the source |
| Map markers | Quest targets after each stage | The target alias filled and its reference enabled |

Stages are run on a fresh start per quest group (a quest line), from a save
made after its first stage, so one broken quest does not poison the next.
The result is "this stage's machinery works", not "a player can get
there": the natural route stays [manual](#manual).

### <a id="check-dialogue"></a>Dialogue

1. **Lines.** For each NPC with lines: the test driver moves the player
   next to it and calls `Say` with each of its topics that has no player
   prompt (greetings, idle chatter, barks, scene lines). The trace already
   logs each converted line's begin and end, so the check is: a line
   began; it is the INFO the menu and dialogue audits expect for the fresh
   state; its time from begin to end is the voice file's length (a
   missing voice ends at once or uses the subtitle time).
2. **Menus.** From phase 6, the driver opens a conversation (the player
   activates the NPC), reads the option list from our dialogue menu movie
   with `UI.Get`, and compares it with the menu audit's expected options
   for the fresh state. It picks each option in turn (`UI.Invoke`), and
   the trace and `CleanroomDialogue.dll`'s "picked" lines name the answer
   played. An option that shows no answer, or the wrong one, is an error.
   Options whose conditions depend on state the run can't set are listed
   for review, not failed.

### <a id="check-npcs"></a>NPC behavior

Rides on the cell stops (above), plus a dedicated pass over each named
NPC's home and work cells at the hours its packages name: the current
package (`GetCurrentPackage`) is the one the source's schedule picks at
that hour and place (from the preflight's `packages` / `behavior` data),
the package starts and ends (`OnPackageStart`/`OnPackageEnd`), and the actor
reaches the package's location in the time its path length allows. Actors
with no package at all are already an offline finding.

### <a id="check-items"></a>Weapons, armor and items

- **Weapons:** each converted weapon is given to the test actor in combat
  with the essential dummy (`StartCombat`): `OnHit` on the dummy from that
  weapon within the wait, and the trace's hit kind for damage after DT.
  Projectile, impact and explosion records are also checked with
  `Weapon.Fire` from the player position. First-person firing by the
  player needs input injection (phase 2 DLL) and is checked for a sample
  per weapon class.
- **Armor:** each armor equipped on the player and on test actors of each
  playable race and sex: `IsEquipped`, and `GetWornItem` for each slot it
  claims names the item and a model path that exists (checked by the
  harness against the asset index the preflight `assets` audit already
  builds). One screenshot per armor and race for the gallery.
- **Aid, ammo, misc:** add, use (`EquipItem` for aid), and remove;
  Papyrus errors and the trace's item lines.

### <a id="check-character"></a>Perks and level-up

- **Level-up menu:** `RewardPlayerXP` to each next level; our level-up
  menu must open (`UI.IsMenuOpen`); its test entry point lists the skills
  and perks offered and picks one; the chosen skill's value and the perk
  (`HasPerk`) must be set after it closes. Covered for levels 2 to 50.
- **Perks:** each converted perk is added; `HasPerk`; its rank
  prerequisites against the source's; for perks with an ability or value
  effect, the actor value before and after.

### <a id="check-radio"></a>Radio

Each station quest running; its transmitter reference enabled; with the
radio on (`IsPlayerRadioOn`, turned on through the Pip-Boy test entry
point), the station's playlist and scene trace lines (`scene`, `line`) for a
few minutes of real time each, which bounds this pass to its own mode.

## <a id="results"></a>Results

Each run writes `output/playtest/<run id>/`:

- `run.json`: the build stamps it ran on (plugins, DLL, kit), mode, stops,
  start and end, restarts with their causes;
- `logs/`: every `Papyrus.*.log` from each game start (the game keeps four
  and rotates them on start, so they are copied before each restart),
  `F3NV.log`, `f4se.log`, the test DLL's log and crash logs;
- `shots/<stop>.jpg` and `gallery.html` (one page, grouped by worldspace,
  quest or item, for a quick look by eye);
- `findings.jsonl`: one line per finding in the preflight's shape
  (`audit`, `key`, `severity`, `summary`, `detail`).

**Into the preflight.** A new preflight audit `play` reads the newest run
for the plugin and turns its lines into `Finding`s, so the existing report,
ledger and "new since last run" marks apply unchanged:
`py -3.14 -m tools.validate.preflight --fo4 <plugin> --audit play`.
Keys are stable across builds because FormIDs are hashed, not counted:

- `play|FalloutNV.esm|crash|<cell or step>`
- `play|FalloutNV.esm|papyrus|<script>.<function>|<message hash>`
- `play|FalloutNV.esm|fall|<actor FormID>`
- `play|FalloutNV.esm|stage|<quest>|<stage>`
- `play|FalloutNV.esm|alias|<quest>|<alias>`
- `play|FalloutNV.esm|line|<INFO FormID>`
- `play|FalloutNV.esm|navmesh|<cell>|<door>-<door>`

**Known issues.** The ledger is the dedup: a key or pattern marked `bug`
stays listed with its note (so a known bug is not reported as new), `ok`
and `skip` hide it. Papyrus errors are grouped before keying, so one bad
script that fires in 300 cells is one finding listing the cells. Crashes
group by the crash log's top frames (as Address Library IDs) from phase 2.
The existing Skyrim `log_triage` audit's log normalizer is extended for the
FO4 log rather than written again.

**Targeted runs.** `build_plan` knows which records a rebuild changed. The
harness turns those into stops (cells holding changed references, quests
whose scripts or stages changed, NPCs whose packages changed) and runs
only those, with `--only changed`. This is the 10-to-20-minute loop the
[iteration goal](fo4_build_speed.md) needs; the whole sweep is for nights.

## <a id="manual"></a>What stays manual

| Area | Why a machine can't judge it |
|---|---|
| The look: color tone, lighting, weather, grass, neon, LOD at distance | Right and wrong are both valid images; only a person compares to New Vegas. The gallery makes it a skim instead of a walk |
| Animation quality: gun grips, third-person clips, creature reactions, idles | The engine reports that a clip played, not that it looks right |
| Combat feel and balance: damage, DT, VATS, kill cams, AI tactics | No engine signal for "feels like New Vegas" |
| Voice and lip timing, sound mix, music cues | A line playing is checked; whether it sounds right is not |
| The natural quest route: speech and skill checks, lockpicking, sneaking, choices and their consequences, companions' reactions | The harness proves each stage's machinery works; a player's path through it is state built up over hours |
| Menu layout and usability | Contents are checked through test entry points; layout is a screenshot for review |
| Stutter and frame pacing as felt | Frame times are measured; whether a hitch matters is judged |
| Story and text correctness | Wrong text that loads fine is still wrong |

## <a id="order"></a>Order and effort

Effort is agent working days, plus one unattended run on the user's PC
per phase to confirm it.

| Phase | What | Size | Needs |
|---|---|---|---|
| 0 | Launch and stop: `Autoplay` profile from `Play` with its INIs; kit builder with an empty driver; the chain's kit step copying a folder; start through MO2; crash, hang and time-cap watch; log collection; measure the main-menu `coc` time and how late the Papyrus log flushes | S, 1 day | one 10-minute run |
| **1** | **Cell sweep, the first slice:** stop lists from the built plugins; the Papyrus driver (move, wait for 3D, heartbeat, begin/end lines); restart and resume past a crashing stop; Papyrus errors grouped per stop; falling actors; screenshots and gallery; `findings.jsonl`; the `play` preflight audit; `--only` for a stop list | M, 2 to 3 days | the PC left idle for the run |
| 2 | `F3NVTest.dll` on CommonLibF4: crash handler writing the stack as Address Library IDs and the current stop; console over a named pipe (game bridge port); missing texture and mesh hook; frame times; HUD off and AI freeze for screenshots | L, 1 to 2 weeks | the user's OK for a test-only DLL |
| 3 | Actors, packages and navmesh: package events and stuck actors at every stop; `PathToReference` between doors; time-of-day pass | M, 3 days | |
| 4 | Quests: `quest_plan.json` from the preflight's setter graph; start and alias checks; stage fragments; automatic advance; objectives; per-quest-line saves | M to L, 1 week | |
| 5 | Weapons, armor and items | M, 3 days | |
| 6 | Dialogue: `Say` sweep first, then menu walking through test entry points in our dialogue menu movie | L, 1 to 2 weeks | a Cleanroom UI change for the movie's test hook |
| 7 | Level-up menu, perks and radio, through test entry points in Cleanroom UI's movies | M, 3 to 4 days | a Cleanroom UI change |
| 8 | Targeted runs from `build_plan`'s changed records | S to M, 2 days | phases 1 and 4 |

Phase 8 can move up to right after phase 1 for cells alone, since the
cell stops are the first list it can narrow.

## <a id="slice-1"></a>First slice: what it needs from the user

Phases 0 and 1 together: about 3 to 4 agent days, no DLL, no change to any
shipped plugin, script or DLL. The output of one run is a findings report in
the preflight and a screenshot gallery: every interior and the land of each
worldspace visited, with each crash, hang, Papyrus error and falling actor
named by the cell it happened in.

From the user:

- **Leave the PC idle for the run**, with nothing else full screen and no
  keyboard or mouse use: the game runs windowed and in the background
  (`bAlwaysActive`), but screenshots need the window shown and not
  minimized. A full interior sweep is about 390 stops; at 10 to 15 s each
  that is roughly 1 to 1.5 hours plus restarts. The exterior grid's length
  is measured on the first run; a night covers both.
- **Fallout 4, MO2 and the CK closed** when it starts (it refuses
  otherwise).
- **A new MO2 profile, `Autoplay`,** copied from `Play` at each run; `Play`
  is never edited.
- **The main session places the kit** with the chain's test-plugin step
  after a finished build; the harness starts no build.
- Optional: a crash logger (Buffout 4 or a successor for 1.11.240) until
  phase 2's handler exists. It is a download, so it is the user's call; the
  slice works without it and names the crashing stop either way.
