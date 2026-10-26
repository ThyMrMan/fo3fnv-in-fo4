# Plan: the dialogue menu audit

**Status:** planned 2026-10-25, not built; revised the same day after an
audit of the plan: exact checks on the pieces the build adds, in place of
trying every state; a per-line effect check in place of conversation walks;
skill checks and reputation paired first; FO4's rules from XDI's source and
the exe; the play log built on `fo4_trace`. Status goes in
[ROADMAP.md](ROADMAP.md).

**Goal.** For any NPC and any game state, check that the player sees the same
dialogue options in the FO4 build as in FNV, with the same prompts, the same
answers behind them, and the same way out. Today a wrong menu is found only in
play-testing, and only when it is obviously wrong: an option that shows a
quest stage too early, or a topic that never unlocks, looks normal unless the
tester plays with a guide open.

The existing audits stop short of this
([fo4_preflight.md](fo4_preflight.md#running)): the quest and dialogue audits
ask whether a line can *ever* play, and the condition differential compares
one line's conditions with its FNV line's. Neither looks at a menu as a whole,
which is where most menu bugs come from: the build assembles each menu from
pieces (prompts, pads, gates, Say Once marks, unlock globals), and each piece
can be right on its own while the menu comes out wrong.

## Contents

- [What it catches](#catches)
- [Where the truth comes from](#sources)
- [How it works](#design)
- [What the build adds](#pieces)
- [Step 0: skill checks and reputation](#vocabulary)
- [Check 1: structure](#structure)
- [Check 2: one option per topic](#exclusion)
- [Check 3: option gates](#gates)
- [Check 4: effects](#effects)
- [The rules](#rules)
- [The FNV side](#fnv-side)
- [The FO4 side](#fo4-side)
- [Conversation facts](#state)
- [Check 5: menus logged in play](#play-log)
- [Findings](#findings)
- [Proving it works](#validation)
- [Phases](#phases)
- [Considered and left out](#left-out)
- [Open questions](#open)
- [What it will not see](#limits)

## <a id="catches"></a>What it catches

Bugs of each kind have already reached play-tests
([fo4_pipeline.md](fo4_pipeline.md#dialogue-conditions)), or are in the
current build's records:

| Kind | Example |
|---|---|
| Option shows with no answer that can play | Johnson Nash's "How can I bring rule of law back to Primm?" after Beagle's rescue; choosing it stalled the talk |
| Option shows too early | Tommy Torini's "Let's talk about the acts I recruited." as soon as the quest ran |
| Option shows on the wrong NPC | Doctor topics on every NPC before quest conditions were added |
| Blank or duplicate option | Cliff Briscoe's "dialogueentry" choice ([blank choices](fo4_pipeline.md#blank-choices)); "Goodbye." seven times ([tool audit #6](fo4_tool_audit.md#fix-first)) |
| Option stays after it should drop | Sunny's Say Once topic in a second menu ([say once](fo4_pipeline.md#say-once)) |
| One FNV topic shown as two options | Found in the records 2026-10-25, fixed 2026-10-26, Jason Bright's pair played ([one option per topic](fo4_pipeline.md#one-option-per-topic)): Jason Bright offers "Sorry. Not interested." and "Like I said, not interested." together before the first is said; Doc Mitchell offers "Okay, fix me. Here's 100 caps." beside "Sorry, I don't have 100 caps." to a player holding 100 caps ([check 2](#exclusion)) |

Plus kinds no play-test has caught yet, because they look normal:

- a topic AddTopic should unlock that never shows, or one that shows first;
- the wrong answer behind an option (a later line answering where FNV plays
  an earlier one: line order, quest priority, padding off by one);
- a Choices menu offering the wrong topics, or `[Leave]` where FNV keeps the
  player in (or missing where FNV lets them go);
- a conversation that ends where FNV's continues, or returns to the topic list
  where FNV's ends;
- a skill, SPECIAL, karma or reputation variant shown in the wrong state.

## <a id="sources"></a>Where the truth comes from

A menu bug comes from one of three places, and each has its own trusted
source:

| Cause | Example | Trusted source |
|---|---|---|
| **Translation:** a condition, flag, choice, priority or unlock lost or changed on the way to FO4 | An option's "some answer passes" test missing | The FNV records themselves (`export/FalloutNV.esm`), compared against the built records |
| **FNV's rules:** how FNV builds a menu from its records | Order across quests, which line wins, Say Once per actor | The FNV engine: `FalloutNV.exe` (GOG, DRM-free), read by disassembly |
| **FO4's rules:** how XDI and Fallout 4 play the built records | Which INFO of a range shows, when a Say Once mark lands | XDI's source (`reg2k/xdi`), `Fallout4.exe.unpacked.exe`, then the [play log](#play-log) |

Sources checked and ruled out (2026-10-25), because each re-reads the same
records with the conditions dropped or unevaluated, or has no game logic:

- **Wiki dialogue files.** The Fandom dump (`references/FalloutWiki`, 526 FNV
  and 428 FO3 pages) and fallout.wiki (a copy) list topic, prompt, emotion and
  line text only. They come from the GECK's Export Dialogue, which keeps only
  seven speaker tests (GetInFaction, GetFactionRank, IsChild, GetIsClass,
  GetIsRace, GetIsSex, IsInList) and no quest state.
- **The GECK.** The Topics tab writes exactly the INFO fields the export
  already holds (`CTDA`, `DATA` flags, `TCLT`, `TCLF`, `NAME`, result scripts).
  Its Dialogue Tree tab displays conditions but evaluates none, and the NV
  GECK has no game logic.
- **xEdit and scripts on it** (e.g. new-vegas-papyri, a text-only CSV). These
  read the same records. xEdit's FNV definitions are still a useful second
  opinion on how we decode condition functions.
- **The console.** `PrintNPCDialog` (`pdialog`, opcode 0x158) is a stub in the
  retail exe: its handler `0x5b5d20` calls `0x483710`, an empty function. No
  other console command lists dialogue. `ResetDialogueFlags` (`rdf`) clears
  Say Once and Talked To PC.
- **The Prima guide** covers walkthrough steps and 127 `[Speech]` checks, not
  full menus. It is a hint for which story points matter, never a reference.

So translation is checked record against record, and the short list of rules
is settled from XDI's source and the two exes ([rules](#rules)). None of it
needs FNV running.

## <a id="design"></a>How it works

The condition differential already proves each built line passes exactly when
its FNV line does: 88,811 built copies judged on the whole-map build, 0
findings (2026-10-25). It treats the build's own state (unlock globals, Follow
Up marks, Say Once marks) as true, and leaves out lines it cannot pair. So the
menu audit does not re-prove lines. It checks what the differential leaves
out: the pieces the build adds to turn lines into menus ([below](#pieces)),
and the lines it cannot pair yet ([step 0](#vocabulary)).

Every check reads the two plugins' records directly, with the differential's
vocabulary (its condition evaluator, form identities and mirror-global
mapping), so a condition means the same thing on both sides, and no check
reads the converter's own tables.

| Check | Asks | Needs a state? | Run time |
|---|---|---|---|
| 0. [Skill checks and reputation](#vocabulary) | The ~2,300 FNV lines the differential skips pass when their copies do | Its sampled states | Inside the conditions audit |
| 1. [Structure](#structure) | Same lines in the same order, same edges, same prompts and flags | No | Seconds |
| 2. [One option per topic](#exclusion) | No two options of one FNV topic show at once | A few facts per pair | About 10 s over all of FNV |
| 3. [Option gates](#gates) | Each option shows exactly when FNV shows that entry | The option's own facts, every combination | Under a minute (to measure) |
| 4. [Effects](#effects) | Each copy writes what its FNV line writes, in the same half | No | Seconds |
| 5. [Menus logged in play](#play-log) | What XDI and Fallout 4 really showed and played | Logged | None: rides along with normal play |

Checks 1 to 3 together decide a menu without trying every state. The reason,
for every place the game picks the first passing line (the greeting, a Follow
Up step, the answer behind an option): if both sides try equivalent lines in
the same order, the same line wins in every state. The differential proves
the lines equivalent; check 1 proves the order; checks 2 and 3 cover the gates
the build adds. Only those gates are evaluated, and each is small.

## <a id="pieces"></a>What the build adds

Each piece stands in for an FNV rule; each is where a menu can go wrong while
its lines stay right (`fo4_import/spike/conversation.py` unless named):

| Piece | Code | Stands in for |
|---|---|---|
| One option per (prompt, quest) of a topic | `Conversations._option` | FNV shows a topic once, with the first passing line's prompt |
| Each option hidden while a line FNV tries first passes, at most 16 OR-groups | `_earlier`, `_unless`, `_together` | The same: one entry per topic |
| An option's gate: the groups its lines share, "some answer passes" (spread into at most 16 OR-groups, past that `one_each`), its speakers, its quest running | `_prompt`, `_shared`, `_either`, `_speakers`, `_running` | The topic shows while some line passes for this speaker |
| Pads: one empty player INFO per further answer, on the prompt's conditions | `_prompt` | The answers behind one entry, first passing wins |
| Unlock global `TES4Unlock_<topic>`, set by the AddTopic line's converted fragment | `_gate`, `attach.py` | AddTopic |
| Say Once marker stage on `FNV_TES4SayOnce`, set by `F3NV_SayOnce`'s OnBegin | `say_once.py` | Say Once |
| Follow Up marks `TES4FollowUpFrom_`/`TES4FollowUpSaid_` | `attach.py` | Follow Ups |
| Random chains (`GetRandomPercent < 100/remaining`, FO4's Random flag off) | `dialogue.py` | Random piles |
| `[Leave]`, and Prevent Player Exit on Choices menus that can end | `_leaves` | Tab |
| Greeting scene order: FNV quest priority, then Hub order | `_greetings` | Which GREETING line plays |
| Hub order: each quest's lines merged by position | `_members` | Line order across quests |
| TSCE to the next scene, End Running Scene, back to the topic list | `_line`, `_next` | Choices, Follow Ups, Goodbye |

The spike's generator (`dialogue.py`) gave each later prompt of a topic "no
earlier option could be chosen" (`exclusivity`); the whole-map path lost it,
which is the two-options bug in the table [above](#catches), and got it back
as `_earlier` on 2026-10-26
([one option per topic](fo4_pipeline.md#one-option-per-topic)). GOODBYE's
options hit the 16-group cap, so some still show beside another.

## <a id="vocabulary"></a>Step 0: skill checks and reputation

Of FNV's 23,247 lines, 2,664 hold a function the differential cannot pair
(`condition_diff.UNPAIRED`); the latest conditions run left 2,263 FNV lines
and 4,989 copies unjudged, these functions among the reasons. Lines holding
each:

| Function | Lines |
|---|---|
| GetReputationThreshold | 1,142 |
| GetActorValue | 1,136 |
| GetScriptVariable | 333 |
| GetHasNote | 46 |
| GetReputation | 12 |
| Packages, regions, sitting, GetPermanentActorValue | 20 |

The actor-value conditions are mostly skill and SPECIAL checks: Speech 540,
Barter 209, Medicine 63, Science 52, Karma 42, Intelligence 42, Explosives
29, Charisma 27. These are FNV's most visible dialogue gates, so the
vocabulary pairs them before any menu check:

- **Actor values** by name: FNV's index names the value (xEdit's
  `wbActorValueEnum`, as `conditions.fnv_av_name` reads it); the FO4 side's
  `GetValue` names an AVIF by EditorID, `FNV_<Skill>` in
  `FalloutHelpers.esl` or Fallout 4's own SPECIAL. Both are master forms, so
  the pairing reads the masters' AVIF EditorIDs, which `Names.built_form`
  marks unjudged today.
- **Karma**: FNV's Karma actor value pairs with the `TES4Karma` global
  ([karma](fo4_pipeline.md#karma-page)).
- **Reputation** by name: each faction's values are globals
  `TES4Rep<slot>_<REPU EditorID>` ([reputation](fo4_pipeline.md#reputation)).
  GetReputation's second parameter picks fame (1) or infamy (0) (GECK wiki,
  `GetReputation`). GetReputationThreshold's meaning is not in the offline
  wiki, so it is settled from the exe with the other [rules](#rules), never
  from the converter's slot table.
- **GetHasNote** pairs with GetItemCount of the note on the player, as the
  build converts it ([dialogue conditions](fo4_pipeline.md#dialogue-conditions)).

Script variables by index, packages and regions stay unpaired
([limits](#limits)). The conditions audit gains these pairs too, so its
findings on the ~2,300 lines come first.

## <a id="structure"></a>Check 1: structure

No state. For each built menu and step, against its FNV source:

- **Lines and order.** Each pick (the greeting scene, a Follow Up step, an
  option's answer range) holds copies of the same FNV lines in FNV's order
  ([FNV rule 5](#fnv-side)); none missing, none extra.
- **Edges.** A line's Choices: its copy's TSCE starts a scene whose menu lists
  exactly those topics (Link From, `TCLF`, counts as a Choice of the linked
  line). Follow Ups: the next phase or scene plays them. Goodbye: End Running
  Scene. Neither: back to the topic list.
- **Topic list.** Every top-level or added topic of the cell quests is on the
  topic list; an added one carries its unlock gate, a top-level one none.
  Order is compared once FNV's rule is known ([open](#open)).
- **Prompts.** An option's text is its line's prompt, else the topic's name;
  a pad carries its prompt's conditions, so it can never pass while its prompt
  fails (Cliff Briscoe's blank choice); no prompt appears twice in a menu
  unless check 2 clears it.
- **Flags.** A Say Once line's copies carry the marker; a Random pile's
  copies carry a chain of the pile's length; `[Leave]` sits on the topic list
  and on a Choices menu that can never end, and nowhere else.

## <a id="exclusion"></a>Check 2: one option per topic

FNV shows a topic once, with the first passing line's prompt. The build makes
one option per (prompt, quest), so two options of one topic in one menu must
never pass together. For each such pair the check looks for a state where both
options' gates pass; each pair holds a handful of facts, so every combination
is tried. A state found is a finding, printed as that state. Nothing being
said yet is a state of its own: the Say Once marker is a fact here, which is
how Jason Bright's pair shows (his first prompt is Say Once).

Measured on FNV's records (2026-10-25, a pass over every topic's lines in
about 10 s, conditions only, quest variables free): 167 topics have two
prompts for the same named speaker that can pass together, and 11 the same
prompt in two quests. The build's records hold both of the examples in
[what it catches](#catches) in one menu
(`Greetings_Scene63_0_P0` and `Greetings_Scene178_0_P0`). Since the variables
are free, 167 is an upper bound.

On the built gates (2026-10-26, a scratch version of this check over the
ledger's option prompts, about 30 s): 760 menus in 113 FNV topics before the
fix, 152 in 8 after. Two lessons for the real check:
- **It must settle speakers' fixed facts** (voice type, factions not changed
  by scripts, as the build's `speaker_facts` does). Without them it reported
  three doctor topics whose options never meet: Ada Strauss and Linda
  Schuler are not in DoctorsDialogueFaction, and Doc Mitchell has the voice
  type the Doctors quest excludes.
- **A pair can come from a loose gate, not a missing exclusion.** In four
  topics (Big Sal, Gloria Van Graff, Diane, Primm's deputy) the later
  option's exclusion is right, but the earlier option's own gate shows with
  no answer passing: its "one answer unsaid" OR-group, or its speakers
  judged apart from the answers. That is [check 3](#gates)'s finding.

## <a id="gates"></a>Check 3: option gates

An option must show exactly when FNV shows that entry: when the first passing
line of the topic, for this speaker, is one of the option's lines, the topic
is known and the quest runs. The check compares the option's gate with that
over every combination of their facts:

- *hidden:* FNV shows it and the gate fails (a missing unlock, a gate tighter
  than its lines);
- *empty:* the gate passes and none of its lines can (Nash, Torini); every
  `one_each` gate is expected here, as review;
- *wrong prompt:* the gate passes while an earlier line of another option of
  the topic passes.

Only lines that can pass together with the option's own count as "earlier"
(check 2's pairs), so the test holds the option's lines and its few
competitors, not the whole topic. Measured per option and speaker on FNV's
records, own lines only (2026-10-25): 9,992 of 10,100 need at most 4,096
states, 36 more than 65,536 (at most 19 facts; `DoctorMedical`'s "I'm hurt. I
need help, Doc." is the largest). An option past the limit is checked by
sampling and marked review, with the count reported.

## <a id="effects"></a>Check 4: effects

No state. For each FNV line, what its result scripts write, against what each
of its copies writes, half by half (FNV's begin and end scripts; FO4's
`Fragment_1` on begin and `Fragment_0` on end):

| FNV writes | The copy writes |
|---|---|
| AddTopic | Its topic's `TES4Unlock_` global |
| SetStage | The converted SetStage (`TES4SetStage`, `TES4Polyfill.SetStage`, `.SetStage`), as `quest_converted.py` reads them |
| A quest variable | Its `TES4QVar_` mirror global, or the converted property |
| Objective shown or completed | The `TES4ObjShown_`/`TES4ObjDone_` mirror |
| Say Once (flag) | `F3NV_SayOnce` with the line's marker stage |
| Follow Ups (structure) | The `TES4FollowUpFrom_`/`Said_` marks |

The FNV side reads SetStage as the quest audit's source side does
(`quest_source.py`); AddTopic and variable sets join it. A finding is an
effect missing on a copy, a different value, or one written in the other half
of the line: an unlock written at the end of the line the next menu needs
lands too late. This is where "AddTopic never unlocks the topic" shows up, on
every copy, without walking to it.

## <a id="rules"></a>The rules

The checks need each side's rules: what order lines are tried in, what makes
a topic show, what XDI lists. Each [open question](#open) is settled by
reading the code that decides it, written into the [FNV side](#fnv-side) or
[FO4 side](#fo4-side) with its address or source line, and given a fixture.
As with all disassembly, a reading is a theory until data agrees: each rule
is also checked against a few records where it decides the outcome (a topic
split across two quests, a Say Once line two NPCs share).

FNV, in the GOG `FalloutNV.exe`, with the `tools/disasm` tools (`--exe`):

| Question | Where to read |
|---|---|
| Line order within a topic and across quests; Random piles | `GetTopicInfo` at `0x61A7D0` (the engine's picker, which JIP's `GetTopicInfo` wraps, `JIP-LN-NVSE/internal/jip_core.h`) |
| Which topics make the list, and their order | The `DialogMenu` topic-list builder (menu singleton `0x11D9510`, `topicList` at +0x40, layout in `JIP-LN-NVSE/nvse/GameUI.h`) |
| Say Once per actor or per line; Say Once a Day timer | The flags `ResetDialogueFlags` (`rdf`, opcode 0x1AF, handler `0x5d8930`) clears, traced to where the picker reads them |
| Choices against Follow Ups; when the list comes back; whether a Choice makes a topic known | The `DialogMenu` code that runs after a line finishes |
| Speech challenge prompt text | Where the menu adds the `[Speech 50]`-style text to a prompt |
| What GetReputationThreshold returns | Its condition function |

FO4: XDI's source, cloned into `references/` for reading (the spike read it
online), and `Fallout4.exe.unpacked.exe` with the `tools/disasm` tools and
F4SE's source (`src/f4se-0.7.9.tar.gz`) for layouts:

| Question | Where to read |
|---|---|
| How XDI builds ranges from its four player topics, and which INFO of a range it shows (play showed a pad can show blank) | XDI `src/DialogueEx.cpp` |
| Option order, and how many show at once | `DialogueEx.cpp`, the `Neanka/DialogueMenu` AS3 |
| Whether XDI tests an option's answers before listing it (play says no: Nash's stall) | `DialogueEx.cpp` |
| Which INFO a scene's Dialogue action plays | `Fallout4.exe` |
| Whether TIQS stages and a fragment's writes land before TSCE's scene lists its options | `Fallout4.exe`, then the [play log](#play-log) |
| Whether `F3NV_SayOnce`'s OnBegin lands before the next menu | The [play log](#play-log) (Papyrus timing is not in the exe) |

## <a id="fnv-side"></a>The FNV side

FNV's rules, each with its source. Rules marked *verify* are believed, not yet
confirmed; each is settled from the exe ([rules](#rules)) before a check
relies on it.

1. **Greeting.** Activating an NPC plays the first passing GREETING line
   (converter notes: highest quest priority first, then line order). A line
   with Choices opens a menu of those topics; otherwise the topic list.
   *Verify:* the order.
2. **A line can play** when its quest runs, its quest's own conditions pass
   and its own conditions pass (converter notes, `with_quest`;
   [dialogue conditions](fo4_pipeline.md#dialogue-conditions)).
3. **Topic list.** Every topic the player knows (Top-level, or added by
   AddTopic; GECK: "Top-level: this topic will be included in the list of
   default topics") with at least one line that can play for this speaker.
   Order: by priority (GECK: "Priority determines where the info will appear
   in the list"). *Verify:* the order and tie-breaks, and whether a Choice
   makes a topic known.
4. **One entry per topic.** Its prompt is the first passing line's Prompt,
   else the topic's name (GECK: "Prompt: displayed in place of the topic
   text").
5. **Answer.** The first passing line of the topic, in quest-priority then
   line order: the line whose prompt shows. *Verify:* the cross-quest order,
   which the build reproduces with heapq-merged Hub positions.
6. **Random.** Consecutive Random lines form a pile and one is picked (GECK:
   Random, Random End). Checks compare the pile, not one pick.
7. **After a line.** Its Choices (a menu of those topics), else its Follow
   Ups, else back to the topic list; a Goodbye line ends the talk (GECK:
   "Goodbye: when this info is completed, the actor leaves dialogue").
   *Verify:* Follow Ups.
8. **Say Once.** Once said, never said again *by that actor* (GECK: "a
   different actor that qualifies may say it"). The build marks a line said
   for everyone ([say once](fo4_pipeline.md#say-once)), so this differs by
   design on lines more than one NPC can say: check 1 counts them, and they
   go to the [drift doc](fo4_drift.md) or get fixed. *Verify:* per actor.
9. **Say Once a Day** (12 game hours, `fSayOncePerDayInfoTimer`): treated as
   Say Once.
10. **Speech challenges.** The option shows with its skill; the answer is the
    success or failure line, both compared.
11. **Shading** (Always Darken, Info Refusal) changes only how a prompt looks:
    not compared.

## <a id="fo4-side"></a>The FO4 side

How the built plugin plays. These were read from XDI's source in
[spike 1](fo4_spikes.md#spike-1-design) and from play; one reading has
already been wrong (empty INFOs were taken as always hidden, until Cliff
Briscoe's pad showed as "dialogueentry"), so each is a *verify* rule until
settled from its source ([rules](#rules)), the same as FNV's.

1. **Greeting.** Activating the NPC plays the shared greeting quest's
   Greeting topic; its silent line (`GetPlayerActivated` or a running force
   greet, and a speaker the GREETING lines name) starts the GREETING scene with
   the NPC in the Speaker alias. *Verify:* its Dialogue action plays the first
   passing line in topic order.
2. **A scene** runs its phases in order; a Dialogue action plays the first
   passing line of its topic; a line's TSCE starts another scene; End Running
   Scene ends the talk.
3. **An XDI menu** (Player Dialogue action): the player INFOs of its four
   player topics fall into ranges, a non-empty INFO and the empty ones after it
   (the pads); each range shows as one option when an INFO of it passes
   (tested with the player as Subject, the NPC as Target), and a passing pad
   whose prompt fails shows blank; the option's answer is the first passing NPC
   INFO in its range; XDI lists an option without testing its answers; Say
   Once player and NPC INFOs drop once said. *Verify:* each part.
4. **The build's own state:** an AddTopic line's fragment sets the topic's
   `TES4Unlock_` global; a Say Once copy's `F3NV_SayOnce` OnBegin sets its
   marker stage; Follow Up marks set `TES4FollowUpFrom_`/`Said_` globals.
   *Verify:* each lands before the next menu lists its options.
5. **`[Leave]`** is an option with End Running Scene; a scene flagged Prevent
   Player Exit Dialogue keeps the player in.

## <a id="state"></a>Conversation facts

The facts are the condition differential's vocabulary (quest stages, quest
variables, globals, factions, items, the speaker, and after
[step 0](#vocabulary) actor values, karma and reputation), plus three
conversation facts. The differential holds the build's side of these true;
checks 2 and 3 read them as facts:

| Fact | FNV reads it as | FO4 reads it as |
|---|---|---|
| Topic known | Top-level, or AddTopic ran | `TES4Unlock_<topic>` global, or no gate |
| Line said (Say Once) | Said by this actor | Marker stage done on `FNV_TES4SayOnce` |
| Follow Up pending | The last line's Follow Ups | `TES4FollowUpFrom_`/`Said_` globals |

## <a id="play-log"></a>Check 5: menus logged in play

The only check of FO4's rules and of timing, at no extra game time. Half of
it exists: `fo4_trace` ([trace](fo4_pipeline.md#trace)) already reads the
Papyrus log for each FNV line begun and ended (`line`: speaker, FNV INFO),
every stage, quest variable and global a converted script sets, and every
conversation scene a script starts. Two parts are missing:

- **Lines with no converted script.** The `line` points sit in INFO fragment
  scripts (`script_convert/trace_points.py`), so a line with no result script
  is never traced. `F3NV_SayOnce` can trace the Say Once ones; the rest need
  the logging below.
- **The options shown.** When an XDI menu opens: the NPC and each option's
  player INFO. Logged by a Papyrus listener if XDI sends the menu's options to
  script, else by `F3NV.dll`, which needs the user's go-ahead first, since it
  adds a DLL hook. Only while `TES4Trace` is on, so released builds are
  unaffected.

After a session, a script rebuilds the state from the logged changes and
judges each logged menu and line by the rules: a menu that differs from what
FNV shows is a finding, and so is one that differs from what the FO4 rules
predict (a rule read wrong, or a write that landed late). A session from a new
game knows every fact; one loaded from a save knows only the facts set since,
and its findings name the facts they assumed.

## <a id="findings"></a>Findings

One finding per (menu, topic, kind), with the state and menu path that shows
it:

| Kind | Check | Severity |
|---|---|---|
| Lines missing, extra or out of order in a pick | 1 | error |
| An edge missing or different (Choices, Link From, Follow Up, Goodbye, back to the list) | 1 | error |
| Blank or duplicate option, or a prompt that differs | 1 | error |
| A topic on or off the topic list where FNV differs, or an unlock gate missing | 1 | error |
| `[Leave]` on one side only | 1 | review (FNV's Tab is not a menu option) |
| A Say Once line more than one NPC says | 1 | review, then the drift doc or a fix |
| Two options of one topic shown at once | 2 | error |
| Option hidden where FNV shows it, or shown with no answer, or with the wrong prompt | 3 | error; review for a gate checked by sampling, and for `one_each` |
| Effect missing, different, or in the other half of the line | 4 | error |
| Logged menu or line differs from FNV's, or from the FO4 rules' prediction | 5 | error |

Keys: `menus|<plugin>|<menu>|<topic>|<kind>`, with the NPC in the detail when
a state names one. The detail names the state (only the facts that matter)
and the path, for example
`greeting → "Who are you?" → "What do you do here?"`, so a tester can
reproduce it in game in a few clicks. A state is one the conditions allow;
whether the story reaches it is not checked ([limits](#limits)).

## <a id="validation"></a>Proving it works

Each check is tried against something independent before its findings are
trusted:

1. **The live bugs.** On the current build, check 2 must report Jason Bright's
   and Doc Mitchell's pairs before any fix, and none of them after.
2. **Known bugs come back.** The play-test bugs in the
   [table](#catches), replayed by mutating a current build's menus the way
   each bug looked (a pad without conditions, an option without its "some
   answer passes" test, an answer out of order, a missing unlock gate, an
   unlock written on the wrong half). Each must produce its finding.
3. **Mutation rate.** As for the condition differential: random mutations of
   agreeing menus (drop a gate, swap two answers, unpad, remove a Say Once
   mark, drop a write), with the catch rate reported. Target: above 95%.
4. **Rules** ([rules](#rules)): every rule a check applies cites the address
   or source line it was read from, has a fixture (a tiny topic, line and
   scene set it decides), and is checked against records where it decides the
   outcome.
5. **The play log** ([check 5](#play-log)): every logged menu the checks call
   correct must match what the user saw, which they see anyway. No play time
   is spent on the audit itself.

## <a id="phases"></a>Phases

| # | Work | Done when |
|---|---|---|
| 1 | [Step 0](#vocabulary): actor values, karma, reputation and GetHasNote paired in `condition_diff.py` | The conditions audit judges the ~2,300 lines it skipped; its findings triaged |
| 2 | Checks [1](#structure) and [2](#exclusion); `--audit menus` in the preflight runner; ledger keys | Jason Bright and Doc found; first whole-map report; under a minute |
| 3 | [Rules](#rules): FNV's from `FalloutNV.exe`, FO4's from XDI's source and `Fallout4.exe` | Each rule written with its address or source line, a fixture and a record check |
| 4 | [Check 3](#gates) | Nash and Torini mutations found; the count of gates past the limit |
| 5 | [Check 4](#effects) | Mutation rate above 95% |
| 6 | [Check 5](#play-log): the missing log points and the replay | One play session replayed with no false findings |

Phases 1 to 3 are independent and can run in parallel; phase 2 runs on the
*verify* rules and re-runs as phase 3 settles them. Phase 2 already finds the
two-options bug; phases 2 and 4 together cover every translation bug in the
[table](#catches).

## <a id="left-out"></a>Considered and left out

- **Trying every state of every option** (the first version of this plan).
  Measured per topic and speaker on FNV's records: 93% need at most 4,096
  states, but 617 need over a million, mostly GREETING (about 2,200 lines and
  400+ facts per speaker), where sampling 256 states proves nothing. The
  order argument in [how it works](#design) settles first-passing picks with
  no state, and the gates left over are small.
- **Walking conversations from seed states** (fresh game, story checkpoints)
  with two menu emulators. Checks 1 and 4 cover each step's edges and writes
  for every line, with no depth limit or node budget. Walks would add only
  which states the story reaches; revisit if findings in unreachable states
  get noisy.
- **An engine oracle**: an NVSE plugin that sets a state from the console and
  calls FNV's own picker (`0x61A7D0`) per NPC and topic. JIP has no command
  that returns the picked line without running its result scripts
  (`CCCRunResultScripts` runs both), so it needs its own plugin (about a day)
  and FNV with xNVSE launchable unattended. Kept only for a rule the exe
  leaves unclear, never as a whole-game run.

## <a id="open"></a>Open questions

FNV's side, settled from the exe ([rules](#rules)):

- Answer order across quests (quest priority, then line order?), and
  topic-list order: compare order, or only the set?
- Say Once per actor (FNV) against one marker per line (the build): check 1
  counts the lines more than one NPC can say, then fix or record as drift.
- Follow Ups: their exact FNV rule (first passing Follow Up, before or instead
  of returning to the topic list) and how the `TES4FollowUp` globals mirror it
  ([VCG01 notes](fo4_spikes.md#spike-2-vcg01)).
- Speech challenge prompts: FNV adds `[Speech 50]`-style text in the engine;
  does the build put it in the prompt?
- What GetReputationThreshold returns, for [step 0](#vocabulary).

FO4's side, settled from XDI's source and the exe:

- How XDI builds ranges and orders options, and how many it shows at once.
- Whether XDI sends the open menu's options to Papyrus (decides how
  [check 5](#play-log) logs them).
- Whether unlock and Say Once writes land before the next menu lists its
  options.

Sizing:

- How many option gates, with their competitors added, pass the exact-check
  limit (own lines alone: 36 of 10,100 over 65,536 states).

## <a id="limits"></a>What it will not see

- How a menu looks: XDI layout, camera, timing, subtitles, voice.
- Scene start conditions and phase conditions (as in the quest audit).
- Conditions run on aliases (chat scenes' Target tests), and the functions
  still unpaired after [step 0](#vocabulary): script variables by index (333
  FNV lines), packages, regions, sitting.
- Effects beyond the parsed ones: a result script that changes state in a way
  the parser does not read is checked on neither side.
- Whether the story reaches a finding's state: a finding names a state the
  conditions allow. Most need little (nothing said yet, caps in hand), but a
  finding that needs an impossible mix of stages is possible.
- Timing and engine behavior no record shows and no rule question names: only
  [check 5](#play-log) sees them, and only in states play reaches.
