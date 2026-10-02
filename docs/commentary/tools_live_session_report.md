# tools/live/session_report — a play-test session against the source game

**Code:** `tools/live/session_report.py`, `tools/live/debug_mark.py`, `tools/live/debug_mark/TES4_DebugMark.psc`, `game_bridge/plugin/recorder.cpp` (`RecorderPapyrus`)

## Contents

- [Overview](#overview)
- [Running it](#running-it)
- [The mark key](#mark-key)
- [What each section checks](#sections)
- [What it does not see](#blind-spots)

## Overview
<a id="overview"></a>
The [flight recorder](../../game_bridge/README.md#flight-recorder) logs what
the engine did. The source export holds what the original game set up to
happen. This report sets the two side by side, so a deviation shows up even if
the player doesn't know the game well. It was built because play-test reports
like "Burke should start in the bar" or "Lucas loops his greeting" needed the
player to know what should have happened. The source data already says, for
most of it:

- where each NPC should be and when: the package list and its schedules;
- what each quest stage sets going: the result scripts' `SetStage` and
  `StartQuest` calls;
- which conversation lines should follow which.

The report does not repeat the Papyrus error grouping or the per-quest "where
it stopped" review. Those live in the preflight
[log triage](tools_preflight.md#log-triage) audit (`--audit logs`), and the
report ends by pointing there.

## Running it
<a id="running-it"></a>
```
python tools/live/session_report.py --game Fallout3            # newest recorder run
python tools/live/session_report.py --game FalloutNV --run 1   # the run before
python tools/live/session_report.py --game Fallout3 --mark 2   # only the second mark
python tools/live/session_report.py --game Fallout3 --out report.md
```

`--plugin` and `--export` override the converted plugin
(`output/<game>.esm/<game>.esm`) and the source export (`export/<game>.esm`).
A runtime FormID maps to its source record through the converted plugin's
load-order prefix: the low 24 bits are the source FormID. A record the
converter made itself (a generated package, quest or location) is named from
the converted plugin and has no source record to compare against.

On the 2026-10-01 Megaton session (7,364 events) the whole report takes about
2 s.

## The mark key
<a id="mark-key"></a>
`python tools/live/debug_mark.py` builds `output/TES4DebugMark/`. It holds
`TES4DebugMark.esp` and `Scripts/TES4_DebugMark.pex`. The plugin has:

- ESL flag and Skyrim.esm as its only master, so it loads beside any
  converted game without taking a load-order slot or touching the conversion;
- one start-game quest whose PlayerRef alias runs the script;
- the `TES4MarkKey` global, which holds the DirectInput scan code (default
  65, F7, which vanilla Skyrim leaves unbound).

To change the key, enter `set TES4MarkKey to <code>` in the console. The new
key takes effect on the next load. `--key` changes the default at build time.

A key press does the following:

- shows "Mark N";
- writes `TES4MARK N ...` lines to the Papyrus log:
  - the player's position, cell, worldspace, game time, and whether a dialogue
    menu is open;
  - the crosshair reference and its base;
  - each actor in the player's cell, plus up to 40 random picks within 4096
    units for exterior neighbors, with:
    - position and distance;
    - current package;
    - AI, dead, disabled, combat, sit and dialogue state.

The key is ignored while the console is open, but works inside the dialogue
menu, which is where loops and wrong greetings happen.

The bridge DLL's Papyrus hook turns each `TES4MARK` line into a `mark` event
outside the error budget, since a mark is a burst of a few dozen lines. This
has two consequences:

- Papyrus logging must be on (`bEnableLogging=1`), because marks travel
  through the Papyrus logger;
- the TESGameBridge DLL must be a build with mark support.

The plugin's script compiles against the vanilla and SKSE headers. It calls
SKSE natives: `RegisterForKey`, `Cell.GetNumRefs`, `GetCurrentCrosshairRef`
and `UI.IsMenuOpen`.

## What each section checks
<a id="sections"></a>
**Marks.** For each mark, the report shows:

- the place and the in-game hour;
- the crosshair reference, with the source record behind its base (type,
  EditorID, model) and the type it was converted as. For example, a PWAT
  puddle shows as converted to STAT;
- each nearby actor's running package, placed in its source package list:
  - `#21 of 21, the last (fallback)`;
  - `not in its source list`;
  - `a Skyrim package`;
- for actors within 2,000 units or in dialogue, every package listed ahead of
  the running one whose daily schedule holds the mark's hour, with its
  conditions decoded. A package with no conditions there is flagged, since it
  should have won;
- the events of the 60 s before the mark, leaving out:
  - package changes of actors that are not in the mark;
  - line-end events.

**Quests.** Each start and each stage reached, in order, with the stage's
journal text. For each `SetStage` or `StartQuest` in the stage's result
scripts that never followed in the session, the report adds one line. A call
inside an `If`, or in a log entry with conditions, is shown with that context.
An unconditioned miss is flagged.

**Packages.** FO3, FNV and Oblivion run the first listed package whose
schedule and conditions hold.

- **Certainly wrong:** an actor ran a package while an earlier one in its
  list had no conditions and an any-time schedule, or ran a package its source
  never gave it.
- **Actors you met** (spoke with, or within range of a mark): what they ran,
  with every package listed ahead of it.

An actor that ran only its list's last package is only counted unless you met
it. On the Megaton session, flagging all of them listed 190 actors, mostly
correct defaults far from the player. That is why the full lists are limited
to actors you met.

**Dialogue.** Lines grouped into talks per speaker, split at a 20 s silence.
A talk whose lines are all one topic, such as two NPCs' scripted chatter, is
collapsed to one line. In other talks, two things are flagged:

- a line said more than once in the talk;
- a GREETING line after other topics, which is the greeting loop's signature.

**Session.** Loads, saves, location changes and cell loads. The cells one
load attaches in a burst are folded into one line, with unnamed exterior
cells counted.

Conditions are decoded from the export's raw CTDA:

- Fallout 3 writes both 20- and 28-byte forms;
- function names come from the engine's own table
  (`tes5_import/generated/dialog_engine_tables.json`), through the FO3/FNV
  index remap;
- form parameters are named by source EditorID;
- `GetStage` and `GetStageDone` gain the stage the quest reached this
  session, when it changed.

## What it does not see
<a id="blind-spots"></a>
- **Quest variables, script variables and a quest's stage before the
  session.** Conditions on them are shown, not judged.
- **Which alias holds an actor.** Papyrus offers no way to enumerate a
  reference's aliases. An actor running its NPC record's fallback instead of
  its alias packages, as Burke did on a save started before the aliases were
  renumbered, shows only as the fallback place in its list.
- **Day-of-week and month package limits.** These are printed but not
  checked against the mark's date.
- **Positions of actors between marks.** Package events carry no position or
  game time. A mark is the only snapshot.
