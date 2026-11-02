# FO4 converter audit before the whole-map build

An audit of `fo4_import` and the FO4 script target on 2026-10-15, before
the converter runs over all of FalloutNV.esm. It looks for what will be
slow, wrong or silently missing at whole-game scale. Status of any fix
goes in [ROADMAP.md](ROADMAP.md), not here.

**How it was checked.**
- The region build (`--region -21 -16 -10 4 GSDocMitchellHouse`) was run
  under cProfile into a scratch copy of the mod folder. Its plugin is
  byte-identical to the 11:02 build the user played, so the build is
  reproducible and the profile is of the shipped code (uncommitted changes
  included).
- Five reviewers read the code by area; every finding below was re-checked
  by a run, a count or the exact lines.
- Marks: **V** verified by a run or count this session; **R** verified by
  reading the lines; **M** a model or estimate, not a measurement.

Scale used for estimates: region against whole game is 20,908 against
~308k references, 1,630 against 7,428 distinct models, 165 against 2,247
distinct faces, 1,260 against 17,549 scripts, 2,788 against 52,896 voice
recordings.

## <a id="order"></a>Suggested order

1. **Today's play-test, uncommitted changes:** watch the Goodbye and other
   repeated options ([#6](#fix-first)). S2 and S3 (the new quest poll
   delay) and #11 (form lists) touch nothing in today's build (checked
   against its quests and lists), so they can wait for the fixes below.
2. **The save contract, before the whole-game build becomes the baseline:**
   a FormID ledger and authored keys for F2–F5 ([FormIDs](#formids)).
3. **Wrong at whole-map scale and invisible in the region:** water (#1),
   other worldspaces (#2), exterior door pairs (#3), talk-scene case (#4),
   shared material and spec-map paths (M1), unbuilt run-on references
   (#5), the stale mirror (S1).
4. **Hours on the first build:** face fits in a process pool with the
   shared half precomputed (M4), `skin_tone_layers` cached, voice
   converted once per recording, the CK FaceGen timeout and face texture
   size, `elric.finish` memory (M2).
5. **Minutes on every rebuild:** narrow the cache tags, prune the caches
   and `_ba2`, copy each texture once, repack only on change.
6. **Before Fallout 3 or a DLC:** #8 and S6.
7. **Test leftovers out of the shipped build:** QASmoke, the test chest,
   stand-in doors ([drops](#drops)).

## Contents

- [Suggested order](#order)
- [Fix before the whole-map build](#fix-first)
- [FormIDs that move as content grows](#formids)
- [Speed: the first whole-game build](#first-build)
- [Speed: every rebuild](#rebuild)
- [Silent drops and spike leftovers](#drops)
- [Meshes and assets](#meshes)
- [Scripts](#scripts)
- [Checked and fine](#fine)

## <a id="fix-first"></a>Fix before the whole-map build

| # | Finding | Where | Evidence | Fix direction |
|---|---|---|---|---|
| 1 | **Water height is the Commonwealth's everywhere.** The world copies Fallout4.esm's DNAM (default water 450) and every cell writes XCLW = FLT_MAX ("use the default"). FNV's WastelandNV default is −2300 and 412 cells set their own 2600 | `exterior.py:40` (`WORLD_COPIED`), `exterior.py:244` | V: 134 cells dry in FNV fall under 450 and flood; 346 cells with FNV water above 450 (Lake Mead, the Colorado) drop to 450. The region has 0 flooded, 2 losing water, so no play-test could show it | Write FNV's DNAM default heights and each cell's own XCLW |
| 2 | **One worldspace per build.** Doors into other worldspaces become plain doors with no teleport and no count; interior doors into them get QASmoke stand-ins | `run.py:56,74`, `cell.py:673-690`, `interiors.py` | V: 37 WastelandNV doors lead to other worldspaces (GreenhouseWorld01 22, WastelandNVmini 11, FreesideNorthWorld 2, BoulderCityWorld 1, TheFortWorld 1); 109 of 388 interiors (44,498 references) are never reached; TheStripWorldNew, Lucky38World and the Freeside worlds are not built | Build every worldspace in one pass; a door whose partner is unbuilt is handled and counted the same way on both sides |
| 3 | **Exterior-to-exterior doors lose their teleport.** `_linked(outside doors, ids)` passes the interior ids only | `cell.py:690` | V: 14 doors (7 pairs) in WastelandNV: the Hoover Dam ladders, FortMainCampGate, VHDLegateCampGate, vCCFortGate and NVCCBarge. All at grid x 16–24, outside the region | Pass `{**ids, **ext_ids}` |
| 4 | **Talk scenes spelled with other case are never written.** `ObjectScripts.talk` reserves a scene per exact property name; the greeting step is placed once, so the other spellings' scene ids have no record and `talk()` still reports them built | `attach.py:147-151`, `conversation.py:137-138` | V: 9 converted scripts use `TES4Talk_Greeting`/`TES4Talk_greeting` against 27 using `TES4Talk_GREETING`. None is in today's build (fo4_audit: 0 dangling properties) | Key `talks` by the lower-case topic |
| 5 | **A condition run on an unbuilt reference keeps FNV's raw FormID**, which then names whatever Fallout4.esm form has that id | `conditions.py:150-157` (`form_map.get(ref, ref)`) | R; the actors reviewer's toy wrote run-on 0x0010A3F2. 353 INFO and 98 PACK conditions run on placed references | Treat an unmapped run-on reference as absent (as `absent()` does for p1) and count it |
| 6 | **Duplicate menu options from today's change.** `_option` now makes one option per (prompt, quest), where it made one per prompt | `conversation.py:229-234` (uncommitted) | V: today's plugin repeats 32 prompts within one menu topic, 51 extra options; "Goodbye." appears 7 times in two menus. Each copy carries its quest's shared conditions, so two show together only where two quests pass for one speaker: watch the Goodbye menus in today's play-test | One option per prompt, each answer gated by its quest; or keep the split and put the quest in the FormID key (see [FormIDs](#formids)) |
| 7 | **Linked references resolve through one side's ids.** `_placed` looks up XLKR in the interior or exterior ids only, never actors or the other side | `cell.py:441` | V: 2 in today's plugin (two dismemberment heads linked to Primm's dead sheriff and his wife); more at whole-map scale. `placement()` already uses `builder.ref_ids` | Resolve XLKR through `builder.ref_ids` |
| 8 | **FO3 and DLC builds read FalloutNV.esm's binary fields.** `install.fnv_esm()` is a fixed path, read by ~14 modules (placement, scol, factions, weathers, voice types, imods, emittance, locations, lighting template, activators, equipment, consumables, fnv_npc, the FormID reservation) | `base/install.py:8-14` | R. For Fallout3.esm, FO3 FormIDs would be looked up in FalloutNV.esm and pick up another record's fields | Read the binary of the plugin being converted (from the export header), not a constant |
| 9 | **Vendors ignore their template's AI data.** Services come from the base's own AIDT | `vendors.py:74-76` (new file) | R; 7 vendor bases take AI data from a template (vGOMBartenderRandom, the VSpawnSpecialMerchant* bases), have Services 0 and become general stores | Read services through `Npcs.source(fnv, USE_AI_DATA)` |
| 10 | **GetScriptVariable converts on quests and ACHR only** | `say_topics.py:140-157` | R; on ACRE 63 INFO and 33 PACK conditions, on REFR 17 INFO and 45 PACK, all left out (counted) | Index creature and reference bases' SCRI too |
| 11 | **Script FormList properties now bind to item-only lists.** Non-item entries are dropped without a count, and the readiness report no longer shows them unfilled | `items.py:180-185` via `attach.py:105` (uncommitted) | V: NVRatList 9 → 0 entries (VRexRatSonarBaseEffectScript), DLC03TeslaExplosionList 12 → 0, TrapGasCloudList 20 → 5; 120 of 464 FLSTs hold non-items | Take the item route only when every entry is an item; else convert the other types or leave unbound and counted |

## <a id="formids"></a>FormIDs that move as content grows

The whole-game build becomes the save baseline, so these matter most.
"Growing the area moves nothing" held so far because collisions and
counted keys were rare at region size.

| # | What moves | Where | Evidence |
|---|---|---|---|
| F1 | **Hash collisions go to whichever key asks first.** `derive_formid` rehashes a key whose slot is taken, so an existing record moves when a new key, allocated earlier, lands on its slot | `tes5_import/base/writer.py:885-933` | V: simulated with the real writer and window (0x180000–0xF00000, FNV's 465,016 ids reserved). Today's plugin holds 11,302 hashed records (DIAL 3,889, INFO 3,310, GLOB 1,028, SCEN 850 …). Adding 10× as many keys moved 34 of them in random order, 70 with the new keys first |
| F2 | **Copies of a line take counted ids.** `new_id(f'INFO {FNV id} {part}')` appends a count per copy | `say_topics.py:109`, `cell.py:217-224` | V (actors reviewer): 1,996 INFO copies of 1,126 FNV lines; 460 lines copied 2–19 times. A menu or quest built earlier renumbers the copies |
| F3 | **Split menu options take counted ids** (`INFO prompt {dial} {text}` has no quest in it) | `conversation.py:254-256` | R; follows from #6 above |
| F4 | **Objective alias ids are numbered among built targets only** | `quest.py:41-56` | R; 7 quests have 12 aliases that renumber once an earlier unbuilt target enters scope |
| F5 | **Say Once marker stages "move up one" on a collision** | `say_once.py` | M: the greeting quest holds 1,750 Say Once lines at whole-game scale; CRC32 mod 55,000 gives ~28 collisions, and which line moves depends on registration order |

**Fix direction.** Make the id a function of authored data only (put the
quest and step in F2/F3's keys, the target's authored index in F4's). For
F1 and F5 no hash scheme is order-free once collisions happen; a persisted
ledger is: write `{(site, key): id}` beside the plugin on each build, load
it first next build, and hash only keys it lacks. That also makes every
rule change (a renamed key) visible as a ledger miss instead of silent
drift.

## <a id="first-build"></a>Speed: the first whole-game build

Costs paid once, then cached. Rates measured on this machine (16 logical
CPUs, 31 GB).

| Stage | Measured rate | Whole game | Notes |
|---|---|---|---|
| Face fits (`npcs._face`) | V: tint fit 4.9–8.6 s, sculpt 0.2–0.5 s per face, one at a time in the main process | 2,247 distinct fit keys among 3,814 NPCs: **~4–5 h**, again after any edit to the 50 files of their cache tag | Run the fits in a process pool before the build, as `mesh_cache.warm` does for meshes, and share the NPC-independent half ([M4](#meshes)) |
| Voice (`voice.convert`) | V: ~6 files/s over 16 threads (timestamps of 4 earlier builds) | 52,896 recordings: **~2.5 h** | M (actors reviewer's model of the step graph): ~210k INFO copies and ~193k .fuz conversions for 33k recordings. Convert each (recording, transcript) once and copy the file to other copies. Today 155 of 2,788 .fuz are byte-identical copies |
| CK FaceGen export (`facegen.run_ck`) | V: 165 faces written in 127 s (0.77 s each) | ~1,100 faces fill the 900 s `CK_TIMEOUT`; the run then **fails** with "did not finish" while the CK keeps going | Raise the timeout with the face count, or export in batches |
| Papyrus compile (`compile_into`) | V: 1,260 scripts in ~115 s (15 batches), full compile | 17,549 scripts: **~25–30 min** | Incremental after that; the saved state is dropped whenever the output folder's path changes (the stage folder and import string carry it) |
| Elric | V: 60 meshes in 4.0 s, 0.07 s each | 7,428 models: ~9 min | Fine |
| Mesh conversion | 389 meshes in 26 s on all cores (pipeline doc) | 7,428: ~8 min | Fine, but see the cache key below |

**FaceGen textures.** V: the CK writes each face as three 2048×2048 DXT5
textures with one mip, 4 MB each (12 MB per NPC). Vanilla's 4,644 face
textures are 1024×1024 BC1 with full mips for `_d`/`_msn` and 512×512 BC5
for `_s` (about 1.7 MB per NPC). 2,247 faces would put ~27 GB raw into the
texture BA2 against ~3.8 GB at vanilla's sizes, and without mips they shimmer
and use full-size VRAM at any distance. Downscale and add mips in
`facegen.collect`, or find the CK setting that sizes them.

## <a id="rebuild"></a>Speed: every rebuild

From the profile (cProfile, so shares rather than seconds; 445 s total, of
which 123 s was the full script compile the scratch folder forced).

| Cost | Region | Whole game (×4.6 models, ×13.6 faces) | Fix direction |
|---|---|---|---|
| `facegen.skin_tone_layers()` re-reads Fallout4.esm (300+ MB) for every face (`npcs._tint_edit`, `npcs.py:348`) | V: 165 calls, 15.1 s | ~3.5 min | `functools.cache`, or read `builder.fo4` |
| `write_assets` per mesh: the source NIF read for the cache key, unpickle, `nif_file.write` per vertex, OBND per vertex, texture copies, `spec_image` DDS decode before the work-cache lookup | V: 61 s over 2,028 calls | ~4.7 min | Cache the finished bytes and bounds per mesh key and skip the write when the file is current |
| Texture copies (`write_converted`) | V: 8,667 `copyfile` calls for at most 2,864 distinct textures (each texture copied once per mesh using it) | grows with models | Copy each texture once per build, and skip it when the staged copy is current |
| `pack_textures` repacks all of `_ba2` with Archive2 | V: 37 s for 3,637 files (558 of them FaceGen) | several minutes, more with faces | Repack only when a staged file changed; faces in their own archive |
| `elric_cache.finish` reading every NIF back to key it | V: 21 s | ~1.6 min | Key on the mesh-cache key instead of the written bytes |
| `npcs._face` with every fit cached | V: 27 s for 165 (mostly the item above) | ~6 min, ~2 min after the cache fix | |
| Export parse (62 files) | V: 31 s | the same | Fine |
| `_rooms` rescans all interior references per interior | V (world reviewer): 4.0 s at 278 × 98,064 | 4 s | Group by cell once (`interiors.by_cell`) |
| Land texture blending (`land_layers`), uncached | V (world reviewer): 8 ms per cell | ~130 s for WastelandNV | Fine |
| Hub option scans (`_option`, `_members` rescan every Hub line per option) | M (actors reviewer): ~1.1 billion ParentDIAL compares | ~92 s | Index the Hub lines by topic |

**Cache keys too broad.** V: `code_tag('fo4_import.nif.convert_static')`
covers 59 files, among them `version.py`, `core/gui/config.py`, the
Morrowind exporter and the LOD decimator. The chains:
`spec_mask → parallax → game_paths → plugin_masters → output_layout →
source_registry → version → core.gui.config`, and
`addons → export_index → text_reader → equivalents →
tes4_export.record_types.morrowind`. The face fits (50 files), outfits (67)
and headgear (65) carry the same modules. So a version bump or a merge
from `standalone` touching those files re-converts every mesh and refits
every face: hours at whole-game scale. Cut the chains (a function-level
import, or a narrower module) or let `code_tag` skip named modules.

*Two more cut (2026-11-01).* Whole builds swung from 1,835 s to 3,250 s
with nothing changed in the stages. Some of it was real: 7,633 new
dialogue lines (35 more quests in scope) took the voice stage to 2,069 s,
once. But the gun clips' key covered 475 files because `gun_clips` took
one constant, `FIRST_PERSON_ARMS`, from `gun_anim_falloutnv`, which pulls
in the Skyrim creature pipeline and with it `script_convert`. So every
script-conversion edit re-recorded every gun (`item WEAP` 29 s → 478 s).
The constant now lives in `gun_vocabulary_falloutnv`: 78 files. Far-LOD
reductions were keyed on `spike.object_lod` (550 files, the record
writers and dialogue among them), so a dialogue fix redid every
reduction. They are now keyed on the reducer's module `lod_far_gen`
(28 files). Outfits are keyed on `nif.outfit` by design: an edit there
re-fits every outfit (`item ARMO` 574 s). Check a key's reach with
`code_tag.tagged_files(module)`.

**Caches are never pruned.** V: `output/fo4_cache/meshes` is 6.5 GB in
45,869 entries, about 28 copies of the region's 1,630 meshes; at whole-game
scale one generation is ~1 GB. Prune entries not read by the last build.

**File opens.** V: a first read of a small file costs 2–3 ms here, a
repeat 0.04 ms; the build opens ~53k files. Windows Defender real-time
protection is on (its exclusions need admin to read). Whether to exclude
the build folders is the user's call.

## <a id="drops"></a>Silent drops and spike leftovers

| Finding | Where | Evidence |
|---|---|---|
| Placed bases of types without a converter are all counted as `skipped other` | `cell.py:246-247, 367-375, 433` | V (world reviewer), whole world 692 references: AudioMarker 469, PWAT 89 (Hoover Dam and sewer water), ASPC 44, Lockpick 36 (FNV 0xA, whose FO4 0xA is another form), TACT 26 (radios, intercoms), FormID 0x17 26, TXST decals 2 |
| Idle markers left out | `idle_markers.py` | V (world reviewer): 531 of 1,000 placed (VHDPreBattleEngineerIdleMarker 110, DefaultRobotIdleMarker 53 …) |
| Placed creatures with no stand-in vanish uncounted | `npcs.py:208-221, 309-319`, `creatures.py:99-102` | V (actors reviewer): 374 of 2,999 ACRE in 21 skeleton folders (nightstalker 74, spinebreaker 47, Mister Gutsy 44, raven 43, giant ant 23) |
| 98 of 389 armors keep the FO4 template's models, counted only as `ARMO` | `equipment.py:272-275` | V (items reviewer): 78 on ClothesMobsterhat (CassHat, ChineseStealthHelmet, HatRaul …), 17 on ClothesPrewarShortSleeves (OutfitRaul, ArmorNVBoone01), 3 on SurgicalMask. 47 are skinned headgear, which no path takes; 31 have no world model; 17 cover other slots. The drift doc covers FO4 outfit models, not uncounted headgear |
| Headgear loses FNV's alternate textures | `equipment.py:277-288` (`_headgear` never calls `_swap`) | V (items reviewer): HeadWrap02/03/04 render alike; HelmetNVNCRTrooperMP, ArmorBoomerWeldingHelmet, ArmorRaider02Helmet lose their variant |
| Spike leftovers in every build: the QASmoke override, `FNV_TestChest` (every table weapon and armor, 100 rounds each), stand-in doors from X −1700 | `cell.py:401-408, 684-689, 783-789` | R. Put them behind a test flag before the whole-game build |
| Unlisted guns still write their FNV meshes, materials and textures | `guns.py` | V (items reviewer): 64 of 82 gun models referenced by nothing, then packed |

## <a id="meshes"></a>Meshes and assets

| # | Finding | Where | Evidence | Fix direction |
|---|---|---|---|---|
| M1 | **Shared material and spec-map files with different contents; the last mesh written wins.** A BGSM's path is its diffuse plus sidedness, glow and alpha, but its normal map, decal flag and specular are not in it; a BGEM's path leaves out alpha; a spec map's path is its normal map, but `spec_image` bakes the mesh's smoothness into it | `convert_static.py:237, 354-361, 416-435`; `statics.write_converted` rewrites them per mesh | V (meshes reviewer, region): 14 of 1,025 BGSM paths have more than one content (normal map 8, decal 6, specular 3); 1 of 61 BGEM (`apartmentpre01gla_effect.bgem`, 4 versions); 38 of 657 spec maps differ in smoothness, used by 376 meshes (`craftsmanroofing_s.dds` wanted at 0.361 by the schoolhouse and 0.159 by `craftsmanhomea`). Which mesh wins changes with the build's scope | Put every content-bearing field in the path, or a short hash of the contents |
| M2 | **`elric.finish` holds every parsed mesh at once** (a dict per vertex) until grafting ends | `elric.py:128-133` | V (meshes reviewer): 1,642 region meshes with physics, 75 MB on disk, hold 2,357 MB. M: ~7.5 GB more in the main process for the whole map, on a first build or after an edit to the 8 files `code_tag('fo4_import.nif.elric')` covers | Keep paths and Elric's output; read, graft and write one file at a time |
| M3 | **Cache keys miss inputs.** `code_tag` hashes `.py` files only; `convert()` loads `native/dist/_nifgeom_native.cp314-win_amd64.pyd`, and `addons.py` reads Fallout4.esm's and the export's ADDN | `code_tag.py:17-20`, `addons.py:22-35` | V that the `.pyd` is loaded; the effect (a stale mesh after rebuilding the native reader) is suspected | Hash the `.pyd` bytes and the data files read into the tag |
| M4 | **Half of each face fit is the same for every NPC.** Of a 7.8 s `tint_fit`: `fit_with_brow` 3.6 s depends on the NPC; `texture.remap` 2.45 s, `texel_points` 0.95 s (a Python loop per triangle), `face_mask` 0.23 s and `bake.align` 0.14 s do not | `face_fit.py`, `face/*.py` | V (meshes reviewer, profiled) | Compute the shared mapping, mask and alignment once per race and sex; with the process pool from [first build](#first-build) |
| M5 | **Worn headgear overwrites the static on the same path**, uncached per slots | `equipment.py:305-312` | R. Two berets sharing `red_beret.nif` (slots 46, and 30+46) get whichever fit ran last; HatNVPsychicNullifier's world model is its worn model, so one overwrites the other | A worn mesh gets its own name, keyed by slots |
| M6 | **`mesh()` and `weapon_mesh()` share one cache key and file**; `_finish` dresses every file in `builder.weapons` | `cell.py:230-241, 826-827` | V (items reviewer): 22 models serve both own-mesh melee weapons and STAT/MISC; 8 of those statics are placed (10 references: BrokenMachete ×2, 1stPersonTireIron ×2 …) and would get the dressed weapon NIF | Name weapon meshes apart (`_weapon.nif`) |
| M7 | **`_ba2` is never pruned**: everything any build wrote ships in the BA2 | `ba2_pack.py:33-41` | V: of 3,637 staged files, 773 were not rewritten by the last build (558 of them FaceGen, which the build does not rewrite); 1 staged face has no NPC_ in the plugin | Prune against what this build and the last FaceGen export wrote |

The uncommitted `without_havok` change in `elric.py` is correct for every
current caller (V, meshes reviewer: 0 bad references over 2,266 output
meshes; the old truncation dropped a terminal's screen shader). Its
`REF_KEYS` leaves out animation and particle keys and cannot renumber
unparsed blocks, so a block appended after the collision later would be
mis-pointed; an assert would catch it. `weapon.py:10` still describes the
old truncation.

## <a id="scripts"></a>Scripts

| # | Finding | Where | Evidence | Fix direction |
|---|---|---|---|---|
| S1 | **A mirror global gets the value read before an atomic add.** After an add, later reads of `Q.v` in the function become `TES4Added_*`, including the `SetMirror` after a direct write | `atomic_adds.py:116-131` | V: freshly converted `FALLOUTNV_VMS21aOmertaAmbushThugSCRIPT` writes `VMS21a.OmertasDead = 4`, then `SetMirror(TES4QVar_VMS21a_OmertasDead, TES4Added_VMS21a_OmertasDead)` (3). The only condition on it, INFO 0012745D `OmertasDead == 4`, can never pass | A direct write drops the variable from the added set, or the mirror takes the assigned value |
| S2 | **`SetQuestDelay X 0` polls at 0.1 s for good.** `TES4SetDelay` does `Math.Max(afSecs, 0.1)`; 0 means the 5 s default (as `quest_delay_arm` already maps it) | `assemble.py:429` (uncommitted) | R; FNV has no such call, Fallout 3 has 17 of its 27 (MQ04 twice, MS10, MS11Fin, MS01Crowd …) | `afSecs <= 0` → 5.0 |
| S3 | **Quests that speed themselves up get a 5 s jump in GetSecondsPassed after any pause.** The prologue's clamp for a gap over 2 s substitutes the compile-time interval, now 5.0 for every Fallout 4 quest script without an authored delay (it was 0.1) | `poll_interval.py:26-27`, `assemble.py:1051-1052` (uncommitted) | V (the converted scripts' `TES4_Delay`): FNV quest scripts with no authored delay that read GetSecondsPassed and set a short delay themselves: VStripSS3/4/6, VOVLighting, VHiddenValleyDustStorm, VMS21aSupport; 3 in FO3. VStripSS5 and VStreetLighting author 2 s and are unchanged. None is in today's build. VOVLighting's flicker runs on 0.3–4.7 s thresholds, so one Pip-Boy visit skips it | Clamp to the live `TES4_Delay` |
| S4 | **The incremental compile ignores header contents.** Its state is keyed on the header paths only | `compile_papyrus.py:208-212` | V (scripts reviewer, toy): a changed header signature reported "0 of 1 changed" and kept the stale .pex | Hash the header files into the state key (F4SE, Base, LevelUpMenuEx, Garden of Eden) |
| S5 | **`.pex` files of deleted sources are never removed**, `--full` included | `compile_papyrus.py:265-267` | V: the mod's `Scripts` holds 3,567 .pex for 1,260 current sources; 2,308 have none (1,920 `TIF` fragments, 87 quest fragments) and ship with the mod | Delete the .pex of names the old state had and the sources lack |
| S6 | **`compile_into` works for FNV only.** `with_types` always opens `FALLOUTNV_GSDocMitchellScript.psc`; `keep` and `_CONVERTED_TYPE` assume `FALLOUTNV_` | `fo4_import/spike/script.py:44, 135-156` | V (scripts reviewer): a Fallout 3 folder raises FileNotFoundError, and every `FALLOUT3_*` script would be staged | Take the prefix from the namespace; add the Doc script only when it exists |
| S7 | Adders mirror and trace before `Return`, so two adds at once can both return the final value | `atomic_adds.py:86-97` | Suspected (FO4 releases an object's lock on a call out; not run in game). 78 adders, e.g. `FALLOUTNV_1EWatchFiendDeathScript` tests `== 4` | Keep the new value in a local and return it |
| S8 | Cross-script counters on references stay non-atomic: `find_adds` sees no ACHR/ACRE | `atomic_adds.py` | V: 7 FNV counters (`VTopsBlackjackDealer01REF.nPlayersAtTable`, `VFSRotfaceREF.RumorCount`, `VFSJulieFarkasREF.iMedDonation*` …) | Index placed actors too |
| S9 | The player-hit trace registers only in `OnQuestInit`, so a save where F3NV_NewGame already ran never traces hits | `F3NV_NewGame.psc:17-18` (uncommitted) | R | Register in `OnPlayerLoadGame` too |

Checked and fine (scripts reviewer): one poll loop per quest (every arm
uses timer 0); stopping and restarting a quest re-arms once; all 15
sampled FNV scripts, F3NV_NewGame and TES4Polyfill compile with FO4's
compiler; the compile rescan over 17,549 sources takes ~3 s.

## <a id="fine"></a>Checked and fine

- **Reproducible build:** the profiled scratch build wrote a plugin
  byte-identical to the user's (V).
- **FormID string case:** none of 1.1M hex values in REFR/CELL/ACHR/ACRE/
  WRLD, nor 12 other record types, is lower case (V).
- **Persistent references:** WastelandNV has 6,060; building them with
  `bytes +` costs 0.15 s (V). The biggest interior has 2,782 references.
- **Texture staging:** `shutil.move` onto an existing `_ba2` file is a
  rename, not a copy (V, Python 3.14).
- **Elric** is quick (0.07 s per mesh) and its cache works (V).
- **World-placement hashed ids** (SCOL parts, trees, load doors, stand-ins):
  611 region keys, none moved when simulated inside the 6,871 whole-world
  keys (V, world reviewer). The drift in [FormIDs](#formids) comes from
  dialogue and quest keys.
- **Packers:** no interior (279) and no base (7,604) makes them raise (V).
- **Persistent references** all fall inside a built grid cell (V).
