# Plan: dialogue reachability

How to find, sort and fix every place where a New Vegas line or option
cannot be reached in the Fallout 4 build. This is design only, not
permission to build. Status lives in [ROADMAP](ROADMAP.md) only.

## Contents

- [Goal and rows](#goal)
- [What exists](#exists)
- [The framework](#framework)
- [Phases](#phases)
- [What the play test should tell us first](#play-test)
- [Open questions](#open)

## <a id="goal"></a>Goal and rows

Every dialogue gap the build leaves gets one cause from a short, fixed list,
and the fixes go in batches by cause, not line by line. The tool that sorts
them is the [dialogue menu audit](fo4_menu_audit.md), built out so that
"why can't the player reach this?" is one report.

Rows of the [issue plan](fo4_issue_plan.md#medium) this covers:

| Row | Size | Doc |
|---|---|---|
| Follower talk options missing ("Let's go", "Keep close", firing) | M | [conditions](fo4_pipeline.md#dialogue-conditions) |
| Choices with no line (236), and 62 Choice topics unanswered | M | [shared infos](fo4_pipeline.md#shared-infos) |
| Dialogue lines left out (~350; 163 for actors FNV never places) | M | [conditions](fo4_pipeline.md#dialogue-conditions) |
| Companion status barks (91) | M | [barks](fo4_pipeline.md#companion-barks) |
| Build checks: menu audit phase 2, timing audit phases 3 to 6 | M | [menu](fo4_menu_audit.md#phases), [timing](fo4_timing_audit.md#phases) |

The counts come from the [dev log](dev_log.md) and the ROADMAP. The 62 is
what was left of 1,686 unanswered Choice topics after shared infos answered
1,624 ([shared infos](fo4_pipeline.md#shared-infos)).

## <a id="exists"></a>What exists

**Where gaps are made** (`fo4_import/spike/`):

- `conversation.py` `Conversations._option`: one option per (prompt, FNV
  quest) of a topic. When no option of a topic converts, it adds a
  `CHOICE_UNANSWERED` readiness entry whose detail is only the topic's
  EditorID and FormID. It does not say why.
- `conversation.py` `Conversations._sayable`: with the menu's speakers
  (`menu_speakers`), it keeps only lines one of them can say by fixed facts
  (`_can_say` → `speaker_facts`: GetIsID, voice type, factions no script
  changes). The lines it drops are counted as one build total
  (`menu lines no speaker of the menu can say`), not per menu
  ([menu speakers](fo4_pipeline.md#menu-speakers)).
- `conversation.py` `Conversations._prompt` returns False when none of an
  option's answers converts (`_line` gives b'').
- `say_topics.py` `SayTopics.info`: a line whose condition cannot convert is
  a `LINE_LEFT_OUT` entry, with `blocker()`'s reason in the detail.
- `readiness.py` `Readiness`: the entry kinds (`LINE`, `LINE_LEFT_OUT`,
  `CHOICE_UNANSWERED`, `TARGET_NOT_BUILT`, `PACKAGE_LEFT_OUT`), written to
  `temp/fo4_readiness/<plugin>.json` ([readiness](fo4_pipeline.md#readiness)).
- `companion_barks.py` `write`: the watch quest for `STATUS_BARKS`
  (`HealthHalf`, `HealthQuarter`, `Wake`, `NoAmmo`), said by
  `script_convert/static_scripts/fallout4/F3NV_CompanionBarks.psc`
  (`OnTimer` over `Game.GetPlayerFollowers()`, then `Check`, `HealthBand`,
  `OutOfAmmo`, `Bark`).
- `dialogue_trace.py`: every prompt, pad and `[Leave]` carries
  `F3NV_TraceTopicInfo`, so the trace logs the option the player *chose*,
  not the options shown ([dialogue trace](fo4_pipeline.md#dialogue-trace)).

**Where gaps are read** (`tools/validate/`):

- `fo4_quest_readiness.py` `findings`: joins the readiness entries with
  unfilled script properties, by quest. It prints per quest, not per cause.
- `preflight/fo4_dialogue.py` `left_out`: reads the `LINE_LEFT_OUT`
  entries as the reason a line has no copy.
- `preflight/dialogue_loss.py` `lost_lines`, `_source_says`: a line counts
  as lost only when FNV can say it (`quest_source.speakable` against placed
  actors). So the preflight already leaves out the 163 lines for actors FNV
  never places; the readiness count does not.
- `preflight/xdi_menus.py` `audit`: menus that can open with no option
  ("dialogueentry"), from XDI's own rules
  ([XDI menus](../commentary/tools_preflight.md#xdi-menus)).
- `preflight/condition_diff.py`: the line-by-line differential. Its
  `UNPAIRED` set still lists GetActorValue, GetReputation,
  GetReputationThreshold and GetHasNote, so the menu audit's
  [step 0](fo4_menu_audit.md#vocabulary) (its phase 1) is not in the code.
- `preflight/timing.py`, `timing_writers.py`, `timing_prereqs.py`: timing
  phases 1 and 2 ([built](fo4_timing_audit.md#built)). `timing.py` already
  reads hub options from the ledger (`_HUB_OPTION`, keys
  `INFO prompt <topic> ... menu hub ...`).
- `preflight/__main__.py`: `AUDITS` and `RUNNERS`, where a `menus` audit
  would register. No `menus.py` exists yet.
- `fo4_trace.py`: the play-session log reader the replay phases build on.

**Elsewhere:** the casino session converts `GetCasinoWinningStage` to its
level global ([casino phase 1](fo4_casino_plan.md#phase-1)), and
`F3NV.dll` already gives Papyrus `F3NV_Condition.GetHealth`, `SetHealth`
and `GetEquippedWeaponHealth`, with wear on the player only
([condition](fo4_condition.md#built)).

## <a id="framework"></a>The framework

**One gap report, sorted by cause.** Each gap (a line with no copy, a Choice
with no option, a follower option missing from a menu, a status bark not
said) gets exactly one cause:

| Cause | Meaning | Fixed by |
|---|---|---|
| `source-dead` | FNV never says it either (no placed speaker, a condition FNV never passes) | Nothing: drop from the count |
| `speaker-filter` | `_sayable` dropped every line for this menu's speakers | The filter or the speaker facts |
| `condition:<function>` | A condition did not convert (`blocker()`'s reason) | That function's conversion, once for all its lines |
| `no-state` | Fallout 4 tracks no matching fact (GetDisposition, a bark's state) | A Papyrus stand-in, or recorded drift |
| `not-built` | The quest, scene or speaker is not in the build | Quest scope or the waiting session (casino) |
| `menu-rule` | Every line converts, but the menu built from them is wrong (menu audit checks 1 to 3) | `Conversations` (`_option`, `_earlier`, `_either`) |

The build already knows the cause at the moment it drops something, so it
writes it in the readiness detail. The menu audit reads the readiness
report and the two plugins' records, adds `source-dead` and `menu-rule` from
its own checks, and prints counts per cause plus a few examples each. A
fix batch is then "every `condition:GetIsClass` line", and its check is that
cause's count going to zero.

Why this covers the rows: the follower options, the 236 choices and the
62 topics are all `CHOICE_UNANSWERED` or `menu-rule` findings; the ~350
lines are `LINE_LEFT_OUT` with a reason; the 91 barks are `no-state`; and
menu audit phase 2 and timing phases 3 to 6 are the checks that find the
`menu-rule` and too-soon/too-late gaps. It extends tools that exist
(readiness, `fo4_quest_readiness.py`, the preflight), as the
[tools-first rule](../../CLAUDE.md#tools-first) asks.

Every fix uses records or Papyrus. Two items could reach for the DLL:

### <a id="dll"></a>DLL decisions

| Candidate | What it would do | Alternative without a new DLL feature |
|---|---|---|
| Log the options an XDI menu shows (menu [check 5](fo4_menu_audit.md#play-log), timing [part E](fo4_timing_audit.md#play-log)) | Hook XDI's option list while `TES4Trace` is on | First read XDI's source for an event it sends to Papyrus. Otherwise rebuild the shown menu offline from the logged state with checks 1 to 3, and compare only the chosen option, which `F3NV_TraceTopicInfo` already logs |
| `WeaponBroke` for companions (17 lines) | Wear on followers' guns | Run the existing `F3NV_Condition` natives on the follower's gun from `F3NV_CompanionBarks` (unverified that `GetHealth`/`SetHealth` work on an NPC's inventory). If they don't, leave the 17 lines as drift |

Both need the user's approval before any DLL work starts.

## <a id="phases"></a>Phases

| # | Size | Delivers | Checked by | Depends on |
|---|---|---|---|---|
| 1 | S | The cause in each entry: `_option` writes why no option converted (`speaker-filter`, `condition`, none in the Hub), `_sayable` writes its drops per menu as entries, not a total. `fo4_quest_readiness.py` gains a by-cause summary, and tags `source-dead` lines with `quest_source.speakable` | A unit test per cause in the readiness tests; on the next build, the 236 and ~350 split with no `unknown` left | The play test (so its build is the baseline) |
| 2 | M | Follower options: the "Let's go", "Keep close" and firing copies in other quests' `VNPCFollowers` menus, diffed against a working copy with phase 1's causes. The fix goes where the cause points (`menu_speakers`, `_can_say`'s faction facts, or the (prompt, quest) key) | Readiness: 0 follower choices unanswered; in game: Cass and Boone each show all three | 1 |
| 3 | M | Menu audit phase 2: checks [1](fo4_menu_audit.md#structure) and [2](fo4_menu_audit.md#exclusion) as `preflight/menus.py`, `--audit menus`, ledger keys `menus|<plugin>|...`, with the cause summary as its first section. **Built 2026-11-08** ([menu audit, built](fo4_menu_audit.md#built)) without the cause summary, which waits for phase 1 | Jason Bright's and Doc Mitchell's pairs found on a build before 2026-10-26, none after; whole map under a minute. Met: 1,178 pair menus on the 2026-10-25 build, both pairs among them; 145 on 2026-11-08, neither; about a minute with the plugin read | 1 |
| 4 | M | Choices with no line, by cause: `speaker-filter` and `menu-rule` in `Conversations`; for the 62 topics, whether INFX order or a missing quest is the cause | `CHOICE_UNANSWERED` count per cause; the `menus` audit's check 1 findings | 1, 3 |
| 5 | M | Lines left out, by cause: `source-dead` (163) leaves the count; GetIsClass and GetDisposition get a rule each (see [open](#open)); the 86 casino lines (49 GetItemCount, 37 GetCasinoWinningStage) move to the casino session's list | `LINE_LEFT_OUT` per cause; the preflight `dialogue` audit's loss count | 1 |
| 6 | M | Status barks with a Papyrus stand-in in `F3NV_CompanionBarks`: `Poisoned`, `OnFire`, `UsedDoctorBag`; `WeaponBroke` per its [DLL decision](#dll). The rest (`WeaponIneffective`, `ArmorIneffective`, `Regenerating`, `Frenzy`, `KnockedBack`) recorded as drift unless a stand-in is found | A test of `companion_barks.write` with the new properties; in game: a poisoned or burning Cass barks | Play test result on the 77 built barks |
| 7 | M | Menu audit phases 1 and 4: step 0's pairs in `condition_diff.py`, then [check 3](fo4_menu_audit.md#gates) (hidden, empty, wrong-prompt options) | Nash and Torini mutations found; the count of gates past the exact limit | 3 |
| 8 | L | Timing phases 3 and 4: [part C](fo4_timing_audit.md#prereqs) over the whole stage graph, then [part B](fo4_timing_audit.md#writers) guards | First whole-map report; mutation catch rate above 95% | 3 |
| 9 | L | Rules: menu audit phase 3 and timing phase 5, from `FalloutNV.exe`, XDI's source and `Fallout4.exe` ([menu rules](fo4_menu_audit.md#rules), [timing rules](fo4_timing_audit.md#rules)). Rule 1 (does a Choice make its topic known) settles the 89 Choice-unlock reviews | Each rule with its address or source line and a fixture | Can run beside 3 to 8 |
| 10 | L | Replay: menu audit phase 6 and timing phase 6, on `fo4_trace` logs | One session replayed with no false findings | 9; the first [DLL decision](#dll) |

Phases 2, 4, 5 and 6 are the fix batches; each is re-run against phase 1's
counts. Phase 1 is the only one that must come first.

### <a id="done-1109"></a>2026-11-09 (not built)

Measured on the 2026-11-08 build (`temp/profile_data`) with the converter's
own functions over the export, no rebuild.

- **Phase 1, choices only.** `Conversations._unanswered` sorts a topic left
  with no option. FNV never answers it either when it has no line at all
  (`no line`) or none the menu's speakers can say (`speaker-filter`:
  `_can_say` drops only lines that can never pass for them): those become
  counts (`choice FNV never answers (...)`), not readiness entries. The rest
  are `CHOICE_UNANSWERED` entries ending in `: not built` (lines only in
  quests outside the build) or `: condition` (no line converts; see the
  lines' `LINE_LEFT_OUT` entries). `_sayable`'s per-menu entries and the
  readiness tool's by-cause summary are still to do.
- **Phase 2, followers: no menu cause.** The built menus hold every
  companion's "Let's get going.", "Wait here.", trade, tactics, firing and
  "Stay close to me." answers. The 15 follower entries were FNV-dead:
  `FollowersTacticsDistanceClose` ("Stick close to me.") has no line in
  FNV, and the firing Yes/No menu that failed is RL3Follower's (quest
  `Followers`, never placed), once per quest copy (5). "Let's get going."
  passes only while the companion's `Waiting` is 1 (FNV's own condition,
  set by "Wait here."), and ED-E's prompt is `<Follow Protocol::Reinitiate>`.
- **Phase 4.** Of 185 entries: 72 `no line`, about 62 to 73
  `speaker-filter` (mostly lines FNV authored with contradictory GetIsID
  tests, e.g. Fort Benny, Mr. House, "[PRESS DEMO]"), about 40 left
  (GetIsClass, GetItemCount, V22Bohr and RL3Follower lines, objective
  tests). Each counts once per quest that builds its own copy of the menu
  (Greetings, VFreeformBlackMountain, VDialogueRaul, VFreeformMcCarran and
  VFreeformFreeside each build the whole Hub, 1,964 options).
- **Repeated answers.** A topic listing its own line as a shared info no
  longer takes a copy of it (as `say_topics.borrowed_lines` already
  skipped): 109 copies leave the Hub; all 146 `answer repeated` menus of
  the 11-08 build were this case.

## <a id="play-test"></a>What the play test should tell us first

- **Followers.** Hire Cass and Boone and open each one's talk. Which of
  "Let's go", "Keep close" and firing show, and in which menu? If all three
  show in their own quest's menu and miss only in other quests' copies, it
  is a menu cause (phase 2 stays small). If one is missing everywhere, look
  at the line's condition first.
- **Empty menus.** Any "dialogueentry" option means a menu with no passing
  option ([XDI menus](../commentary/tools_preflight.md#xdi-menus)). Note the
  NPC and the line before it; it goes straight into phase 3's fixtures.
- **Doc Mitchell's 100-caps pair.** Played for Jason Bright only
  ([one option per topic](fo4_pipeline.md#one-option-per-topic)). Both
  showing at once moves `_earlier` fixes ahead of phase 4.
- **Shared answers.** Any Choice whose answer comes from another topic
  (shared infos, in the 2026-11-05 build, not played). A stall after picking
  one moves INFX order up in phase 4.
- **Companion barks.** Whether the 77 built barks are heard at all (low
  health, waking, no ammo). If none are, phase 6 starts by fixing the watch
  quest, not by adding barks.
- **Trace.** Whether the session's `fo4_trace` log has a `choice` row for
  every option picked. Phase 10 depends on it.

## <a id="open"></a>Open questions

- Follower options in other quests' `VNPCFollowers` copies: settled
  2026-11-09, FNV-dead, not a menu cause ([2026-11-09](#done-1109)).
  Whether FO4's own follower commands (wait from the command mode) leave
  FNV's `Waiting` at 0, hiding "Let's get going.", is for the play test.
- Five quests building their own copy of the whole Hub menu (1,964 options
  each) is not measured for plugin size or load time.
- The 62 unanswered topics: the shared-infos copy ignores INFX and follows
  the topic's own lines in file order. Whether that order or an unbuilt
  borrowing quest leaves them empty is not measured.
- GetIsClass: the dev log says the build writes no CLAS records. Whether to
  write FNV's classes, or settle the test from the speaker's base, is open.
- GetDisposition has no Fallout 4 function. A fixed value (FNV's default
  disposition) or drift; not measured how many lines each choice keeps.
- Lily's child-race tests and the player's own barks (GenericPlayer,
  grenade and mine barks) have no plan here. They may belong in drift.
- Whether FO4 exposes a poisoned or burning state to Papyrus through a magic
  effect keyword on converted effects is unverified; phase 6 depends on it.
- Whether XDI sends a menu's options to Papyrus (decides the first
  [DLL decision](#dll)).
- Menu audit step 0 (phase 1 of that plan) is not in `condition_diff.py`.
  The issue plan names phase 2 as next; this plan puts step 0 in phase 7,
  before check 3 needs it.
