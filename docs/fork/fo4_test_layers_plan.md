# Plan: testing in layers, against the source games (PLAN 2026-11-17)

**Why.** Step 1 of the [progression plan](fo4_opening_progression_plan.md#order)
passed on 2026-11-17, for both games and both sexes. FO3 ran from birth
through CG01, into CG02. FNV ran from the cemetery through the Vit-o-matic.
Getting there took most of a day for a few minutes of each opening.
The runs were not wasted: they found these bugs, and a player would have
hit every one:

- Trigger boxes were solid, so Dad's crib-exit trigger stopped the player
  at its edge ([trigger layer](fo4_pipeline.md#trigger-layer)).
- The door closer shut the door in front of a player following Dad.
- Character creation ran twice. Two starts of FNV's VCG00 left its stage 0
  fragment with every property None, and the player stayed in the bathroom
  ([new game](fo4_pipeline.md#character-creation)).
- The dialogue code's "10 s at most" wait ran past two minutes under load,
  so Doc Mitchell stopped at stage 8 in 2 of 3 runs.
- Far-off speakers held every line end in the game, so the Vit-o-matic
  ignored a press made just after Doc's line
  ([says settled](fo4_pipeline.md#says-settled)).

The cost is in the loop around each fix. These numbers are measured on the
2026-11-17 builds:

| Step | Time | Why |
|---|---|---|
| Build FNV | 448 s (FO3: 183 s) | A full build per fix. Converting scripts takes 30.5 s; Caprica compiled 498 files. The scripts-only hotfix existed but went unused ([S1](#s1)) |
| Deploy and push FNV | several minutes | Scripts ride in `FalloutNV - Main.ba2`, 5.38 GB with 124,237 other files, so every script change sends 5.4 GB |
| Run to the failing case | 4 to 5 min | Each run replays character creation (about 90 s), the intro and every earlier case; `--from` hangs on load |
| Diagnose | one more run, often | Only the Papyrus log is read, after the run ends. The Vit-o-matic took two runs; one live query of objective 30 would have answered it |

At 20 to 25 minutes a loop, the tutorials alone take days, so the main
quests never get covered. This plan does two things. It makes the loop
fast, and it splits testing into layers so the slow, detailed runs are
spent only where they pay.

## Contents

- [The layers](#layers)
- [What today's bugs each layer would have caught](#caught)
- [Speed work](#speed)
- [Layer 0: data audits](#l0)
- [Layer 1: the stage sweep](#l1)
- [Layer 2: route sweeps](#l2)
- [Layer 3: scene runs](#l3)
- [Layer 4: the source games as the answer key](#l4)
  - [The FNV engine ports: nv-rs and NVForever](#engine-ports)
- [Order and effort](#order)
- [Open questions](#open)

## <a id="layers"></a>The layers

Each layer is cheaper and wider than the one below it. A bug a cheap layer
can catch should never cost a scene run.

| Layer | Runs | Per unit | Scale | Catches | Misses |
|---|---|---|---|---|---|
| 0. Data audits | every build, no game | seconds for the whole plugin | every record | wrong or missing data | anything the engine does with correct data |
| 1. Stage sweep | in game, `SetStage` per stage | seconds per stage | every quest | fragments that error, quests that refuse to start, objectives, auto-advancing stages | whether a player can get there |
| 2. Route sweep | in game, teleport, then talk and choose | about a minute per quest | every quest with a route | wrong or missing lines, choices that don't advance, conditions that never pass, stages a line should set | walking, triggers, doors, actors' behavior on the way |
| 3. Scene runs | in game, walking and watching in real time | minutes per scene | the hard spots only | everything a player sees in that scene | content no case names |
| 4. Source recording | in FO3/FNV | one recording per route or scene | grows with layers 2 and 3 | what "right" is, for layers 2 and 3 | nothing on its own; it is the reference |

The run is still one harness, `fo4_story_cases` on the
[test machine](fo4_story_tests.md#laptop). Layers 1 and 2 are case files
too, generated rather than written, so every speed fix below serves them all.

## <a id="caught"></a>What today's bugs each layer would have caught

| Bug | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Solid trigger boxes | yes: a census of activator primitives without XTRI | no | no (teleports past it) | yes (found) | |
| Door shut in front of a follower | no | no | no | yes (found) | yes: FO3's door stays open |
| Character creation run twice | no | no | no | yes (found) | |
| Says wait capped in passes, not seconds | no | maybe: a long stall shows if the sweep times each stage | yes: Doc's chain stalls | yes (found) | yes: FNV's timing |
| Far speakers hold every line end | no | no | yes | yes (found) | yes |
| A press before the objective shows | no | no | no | yes (a case bug that exposed the one above) | yes: the order of line end and objective |

Most of today's bugs sit where the engine meets timing and movement.
That is why layer 3 stays for the openings and set pieces, while layers 1
and 2 take the breadth.

## <a id="speed"></a>Speed work

These come first, because every layer pays them on every loop.

### <a id="s1"></a>S1. A scripts-only build: the hotfix (built)

It already existed: [fo4_hotfix](fo4_hotfix.md) converts the plugin's
scripts as its build does, compiles only those that differ from what the
last build compiled, and ships the `.pex` loose into a hotfix MO2 mod that
sits last (loose files beat archives). The next deploy of a later build
clears them. A dry run with nothing changed took 36 s on FNV (26.6 s
converting), against 448 s for the build. This plan first missed it.

Changed for the test loop (2026-11-17):
- **One hotfix mod per source game** ([per game](fo4_hotfix.md#per-game)).
  Both games ship scripts of the same names, so the shared mod mixed them.
  The "Fallout 3" profile now enables `F3NV - Fallout 3 Hotfix`.
- **The guard** ([needs a build](fo4_hotfix.md#needs-a-build)): a changed
  script that adds or retypes an object property with no default is refused
  (exit 2), since the built plugin fills none of them and the script would
  see None.

### <a id="s2"></a>S2. Small pushes (answered)

`Fallout4.exe` names only ` - Main.ba2`, ` - Textures.ba2` and ` - Voices_`
as plugin archives ([main archive](fo4_pipeline.md#main-archive)), so a
separate scripts archive would need an ini list. It isn't needed: the
hotfix ships scripts loose, and the push sends only changed files, so a
script fix sends kilobytes. A full build still rewrites Main and sends it.

### <a id="s3"></a>S3. Checkpoints that load (fixed 2026-11-17)

`--from <case>` hung the game on every checkpoint, not only the one saved
after the SPECIAL card's hide: a save after `cg00_name_and_face` hung the
same way. The Papyrus VM froze, "Reverting game..." was logged, and the VM
never thawed (still hung 10 minutes later). The runner loaded with the
console's `load`, and the test DLL runs each console line inside an F4SE
task, so the whole load ran synchronously inside that task and stopped.
`coc`, which only queues a cell change, always worked.

The test DLL's `load` command now queues the load as the Load menu does
(`BGSSaveLoadManager`: the save's entry in `saveGameList` as
`queuedEntryToLoad`, then `QueueSaveLoadTask(kLoadGame)`), and the main
loop loads it outside the task. Both checkpoints then loaded, and the
cases after them passed (`cg01_walk_to_daddy` and `cg01_playpen` from
`cg00_name_and_face`, `cg01_follow_dad` from `cg01_special_book`).

**A load mid-run (2026-11-18).** The FNV sweep's second `load`, the same
checkpoint while the game stood in that cell (Doc's house), timed out
waiting for `LoadingMenu`. The test DLL's `status` now gives `loads`, the
count of F4SE `kPostLoadGame` messages since launch, and the sweep's `load`
waits for it to rise instead of watching for the loading menu.

**A dropped load (2026-11-18).** In the full FNV sweep, the load after
`vNellisMoveToPearl` never ran: `loads` stayed at 324 for 120 s, the game
stood in Nellis with `ButtonBarMenu` open, and the run stopped there with 26
cases left. That quest's script moves the player across cells and calls
`Game.RequestAutoSave()` just before the load was queued. The likely cause
is that the autosave took the save manager's queued task. The sweep's `load`
now queues again every 30 s the count has not risen (`queue_load`), for up
to 120 s.

Still to build:
- a save after every passing case, as designed (built: `--checkpoints`).
  Each save is named after its case and the run's `--set` values
  (`f3nvtest_cg01_playpen_female`): one shared name let a female `--from`
  run load the male save;
- `run` stops a game a failed run kept before it rebuilds the instance, and
  so does `push` (the kept game locked the bridge's DLLs and the copy
  failed);
- runs start from the last passing case of the build under test. They
  replay from the start only when that case's build is older than the
  last change to its quest's scripts;
- a start save per quest group for layers 1 and 2: after character
  creation, with the source game started, so no sweep replays the opening.

This saves 4 to 5 minutes a loop at the openings, and more as the cases
reach further.

### <a id="s4"></a>S4. A snapshot when a step fails (built 2026-11-17)

A failed case prints a snapshot into the run's log
(`fo4_story_cases.snapshot`):
- the bridge status (cell, menus open);
- for each quest the case's steps name, `sqs` (stages) and `sqo`
  (objectives);
- the last 12 lines the trace heard.

The game stays open on a failure (`--keep-on-fail`, the default for
`fo4_laptop run`; the next run stops it first), and the laptop's game
answers from this PC: `fo4_laptop query "<console line>"`, `status`,
`stop`. The Vit-o-matic failure was "objective 30 not displayed yet",
visible in one query.

Still to add when a case needs them: each nearby actor's package, scene,
`IsTalking`, sit state and distance; the Papyrus suspended-stack warnings.

### <a id="s5"></a>S5. Passing means several times (built 2026-11-17)

`fo4_story_cases --repeat N` runs the chosen cases N times, each in a
fresh game, and passes only if every round passes. A case counts as
passing at 3 rounds in a row on one build
([story tests order](fo4_story_tests.md#order) already says so for scene
fixes). Two of today's bugs showed in some runs only: the double start
when the two copies came 0.1 s apart, the stall in 2 of 3. The repeats run
unattended, from checkpoints, so they cost no one's time.

`--keep-going` relaunches the game after a failing case and runs the rest.
The sweep's failed checks carry over to the new game, so `report` still
lists them all. This is meant for the sweep, whose cases each load their
own save; a story case after a failure has no checkpoint to start from.
One hung load had stopped the full FNV sweep with 26 cases unrun.
A game that stops answering in the middle of a case (a crash) also counts
as that case failing, so the run relaunches instead of ending. The first
FO3 sweep crashed in `CG00`'s birth stages on a CG02 save.

**Background errors (2026-11-18).** In a region build, other quests' timers
keep failing on references the build left out (FO3: `MS04Script`,
`MS12QuestScript` and `DialogueRivetCityScript` OnTimer, 132 errors in one
window), so every check of every case failed. The sweep's `load` now watches
the 6 s after the save loads and keeps the causes it sees as the case's
background, and `errors` leaves those causes out. A cause is script,
function and message, so a stage that sets off the same error in the same
place is not told apart. It already happened before the stage ran.

### <a id="s7"></a>S7. A faster game (built and measured 2026-11-18)

`fo4_story_cases --speed X` (and `fo4_laptop run ... --speed X`) sets the
console's `sgtm X` (the global time multiplier V.A.T.S. slows) while an
`until` waits, and `sgtm 1` when it ends, even on failure. The game's own
work (packages, timers, fights) runs faster there; talks, picks and walks
stay at 1x.

Measured on the Goodsprings chain (VCG02, VCG03, VMS16, VMQ01; case
seconds, failed checks):

| Run | Setting | Seconds | Failed checks |
|---|---|---|---|
| 5 | 1x, before fail-fast | 1,047 | 36 of 177 |
| 6 | 1x, fail-fast | 751 | 32 of 173 |
| 7 | `sgtm 4` the whole run | 912 | 47 of 190 |
| 8 | `sgtm 4` in `until` only | 698 | 33 of 172 |
| 9 | as 8, with the bottle route (no shot fired: [fighting off](#fighting-controls)) | 1,075 | 46 of 208 |
| 10 | as 9, carebear trigger first, [objective fallback](#objective-fallback) | 1,186 | 48 of 210 |
| 11 | as 10, shots stop at the objective, `talk` takes Sunny's own greeting | 1,038 | 45 of 213 |
| 12 | as 11, row keys through the game window, `-`, [quest-variable needs](#objective-fallback) | 872 | 29 of 208 |
| 13 | as 12, a talk only for a need skipped once it holds | 854 | 19 of 201 |

In run 11 VCG02 25 was set by its route for the first time: the trigger
walk, Sunny's bark, the bottles hit, then "Okay, I'm in." chosen and
heard. VCG02 took 419 s (run 10: 575 s, where the talk waited out
Sunny's own conversation).

- **4x the whole run breaks dialogue input.** The dialogue menu drops
  number-key picks: `choose` pressed Sunny's "[END TUTORIAL]" row five
  times and none took, so VCG02 never ended, Trudy stayed disabled, and
  VMS16 5 and 50 failed after it. Timer scripts also raised more errors
  (`BlackbirdSinging` 5 against 1). The VMS16 100 fight and the VCG02 30
  package did finish at 4x.
- **4x in waits only is safe and worth about 7%.** VCG02 30's wait passed
  (it times out at 1x); everything else failed as at 1x. Timer errors land
  in an earlier stage's window (the region build's 18 `VSouthStalkers01`
  errors in VMS16 70 instead of later).
- **Most of a run is dialogue and failed routes, not game simulation.**
  Run 4 (about 1,260 s) spent about 910 s with failed checks waiting out
  their timeouts (`heard` 420 s, `choose` 220 s, `until` 180 s, `talk`
  90 s). Voiced lines play at their audio's length at any speed.
  [Fail-fast](#fail-fast) cut 28%; the next gains come from routes that
  work (fewer failures), not from speed.

A `--keep-going` relaunch resumes from the last passing case's checkpoint
(with `--checkpoints`); before, the rest ran at the main menu.

### <a id="fail-fast"></a>Fail-fast for a broken talk (built 2026-11-18; run 6: 1,047 s to 751 s)

`talk` (no dialogue menu) and `choose` (the wanted prompt not listed) are
gates. Each fails only after its own full wait: `talk` activates again
every 6 s for 30 s, and `choose` re-reads the list every 0.5 s for 20 s,
so slow dialogue gets the same time as before. Once a gate of a talk
fails, `check` skips that talk's remaining `look`, `talk` and `choose`.
Its `heard` still looks for 5 s, for a wanted line said without a pick (a
greeting line), and its `bye` always runs, so no menu is left open. Each
talk has its own note (`FNV_VCG02 complete: talk 1 with Sunny Smiles`),
so other talks, other routes and the block's `until` and fallback run as
before.

### <a id="tutorial-harness"></a>Harness fixes from the FO3 tutorial run (2026-11-18)

- **A message box with non-ASCII buttons** (the G.O.A.T.'s Q8): `box_gone`
  compared the buttons as `ensure_ascii=False` JSON against an error text the
  bridge wrote that way, while the harness wrote them escaped, so a lost key
  press was never retried (`test_fo4_story_cases.py`).
- **`talk` faces the speaker first**, and `follow` sends the raw bytes the
  bridge expects.
- **A fresh run needs `tests/story/fo4_creation.f4test` first**; without it
  the run stood at the main menu. `--from <case>` loads the checkpoint saved
  after the case before it (`f3nvtest_<case>_<sex>`), so it needs a run that
  passed that case with `--checkpoints`.
- **`--from` replays what the save already holds.** A package that began
  before the save keeps its begin fragment's outcome: to retest a begin
  fragment, start from a case before the package begins (Kendall's SayTo
  begins at CG03 stage 40, so its fix was retested from `cg03_brotch`).
- **Cases that wait for the game's own choices.** `cg03_sit` waits for the
  seven students before the player sits (their Find packages pick any seat),
  and `cg04_hall` has the player finish the radroaches when Kendall falls
  ([fo4_opening_progression_plan.md](fo4_opening_progression_plan.md#tutorial-run-2026-11-18)).
- **The laptop runs the pushed cases.** `run` reads the case files from the
  last `push`; a run started after an edit and before a push ran the old text
  (runs 44-45).
- **`walk` stops at a closed door.** The AI-driven player's `PathToReference`
  never opens one, so a case walks to each door, `activate`s it, then walks
  on ([atrium-path](fo4_opening_progression_plan.md#atrium-path)).
- **Terminals.** FO4's terminal types its header out first, and keys pressed
  meanwhile were lost: wait 5 s before `press s`/`press e`. Tab on a result
  page did not close it; `close TerminalMenu` (the bridge's hide) does. No
  checkpoint saves while it is open (`no checkpoint ... cg04_terminal`).
- **Console conditions must print a number.** `unless X.IsInCombat == 0`
  failed: FO4's console prints "is not in combat" for it. `GetDead` prints
  a value.
- **The harness hid what the user found by hand (2026-11-19).** The
  console's activate needs no prompt and no reach, so the Overseer's
  terminal, which a player cannot use, passed. A missed shot fell back to
  `setstage` and a radroach that never came out died by console `kill`.
  Each failed `check` was kept but never reported, because no FO3 case ran
  `report`. Now:
  - `activate` aims and presses E;
  - the folder ends with a `report` case, so a set-aside check fails the run;
  - `cg04_hall` checks that Kendall wears his armor.

  A seated pose cannot be read through the console (`GetSitting` is 3 even
  through a desk), so sitting is not checked yet.
- **E takes whoever stands in the way.** The playpen gate needed the
  player's own eye (the baby is at scale 0.40) and the middle of the gate's
  bounds, not its hinge. At the party, E toward Mrs. Palmer from 150 units
  opened the Overseer's talk (CG02OverseerA1/A2). `talk` now checks
  `IsInDialogueWithPlayer`: if someone else answered, it leaves with `bye`
  and steps within 64 units. The console answers `IsInDialogueWithPlayer`
  in words ("Actor is in dialogue state with player."), not `>> 1`, so the
  check reads both. **Open:** in runs 64 and 66, Tab did not close the talk
  E had opened, still open minutes later with its choices showing, as with
  Sunny at VMS16 70. So `cg02_mrs_palmer` walks up to 64 first.
  The Overseer stood 52 units in front of the player, facing her, and the
  engine's path stopped 154 units out, so a stuck `walk` now sidesteps
  (A, then D) around whoever stands in the way before it fails.
- **Converted gear has a made FormID.** `{Fallout3.esm:01CBDD}`
  (ArmorVault101Security) is built as `FNV_ArmorVault101Security` under
  the id kept at ledger site `FNV ARMO` (E4608B), so `cg04_hall`'s check
  failed with "no form" (run 72). `local_id` now looks a source record up
  at `equipment.SITES` too. Asked directly, Kendall wore it
  (`GetEquipped >> 1.00`): the NPC armor fix holds in game.
- <a id="atrium-route"></a>**No route found to the atrium door (run 72).**
  The passing runs moved the player to the radroach stop box
  (`player.moveto`); the strict walk from Vault101b's entrance to hinged
  door 05396D never arrived. The engine's path stopped 334 units off, at
  (−4167, −221), with no line of sight to the door (`GetLineOfSight`: can't
  see it), and the same path asked again led north, away from it. The walk
  is now a set-aside `check` with the old move as its fallback, so `report`
  flags it. **Open:** the route a player takes there.
- **E reaches about 150 units.** Stanley's case walked to 400 (the
  console's activate has no reach) and ten presses from 277 did nothing;
  it walks to 100 now. Butch's (CG03) path stopped at 172, so `talk` now
  steps within 64 units whenever E gets no dialogue menu.
- **Beatrice's greet opened an empty menu (run 68).** Stage 40 enables
  her (she starts disabled) and her force greet runs while
  `GetStage CG02 >= 40`, so in FO3 she meets the player on the way to
  Jonas. In run 68 her greet opened a dialogue menu with no choice list
  that nothing closed: `CleanroomDialogue.log` has no line for it, and only
  Beatrice answered `IsInDialogueWithPlayer`. `cg02_beatrice` now waits
  for her greet after Dad's surprise; in run 70 her menu listed its choices
  and the case passed. **Open:** run 68's empty menu did not come back; if
  it does, a player is trapped there too (compare Sunny at VMS16 70).
- **A talk that just closed holds the player.** After Amata's (run 69) and
  Beatrice's (run 70) talks the engine's path moved the player 3–8 units and
  no stride moved it; the same path from the kept game a minute later went
  180 units in 8 s. A stuck `walk` now sidesteps, then waits 5 s and paths
  again (twice) before it fails.
- **A goodbye line ends the talk itself.** `bye` presses Tab for 6 s, which
  does not cut an NPC's goodbye line short (the Overseer's ran 11 s); wait
  with `closed 60 DialogueMenu` instead.

### <a id="s6"></a>S6. Two machines

The desktop instance and the laptop both run cases ([hidden
instance](fo4_story_tests.md#instance)). Shard by game: FO3 on one, FNV on
the other. This needs nothing new beyond pointing each at its own build.

## <a id="l0"></a>Layer 0: data audits

These exist ([data audits](fo4_story_tests.md#data)) and run every build.
Two additions from today:

- **Trigger census:** every activator reference with a primitive (XPRM)
  carries XTRI 12 (L_TRIGGER), as Fallout4.esm's 20 do. The placement fix
  writes it; the census keeps it written. **Built 2026-11-18** in the
  `world` audit (`world_links.trigger_findings`): the 2026-11-18 builds
  hold 75 trigger boxes (FO3) and 1,263 (FNV), all on the layer.
- **Clearing the noise:** the audits' findings are sorted once into the
  review ledger, so "new since the last build" is a real regression. This
  was planned already: 449 dialogue errors, 107 timing errors and 539
  condition reviews on the FO3 run.

## <a id="l1"></a>Layer 1: the stage sweep

This is the [autoplay plan's quest check](fo4_autoplay.md#check-quests), moved
onto the test instance and the case runner. For each quest group, from its
start save (S3):

- `Start()` each quest the source starts. A false `IsRunning()` names the
  empty required alias.
- `SetStage` each stage in order. Collect the Papyrus errors in each
  stage's window, grouped by script and message. A wall of "None object"
  errors on a fragment's first line is a quest whose properties never bound.
- For a stage set by a timer or script, set the one before and wait. If the
  next doesn't come, name its setter from the quest data.
- Check `IsObjectiveDisplayed` against the source's objective lists, and
  that each quest target's alias is filled.

The cases are generated from `quest_plan.json`, the quest data the autoplay
plan already describes: per quest, its stages in order and how the source
sets each one. The preflight reads every SetStage site today
(`quest_progression`, `quest_start`, `quest_targets`); the plan file is
that data written down once.

Scale: thousands of stages a night. What it proves: each stage's machinery
runs, not that a player can reach it.

### <a id="l1-built"></a>Built (2026-11-18; five Fallout 3 runs 2026-11-19 to 2026-11-21, 267 to 56 failed checks)

```bash
py -3.14 -m tools.live.fo4_quest_plan --game FalloutNV.esm --plugin <built FalloutNV.esm>
py -3.14 -m tools.live.fo4_stage_sweep temp/stage_sweep/FalloutNV.esm/quest_plan.json --save <start save>
python -m tools.live.fo4_story_cases temp/stage_sweep/FalloutNV.esm --set SEX=male
```

- **The plan** (`tools/live/fo4_quest_plan.py`) writes
  `temp/stage_sweep/<game>/quest_plan.json` from the preflight's source model
  (`quest_source.SourceGame`, every SetStage and StartQuest site) and its
  progression graph (`reached_stages`: which stages the source reaches). Per
  quest: its FO4 EditorID (`FNV_<EditorID>` for both games, as `spike/cell.py`
  writes it; checked against both built plugins), Start Game Enabled, its
  StartQuest sites, and its stages in order. Per stage: whether the source
  reaches it, whether the build holds it (QUST INDX, with `--plugin`), and
  each setter: `stage` (another stage's result script), `info` (line, topic,
  the speakers its GetIsID conditions allow), `quest script`, `timer` (a quest
  script's GameMode block in a script that reads GetSecondsPassed), `object
  script`, `package`; each with its line and whether its container runs in
  the source.
- **The cases** (`tools/live/fo4_stage_sweep.py`): one `q_<EditorID>.f4test`
  per quest the build holds, beside the plan. Each loads the start save
  (`load`), starts the quest when the source starts it and checks
  `GetQuestRunning`, then for each stage the source reaches and the build
  holds (`--all-stages`: every built stage), in order: when an earlier swept
  stage's result script (10 s) or the quest's timer sets it, waits for it
  first; then `setstage`, `GetStageDone` within 10 s, and the window's
  Papyrus errors. A timer wait lasts the timer's authored length and 10 s,
  at least 30 s: the plan's `seconds` (`fo4_quest_plan.timer_seconds`), the
  largest number set to a countdown named in the conditions around the
  SetStage (its own `set t to N`, or `set <quest>.t to N` anywhere), or a
  count up is compared with; MQ01 105 gets 70 s for its 60 s failsafe. The
  waits are `alone` steps: `until`, leaving each talk that opens meanwhile
  with Tab, since an open talk holds every quest script's poll.
- **Why one case per quest, and soft checks.** The runner stops at the first
  failing case, so a sweep built from hard steps would stop at the first
  broken quest. Every sweep check is `check <step> | <note>`: a failure is
  printed and kept, and the case goes on. `zz_report.f4test` sorts last and
  fails the run listing every failed check. The `load` at each case's start
  is what keeps one quest's fragments (moves, kills, other quests started)
  from poisoning the next; without `--save` the quests run on in one game.
  The source has no "quest line" record, so the group is the quest.
- **The errors step** (`tools/live/fo4_sweep_steps.py`, `errors [seconds]
  [prefix...]`) reads `Papyrus.0.log` forward (its own offset, starting where
  the runner's `Trace` stood), waits 1 s for the log to catch up, and groups
  errors with the preflight's play-test reader (`log_triage.classify`: cause,
  message with names masked, `Script.Function`). An error counts when a frame
  of its stack is a converted script (`FALLOUTNV_`, `FALLOUT3_`, `F3NV_`,
  `TES4Polyfill`, `TES4_`); that frame is the one charged, so a native call
  failing inside one of ours counts too. Errors with none of ours in the
  stack (vanilla, DLC) are ignored. `load` restarts the window 3 s after the
  load ends, so the save's own start-up errors are not charged to a quest.
- **Counts** (2026-11-18 builds, reached stages only): FNV 349 quest cases,
  643 stages, 82 waited for first (404 source quests with stages or a start;
  51 not in the build). FO3 135 cases, 533 stages, 94 waited for (188 source
  quests; 44 not in the build).

**First FO3 run (2026-11-19, laptop, no start save):** 166 quest cases,
549 stages, about 35 minutes after FO4's character creation. 77 checks
failed: 49 timer waits, 4 result-script waits, 3 stages that would not set
(CG01 10, CG03 6, CG03Test 1), and Papyrus errors at 21 stages.

<a id="stopped-quest-fragments"></a>**Open: fragments of a stopped quest see None.**
Most errors (about 200 of 300) are on stages swept after one whose
fragment stopped the quest: FO3's alternative endings (MS03
210/215/225/250, MS16 215/240) and the CG hand-off stages. MS03 stage 210
ran cleanly and ended with `Stop()`. The quest was running again for
stage 215 (`GetQuestRunning` 1), yet the kept game listed all 111
properties of `FALLOUT3_QF_MS03` as None, while the quest script's were
bound. Ruled out, each measured:
- the quest staying stopped: a `startquest` before each later stage
  (runs 2 and 3) changed no count;
- non-Const properties: with the fragment properties `Auto Const` (run 3,
  confirmed `const` in `sqv`) they were still None;
- VMAD layout: the fragment script is named only in the fragment section,
  with its properties, as vanilla's.
Whether real play restarts a stopped FO3 quest, and why FO4 drops the
properties, is not known. The sweep goes around it: the plan marks each
stage whose source script runs `StopQuest` on its own quest (`stops`,
from `quest_source`; 54 in FO3), and with `--save` the stage after one
loads the start save again and restarts the quest.

**Second FO3 run (2026-11-20, laptop, start save
`f3nvtest_fo4_character_creation_male`):** all 189 loads worked, 166 cases.
Leaving out the start save's own two errors (below), 66 checks failed
against run 3's 77: 48 waits, 2 stages that would not set, and errors at 16
stages. The None walls (11 to 17 errors each) are gone from MS03
215/225/250, MS16 215/240, CG00/CG01/CG03 100, CG03Test 2 and MS11 210.
What is left there is one or two single None properties per fragment
(`Disable()`, `Start()` on None), which are bugs of their own.

<a id="unmet-waits"></a>**The unmet waits, triaged (third FO3 run, 2026-11-20, first 103
cases).** 35 waits failed. Each was checked against the source condition
around its SetStage, and the suspect ones against the quest script's
`pass` and `stage` traces in the Papyrus log. None is a converter bug:
- **27: a condition the sweep never meets.** A menu open (CG00 61, CG01 0,
  CGTutorial 52/72/212), a place, item, door, kill or actor state (CG02
  90, CG03 30, CG04 33/144, MQ01 72 needs the ambush mutant dead, MQ02
  20/30/40, MQ04 5/40/50/60/70/75), and the rest of CGTutorial (sneaking,
  hurt, crippled, addicted, irradiated, worn weapon, locations found).
- **5: a talk the sweep left open.** A stage's result script makes an
  actor force-greet (CG04 stage 3, Amata). The quest script's poll then
  traces `held: dialogue` until the case ends, as FO3's GameMode would not
  run in a menu either, so its timers never finish: CG02 98/100, CG04
  141/142/200 (CG04's own stage 2 to 3 timer fired, 6.5 s for 6.3).
- **1: a wait shorter than the authored timer.** MQ01 stage 100 starts a
  60 s failsafe for 105; the sweep waits 30 s.
- **1: the start save's own scene.** The save stands in Vault 101 with CG00
  (the birth) still at its start; each load runs it (stages 5, 6, 8, ...)
  beside the case. Setting CG00 61 was followed at once by CG00's own 65,
  so 62's `GetStage == 61` never held.
- **1: a quest the start save already ran.** ControlRumble is Start Game
  Enabled; its first pass set stage 0 (which stops it) and its do-once
  `initDefaults` before the save, so a restart never sets 0 again, as in
  FO3.

What the sweep needs, from this: close a talk a stage opened before
waiting, take a timer's authored length from the result script that
starts it, not count a wait whose setter tests more than the stage, and a
start save with no scripted scene running. The first two are built (the
`alone` wait and the plan's timer `seconds`, above); the last two are
open.

**Fourth FO3 run (2026-11-20, `alone` and timer lengths):** 60 checks failed,
against 66 in the third: 41 waits, 17 error checks, 2 stages that would
not set. All six targeted waits passed (CG02 98/100, CG04 141/142/200, MQ01
105 with its 70 s wait), and MS11 50 passed too. Two harness bugs showed:
- A stage whose wait passed was then set again from the console. At CG00
  100, CG02 100 and CG03 100 the quest's timer had set it, its fragment
  had stopped the quest, and the second run met the
  [stopped-quest](#stopped-quest-fragments) None wall (CG02: 115 errors,
  one burst 6 s after the wait). A waited stage is now set only
  `unless GetStageDone ... == 1`.
- The console answers `setstage` with "SetStage ignored - please start the
  game or go into a cell first" while the player is between cells, as a
  CG stage moves them to the next age. That happened 7 times. It caused
  both stages that would not set (CG01 10, CG03 6); the other 5 passed only
  because the quest set them itself. `run` now sends the command again each
  second, for up to 30 s, while the console gives that reply.

**Fifth FO3 run (2026-11-20, both fixes):** 56 checks failed: 42 waits and
14 error checks, with no stage that would not set and no ignored
`setstage`. The stage-100 None walls left CG00, CG02 and CG03, and CG01
10 and CG03 6 now set. MQ01 105 and MS11 50 failed again (they failed in
the third run and passed in the fourth); both waits run before the stage
is set, so they are flaky, not caused by the fix. The one-off "cannot
speak a None topic info" `Say` errors move between stages and speakers from
run to run (CG02 22/30/35, MS01 62).

<a id="later-waits"></a>**The later quests' waits, triaged (run 9, 2026-11-20).** Run 9 left
41 waits and no error check (CG03 40's walk-up bind, fixed after it:
[walk-up before its quest](fo4_pipeline.md#walk-up-before-quest)). 26 are
the [unmet waits](#unmet-waits) above. The other 15, read against the
source around each SetStage, all wait on a condition the sweep never meets;
none is a converter bug:
- A kill or count: MS01 200 (mutants dealt with), MS04 45 (5 nest
  guardians), MS04 50 (queen hit, Lesko dead), MS18 50 (5 mutants or every
  Ranger dead), MS11 50 (stage 40's log entry that sets it is conditioned
  on `GetDead` Mister Burke, so it passes only in runs where he died).
- A place or sight: MS01 251 (player in an interior, away from Big Town a
  day), MS04 20 (line of sight to Fred Wilks's body), MS18 20 (player in
  Our Lady of Hope).
- A scene state: MQ11 30 (Liberty Prime's activation, `PrimeActivate == 2`),
  MS01 70 (a training scene finished), MS10 100/150 (the Treeminders
  hostile, Harold burning), MS18 40 (the roof panel fixed).
- A "function" stage: MS08 stage 1 sets `clue4` only for the clue type its
  caller set first, so stage 20 stays unset with the defaults.

<a id="setter-needs"></a>**Waits the sweep cannot meet, marked (built 2026-11-21, not yet
run).** `tools/live/fo4_setter_needs.py` reads the conditions around each
setter's SetStage (each enclosing `if`'s taken branch, and a stage log
entry's own conditions) and the plan keeps the ones the sweep cannot meet
as the setter's `needs`. A condition holds for the sweep when it tests a
stage or a quest, a timer the script counts, a variable at 0 or at a value
a stage result, a line or the setter's own script sets, or a function at
the 0 it returns before anything happens. A `MenuMode <n>` block is a need;
a plain `MenuMode` is not (CG00 0 and 61 pass under it). When every setter
a wait would use has needs, the case writes `unmet` instead of `check`: the
same wait, but a stage that does not come is listed apart in the report
("waits unmet") and does not fail the run. On run 9's plan, 30 of the 41
failed waits are marked, and none of the waits that passed. The other 11
stay checks, on the cautious side: the start save (CG00 62, ControlRumble
0), a plain MenuMode (CG01 0), a function that holds at 0 (CGTutorial 200
and 218 test health and weapon condition below a value), and variables a
script or line sets (CG03 30, MQ02 20, MQ11 30, MS01 70/200, MS10 150).

<a id="fnv-run-1"></a>**Full FNV run (2026-11-21, laptop, start save
`f3nvtest_vcg01_tags_traits_male`, build at `e45d56d6`):** 350 quest cases,
646 stages; 42 of 2,066 checks failed and 17 waits were unmet. No failure
is a converter bug in the quest itself:
- **33 are VCG00 swept from a save after it.** The save stands in Doc
  Mitchell's house with VCG00 done to 100, so its timers never run and its
  fragments act on the unloaded cemetery actors ("no AI process", "does not
  have any inventory"). The [opening case](fo4_story_tests.md#cases) plays
  VCG00 for real; a sweep of it needs the character-creation save.
- **4 are creature idles never built.** `PlayIdle` on None:
  `NVopeningSecuritron`/`NVopeningSecuritronIdle` (VCG00 50/54/60, Victor)
  and `LooseNVPHMCconnectionLost` (VMQHouseFail 1, Mr. House's screen).
  Securitrons stand on FO4's Protectron rig and the screen is an unseen
  speaker, and a creature idle converts only on one of our own rigs
  ([idles](fo4_own_rig.md#idles)).
- **5 are needs the sweep does not meet:** VCG01 20 (the Male/Female box's
  button), VMQNCRFail 2 (VMQ02 objective 25 or 30 completed), CGTutorial
  200/218 (health and weapon condition, as in FO3), and VDialogueVegasNorth
  80 (stage 72 sets 80 only when stage 63 is done, which the sweep does not
  set, so 72 rightly set 100).

Known limits:
- The errors in a stage's window include those of any stage its fragment set
  in turn, and errors that reach the log more than 1 s late fall into the
  next window.
- A `stage` or `timer` setter is waited for even when its SetStage sits
  inside a condition the sweep never meets, so some waits fail by design;
  the failure names the setter for review.
- Not built yet: objectives (`IsObjectiveDisplayed` against the source's
  lists), quest target aliases, naming the empty required alias of a quest
  that does not start (the preflight's `quest_start` alias findings list
  them offline), and a start save per quest group: today every case loads
  the character-creation save (`--checkpoints` on `fo4_creation.f4test`).
- That save stands in Vault 101, and two of its scripts raise errors more
  than 3 s after each load: `CG04ButchRadroachSCRIPT.StartCombat` ("Actor
  has no AI process") and `RobcoProtectronSCRIPT.Activate` (None action
  ref). They land in each case's first window, so every case's start check
  failed on them. Both are fixed in the converter
  ([onload-disabled](fo4_pipeline.md#onload-disabled)); the third and
  fourth runs had none of them.
- `temp/` is gitignored, but `fo4_laptop push` sends the generated cases
  anyway (`GENERATED_CASES`: `temp/stage_sweep`, `temp/route_sweep`), so
  sweeps run on the laptop like any other case.

## <a id="l2"></a>Layer 2: route sweeps

These are fast runs of a quest the way a player moves it on, with travel
cut out:

1. From `quest_plan.json`, per stage, find what the source does to reach it:
   - a line's result script (which INFO, its speaker, its conditions, the
     choices that lead to it in the source's topic tree);
   - a script block (an activation, a trigger, an item picked up, a kill);
   - another stage, or a timer.
2. Turn the route into steps:
   - **A line:** `moveto` beside the speaker, `talk`, `choose` along the
     topic path, `heard` the INFO, `until` the stage.
   - **An activation:** `moveto` beside it, then `activate`.
   - **A trigger:** `moveto` just outside it, then `walk` into it, so the
     trigger itself is tested.
   - **A kill:** `Kill()` the target. **An item:** `AddItem` to the player.
   - **A timer or another stage:** wait.
   - **Plain travel:** skipped by the `moveto`.

   `setstage` is used only where the route can't be found. Such a stage
   is listed as a gap in the generator, not hidden.
3. Each step checks the stage it should set and the line it should play.
   Where a recording exists (layer 4), it also checks the order of the
   lines and stages against the source.

Driving the talk, not just setting the stage, is the point. Today's bugs
lived in the fragment and line-end code that a bare `setstage` skips.

This needs the dialogue verbs `talk`, `choose` and `bye` from the
[progression plan](fo4_opening_progression_plan.md#verbs). They go through
the dialogue menu's test entry point, so the options read are the ones our
menu shows.

When a quest's route can't be generated (a branch on a global, a timing
puzzle, a companion), it gets a hand-written case in layer 3, or a
`setstage` gap.

### <a id="l2-built"></a>Built (2026-11-18)

```bash
py -3.14 -m tools.live.fo4_quest_plan --game FalloutNV.esm --plugin <built FalloutNV.esm> --out temp/route_sweep/FalloutNV.esm/quest_plan.json
py -3.14 -m tools.live.fo4_stage_sweep temp/route_sweep/FalloutNV.esm/quest_plan.json --routes --save f3nvtest_vcg01_tags_traits_male [--quest VCG02 ...]
py -3.14 -m tools.live.fo4_laptop run --profile "New Vegas" temp/route_sweep/FalloutNV.esm --keep-going
```

- **Routes in the plan** (`fo4_quest_routes`). `quest_plan.json` keeps a
  `route` on each line and object-script setter:
  - A line: its speaker's placed references (the line's GetIsID), display
    name, and the prompts to pick. The prompts are found back from the
    line's topic through the choices of lines that speaker may say, up to
    the greeting (said, not picked), a top-level topic or an added topic.
    Each prompt is the line's own, else its topic's name.
  - An object script: its step by block (`trigger`, `activate`, `kill`,
    `take`) and the placed references whose base carries it. A block
    another actor must run (`OnTrigger SunnyREF`) gets no step.
  - The source model (`quest_source.SourceGame`) keeps the prompts, topic
    names, display names, placed references by base and script FormIDs
    for this. `quest_source.script_bases` reads which base runs each
    script.
  - Each stage's `ends`: `fail` or `complete` when one of its log entries
    has the Fail Quest or Complete Quest flag (QSDT flags 2 and 1).
- **The cases** (`fo4_stage_sweep --routes`, `fo4_route_steps`). Per stage,
  the live setters' routes, tried in turn (at most 3):
  1. waited for, alone: an earlier stage of the run, the quest's timer, or
     a line the run already played;
  2. the lines, as **one conversation per speaker**: `moveto` the speaker,
     `look`, `talk`, `look`, at each depth `choose A || B` over every way's
     prompt there, `heard` any of the lines (`heard 60 Sunny Smiles
     0015D97E,0015F8B6`), `bye`. Trying the lines, or the ways to one line,
     in separate talks fails: a Say Once greeting the first talk used up
     no longer offers its choices to the second (run 3: Sunny's "See?
     You're getting the hang of it…" offered "[END TUTORIAL]" to a talk
     that wanted "Couldn't hurt.", and the next talk got only "I wanted to
     ask you some questions."). A line has up to 3 ways (`prompts`, then
     `more`), shortest first;
  3. each object script's step;
  4. waited for (60 s): the quest script or an actor's package;
  5. none: a gap, `setstage` as in layer 1.

  Every step is a soft `check` behind `unless GetStageDone … |`, so once
  the stage is done the rest are skipped. Then `unless GetStageDone … |
  run setstage …` sets it only when no route did, so a failed route doesn't
  stop the quest and a finished quest isn't restarted, and the stage must
  be done. The quest start works the same way, checked with
  `GetQuestRunning`, with `startquest` as the fallback.
- **A speaker who starts disabled** is enabled first: the plan lists the
  lines and scripts that call `<ref>.Enable` on one of a line's speakers
  (`enabled_by`). The first usable one joins its own speaker's
  conversation, and the disabled speaker's talk then waits
  (`until 60 <ref>.GetDisabled == 0`) before it starts. Trudy's VCG02 line opens with
  Sunny's "[END TUTORIAL] I've had enough of geckos for one day.", whose
  follow-ups end in 0015F8B6 ("Hey, do me a favor. Trudy…"), which enables
  Trudy and Joe Cobb in its end result script.
- **Story order** (`--chain`, with `--quest` in story order): the quests
  run one after another in one game. The files are numbered
  (`q_01_VCG02.f4test`), only the first loads `--save`, and the cases share
  one record of done stages and played lines, so a stage or start another
  quest's stage sets is waited for. Stages flagged Fail Quest are left out
  (VCG02 100 kills Sunny, whom VMS16 needs; VMS16 110). Each quest then
  ends the way the source ends it: a `complete` route block runs a line or
  script that calls `CompleteQuest` (the plan's `completes`), checked with
  `GetQuestCompleted`, with `completequest` as the fallback. A quest can end
  with no stage at all: after stage 50, VCG02 runs on objectives and
  quest variables. Sunny's "Couldn't hurt." (which also starts VCG03) needs
  the other wells' geckos hunted first (objective 60). Trudy's greeting
  ends it after "[END TUTORIAL]". The saloon's actors (Trudy, Joe Cobb) stay
  disabled until one of Sunny's endings plays: a console `completequest`
  does not enable them. `--checkpoints` saves after each quest, so
  `--from VMS16` resumes there.
- **Lines the routes reach** also count follow-ups: a follow-up line is said
  on from the line it follows, with nothing picked
  ([follow-ups](../commentary/tools_preflight.md#dialogue-loss)), and a
  GREETING line that is some line's follow-up is reached through that line
  first. Sunny's "Couldn't hurt." is a choice of a follow-up of a follow-up
  of her greeting. When several lines set a stage, one whose speakers all
  start disabled (record flag 0x800) is tried last.
- **Objectives a line's way needs.** FNV lines test objectives
  (`GetObjectiveCompleted`/`GetObjectiveDisplayed`, CTDA 420/421; FO3 has
  neither). The route keeps the lone `== 1` tests of its first way's lines
  (`needs`), the plan lists the sites that `SetObjective…` it (`needs[].by`),
  and the block runs the first usable one first, a line in a talk of its
  own. Sunny's "Okay, I'm in." (VCG02 25) is a choice of greeting 0010A1EC,
  which wants objective 10 done: `VCG02TargetSCRIPT.OnHitWith` after three
  bottles, so the block shoots the seven placed targets (`OnHitWith` is the
  `shoot` route). "Couldn't hurt." wants objective 60 shown: the other
  wells' geckos killed. 195 of 1,126 FNV lines carry needs (96 met by a
  talk, 19 kill, 5 activate, 3 trigger, 1 shoot; 94 by none usable).
- **A first meeting.** A speaker's Say Once greeting conditioned on the
  speaker alone is said before anything else, and offers only its own
  choices (Ringo's "I'm not an enemy…", Jessup's "Well, I'm not, and I
  believe you have something of mine."). A line reached from the topic list
  also gets that greeting's shortest chain to a line handing the list back,
  ahead of its prompts, as another way; 425 of 1,126 lines gained one.
- An enabler's talk is skipped once the speaker it enables is enabled
  (`unless <ref>.GetDisabled == 0 | check …`): VMS16 5 had re-talked to
  Sunny for Trudy.
- **Object scripts on references outside the loaded cells.** A placed
  reference that is not persistent has no form until its cell loads ("no
  form"), so a route on one first goes there (`goto`): `coc <cell>` for an
  interior, else `cow <world> <x> <y>` (grid cell = position / 4,096), then
  `wait 2` and `ready 120`. The world and cell EditorIDs carry the build's
  `FNV_` prefix.
- **A disabled carrier.** A step whose reference (or its enable parent,
  XESP) starts disabled gets `enable`, and the plan lists the sites that
  enable it (`enabled_by`), run first like an objective's.
- **A line nobody picks.** A line no player prompt reaches (no choice
  chain) but that a script `Say`s or `SayTo`s gets `said_by`: the sites
  saying its topic, run instead. VCG02 20's bark (0010A1E6) is Sunny's
  `SayTo` from her patrol trigger.
- **A block another actor runs** (`OnTrigger SunnyREF`) gets `actor` and is
  waited for. VCG02 20 is set when Sunny's package walks her into the
  patrol trigger while the player stands in it.
- Needs nest to `DEPTH` 3 (a need's site may have needs of its own), and
  `Routes` works out each line's and script's route once (36.5 s for the
  FNV plan; over 300 s without the cache).
- A `shoot` route walks to 600 units of its first target, then fires one
  shot at each carrier.
- <a id="fighting-controls"></a>**Fighting controls before a shot.** FNV
  keeps the player's fighting (and movement) off in Doc's house until the
  player walks out through `VCG01RemoveDocCarebearModeTriggerSCRIPT`
  (OnTriggerEnter player: `EnablePlayerControls 1 1 1 1 1 1`). A run that
  `moveto`s from the save past it can't fire: in run 9 the seven shots at
  the VCG02 bottles fired nothing (no `weaponFire`, the 5.56 count stayed
  30), and the laptop's `GetPlayerControlsDisabled` listed fighting
  disabled right after the load. Its value read 0 all the same: the
  converted scripts toggle a shared InputEnableLayer
  (`F3NV_PlayerControls`), which the condition doesn't see, so it can't
  guard a step. So a `shoot` route keeps `controls`: the route of the
  script nearest its target (same world or cell) whose block a player
  walks into or activates and whose `EnablePlayerControls` turns fighting
  on (the third flag; a flag left out enables). The case takes it right
  after `load`, before any quest, once per script for the whole chain:
  that trigger also runs `StopQuest VCG02`, so it can't wait for the
  stage that shoots. Only object scripts count; a line or quest stage that
  turns fighting on is not looked for.

  With the trigger walked first, the rifle fires and the bottles take the
  hits. In run 10, 6 `Hit` traces came from `VCG02TargetSCRIPT`, and
  objective 10's global turned 1 on its own. Probes that set VCG02 10
  from the console instead of starting it by Sunny's talk logged no hits
  at all, so they say nothing about the bottles. After the third hit Sunny
  comes over and says greeting 0010A1EC herself. So:
  - a needed objective's sites stop once it is done (each step behind
    `unless <objective's global> == 1`);
  - `talk` takes a dialogue its speaker already opened
    (`<ref>.IsInDialogueWithPlayer`) instead of waiting for it to close.
    Run 10's stage 25 failed on that: "another conversation stayed open".

  Also seen in these runs:
  - `VCG02SunnyShotReaction` fails to bind on all seven bottles (null
    form 0849AB90), so each hit's reaction raises "cannot speak a None
    topic info" (6 in run 10).
  - The carebear trigger's script raises `ForceActive() on a None object`
    in OnTriggerEnter (line 91 of its .psc) and an error in OnTimer
    (line 67).
- <a id="objective-fallback"></a>**An objective a talk needs falls back
  to the console.** After the sites that should set it, the block checks
  the objective's mirror global (`TES4ObjDone_<quest>_<n>` or
  `TES4ObjShown_…`, which the converted line condition reads;
  [objective conditions](../commentary/tes5_import_conditions.md#fallout-objective-conditions))
  for 10 s. A failed check is reported as usual. Then, only while the
  global is still 0, it runs `setobjectivecompleted FNV_<quest> <n> 1`
  (or `…displayed`) and `set <global> to 1`. So a route that can't set
  the objective (the bottles above) doesn't stop the talk behind it from
  being tested: VCG02 25's "Okay, I'm in." is still offered.
  - **Quest variables too.** A lone `GetQuestVariable <quest> <n> == N`
    on a way's line is a need like an objective. Its sites are the
    `set <quest>.<var> to N` lines of result and object scripts, and its
    fallback is `set TES4QVar_<quest>_<var> to N`. Ringo's "What are you
    going to do about the Powder Gangers?" (VMS16 10) wants
    `VFreeformGoodsprings.bKnowRingoHiding == 1`; in run 12 it was offered,
    and VMS16 10 was set by its own route.
  - A talk run only for a need is skipped once the need holds (run 12:
    Ringo's "Sunny's with us." was looked for after `bSunnyHelp` was
    already 1).
- **Picking a row** presses the digit key through the game window's own
  input (`hidden_launch.tap_key`). The old `game_input` path never reached
  the dialogue movie for rows past the first: run 11's "[END TUTORIAL]"
  (row 2) logged no `picked` in the dialogue DLL's log.
- **`-` in a `choose`** means nothing is to be picked at that depth. It is
  written when one of the talk's ways has already ended there (a greeting
  way ends before any pick). Run 11's VCG02 start failed with an empty
  list.
- **Run 12** (29 of 208 checks failed; run 11: 45 of 213). VCG02 complete
  and Ringo's VMS16 10 now pass on their own routes. Left:
  - **A conversation the game carries over.** After Ringo's "Let's do
    this." (VMS16 65), the same menu lists Sunny's "How many are there?"
    and "Let's go." (VMS16 70's topic,
    `VFreeformGoodspringsGSSunnySmilesTopic008`, whose lines are all
    `GetIsID GSSunnySmiles`). Ringo's line has no choices, so no route
    reaches "Let's go." from his talk. `talk` to Sunny then saw "another
    conversation" (Sunny not `IsInDialogueWithPlayer`). From 16:07:13 to
    16:08:54 the dialogue DLL logged no Tab event, only the menu hiding and
    re-showing that list, so `bye` could not close it. VMS16 70 and 100
    failed behind it. **Open:** whether a player is stuck in that menu
    too. FNV would list only topics Ringo can say.
  - **No dialogue menu at all:** Ringo at VMS16 60 (his talk opened about
    50 s later, at stage 65) and Manny at VMQ01 50, each activated every
    6 s for 30 s.
  - Trudy at VCG03 complete (talk 2): another conversation stayed open.
- **Where shooting matters** (FNV plan): only two scripts make a `shoot`
  route. `VCG02TargetSCRIPT` covers the 7 bottles, for VCG02 and
  CGTutorial; `CG02TargetSCRIPT` has no placed reference in FNV. In FO3 it
  is CG02's BB targets. FNV's other 56 hit scripts are `OnHit`
  (no `With`) on actors reacting to being hit, so none is a stage route.
- `unless` and `check` leave filling source records to the step they run,
  so a record absent from a region build fails that one check, not the case
  (VMQ01 failed on the Tops trigger in run 4).
- `fo4_laptop push` removes the generated cases the checkout no longer has,
  so a renumbered chain doesn't run old files too.
- `fo4_laptop stop` (and `push`) first end the laptop's scheduled run task:
  a `--keep-going` run relaunches a game stopped under it and keeps
  `run.log` open, so the next `run` failed with WinError 32.
- **New verbs:** `bye` (Tab until the dialogue menu closes), and `choose`
  scrolls a list longer than 5 rows (the list's `move 1`, as Down does).
  `fo4_laptop push` sends `temp/route_sweep` too.
- **Coverage** (FNV, 643 reached stages): talk 299 (46%), kill 89,
  trigger 23, activate 12, take 6: 429 by a player's action (67%); 142
  waited for (22%); 72 gaps (11%). Of 313 quest starts, 240 are gaps
  (`startquest`), 51 talks.

**First runs: Goodsprings** (VCG02, VCG03, VMQ01, VMS16; 21 stages and
the starts, from `f3nvtest_vcg01_tags_traits_male`, about 17 minutes):
- **Set by their own route:** VCG02's start (Sunny, "Doc Mitchell said
  you could teach me…"), 10 (the same line), 35 (her greeting), 40 (her
  package), 45 and 50 (the geckos killed), 100; VMS16's 50, 60, 65 (talks
  to Sunny and Ringo) and 100 (the Powder Gangers killed).
- **Fixed in the harness on the way:**
  - A `kill` route killed only one carrier; a death count (the three
    geckos, six Powder Gangers) wants all, so it kills every one.
  - The fallback `setstage` restarted a quest the route had finished and
    stopped. Its stage 100 fragment then ran again in the restarted
    quest, whose properties read None: 23 errors in `QF_VMS16`. The
    fallback is now `unless GetStageDone … | setstage …`. This is the
    lead from the [stage sweep](../audits/fo4_fnv_stage_sweep.md): its
    VMS16 and CG02 errors came from the same restart.
  - Menu names ignore case ([menu names](fo4_story_tests.md#menu-names)).
  - A reputation notice (the Powder Gangers box) blocked the next talk;
    `talk` accepts an open message box before each activation.
- **Left open:**
  - **Quest order** (now [story order](#l2-built), `--chain`). Trudy
    (VMS16 5) starts disabled until Sunny's tutorial ends, so a save
    before VCG02 can't reach her. (`bAllowEnableTrudy`, an earlier guess,
    is set only when Sunny dies.)
  - **Choices only an NPC opens.** VCG02 25's "Okay, I'm in." is a choice
    of the line Sunny says when she comes to the player (stage 20, a
    gap here). A topic added by a script counts as a root the player can
    pick, which is wrong when only the NPC's force greet lists it.
  - **A first meeting's own choices.** Ringo (VMS16 10) and Jessup
    (VMQ01 100) open with a greeting whose choices come first; the route
    only follows the topic list.
  - **Sunny at VMS16 70:** once, the menu opened with no list and Tab did
    not close it; it passed in the next run.
  - **Another line than the route's:** at VMS16 110 Ringo talked, but not
    with the greeting the route waits to hear (001093C6).

  With those fixes, VMS16 alone: 12 of 73 checks failed (18 before), all in
  the open items above.
  - **Waits:** VCG02 5 (`VGenericTimerSCRIPT`) and 30 (her walk to the
    well) did not come within 60 s.

## <a id="l3"></a>Layer 3: scene runs

These are the cases we have been writing, kept for places where many things
can go wrong at once:

- the openings, up to the free world: FO3 to the Vault exit, FNV through
  Goodsprings;
- scripted set pieces: scenes, forced greetings, escorts, followers,
  ambushes;
- anything that walks the player through triggers and doors.

Each is checked against its source recording (layer 4) once that exists,
and the [behavior recorder](fo4_story_tests.md#recorder) adds facing,
idles and seating.

## <a id="l4"></a>Layer 4: the source games as the answer key

Recordings of FO3 and FNV themselves turn "is this right?" from a guess
into a diff. They compare the order of events and how they relate, not
seconds: the same lines in the same order, the same stages, the same
objectives, a door that stays open.

**What exists.** The FO3 recorder spike (`F3Recorder.dll`,
`tools/live/fo3_record.py`, `fo4_laptop record`;
[recorder spike](fo4_story_tests.md#baseline)) runs on GOG Fallout 3
1.7.0.3. It takes console lines at the main menu and in the first cell,
and writes changes only:
cell, actors, packages, sitting, talking, the line each actor says, every
quest's stage. Its first run reached CG00 stage 10.

**To build:**

1. **The FNV recorder.** The same timeline from an xNVSE plugin, on the
   xNVSE and JIP LN sources in `references/`. It is a test-only DLL, like
   the FO3 one. NVSE has more reads than FOSE, so it is the easier of the
   two. The [nv-rs spike](#nv-rs) comes first: if it holds up, it replaces
   this plugin.
2. **One timeline format** for FO3, FNV and our FO4 trace, in source
   FormIDs, which all three already use, plus a diff tool that reports
   order differences per quest.
3. **Driving the source game.** Three ways, cheapest first:
   - *Jumps:* layer 2's route steps are console lines, and FO3/FNV have
     the same `moveto` and `coc`. Talking and choosing go through the
     recorder plugin calling the game's own menu functions, as upstream's
     TES4 backend does. So the generated route runs in both games, and the
     source run is the expectation.
   - *Scene cases:* the same case files, with walk and activate made
     through the recorder plugin (pathing the player as we do on FO4).
   - *A played recording:* someone plays the stretch normally with the
     recorder on. This is optional, never required, and gives a reference
     for anything the driver can't do yet.
4. **When to record:** once per route or scene, and again only when the
   case changes. The source game doesn't change.

A difference that FO3 or FNV itself shows (a known source bug) is marked in
the recording's notes and skipped by the diff, so no one chases it in our
build.

### <a id="engine-ports"></a>The FNV engine ports: nv-rs and NVForever

Two open-source projects rebuild New Vegas's engine in Rust. Both are
GPL-3. Reading them and using what they show is fine; copying their code
into this repo needs a license check first. Both move fast, so cite a
commit with any claim. Neither covers Fallout 3, though much of what they
document holds for FO3's engine too. What is said here comes from their
READMEs and status pages (read 2026-11-17), not from running them.

- **[nv-rs](https://github.com/slaterain/nv-rs)** translates
  FalloutNV.exe 1.4.0.525 into Rust function by function, checking each
  piece against the original. It tracks all 66,259 functions; its function
  map is `references/nv-rs/engine_map.tsv`. Quests, dialogue and scripts
  are listed as live, AI and pathfinding as fully translated. Physics is
  listed as not yet compared in play, and the game as playable with bugs.
  It has a single-threaded stepped mode (`NV_THREADS=stepped`) used for
  test runs.
- **[NVForever](https://github.com/LootJunkieAzza/NVForever)** is a
  clean-room rewrite. Its behavior comes from recordings of the original
  game and a wiki, and many notes are marked "[hypothesis]". It has a smoke
  runner (`tools/smoke`, scenarios driving console and script steps), a
  parity lab comparing it with the original (`parity-lab/`), and one
  behavior note per system (`docs/spec-notes/`).

**How they are used here:**

- **Engine behavior.** The byte-matching decompilation
  (`references/fnv_decomp`, [research note](research/fnv_decomp.md)) stays
  the authority. nv-rs is the same code in readable Rust and a faster way
  in. NVForever's spec notes are a map of what to look up; a claim from
  them is checked against the decompilation before anything is built on it.
- <a id="nv-rs"></a>**The nv-rs spike: a recordable New Vegas.** If nv-rs
  runs FNV's own quest, dialogue and AI code, then adding the layer 4
  timeline to its source may be much cheaper than the xNVSE plugin. It
  would also be easier to drive, since its code can be changed.
  1. Build nv-rs on the test machine against the Steam 1.4.0.525 install.
  2. Add a timeline writer in the [one format](#l4): stage changes, each
     line begun and ended (speaker, INFO), objectives, packages, positions.
  3. Record FNV's opening through the Vit-o-matic (VCG00 to VCG01 stage 65)
     in nv-rs, and the same stretch in the real game (a played recording,
     or the xNVSE plugin's first slice if that is quicker).
  4. Compare the two. If they agree on the order of stages, lines and
     objectives, nv-rs becomes the FNV recorder and step 8 shrinks to the
     diff. If not, the differences are listed and the plugin is built as
     planned.

  Its own bugs are the risk: a difference against nv-rs is a lead, not a
  finding, until the real game agrees. A route nv-rs can't finish falls
  back to the real game.

  **Result (2026-11-18, steps 1 and 2 done):** built in 3 minutes; a
  timeline patch recorded FNV's opening from the menu to VCG01 stage 15 in
  110 s, unattended, with stage and line events that match the records;
  the real-game comparison (steps 3 and 4) is still to do, through nv-rs's
  own `nv-trace`. [Findings](research/nv_rs.md).
- <a id="ttw"></a>**Fallout 3 through Tale of Two Wastelands.** TTW rebuilds
  Fallout 3's content as New Vegas data, played on the FNV engine; the TTW
  add-on *Tales from Separate Wastelands* keeps the two games apart. If an
  FNV engine port runs TTW, the [nv-rs](#nv-rs) timeline would record FO3's
  quests too, without the FOSE recorder's custom work (FOSE 1.3 beta 2 has
  no console interface, and the recorder runs lines through hand-matched
  engine addresses on 1.7.0.3 English only). Nobody has tried TTW on either
  port yet. Checks before relying on it:
  1. Whether nv-rs or NVForever loads TTW at all, and plays CG00 to CG01.
  2. Which FormIDs TTW gives Fallout 3's records. Our trace names
     Fallout3.esm's own FormIDs; if TTW keeps Fallout3.esm as a master they
     line up, otherwise a map from TTW's records back to Fallout3.esm's is
     needed (by EditorID, checked for collisions).
  3. What TTW changes in FO3's scripts and quests to fit the FNV engine
     and the merged world (its start, travel between the wastelands, its
     own fixes). Each change is a place where TTW's timeline differs from
     FO3's for TTW's reasons, not ours. So TTW is checked against the FOSE
     recorder on a stretch both can play (CG00 to CG01) before anything is
     judged by it, and its known changes are listed in the recording's
     notes, as a source bug is.
  4. That the test machine can hold it: TTW's installer needs both games
     installed and builds its data from them.
- **NVForever's notes and parity lab** are read for open questions before
  playing them out. The first is the [Nightkin](fo4_story_tests.md#recheck)
  re-running a package fragment far from the player (its package note).
  Its recordings of the original, where they cover a stretch we test, are a
  second reference.

## <a id="order"></a>Order and effort

Effort is agent working days. The order puts speed first, then breadth,
then the reference.

| Step | What | Size | Needs |
|---|---|---|---|
| 1 | S2 check (archive names FO4 loads) | done: none needed | |
| 2 | S1 scripts-only build: the existing hotfix, per game, with the property guard | done 2026-11-17 | |
| 3 | S3 checkpoint load hang (done 2026-11-17); start saves per quest group (with step 5) | S | |
| 4 | S4 failure snapshot and live query, S5 repeats (done 2026-11-17); S6 two machines | S, under a day | |
| 5 | `quest_plan.json` from the preflight's quest data; layer 1 stage sweep cases | done 2026-11-18; run on Fallout 3 ([unmet waits](#unmet-waits)) | steps 3 to 4 |
| 6 | `talk`, `choose`, `bye` through the dialogue menu's test entry point | done 2026-11-18 | |
| 7 | Layer 2 route generator; the first sweep, FNV's Goodsprings quests | built 2026-11-18, first runs ([l2](#l2-built)); next: quests in story order from one game | steps 5 to 6 |
| 8a | [nv-rs spike](#nv-rs): build it, add the timeline, record FNV's opening, compare with the real game | M, 3 to 4 days | |
| 8b | [TTW on the port](#ttw): load it, play CG00 to CG01, compare with the FOSE recorder's timeline | M, 2 to 3 days | step 8a, TTW installed on the test machine |
| 8 | FNV recorder: nv-rs if 8a holds up, else the xNVSE plugin; one timeline format and the diff | S with nv-rs, L (1 to 2 weeks) without | step 8a |
| 9 | Route steps run in FO3/FNV through the recorders; layer 2 checked against them | M, 3 days | steps 7 to 8 |
| 10 | Layer 0 additions: trigger census, ledger pass | S, 1 to 2 days | |

After steps 1 to 4, a script fix should cost about 5 minutes from edit to
answer, not 20 to 25. After step 7, a night covers the stages of every
quest, plus the routes of every quest the generator can route.

Scene work (layer 3) continues alongside, on the openings, with each step
making it cheaper.

## <a id="open"></a>Open questions

- How much of a quest's route the generator can find from the records.
  Measured on the first sweep: the share of stages with a route, a `setstage`
  gap, or a hand-written case.
- Whether nv-rs plays FNV's opening the way the real game does
  ([spike](#nv-rs)): it plays it to VCG01 stage 15 with a background
  window; the comparison with the real game, and a run with no window, are
  still open ([findings](research/nv_rs.md#verdict)).
- Whether an FNV port runs [Tale of Two Wastelands](#ttw), which would let
  one recorder cover both games, and how far TTW's FO3 differs from FO3.
- Whether FO3's recorder can run the dialogue choices layer 2 needs.
  FOSE 1.3 beta 2 has no console interface, so the recorder runs lines
  through the game's own handler on 1.7.0.3 English
  ([recorder spike](fo4_story_tests.md#baseline)).
- Whether far-off actors running package fragments over and over (FNV's
  REPCON Nightkin, [re-check](fo4_story_tests.md#recheck)) is a general
  cost. It slowed every line end in the openings, and a stage sweep makes
  it easy to count.
