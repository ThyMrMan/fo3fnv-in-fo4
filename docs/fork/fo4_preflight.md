# Preflight audits on the Fallout 4 build

**Code:** `tools/validate/preflight/` (`fo4_dialogue.py`, `asset_fo4.py`,
`condition_diff.py`, the FO4 parts of `__main__.py`, `plugin_index.py`,
`quest_progression.py`, `quest_start.py`, `package_ai.py`, `build_diff.py`);
tests in `tests/test_preflight_fo4.py`. Status goes in [ROADMAP.md](ROADMAP.md).

The preflight audits ([tools_preflight.md](../commentary/tools_preflight.md))
run on the Fallout 4 plugin after every build, with no game: quests that can
no longer progress or start, lines nobody can say, conditions that changed
meaning, packages and doors that point at nothing, models that load as red
markers, and records that moved or changed.

## Contents

- [Running it](#running)
- [Why the Skyrim audits missed the FO4 build](#why)
- [The FO4 dialogue model](#fo4-dialogue)
- [Assets](#assets)
- [The condition differential](#condition-diff)
- [First results](#results)
- [What it does not see](#limits)

## <a id="running"></a>Running it

```
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm"
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm" --audit quest --audit conditions
```

The source export is `export/<plugin stem>.esm` (`--fo4-source`), the
converted sources `temp/fo4_scripts/<source>` (`--fo4-scripts`), the compiled
scripts `<mod folder>/Scripts`. Audits: quest, start, dialogue, conditions, timing ([timing audit](fo4_timing_audit.md#built)),
packages, world, assets, build (68 s for all on the whole-map build). Script
health and log triage stay Skyrim-only: `fo4_audit` checks FO4 script
properties and `fo4_trace` reads FO4 play sessions. State and the report go to
`output/preflight/<plugin>/`; finding keys use the plugin name
(`quest|FalloutNV.esm|...`). Since the FO4 plugin took the name `FalloutNV.esm` (2026-10-30) it shares
the Skyrim build's folder name; run the two from their own checkouts.

## <a id="why"></a>Why the Skyrim audits missed the FO4 build

- The runner only found Skyrim-layout builds (`output/<plugin>/<plugin>`).
- The dialogue model was Skyrim's (branches, Choices). The FO4 build puts
  63,184 of its 63,685 topics in scenes.
- A Fallout 4 VMAD names a line's, package's, scene's, terminal's or quest's
  fragment script after its script list; the reader saw none of them, so every
  converted line looked unattached (542 false findings). Object-array
  properties (`Scene[] Steps` of `F3NV_RadioPlaylist`) were skipped too, which
  hid every radio step scene (191 false findings).
- Built records carry an `FNV_` EditorID prefix, and an FNV line becomes
  several FO4 lines (one per response, one per hub and menu), found through
  the FormID ledger.
- NPC templates read ACBS template flags at byte 14 (Skyrim 18) and the AI
  Packages template from TPTA's sixth entry.
- Skyrim-only rules are left out on FO4: the Fallout journal check,
  greeting replies and scene originals. The one-bark-per-quest rule runs on
  FO4 too since 2026-10-31 (vanilla Fallout4.esm keeps it; see
  [barks](fo4_pipeline.md#barks)).

## <a id="fo4-dialogue"></a>The FO4 dialogue model

A built line can play when its topic is reachable and a placed actor passes
its GetIsID tests. A topic is reachable when it is neither a scene nor a
custom topic (the engine plays greetings and hellos itself), when a reachable
scene's action names it (Dialogue, Player Dialogue, NPC Response, Start Scene
or Radio), or when a script property names it (Say). A scene is reachable
when it begins on quest start, when a voice holotape plays it (NOTE DNAM 1, its SNAM; since 2026-10-31,
before which every holotape line read "in no scene that starts"), when a script property names it (`TES4Talk_*`,
`Start()`, an array of steps), when a reachable line starts it (TSCE), or when
a reachable scene's Start Scene action names it.

An FNV line's built copies are the INFOs whose ledger key starts with
`INFO <FNV FormID> <response>`, plus the INFO at the FNV FormID itself when
the build kept it. A line whose first response is not built never plays, even
when later responses were written. When no copy exists, the reason comes from
the build's readiness report when it has one ("the build left it out
(condition: GetIsID: never true in this build)").

A quest the build does not hold is one `start|<plugin>|unbuilt|<quest>`
finding (an error when the source reaches its stages, else a review), not one
per stage. A script the build never attached is reported as such, not as a
compile failure, since the build compiles only attached scripts.

## <a id="assets"></a>Assets

Every model a player can meet (placed, carried, worn, rolled from leveled
lists, as the Skyrim audit collects them) must exist, and so must each
material (BGSM, BGEM) its NIF names, each texture its NIF names, and each
texture its materials name. Files resolve as the game finds them, through
`fo4_import.app.files.Files`: loose before archived, the plugin's mod folder
first, then the sibling mod folders that hold one of its masters, then
Fallout 4's Data. Block types are not checked: the FO4 NIF writer rebuilds
vanilla byte for byte. On the whole-map build it reads 6,049 models, 2,708
materials and 5,655 NIF texture paths in about 57 s.

## <a id="condition-diff"></a>The condition differential

The quest audit checks structure; it trusts that a converted condition means
what the FNV one meant. The differential checks that. Every first-response
copy of an FNV line is evaluated against the FNV line under the same sampled
states, and a state where they disagree is a review finding.

- **Vocabulary.** A condition is a fact (a function, whom it runs on, its
  parameters), a comparison and a value. Functions pair by xEdit's names
  (`GetPCIsSex` is `GetIsSex` on the player); forms pair by EditorID, by the
  ledger's renumbered placed references (`'ACHR <FormID> STH'`, only while the
  built FormID exists: the ledger keeps earlier builds' entries), or by the kept
  FormID. Mirror globals pair by their authored names: `TES4QVar_<quest>_<var>`
  with GetQuestVariable (variable names from the quest script's export) and
  with `GetVMQuestVariable`'s `::<var>_var`, `TES4ObjDone_`/`TES4ObjShown_`
  with the objective tests. Nothing goes through the converter's own tables,
  so a converter mistake cannot hide in a shared model.
- **What a line needs.** FNV says a line only while its quest runs and its
  quest's own conditions pass, so the FNV side holds both. The copy plays in
  its hub quest's scene, so that quest counts as running.
- **Fixed parts.** A form the build left out reads 0. The build's own state
  (`TES4Unlock_`, `TES4FollowUpFrom_`/`Said_` and Say Once marks) counts as
  true. Yes/no functions take 0 or 1, counts never go below 0, and identity
  functions (GetIsID, GetIsVoiceType and the like) take one value at a time.
- **Not judged** (counted): actor values, script variables by index,
  reputation, packages and regions; a Fallout 4 master form standing in for
  an FNV one; a line of a quest the build lacks that the source does not
  start at game load; a copy a holotape plays.
- **Sensitivity.** Mutations injected into 2,000 agreeing copies: a flipped
  comparison is caught 662 of 669 times, a dropped condition 638 of 659, a
  shifted value 656 of 669, an OR turned into AND 4 of 4. The misses are
  mutations that change nothing (a duplicate test, a bound already implied).

## <a id="results"></a>First results

Whole-map build of 2026-10-25 04:12 (541,179 records):

| Audit | Errors | Review | What they are |
|---|---|---|---|
| quest | 189 | 1 | Speakers the build leaves out (GetIsID never true, 209 setters), scripts attached to no record (88), lines with no built copy and no readiness entry (37, e.g. VDialogueVegasNorth's Crandon menu answers), unattached scripts the build never compiled (20), lines whose scene never starts (11) |
| start | 139 | 125 | 132 quests the build does not hold (errors when the source reaches their stages); the rest built quests whose starting setters are lost |
| dialogue | 465 | 0 | By speaker: Mr. House 357, Arcade Gannon 309, Caesar 261 left out by GetIsID; FNV combat and detection barks not converted; FNV HELLO and GOODBYE topics built as custom topics no script says, so they never play |
| conditions | 0 | 0 | 63,781 copies agree with their FNV lines. A first run listed 20 copies dropping a `GetDead` run on a placed reference; each reference was one the build leaves out (V03BryceAndersRef stands in Vault3a, not built), which the converter rightly reads as 0, and the audit had followed a stale ledger entry to it. The audit now follows a renumbered reference only when its built FormID exists |
| packages | 0 | 0 | 1,459 packages, 3,115 locations and targets checked |
| world | 0 | 2 | Two doors whose destination leads back to another door |
| assets | 8 | 0 | Materials naming `.bmp` and `.nif` files as textures; DLC04 and alien blaster textures missing |
| build | 0 | 0 | Baseline recorded; content hashes count changed records from the next build |

**Rerun on the whole-map build of 2026-10-31** (after `61a34613`):

| Audit | Errors | Review | Since 2026-10-25 |
|---|---|---|---|
| quest | 13 | 1 | 189 → 13. Left: stages set from scripts attached to no record (Mr. House's `NVCRMrHouseSCRIPT` for VDialogueMrHouse 20, VMQ02 15, VMQHouseFail 1; `Lucky38MainframeSCRIPT`; `Lucky38UpgradeSecuritronsSCRIPT`; `VMQHouseLockdownSCRIPT`), package OnEnd fragments never compiled (VCG00 14, VVault21Tour 20), `MenuMode` blocks kept as comments (CGTutorial 52, 212), and lines whose topic sits in a scene nothing starts (Benny in VMQTops 20, Poindexter in VFreeformCampGolf 30) |
| start | 170 | 87 | 87 quests the build does not hold; about 80 "required alias never fills", each a quest target alias forced onto a reference that starts disabled (VMQ01, VMS02, VMS04 and others). Not settled whether FO4 refuses that fill: no wiki says, and vanilla leans toward it filling (DN050's quest fragment enables its markers through required forced aliases on disabled references, no Allow Disabled). But vanilla sets Allow Disabled (FNAM 0x80) on 73 of its 89 required forced aliases on disabled references, so every forced alias we write now does too (`records._alias`, 2026-10-31): vanilla's practice, and safe either way |
| dialogue | 248 | 0 | 465 → 248 findings. By line: combat and detection barks never converted (1,595 and 1,079), topics in no scene that starts (850), conversation lines missing (693), radio lines no placed actor passes GetIsID for (461), reputation conditions (201) |
| timing | 0 | 88 | New audit since: mostly build writes unlocking a topic where FNV only offers it as a Choice of the line |
| packages | 0 | 3 | A waiter package needing a GetIsID no holder passes; two packages into cells with no navmesh |
| world | 0 | 2 | The same two doors |
| assets | 4 | 0 | `.bmp` and `.nif` named as textures; one DLC04 texture. None of the four is in FNV's data either (FNV's own meshes name them), so FNV could not draw them while FO4 shows them purple: a lit material now leaves out a diffuse or normal map FNV lacks (`convert_static.drawable`, 2026-10-31) |

**Second rerun, 2026-10-31 evening** (interiors a script reaches, player
topics only a script says, `IsActorTalkingThroughActivator` read as 0):
quest 13 → 5 errors (Mr. House's three stages, VMQYesMan01 80, VMQTops 20,
VMS01 20 and VVault21Tour 20 clear), dialogue 248 → 208. Left in quest:
CGTutorial 52 and 212 (the Pip-Boy MenuMode map, built, waits on the scripts
being converted again), VCG00 14 (a false positive: FNV's
`VCG00BennyTravelToPlayer` is named by nothing), Poindexter's line in a
Black Mountain scene nothing starts, the mainframe terminal's and
`VMQHouseLockdown`'s scripts unattached. The conditions audit's 41 new
reviews were its own sampling `IsActorTalkingThroughActivator` as 1; it now
reads that as 0 too (`condition_diff.FIXED_IN_BUILD`).

**Third rerun, 2026-10-31 night** (Allow Disabled on forced aliases, the
holotape fix, the texture drop, FO4 menu listeners for `MenuMode`):

| Audit | Errors | Review | Change |
|---|---|---|---|
| quest | 3 | 1 | 5 → 3: CGTutorial 52 and 212 clear. Left: VCG00 14 (false positive), Poindexter's Black Mountain scene, `Lucky38MainframeSCRIPT`; review `VMQHouseLockdownSCRIPT` |
| start | 4 | 85 | 170 → 4: every "required alias never fills" clears. Left: unbuilt CG00, CG02, ControlRumble, VT74 whose stages the source reaches; 85 unbuilt quests it never reaches |
| dialogue | 217 | 0 | 208 + 9: the Jacobstown holotape had copied 1,489 GREETING lines, and the audit counted those copies as built. Nine generic quests' greetings now show as missing; all nine quests are unbuilt (start reviews) |
| conditions | 0 | 0 | The 41 reviews clear |
| timing | 0 | 89 | Unchanged |
| packages | 0 | 5 | Unchanged |
| world | 0 | 2 | The same two doors |
| assets | 0 | 0 | 4 → 0 |
| build | 0 | 0 | 1,489 DIAL and INFO removed (the holotape copies), accepted as the new baseline |

**Fourth rerun, 2026-10-31 night** (the terminal's own script, quest
scripts that wait for their quest, [talking-as lists](fo4_pipeline.md#talking-activators)):
quest 3 → 2 errors and the review clears. `Lucky38MainframeSCRIPT` is now
attached (both control-terminal copies carry `Lucky38ControlTerminalSCRIPT`),
so vfreeformlucky38 20 is reachable. `VMQHouseLockdownSCRIPT` waits for a
quest nothing starts. Left: VCG00 14 (a false positive) and Poindexter's
Black Mountain scene. Dialogue goes 217 → 216. The build has 11 non-radio
talkers and 9 talking-as lists; the two lists of the control panel's two
actors (Yes Man, Mr. House) hold only the actor.

The intercom lines' `GetIsID OR IsInList` raised 760 condition reviews; the
audit's FNV side reads `IsActorTalkingThroughActivator` as 0, so it now reads a
built `IsInList` on a `TES4TalkingAs_` list as 0 too (both sides judge the
actor speaking in person), and conditions are back to 0.

"Its topic is never played" was 267 lost lines on the fourth rerun's build.
178 of them were the audit's own mistakes about FNV (fixed in
`quest_source.reachable_topics`, see
[dialogue loss](../commentary/tools_preflight.md#dialogue-loss)). It counted
every Conversation topic as playable; only HELLO and GOODBYE play by
themselves. Mr. House's `vDialogueMrHouse*Pissed` lines, which the Fallout
wiki calls unused, were among them. It also followed Choices past a Goodbye
line (Jason Bright's speech 5–9). Festus's and Jason's chains do play, through
their chat scenes' own topic copies. With the fix, 89 remain:

- 44 `PLAYERINIRONSITES`, an engine bark (FO4 has a Player In Iron Sights
  subtype). Barks are not converted yet: Combat and Detection topics lose
  thousands of lines.
- About 30 random NPC-to-NPC conversations: a HELLO line to another NPC whose
  Choice that NPC answers (Cass's Freeside replies, the Kings, Boone and Rex,
  Nellis's Jack): 26 lines. FO4 runs these as Story Manager Actor Dialogue
  (`ADIA`) quests, 297 in Fallout4.esm. Converted since: see
  [actor dialogue](fo4_pipeline.md#actor-dialogue).
- Dialogue packages aimed at an NPC (Captain Parker and Keith, Jerry's poetry,
  Jean-Baptiste and Cass). Converted since: see
  [packages](fo4_pipeline.md#packages).
- Patrol points: Mr. Janitor's lines come from a patrol script (106 FNV patrol
  points carry one, which FO4 patrol data cannot); the Strip escort's from a
  patrol topic (FO4's `PDTO`, written empty today).

The 37 `VEnding*` narrations were never counted (the audit does not reach
them), but no script said them: `NarratorScript` converts, and the `Endgame`
cell holding `NarratorRef` was not built. It is now (see
[interiors](fo4_pipeline.md#interiors)).

Two converter leaks showed up while checking the dialogue model: a line left
out of a quest still has its later responses and their scene written there
(0014D259 in vCrucifiedFaction and Greetings), and the readiness report has
no entry for some menu answers that were not built.

**Fifth rerun, 2026-10-31 10:51 PM build** (barks, actor dialogue quests,
NPC dialogue packages, the Endgame cell, Say Once prompts, the talker
greeting): quest 2 errors (unchanged: VCG00 14, Poindexter's scene),
dialogue 216 → 162, conditions 0. Lost lines 5,773 → 3,688; "never played"
89 → 27, and none of the 162 is new. In the build: 22 NPC dialogue packages
carry `F3NV_DialoguePackage` (Captain Parker, Jerry, Jean-Baptiste, the Strip
escorts); the `Endgame` cell and the `Narrator` actor with `NarratorScript`
are placed; none of the 59,171 prompt lines is Say Once.

What is left:
- 2,529 of the lost lines are in generic quests the build does not hold
  (31 quests' GREETING and HELLO sets: `vDialogueNCRCivilian` 331,
  `VDialogueBrotherhoodOfSteelFaction` 234, `vDialogueFreeside` 224,
  `vDialogueNCRMilitary`, `vDialogueCaesarsLegionMilitary`, …, plus the
  barks of `vDialogueNightkin` and the like). They choose speakers by
  faction, voice type or race, which [quest scope](fo4_pipeline.md#quest-scope)
  did not follow; the same gap as [barks](fo4_pipeline.md#barks-open). Quest
  scope follows them since 2026-11-01; 2,212 of these lines are in quests the
  next build includes.
- 461 radio lines no placed actor passes GetIsID for; 217 lines the build
  left out over a condition; 92 in scenes nothing starts.
- 27 never played. 14 were the audit's own mistakes, fixed since (dialogue
  162 → 153 on the same build): Meyers, Primm's Hayes and McGee and Rex
  come from packages FNV gives no one, and the Omertas' and Captain Curtis's
  from LinkFrom after a `SayTo`, which opens no conversation
  ([dialogue loss](../commentary/tools_preflight.md#dialogue-loss)). Left:
  Mr. Janitor's patrol script (7) and two Strip escort lines (patrol scripts,
  which FO4 patrol data cannot hold), the Novac nightkin chupacabra (3, its
  script-given Use Weapon packages, [converted since](fo4_pipeline.md#use-weapon)),
  and one Veronica HELLO, not traced.

## <a id="limits"></a>What it does not see

- Run-on: alias run-ons (chat scenes' Target tests) are not paired.
- Scene start conditions and phase conditions are not evaluated; a scene
  counts as playable once something starts it.
- Custom topics a script says by `Say` count as reachable whether or not the
  script runs.
- The asset audit reads the mod folder as it stands when it runs; a build or
  pack writing there at the same time changes its result.
