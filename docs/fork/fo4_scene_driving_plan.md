# FO3's scripted scenes on Fallout 4's scene engine
Status: PLAN (2026-11-16)

**Code today:** `script_convert/commands.py` (`say`), `TES4Polyfill.SayWhenFree` / `SaysSettled` /
`HoldSays`, `script_convert/say_to_done.py`, `fo4_import/spike/packages.py` (`_plan`, `_talk_to`,
GreetOnce), `script_convert/package_events.py`.

## <a id="why"></a>Why this plan

Ten playtests of Fallout 3's opening (birth, first steps, the 10th birthday)
each moved the scene a few steps and stopped somewhere new. Sorted by the
mechanism at fault, the same few FO3 mechanisms keep breaking:

| Round's symptom | FO3 mechanism | What we did | Result |
|---|---|---|---|
| Dad stays leaning over the playpen; Dad stands at the open door | `begin OnPackageDone/End` blocks, package section scripts | ran them from FO4 package fragments | **fixed** (played) |
| Party stops after "Surprise!"; stops after "Happy birthday" | script `Say`: FO3 returns at once, the whole block runs before any line ends | `SayWhenFree` blocks until the line begins, then a counter, then a per-block hold | Surprise fixed; birthday fixed only after a wider hold, which then **stopped the birth** (too broad), now narrowed, not yet played |
| Amata never comes over; nothing after the Pip-Boy | Dialogue package, SayTo to the player (walk up, say a line) | first a ForceGreet (never fired), then a Travel to the player whose arrival says the line | **still stuck**: the arrival never ran |
| Dad stands up halfway between verse lines; then stays kneeling | speaker idles with FO3 loop counts | looped seconds, then a baked loop plus `IsIdlePlaying == 0` | **still wrong**: never released |
| Overseer arrives early, the atrium door stays open | Overseer's walk-up package (stage 5, above his hold package, so FO3 also sends him early); its end script `CG02AtriumDoor.setOpenState 0` | not looked at yet | open |
| Adult body, then adult height | `AgeRace` | child race, child addons, scale | body fixed; height built, not played |

The pattern is the user's: each fix forces FO4 to imitate an FO3 runtime
behavior (Say's timing, a package that walks up and talks, an idle that
loops a count), and each imitation has a new edge. FO4 does all of these
with **scenes**, and its own opening does nothing else.

## <a id="fo3"></a>How Fallout 3 drives the opening

There is no scene record in FO3. A scene is quest stages plus AI packages
plus lines plus polled scripts (census of the export, 2026-11-16):

| Quest | Packages gated on it | Lines (of which set a stage) | Scripts naming it |
|---|---|---|---|
| CG00 (birth) | 21 Travel | 60 (7) | 4 |
| CG01 (age 1) | 6 Travel, 1 Escort | 20 (5) | 10 |
| CG02 (birthday) | 85 on 17 actors: 45 Travel, 20 Dialogue/Conversation, 4 Dialogue/SayTo, 16 other | 343 (42) | 17, with 16 `Say` calls in `CG02SCRIPT` alone |
| CG03 (G.O.A.T.) | 65: 30 Travel, 16 Find, 13 Conversation, ... | 318 (27) | 14 |

The flow, as CG02 shows it:

1. **A stage gates packages.** Each actor's package list is ordered and
   conditioned on `GetStage CG02`; a stage change re-picks every actor's
   package (Dad has 13, top first).
2. **A polled quest script runs a timer** (`CG02SCRIPT` GameMode:
   `intro` 1..5, `runTimer`, `timer`) and calls `Say`/`SayTo` on several
   actors in one block.
3. **A line's end result advances it** (`set CG02.intro to 4`,
   `setstage CG02 6`); `SayToDone` blocks on the speakers' scripts run too.
4. **Dialogue packages** walk an actor to the player or another NPC and
   start a talk (Conversation: the menu; SayTo: one line, no menu).
5. **Package end scripts** close doors and set stages.

Across all of Fallout 3 the same pieces are everywhere: 451 `Say`/`SayTo`
calls in 154 scripts plus 35 line results; 383 Dialogue packages (170
Conversation to the player, 193 to another NPC, 10 SayTo to the player, 8
to another NPC); 507 package section scripts; 128 `SayToDone` and 67
`OnPackage*` blocks.

## <a id="fo4"></a>How Fallout 4 does the same

Vanilla's opening (`MQ101`, Sanctuary Hills to Vault 111) is **98 scenes**
(3,568 in Fallout4.esm). A scene has actors (quest aliases) and phases;
each phase holds actions: Dialogue (a topic said by an alias), Package (an
alias runs a package for the phase: walk somewhere, hold, sit), Timer,
Player Dialogue (the menu), Start Scene. A phase ends when its actions end;
a scene line's end result runs before the next phase. Approaching the
player and speaking is a Package action (29 vanilla Travel packages target
PlayerRef, such as `DefaultApproachPlayer`, `CIS_TravelToPlayer`) followed by
a Dialogue or Player Dialogue action in the next phase.

What that gives for free, where FO3's runtime needed imitating:

| FO3 runtime behavior | Imitation today | FO4 scene |
|---|---|---|
| `Say` returns at once; lines play later, in order | `SayWhenFree` waits for the speaker, a global counter holds line results | `Scene.Start()` returns at once; the engine waits for a free speaker and never drops the line; results run when the line ends |
| Walk up to the player and say a line | ForceGreet template, then Travel + end fragment | Package action (travel to the player), then Dialogue action |
| Walk up and open the menu | ForceGreet + shared GREETING scene | Package action, then Player Dialogue action |
| Talk to another NPC | Travel + `F3NV_DialoguePackage` starting a chat scene | the same as above, already scene-based at its end |
| A pose held for several lines | idle loop counts on speaker idles | a Package action holding the pose across the dialogue phases, released when the phase ends |

## <a id="options"></a>Options

**A. Keep FO3's logic, run its actions as FO4 scenes (recommended).**
Stages, conditions, quest timers, line results and package fragments
already work on FO4: this playtest ran the party from the birth through
the Overseer's speech to stage 10 on them. Only the *actions* that FO4
plays differently change, and they change everywhere at once (generic):

1. **Script `Say`/`SayTo` → a one-line scene per call site.** The
   converter already writes call-site scenes for FO3's speak-as `Say`
   (`TES4Polyfill.SpeakAs(topic, TES4Scene_...)`). Every `Say` becomes
   that: its own Speaker (and Target) alias, filled by the call, then
   `Start()`. This deletes `SayWhenFree`, `SaysSettled`, the says count and
   the per-block hold, the source of three of the stalls. Cost: about 490
   scenes and their aliases on one or a few helper quests.
2. **Dialogue packages → a two-phase scene.** The package stays in the
   actor's list with FO3's conditions and order, so FO4 picks it exactly
   when FO3 would; its begin fragment fills the scene's aliases (actor,
   target) and starts it: phase 1 a Package action walking to the target
   within FO3's distance, phase 2 the topic (Dialogue action; Player
   Dialogue for a Conversation with the player). The scene's end marks the
   package done (the GreetOnce parked copy already does this for force
   greets). Covers the 383 Dialogue packages, the Amata and Pip-Boy stalls
   among them.
3. **A pose across lines** (Dad's verse): the speaker idles stay, and a
   scene that says several lines in a row by one speaker who has a looped
   idle holds it with a Package action for those phases. That is what the
   user asked for: locked for the dialogue, released when it ends.

Package events, `SayToDone`, stages, timers and triggers stay as they are.

**B. Hand-build FO4 scenes for the opening only.** Fastest route to a
playable opening, but it is a replacement for one quest's data, not a
conversion: nothing it fixes reaches Megaton, Rivet City or New Vegas,
which use the same 451 `Say` calls and 383 Dialogue packages. It also
breaks the "all fixes are generic" rule, so it would stay fork-only.

**C. Translate FO3's quests into FO4 scenes wholesale.** FO3's order of
events is implicit, spread across timers, stage conditions, package order
and line results; recovering a scene graph from that in general is not
possible without guessing, and A already keeps that logic working.

## <a id="order"></a>Order of work for A

1. `Say` → call-site scenes (phase 1 above), then a playtest from the
   birth: the birth, the playpen, "Surprise!", "Happy birthday".
2. Dialogue packages → scenes (phase 2), then the Pip-Boy follow-up, Amata,
   Butch, the G.O.A.T. walk-ups.
3. The verse pose (phase 3) and the Overseer's atrium door (diagnose: its
   walk-up end script closes the door, FO3's own package order sends him
   at stage 5).

Each step removes the imitation it replaces in the same change.

## <a id="fnv-check"></a>The FNV check on every step

FO3 and FNV share the converter and `TES4Polyfill`, and FNV has more of
every pattern above (549 `Say` calls in 229 scripts, 265 line results that
say, 332 Dialogue packages), so each step changes FNV's build too. Before a
step, `tools/validate/build_diff.py snapshot` keeps both games' built
plugins and generated scripts; after the rebuild, `diff` lists every record
and script that changed, and each one is read before the step is reported,
with the counts per kind and the FNV quests involved. A short FNV play
then covers one of each: Doc Mitchell's opening (`VCG01`), Sunny Smiles,
and a walk-up (Arcade or Sarah's Vault 21 tour).

Baseline: `fnv-pre-scenes` and `fo3-pre-scenes`, the builds of 2026-11-16
with the narrowed says hold.
