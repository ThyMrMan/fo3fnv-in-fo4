# Plan: story runs that catch scene bugs before anyone plays (2026-11-17)

Status: built and running on the test laptop: FO3 into CG02 and FNV through the Vit-o-matic pass for both sexes ([progression plan](fo4_opening_progression_plan.md#order)). Status lives in [ROADMAP.md](ROADMAP.md).
Expands the [autoplay plan](fo4_autoplay.md) and the
[regression plan](fo4_regression.md) with what upstream's harness already
does for Morrowind and Oblivion.

**Goal.** A converted opening (FO3's Vault 101, FNV's Goodsprings) plays
itself in a hidden copy of the game. The run reports every place it
went off course: a line missing or swapped, a stage that never came, a
speaker facing away, an idle cut mid-line, guests leaving their seats. A
fix is proven against that report before the user plays it.

## Contents

- [Why the earlier plans miss these bugs](#gap)
- [What each approach would have caught](#coverage)
- [What upstream built](#upstream)
- [1. A hidden test instance](#instance)
- [1b. A dedicated test machine](#laptop)
- [2. Story cases](#cases)
- [3. The behavior recorder](#recorder)
- [4. The source game as the answer key](#baseline)
- [5. The data audits: what they can and can't see](#data)
- [How far it goes](#reach)
- [Order and effort](#order)
- [What it needs from the user](#needs)

## <a id="gap"></a>Why the earlier plans miss these bugs

The bugs that took the most rounds since 2026-11-10 were all in the
FO3 opening's scripted scenes, and all about timing and behavior:

| Play test | Bug | Kind |
|---|---|---|
| 2026-11-16 | Dad didn't walk to the intercom (FO3's Once Per Day flag) | package condition |
| 2026-11-16 | Dad talked to the wall after the intercom, an idle looping | idle never released |
| 2026-11-16 | Dad stood still instead of walking to the BB gun room | greet fired outside its trigger |
| 2026-11-17 | Dad's intercom reply never played for a male player; a generic greeting instead; the party stopped | wrong line chosen |
| 2026-11-17 | Dad's idles cut mid-line in the Scene6 talk | the 11-16 idle release firing late (4 of 11 releases) |
| 2026-11-17 | Dad facing away at the surprise | FO3's `Look` turns the body, FO4's `SetLookAt` the head |
| 2026-11-17 | Guests standing after the Overseer, sitting again elsewhere | lead: 469 nearby re-evaluations in the session, 22 to 36 actors each |

The [autoplay plan](fo4_autoplay.md#check-quests) sets each stage
directly and proves "this stage's machinery works". That skips exactly
the part that broke: the stage is reached, but by the wrong line, late,
or with actors doing the wrong thing. Its dialogue check `Say`s each topic
alone, so a line chosen wrongly in context (the male intercom reply) still
passes. Nothing in either plan watches where an actor faces, what idle it
plays, or whether it stays seated.

## <a id="coverage"></a>What each approach would have caught

| Bug | Data audits today | Autoplay plan as written | Story case | + recorder | + source baseline |
|---|---|---|---|---|---|
| Dad not walking to the intercom | no | no (stage set directly) | yes: `until` the stage times out | yes | yes |
| Idle looping at the wall | no | no | no | yes: idle running past the line's end and the package change | yes |
| Greet outside its trigger | no | no | yes: Dad's line heard far from the range | yes: distance at the line | yes |
| Male intercom reply | partly: a scene-target audit could ([below](#data)) | no (Say per topic) | yes: `hear` names the wrong INFO | yes | yes |
| Idle cut mid-line | no | no | no | yes: idle stop inside a line | yes |
| Facing away | no | no | no | yes: heading to the listener during the line | yes |
| Guests standing | no | no | no | yes: sit state dropped with no package change | yes, and it says whether FO3 did the same |

Rows marked "no" under data are runtime behavior: the records are right,
the engine does something else with them. Only a run can see them.

## <a id="upstream"></a>What upstream built

`bryantmh/tes4skyrim` master, read 2026-11-17: its headless testing
commentary (`headless_testing.md`), `tools/live/test_instance.py`, `tools/live/hidden_launch.py`,
`game_bridge/sandbox/`, `tes_runtime/common/test_runner.{h,cpp}`, and 184
case files under `tes_runtime/*/testdata/quests/` (Morrowind main, Temple,
Tribunal, Bloodmoon, Tamriel Rebuilt, Oblivion main, Nehrim main).

- **A hidden, isolated instance.** Hard links to only the vanilla files
  plus the converted mod, launched suspended on its own Windows desktop (it
  renders and ticks, but never takes focus or input), with a DLL that
  answers Documents and LocalAppData from a sandbox folder so the player's
  INIs, saves and logs are never touched. Muted by keeping the audio
  session at zero, so line lengths stay real. Launch to ready in 4 to 5 s.
- **Faster than real time.** `iFPSClamp=N` advances each frame a fixed
  1/N s: N=6 runs about 11 times faster.
- **Story cases** in a small step language, played as a player would:
  `talk`, `ask`, `choose`, `bye`, `activate`, `walk`, `hear <speaker>
  [text]` (a line begun, from the subtitle queue), `until <ticks>
  <condition>`, `expect`, `run` for console stand-ins (`coc`, `kill`).
  A case never sets a stage a player couldn't.
- **Checkpoints**: a save after each passing case, and `--from <case>`
  reruns from there, so a fix is retested without replaying the quest.
  `repeat_case` runs one case N times in a row, because one pass proves
  nothing for an intermittent bug.

The FO3 opening is mostly scenes the player watches, which is what `hear`
and `until` cover.

## <a id="instance"></a>1. A hidden test instance

Port upstream's instance to Fallout 4. Checked in the installed 1.11.240
`Fallout4.exe`: it reads `iFPSClamp`, `bAlwaysActive`,
`sStartingConsoleCommand`, `bDialogueSubtitles` and `fAudioMasterVolume`,
and imports `SHGetFolderPath` (the call upstream's sandbox answers);
`f4se_loader.exe` and `f4se_1_11_240.dll` are installed.

- **The folder**: hard links to Fallout 4's own files, F4SE, the Address
  Library, and the built mod folders the run needs (the plugins, archives,
  `F3NV.dll`, Cleanroom UI, `F3NV - Trace`). This replaces the autoplay
  plan's MO2 `Autoplay` profile: no MO2, no window, and the user can keep
  using the PC.
- **Hidden launch**: upstream's `hidden_launch.inject` starts the game
  suspended on its own desktop, loads the extender's DLL and calls its
  start export. Step 2 reads `f4se_loader.exe` for F4SE's equivalent
  (which export, which arguments) before porting it.
- **The sandbox DLL** answers My Games from the instance's own folder.
  It is a test-only DLL, never shipped ([needs](#needs)).
- **Speed**: `iFPSClamp` with the rate measured on the instance, as
  upstream did; cases that assume time use `until`.

**Built (2026-11-17), not yet working end to end:**

- `tools/live/fo4_test_instance.py`: `build` hard-links the game, F4SE and
  the mods of an MO2 profile (default "Fallout 3") into `<drive>\Fallout 4
  Test` (754 files, 14 mods). It copies config files (`.ini`, `.json`,
  `.txt`) instead, so the game never writes into a mod folder. Slot N
  lives in `Fallout 4 Test N` with its own pipe and desktop. Fallout 4's
  new-game intro (`Video\Intro.bk2`, which MQ101 stage 0 plays,
  interruptible; its menu is `PlayBinkMenu`) cannot be emptied: an empty
  file leaves the menu open on a black screen (2026-11-17), so a case
  skips it with T twice: the first shows the skip prompt, the second
  skips (Esc does nothing).
- `tools/live/hidden_launch.py`: upstream's launcher. F4SE starts the same
  way SKSE does: `f4se_loader`'s stub and `StartF4SE` at ordinal 1.
- `tes_runtime/fo4_test/`: `TESSandbox.dll` (upstream's, unchanged) and
  `F3NVTest.dll`, a CommonLibF4 plugin with a pipe.
  - The pipe speaks `game_bridge.py`'s protocol (`ping`, `status` with the
    open menus, whether the player exists, and the player's cell;
    `console`; `button`).
  - `console` runs a line through `Script::CompileAndRun` on the main
    thread and returns what it printed. Two engine details, checked in the
    1.11.240 exe:
    - Handlers print only in console mode, the thread-local byte at 0x830
      (`RE::TLS::consoleMode`; `GetStage`'s print helper `0x59CB40` tests
      it). The console menu sets it around each line; the bridge does too.
    - `ConsoleLog::AddString` drops new text once the log holds 0xFFFE
      characters, so a long session returned nothing. The bridge empties
      the log (`BSString::Set`, `0x1E64F0`) before each line and returns
      what is in it afterward.
  - `button` presses the open message box's button with that label, as its
    Flash button does: `0x107A2A0` (ID 4486575) closes the box and gives
    the callback the index. `currentMessage` is at menu+0xF0 on 1.11
    (CommonLibF4's header says 0xE8).
  - `coc` from the main menu waits for `status.player`: a `coc` before the
    player exists crashes in `PlayerCharacter::CenterOnCell`.
  - A line that holds the main thread past 20 s (`coc`) answers
    `E_LOADING` and still runs; the task owns its result, because an
    earlier version wrote into a stack frame that was already gone and
    killed the game.
  - `build.bat` builds both DLLs; CommonLibF4 is mirrored from `tools_ext`.
- Measured: the redirect works (INIs, logs, saves and Plugins.txt all go
  to the sandbox); every F4SE plugin loads; the main menu is reached; the
  console answers there.
- **Open:** after `coc QASmoke` from the main menu, the hidden game's
  memory and Papyrus log did not move for over 3 minutes, although the
  bridge kept answering. Suspected: Fallout 4 does not run the load while
  its window is not active, even with `bAlwaysActive=1`. Not yet
  diagnosed.

## <a id="laptop"></a>1b. A dedicated test machine

Built and first run 2026-11-17. A dedicated laptop runs the
cases with the game visible and in front, which sidesteps the stall of
the hidden instance. This PC keeps building and fixing; it drives the
laptop over SSH with `tools/live/fo4_laptop.py`:

| Command | Does |
|---|---|
| `setup --host H --repo R --mo2 M [--profile P] [--fallout3 F]` | Saves the laptop's address, its copy of this checkout, its MO2 folder and its Fallout 3 install |
| `push` | Sends what differs by size or time, as one tar stream: this checkout as git sees it (tracked and new files, so uncommitted work goes too), the test DLLs, the profile's enabled mods, and its modlist, plugins and INIs. Removes files gone from a pushed mod folder |
| `run [--profile P] <case args>` | On the laptop: builds the instance, then runs `fo4_story_cases --visible` and streams the log back. `--profile` (also on `push`) uses that MO2 profile instead of the saved one |
| `record -- <recorder args>` | On the laptop: records Fallout 3 itself with `fo3_record` ([the answer key](#baseline)) and streams the timeline back |
| `fetch [--out DIR]` | Brings back the run's Papyrus log, F4SE logs (crash logs included), run log and the Fallout 3 timeline |

- **Why a scheduled task:** a program started over SSH runs outside the
  logged-on desktop and can't show a window. `run` creates an interactive
  task (`schtasks /it`) that starts the run in the user's session.
- **`--visible`:** the game runs on the `Default` desktop. Once the main
  menu is up, its window is brought to the front with an Alt tap, then
  `SetForegroundWindow`. The sandbox profile and the mute stay on.
- **Windows' `tar.exe` and `ssh.exe`, by full path:** Git's GNU `tar`
  reads `C:` in a path as a remote host.
- **The laptop needs:**
  - OpenSSH Server with this PC's key;
  - Python 3.14 (`py -3.14`) with `requirements.txt`;
  - Steam (offline mode works) and Fallout 4 with F4SE;
  - the MO2 folder, on the same drive as Fallout 4 (the instance is hard
    links);
  - a user logged on, with sleep, screen lock and the screen saver off;
  - for `record`: GOG Fallout 3, made 1.7.0.3 by the Anniversary
    patcher, with FOSE 1.3 beta 2's DLLs (see [the answer key](#baseline)).
- **The laptop is reached by its address** (`192.168.50.204`): its name
  resolves only now and then, `.local` included. Reserve the address in
  the router.
- Watch it with Steam Remote Play, Parsec or VNC, not Remote Desktop:
  disconnecting an RDP session locks the console, and the game stops
  drawing.

## <a id="cases"></a>2. Story cases

The same grammar as upstream's `.tes4test`, so cases and the runner core
stay shared with the Skyrim side. The FO4 backend is simpler than
upstream's TES4 one, because the parts it reverse-engineered are ours here:

<a id="menu-names"></a>**Menu names ignore case.** The engine's strings
ignore case and keep the first spelling the game saw, so a menu can be
listed as `cRUI_LevelUp` while a case names `CRUI_LevelUp` (2026-11-18: the
tags case timed out on that with the menu open). The bridge's `status`
returns `menus` as `MenuNames`, whose `in` ignores case, so every check
(`menu`, `closed`, `talk`, `bye`, loading) matches either spelling.

| Step | FO4 backend |
|---|---|
| `{Plugin.esm:id}` | in any step: that source record's FormID in the running game. The test DLL's `form` looks it up wherever the plugin loads (a light plugin's id through its ledger), once a run (`fo4_story_moves.Refs`) |
| `activate <ref>` | the player looks at the ref and presses E, so it needs what a player needs: the activate prompt and reach (about 150 units; walk up first). The console's `<ref>.activate player` reached any distance and needed no prompt, which hid an unusable terminal and a talk started from 630 units away; it stays available as `run <ref>.activate player` ([why](fo4_test_layers_plan.md#tutorial-harness)) |
| `unless <query> <op> <value> \| <step>` | runs the step (`run <console line>`, `check talk …`) only when the condition doesn't hold now: the route sweep skips a route's steps once its stage is done, and its fallback `run setstage` must not restart a quest its route already finished ([layer 2](fo4_test_layers_plan.md#l2-built)) |
| `bye [seconds]` | the player leaves the talk: Tab, again every 3 s, until `DialogueMenu` closes ([layer 2](fo4_test_layers_plan.md#l2-built)) |
| `look <ref>` | turns the player's eye to the middle of the ref's bounds (`setangle` z, then x, as `shoot` aims): FO4 lists a talk's choices only while the player faces the speaker, so a seated player beside the speaker looks first ([psych test](fo4_pipeline.md#psych-test-no-choices)) |
| `talk [seconds] <ref>` | `activate` on the NPC, again every 6 s until `DialogueMenu` opens: an NPC finishing a bark ignores the first (Mrs. Palmer, 2026-11-18), and a player presses E again |
| `shoot [shots] <ref>` | draws the player's weapon (`Actor.DrawWeapon`), then per shot turns the player toward the ref (`setangle z`) and pitches from its eye (90% of its bounds' height) to the middle of the ref's bounds (`setangle x`, down positive), and clicks the left mouse button; 3 s between shots (the BB gun cocks between). FO3's CG02 targets count any hit (`OnHitWith` with no weapon) |
| `choose [seconds] <words>` | reads the rows our dialogue menu movie (Cleanroom UI) draws (`FadeHolder_mc.Question.0.0`: `count`, `top`, fields `0`..`4`) through `invoke`, then presses the number key of the first shown row holding the words (compared plain: case, entities and a `[skill]` tag ignored); `#N` is row N. It waits while the list is not built yet (`E_NOPATH`). A pick hides the list within milliseconds; a list still shown 3 s after the press means the key was lost (no key event in `CleanroomDialogue.log`, female Mrs. Palmer, 2026-11-18), so it presses again. `choose A || B` picks the first listed row holding any alternative, so one talk can serve several ways to a line ([layer 2](fo4_test_layers_plan.md#l2-built)) |
| `closed [seconds] <menu>` | waits for that menu to be closed |
| `hear [seconds] <speaker> <INFO>` | the speaker's display name may have several words (`hear Doc Mitchell 1074A2`). Reads the trace's `line\|...\|Begin` lines, which already carry the speaker and the **source INFO FormID**. Stronger than subtitle text: the male and female intercom replies differ by one word, but not by FormID. Several INFOs, comma-separated (`hear Sunny Smiles 15D97E,15F8B6`), match any of them |
| `heard [seconds] <speaker> <INFO>` | as `hear`, but waits for the line's end (`End`, or FNV's `end goodbye`), after its result script ran. Use it before acting on what the line sets: Doc Mitchell's 001074A2 shows objective 30 only as it ends, and the Vit-o-matic does nothing before that, as in FNV |
| `until`, `expect` | Papyrus conditions through the test DLL's console, or the trace's `stage` lines |
| `walk [seconds] <ref> [radius]` | first the engine's own path: `cgf "Game.SetPlayerAIDriven" 1` and `player.cf "Actor.PathToReference" <ref> 1.0`, polled through the test DLL's `where` until no nearer for 4 s. Then the player faces the ref and holds W, stride by stride. It arrives within radius of the ref's bounds (`where`'s `min`/`max`: a trigger's primitive radii, else the object's own bounds). By default it arrives inside a trigger's primitive, or pressed at its edge by whoever stands in it (Dad stands in his own trigger). A player already standing in the trigger backs out first, so `OnTriggerEnter` fires as it does for a player coming in |
| `run` | any console line (`coc`, `setstage`, `startquest`...). A story case uses it only for what the player cannot do; the sweep cases set stages with it |
| `answer [seconds] <label>` | the test DLL's `button`: waits for a message box, selects the button with that label in its list (`List_mc.selectedIndex`), then brings the game to the front and presses a real Enter, then E (Fallout 4's other Accept key) if the box is still up. LooksMenu's "Confirm character" box takes only E (2026-11-17) |
| `close [seconds] <menu>` | the menu's own Done, the code function its Done button calls: LooksMenu's `ConfirmAndCloseMenu` (puts up "Confirm character"), SPECIALMenu's `tryCloseMenu`; else a hide message. As the greyed-out button, it refuses (`E_DISABLED`) while the card has points left (`pointsRemaining`) or no name. ConfirmAndCloseMenu answers false while the edited actor's face object is busy (byte +0x59B, read at 0xD0C290; just after ChangeSex, while Nora's face loads): the DLL answers `E_BUSY` and the step retries |
| `call [seconds] <menu> <function>` | the menu's code function by name (`BGSCodeObj.<function>()`, as its Flash calls it): `call LooksMenu ChangeSex` (Nate to Nora at the mirror). The names are in the menu's movie (`Fallout4 - Interface.ba2`, decompiled with JPEXS FFDec), so no disassembly |
| `invoke [seconds] <menu> <path> [args]` | a public method of the menu's movie object, by dotted path, with int or string args, as its own buttons call it; `<path>=<value>` sets a member instead. The SPECIAL card: `invoke SPECIALMenu List_mc.selectedIndex=1`, then `invoke SPECIALMenu IncrementPoints` (its right arrow); the name through `invoke SPECIALMenu onVirtualKeyboardResult Tester 1`, the call the gamepad's on-screen keyboard makes. Typing it (Enter, keys, Enter) passed 2 of 5 runs: one Enter both started the edit (key down) and ended it (key up, once focus had moved) |
| `errors`, `check`, `load`, `report` | the stage sweep's ([layer 1](fo4_test_layers_plan.md#l1-built)): new Papyrus errors from converted scripts; a step whose failure is kept and the case goes on; a save loaded mid-run; fail listing every kept failure |
| `menu [seconds] <menu>` | waits for that menu to be open (status only, no console line) |
| `press [seconds] <key>` | holds a key in the game window: `press T` twice skips the intro movie, `press 1 W` leaves the mirror's sink |
| `${NAME=a:x,b:y}` | x or y by `--set NAME=` (`SEX=male` / `female`), filled before the line is read |

The opening's first case runs Fallout 4's character creation
([character creation](fo4_pipeline.md#character-creation)): `setstage
FNV_NewGame 5` from a coc, the mirror, ChangeSex for a female run, confirm,
leave the sink.

**First pass (2026-11-17):** `cg00_birth` passed on the laptop in 70 s:
`coc QASmoke`, the new game's stage 10, CG00 to stage 5, Dad's two lines
around the Boy/Girl box, and Catherine's line.

**With Fallout 4's character creation (2026-11-17):** all 4 cases of
`tests/story/fo3_opening` pass for both sexes, about 4 minutes a run
(creation 76–79 s, birth 35 s, name and race menu 76–81 s, CG01 17 s).
What it took:
- The intro movie's menu is `PlayBinkMenu`. T twice skips it (the first T
  shows the prompt); Esc does nothing, and an empty `Intro.bk2` leaves it
  open on a black screen.
- `answer` brings the game to the front before each key. The confirm box
  took E in one run and Enter in another, so it tries both.
- `close` retries a busy LooksMenu: right after ChangeSex, Done does nothing
  until Nora's face has loaded, and the old hide fallback closed the menu
  without a confirm.

**Step 1 of the progression plan (2026-11-17):** Fallout 4's character
creation is its own file, `tests/story/fo4_creation.f4test`, run before
either opening's folder (the runner takes several paths in turn). FO3's
CG01 passes on the laptop through the SPECIAL book: walk into Dad's trigger
(12), the playpen gate (30), out of the crib (40), the book (50) and the
SPECIAL card (closed by a hide until step 2). What it took:
- Dad's trigger never fired: the player stopped at its surface. FO3's
  trigger bases carry an editor model whose collision is static, and a
  primitive without `XTRI` became solid. Fixed in the converter
  ([trigger layer](fo4_pipeline.md#trigger-layer)).
- A straight walk can't get round walls, so `walk` lets the engine path
  the player first.
- The bridge client never applied its timeout to the reply: a game hung
  in a load left the runner waiting forever. A request now fails after
  the timeout with `E_TIMEOUT`.
- Open: the engine's path stops in front of CG01's closed main door
  (`CG01MainDoor`, unlocked but closed at stage 80), so `cg01_follow_dad`
  stops there. `--from` hung every checkpoint load ("Reverting game..." and
  nothing after): the console's `load` ran inside the test DLL's F4SE task.
  The DLL's `load` now queues it as the Load menu does
  ([checkpoints](fo4_test_layers_plan.md#s3)).
- `fo4_laptop push --profile "New Vegas"` and `run --profile ...` use
  another MO2 profile. "New Vegas" is "Fallout 3" with FalloutNV.esm in
  place of Fallout3.esm (the same support mods).

<a id="recheck"></a>**Early decisions to re-check as the cases reach them.** Several
mechanisms were built early, before we knew FO4 well. When a case runs
into one, check it against what vanilla FO4 does before patching it:
- **The door closer** (`F3NV_DoorCloser`, [door-closer](fo4_pipeline.md#door-closer)),
  built for the Primm deputy rescue (doors left open behind NPCs). CG01
  showed it shutting a door in front of a following player; it now leaves
  a door open while the player is within 200 units. Still to measure: what
  FO4's own NPCs do with an ordinary door, which navmeshes don't list
  (Fallout4.esm's navmeshes link only teleport doors: 961 links, none of its
  3,324 ordinary doors, the same as ours).
- **The says-settled count** (`TES4Polyfill.SaysSettled`,
  [says-settled](fo4_pipeline.md#says-settled)) is one count for the whole
  game. In FNV's opening four far-off Nightkin (REPCON's
  `REPCONNightkinGoCrazy` package fragment) asked a line every few seconds
  that never started. So every line's end in Doc Mitchell's house waited on
  them, up to the cap. The count now holds only for speakers whose 3D is
  loaded. Still to find: why their package fragment asks again and again
  far from the player (FNV runs it as the package begins).

**Next:** the verbs for walking, using, talking, choosing, fighting and
terminals, and the beats of both openings that need them, are planned in
[fo4_opening_progression_plan.md](fo4_opening_progression_plan.md#progression).
How the scene runs fit with faster, wider sweeps, and the speed work
before them, is in the [test layers plan](fo4_test_layers_plan.md).

**The first cases** are the FO3 opening, CG00 to CG04 (birth to the
G.O.A.T.), then MQ01's escape, and FNV's opening through Goodsprings. Each
quest is a folder of cases, one per beat, with a checkpoint after each.
A case for the party, for example:

```
case cg02_intercom
until 1200 GetStage CG02 >= 35
hear Dad 00031D3C            # "Jonas?"
hear Intercom 00031D3D       # "Hey doc. We're all set down here."
hear Dad 00031D43            # male player: "Thanks. I'll send him right down."
until 300 GetStage CG02 >= 38
end
```

Cases name source records (EditorIDs, FormIDs), resolved through the
FormID ledger, so they don't change from build to build.

**Both player sexes.** The opening runs twice, once as each. Today's
intercom bug shows only for a male player.

## <a id="recorder"></a>3. The behavior recorder

A case checks the lines and stages. The recorder checks what the actors
do between them. During each case, the named actors of the quest being
tested (the quest's aliases and every actor its lines name) are sampled
on each tick of the test quest, into the run's results as one timeline:

- current package, and its start and end events;
- position, and heading to whoever they are talking to;
- sit state (`GetSitState`);
- animation events, through `RegisterForAnimationEvent` on each watched
  actor (today the trace logs them only where a converted script already
  registers, as `CG02DadSCRIPT` does): `initiateStart`, `weaponSheathe`,
  idle starts and stops;
- each line's begin and end, with the speaker and the INFO.

Rules over the timeline, each a finding with the actor, the line and the
time:

| Rule | Catches |
|---|---|
| During a `SayTo` line, the speaker's body heading is within FO4's own dialogue facing of the listener | facing the wall |
| An idle the line started does not stop before the line ends | idles cut mid-line (today's stale release) |
| A held idle stops when the speaker's package changes | idles looping on |
| A line plays to its voice file's length, unless the source cuts it | lines cut short |
| A seated actor stands only when its package changes | guests standing |
| An actor's package is not re-evaluated more than once per source event | evaluate churn |
| A force-greet starts inside the package's trigger location | greeting from the wrong place |

Where FO4 has no Papyrus reading (the idle running now), the test DLL
reads it from the actor's animation graph; it stays test-only.

## <a id="baseline"></a>4. The source game as the answer key

The rules above encode what FO3 does as we understand it, and that is
where we have been wrong. The stronger check records the same opening in
the source game itself and diffs the two timelines: same lines in the
same order, same stages, same sitters, same facing.

- **New Vegas**: xNVSE is installed (`nvse_loader.exe`, `nvse_1_4.dll`).
  An NVSE plugin, built on the xNVSE and JIP LN sources in `references/`,
  writes the timeline: each line begun (speaker, INFO), each stage, and
  every few frames the actors' package, position, heading and sit state.
  The same hidden-desktop launch applies.
- **Fallout 3**: FOSE supports only 1.7.0.3 (English, and German
  no-gore as `fose_1_7ng`). Steam's current exe is **1.7.0.4**, and the
  installed 2022 `fose_loader.exe` refuses it with "Version 1.7.0.4 is
  unsupported. Please downgrade to 1.7.0.3." The DLLs installed beside it
  are FOSE 1.2 beta 2 (2010), which lacks the plugin command-table
  interface. The recorder needs FOSE 1.3 beta 2 (`references/FOSE`) on a
  1.7.0.3 exe. FOSE's script commands add `PrintToConsole`, reference
  walking, key taps and UI reads; package, sitting and heading reads are
  FO3's own condition functions. It has fewer reads than NVSE, so the
  recorder is a FOSE plugin built on the FOSE source in `references/`, and
  a spike measures what it can record before anything is built on it.
- **Driving the source game**: its opening needs few inputs (a name, the
  appearance menu's accept, the dialogue choices). The recorder's plugin
  makes them through the game's own menu calls, as upstream's TES4 backend
  does; a choice list per case picks the same options as the FO4 case.

**Built and run (2026-11-17): the Fallout 3 recorder spike.**
`tes_runtime/fo3_test/recorder.cpp` builds (`build.bat`, MSVC x86) into
`F3Recorder.dll`, a FOSE plugin. `tools/live/fo3_record.py` installs it,
starts the game, prints the timeline and closes the game; `fo4_laptop
record` runs it on the test machine.

- **The game it runs on:** GOG Fallout 3 after the Anniversary patcher,
  which makes it 1.7.0.3 (FOSE checksum `FAEE50E7`, unknown to both FOSE
  loaders), removes GFWL and adds a section that loads `fose_1_7.dll`
  itself. `fo3_record` starts `Fallout3.exe` directly when the exe names
  `fose_1_7.dll`. The Steam copy, given the same patch, quit after one
  second with exit code 0, even without the recorder; that was not
  explained, and the laptop uses GOG.
- **Console lines:** FOSE 1.3 beta 2 has no console interface (its
  `QueryInterface` case sits under `#if 0 // not yet supported`). The
  recorder runs a line the way the console's line handler (`0x62B620`)
  does, matched call for call against New Vegas's (`0x71C3A4`, NVSE's
  `RunScriptLine`). It constructs a temporary `Script` (`0x517010`),
  marks it temporary (`0x4553B0`), sets the text (`0x517450`), runs it
  in the ConsoleManager's script context (`0x518D30`), and destroys it
  (`0x519960`). The ConsoleManager is at `[0x1075D18]`, with the context
  in its first field, as in NVSE: both keep `COFileName` at `+0x810`.
  This works on 1.7.0.3 English only.
- **First run:** `--menu "coc Vault101d"`, then `--cell "startquest
  CG00;setstage CG00 0"`. The run reached CG00 stage 10 after 29 s, with
  950 lines and no fault:
  - every actor's package read as a PACK;
  - `GetSitting`, `IsTalking` and `GetCurrentAIProcedure` answered;
  - Dad's opening line came through as `sayto|000290A7|0001F387|0001F378`,
    the INFO that the Fallout 4 case expects to hear.

  The first sample lists every quest's stage, then only changes.

- **Its tick** is the game's own `PeekMessageA`, swapped in the exe's
  import table, at most every 100 ms. The main loop (`0x9B3CC0` in
  1.7.0.4) calls it with no window filter between frames on the main
  thread, so the reads never land mid-frame. The same loop runs a frame
  only when `GetForegroundWindow()` is the game's window or a few flags
  are set, which supports the unfocused-window stall seen in Fallout 4.
- **Each tick reads:**
  - the player's cell;
  - every actor in it and every talking activator, with position, heading
    (`rotZ`), current package (process at `0x60`, package at `+4`, the
    JIP layout), and `GetCurrentAIProcedure`, `GetSitting` and `IsTalking`
    through FOSE's command table;
  - the INFO and topic of an `ExtraSayToTopicInfo`, each picked by form
    type, since Fallout 3's extra is 0x18 bytes against New Vegas's 0x1C;
  - the player's dialogue topic (`+0x604`);
  - every quest's running flag and `GetStage`.
- **It writes changes only,** as `ms|kind|...` lines: `cell`, `actor`,
  `pos`, `pkg`, `proc`, `sit`, `talk`, `sayto`, `ptopic`, `quest`,
  `stage`, `cmd`.
- **Guarded reads:** every read is guarded, and every pointer is checked
  for its form type. A reader that faults, or a package pointer that is
  not a PACK, writes one `fault|<reader>` line and stops. A wrong layout
  shows in the timeline instead of crashing the game.
- **Starting the opening:** Fallout 3 has no NewGame quest (`FNV_NewGame`
  is ours), so `--menu` and `--cell` take console lines the plugin runs
  at the main menu and in the first cell. Driving the real New Game
  menu is the next step.
- **Still open:** whether `ExtraSayToTopicInfo` carries the lines of
  dialogue packages and conversations, or only `SayTo`, and how common a
  `talk` with no `sayto` (a line it cannot name) is. The run stopped at
  Dad's first line.

Only the timing of each event differs between the two games, so the diff
compares order and relationships, not seconds: Dad's reply after the
intercom's line, the guests seated from the Overseer's speech to the
cake. Each difference is a finding; where FO3 itself behaves oddly, the
baseline says so, and nobody chases it in our build.

This tier also checks our reading of FO3 before a fix is built.

## <a id="data"></a>5. The data audits: what they can and can't see

Data audits stay the cheapest check and run on every build, but they
only see what the records say. Of today's bugs, one is a data bug:

- **Scene targets against line conditions.** Dad's reply to the intercom
  is a GREETING line whose conditions test the intercom as the line's
  target (`GetIsID` run on the target). A new check in the `conditions`
  audit: for each scene dialogue action, evaluate each line's target
  conditions with the action's target. A line that can never pass is an
  error. Built first, because it is a day's work.

  **Built 2026-11-17, not yet confirmed in game:**
  `tools/validate/preflight/scene_targets.py`, run by `--audit conditions`.
  The converter turns a chat line's FO3 Target tests into tests on the
  scene quest's Listener alias (1000), and its Speaker alias (0) is the
  speaker, so the check works on alias fills:
  - Each way a scene starts gives a fill. A `TES4Polyfill.StartConversation`
    or `TalkerActivate` call in a script that names the scene (a dialogue
    package's `F3NV_DialoguePackage`: `akActor` is the NPCs listing the
    package, `Target` its property) fills Speaker and Listener. A passing
    line of a step that starts another scene (TSCE) carries the fill on
    within the same quest, and ALFA puts the speaker in. Forced and
    unique-actor aliases are always known. Any other start (quest start,
    a Greeting line, a menu answer) leaves Speaker and Listener unknown.
  - `GetIsID`, `GetIsReference`, `IsInList`, `GetInFaction`,
    `GetIsVoiceType` and `GetIsRace` run on the speaker, an alias or a
    reference are decided from the records. A list or faction a script
    property or an alias (ALFC) names counts as changeable, and a templated
    NPC as unknown. Anything else (stages, globals, sex, run on Target in a
    Dialogue action) can pass.
  - **Error**: a step none of whose lines can pass under some fill (the
    step plays nothing). **Review**: a line whose known speaker can say it
    but whose listener or alias tests fail under every fill. A line that
    fails its own speaker test is another NPC's line in a shared step
    (every GREETING line is in one), so it is only counted.

  On the FO3 build of 2026-11-17 08:45: 871 scenes reached under 877
  fills, 44 with a known speaker; 1,324 steps judged; 0 errors; 5 reviews,
  all Dad's BB-gun greetings to the player (0001F9BB to 0001F9BF, `GetIsID
  Player` on the listener) in the intercom chat step, which FO3 skips
  there too; 259 lines counted as another speaker's. The intercom reply
  00031D43 (built 02A56D89) passes for Dad and the intercom in this build,
  through its `IsInList TES4TalkingAs_000300E7` test on the listener, so it
  is not flagged. With every talking-as test removed in memory, the check
  reports `CG02_Scene1` action 1 as an error ("Jonas?" wants Jonas as the
  listener); removed from the reply alone, a review of 00031D43. It does
  not judge order: a line ahead of the intended one that can also pass
  still wins, and a generic greeting played instead is that case.

The audits also need their noise cleared before anyone can use them:
today's FO3 run reports 449 dialogue errors, 107 timing errors, 539
condition reviews and 551 packages left out. Some are wrong: the timing
audit says `CG02DadSCRIPT`'s `OnPackageDone` block is gone, but it runs
from the package's fragment (`FALLOUT3_PF__000306D4` calls it). Sorting
each class once into the review ledger, and fixing the audits that are
wrong, makes "new since the last build" mean a real regression.

Facing, idles, seating and timing can't be seen in the records: the
records are correct and the engine does something else with them.

## <a id="reach"></a>How far it goes

| Tier | Runs | Catches | Doesn't |
|---|---|---|---|
| Story cases | Each opening, both sexes, about 15 to 25 min at the measured speed-up | Missing or wrong lines, stages that don't come, quests that stop | How actors behave between lines |
| + recorder | Same runs | Facing, idles, seating, greet placement, churn | Whether it matches FO3 when our rule is wrong |
| + source baseline | One recording per source game per opening, redone only when a case changes | Everything above, judged against the real game | Look and feel |
| Main quests | Nightly, with checkpoints, from upstream's quest-run shape | Story-breaking bugs across the game | Side content the cases don't name |
| The [autoplay sweep](fo4_autoplay.md) | Nightly on the same instance | Crashes, Papyrus errors, falling actors, navmesh | Story order |

What stays manual is unchanged from the [autoplay plan](fo4_autoplay.md#manual):
the look, animation quality, combat feel, voice and sound, story choices.

## <a id="order"></a>Order and effort

Effort is agent working days.

| Step | What | Size | Needs |
|---|---|---|---|
| 1 | Scene-target conditions audit; ledger pass over the FO3 audit findings | S, 1 to 2 days | |
| 2 | Hidden instance on FO4: hard-link folder, F4SE hidden launch, sandbox DLL, mute, `iFPSClamp` measured, smoke run | M, 3 days | test-only DLL approval |
| 3 | Case runner on F4SE (upstream's grammar and core); `hear` from the trace; `until` and `expect`; checkpoints; `--from`; `repeat_case` | M, 3 to 4 days | step 2 |
| 4 | Dialogue menu test entry point; `talk`, `ask`, `choose`, `bye` | S to M, 2 days | a Cleanroom UI change |
| 5 | FO3 opening cases, CG00 to CG04, both sexes; FNV opening through Goodsprings | M, 3 days | step 3 |
| 6 | Behavior recorder and its rules | M, 3 to 4 days | step 3 |
| 7 | NVSE recorder for the FNV baseline; timeline diff | L, 1 to 2 weeks | step 6 |
| 8 | FOSE spike, then the FO3 baseline | M to L | |
| 9 | Main quests nightly; the [autoplay](fo4_autoplay.md#order) cell sweep moved onto the instance | as in that plan | step 3 |

Steps 1 to 5 give a run that would have caught today's intercom bug and
the BB gun stall: about 2 weeks. Step 6 adds today's facing, idle and
seating bugs.

From then on, a fix to a scene is done only when its case passes several
times in a row on the instance and the recorder shows no new findings for
that quest.

## <a id="needs"></a>What it needs from the user

- **Approval for a test-only DLL** (the sandbox and test runner, on
  CommonLibF4 with Address Library IDs). It lives only in the test
  instance and is never shipped, so no feature comes to depend on it.
- **Nothing at run time**: the instance runs hidden and muted, so the PC
  stays usable. Whether the user's own Fallout 4 can run beside it (Steam
  may allow one copy) is measured in step 2.
- The user still plays to judge the look and feel, and marks a build
  good ([regression plan](fo4_regression.md#good-build)).
