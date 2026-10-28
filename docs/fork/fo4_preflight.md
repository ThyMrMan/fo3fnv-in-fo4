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
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esp"
py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esp" --audit quest --audit conditions
```

The source export is `export/<plugin stem>.esm` (`--fo4-source`), the
converted sources `temp/fo4_scripts/<source>` (`--fo4-scripts`), the compiled
scripts `<mod folder>/Scripts`. Audits: quest, start, dialogue, conditions,
packages, world, assets, build (68 s for all on the whole-map build). Script
health and log triage stay Skyrim-only: `fo4_audit` checks FO4 script
properties and `fo4_trace` reads FO4 play sessions. State and the report go to
`output/preflight/<plugin>/`; finding keys use the plugin name
(`quest|FalloutNV.esp|...`), apart from the Skyrim build's `FalloutNV.esm`.

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
- Skyrim-only rules are left out on FO4: the Fallout journal check, the
  one-bark-per-quest rule, greeting replies and scene originals.

## <a id="fo4-dialogue"></a>The FO4 dialogue model

A built line can play when its topic is reachable and a placed actor passes
its GetIsID tests. A topic is reachable when it is neither a scene nor a
custom topic (the engine plays greetings and hellos itself), when a reachable
scene's action names it (Dialogue, Player Dialogue, NPC Response, Start Scene
or Radio), or when a script property names it (Say). A scene is reachable
when it begins on quest start, when a script property names it (`TES4Talk_*`,
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

Two converter leaks showed up while checking the dialogue model: a line left
out of a quest still has its later responses and their scene written there
(0014D259 in vCrucifiedFaction and Greetings), and the readiness report has
no entry for some menu answers that were not built.

## <a id="limits"></a>What it does not see

- Run-on: alias run-ons (chat scenes' Target tests) are not paired.
- Scene start conditions and phase conditions are not evaluated; a scene
  counts as playable once something starts it.
- Custom topics a script says by `Say` count as reachable whether or not the
  script runs.
- The asset audit reads the mod folder as it stands when it runs; a build or
  pack writing there at the same time changes its result.
