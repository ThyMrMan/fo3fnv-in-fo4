# Preflight audits on the Fallout 4 build

**Code:** `tools/validate/preflight/` (`fo4_dialogue.py`, `asset_fo4.py`,
`condition_diff.py`, the FO4 parts of `__main__.py`, `plugin_index.py`,
`quest_progression.py`, `quest_start.py`, `package_ai.py`, `build_diff.py`,
`asset_nif.py`, `build_history.py`, `quest_targets.py`, `built_masters.py`,
`dlc_overrides.py`); tests in `tests/test_preflight_fo4.py` and
`tests/test_preflight_fo4_builds.py`. Status goes in [ROADMAP.md](ROADMAP.md).

The preflight audits ([tools_preflight.md](../commentary/tools_preflight.md))
run on the Fallout 4 plugin after every build, with no game: quests that can
no longer progress or start, lines nobody can say, conditions that changed
meaning, packages and doors that point at nothing, models that load as red
markers, and records that moved or changed.

## Contents

- [Running it](#running)
- [Why the Skyrim audits missed the FO4 build](#why)
- [The FO4 dialogue model](#fo4-dialogue)
- [Assets](#assets) and [shader names](#materials)
- [The previous build](#previous-build)
- [Quest-stage and actor targets](#targets)
- [DLC overrides](#dlc-overrides)
- [Script properties](#script-properties)
- [The condition differential](#condition-diff)
- [First results](#results)
- [What it does not see](#limits)

## <a id="running"></a>Running it

```
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm"
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm" --audit quest --audit conditions
py -3.14 -m tools.validate.preflight --fo4 temp/profile_data_hh/HonestHearts.esm --audit targets --audit dlc
```

The source export is `export/<plugin stem>.esm` (`--fo4-source`), the
converted sources `temp/fo4_scripts/<source>` (`--fo4-scripts`), the compiled
scripts `<mod folder>/Scripts`. Audits: quest, start, dialogue, conditions, targets, timing ([timing audit](fo4_timing_audit.md#built)),
packages, world, assets, build, dlc, properties ([script properties](#script-properties)),
behavior (left-out AI packages by cause, actors with no package; [NPC behavior](fo4_plan_npc_behavior.md#phase-1)),
menus (menu structure and one option per FNV topic; [menu audit](fo4_menu_audit.md#built)) (68 s for all but the four added on 2026-11-02; assets now 41 s,
targets 26 s with build on the whole map; targets and dlc on a DLC build 10 to 18 s). A DLC build's
built masters come from its stamp's `--plugin-dirs` unless `--plugin-dirs` names them. Script
health and log triage stay Skyrim-only: FO4 script properties are the
`properties` audit (`fo4_audit.check_properties`) and `fo4_trace` reads FO4 play sessions. State and the report go to
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

### <a id="materials"></a>Shader names and every built NIF

`asset_nif.py` reads every NIF in the build's own folder (loose or archived)
block by block with the converter's reader (`fo4_import.nif.file.read_header`,
`blocks.read_texture_set`, `read_effect`), not only the models a record uses:

- A shader property's name (BSLightingShaderProperty, BSEffectShaderProperty)
  is empty or a `.bgsm`/`.bgem`; any other name is an error
  (`assets|<plugin>|shader-name|<name>`). FO4 reads the name as the material
  path, so a name like `BSX` draws purple while every file exists. That was the
  securitron face screens, Tesla armor, the advanced power armor glows and
  `NVGiantRat.nif` (`Lambcaps:2`): a string index -1 read as Python's last
  string (fixed in `outfit.text`).
- An effect shader never names a `.bgsm` (`effect-bgsm`); vanilla has 2,062
  skinned actor effect shaders and none names anything but a `.bgem`.
- Every material named this way, and every texture a texture set or an effect
  shader names, joins the material and texture checks above. The build's
  texture staging folder (`output/fo4_cache/ba2/<data folder>-<hash>/`,
  `ba2_pack.staging_root`) resolves like a Data folder, after the mod folder.
- A texture path's leading `Data\` goes, as the game drops it: FaceGen meshes
  name `Data\Textures\Actors\Character\FaceCustomization\...`.

Checked on the pre-fix meshes still in the work cache
(`output/fo4_cache/work/outfit_worn`, 13,524 worn NIFs of all code versions):
42 name an effect shader `BSX`, 1,386 `UpperBody8:1`, 204 `UpperBody2:0`. The
whole-map build has none.

## <a id="previous-build"></a>The previous build

The drift baseline moves only on `--accept-build`, and the FormID ledger is
cumulative, so a record the latest build stopped writing showed nowhere: the
ledger said "0 moved" while 1,282 pad INFOs and 17 SCEN were gone. The build
audit therefore also compares each Fallout 4 build with the one before it
(`build_history.py`). Per run it keeps the build it saw in
`output/preflight/<plugin>/build_seen.json` (the stamp, and per record its
signature, EditorID and a CRC of its subrecords: about 40 MB for the whole
map, no plugin copies) and the build before that in `build_seen_before.json`. A new
build (another stamp `ended`) is compared with the last one; a build already
seen, with the one before it, so running the audit twice changes nothing.

- Printed: records added and records whose bytes changed, per signature.
- Review findings: records gone (`build|<plugin>|previous-removed|<SIG>`),
  FormIDs now holding another type (`previous-retyped`) and EditorIDs that
  moved to another FormID (`previous-moved`), each with sample FormIDs.

It also prints the code-tagged caches the build's code invalidated: every
`cached`/`lookup`/`store`/`code_tag` call in `fo4_import` whose module
argument it can name (a string, `__name__`, `<module>.__name__`,
`<function>.__module__`; a variable means the repo modules the file names as
strings, as `face_fits.FIT_SITES` does), against `code_tag.tagged_files()` of
that module. The changed files are the stamp's `changed files` plus, when the
commit moved since the previous build, `git diff --name-only` between the two
commits and the previous stamp's own list. An edit to `convert_static.py`
shows as the mesh cache (`mesh_cache.py`) going, which made one build take 2 h
instead of 20 min.

## <a id="targets"></a>Quest-stage and actor targets

`--audit targets` (`quest_targets.py`). FO4Edit found 866 "Quest Stage not
found in FNV_TES4SayOnce" in a DLC build that no audit caught: Honest Hearts'
say-once lines tested stages its copy of the game quest had dropped.

- **Stages.** Every `GetStageDone` condition, every `GetStage == N` (N above
  0, which means "not started"; not against a global) and every `SetStage`,
  `GetStageDone` or `IsStageDone` call in an attached script whose quest is a
  property of the script (`Quest.SetStage(N)`, `X.TES4SetStage(Quest as T, N)`,
  `TES4Polyfill.SetStage(Quest, N)`) names a stage. The quest's stages (QUST
  INDX) are those of its last copy in load order: the build's own override
  wins over the built master's. A missing stage is an error
  (`targets|<plugin>|stage|<quest>|<stage>`), or a review when the source
  game's quest of that EditorID lacks it too. A quest FormID in the build's or
  a built master's id space that no QUST holds is an error (`quest`).
- **Actors.** A `GetIsID` naming an NPC_ the build places nowhere (no ACHR, no
  placed leveled list giving it at any depth, no script property) is an error
  when the source game places it (ACHR or ACRE), else a review (`actor`).
- **Masters.** A DLC build reads its built masters from the folders its stamp's
  `--plugin-dirs` names (or preflight's own `--plugin-dirs`), each kept only
  when its own masters lead the build's, so FormIDs read alike
  (`built_masters.py`). Fallout4.esm has no built plugin; its quests are not
  judged.

## <a id="dlc-overrides"></a>DLC overrides

`--audit dlc` (`dlc_overrides.py`) runs on a build with built masters and
flags what is its master's (each a finding with samples):

- `identical|<SIG>`: an override byte-identical to the master's record (flags
  without compression, then the data), as `master_overrides.master_records`
  reads it. One that heads a children group still holding a record (the game
  quest or topic a DLC line sits under) is kept as the master's copy and only
  counted. One the DLC's source overrides too is a review
  (`identical-authored`).
- `copied-lines`: an own INFO whose ledger key (`INFO <source FormID> ...`)
  names a master's source line that the DLC's source does not change
  (`say_topics.dlc_lines`).
- `voice`: a file under `Sound/Voice/<plugin>/` (loose or in the plugin's
  archives) whose object id is no INFO the plugin owns.
- `master-files`: copies of a master's own-rig files (a path under
  `Meshes/Actors/<rig>` the master's folder ships too, where that folder holds
  `CharacterAssets/skeleton.nif` and Fallout 4 ships no skeleton: `Character`
  is FO4's; a DLC's own mesh there, such as HH's green gecko, is not one) or
  files of a master worldspace's LOD
  (`LODSettings/<world>.lod`, `Meshes/Terrain/<world>/`,
  `Textures/Terrain/<world>/`).
- `shared|<other plugin>|<SIG>`: a master record this build and another
  finished DLC build beside it (a sibling profile or mod folder whose stamp
  says finished) both override. Overrides do not stack: the plugin loaded last
  wins, which is how every DLC but Honest Hearts (loaded last) lost its
  condition rows in play when all 8 overrode `FNV_Condition`,
  `FNV_AmmoSwitch`, `FNV_Challenges` and about 32 form lists. A review
  (`shared-authored`) when both DLCs' sources override the record, as FNV's
  DLCs do, and a review (`shared-identical`) when both copies are the
  master's own bytes: load order loses nothing there. Those are the game
  quests and topics FO4 needs as parents of a DLC's lines (HH and DM both carry
  FalloutNV's Greetings and TES4PatrolTopics QUST and 8 Greetings DIALs).
- Master records come from `master_overrides.master_records`, which walks
  every group: a filtered `walk(raw, b'DIAL')` skips topics nested in a
  quest's children group (type 10), and until 2026-11-02 that hid every
  master's nested DIAL, INFO and SCEN from it and from `drop_unchanged`.
- `stale`: a file under the folders a build lists (`stale_files.roots`) that
  no `*.files.txt` beside the plugin names and that predates the build's
  start. Newer unlisted files are a review (`unlisted`): the build made them
  but no later build prunes them.
- `unpaired-menus`: a master menu (a Player Dialogue action's PTOP and NPOT
  topics) given unequal numbers of the plugin's own INFOs. Options and answers
  pair by position, so every option after the extra ones answers wrong
  ([dlc-prompts](fo4_plugin_layout.md#dlc-prompts)). On the YUP build of
  2026-11-10 it flagged 124 menus (284 extra options), among them Vulpes's
  hub (54 options, 31 answers); Goodies 2, ExtraGoodies 0.

## <a id="script-properties"></a>Script properties

`--audit properties` (`script_props.py`, built 2026-11-04) reports each
converted script's object properties that a build leaves unfilled. There is
one finding per script property, with its records as samples. It runs
`fo4_audit.check_properties`, which until then ran only when someone called
`fo4_audit` by hand. A master no folder holds (XDI.esm, which the build only
names) is left unread, and its FormIDs count as defined.

- `timer` (error): the script's OnTimer pass names the property, so every
  pass that reaches it fails and writes a stack to the Papyrus log. In the
  user's 2026-11-04 log, Lonesome Road's `NVDLC04DivideSupport` (authored
  0.1 s delay) failed this way 4,266 times in 12 minutes on two `ActorBase`
  properties (see
  [DLC script bases](fo4_plugin_layout.md#dlc-script-bases)).
- `helper` (error): a form the converter itself names, a `TES4…` property or
  one on a build script (`F3NV_…`), such as `TES4ConfidenceFaction` or
  `F3NV_SurvivalNeed.Caffeine`. The build should always make these.
- `fnv-form` (review): an FNV form of that name exists in the export's
  master chain, but the build has no FO4 form for it.
- `no-fnv-form` (review): no FNV form has that name.
- `dangling` (error): a property filled with a FormID no file defines.

First run, on the deployed Lonesome Road (before the `ActorBase` fix):
403 unfilled on records, made of 170 `timer`, 24 `helper`, 140 `fnv-form`
and 9 `no-fnv-form` script properties. The base game: 2,660 on records,
made of 221 `timer`, 322 `helper`, 569 `fnv-form` and 124 `no-fnv-form`.
After the fixes below (build of 2026-11-04): 2,001 on records, made of 209
`timer`, 23 `helper`, 564 `fnv-form` and 124 `no-fnv-form`.

What the base game's `helper` findings turned out to be:

| Group | Count | Cause, and what was done |
|---|---|---|
| `TES4Swap_*` | 200 | `Swaps` mapped only the starting cell's references to models (`_object_makers`' `refs`), so SwapTexture worked only in Doc Mitchell's house. The ending slideshow's 198 swaps on `OnScreenSlideRef` (Endgame cell) had none. Fixed: every built reference. |
| `TES4PlayerEnemyFactions` | 19 | Never written for Fallout 4. `SetPCEnemyOfFaction` still worked (native `SetPlayerEnemy`), but `GetPCEnemyOfFaction` was always false. Fixed: written empty, as `TES4DestroyedRefs` is (`attach.RUNTIME_LISTS`). |
| Confidence and flee (`TES4ConfidenceFaction`, `TES4FleeMarginFaction`, `TES4FleeHealthScale`, `TES4ConfidenceFlee`) | 44 | Oblivion's emulation. An FO3/FNV actor's Confidence is the engine's tier, and `GetConfidence` reads it when the faction is None. Not a defect: added to `fo4_audit.OPTIONAL_PROPERTIES`. |
| `TES4FX_*` | 22 | Effect family keywords: no Fallout 4 MGEF carried one, so `HasMagicEffectWithKeyword` checks were skipped. Fixed for script effects: each copy `script_effects.ScriptEffects` writes carries `TES4FX_<effect>` (KSIZ and KWDA before DATA, as vanilla's 17 scripted MGEFs with keywords), and `attach` fills the property (`family_named`). That covers the 17 `TES4FX_disguisefactionpulseeffect`: the Legion ear sniffer, the Fort's praetorians and Kimball's guards now see a faction disguise pulse. The 5 `TES4FX_flamermagiceffect` (gas traps igniting) stay open: the built flamer wears Fallout 4's `FlamerFXEnchFireHit`, and no gun carries its FNV object effect yet. |
| `TES4AV_*` | 14 | No Fallout 4 actor value. Fatigue (11, written as Skyrim's `Stamina`) is now a helper actor value with FNV's knockout ([fatigue](fo4_pipeline.md#fatigue)). `NightEye` (Cateye, Dead Money's Ghost Sight) is now Night Person's night vision, and `MeleeDamage` (two lines upgrading Rex) is a dropped write, as is any actor value Fallout 4 lacks ([night eye](fo4_pipeline.md#night-eye)). |
| `TES4Scene_*` | 10 | Speak-as scenes (Vault 11's chamber, the monorail, Curtis's radio). Open. |
| `TES4ForceFlees` | 7 | The force-flee package pool. Open. |
| `F3NV_*` scripts | 5 | None by design, so `fo4_audit.OPTIONAL_SCRIPT_PROPERTIES` skips them. `FalloutLock.Password` is set only on locks a password note opens (the 87 are Easy locks without one), and `SurvivalNeed.Caffeine` only on the sleep need (the 30 are hunger and thirst effects). `PipboyTab.Shown` None shows every row. `ScriptPackages.Hub` is None on the game's own quest, which is the hub. `VoidActor.VoidRace` is None on the void actor itself. |

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
- **Fixed parts.** A form the build left out reads 0, and so does an
  objective test of an index its FNV quest does not author (it reads 0 in
  FNV; 9 lines testing VFreeformCampGolf 50, VMS41 11 or VMS29a 42 read as
  "the build says it where FNV cannot" before). The build's own state
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
| start | 170 | 87 | 87 quests the build does not hold; about 80 "required alias never fills", each a quest target alias forced onto a reference that starts disabled (VMQ01, VMS02, VMS04 and others). Not settled at this rerun whether FO4 refuses that fill (the third rerun below clears these; play had already settled it: [timing audit](fo4_timing_audit.md#measured), VCG02 on 2026-10-29): no wiki says, and vanilla leans toward it filling (DN050's quest fragment enables its markers through required forced aliases on disabled references, no Allow Disabled). But vanilla sets Allow Disabled (FNAM 0x80) on 73 of its 89 required forced aliases on disabled references, so every forced alias we write now does too (`records._alias`, 2026-10-31): vanilla's practice, and safe either way |
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
  subtype). Barks were not converted yet: Combat and Detection topics lost
  thousands of lines. Converted since: see the fifth rerun below.
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

### <a id="results-2026-11-02"></a>The four audits added on 2026-11-02

Game build of 2026-11-02 17:40, Honest Hearts of 18:00, Dead Money of the same
evening:

- **Assets** (game 41 s): no shader name is wrong in any built NIF of the
  game, HH, DM or the seven other profile folders. 7 textures the build's
  meshes or materials name were never converted, though FNV has them: the
  Lucky 38 and Ultra-Luxe light meshes' `...wl.dds`, `metalbasepanel_imposter`,
  and generated glow maps (`lucky38sign_m`, `windowquad_g_cut128`,
  `..._lod_g_cut70`). No record places those meshes. DM: the heated spear's
  generated glow `nvdlc01_knifespear_..._g.dds` is missing, and
  `effects\fwspark.dds` is missing from FNV's Dead Money too.
- **Previous build**: saved game builds 1102d → 2026-11-02 17:40: 738,236 →
  738,780 records, 544 SCEN added, 9,797 changed (6,863 INFO, 2,415 DIAL, 517
  SCEN, 2 NPC_), none gone; between the saved 1102d, e, f and g the same 544 and
  9,795, then nothing, then 2 NPC_. None of the saved builds holds the 1,282
  pad INFOs that went, so the gone report is checked by its test only. Ten code-tagged caches were invalidated by the
  uncommitted code (convert_static, outfit, shader_anim and export_index edits):
  the mesh cache, gun clips, headgear, outfits, rigs, object and terrain LOD,
  face fits and head parts.
- **Targets**: game 6 reviews (stages FNV's quests lack too: VMQ01 110,
  Doctors 10, VMS29a 1, VMS44 37; GetIsID of VFSFollowersGuard and
  VStreetTopsPromoter02, which FNV places nowhere). HH: the 14 `NVDLC02MQ04
  30` tests (a review, FNV's quest lacks it). DM: 9 reviews, all stages FNV's
  Dead Money quests lack. No errors: the say-once quest gap is fixed in these
  builds.
- **DLC**: HH writes 33,357 REFR, 969 ACHR, 69 NAVM and 2 PHZD overrides
  byte-identical to the game plugin's, while HH's source overrides only 94
  REFR and 3 ACHR of FNV's (DM: 30,352 REFR, 938 ACHR, 63 NAVM, 2 PHZD, plus
  14 REFR its source authors). 13 HH voice files under
  `Sound/Voice/HonestHearts.esm/FNV_RobotUniqueRex` belong to no HH INFO:
  left in the staging folder by a 14:02 build and packed again; so are 3
  WastelandNV object LOD textures in HH's texture archive. No copied lines.
  Shared with the other finished DLC builds: HH and DM both override 28,834
  REFR, 943 ACHR, 42 CELL, 21 FLST and the game's Condition, TES4SayOnce,
  TES4PatrolTopics and Greetings quests; HH and GRA 24 FLST, Condition,
  AmmoSwitch and NVChallengeKaboomPowWeapons; every pack 2 to 5 FLST and
  Condition. One PERK both HH's and DM's sources override is a review. 1,115 HH files (987 DM) the build made
  are on no file list: these builds ran before `stale_files.DLC_ROOTS` was
  added, so the next build lists them.

### <a id="results-2026-11-07"></a>Rerun on 2026-11-07

Game build of 2026-11-07 08:14 (commit 09d64d37), every audit; Honest Hearts
with `dlc` and `targets`. Changes since the runs above:

- **Fixed:** HH's 33k byte-identical REFR/ACHR/NAVM overrides are gone (HH
  `dlc` 0 errors, 11 reviews: DIAL and PERK records HH and DM both override).
  Dialogue errors fell from 153 to 70; script properties from 2,001 unfilled
  (2026-11-04) to 138 errors and 583 reviews. Targets: 0 errors (game 5
  reviews, HH 1).
- **Still open:** quest 1 error (VCG00 stage 14, its fragment on no record);
  start 3 errors (CG02, ControlRumble, VT74 not built) and 86 reviews; the
  same 7 missing textures; dialogue's top losses are the radio quests
  (RadioNewVegas 216, RadioBlackMountain 186), VDialogueTEST 64,
  vNCREmergencyRadio 33, Cass 31, GenericPlayer 27 and, new, VMS38RedLucy 20.
  Properties left are mostly timer and swap ones (`CRBrahminScript`'s push
  idle on 9 brahmin, `EDEScript.rLogBlocker`, `TES4FX_*` keywords,
  `EuclidsCFinderSCRIPT`'s `TES4Swap_*`). Conditions 23 reviews, packages 6,
  world 2.
- **Timing, 5 new errors, false:** the cattle prod, Zap ISM and three boxing
  `FatigueOnHit` scripts are FNV weapon scripts whose `Begin OnHit` is
  converted to an effect's `OnEffectStart` ([weapon hits](fo4_pipeline.md#weapon-hits)).
  The audit now reads that mapping (`block_state`): timing 0 errors.
- **Dialogue, 70 → 57 errors after audit fixes** (same build):
  - *Audit, fixed:* 461 radio lines named their station's talking
    activator, which the audit did not count as a speaker; 64 VDialogueTEST
    lines and Red Lucy's 20 bet answers [never pass in FNV](../commentary/tools_preflight.md#dialogue-loss).
  - *Converter, fixed, not yet built:* Cato Hostilius 18 ([talk order](fo4_pipeline.md#talk-order)),
    Big Sal 10 ([furniture scripts](fo4_pipeline.md#furniture-scripts)).
  - *Known, no FO4 state or not built:* companion status barks
    (WeaponIneffective, WeaponBroke, UsedDoctorBag, …: Cass, Raul, Lily,
    Boone, Arcade, Veronica), GenericPlayer's 27 barks, the casino
    (`GetCasinoWinningStage`), GetItemCount (the Weathers family), GetIsRace
    (Lily), GetDisposition (GenericKids), GetIsClass.
  - *Audit, not real:* Vault108DialogueShell's 23 (a faction no FNV actor
    joins); VES08CampGolf's 13 (its speakers stand in `2EOCasHiHotelLobby01`,
    which no door reaches; the audit counts every placed actor).
  - *Second pass, 63 → 59:* the audit now follows each radio station's own
    topics and plays speech challenge outcomes only after a challenged topic
    ([dialogue loss](../commentary/tools_preflight.md#dialogue-loss)); Black
    Mountain fell from 14 lost lines to 3, which have no recording. Six
    speakers show as new only because talking activators are now named by
    EditorID (Hanlon's and Lily's recordings, the Vault 11 chamber, three Tops
    radios). Vault 11's 4 lines and the Curtis and monorail recordings are a
    converter fix, not yet built ([talker says](fo4_pipeline.md#talker-says)).
    The three Tops radios' 8 lines (one quest holding three stage acts) are
    a converter fix, not yet built ([stage acts](fo4_radio.md#stage-acts)),
    started by the converted `StartRadioConversation`
    ([programs a script starts](fo4_radio.md#start-radio-conversation)).
  - *Silent in FNV, still counted:* the Strip and Goodsprings radios'
    RadioHello songs are placeholder tracks FNV never shipped
    (`temp_bluemoon_strip.mp3`, `_nv_temp_billy_the_kid.mp3`), and Repcon's
    RepconMusic line has neither recording nor sound. The audit can't tell,
    because the export does not write a response's sound (TRDT).
  - *Not looked at:* about 25 single lines (Mr. House, Benny, the Khan
    messenger, JeannieMay, YesMan 068).
- **Previous build** (against 2026-11-04 09:09): 738,898 → 657,099 records.
  83,370 INFO, 91 DIAL and 19 SCEN gone are the
  [menu speakers](fo4_pipeline.md#menu-speakers) change; 8 STAT gone are the
  thrown-weapon stand-ins. No FormID moved. The first run reported 60 DIAL and
  16 SCEN as moved: scene EditorIDs end in a counter (`Greetings_Scene3734`),
  so removing scenes renumbers the names after them, and the check matched by
  EditorID. It now counts a move only onto a FormID the earlier build lacked
  ([build diff](../commentary/tools_preflight.md#build-diff)), and those 76 are
  among the removed. This build is accepted as the baseline (`--accept-build`).

### <a id="results-2026-11-08"></a>Rerun on 2026-11-08

Game build 1108a (the casino build), `quest` and `start` only. Quest: 1
error, VCG00 14. Start: 3 errors and 86 reviews, as on 2026-11-07. All four
errors are reviewed and marked ok in the ledger:

- **VCG00 14:** the false positive above (`VCG00BennyTravelToPlayer` is
  named by nothing).
- **CG02:** Fallout 3's birthday quest, left in FalloutNV.esm with its cake
  trigger and radroach scripts.
- **ControlRumble:** a controller-rumble helper; its script sets only its
  own stage 0.
- **VT74:** "Exploring Vault 74", the GECK tutorial vault. Its cell
  `Vault74a` holds 197 references and both triggers, but no door leads in.

Poindexter's scene, open in earlier runs, no longer appears.

## <a id="limits"></a>What it does not see

- Run-on: alias run-ons (chat scenes' Target tests) are not paired.
- Scene start conditions and phase conditions are not evaluated; a scene
  counts as playable once something starts it.
- Custom topics a script says by `Say` count as reachable whether or not the
  script runs.
- The asset audit reads the mod folder as it stands when it runs; a build or
  pack writing there at the same time changes its result.
- Targets: a stage call through a local variable, `GetOwningQuest()` or a
  property the VMAD does not fill is not read, and Fallout4.esm's quests are
  not judged. A missing texture is an error even when no record places the
  mesh naming it.
- DLC: a master's file the DLC ships at the same path outside an own-rig or
  LOD folder is not flagged.
