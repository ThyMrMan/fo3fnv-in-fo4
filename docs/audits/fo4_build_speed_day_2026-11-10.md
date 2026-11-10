# FO4 build speed work and mod queue rerun, 2026-11-10

One day's work on [fo4_build_speed.md](../fork/fo4_build_speed.md), the rerun
of the [overnight queue](fo4_overnight_build_2026-11-10.md), and the defects
the rerun exposed. Every number was measured that day. **Nothing here has been
played in game, and nothing is committed.**

## Contents

- [Summary](#summary)
- [Build times](#times)
- [The queue, overnight against the rerun](#queue)
- [What was changed](#changed)
- [Defects found and fixed](#fixed)
- [Found, not fixed](#open)
- [What is deployed](#deployed)
- [What to test in game](#test)
- [Work left](#left)

## <a id="summary"></a>Summary

- The game's whole-map build went from 135 min (overnight, cold caches) to
  32 min with the day's caches warm.
- All five overnight crashes are gone and all 14 mods build. Every reference
  check passes, including the three that failed overnight.
- The rerun exposed four defects that are not about speed, all of the same
  family: a build with masters looking only at its own records, or leaving a
  master's numbering unconverted. All four are fixed and confirmed in builds.
- Script compile on an unchanged mod rebuild fell from 159 s to 3 s.
- An unchanged mod rebuild still takes about 11 min. The weapons stage is the
  largest part and its cause is traced but not fixed.

## <a id="times"></a>Build times

Game, whole map (`WastelandNV reached`), into `temp/profile_data`:

| Stage | Overnight (cold) | Rerun |
|---|---|---|
| Total | 8,119 s | 1,772 s |
| People | 5,827 s | 314 s |
| Collision | 653 s | 286 s |
| Weapons | 495 s | 108 s |
| Armor | 166 s | 83 s |
| Script compile | — | 120 s |
| Source faults | — | 0 |

The rerun's people stage fitted 1,662 faces; the rest had been refitted by
two region builds earlier in the day, so 314 s is not a fully cold figure for
the new face code.

Mods (build step only, seconds; overnight in minutes from its audit):

| Mod | Overnight | Rerun, first build | Later rebuild |
|---|---|---|---|
| YUP - Base Game + All DLC | failed (17 min) | 2,856 s | 1,372 s, 1,362 s |
| AguaFria | failed (8 min) | 840 s | 724 s, 661 s |
| TLD_Travelers | failed (36 min) | 1,026 s | |
| NVWillow | failed (8 min) | 753 s | |
| Landscape Disposition Fix | 8 min | 479 s | |
| Better Brotherhood | 15 min | 370 s | |
| Strip Lights Region Fix | 14 min | 473 s | |
| Sunshine On My Shoulders | 19 min | 253 s | |
| Placement Fixes | 39 min | 846 s | |
| DLC Enhancements | 32 min | 699 s | |
| Goodies | 41 min | 1,136 s | |
| ExtraGoodies | 36 min | 938 s | |
| NVMIM | stopped | 686 s | |

First builds paid one-time costs: gun clips and outfits rerun under the new
cache keys, a full script recompile after the game's scripts changed, and for
YUP a first voice conversion. They are not the steady figure.

AguaFria's last rebuild, nothing changed (661 s): weapons 200 s, people 76 s,
collision 52 s, mesh cache check 46 s, ledger and cleanup 46 s, armor 40 s,
script conversion 10 s, script compile 3 s.

## <a id="queue"></a>The queue, overnight against the rerun

| Step | Overnight | Rerun |
|---|---|---|
| Game reference check | clean | clean (after the helper plugin was regenerated) |
| NVTUP + NVMIM overlay | crashed: Havok motion system 205 | built; that mesh is a counted source fault (18 faults) |
| NVWillow | crashed: missing bobblehead mesh | built, check clean, 32 source faults |
| YUP | crashed: pre-order pistol mesh | built, check clean, 0 faults |
| AguaFria | crashed: pre-order armor mesh | built, check clean, 0 faults |
| TLD_Travelers | crashed: collision node matching no node | built, check clean, 1 fault |
| DLC Enhancements | 6 unresolved quest properties | check clean |
| ExtraGoodies | 3 unresolved quest properties | check clean |
| Other seven mods | built | built, check clean (NVMIM: 2 faults) |
| NVWillow faces | never ran | ran, wrote 0 face meshes and 0 textures |

Not rechecked: Better Brotherhood's `BBSelfDestructQuestScript`, which failed
to compile overnight.

## <a id="changed"></a>What was changed

Plan steps, in the plan's order:

| Plan step | State | What it is |
|---|---|---|
| 1. Bad source files counted, not fatal | built, confirmed in builds | `SourceFault` (`fo4_import/base/source_fault.py`), 12 catch sites; faults listed at the end of the build and in the stamp. Asset lookup now follows the master chain, which is what fixed YUP and AguaFria (their pre-order meshes are in ClassicPack). |
| 2. Face fits a/b/c | built, confirmed in builds | QR brow solve, per-process memos, a mesh cache fix, the 256 tint target, `FIT_VERSION`, a worker pool sized by `npcs.face_workers`. Both visible changes kept by decision: the 256 target, and sculpt controls with no effect left at 0. |
| 3. Cache keys | built, confirmed in builds | Versioned work-cache sites for gun clips and worn outfits, keyed without FormIDs; honesty tests (`tests/fo4_versions.py`). Old entries pruned: 338,206 files, 48 GB freed. |
| 4. Publish face fits | not started | Open question: publish as a release asset. |
| 5. Fixed costs | partly done | Script compile done (below). Mesh cache check, collision, `ledger and cleanup` untouched. |
| 6. Read-recording spike | recorder built, not run on a build | `fo4_import.pipeline.read_log`, `tools/audit/read_log_report`. |
| 7. Journal | waits on 6 | |

Script compile (plan section 4), all in `tools/script/compile_papyrus.py`,
`fo4_import/base/caprica.py`, `script_convert/pipeline.py` and
`script_convert/context_setup.py`:

- A script source whose content did not change is no longer rewritten. The
  game build had rewritten 17,440 files for 59 real changes, and the first
  read of freshly written files cost about 65 s.
- A plugin's own source wins over a master's same-named script in both
  compilers.
- A script Caprica rejects with a real source error is recorded as failing
  and not sent to Bethesda's compiler. The fallback stays for a Caprica crash,
  timeout, or a construct only Caprica rejects.
- Scripts are split across parallel Caprica folders (YUP: 194 s of relaunches
  became 64 s in scratch).
- The header-hash record is shared per set of header folders, not kept per
  mod.

Measured in builds: AguaFria's compile stage 159 s → 3 s unchanged; Goodies
compiled 220 scripts in 8 s; ExtraGoodies with nothing to compile 5 s.

Smaller changes: `say_topics.borrowed_lines` iterates a set in sorted order
(the plugin was not byte-reproducible run to run); the face section of
`fo4_pipeline.md` was updated to the new face code.

## <a id="fixed"></a>Defects found and fixed

1. **A head with no `.egt` crashed the face fit.** Willow's race ships no
   face color file. Such a head now gets no color offset
   (`fo4_import/face/texture.py`).
2. **Stale helper plugin.** `FalloutHelpers.esl` in MO2 dated from November 7
   and lacked the `DialogueDone` actor value the greet-once packages use, so
   every check reported unresolved package conditions (458 in the game). The
   game build had been run without the app's helper step. Regenerated and
   copied; no code change.
3. **Mod builds gave almost every choices menu a `[Leave]`.** A build with
   masters judged "can this conversation end" on its own lines only, so
   nothing ended and every menu counted as never-ending. YUP: 682 menus, each
   with a silent exit line written once per voice type, 88,660 files. The
   rule now also sees the masters' lines (`conversation.py`, `say_topics.py`,
   `cell.py`). Confirmed in YUP's rebuild: 0 such menus, 0 silent files, the
   plugin 2,577 records smaller. The game build is unchanged (4,549 menus,
   same answer before and after).
4. **Script properties on copied master records kept the master's own
   numbering.** A mod with several DLC masters writes back a DLC quest whose
   properties still use load byte `04`. YUP: 89 stale properties, 72 pointing
   at nothing and 17 bound to an unrelated Dead Money record; DLC
   Enhancements 6; ExtraGoodies 3. Script blocks are now renumbered
   (`master_plugin.py`, walker in `dangling_scripts.py`). Confirmed: all three
   checks clean.
5. **The script converter merged masters' records without restating their
   ids.** Every DLC numbers its own records `01` in its export, so DLCs
   overwrote each other and a mod's override sat beside the master's copy.
   YUP lost 65,376 record types, and overrides of master scripts converted
   with generic types. Fixed in `script_convert/cross_ref.py` with a helper
   in `core/plugin_masters.py`. Game and DLC output unchanged (0 of 1,405
   Dead Money scripts differ).
6. **Bethesda's compiler shipped the master's script under the mod's name.**
   With the masters' folders first on its search list, a mod's override of a
   master script compiled the master's file. 5 of AguaFria's 11 shipped
   scripts and 87 of YUP's were the master's code. This hid defect 5. After
   both fixes: AguaFria 11 of 11 compile from its own source, YUP 3,654 of
   3,665.

## <a id="open"></a>Found, not fixed

- **"Collision node 'NNNNN.nif' matches no node of the mesh".** At least 23
  of Willow's 32 source faults, plus the overlay's, TLD's and NVMIM's. A node
  named like a numbered temporary file suggests the converter, not the mods'
  meshes. Those meshes ship without collision. Not investigated.
- **Willow's faces step writes nothing.** Exits cleanly with 0 face meshes.
  Cause unknown.
- **1,074 of YUP's scripts lack helper calls their master's copy has**
  (`TES4QVar_*`, `TES4Add_*`, `TES4_TakeMsgButton`). The per-run plans in
  `script_convert/pipeline.py` `build_script_context` read only the plugin's
  own records. They compile; the effect in game is unchecked.
- **Other record parts copied without renumbering** that hold a value
  matching a DLC's own record id, in YUP's four moved DLCs: navmesh data
  1,210 subrecords, package locations 226, package targets 177, weapon mod
  templates 75, object mod data 57, placed-reference package data 25, placed
  grenade base 25, note sound or scene 11, NPC mod templates 6, region sound
  1. A raw value match, so some are coincidence. Whether any ships wrong is
  unchecked.
- **YUP's 11 scripts that fail to compile**: four fatigue-on-critical scripts
  (cannot cast to actor), three with unresolved names (`d15F316`, `d10F57E`),
  and one each for `GetParentCell`, `TES4_AnimPlaying`, `bAutodocScars`, and a
  string passed as a reference. TLD has two more (`GetPCMovedCell`,
  `GetMapMarkerRep`).
- **`F3NV_Array.psc` still goes to Bethesda's compiler.** Bethesda's accepts
  only `None` as a `Var` default and Caprica accepts none. The fix is to drop
  the defaults and pass all 20 arguments from `nvse_falloutnv._array_call`.
- **The no-rewrite change does nothing when only one plugin has ever been
  converted**: an unshared source folder is still wiped whole.
- **One slow compile unexplained**: a build in the queue (believed DLC
  Enhancements) compiled 23 scripts in 120 s with one source error.
- **Stale converted scripts**: 29 files in `temp/fo4_scripts/DeadMoney.esm`
  differ from a fresh conversion.
- **74,697 old silent voice files** from earlier game builds sit in the voice
  cache; not packed, only disk space.
- **Tests failing before the day's work**:
  `test_fo4_items_audit::test_an_armor_fnv_gives_no_world_model...`,
  `test_fo4_faces_audit::test_an_unused_voice_file_waits...`,
  `test_script_converter::test_fallout3_islimbgone_negative_argument_and_or_chain`,
  and two in `test_plugin_path_resolution.py`.
- **Not re-proven**: that a build under the read recorder is byte-identical
  to one without, after the `sorted` fix.

## <a id="deployed"></a>What is deployed

All in `C:/Modlists/fo3fnv-in-fo4/mods`, each with a `finished` stamp. Which
are enabled in the MO2 profile was not checked.

| What | Built |
|---|---|
| `FalloutNV.esm` and archives | Nov 10, 11:10 |
| `FalloutHelpers.esl` | Nov 10, 13:09 |
| NVTUP + NVMIM overlay | Nov 10, 11:29 |
| The 13 queued mods | Nov 10, 13:02–16:23 |
| Old World Blues | Nov 10, 00:28 (overnight) |
| Dead Money, Honest Hearts, Lonesome Road, Gun Runners Arsenal, the four pre-order packs | Nov 9, 01:39–02:19 |
| Weapons of the New Millenia | Nov 9, 21:52 |

- The DLCs were built against the previous game build. The new game build
  added 242 records and moved no existing FormID.
- The game was built before the afternoon's fixes; none of them changes a
  build without masters.
- Mods built before a fix landed were rebuilt only where the fix applied: YUP
  and AguaFria. TLD_Travelers, Better Brotherhood, NVWillow and the mods
  built before 14:00 were checked for stale script properties (0) but not for
  scripts compiled from a master's copy.

## <a id="test"></a>What to test in game

- **Faces (game):** the 256 tint target, and sculpt controls with no effect
  left at 0.
- **Greet-once packages (game):** the helper plugin now has `DialogueDone`.
- **Conversations in YUP:** menus that had a wrong `[Leave]` now lock the
  player in as New Vegas does; about 670 `[Leave]` and exit lines are gone.
  Real never-ending menus (Victor's loop) must still offer `[Leave]`.
- **DLC quests under YUP, DLC Enhancements, ExtraGoodies:** Old World Blues
  and Honest Hearts quest scripts now point at the right records.
- **Scripts YUP and AguaFria override:** these now run the mod's own version
  for the first time.
- **Willow:** her face (no color offset, and no exported face data at all).
- **Collision** on the meshes listed as source faults.

## <a id="left"></a>Work left

Speed, largest first:

1. **Mod builds re-make their masters' weapons.** AguaFria overrides 42
   weapons and adds none, yet makes 376 (149 guns with clips) and discards
   255 as the same as the master's. The clip cache hits; replaying a cached
   gun still costs 0.6–1.35 s (about 96 clip files read back and compared,
   about 8 mesh reads and writes). Skipping master guns the mod does not
   override: an estimated 200 s → 50 s on AguaFria. Armor (40 s) looks the
   same and is untraced. This is the plan's section 5.
2. **Remaining fixed costs** on an unchanged mod rebuild: people 76 s,
   collision 52 s, mesh cache check 46 s, ledger and cleanup 46 s.
3. **Silent voice lines.** Each is still written once per converted voice
   type. Untested whether the files are needed at all now that
   `fDialoguePaddedAudioLengthMin` is 0.2; one play-test with them removed
   settles it. Otherwise write them only for the voices that can say the line.
4. **Voice size.** The game's 159,013 `.fuz` files are 5.7 GB under 112,614
   distinct names; whether the repeats are the same recording is unchecked.
5. **A converted-voice cache shared across output folders**, for fresh
   folders and second profiles.
6. **Run the read recorder on a whole-game build** and report for Landscape
   Disposition Fix, Goodies and Better Brotherhood (plan step 6), then the
   journal (step 7).
7. **Publish face fits** (plan step 4).
8. **Redo the plan's Order table** from these numbers.

Correctness, from [Found, not fixed](#open): the collision-node faults,
Willow's faces, the 1,074 scripts missing helper calls, the other unrenumbered
record parts (navmesh and packages first), and the 13 scripts that do not
compile.

Housekeeping: rebuild the DLCs against the new game build; decide whether to
rebuild the mods built before 14:00; about 8 GB of region output and the
day's logs sit in the session scratchpad.
