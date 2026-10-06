# FO4 spikes: deciding whether FO3/FNV on Fallout 4 is buildable

Design only; status is in [ROADMAP.md](ROADMAP.md). The findings behind this
plan are in [research/fo4_target.md](research/fo4_target.md).

## Contents

- [Order and why](#order)
- [Step 0: groundwork](#step-0)
- [Spike 1: dialogue](#spike-1)
- [Spike 3: one script](#spike-3)
- [Spike 2: one interior cell](#spike-2)
- [Decision point](#decision)
- [Test setup](#test-setup)

## <a id="order"></a>Order and why

Spikes come before more exe reading. The [AI rules](research/fo4_target.md#ai-rules)
read so far settled the one question exe work could decide: FO4's AI
decisions are Skyrim's. The questions that could still sink the project are
on the content side, ordered by how decisive each is:

1. **Dialogue (spike 1).** Can FO3/FNV dialogue be generated for FO4 at all?
   This is go/no-go.
2. **Scripts (spike 3).** How big is the script back end? Runs in parallel
   with spike 1 and needs none of your play time.
3. **Assets (spike 2).** What does the mesh/material/collision/FaceGen back end
   really cost? Only worth paying for once spike 1 passes.

Exe reading resumes where a spike needs it. Spike 1 plays a force greet, which
settles R10 by observation.

## <a id="step-0"></a>Step 0: groundwork

| Piece | What |
|---|---|
| FO4 plugin writer | `fo4_import/base/writer.py`: `FO4PluginWriter` (form version 131, FO4 header with HEDR 1.0, INTV and INCC, FO4 top-level group order), plus `pack_quest()` / `pack_topic()` for FO4's nesting. Dialogue has no top-level group: each QUST is followed by a quest-children group (type 10) holding DLBR, then DIAL with its INFO group (type 7), then SCEN, in vanilla's order. Tests: `tests/test_fo4_writer.py` |
| Vanilla dump | `references/Fallout4.esm/`: all 138 record types, 558 MB, from `tools/esm/tes5_esm_reader.py --generic`. The `--generic` switch skips the tool's Skyrim field layouts and condition names, so FO4 fields show as raw FormID/uint/float/hex rather than mislabelled Skyrim fields. FO4-specific decoders get added as spikes need them |
| Script sources | `references/fo4_scripts/Base` (Base, the six DLC and Creation Club zips, 10,258 files, with `Institute_Papyrus_Flags.flg`) and `references/fo4_scripts/F4SE` (29 files). Import order: F4SE first, then Base |
| Compiler | Fallout 4's own `Papyrus Compiler\PapyrusCompiler.exe`. A smoke script with a struct, a timer and F4SE's `Form.GetEditorID` compiles. The vendored `external/papyrus-compiler/papyrus.exe` is Skyrim-only: it stops at the first `Struct` |

Known gap: `tes5_import.base.tes5_reader.walk(raw, b'DIAL')` (a *filtered*
walk) prunes group type 10 as Skyrim cell children, so it misses every FO4
topic. Unfiltered walks, and the dump tool, see them. An FO4 reader needs its
own child-group table.

## <a id="spike-1"></a>Spike 1: dialogue (go/no-go)

Generated from the FNV export by code, not built by hand in the CK.

- **1a. Doc Mitchell's opening conversation**, as XDI-enabled scenes:
  - the topic list, with more than four options;
  - SPECIAL and skill checks;
  - a silent player;
  - the force greet, played, to settle R10;
  - his voice lines as `.fuz` with lip data.

  The speaker is a vanilla FO4 NPC base in a test cell, so no converted
  meshes or FaceGen are involved.
- **1b. One generic topic many NPCs share**, placed on three vanilla NPCs.
  This tests how FO3/FNV's "any NPC whose conditions pass can say it" maps onto
  FO4's alias-based scenes.
- **Gate:** if 1b can't be generated without hand work, stop and rethink
  before any asset work.

### <a id="spike-1-design"></a>1a as built (text only)

Generator: `py -3.14 -m fo4_import.spike.dialogue --export <FNV export> --out <esp>`
(`fo4_import/spike/`). Source view: `tools/dialog/tes4_ctda_dump.py --names fnv --npc DocMitchell`.

**Source.** Doc's menu conversation is the `VFreeformGoodSpringsDocMitchell*`
topics plus the shared doctor services. His very first lines (waking up) are
scripted `SayTo` chains (`VCG01Intro`), not the menu, and are not part of 1a.

**How XDI decides** (its source, `reg2k/xdi` `src/DialogueEx.cpp`, and the
`Neanka/DialogueMenu` AS3):

- Every non-empty player INFO in the action's four player topics is an option.
- Options whose conditions fail are hidden, as are options with empty response
  text.
- Player INFOs are tested with the player as Subject and the NPC as Target.
- NPC response INFOs pair with player INFOs by position. Empty player INFOs are
  padding, and the response is the first passing NPC INFO in the option's range.
- Say Once player and NPC INFOs drop out once said.

**Mapping.**

| FNV | FO4 |
|---|---|
| Topic list (GREETING with no choices) | One XDI scene per menu, one phase `Menu`, one Player Dialogue action; PTOP holds the options, NPOT the responses, NTOP/NETO/QTOP empty (XDI reads all four) |
| A topic's INFOs, consecutive ones with the same prompt | One option; its INFOs become the NPC responses behind padding, so the first passing one answers (FNV's rule) |
| INFOs with different prompts (skill-check variants) | One option each. Each later option also gets "no earlier option could be chosen": the earlier INFO's negated conditions as one OR-group, plus "it has been said" for a Say Once one |
| Prompt (`RNAM`), else topic name | Player INFO response text and `RNAM` |
| Choices | Their own scene; the NPC INFO's `TSCE` points there |
| Goodbye | No `TSCE`, and End Running Scene (XDI's door icon) |
| Any other line | `TSCE` back to the menu scene, phase `Menu` |
| Top-level topic | Always offered |
| AddTopic | INFO `TIQS` on end sets a quest stage; the added topic's option needs `GetStageDone` |
| "Has been said" (no FO4 condition for it) | INFO `TIQS` on begin sets a stage |
| Line of a stopped quest | Left out (FNV only speaks lines of running quests) |
| Conditions | Function by name (`GetActorValue` → `GetValue`); actor values by name (limb conditions, Rads); FNV skills → plugin actor values `FNV_<Skill>`. Player-line conditions swap Subject and Target. Anything unconvertible drops the line, and the report names it |
| GREETING lines | An FO4 greeting topic (`GREE`); each line starts the menu scene |

**Assumed state** (quests not converted here): just after character creation.
VCG01 is finished, and Doc's script variable 4 is 0. VMS16 and VMS16b are not
started, so the bandit-shootout and injured-man topics are absent.

**Built (2026-10-05):** 87 records. The main menu has 15 options, including the
four Medicine/Speech variants, the two added topics, the doctor services and
their pay/decline sub-menus. One line is left out (an unconverted quest
variable), and result scripts are not converted (8 lines: items, healing).

**Played (2026-10-05).** First build: the greeting opened a pay sub-menu, and
sub-menu answers looped to themselves. Both went to "the first scene built"
instead of the main menu; the main menu now has a fixed id. Second build: the
greeting opens the menu, and all of Doc's options show. Also confirmed:
- an added topic appears after its AddTopic line, and a Say Once prompt gives
  way to the next variant ("…one more time?");
- the Medicine/Speech variants follow FNV's first-passing rule as the skills
  change;
- a doctor service answers by condition (full health: "nothing wrong") and
  returns to the main list;
- Goodbye ends the conversation.

A "Hi" before the greeting is the player character's own greeting line. FNV's
player is silent, so it needs suppressing (open). Looked at 2026-10-05, left
until it causes a problem:
- FO4 has no player-greeting subtype. The line is most likely
  `DialogueGenericPlayer` (`000179EF`)'s Hello topic (`00018184`, HELO, 52
  INFOs);
- 49 of the 52 have no conditions, and the other 3 only test combat, dying
  and keywords, so there is no global or setting to switch them off;
- likely fix: a player HELO line in our own quest (priority 90 against
  vanilla's) that wins for our speakers and says nothing. Untested: whether
  FO4 accepts an INFO with no response or shows a "..." subtitle. No
  vanilla edit;
- alternative (outside research): silent voice files over the player's
  Hello lines, as [mod 5702](https://www.nexusmods.com/fallout4/mods/5702)
  does for other player voices. Loose
  `Sound\Voice\Fallout4.esm\PlayerVoice{Male,Female}01\<INFO>_1.fuz` files
  for topic `00018184`'s 52 INFOs; no record changes. Open: whether the
  line's subtitle still shows, and it silences those hellos everywhere
  (fine for a game where the player is silent).

### <a id="spike-1b"></a>1b: one scene for many speakers

Generator: `fo4_import/spike/dialogue.py` (replaces `doc_dialogue.py`; 1a's
behavior is kept).

**How vanilla FO4 does it.** `DialogueGenericDoctors` (`0005F76B`) has one
alias, `Doctor`, that is optional and has no fill rule (`FNAM=2`). Its greeting
lines carry `ALFA=0` (Forced Alias) and a scene to start (`TSCE`). Whoever is
greeted is pushed into the alias, and the scene runs with them. All 122
vanilla INFOs with `ALFA` also carry `TSCE`.

**What FNV's menu topics are like.** Almost all lines are per-NPC (GetIsID).
Only a handful of top-level menu topics have lines that name no NPC:
- Lucky 38's robots (`HD00*`) and casino cashiers, by faction;
- followers, by voice type;
- the water beggar;
- Goodbye.

A shared topic like `DoctorMedical` still keys each line to one doctor.

**Mapping added for 1b:**

| FNV | FO4 |
|---|---|
| Several speakers | One quest with one optional, empty alias. Every greeting line has `ALFA=0` and starts the menu scene; the options are tested against the speaker |
| Quest dialogue conditions (the line picker checks them first) | ANDed onto every line of the quest; `GenericKids`' child-only Goodbyes no longer reach adults |
| Same prompt anywhere in a topic | One option (FNV shows a topic once) |
| An option with several variants | Gated by an OR of the variants' speaker tests (GetIsID, GetInFaction); ungated only if a variant has none |
| Random piles | `GetRandomPercent < 100/remaining` chained down the pile, and FO4's Random flag left off. XDI answers with the first passing line and has a "TODO: handle Random"; with the flag on, the robot butler's jokes never played |
| Tab (leave at any time) | A last `[Leave]` option on every menu: a silent `...` with End Running Scene. XDI's `DialogueMenu.as` `ProcessUserEvent` takes every key press while the list is up, so Tab never reaches the game. On a main menu it is hidden while a GOODBYE-topic option shows (the Goodbye options' conditions, negated) |
| Walking away (FNV has no equivalent; a talk always starts fresh) | The `Menu` phase completes on `GetDistance(Player) > 500` run on the alias, the same 500 as the scene's dialogue distance (`ACTV`). Without it the scene waited, and the menu reopened when the player came back. 127 vanilla phases end on a `GetDistance` this way |
| `GetPCIsSex` | `GetIsSex` run on the player reference |
| A speaker with no FNV greeting | A silent `...` greeting, last in the topic (FNV opens the topic list without one) |
| Only the player opens a talk (FNV NPCs do it only by force greet) | Every greeting line needs `GetPlayerActivated == 1` on the speaker, as 71 vanilla scene greetings have. Without it an NPC idling near the player said the greeting unasked, and it started the menu. A converted force greet will need a greeting without it |
| A condition settled by the test world | A speaker test naming no test speaker is false; a null form parameter is false (FNV's `GetInCell(NULL)` makes Doctor Barrows' `DoctorMedical` lines unplayable in FNV itself) |

**Test world.** Doc Mitchell → Doc Weathers; Doctor Barrows → Doctor Amari
(`0009A680`); a Lucky 38 robot butler → `WorkshopVendorBar01` (`00192356`),
with `HD00RoboButler` mapped to his `REMerchantBarVendorFaction`. All three
stand in `QASmoke`. Two stand-in traps:
- a unique NPC whose packages point elsewhere leaves the cell. Doctor Duff's
  all point to Diamond City, and she was gone on arrival; pick a base with no
  packages or only `DefaultSandboxInteriorUnlockDoors`;
- a faction listed at rank -1 (`FF`) is not membership. The vendor's
  `WorkshopVendorFactionBar` is -1 until a settlement assigns him, so
  `GetInFaction` failed and his vanilla greeting played;
- a stand-in keeps its own vanilla dialogue. Once ours needs the player to
  start the talk, Doc Weathers greets unasked with `DialogueGenericDoctors`'
  scene greetings, which have no activation check. Converted NPCs have no
  vanilla dialogue, so this is test-only.

**Played (2026-10-05), passed:**
- each speaker sees only their own options, all from one scene;
- Amari leaves through `[Leave]`;
- the vendor's time-of-day greeting, drink, haircut and Goodbye work, and his
  jokes play and vary;
- walking away ends the talk, and coming back does not reopen it.

Also fixed on the way: `tools/generators/gen_ctda_param_types.py` missed 108
of FO4's parameter types, because xEdit's FO4 file spells `Paramtype` in 100
entries. The match is now case-insensitive; the TES5, FNV, FO3 and TES4 tables
come out identical.

### <a id="spike-1-voice"></a>Voice

`--data <Data folder>` also writes the lines' voice (`fo4_import/spike/voice.py`).

- **Path:** FO4 finds a line at
  `Sound\Voice\<plugin>\<speaker's voice type>\<INFO FormID, load-order byte 00>_<n>.fuz`
  (the vanilla `Fallout4 - Voices.ba2` names its files the same way).
- **Source:** FNV files are `<quest>_<topic>_<INFO id>_<n>.ogg` in the
  speaker's voice-type folder. Each speaker maps that folder to the stand-in's
  FO4 voice type (`VOICES`), and a line gets a file wherever FNV recorded it.
- **Conversion:** the shared `convert_file_to_xwm` with the FO4 CK's own
  `Tools\LipGen\LipGenerator\` `LipGenerator.exe` and `xWMAEncode.exe` (same
  command line as Skyrim's). The `.fuz` is the same `FUZE` v1 container, and
  the lip header matches vanilla's.
- **Transcript:** response text with bracketed tags (`[SUCCEEDED]`) removed;
  the subtitles keep them, as FNV's do.

Built 2026-10-05: 41 files, 40 on Doc's lines and 1 on Barrows'. FNV has no
recordings for `HD00`'s robot butler lines. **Played:** Doc speaks in Doc
Mitchell's voice with moving lips.

### <a id="spike-1-force-greet"></a>Force greet (designed, not built)

FO3/FNV force greets play the same GREETING lines the player gets by
talking. FO3's Amata: `CG04AmataForceGreet` is a Dialogue package targeting
the player (`00000014`, 150 units) with type Conversation and no topic, so it
opens with her stage-conditioned greetings (`MS16AmataGreetPlayer` and
`CG02AmataGreetPlayerBeginning` look like the same kind by name).

Every generated greeting needs `GetPlayerActivated == 1`, which would leave a
converted force greet with nothing to say. Plan:

- the greeting check becomes `GetPlayerActivated == 1` **OR**
  `GetIsCurrentPackage(<FO4 copy of one of the speaker's force-greet packages>)`
  on the speaker, taken from the package records. Unprompted NPCs stay
  blocked; only authored grabs open a talk;
- the FO3/FNV Dialogue package becomes an FO4 force-greet package
  (`BGSProcedureForceGreet` exists);
- records only, no DLL.

Open, for a play-test (a FO3 force greet like Amata's is the natural spike-1
force-greet test):
- [R10](research/fo4_target.md#ai-rules): FO4's greet probably lasts until the
  talk ends, as FO3's does, so the package would still be current when the
  greeting is picked. Unconfirmed;
- whether `GetIsCurrentPackage` holds at that moment.

**Follow-up: one place for the way out.** Today Goodbye sits where its topic
falls (first on the main menu) and `[Leave]` is always last, so the exit moves
between menus. Put Goodbye and `[Leave]` in the same fixed slot on every menu,
top or bottom (check where FNV's topic list puts GOODBYE before choosing). Later,
give both the same name; they keep different names while testing, so a
play-test shows which one appeared.

Not covered yet: voice, the player's own "Hi" before a greeting, and the force
greet (Doc's menu conversation has none).

## <a id="spike-3"></a>Spike 3: one script

Convert one FNV terminal or object script, emit FO4 Papyrus, and compile it
with FO4's compiler. Hydra (in the MO2 instance) logs broken script linkage
in game. Answers: the size of the FO4 command-row table and of VMAD for FO4.

### <a id="spike-3-measured"></a>Measured (2026-10-05)

Corpus: the Skyrim pipeline's 17,703 converted FNV scripts
(`tes4skyrim_standalone/output/FalloutNV.esm/scripts/source`; 14,155 are
dialogue fragments `TIF__*`), compiled unchanged with FO4's
`PapyrusCompiler.exe` (imports F4SE, Base, the corpus and our 17
`static_scripts`). The compiler scans its working directory and fails on a
path over 260 characters, so run it from a short folder.

**A random 199 (149 object/quest scripts, 50 fragments):**

| Result | Scripts |
|---|---|
| Compile unchanged | 81 (all object/quest) |
| Fail only through a helper script (`TES4Polyfill` pulls in helpers that do not compile) | 54 (47 fragments) |
| Fail on their own code | 64 (3 fragments) |

**What fails, by kind** (errors in the sample; every one has an FO4 native
except `SetDontMove`):

| Skyrim (as we emit it) | Errors / scripts | FO4 |
|---|---|---|
| `RegisterForSingleUpdate` + `Event OnUpdate` (our GameMode loop) | 155 / 28+ | `StartTimer` + `Event OnTimer(int)`; `StartTimerGameTime` for `OnUpdateGameTime` |
| `Get`/`Set`/`Restore`/`Damage`/`Mod`/`ForceActorValue("Name")` | 52+ | `GetValue`/`SetValue`/`RestoreValue`/`DamageValue`/`ModValue(ActorValue)` on ObjectReference: an `ActorValue` property per name. Helpers that take the name as a string need a name → form lookup |
| `SendModEvent` (SKSE) | 10 | `CustomEvent` + `SendCustomEvent` |
| `Game.Disable`/`EnablePlayerControls` | 3 | `InputEnableLayer` (create, disable, delete) |
| `Debug.SendAnimationEvent` | 3 | `PlayIdle` (Actor) / `PlayAnimation` (ObjectReference) |
| `Event OnHit` parameters | 5 | FO4 adds `akTarget` first and needs `RegisterForHitEvent`, renewed after each hit |
| `Event OnTrigger`, menu and sleep events | 6 | no `OnTrigger`; `RegisterForMenuOpenCloseEvent`, `RegisterForPlayerSleep` |
| `SetDontMove` | 4 | none; `SetRestrained` is the nearest |
| A function variable shadowing a script variable (`TES4_CombatQueue`) | 2 | FO4's compiler rejects it; rename |

**The command-row table:** 20 of the 554 rows emit a call FO4 lacks (8 of
them `SendModEvent`, the rest actor values, `Debug.SendAnimationEvent`,
`Game.EnableFastTravel`, `SetDontMove`). The rest of the Skyrim API is
written by about 10 other converter files (handlers, event assembly, blocks),
so an FO4 target is a target-API layer across those, not a row swap.

**VMAD:** small. FO4 is version 6 (Skyrim 5), the same object format and
property layout plus struct types (7, 17). A fragment block starts with bind
data version 3 (Skyrim 2) and embeds a full script entry with its properties
where Skyrim has a file name; vanilla FO4 INFOs attach no other scripts.
Fragment scripts are namespaced (`Fragments:TopicInfos:TIF_<quest>_<id>`).
Five builders in `script_convert/pipeline.py` change.

### <a id="spike-3-target"></a>The target switch (in progress)

`script_convert/target.py` picks the game a run emits Papyrus for (Skyrim by
default, Fallout 4 with `convert_scripts_subset.py --target fallout4`),
through the environment so worker processes inherit it. The converter keeps
Skyrim's spelling internally, because event headers double as merge keys and
comparison values. Where FO4 differs, the converter builds the target's form
directly; nothing rewrites emitted text:

| Construct | How |
|---|---|
| Update loop | `event_opener` (`OnUpdate` → `OnTimer(int)`), `arm_update` (`RegisterForSingleUpdate` → `StartTimer`), `run_update_now` |
| `OnHit` | FO4 opener; `RegisterForHitEvent(Self)` at start (`lifecycle`) and first in the event, since one registration delivers one hit |
| Actor values | `av_call`: `GetValue(TES4AV_<name>)` etc. with an `ActorValue` property per name |
| Row templates | `command_rows_fallout4.FALLOUT4_ROWS`, keyed by the Skyrim `Cmd`, picked by `emit_row` (9 rows so far) |
| Animation events | `anim_event_call`: `PlayAnimation` |
| Player controls | `controls_call`: the FO4-only helper `static_scripts/fallout4/TES4_PlayerControls` holds the one shared `InputEnableLayer` |
| Tables | `FALLOUT4_EVENTS`, `FALLOUT4_AV_NATIVES` in `constants.py` |

Skyrim output is byte-identical (Doc's script against the pipeline's; 579
converter tests pass). `arch_fitness` matches `HEAD` except +8 branch points
and +93 code lines.

**Doc Mitchell's `GSDocMitchellScript` compiles with FO4's compiler**
(2026-10-05), emitted by the converter with no hand edits. It needed the
update loop, `OnHit`, actor values, player controls and an animation event,
plus one shared-helper fix (`TES4_CombatQueue` locals renamed: FO4's compiler
rejects a local that shadows a script variable).

**Helpers:** FO4's compiler checks only the declarations of the scripts a
script uses, so Doc compiles while helper bodies still fail. Compiled alone,
11 of 18 helpers pass. The 7 left:

| Helper | FO4 rejects |
|---|---|
| `TES4Polyfill` | about 75 actor-value calls by name, many with the name in a variable (needs a name → ActorValue lookup); SKSE `SendModEvent`, `GetModByName`; Skyrim's vampire quest; `IsPlayable` |
| `TES4_DialoguePause` | SKSE menu events and cell reference walking |
| `TES4_CombatQueue`, `TES4_DayClock` | the update loop (`OnUpdate`, `OnUpdateGameTime`) |
| `TES4_StagePackageAlias` | SKSE mod events |
| `TES4_BoundItemEffect` | SKSE `GetEquippedArmorInSlot` |
| `TES4_Terminal` | one actor-value read |

Not yet done: the pipeline's FO4 VMAD, filling `TES4AV_*`,
`TES4PlayerControls` and `TES4CharacterEvents`.

### <a id="spike-3-helpers"></a>The Fallout 4 helper set

**All 16 Fallout 4 helpers compile (2026-10-05)**; corpus 98.5% (17,429 of
17,695), every remaining failure in a converted script's own code.
Overrides so far: `TES4Polyfill` (new `AV`; `HasVampireFed`, `IsPlayable`,
`PlayerAttributeGlobal`, `StageSet`, `GlideAxis`, `SpinAxis`) and
`TES4_StagePackageAlias` (`OnInit` and the stage event: the quest's native
`OnStageSet` as a remote event). Two shared fixes, harmless for Skyrim: a
local that FO4's compiler rejects as a type name (`actorBase` in
`SetTalkingActivatorActor`), as in `TES4_CombatQueue`. `TES4_Terminal` only
compiles: FO4 terminals are TERM records with their own fragments, which is
records-side work.

`script_convert/helpers_fallout4.py`, applied when the pipeline deploys the
static scripts for Fallout 4:

- **Left out** (`FALLOUT4_UNUSED_HELPERS`): `TES4_DialoguePause` (FO4 talks
  stay unpaused, [R5](research/fo4_target.md#no-pause)), `TES4_DayClock`
  (FO4's `GameDaysPassed` carries the day's fraction, as FNV's did),
  `TES4_BoundItemEffect` (FO3/FNV have no bound items).
- **The converter's FO4 rules on the shared source**: actor-value calls
  become `GetValue(TES4Polyfill.AV("Name"))` etc.; `OnUpdate` → `OnTimer`,
  `RegisterForSingleUpdate` → `StartTimer`; menu names (`Dialogue Menu` →
  `DialogueMenu`). Every rule keeps line counts, so overrides still find
  their blocks.
- **Overrides**: `static_scripts/fallout4/overrides/<Script>.psc` holds only
  the functions or events whose FO4 body differs. Each sits under
  `; fallout4: replaces <Name> <sha1 of the shared block>` (or
  `; fallout4: new`); when the shared block changes, the conversion stops
  with the new hash instead of shipping a stale copy.
- `TES4Polyfill.AV(name)`: FO4 global functions cannot hold form properties,
  so the actor value is looked up in `Fallout4.esm`. `Aggression` (`0x2BC`),
  `Confidence` (`0x2BD`) and the other AI values are engine-made forms, not
  records in the esm. **FO4 has no `Variable01`–`10`**: the play-test's
  `setav variable01 1` answered "item not found", and no vanilla record or
  script uses them; vanilla scripts make their own actor value instead
  (`REAssaultRole` `000ABEA0`). The converted plugin has to carry
  `FNV_Variable01`–`10` as its own AVIF records, as the spike does, and
  `AV()` has to find them there: open for the corpus, and the helpers' own
  bookkeeping in `Variable03`–`09` depends on it.

### <a id="spike-3-trigger"></a>OnTrigger on Fallout 4

TES4's `OnTrigger` ran every frame something was inside the volume. Skyrim
sends a repeating `OnTrigger`; Fallout 4 sends only `OnTriggerEnter` and
`OnTriggerLeave`. So the per-frame body becomes the function
`TES4_OnTrigger` (still one at a time), `OnTriggerEnter` records the
reference and calls it every 0.1 s (`MIN_INTERVAL`) while the reference is
inside and the trigger loaded, and `OnTriggerLeave` removes it. The lines
join any authored enter and leave blocks (`assemble._trigger_repeat`).

### <a id="spike-3-singles"></a>The remaining failures (2026-10-05)

**99.9%** (17,672 of 17,695) after these, each the FO4 native closest to FNV:

| FNV | FO4 |
|---|---|
| `SetRestrained` (Skyrim: `SetDontMove`) | `Actor.SetRestrained` |
| `EnableFastTravel`, `SetCanFastTravelFromWorld` | `TES4_PlayerControls.FastTravel` (an `InputEnableLayer` setting) |
| `GetLOS` | `HasDetectionLOS` |
| `RemoveAllItems` | at most 2 arguments |
| `OnMagicEffectApply` | FO4's opener (adds `akTarget`) |
| sleep MenuMode | `RegisterForPlayerSleep`, `OnPlayerSleepStart`/`Stop` |
| menu-ID MenuMode (`RaceSex Menu`, VCG01's chargen) | `RegisterForMenuOpenCloseEvent("LooksMenu")`, `OnMenuOpenCloseEvent` returning on open |
| `OnTrigger` | [the enter loop](#spike-3-trigger) |
| `(Self as Actor)` | `((Self as ObjectReference) as Actor)`: FO4 casts a script type only to a relative (`target.self_as_actor`, now the one spelling for 12 sites) |

Shared fixes (Skyrim output changes, still valid Papyrus): a Float operand
of `%` is cast to Int; a cast of an expression already ending in a cast is
parenthesised (`(X as Int) as Float`); the generated `TES4SetStage` local is
`TES4_StageSet`, which no script variable shadows. `emit.commands.target_row`
is now the one place a row is swapped for its FO4 one; `emit_row`,
`_emit_mapped` (MAP rows) and `_convert_args` all ask it.

**Left (23):**
- 18 in scripts nothing in FNV attaches (dead): actor events (`OnDeath`,
  `OnCombatStateChanged`, `OnPackageEnd`, `OnEffectStart`) and casts in
  scripts the converter types `ObjectReference` for lack of an attaching
  record. Never bound, so never run.
- `QF_VDoctors`, `QF_Doctors`: bare `RemoveSpell Withdrawal*` in a quest
  stage result script ("heal the player of addictions"). The GECK/CS wiki
  says only object and dialogue result scripts have an implicit reference;
  the converter casts the quest to an actor, which is None in Skyrim too.
  **Open:** what FNV runs it on (play Doc's addiction cure).
- Singles: `VES01VictorGSMyBodyguard` (a void read as Bool), `VMS03Quest`
  (`AddItem`'s result assigned), `50MGIncendiary` (an Enchantment cast to
  Spell). Settled in [the singles](#spike-3-else-text).

### <a id="spike-3-else-text"></a>The three singles (2026-10-06)

- **Text after `else` is dropped by FO3/FNV's compiler.** VES01's
  `else GSVictorRef.AddScriptPackage …` became `ElseIf <void call>`. FNV's
  bytecode (`SCDA` read from `FalloutNV.esm`) has every one of the 18
  `else <text>` lines in 13 scripts as a bare 2-byte `else`, the next
  statement being the else body: the text, `else if <cond>` included, never
  ran. The converter had made all 18 `ElseIf <text>`, adding a test FNV never
  made to 12 scripts that compiled. The parser now takes
  `else_takes_condition`; the converter turns it off for FO3/FNV, the text
  goes to `If.else_dropped` and a note on the `Else`. TES4 keeps reading
  `else <cond>` as an elseif (not checked against Oblivion's bytecode).
- **`set x to <call returning nothing>`.** FNV's `AddItem` returned 0, so
  VMS03's `set rCharge to player.additem …` gave the item and cleared
  `rCharge`; Papyrus's `AddItem` returns nothing. A row flagged `void`
  (`AddItem` so far) is emitted as the call, then the variable's empty value
  (`command_rows.void_assign`).
- **`50MGIncendiaryScript` is dead.** It casts the enchantment
  `EnchFlamerEffect`, which Papyrus cannot, but no record in FNV names the
  script, so it joins the unattached ones. A live case would need a record
  side spell made from the enchantment's effects.

### <a id="spike-3-vmad"></a>FO4 VMAD

`fo4_import/base/vmad.py`: `object_scripts`, `info_fragments`,
`quest_fragments` (stage fragments and alias scripts), and `read_entry`. It
reuses the shared script entry packer (`script_convert.pipeline.script_entry`,
`pack_wstring`), since FO4's entries and properties are laid out as Skyrim's.
Against `Fallout4.esm` (measured 2026-10-05):

| Kind | Re-packed identically |
|---|---|
| INFO fragments | 520 of 521 (1 uses a property type the packer does not write) |
| Quest fragments with form-bound properties | 169 decodable; all 20 sampled identical. 125 more bind properties to quest aliases, which converted scripts do not |
| Object scripts | 673 of 1,018; 218 more differ only in property order (vanilla sorts by name; the packer writes objects, then values; properties bind by name); 127 use strings, structs or alias-bound objects |

Tests: `tests/test_fo4_vmad.py` (three vanilla records, byte for byte).

### <a id="spike-3-end-to-end"></a>End to end: Doc's script on his stand-in (played)

```bash
py -3.14 -m fo4_import.spike.dialogue --export export/FalloutNV.esm --out <esp> --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm
```

`fo4_import/spike/script.py` puts the converted `GSDocMitchellScript` on the
Doc Weathers stand-in (ACHR VMAD) and compiles it and the FO4 helper set with
FO4's compiler into `<Data>/Scripts`. Properties filled: `TES4AV_Variable01`
and `TES4AV_Health` (the spike's actor values: FO4's `Health`, and the
plugin's own `FNV_Variable01` record, made the way the spike makes FNV
skills, since FO4 has no `Variable01`), `TES4PlayerControls` (a
start-game-enabled helper quest carrying `TES4_PlayerControls`). Left unfilled:
`VCG01`, `VDoctors`, `TES4CombatApproaches`, `TES4ControlsDisabled`,
`TES4ForceCombatAttackers`, `Sawbones`, `FadeToBlackISFX` (not converted).

What to see: the script binds (no binding errors in the Papyrus log); talking
to Doc still opens his menu (the script blocks activation and passes it on,
as FNV's `onActivate: if IsTalking == 0, Activate`); `setav FNV_Variable01 1` on
him runs his medical sequence: the player's controls off for 8 seconds, then
back on.

### <a id="spike-3-timing"></a>Update loop timing on Fallout 4

Measured 2026-10-05 with a traced copy of Doc's script (`Debug.TraceUser`
on each tick; the converter unchanged): `setav FNV_Variable01 1` turned
controls off at 43.62 s and on at 51.68 s of real time, 8.06 s for FNV's 8.

- One timer chain: `OnInit`, `OnCellAttach` and `OnLoad` each start the
  timer, and FO4's `StartTimer` on the same id replaces the pending one.
- A `StartTimer(0.1)` fires every 0.175–0.188 s. The converted loop
  subtracts measured real time, so its counts hold; anything counting ticks
  instead would run about 1.76 times slow.
- Timers stop while a menu is open (here the console); the loop's clamp
  turns that gap into one 0.1 s step, as in Skyrim.

### <a id="spike-3-helper-plugin"></a>The shared helper plugin (played 2026-10-05)

```bash
py -3.14 -m fo4_import.helpers_plugin --out <Data>/TES4Helpers.esl
```

`TES4Helpers.esl` (ESM + ESL flags, master `Fallout4.esm`) holds what every
converted FO3/FNV plugin needs and no source plugin has, once for all games,
since it is player or actor state:

| Object ids | Records |
|---|---|
| `0x800`–`0x809` | AVIF `TES4Variable01`–`10` (FO4 has no Variable actor values) |
| `0x810`–`0x81E` | AVIF per FO3/FNV skill (`TES4Barter` … `TES4Unarmed`; FO4 has no skills) |
| `0x900`, `0x901` | start-game quests running `TES4_PlayerControls` and `TES4_CharacterEvents` |
| `0xA00` | GLOB `TES4ControlsDisabled` |

The ids live in `script_convert/constants.py` (`FALLOUT4_HELPER_*`) and are
a save contract: append only. Converted plugins list the helper plugin as a
master; `helpers_plugin.actor_value_form` and `helper_forms` give the FormIDs
a plugin writes for them, by its master index.

- `TES4Polyfill.AV(name)` is generated from `target.fallout4_actor_values()`:
  Fallout4.esm's ids read from `Fallout4.esm`, the rest from the helper
  plugin. Names match in any case (Papyrus string compare), and the Skyrim
  skill names the shared helpers still use (`Lockpicking`, `Speechcraft`,
  `Smithing`) read the FO3/FNV skill.
- On the Fallout 4 target an FO3/FNV skill or variable keeps its own name
  (`TES4AV_EnergyWeapons`) instead of Skyrim's folding (Barter and Speech
  into `Speechcraft`) or dropping (Guns, Medicine, Science…).
- The FO3/FNV values FO4 has under another name (resistances, `SpeedMult`,
  `ActionPoints`) are character-systems work and not mapped here.
- The spike masters the helper plugin (`Fallout4.esm`, `XDI.esm`,
  `TES4Helpers.esl`) instead of making its own actor values and controls
  quest; each skill's first use still takes the FormID its spike record had,
  so no line moved.

### <a id="spike-3-vdoctors"></a>A converted quest: VDoctors (played 2026-10-05)

FNV's doctors do their work in the shared `VDoctors` quest: stage 10 heals
(`Player.ResetHealth`), 20 cures addiction (`RemoveSpell Withdrawal…` ×13 and
a message), 30 clears radiation (`player.RestoreAV RadiationRads 1000`), 40
has no script. Doc's script sets stage 10 when his treatment ends; his
100-cap line sets 30.

- **A quest stage's result script runs on the player.** FNV's per-entry stage
  runner (`0x60FB60` in the GOG `FalloutNV.exe`) calls `Script::Execute`
  (`0x5AC1E0`, as JIP names it) with the player singleton (`0x11DEA3C`) as
  `thisObj`, after checking the entry's conditions against the player too.
  So stage 20's bare `RemoveSpell` acts on the player, which is how the
  doctors cure addiction. The converter emitted `(Self as Actor)` on a
  Quest, which FO4's compiler rejects (the `QF_VDoctors` and `QF_Doctors`
  open question in [the remaining failures](#spike-3-singles)); a call with
  no receiver in an FO3/FNV quest stage fragment is now `Game.GetPlayer()`
  (`script_convert/implicit_subject.py`). FO3 is assumed to share the
  runner; only FNV was disassembled.
- **`RadiationRads` is FO4's `Rads`.** Vanilla FO4 scripts heal radiation
  with `RestoreValue(Rads, n)` (doctor and RadAway scripts), so on Fallout 4
  the name maps through `constants.FALLOUT4_FALLOUT_AV_RENAMES` instead of
  being dropped as a value Skyrim lacks.
- **In the spike**, `VDoctors` is a start-game quest with FNV's four stages,
  each with one log entry, and `FALLOUTNV_QF_VDoctors` attached by quest
  VMAD (`Fragment_Stage_0010_Item_0` …). Doc's script and the 100-cap line
  fill their `VDoctors` property with it. Its object id is fixed (`0x1000`,
  `script.QUESTS`), outside the spike's sequential ids, because the lines
  naming it are packed before the sequence reaches the end. The withdrawal
  spells, `AddictionRemovalMsg` and `Generic` stay unfilled: FO4's addictions
  are its own effects, and the message and the generic quest are not
  converted.
- **Played:** paid treatment restores health and the 100-cap line clears
  rads; `sqs VDoctors` shows stages 10 and 30 done.

### <a id="spike-3-fragments"></a>Dialogue fragments (played 2026-10-05)

`script.Fragments` gives every spike INFO whose FNV INFO has a converted
`FALLOUTNV_TIF__<id>` script its INFO VMAD (`Fragment_1` on begin,
`Fragment_0` on end): 29 of the spike's INFOs. Properties are filled from
the spike's actor values and from Fallout4.esm records of the property's type
with the same editor ID (`Caps001` `0000000F`, `Stimpak` `00023736`,
`WaterPurified` `000366C0`). Played: Doc's paid treatment takes the caps and
runs his 8-second sequence from his own line; the stimpak and water lines give
their items; barter opens.

- **No FormID drift.** The spike packs INFOs as it hands out ids, so a
  fragment needing a new plugin actor value would shift every later line (and
  its voice file name). The build runs twice: the first pass lists the actor
  values fragments need and gives them ids last, the second packs with them.
- **A fragment links only when every script type it names exists.** The water
  line names `FALLOUTNV_HD00RobotQuestScript` (an unfilled property) and was
  skipped whole ("Unable to link type of property") until that script was
  compiled too; `script.with_types` compiles the converted scripts a fragment
  names, transitively.
- **Random piles chain per condition set.** Ron's goodbye pile is three "sir"
  and three "madame" lines; one chain over all six left a male player with no
  passing reply about one time in three, stuck in the menu. Each set of
  same-condition members now gets its own chain and its own unconditioned last
  member.
- **The helpers' line bookkeeping is silent, not broken.** `LineBegan` and
  `LineEnded` read `Variable03`–`09` through `TES4Polyfill.AV`, which returns
  None on FO4; `GetValue(None)` reads 0 without a log line. It still needs
  the shared actor values ([helpers](#spike-3-helpers)).
- **The stand-ins' own FO4 dialogue competes with ours.** A `--trace` build
  (a debug quest logging scene, alias and per-actor state to
  `FNVSpikeTrace.0.log`) showed Doc in vanilla `DoctorGreetScene` (`0005FD39`,
  the doctors quest's greeting, some lines `GetIsID` Doc Weathers) and Ron in
  `WorkshopVendorBarUniqueScene` (`0019235F`) when they greet the player
  unprompted; ours needs `GetPlayerActivated`, so theirs wins then. Converted
  NPCs are new records without those ties, so this stays a stand-in artifact.
- Doc's barter line keeps the scene running (FNV returns to the conversation
  after barter), so the menu box stays under the barter menu.

### <a id="spike-3-names"></a>Script names

Two scripts sharing a name is a bug only a play-test shows: the later write
replaces the earlier, and the compile gate sees just the survivor.
Measured 2026-10-05:

- **Within one game's run:** 17,679 names, each written once. Since then
  `pipeline.refuse_duplicate_names` stops the run on a name written twice
  with different text (the same text twice is harmless), naming each source.
- **Against Fallout 4's own scripts:** 0 of our names among its 10,260 (Base
  and F4SE).
- **FO3 and FNV in one Data folder:** the games share many EditorIDs, so
  each game's scripts carry its prefix (`FALLOUTNV_`, `FALLOUT3_`), as in the
  Skyrim fork. `script_convert.pipeline`'s command line now sets it as
  `convert.py` does (it used the generic `TES4_`), so the gate compiles the
  names that ship. Once FO3 is converted, compiling both corpora into one
  folder checks the two games against each other.
- The shared helpers ship once; every game's build must carry the same
  version.

FO4's script namespaces (`FalloutNV:Name`) could replace the prefix and the
hashed short names (`..._CB26`); decided with VMAD, which records the names.

### <a id="spike-3-gate"></a>The corpus compile gate

```bash
py -3.14 -m script_convert.pipeline export/FalloutNV.esm -o temp/fo4_scripts/FalloutNV.esm --target fallout4
py -3.14 tools/script/compile_papyrus.py --game fallout4 --src temp/fo4_scripts/FalloutNV.esm --out temp/fo4_pex --baseline tools/script/fo4_compile_baseline.json
```

The pipeline converts every FNV script for Fallout 4 (the FO4 helper set:
`static_scripts/fallout4/` adds to and replaces `static_scripts/`). The
compile uses FO4's own compiler, one `-all` batch per worker, and splits
failures into files with their own errors and files that fail only through a
script they use. Error kinds fold converted script names to `<script>` and
keep native names, so a missed Skyrim call shows up by name. Against the
baseline it exits 1 when more files fail or an error kind grows or is new;
`--write-baseline` records an improvement.

**Only what changed is compiled.** `<out>/compile_state.json` keeps each
script's source SHA-1 and result; a run compiles the scripts whose source
changed plus every script naming one of them, transitively (a script can fail
through one it uses), and takes the rest from the state. No state, other
include folders, or `--full` compiles everything. A narrow converter fix
recompiles tens to hundreds of files; a change to a helper every script
names (`TES4Polyfill`) is still a full run. Each compiled script's old
`.pex` is deleted first: before, a script that stopped compiling still
counted as compiled through the `.pex` an earlier run left.

**First full run (2026-10-05):** 19,552 scripts converted with 0 errors
(17,697 files); **16,640 compile (94.0%)**. All 1,057 failures are their own
errors (none only through a helper), by file:

| Files | Error | Cause |
|---|---|---|
| 804 | `SendModEvent` | SKSE mod events (8 command rows) |
| 90 | `OnTrigger` | FO4 has no such event |
| 86 | `SetDontMove` | no FO4 native |
| 49 | `EnableFastTravel` | on `InputEnableLayer` in FO4, not `Game` |
| 11 | `OnDeath` on a script FO4 cannot give it | to read |
| ~15 | singles: a fragment parse error, `HasLOS`, `OnMagicEffectApply` parameters, a modulus of floats, an enchantment cast | to read |
| 7 | the 7 helpers above | listed |

Baseline: `tools/script/fo4_compile_baseline.json`.

**`SendModEvent` (2026-10-05): 98.5%** (17,425 of 17,698). It came from
FNV's `RewardXP` (903 uses) and the character menus (6). Where FO4 has
FNV's own feature the FO4 row uses it: `RewardXP` → the native
`Game.RewardPlayerXP`, FO4's own XP and notification. The menus (SPECIAL with
a point total, tag skills, traits) have no full FO4 native (`ShowSPECIALMenu`
takes no total), so they become one custom event,
`TES4_CharacterEvents.CharacterMenu(kind, value)`, for the FO4 character
rules to answer; the FO4-only helper `static_scripts/fallout4/TES4_CharacterEvents`
sends it, since only the declaring script may. The one `SendModEvent` left is
in `TES4Polyfill` (helper port).

## <a id="spike-2"></a>Spike 2: one interior cell

Doc Mitchell's house:

- statics, lights and doors;
- meshes through a minimal FO4 mesh writer plus BGSM/BGEM materials;
- textures re-encoded;
- FaceGen for Doc from the CK;
- no precombines.

fnv-to-fo4's format facts serve as a checklist
([research](research/fo4_target.md#fnv-to-fo4)), with NifSkope 2.0.dev11's
`nif.xml` as the layout reference.

Order, by risk: one FNV static rendering in FO4 (mesh, material, textures,
placed in QASmoke, no collision); then Doc's house cell (208 statics, 134
misc items, 25 lights, 14 furniture, 11 containers, 11 activators, 2 doors
in `GSDocMitchellHouse` 00103DF9); then collision; then FaceGen.

### <a id="spike-2-nif"></a>The FO4 NIF reader and writer

`fo4_import/nif/` reads and writes 20.2.0.7 files at BS stream 130:
`file.py` the header (export strings kept), block list, string table and
roots; `blocks.py` the blocks a static mesh uses, as dicts: NiNode and
BSFadeNode, BSXFlags, BSTriShape (unskinned; half or full precision
positions, UV, normal, tangent, colour), BSLightingShaderProperty (default
and environment-map types), BSShaderTextureSet, NiAlphaProperty. Other block
types are kept as raw bytes.

**Checked against vanilla (2026-10-06):** all 32,397 of `Fallout4 -
Meshes.ba2`'s 34,995 meshes that hold only supported shader types and no
skinned shapes rebuild byte for byte (75,173 BSTriShape, 79,925 lighting
shaders, 97,312 nodes). A shape with no vertex data (particles) keeps its
stored counts. The 2,598 refused use skin, face, hair or eye shaders or
skinned shapes, none of which a static needs. Vanilla meshes and materials
are unpacked to `references/fo4_assets/` (BSArch) for this.

### <a id="spike-2-bgsm"></a>BGSM materials

`fo4_import/nif/bgsm.py` reads and writes the binary `.bgsm` a lighting
shader names: the Material Editor's BaseMaterialFile fields (tiling, UV,
alpha blend and test, z-buffer, refraction, environment mapping), nine
texture paths, the BGSM lighting fields (rim and back light, subsurface,
specular, smoothness, fresnel, wetness), the root material, emittance (its
colour only when on) and the flags after it. Strings are u32-length and keep
their null. NifSkope's `BSMaterialDataBGSM` is its in-memory view, not this
file layout.

**Checked against vanilla (2026-10-06):** every `.bgsm` in `Fallout 4 -
Materials.ba2` is version 2, and all 6,616 rebuild byte for byte.

### <a id="spike-2-static"></a>An FNV static as an FO4 mesh (played 2026-10-06)

`fo4_import/nif/convert_static.py` reads the FNV mesh with pyffi and writes:

- one BSTriShape per visible NiTriShape/NiTriStrips, its transform to the
  root baked in, triangles from pyffi's strip reader (degenerates dropped),
  under a root NiNode; collision is left out (vanilla ClutterGenShelfA has
  none either, nor a BSXFlags);
- the vertex layout of vanilla statics (`0x1B00000430205`: half position,
  UV, normal, tangent; `0x3B00005430206` with vertex colours);
- **a tangent frame computed from positions and UVs.** FO4 stores dP/dv in
  the field nif.xml calls *Tangent* and dP/du as the *Bitangent* (measured on
  15,013 vanilla SetDressing triangles: 0.94 and 0.96 agreement, ~0 the
  other way);
- a lighting shader naming `materials\fnv\<diffuse path>.bgsm` (shader
  values and a 10-slot texture set from vanilla ClutterGenShelfA), and an
  NiAlphaProperty when FNV had one;
- the material: every field the most common value over the 6,616 vanilla
  BGSMs, FNV's diffuse and normal map, its alpha blend and test (same
  blend-function enum in both). Shapes with the same textures and alpha
  share it.

Textures keep their FNV paths under `textures\fnv\`.

**Specular.** First played (2026-10-06): the shelf looked right, the wall
corner shiny. Vanilla: 6,236 of 6,616 BGSMs have a specular map; of the 380
without, 271 turn specular off. The first build had no map and specular on
at full smoothness. FNV keeps specular in the normal map's alpha, so a shape
whose normal map carries a mask (`asset_convert/texture/spec_mask`, the rule
the Skyrim side uses; the mesh's material colour, black on every test shape,
is ignored) gets an `_s.dds` beside it: BC5 (`dds_codec.write_normal_dds`),
R the alpha, G the smoothness from FNV's glossiness by the Blinn-Phong to GGX
relation `1 - sqrt(2 / (power + 2))`. No mask, or a non-square map: specular
off. In the test set the wall corner's wall and floor have none.

### <a id="spike-2-bgem"></a>Glass: effect shaders and BGEM

Second play: the rack's glass did not show. FNV's glass is an alpha-blended
lit shape (diffuse alpha a flat 132, a cube map in texture slot 4). In
vanilla FO4 only 340 of 6,616 BGSMs blend, almost all hair, beards and lashes;
glass is effect-shader material: 283 `.bgem`, 81 named glass. So an FNV
shape that alpha-blends and is not a decal becomes a BSEffectShaderProperty
naming `materials\fnv\<diffuse>_effect.bgem` (fnv-to-fo4 does the same),
with FNV's diffuse, normal and cube map and its blend.

The template is vanilla's own small glass prop, `ChemistrySetBeaker01`
(its BGEM and its mesh's shader block): a near-black base colour
(0.18–0.20, scale 0.2), edge falloff (opacity 0.5 facing, 0.9 at the
edge), lighting influence 0.95, environment map scale 2, two-sided. The
first build used the most common value over all 81 glass BGEMs instead,
mostly windows (white base, scale 1, no falloff), and FNV's mid-grey glass
texture (RGB ~150, alpha 132) came out as white tinted glass (third play,
2026-10-06).

`fo4_import/nif/bgem.py` reads and writes version 2 (the only version
vanilla ships): BaseMaterialFile, five textures, the effect fields. **Checked
against vanilla (2026-10-06):** all 283 `.bgem` rebuild byte for byte, and
all 10,787 BSEffectShaderProperty blocks in the 32,397 readable meshes.

### <a id="spike-2-cell"></a>Doc Mitchell's house as an FO4 cell (played 2026-10-06)

`fo4_import/spike/cell.py` rebuilds one FNV interior cell, by EditorID, in
its own plugin: `coc FNV_GSDocMitchellHouse`. Of the house's 434
references, 427 are placed:

- **Lighting:** FNV's XCLL colours, fog, directional light and fog power,
  inheriting nothing from the lighting template. FNV's ambient colour also
  fills FO4's six directional ambient colours. The fields FNV lacks, and the
  template and imagespace, are QASmoke's.
- **Objects:** every base with a mesh becomes a static of that mesh (204),
  whatever its FNV type (STAT, MISC, FURN, CONT, ACTI, MSTT, items).
  Containers, furniture and pick-ups come later.
- **Markers:** FNV's engine statics below 0x800 are editor markers. The
  three Fallout4.esm shares by FormID and EditorID (COCMarkerHeading,
  XMarkerHeading, XMarker) keep their base, and the rest are dropped
  (AudioMarker). Engine-range items, such as caps, are converted.
- **Lights:** FO4 LIGH with FNV's radius, colour, fade and flags. The rest of
  DATA is the most common vanilla omni light (604 of 801: falloff exponent
  1, FOV 90, near clip 7.217, attenuation 0/1/2). XRDS on a light reference
  is an offset to the base radius in both games: across 6,802 FNV light
  references, base plus XRDS is always positive, including 2,259 negative
  offsets, and xEdit's `wbREFRRadiusToStr` adds the base. It is copied
  unchanged.
- **Doors:** a door with a teleport leads to a stand-in copy in QASmoke at
  (-1700, -1184, 0). The copy leads back to where its FNV partner door led
  in.
- **Skipped:** 4 trigger activators with no mesh, 2 sounds and Doc himself.

Played: the house looks right. Its fog and colour cannot be judged yet, because its imagespace and FO4-only lighting fields are QASmoke's, which shows the same haze.

The house's 206 models brought two shading cases the first statics did not
have:

- **Unlit shapes.** The house has 39 FNV `BSShaderNoLightingProperty`
  shapes: painting and furniture shading layers, window panes, light rays and
  liquids. Most have no texture and are drawn with vertex colours and alpha.
  They become effect shaders with no material file: vanilla writes 1,104
  untextured ones, plus 323 with vertex colours. These draw without scene
  lighting, use FNV's texture, vertex colours and vertex alpha, write depth
  unless they blend, and are two-sided under a `NiStencilProperty`.
- **Glass is blending plus an environment map.** Every blended lit shape
  used to be glass. In the house, the 22 blended shapes with an environment
  map are glass or clear plastic (windows, beakers, blood packs, a clock
  face). The 7 without one (fan blades, stains, a screen, a gourd) stay lit
  BGSMs with their blend. A `NiStencilProperty` also makes a BGSM two-sided.

### <a id="spike-2-collision"></a>Collision through Elric (played 2026-10-06)

Vanilla FO4 meshes hold only Elric's output: `bhkNPCollisionObject` (14
bytes: target, flags, system, body id) and a `bhkPhysicsSystem`, a Havok
2014 (`hk_2014.1.0-r1`) packfile of hknp data. Of the old blocks there are
none: 26,992 and 22,426 of those two and nothing else, across the readable
meshes. So nothing writes hknp; FNV's collision goes in as the old blocks
and the CK's Elric (`Tools\Elric\Elrich.exe Settings\PCMeshes.esf
-ElricOptions.ConvertTarget=... -ElricOptions.OutputDirectory=...`) builds
the physics, as fnv-to-fo4 does.

`fo4_import/nif/collision.py` writes FNV's blocks in nif.xml's stream-130
layout. FNV Havok units are game units / 7 and FO4's game units / 69.99
(NifSkope's Havok scale is FO3's × 10 from Skyrim on), so lengths × 0.1 and
inertia × 0.01. Layers 0-28 keep their numbers (the names match) and the rest
map by name. FNV's 32 materials and their stairs variants map to FO4 material
CRCs. A body on a child node gets its own NiNode with that node's transform.
The root's BSXFlags are FNV's, keeping Havok, Complex, Dynamic and
Articulated. Every vanilla mesh with root collision has a BSXFlags: statics
mostly 0x82, clutter 0xC2. FNV writes 0x2 and 0x42.

What Elric accepts (2026-10-06, measured by running it on minimal files):

- **Block order.** Every block must come after the blocks it references:
  shape, body, then collision object. A box shape converts in that order and
  crashes Elric (access violation) in every other.
- **Mesh shapes.** FNV's `bhkMoppBvTreeShape` → `bhkPackedNiTriStripsShape`
  crashes it, with or without the MOPP tree (scaled origin and quantisation).
  It converts as `bhkNiTriStripsShape` with one `NiTriStripsData` per FNV
  sub-shape: game-unit positions, each a 3-point strip, the material CRC in
  the data, the filter in the shape. This is what NifSkope's OBJ-as-collision
  import and fnv-to-fo4 write. Elric builds the tree itself.
- **Coordinates.** Elric keeps them: the telephone's convex hull comes out
  with FNV's vertices × 0.1 (-0.1545, 0.1498, 0.2002) and radius 0.01.
- **Render blocks.** Elric changes them too: it sets the vertex-colours bit
  in a lighting shader's flags2 (0x11 → 0x31). So `fo4_import/nif/elric.py`
  keeps our blocks and grafts in only its two physics blocks per body,
  matched by node name.

**Winding.** First play: the floor held in some places and dropped the player
in others. FNV collides with both sides of a triangle and FO4, like Skyrim,
with one, and FNV's mesh collision has many triangles wound downwards: in the
house 57 models, about half the triangles of most Craftsman room pieces. The
mesh path now takes its triangles from asset_convert's winding repair
(`repaired_mesh_soup`: each collision face takes the facing of its render
twin, else of its coplanar neighbour, and FNV floors met only from below get
a reversed copy; [winding](../commentary/asset_convert_collision.md#inverted-collision-winding-i-fall)),
the same code the Skyrim converter runs. 1,076 triangles flipped. Second
play: the floors hold.

Materials ride through the repair per triangle (`repaired_mesh_soup`'s
`materials_of`): each mesh triangle takes its FNV packed sub-shape's
material (those sit on the data block at 20.2.0.7), mapped straight to FO4.
The repair's own list is Skyrim CRCs built from `shape.sub_shapes`, empty
for FNV, so through it all 64 of the house's mesh collisions were stone; now
they are FNV's (wood 38, stone 10, hollow metal 8, metal 6, glass 5, chain 5,
cloth 4). The Skyrim converter still has that stone default and reads FNV
material numbers with Oblivion's meanings (FNV 14 bottlecap → snow).

Doc's house: all 172 meshes with collision convert (165 with one body, 7
with two), with no Elric crash, in one 17-second build. Clutter (MISC,
ALCH...) keeps FNV's dynamic body while it is placed as a static.

### <a id="spike-2-transparency"></a>Blended lit surfaces (played 2026-10-06)

FO4 does not draw an alpha-blended lighting-shader surface unless it is a
decal. Doc's hospital screen cloth and ceiling fan (blended BGSMs) were
invisible; in-game splits in Doc's house and QASmoke ruled out the cell,
our BGSMs, textures, file structure, normals, winding, the alpha property,
Double_Sided, root material and vertex colours. Vanilla's own blood pack
tabs (`Props\BloodPack.nif`, blended non-decal BGSM) are invisible too, from
an unmodded Steam launch; the BloodPack Mesh Fix mod (Nexus 25800) makes
them an opaque environment-mapped lit shader. Of Fallout4.esm's 340 blended
BGSMs, 253 are decals; the 87 others are LOD, placeholders, the blood pack,
the mobster glasses and an unused Diamond City TV. FO4's own translucency is
the effect shader (glass, insect wings), alpha test (cloth, foliage, hair)
or a decal.

FO3/FNV use blended lit surfaces widely: of 14,909 FNV meshes, 2,159 have a
blended non-decal lit shape and 366 a blended decal (FO3: 1,431 and 262 of
10,989). Over the 241 textures of FNV/FO3 blended, non-decal,
non-environment-mapped lit shapes (1,013 shape uses), the share of seen
texels (alpha 8 and up) that are partly transparent (below 247) is bimodal:
546 uses below 20%, 337 at 50% and up (glass panes, neon tubing, Doc's
cloth at 81%), the middle mostly FNV hair and graffiti.

`convert_static._material` therefore maps a blended lit FNV shape by kind:

- environment-mapped (glass): vanilla's beaker BGEM, as before;
- decal (`sf_decal_single_pass` or dynamic): a blended BGSM with `decal` and
  the shader's Decal and Dynamic_Decal flags (vanilla's blended decals);
- a texture at least 50% partly transparent: vanilla BloatflyWing's BGEM
  (lit, blended, no falloff) and its mesh shader values;
- otherwise a cut-out: alpha test at FNV's threshold when it had one, else
  vanilla's commonest 128, blend off (Doc's fan texture is 240-255).

### <a id="spike-2-facegen"></a>FaceGen and FNV faces (played 2026-10-06)

The CK exports FaceGen from the command line: `CreationKit.exe
-ExportFaceGenData:<plugin> W32`. It writes
`Meshes\Actors\Character\FaceGenData\FaceGeom\<plugin>\<id>.NIF` (every head
part as a skinned BSSubIndexTriShape in one head-local frame) and the face
tint textures (`_d`, `_msn`, `_s`). Run through MO2 (`ModOrganizer.exe run -e
"Creation Kit" -a ...`), it loads the profile's plugins and writes into
MO2's overwrite (35 s for Doc). CKPE (loaded through `winhttp.dll`) needs
its address library for the CK version in `CKPEBins\`, or it stops the CK.

**Doc's face, three ways, side by side.** Each is a clone of the dialogue
spike's stand-in (DocWeathers 0012FCCB) without its face shape
(MSDK/MSDV/FMRI/FMRS), so all three share head parts, tints and body:

- **A**: FO4's default male face.
- **C1**: FO4's default face moved by Doc's FNV FaceGen offset from FNV's
  mean face.
- **C2**: FO4's head moved onto Doc's FNV head surface itself.

FNV's head is the race's head part (`headhuman.nif`) plus its `.egm`: 50
symmetric and 30 asymmetric modes, a float scale times int16 x/y/z, over the
FaceGen vertex list (the mesh's 1,211 vertices, then the `.tri`'s 238
modifier vertices: 1,449). Doc is the mean plus FGGS (and FGGA, zero)
times the modes. His offset from the mean is small: 0.135 units mean, 0.66
max.

**Why not FO4's own face sliders.** HumanRace's male morph presets name
about 35 distinct morphs in `BaseMaleHeadCharGen.tri` (eyes, nose, ears,
lips) plus 5 two-way sliders. A bounded least-squares fit of them to Doc's
offset, carried onto FO4's head, captures 2.3% of it: they are local
features, and Doc differs in overall shape. FO4's overall shaping is the 32
region sculpts (FMRI/FMRS), which move 59 `skin_bone_*` face bones through a
per-vertex remap table in `BaseMaleHead_faceBones.nif`
(`CustomizationRemapData`, 12 bytes per vertex). That route is not built.
Instead `fo4_import/face/bake.py` moves the CK's exported head directly:

1. FNV's mean head is aligned to the exported FO4 head by a similarity fit
   over the front of the face: scale 1.008, mean residual 0.165.
2. Each FO4 head vertex gets C1's or C2's displacement from its nearest
   point on FNV's surface.
3. The displacement is smoothed, and fades to zero within 3 units of the
   body seam, so the seam does not move. The seam is read from topology. The
   face and each part sharing border with it (the rear head) have an outer
   open boundary loop, welded within 0.01, just over half-float precision.
   Its stretches shared between parts join head parts; the unshared rest is
   where the body joins. That is a 22-point ring from z -12.1 at the front
   of the neck to -5.7 at the back. A tighter weld (0.001) also pinned two
   forehead points 0.002 from the rear head's border.
4. Every part (eyes, mouth, hair, beard) moves with its nearest head
   vertices.

Positions are rewritten in the raw blocks. Vertex order, which FO4's
expression and lip morphs index, is kept, and so are skinning and normals.
Doc's face moves 0.13 mean and 0.46 max in C1, 0.11 and 0.45 in C2. C2 also
moves the skull and hair, about 0.2 to 0.4: FNV's skull shape differs from FO4's.

`fo4_import/spike/facegen.py` runs the CK, moves its files into the mod
folder, and bakes the C variants.

Played: all three render with FaceGen and look very alike; C1 looks right.
The shape offset is small. FNV's face texture (FGTS) is what is left to
carry (next).

### <a id="spike-2-face-texture"></a>FNV face texture (played 2026-10-06)

FNV draws a face with the race's head texture plus the NPC's FaceGen colour
offset. The `.egt` next to the head mesh (`FREGT003`, 256x256) holds 50
modes. Each is a **float scale** (falling from 0.22 for mode 0 to 0.02 for
mode 49) and then signed-byte R, G and B planes. The offset is FGTS × scale ×
plane, summed. The rows are stored **bottom-up**: the sum drawn top-down
smears features, and flipped it lands on the race texture's eyes, brows and
mouth.

Doc's offset is large: (-12, -24, -36) mean per channel and up to 98, a
warmer, darker, weathered face with shadowed eye sockets. FGTS carries much
of an FNV face's look.

The Skyrim converter's `facegen_egt` reads those 4 bytes as "unknown, flags"
and uses one scale (0.25, calibrated on one Oblivion race). That is mode 0's
own scale, but up to 12x too much for the later modes.

`fo4_import/face/texture.py` carries the colour onto FO4's face texture (the
CK's `_d`, 2048 DXT5) by geometry:

1. Each FO4 face texel is a point on FO4's head, found from its triangle in
   UV space.
2. `bake.align` places that point on FNV's head; FNV's UV there gives the
   FNV colour.
3. The new colour is padded 8 texels past each UV island, so filtering and
   compression do not bleed FO4's colour in.
4. texconv (the CK's, in `Tools\Elric`) writes the result as DXT5, keeping
   FO4's alpha.

Two variants, both with C1's shape:

- **T1**: FO4's face texture plus Doc's FNV offset.
- **T2**: FNV's face texture (race texture plus offset).

In both the eyes, brows, nose, mouth and ears land on FO4's. FO4's body tone
comes from the NPC's skin tone layer, still the stand-in's. In FNV the same
FGTS also colours the body (the race's `UpperBodyHumanMale.egt`), so the
neck seam may show a tone step.

**Skin tone is applied at runtime.** Four clones that differed only in their
Skin Tone layer colour (233,218,216; 128 grey; 255 white; 200,150,100) got
identical CK face textures, and FaceGeom NIFs that differ only in texture
paths. The game tints the face, hairline, rear head and body alike, by the
NPC's QNAM texture lighting (the stand-in's QNAM is its Skin Tone colour
/ 255). HumanRace's Skin Tone options are the TETI slot 12 ones (male
0x0484).

First play showed a skin step at the hairline. So each variant's overall
colour shift now goes into the tone: the face texture is scaled back, per
channel, to FO4's median over the face, and QNAM and the Skin Tone layer are
multiplied by the same ratio (T1 0.84/0.65/0.51, T2 0.93/0.76/0.61, patched
in place in the plugin).

Second play: T1 looks better than T2, but the hairline still shows in both.
T2's more. Moving FNV's texture across leaves a seam with FO4's own skin
parts; the next route recreates the face in FO4's own systems (sculpt
regions, tint layers).

### <a id="spike-2-sculpt"></a>Sculpt region fit (played 2026-10-06)

FO4's own face shaping: HumanRace has 32 male sculpt regions (FMRI
0x0-0xA, 0x36EF34BA-0x36EF34C7, 0x19-0x1B, 0x3C-0x3F) and 32 female ones.
Each has seven controls in FMRS: position x/y/z, rotation x/y/z, scale,
then 8 unknown bytes; 0 is no change, and the stand-in uses about ±1.
They drive 59 face bones.

The effect of each control is measured through the CK, not decoded.
`fo4_import/face/sculpt.py` writes a calibration plugin: a baseline NPC (the
stand-in without its face shape), then per region and control one NPC at
+0.5 and one at -0.5, 449 in all. The CK exports their heads, and the
central difference per face vertex is that control's effect. The basis
depends only on race and sex, so it is cached under `output/fo4_cache/`
(Bethesda geometry, never committed). A face is the bounded (±1)
least-squares fit to the target moves, written as FMRI/FMRS before FMIN.

**Measured (male HumanRace, 2026-10-06; calibration 5 min):**

- Of the 224 controls, 103 move the face. By kind: position x/y/z 21/28/30,
  rotation 5/1/2, scale 16. A control moves a vertex up to 0.81 at ±1 (p90
  0.37).
- Doc's target is the C1 moves (0.129 mean). The linear fit captures 77% of
  it: 144 controls used, 4 at the bound.

The controls are not linear over their range. The basis is measured at ±0.5
but the fit uses up to ±1, and the CK's actual export captures 56%. So
`spike.facegen` refines with the CK in the loop. It measures the exported
head, fits the miss with the same basis, adds the step to the values
(patched in place: an S NPC lists all 32 regions, so the record keeps its
size), and exports again. Doc: 56% → 69% → 70%. The residual is the shape
FO4's regions cannot make.

For comparison: FO4's morph presets alone capture 2.3%, and the direct bake
(C1) 100% by construction.

### <a id="spike-2-tints"></a>Tint layer fit (played 2026-10-06)

FO4's own complexion: HumanRace has 143 male tint options. There are 7
region masks (forehead, eyes, nose, ears, cheeks, mouth, neck), 59 face
detail patterns (most soft light), 5 dirt, 17 brows, 21 scars, 33 paint and
the skin tone. Brows are a style choice, and scars and paint are not
complexion. Skin tone (QNAM and the Skin Tone layer) takes the overall colour
shift, which the game applies at runtime to face, hairline and body.

An NPC layer is TETI (data type 1 value and colour, or 2 value only; the
option index) and TEND (value 0-100; for a colour layer RGBA and a template
colour index).

**What the CK accepts.** Two calibration attempts crashed it (CKPE writes the
zipped log to `Fallout 4\Logs\CKPE\Crashes`, which `spike.facegen.run_ck`
now checks):

- A colour layer with template index -1, in
  `BGSCharacterTint::Template::TextureSet`. A colour layer must name one of
  its option's TTEC template colours.
- A region mask as a value-only layer, in
  `BGSCharacterTint::Template::Mask` (null read). The masks have a mask
  texture but no TTEC, and no Fallout4.esm NPC uses them: all 8,618 vanilla
  NPC layers are type 2 with a 1-byte TEND (6,169) or type 1 with a 7-byte
  TEND (2,449), none on options 0x0493-0x0499.

So the fit uses value-only options (no TTEC) from the race's tint groups
(TTGP names them from the string table; TTGE closes each with its index):
Markings and Blemishes (44 male options: blemishes, moles, freckles,
creases, sunken cheeks, dark eye sockets, sunburn, red nose) and Brows (17,
see [hair](#spike-2-hair)). TETI slot 22 is not a complexion: it also holds
the Face Tattoos group, and a fit over the whole slot put a faint forehead
tattoo and a neck eagle on Doc (one at full value). Per option the calibration plugin has one NPC at full value; the CK's
face textures, reduced to 256x256, minus the baseline's are that option's
effect, taken as linear in its value (calibration about 1 min). The target is
T1's texture with its mean moved into the skin tone, fitted by bounded
least squares over the face UVs and refined with the CK's exports. The
refinement step is bounded to each value's remaining 0..1 range; a step
fitted in ±1 and clipped afterwards made each round worse (10% → 3% → 2%).

**Measured (Doc, 2026-10-06):** over slot 22 the linear fit captured 12% of
the spatial colour variation and the CK's export 10% → 11% → 11%; over the
complexion groups with a brow choice, 11% and 11% → 11% → 11%. Face details are fixed
patterns (freckles, wrinkles, blemishes), so they carry little of FNV's
FaceGen colour; the skin tone carries the rest.

**Played:** of S (stand-in tints), ST (fitted tints and skin tone) and ST1
(FNV colour baked), ST was chosen.

### <a id="spike-2-hair"></a>Hair, facial hair, eyes and brows (played 2026-10-06)

FO4 has no FNV hair, so `fo4_import/face/hair.py` picks FO4's nearest by
what each game draws. FO4 head parts sit in the FaceGen head's space (Hair33
from the archive matches the FaceGen NIF's copy vertex for vertex); FNV's are
moved there by the face alignment. `fo4_import/base/ba2.py` reads the game's
BA2s (GNRL, and DX10 as a one-mip DDS), so no reference copy is read.

- **Hair, facial hair:** surface samples with their texture's opacity, drawn
  from front, back, both sides and top over the FO4 skull (face and head
  rear parts), which hides what is behind it; 1.0 unit of slack, since FNV's
  skull differs. Opacity is pooled to 4-pixel blocks, and the part whose
  coverage differs least overall wins. Per-pixel or per-view scoring picked
  full caps for Doc's balding hair: strand noise and small views dominated.
  Facial hair is compared without its `_Hairline` extra part, a stubble
  decal that FNV carries in the face texture; with it every beard scored
  about 0.95.
- **Eyes:** the mean Lab colour of the iris ring, 12-28° off each eyeball's
  forward axis, with a sphere fitted to the eye mesh (FO4's eye mesh is only
  the front cap), sampled from each game's texture. The layouts differ, so
  no fixed texture region works.
- **Hair colour:** FNV's hair pixel shader (`SM3002` in
  `shaderpackage019.sdp`, disassembled with `d3dcompiler_47`) draws
  `lerp(base, _hl, _hl.a) x (1 + green x (2 HairTint - 1))`, so 2 x HCLR at
  full vertex green. FO4 hair is a greyscale diffuse looked up in
  `haircolor_lgrad_d.dds` (64 x 512, 32 bands of 16 rows): the CLFM's CNAM is
  the row, the grey x `grayscale_scale` the column. Hair colours are CLFMs
  with FNAM playable and remap-index bits; no vanilla NPC has a separate
  facial hair colour, HCLF covers both.
- **Brows:** FO4 brows are 17 value-only tint options (the Brows group), so
  they join the tint fit. FNV draws a brow mesh (in hair colour) over a head
  texture that already has brows; the mesh is drawn onto the target's face
  texels (each texel takes the nearest brow sample within 0.5 units). The CK
  draws a brow near full strength at any value: fitted linearly, six brows
  at 0.03-0.13 dropped the CK's capture to 3-6% against 13% predicted. So
  one brow, or none, is chosen at full value (each tried, the complexion
  fitted to the rest). FO4's base face texture has brows painted in, as
  FNV's does, and FO4's brow options are all dark: for Doc (silver brows
  over dark painted ones) none is chosen.
- **FNV head parts** have no type: centred below the eye mesh they are facial
  hair, above it brows, otherwise reported. The FNV export has no NPC PNAM
  and dumps HDPT as sizes, so both are read from FalloutNV.esm. `export\` is
  shared with the Skyrim fork, whose exporter has moved on, so the export is
  not redone from this repo.

An NPC record lists every head part, extras included (vanilla Doc Weathers:
eyes plus lashes, AO and wet layer). The clone drops the stand-in's eye,
hair and facial hair parts with their extras and adds the chosen ones with
theirs.

**Doc (2026-10-06):** HairMale08 (balding, 0.42), BigBeard20 (a mustache,
0.46), MaleEyesHumanBlue, HairColor04Silver; EyebrowM goes to the tint fit.

**Played:** STH (matched parts) beside ST (the stand-in's): face and hair
look right. What still reads as unlike FNV is the cell's overall colour and
tone (QASmoke's imagespace).

### <a id="spike-2-imagespace"></a>Imagespace: FNV's colour grading and tone (played 2026-10-06)

The cell used QASmoke's imagespace, so its colour and tone were FO4's.
`fo4_import/spike/imagespace.py` makes one FO4 imagespace per FNV one.

**FNV** (`ISHDRBLENDINSHADERCIN` in `shaderpackage019.sdp`) scales the scene
by an exposure, adds bloom and grades in display space: with Y =
dot(c, 0.299/0.587/0.114), c = lerp(Y, c, saturation), then lerp(c, Y x tint
colour, tint amount), then (c x brightness - pivot) x contrast + pivot. IMGS
DNAM's cinematic block (offset 96 in the 11 132-byte records, 100 in the
others) ends with a flags word: saturation 1, contrast 2, tint 4,
brightness 8. Across all 67 records it is 0, 2, 7 or 15, and records with it
0 hold values that cannot be in use (saturation 0.0, brightness 0.0 in
RCDefaultImageSpace): an unset value is not applied. Doc's ShackInterior01
(flags 7): saturation 0.9, contrast 1.2 about 0.14, a 50% tint toward
(0.69, 0.56, 0.30) x Y; brightness 1.1 unset.

**FO4** (DXBC blobs in `shaders011.fxp`, reflection stripped, found by what
they do): exposure clamped to the auto-exposure range, a Hable filmic curve,
its own cinematic (Rec. 709 luminance, pivot the adapted luminance), then a
pass that gamma-encodes (1/2.2) and samples up to four 16^3 LUTs blended by
weight, writing the result. A LUT is a 256 x 16 uncompressed 24-bit DDS, 16
slices of 16 x 16 (red across, green down, blue by slice); `colorlut.dds` is
the identity. Vanilla interiors grade only in the LUT: 180 of the 317
Fallout4.esm interior cells with an imagespace use DefaultImageSpaceF4LUT
(cinematic neutral, `ColorLUT_BaseInteriorAdjusted.dds`).

**Port:** DefaultImageSpaceF4LUT's HDR, exposure and depth of field, its
cinematic neutral, and a LUT holding FNV's grading of the identity (written
to `Textures\Effects\LUTs\FNV\<FNV EditorID>.dds`); the generated identity
matches `colorlut.dds` byte for byte. FNV grades the colours its renderer
leaves on screen, so the LUT grades FO4's display colours.

**Tone curve.** FNV has none: every pass of its HDR chain (`ISHDRDOWN*`,
`ISHDRLUMCLAMP`, `ISHDRADAPT`, `ISHDRBRIGHT`, `ISHDRBLUR`) writes a constant
alpha, so the final blend's `HDRParam.x / max(alpha, HDRParam.x)` is a slowly
adapting scale, plus bloom; the result is clamped. FNV also lights in gamma
space (sRGB textures times light), so against FO4's exposed linear colour c
it shows c^(1/2.2), clipped. FO4 shows (Hable(2c) / Hable(11.2))^(1/2.2)
(E = Tonemap E, 0.02 in the base). The LUT inverts FO4's curve and applies
FNV's straight one anchored where FO4 shows middle grey (0.18 shows at
0.393), so FO4's exposure, which adapts to middle grey, keeps the average
where it was. Below middle grey the curves nearly agree (FO4 0.1 / 0.3 ->
FNV 0.097 / 0.294); above it FNV is brighter (0.5 -> 0.518, 0.7 -> 0.811) and
clips at FO4 0.8 (8x middle grey), where FO4's shoulder rolls off to 5.6x
more. Anchoring at middle grey assumes FNV's adaptation targets the same
average; FNV's HDRParam is filled by the engine, not read here.

## <a id="decision"></a>Decision point

After spikes 1–3: the architecture plan (the `fo4_import` package, the asset
writers, the script back end, the runtime), or a stop.

## <a id="test-setup"></a>Test setup

MO2 instance `C:\Modlists\fo3fnv-in-fo4`. Spikes run in a minimal `Spike`
profile, one change per test:

- the game and DLC;
- F4SE, the Address Library and MCM;
- XDI and LevelUpMenuEx;
- Addictol (crash logger, with its engine fixes off if its INI allows);
- Hydra.

UFO4P and the engine-fix mods stay in the `Default`/`Play` profile, because
they edit vanilla records and engine code a spike may be measuring. Generated
plugins never master UFO4P. Vanilla censuses read the game's own
`Fallout4.esm` (the dump above), not MO2's merged view.
