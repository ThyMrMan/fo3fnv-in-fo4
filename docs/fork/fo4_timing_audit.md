# Plan: the progress timing audit

**Status:** planned 2026-10-29; phases 1 and 2 built the same day as
`--audit timing` ([what was built](#built)). Status goes in
[ROADMAP.md](ROADMAP.md).

**Goal.** Check, from the two plugins' data and with no game running, that
the build changes each piece of game state at the same moment FNV does. That
means quests start, stages advance, topics unlock and options appear no
sooner and no later than in FNV, and nothing FNV moves forward is left stuck.
Today these bugs are found only in play, and only when they are obvious.

## Contents

- [Why the current audits miss it](#gap)
- [What the first measurements found](#measured)
- [How it works](#design)
- [Part A: starting state](#start)
- [Part B: writers](#writers)
- [Part C: prerequisites](#prereqs)
- [Part D: rules](#rules)
- [Part E: the play log](#play-log)
- [Findings](#findings)
- [Proving it works](#validation)
- [Phases](#phases)
- [What was built (phases 1 and 2)](#built)
- [Converter fixes](#fixes)
- [What it will not see](#limits)

## <a id="gap"></a>Why the current audits miss it

The game plays the same on both sides when four things match:

| Part | Question | Covered by |
|---|---|---|
| Guards | Do the same facts let each line, option and stage setter run? | [Condition differential](fo4_preflight.md#condition-diff) (built, 0 findings); [menu audit](fo4_menu_audit.md) (planned) |
| Starting state | Does each fact start at the same value in a new game? | This plan, [part A](#start) |
| Writers | Does each fact change at the same event, under the same test, and nowhere else? | This plan, [part B](#writers) |
| Rules | Does the engine turn facts into play the same way? | Menu audit [rules](fo4_menu_audit.md#rules); this plan, [part D](#rules) |

The condition differential proves that the same facts give the same answer.
It takes the facts as given: a topic's `TES4Unlock_` global counts as true,
and "quest running" is one fact on both sides. The quest audit proves that
each stage FNV reaches has a setter in the build. But it accepts a line's
setter in either half of the line and a script's setter in any event, and it
reads only SetStage and StartQuest. So a fact written at a different moment,
or a "topic known" rule that differs from FNV's, passes every audit built so
far. "Dialogue unlocking too soon" is mostly this: a line's own conditions
match, but the topic it belongs to becomes known earlier.

## <a id="measured"></a>What the first measurements found

Each probe ran in under 5 seconds on the FNV export and the built plugin.
The scripts are one-offs (scratchpad), not tools.

| Probe | Result |
|---|---|
| **Topic known** | The build gets "topic known" from `tes5_import/dialogue/unlocks.py`, the Oblivion converter's unlock plan, unchanged (`fo4_import/spike/cell.py` `_hub`). FNV: 16,350 Topic-type topics, 2,281 Top-level. Build: 2,684 on the topic list, 366 gated by an unlock global. Four places where its rules are Oblivion's, not FNV's: **41** topics are Top-level in FNV (listed from the start) but gated in the build, so they may show **late**. **76** topics that only greetings add are left ungated ("bark ungating"), so they may show **early**. In **99** topics (448 lines), choosing the topic as a Choice unlocks it for good, which FNV may not do ([rule 1](#rules)). **13** unlocks on 6 stages come from "a line that reveals the topic also sets this stage". Mention reveals (Oblivion's topic-name links): 0 in FNV. |
| **Topic known, by prerequisites** | Judged on [prerequisites](#prereqs) only, 117 mismatches come down to 6. **Early (3, confirmed in both plugins):** the Freeside vagrant's three VMS49 topics ("I'm looking for someone carrying an antique gun." and two variants). FNV adds them only through his greeting, which requires VMS49 objective 50 displayed. The topics' own lines test only "objective 50 not completed", true from a new game. The built option (`5C43AA`) tests that, the speaker, and that `FNV_VFreeformFreeside` runs, so he offers it from the first talk. **Late (3, not yet checked by hand):** Regis's "What's your opinion of the NCR?" (its revealers need VMQ05 objective 20 or VMS45 objective 55 displayed); Mortimer's "Did you succeed in turning the White Glove Society back to cannibalism?" (VMS18 objective 180 completed); Ignacio's "The NCR asked me to help increase the plant's power output." (revealed only by a derived stage reveal on vDialogueEDE stage 10). |
| **Line halves** | All 1,053 SetStage and StartQuest sites in FNV line scripts land in the same half in the build (begin script → `Fragment_1`, end script → `Fragment_0`). Clean. |
| **Script blocks** | 3,871 FNV `Begin` blocks: 3,832 have a handler, 18 are kept as comments (MenuMode), 21 are dropped with no trace. 17 of the 21 are empty or a plain `Activate` pass-through, which is correct since Fallout 4 activates by default. **4 lose code.** Three are `OnFire`, for which the converter has no handler: `EuclidsCFinderSCRIPT` (starts `VEuclidQuest`, so the Archimedes II strike never comes), `VMS15LoyalDetonatorFireScript` (activates the ballast deployer in "Volare!"; it builds as an empty script) and `DetonatorOnFire` (damages the Hoover Dam generators). The fourth is `VLegateScript`'s `OnActorEquip`. |
| **Stage setters by block** | MenuMode stage sets: 17 run on the message box closing, 3 on the menu event, 6 on the game-mode timer (FNV runs MenuMode only while a menu is open), and 4 CGTutorial ones are comments only. Every other block kind maps to one Fallout 4 event. |
| **Waits counted in frames** | Only 2 object scripts that set stages count GameMode passes, both under 10. Quest scripts keep FNV's quest delay. Negligible. |
| **Quest start** | FNV's Start Game Enabled flag is kept on every quest except VCG00, VCG01 and CGTutorial, which are started by hand. 165 required forced aliases (in 60 quests, 21 of them start-game) target initially disabled references, and none carries Allow Disabled. Vanilla sets it on 73 of its 89, and the CK wiki says the flag "allows the alias to be filled with a disabled reference". Settled by play: VCG02 started at stage 5 on 2026-10-29 with three such aliases, so a forced alias fills anyway. Not a finding. |

## <a id="design"></a>How it works

The audit uses the condition differential's vocabulary: facts are quest
stages, objectives, quest running, quest variables, globals, factions, items
and death, paired between the plugins by EditorID, kept FormID or authored
mirror-global names. It adds two conversation facts, *topic known* and *line
said*. Nothing goes through the converter's own tables, so a converter
mistake cannot hide in a shared model.

Each fact is checked three ways: its value at a new game ([A](#start)),
every place that writes it ([B](#writers)), and what must already be true
before it can change ([C](#prereqs)). [D](#rules) lists the engine rules the
three rest on. [E](#play-log) checks the order of real writes in play.

Code: `tools/validate/preflight/timing.py` (with a `timing_writers.py` for
part B if it grows), run as `--audit timing` in the preflight runner. It
reuses `quest_source.py` and `quest_converted.py` (setters),
`condition_diff.py` (names, mirror globals, the evaluator) and
`fo4_dialogue.py` (which built lines play).

## <a id="start"></a>Part A: starting state

For each fact, its value in a new FNV game against the build's:

| Fact | FNV | Build |
|---|---|---|
| Quest running | QUST `DATA` Start Game Enabled | QUST `DNAM` flag, or started by `F3NV_NewGame` |
| Topic known | Top-level (`DATA` flag 0x02) | No unlock gate on its options |
| Global | GLOB value | GLOB value (kept, or its mirror) |
| Quest variable | 0 | Its `TES4QVar_` mirror's value, or the property's default |
| Objective shown or done | No | `TES4ObjShown_`/`TES4ObjDone_` at 0 |
| Line said | No | Say Once marker stage not done |

A difference is a finding, unless it is on the hand-started list with its
starter named. The 41 gated Top-level topics are part A's first result. Run
time is seconds.

## <a id="writers"></a>Part B: writers

Every write in either plugin becomes a row: (fact, value, trigger, guard).

- **FNV writers:** stage result scripts; line begin and end scripts; a
  line's Add Topics list; script blocks by `Begin` kind; package begin, end
  and change scripts; terminal menu items; effect scripts. The commands:
  SetStage, StartQuest, StopQuest, CompleteQuest, AddTopic,
  SetObjectiveDisplayed and SetObjectiveCompleted, `set` on quest variables
  and globals, and the item, faction and kill commands the vocabulary reads.
- **Build writers:** the converted fragments and events, plus the build's own
  state (unlock globals and the stages that set them, mirror globals, Say
  Once marks, Follow Up marks, `F3NV_*` static scripts).
- **Triggers** pair by a table (FNV `Begin GameMode` → the converted poll's
  `OnTimer`, `OnAdd` → `OnContainerChanged`, and so on). Each pair is
  confirmed by a census over the whole build, as in
  [the block probe](#measured), and never assumed.

Findings:

| Kind | Example |
|---|---|
| Writer missing | An FNV write with no build write of the same fact and value. The quest audit already does this for stages; this extends it to every fact |
| Writer moved | Same write on a different trigger: the other half of a line, MenuMode on the game-mode timer, a stage fragment instead of the line |
| Writer extra | The build writes a fact where FNV does not: Choice reveals, derived stage reveals, a static script's write |
| Block dropped | An FNV block with code and no handler or comment in the build (`OnFire` ×3) |
| Guard differs | The `if` tests on the path to a write differ between the two scripts |

Guards come last ([phase 4](#phases)). They need a reader for the `if` chain
above each write on both sides (FNV script text, converted Papyrus), turned
into the vocabulary's facts and compared with the condition differential's
evaluator over every combination of the few facts each guard holds. Only the
`if` tests are read, not whole scripts.

## <a id="prereqs"></a>Part C: prerequisites

This part answers "too soon" and "too late" directly. Some facts, once true,
stay true: a stage reached or done, an objective shown or completed, an actor
dead, a quest completed. These are *prerequisites*. For every unlock (a topic
becomes known, an option can show, a quest starts, an objective shows, a
stage is set), each side has a set of prerequisites that must already hold:

- an event needs the prerequisites its own required conditions test (outside
  OR chains), plus those of where it runs (a stage fragment needs its stage;
  a line needs its conditions; a script block needs its guard);
- a fact needs what *every* writer of it needs: the intersection over its
  writers, since any one of them is enough;
- "stage ≥ 50" covers "stage ≥ 30" on the same quest;
- a fixed point carries prerequisites along the quest audit's stage graph, so
  stage 30, set only by a line that needs stage 20, needs stage 20 too.

A prerequisite FNV has and the build lacks means the unlock *can happen too
soon*. One the build has and FNV lacks means *too late*, or stuck if it is
never met. Facts that change both ways (variables, "not met yet" flags) are
not prerequisites. They are left to the guard comparison, which removes the
noise they cause: the first comparison over all conditions flagged 75 of the
117 topic mismatches, mostly first-meeting greetings that test "not met
yet", and only 6 remained on prerequisites.

The intersection matters. The first version took the union across a topic's
revealers and flagged 12, among them FollowersFired: many companion lines
reveal it, and no prerequisite is common to all of them.

## <a id="rules"></a>Part D: rules

Each rule is settled from the exe, the data or a play log, as the menu
audit's [rules](fo4_menu_audit.md#rules) are, and gets a fixture.

| # | Rule | Why it matters | Settle from |
|---|---|---|---|
| 1 | Does a Choice make its topic known in FNV, so it stays on the topic list? | The build says yes for 99 topics (448 lines) | `FalloutNV.exe`, the `DialogMenu` code after a line (menu audit) |
| 2 | Is a Top-level topic listed without AddTopic? | 41 gated Top-level topics | GECK wording says yes; confirm in the same exe code |
| 3 | FNV runs result scripts inside the engine, at once. Fallout 4 queues fragments in Papyrus. Does a line's end fragment land before the next menu, greeting or condition reads the fact? | Every write the next menu depends on | The [play log](#play-log), with menu audit check 5 |
| 4 | SetStage on a stopped or completed quest; a stage set twice; StopQuest | Fallout 4 clears a stopped quest's aliases; FNV keeps the quest's state | `Fallout4.exe`, `FalloutNV.exe`, then a census of FNV's StopQuest use |
| 5 | MenuMode on the game-mode timer | 6 stage sets run outside menus | The 6 scripts read by hand |
| 6 | A forced alias on a disabled reference fills | 165 aliases | **Settled 2026-10-29** by the VCG02 log |
| 7 | Poll cadence: FNV GameMode every frame, the build 0.5 s for objects, the quest delay for quests | Waits counted in passes | **Settled 2026-10-29**: 2 scripts, under 10 passes |

## <a id="play-log"></a>Part E: the play log

`fo4_trace` already logs every converted stage set, line begin and end, and
mirror-global write, with timestamps. After a session, a replay checks the
logged writes against part C: a stage set, topic unlocked or quest started
while one of its FNV prerequisites is still false is a finding, and so is a
write that lands after a menu that needed it ([rule 3](#rules)). This is the
only part that sees timing no record shows. It costs no extra game time and
shares its log points with the [menu audit's check 5](fo4_menu_audit.md#play-log).

## <a id="findings"></a>Findings

Keys: `timing|<plugin>|<fact>|<kind>`, with the trigger and the state in the
detail, for example `topic VFreeformFreesideVMS49VagrantTopic000 known |
too-soon | FNV needs objective VMS49 50 shown (greeting 0014E7C7); the build
needs nothing`.

| Kind | Part | Severity |
|---|---|---|
| Starting value differs | A | error |
| Writer missing, moved, or block dropped with code | B | error |
| Writer extra | B | error; review when it rests on an open rule (Choice reveals) |
| Guard differs | B | error; review when checked by sampling |
| Prerequisite missing (too soon) or extra (too late) | C | error for a prerequisite, review when it rests on an open rule |
| A logged write breaks a prerequisite or lands late | E | error |

## <a id="validation"></a>Proving it works

1. **The live bugs.** On today's build: the three VMS49 vagrant topics
   (part C), the three `OnFire` blocks (part B), and the 41 Top-level gates
   (part A) must be found.
2. **Mutations.** On agreeing data: drop an unlock gate, move a setter to the
   other half, delete a block, change a global's start value, remove a
   prerequisite from a greeting. Catch rate above 95%, as for the condition
   differential.
3. **Hand checks.** Each part's first findings read in both plugins before
   the part counts as working, as the VMS49 case was.

## <a id="phases"></a>Phases

| # | Work | Done when |
|---|---|---|
| 1 | Parts A and C for *topic known*, built from the probes | VMS49 found; Regis, Mortimer and Ignacio read by hand |
| 2 | Part B writers and triggers for every fact kind: extend `quest_source`/`quest_converted` past SetStage and StartQuest, add the build's own writers, and flag dropped blocks | `OnFire` ×3 found; a census per trigger pair |
| 3 | Part C over the whole stage graph (stages, objectives, quest starts) | First whole-map report |
| 4 | Part B guards | Mutation rate above 95% |
| 5 | Part D rules 1 to 4 | Each with its address or log line and a fixture |
| 6 | Part E replay, with menu audit phase 6 | One session replayed with no false findings |

Phases 1 and 2 are independent. The menu audit's
[check 4](fo4_menu_audit.md#effects) (each line's writes, half by half)
becomes part B's line rows, so it is built once, here.

## <a id="built"></a>What was built (phases 1 and 2)

```
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm" --audit timing
```

Code: `tools/validate/preflight/timing.py` (topic known, the findings),
`timing_writers.py` (both sides' writes, triggers, blocks),
`timing_prereqs.py` (prerequisites); tests in
`tests/test_preflight_timing.py`. About 60 s on the whole-map build, most of
it loading the plugin.

- **Topic known** is read from the build, not from the converter's unlock
  plan: a topic is listed when the ledger has a hub option for it
  (`INFO prompt <topic> ... menu hub`), gated when every such option requires
  a `TES4Unlock_` global at 1, and unlocked by any converted script that sets
  a property bound to that global to 1. A line script's needs come from its
  line's *first-response* copies: the end fragment also sits on the last
  response, which tests only the quest running but plays only after the
  first.
- **Writes** read on both sides: SetStage, StartQuest, StopQuest,
  CompleteQuest (and FNV's Complete Quest log flag), AddTopic (and Add
  Topics lists), SetObjectiveDisplayed, SetObjectiveCompleted. Not yet read:
  quest variables, globals, items, factions, Fail Quest.
- **Left to other audits:** a lost SetStage or StartQuest (quest audit), a
  line the build did not write (quest and dialogue audits), an AddTopic of a
  topic the build never gates, a line adding its own topic.
- **Not findings:** the build's "objective = stage" display and sweep for an
  objective the FNV quest never authors (a no-op in Fallout 4); a MenuMode
  block folded into the timer poll is kept, and each write it moved is a
  review ([rule 5](#rules)).
- **Severity:** a topic finding that rests on a Choice unlock, and every
  Choice or derived-stage unlock, is a review until [rule 1](#rules) is
  settled.

First run (whole-map build of 2026-10-29 17:55): 8,039 FNV writes, 8,131 build
writes, 345 gated topics. Findings:

| Kind | Count | What |
|---|---|---|
| Too soon | 3 + 1 review | The three VMS49 vagrant topics; Ramos's "HELIOS" story (review: one unlock is a Choice) |
| Too late | 2 | Regis's "What's your opinion of the NCR?", Mortimer's VMS18 topic (Top-level in FNV, gated in the build) |
| Complete Quest lost | 3 | VMS38 stage 130, VMS22 stage 90, VES34Vault stage 60: entries with only the Complete Quest flag. `script_convert/quest_fragments.py` `stage_fragments` keeps an entry only with text or a script, so the flag is dropped |
| Block dropped | 4 | `OnFire` ×3 (C-Finder, Volare's detonator, the dam generators), `VLegateScript` OnActorEquip |
| Moved (review) | 3 | MenuMode stage sets on the game-mode poll: VEFR01NCRGood2EmergencyRadio 10, VCG00 0, CG00 0 |
| Extra unlocks (review) | 101 topics | 89 Choice unlocks, the rest derived stage reveals |

Audit mistakes found and fixed on the way, each by reading the records: an
operator-precedence slip that read no gate; MenuMode folded into the poll
counted as dropped; a line's end fragment on its last response making four
topics look early (Marjorie ×2, Manny Vargas, Ramos, before the Choice);
FNV's Complete Quest flag not read as a write (115 false extras); "objective
= stage" writes for objectives FNV never authors.

## <a id="fixes"></a>Converter fixes

Made 2026-10-29 (tests in `tests/test_fo4_timing_fixes.py`). Checked on a
whole-map build of 2026-10-29 22:54 (`temp/profile_data`, built by another
session with these changes): `--audit timing` 0 errors and 88 to review (was
12 and 105), 0 FormIDs moved, 41 records removed, all of them the Top-level
topics' `TES4Unlock_` globals. Not deployed or played.

- **Complete Quest flag** (`script_convert/quest_fragments.py`
  `log_entry_has_fragment`, shared with the importer's
  `quest_stage_fragments`): a stage log entry whose only content is the flag
  now gets a fragment that completes the quest. FNV: VMS38 130, VMS22 90,
  VES34Vault 60.
- **Greeting reveals** (`tes5_import/dialogue/unlock_prerequisites_falloutnv.py`,
  used by `unlocks.py`): on an FO3/FNV source, a topic only greetings add
  stays gated when every revealing greeting needs a stage or objective
  (reached, done, shown, completed) that some line of the topic does not.
  FNV: the three VMS49 vagrant topics.
- **Top-level topics:** an FO3/FNV topic with the Top-level flag is never
  gated ([rule 2](#rules), from the GECK's wording). FNV 41, FO3 13. Unlock
  plan on FNV: 366 gated topics to 328, 1,455 revealing lines to 1,273; FO3
  46 to 33. Oblivion is unchanged (its DIALs carry no flags): 535 gated
  before and after.
- **`OnFire`** (`script_convert/blocks.py` `FALLOUT4_BLOCK_MAP`,
  `assemble._listen_for_fire`): Fallout 4's `OnPlayerFireWeapon` fires only
  out of combat and on a timer (CK wiki), so the block runs in
  `OnAnimationEvent` behind `asEventName == "weaponFire"`, registered on
  the wielder in `OnEquipped` and dropped in `OnUnequipped`. Volare's
  detonator and the dam generators' detonator now run. **Euclid's C-Finder
  still does not:** its body needs `PlaceAtReticle`, which the converter
  leaves inert, so `bTargeted` stays 0 and `VEuclidQuest` never starts.
- **`OnActorEquip` on an actor** becomes `OnItemEquipped` (filtered on
  `akBaseObject`); the shared table's `OnEquipped` fires only on the
  item. The Skyrim target has the same mistake (it should be
  `OnObjectEquipped`) and is left unchanged here.

Not made: dropped blocks still leave no comment, and Choice reveals wait on
[rule 1](#rules).

## <a id="limits"></a>What it will not see

- Whether the story can reach a finding's state; a prerequisite gap is a
  state the data allows.
- Writes through commands the readers do not parse, on either side.
- Facts outside the vocabulary (actor values, script variables by index,
  packages, regions), as in the condition differential.
- Engine timing not covered by a rule question or reached in play.
