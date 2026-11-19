# The SPECIAL menu, and driving quests and conversations (PLAN 2026-11-17)

Two pieces of the FO3 and FNV openings on Fallout 4:

1. [The SPECIAL menu](#special): when it opens, what it sets, and the
   redo flows.
2. [Progression](#progression): how the story cases get past each beat
   that needs the player (walk, activate, talk, choose, fight, terminals),
   so they reach every quest stage the way a player does.

Both build on what passed on 2026-11-17: Fallout 4's character creation
stands in for the source game's ([character creation](fo4_pipeline.md#character-creation)),
and `tests/story/fo3_opening` passes CG00 and CG01's first beat for both
sexes ([story cases](fo4_story_tests.md#cases)).

## <a id="special"></a>1. The SPECIAL menu

### <a id="special-source"></a>What the source games do

| | FO3 | FNV |
|---|---|---|
| First SPECIAL | CG01 (age one): `CG01SpecialBookSCRIPT` OnActivate, stage ≥ 30 and 50 not done: `setstage CG01 50`, `ssbmp 40` | VCG01: `VCG01VigorTesterSCRIPT` OnActivate, stage 60 and objective 30 shown: `ShowLoveTesterMenuParams 40`, `SetStage VCG01 65` |
| Name | CG00 stage 40, `GetPlayerName` | VCG01 stage 10, `GetPlayerName` |
| Tags | CG03, the G.O.A.T.'s result lines: `SetTagSkills 3` | VCG01 stage 90: `SetTagSkills 3 1` |
| Traits | none | VCG01 stage 102: `ShowTraitMenu` |
| Redo | `Vault101ExitScript` box: name, face, `SetSPECIALPoints 40`, tags, leave | `VCG04ActivatorScript` box: name; or level 1, face, SPECIAL back to 5 + `SetSPECIALPoints 40`, tags, traits |

Both games give 40 points over 7 stats that start at 5.

### <a id="special-built"></a>What is built

- Every SPECIAL command (`ssbmp`, `ShowSpecialBookMenu`,
  `ShowLoveTesterMenuParams`, `SetSPECIALPoints`) converts to
  `TES4CharacterEvents.Menu("special", n)` (`command_rows_fallout4.py`).
  `F3NV_CharacterRules` answers with FO4's own `Game.ShowSPECIALMenu()`.
  The 40 comes from the `uSPECIALPoints` setting the build writes
  (`spike/character.py`), not from `n`.
- When `SPECIALMenu` closes, `SetSkillBases()` derives the skills.
- FO4's SPECIAL card has a name field. That is our name entry:
  `GetPlayerName` is only a note on FO4.
- Tags and traits open Cleanroom UI's `CRUI_LevelUp` in its tags and traits
  modes (built 2026-11-12, not played).
- **Played:** FNV's Vit-o-matic (2026-10-19): the menu opened, it closed at
  40 points, and Doc reacted ([spike 2](fo4_spikes.md#spike-2-vcg01)).
  FO3's book has never been played.

### <a id="special-decision"></a>When it opens: at the source game's beat (decided 2026-11-17)

**Decided:** A. Both the book and the Vit-o-matic work for SPECIAL as they
are.

**A. Keep it where the source game has it (chosen).** FO3's book at
age one, FNV's Vit-o-matic. Nothing new to build: the book and the tester
already open FO4's card. The name moves to that card. Nobody says the name
aloud or shows it on screen before then, so the move can't be seen: FO3's
Pip-Boy arrives at 10, and FNV's Doc never says it.

**B. Move it into Fallout 4's opening, after the mirror.** One sitting for
look, name and SPECIAL, as character creation now is. Then the book and
the tester would open nothing, the same way the first race menu is
skipped. It costs a second skip flag and a real beat: the book is an
objective, and the Vit-o-matic is a Doc scene that breaks the machine.
Not chosen.

### <a id="special-work"></a>Work under A

1. **Play FO3's book** (story case, [CG01](#cases-fo3)). Check that the card
   opens with the player at toddler scale (`setscale 0.4`,
   `SetPCToddler`), that the name sticks, and that CG01 goes on to 70.
2. **Honor a total other than 40.** `ShowSPECIALMenu` takes no total, and
   the build writes one setting for the whole game. Census (2026-11-17):
   all 4 sites in both games pass 40 (2 `SetSPECIALPoints`, 1 `ssbmp`,
   1 `ShowLoveTesterMenuParams`). Keep the
   setting, and have `Menu("special", n)` trace a note when `n` isn't 40,
   so a mod with another value shows up in the log.
3. **The redo flows** (FO3's vault door, FNV's VCG04). FNV first sets each
   stat back to 5, then opens the card on a character that already has
   points spent. What FO4's card offers then (40, 0, or 40 minus spent) is
   [the open question](#special-unknowns). If it offers too few, the
   "special" handler sets the stats to the source game's start values
   before it opens the card.
4. **Name buttons in the redo boxes** (button 0 of both). Today they do
   nothing. Under A they open the card, which can rename: map
   `GetPlayerName` to `Menu("special", 0)` only where it is a redo button.
   That is the box's own button test, the same way `sex_buttons` reads its
   box.

### <a id="special-unknowns"></a>What must be learned in play

- What FO4's card offers on a character that has already spent points
  (the redo).
- Whether the card and its camera work at toddler scale.
- Whether `SetSkillBases` runs once per close and leaves no extra points
  (the 2026-10-21 "no controls after the Vit-o-matic" report was fixed
  but never played).

## <a id="progression"></a>2. Driving quests and conversations

### <a id="rule"></a>The rule

A case reaches a stage only through what a player does. It moves, uses
things, talks, picks lines, fights and uses terminals. It never sets a
stage ([story cases](fo4_story_tests.md#cases)). A beat the harness can't
drive yet ends the folder with a note, as `02_cg01.f4test` does today.

### <a id="what-moves-a-stage"></a>What moves a stage in the converted game

| Source trigger | On FO4 | The case does |
|---|---|---|
| Trigger box (OnTriggerEnter) | the same trigger | `walk` into it |
| OnActivate script | the same | `activate` |
| INFO result script (a picked line) | the INFO's fragment | `talk`, then `choose` |
| Say / SayTo lines, package ends, timers | Custom topics, package events | `hear`, `until` (built) |
| OnDeath / OnHitWith | the same events | `kill`, `shoot` |
| Terminal entries | FO4 terminal menu | `terminal` |
| Message boxes | FO4 message box | `answer` (built) |
| Character menus | FO4's card, LooksMenu, Cleanroom UI | `close`, `call` (built); `pick` |

### <a id="verbs"></a>The verbs to build

All of them go through the test DLL or the console, and none of them set a
stage. Each one names **source** records (an EditorID, or a FormID through
the build's FormID ledger), so a case reads the same from build to build.
That needs one shared lookup: the harness reads the build's ledger once a
run and turns a source reference into the FO4 FormID.

| Verb | How | First case that needs it |
|---|---|---|
| `walk <ref>` | built: `Game.SetPlayerAIDriven` and `Actor.PathToReference` (through `cgf`/`cf`) path the player over the navmesh, then the player faces the ref and holds W until it arrives (inside a trigger's primitive, or within a radius). A real walk tests the navmesh and the triggers ([fo4_story_moves](fo4_story_tests.md#cases)) | CG01 stage 12 (Dad's trigger) |
| `activate <ref>` | built: the player looks at the ref and presses E (since 2026-11-19; before, the console's `<ref>.Activate player`, which needed no prompt and no reach) | CG01's playpen gate (30), the SPECIAL book (50) |
| `heard <speaker> <INFO>` | built: as `hear`, but waits for the line's end, after its result script ran | FNV 60: Doc's line shows objective 30 as it ends |
| `look <ref>` | built: turns the player (heading, then pitch) from its eye to the middle of the ref's bounds, as `shoot` aims. FO4 lists a talk's choices only while the player faces the speaker; a seated player faces the seat's way ([psych test](fo4_pipeline.md#psych-test-no-choices)) | VCG01's psych test (Doc beside the couch) |
| `talk <npc>` | built: `activate` on the NPC once no menu is open, again every 6 s until the dialogue menu opens ([verbs](fo4_story_tests.md#cases)) | CG02's party guests |
| `choose <words>` | built: reads the rows our dialogue movie draws through `invoke`, presses the row's number key, and presses again if the list stays up (a lost key) | CG02 guests (7–50), CG03's G.O.A.T. (40/42/45), FNV's psych test (85) |
| `bye` | the dialogue menu's own exit | CG02 |
| `pick <menu> <choice>` | test DLL `invoke`: calls a function in our own Flash movie (Cleanroom UI tags and traits), the one its button calls | CG03's tags; FNV's tags (90) and traits (102) |
| `kill <ref>` | `<ref>.Kill player`: OnDeath with the player as killer | CG02's radroach (70), CG04 |
| `shoot <ref>` | built 2026-11-18; kills CG02's radroach (70), but the BB targets take no hit ([open](fo4_pipeline.md#cg02-targets-unhit)): draws the weapon, faces the target and pitches to its bounds' middle (`SetAngle` z and x), then a left click per shot. OnHitWith needs a real hit | CG02's BB gun targets (55) |
| `terminal <entry>` | test DLL `call` on `TerminalMenu`'s code functions, found by disassembly as LooksMenu's were | CG04's Overseer terminal |
| `sit <ref>` | `activate` on the furniture | CG03's G.O.A.T. desk |

**One mechanism for our own menus.** `choose` and `pick` share a single
test DLL command, `invoke <menu> <path> <args>`: a Scaleform Invoke on an
open menu's movie. It works for any menu we draw (the Cleanroom dialogue
menu, `CRUI_LevelUp`) without a test hook in Cleanroom UI. For FO4's own
menus, `call` stays: a code function by number, found by disassembly.
`close` gains each menu's Done the same way (`SPECIALMenu` next).

**The SPECIAL card in a case.** `menu SPECIALMenu`, then `close
SPECIALMenu` through its Done code function, then `answer OK` if it asks
to confirm. The default stats are what the case wants; a later case can
`call` the stat buttons for a build that needs them.

### <a id="cases-fo3"></a>FO3 beats, in order

| Quest | Beat | Verbs |
|---|---|---|
| CG01 | Walk to Dad (12), lines and package (14→20), playpen gate (30), leave the crib (40), SPECIAL book (50), timer (70), follow Dad (90→100) | `walk`, `hear`, `activate`, `close SPECIALMenu` |
| CG02 | Party guests and their choices (7–50), cake (15), BB gun targets (55), radroach (70), photo, Jonas (95) | `talk`, `choose`, `walk`, `shoot`, `kill` |
| CG03 | Triggers (15, 20, 50/60, 90), Brotch, the desk, the G.O.A.T. choices (40/42/45), tags, Tunnel Snakes (optional) | `walk`, `talk`, `sit`, `choose`, `pick` |
| CG04 | Amata's force greet and choices, radroaches and security (15/30), the office (60), the Overseer's terminal and door, reactor switches (110/120), the control pod (140), the exit (150) and its redo box | `choose`, `kill`, `walk`, `terminal`, `activate`, `answer` |

### <a id="cases-fnv"></a>FNV beats, in order (a new `tests/story/fnv_opening`)

| Beat | Verbs |
|---|---|
| Waking at Doc's: stages 0–50 are timers and Doc's lines. The name and the Reflectron are skipped (FO4's creation ran first) | `hear`, `until` |
| Walk to the Vit-o-matic (60), use it (65): the SPECIAL card | `walk`, `activate`, `close SPECIALMenu` |
| Psych test (85): case `vcg01_psych_test` passes; it failed while the seated player looked away from Doc; it now uses `look` ([fixed](fo4_pipeline.md#psych-test-no-choices)) | `walk`, `activate`, `look`, `choose` |
| Tags (90), traits (102) | `pick` |
| Leave (115): Doc's talk, the hardcore box, then 200 | `walk`, `talk`, `choose`, `answer` |

### <a id="order"></a>Build order

Each step ends with its cases passing on the laptop for both sexes.

1. **Ledger lookup, `activate`, `walk`** (moveto stand-in first, the real
   walk right after). FO3: the rest of CG01, including the SPECIAL book
   ([work 1](#special-work)). FNV: up to the Vit-o-matic.
   **Built and passing 2026-11-17, both sexes, on the laptop:** FO3 7 of 7
   cases into CG02, FNV 3 of 3 through stage 65. The SPECIAL card is still
   closed by a plain hide (step 2). The runs found and fixed five converter
   bugs; they and the cost of each loop are in the
   [test layers plan](fo4_test_layers_plan.md), which also orders the
   speed work to do before going much further.
2. **`SPECIALMenu`'s Done** in the test DLL (disassembly, as LooksMenu).
   CG01 to stage 100; FNV through 65.
3. **`invoke`, `options`, `choose`, `bye`**: the dialogue menu. CG02's
   guests, FNV's psych test, CG03's G.O.A.T.
   **CG02 passing 2026-11-18 on the laptop, through the BB gun (44):**
   female from `cg02_mrs_palmer` to `cg02_bb_gun`, male to
   `cg02_dad_surprise`. The runs found and fixed a speaker hijacked by a
   second shared-alias scene, a dialogue gate that never held, and a force
   greet that pulled Dad out of his scene
   ([fo4_pipeline.md](fo4_pipeline.md#gate-speaker)).
4. **`pick`**: tags and traits. CG03's tags, FNV 90 and 102. These menus
   are also played here for the first time.
5. **`kill`, then `shoot`**: CG02 to stage 95. `shoot` is built
   (2026-11-18): Dad's talk in the range sets 50, and the BBs leave, but
   the targets take no hit yet ([open](fo4_pipeline.md#cg02-targets-unhit)).
6. **`terminal`**: CG04 to the exit, then both redo boxes
   ([work 3 and 4](#special-work)).

Checkpoints (`--checkpoints`, `--from`) are built, so each folder can
start from the last passing case. Loads are queued as the Load menu does;
the console's `load` hung ([S3](fo4_test_layers_plan.md#s3)).

### <a id="tutorial-run-2026-11-18"></a>The whole FO3 tutorial, 2026-11-18

CG04 now has cases to the exit: `cg04_butch` (18, his force greet, declined
by A3: 20), `cg04_atrium` (33, 35), `cg04_overseer`
(38, his key and password through A1 then B2), `cg04_office` (60),
`cg04_terminal` (120, the fourth entry by S and E), `cg04_control_pod`
(140 to 145), `cg04_exit` (the redo box, 200).

Result, 2026-11-19: every case passes as both sexes. Female ran in pieces
from checkpoints (runs 29-59). Male ran from a fresh character (run 60), and
after `cg02_targets` failed once, from that case on (run 61): 38 of 38 cases.

Converter bugs these runs found and fixed:
- **GetLocked's 0/1/2** ([fo4_pipeline.md](fo4_pipeline.md#getlocked-states)):
  CG04 stage 0 opened "You are now locked out of the terminal" before the
  Overseer's terminal was touched, and every quest script held behind the box.
- **Kendall never barked (stage 12)**
  ([fo4_pipeline.md](fo4_pipeline.md#walk-up-before-quest)): his SayTo
  package begins at CG03 stage 40, before CG04 runs, and FO4 had not loaded
  CG04's walk-up scene yet, so `WalkUp` quit. An earlier note here blamed
  stale checkpoints; a run from CG03 on the current build failed the same way.
- **Amata never said goodbye at the vault door (stage 145)**
  ([fo4_pipeline.md](fo4_pipeline.md#package-target)): her
  `CG04AmataSayGoodbye` tests `IsInCombat` on its Target, which FO4
  packages do not have, so it never ran. Target tests now run on the
  package's target reference (FO3 42 packages, FNV 4).
- Earlier the same day: the chat listener, Find furniture packages, and the
  harness's `talk` facing the speaker (fo4_pipeline.md).

Harness fixes:
- **`cg03_sit` sits last.** The students' Find packages pick any free seat
  (in one run Wally took `02B793`, in another `02B765`), so the case waits
  for all seven to sit, then tries every seat. The old order took a desk a
  student had already chosen.
- **CG04 after the Overseer** follows the doors and switches a player
  uses: kill Mack first ([talk-in-combat](#talk-in-combat)), wait out the
  Overseer's goodbye line (`closed`, not Tab), open each closed door on the
  way ([atrium-path](#atrium-path)), wait 5 s before the terminal's keys
  (its header types out first), close the terminal with `close`
  (Tab on its "Opening..." page did nothing, and no checkpoint saves with it
  open), and press `CG04DoorSwitchREF`, the activate parent of the tunnel's
  secret door, which only a non-player may open.

<a id="seat-taken"></a>**Open: a student whose found seat the player takes
stands for good.** In two runs the player sat in the desk Paul's
`CG03PaulGoToClass` (Find, now `SitFoundRef`) had chosen. Paul stood beside
it for 300 s, still on that package (`GetIsCurrentPackage`), and did not sit
even when moved next to a free desk, re-evaluated (`evp`), or disabled and
enabled. Stage 60 needs every student seated, so the G.O.A.T. never started.
A real player who sits before a student arrives hits this. Not changed: how
FO3's Find recovers from a taken seat is unconfirmed.

<a id="atrium-path"></a>**Harness: the player's engine path stops at closed
doors.** `walk` paths the player with `PathToReference`. From the
apartments, that path never reached the load door to Vault101b (`054285`);
via the hall's open door `09BA40` it did. Inside Vault101b the path toward
the radroach stop box `02D4B6` stopped at -4459, -221 in two runs, beside
the closed hinged door `05396D`, which the player could not reach (336 units
off). Whether this is a navmesh gap NPCs also hit is unconfirmed: Amata
walks this way to the office at stage 33. `cg04_atrium` moves the player to
the stop box.

Later CG04 cases show the same pattern: the player's engine path stops at
a closed door. From the Security Center it stopped before the closed sliding
door `0539B5`, while Amata had reached the office through it. In the tunnel
it stopped at the hinged door `05396D`. Once each door was activated, the
walks went through. NPCs open doors on their paths; the AI-driven player
does not. So this is the harness's walker, not the navmesh, and the cases
open each door on the way. One spot is still a moveto: from the Overseer's
terminal the stride to the stairs his desk opens stops at the desk's edge,
while the player set down there lands on the floor below, so the opening
is real.

<a id="talk-from-afar"></a>**Harness: `talk` from afar spends a Say Once greeting.**
The console's `activate` reaches an actor at any distance. From 630 units
the Overseer's greeting `000681FB` ("turn yourself in", Say Once) played as
a line with no dialogue menu, so its choices never showed, and every later
activation played his catch-all `0002E6C6` ("I have nothing else to say to
you."). A player cannot activate him from there. `cg04_overseer` walks up to
him first. (An earlier reading blamed the interrogation scene for holding
him; the log shows the greeting played at the first activation.)

<a id="talk-in-combat"></a>**Open: FO4's dialogue does not pause a fight.**
At stage 38 Officer Mack (`064913`) starts combat with the player (his
`OnStartCombat` sets 38). FO3's dialogue menu is a menu mode, so the world
stops while the player talks to the Overseer. FO4's does not: in run 43
Mack and then Chief Hannon (`06490E`) beat the player from 171 to 40
health during the talk, the Overseer's A1 answer scene ran 68 s, and the
menu showed no choices for 60 s. A player would kill Mack first, which is
FO3's intended path (his death only starts the Overseer's calls for help).
`cg04_overseer` kills both before talking. Any FO3/FNV talk next to a
hostile has this gap; nothing converts it.

<a id="npc-health"></a>**Open: converted NPCs have FO4's human health, not
FO3's.** In `cg04_hall` the three ambush radroaches killed Officer Kendall
(100/100 health, 5 per bite, 15 bites in 14 s) while he swung 4 times and
killed one, so stage 15 waited on the player. FO3's NPC record has Base
Health 10, Endurance 6, level 2 (the GECK: health from Endurance and level,
plus Base Health), and FO3's radroach bites for 3 (`DATA.AttackDamage`),
where ours use Fallout4.esm's `UnarmedRadRoach`. Creatures get FO3's health
([creature stats](fo4_pipeline.md#creature-stats)); NPCs do not
(`DATA.BaseHealth` is read only for the player). The case has the player
finish the radroaches when Kendall falls.

<a id="greet-before-mark"></a>**Open: a force greet before the NPC reaches its
Wait Location.** At CG02 stage 44 Dad runs `CG02DadToInsideTargetRange`
(Conversation: wait at `CG02DadTargetRangeInsideMarker`, trigger the player
within 150 of it). The case walked the player there ahead of him; Dad greeted
242 units from his mark, so his range line `0001F9C9` (GetDistance to the
marker < 200, the one offering "Thanks, Dad.") failed and the generic Goodbye
greeting `0001F9CA` played: no stage 50. The GECK wiki's Dialogue Package
page has the actor move to the Wait Location and wait there for the target
to enter the trigger; our `F3NV_ForceGreetInTrigger` greets as soon as the
player is in the trigger, wherever the NPC is. Not changed: which FO3 rule
holds when the player arrives first is unconfirmed, and the template tree is
shared by every converted force greet. The case now follows Dad in.

### <a id="docs-to-fix"></a>Docs out of step (found while planning)

Fixed 2026-11-18: the story tests' status and `run` row, autoplay's stance on
real keys, drift's retired Male/Female box, and ROADMAP's tag skills row.
