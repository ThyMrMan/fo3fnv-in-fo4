# Talking next to a fight: a stand-in for FO3/FNV's dialogue pause (PLAN 2026-11-19)

**Status:** A chosen (user, 2026-11-19); built, not played ([built](#built)).

FO3's and FNV's dialogue menu is a menu mode: while it is open the world
stops, so nobody can hurt the player mid-conversation. Fallout 4's dialogue
is a scene that runs on game time, so a fight goes on around it. The user
confirmed in game that the converted FO3 lets you talk to the Overseer
while Officer Mack beats you; in the test harness (run 43) Mack and Chief
Hannon took the player from 171 to 40 health during that talk, the
Overseer's A1 answer ran 68 s, and the menu showed no choices for 60 s
([talk-in-combat](fo4_opening_progression_plan.md#talk-in-combat), in the
playtest-harness branch). Why the choices stalled is not proven.

**V** = verified this session (data, source, disassembly notes with a
citation), **I** = inferred.

## <a id="source"></a>What FO3 and FNV do

- **Dialogue is menu mode 1009 (V,** GECK wiki `MenuMode`): with any menu
  open the game is not in GameMode, so GameMode script blocks stop as well
  as AI, combat and timers. Result scripts still run.
- **Talking to an actor in combat is allowed (V,** GECK wiki
  `StartConversation`): a force greet on an actor in combat with the player
  opens GREETING instead of the chosen topic. FNV authors in-combat answers
  there (below), so the menu does open on a fighting actor.

### <a id="census"></a>Census: conversations next to hostiles

Script: a one-off in the session scratchpad (`talk_combat_census.py`),
over `export/<plugin>/INFO.txt`, `PACK.txt`, `SCPT.txt`, `DIAL.txt`.
"Menu INFO" = a Topic-type INFO or a GREETING line. Conditions decoded from
`Condition[].Raw` (function ids from xEdit's `wbDefinitionsFO3.pas`:
IsInCombat 289, GetAttacked 63, GetShouldAttack 66, GetIsAlerted 91).

| What | FO3 | FNV | FNV DLC (DM, HH, OWB, LR) |
|---|---|---|---|
| Menu INFOs | 10,864 | 17,981 | 3,944 |
| Menu INFO starts a fight (`StartCombat`, `SetEnemy`, `SendAssaultAlarm` in its result) | 140 / 37 / 4 | 241 / 139 / 14 | 27 / 21 / 0 |
| ... and is not Goodbye, so the menu can stay open after it | 4 | 30 | 1 |
| Menu INFO stops a fight (`StopCombat`, `StopCombatAlarmOnActor`): talk-downs | 1 | 20 | 0 |
| Menu INFO that only passes in combat (`IsInCombat` true on speaker, player or a ref) | 1, Goodbye | 22, 21 Goodbye | 2 (Dead Money), Goodbye |
| Menu INFO that only passes out of combat | 3 | 22 | 0 |
| Menu INFOs that hire a companion (`SetPlayerTeammate 1`) | 26 | 25 | 2 |
| Dialogue packages (force greets) | 386 | 332 | 73 |
| ... gated on a combat test (all `IsInCombat == 0` or `GetShouldAttack == 0`) | 6 | 16 | 1 |
| Scripts that `StartConversation` and test combat | 1 | 12 | 8 |

What the numbers say:

- **Authors keep force greets out of fights.** Every combat-gated dialogue
  package is gated *off* in combat (CG04's Amata, Gomez and Butch; FNV's
  companion force greets on both the speaker and the player). None is gated
  on.
- **FNV answers "you're in a fight" with one line.** 22 GREETING lines pass
  only in combat, and 21 are Goodbye: Casa Madrid's "Leave me out
  of your fight!" (`00158738`, player in combat), the Hoover Dam
  assassination's "Not now!" (`00145AF7`), Cass's "Save the sweettalk for
  when the shooting's done" (`0015E8CA`). FO3 has one (`00061F97`, an
  Outcast: "Shut up. Kinda busy."). Boone's "Let's get out of this first."
  (`00136A08`) is not Goodbye.
- **Talk-downs are FNV's.** 20 lines stop a fight: the Freeside securitron
  greeter (`0011976E`...), Mortimer (VMS18), Legate Lanius (12 lines,
  VFreeformHooverDam), the Primm hostage (`000BACD5`). FO3 has one, Amata
  after Butch's fight in CG02 (`0003162F`).
- **A fight that starts mid-talk is rare** (4 FO3, 30 FNV, 1 DLC): a line
  that starts combat but leaves the menu open. In FO3/FNV the attacker
  waits for the menu to close; on FO4 he attacks the player who is still
  reading.
- **The common case is not authored at all:** the player opens a talk with a
  bystander while someone else is fighting them. That is the Overseer and
  Mack. Nothing in the data marks it; it can happen anywhere.

## <a id="fo4"></a>What Fallout 4 itself does

- **The dialogue menu does not pause (V).** DialogueMenu's constructor ORs
  `0x18800` into its flags (allow saving, custom rendering, assign cursor),
  not Pauses Game ([R5](research/fo4_target.md#no-pause)); the CK wiki's
  `Utility.IsInMenuMode` says the same.
- **Earlier decision (2026-10-05):** talks stay unpaused, and "combat
  breaking into a talk" was accepted as FO4's normal behavior
  ([no-pause](research/fo4_target.md#no-pause)). The user's 2026-11-19
  play reopens that line; this plan replaces it once an option is chosen.
- **FO4 lets the player talk mid-fight, and answers in one line (V).**
  Fallout4.esm's `PlayerCombatHellos` (quest
  `DialogueGenericPlayerCombatHellos` 0001E5EA) is a Hello that needs
  `IsInCombat == 1` on both the player and the target. No setting refuses a
  talk in combat: the exe's only `sNoTalk*` strings are `sNoTalkFleeing` and
  `sNoTalkUnConscious`.
- **Scene combat handling is per actor, not a pause (V,**
  `wbDefinitionsFO4.pas`, census of 3,568 vanilla scenes). Each scene actor
  has Combat End (3,602 of 4,752 actors) or Combat Pause (436) for when
  *that actor* fights; no scene flag stops or pauses the world. Our scenes
  write Combat End (`fo4_import/spike/records.py`). The Overseer is not in
  combat, so neither applies to him.
- **No Papyrus pause or time scale (V).** `SetGlobalTimeMultiplier` exists
  only as a console command; neither vanilla's nor F4SE's scripts expose it.
  `Debug.SetGodMode` and `Utility.SetINI*` are debug-only and do nothing in
  release. What Papyrus has: `InputEnableLayer` (player controls only),
  `Actor.SetGhost` (unaffected by weapons, spells, explosions),
  `StopCombat`, `StopCombatAlarm`, `SetPlayerAIDriven`.
- **Slow Time is an FO4 archetype (V):** archetype 37; vanilla uses it for
  Jet (0.3 for 10 s) and the Nerd Rage / legendary slow-time spell (0.3 for
  15 s). Whether it slows a speaker's voice or the dialogue camera is not
  known.
- **A pausing menu can come from F4SE (V):** `UI.RegisterCustomMenu`'s
  default flags `0x801849D` include Pauses Game (`F4SE\UI.psc`). Whether one
  can be open beside the DialogueMenu is not known.

## <a id="ours"></a>What our dialogue menu has

- The menu is Cleanroom UI's: `CleanroomDialogue.dll` plus its own
  `DialogueMenu.swf`, which the converter ships
  ([spin-offs](spin_offs.md#move), `fo4_import/cleanroom.py`). It replaces
  the game's movie but stays the engine's `DialogueMenu`, with the engine's
  flags. The DLL hooks the option and answer picks, knows when an action is
  waiting for the player (`TraceWaits`), and reaches the open menu through
  CommonLibF4 (`UI::GetMenu("DialogueMenu")`)
  ([as built](fo4_dialogue_menu_plan.md#as-built)).
- Nothing in it pauses, slows or tests combat today (V: no match for
  pause, combat, menuMode or freezeTime in `cleanroom_ui/dll/dialogue/`).
- **What CommonLibF4 exposes for a pause (V, headers):**
  `UI_MENU_FLAGS::kPausesGame` (bit 0) on each menu; `UI::menuMode` (0x1E0),
  the count of open menus that pause; `Main::freezeTime` (0x2A, what `tfc 1`
  sets); `Main::inMenuMode` (0x1D0) and `Main::inDialog` (0x1D1). The
  engine's own way to change the first two on an open menu is in
  [built](#built).
- **A lead for the 68 s with no choices (I, not proven).** The Player
  Dialogue action waits until neither the player nor the NPC is "talking"
  (`Talking`, vtable slot 0x270/8, the test the run function waits on;
  `TraceWaits` logs it). FO4 gives the player hit grunts, which the
  converter leaves on ([ROADMAP](ROADMAP.md): "Fallout 4 voices its own"),
  so a player being beaten may count as talking and hold the list. The
  menu's own trace in that run's `CleanroomDialogue.log` (debug level) would show
  `player talking 1` through the stall if so.
- The converted game already needs both Cleanroom UI DLLs for its dialogue,
  so an option inside `CleanroomDialogue.dll` adds code to a DLL the
  feature already has, not a new DLL. It is PC only, like the menu.

## <a id="options"></a>Options

Each option is measured against the census above: the Overseer case (talk
to a bystander while someone fights you), the 30-odd lines that start a
fight with the menu still open, the 21 talk-downs, and the 24 in-combat
Goodbye answers.

### <a id="a"></a>A. Pause the world while the choices wait (in `CleanroomDialogue.dll`)

While our list is up and waiting for the player, the DLL pauses the game;
on a pick or a leave it lets go, and the NPC's answer plays on game time.

- **Mechanism:** the engine's own switch for an open menu's Pauses Game
  flag, which vanilla's DialogueMenu already uses; driven by the menu
  movie while its list waits ([built](#built)).
- **Right against FO3/FNV:** the player's reading time, which is unbounded
  and is most of a conversation's length, costs nothing: no hits, no
  timers, no AI, no GameMode-style scripts, as in menu mode 1009. A line
  that starts a fight but leaves the menu open (4 FO3, 30 FNV) is held
  while the player reads the next choices, though not during the next
  answer line. Talk-downs and in-combat answers
  keep working, since the menu opens as before.
- **Wrong:** each NPC line plays on game time (a few seconds each), so a
  hostile still lands hits during the answers. In run 43 that is most of
  the damage only if the stall is the answer itself; with the stall's
  cause unproven ([lead](#ours)), A may not cover it. Papyrus also
  pauses while the list waits, which FO3 does too, but a converted script
  that polls on a timer during a talk now stops (FO3's GameMode blocks
  stopped the same way).
- **Cost:** small code in the DLL and the menu movie, then play to check
  that input, camera, lip sync and the scene resume. A Cleanroom UI
  release and a DLL rebuild.
- **DLL:** yes, the existing `CleanroomDialogue.dll`. The dialogue menu
  already needs it, so no new DLL and no new dependency.

### <a id="b"></a>B. Pause the whole talk, lines included

Menu mode for the whole conversation, as FO3: the world stops from the
menu's open to its close, while the speaker's lines still play.

- **Right:** exact FO3/FNV behavior; the Overseer case costs no health at
  all.
- **Wrong / cost:** FO4 plays a line as a scene action on game time
  ([fo4](#fo4)), so a plain pause stops the line, its voice timer and the
  scene. Making it work means letting one scene and two actors run while
  the world is paused: new engine hooks in the scene, actor update and
  audio paths, found by disassembly, with no vanilla precedent. Large,
  fragile across game versions, and the highest risk of a hang.
- **DLL:** yes, much deeper hooks in `CleanroomDialogue.dll`.
- **A cheaper cousin, slow time (not recommended):** cast vanilla's Slow
  Time archetype (0.3) on the player for the talk, in Papyrus. Hits land at
  a third of the rate rather than none, and it may slow the speaker's voice
  and camera too (unknown). Neither FO3 nor FO4.

### <a id="c"></a>C. Shield the player during a talk (no pause)

While the DialogueMenu is open, the player takes no damage and hostiles
stand off; the world keeps running.

- **Mechanism:** Papyrus only. A helper quest registers for
  `OnMenuOpenCloseEvent("DialogueMenu")` and, while it is open, makes the
  player unhittable (`Actor.SetGhost`) and, optionally, calls
  `StopCombatAlarm` on the player so attackers drop the fight, undoing the
  ghost on close (a stopped fight does not come back by itself).
- **Right:** no damage during a talk, lines included; no DLL; works with
  any dialogue menu.
- **Wrong:** the world does not stop. Attackers walk up, reload, throw
  grenades, kill allies and the speaker; timers and quest scripts run; a
  line that starts a fight starts it during the talk. The player can
  open a talk to become untouchable (FO3's pause is the same exploit, but
  there the attacker also froze). Ghosting the player also hides them
  from friendly AI.
- **Cost:** small; one script and a menu event.
- **DLL:** no.

### <a id="d"></a>D. No talk while the player is fighting

Generalize FNV's own answer: if the player is in combat, activating a
non-hostile NPC plays that NPC's in-combat GREETING line when it has one
(the 24 Goodbye lines), else a short refusal, and opens no choices.

- **Mechanism:** the converter adds a player-in-combat Goodbye line at the
  top of every converted GREETING (or the menu DLL refuses to list options
  while `PlayerCharacter::IsInCombat`). Force greets are already gated
  off in combat by their authors.
- **Right:** never stuck in a menu taking damage; matches FNV's authored
  intent for the NPCs it covers; cheap.
- **Wrong:** changes both games. FO3 lets you talk to the Overseer while
  Mack hits you; a talk-down while the player is still flagged in combat
  (the securitron greeter, Lanius, Amata after Butch) would refuse; a talk the source opens with
  `StartConversation` on a fighting actor opens GREETING, not nothing.
  Every NPC without an authored line gets an invented one. It hides the
  difference rather than standing in for the pause.
- **Cost:** small. **DLL:** no (the converter-side form).

## <a id="recommendation"></a>Recommendation

**A: pause the world while the conversation waits on the player.**

- It stands in for the part of FO3's pause that costs the player: the
  open-ended time spent reading and choosing, during which FO3 stops
  everything. It keeps every authored case working (talk-downs, the 24
  in-combat Goodbye lines, `StartCombat` lines firing when the talk moves
  on), where D breaks talk-downs and C lets the world run on.
- It adds a few lines to a DLL the dialogue already ships, needs no new
  DLL, and is easy to switch off (one setting) if play shows a problem.
- It leaves NPC lines on game time. If play then shows the answers alone
  still hurt (a long answer next to a melee attacker), B is the only exact
  fix and should be weighed then, not before.

## <a id="built"></a>As built (2026-11-19, not played)

**The engine's switch (V, disassembly).** `UI` + menu name + bool, at
1.11.240 `0x1A82A00` (next-gen ID 2284770, also in the 1.10.984 database;
old-gen 241336 at `0x20440D0` in the decrypted 1.10.163 exe). It looks the
menu up, and only when its Pauses Game flag (`+0x58` bit 0) differs it sets
or clears the flag, counts the paused menus (UI `+0x1E0`, CommonLibF4's
`menuMode`) up or down, and sends `MenuModeCounterChangedEvent` and, when
the count crosses zero, `MenuModeChangeEvent`: what opening a pausing menu
does (`0x1A811C2`). Vanilla's DialogueMenu calls it itself around the
speech-challenge animation (`0x10460BD`, `0x1045EE7`). Closing a menu
whose flag is set counts it down (`0x1A80A5D`), so a talk that ends while
paused leaves no pause behind.

**What is built**, in two Cleanroom UI branches:
- `claude/talk-pause-pin` (commit `ea1e24a`, on `8cd1f3b`, the commit the
  converter pinned before; F4SE 0.7.9 build, 1.11.240 only). The converter
  now pins it (`tes_runtime/dist/cleanroom_ui.txt`) and ships its
  `CleanroomDialogue.dll`; `CleanroomUI.dll` rebuilt from it matches the
  shipped one in size, so only the pause changed.
- `claude/talk-pause` (commit `297253d`, on Cleanroom UI main;
  CommonLibF4 build, both game generations by Address Library ID), for
  when the pin moves to main.

In both:
- `dll/dialogue/dialogue.cpp`: native `PauseWhileChoosing(on)`, which calls
  the switch for `DialogueMenu` on the game's thread (F4SE task); it does
  nothing once the menu has closed. The pinned one first checks the
  switch's bytes (`0x1A82A8E`) and refuses when they differ.
- `menus/dialogue/as3/DialogueMenu.as`: with `[Dialogue]
  bPauseWhileChoosing=1` in `CleanroomDialogue.ini` (off by default, so
  Cleanroom UI on stock Fallout 4 is unchanged; the pinned DLL reads it,
  the main one's movie does), the world pauses while the list is up and
  done looking for options of ours (the 30-frame retry), and runs again on
  every way the list goes: a pick or a leave (`closeList`), the game hiding
  it (`HideButtonHelp`). Picks of the game's own buttons go through the
  same list, so no pick can leave it paused.
- Converter: the masterless build writes that INI with the pause on
  (`fo4_import/dialogue_menu`, `write_settings`).
- Tests: Cleanroom UI `tests/test_dialogue_menu.py` (11 pass on the pin,
  14 on main; the movie compiles), `tests/test_fo4_dialogue_menu.py`
  (7 pass). All DLLs compile.

**To play** (`CleanroomDialogue.log` at `[Log] iLevel=3` names each pause
and release):
1. The Overseer with Mack attacking (FO3 CG04, stage 38): no damage while
   the list is up; the fight goes on after a pick.
2. The list keeps its keys and pad under the pause.
3. The camera, lips and scene resume after the pick; Tab leaves cleanly.
4. A save and a load with the list up leave no pause behind.
5. An FNV talk-down (the Freeside securitron greeter) and a line that
   starts a fight with the menu open (FNV `VMS45` Papa Khan).

**Not covered:** NPC lines still play on game time. The 68 s stall in run
43 came after a pick, so the pause does not reach it; its
[lead](#ours) is still unproven, and no dialogue log was kept for that run.

Once played, replace [no-pause](research/fo4_target.md#no-pause) with a
link here.
