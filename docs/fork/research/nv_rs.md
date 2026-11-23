# nv-rs as the FNV timeline recorder

**Step 8a of [the test layers plan](../fo4_test_layers_plan.md#nv-rs).**
nv-rs ([slaterain/nv-rs](https://github.com/slaterain/nv-rs)) is a Rust
translation of `FalloutNV.exe` 1.4.0.525. This note records what it took to
build it, run FNV's opening in it, and add the layer 4
[timeline](../fo4_story_tests.md#baseline) to it. Spike done 2026-11-17/18 on
the dev PC (not the test machine).

## <a id="clone"></a>The clone

- Cloned to `references/nv-rs-src` (gitignored) at commit
  `70fd4faf7dc5191f61827b4b4fd9dc418377e927` (2026-11-17 23:29 -0500).
  `references/nv-rs` is a different folder: it holds only `engine_map.tsv`.
- The timeline is a patch on that clone, saved as
  `references/nv-rs-timeline.patch` (563 lines). Apply it with
  `git -C references/nv-rs-src apply ../nv-rs-timeline.patch`. nv-rs is
  GPL-3, so the patch stays out of this repo.

## <a id="build"></a>Build

| Step | Command | Time |
|---|---|---|
| Viewer | `cargo build --profile play -p nv-viewer` | 3 min 7 s cold (rustup installed the pinned toolchain 1.99.1 itself); 3 to 4 s incremental, 67 s after a change in `engine-core` |
| 32-bit target for the capture tools | `rustup target add --toolchain 1.99.1 i686-pc-windows-msvc` | seconds |
| Adapter table | `scripts/d3d9-capture`, `scripts/nvapi-capture` (i686) and the device queries, per `docs/PLAYTESTING.md` | under a minute |
| Sound table | `cargo run --release --target i686-pc-windows-msvc --manifest-path scripts/dsound-capture/Cargo.toml > dsound.tsv` | 15.5 s to run |

The result is `target/play/nv-viewer.exe` (122 MB). It needs both machine
tables. Without the sound table it stops in frame 0:

> Game's main stopped in frame 0: the sound table
> (Some("%LOCALAPPDATA%\\nv-rs\\dsound.tsv")) is not there:
> run `cargo run --release --target i686-pc-windows-msvc --manifest-path
> scripts/dsound-capture/Cargo.toml > <file>`...

`--check` passes on both installs found on this PC
(`D:\SteamLibrary\steamapps\common\Fallout New Vegas` and
`C:\Standalone Games\Fallout New Vegas`): "is 1.4.0.525". It reads the
player's own exe, packed or unpacked.

## <a id="run"></a>Running it

nv-rs maps the player's exe and runs its own translated functions in place
of the exe's. The game's data comes straight from the install's `Data`.

- **Folders.** The game writes to Documents and AppData through
  `SHGetFolderPathA`, which the adapter table answers (lines `5`, `1a`,
  `1c`). Rewriting those three lines points a run at its own folder, so a
  test run never touches the player's saves or inis. The run folder needs
  `Fallout.ini` (from `Fallout_default.ini`), `FalloutPrefs.ini` (windowed,
  1280x720, the right `sD3DDevice`) and `plugins.txt`.
- **Switches used.** `NV_THREADS=stepped` (threads take turns),
  `NV_D3D9=real` (draws through the real Direct3D 9), `NV_D3D9_BACKGROUND=1`
  (the window stays behind others), `NV_SHOT=DIR,ms` (screenshots),
  `NV_DSOUND_TABLE`, `NV_D3D9_ADAPTER`. `NV_MOVE_KEYS` (scripted keys) also
  turns the real window's input off, which a driven run needs: a dummy
  `NV_MOVE_KEYS=99999999:01:1` does that.
- **Not tried:** `NV_D3D9_HIDDEN=1` (window never shown) and running with
  `NV_D3D9` unset (the docs say a scripted run then draws nothing). Every
  run here had a background window.
- **Speed.** The main menu shows after about 10 s. It takes keys only after
  about 46 to 50 s, and that varies by about 15 s from run to run. The intro
  movie plays at real length (about 320 s) unless Escape skips it.
- Each run was closed by its own end condition or by `taskkill`; nothing is
  left running.

## <a id="hooks"></a>Hook points

nv-rs has its own extension seams: a static `SITES` table in
`crates/engine-core/src/extend.rs` names exe addresses where extenders
(xNVSE, JIP, UIO ports) may run code, each with an owner list. A seam runs
only while its hook has a user (`e.add_hook_user(Hook::X, true)`). The
timeline added a row owner `Row("timeline")` to two existing seams, ahead of
JIP, and only reads there.

| Event | Where in nv-rs | How the spike gets it |
|---|---|---|
| Stage set | stage mark-done `fn_0060f4a0` (`crates/engine-fallout-script/src/units/fallout_shared/run_0060f4a0.rs`), reached from `TESQuest::SetStageDone` 0x0060D510 and `Script::SetStageFunction` 0x005C7140 | seam 0x0060F4A9 (JIP's SetQuestStage seam): `stage|EDID|QUST|index`, skipped when the stage was already done and the quest doesn't repeat stages |
| Line begun / ended | `TESTopicInfo::RunResult` 0x0061F170 (`crates/engine-fallout-forms/src/units/fallout_shared/testopicinfo.rs`), result index 0 = begin, 1 = end; also `TESObjectREFR::SetSayToTopicInfo` 0x0057ACE0 and `DialoguePackage::Speak` 0x009EE0A0 | seam 0x0061F184 (JIP's RunResultScript seam): `line|speaker|INFO|DIAL|begin` or `end`, topic from `GetOwnerTopic` 0x0061A310 |
| Objective shown / done | `fn_005ec5d0` (`run_005ec4d0.rs`; state 1 shows it through `HUDMainMenu::ShowQuestObjective`, 3 completes it) | polled each frame: `BGSQuestObjective` state at +0x20 for every quest. An exact event needs a new `SITES` row there |
| Package change | `BaseProcess::SetCurrentPackage` 0x008D08B0 (`crates/engine-fallout-ai/.../baseprocess.rs`), `LowProcess::SetCurrentPackageFromSchedule` 0x00907700 | polled: `[process+4]` for the player and every actor in the cell |
| Position, cell | reference +0x30 / +0x2C / +0x40 | polled, at most every 500 ms per actor |
| Quest running | quest flags +0x3C bit 0 | polled over the DataHandler's quest list |
| Menus | InterfaceManager 0x011D8A80, menu stack at +0x114 | polled: `menus|...` on a change |

Polling runs between frames on the game's own thread, so it needs no
locking; its cost was not measured.

## <a id="timeline"></a>The timeline writer

`crates/host/src/timeline.rs` (473 lines), installed from
`install_rows_and_extenders` and driven from the viewer's frame loop. With
`NV_TIMELINE=<file>` set, it writes `ms|kind|...` lines, changes only, flushed
per line, in the [baseline format](../fo4_story_tests.md#baseline): `start`,
`screen`, `menus`, `menu`, `cell`, `actor`, `pkg`, `pos`, `quest`, `stage`,
`objective`, `line`, `cmd`, `fault`. New kinds against the FO3 recorder:
`line` (begin and end, where FO3 has `sayto`), `objective`, `screen`,
`menus`.

It also drives the run, since a test needs no hands:

| Variable | Does |
|---|---|
| `NV_TIMELINE_MENU_WAIT` | frames to wait once the main menu takes keys (default 90) |
| `NV_TIMELINE_MENU_KEYS` | DirectInput keys pressed at the main menu, one every 45 frames, e.g. `d0,d0,1c,1c` |
| `NV_TIMELINE_MENU` | console lines run at the main menu; `!newgame` calls `StartMenu::ConfirmNewGame` |
| `NV_TIMELINE_CELL` | console lines run once the first cell has played 60 frames |
| `NV_TIMELINE_KEYS` | `FRAME:key` presses, counted from the menu drive or the first cell |
| `NV_TIMELINE_ON_MENU` | `TYPE:key`: press a key while that menu type is on top (e.g. `3e9:1c`, Enter on a message box) |
| `NV_TIMELINE_UNTIL` | `EDID:STAGE`: end the process once that stage is set |
| `NV_TIMELINE_FRAMES` | end after this many frames |

Console lines run through nv-rs's own `nvse::compile_script::run_script_line`.

## <a id="results"></a>What ran

FNV's opening, from the main menu to VCG01 stage 15 ("wouldn't have picked
that name"), in 110 s of wall time, with no hands. The timeline is saved
as `references/nv-rs-vcg01-timeline.txt`. Run with the switches above plus:

```
NV_TIMELINE=tl.txt NV_MOVE_KEYS=99999999:01:1 NV_TIMELINE_MENU_WAIT=60
NV_TIMELINE_MENU_KEYS=d0,d0,1c,1c NV_TIMELINE_KEYS=450:01
NV_TIMELINE_ON_MENU=3e9:1c,41b:1c,3f1:1c NV_TIMELINE_UNTIL=VCG01:15
```

(Down, Down, Enter on New, Enter on the new-game warning; Escape 450
frames later skips the intro movie; Enter on message boxes and the name
box.) The timeline, with `quest` and `pos` lines left out:

```
48183|menu|main
52406|stage|VCG00|00102037|0
64589|key|01
64603|stage|VCG00|00102037|90
69804|cell|00103DF9
69804|actor|00104C0F|00104C0C
69804|pkg|00104C0F|00104C1D
71078|menus|3e9            (three pre-order pack boxes, "Classic Pack items added")
79845|stage|VCG00|00102037|95
79883|stage|VCG00|00102037|100
79883|stage|VCG01|00104C1C|0
79889|pkg|00000014|001055BE
80080|stage|VCG01|00104C1C|1
85054|stage|VCG01|00104C1C|3
85057|line|00104C0F|00104BEE|00104BDD|begin
88040|line|00104C0F|00104BEE|00104BDD|end
88040|stage|VCG01|00104C1C|5
88078|pkg|00000014|001055C3
91344|stage|VCG01|00104C1C|7
91383|stage|VCG01|00104C1C|8
91386|line|00104C0F|00104BEF|00104BDD|begin
97295|line|00104C0F|00104BEF|00104BDD|end
97297|line|00104C0F|00104BF0|00104BDD|begin
100680|line|00104C0F|00104BF0|00104BDD|end
100682|line|00104C0F|00104BF1|00104BDD|begin
106868|line|00104C0F|00104BF1|00104BDD|end
106868|stage|VCG01|00104C1C|10
106908|menus|41b           (name box)
109807|stage|VCG01|00104C1C|15
109810|line|00104C0F|00104BF2|00104BDD|begin
```

Checked against the export: INFO 00104BEE is Doc's "You're awake. How
about that." in VCG01Intro (00104BDD), and its end result script is
`SetStage VCG01 5`; the timeline puts its `end` and stage 5 in the same
millisecond. Stages 3, 8 and 15 are the ones whose scripts run
`DocMitchellREF.SayTo player VCG01Intro`, and each is followed by a line
from Doc within 3 ms. The player's script packages (VCG01PlayerSection1)
appear as `pkg` changes where stages 0 and 5 add them. The screenshots show
the intro, the pre-order boxes, and Doc in his chair.

| Works | Not shown |
|---|---|
| Stages (event), lines begun and ended (event), quests running, packages, cell, actors, positions, menus, console lines, scripted keys, ending on a stage | Objectives: polled, but none is shown in this stretch, so the code is untested. Positions: only 2 lines, since nobody moves before stage 15. A comparison with the real game (spike steps 3 and 4): not done |

Earlier attempts, for the record: the intro movie runs about 320 s if not
skipped; the new game started by calling `ConfirmNewGame` stalls (below).

## <a id="driving"></a>Driving the main menu

Findings that cost most of the spike's time:

- Real window input mixes with scripted keys until `NV_MOVE_KEYS` is set.
- A key held for 4 frames did nothing; a 1-frame press works.
- The start menu builds its options long before it takes keys: the options
  list (`StartMenu::pMe` 0x011DAAC0, list at +0x84) holds 7 items at 7.6 s,
  but keys work only from about 46 s. The reliable signal found: bit
  0x80000 of the start menu's flags (+0x1A8) is set until it takes keys
  (observed, not traced in the code). The timeline waits for it.
- The first Down after that is eaten; Down, Down, Enter reaches New. A
  Yes/No warning follows (its text mentions content not present, likely the
  DLC; not checked), and Enter accepts it.
- Calling `StartMenu::ConfirmNewGame` directly between frames starts the new
  game (VCG00 stage 0 at +39 ms, the intro, stage 90, Doc's house), but the
  start menu stays on the menu stack, so the game stays in menu mode: VCG00's
  GameMode timer never runs and stage 95 never comes. Real keys are the way
  in.
- A `plugins.txt` naming only `FalloutNV.esm` still loads every DLC's quests
  (probably through the `.nam` files; not checked).

## <a id="real-game"></a>The real game's side

nv-rs ships `research/nv-trace`: it runs the real `FalloutNV.exe` with
function lists (address, calling convention, argument words) and scripted
DirectInput keys, guards the player's folders, and diffs its traces against
the port's. Listing the four hook addresses above gives the real game's
timeline with the same keys, which is step 3 of the spike without a played
recording or the xNVSE plugin. Not run in this spike.

## <a id="verdict"></a>Verdict

**Yes, as far as this spike reached.** nv-rs plays FNV's opening from its
own data through quest, dialogue and package code, and a 473-line timeline
module records it in the layer 4 format with exact stage and line events.
It is cheap to drive (keys and console lines from variables) and quick
(about 50 s to the menu, 110 s to VCG01 stage 15, background window).

What is left before it can be step 8's recorder, in agent days:

| Work | Size |
|---|---|
| The real game's side through `research/nv-trace` with the same keys, and the diff on the opening (spike steps 3 and 4) | 1 to 2 |
| Objective events from a `SITES` row at `fn_005ec5d0` instead of polling, checked on a stretch that shows one (VCG01's later stages) | 0.5 |
| Running on to VCG01 stage 65 (race menu, Vit-o-matic: more menu keys) | 0.5 to 1 |
| Keeping the patch building as nv-rs moves (it touches `extend.rs`, `host/lib.rs`, `viewer/main.rs`); or offering it upstream | ongoing |
| Starting at the main menu needs the menu wait (about 48 s); a start save or `coc` from the menu would cut it | 0.5 |

Against the xNVSE plugin (1 to 2 weeks), that is about 3 to 4 days. The
risk is unchanged: every difference against nv-rs is a lead until the real
game agrees, which is what nv-trace's diff is for. Not tried: a run with no
window at all (`NV_D3D9_HIDDEN=1`, or `NV_D3D9` unset).

## <a id="ttw"></a>TTW

TTW is not installed on this PC (only a hidden "TTW Fallout 3 LOD" mod in
`C:\Modlists\VNV`). nv-rs mentions TTW only for engine limits it lifted: 2 GB
archives, OFST cell offsets, the 512 open-file limit. Nothing in its docs
says TTW plays. Since the timeline reads quests, stages and lines by form,
it would record TTW unchanged; the questions in the
[plan](../fo4_test_layers_plan.md#ttw) (FormIDs, TTW's own changes, disk
space) are untouched by this spike.
