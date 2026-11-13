# FO4 spikes: how FO3/FNV on Fallout 4 was shown buildable (done; work continues in fo4_pipeline.md)

Design only; status is in [ROADMAP.md](ROADMAP.md). The findings behind this
plan are in [research/fo4_target.md](research/fo4_target.md).

## Contents

- [Step 0: groundwork](#step-0)
- [Spike 1: dialogue](#spike-1)
- [Spike 3: one script](#spike-3)
- [Spike 2: one interior cell](#spike-2)
- [Scripted sequences as FO4 scenes](#scene-census)
- [Creatures on Fallout 4](#creature-census)
- [FormIDs: none counted](#formids)
- [Decision point](#decision)
- [Test setup](#test-setup)

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
- **Open (2026-10-10):** the silent `...` greeting a speaker needs (the talk
  breaks without it) adds an unskippable second or two to every
  conversation; wanted: a replacement for it.
- <a id="silent-line"></a>**Silent lines, built for a play-test
  (2026-10-19).** Every filler line now takes its text from
  `records.SILENT_LINE`, set to an empty line instead of `...`: the
  greeting that opens a talk scene (`Conversations.greeting`), a speaker's
  fallback greeting, the NPC line after [Leave], and an FNV line with no
  text. The INFO and its scene place stay (the talk broke without the
  greeting line); only its text is empty. The player's Hello is now
  answered too: the Greetings quest holds a Hello topic (`HELO`, DATA 0 7
  0x49 0, as DialogueGenericPlayer's 00018184) with one SILENT_LINE said
  by the player (GetIsID 0x7 on the subject, as vanilla's 52 player hellos
  test), and the quest's priority (the built quests' highest) outranks
  DialogueGenericPlayer's 10 (`Conversations.player_hello`). To test: the
  "..." subtitle and the player's "Hi" are gone, and the talk still opens
  and closes. If an empty line breaks the talk, set SILENT_LINE back to
  `...`.
  - Played 2026-10-19: no crash, but the greeting still took as long; it
    only looked as if nothing happened. A line with no voice file is held
    for a fixed time whatever its text. Fallout4.exe's compiled-in
    defaults (`tools/disasm/ck_settings_dump.py`): `fDialoguePaddedAudioLengthMin`
    2.5 s, `fDialogSpeechDelaySeconds` 2.0, `fSubtitleSpeechDelay` 1.5,
    `fSpeechDelay` 0.1 (FNV has only fSpeechDelay, 0.17). Fallout4.esm sets
    none of the first, so the engine pads every line to 2.5 s. Now, for
    the next play: each silent line plays a 0.2 s silent recording
    (`voice.silent_jobs`, .xwm without lips: the greeting and [Leave]
    lines under every converted voice type, the player Hello under
    PlayerVoiceMale01 and PlayerVoiceFemale01), and the plugin sets
    `fDialoguePaddedAudioLengthMin` to 0.2 (a new GMST, matched by
    EditorID; `cell.PADDED_SETTING`). FNV pads no line, so FNV's shortest
    recordings now also end with their audio. Two changes in one play: if
    the greeting is quick, both stay; if not, the setting is the suspect.
    NPCs whose voice type is a stand-in's vanilla one (no FNV voice
    folder) get no silent file.

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

### <a id="spike-1-force-greet"></a>Force greet (built: [greet trigger](fo4_pipeline.md#greet-trigger))

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

Not covered when 1a was built (all since built): voice ([voice](#spike-1-voice)),
the player's own "Hi" before a greeting ([silent lines](#silent-line)), and the
force greet ([greet trigger](fo4_pipeline.md#greet-trigger)).

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

### <a id="spike-3-target"></a>The target switch (done)

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
| Player controls | `controls_call`: the FO4-only helper `static_scripts/fallout4/F3NV_PlayerControls` holds the one shared `InputEnableLayer` |
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

Then still to do, since built: the pipeline's FO4 VMAD ([FO4 VMAD](#spike-3-vmad)),
filling `TES4AV_*` and `TES4PlayerControls` ([end to end](#spike-3-end-to-end))
and `TES4CharacterEvents` ([helper plugin](#spike-3-helper-plugin)).

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
  `TES4_BoundItemEffect` (FO3/FNV have no bound items). A `Script.Function`
  entry drops one function and the comment above it: `TES4Polyfill`'s
  `MirrorPlayerFactionRelation`, `GetIsCreature`, `IsGuard` and
  `GetDayOfWeek` read `Skyrim.esm` forms and have no FO3/FNV caller (0 in the
  FalloutNV.esm and Fallout3.esm exports, 2026-10-13: FNV's `GetDayOfWeek`
  converts to the `GameDaysPassed` property, its `GetIsCreatureType` is a
  different command). Fallout4.esm equivalents if one ever gains a caller:
  `PlayerFaction` `0x1C21C`, `ActorTypeNPC` `0x13794`, `GameDaysPassed`
  `0x39`.
- **Player-hating faction**: `ForceCombatNow`/`EndCombat` use Fallout4.esm's
  `PlayerEnemyFaction` (`0x106C2F`, sole relation Enemy of `PlayerFaction`,
  which returns it) where Skyrim used `WIPlayerEnemyFaction`.
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
| `EnableFastTravel`, `SetCanFastTravelFromWorld` | `F3NV_PlayerControls.FastTravel` (an `InputEnableLayer` setting) |
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
start-game-enabled helper quest carrying `F3NV_PlayerControls`). Left unfilled:
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
py -3.14 -m fo4_import.helpers_plugin --out <Data>/FalloutHelpers.esl
```

`FalloutHelpers.esl` (ESM + ESL flags, master `Fallout4.esm`) holds what every
converted FO3/FNV plugin needs and no source plugin has, once for all games,
since it is player or actor state:

| Object ids | Records |
|---|---|
| `0x800`–`0x809` | AVIF `TES4Variable01`–`10` (FO4 has no Variable actor values) |
| `0x810`–`0x81E` | AVIF per FO3/FNV skill (`TES4Barter` … `TES4Unarmed`; FO4 has no skills) |
| `0x900`, `0x901` | start-game quests running `F3NV_PlayerControls` and `F3NV_CharacterEvents` |
| `0xA00` | GLOB `TES4ControlsDisabled` |

The ids live in `script_convert/constants.py` (`FALLOUT4_HELPER_*`) and are
a save contract: append only. Converted plugins list the helper plugin as a
master; `helpers_plugin.actor_value_form` and `helper_forms` give the FormIDs
a plugin writes for them, by its master index. The same command writes
Cleanroom UI's `CleanroomUI.esl` beside it
([level-up plugin](fo4_level_up_plan.md#plugin)).

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
  `FalloutHelpers.esl`) instead of making its own actor values and controls
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
- *Quest tracking (fixed and played 2026-10-21).* Back in the Saddle
  (VCG02) showed in the Pip-Boy but would not take tracking: a click, no
  selection. Its record matched They Went That-a-Way's, which tracks, and
  its stages ran. FNV's `ForceActiveQuest` (VCG02 stages 5 and 10; VMQ02,
  VMS16, VMS16b: 7 calls) was dropped as a TODO; it is now FO4's
  `Quest.SetActive()` (`commands_falloutnv.quest_call`). Played:
  the quest is tracked when it starts and can be toggled.
- *Ghost Town Gunfight commands (built 2026-10-21, not yet played).* Its
  scripts (VMS16, VMS16b and their lines) dropped five FNV commands, now
  converted: `CompleteAllObjectives` (Quest native; 52 calls in FNV),
  `SetCellOwnership` (`Cell.SetFactionOwner`/`SetActorOwner`; with no
  owner the player, as FNV gave Goodsprings' houses, saloon and Doc's
  house to the player for siding with the Powder Gangers),
  `AddItemHealthPercent` (`AddItem`, FO4 items carrying no condition; the
  settlers' leather armor), `imod`/`rimod` (FNV's short forms of the
  imagespace modifier commands; the region now builds 9 more IMADs: the
  fades and cave transitions) and `IsKiller` (`GetKiller() ==`; a dead
  settler turns Sunny on the player only if the player killed him). Left
  as FNV had them: objective indices the quests never author, and
  `GetShouldAttack` (no FO4 equivalent).
- *A talking object (built 2026-10-21).* `StartConversation`'s speaker was
  cast `as Actor` for the Skyrim target's Say; Hoover Dam's control panel
  (`VHDControlOverrideBoxSCRIPT`, an ObjectReference script) talks, and the
  cast did not compile, the one script of 1,438 that failed. On Fallout 4
  the speaker stays an ObjectReference, which the polyfill and Say take:
  76 casts gone, 1,438 of 1,438 compile.

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
script's source SHA-1, its declarations (header, imports, custom events,
structs and their members, function and event signatures with their
defaults, properties) and its result. A run compiles the scripts whose
source changed. A script naming one of them (transitively) recompiles only
when that script lost or changed a declaration, which is all another script
compiles against, or, if it failed last time, when that script added one (it
may have failed on the missing function). A body edit or an added function
recompiles that script alone. Then the scripts naming one that started or
stopped compiling recompile, as a script can fail through one it uses. The
rest come from the state. No state, other include folders, or `--full`
compiles everything. Adding `ResponseBegan` and `LineOver` to `TES4Polyfill`
recompiled 17,678 scripts (15 minutes) before this rule; under it, 13 (the
polyfill and its failing users). A lost or changed function, event,
property or custom event recompiles only the users that also name it
(removing those two reached 16,959 scripts before); a changed header,
import or struct line reaches every user. Each compiled script's old
`.pex` is deleted first: before, a script that stopped compiling still
counted as compiled through the `.pex` an earlier run left. The scripts'
own folder leads the import list; the state's `imports` text keeps the
older order (own folder last) so earlier results still load, and
`own_first` marks a state made under the new one
([own source first](fo4_pipeline.md#own-source-first)). A script's saved
errors are FO4's compiler's or, for a source error Caprica found,
Caprica's ([whose failure](fo4_pipeline.md#caprica-errors)).

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
`F3NV_CharacterEvents.CharacterMenu(kind, value)`, for the FO4 character
rules to answer; the FO4-only helper `static_scripts/fallout4/F3NV_CharacterEvents`
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
R the alpha, G the smoothness from FNV's glossiness: `1 - (2 / (power +
2)) ** 0.25` (Walter's Beckmann alpha `sqrt(2 / (power + 2))` is GGX roughness
squared; the first build used it as roughness, see
[exterior](#spike-4-exterior)). No mask, or a non-square map: specular
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

`fo4_import/spike/cell.py` (run by `fo4_import.pipeline.run`) rebuilds one
FNV interior cell, by EditorID, in its own plugin: `coc FNV_GSDocMitchellHouse`. Of the house's 434
references, 427 are placed:

- **Lighting:** FNV's XCLL colours, fog, directional light and fog power,
  inheriting nothing from the lighting template. FNV's ambient colour also
  fills FO4's six directional ambient colours. The fields FNV lacks, and the
  template and imagespace, are QASmoke's.
- **Objects:** every base with a mesh becomes a static of that mesh (204),
  whatever its FNV type (STAT, MISC, FURN, CONT, ACTI, MSTT, items).
  Containers, furniture and pick-ups came next ([items](#spike-2-items),
  [furniture](#spike-2-furniture)).
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

**Rotated nodes.** An invisible low wall stood in front of the oven. FNV
has no collision there; it was the shack cabinet's door boxes
(`dlc04shackcabinet01door.nif`, a `bhkRigidBodyT` offset 16 units along
its node, whose parent turns 90°). Reading Elric's output (each
`hknpBodyCinfo`'s position at +48 and orientation at +64 of its 96 bytes),
the boxes sat at x ±51 where the doors are at ±19: Elric reads a NiNode
rotation as the transpose of pyffi's matrix, so a child node's turn went the
other way. `collision.node_transform` now writes the transpose and the boxes
land at ±19.3, on the doors. In Doc's house 11 of 25 child-node bodies sit
on a rotated node (globe, teddy bear bones, cabinet doors, deathclaw belt);
render shapes are baked into root space, so only collision was affected.

Doc's house: all 172 meshes with collision convert (165 with one body, 7
with two), with no Elric crash, in one 17-second build. Clutter (MISC,
ALCH...) keeps FNV's dynamic body while it is placed as a static.

Animated containers (fridge, oven, gun cabinet, cabinet door) hold
keyframed bodies (motion system 6, layer ANIMSTATIC, collision object flags
SET_LOCAL and USE_VEL) that their open/close animation moves. The converter
drops that animation, and in game the fridge, oven and gun cabinet have no
collision. Making those bodies fixed (motion 7, quality 1, layer STATIC,
those two flags cleared) did not help in play: Elric read FNV's fixed as a
moving body (see [furniture](#spike-2-furniture)), so the fridge's fixed
main body moved too. Left
for the animated-object work (keep the controller and keyframed bodies as
vanilla's animated containers do).

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

- environment-mapped (glass): vanilla's beaker BGEM when its texture is
  mostly see-through; else a cut-out whose see-through triangles split off
  to the beaker BGEM. The mutagen tank (`ms04mutagentank01.nif`, 88% of its
  texels solid) drew as dark glass whole; now 508 of its 556 triangles are
  lit and 48 glass. In Doc's house 9 more of the 18 glass meshes now draw
  their solid parts lit (camera, clock, pressure cooker, window frames).
  Alpha-tested glass split too since 2026-10-21. Before that, only glass
  without alpha test split, and the rest drew as glass whole. The Prospector
  Saloon's framed posters (`nvposter01`-`12`) use `Marquee.dds`, an atlas
  of an opaque wood frame beside a cracked, partly transparent glass pane.
  They are blended (SRC_ALPHA, INV_SRC_ALPHA) with alpha test 0, so their
  frames drew as see-through glass (played 2026-10-21). Additive glass still
  never splits: it only adds light, and the Primm museum cases' grime
  patch is one. In the region the change touches 19 shapes in 14 of 2,236
  meshes: the 12 posters, `drinkingglass01` and `glasspitcher01`;
- additive (the blend's destination ONE): glass too, as environment-mapped
  shapes are, through the effect shader with FNV's own blend. The Primm
  museum cases (`archivesdisplaycases02.nif:18`, a grimy `StoreFrontQuad01`
  patch added on top, ONE/ONE with alpha test 60, no environment map) were
  flat sheets, so they became lit decals and drew the grime as a solid
  streaky top (played 2026-10-19). Over 11,817 FNV meshes, 159 blended lit
  shapes are additive: 143 environment-mapped, 16 not (the two museum
  cases, 10 DLC05 grate lights, the Protectron pod glow, the war-room table
  map, the minigun tracer), all glows or glass;
- decal (`sf_decal_single_pass` or dynamic): a blended BGSM with `decal` and
  the shader's Decal and Dynamic_Decal flags (vanilla's blended decals);
- a texture at least 50% partly transparent: vanilla BloatflyWing's BGEM
  (lit, blended, no falloff) and its mesh shader values;
- otherwise a cut-out: alpha test at FNV's threshold when it had one, else
  vanilla's commonest 128, blend off (Doc's fan texture is 240-255). The
  cut-out's triangles whose texels are mostly partly transparent (7 samples
  each, the same rule) split into a second shape with the insect-wing BGEM:
  Doc's fan mount bakes a soft shadow ring (black, alpha 8-184) into the
  same texture, which as a cut-out drew as a hard black ring (36 of its 774
  triangles split).

FNV's baked soft shadows also come as unlit planes: `Gurney01:2` is an
untextured BSShaderNoLightingProperty decal with black vertex colours, alpha
0 to 0.6, flagged `sf_vertex_alpha`, and no NiAlphaProperty; FNV blends it,
and with no alpha property our effect shader drew it as a black quad. An
unlit shape flagged for vertex alpha with some vertex alpha below 1 and no
alpha property now blends (src alpha, inverse src alpha). Of FNV's 197
unlit vertex-alpha shapes without an alpha property, 119 are editor markers
(already dropped); 61 have vertex alpha below 1 (shadow planes, smoke, fog).

### <a id="spike-2-items"></a>Items and containers (played 2026-10-06)

Doc's house places 434 references: 208 statics, 134 misc items (books,
clipboards, pencils, cookware, 11 bottle caps), 16 consumables, 14
furniture, 11 containers, 11 activators, 8 movable statics, 2 doors, a
knife, a hat and reading glasses. All but lights and doors were statics.

`fo4_import/spike/items.py` converts misc items (name, model, value,
weight), leveled items (chance none, flags, the entries whose items
convert: FO4's LVLO is level, item, count, chance none in 12 bytes) and
containers (model, contents, the Respawns flag). An item type not converted
yet is skipped and counted. FNV engine objects that Fallout4.esm has under
the same FormID, type and EditorID are FO4's own: the bottle cap
(`Caps001`, 0x0F) and the COC/X markers, computed rather than listed.

First play: items pick up and containers open, but the Pip-Boy showed no
item preview. 1,128 of Fallout4.esm's misc items name `MiscMod01`
(0x248769) as their preview transform (PTRN), and those without one are
mostly not inventory items (no name); every converted misc item now does.
The fridge and oven are containers in FNV too (food).

### <a id="spike-2-furniture"></a>Furniture (built 2026-10-06, played 2026-10-08: every seat and bed in Doc's house)

FNV marks each way into a seat or bed in the mesh: a `BSFurnitureMarker`
position has an offset, a heading in thousandths of a radian pointing at the
furniture, and an animation slot (1/2 sleep entered from the right/left,
11/12 sit entered from the left/right, 14 sit from the front). The FURN's
MNAM low bits pick which of them are active (`Chair01F` front only,
`SubDiningChairDirtyL`/`R` one side; Doc's couch has 3 front markers and
activates one); its high bits are FO4's own, 0x40000000 sit and 0x80000000
sleep.

FO4 furniture meshes have no marker blocks (vanilla chairs, couches and beds
read: root NiNode, BSXFlags, physics, shapes). The markers are the record's
SNAM: offset, heading the actor faces, a keyword, and an entry byte whose
low bits are the sides (front 1, rear 2, right 4, left 8, other 16; vanilla
sets the unused high bits too: chairs 0xF0 | sides, beds 0xE0 | side). The
left-exit vault chair has only Left. Animations come from keywords:
`AnimFurnChairSitAnims` + `FurnitureClassRelaxation` on chairs and couches,
`IsSleepFurniture` + `AnimFurnBedAnims` on beds, which also carry MNAM Must
Exit to Talk, record flag Must Exit To Talk and XMRK `Markers\SleepBed.nif`.

`fo4_import/spike/furniture.py` writes one SNAM per seat or sleeper:

- **Seats.** FNV's front markers stand outside the chair, 31-36 units in
  front of the converted mesh's front edge (Chair01F: edge 21, marker 54.6).
  Over 129 vanilla sit markers the seat marker sits a median 18 units behind
  the front edge (quartiles 16 and 21), at floor height, facing out. A seat
  is FNV's front marker turned by π and moved to 18 behind the front edge,
  keeping its sideways position and height; each active marker adds its
  side. A lone seat entered from the front is also left from both sides
  (entry 0xFD): of vanilla's 75 one-seat sit furniture, 21 are 0xFD and 38
  0xFF, only 10 front only (0xF1). Front only, Doc stood up from the
  wake-up chair (`Chair01F`) straight into the seated player and stuck
  there about 90% of the time. Played 2026-10-20: he stands out of the
  chair to its side and walks on without sticking (7 chair bases in the
  region change; couches and side-entry chairs do not).
- **Beds.** FO4 and FNV beds both lie along Y with the headboard at +Y
  (tallest end, 5 vanilla beds and both FNV beds). Vanilla bed markers face
  +X (heading π/2) across the bed, at the middle of their lane: 0.5 of the
  width for one sleeper, 0.26 and 0.74 for two, the +X lane entered from
  the Right. FNV's slot-1 marker stands at +X facing −X, slot 2 at −X facing
  +X; both become heading π/2 in their lane, slot 1 Right and slot 2 Left.
- **Side-entry chairs** (slots 11/12 only, e.g. pushed under a table): the
  front marker is midway between a left and right marker facing the same
  seat, the seated actor a quarter turn from them (`Chair_LeftEnter.kf`
  −90°, `Chair_RightEnter.kf` +90°).
- **Stools, floor and restrained sits** (slots 15, 17, 18): the seat is
  where FNV's enter animation leaves the actor (`stoolenter.kf`,
  `sitfloorenter.kf`, `restrainedsitenter.kf`: Bip01's travel, Bip01
  NonAccum's turn to the nearest quarter), with the keywords and marker
  model of vanilla `NpcStoolDinerIntSit01`, `NPCInvGroundSit` and
  `NPCPrisonerFloorSit`, entered from every side.
- **Standing furniture.** Wall leaning (slot 19) and the special idle (slot
  22, its animation an FNV IDLE whose `IsCurrentFurnitureObj` names the
  furniture) were left with no SNAM, so a package sending an actor to one
  did nothing: Trudy's bar spot (`BarKeep`) and Joe Cobb's exit
  (`WallMarker`) froze both after their argument (played 2026-10-14). Each
  active FNV marker is now an SNAM where FNV has it, entered from every
  side (0xFF), MNAM sit | its bit, with the keywords of vanilla's
  equivalent: `NPCInvWallLean01` for slot 19; by idle group,
  `NPCBartender` (BarKeeping) and `NPCPushUps` (PushUps). A special idle
  FO4 has no NPC furniture for (`CookingStove`: FO4's stoves are player
  workbenches) keeps the marker without keywords. Confirmed in game:
  Trudy and Joe walk off once the argument ends.

Doc's house: 7 furniture bases (14 references) convert: 4 chairs, the couch
(one seat), 2 dining chairs, a twin and a queen bed.

First play: the furniture had no collision, one chair could be sat in and
lost its collision after, and a chair ended up on top of the easel. Their
FNV bodies are fixed STATIC ones, as when they were statics and collided;
the difference is BSXFlags. The converter kept FNV's 0x2 (Havok only). Of
vanilla's FURN, STAT and MISC meshes with Havok, all 2,352 without Complex
(0x8) also set Articulated (0x80): statics 0x82, clutter 0xC2, so a mesh
with Havok and not Complex now gets Articulated too. That put the chair
back on the floor but the furniture still lost its collision and tipped
over once touched or looked away from.

The cause was the motion type. Vanilla fixed furniture's
`hknpPhysicsSystemData` has no motion (0 motion properties, 0 motion
cinfos); a drinking glass has one. Every body we sent through Elric came
out with one, the bathtub and every chair and bed included: moving bodies
that a STAT reference never simulates but a FURN or CONT reference does.
Elric reads the input body's motion system in Havok 2014's numbering
(hkpMotion, which dropped the stabilized types), not FNV's: run on the
chair with that byte set to each value, 5 comes out fixed (no motion), 4
keyframed (motion cinfo, no properties), 1, 6 and 7 moving. FNV's fixed
(7) is 2014's character. `collision.MOTIONS` maps FNV's numbers to
2014's: fixed 7 → 5, box inertia 4/5 → 3, sphere 2/3 → 2. Keyframed (6)
is fixed (5) too where the converter drops the animation that moves it
(a static mesh); Elric then writes them with no motion, as vanilla's fixed
bodies. On a node that keeps its animation it is keyframed (4), see
[animations](#spike-4-animations).
Played: the furniture keeps its collision and its sit and sleep options,
and the fridge, oven and gun cabinet collide too.

Standing up from two dining chairs put the player inside the table. Seats
had Other (0x10) on every entry byte; over vanilla's SNAMs, the one-sided
seats are plain Left 0xe8 (21) and Right 0xe4 (22), and Left with Other
(0xf8) appears once, while Other comes with Front (0xf1 25, 0xfd 22, 0xf5
and 0xf9 19 each). Other is now set only on a seat entered from the front,
so `SubDiningChairDirtyL`/`R` are 0xe8/0xe4.

### <a id="spike-2-activators"></a>Activators (built 2026-10-06, played 2026-10-21)

```bash
py -3.14 -m fo4_import.pipeline.run ... --scripts temp/fo4_scripts/FalloutNV.esm GSDocMitchellHouse
```

Doc's house has 11 activators: the sink and toilet (purified water), the
chemistry set, broken SMG, Vit-o-matic, brahmin skull and game-mode note
(scripted), and four triggers with no model (couch, chair, vigor tester,
exit). `fo4_import/spike/activators.py` writes each as an ACTI with its name
and model:

- **Scripts.** The FNV script's conversion (`papyrus_script_name`, so
  hashed long names match) is attached by VMAD and compiled into
  `<Data>/Scripts` with the helpers (`script.compile_into`); all 9 compile.
  Properties are filled from Fallout4.esm records with the property's name
  (Stimpak, Psycho, Buffout, Mentats) and from the spike's converted
  messages. Left unfilled: `VCG01` (Doc's intro quest), `CGTutorial`,
  `DocMitchellREF`, FNV-only items (Steady, Rebound, the 9mm SMG) and
  `TES4DestroyedRefs` (`TES4Polyfill.SetDestroyed` skips a missing list).
  So the chemistry set, SMG and game-mode note work; the quest-driven ones
  bound and did nothing until VCG01 was converted ([VCG01](#spike-2-vcg01)).
- **Messages.** A script's `Message` property makes the FNV MESG it names:
  title, text, buttons, and the Message Box flag (FNV's bit 1 is Auto
  Display, FO4's Delay Initial Display, so it is dropped); a notification
  gets vanilla's default 2 seconds. The export has no button conditions
  (the chemistry set's "Science 25"), so every button showed. Since
  2026-11-05 the export writes them and buttons are gated (9 of the base
  game's 136 still ungated; built, not played:
  [message buttons](fo4_pipeline.md#message-buttons)).
- **Triggers.** FO4 trigger references are NAME, XPRM, DATA (8,832
  vanilla), their bases plain ACTIs (EDID, VMAD, OBND, PNAM, FNAM:
  `DefaultSetStageTrigger` and the like). XPRM is the same 32 bytes in both
  games (half-extents, colour, a float, shape 1 = box), so FNV's is copied.
- **Water.** FO4 never uses ACTI WNAM for sinks: its 5 drinkable sinks and
  fountains run `drinkFromFountainScript` (drinking idle, sounds,
  `spellOnDrink`) with a "Drink" prompt. A drinkable FNV activator takes
  `PlayerHouse_Ruin_KitchenSink01Activator`'s script, its spell
  `WaterRadiationDrinking` when the FNV water type's actor effect (WATR
  XNAM) has `DamageRadiationLevel`, else `WaterFountainCleanDrinking`.
  Purified water (`WaterHeal1Purified`) has none; average, good and
  terrible water do.
- **Export gaps.** The shared export has no ACTI VNAM (activation sound, 100
  activators), WNAM (water, 31), XATO (prompt, 59), RNAM (radio, 24) or INAM
  (3), and no WATR XNAM; the spike reads WNAM and XNAM from FalloutNV.esm
  (`install.FALLOUTNV_ESM`). Sounds were converted later
  ([sounds](#spike-4-sounds), played 2026-10-10).

### <a id="spike-2-navmesh"></a>Navmesh (played 2026-10-06)

FNV's navmesh is authored, so `fo4_import/spike/navmesh.py` repacks it as
the Skyrim side does (`navm_falloutnv`), into FO4's layout. Measured over
Fallout4.esm's 781 interior navmeshes:

- **NVNM version 15**, pathing-cell CRC `0xA5E9A03C`, as Skyrim. A
  triangle is 21 bytes: Skyrim's 16 plus a float after the edges and a byte
  (0 in 55,573 of 56,119 sampled). The float is not the floor height (it
  differs from the vertices' mean z by −2,848 to +2,500); vanilla writes
  FLT_MAX in some, so it reads as the clearance above the triangle, and the
  spike writes FLT_MAX (unbounded). Edge links gain an edge-index byte (11
  bytes); door links are triangle, `PathingDoor` CRC, door.
- **Cover and waypoints are optional:** 92 of the 781 have no cover array
  and 428 no waypoints; the spike writes neither. The lookup grid is the
  Skyrim one (`lookup_grid.build_navmesh_grid`, `choose_divisor`).
- **Triangle flags** are the same bits in FNV and FO4 (xEdit's shared
  `wbNavmeshTriangleFlags`: edge links, Door 0x400, Found 0x800, Water,
  Preferred), so FNV's flags and cover flags carry over. Edge links to
  navmeshes in the build are kept and gain FO4's facing-edge byte; links
  to any other navmesh are dropped and their edges left open
  ([exterior navmesh](fo4_pipeline.md#exterior-navmesh)).
- **The record** is NVNM and an empty MNAM (pre-cut map; empty in 7,723 of
  7,799). It is a temporary child of the cell.
- **NAVI.** Vanilla registers every navmesh in the singleton `0x00000FF1`
  (NVER 15, 7,799 NVMI, a 26,840-byte NVPP of precomputed paths), whose
  NVMI layout is Skyrim's. The plugin overrides it with its own NVMI and a
  copy of vanilla's NVPP, as `tes5_import/navmesh/navi.py` does for Skyrim.

Doc's house: one navmesh, 118 vertices and 123 triangles, its door link on
triangle 77 to the interior door (`GSDocMitchellHouseIntDoorREF`, flags
Door + Found), no edge links.

### <a id="spike-2-vcg01"></a>Doc's intro quest, VCG01 (step 1 played 2026-10-06)

VCG01 ("Ain't That a Kick in the Head") is FNV's character creation in
Doc's house: 38 stages run by the quest script's timers (`DATA.Delay` 0.01,
so the converted poll re-arms at the 0.1 s minimum) and by Doc's lines;
name, sex, Reflectron (race menu), the Vit-o-matic (SPECIAL), the
questionnaire (tag skills) and traits; 4 objectives; the triggers and
activators of the [activators](#spike-2-activators) step. Steps: (1) the
quest and its scripts on the cell's forms; (2) Doc's intro lines (five
`SayTo` topics and the questionnaire) in the cell plugin; (3) Doc's AI
packages; (4) the character menus on FO4; (5) the player's bed package,
idles and imagespace modifiers.

**Step 1** (`fo4_import/spike/quest.py`, `attach.py`):

- The QUST keeps name, priority and stages (one log entry each, FNV's
  complete flag); it is not start-game enabled (`setstage FNV_VCG01 0`
  starts it). Its VMAD attaches `FALLOUTNV_VCG01SCRIPT` plainly and
  `FALLOUTNV_QF_VCG01`'s 38 stage fragments (`vmad.quest_fragments` gained
  plainly attached scripts).
- FO4 objectives target aliases, not references: each distinct FNV target
  becomes a forced-reference alias (the Vit-o-matic, the couch, the exit
  marker) and its QSTA names it.
- `attach.ObjectScripts` attaches every record's converted script (doors,
  activators, Doc's ACHR, the quest) and fills a property from the cell's
  own forms by FNV name (references, actors, the quest), `Player`, the
  helper quests and globals (the plugin now masters `FalloutHelpers.esl`),
  Fallout4.esm misc items and potions, and the messages it names. Other
  same-named Fallout4.esm forms are not used: stage 0's
  `RemoveItem PipBoy` would take FO4's Pip-Boy.
  - **Engine globals** (built 2026-10-10) are the exception: a
    `GlobalVariable` property takes the Fallout4.esm global of its name
    when that global's FormID is below 0x800. Those are the engine's own,
    the same form in both games (`GameHour` 0x38, `GameDaysPassed` 0x39).
  - Before this, `GameHour` was always empty, and two things broke:
    - every `FALLOUTNV_WastelandWindowScript` window logged two errors
      every 0.5 s (13 windows: about 95% of a 3 MB Papyrus log over six
      minutes);
    - VCG01's stage 200 never set the clock to 8 AM.
  - The window and Lucky 38 light scripts still change nothing in game:
    the mesh conversion drops FNV's NIF animations ("Left"/"Right"), and
    the light's `IsAnimPlaying` (`GetAnimationVariableBool("bAnimPlaying")`)
    logs two errors every 0.5 s on a mesh with no animation graph.
- A property typed as a script (`DocMitchellREF` as
  `FALLOUTNV_GSDocMitchellScript`) needs the reference to carry it, so Doc
  carries his FNV script and doors theirs. Doc is one clone now (STH).
- Unfilled: `VCG00`, `VMQ01`, `VCG04`, `CGTutorial`, `VictorREF`, the
  topics (step 2), packages (step 3), imagespace modifiers, `PipBoy`,
  `TES4DestroyedRefs` (and `GameHour` until the engine-globals fix above).

Without Doc's lines the quest stops at stage 3 (stage 5 is set by his
line's result).

**Step 2a, Doc's scripted lines** (`fo4_import/spike/say_topics.py`;
built 2026-10-06, played 2026-10-21). VCG01's 128 INFOs are 39 lines in five
Conversation-type topics the quest Says (`VCG01Intro` 15,
`VCG01DocReactions` 16, `VCG01DocPsychIntro` 3, `VCG01DocTraitIntro` 3,
`VCG01DocFarewellTransition` 2), the psych test's greeting and 77 answer
topics (step 2b), the outro and two epilogue lines.

- FNV's SayTo plays a topic's first passing line; the `VCG01Intro` lines
  all test only `GetIsID DocMitchell` and are Say Once, and each one's
  result says the topic again or sets the next stage, so the chain steps
  line by line.
- FO4's Say takes a Custom topic (DATA 0, SNAM `CUST`), and vanilla's sit
  in a branch of their quest: all 1,243 Custom topics have a BNAM, as
  `MS09LorenzoWeakenedTopic` in `MS09Branch` (DLBR: Player, Top-Level, a
  starting topic). The quest gets a branch and the five topics, with each
  line's responses, Say Once flag, conditions and converted fragment.
- <a id="hello-goodbye"></a>**HELLO and GOODBYE** (FNV DIALs `000000D2` and
  `000000D4`) are Conversation-type too, but FNV's engine plays them itself,
  and no script Says them; as Custom topics they never played (the preflight
  dialogue audit, [fo4_preflight.md](fo4_preflight.md#results)). Since
  2026-10-25 each quest's HELLO is its FO4 Hello topic (SNAM `HELO`, DATA
  0 7 0x52 0 as DialogueDiamondCity's; vanilla has one per quest, no branch,
  360 quests) and its GOODBYE a Goodbye topic (SNAM `GBYE`, as
  DialogueDrinkingBuddy's), outside the branch. A quest whose only Say
  topics were these keeps no branch: on the whole-map build that removes 43
  of 93 DLBRs (`GenericBranch`, `VDialogueNovacBranch`, ...), approved drift
  2026-10-25. Not played yet; whether FO4 plays a
  Goodbye when the player leaves a scene conversation is untested (vanilla
  has 2 Goodbye topics).
- Conditions: forms through the cell (Doc's NPC to his clone, the quest,
  references, the player). FNV's `GetQuestVariable VCG01 5` becomes FO4's
  `GetVMQuestVariable` (function 629): parameter 1 the quest, the variable
  named in a CIS2 after the CTDA as `::<property>_var`, as vanilla's 8,906
  uses (`::var_VaultLife_var`); the index comes from the quest script's
  variable list (5 is `nDocReaction`).
- **SayTo's target.** Four reaction lines test the player's sex on the
  Target ("Sorry, son" / "little lady"). The converter wrote SayTo as a
  bare `Say(topic)` (Skyrim's Say has no target); FO4's
  `Say(Topic, Actor, bool, ObjectReference akTarget)` does, so on Fallout 4
  `SayTo <target> <topic>` now passes it. Corpus: 2,947 scripts recompiled,
  still 17,676 of 17,695.
- Voice: the 39 lines' FNV recordings as `.fuz` under the clone's stand-in
  voice type (`NPCMDocWeathers`), as the dialogue spike does.
- **First play:** moving to the bed opened FO4's generic doctor dialogue on
  Doc, and the quest jumped several stages. The clone kept Doc Weathers'
  factions: `DialogueDoctorsFaction` (vanilla's doctor greeting and menu,
  the stand-in artifact [fragments](#spike-3-fragments) noted),
  `CaravanFaction`, `CaravanLeaderFaction`,
  `CaravanVendorDocWeathersFaction`, two companion-chat factions, and his
  crime faction. The cell's clones now leave out the stand-in's factions
  (SNAM) and crime faction (CRIF).
- **A line said from a line's end is dropped.** The doctor box gone, the
  quest still ran from stage 8 to 36 in 0.4 s after Doc's second line. A
  diagnostic polyfill (`SAY_TRACE` on, real-time stamps on LineBegan,
  LineEnded and every stage set) showed lines 1 and 2 playing normally
  (BEGIN 21.29 → END 23.94, BEGIN 27.55 → END 32.93), then about eight END
  fragments with no BEGIN between 32.95 and 33.10: line 2's end result
  says `VCG01Intro` again, FO4 drops a Say to an actor still in its line
  and runs the dropped line's End fragment at once, whose result says the
  next, and so on. FNV queued such a line (its chained SayTo results are
  how Doc's intro steps). Vanilla FO4 never Says from a fragment (0 of its
  fragments); it chains lines in scenes. On Fallout 4 the converter now
  emits Say/SayTo as `TES4Polyfill.SayWhenFree(speaker, topic, target)`,
  which waits while the speaker `IsTalking()` (at most 3 s), then Says.
  Played: every line in order through to the couch.
- **The Reflectron.** `ShowRaceMenu` became a bare `Game.ShowRaceMenu()`:
  the menu opened with the camera in first person and no body to edit.
  Vanilla never calls it bare. Mode 0 is MQ101's mirror (with the spouse
  refs), 2 the barber, 3 the surgeon, 1 the vault exit elevator's full
  edit, which first sets the chargen skeleton and a neutral face, forces
  third person and plays `ElevatorFaceCamera` (`0001A9EE`) to turn the
  player to the camera. On Fallout 4 `showracemenu` is now
  `TES4Polyfill.ShowRaceMenu()`, doing that, opening mode 1, and going back
  to first person once it closes, as the elevator's `MenusDone` does.
  Played: the camera swung out, then the menu came up in first person
  again. Stage 0's `DisablePlayerControls` reaches FO4's shared input
  layer with the camera switch disabled (`F3NV_PlayerControls.Disable`'s
  third flag), which pins first person; FNV's Reflectron did not depend on
  it. Lifting it alone changed nothing: the helper's
  `Utility.Wait(0.5)` then `ForceFirstPerson()` ran half a second after
  the menu opened, since `ShowRaceMenu` returns at once and FO4's LooksMenu
  does not pause the game (no Papyrus errors in the log). Vanilla restores
  the view in `OnMenuOpenCloseEvent("LooksMenu")` (`SurgeonScript`,
  `WorkshopSurgeryChairScript`), which needs a script instance, so the
  edit moved onto the controls quest: `showracemenu` emits
  `TES4PlayerControls.ShowRaceMenu()`, which enables the camera switch on
  its layer if it disabled it, sets up and opens mode 1, and on the
  menu's close goes back to first person and disables the switch again.

**Step 2b, the psych test** (`fo4_import/spike/conversation.py`; played
2026-10-06). Once the player sits, the couch trigger sets
`bGiveTest` and calls `DocMitchellREF.StartConversation Player` every 2 s
until the greeting's result sets `bBeganTest`. The test is FNV menu
dialogue: the GREETING line "I'm gonna say a word" has six Choices, and
each answer's line has the next question's Choices (5 or 6 answers, past
FO4's four, so XDI menus as in [spike 1](#spike-1-design)). Follow Ups
(TCFU, INFOs the speaker says next with no choice) chain "Human shield"
into the statements and the outro's lines.

- **Starting a talk.** Vanilla FO4 opens a scripted talk with a scene,
  or with a ForceGreet package whose topic's line starts one (Danse's
  `BoSM01DanseOverrides_DanseStage148Forcegreet`). On Fallout 4,
  `StartConversation Player [topic]` becomes
  `TES4Polyfill.StartConversation(TES4Talk_<topic or GREETING>, speaker)`:
  the speaker fills alias 0 (`Speaker`, optional and empty) of the scene's
  quest and the scene starts; nothing while it plays. 66 converted scripts
  call it. The cell gives each `TES4Talk_` property its scene's FormID.
- **Scenes.** A line scene is one Dialogue action (PastorGreetScene's
  flags) saying a topic of lines, first passing. Each line starts what
  follows it by TSCE, as 382 vanilla Dialogue-action lines do
  (`PastorGreetScene`, `005_CodsworthPostWarSpeechChallenge`): Follow Ups
  a line scene, Choices an XDI menu scene (one option per topic, its lines
  the answers behind padding, `[Leave]`). A Goodbye line, or one followed
  by nothing, ends the talk. Built: 21 scenes, 92 more lines and their
  voice files. The plugin now masters `XDI.esm`.
- `VCG01Test` (the answers' tallies, read at stage 85) is converted with
  the cell and keeps FNV's start game enabled flag; VCG01 still starts by
  hand.
  - *The picks (built 2026-10-19, played 2026-10-21).* `VCG01TestSCRIPT`
    picks three tag skills from the tallies (a combat skill, one of
    Speech, Science, Lockpick and Barter, then the best untagged) with
    `SetPlayerTagSkill`, which preselects them in FNV's tag menu. It
    converts to `F3NV_CharacterEvents.SuggestTag(<skill>)`: LevelUpMenuEx's
    `AddTagSkillAV` tags it at once (so the third pick's `IsPlayerTagSkill`
    sees the first two) and the helper records it; FNV's slot is dropped.
    With suggestions pending, `F3NV_CharacterRules` opens the tag menu with
    re-tagging allowed and only the picks left to make (three in all, the
    suggestions counting; untagging one frees a pick), and on its
    `PRKF::TagSkills::Finish` event sets each
    skill to its value before the menu plus `TagBonus` when it ends tagged,
    so the bonus is right whatever the menu does for a skill tagged before
    it opened. Later tag menus (FNV's Tag! perk) keep re-tagging off.
- Left out: two topics no FNV line answers ("Double-tap.", "What do I do
  now?"; FNV hides them too), and the two greetings Doc gives when clicked
  mid-quest ("We can chat later", "have a seat"): FO4 has no condition
  function for quest objectives (`GetObjectiveDisplayed`,
  `GetObjectiveCompleted`), and talking to Doc by activation (a GREE
  topic) is not built.

First play of 2b: the word association never started. The couch script
starts its talk timer only once Doc sits in his chair (the chair trigger
sees him seated, `bDocInChair`), and Doc reaches the chair by his stage 80
package; without packages he never sat. So step 3 came next.

**Step 3, Doc's AI packages** (`fo4_import/spike/packages.py`; played
2026-10-06). FO4 packages are template instances like
Skyrim's (`tes5_import/packages/templates.py`); FO4's roots are Travel
`00002CB0`, Sandbox `00002CB1`, Sit `00003896`, ForceGreet `00017BAB`
(`tools/esm/pack_template_dump.py --pack references/Fallout4.esm/PACK.txt`).
Each FNV package becomes a copy of a vanilla instance with no conditions,
scripts or quest and a reference as first input (Travel
`MS09Mission3ParsonsJackToMarkerB02Scene`, Sit
`ChildrenOfAtomCraterPrayPackage7`, Sandbox
`MinutemenRadioOperatorSandboxDefault`), with its EditorID, conditions
(after PSDT) and first input replaced. A Travel to furniture becomes a Sit
on it (FNV seats an actor who travels to a chair). Doc's clone gets them in
FNV's order in place of the stand-in's PKIDs: 7 of 9; left out are
`GoodspringsMilitiaTravelPackage` (another quest's variable) and
`VCG01DocMitchellFarewellDialogueStart` (a Dialogue package, the outro's
force greet).

**The outro** (built and played 2026-10-07: Doc force-greets the player at the door before they leave). At stage 115 Doc's
`VCG01DocMitchellFarewellDialogueStart`, a Dialogue package on the player
with no topic (FNV: the GREETING), force-greets at the exit marker.

- It becomes a copy of `MS04KendraStaysAtHomePackage`, a ForceGreet
  `00017BAB` instance on the Greeting subtype (108 of vanilla's 217 force
  greets; 106 more use Hello), its NPC wait location FNV's.
- The GREETING lines stay in the talk scene `StartConversation` starts, so
  each Say Once line exists once (FO4 has no condition that sees another
  line was said; a second copy in a Greeting topic would replay "I'm gonna
  say a word"). The quest's Greeting topic has one silent `...` line: it
  needs GetPlayerActivated or a converted force greet running (the
  [force greet](#spike-1-force-greet) plan) and a speaker the GREETING
  lines name, puts the speaker in the Speaker alias (ALFA) and starts that
  scene. "Here. These are yours" then runs its Follow Ups (the Pip-Boy,
  the vault suit by sex) into the two answers and the farewell.
- **Objective conditions.** FO4 has no objective condition function, as
  Skyrim's are script-only; the Skyrim build mirrors each state in a
  global (`TES4ObjDone_<quest>_<n>`, `TES4ObjShown_<quest>_<n>`,
  `tes5_import/base/objectives_falloutnv.py`) that converted
  `SetObjective*` calls set. The cell writes them for its quests (8 for
  VCG01 and VCG01Test), fills the scripts' properties (the couch script's
  were None), and `GetObjectiveDisplayed`/`GetObjectiveCompleted` become
  `GetGlobalValue` on them. The two clicked greetings ("We can chat
  later", "have a seat") now convert, so clicking Doc mid-quest no longer
  reaches the outro's line.
- **First play:** at the door Doc drew his gun on the player, then
  force-greeted. The copied vanilla instance's PKDT general flags came
  along, and Kendra's force greet has `0x00800000`, Weapon Drawn. FNV and
  FO4 share the flag layout (xEdit's common `wbPackageFlags`), so each copy
  now takes FNV's flags where both games define the bit alike; all of Doc's
  VCG01 packages carry Weapons Unequipped (`0x200000`). The "We can chat
  later" line before the force greet needs stage < 115 with the new
  objective globals at 0, which a save from the previous build at stage
  110 gives (this build added the globals ahead of the packages, so ids
  moved): test from a save made outside the house.
- **As one scene** (2026-10-07, played 2026-10-21). Each step (a set of
  lines, or a Choices menu) is a phase; while every line of a step leads
  to the same next step the scene runs on into it, and lines that lead
  apart start their own scene by TSCE (by phase name when the step is
  already placed). The outro after "Here. These are yours" is one scene
  of four phases (the Pip-Boy, the vault suit by sex, the two answers,
  the farewell); the psych test's menus join into scenes of 3, 3 and 8
  phases where FNV's answers converge. 21 scenes became 7.
  First play: stuck at the psych test's second question. Every phase
  carried the walk-away check (`GetDistance > 500`) as a completion
  condition, and a completion condition holds a phase until it is true, so
  phase 0 never ended. Vanilla phases have none (`ArturoGreetScene`,
  `NatMQ103Scene`; 140 vanilla scenes have menus in consecutive phases);
  only one-phase scenes keep it now. Played: the psych test and the outro
  run through; the opener's `...` subtitle shows before the outro. No
  vanilla greeting that starts a scene lacks a response (2,663 have their
  own, 285 share one by DNAM; the 400 without any start nothing). Tried
  without a response: played, the force greet stalled and nothing was
  said, so a line without a response does not start its scene. The `...`
  opener stays, recorded in [drift](fo4_drift.md#recorded).
  The `...` also played "Didn't have much choice, I'm afraid": voice files
  are named by INFO FormID, ids move between builds, and an earlier build's
  file for that id was still on disk. The cell build now deletes the
  plugin's `.fuz` files it did not write (250 stale ones, 155 kept).
- **The handouts** (played 2026-10-07). "Here. These are yours" gives
  Stimpaks, caps, lockpicks and a weapon by tag skill, then the Pip-Boy and
  the vault suit, all through FNV leveled lists (each gun listed once per
  condition, FO4 has no item condition) and `IsPlayerTagSkill`, which was a
  TODO. On Fallout 4 it is LevelUpMenuEx's `PRKF:PRKF.IsTagSkillAV` on the
  skill's actor value. An FNV item with an FO4 counterpart is that
  Fallout4.esm item (`items.STAND_INS`, with FO4's name and stats): Stimpak,
  Med-X, Rad-X, blood pack, Cram, Pork N' Beans, Sugar Bombs, the bobby pin;
  the 9mm pistol and ammo as the 10mm, the laser pistol and energy cells as
  the laser gun and fusion cells, dynamite as the frag grenade, the straight
  razor as the switchblade, boxing gloves, knife, the Pip-Boy (one piece: the
  glove has none) and the vault suit as Vault 111's. Copies carrying FNV's
  names need FO4's string tables (Fallout4.esm is localized, and each weapon's
  object templates name themselves). FNV text notes become paper notes
  (BOOK, vanilla `BoS302BIngramBackupNote`'s fields). Item properties of the
  converted scripts are filled through the item converter by FNV name.
  `VGenericTimer` is converted with the cell: its event 3 completes VCG01
  (stage 200) and starts VCG02 (not converted).
- **A line's result runs once.** Fallout 4 runs a line's Begin fragment for
  each response: "Here. These are yours" (2 responses) gave its items twice
  and the Pip-Boy line (3) three times, 4 to 6 s apart. Vanilla has 58
  multi-response lines with a Begin fragment, all repeat-safe (a spotlight,
  a flag).
  - Tried and dropped (2026-10-09): counting responses. In the fragment's
    own variables it failed (a topic info fragment's variables do not last
    between calls: the Pip-Boy line's gated handout ran on all three
    responses); in a helper quest keyed by the fragment's script object it
    failed too (each call is a new object: every response took a new slot).
  - Now (played 2026-10-21): a line with several responses and a result
    script is split into one FO4 line per response, each a scene step, the
    FNV Begin result on the first, its End result on the last
    (`conversation.part`), so each runs once. Vanilla writes 94% of its
    lines with one response (73,099 of 78,087), and 4,279 of its 4,544
    lines with a fragment; all 1,975 such FNV lines are Topic-type (scene)
    lines, none a scripted Say topic.
  - With it (vanilla patterns, census of Fallout4.esm): a line leading to
    another step jumps once said (Start Scene on End, as 316 vanilla lines
    into another scene at a phase), without End Running Scene (XDI draws
    that as the door icon); a topic's lines with different prompts are one
    option each, gated by their line (the speech check's four lines gated
    on Medicine and Speech: one option shows, as FNV shows the first
    passing line's prompt); a Choices menu has no `[Leave]` and its scene
    Prevent Player Exit Dialogue (as 84 vanilla scenes): leaving at the
    farewell's two answers had stranded VCG01 (both GREETING lines before
    it are Say Once, so talking again went to Doc's everyday greeting, the
    Pip-Boy still disabled). Only the topic list keeps `[Leave]`, and
    (2026-10-22) a Choices menu whose conversation can never end, where no
    step reached from it is a Goodbye, a line followed by nothing, or the
    topic list (`Conversations._leaves`). Played: Victor's bodyguard talk
    (VES01VictorGSMyBodyguard) loops menu to menu. Each menu's third choice
    is "Goodbye.", a topic with no line, so FNV shows two options and the
    player leaves by Tab; on FO4 the player was held in until walking off.
    Doc's farewell still ends in a Goodbye, so it stays held. A build with
    masters (a DLC, a mod) judges this on the whole conversation: its own
    lines plus the masters' lines it does not write (`Hub.outside`,
    `conversation.outside_lines`, read only by `_leaves`). Judged on its
    own lines alone, a menu whose answers are all the game's reached
    nothing and kept `[Leave]`: YUP got it on 682 menus, 0 with the
    masters' lines ([DLC dialogue](fo4_plugin_layout.md#dlc-dialogue)).
  - **Starting a scene at a phase needs INTV.** Played: from Bandit's menu
    "Light." came with Bandit's answers again, then "Light." and the right
    ones; "First one. Conflict..." was said twice. Every jump had started
    its scene at phase 0 (the Enemy menu; the statements scene's own
    "First one"). The engine reads the start phase's index from the
    INFO's INTV (after TSCE), not the NAM0 name: all 1,911 vanilla lines
    starting a later phase write INTV equal to its index, and the 2,042
    naming a phase without INTV start at phase 0. `pack_info` writes it
    (89 jumps). Played (2026-10-10): the dialogue works through.
- The Pip-Boy stays disabled until the farewell's last line ends (FNV's
  stage 55 disables it, the farewell's End enables it), as in FNV.
- <a id="spike-2-doc-quests"></a>**Doc after the intro** (built 2026-10-09,
  played 2026-10-21). Played: after the outro Doc said nothing and could not be
  talked to. His talk after VCG01 is VFreeformGoodsprings' (greetings,
  Goodsprings topics, a speech check) and VDoctors' (healing, supplies,
  radiation), and VCG01 (priority 76, still running after stage 200) kept
  winning the greeting with none of its 4 GREETING lines passing. The cell
  now converts both quests, and every cell quest's conversations share one
  Hub (`conversation.hub`):
  - **One greeting:** every cell quest's GREETING lines, highest quest
    priority first (FNV picks the first passing), in the scene of one quest
    the game starts (highest priority: VDoctors); VCG01's
    `StartConversation ... GREETING` starts the same scene.
  - **The topic list:** FNV shows, after a line with no Choices, Follow Ups
    or Goodbye, every top-level topic (DIAL flag 0x02) and every added one
    with a passing line. Such a line now returns to that list (a menu
    step), and the list holds the cell quests' topics with a line whose
    conditions convert: Doc's 10 (yourself, Goodsprings, the town, the
    man who shot me, who rescued me, something taken, the speech check,
    healing, supplies, radiation). Addiction (quest 0x38B2), the shootout
    (Ghost Town Gunfight) and the injured man (0x15EC5B) need quests the
    cell does not convert.
  - **Gates:** a topic an AddTopic reveals shows when its `TES4Unlock_`
    global is set, named by the script converter's own unlock plan; those
    globals and the Follow Up marks (`TES4FollowUpFrom_`/`Said_`, which
    logged "SetValue() on a None object") are made on demand, hashed by
    name. An option with several lines shows to their speakers (GetIsID on
    the target); a line of another quest than the scene's needs that quest
    running (GetQuestRunning).
  - Conditions: GetQuestVariable reads the variable of the quest it names
    (it used the line's quest); GetScriptVariable is GetVMScriptVariable on
    the reference (CIS1 the script, CIS2 `::<name>_var`, as 107 vanilla
    conditions); items FO4 shares by FormID (caps) map, so the caps answers
    convert. None of Doc's lines is left out (388 other residents' are:
    their NPCs are not in the cell).
  - FormIDs moved (approved): 3,045 records became 3,623.

**Step 4, the character menus** (`fo4_import/spike/character.py`,
`F3NV_CharacterRules.psc`; played 2026-10-07). FNV's
character system on LevelUpMenuEx ([decision](research/fo4_target.md#decisions)).

- LevelUpMenuEx reads `Data\PRKF\*.ini`; its list keys name a FormList as
  `Plugin.esp|<hex id>` (the DLL splits at `|`, `mov r8b, 0x7C` before
  the find in its parser at RVA `0xa190`) and check the entries are perks
  or actor values. The cell writes `PRKF\<plugin stem>.ini` (now `PRKF\FalloutNV.ini`): `FNV_Skills`
  and an empty `FNV_Perks` (perks are a later step), FO4's perk chart off,
  0 points per level (the rules add them).
- The 13 FNV skills are the helper plugin's actor values, overridden with
  FNV's AVIF names and descriptions. The 10 FNV traits are trait perks
  with name and description only; their effects come with the perks.
- `F3NV_CharacterRules` (a start-game quest) answers the converted
  scripts' `CharacterMenu` events: `special` opens FO4's
  `Game.ShowSPECIALMenu()`, `tags` LevelUpMenuEx's tag menu (3, +15,
  `fAVDTagSkillBonus`), `traits` its trait menu (up to 2,
  `iTraitMenuMaxNumTraits`). When the SPECIAL menu closes it sets each
  skill to 2 + 2 × governing stat + Luck ÷ 2 rounded up (`fAVDSkill*Base`;
  governing stats from the wiki). FO4 has no plain level-up event (only the
  Story Manager's), so when LevelUpMenuEx's `LevelUpMenu` opens it adds the
  points for the levels since the last time: 10 + Intelligence ÷ 2 skill
  points (FO3: 10 + Intelligence; a fraction carries over) and a perk
  point every 2 levels (FO3: every level), minus whatever arrived
  meanwhile. FNV's `iLevelUpSkillPointsBase` is 11, but the wiki's 10 +
  half Intelligence is what the game gives.
- **Sex and name (research 2026-10-07).** The Reflectron's `ShowRaceMenu`
  runs mode 1 (the vault exit elevator's remake), which edits only the
  player and cannot change sex (Papyrus reference). Mode 0 is the MQ101
  mirror's: `SF_MQ101_001_MirrorScene` passes both spouse aliases
  (`akMenuSpouseFemale`, `akMenuSpouseMale`), and sex is picked between
  them. The name is not in the race menu: vanilla names the player in the
  SPECIAL menu (the Vault-Tec rep scene and the exit elevator's
  `ShowCharacterMenus` call `Game.ShowSPECIALMenu()`). FNV asks the sex in
  VCG01's own message box and runs `player.SexChange` (converted as a
  note); FO4 Papyrus has no sex setter, but Garden of Eden's
  `ExecuteConsoleCommand` can run `sexchange`, which swaps the body, not
  the player's voice (FNV's player is silent). Alternate-start mods (Start
  Me Up) keep FO4's mirror chargen and SPECIAL form, then skip ahead.
  Taken: FNV's way. VCG01's own message box picks the sex and
  `SexChange` becomes `TES4Polyfill.SetSex`, running `sexchange` through
  Garden of Eden when the sex differs (since 2026-10-29 the F3NV plugin
  runs the game's `SexChange` itself, [sex change](fo4_pipeline.md#sex-change));
  the Reflectron stays mode 1 for the face; the name is the SPECIAL menu's
  (the Vit-o-matic).
- **The ink blots** (`fo4_import/spike/swaps.py`; played 2026-10-07). FNV's `SwapTexture <ref> "<node>" "<texture>"` (242 sites,
  all FNV: 198 on `OnScreenSlideRef`, 41 on the psych test's card, 3 on
  the Pip-Boy screen) retextures one shape. FO4 swaps materials, and only
  F4SE applies one at runtime (`ObjectReference.ApplyMaterialSwap`). The
  converter emits `ref.ApplyMaterialSwap(TES4Swap_<node>_<texture>)`; the
  cell finds each SwapTexture in the game's scripts and line results and
  writes the property's MSWP: the shape's converted BGSM copied with the
  new diffuse, and every material that shape can wear (its own and the
  other swaps' on the same reference and node) mapped to it, since F4SE's
  matching against the material on it is unconfirmed. The card: 8 swaps
  (three ink blots, five card faces).
- **Played:** SPECIAL, traits and the test's results work. The sex box
  never showed: FNV's `VCG01ChooseSexMessage` has no text (`DESC`), only
  a title ("Choose Sex") and two buttons, and FO4's message box shows
  only the text, so `Show()` returned the first button at once. A message
  without text now shows its title. The ink blots all changed at the end
  of the test instead of with their questions. F4SE's `ApplyMaterialSwap`
  (f4se `PapyrusObjectReference.cpp`) normalizes the shape's material name
  to the part after `materials\`, looks it up in the swap and loads the
  new material onto the live shape, so the swaps should match; the
  converter now calls `TES4Polyfill.SwapMaterial`, which traces each
  swap's time, count of swapped materials, 3D and disabled state, for the
  next play. Also: the card and both `TempRorschachTest` statics are
  Initially Disabled in FNV (the test enables and disables the card); the
  cell's references now keep that flag (`R.INITIALLY_DISABLED`).
- **Played again:** still no sex box; the Vit-o-matic reaction always the
  same; the card kept its first face and showed the last after the test.
  - Nothing sets VCG01 stage 17 in FNV (the line after the name goes to
    stage 25): the "Choose Sex" box is dead content, and FNV picks the sex
    in the Reflectron's own race menu. FO4's remake menu cannot, so
    `F3NV_PlayerControls.ShowRaceMenu` first shows the helper plugin's
    `TES4ChooseSexMessage` (Male, Female; object id `0xB00`) and sets it
    through `TES4Polyfill.SetSex`. Drift: a box before the editor.
  - Doc's reaction reads SPECIAL through `GetTES4ActorValue`, which took
    Intelligence and Luck for Oblivion attributes and returned a fixed
    stub on FO4. FO3/FNV have no Oblivion attributes: on Fallout 4
    `IsTES4Attribute` is false and SPECIAL reads FO4's actor values. Also,
    FO4's Papyrus timers run while a menu is open and FNV's GameMode does
    not, so a converted poll pass now returns while
    `TES4Polyfill.InMenuMode()` (676 scripts; not those whose MenuMode
    blocks poll); Doc's reaction waits for the SPECIAL menu to close.
    `InMenuMode` is `Utility.IsInMenuMode()` or one of `SPECIALMenu`,
    `LevelUpMenu` (LevelUpMenuEx's tags and traits) or `LooksMenu` open:
    On 2026-10-19 Doc said "a pretty standard score" (reaction 0) on
    every run. The log shows the game paused from stage 65 until the menu
    closed, so the reaction did read the picks. FO4's menu totals
    `uSPECIALPoints` (28: every stat at 1 plus 21), FNV's 40, so the same
    picks read lower; the plugin now overrides `uSPECIALPoints` to 40
    (`fo4_import/spike/character.py`), and `F3NV_NewGame` sets each stat
    to the FNV player record's value (5) before VCG00 starts
    (`SetStartSpecial`; `Special`/`SpecialStart`, a float array property),
    so the menu opens at 5s with 5 points left. `F3NV_CharacterRules` traces
    `special|opened|closed` with the seven values (`GetGameSettingInt`
    refuses a `u` setting). Played 2026-10-19: opened at 5s, closed at
    5/5/6/8/6/5/5 (40), and Doc gave the Charisma line (reaction 10).
  - The swap trace: every swap ran with its line and reported one material
    swapped, but the card did not redraw. `TES4Polyfill.SwapMaterial` now
    sets the persistent swap (`SetMaterialSwap`), which the game applies
    whenever the 3D loads, and reloads a shown reference
    (`Disable()`/`Enable()`).
  - Played: the sex box before the Reflectron, Doc's stat reaction and the
    ink blots in step with the questions all work.
- To learn in play: the SPECIAL menu's point budget on an existing save,
  and whether LevelUpMenuEx's `AddPP` takes a negative count (FO4's own
  perk point each level would otherwise stay).

**Step 5, the bed, idles and imagespace modifiers** (`fo4_import/spike/imods.py`,
`poses.py`; played 2026-10-07). FNV wakes the player on
Doc's bed with script packages on the player: stage 0
`player.AddScriptPackage VCG01PlayerSection0` (lying, `LooseVCG01PlayerWakeup`,
an animated camera), stages 5 and 7 `VCG01PlayerSection1` (sit up, then the
`LooseVCG01PlayerBedsit` loop on the bed's edge as its OnChange idle),
stage 50 `RemoveScriptPackage` (the camera frees, then stage 55 enables
walking). Each is a type 6 package whose only content is a special idle
(`.kf`). Stage 0 also removes `WhiteISFX` and applies
`VCG01FadeInFromBlackISFX` (a fade from white), stage 5
`VCG01PlayerStrainISFX`, and stage 30 has Doc `PlayIdle VCG01DocGiveMirror`.

- **The player.** FO4 runs no package on the player and cannot play FNV's
  `.kf` idles. All of FO3/FNV's player script packages (25: VCG00/VCG01,
  CG00, CG04, MQ08, MQ11) are such cinematics. Vanilla puts the player in
  furniture by activation (MQ101's cryopod `Activate(Game.GetPlayer())`),
  and a bed opens the sleep menu. On Fallout 4,
  `player.AddScriptPackage <package>` becomes
  `TES4PlayerControls.HoldPlayer(TES4Pose_<package>)` and
  `RemoveScriptPackage` `ReleasePlayer()`. For the packages
  `poses.SEATED_PACKAGES` names (VCG01's two, with the marker VCG00 moves the
  player to, `VCG01PlayerStartMarkerREF`) the cell places a seat reference,
  initially disabled, of `TES4PlayerSeat`: an invisible one-seat furniture
  (`AnimFurnChairSitAnims`, and `FurnitureAllowEnter/ExitThroughGeometry` as
  `NpcChairVaultSitThruGeom03` has, since the seat lies inside the bed).
  FNV's marker stands outside the bed: the twin bed's mesh reaches 49 units
  from its center, the marker 62 (13 outside its edge), and FNV's idle moves
  the player onto it. The seat moves back along the marker's facing to 18
  units (`SEAT_DEPTH`, a converted chair seat's depth) inside the mesh edge of
  the nearest furniture, measured within 24 units to either side
  (`seat_place`): 33.7 units for Doc's bed. `HoldPlayer` enables it and has
  the player activate it once its 3D is loaded, with movement and activation
  lifted on the controls layer until they sit (stage 0 disables both
  first). Papyrus cannot stand the player up gently: after `ReleasePlayer`
  the seat stays until the player leaves it (moving, once stage 55 enables
  it) and is disabled on `OnExitFurniture`. The Reflectron stands a seated
  player for the editor (the seat disabled) and seats them again when it
  closes. Other player packages leave the player standing where the
  disabled controls hold them.
- **Imagespace modifiers.** FO4's IMAD keeps FNV's layout (xEdit
  `wbDefinitionsFNV/FO4.pas`): the DNAM key counts, the keyed blur, double
  vision, tint, fade, radial blur, depth of field and motion blur arrays, and
  21 mult/add pairs. Past the first the pairs differ: FNV's HDR pairs 1-13
  (blur radius, skin dimmer, target luminance and so on) and bloom alphas
  have no FO4 counterpart; FNV's bloom blur radius (14) is FO4's 1; FNV's
  cinematic saturation, contrast, contrast average, brightness (17-20) are
  FO4's 17, 19, none, 18. A pair FO4 lacks gets identity keys. Form version
  131 adds vignette radius and strength (DNAM 252, NAM5/NAM6), vanilla's
  zero. All 215 FNV IMADs convert with every count matching its keys; the 10
  with an intro or outro sound (RDSD) lose it. The cell converts each
  `ImageSpaceModifier` property's FNV modifier by name.
- **Idles a script plays.** `PlayIdle <idle>` was `PlayAnimation("<idle>")`,
  a behavior event FO4 does not know; it is now `PlayIdle(<Idle property>)`
  (86 converted scripts), an FO4 Idle form. FO4's human give,
  `DialogueGiveItem` (`000CEA8D`, event `dyn_talkGeneric`), is a talk idle:
  vanilla plays it only as a line's speaker idle (INFO `SNAM`, `00142444`),
  and `PlayIdle` on Doc at stage 30 played nothing. FNV's hand-over sits
  between "needlework" (its end sets 30) and "How'd I do?" (stage 35), so
  `poses.LINE_IDLES` gave "How'd I do?" (`00104BF8`) that speaker idle.
  Replaced 2026-10-19: FNV's own clips play as FO4 dynamic idles, and
  `VCG01DocGiveMirror` plays FNV's own clip, from the stage-30 script
  only: seated clips stay off lines ([seated idles](fo4_idles.md#furniture)).
- **Played:** the blur and fade work; the player sits on the bed's edge,
  out of Doc's way, through the Reflectron and until they walk off.
  Getting there:
  - Placed where the player stood and activated right after stage 0, the
    seat was refused (logged `3D True, seated False` with movement and
    activation lifted and its 3D loaded). Vanilla's chairs whose seat lies in
    geometry carry the through-geometry keywords; with them the activation
    seats the player.
  - The seat beside the bed blocked Doc's walk to the Vit-o-matic (his
    first marker is 74 units in front of the start marker): `player.moveto`
    the start marker and the seat on it are both outside the bed, hence
    `seat_place`.
  - Opened while seated, the editor did not show the character, and its
    close stood the player up; hence the stand and re-seat around it.
  - The hand-over (`DialogueGiveItem` as the speaker idle of "How'd I do?")
    did not show; accepted as drift.

**Played (2b, 3):** Doc walks to his chair and sits, the word association
starts, and the whole test runs through to its end and Doc's walk to the
door; the outro there came next (played 2026-10-07, above).

**Seen once, not reproduced (2026-10-19): no controls after the
Vit-o-matic.** After the SPECIAL menu closed, the player could not move or
open the pause menu (alt-tab, then the mouse, got out). Repeated runs did
not show it again; possibly an FO4 glitch. The Papyrus log for that run:
the menu opened at 23:49:33 and closed at 23:49:41 with the chosen values,
Doc's reaction and psych-intro lines played, stage 80 set at 23:50:02, and
quest timers kept running to 23:50:24 (so the game was not paused under an
invisible menu). No script in stages 60 to 80 changes controls; stage 55
enables movement. The pause menu was blocked by design of the conversion,
not by the fault: FNV's stage 55 disables the Pip-Boy, mapped to FO4's
menu flag (`F3NV_PlayerControls.Disable`'s `abMenu`), which also blocks the
pause menu until stage 110. If it shows again: note how the SPECIAL menu
was closed, and trace the controls layer when it closes.

*Fixed (built 2026-10-21, not yet played):* FO4's layer has a separate
journal flag (`abJournalTabs`; `EnableJournal`, "the journal menu", the
Pip-Boy), and its menu flag is the main (pause) menu, which FO3/FNV never
blocked. On Fallout 4 the Pip-Boy flag now goes to the journal alone and
the menu flag is false (`commands._flagged_controls`); a flagless
DisablePlayerControls passes FNV's defaults the same way instead of the
layer's own (which block the menu). All 151 converted calls leave the
pause menu open.

**Played (step 1):** from the start marker beside the bed (player.moveto, as the hallway the vigor tester trigger covers lies between the coc door and the bed), stage 55 shows the walk objective, the trigger sets 60 and completes it, and with objective 30 shown by hand the Vit-o-matic sets 65. The trigger fires on any entry and starts the quest if it is not running, as in FNV, where the player cannot reach it before 55.

### <a id="spike-4-exterior"></a>Goodsprings exterior (built 2026-10-07, played 2026-10-08)

The cell spike can add a block of an FNV worldspace
(`fo4_import/spike/exterior.py`, `--world WastelandNV --around -18 0
--radius 1`): Doc's front door stands in WastelandNV's persistent cell at
(-73,350, 1,297), grid cell (-18, 0) "Goodsprings". The 3×3 block holds
1,049 references (851 statics, 45 activators, 43 trees, 28 containers, 24
moving statics, 22 static collections, 11 misc items, 6 lights, 6 sounds,
6 doors, 3 furniture), 4 creatures and 9 LAND records of 24 to 28 layers.

- FO4's LAND has FNV's layout: DATA, VNML, VHGT, VCLR, and BTXT/ATXT/VTXT per
  quadrant (vanilla `0000F540` has 9 alpha layers in a quadrant, so no cap
  like Skyrim's 6). Two meanings differ (played 2026-10-11: the region's
  straight pale, grassless ground seams are about 95% gone):
  - **Opacities.** FNV paints each alpha layer over the ones below, so a
    vertex's opacities can sum past 1 (up to 1.51; 8.7% of FNV vertices).
    FO4's are shares of the vertex: none of 694,000 vanilla vertices sums
    past 1.0, and 53% sit at 1. Each layer is written as its opacity times
    what the layers above leave showing (`layer_weights`).
  - **Texture 0** (and a quadrant with no base) is the engine's default:
    FNV's is `DirtWasteland01.dds` (FalloutNV.exe and Fallout.ini
    `sDefaultLandDiffuseTexture`), FO4's `Ground\CommonwealthDefault01`,
    pale and grassless. The region has 272 alpha layers on texture 0 and 95
    quadrants with no base (whole columns at x -21 and -20). Texture 0 now
    becomes the lowest FNV LTEX using FNV's default (`Dirt10`, no grass),
    and every quadrant gets a BTXT.
  - **Seams at quadrant borders (played 2026-10-11: hard seams became soft
    edges).** FNV switches base texture at a quadrant border; 669 of the
    region's 1,950 quadrant borders change base, and the base is 58% of
    the ground. `land_layers.py` makes each quadrant a mix of shares (the
    base taking what the painted layers leave), and gives every vertex
    shared by quadrants, inside or across cells, their average mix.
  - That alone left straight seams. Fallout4.exe (and the CK, which shares
    the code) stores a weight byte per vertex for up to 12 layers
    (`0x4B3A90`), merges duplicate textures and puts the base in slot 0
    (`0x4BCD40`, base weight 255 minus the rest), and the landscape pixel
    shaders blend 4 textures per draw. Textures past the first 4 draw
    differently: listing the road first in every quadrant removed the road
    seams. So each quadrant keeps its 4 heaviest textures (the heaviest as
    the BTXT), and a shared vertex keeps only textures every quadrant on it
    keeps, renormalized. Vanilla holds 88% of its weight in the base and
    first 3 layers (layers sorted by coverage).
  - Cost: a median 7% of a quadrant's weight moves (p90 28%); 630 road
    vertices above 0.2 lose the road; 67 of 30,321 shared vertices cannot
    match (no common texture).
  - Ruled out on the way: a 3-layer cap (each quadrant kept different
    textures, so seams stayed in the data), FNV's terrain LOD textures as
    FO4's land-LOD blend target (seams got worse), and VCLR, DATA flags,
    VTXT grid order and texture formats (all match vanilla).
  FNV's LTEX names a texture (`ICON`, under
  `Textures\Landscape\`); FO4's names a texture set (TNAM), whose landscape
  sets are diffuse (TX00), normal (TX01) and specular (TX07).
- The worldspace record takes the Commonwealth's water, map and
  water-environment settings (`0000003C`), and FNV's climate
  ([weathers](fo4_pipeline.md#weathers)); its persistent cell and grid
  cells follow vanilla's (DATA `0x02`, XCLC, LTMP, no water). Exterior
  groups are labelled (y, x) in int16s: block = coordinate ÷ 32, sub-block
  ÷ 8 (vanilla cell (-89, 7) is block (0, -3), sub-block (0, -12)).
- Static collections carry their merged mesh (`SCOL\…`), placed as
  statics. Trees are SpeedTree (`.spt`), converted later ([trees](#spike-4-trees)).
  Grass came later (below), as did the exterior navmesh
  ([exterior navmesh](fo4_pipeline.md#exterior-navmesh)) and object LOD
  ([object LOD](fo4_build_next.md#object-lod)).
- **Played (2026-10-08):** in good shape. Open:
  - **Trees:** the block's 43 trees are not converted (since done:
    [trees](#spike-4-trees)).
  - **Porch teleport (not a bug):** stepping onto Doc's porch moves the player to the
    same spot each time. It is the one-time event that blurs the screen on
    first stepping outside, replaying. Not found in the data: the two doors link each
    other (FO4 FNAM 0, no Automatic flag), the porch trigger
    (`DocHouseTriggerREF`, `VCG01RemoveDocCarebearModeTrigger`) and the two
    triggers above the house carry no script in the exterior, no shipped
    script moves the player, and the worldspace bounds hold the whole block.
    The interior door's arrival point is on the porch at (-73,163, 1,312,
    8,686), 55 units under the porch floor (8,741).
  - Leaving Doc's house by its door: works both ways (played 2026-10-10).
- **First play:** invisible walls (one across a road at -69,091, 5,594),
  purple ruins and flagpole, blurry ground.
  - Collision placed twice. Static collections keep each part's collision
    on a child node (`Havok0`… of `SCOLGoodpringsFenceA01`, up to 2,000
    units from the origin). FNV's placement (node once) matches the
    visible fence (x -2,045 to 503 against -2,047 to 501); applied twice
    it reaches (-3,517, -3,870), covering the road spot, and is the only
    placement that does. Elric keeps the node transform on its output and
    bakes it into the physics too, so `elric.graft` resets a collision-only
    node to identity. (Wrong, corrected 2026-10-25: Elric keeps the vertices
    local and FO4 places them by the node; the reset was removed. See
    [collision nodes](fo4_pipeline.md#collision-nodes).)
  - A `bhkRigidBodyT` with a convex shape (163 placements: crates, the
    floor mattress, maize groups) now carries its transform in a
    `bhkConvexTransformShape` under an identity body, as a mesh shape
    already carries it baked.
  - Some FNV meshes name textures from `Data\Textures\…`
    (`SCOLgsRuinHouse*`), which was not stripped: purple.
    `convert_static.texture_source` normalizes every FNV texture path.
  - The Nevada flag keeps 11 bone helper boxes (`TTail3:0`…, 24 vertices,
    a material colour, no shader): FNV draws no shape without a shader
    property, the conversion gave them `untextured.bgsm`. Unshaded shapes are
    left out (in the block: only those 11).
  - FNV's ground normal maps are DXT1 (no alpha): the specular map took
    alpha 1 as full specular. A DXT1 normal now gets Skyrim's dim mask
    (`landscape_normals.SPECULAR_ALPHA`, 32).
  - FNV's ground textures are 512² DXT1; FO4's vanilla ground diffuse maps
    are 2048² (BC1/BC3), so FO4's tiling likely stretches FNV's 4× (not
    yet changed).
- **Second play:** black triangles on the ground by houses; FNV objects
  (the motorcycle, houses, the gas station sign) blurrier and glossier than
  the Skyrim conversion of the same files (`motorcycle01.dds` is FNV's
  1024² DXT1 in both; `iTexMipMapSkip` is 0).
  - The black triangles are FNV's baked soft shadows under buildings
    (`NV_NoSo_RanchHouse03:1`, `SCOLgsHouse03`'s `NVRanchHouse03002`):
    unlit, untextured, black vertex colours with alpha 0 to 1, an
    NiAlphaProperty blend, but no `sf_vertex_alpha`, so the effect shader
    ignored vertex alpha. Untextured, the vertex alpha is all FNV can fade
    by: an untextured unlit shape that fades now uses it.
  - Smoothness was far above vanilla's: our specular maps' G quartiles
    151/186/209 against 59/78/130 over 150 vanilla `_s` maps (R 45
    against 63). The Blinn-Phong to GGX relation was used with Walter's
    alpha as roughness; GGX alpha is roughness squared, so smoothness is
    `1 - (2 / (power + 2)) ** 0.25` (quartiles about 92/122/147).
- **Third play:** textures better; black triangles on bare hills; an
  invisible wall on the road at (-72,122, 729); the saloon's step needs a
  jump; the Poseidon sign now and then shows a lower-quality texture.
  - The hill triangles are terrain (no mesh there; the layer data is clean:
    sorted, in range, at most 6 alpha layers per quadrant against
    vanilla's 9, at most 6 per square against vanilla's 7). Vanilla writes
    a BTXT's layer as -1 (every one of 2,000+ sampled); ours wrote 0, an
    alpha layer's index. Now -1; not yet confirmed as the cause.
  - The wall is `VCG01TumbleweedHolderREF`, a CollisionMarker plane (FO4
    shares its id 0x21). FNV's `DefaultDisableLinkTrigger` around it
    disables its linked reference on entry; references kept no link, so the
    plane stayed. FNV's XLKR becomes FO4's (no keyword) when the target is
    converted (9 in the block).
  - The saloon's collision has no stairs material (FNV materials 0, 9, 17,
    3; stairs set bit 64): FNV's character steps up it, FO4's does not.
  - The sign is one shape (diffuse, normal, environment mask), no LOD
    node: the lower texture is FO4 streaming mips in.
- **Fourth play:** the road wall is gone. The black hill triangles stay
  with layer -1; the F4SE mod Black Landscape Fix clears them. The engine
  bug is real, but our data triggers it ([empty layers](#empty-land-layers)).
  Blurry textures vary between launches (sign one
  launch, sign and bike another); a wall in front of Doc's house; an
  uneven wall at the water tank and a ruined house you can slip into.
  - The sign's DDS is full size (512², 10 mips, as FNV's). FO4 streams
    mips from a BA2's chunks; loose files are known to stay blurry. The
    build now moves loose textures to `_ba2\Textures` and packs them as
    `<plugin> - Textures.ba2` (fo4_import/base/ba2_pack.py, Archive2).
    Archive2 skips the generated LUTs (uncompressed 24-bit, one mip;
    vanilla's sit in the general `Fallout4 - Misc.ba2`), so they stay loose.
    It writes names with forward slashes even given a root (vanilla's
    archives use backslashes); the game finds files by hash.
  - Elric ignores a collision node's scale (scale 0.62, 1.0 and 2.0 give
    the same physics but for run-to-run noise), and the graft sets the node
    to 1.0, so a scaled part's collision came out at full size. SCOLs scale
    parts: `scolgsdochouse02` 0.49, `scolgsruinhouse11` 0.62, the
    Goodsprings fence 1.19, parking lots 0.77–1.99, corn 0.89–1.43. The
    node now gets 1.0 and the shapes the scale.
- **Fifth play:** the Poseidon sign is sharp close up and blurry a few
  steps further out, every time; more invisible walls (in front of Doc's
  house, by the barrels west of the saloon, by `scolgsruinhouse06`).
  - The sign switch is FO4's texture degrade (`iTextureDegradeDistance0/1`,
    `iTextureUpgradeDistance0/1`): past the distance the game drops a
    texture's top BA2 chunk. Our chunking matched vanilla's (a 512 texture:
    mip 0, then the rest), so FNV's 512 textures fell to 256, which shows
    on logos drawn small. The gas station is one SCOL whose origin is about
    2,500 units from the sign. Textures now pack as one chunk each
    (`-maxChunkCount=1`; vanilla has 125 such 512 textures in Textures1–2).
  - `tools/nif/fo4_collision_audit.py` compares each collision part's box
    in FNV (pyffi), in our pre-Elric blocks and in the shipped mesh
    (`fo4_import/nif/hknp.py` reads Elric's hk_2014 packfile: body infos,
    convex polytope vertices, compressed mesh vertices). All 383 placed
    models match within 4 units at every stage (6 small ones use sphere,
    capsule or compound shapes the reader does not decode).
  - None of a placed mesh's collision reaches the Doc's-house wall. The
    barrels and tumbleweeds are FNV MSTTs (movable statics) whose bodies
    are dynamic, and they were placed as FO4 STATs; a wall sits 56–121
    units from three barrels. They are now FO4 MSTTs (EDID, OBND, MODL,
    DATA 0, as 506 vanilla ones), whose 3D follows the body. Not yet
    confirmed as the walls' cause.
- **Sixth play:** textures fixed; barrels now move when walked into; walls
  remain, one more at (-70,613, -3,128).
  - Triangles, not just boxes: at the rubble wall by `scolgsruinhouse06`
    the mound's collision is wound at random (Havok9: 42 faces up, 38 down,
    no authored normals), identical in FNV and ours. FNV collides both
    sides; FO4 does not. The shared winding repair
    (`repair_inverted_floors`, `two_sided_floors`) takes its render oracle
    from the collision node's own subtree, and a SCOL's Havok nodes have
    none, so no SCOL part was ever repaired. A collision-only node now
    gets the whole mesh's render triangles in its own frame
    (`collision.visual_tri_soup_in`); Havok9 comes out all faces up, with
    the floor rule's reversed copies (80 → 148). Over the block's placed
    models it changes 17 SCOLs (houses, ruins, gas station, fences,
    parking lots, roads): 2,777 faces turned and 2,713 reversed copies
    added. Road surfaces were nearly all face down (90 of 94, 172 of 190).
    The shipped audit still matches FNV everywhere.
  - At the Doc's-house wall and the new one nothing with collision is in
    reach, in FNV's REFRs or ours: the nearest is a fence line or house
    part 170–270 units away, and no primitive, actor, tilted reference,
    water or terrain slope (7–21°) explains them.
- **Seventh play:** walls remain. Console clicks in front of house06 pick
  only `0B1003EE` (the house) or "Picked Non Ref AV Object".
  - Decoding Elric's faces (compressed mesh primitives: four u8 corner
    indices, a quad when the last two differ; a section's u32 at 0x4C is
    shared-index offset << 8 | packed count, at 0x50 primitive offset << 8
    | count, bytes 0x58/0x59 packed and shared counts) shows no face of
    house06 over the clicked spot, nor any of FNV's or our pre-Elric
    triangles. The pick likely passed through to the house behind.
  - Vanilla multi-body meshes share one bhkPhysicsSystem among their
    collision objects (177 of 177 sampled architecture/setdressing NIFs);
    the graft gave each object its own copy of the whole system (house06:
    18 objects, 18 copies of 18 bodies). Every SCOL, and only SCOLs here,
    has several. The graft now shares one system, as vanilla does.
  - FNV's placement rotation is Rx(-x)·Ry(-y)·Rz(-z) (11 of 12 tilted SCOL
    parts land exactly on the GECK's merged SCOL mesh).
- **Eighth play:** walls remain with the shared system, and they are not in
  the Skyrim conversion of the same block, so they come from the FO4 path.
  - SCOLs are now placed as their parts (`fo4_import/spike/scol.py`): each
    SCOL's ONAM/DATA read from FalloutNV.esm (the export drops them), every
    placement composed with the reference's (position, rotation, scale) as
    a reference of its own. The block's 22 SCOL references become 355 part
    references; parts land exactly on the merged mesh (median gap 0) except
    the three parking-lot chunks (median 2–3 units, p95 13–18).
  - FormIDs: a part reference's is hashed (`derive_formid`, the writer's
    0x400000–0xFFF000 region) from its SCOL reference's FNV FormID and its
    index in the SCOL's part list; a base first made for a part only used in
    SCOLs (20) from the part's FNV FormID. Both keys are authored, so a part
    keeps its id however many cells are built. The exterior's bases are made
    up front in placement order (`Exterior.placement_order`), so no existing
    record moves (2,231 compared, 0 moved; 22 SCOL references gone). The
    SCOL bases themselves are still written, unused, to keep later ids.
    (Since [FormIDs](#formids), a part's base takes FNV's id, as when it is
    placed by itself. The hashed part-base id depended on how the base was
    first reached: building 5×5 cells instead of 3×3 moved two wires,
    `CeilingMountWire` and `GeneratorWire`, placed directly there.)
- **Ninth play:** the split fixed the walls. Cause not pinned down: every
  file-side check of the merged meshes matched FNV (boxes, vertices,
  decoded faces), so the difference is in how FO4 loads a mesh with many
  bodies on our collision-only nodes (Elric-baked bodies, nodes reset to
  identity), which a part mesh (one body on the root) never uses. Cost: the
  22 SCOLs drew 99 shapes merged and 422 as parts (the block's other
  references 1,349), about +22% shapes for the block.
- **Grass** (`fo4_import/spike/grass.py`): both games scatter grass at
  runtime from each LTEX's grass list (GNAM) over ground painted with it,
  so nothing is regenerated. FNV's 24 GRAS become FO4 GRAS (FormID hashed
  from FNV's; DATA copied, FO4's 32-byte layout is FNV's: vanilla
  densities 1–96 against FNV's 4–100), and each converted LTEX lists its
  FNV grasses (52 links over FNV's 89 LTEX). FNV grass draws with a
  TallGrassShaderProperty whose file name is the texture; the converter
  now reads it (it gave an untextured material). The 17 grass meshes come
  out alpha-tested and two-sided with no normal map; FNV's grass sway is
  not carried.
  - First play: no grass. Records, links, LAND flags (0x1F, as vanilla's
    textured LAND) and coverage (the block's grass LTEX: 43 layers) were
    right, and FNV's "above water by 0" is vanilla's too (46 GRAS, with
    36,320 Commonwealth cells at the no-water height). Every vanilla FO4
    GRAS model (71) sits directly in Landscape\\Grass, the contract Skyrim's
    grass renderer has (`asset_convert/nif/grass_profile.py`); ours were
    in fnv\\landscape\\grass. The converted mesh is now copied to
    Landscape\\Grass\\FNV_<name>.nif. Vanilla grass shader flags vary
    (flags1 0x80400201 in 44 of 71, flags2 0x31 in 29), so they were left.
  - Physics clutter far too light (2026-10-20): FNV's wooden barrels and
    the Sarsaparilla crates flew when walked into (one over a building);
    in FNV they barely move, and vanilla FO4's 15 kg trash can and 75 kg
    oxygen tank stay put. Mass, damping, friction, restitution, speeds,
    gravity factor, motion and shape type all match FNV's and vanilla's
    conventions. A probe giving FNV_Barrel01 vanilla's oxygen tank mesh
    behaved like vanilla, and a freshly spawned wooden barrel flew, so
    the mesh is at fault. Both are on FNV's props layer (10). In vanilla
    FO4, layer 10 holds only small knock-about props (25 moving bodies,
    glasses, vases, rattles, skeletons: 10 kg or less); everything that
    resists a kick, up to 100 kg, is on clutter (4, 305 bodies). A moving
    body on FNV's props layer now takes clutter (`collision.MOVING_LAYERS`;
    77 bodies in the region build); fixed bodies keep theirs. Played
    2026-10-21: the wooden barrels and crates stay heavy when walked into.
  - Floating grass on slopes (2026-10-20, fixed 2026-10-21): tufts sat on a
    flatter surface than the terrain, above it downhill and under it
    uphill. Ruled out: the GRAS layout and flag bits (same in both
    games), slope limits and position ranges (vanilla's range), the
    meshes (FNV's vertex for vertex, no wider than vanilla's tufts,
    sunk deeper than vanilla's), the shader (vanilla grass sets no
    fit-to-slope shader bit), the NIF layout (vanilla's NiNode plus
    shape), LAND heights, normals and flags (copied, vanilla-legal), a
    grass cache (none), and terrain LOD (xLODGen's FNV_WastelandNV LOD
    installed: still floating), and GRAS flag 0x1 (all 82 vanilla
    grasses set it, no FNV grass does; set on ours: still floating at
    Goodsprings and Primm, reverted). What we write matches vanilla;
    the placement mechanism was next. Project Mojave's grass does not
    float, and a probe putting our 15 grasses on its model sat on the
    hill: the model was the fault. Vanilla grass vertex alpha is a height
    ramp, 0 at the base rising to 50-190 (correlation with height +0.83
    to +0.99), as is Project Mojave's; FNV authors the same ramp. Ours
    was 255 everywhere: `convert_static.opaque` (vertex alpha on lit
    shapes, [vertex-alpha](fo4_pipeline.md#vertex-alpha)) also flattened
    grass. A TallGrassShaderProperty shape now keeps FNV's vertex alpha
    (`convert_static.is_grass`; 10 models, 0 to 31-191). Played: the
    grass sits on the hillsides.
  - Second play: grass shows, a little thick; density is now FNV's × 0.5
    (`grass.DENSITY_SCALE`).
  - Third play (2026-10-19): still too thick, so FNV's × 0.25. The grass
    also went from bright to dark with the view. Its BGSM was a plain lit
    two-sided material, so the side of a blade facing away from the sun
    drew unlit. Vanilla grass lights through the blade: of the 28 BGSMs in
    Materials\\Landscape\\Grass, 26 set subsurface lighting and 22 a
    backlight power, the commonest setting (6) subsurface rolloff 4.0 and
    backlight 12.5. A TallGrassShaderProperty shape (every FNV grass mesh,
    17 of 17) now takes that (`convert_static.GRASS_MATERIAL`). Vanilla
    grass also sways through Tree_Anim and vertex alpha; FNV's sway is
    still not carried.
- **Steps.** The saloon's front step is `WoodSteps01NV`: FNV material 0
  (stone, no stairs bit), risers 15–16 units (collision tops at 3, 16, 31,
  47, 65; placed at 8,316 on ground at 8,352, so about 16 units show per
  step). FNV's controller walks up it; FO4's does not without a jump.
  FO4's `[HAVOK] fStepHeightModifier` defaults to 0.5 (read from
  Fallout4.exe with `tools/disasm/ck_settings_dump.py`, Python 3.13 with
  capstone); FNV has no such setting. FO4 also has a stairs state for its
  character controller (`bCCOnStairs`), entered on its stairs materials,
  which vanilla puts on step collision.
  - Played: `fStepHeightModifier=1.0` changed nothing, and the console
    finds no such setting: FO4 compiles the name and default in but does
    not register it.
  - What is climbed: the steps' treads sit at 3, 16, 31, 47 and the deck at
    65 (local, rising toward -X); the ground meets them at local 36, so the
    walk is 11 units onto the last tread, then 18 onto the deck.
  - Vanilla stair collision (decoded with `fo4_import/nif/hknp.py`, face
    slopes and material CRCs): plain risers up to 16–17 units carry no
    stairs material (decobasea1x1stairs01: risers 16–17, no ramp, no
    material; housekit stairs: material 9); the 21–22-unit risers of
    hitextintstairs128 carry stairs material (FO4 CRC of STAIRS[5]) with
    only small 18° nosing bevels, no ramp; bossteps01 (risers 14–20) also
    carries it. So FO4 climbs about 17 units on plain collision and taller
    risers with stairs material. FNV marks only its staircases (bit 64).
  - Built: `fo4_import/nif/stairs.py` marks steps in every FNV mesh
    collision with the stairs variant of their material (STAIRS[0], stone
    stairs, where FNV's has none). WoodSteps01NV has no riser faces: each
    step is a floating plate (treads at 16, 31, 47, the deck at 65 with a
    17-unit gap before it), so a step is two treads, the lower within
    REACH (24) beyond an edge of the upper, more than RISER_MIN (16, what
    FO4 climbs on plain collision) and at most RISER_MAX (24) below it.
    WoodSteps01NV marks tread 47 and the deck (the 18-unit step). Marking
    every step up to 24 touched 94 of the block's 179 mesh-collision models
    (road edges, rock ledges, logs) for no climbing gain; above 16, 27
    (house shells, Novac buildings, beds, a bathtub, some rocks). A rule
    for short vertical faces under a tread (a step up from open ground)
    marked every board's front edge, so it was dropped; a step up from
    terrain is not seen, the ground not being in the mesh.
  - Played (RISER_MIN 16): the marked step (47 → deck, 18) works; the one
    below still sticks, run into it long enough and you slip up. Terrain
    sampled along the steps sits at local 24–28: tread 16 is buried, tread
    31 shows 3–7 units, so that step is 31 → 47, 16 units, left plain.
    FO4's plain limit is under 16, so RISER_MIN is now 8 (curbs and lips
    stay plain): 54 of the block's 179 mesh-collision models get stairs
    faces, the shelf's 11-unit bottom board among them.
  - Played (RISER_MIN 8): still stuck at 31 → 47 though marked. The step
    that worked (47 → deck) is the only one with an upright face (the
    deck's skirt, 54–65); FNV's step plates have none between them (no
    near-vertical face tops at 47), so FO4's character meets a bare plate
    edge and the plate's underside. Each detected step now also gets a riser:
    two upright triangles from the upper tread's edge down to the lower
    tread, facing out, on the stairs material (deduplicated per edge, as
    the repair doubles treads). In the shipped WoodSteps01NV: risers at x
    108 (16–31), 73 (31–47) and 21 (47–65). The audit still matches FNV.
  - Played: the general store's steps work; the saloon still not reliably.
    The saloon's own porch: a front strip at local 3, the porch floor at 16;
    terrain along the front at local −16, so the street-to-porch step is 19
    units, from the terrain, which no mesh rule saw. The porch has a skirt
    from −15 (the mesh's lowest point) to 3. An upright face rising from the
    mesh's lowest point (within 2) to a tread 8–24 above it is now a step
    from the ground, marked with its tread (shelf base boards qualify too).
    63 of the block's 179 mesh-collision models get stairs faces.
  - *24-unit steps (fixed and played 2026-10-18: the Bison Steve stairs).*
    FNV's kit stairs rise 24 units (`HtlHallSmStairs03`: treads 0, 24 …
    288), which read 24.003 apart after the Havok scale, just past
    RISER_MAX, so none was marked. Both riser tests now allow TOUCH, as
    every other height test in the pass does: all 12 steps marked, with
    risers; 37 of the region's 2,365 meshes change (hotel pieces, Bison
    Steve's entrance, broken Old Town buildings, and 24-unit edges of
    beds, shelves and a footlocker, which FNV's player could step onto).
  - <a id="stair-ramps"></a>*Stair-helper ramps (built and played 2026-10-21: the staircase climbs smoothly).*
    Played: `OTBldgDestroy01NV`'s inside staircase (13 steps, 24 up,
    26.8 deep, 41.9°, all marked, risers in place) climbs only by
    pushing into it. Steepness is not the cause: vanilla ships steeper
    (`bldbricksmstairs03` 23 over 23, `qrystonestair01` 25.5 over 25.5).
    Vanilla's staircases carry a second body beside the stepped mesh: an
    8-vertex convex slab whose top runs along the nosings to the foot
    (`bldbricksmstairs01`, `02`, `03`, `qrystonestair01`,
    `churchintstairs01`), its collision filter layer 31, the stair
    helper, which only the character controller meets (the steps are on
    layer 1). The stairs pass now finds flights (3 steps or more on one
    edge span, each rising from the last and further along) and gives
    each such a slab, 4 units thick, on its own NiNode
    (`StairHelper`, the owner's place) with a layer-31 body
    (`collision._stair_ramps`); only still bodies, not animated ones.
    The building gets one ramp (y −153 to 195, z 20 to 336); the hotel's
    switchback stairs one per flight. In the region, 4 meshes get ramps:
    `OTBldgDestroy01NV` and `02NV`, `HtlHallSmStairs03` and
    `CasLoPit2xStairs01` (34°). After Elric each holds a second,
    8-vertex body on layer 31, as vanilla's. A static's root is always in
    the converter's kept-node map, so stillness is judged as the body
    writer does (keyframed on an animated node moves), not by that map.
- **Items** (`fo4_import/spike/consumables.py`): consumables (ALCH) and
  ammunition (AMMO) were skipped wherever they appeared, and placed ones
  stood as static stand-ins. In this block: a Speech magazine and a 5.56
  box on the ground; in containers 13 skill magazines, Nuka-Cola, Sunset
  Sarsaparilla, five plant foods and a hockey mask (armor, still skipped).
  - A consumable keeps name, model, value, weight and kind (FNV ENIT flags:
    food 0x2 kept, medicine 0x4 to FO4's 0x10000), with Nuka-Cola's or the
    Stimpak's sounds and category keyword. Effects: RestoreHealth →
    RestoreHealthFood, DamageRadiationLevel → DamageRadiationChem,
    NukaColaAddCap → NukaColaBottlecapAdder, IncreaseSkill* → a copy of
    Rad-X's timed boost (FortifyResistRadsRadX, archetype 5; actor value
    at DATA 0x44, per xEdit) on the helper plugin's skill actor value. An
    effect gated on HasPerk is read as without the perk (magazines keep
    their +10 for 60 s). Dropped: Hardcore needs, chem stats, limbs,
    scripted effects (counted per effect in the build).
  - Ammunition: FNV's name, model, value and weight over FO4's Ammo556
    (projectile, keyword, sounds).
  - FormIDs: consumables, ammunition and skill boosts are hashed from FNV's;
    a leveled list first made non-empty by them is hashed too, and a
    placed consumable's old static base keeps its numbered id unused, so
    no existing record moves (2,591 compared, 0 moved; the 23 static
    stand-ins are gone, their references now on the items). Since
    [FormIDs](#formids), leveled lists keep FNV's id and nothing is
    reserved.
  - Played: items work; harvested foods made a bottle sound and showed no
    Pip-Boy preview. Every FNV food item had taken Nuka-Cola's sounds. A
    consumable's category now comes from FNV's ETYP (10 chem, 11 stimpak,
    12 food, 13 alcohol) and its ENIT consume sound (NPCHumanEatingFood*,
    NPCHumanDrinking*, NPCHumanUsingComic...), both dropped by the export
    and read from FalloutNV.esm; it takes that vanilla item's PTRN, YNAM,
    ZNAM, CUSD and consume sound and a plain category keyword (Mutfruit,
    NukaCola, Stimpak, Mentats, BeerGwinnettStout_Cold; magazines a perk
    magazine's preview).
- **Mobile home threshold (fixed: the player was too tall, see the
  [step map](#step-map)).** Enter, can't leave, behind the saloon
  (0x10638D); the same model east of town (0x1070C1) left fine. No
  collision difference between the two was found (same mesh, nothing
  placed at either door, terrain 6 units lower at the saloon one). Its
  only opening is at x −344..−248, y+ side: the floor (47) ends in a
  10-unit lip with no top, a 15–22 unit hole, then the skirt's top edge at
  56–62; the render mesh's threshold sits 14 units further out. Tried and
  reverted: 30° ramps onto treads under REACH / 2 deep (they landed on the
  two 10-deep sills at x 13–107, which are closed doors), and a
  stairs-marked tread bridging the hole at the lip's top (both homes then
  trapped the player, who bounced up and down at the door). Played: the
  same home leaves only with the doorway raised: X tilt 0 and 0.2138 trap,
  0.3038 is 50/50, 0.4938 and up leave, door south; the same tilt with the
  door north traps (the tilt is about the world axis, after the heading).

### <a id="empty-land-layers"></a>Empty land layers and Black Landscape Fix (census 2026-11-12)

- **What the mod does:** Black Landscape Fix (Nexus 108574, an F4SE plugin)
  hooks the terrain renderer. Its `SanitizeMergedLayers` runs on the
  texture layers and weights the game gathers for each LAND before drawing,
  and drops "excess" layers and "invalid weighted" layers. Affected ground
  falls back to its base texture instead of drawing black. With
  `bEnableCellLogging=1` in its ini, it logs each cell it cleaned:
  `terrain scratch sanitized: cell=…, land=…, retained N, removed X excess and Y invalid weighted layer(s)`.
- **The census** (scratch `land_census.py`; vanilla `Fallout4.esm` against
  the 2026-11-12 `FalloutNV.esm`):

  | | Vanilla (37,020 LAND) | Ours (29,180 LAND) |
  |---|---|---|
  | Layers in the fullest quadrant | up to 10 | at most 4 |
  | Distinct textures in one cell | up to 15 | at most 11 |
  | Most alpha layers weighted at one vertex | up to 6 | at most 3 |
  | Alpha layers with an empty VTXT | 0 | 154,352, in 15,080 cells |

- **The cause in our data:** the land writer gave every texture that
  `land_layers.limit_textures` kept an ATXT, then wrote that layer's VTXT
  only where its share was over `MIN_SHARE`. A kept texture with no share
  that large anywhere in the quadrant got an ATXT with an empty VTXT. This
  is mostly a neighbor's texture that `blend_borders` brought to a shared
  edge and the limit then trimmed. We never exceed vanilla's layer counts,
  so the mod has no excess layers of ours to drop.
- **Fix:** `exterior._land` leaves such a layer out and numbers the rest in
  order (counted as `land alpha layers left out (no share)`). Those layers
  drew nothing, so the ground should look the same. Not yet played: the
  check is the mod's log (no cells on the fixed build), then a play
  without the mod.

### <a id="spike-4-trees"></a>Trees (built 2026-10-09, played 2026-10-10: they look right)

FNV has 3 TREE records, all SpeedTree (`.spt`): its Joshua trees, dead
trees and palms are ordinary meshes, converted as statics already. The
block's 43 trees are one, `WastelandShrub01`. `fo4_import/nif/tree.py`
builds its mesh from asset_convert.speedtree's generator (bark, leaf cards
with the wind weight in vertex alpha, a collision mesh; seeded by the
record's first seed, leaves from its ICON; the Oblivion-engine geometry path
needs a configured Oblivion.exe and is not used), as vanilla builds trees:

- Vanilla Fallout 4 has no TREE records; its 175 tree meshes
  (`landscape\trees`) are statics. 108 have a NiNode root and materials
  without the tree flag (dead trees, stumps); 66 have a BSLeafAnimNode
  root and tree-flagged materials (98 shapes), the wind-animated ones.
  All are alpha-tested and nearly all two-sided; BSXFlags 130 on 131 of
  151.
- The shrub follows blastedforestfungaltreelarge01: BSLeafAnimNode root,
  BSXFlags 130, vertex-coloured shapes, the leaves' shader flags
  0x80400209 / 0x20000031 (Tree Anim) with alpha test 0x12EC at 160 on a
  two-sided, tree-flagged BGSM; the bark's 0x8C400201 / 0x21.
- Collision: the generated mesh, wood, on FNV's own tree body
  (nvgreybirch01: static layer, fixed motion, as FNV's tree meshes),
  finished by Elric as the statics' is.
- The TREE becomes a STAT on a FormID hashed from FNV's (`FNV TREE`), so
  no record moves.

### <a id="spike-4-sounds"></a>Sounds (built 2026-10-09, played 2026-10-10: they work)

In Doc's house and the block: 8 placed SOUNs (ambient loops: Doc's fridge
and bathroom, the air conditioner, a light string), 23 doors' open and
close sounds, 28 containers', 6 activators' loops. An FNV SOUN names a file
or a folder (one file picked at random) with attenuation and flags
(xEdit: Loop 0x10, min distance ×5, max ×100).

- Fallout 4 splits it: a descriptor (SNDR: CNAM type, GNAM category, ANAM
  files picked at random, ONAM output model, LNAM playback flags, BNAM
  priority and attenuation; 5,475 in Fallout4.esm) holds the sound; DOOR
  SNAM/ANAM (263/259 vanilla uses), CONT SNAM/QNAM (265 each) and ACTI SNAM
  name SNDRs; a sound marker (SOUN: EDID, OBND, SDSC, 179 vanilla) places
  one.
- `fo4_import/spike/sounds.py` writes one SNDR per FNV SOUN, copied from
  the vanilla descriptor of its kind: a looping one (FNV Loop) from
  AMBSteamVaultPipeA, the rest from DRSWoodSingleLightLoadAOpen. Its files
  are FNV's (49 here), converted to .xwm under `Sound\FX\FNV` and named
  .wav, as vanilla names its .xwm files.
- Volume and reach are FNV's (`Sounds.playback`). Both games store static
  attenuation in hundredths of a dB (FNV SNDD i16, FO4 BNAM u16), so FNV's
  copies into the template's BNAM. FO4 keeps reach in the output model
  (SOPM ATTN, minimum and maximum distance as floats at bytes 8 and 12):
  the vanilla `SOMMono<distance>` model (26, 250 to 40,960 units) nearest
  FNV's maximum distance; FNV's 0 (484 sounds) keeps the template's.
  Played 2026-10-19 before this: the Vikki and Vance casino hum drowned
  everything. The template (AMBSteamVaultPipeA) is 18.9 dB over 80-800
  units; FNV's fluorescent hum (`AMBLightFluorescentLP01`) is 46.7 dB over
  400, its neon sconces (`EMTNeonSignNeoClassicalSconce`, 11 in the casino)
  57.3 dB over 300. Vanilla's own fluorescent buzz is 19-26 dB over 500.
- FormIDs are hashed from FNV's (`FNV SNDR`, `FNV SOUN`): 44 records added,
  none moved.

### <a id="spike-4-animations"></a>Door and container animations (built 2026-10-09, played 2026-10-10)

FNV and Fallout 4 animate doors and containers the same way, inside the
mesh: a NiControllerManager on the root (vanilla: 201 of 227 door meshes, 94
of 119 container meshes) whose NiControllerSequences ("Open", "Close") drive
named nodes through a NiMultiTargetTransformController, NiTransformInterpolators
and NiTransformData, with NiTextKeyExtraData and a NiDefaultAVObjectPalette.
The static conversion flattened every shape into the root, so nothing could
move.

- `fo4_import/nif/anim_blocks.py` reads and writes the seven block types
  (nif.xml at 20.2.0.7; FNV's stream 34 and Fallout 4's 130 share them):
  all 343 vanilla door and container meshes rebuild byte for byte.
- `fo4_import/nif/animation.py`: the nodes a sequence names, and those
  between them and the root, are kept with their own transforms; shapes
  under them sit in their space; the controller blocks carry over with
  strings and references renumbered (vanilla: empty controlled-block
  strings -1, a text key list named ''). Collision on a kept node stays on
  it (`collision_nodes`), so it moves with the door.
- BSXFlags Animated (0x1) is set on such a mesh, as on every vanilla
  animated door and container (139, 11, 171, 43...).
- Only NiTransformInterpolator sequences carry over; a mesh with another
  interpolator stays static. Weapon and equipment meshes stay static
  (`animated=False`): FO4 animates weapons through behaviour graphs, and
  the headgear and outfit fitting expect the flat layout.
- Checked: all 2,275 vanilla meshes holding any of the seven types rebuild
  byte for byte. In this build 26 meshes keep animation: doors and gates
  (Doc's, the saloon's, two fence gates, the shack cabinet), containers
  (fridge, footlocker, gun cabinet, toolbox, first aid kit, ammo box,
  dumpster, range, Mojave Express drop box, a mailbox), the harvestable
  plants' Forward/Backward, and Idle/SpecialIdle loops (a fan, a flag,
  vultures, two windmills, the saloon sign). Elric built every collision,
  the moving ones on their node; no record changed.
- **First play:** the bathroom door and fence gates played their sound but
  did not move; after leaving and coming back they stood where the click
  had put them. Doc's flag did not wave.
  - The moving part's body was fixed. FNV gives it the keyframed motion
    system (6), which `collision.MOTIONS` had mapped to fixed (5) while
    the animation was dropped ([collision](#spike-2-collision)); a fixed
    body holds its node still each frame, and only the end pose set at
    load showed. A keyframed body on a node that keeps its animation now
    goes to Elric as Havok 2014's keyframed (4), which gives it a motion
    (Elric's physics for the craftsman door: 1,508 bytes, 1,380 fixed).
    Changed: 12 meshes (doors, gates, fridge, gun cabinet, dumpster,
    toolbox, shack cabinet, mailbox, windmills); a keyframed body on a
    static mesh stays fixed.
  - The flag is skinned: two shapes weighted to ten bones that its Idle
    loop moves, as vanilla FlagWavingMinutemen01.nif (BSSkin::Instance and
    BoneData, which plays a looping sequence on a static too: 12 vanilla
    meshes loop "Idle" with no behaviour graph). The static conversion had
    baked it flat. An animated mesh now keeps the bones its skins name
    (`animation.skin_bones`), and each skinned shape is weighted to them
    (four heaviest weights per vertex). A bone's transform takes a
    root-space point to bone space: the shape's placement undone, then
    FNV's skin transform (pyffi's `get_skin_deformation` reads it so); at
    the stored pose every vertex lands within 0.08 units of pyffi's
    skinning. FNV's NiGeomMorpherController (8 morphs rippling the cloth)
    is dropped: a BSTriShape has no morphs, so the wave is the bones'.
  - Every kept node's rotation had been written transposed (pyffi lists a
    Matrix33 row by row; the file holds it column by column, as
    `collision.node_transform` already reads it). Turned back: parts of
    the saloon sign, ammo box, toolbox, mailbox flag, fan, a windmill, the
    shack cabinet, the vultures and the flag's bones.
- **Played (2026-10-10):** doors and gates open and close, the flag waves.
  Open: an opened door shows what is behind its frame (as in the Skyrim
  build). See [load doors](#spike-4-load-doors).

### <a id="spike-4-load-doors"></a>Load doors stay shut (built and played 2026-10-10: the door loads without opening)

Fallout 4 swings a load door open before the loading screen; FNV goes
straight to it. An opened FNV load door showed what is behind it.

- **FNV's load doors are not built to open.** Doc's exterior door uses the
  animated craftsman door mesh (the same as the bathroom door), but behind
  it `CraftsmanHomeA` closes the doorway: rays through the doorway at 12
  points all hit one wood face 3.2 units in front of the panel's middle
  (panel x -11..5, door frame). Its interior partner uses the static
  `nvcraftsmanrmdoor.nif`. The house is a closed shell with the door laid
  on its wall.
- **Fallout 4's way does not fit.** Vanilla load doors are their own bases
  (57 models, 974 placements); the CK wiki's Door page says a load door
  differs only by "a solid black or white backing". In the mesh:
  `paintedwooddoorload01.nif` is `paintedwooddoor01.nif` plus a 4-vertex
  `BlackPlane` on the root across the doorway, inside the closed panel (y
  3 in -5..11), on the door's own material. No placed `BlackPlane`
  (5,421 of them) is within 300 units of a load door. Built and played:
  an unlit black quad through the panel's middle; the house's wood face
  in front of it showed instead.
- **Built: a load door is static.** A door placed with a teleport (cell,
  exterior, QASmoke stand-ins) takes `CellBuilder.load_door`: a copy of
  its DOOR (`FNV_<edid>Load`, FormID hashed from FNV's at
  `FNV DOOR load`) on `<model>load.nif`, the mesh converted without its
  animation (its moving body fixed). Fallout 4 loads through a door that
  does not move (vanilla `vltdoorload01.nif`). A mesh with no animation
  keeps its plain base.
- The saloon's door leads into an interior the spike does not build, so
  it is a plain door here and swings open onto the empty building; it
  becomes a static load door once that interior is converted.

### <a id="spike-4-creatures"></a>Creatures: Cheyenne on Dogmeat (built and played 2026-10-10: works in game)

The first creature by the census's second way ([census](#creature-census)):
FNV's mesh on FO4's creature, its animations, AI and combat. Cheyenne
(`GSCheyenne`, Sunny Smiles' dog; FNV parts `dogskin.nif` and
`eyessetblue.nif` on `creatures\dog\skeleton.nif`) is placed in QASmoke,
since the saloon she lives in is not built.

- **Mesh** (`fo4_import/nif/creature.py`). FNV's dog skeleton rest pose is
  `dogskin.nif`'s bind pose (every bone 0.0 apart); FO4's Dogmeat bind data
  is the same in all six of `Dogmeat.nif`'s shapes and within 0.25 of
  `skeleton.nif`. The parts are converted as statics, each vertex moved
  from FNV's skeleton onto Dogmeat's by the `DOG` rig (`retarget.py`,
  shared with the outfits: pelvis to spine to neck to head, legs as
  collarbone/leg/ankle/toe, tail 1 to 5; the head moves with the neck, as
  FNV's off-centre muzzle bone, x -3.9, turned it sideways), then weighted
  from Dogmeat's surface. The body's vertices sit a median 0.6 units from
  Dogmeat's surface (95% within 2.4); eyes, mouth and tongue within 1.7.
- **Rigid parts.** FNV attaches a part's root node in place of the
  skeleton's node of that name, keeping the part's own local transform
  under that node's parent: `eyessetblue.nif`'s root `EyesBlue` under
  `Bip01 Head` puts the eyes at x ±4.6, level with FNV's eyelid bone.
- **Shapes.** One BSSubIndexTriShape per FNV shape with Dogmeat's segment
  layout (an empty segment, then every triangle; Dogmeat has no
  dismemberment data). FNV's `MeatCap` shapes are left out.
- **Records** (`fo4_import/spike/creatures.py`): copies of `dogmeat`
  (`0001D15C`), `SkinDogmeat` and `DogmeatAA` on FormIDs hashed from FNV's
  (`FNV CREA`); the NPC keeps Dogmeat's race, stats and keywords, drops his
  scripts, factions, perks and spells, and sandboxes at its spot
  (`DefaultSandboxEditorLocation`). FNV's own packages (follow Sunny) wait
  for Sunny.
- The mouth takes Dogmeat's jaw and lip weights by surface, not FNV's jaw bone.

**Super mutants and nightkin on FO4's super mutant (built 2026-10-31, played 2026-11-01 and 2026-11-02).**
The same way, by the outfits' `HUMAN` rig: FNV's `creatures\smspinebreaker`
parts (a base body with its own head, plus an armor NIF: 91 records, 34
distinct part lists, nightkin included) on
`Actors\Supermutant\CharacterAssets\SupermutantBody.nif` and its
`skeleton.nif`, whose bones carry the human names.

- **Body space.** FO4's super mutant body skins in a space 140 units below
  its skeleton (every bone's bind data in all three shapes agree, z -140;
  Dogmeat's 0.2): its vertices run z -140.5 to 19.8. The fit moves FO4's
  skeleton by that shift before retargeting (`outfit.skin_shift`, the human
  body fit's same correction), so FNV's mesh lands in the body's own
  space. Without it every vertex sat ~90 units off. With it the feet sit a
  median 1.1 units from FO4's (soles at -140), boots 2.3, the four other
  bodies checked (nightkin, Marcus, captain, vault) a median 3 to 7.
- **Head.** FO4's body has no head (the race's `SupermutantHead` head part
  draws it), FNV's base NIF has its own. FNV's head vertices take FO4's
  `Head_skin` weight by nearest surface (the neck cap), all 1,421 headgear
  vertices and every base-mesh vertex above the neck. The copied skin and
  addon add slot 32 (FaceGen head) to their BOD2 (`SkinSuperMutant` and
  `SuperMutantBody` cover only 33), as vanilla's whole-body skins do
  (`FeralGhoulGlowingWhole` 0x0C, `AA_SynthGen1`), so the race's head part
  is hidden. Dogmeat's race has no head parts, so the dog is unchanged.
  FNV's head reaches z 35 to 40 against FO4's 17.7: FNV's taller head and
  hunch are kept (drift: the race's capsule is FO4's).
- **Records.** A unique target (Dogmeat, ACBS 0x20) loses its perks and
  spells with its scripts and factions; a kind's template
  (`EncSuperMutantTemplate`: `ImmuneToRadiation`, `crDamage125`) keeps
  them, as the `stats` stand-in did. A template actor with its own base
  scale gets a sized copy as in `stats` mode (`traits_variant`), sharing
  the creature's skin (written once).
- **Weights: FNV's own (fixed 2026-10-31, built 2026-11-01).** Played, the
  first build's bodies stretched when dead (long thin arms and neck) and
  armor pieces came away from the body. Taking FO4's body weights at the
  nearest surface point, as the dog does, fails on a body shaped unlike
  FO4's: FNV's bulky torso and armor lie nearest FO4's arms. In
  `nightkinbare.nif`, 46 of 90 vertices in one armor shape took arm weights
  and one 34-vertex piece took only the right arm. With the left arm raised
  90 degrees at the shoulder, edges stretched up to 17.7x (nightkin) and
  34.5x (captain). The pair now keeps FNV's own weights (`Pair.own_weights`):
  each FNV bone goes on its rig bone in FO4's body, or that bone's `_skin`
  helper (`Neck`, `HEAD`, `LLeg_Calf` and `LArm_ForeArm1` are skinned only
  as `_skin`), and an unmapped bone (fingers, twists, ponytail) goes on its
  nearest mapped ancestor's. The same pose now stretches at most 3.2x and
  3.4x, against 4.0x for FO4's own super mutant body. The rig still
  lengthens FNV's arms 1.2x and its neck 1.55x along themselves, to FO4's
  bone lengths. The dog keeps the surface weights: its body has FO4's shape,
  and they give it FO4's jaw and mouth bones.
- **Nightkin stealth is the scripts', not the records'.** FNV's nightkin
  have no invisibility ability: `CrNightkinSCRIPT`, `CrNightkinGunScript`
  and `CrNightkinCloakUntilFireScript` add `StealthBoyInvisibilitySpell` on
  load and remove it when `GetAnimAction` reads an attack. Nightkin without
  a script are visible in FNV too: Jacobstown's, the dead ones,
  `CrNightkinSniper`, and `BMNightkinTabithaMob`, whose template flags don't
  inherit a script. In the build every scripted nightkin keeps its script.
  The 2026-10-31 build's script converter read `GetAnimAction` as always
  true, so those nightkin uncloaked every pass; by the 2026-11-01 build it
  reads the actor's attack events. The spell's Chameleon effect is
  vanilla's `AssaultronStealthEFFECT`, which `AssaultronHeadModStealthScript`
  adds in combat with no sneaking, so the effect needs no sneak.
  Played 2026-11-01 (00:24 build), still open, none of it the mesh:
  - `CrNightkinGunScript` aborts every pass: its `NightkinCloakFXShader`
    property is empty, because no FNV effect shader (EFSH) is in the build,
    and the pass plays it before re-adding the spell. A gun nightkin that
    uncloaks to fire never cloaks again. Fixed 2026-11-01 (the shader plays
    in the next build, below; re-cloaking needed the `GetAnimAction` fix, also
    2026-11-01, not yet seen in play): every
    script `EffectShader` property gets a Fallout4.esm shader, the nightkin's
    vanilla's `StealthBoyInvisibilityEffect`
    ([effect shaders](script_markers.md#effect-shaders)).
  - The four `REPCONSuperMutantNightkinSCRIPT` nightkin (`RocketLabBasement`)
    never loaded in that log: their packages ran unloaded all session. FNV's
    script also calls `SetForceSneak 1` out of combat, which the conversion
    drops; FNV uncloaks them on purpose within 400 units of a combat target.
    Fixed 2026-11-01, not rebuilt: `SetForceSneak 1` is now `StartSneaking()`
    ([SetForceSneak](script_markers.md#setforcesneak)).
- **Weapons: a super mutant additive race (fixed 2026-11-01, played 2026-11-01: nightkin fire their guns).**
  Played, nightkin hit only with FO4's `UnarmedSuperMutant` and loaded with
  nothing equipped, the sniper too. `SuperMutantRace` picks weapon behaviour
  by nine keywords. FNV's guns on their own clips trade theirs for a
  per-gun one only the human additive race maps, and FNV's two-handed melee
  carries the baseball bat's `Anims2hmWeapon`, which super mutants lack
  (FO4's sledges carry `Anims2hmWideWeapon`). Of the 18 weapons the built
  super mutants carry, only the minigun and missile launchers matched.
  `spike.mutant_subgraphs` writes `FNV_SuperMutantRaceSubGraphDataAdditive`
  (SADD on `SuperMutantRace`, as Wasteland Workshop's
  `DLC02SupermutantRaceAdditive`), copying each class's super mutant
  entries, crippled-limb variants included, for every gun's own keyword and
  the vanilla keywords of kinds FO4 never gave super mutants (`NEAREST`:
  flamers hold like the minigun, submachine guns like the assault rifle, the
  Fat Man like the missile launcher, `Anims2hmWeapon` like the sledge). Run
  against the built plugin, 15 of the 18 are now covered (560 entries); the
  frag mine and dynamite are thrown, and the Multiplas rifle's grip keyword
  (its own over `AnimsPlasmaRifle`) had no class, mapped since 2026-11-08 with
  pistols ([super mutants](fo4_build_next.md#super-mutants), [drift](fo4_drift.md#recorded)).
- **Played 2026-11-01 (13:25 build): hands and grip need FO4's body.**
  Nightkin now fire their guns (the additive race works). Their hands
  stretch and don't grip. Skinned under FO4's own super mutant rifle clips
  (`wpnidleready`, `wpnfiresinglesighted`, `wpnequip`; validated to 0.05
  units at rest), the FNV skin deforms like FO4's body (arm and hand edge
  stretch p99 1.66-1.73 against 1.54-1.61; leader armor 2.32). But it
  binds only Collarbone, UpperArm, ForeArm1_skin and Hand, where FO4's body
  binds every finger (Finger11-53), the forearm twists (ForeArm1-3_skin)
  and the upper-arm twists. The fingers never close: the palm stays 17.8
  units from the hand bone in every frame, where FO4's curls from 13.2 to
  11.0. FNV's hand can't take FO4's finger bones either: its knuckles sit
  14.7 units from the wrist against FO4's 9-10, its fingertips at 24-26
  against 12-20, its finger axes are flipped, and its arm is 47.4 long
  against FO4's 56.9.
- **FO4's body and head under FNV's armor (played 2026-11-02: armor, head
  tint).** The first try (below) kept FNV's head on FO4's body. Played:
  skin gaps under the jaw, then (with its cut edge sunk into the body) a
  head sitting high with FO4's tinted neck showing beneath like a second
  head. FO4's super mutant head (`SupermutantHead.nif`, the race's default
  head part) is only a face plate, 15.5 x 12 x 24 units, filling an oval
  hole on the front of the body; the skull and hump are the body's. FNV's
  head is a whole head, 17 x 26 x 42, its top 15 units above FO4's body. So
  the shapes can't be stitched. Now:
  - The part holding FNV's bare skin (FNV's body: head, eyes, teeth, built-in
    bands) drops whole; only the armor parts stay.
  - Each armor vertex moves, by its share of head weight, from FNV's head
    box (the bare skin's head-led vertices) onto FO4's (head-led body
    vertices plus the face plate: `head_box`), then is pushed out of the
    body as before. FNV's mutant armor has no helmets; the nightkin
    goggles are the head gear this moves.
  - The skin no longer covers slot 32, so the race's head shows. The NPC
    names its own face set (FTST, before QNAM as vanilla's suiciders): a
    copy of the race's `SkinSupermutantHead` (DFTM) whose MNAM is a tinted
    copy of `SupermutantFGHead1.BGSM` (`creature_tint.tinted_materials`).
    Three are built: `SM3D1024_D`, `SM_1_D`, `SM_2_D`.
  - **The armor addon needs slots of its own.** With slot 32 gone, both
    addons covered only slot 33 and the mutants played naked: FO4 drew the
    body addon alone. All 34 vanilla skins with several addons give each
    addon for one race its own slots (an FX addon on slot 59, 60 or 61, the
    skin covering their union), so FNV's armor addon covers 33 and FX slot
    61 (`FX_SLOT`), as does the skin. Played: armor shows.
- **FO4's body under FNV's head and armor (built 2026-11-01, replaced).**
  `Pair.fo4_body`: the skin (a copy of `SkinSuperMutant`) lists two addons
  (INDX 0 each, as vanilla's multi-addon skins). The first is a copy of
  vanilla `SuperMutantBody`, mesh, weights, finger bones and dismemberment
  untouched, whose MO2S/MO3S name an MSWP putting a tinted copy of
  `Supermutant1.bgsm` on it (`spike.creature_tint`: each color channel's
  mean and spread of FO4's diffuse set to FNV's bare skin's; nightkin
  `SM3D1024_D` averages 71/75/84 against FO4's 98/91/71; gore is left
  as is). The second shows FNV's parts (`nif.creature`), cut:
  - FNV's bare skin is the texture of the shape with the most
    finger-weighted vertices (`skin_texture`). Of it only the triangles
    whose three corners lead with a head or neck bone stay: head, neck,
    teeth, neck bands. Body, arms, hands, legs and feet are FO4's.
  - A triangle with two finger-weighted corners drops from any part.
  - Armor is pushed 0.5 units outside FO4's body along the nearest outward
    triangle (every one of the body's triangles winds outward); after
    three passes no armor shape keeps over 2% of its vertices inside (the
    arm braces' 2%, at most 0.5 deep). The head isn't pushed: its mouth
    sits inside FO4's neck, and FO4's shoulders cover the base of its neck
    (up to 5 units).
  All 34 super mutant part lists resolve a bare skin (`SM3D1024_D`
  nightkin and Lily, `SM_1_D`/`SM_2_D` the rest, the vault mutant's
  `SMSpineBreaker`). The captain alone (one record) has skin and armor in
  one shape, so `skin_texture` returns '' and it keeps FNV's whole body as
  before. Hands and grip are vanilla's by construction (the rifle-clip
  numbers above).
- **Gun nightkin stay uncloaked: the converted GetAnimAction latches.**
  FO4's rifle attack sends `WeaponFire`, `attackState` and back to
  `readyState`, almost never `attackStop` or `AttackEnd` (one in 20 s of
  firing), and `attackState` fires on leaving the attack too. So
  `TES4_AnimAction` reads an attack from the first shot on and the gun
  script never re-adds the cloak. Fixed 2026-11-01 in
  `script_convert/anim_action_falloutnv.py` (in every build since, not yet
  seen in play): `attackState` is no start, `readyState` an end, and an
  attack with no end event ends 2 s after its last start. The cloak shader
  now plays (vanilla `StealthBoyInvisibilityEffect`); its only error is on
  an unloaded nightkin. FO4's Stealth Boy and assaultron descriptions ("Invisible for 30
  seconds", "Stealth Field for <dur> seconds") carry no sneak condition.
- **Dead nightkin and ghouls T-posing are not the mesh.** The REPCON
  corpses (`RocketLabMid`: three `FeralGhoulDEAD2`, two
  `NightkinMeleeDEAD`) are placed Starts Dead (FNV's record flag 0x80000 on
  FO4's ACHR 0x200), and the ghouls' `DeadGhoulGib` also calls `Kill()` in
  `OnLoad`. The nightkin mesh skins only to bones FO4's super mutant
  skeleton has (21 of them), and that skeleton carries its
  `bhkRagdollSystem`. Weights only follow the bones; a T-pose is bones the
  ragdoll never moved, and the ghouls are FO4's own body. The cause is the
  missing ragdoll pose. FNV's corpses carry one (XRGD: 16 bones for the
  nightkin, 18 for the ghouls, plus XRGB on the nightkin), but actor
  placement drops it (`placement(..., pose=False)` in `spike.npcs`: FNV's
  ragdoll bone indices aren't FO4's). FO4 settles a Starts Dead actor from
  its stored pose (1,090 of Fallout4.esm's 1,188 have XRGD); none of the
  build's 396 has one: 260 human, 39 brahmin, 30 ghoul, 12 super mutant,
  the rest robots and creatures.
- **Dead-at-start poses: converted (2026-11-01, not rebuilt).**
  `spike.ragdoll_pose` writes FO4's XRGD from FNV's, after NAME as vanilla
  orders it, and copies XRGB. Both games store one 28-byte entry per ragdoll
  body in the skeleton NIF's tree order: the body's collision-filter part
  number (FNV's bhkRigidBody filter; FO4's hknp `collisionFilterInfo >> 8`),
  the node's rest offset, and its rotation relative to its skeleton parent
  (the root's in the reference's space), with a reference's angles
  (`Rx(-x)Ry(-y)Rz(-z)`, `spike.scol`). Bodiless nodes (clavicle, pelvis,
  forearm twists) stay at rest. Checked against Fallout4.esm: 880 of its
  1,090 posed corpses have exactly the derived part sequence (humans, feral
  ghouls, brahmin, dogs, super mutants and 11 other skeletons), and each
  converts onto its own skeleton unchanged. The other 210 are variants: 172
  humans with a 19th entry, robots, and other body counts. Only this reading
  lays FNV's corpses flat: 101 of 150 human corpses are flattest with it,
  6 units ahead of the next.
  Each FO4 body takes the turn its FNV bone (by name through the rig:
  `HUMAN`, a pair's, the feral ghoul's own table `FERAL_GHOUL`, else the
  same name) made from rest, on FO4's rest orientation; a body without a
  source stays at rest under its parent. A pose is written when at least
  three quarters of FO4's bodies have a source (`MAPPED_SHARE`). Of the
  build's 396 dead actors:
  - written: 298 (274 human, 12 super mutant, 7 feral ghoul, 4 nightstalker,
    1 dog), lying as flat as in FNV (median joint-height spread 25.8 against
    FNV's 23.7);
  - no bone match: 57 left out (brahmin 37, mole rat 13, deathclaw 2, and one
    each of gecko, radroach, eyebot, mirelurk king and radscorpion), whose
    FO4 rigs share at most 10 of 20 to 49 bodies by name;
  - no FO4 ragdoll in the skeleton: 19 robots (protectrons, Mister Gutsies,
    sentry bots; FO4's robot skeleton has no `bhkRagdollSystem`);
  - no pose in FNV: 22.
  The build counts each as `ragdoll pose written` / `left out: <why>`.
  <a id="creature-poses"></a>**Brahmin and mole rats (built 2026-11-06, not
  played):** FO4's brahmin and mole rat skeletons get their own tables
  (`BRAHMIN`, `MOLERAT`), as the feral ghoul's: FNV's spine, two necks and
  heads (`Bip01 HeadL` is `LHead`), legs (the mole rat's arms are its front
  legs), tail and sack by name. They find a source for 33 of the brahmin's 39
  bodies (the ears and each third neck bone stay at rest) and all 20 of the
  mole rat's, so FNV's 37 brahmin and 13 mole rat corpses take their pose.
  Measured on 8 of them: the mole rats' lowest joint sits within 7 units of
  FNV's below the root; the brahmin's 20 to 30 lower, partly because FO4's
  brahmin has a toe body below the foot that FNV's lacks. To check in game:
  whether a dead brahmin sinks into the ground. Deathclaws, the gecko,
  radroach, eyebot, mirelurk king and radscorpion (one or two each) stay
  out.
  <a id="fallback-pose"></a>**No FNV pose: a vanilla corpse's (2026-11-08, not
  built):** FNV gives 22 dead actors no XRGD (the Freeside vagrant
  `VMS49VagrantREF` stood in an A-pose). Each now takes the XRGD and XRGB
  of Fallout4.esm's flattest posed Starts Dead corpse on the same FO4
  skeleton: placed upright (DATA x and y angles 0), entries in the
  skeleton's part order, least height between its highest and lowest body
  (human `00043F3B`, 10 units; brahmin `0007815B`, 43.5). XRGD is in the
  reference's own space (the root entry's position is its rest offset: median
  0 over the 1,090, against a median 32,276 units from the corpse's DATA), so
  the copy lies at the new reference's place and heading unchanged. 18 of the
  22 get one (16 human, 2 brahmin); a protectron (no FO4 ragdoll) and three
  ED-E eyebots (no vanilla eyebot corpse) stay out. Counted as
  `ragdoll pose written (fallback)`.
  Fallout4.esm's 98 Starts Dead actors without XRGD differ from the vagrant:
  26 stand on ragdoll-less turret and robot skeletons, 83 are leveled
  `Lvl*` bases (with XLCM), and the 6 persistent ones are all turrets or
  protectrons. No vanilla persistent corpse on a ragdolled skeleton lacks a
  pose; 14 of the 16 FNV humans here are persistent.
- FO4's animations, not FNV's; FNV's armor is its own addon over FO4's body
  (slots 33 and 61, above).

<a id="dead-money-humans"></a>**Dead Money's Ghost People and holograms on FO4's human (built 2026-11-02, not played).**
Both stand on FNV's own human skeleton (`nvdlc01\creatures\ghosts`, `...\hologram`: the
`_male` bones plus arm twists, `MeleeWeapon`, `ProjectileNode_Beam`), so they
take the super mutants' way on FO4's human: a copy of `EncRaider01Template`
(no template, its own skin) wearing FNV's body as its skin
(`Pair.human`).

- **Folders.** `skeleton_folder` is the folder holding the skeleton. It used to be the
  first two path parts, which put both DLC folders (and FO3's `dlc05` alien,
  whose rule moved with it) under `nvdlc01\creatures`. Base-game creature keys are
  unchanged.
- **Mesh.** FNV's weights on the `HUMAN` rig (`own_weights`). FO4's
  `malebody.nif` skins no `HEAD`, which left FNV's head bone with no target. It
  then spread over every bone, putting the hood on the chest, belly and arms. `creature_fit`
  adds each rig bone the body lacks (neither the bone nor its `_skin` helper)
  at the skeleton's rest frame, as outfits add `HEAD`. The super mutant and dog fits lack none.
  Ghost hood centre 6 units from `HEAD`, gloves 10 from the wrists.
  FNV's fingers ride the hand.
- **Slots.** The skin covers hair 30-31, head 32 and face 46-50, as vanilla
  `AAArmorHazmatSuitHat` and the raider hoods (17 vanilla human head
  covers), so the raider's head and hair don't show.
- **Voice.** Neither has a VTCK; their sound sets (`AudioTemplateGhostSeeker`,
  `AudioTemplateHologram`) speak `VoiceDoNotRecordF`. On FO4's human the
  creature takes that voice type recorded or not, so it says nothing. Without this, it
  would speak the raider's combat lines. Dogs (105 also on `VoiceDoNotRecordF`)
  keep Dogmeat's.
- **Guns.** A human holds its creature guns: `NVDLC01HologramBeam` (embedded,
  no model, fired from `ProjectileNode_Beam`) is FO4's laser pistol in hand.
  Drift: FNV's beam leaves the skeleton's node with nothing held.
- FO4's human animations and combat; FNV's play-dead and special idles are
  not carried.

<a id="old-world-blues-creatures"></a>**Old World Blues' creatures (rules added 2026-11-03, not built).**
OWB placed 9 actors on folders with no rule, and their records are still used:
98 Mobius dialogue conditions and the X-42 turret package point at them.

- `nvdlc03\creatures\hologram` is Dead Money's hologram again (same parts,
  `nvdlc01hologramoutfit`), so it takes the same human pair.
- `brainbot` (the Think Tank: Klein, Dala, Borous, 8, O, Mobius) are hovering,
  armed, talking robots. They become FO4's Mr. Handy (`encMrGutsy01Template`,
  stats), as FNV's Mr. Gutsy does. Their records are template actors on
  leveled lists, so the count names the record, not the folder.
- `roboscorpion` becomes FO4's radscorpion (stats), sized by FNV's base scale.
- `braintank` (no packages, a talking idle and no walk clips) is a speaker
  like Mr. House: FNV's parts are placed beside an unseen talker.
- Drift: the stand-ins keep FO4's bodies, animations and attacks.

Lonesome Road's ED-E and its medical and repair eyebot clones all sit in
`nvdlc04\creatures\nvdlc04edeclone` (`skeleton_Low.nif`). The folder takes
the base-game eyebot's rule (`EncEyeBot`, stats).

**Geckos: the deathclaw tried and dropped; a mole rat stands in (2026-10-10).**
FNV's most placed creature with no FO4 counterpart ([census](#creature-census)).

- **Tried: FNV's gecko on FO4's deathclaw.** FNV's gecko (`NVGecko.NIF`, an
  upright biped with arms, digitigrade legs and a tail) on the deathclaw
  skeleton, by a gecko rig like the dog's. The mesh fitted (feet on the
  deathclaw's floor once toes and fingers moved without the foot's 6.7x
  stretch; body a median 3.6 units from the deathclaw's surface). Played:
  it does not work. The movement is the deathclaw's and reads wrong, FO4's
  deathclaws are far more aggressive than FNV's geckos, and it came out
  deathclaw-sized: "a deathclaw with an odd skin over top". (The size was
  also a bug: FO4's NPC has a minimum and a maximum height, `NAM6` and
  `NAM4`, and only `NAM6` was set, to 0.32.) What makes a creature read as
  itself is its own motion and behaviour, so FNV's mesh on an FO4 rig
  works only where the two are the same animal (Cheyenne on Dogmeat).
  Removed: the gecko rig, the height scaling and the rig's rigid tips.
- **Built: an FO4 stand-in (played 2026-10-10: works as mole rats).** A creature with no FO4 counterpart is a copy of
  a vanilla creature of its size and role under FNV's name, with that
  creature's own body, animations and factions; only its scripts drop
  (`creatures.STAND_INS`). Geckos stand in as a mole rat
  (`EncMolerat01Template`, `0001D966`: no template, no scripts, its two
  factions): small, an aggressive pack biter, and it moves as itself. FNV's
  quest steps that count geckos still work. A ported gecko from the modlist
  replaces it through the replacement table
  ([direction](fo4_replacements.md#direction)).
- **Placed:** VCG02's two well geckos (`VCG02CrGecko`, "Gecko") in QASmoke
  beside Cheyenne. Their real spot, the first well at (-68,150, -12,819), is
  3 grid rows south of the built block; building down to it adds cells.

### <a id="spike-4-equipment"></a>Weapons and armor (played 2026-10-08)

The Goodsprings build skipped 6 weapons and 13 armor pieces, all from
leveled lists and quest properties: the BB gun, baseball bat, 9mm SMG,
rolling pin, switchblade and tire iron; 12 pre-war outfits, the hockey
mask and the Pip-Boy glove. `fo4_import/spike/equipment.py` writes each on
a copy of a Fallout4.esm record, the
[substitution table](research/fo4_target.md#asset-overlap): FO4's model,
first- and third-person animations, sounds, keywords and mod templates
(OBTE), with FNV's name, value and weight.

**One configuration per weapon (2026-10-22).** A copy keeps only its FO4
template's default combination (`Guns.default_only`), as a chosen gun
already did. Fallout 4's other combinations are loot variants drawing random
parts from mod collections (`modcol_*`). They gave converted weapons FO4
parts FNV never had: the 9mm SMG's "Silver Shroud" and 10 fist and melee
weapons' "Standard"/"Simple Epic" sets kept 5 each. FNV weapons have one
form, plus FNV's own mods.

| FNV | Written on |
|---|---|
| Baseball bat, rolling pin, switchblade, tire iron | The same FO4 weapon |
| 9mm SMG | `SubmachineGun` |
| BB gun | `PipeBoltAction` |
| Business wear (dirty, dark) | `ClothesSuitDirty_Grey`, `_Black` |
| Casual wear, relaxed wear (and dirty) | `ClothesPrewarSweaterVest`, `ClothesPrewarShortSleeves` |
| Spring outfit, parkstroller outfit (and dirty) | `ClothesPrewarWomensCasual`, `ClothesPreWarDress` |
| Sexy sleepwear | `ClothesBathrobe` (FO4 has no negligee) |
| Hockey mask | `Clothes_Raider_SurgicalMask` (none in the base game) |
| Pre-war hat, reading glasses (placed in the world) | `ClothesMobsterhat`, `ClothesEyeGlasses` |

- **Weapons:** DNAM takes FNV's weight, value and base damage; a gun also
  its magazine size and its ammunition (FNV's `NAM0`, not in the export,
  read from FalloutNV.esm; a form list gives its first entry), as
  converted. The template's mods still apply on top, so a gun's receiver
  and magazine mods change those numbers as in FO4.
- **Armor:** DATA takes FNV's value and weight (also missing from the
  export), FNAM's armor rating FNV's protection unscaled: FNV gives all
  armor 0 DR and its protection as DT (combat armor 15, leather 6, the
  hockey mask 1), FO3 as DR. The template's resistances (DAMA) are
  dropped. FO4's armor rating is a damage curve, not a threshold, so the
  scale is open.
- Placed weapons and armor become pickups as consumables did: each keeps
  its old static's numbered FormID unused (the hat, the glasses and a
  knife, now FO4's knife; 0 existing records moved). A placed piece with
  no substitute stays a static on that id (since [FormIDs](#formids), on
  FNV's id).
- Fallout4.esm is localized, so a copied FULL or DESC holds a string ID;
  the copy takes the text (`fo4_import/base/strings.py`, from the game's
  `Strings\Fallout4_en.*STRINGS`), including the mod templates' names.
- **Test chest:** QASmoke gets `FNV_TestChest` (vanilla QA chests' footlocker,
  `Props\FootLocker01.nif`) in front of the first stand-in door's arrival
  point, holding one of every piece the table names (made even when the
  block does not use it) and 100 rounds of each gun's ammunition.
  `coc QASmoke`.
- **Not converted:** the Pip-Boy glove (FO4's Pip-Boy is one item, already
  the Pip-Boy's stand-in); condition; critical data; the stand-ins in
  `items.STAND_INS` (9mm pistol, laser pistol, Vault 21 suit…) still keep
  FO4's stats.

### <a id="spike-4-melee"></a>Melee weapons on FNV's own meshes (played 2026-10-08)

The bat, rolling pin, switchblade and tire iron keep their FO4 template
record (animations, sounds, keywords, reach) but show FNV's mesh
(`fo4_import/nif/weapon.py`).

- **Vanilla's layout** (RollingPin01.nif, TireIron.nif, BaseballBat.nif,
  Switchblade.nif): one root node with `Prn` string extra data `WEAPON`
  (the bone it hangs from), BSXFlags 194, attach points `p-MeleeMod` and
  `p-Material` for weapon mods, and each shape twice: once with its own
  material, once hidden (node flags 15 against 14) with
  `BloodWeapon.BGSM`, shown as the weapon gets bloody. The first-person
  model (`MOD4`, `*_1.nif`) is the same mesh again; FNV's (`WNAM`, a STAT)
  is the world model itself for all four.
- **Placement:** both games hold a melee weapon with its grip at the origin
  and its length along +Y (rolling pin: FNV −4.6 to 38.7, FO4 −3.9 to
  42.8; bat: FNV −18 to 59, FO4 −8 to 48), so FNV's geometry is used as
  converted. FNV's tire iron hooks to +X where FO4's hooks to −X.
- **Held pose** (played: the switchblade faced the wrong way, the hand off
  its handle). FNV's switchblade mesh is folded: its resting nodes put the
  handle at y 2.7 to 15.2 and the blade inside it (3.3 to 14.2). FNV's hold
  animation for one-handed melee (`characters\_male\1hmaim.kf`) moves
  `##l_SwitchBlade` back 10 and slides `##l_Blade` out 11. In that pose
  the handle is −7.3 to 5.2 around the grip and the blade 4.4 to 15.3,
  FO4's switchblade layout (−8 to 5 and its blade). A melee mesh is now
  converted with its nodes in the hold animation's pose (`1hmaim.kf`,
  `2hmaim.kf` by FNV animation type; `convert_static.posed`); the other
  three have no keyed nodes and are unchanged.
- The converted mesh gets `Prn`, BSXFlags 194 and a blood copy of each lit
  shape, after Elric (which drops every block after the first Havok one).
  No attach points: the record drops its template's mod templates
  (OBTE…STOP) and model data, so the weapon takes no FO4 mods.

### <a id="spike-4-headgear"></a>Headgear on FNV's own meshes (played 2026-10-08)

The hockey mask, pre-war hat and reading glasses use FNV's meshes
(`fo4_import/nif/headgear.py`), through their own armor addons.

- **FNV:** headgear is not skinned. The mesh is rigid, in the head mesh's
  frame (`characters\head\headhuman.nif`), and an NPC's `.egm` moves it
  with the face. The mask spans x ±7.5, y −7.1 to 10.6, z −1.6 to 17;
  the mean head x ±6.3, y −6.3 to 9.6, z −7.4 to 15.1.
- **FO4:** worn meshes are skinned BSSubIndexTriShapes (118 of 119 in
  vanilla hats, masks and glasses) under a stub of skeleton nodes. Their
  vertices are in model space shifted so the HEAD bone sits at the origin:
  HEAD's skin transform is its node rotation transposed, with no
  translation (BaseMaleHead.nif, Raider02MaskM.nif). Bone bounding spheres
  are in bone space.
- **Fit:** FO4's base head (`basemalehead.nif`, `basefemalehead.nif`) is
  fitted onto FNV's mean head (`headhuman.nif`, `headfemale.nif`) with
  the face fit's `align`. Male: scale 1.008, offset 4.2 up; female: scale
  0.963. The mask goes through the inverse and lands in front of FO4's
  face (y to 10.55 against the face's 9.5).
- **Head shape** (played: the head came through the back of the hat). The
  face fit leaves FO4's skull out: its back and top are a separate mesh
  (`faceparts\maleheadrear.nif`, `femaleheadrear.nif`), larger there than
  FNV's. Each FNV head vertex, fitted into FO4's frame, gets the offset to
  FO4's nearest face-or-rear surface point (smoothed over 8 neighbours, 3
  passes), and each headgear vertex the inverse-distance average of its 8
  nearest. Head vertices under the hat poking through it: FNV's own hat on
  FNV's head 2 (0.08 deep), the face fit alone 25 (0.38), with the shift 2
  (0.07).
- **Hair line** (played: female, a hair gap at the back under the hat).
  A hat on slot 30 hides FO4's hair top; FO4 keeps the hair below a cut
  meant for its own hats. Lowest back brim (within 15° of straight back
  round HEAD) of vanilla's female hats on slot 30: 1.34 to 4.55 (postman's
  cap, `postwomanfhat.nif`, which tips forward like FNV's: front 2.79).
  FNV's pre-war hat tips forward (back 9.01, front 7.86 on FNV's head)
  and lands at back 5.30 (male) and 5.56 (female). The fit is not the
  cause: matched over the upper skull instead of the face, it tips the hat
  further (pitch 5.4° and 6.7° against 3.3° and 4.0°). A hat that hides
  hair is now tipped back about its front brim's lowest point until its
  back brim is at 4.55 (2.1° male, 2.8° female).
- **Clearance:** every headgear vertex is then moved out from FO4's head,
  along the line from its centre, until it is at least as far outside it
  as it was outside FNV's head (nearest surface sample, radial distance).
  Head points under the hat whose ray from the head's centre meets no hat
  surface beyond them: male 0 of 184, female 0 of 139 (tipped alone: 2
  and 0; untipped: 0 and 2, at the back). The mask and glasses move at
  most 0.8. Final back brims: male 4.62, female 4.55. Every vertex is weighted fully
  to HEAD; there is no `_facebones` variant, so the mask does not follow
  facial animation, and FNV's `.egm` is not used.
- **Segments,** as vanilla's head items: an empty segment, then one with
  every triangle and one sub-segment, and shared data whose last entry is
  the item's first slot with bone ID `0x86B72980`; no `.ssf` file.
- **Slots:** FNV hair maps to 30 (which hides FO4's hair top), headband
  and hat to 46, eyeglasses to 47, mask to 48 and 49, as vanilla's hats
  (30, 46), glasses (47) and gas masks (46–49). FNV's hat bit does not
  hide hair; its hair bit does (played: the hockey mask on 30 left the
  player bald). Hockey mask: 46–49. Hat: 30, 46. Glasses: 47–49 (FNV's set
  the mask bit too).
  - *Hats without the hair bit (fixed 2026-10-25, not yet played).* Hair
    showed through Westside Marco's Pre-War Baseball Cap (bits 9 and 10,
    no hair bit), which went on 46 alone, so FO4 kept the hair top. FNV's
    hat bit does not hide hair; it swaps the hair to its `Hat` node, a
    flattened version, and nearly every vanilla hat covers 30 (fedora 30,
    46; caps 30, 31; hard hat 30; only the super mutant hats 46 alone). A
    hat bit without the mask bit now adds 30: 35 converted hats (the
    caps, Ranger hats, berets, fedoras, head wraps, fire helmet). A hat
    with the mask bit (the hockey mask, White Glove masks) stays off 30.
- **Records:** an ARMA per item (`FNV_AA_<EditorID>`, hashed FormID)
  with those slots, the template addon's race, priorities and additional
  races, and male and female models (`<mesh>.nif`, `<mesh>_female.nif`).
  The ARMO points at it, and its world model is FNV's ground model.

### <a id="spike-4-outfits"></a>Outfits on FNV's own meshes (played 2026-10-08)

The 12 pre-war outfits (`OutfitPrewar*`, `fnv` in the
[replacement table](fo4_replacements.md)) show FNV's outfits, male and
female (`fo4_import/nif/outfit.py`), each through its own armor addon:
casual wear, relaxed wear, business wear, spring and parkstroller outfits
(each with its dirty variant) and the sexy sleepwear, on four FNV meshes
per sex. Pre-War Casualwear was played first (2026-10-08), then the rest
(2026-10-08).

- **Variants:** FNV tells an outfit's variants apart on one mesh by
  alternate textures (ARMO `MODS` male, `MO3S` female, `MO2S` ground model;
  dropped by the export, read from FalloutNV.esm): (shape name, texture
  set, shape index), the index counting shapes in tree order. The index
  decides; the names are sometimes another shape's (Pre-War Relaxedwear's
  index 5, `UpperBody`, is listed as `pipboyoff`). Each becomes an MSWP
  (`FNV_MS_<EditorID>_<subrecord>`, hashed FormID) mapping the shape's
  converted material to a copy with the texture set's diffuse and normal
  maps and a specular map from that normal map's alpha, at the original's
  smoothness (`statics.swapped_material`). The addon names it after each
  model (`MO2S`-`MO5S`, as vanilla's `HighSchoolJacketSwap`), the ARMO
  after its ground model (`MO2S`). 20 swaps; Pre-War Businesswear (dirty)
  has none, as in FNV.

- **FNV:** an outfit is skinned to the Bip01 skeleton in its bind pose
  (`characters\_male\skeleton.nif`, both sexes), and holds the whole body
  but hands and head: clothes, any bare skin (shapes whose shader has the
  FaceGen flag, tinted to the body), dismemberment caps (partitions 100 to
  999), and the left sleeve twice (`pipboyon`, `pipboyoff`).
- **FO4:** worn bodies are skinned BSSubIndexTriShapes on the body's bones
  and its helper `_skin` bones (58 male, 60 female), under a stub of
  skeleton nodes (SweaterVest\MOutfit.nif, MaleBody.nif). Vertices are in
  the skeleton's world shifted by (0, -0.88, -120.84), which puts the neck
  near the origin; every bone's bind data in MaleBody.nif shows the same
  shift. The first-person body (`1stPersonMaleBody.nif`) has the same bind
  data, arms only.
- **Skeletons:** FO4's is close in size; its torso is taller (neck 113.2
  against FNV's 107.4, collarbones 110.4 against 105.2) and its arms hang
  lower and further forward (hand at x -38.1, y 7.7, z 84.0 against -44.3,
  -0.2, 85.3).
- **Retarget:** FNV bones map to FO4's (Spine, Spine1, Spine2 to SPINE1,
  SPINE2, Chest; limbs by name). A bone that spans a part (spine, neck,
  collarbone, upper arm, forearm, thigh, calf, foot) turns onto FO4's
  direction and stretches along itself to FO4's length; twist bones,
  hands, toes and the head move with the part they follow. Each outfit
  vertex moves by its FNV weights. (Played: dark blocks and streaks on the
  dress's skirt. Converted vertices found their FNV originals, which give
  the normal and weights, by position alone; where vertices share a
  position (hard edges, the hem's two sides) some took a neighbour's, 152
  normals of the dress facing in. They are now matched by position, UV and
  normal: 0 facing in, 90 more than 45° off their triangles against FNV's
  own 80.)
- **Conform:** FNV's body (`upperbody.nif`, `femaleupperbody.nif`, caps
  left out), retargeted the same way, lies within 0.7 (male) and 1.0
  (female) on average of FO4's body surface, at most 2.6 and 3.5; each FNV
  body vertex's offset to FO4's nearest surface point is smoothed (8
  neighbours, 3 passes) and each outfit vertex takes the inverse-distance
  average of its 8 nearest. Outfit vertices then lie on average 0.6 to 1.5
  from FO4's body (90% within 4; the dress hem 13); the cuffs meet FO4's
  hands and the shoes its feet.
- **Seams** (played: a step between the female's bare forearm and FO4's
  hand). FO4's body has open edges only at the wrists and neck, where the
  hands and head join (the hand's edge lies on the body's exactly); FNV's
  skin edges there sit 0.28 from FNV's body edge (FNV's hands overlap) and
  landed a median 1.3 from FO4's. Each FO4 body edge is paired with the
  FNV body edge whose retargeted centre is nearest; an outfit edge vertex
  within 0.5 of that FNV edge (in FNV's frame) moves to the nearest point
  of FO4's edge, the move fading out over 3 units inward (`seamed`). The
  sexy sleepwear's wrists: within 0.02 of FO4's edge after. Played: the
  wrist still looked wrong (FO4's hand too large for FNV's forearm);
  accepted (Skin, below).
  - *Mutual pairs only (fixed and played 2026-10-18: Deputy Beagle's and a
    Primm resident's left sleeves).* FNV's male body has wrist edges but no
    neck edge, so FO4's neck took the nearest FNV edge, a tie the left
    wrist won. Every male outfit's left wrist edge then had two targets
    and part of it snapped onto the neck: 8 vertices of the leather armor's
    `Arms02` at one point by the chest, edges up to 41.8 units (median
    3.6), a spike from the elbow when the arm moved. An FO4 edge now pairs
    only with the FNV edge that is nearest it and has it as its own
    nearest (`_seams`); the male neck pairs with none, the female body's
    neck edge still pairs with FO4's. After: longest edges 4.8 (leather)
    and 4.2 (settler 02).
  - *Whole skin loops (fixed 2026-11-09, not built: Jacklyn's neck, 1108d).*
    Some female outfits cut their neck skin off FNV's body edge: the Raider
    Badlands armor's `Arms01` neck rim sits a median 1.0 (max 1.34) from
    it, so 4 of its 24 vertices snapped and the rest stayed up to 2.4 off
    FO4's neck edge, a jagged rim crossing in and out of FO4's head neck
    (skin on body texture against the head's face texture). A skin shape's
    open loop wholly within 2.0 (LOOP_REACH) of an FNV body edge now moves
    whole; that rim then lies within 0.004 of FO4's neck edge. Census of
    FalloutNV.esm's upper-body outfits: 16 skin loops change (6 female
    necks, among them `ArmorRaider03`, `ArmorMetal`, Legion, Great Khan and
    Powder Ganger battle armors; 9 female wrists, 8 of them partly snapped
    before and Raider 04's not at all; BirthSkirt's male wrist). Cloth keeps the per-vertex rule (collars sit near the
    neck). Male necks still have no seam (FNV's male body has no neck edge);
    their skin rims sit 0.82 from FO4's, tucked inside the head's neck.
- **Weights:** FO4's body's at each vertex's nearest surface point
  (barycentric), the four largest, normalized. Each shape's skin instance
  lists the body bones it uses; their bind data is the body's, with
  bounding spheres of the outfit's own vertices.
- **Segments:** each triangle goes to the segment of its strongest bone, in
  vanilla's body order: left arm 2, torso 3, right arm 4, left leg 5,
  right leg 6 (collarbones and shoulders are torso). No sub-segments,
  cut data or `.ssf` file, so dismemberment does not cut the outfit.
- **Left out:** caps, and `pipboyoff`: FO4's player always wears the
  Pip-Boy, so the sleeve rolled for it (`pipboyon`) is the one drawn, NPCs
  included. Vertex colours are dropped.
- **Skin:** FNV's skin shapes keep their mesh, fitted like the clothes,
  and are drawn with FO4's body skin-tint shader, material and textures
  (`FemaleBody_d.dds`), so their colour matches FO4's hands and head.
  Each vertex takes the body texture's UV at its nearest body point; a
  triangle whose corners land on distant parts of the texture (longest
  UV edge over longest edge past the body's own most stretched triangle,
  0.0166 female) takes the UV mapping of the body triangle nearest its
  centre, extended over its corners, on vertices of its own (the
  negligee's skin: 320 of 2,788 such triangles before, 0 after).
  - **Accepted (2026-10-08):** FO4's hand is a little large for FNV's
    thinner forearm, so the wrist does not meet cleanly; and the painted
    underwear below. Both are for [CBBE and BodySlide](fo4_replacements.md#bodyslide).
  - **Tried and dropped: FO4's own body in the skin's place** (vanilla's
    `BaseFemaleBodyFitted` method; commit `ea8d8ac7`). The covered piece
    of FO4's body (triangles the fitted skin lies over, within half a
    triangle sideways, 3 units deep), without skin under the clothes and
    with FNV's foot shape by foot weight. Played: arms through the sleeves
    (FO4's arm is thicker than FNV's sleeves allow), skin missing along
    hems and straps, heels without soles. FNV's clothes are cut for FNV's
    body, so each fix would move the mismatch.
  - **Painted underwear:** FO4's female body texture has a bra and briefs
    painted on (diffuse and normal map), which vanilla outfits keep
    covered; skin FNV shows there (the sexy sleepwear's chest) shows FO4's
    painted bra, as every FO4 woman wears it. Accepted (2026-10-08); a body
    texture replacer the player installs applies here too. Masking it out
    by colour misses the painted shadows and strap edges.
  - **History (played 2026-10-08):** FNV's skin under FO4's skin material
    first crashed the female version (the skin-tint shader block ends in
    four floats, colour and alpha, 156 bytes in vanilla's FemaleBody.nif;
    it was written with three, 152; the shader reader now refuses a block
    it does not read to the end), then looked patchy and unlike FO4's
    hands. FNV's skin mesh on FO4's body texture (each vertex at its
    nearest body point's UV) matched the colour; FO4's own body in its
    place was tried next and dropped (above).
- **Shine** (played: many outfits too shiny). A specular map's strength
  (R) was FNV's normal-map alpha and its smoothness (G) FNV's glossiness
  as the same lobe width (`smoothness()`): 0.36 to 0.58 on the outfits,
  against 0.06 to 0.13 on vanilla clothing. FNV's Blinn-Phong highlight
  peaks at its specular map; FO4's lobe is normalized, so the same
  strength in a lobe of glossiness n reflects (n + 2) / 2 pi times the
  energy. R is now scaled by 2 pi / (n + 2), pi (1 - smoothness) ** 4
  (`specular_scale()`): 0.53 at glossiness 10, 0.10 at 60. This applies
  to every converted specular map (statics, landscape, outfits).
- **First person:** the arm segments alone (`<mesh>_1stperson.nif`), on the
  same bind data.
- **Records:** an ARMA (`FNV_AA_<EditorID>`, hashed FormID, the one new
  record) with the template addon's slots (33, and 60 as vanilla clothes
  have), race, priorities and additional races, and FNV's meshes as the
  male and female third- and first-person models. The ARMO keeps the
  template's slots (33 and armor slots 41 to 45, so no armor goes over it)
  and shows FNV's ground model.

### <a id="spike-4-guns"></a>Guns on FNV's own meshes (played twice 2026-10-08, parked; superseded by [FNV's own gun clips](#spike-4-gun-clips))

The 9mm SMG and BB gun show FNV's meshes on their templates' animations
(`fo4_import/nif/gun.py`, `fo4_import/spike/guns.py`).

- **FO4's guns are parts.** The record's model is a dummy receiver; its
  default object template combination (OBTS with Default set; its
  keyword count is one byte at form version 131) attaches object mods at
  attach points. SubmachineGun: `TGunReceiver.nif` (ap_gun_receiver),
  grip, barrel, drum magazine, iron sights, null muzzle; PipeBoltAction:
  `PipeRifleBoltAction.nif`, grip, barrel, sights, a range offset; 10mm:
  `10MMPistol.nif` and parts. The animation set comes from keywords
  (`AnimsSubmachineGun`, `AnimsRecieverHandmadePipe`, `AnimsFP10mm`).
- **A receiver mesh is the gun's skeleton:** root `WEAPON` with the bones
  the animations move (WeaponBolt, WeaponMagazine and its children,
  WeaponTrigger, WeaponExtra1–3, their `*Trans` twins, WeaponOptics1–2),
  the receiver geometry under its own node with `ProjectileNode`, and
  on some `ScopeCameraDelta` and `WeaponIKTargetL` (the left hand). The
  trigger is not at the origin: y 17.1 on the tommy gun, 4.7 on the 10mm,
  1.0 on the pipe rifle.
- **FNV's guns** lie along +X with +Y up (FO4: +Y, +Z up) and name their
  moving parts: 9mm SMG `##Clip`, `##Trigger`, `##Bar`, `##Lever`,
  `##Shells`, nodes `ProjectileNode`, `ShellCasingNode`,
  `##SightingNode`; BB gun `##BBLever`, `##BBTrigger`, `##BBCarton`.
- **The mesh:** the template's default receiver, read from the user's
  BA2, with its own shapes' geometry emptied (played: turning them into
  empty nodes crashed the game opening a container holding the BB gun,
  whose railway rifle receiver drives its shapes' shaders from controller
  sequences; no block index moves; its
  bones, controllers and collision stay). The converted FNV gun is turned
  to FO4's axes, moved so its trigger's top sits on the receiver's, and
  each part goes under the bone its name ends with (trigger, clip or
  magazine, bolt, slide, lever or bar, hammer), the rest under the
  receiver's node; `ProjectileNode` moves to FNV's muzzle.
- **The record:** its other combinations go; the default one includes
  copies of its mods (`FNV_<mod>_<EditorID>`, hashed FormIDs): the
  receiver's copy shows the FNV gun, the other parts with a model keep
  their properties and lose the model (FNV's mesh has them), and a mod
  without a model stays vanilla's. Their properties (automatic, bolt
  action, capacity, accuracy) stay; vanilla's mods are untouched.
- **First pass, played:** on the substitution table's guns (SMG on the
  tommy gun, BB gun on the pipe bolt-action) the SMG reloaded from the
  wrong spot and was held in the wrong place, its sights near; the BB gun
  was held like a pistol. The tommy gun's magazine is 4.7 ahead of its
  trigger, FNV's SMG's 12.7; the pipe bolt-action's default grip
  (`HandMadePistolGrip.nif`) adds AnimsGripPistol, its stocks
  AnimsGripRifleStraight.
- **Second pass, the template is chosen** (`fo4_import/spike/gun_choice.py`):
  every playable FO4 gun (Gun animation, not non-playable or embedded,
  with a default combination), in its default combination and with each
  receiver and grip its other combinations use swapped in. It must be held
  as FNV's gun is (FNV animation types 3–4 one-handed, 5–7 two-handed
  against the AnimsGrip keywords, else WeaponType, the record and parts
  give), fire alike (parts' IsAutomatic, else DNAM's Automatic; FNV's
  Flags1 Is Automatic) and spread alike (projectile count over 1: parts'
  NumProjectiles, else FNAM; FNV's ProjectileCount). The nearest layout
  wins: magazine mouth (the receiver's `P-Mag` connect point; FNV's clip
  top) and muzzle offsets from the trigger, the muzzle weighted 0.25.
  OMOD DATA counts are all u32 (2,409 of 2,409 parse exactly); its
  properties are its last 24-byte entries. Chosen: 9mm SMG (one-handed,
  automatic) on PipeGun with its automatic receiver and pistol grip; BB gun
  (two-handed, single shot, no magazine) on RailwayRifle with its full
  stock (the double-barrel shotgun was nearer before shotguns were kept
  to shotguns).
- **Sights:** the receiver copy adds ZoomDataCameraOffsetZ (property 72,
  ADD; vanilla zoom records use this offset too, ZM_HuntingRifle −0.25,
  ZM_InstituteLaserGun 1.87): FNV's `##SightingNode` height over its
  trigger less the template's sights (its `P-Scope` point plus the top of
  the sights mod's mesh) over its trigger. SMG +1.14, BB gun −5.70 (the
  railway rifle's sights sit 9.7 over its trigger). Measuring the
  template's whole top instead gave the BB gun −8.6, off its tall gauge.
- **Second pass, played:** the SMG held and aimed right on the pipe gun,
  but its reload was the pipe gun's side-magazine one; the BB gun's left
  hand hovered over the barrel, it kept the railway rifle's sound and
  steam, and fired once without reloading. Each is the chosen gun's own
  animation or effect: automatic choice fits only as far as a FO4 gun's
  layout and action match FNV's.
- **Parked then:** guns went back to FO4's guns (`stats` in the
  [replacement table](fo4_replacements.md)). Since 2026-10-29 the `fnv`
  mode carries FNV's own clips and is the default for every gun without a
  near FO4 match ([which guns convert](#spike-4-gun-clips)).

### <a id="placed-guns"></a>Placed guns lie as FNV's (built 2026-11-06, not played)

FNV's reference rotation fits FNV's model, which lies along +X with +Y up;
the FO4 weapon in its place lies along +Y with +Z up (the store's .22 stood
on its grip). A placed reference of a converted gun now takes back the turn
its mesh was given (`guns.turned`, in `cell._placed_at`):
- a gun on FNV's own mesh, its `gun.placement` matrix (the axes turn, a
  launcher's tip and roll, the trigger offset onto the receiver's);
- a gun shown on an FO4 model, FO4's axes alone (`gun.AXES`), no offset:
  both games put a gun's origin in the hand.

The reference's rotation becomes FNV's times the mesh's turn, and its
position moves back by the offset, turned and scaled as the reference is,
so every point of FNV's model lands where FNV put it
(`tests/test_fo4_placed_guns.py`). Counted as `placed guns turned as their
mesh`. Melee and thrown weapons are not turned: FNV and FO4 build them
along the same axis.

### <a id="spike-4-gun-clips"></a>FNV's own gun clips on a vanilla graph (built; played 2026-10-28/29; good enough, tweaks parked)

**Code:** `fo4_import/havok/gun_clips.py` (clips), `fo4_import/nif/gun.py`
(mesh), `fo4_import/spike/guns.py` (records). A chart entry with
`"as": "fnv"` builds the FNV gun on its FO4 template with FNV's own
first-person clips. Played on one gun per FNV class: 9mm Pistol (`1hp`),
Assault Carbine (`2ha`, full auto), Hunting Rifle (`2hr`), Flamer
(`2hh`), Tesla Cannon (`2hl`).

**The mesh.**
- FNV guns lie along +X; launchers (Missile Launcher, Fat Man, Tesla
  Cannon) along +Y. `axes_for` tips a launcher by its ProjectileNode's
  side and picks the quarter-turn roll whose box best fits the template's.
- The game ignores a weapon NIF's root transform (FO4's Missile Launcher
  root is turned 180°; applied, its missiles would leave the back, and the
  Tesla played reversed and mirrored). `node_worlds` leaves it out.
  Vanilla roots are often junk: batons, flares and suppressors carry
  turns, and the baton's world and first-person copies disagree.
- A receiver-less template (Flamer, Missile Launcher) draws its body from
  the WEAP's own MODL and its 1st-person model MOD4 (`Flamer_1.nif`); the
  FNV mesh replaces both, or FO4's body draws in first person.
- WEAP DNAM.Flags1 0x10 (Hide Backpack): the mesh's `Backpack` part is
  worn on the back, not drawn on the gun (JIP's ReloadEquippedModels moves
  it). It is dropped; the flamer's tank hung 40 units under the gun.

**The clips** (PLAN): FNV's class clips under the vanilla names.
- A shot is held to the vanilla clip's length: the graph leaves the fire
  state by triggers timed back from the clip's end (WPNFireSingleReady:
  initiateStart at end-0.5 s), so a shorter shot leaves before weaponFire.
- Full auto (DNAM.Flags1 0x2 → WEAP DNAM 0x8000): `{cls}attackloop` tiled
  to vanilla's 2.2 s, vanilla's events kept.
- A class without iron-sight clips (`2hh`, `2hl`) plays its aim clip while
  sighted, as FNV does; otherwise the template's own sighted clip shows
  FO4's hold.
- Spline clips use 48-bit quaternions; 40-bit made the idle jitter.

**The hold.** The right hand holds the Weapon bone where vanilla's does.
The gun stays where FNV's clip puts it relative to the camera, unless
FNV's aim pose leaves none of it in FO4's view (80° first-person FOV,
16:9). Then (`off_screen`, `anchor_for`) each clip starts where the
template's matching vanilla clip starts, FNV's motion from there kept.
- FNV's flamer has no clips of its own: `2hh` is the minigun's, aimed 23°
  down at the hip (0% on FO4's screen) and lifted 35° to fire. One move
  from the idle pointed every shot 30° up; per clip, the flamer fires
  level as FO4's does.
- The Tesla on FNV's own hold is 71% on screen and clears the eye by 3.5
  units. Moving it to the Missile Launcher's hold put the barrel across the
  camera and the left hand under the gun.
- FNV's camera bone `Camera1st` is the eye: in `2hraimis`, `2haaimis` and
  `1hpaimis` the gun's `##SightingNode` sits on its forward axis within
  3.2 units. FNV draws first-person arms at fDefault1stPersonFOV 55; FO4
  at 80.

**The left hand.**
- `1hp`: vanilla's grip and finger curl, eased over equip and unequip.
- Others: FNV's hand (on the moved gun). Where it misses our mesh,
  `left_reach` moves it straight to the nearest vertex until its middle
  finger's base is as far from it as vanilla's is from the template's gun
  (about 2 units). FNV's flamer hand reached for the minigun's top handle,
  23 units above the flamer's side handle; it now lands 3-4 units off.
- Reloads keep FNV's hand (it works the magazine).

**FO4's additive layers.** The first-person graph plays, over the gun's
clips, the template's additive layers (blend hint 2): pitch up and down,
turn, constant motion, after-jiggle, jump, stagger, and
`WPNIdleSightedWobble` (an 11.7 s sway while sighted). They are
lossless-compressed, authored on FO4's own hold, and turn FO4's arm bones
by FO4's amounts: on the Varmint Rifle looking down while sighted they put
the left forearm across the camera (played 2026-10-29). FNV's first person
has no such layers, so a converted gun writes each in its folder as a clip
moving nothing, the vanilla length and events kept (`_neutral_layers`;
`WPNJumpLandAdd`'s `JumpDown` stays). `Recoil` (blend hint 1, the
deprecated additive) is left alone. `anim_fo4.fo4_animation_header` reads
any clip's length, events and blend hint, compressed or not.

**The right hand while aiming.** The right hand holds the gun as the
template's clip holds its own (one grip for every clip: FO4's never changes
it, sighted included), so the template decides where FO4's hand, bulkier than
FNV's, sits against the sight line. On the pipe gun the Varmint Rifle's hand
rose into view while sighted (played 2026-10-29); FNV's never shows.
`gun_quick_convert` measures it (aim_hand: the right hand's vertices on a
16:9 screen, FO4's 80° taken as measured on 4:3, so 96° across, the aiming
camera lift applied; the Varmint on the pipe gun 23%, matching the played
view). Across the 38 converted rifles the Hunting Rifle and Assault Rifle
grips keep it at 0–9% (the carbine, played, 8%); the pipe gun, Railway
Rifle and double-barrel grips at 16–57%. Table entries put semi-automatic
and automatic rifles on the Assault Rifle and single-shot, pump, lever and
bolt ones on the Hunting Rifle. Still 20–40% on any grip: the lever-actions,
single and riot shotguns, BB guns, the .22 SMG. Rejected: lining up the
palm instead of the trigger (the two skeletons' middle-finger bases differ
by about 1.6 units, so the 9mm's hand slid to the bottom of its grip) and
the wrist (offsets scattered).

**Heavy guns (2026-10-29).** FNV's `2hh` class (the minigun's clips) holds
every heavy gun off FO4's screen, so each takes its template's hold
(off_screen); the Flamer, Minigun and Gatling Laser holds put the same share
of the gun on screen (Grenade Machinegun 28–30%, Plasma Caster 11%,
Incinerators 17–23%). The Grenade Machinegun, Mercy, Plasma Caster and both
Incinerators go on the Flamer, as the played Flamer: FO4's Minigun and
Gatling Laser graphs spin their barrels up before firing, which none of these
does, and on the Gatling Laser the Plasma Caster's right elbow rose to the
face. The Plasma Caster had been on the Assault Rifle (18% of the right hand
in view while aiming; 0% on the Flamer).

**Heavy-gun left hands.** FNV's `2hh` left fist grips the minigun's top
handle; on the Incinerator that is 18 units above its vertical front post,
and the left_reach drop put the fist palm-down on the post's top edge
(played: it hovered). For a gun moved to its template's hold, vanilla's
left grip (with its finger curl) is carried onto our handle instead
(`handle_grip`): the template mesh piece nearest vanilla's left finger and
ours nearest FNV's, each described by its centre and main directions
(`handle_frame`, from `nif.gun.pieces`), the grip kept in that frame. Only
for handles held the same way (long directions within 45°): the Flamer's
post onto the Grenade Machinegun's top bar pointed the fist straight up, so
that gun keeps FNV's fist and the reach. Incinerators: finger gap 6.0 → 0.8,
on the post.

**Scopes.** FO4 zooms through a scope part: its ZoomData property (OMOD
property 67) names a ZOOM record, the FOV multiplier and the full-screen
overlay. A converted gun keeps the template's default parts, iron sights
included, so the scoped Sniper Rifle zoomed only as far as its sights
(played 2026-10-29). FNV marks a gun with a scope of its own by
DNAM.Flags1 Has Scope (0x4) without DNAM.Flags2 Scope from Mod (0x2000):
the 9mm, the plain Varmint, Hunting and Laser Rifle carry 0x4 with Scope
from Mod and aim down sights until a scope mod goes on (`built_in_scope`).
Don't Use 1st Person IS Anims (0x40) only skips the raise: the Bozar, Gauss
Rifle, La Longue Carabine and Boone's rifle lack it and are still scoped
(0x44 alone missed them and gave the Laser Rifle a scope, 2026-10-31).
Unlisted, such a gun is matched among the FO4 guns with a scope part first
(all of them when none fits), as the layout match put the Gauss rifles,
Boone's rifle and La Longue Carabine on the scopeless Railway Rifle; they
went to the Pipe Bolt-Action. Such a gun takes, in place of the default sights, the scope part
one of its template's combinations uses whose magnification
(fDefaultWorldFOV 70 / FNV's DNAM.SightFOV) comes nearest, a plain scope
before night vision or recon (`GunChoices.scoped`). The part's copy drops
its model (FNV's mesh draws the scope) and keeps the zoom. 0x40 alone also
makes a gun aim with its unsighted clip, as FNV does (`fnv_stem`). The
Anti-Materiel Rifles (Railway Rifle has no scope part) go on the Hunting
Rifle and the Binoculars on the .44. The table keys on EditorID, so Gun
Runners' Arsenal's `NVDLC05…Custom`/`…Unique` copies need rows of their
own: without them they fell to the layout match, which put the AMR and the
Medicine Stick on the Railway Rifle (no scope, its steam), the Tri-beam on
the Combat Shotgun, the Assault Carbine and Bozar on the SMG, the Plasma
Pistol and Hyperbreeder on the Pipe Gun. Each now takes its base gun's row;
the Bozar takes the Assault Rifle for its scope part. That scope is 10x
against FNV's 2x: no FO4 gun's combinations offer a scope under 4x, and the
Combat Rifle (6x) has no default combination, so it can't be a template.

**Third person** keeps the template's clips. Entries copy each template
entry that targets the replaced keyword (third person, power armor) to the
gun's own. Its left hand is IK'd to `WeaponIKTargetL`, a child of the Weapon
bone that each gun folder's two-frame `WPNAssemblyPose` sets (196 of them in
Fallout4 - Animations.ba2, player, NPC and synth copies), so the template's
pose put it on the FO4 gun's fore-end (the carbine's left hand sat under
ours). Since 2026-10-31 each human third-person entry searches first a
folder of the gun's own (`Actors\FNV\Character\Animations\<gun>\<the
vanilla folder's last two>`) holding a copy of that pose whose target is
moved onto our gun (`_with_assembly`, `carried_target`): it keeps the
hand-local offset vanilla's target has from vanilla's first-person left
hand, applied to ours in `WPNIdleReady`. Measured on the Hunting Rifle: the
two hands turn alike (about 2° apart) and sit 1.2–1.5 units apart, so the
hand bones share axes and the offset is the third-person hand's own. A
pistol on vanilla's grip writes no first-person target and keeps vanilla's
pose; other skeletons (power armor) keep theirs. Not played.

**Measured, not changed (2026-10-31):**
- *The left hand going into aim.* FO4's first-person gun graph has no hand
  IK (`LeftHandTarget` is a variable; only the Pip-Boy graph has
  `hkbHandIkControlsModifier`), so ready to sighted is a local-space blend.
  Blended halfway, the left middle finger moves off the gun by at most 1.6
  units more than at either end on the Cowboy Repeater (5.7 → 7.3), none on
  the Varmint Rifle, Service Rifle or Riot Shotgun; FNV's own `2hr` clips
  drift 1.4 the same way. Too small to be the reported slip; its cause is
  still open. Vanilla's idles are `hkaLosslessCompressedAnimation`, which
  the reader cannot decode, so vanilla's own drift is unmeasured.
- *Heavy guns low on screen.* Moving the gun so its body's centre sits where
  the template's does (whole move, then only across the screen) raised the
  share on screen (Flamer 32 → 46–48%, Plasma Caster 11 → 20–34%) but
  folded the right upper arm across the camera in Blender: reverted.
- *The Flamer's reload* is FNV's own (DNAM.ReloadAnim 1, `2hhreloadb`); the
  minigun's is `2hhreloade`.
- *The template's parts* (stock, barrel) left vanilla's left-finger gap
  unchanged (Hunting Rifle 5.28, Assault Rifle 4.39): vanilla's finger is
  nearest the receiver.

**Which guns convert (2026-10-29).** An FNV gun with a near-identical
FO4 gun stays on it (`"as": "stats"`: FO4's mesh, clips and hands, FNV's
stats): 10mm, .44, laser and plasma pistols and rifles, Alien Blaster,
Minigun, Gatling Laser, Missile Launcher, Fat Man, the double-barrel
shotguns. A variant with its own mesh (Pew Pew, AER14, Q-35, Plasma
Defender, Mysterious Magnum, CZ57 Avenger, Annabelle, Big Boomer)
converts on its base's FO4 gun; one sharing the base's mesh follows the
base. Every other gun converts (`"as": "fnv"`), and so does a gun the table
leaves out, on the FO4 gun `gun_choice` picks: no external mod is needed.
The converted laser pistol played fine but held lower on the grip than
FNV's, the reason the near matches stay on FO4's own.

**Modular templates.** A modular FO4 gun (pipe gun and revolver, laser,
plasma) keys its clips on two keywords, neither on the WEAP alone: the
grip mod's `AnimsGripPistol` plus its receiver's or grip's own
(`AnimsRecieverHandmadeRevolver`, `AnimsLaserGripPistol`,
`AnimsPlasmaPistol`). `template_entries` matches the most specific entry
whose targets the gun carries with its default parts
(`GunChoices.clip_keywords`) and replaces the target keying the fewest
entries; when that keyword comes from a part, the gun's copy of that part
(`Guns._part`, `gun_choice.traded`) adds the gun's own instead. A table
entry's `mods` now apply to an `fnv` gun too (`Guns.choose`), so a laser
rifle gets FO4's rifle grip, not the default pistol one.

**Sweep (2026-10-29, offline, every playable FNV gun of a clip class).**
99 of 101 convert (before the modular fix about 35 got no clips); the
sawed-off shotguns find no template. Pistols, revolvers, plasma guns and
most rifles hold with 60–99% of the gun on screen and the left finger
2–5 units off. Flagged:
- Laser pistols (fixed): the gun hung about 10 units below the empty right
  hand. The laser receiver's WeaponTrigger is a placeholder 23 units off
  the gun (19 below, 9 behind; the grip part draws the trigger), and the
  FNV trigger was lined up on it. A trigger bone outside the receiver's
  drawn shapes no longer moves the gun (the 10mm's sits inside its
  receiver, by its `10mmTrigger` shape); the gun keeps its origin, which
  both games put in the hand. Finger gap 8.8 → 2.7; laser rifles 4.1 →
  4.0, more on screen; no other gun moved. The hand holds lower on the
  grip than FNV's, as FO4's laser clips hold theirs.
- Heavy guns moved to the Flamer's hold (Minigun, Incinerator, Plasma
  Caster, Grenade Machinegun) show 10–30% of the gun; the build's own
  choice put the Minigun on the Flamer and the Plasma Caster on the
  Assault Rifle.
- Launchers without a table entry go to the wrong FO4 gun (Fat Man and
  Nellis artillery on the 10mm, Missile Launcher on the Plasma gun): the
  hold matches FNV's, the record behaves as its template. They need table
  entries.

**Checking offline:** `tools/nif/gun_quick_convert.py` converts one
gun's clips in seconds; `tools/nif/gun_pose_scene.py` and
`blender_pose_scene.py` render FNV's hold, ours and vanilla's side by side
([python_tools](../reference/python_tools.md)).

**First tried** on the Varmint rifle (`2hr`, `2hrattack8`, `2hrreloadm`): the
hunting rifle's behaviour graphs kept unchanged, FNV's clips retargeted
onto FO4's human and first-person skeletons (arm IK on) and written under
the vanilla clip names in a folder of the gun's own, reached through an
additive subgraph race (SADD on HumanRaceSubGraphData, as DLC01 adds its
lightning gun) and a keyword of the gun's own; FNV's mesh at FNV's size;
the `##VRClip`/`##VRBolt`/`##VRTrigger` tracks of FNV's character clips on
the receiver's WeaponMagazine/WeaponBolt/WeaponTrigger bones.

- **Why the earlier pass reloaded from the side:** `gun_choice` put the
  Varmint rifle on PipeGun's semi-automatic receiver, whose magazine sits
  2.5 units left of center; its muzzle is 26 past the trigger to FNV's 46.
- **Played:** iron sights were off (shots missed), the left hand came off
  the gun while walking (vanilla walk clips, the hunting rifle's hold),
  the gun never reloaded, and FNV's mesh looks poor in FO4 as ported.
  Offline the hands landed within 0.05 units of FNV's and the gun on
  FNV's, so the failures are in what FO4 does around the clips.
- **Reverted then;** the findings below still hold:
  - FO4's AnimTextData id (`Meshes\AnimTextData\AnimationFileData\<id>.txt`,
    one per subgraph entry's folder list and graph): CRC-32 of the folder
    list joined by `|` as the race writes it (case kept; high half) and of
    the behaviour graph's path in lower case (low half), zero start, no
    final inversion. It reproduces vanilla's and DLC01's names (all six
    MoleratRace entries checked 2026-10-25; an earlier note had the folder
    list lower-cased, which matches none).
  - FO4's character skeletons carry the weapon bones (Weapon,
    WeaponMagazine, WeaponBolt, WeaponIKTargetL...); third person's left
    hand is IK'd to WeaponIKTargetL, which the gun's two-frame
    `WPNAssemblyPose` sets.
  - FO4 shoots a bolt action as two clips (`WPNFireSingleReady`, then
    `WPNBoltChargeReady`); FNV's attack clip holds both.
  - Without arm IK, FNV clips on FO4's rigs put both hands 4.1–5.1 units
    off FNV's (FO4's taller torso).

### <a id="step-map"></a>Step test map (played 2026-10-08)

`fo4_import.spike.step_map` builds `StepTest.esp`: one interior (`coc
StepTest`) of labeled stations, to measure what Fallout 4's player climbs
instead of guessing from converted meshes. Each station's visible mesh is
its collision, sent through Elric as is (no winding repair, no stairs
pass). Click a station in the console: its reference is `Step<code>`.

| Codes | Station |
|---|---|
| A06–A20 | plain step, 6 to 20 tall, 128 deep |
| S12, S16, S20, S24 | the same on a stairs material |
| R20–R50 | ramp at 20–50° up to 46.9 |
| C000–C052, CN052 | the mobile home's doorway (floor 46.9, a bare 10.3 lip with no top, a 22.4 gap, the skirt's slanted face topping 0.9 below the lip), left going south, at the played X tilts (CN052: −0.5238) |
| E06–E14 | that doorway with another lip height |
| GNO, G08–G30 | no skirt (open drop), or another gap |
| FM4, F00, FP1 | skirt top 4 below, level with, 1 above the lip |
| K10 | a 1-thick solid lip (with a top) |
| D000, D052 | the home's own doorway collision cut out (lip notch, jambs, lintel at 196), its pivot kept, X tilt 0 / 0.5238 |
| DNF000, DNF052 | the same cut below 70: the lip notch without the frame |
| H130–H160 | a free-standing doorframe 94 wide, lintel 130–160 above the floor, walked through going north |
| HS130–HS160 | the same on a 10 step starting at the frame, lintel 130–160 above the step |
| StepCaravanTilt / Flat | the converted home itself, door south, X 0.5238 / none |

Every doorway station is entered by its back ramp (20°) and walled on both
sides, so the only way off is over the lip.

Played: every A, S, C, E, G, F and K station lets the player off, and every
ramp up to 45° (R50 does not); StepCaravanTilt lets the player out and
StepCaravanFlat traps them, as in Goodsprings. So the flat 96-wide lip with
an open top is not the mobile home's doorway. What the C stations leave out:
the lip is flat at 57.2 only across its middle 51 units (59.9 by ±35, 68 at
the jambs), the door has a frame (lintel at 196, 139 above the lip), and the
home pivots 90 units behind its door, so its tilt raises the doorway (a C
station pivots at its lip). The D stations add all three.

Played: D000 and D052 trap the player; DNF000 and DNF052 let them off, so
the frame does it, not the lip. No collision crosses the opening between
the lip and the frame's top corners (184–198); the opening is 149 above
the floor and 139 above the lip, against 153 (metal shack prefab doorway),
164 (Prydwen and subway room doorways) and 168 (airport room doorway) in
vanilla FO4's walk-through doorways. Jumping hits the frame too, and
`setscale 0.8` does not help. The H stations measure the headroom FO4's
player needs.

Played: H130–H140 and HS130–HS140 block the player; H145–H160 and
HS145–HS160 let them through. FO4's player needs 141–145 units of headroom
over what it stands on, stepping up or not; `setscale` does not change its
collision. The mobile home's door gives 149 over its floor but 139 over
its lip, so the player is stopped as it steps onto the lip. FNV's player
fitted 139. The player's height comes from the human skeleton's `BSBound`
box ([player collision](research/fo4_target.md#player-collision)): with it
30 shorter, H130 and both mobile homes let the player out (played). The
cell spike now writes the skeletons with the box's top at 115 (played:
H130, both mobile homes and the Goodsprings saloon one let the player out).

Played: Fallout4.esm's unused ScaleCustomCharacterController keyword
(00249F53, "a race with this keyword ... character controller to be
scalable as the character scales") added to HumanRace does not shrink the
player's collision (setscale 0.9, after a reload too). The skeleton's one
Havok capsule is CharacterBumper's (radius ~13, top ~124), not the movement
capsule, and no GMST sizes it (only fCharControllerCheckHeightOffset and
fCharControllerWarpDistSqr exist): the 141–145 comes from the executable.

### <a id="spike-2-facegen"></a>FaceGen and FNV faces (played 2026-10-06)

The CK exports FaceGen from the command line: `CreationKit.exe
-ExportFaceGenData:<plugin> X64`, never `W32` (see
[stretched hair](#spike-2-hair-cloth)). It writes
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

<a id="spike-2-hair-cloth"></a>**Stretched long hair (fixed 2026-10-19, not yet
played).** On a fresh save, women with long FO4 hair had a strand stretched
from the head to the floor (a woman at the Vikki and Vance bar in Primm). It
was not old save state, the seat or the skeleton: it followed the FaceGen
export. FO4's long hairs carry cloth physics, a BSClothExtraData block holding
a Havok packfile (`hk_2014.1.0-r1`). Primm's women wear HairFemale04 (two
residents) and HairFemale13; their FaceGeom NIFs, set beside vanilla
Scarlett's (0004B240, also HairFemale04):

- Skinning matches: the same 11 bones (`HEAD`/`Head`, `Head_skin`, nine
  `Hair_{C,L,R}_Cloth0n`), the cloth bone nodes in both, same vertex data
  size.
- The cloth block does not. Vanilla FaceGen keeps the hair's own packfile
  (46,260 bytes, the same size as `FemaleHair04.nif`'s). Ours was 43,908, and
  its layout byte for pointer size (packfile offset 16) was 4, where vanilla
  is 8.

The CK knows four export targets, `XB1 X64 PS4 W32` (a string table in
`CreationKit.exe`). We passed `W32`, so it re-serialized every cloth packfile
for 32-bit pointers, which the 64-bit game misreads. `spike.facegen` now
passes `X64` (`CK_TARGET`), and `export` stops if any collected FaceGeom
NIF's cloth packfile is not 8-byte (`cloth_pointer_sizes`). The bake is not
involved: it moves vertex positions only, and these NPCs are STH faces (not
baked). Re-exported with X64, the region's 167 FaceGeom NIFs hold 7 cloth
hairs (HairFemale04 ×4, HairFemale01 ×3, all women), all 8-byte. Each one's
packfile is byte for byte the hair mesh's own. HairFemale13 has no cloth.

<a id="stale-facegen"></a>**Stretched long hair again: stale FaceGen (2026-11-11, not
yet played).** The same plank came back in Primm with every deployed cloth
packfile still 8-byte and byte-equal to the vanilla hair's, cloth bones as
vanilla Scarlett's, and every shipped skeleton equal to the lowered vanilla
one. The FaceGeom NIFs were stale: exported 2026-10-30, before hair matching
by name and style (2026-11-07) changed the records. 101 of FalloutNV's 167
FaceGeoms drew other hair than their NPC's record, e.g. PrimmResidentFemale2:
the record HairFemale15, the FaceGeom HairFemale04 with its cloth. The CK
names each FaceGeom shape for its head part's EditorID, so
`facegen.outdated` compares those names with the parts the record draws
(`facegeom.head_parts`), and the build deletes a FaceGeom that differs
before it prunes face textures and packs (`build_finish._faces`, after the
plugin write); the game then draws that NPC from the record until the faces
stage runs again. Counted as `FaceGeom NIFs older than their NPC head parts
removed`. A fresh export (NVWillow) has none; the check takes 1.5 s.

<a id="hair-styles"></a>**Hair by name, then style (2026-11-07).** Coverage
alone lost Sgt Kilborn's crop: FNV's HairAfricanAmericanBase is a solid
short crop, and coverage picked HairMale17, a shaved stubble. Both games name
their hairs (FNV HAIR FULL, FO4 HDPT FULL as a Fallout4.esm string), and many
FO4 names are Fallout 3's, which FNV keeps. `fo4_import/face/hair_styles.py`
narrows the candidates before coverage picks:

1. **Name.** An FO4 hair of the NPC's sex whose name equals the FNV hair's
   (lower case, letters and digits only). Male and female hairs can share a
   name (Blast Back), so the sex filter comes first. Checked side by side on
   the FO4 head: Warhawk, Blast Back, Pompadour, Bedraggled, Balding, Shaggy
   Suave, Waster, Combover; female Wendy the Welder, No Nonsense, Unladylike,
   Rude Ridge, Fairy Tails, Frazzled, Rough Nite, The Sophisticate.
2. **Style.** `fo4_import/data/hair_styles.json` maps each FNV hair with no
   name match (by EditorID) to a group of FO4 hairs drawn in its style,
   grouped by eye from front and side renders of both games' hairs on the FO4
   head. FO4's Megaton and Hornet's Nest render oddly there and are in no
   group.
3. **Coverage** over every hair of the sex, as before, for a hair in neither.

Over the 2,670 FNV NPCs with a hair: 732 by name, 1,870 by style, 68 by
coverage alone (children's and ghouls' hairs, and NPCs wearing the other
sex's hair). Buzz Saw (527) and Buzz Cut (219, Kilborn's) became Short Crop,
The Unsettler Bedraggled, Clean Cut Heavyweight, Tunnel Snake Rebel.

Coverage still picks within a name match (one hair) or a group. The hair
choice is part of the face fit's code tag, so a change here makes the
published `face_fits.json.gz` stale until it is re-exported.

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

**Exposure (played 2026-10-10).** That assumption washed out Vikki and Vance. The
alpha FNV's exposure divides by is constant, so FNV does not brighten a dark
room, while the base imagespace auto-exposes 0.5x–15x toward middle grey.
`pack_imgs` now pins Auto Exposure Min and Max to `fixed_exposure`:
middle grey / fo4_display(middle grey)^2.2 = 0.18 / 0.393^2.2 = 1.40. With the
LUT, FO4 then shows exposed colour c as c^(1/2.2), FNV's display, at every
level (0.01 / 0.05 / 0.18 / 0.5 → 0.123 / 0.256 / 0.459 / 0.730 on both).
Cells without an FNV imagespace keep QASmoke's.

**Superseded 2026-11-09:** the LUT no longer carries FNV's curve; FO4's
curve and bloom act, with exposure pinned at 1.46 so middle grey still
shows where FNV shows it ([tone](fo4_look.md#route-tone)).

## <a id="scene-census"></a>Scripted sequences as FO4 scenes (census 2026-10-07)

**Drift policy.** Emulating an FO3/FNV mechanism exactly on FO4 costs
play-test rounds (VCG01: dropped lines said from a line's end, the
Reflectron view, Say Once across two copies of a greeting, a copied
package's Weapon Drawn flag). FO4's own systems already change combat,
movement and characters, so a sequence may play the FO4 way when that is
simpler: prefer the FO4-native mechanism, record each change from FO3/FNV
behavior in [fo4_drift.md](fo4_drift.md), and leave exact parity to a
later patch. No content is dropped.

**Census** (`temp/scene_census.py`, FNV / FO3 exports):

| Pattern | FNV | FO3 | FO4-native target |
|---|---|---|---|
| Line results that `Say`/`SayTo` the next line (chains) | 282 | 36 | One scene, a Dialogue action per line; results become fragments. Drops `SayWhenFree` and FNV's first-passing stepping |
| Topics object/quest scripts `Say` (1 line / 2–5 / 6+) | 88 (47/28/13) | 116 (35/47/33) | 1-line and pool topics stay Papyrus `Say` barks; multi-line ones are chains |
| Scripts that talk inside a GameMode timer (timed beats) | 80 | 76 | Scene phases with Timer actions where the script is a straight sequence; the rest stay converted Papyrus |
| `StartConversation` with the player (scripts + results) | 76 | 3 | Stage-started scene, or a ForceGreet whose greeting starts it |
| Dialogue packages on the player (GREETING / named topic) | 67 / 226 | 132 / 50 | FO4 ForceGreet (vanilla: 108 on Greeting, 106 on Hello); the line starts the scene |
| NPC↔NPC talk (Dialogue packages on others + `StartConversation` NPC) | 39 + 16 | 204 + 7 | Two-actor scenes, as FO4's ambient conversations |
| Quest-gated packages (scripted walks, positions) | 1,454 | 1,399 | Stay FO4 packages (built); a package that is a beat inside a sequence becomes a scene package action |
| Menu dialogue (lines with Choices / Follow Ups) | 6,348 / 1,107 | 7,717 / – | XDI scenes ([spike 1](#spike-1-design), [2b](#spike-2-vcg01)) |

Quests with scripted talk: 69 in FNV (66 also move NPCs with quest-gated
packages; VMS49, VMS29a, VFreeformMcCarran2, VMS18, VCG00, VCG01 lead), 42
in FO3 (CG02, the tutorial: 24 Dialogue packages and 56 gated packages; MQ05,
MQ07, MS06, CG03).

**Expected outcome.** Chains, force greets and NPC↔NPC talk (706 FNV and 432
FO3 sites) map onto scenes mechanically: the order is the scene's,
not a race between packages, the GREETING picker and Say Once. Drift:
pacing between lines, how an NPC approaches or stands up, and lines picked
by scene order rather than FO3/FNV's first-passing rule. Timed beats need a
per-script pattern match, so only straight sequences convert. Packages stay
packages. First comparison: VCG01's outro as one stage-started scene against
the force-greet build.

## <a id="creature-census"></a>Creatures on Fallout 4 (census 2026-10-10)

Placements per FO3/FNV creature skeleton folder, counting placed creatures
and leveled lists (a list's share split over its entries, through
templates; FNV's `nvvoid`, the empty "spawn nothing" entry, left out),
against Fallout 4's races (Fallout4.esm and the three DLCs).

| | FNV | FO3 |
|---|---|---|
| Placements | 2,547 | 3,349 |
| FO4 has the same creature | 1,292 (51%) | 3,095 (92%) |
| FO4 has a close body plan | 698 (27%) | 185 (6%) |
| No FO4 counterpart | 556 (22%) | 69 (2%) |

- **Same creature** (FO4 race): feral ghoul, dog (Dogmeat), deathclaw,
  radscorpion, super mutant and behemoth, brahmin, mole rat, radroach,
  bloatfly, mirelurk and king, yao guai, protectron, Mr. Gutsy (Handy),
  sentry bot, eyebot, robobrain (Automatron), turrets, Liberty Prime,
  alien.
- **Close body plan:** giant ants (Nuka-World rad ant), giant rat
  (Nuka-World rad rat), bighorner (brahmin or radstag), cazador
  (stingwing), night stalker (dog body), raven (no FO4 bird race; FO4's
  birds are ambient critters).
- **None:** FNV gecko 256, giant mantis 126, securitron 104, centaur and
  floater 29, spore carrier 20, spore plant 12, Mr. House's computer and
  Festus; FO3 centaur 53, Eye Intercom 14, failed FEV subject 2.
- **The Goodsprings block:** 5 young bighorners, 4 ravens. VCG02 adds
  geckos and Sunny's dog Cheyenne.
- **Bones share no names.** FNV builds every creature on a `Bip01` biped
  rig; FO4 names its own (`Dogmeat_COM`, `LArm1`, `HubSpine`): dog 58
  against 67 bones, brahmin 51/50, deathclaw 78/89, ghoul 62/94,
  radscorpion 66/75, mole rat 49/45, super mutant 59/111, none shared
  (`Weapon` aside). An FNV mesh moves onto an FO4 skeleton only by
  position, as the outfits take FO4's body weights at each vertex's
  nearest point ([outfits](#spike-4-outfits)).

Three ways a creature can convert:

1. **FO4's own creature** (record, mesh, skeleton, behaviour): the
   replacement table, as guns default to FO4's.
2. **FNV's mesh on FO4's creature:** aligned to the FO4 creature's bind
   pose and weighted from its skin; FO4 animations, AI and combat. For
   the "same" and "close" rows (78% FNV, 98% FO3).
3. **FNV's skeleton, animations and behaviour graph rebuilt for FO4**
   (Havok 2014; `external/pynifly_hkx/anim_fo4.py` reads and writes FO4
   animations; the Skyrim converter builds creature graphs in
   `asset_convert/havok`). The only way to keep geckos, mantises and
   securitrons; the costliest.

### <a id="creature-option3"></a>Option 3: FNV's own skeletons on Fallout 4 (feasibility 2026-10-10)

What a vanilla creature ships (the mole rat, Fallout4.esm `MoleratRace`):
the race names a behaviour **project** (`Actors\Molerat\MoleratProject.hkx`,
male and female `MODL` after `NAM3`), shared subgraphs (`SGNM`
`Actors\Shared\Behaviors\MoleratSharedCoreWrappingBehavior.hkx`, the
ambush and furniture behaviours) each with an animation folder (`SAPT`),
the skeleton NIF (`ANAM`) and attack data (`ATKD`/`ATKE`: events such as
`meleeStart_1_Mirrored`). Under `Actors\Molerat\`: the project, a
character file (`Characters\MoleratCharacter.hkx`), its behaviour
(`Behaviors\MoleratRootBehavior.hkx`), `CharacterAssets\skeleton.hkx` (the
animation skeleton, a skeleton mapper and an `hknpRagdollData` ragdoll)
and 74 clips in `Animations\`, plus `AnimTextData\AnimationFileData\
moleratproject.txt`. All files are `hk_2014.1.0-r1` 64-bit packfiles.

| Piece | State |
|---|---|
| Body mesh, skeleton NIF | Have: the FO4 NIF writer and skinning (Cheyenne) |
| Animations (FNV `.kf` to FO4 `.hkx`) | Have the parts: the Skyrim converter decodes and retargets KF (`asset_convert/havok/kf_decode.py`, `clip_retarget.py`); `external/pynifly_hkx/anim_fo4.py` writes FO4 spline-compressed animations |
| Animation skeleton (`hkaSkeleton`) | Have: `anim_fo4.write_fo4_skeleton` |
| Ragdoll and skeleton mapper | Missing: no `hknpRagdollData` writer; Elric builds static physics only |
| Behaviour graph, character, project | **Missing, the blocker** |
| AnimTextData, RACE | Easy: text, and a copy of a vanilla race |

**The behaviour graph is the blocker.** The FO4 root behaviour holds 42
classes (`hkbStateMachine`, `hkbClipGenerator`, `BSLookAtModifier`,
`hkbKeyframeBonesModifier`, `hkbGetUpModifier`...). Nothing here reads or
writes Havok 2014 behaviour classes: `hkxconv` (HKX2E) and `hkxcmd` know
Skyrim's 2010 layouts only, and pynifly reads only animations and
skeletons. The files carry no class descriptions (`__types__` is empty in
the project, behaviour and skeleton), so a reader needs every layout from
elsewhere. `Fallout4.exe` and `CreationKit.exe` hold the member names
(`cropStartAmountLocalTime`, `hkbFootIkDriverInfo`), but in string lookup
tables (`0x142F40B18`), not static `hkClass`/`hkClassMember` records; the
layouts are built in code. Recovering them means disassembling Havok's
type registration, or inferring ~40 layouts from vanilla files against
Skyrim's 2010 ones. Bethesda ships no behaviour tools (`Tools\`: Elric,
LipGen, Archive2, the material editor, the NIF exporter).

Three ways a creature with no FO4 counterpart can still convert:

1. **FNV's mesh on the nearest FO4 rig** (option 2). The FNV gecko is an
   upright biped (pelvis z 36, head z 87, arms with hands, digitigrade
   legs, a tail): FO4's deathclaw rig, scaled down. FO4's deathclaw
   animations and AI. **Played 2026-10-10 and dropped:** it reads as a
   deathclaw ([geckos](#spike-4-creatures)); a vanilla stand-in (a mole
   rat) is the default until a ported gecko.
2. **A vanilla behaviour project reused byte for byte, FNV's motion on
   its rig.** The project, character and behaviour files are copied
   unchanged under a new folder (their paths are relative, so nothing in
   them changes); the skeleton keeps the vanilla rig's bones and order (so
   every bone index in the behaviour stays valid) at FNV's proportions;
   FNV's clips are retargeted onto it and written under the vanilla clip
   names. FNV's look and motion on FO4's states, attacks and events. Needs
   the skeleton (and ragdoll) rewritten in place: same bone count, new
   reference pose and shape sizes. No new behaviour writer.
3. **FNV's skeleton and its own behaviour graph:** the full option 3.
   Needs a Havok 2014 behaviour serializer, a project of its own.

**Behavior Graph Studio** ([Nexus 107691](https://www.nexusmods.com/fallout4/mods/107691),
source [G-A-R-D-E-N/BGS](https://github.com/G-A-R-D-E-N/BGS), MIT, C#/.NET)
removes the serializer blocker: `src/Hkx/HavokClassTypes.json` holds the
Havok 2014 class layouts (hkxpack's MIT class descriptions with instance
sizes measured from Fallout 4), under a native reader and writer for
behaviour, character, project, skeleton and animation files (all 531
vanilla behaviour graphs parse; 15,320 animations rebuild byte for byte;
add, remove and rename edits go through its native writer). Not covered:
ragdoll physics (its physics tab is a preview and writes no HKX physics),
skeleton-mapper write-back (unfinished; its mapper math is documented in
BGS's `skeleton-mapping-authoring.md`), and bone-index edits in skeletons
that hold physics or mapper data. The route, when option 3 resumes: a
Python Havok 2014 reader and writer built on its class tables (with the
MIT notices), proved by rebuilding every vanilla behaviour byte for byte,
as the NIF writer was. Parked with the modlist direction
([direction](fo4_replacements.md#direction)) until 2026-10-25; resumed as
[own rigs](#own-rigs) and [fo4_own_rig.md](fo4_own_rig.md).

A community port (GrilledTurkey's, [candidate mods](fo4_replacements.md#candidate-mods))
answers the same need as way 1 or 2 for the creatures it covers.

### <a id="route-b"></a>Route B measured: the gecko on the deathclaw rig, and rigs for the rest (2026-10-25, offline)

Way 2 above, tested without a build. The FO4 rig keeps its bone list and
order (so its behaviour graph, ragdoll and attack events stay valid), its
rest pose moves to FNV's proportions, and FNV's own clips are retargeted
onto it with `clip_retarget` (the method `havok/human_clip.py` uses for
the played standing idles). Since [combat styles](fo4_pipeline.md#combat-styles),
[attacks](fo4_pipeline.md#creature-attacks) and [speed](fo4_pipeline.md#creature-speed)
the creature also decides, attacks and runs as FNV's does; the 2026-10-10
gecko-on-deathclaw failure (deathclaw motion, aggression, size) was all
three.

- **Motion transfer is exact.** Gecko → deathclaw by a hand map (spine 4 →
  3 plus SpineControl, neck, head, jaw, both arms with every finger, legs,
  tail 5 → 7 bones): with FO4's bones at FNV's rest positions every watched
  bone (feet, hands, head, tail tip) lands on FNV's to 0.0% of leg length
  on idle, walk, run and five attacks. Keeping the deathclaw's own
  proportions at the gecko's size (scale 0.268) is 20–35% off at the feet,
  15–45% at the hands, 41–56% at the head and 52–74% at the tail, idle
  included: the upright gecko becomes a hunched deathclaw. The rest-pose
  rewrite is what Route B buys.
- **Clip coverage, gecko on the deathclaw graph (about 85 clips):** FNV
  has idle and combat idle, walk and run forward (sprint can take the
  run), turns, left/right/power-forward attacks, hit reactions for head,
  torso and each limb (FO4's crit hits by the same parts), a get-up, hurt
  walk and run (FO4's injured-legs states), and special idles for FO4's
  idles and taunts. FNV has none for walking or running back, sideways or
  on diagonals (FNV's gecko never moves that way; its style's circle and
  fall-back are near 0), jumps, staggers beyond hit reactions, deaths
  (ragdoll), and the 12 paired kill moves (to be left out). The horn ram,
  tail combo and jump attacks would have no clip and come off the attack
  list.
- **Events map one to one:** FNV `Hit` → `HitFrame` (with `preHitFrame`
  and `weaponSwing` before it; FO4 never picks an attack without one),
  `Enum: Left`/`Right` footfalls → `FootLeft`/`FootRight` plus
  `SyncLeft`/`SyncRight` on cycles, `Sound: X` → `SoundPlay.X`.
- **The files.** The deathclaw `skeleton.hkx` (65 KB) holds the animation
  skeleton (86 bones), the ragdoll's own skeleton, two skeleton mappers and
  an `hknpRagdollData` (27 capsules, 8 convex shapes, a compressed mesh,
  25 ragdoll and 2 hinge constraints). The animation rest pose is a fixed
  array and patches in place (`anim_fo4` already locates it); the ragdoll
  skeleton likewise; the mappers' transforms, the shapes and the
  constraint pivots need their class layouts, which these files do not
  carry (Behavior Graph Studio's MIT class tables have them, not in
  `references/`). Unpatched, a dead gecko would ragdoll at deathclaw size.
  `write_fo4_animation` writes the extracted-motion block as zeros; walk
  and run need FNV's root travel in it. The mesh needs no vertex fit:
  FO4's bones sit at FNV's positions, so FNV's skin weights only change
  bone names (unmapped fins and eyes ride their parent).
- **Rigs for the creatures FO4 lacks** (a chain matcher over 14 FNV
  creatures and 36 FO4 rigs, base game and DLC; fit 1.0 = FNV against
  itself; "FNV-prop error" is the Route B error, 0 when every chain has a
  counterpart):

  | FNV creature | Best rig | Animated bones mapped | Route B error idle/run | Fit |
  |---|---|---|---|---|
  | Gecko | deathclaw | 60/82 (head fins lost) | 0.1 / 1.2% | good |
  | Spore carrier | deathclaw | 42/45 | 3 / 7% | good |
  | Bighorner | dogmeat | 33/33 | 1.1 / 2.6% | good |
  | Giant rat | deathclaw | 48/55 | 1.8 / 8.3% | good |
  | Giant mantis | mirelurk hunter, fog crawler (DLCCoast) | 32–33/36 | 0.1 / 0.1% | good; wing stubs on arms |
  | Night stalker | dogmeat | 36/47 | 5% | good, but FNV ships no walk or run clip |
  | Giant ant | radroach | 25/33 | 15 / 15% | partial: abdomen unmatched |
  | Queen ant | radscorpion | 38/45 | 4 / 5% | head on an arm: poor |
  | Cazador | radscorpion | 50/56 | 23 / 4% | poor: no rig has 6 legs, 4 wings and a stinger |
  | Securitron | mirelurk king, robobrain | 41–46/57 | 7–13 / 24–47% | poor: wheel, doors, screens |
  | Centaur | robobrain, createabot | 48–50/53 | 14 / 25% | poor |
  | Raven | mirelurk king | 23/27 | 13.5% | poor; 3 clips only |
  | Spore plant | fog crawler, mirelurk | 26–29/48 | — | poor; never moves |
  | Failed FEV subject | — | — | — | no skeleton file, no clips |

  The matcher (scratch, not a tool yet) resolves siblings greedily, weighs
  every bone alike, and checks topology only: a rig's own graph needs
  (foot IK legs, head tracking, ragdoll bodies) are not measured.
- **What it leaves for a build:** a skeleton patcher (animation pose now;
  ragdoll with class layouts), root motion in the clip writer, the gecko
  bone map, the clip table (FNV group → vanilla clip name) with event
  mapping, a project folder of its own (the graph files copied unchanged;
  AnimTextData by the CRC rule [found for guns](#spike-4-gun-clips)), a
  race copy naming it, and the creature entry. The gun-clip spike's
  failures (sights, hand IK on walk clips, no reload) came from what the
  vanilla graph does around replaced clips; a creature graph has foot IK
  and look-at instead, still to be seen in game.

### <a id="own-rigs"></a>Own rigs: what IceStormNG's tutorial shows (2026-10-25, read)

IceStormNG's *New Creatures from Scratch* (Nexus 56676, commissioned by
VelvetGoat; three PDFs, two sample creatures as Havok XML, in
`references/New Creatures Behavior and Implementation`) builds a creature
with 3ds Max 2013, Havok Content Tools and the Havok Animation Tool. What
it settles for a converter that has none of those:

- **The ragdoll lives in `skeleton.nif`, not in a hand-written hknp file.**
  Bethesda's exporter writes the ragdoll (one rigid body per controlling
  bone, capsules first, compounds allowed), its constraints (ragdoll or
  limited hinge only; n − 1 of them), a `CharacterController` (phantom)
  and optional `CharacterBumper`, and a `BoundingBox` node for pathing;
  Elric turns it into FO4 physics. Vanilla confirms it: the deathclaw's and
  mole rat's `skeleton.nif` hold a `bhkRagdollSystem` (hknpRagdollData,
  hknp capsules and convex shapes, hkp ragdoll and hinge constraint data)
  beside `bhkNPCollisionObject`/`bhkPhysicsSystem`. FNV's skeletons carry
  an authored ragdoll in the same terms (gecko: `bhkRigidBody(T)`, capsules
  and boxes, `bhkRagdollConstraint`, `bhkLimitedHingeConstraint`), and
  `nif/collision.py` already writes those constraints in FO4's pre-Elric
  layout for statics.
  - **Tested 2026-10-25 (offline): Elric builds the ragdoll.** FNV's gecko
    `skeleton.nif` through `convert_static.convert` (25 `bhkRigidBody` on
    bone nodes, 22 capsules, 3 boxes, 20 ragdoll and 4 limited-hinge
    constraints) and Elric gives a `bhkRagdollSystem` holding
    `hknpRagdollData`, its own `hkaSkeleton`, hknp capsule and convex
    polytope shapes, mass properties, `hkpRagdollConstraintData`,
    `hkpLimitedHingeConstraintData` and a position motor — vanilla's class
    set — with a `bhkNPCollisionObject` on each of the 25 bones (pelvis,
    spine, neck, head, jaw, tongue, arms, legs, tail). BSXFlags (0x82, 0x86,
    vanilla's 0xC6) and the file's path made no difference.
  - **Missing beside vanilla** (the mole rat): the `CharacterController`
    and `CharacterBumper` nodes, whose bodies form vanilla's separate
    `bhkPhysicsSystem` (FNV has no counterpart; the tutorial builds them as
    phantom capsules), `BSBound` (FNV's skeleton has one), the bones without
    a body (the static converter keeps only bodies and their parents;
    a creature skeleton needs every bone), `BSBoneLODExtraData` and
    `BSLagBoneController`. Whether the game ragdolls it was played later:
    it does ([ragdoll](#own-rig-ragdoll), 2026-10-27).
    Probe: `elric_ragdoll_test.py` in the session scratch.
  - **Controller and bumper, tested 2026-10-25 (offline).** The gecko
    skeleton with every bone kept (88 FNV bones) plus two root children,
    `CharacterController` (capsule through the `BSBound` centre, radius 0.8
    × its smaller half width) and `CharacterBumper` (1.2 ×), on layer 30
    (FO4_CHARCONTROLLER). Written either as a keyframed `bhkRigidBody` under
    a `bhkCollisionObject` or as a `bhkSimpleShapePhantom` under a
    `bhkSPCollisionObject`, Elric gives vanilla's split both ways: both
    nodes point to one `bhkPhysicsSystem` (`hknpPhysicsSystemData`, hknp
    capsules) and the bones to the separate `bhkRagdollSystem`, as the mole
    rat's do. **The phantom form is vanilla's:** its physics system is
    1,876 bytes like the mole rat's (the body form 2,100), its two layer-30
    filter words sit at the same offsets (696, 792), and 375 of its 469
    words are identical; the rest are the capsules' geometry and a few
    words near 724–844 (vanilla 0.641 where ours is 0), not identified.
    Probe: `elric_controller_test.py`, `controller_compare.py`.
- **`skeleton.hkx` can be skeleton-only.** The tutorial's game export
  (`ExportSkeleton`: align, create skeletons, prune, write AMD64 packfile)
  has no ragdoll or mapper, which is what `anim_fo4.write_fo4_skeleton`
  already writes. Vanilla's carry ragdoll data too; the tutorial's working
  creatures do without. The ragdoll `.hkt` with hkp bodies and two
  `hkaSkeletonMapper`s is only an input to the Havok Animation Tool.
- **Behaviours as XML.** HAT exports TagXML; hkxpack packs it to FO4's
  64-bit packfile (IceStorm ships a modified hkxpack that encodes certain
  flags hkxpack 0.1.6 gets wrong). The character file needs its character
  controller block replaced and `hkRootLevelContainer` moved first; the
  project is a fixed template. Behaviours: a root (the
  `BSBehaviorGraphSwapGenerator` subgraph entry and the ragdoll state) and
  a core with everything else; the root carries every event and variable
  the core uses. Bethesda node types (`BSIsActiveModifier`,
  `BSiStateTaggingGenerator`, `BSAssignVariablesModifier`,
  `BSDirectAtModifier`, `BSRagdollContactListenerModifier`,
  `DynamicAnimationTaggingGenerator`…) are inserted by IceStorm's
  HavokBehaviorPatcher, since HAT lacks them. A generator writing the XML
  itself (as the Skyrim one writes Havok 2010 XML) needs neither tool.
- **The engine contract** (variables): `bGraphDriven` (default; movement
  from the clips' root motion), `bAnimationDriven` (attacks, evades, jumps;
  Root moves in the plane, COM up and down), `bAllowRotation`,
  `bEquipOk`, `IsAttackReady` (else `WeaponFire` does nothing),
  `IsSprinting`, `iState` with `iState_<X>` constants naming movement
  types, `iSyncTurnState` (Idle 1, Turn_Right 0, Turn_Left 2), `Speed`,
  `SpeedSmoothed`, `TurnDeltaSmoothed` (−90 right to 90 left),
  `weaponSpeedMult`, `bSupportedDeathAnim`, `bManualGraphChange`,
  `bAimActive` with `camerafrom{x,y,z}`, `iIsInSneak`, hit-reaction twist
  floats `<Prefix>{X,Y,Z}Twist`. Events: `HitFrame`, `PreHitFrame`,
  `WeaponSwing`, `WeaponFire[.n]`, `WeaponDraw`/`WeaponSheathe`,
  `ReloadComplete`, `SoundPlay.<EDID>`/`SoundStop`, `CullBone`/`UnCullBone`,
  `StartAnimationDriven`, `AddRagdollToWorld`,
  `RemoveCharacterControllerFromWorld`, `ReevaluateGraphState`; the engine
  sends `startWalk`/`startRun`, `sprintStart`/`sprintStop`. Melee attack
  events must begin `melee` (the Creation Kit's Update Events takes only
  those). HavokScript is not implemented.
- **Actor actions reach the graph through IDLE records** (Animation
  Manager, under the behaviour file): `ActionMoveStart`/`Stop`,
  `ActionDeath`/`ActionDeathWait`, `ActionRagdollInstant`,
  `ActionDodge`/`Evade` (direction in `GetActionDataByte`: 0 right, 1 left,
  2 back, 3 front), `ActionLargeMovementDelta` (in-place turns,
  `MovementIdleMatches`), `ActionInitializeGraphToBaseState`, bleedout,
  unconscious, limb and leg critical, draw and sheathe. An action with no
  IDLE is treated as unsupported.
- **Records:** body part data (a root part; `Head1`/`Head2` parts are the
  creature's vision; part node, VATS target, segment index, actor value,
  damage mult, health percent, to-hit chance; meat caps at sub-segment
  102, robot sub-segment damage at health threshold + 2), race (skeleton
  NIF, project path, skin armor, movement flags, `Base Movement Defaults`
  left empty when `iState` is used, attack data by Update Events, combat
  slots, subgraphs), skin ARMO/ARMA, weapons, movement types per `iState`
  name, and AnimTextData from `CreationKit.exe -GenerateAnimInfo:<esp> Data
  Data --speed --stance` (plugin name without spaces; empty output means a
  broken graph or events).
- **Skeleton rules:** `Skeleton` dummy → `Root` (origin) → `COM`; skin only
  below Root; unique bone names; extra non-animated bones for VATS targets
  and body parts; `WEAPON` (or named slots) with `ProjectileNode`; +Y
  forward, +Z up; segments on every polygon.

- **Behaviour files, tested 2026-10-25 (offline): a Python Havok 2014
  reader and writer works.** Driven by hkxpack's MIT class descriptions
  (`classxml/` in the tutorial's `hkxpack-core.jar`, read as data, the jar
  not run: 910 classes with 64-bit member offsets, signatures, enums), it
  rebuilds **785 of 786** vanilla behaviour, character and project files in
  `Meshes` byte for byte in 2 s (every `.hkx` outside `animations\` and
  `characterassets\`; the one miss is
  `genericbehaviors\zsingleboneskeleton\singleboneskeleton.hkx`; the two
  creature `skeleton.hkx` tried, with hknp ragdoll data, do not round-trip).
  The packfile rules, measured against vanilla:
  - Section headers at 0x40 plus the u16 at 0x3E; class names in
    first-use order after `hkClass`, `hkClassMember`, `hkClassEnum`,
    `hkClassEnumItem`; fixup tables padded with 0xFF to 16, no end marker.
  - Objects in a depth-first walk from the root container over pointers in
    member order, each 16-aligned; an object's size is its last member's end
    rounded up to 16 (hkxpack gives no sizes).
  - Each object is followed by its arrays (contents 16-aligned) and strings
    in member order, recursing into struct elements. A member string pads to
    16 after; strings of a string array are 2-aligned back to back, padded to
    16 after the last.
  - Every array, saved or not, has capacity `count | 0x80000000`.
  - Local fixups in write order; global (pointer) fixups in member order, an
    array's element pointers where the array member sits.
- **A minimal gecko project written with it (offline, not played):**
  - **Root:** the subgraph swap and a fully-ragdoll state (powered ragdoll,
    no bone list, max force 0, entered with
    `RemoveCharacterControllerFromWorld` and `AddRagdollToWorld`), carrying
    every core event and variable, as vanilla's radroach root.
  - **Core** (85 objects): noncombat and combat (`weapEquip`/`weapUnequip`,
    entering with `weaponSheathe`/`weaponDraw`). Each holds standing (idle
    and turns, synced to `iSyncTurnState`) and moving (FNV walk and run
    blended on `Speed` at their root speeds, 62.5 and 578.6 units/s).
    Combat sets `IsAttackReady` and `bEquipOk` and starts four attacks on
    `meleeStart_Left`/`_Right`/`_Power`/`_ForwardPower`; FNV's `Hit` key
    becomes `preHitFrame` (−0.2 s), `weaponSwing` (−0.1 s) and `HitFrame`,
    as the deathclaw's clips space them, and `AttackEnd` returns.
  - **Character and project:** the mole rat's, re-pointed (root behaviour,
    10 clips, an 88-bone L/R mirror map).

  Not in it yet: hit reactions, staggers, the get-up, dynamic idles, the fire
  gecko's breath (`2hl*`, `Fire` → `WeaponFire`), head tracking, foot IK and
  sprint. Also outside the files:
  - the IDLE records that turn actor actions into these events (the
    Animation Manager);
  - the race's subgraph entry naming the core;
  - the clips, skeleton and AnimTextData.

  Probes: `hk2014.py`, `hk2014_write.py`, `hk_corpus.py`, `hkb_build.py`,
  `gecko_graph.py` in the session scratch.
- **The whole single-gecko test assembled (2026-10-25, offline, not
  played).** `gecko_test.py` (session scratch) writes a 6.4 MB Data tree:
  `FNVGeckoTest.esp` (Fallout4.esm master) and `Actors\FNVGecko\`.
  - **Bones:** FNV's 87, the accumulation root `Bip01` as `Root`
    (vanilla's bone 0; the mole rat has no `COM`), the same names in
    `skeleton.hkx` (`anim_fo4.write_fo4_skeleton`, `Root` and
    `Bip01 NonAccum` unlocked), the Elric `skeleton.nif` (ragdoll,
    `CharacterController`/`CharacterBumper` phantoms, as tested above), the
    clips and the body's skin.
  - **Clips** (10, `anim_fo4.write_fo4_animation`, then the
    `hkaDefaultAnimatedReferenceFrame` samples filled in place): FNV's
    accumulation-root motion per frame as (x, y, z, yaw) since the first
    frame, vanilla's form (the mole rat's walk moves 55 units in 0.47 s,
    its turn 1.05 rad). Walk 50 units per 0.8 s cycle, run 231.5 per 0.4 s,
    the forward power attack lunges 374. FNV's turn clips carry no root
    rotation (FNV turned creatures itself), and vanilla creature graphs
    start `bGraphDrivenRotation` 0 and `bGraphDrivenTranslation` 1 (27 of
    the 30 root graphs read), so the engine turns the gecko, as FNV did.
    Vanilla animations do not yet round-trip through `hk2014` (0 of 79
    mole rat clips); `anim_fo4` writes them.
  - **Body:** `nvgecko.nif`'s two skinned shapes (caps left out) as
    BSSubIndexTriShapes on the gecko's own bones: pyffi's skin deformation
    gives the rest-pose vertices, each bone's bind is the inverse of its
    `skeleton.hkx` world pose (the FNV body's own bone nodes sit on it to
    0.0 units); 4,056 vertices on 75 bones plus the tongue. Materials and
    textures staged as the statics are.
  - **Records:** `FNVGeckoRace` (MoleratRace with the gecko's skin,
    skeleton, body parts, project, one subgraph entry `SGNM`
    FNVGeckoCoreBehavior / `SAPT` `Actors\FNVGecko\Animations`, and four
    attacks on the graph's melee events, normal weight 2.23 to power's 1
    for FNV's power share 0.31), body part data on gecko bones (no limb
    models, hit reactions only), skin and addon, `FNVGecko_Default_MT`
    (forward walk 62.5, run 578.6, the graph's `iState_FNVGecko`), an NPC
    (EncMolerat01Template on the race, SpeedMult FNV's 100), and 13 IDLEs.
  - **Actions reach a graph through IDLEs parented to the AACT record**
    (xEdit's `ANAM` parent is `[AACT, IDLE]`): the engine plays the IDLE
    under the action whose `DNAM` is the actor's graph. The cat answers
    each action itself (`ActionMoveStart` → `CatMoveStart` → `MoveStart`);
    the mole rat leans on `SharedCoreBehavior.hkx`'s IDLEs, which its core
    references. The gecko's IDLEs are the cat's kind: move start/stop, turn
    left/right/stop, draw, force equip, sheathe, death, death wait, instant
    ragdoll, initialize graph (instant too), unconditioned, each after its
    action's last vanilla IDLE.
  - **AnimTextData:** the file data (`3`, `1`, id, count, clip paths, LF)
    and dynamic idle data (`Version 1`) are text and written. The speed
    info and stance data are binary and Creation Kit made; installed
    custom-creature mods (Mojave Geckos, Cazadores, Bighorners) ship them
    for few or none of their entries.
  - **Cross-check, 22 of 22 pass** (`gecko_check.py`): every path, event,
    variable, bone and material one file names exists where it is
    defined.
  - **Creation Kit run (2026-10-26):** installed as MO2 mod `FNV Gecko
    Test` in the `Spike` profile and run as `ModOrganizer.exe -p Spike run
    -e "Creation Kit" -a "-GenerateAnimInfo:FNVGeckoTest.esp Data Data
    --speed --stance"` (usage string: `-GenerateAnimInfo:<ESMFilename>
    <DataFilepath> <OutputFilepath> [--speed] [--stance] [--forceAll]`),
    the profile's `[custom_overwrites]` sending new files to mod `FNV Gecko
    Test CK`. It generated data for both graphs in 9.6 s: AnimationFileData
    (rewritten in place in the test mod: the same 10 clips in another
    order), AnimationSpeedInfo (a `SpeedSampledAnimationSpeedContour` for
    `NonCombatLocomotionSM` and `CombatLocomotionSM`: 62.5 and 578.64,
    the clips' root speeds), AnimationStanceData, AnimationOffsets (also
    root id 1834888878 and `PersistantSubgraphInfoAndOffsetData.txt`),
    ClipGeneratorData and AnimEventInfo for both graphs, and a SyncAnimData
    file. Its log (`ckpe.log`):
    - "Invalid prev idle" on all 13 IDLEs: an IDLE directly under an
      action has previous 0 (all vanilla ones, e.g. 17 of 17 under
      ActionMoveStart; Mojave Geckos' too). Fixed; not rerun.
    - an assertion that speed info had already been written, after which
      it reported "Speed Info found" and wrote it.
    - MO2 redirects only new files: the CK still edited existing files in
      the game folder in place (`CreationKitPrefs.ini`, `ckpe.log`,
      `Logs\BNet`, `Logs\CKPE`, `Logs\Script`).
  - **Played 2026-10-26: frozen.** The gecko showed with the right body
    and skin, was hostile on the compass and died with sounds, but held
    its rest pose alive and dead (no ragdoll). Cause: its one subgraph
    entry carried target keyword `AnimFurnMoleratAmbushShort`. A race's
    subgraph entry is [`SAKD` actor keywords] `SGNM` [`SAPT`] [`STKD`
    target keywords] `SRAF` (xEdit; `SRAF` closes it), so a `STKD` right
    after an `SRAF` belongs to the next entry: MoleratRace's core entry has
    none, its ambush and furniture entries carry AnimFurnMoleratAmbushShort,
    AnimFurnMoleratSleep and so on (the Mojave Geckos mod's core likewise
    none). The copy paired it with the core entry, so the gecko only had a
    core graph in ambush furniture and its root's swap generator ran
    nothing. Fixed (no keyword); **replayed: no change.** Next difference:
    the Elric skeleton kept convert_static's BSXFlags 0x82 and no
    `BSBound`, where every vanilla creature skeleton has the Ragdoll (0x4)
    and Dynamic (0x40) bits (0xC6 on 28 of 33 actor skeletons, 0x46 on
    the robot, Codsworth's create-a-bot and turret; none on the human and
    power armor skeletons) and 30 of 33 a `BSBound` (the Mojave Geckos
    skeleton too: 0xC6 and a bound). Set to 0xC6 with FNV's bound (centre
    0, −11.2, 49.3; half sizes 40, 60, 50); **replayed: no change**, and
    the AI never tried to attack (sounds on hit and death only): the graph
    is not running at all. Next suspect: a `skeleton.nif` ragdoll with no
    ragdoll or skeleton mappers in `skeleton.hkx`, which nothing vanilla
    has (every NIF `bhkRagdollSystem` pairs with `hknpRagdollData` and two
    `hkaSkeletonMapper`s in the hkx; the robot, whose hkx has neither, has
    no ragdoll in `skeleton.nif` either, only the controller's
    `bhkPhysicsSystem`; Mojave Geckos pairs both). Test installed: a
    robot-shaped gecko `skeleton.nif` (bones, controller and bumper, no
    ragdoll, BSXFlags 0x46); **replayed: no change.** Next difference:
    no project file data. Besides the per-entry `<id>.txt` files, every
    vanilla actor project has `AnimationFileData\<project name>.txt` (218
    named files: `moleratproject.txt`, `cat.txt`, `deathclawproject.txt`;
    the Mojave Geckos mod ships `geckoproject.txt`): `3`, `0`, the project
    name, the count, its root behaviour, character, `CharacterAssets\
    skeleton.hkx` and the root graph's clips, `0`, CRLF lines. The Creation
    Kit's `-GenerateAnimInfo` (without `--forceAll`) did not write one.
    Written by hand as `fnvgeckoproject.txt` (the robot-shaped skeleton
    still installed, so this is the only change); **replayed: no change.**
    Swap test installed: the race on MoleratRace's own project, six
    subgraph entries and 20 attacks, our skeleton, body and NPC kept, to
    split our project, graph and clips from the records and skeleton.
    **Replayed: the gecko slid around and attacked, body unanimated** (the
    mole rat graph names mole rat bones). Records, `skeleton.nif`, body
    and AI are sound; the fault is in our project, character,
    `skeleton.hkx`, graphs or clips. Bisect 1 installed: our plugin back,
    our character's rig and ragdoll pointed at
    `..\Molerat\CharacterAssets\Skeleton.hkt` with the mole rat's
    39-entry mirror map (if the gecko then acts, our `skeleton.hkx` is the
    fault). **Replayed: still frozen**, so `skeleton.hkx` is not the only
    fault. Offline: the graphs' data bookkeeping matches vanilla's 147
    actor graphs (values, event infos and character properties pair; an
    empty bounds list in 40 of them; variableMode 0 in all), and the CK's
    ClipGeneratorData and AnimEventInfo for our graphs are sane. Build-up
    test 1 installed: our character back, the root graph cut to one
    looping Idle clip (no state machine, ragdoll or subgraph). **Replayed:
    the idle plays**, so project, character, `skeleton.hkx` and the clip
    format work in game. Build-up test 2 installed: the original root
    graph with the swap generator's `pDefaultGenerator` set to the Idle
    clip (vanilla leaves it null). **Replayed: frozen**, so the root graph
    itself never starts (not even its default idle). Build-up test 3
    installed: that root with its Fully Ragdoll state playing a plain clip
    instead of the modifier generator and powered-ragdoll modifier.
    **Replayed: frozen.** The root's nodes match the radroach root's field
    for field (start state, an instant blend and a looping clip aside), and
    the CK's `PersistantSubgraphInfoAndOffsetData.txt` (an index of offset
    files; vanilla ships none loose, each creature mod ships its own)
    lists our core's id. Lead: the graph waits for the swapped-in
    subgraph, so a core that never loads keeps the whole graph inactive.
    Build-up test 4 installed: that root, the core cut to one looping
    CombatIdle clip (combat idle pose: subgraph attaches; plain idle: root
    runs, no subgraph; frozen: the subgraph load fails whatever the core
    holds). **Replayed: frozen.** Own-folder cores are vanilla (the cat's
    `Actors\Cat\Behaviors\CatCoreBehavior.hkx`, the turrets', Liberty
    Prime's). Build-up test 5 installed: the root only the swap generator
    with the Idle default (no state machine), the one-clip core kept
    (frozen: the swap and subgraph load blocks; either idle: the state
    machine was the fault). **Replayed: frozen**: a root of only the
    swap generator blocks, a root of one clip plays, so the graph waits on
    a subgraph load that never completes, whatever the core holds.
    AnimTextData's 32-bit names are the raw CRC-32 (zero start, no final
    inversion) of a lower-case path: `AnimationOffsets` and
    `DynamicIdleData` of the project, `AnimEventInfo` (and
    `ClipGeneratorData`) of each graph. The mole rat has
    `DynamicIdleData\1693439668.txt` (its project) listing its dynamic
    idles; 32 of the 33 race projects have one (the cat's only `Version
    1`), the Mojave Geckos mod ships its own; the Creation Kit wrote none
    for us. Added `DynamicIdleData\1834888878.txt` (`Version 1`) as the
    only change. **Replayed: frozen.** Our project's AnimationOffsets
    (the root path only) is the cat's form (`V4`, the root, zeros), so
    not that either. Test 6 installed: our project with a swap-only root
    carrying the mole rat root's 421 events and 93 variables, the race's
    subgraph entries and attacks the mole rat's (acts: our subgraph entry,
    core or its data is the fault; frozen: our project or root side).
    **Replayed: the gecko moved and attacked** (mole rat clips on gecko
    bones): our project and root work; the fault is on our core side.
    A subgraph core's clips are found by name in the race's `SAPT` folder
    (the mole rat core names `..\Bloatfly\Animations\TurnLeft.hkt`, its
    file data loads `Actors\Molerat\Animations\TurnLeft.hkx`; the cat's
    own core uses our `Animations\X.hkt` form), so not the clip names.
    The working cat and mole rat cores have file data, speed info, stance
    data and dynamic idle data but no AnimationOffsets file (vanilla writes
    those for furniture and ambush entries); the CK gave our core one (693
    B, our attack clips) and listed it in its
    `PersistantSubgraphInfoAndOffsetData.txt`. Test 7 installed: test 5's
    setup with that offsets file and its index line removed. **Replayed:
    frozen** (restored). Test 8 installed: test 6's working setup (mole
    rat subgraph entries and vanilla data) with our one-clip core
    (playing the mole rat's IdleCombat, no variables or events) as a loose
    override of `Actors\Shared\Behaviors\MoleratSharedCoreWrappingBehavior.hkx`
    in the test mod: the vanilla entry and data with our graph file (a
    distorted held pose: our graph file attaches, so our entry or its data
    is the fault; gecko idle or frozen: our graph file is). **Replayed:
    body still, but the gecko turned on the spot** (the engine turning an
    actor whose graph runs; no fallback idle, so the core attached): our
    graph file works as a subgraph; the fault is our entry or its data.
    Lead: a subgraph's clips (its AnimationFileData list) load before it
    attaches, and only Idle.hkx had been shown to load. Test 9 installed:
    test 7's setup with our entry's file data listing only
    `CombatIdle.hkx`. **Replayed: frozen, not turning.** Test 10
    installed: the same with `Idle.hkx` (the one clip shown to load, in
    test 1) as the core's clip and the only one listed. **Replayed:
    frozen.** So the graphs and clips are not the fault; the difference
    left is how our entry's AnimTextData reaches the game. Every vanilla
    AnimTextData file is in a BA2, `animationfiledata\dirlist.txt`
    indexes the per-id ones, and all 35 installed mods that ship
    AnimTextData pack it in their BA2s (no loose file in any); ours was
    loose, which a game that lists archives and indexes but cannot list
    loose folders would never see. Test 11 installed: test 10's setup with
    all 14 gecko AnimTextData files packed into `FNVGeckoTest - Main.ba2`
    (Archive2, general, uncompressed) and no loose copies. **Replayed:
    frozen.** Overlooked difference: in tests 6 and 8, which attached a
    core, the root carried the mole rat root's 421 events and 93
    variables; every frozen root carried only ours. A vanilla root carries
    every name its possible subgraphs use (furniture, idle, dialogue
    included); every one of the 28 vanilla roots has the events
    `PickNewIdle`, `Ragdoll`, `SoundPlay`, `weapEquip`, `weaponDraw`,
    `weaponSheathe` and the variables `bAnimationDriven`, `camerafrom
    x/y/z` (ours lacked `PickNewIdle` and a plain `SoundPlay`). Test 12
    installed: test 11 with the swap-only root carrying the mole rat
    root's names plus ours (428 events, 97 variables). **Replayed: the
    first gecko placed turned (the graph ran), then the game crashed;
    after relaunching, every gecko froze.** Neither crash log
    (`OneDrive\Documents\My Games\Fallout4\F4SE\crash-2026-10-26-08-5*`)
    names the gecko: `Actor::AddFollower` from a patrol package on vanilla
    actors, then `ExtraDataList::SaveGame`, both in DLCNukaWorld's Tunnels
    cell and both reading `0x100000000` from a reference's extra data (a
    damaged reference in that save or cell). **Replayed from the main menu
    in `QASmoke` (no save): every gecko placed turns** — the graph runs on
    our own subgraph entry. So the root's names were the blocker (whether
    earlier tests in the damaged save were also affected is not
    separated). Test 13 installed: the real root (state machine, ragdoll
    state, swap with an Idle default) with the mole rat root's names
    appended after ours (428 events, 97 variables; our ids unchanged), the
    real core, the CK's 10-clip file data in the BA2, the robot-shaped
    skeleton kept. **Played 5 times (launch, `coc QASmoke`, place):
    frozen in runs 1, 3, 4 and 5; run 2 turned with a still body.** The
    outcome varies between launches of the same files (FO4 loads graphs
    and clips asynchronously), and when the graph does run, even the
    gecko's own idle does not animate the body: our subgraph clips do not
    arrive, while our root's clip did (test 1) and the mole rat's subgraph
    clips did (test 6). Every working creature (vanilla, the Mojave mods)
    ships all its actor files in BA2s; ours were loose but for the
    AnimTextData. Test 14 installed: test 13's files unchanged, the whole
    `Meshes\Actors\FNVGecko` folder (17 files) packed into
    `FNVGeckoTest - Main.ba2` with the AnimTextData (31 files), no loose
    copies. Since one launch no longer settles a test, each needs
    several. **Played 5 times: 2 turned with a still body, 3 froze.**
    Packaging is not it. Test 8 already showed the pattern: a clip played
    from any core graph we write stays silent (the mole rat's IdleCombat,
    which visibly moved the body under the mole rat's own core, did not),
    while our root graphs play (test 1). ClipGeneratorData is not it
    either: the Mojave Geckos core's lists only its single-play players
    (attacks, dynamic idles), as ours does. Test 15 installed: no subgraph
    swap at all; the root graph holds the whole creature (the core's
    noncombat and combat machines beside the ragdoll state) with the mole
    rat root's names after ours, the project file data listing the root,
    character, skeleton and all 10 clips, everything in the BA2. **Played
    3 times: the gecko's idle plays every time** (our graph and clips run
    in game), one run also turned, but none walked or attacked. Movement
    and attacks start from events the engine sends through the IDLE
    records (`moveStart`, `weapEquip`, the `melee…` events). Next: the
    console's `sae <event>` on a selected gecko, to split "the engine
    sends nothing" from "the graph does not react". **Result:**
    `weapEquip` switched to the combat idle; `moveStart`, `moveStop`,
    `meleeStart_Left` and `meleeStart_Power` were "not processed by the
    graph". The working one is a state's own transition; every ignored
    one is a state machine's wildcard transition. Cause: every vanilla
    wildcard transition carries `FLAG_IS_LOCAL_WILDCARD` (0x800; 842 alone,
    321 with `ALLOW_SELF_TRANSITION_BY_TRANSITION_FROM_ANY_STATE`, 0xA00),
    state transitions mostly 0 (2,210); our builder wrote 0 on wildcards,
    so Havok never matched them (the root's `Ragdoll` wildcards included:
    the gecko could never ragdoll). Fixed in the builder; test 15 rebuilt
    with every wildcard at 0x800 (robot-shaped skeleton still installed).
    **Replayed twice with the same files:** in one launch `moveStart` and
    `moveStop` worked but the attacks were "not processed"; in the next
    the gecko ran around and attacked on its own and every `sae` event
    worked. So the graph content is right, and what varies between
    launches is whether the actor finishes setting up. Lead: the race
    still carried the subgraph entry for our old core, and the engine
    loads a race's subgraphs when it sets up the actor, whether the root
    uses them or not; loading our core as a subgraph was the step that
    stalled at random in tests 5–14. (Vanilla attack wildcards mostly use
    0x600, global plus self, 20 of 31; move and turn ones 0x800; the
    launch that worked used 0x800 for the attacks too.) Test 16 installed:
    the race with no subgraph entry, nothing else changed. **Played 6
    launches: 4 idled without acting, 2 ran around without attacking, none
    fully worked.** Not the subgraph entry. Next lead: the AnimTextData was
    generated for the old layout (a small root plus a core subgraph); the
    root now holds every clip player and attack event, but its
    ClipGeneratorData and AnimEventInfo say it has none, and the speed
    info names the old core's machines. Every working creature ships data
    generated from its actual graphs. **CK rerun (2026-10-26)** on the
    current files (the 12 stale files set aside first, the hand-written
    project file data and project dynamic idle data kept): it wrote the
    root graph's ClipGeneratorData (577 B) and AnimEventInfo (201 B), the
    project's AnimationSpeedInfo and AnimationOffsets (`1834888878`), a
    new offsets index and sync data; no stance data (vanilla writes that
    per subgraph). Its log: "Could not find base MT/weapon graph for race
    'FNVGeckoRace'" (the race no longer has a subgraph entry). Packed into
    the BA2 (25 files), no loose copies. The CK again edited
    `CreationKitPrefs.ini`, `ckpe.log` and its log folders in the game
    folder in place. **Played 5 launches: 2 fully worked** (moved and
    attacked on their own), the rest partly or frozen. Test 17: the race
    given one base entry pointing at the root graph itself (`SGNM`
    `Actors\FNVGecko\Behaviors\FNVGeckoRootBehavior.hkx`, `SAPT` our
    animation folder, `SRAF` 1, the role vanilla creatures give their base
    entry); the root has no swap generator, so nothing runs it as a second
    graph. The CK's warning went, and it wrote that entry's file data,
    offsets, speed info and stance data (id `536022380439387835`); a
    per-entry `DynamicIdleData` (`Version 1`) added by hand as every
    vanilla core entry has. Packed (30 files). **Played 6 launches: all
    froze** (with the faults below still in the graph, so the entry is not
    to blame; it is kept from test 25 on).
    `animationfiledata\dirlist.txt` is a vanilla index of the per-id files
    that mods do not ship, so the game looks files up by name. Body NIF root
    flags 0xE are vanilla's commonest (1,113 bodies). Ruled out on the way:
    a skeleton-only `skeleton.hkx` under a character that names it as the
    ragdoll is vanilla (RobotCharacter does it). (An earlier note here said
    our clips and skeleton matched vanilla's layout; they did not, see
    below.)
  - <a id="own-rig-graph-contract"></a>**What the graph must do, tests
    18–23 (2026-10-26, each played; scripts in the session scratch):**
    wildcard versus state transitions made no difference (18). Vanilla's
    ragdoll state gets up by itself: `GetUpBegin` arms a 0.5 s
    `hkbTimerModifier` raising `GetUpStart`, the get-up clip raises
    `ReevaluateGraphState`, leaving raises `GetUpEnd` (19). `bEquipOk` is
    bound to the core state machine's `isActive` and `IsAttackReady`
    starts at 1 (20; a modifier binding that registers a variable first
    fixes its initial value, so register the contract first). Every one of
    328 vanilla graphs gives each clip generator a unique name (21). Every
    re-entered machine starts where the game says: the normal/combat
    machine syncs to `iCombatState` (`startStateMode` 1), both
    standing/moving machines bind `startStateId` to `iSyncIdleLocomotion`,
    both idle/turn machines to `iSyncTurnState` (22). Every attack state
    raises `attackStop` and `startAnimationDriven` on exit and holds
    `bAnimationDriven` while it plays (23): without `attackStop` the gecko
    bit once and never again. The `sae` handler (`0x5D8740` in 1.11.240)
    reports "not processed" only when the graph is inactive, busy, lacks
    the event name, or Havok handled nothing.
  - <a id="own-rig-clip-layout"></a>**The crash and most freezes were the
    clip writer (tests 24–28, 2026-10-26, played).** A Papyrus trace on the
    gecko (`GeckoTrace`, logging AI and graph state each second) showed a
    frozen gecko is in combat with its weapon drawn and its graph accepting
    events, but its AI never sets `Speed`; it still bites when the player
    comes close. Every gecko in one world load behaved the same, a vanilla
    mole rat in the same load moved, and leaving to the main menu crashed
    (`BSAnimationDBData` teardown, `hkThreadMemory` free of a bad block) even
    when the geckos worked. Bisect: the gecko on the mole rat's animation
    project never crashed (27); our clips and `skeleton.hkx` rewritten in
    vanilla's layout, values unchanged, never crashed in 8 runs and froze
    in 1 (28; it had frozen 2 in 5 to 6 in 6). PyNifly's FO4 writer
    (`external/pynifly_hkx/anim_fo4.py`) differed from vanilla in: the
    clip's `hkMemoryResourceContainer` (80 bytes, null name; vanilla 64
    bytes named `''`), an extra resource container in `skeleton.hkx`
    (vanilla skeletons have none), unpadded member strings and fixup
    tables, a 112-byte reference frame (vanilla 96), and `FF`-filled
    section names. Which of these the game choked on is not isolated; the
    writer now matches vanilla in all of them (fixed 2026-10-26; its output
    equals the played files byte for byte apart from fixup order), guarded
    by `tests/test_fo4_hkx_layout.py`. The same writer makes the build's
    idle clips (`fo4_import/spike/idles.py`) and human clips
    (`fo4_import/havok/human_clip.py`). Our behaviour, character and
    project writer reproduces vanilla's mole rat, radroach and shared
    graphs byte for byte. Still open: the occasional freeze left (closed
    below).
  - <a id="own-rig-movement-type"></a>**The freeze was our movement type's
    `SPED` layout (tests 29–40, 2026-10-26, played).** Fallout4.exe's MOVT
    loader (`0x620ce0`, `SPED` at `0x620e2b`) reads `SPED` by the record's
    form version: 104 (`0x68`) and newer is 28 floats (left, right,
    forward, back as `[0, walk, run, sprint]`, then 12 rotation rates);
    60–103 is the old 17-float layout, which it upgrades (each rotation
    rate written to two slots, forward sprint = run × 1.75 from
    `0x24D1A00`). Our MOVT copied `Molerat_Default_MT`'s 17 floats (form
    version 98) but was written at 131, so the forward slots got rotation
    rates (3.14, 4.71): a top speed of about 4 units/s, the stray `Speed`
    of 1.4–4.7 every frozen trace showed. Only 13 of Fallout4.esm's MOVTs
    are version 131; the race, NPC and body part data we clone already
    are. `fo4_import/spike/creature_speed.py` already documented the size
    rule. It looked random because our root graph also carried the mole
    rat's `iState_Molerat` (from the mole rat root's variable list):
    Fallout4.exe (`0x139c0f0`) maps each `iState_<name>` variable's initial
    value to the MOVT whose `MNAM` is `<name>`, so two links shared value 0
    and the one the game took varied per launch, fixed until quit to
    desktop. With only `iState_Molerat` the gecko moved in 10 of 10
    launches; with only ours, frozen in 8 of 8; ours rewritten in the new
    layout (forward 62.5 / 578.6 / 1012.6, the FNV clips' root speeds),
    moved in 8 of 8 (test 40). Rules: write `SPED` in the layout of the
    form version written, and give a creature graph only its own
    `iState_` variable. Ruled out on the way, each by a freeze: the
    subgraph entry, attack data, CK-generated AnimTextData, our clips and
    skeleton, IDLE and action lookup (`PlayIdleAction` worked while
    frozen), graph-driven movement. A Papyrus trace (`GeckoTrace`) and a
    read-only live reader (actor by FormID, objects by RTTI) showed the
    AI issuing combat path requests while the movement controller gave no
    speed. A vanilla-structure two-graph layout (root with the swap node,
    our creature as the core subgraph) still never attaches our core
    (test 34). Four clean launches were too few to trust: at a freeze
    rate near one in three that happens by chance about one time in five.
  - <a id="own-rig-ragdoll"></a>**Death, knockdown and get-up work (tests
    41–51, 2026-10-27, played).** What the working gecko has, each part
    shown needed by a test without it:
    - **The ragdoll only in `skeleton.nif`** (FNV's ragdoll through Elric),
      with a skeleton-only `skeleton.hkx`, as IceStormNG's tutorial
      creatures do. A ragdoll and two identity mappers built into
      `skeleton.hkx` beside it (vanilla's file layout; tests 42–48) left
      every plain death a corpse frozen in its last pose and floating:
      `pushactoraway` did not move it, and the live reader showed the
      model placed on the ragdoll's pelvis and posed by the animation.
      Only a death that came with a knockdown (power attack) ragdolled.
      Neither game units in that ragdoll (vanilla's `skeleton.hkx` holds
      its ragdoll in game units, the NIF in Havok units ×69.99) nor joint
      friction scaled from FNV's units (×7/69.99) changed it.
    - **Fully Ragdoll on a `hkbPoseMatchingGenerator`**, as all 29 vanilla
      organic creatures' graphs have (only turrets and the vertibird use a
      plain clip). Under a looping clip the body played the clip (test
      46); with the matcher it follows the ragdoll (47). One matcher is
      shared by Fully Ragdoll and GetUpFromRagdoll: `startMatchingEventId`
      `EnterFullyRagdoll`, `startPlayingEventId` `GetUpStart`, its child the
      Idle clip raising `ReevaluateGraphState` at 0.433 s (the radroach's
      `GetUp_Faceup`); matching bones in the mole rat's roles (pelvis,
      chest, right upper arm; its character properties
      `PelvisRagdollBone`, `SecondRagdollBone`, `ThirdRagdollBone`).
    - **The radroach's layout around it:** root state `RagdollAndGetUp`
      raising `GetUpEnd` on exit and holding Fully Ragdoll (enter
      `RemoveCharacterControllerFromWorld`, `AddRagdollToWorld`,
      `EnterFullyRagdoll`) and GetUpFromRagdoll. The engine re-evaluates the
      graph on `ReevaluateGraphState`, so a `GetUpEnd` raised later by a
      clip trigger never fires; then the actor never leaves its getting-up
      state, has no AI, and saves that way (test 44). IDLEs for
      `ActionKnockDown` → `Ragdoll` and `ActionGetUp` → `GetUpBegin`; with
      no IDLE the action is unsupported and nothing happens.
    - **A mole-rat death step.** Our race is the mole rat's, and the shared
      death-wait IDLEs exclude `MoleratRace`. `ActionDeathWait` →
      `DeathAnimation`, a root state that raises `AddRagdollToWorld`,
      keyframes all 25 ragdoll bones (`hkbKeyframeBonesModifier`), holds
      `bAnimationDriven` and `bSupportedDeathAnim` true
      (`BSIsActiveModifier`) and raises `Ragdoll` from a clip trigger;
      `ActionDeath` → `Ragdoll`. With `ActionDeathWait` → `Ragdoll` straight
      into Fully Ragdoll, the radroach's way, the body froze with no
      ragdoll (test 50). The gecko has no death clip, so the step holds
      CombatIdle: 0.3 s showed as a freeze before the ragdoll (49), 0.05 s
      does not (51).
    Not settled: whether the friction scaling is needed now that the NIF
    ragdoll is the one used, and the controller and bumper capsules (ours
    reach about 99 units high; the mole rat's are low and long).
  - <a id="own-rig-code"></a>**Converter code, stage 1 (2026-10-27): the
    Havok 2014 files.** `fo4_import/havok/packfile.py` reads a 64-bit
    hk_2014.1.0-r1 packfile into objects (`{'#', 'class', 'fields'}`;
    pointers as object names, a shape's relative-array data past its class
    size as `__tail__`); `packfile_write.py` writes them back; `graph.py`
    builds behaviour graphs on them (nodes from class defaults, events and
    variables by name). Behaviour, character and project files are laid out
    depth first from the top object; skeleton files are not, so a read
    skeleton is rewritten in its own order (`keep_order`), and animation
    and skeleton files carry a 16-byte header extension (`0x14`, then
    zeros). `tests/test_fo4_packfile.py` rebuilds six vanilla files byte
    for byte (mole rat and radroach roots, the mole rat's shared core,
    character, project and ragdoll skeleton). Class layouts come from
    `fo4_import/data/hk2014_layouts.json`: member names, types, offsets
    and sizes for the 279 classes the game's actor files use (131 named in
    them, plus parents and struct types), generated by
    `tools/generators/hk2014_layouts.py` from hkxpack-style class
    descriptions. hkxpack is MIT, but its class descriptions are read from
    the game and it does not ship them, so the repo keeps only the layout
    table, not the descriptions.
  - **Not done:** hit reactions, staggers, idles, the fire gecko's breath;
    the bone LOD and lag-bone extras on `skeleton.nif` (`BSBound` is now
    written: [modules](fo4_own_rig.md#modules)). Stage 2, the gecko through
    a per-creature table as mode `rig`, is wired since 2026-10-27
    ([parity](fo4_own_rig.md#parity)).

So a converter's own rig needs, from tools it lacks: nothing proprietary.
The skeleton, clips and behaviour, character and project files are writable
from Python; the ragdoll and controller come from FNV's own NIF ragdoll
through Elric; AnimTextData from the Creation Kit's command line or the CRC
rule. What is left is records and a play test.

## <a id="formids"></a>FormIDs: none counted

Every FormID in the spike plugin is a function of FNV's data, never of build
order, so building more of the map moves nothing already built:

- **An FNV record made into one FO4 record keeps FNV's object id**
  (`CellBuilder.fnv_id`): cells, references, bases, quests, packages,
  messages, imagespaces, navmeshes, LAND and LTEX, traits. This is how the
  Skyrim converter keeps Oblivion's ids. Every FalloutNV.esm id (465,016,
  ending at 0x17BA47) is reserved first (`reserve_source_ids`), which
  also puts the hashed window in the emptiest run after them,
  0x180000-0xF00000, the window the full pipeline will use.
- **A generated record is hashed** (`derive_formid`). Older sites keep
  their own site names (trees, load doors, sounds, consumables, equipment,
  creatures). The rest use `CellBuilder.new_id(owner)`: site `FNV made`,
  key the FNV data the record is made from (`DIAL <quest> <topic>`,
  `INFO <line>`, `SCEN <quest> <step>`, `GLOB <quest> <objective> <state>`),
  plus a count when one owner makes several (an FNV line said in two
  menus; a menu's five topics). Only those counts depend on build order,
  and only within their owner.

Switching cost one round of drift (2026-10-10, approved): 3,757 of the
plugin's 3,772 records moved, so saves from earlier builds don't carry
over; the other 15 are overrides of Fallout4.esm. Built, no FormID
duplicated, and every record on an FNV id carries that record's EditorID:
1,524 references, 253 statics, 138 leveled lists, 87 misc items, the 11
cells, 9 LAND, 5 quests, 8 packages and the rest. Hashed: 487 topics, 361
lines, 108 scenes, 357 generated references (seats, stand-in doors, SCOL
parts, QA test objects) and the equipment and consumables. A second build into a
fresh data folder wrote the plugin byte for byte the same.

## <a id="decision"></a>Decision point

After spikes 1–3: the architecture plan or a stop. Decided: go ahead, as
[fo4_pipeline.md](fo4_pipeline.md).

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
