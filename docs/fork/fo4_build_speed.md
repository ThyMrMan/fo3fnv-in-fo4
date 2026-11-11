# Plan: build time, first builds and rebuilds (2026-11-10)

Status: planned, nothing built. Numbers come from the
[overnight run](../audits/fo4_overnight_build_2026-11-10.md) and from two code
reads done for this plan. A line marked *(read)* was read in the code but not
rerun; *(timed)* was timed once in a single process on one male face
(DocMitchell).

**Goal.** Three times, each with its own cause:

| Build | Today | Cause | Target |
|---|---|---|---|
| The game, first build (what a user waits for) | 135 min | 97 min of face fits | about 30 min |
| One mod against a built game | 7–41 min, whatever its size | the mod build remakes what its masters hold | 1–5 min, by the mod's size |
| A developer's rebuild after a code change | 25–55 min, 135 when a cache empties | caches emptied by unrelated edits; every record remade | minutes |

Related: [mod builds](fo4_mod_builds.md) (the master kit, MO2, the app),
[Part D](fo4_plugin_layout.md#incremental) (the journal),
[Part E](fo4_plugin_layout.md#which-builds) (which plugins build, code
identity). This plan sets the order across them and adds what they lack.

## Contents

- [What was found](#found)
- [The decision](#decision)
- [1. One bad source file does not end a build](#faults)
- [2. Face fits](#faces)
- [3. Cache keys that hold](#keys)
- [4. Fixed costs every build pays](#fixed)
- [5. Mod builds replay the game build](#replay)
- [Routes considered and not taken](#left-out)
- [Order](#order)
- [Open questions](#open)

## <a id="found"></a>What was found

**The face fit is slow for reasons that are not the fit.** A cold game build
fitted 2,130 faces in 5,827 s on 6 workers, about 16 s of worker time per face.
*(timed)* one male face costs 5.9 s of tint fit, 0.9 s of head-part choice and
0.2–0.4 s of sculpt fit, and a worker's first face per sex pays about 10 s of
setup. Inside that:

- `tint.fit_with_brow` solves the same bounded least-squares problem once per
  brow option, 18 times for a man and 3 for a woman, over 149,475 rows by 44
  columns each time: 4.55 s of the 5.9. The matrix is the same for every face
  of a sex; only the target changes.
- `fnv_head._mesh` is under `functools.cache`, but its argument is a new
  `Layered` object on every call, and `Layered` has no `__eq__` or `__hash__`.
  Every call misses, parses the head mesh again (62 ms, 4 times a face) and
  keeps 2.4 MB for the life of the worker: about 10 MB leaked per face.
  *(timed, 2 calls, 0 hits.)* It dates from the `asset_root` change of
  2026-10-31.
- The basis files are loaded from disk again on every call (tint twice a face,
  sculpt three times), and the hair color step converts the same hair texels
  to Lab 34 times a face (0.6 s).
- The target face texture is built at 2048 by 2048 in float64 and then reduced
  to 256 (about 1 s).
- Six workers each start BLAS on all 16 threads, so they fight for cores. The
  worker count is held down by the leak and by BLAS already using every core.

**The face cache empties on edits that cannot change a fit.** *(read, with the
recorded identities of 3,733 entries compared.)* The 2026-11-10 cold build was
caused by working-tree edits to `export_index.py`, `fnv_head.py` and
`nif/blocks.py`. The `blocks.py` edit added new block readers. A fit never
runs them, but `nif/file.py::_parsed` reads the `BLOCKS` table, the table
names every reader, and code identity follows a table's values whole. So any
new or edited NIF block reader refits every face.

**The same record misses real changes.** *(read, counted.)* Work done inside a
per-process memo (`assets.kept_value`: `fo4_part_samples`, `head_depths`,
`skull`) runs during the first face a worker sees for a sex, so it is in the
code record of that face only: 61–66 of 1,861 head-part entries. An edit to
one of those functions leaves about 1,795 entries marked current that are
stale.

**Published face fits would not have survived.** `face_fits.fit_code` is
still a byte hash of 51 files in the fit modules' whole import tree, comments
included, so any day's work would have made a published file useless. Fits
taken from a published file are also stored locally with the widest key the
work cache has (`ran=None`).

**A mod build is a game build of a region, pruned at the end.** *(read.)*

- The app passes one bounding box around every exterior cell the mod edits
  (`addons.build_scope`). The build then takes every cell in the box, follows
  doors and script links into interiors, and adds every cell a script moves
  the player to, all from the mod's records laid over its masters'.
- Every reference, base, actor and quest reached that way is made by the same
  makers the game build uses. Thirty or so passes run over every record of a
  type whatever the mod holds (globals, factions, perks, reputations, recipes
  and their items, encounter zones).
- Master meshes are checked in the mesh cache (26–153 s), written into the
  mod's folder, given collision by Elric (23–183 s), and deleted afterwards
  when they match the master's copy.
- At the very end `master_overrides.drop_unchanged` compares each master
  record to the built master's bytes and drops the ones that match.
- Only dialogue lines, challenges and LOD ask whether a record is the mod's
  own.

So Landscape Disposition Fix, 2,242 records, made 1,622 NPCs and readied
6,360 meshes. The 1,585 "master records changed by the build alone" are
master records the region build made differently from the game build. They
are dropped, but each one is a place where the two builds disagree.

**Costs that do not scale with the work.**

- Script compile took 146 s to compile 1 script (Placement Fixes) and 113 s
  for 1 changed script of 16,190 (the game), against 3 s with none. Something
  costs about two minutes whenever any script compiles. Not yet traced.
- `ledger and cleanup` is 160 s on the larger mods and 50 s on the smallest.
- Gun clips rerun whenever the set of masters changes
  ([audit](../audits/fo4_overnight_build_2026-11-10.md#time)): 650–750 s on
  three mods. They also run one gun at a time, 495 s cold for the game.
- The gun clip cache is 11 GB: each entry holds every clip file it wrote.
- Collision was 653 s on the cold game build. `elric_finish` entries are
  stored with the widest code key too, so the same edits may have emptied
  them. Not confirmed.

## <a id="decision"></a>The decision

1. **Make the face fit fast, then publish it.** Both, not one. A published
   file covers New Vegas's own faces; a mod's new NPCs and any developer
   change to the fit still run locally. The fit itself can be about 10 times
   cheaper with no change to what it computes.
2. **Give the expensive caches a version we bump by hand, checked by a test.**
   A code hash has now failed in both directions for faces. The cheap caches
   keep code identity, with its hole closed.
3. **Mod builds replay the game build's journal.** Part D's journal and the
   mod build are one mechanism, not two. The other route, teaching each maker
   to skip master records, runs into the same shared state Part D already
   surveyed, has no check as strong, and would be a second mechanism to keep
   in step. A [spike](#replay-spike) confirms this before the large work
   starts.
4. **Until the journal lands, cut the fixed costs** a mod build pays, where
   the fix is small and stays useful afterwards.
5. **First of all, a bad source file is counted, not fatal,** so that every
   later run measures all of its builds.

## <a id="faults"></a>1. One bad source file does not end a build

Five of the 13 overnight steps died on one file each. New Vegas shows a
marker or nothing for a missing or broken mesh and carries on. The build
should match that.

- **One boundary, per asset.** The mesh, collision, gun and equipment
  converters raise a `SourceFault` naming the file and the reason. The caller
  that asked for the asset catches it, leaves the record without that model
  (as it already does for a base with no mesh), and counts it. The build
  report lists every fault by file. Nothing else is caught: a bug in our code
  still stops the build.
- **Covered by it:** a missing model (Willow), a Havok motion system outside
  the defined values (the overlay, where one mesh failed 13 GB of output),
  and a collision node whose name matches no node (`elric.graft`; its error
  does not name the mesh today).
- **Assets are found the way New Vegas finds them.** The pre-order pack
  meshes YUP and Agua Fria use are in `ClassicPack.esm`'s export, which is not
  among their masters. New Vegas resolves a model path across every loaded
  archive, not through a plugin's masters. So asset lookup covers the game's
  own plugins (the game, the five DLC, the four packs) for every mod. Record
  lookup stays with the masters.
- **Not build speed, listed so they are not lost:** the 6 unresolved quest
  properties in DLC Enhancements (Old World Blues dialogue quests the region
  did not write; [section 5](#replay) removes the region) and the three
  compile errors in `FALLOUTNV_BBSelfDestructQuestScript`.

Size: S. Test: a build with a missing model and an undefined motion system
finishes and lists both.

**Status: built, not yet run in a game build.** `fo4_import/base/source_fault.py`
holds `SourceFault` and the run's list. Raised by `mesh_cache` (missing
model), `collision._motion` (undefined motion system) and `elric.graft`
(unmatched node; `elric.finish` names the mesh). Caught at twelve places:
`CellBuilder._asset` (every `mesh`/`weapon_mesh`/`prop_mesh` caller),
`CellBuilder.record` (left out as "in no archive" is, counted as "a source
fault"), `Guns.choose`, `Equipment._own_models`, `overlay.meshes`,
`elric.finish`, `Activators.ambient` (not ambient), `Creatures._skin` (the
creature keeps its target's skin, as a `stats` stand-in does),
`TalkingMachines._part` (part left out, as a missing one is),
`Terminals._look` (falls to `mesh()`), `Swaps._pair` (no swap, as for no
such shape) and `ObjectLod._converted`/`_shipped` (no LOD mesh). A faulted Elric graft is not stored in the work cache. `run`
and `overlay` print `source fault: <file>: <reason>` lines and write them to
the stamp under `source faults`. Asset lookup (`export_index.asset_chain`,
behind `export_file` and `asset_root`) adds the game's own plugins
(`source.GAME_PLUGINS`, keyed on the game, shared with
`fo4_install_check`) after a plugin's masters; record lookup is unchanged.
Tests: `tests/test_fo4_source_faults.py`.

## <a id="faces"></a>2. Face fits

**Status: a, b, c and the keying half of d are built and measured
(2026-11-10); not yet run in a game build.** Publishing the file and the
app install are not built. One change beyond the plan is in: sculpt controls
with no effect stay 0 ([below](#sculpt-dead)).

**How it was measured.** The real fit functions (`sculpt_fit`, `tint_fit`,
`head_parts.choose`) run directly, with no work cache, on three men
(DocMitchell, GSEasyPete, GSChet) and three women (GSSunnySmiles,
NellisPearl, Veronica). Every result was saved before any edit and compared
after each step. Times are one process, for a face whose sex, head mesh and
hair that process has already met.

| | A man | A woman |
|---|---|---|
| Before (16 BLAS threads, as built) | 6.7–7.5 s | 3.8–4.0 s |
| After a | 5.2–7.1 s | 2.0–2.2 s |
| After b (one BLAS thread) | 1.4 s | 1.1 s |
| After c | 0.33–0.37 s | 0.34–0.51 s |

a. **Stop the repeated work.** All six faces came out byte-identical.
   - `fnv_head.head` hands `_mesh` the resolved path, so its cache hits. A
     process's memory is flat over nine faces (it grew 9 MB a face).
   - `load_basis` (tint and sculpt) is kept per process until its file
     changes, its arrays read-only.
   - Each hair color form's color on a hair is worked out once per process
     and hair material (`hair.hair_colours`). The head-part choice went from
     0.8–1.4 s to 0.10–0.13 s.
   - The cache key holds each sex's basis hash, worked out once per process,
     not the two basis files' bytes.

b. **Solve the small problem** (`tint.BrowFits`). Per sex, once per process:
   the QR factorization of the 44 free tint options under the face mask, and
   each brow's effect projected onto it. Per face: one product with the
   target, then a bounded fit on the 44 by 44 triangle per brow. The brow
   fits went from 4.0–5.0 s to 0.05–0.07 s for a man (17 brows and none) and
   from 0.7–0.9 s to 0.011–0.017 s for a woman (2 brows and none).
   - Against the full fits, the largest change in a fitted value was at most
     5e-14 on four faces, 5.5e-10 on GSChet and 3.2e-07 on Veronica. That is
     the solver's own stopping tolerance (1e-10 on the cost), not the 1.7e-15
     timed on one face. No layer's stored percent changed and no brow flipped.
   - Ties are real: the two female brow options have the same measured
     effect, and one male brow option has none. Each brow goes through the
     same arithmetic, so the first still wins exactly, as before. Factoring
     the free and brow columns together breaks such a tie by rounding
     (`tests/test_fo4_face_fit_speed.py`).
   - Between 1 and 16 BLAS threads the tint values now differ by at most
     9e-15, and by at most 3.5e-07 under OpenBLAS's Sandybridge kernel. No
     stored percent changed in either case.

   <a id="sculpt-dead"></a>**Sculpt controls with no effect.** One BLAS
   thread alone does not make a sculpt fit repeat. 121 of the 224 male
   sculpt basis columns, and 120 female, are exactly zero: the control moved
   no face vertex in the CK calibration. The solver left values up to ±0.9
   there, and they went into the record. They changed with the thread count
   (about 52 controls a face, by up to 1.8, between 1 and 16 threads) and
   with the CPU kernel at one thread. The controls that have an effect agreed
   to 1.7e-06. This is what "many equally good answers" was.
   `sculpt.fit` now leaves a control with no effect at 0. After that the
   sculpt bytes are the same at 1, 4 and 16 threads and under the Sandybridge
   kernel, on all six faces; the share captured is unchanged to 1e-12. It
   changes every NPC's FMRS bytes once, as the change to one thread would
   have. To drop it, restore the two lines in `sculpt.fit`.

c. **Build the target at the size the fit uses** (256, not 2048;
   `texture.face_colours`, `face_fit.tint_target`). The target went from
   1.0–1.4 s to 0.11–0.15 s a face, the first face on a new head mesh from
   3.9 s to 0.3–0.7 s, and a worker's peak memory from 1.65 GB to 0.84 GB.
   It moves the fits more than slightly. The median is taken over 256-size
   texels, and the color is no longer rounded to bytes before it is reduced:

   | Face | Largest move of a tint value | Layers whose stored percent changed (largest step) | Move of the skin tone scale | Brow |
   |---|---|---|---|---|
   | DocMitchell | 0.074 | 10 of 61 (7) | 0.021 | none, as before |
   | GSEasyPete | 0.081 | 16 of 61 (8) | 0.017 | none, as before |
   | GSChet | 0.098 | 12 of 61 (10) | 0.029 | the same one |
   | GSSunnySmiles | 0.055 | 12 of 46 (5) | 0.008 | none, as before |
   | NellisPearl | 0.024 | 5 of 46 (2) | 0.009 | none, as before |
   | Veronica | 0.037 | 9 of 46 (4) | 0.008 | none, as before |

   Sculpt fits and head parts do not change. To drop c, `tint_target` goes
   back to `face_texture` on the full-size texture; nothing else depends on
   it, but `FACE_WORKER_BYTES` must then be 1.7 GB.

d. **Key** ([section 3](#keys)). The three face sites (`sculpt_fit`,
   `tint_fit`, `head_parts`) are versioned work-cache entries
   (`work_cache.versioned`) under `face_fits.FIT_VERSION`, on the face's
   fields, its head parts and its sex's basis hash; no code record decides
   them. The published file carries the same version (its `fit_code` field),
   and a fit taken from it is kept under the same key. Every face entry made
   before this is unreachable. `tests/test_fo4_face_fit_version.py` fits the
   six faces above in a worker process and checks what a record takes from
   them (sculpt bytes, packed tint layers, tone scale to six places, head
   parts) against `tests/fo4_versions/face_fits.json`; after a bump, record
   again with `F3NV_RECORD_VERSIONS=1`. Still to do: publish the file as a
   release asset and have the app install it with the converter.

<a id="face-pool"></a>**The pool.** Workers run BLAS on one thread
(`npcs.WORKER_BLAS_THREADS`). A worker commits 0.84–0.88 GB at its peak; a
16-thread worker reserved 1.18 GB before its first face, a one-thread worker
0.22 GB. Measured on an 8-core, 16-thread machine with other work running:

| Faces | Workers | Wall | Fit time of a typical face in a worker |
|---|---|---|---|
| 150 | 2 | 44 s | 0.35 s |
| 150 | 3 | 37 s | 0.36 s |
| 150 | 6 | 34 s | 0.45 s |
| 150 | 15 | 53 s | 0.96 s |
| 500 | 7 | 56 s and 62 s | 0.45–0.50 s |
| 500 | 8 | 60 s | 0.50 s |
| 500 | 10 | 69 s | 0.65 s |
| 500 | 15 | 70 s and 77 s | 0.76–0.92 s |

**`cpu_count() - 1` workers is not faster here.** Once warm, 15 workers fit
27% more faces a second than 7 (19.7 against 15.6), not 2.5 times as many:
the machine has 8 cores. Each worker also pays its own start: the head-part
candidates of each sex (about 6 s a sex alone, 20–40 s for both when 15 start
together) and each hair's color candidates the first time it meets that hair
(1.1 s). That was 134 worker-seconds at 7 workers and 606 at 15. So
`npcs.face_workers` starts one worker per 25 faces (`FACES_PER_WORKER`: a
worker's start costs about that many fits), at most half the logical cores,
and as many as free memory holds at 1 GB each with 2 GB left over. That is
6 workers for 150 faces and 8 for 500 or more on this machine.

**Expected for the game's 2,130 faces** *(estimate from the rates above, not
run)*: about 150 s on 8 workers, against 5,827 s; the same rates give about
150 s on 15 workers too. The next cost to remove is the per-worker start: its
results are a few kilobytes per sex and could be made once and shared. With
that gone, more workers than cores would add their 27%.

## <a id="keys"></a>3. Cache keys that hold

- **A hand-bumped version for the expensive sites.** Face fits (5,500 s to
  refill), gun clips (450–750 s), outfits (`item ARMO`, 574 s). Each site's
  key is its inputs and a `<SITE>_VERSION` constant. A test keeps the bump
  honest: it recomputes a few reference results (three faces of each sex, two
  guns, two outfits) and fails when a result changes while the version did
  not. This is the navmesh cache's rule turned around: it guards the output,
  not the source text.
  *Built (mechanism):* `work_cache.versioned` / `lookup_versioned` /
  `store_versioned` key on the inputs plus the version and write an empty
  code record. `tests/fo4_versions.py` `check(site, VERSION, {name: (inputs,
  make)})` keeps each reference's inputs and result digests in
  `tests/fo4_versions/<site>.json`. It fails when a result changes and the
  version and inputs do not. It also fails on a new version or new inputs
  until recorded again with `F3NV_RECORD_VERSIONS=1`, which will not record a
  changed result under the same version and inputs.
  *Built (sites):* gun clips (`GUN_CLIPS_VERSION`, site `versioned_gun_clips`)
  and worn outfits (`outfit.OUTFIT_VERSION`, site `versioned_outfit_worn`).
  The new site names leave the old `gun_clips` and `outfit_worn` folders to
  `prune_unnamed` (12 GB). The outfit key adds `outfit.body_reads`: the FNV
  skeleton, upper body, head and its `.egm` that `body_fit` reads. Before,
  a replaced FNV body left every worn outfit stale. References: the Varmint
  Rifle (2hr) and 9mm Pistol (1hp); Reinforced Leather Armor and the Vault
  21 jumpsuit, each sex and view. The honesty tests take 16 s and 15 s cold.
- **Close the hole in the code record** for every site that keeps it. A
  worker's code record for a site becomes everything that has run for that
  site in the process so far, not only what ran during this one entry. That
  covers per-process memos. It is wider than needed and never misses.
  *Built:* `ran_code.ran_while` takes its site from the code its maker runs
  (`site_of`, through `functools.partial`), so its callers are unchanged. A
  memo shared across makers of different code is still missed. The
  `lod_atlas` normal and specular sites share one maker with diffuse, so this
  closes their hole too: 32 entries each held an empty record, current
  whatever code changed. Those old entries stay until pruned.
- **Tables of functions.** Code identity follows `BLOCKS` into every reader.
  With the expensive sites on versions this costs little: the mesh cache
  really does depend on the readers. Left as is.
- **Gun clips key on what a gun reads:** its skeleton, its aim clip, each
  clip its plan names, and whether each sighted variant exists. Not the whole
  first-person folder of every export layer. A helper shared with `fnv_stem`
  lists them before the lookup. This ends the reruns when the master set
  changes (about 35 min of the overnight run).
  *Built:* `gun_clips.clip_reads` / `planned` (shared with `_view`). The key
  also drops the gun's own keyword FormIDs: the kept value holds placeholders
  and `convert` puts the plugin's ids in. So a DLC or mod build takes the
  game build's entry, and the ledger calls stay as before. Each written file
  is kept once by SHA-1 (site `gun_clip_files`).
- **Gun clips cold, in the pool.** 86 guns at 6–8 s each, one at a time
  today.
  *Built:* the first gun to reach `Guns._clips` runs `_warm_clips`. It guesses
  the plugin's own guns (gun type, model, no non-`fnv` table entry) and
  chooses and builds each quietly: no count, fault or FormID. It then makes
  the missing ones in `gun_clip_pool` (whole guns, each worker writing its own
  temporary folder). Every gun then replays from the cache in build order, so
  records don't depend on which worker finishes first. Measured: the pool's
  output is identical to a one-at-a-time run for both reference guns. A
  wrong guess costs pool time only. The guess runs on every build, even a
  warm one, but it is the real pass's work done early: `choose` takes the
  guess for the same gun and table entry, `templates` its build, and
  `_clips` its clip key, so each gun is chosen and built once per run. A
  mesh fault the guess met is counted by `choose`, once. The pool's
  already-kept check reads each entry but not its files (`is_kept`).
  Measured on FalloutNV.esm's 91 guessed guns with the meshes warm: choosing,
  building and keying them costs 27–59 s on a busy machine. Before, a warm
  build paid that twice. Now the real pass over the same guns takes 0.03–0.06
  s, and every guess was used.
- **`elric_finish`** keys on Elric's version and the mesh's bytes alone, if
  the read confirms nothing else of ours decides its output.
  *Read: our code does decide it.* `elric.finish` hands Elric
  `nif_file.write(nif_file.read(raw))`, and writes
  `nif_file.write(graft(...))` or `without_havok(...)`, so the NIF reader and
  writer (`BLOCKS`) and `graft` / `without_havok` / `_renumber` shape the bytes.
  Elric's own run is already cached by bytes alone (`elric_cache.process`).
  So `elric_finish` keeps a code record: the functions `elric.finish` ran,
  not `ran=None`. *Built.*
- **Prune.** The gun clip cache keeps the hashes of the files it wrote and one
  copy of each, not a copy per entry (11 GB today). Entries without a code
  record, and the sites no code names any more (`bordered_map`, `encode_dds`,
  `normal_dds`), are deleted.
  *Built, not run:* `work_cache.prune_unnamed()` deletes each site folder
  whose name is no string constant in `fo4_import`.
  `prune_unrecorded(folders)` deletes each file that is neither a code
  record nor has one. Run it with no build running. Measured by reading:
  262,180 of the work cache's files and 90,388 of the mesh cache's lack a
  record. That is 28.4 GB of the work cache (spec_map 9.6, gun_clips 7.4,
  mesh_files 6.1) and 18.9 GB of the mesh cache. No lookup takes them.

Size: S–M. None of it changes a record.

## <a id="fixed"></a>4. Fixed costs every build pays

Each is small, and each still pays after [section 5](#replay), because the
game build and a mod's own content go through the same steps.

| Cost | Seen | Lead |
|---|---|---|
| Script compile with at least one script | 113–154 s against 3 s with none | Traced and built 2026-11-10 (not yet in a build). The conversion deleted and rewrote every .psc (17,440 files for 59 changed), which voided every size-and-time stamp and made the first read slow: 17,507 fresh files hash in 68 s against 1.4 s, the masters' 31,835 headers in 113 s against 2.3 s, Caprica's first run 62 s against 1.0 s. Now an unchanged .psc is left alone ([sources](../commentary/script_convert.md#wipe-output-dir)), the header memo is per header folder for all plugins, a Caprica source error is kept instead of recompiled by FO4's compiler, and Caprica's reruns go side by side: YUP 99 runs in 194 s before, 112 runs in 58 s ([errors and runs](fo4_pipeline.md#caprica-errors), [import order](fo4_pipeline.md#own-source-first)). Left: a Caprica run reads every import file (0.7–1.4 s each), and Caprica cannot go past a failing script, so runs = folders + failures. |
| Mesh cache check | 26–153 s | Each hit reads the whole NIF to hash it, reads its code record and unpickles the result. Use the size-and-time stamps the compile step already has (`file_stamps`), and don't unpickle on a hit. |
| Master meshes written, given collision, then deleted | 23–183 s of collision | Decide before writing: a mesh whose master folder already holds the same cache key is skipped. |
| `ledger and cleanup` | 50–163 s | Not profiled. Profile it on Goodies. |
| `base STAT` on Goodies | 796 s against 148 s for the whole game | Not explained. Find it before trusting any estimate here. |

Size: S each, after a profile of one mod build (Goodies has all five).

## <a id="replay"></a>5. Mod builds replay the game build

**The idea.** [Part D](fo4_plugin_layout.md#incremental) cuts a build into
units (a cell, a base form, a topic, a quest, one of the passes over a whole
type). A unit that runs is recorded: the records it wrote, the ids it handed
out, what it added to the shared lists, and the source records it read. Part
D uses that to skip unchanged units in a developer's rebuild.

A mod build is the same case. It is the game build with a few source records
changed or added. So:

- The game build ships its journal beside its plugin. This is the
  [master kit](fo4_mod_builds.md#master-kit), with the journal as its main
  part.
- A mod build finds the units whose recorded reads include a record the mod
  changes, and the units for the mod's new records. It runs those.
- Every other unit replays: its ids and shared-list entries come back from
  the journal, and its records are never made, since they are the master's by
  construction.
- There is no region. The 30 global passes are units like any other, and most
  replay.
- `drop_unchanged` stays as the last check, on far fewer records.

**What it settles** that skipping in the makers does not:

- The lists written at the end (type lists, ammo, condition rows, the combat
  perk) see the master's entries from the journal and the mod's from its
  units.
- A master record that changes because of the mod without the mod holding it
  (a gun whose ammo list a mod extends) reruns, because its unit read the
  changed record.
- The 1,585 records the region build makes differently go away. A replayed
  unit is the game build's own output.
- The check is strong and cheap to state: **a mod built by replay equals the
  same mod built the old way, byte for byte.** The old way stays in the tree
  as the reference until that holds on every test mod.

**<a id="replay-spike"></a>The spike that confirms it** (before any journal
code). Record reads only: which source records each maker call reads, through
the hooks Part D lists (`export_records`, `own_records`, `export_file`,
`Layered`). Run it over the game build once, then answer for three mods
(Landscape Disposition Fix, Goodies, Better Brotherhood):

- How many units read a record the mod changes?
- How many units read a whole type (every INFO, every FLST)? A new record of
  that type would rerun each of them. Those reads have to be recorded as a
  question with its answer ("the INFOs of topic X", "the lists naming Y"), as
  Part E already does for master lookups.
- What does recording cost in build time?

If a small mod reruns a small share of units, build Part D's phases 6 and 7
with the mod build as the first user and the developer's rebuild as the
second. If whole-type reads make most units rerun and can't be narrowed, fall
back to the narrower route: build only the cells the mod edits (not their
bounding box), don't follow doors into master interiors, and take a master
form's id from the ledger without making it. That route is smaller. It leaves
the end-of-build lists and the records changed without being held as known
gaps to close one by one.

Size: the spike S–M; the journal L, then M (Part D's own estimate).

## <a id="left-out"></a>Routes considered and not taken

- **Ship the finished output as patches against the user's own game files**
  (how Tale of Two Wastelands installs). A first install would take minutes.
  It is not taken now for three reasons. It does nothing for mods, which is
  where the count grows. It needs every build to give the same bytes on every
  machine. And hosting data derived from Bethesda's files is the user's call
  ([open questions](#open)). Publishing face fits is the same idea limited to
  numbers that are ours.
- **Native code for the hot loops.** The cold time is in numpy and BLAS doing
  the same work many times, not in Python being slow. The rule stands: numpy
  first, C++ for a measured loop.
- **A build server kept running** so the export and Fallout4.esm stay parsed
  between the builds of a queue. Setup is about 30 s a build. The journal
  removes far more.
- **One build of the game and every enabled mod, split by owner afterwards.**
  Ticking one mod would rebuild all of them, and Fallout 4's last-loaded-wins
  rule for overrides would have to be worked out again inside the split.
- **Building in the cloud.** It would shorten a developer's cold build and do
  nothing for a user's.
- **Skipping master records inside each maker** as the main route: see
  [section 5](#replay). Kept as the fallback.

## <a id="order"></a>Order

| # | Work | Saves | Size |
|---|---|---|---|
| 1 | [Bad source files counted, not fatal](#faults); assets found across the game's own plugins | 5 of 13 overnight steps finish | S |
| 2 | [Face fits a and b](#faces), then c | about 90 of the cold game build's 135 min | M |
| 3 | [Version keys, the code record's hole, gun clip key and pool](#keys) | cold reruns after unrelated edits; about 35 min of a 12-mod queue; about 7 min cold | S–M |
| 4 | Publish face fits; the app installs them | the remaining cold face time for New Vegas's own NPCs | S |
| 5 | [Fixed costs](#fixed), after one profile | an estimated 3–8 min of every mod build | S each |
| 6 | [The read-recording spike](#replay-spike) | decides 7 | S–M |
| 7 | The journal: mod builds, then developer rebuilds | mod builds by size; a one-maker fix in minutes | L, then M |

Steps 1–5 don't depend on each other. Step 1 goes first so that the next
overnight run measures every build.

After every step, rerun the overnight queue and write a new dated audit. The
table above is redone from that file, not from these estimates.

### <a id="audit-2026-11-11"></a>Overnight audit, 2026-11-11 (V)

The save-break run after the dialogue switch (no XDI): 33 builds, warm mesh
and face caches. These are the `stage` lines of each build log.
- **The game:** 37 min. Biggest stages: voice 431 s, own-rig animation data
  (Creation Kit) 337 s, people 194 s, script compile 158 s.
- **DLCs:** 6–19 min. Old World Blues spends 332 s in the Creation Kit step
  as well.
- **Packs:** 1 min each.
- **Mods:** 3.4–19.5 min. Placement Fixes, a small patch, took 18.7 min.

Summed over all 33 builds, 381 min:

| Stage | Min | Share | Note |
|---|---|---|---|
| item WEAP | 63.5 | 17% | 100–276 s in nearly every mod, whatever its own weapons |
| script compile | 40.8 | 11% | 41–174 s per mod; the 2026-11-10 stamp fix did not show (this run rewrote every dialogue script, so rerun before judging) |
| people | 39.4 | 10% | |
| base STAT | 38.3 | 10% | Goodies 157 s, down from 796 s |
| ledger and cleanup | 30.2 | 8% | 14 s even on a 1-min pack, up to 137 s |
| voice | 25.1 | 7% | the game, Autumn Leaves (394 s) and the FO3 spike |
| collision | 25.1 | 7% | |
| item ARMO | 17.6 | 5% | |
| own-rig animation data | 14.3 | 4% | a Creation Kit load per plugin with rigs |

Weapons, people, statics and collision (about 44% together) are mostly
master content that each mod build makes again ([section 5](#replay)).
Separately, the mesh cache check took 10–126 s per build even with every
mesh cached.

The Frontier is the first huge new worldspace, with 589,612 references.
- **Import:** 15 min, placing 105,250 loose files.
- **Mesh pool:** 982 s for 13,625 new meshes. It runs 15 workers at normal
  priority, which left the desktop unusable for about 10 min.

#### <a id="worker-memory"></a>Mesh workers cap their own memory

**What happened (V).** 118 of The Frontier's meshes fail to convert. A
failed mesh is never cached, so every build retries all of them. One of
them, `tfssspacestationext.nif` (61 MB), grows about 1 GB per second
while it converts. (Not in pyffi's read, which takes 3.7 s and 738 MB, but in
the overlay check: [station](research/fnv_nif_reader.md#station).) In the rebuild after the gun fix, that worker
reached 10 GB. RAM fell to 1.2 GB free with 65 of 72 GB committed, and the
machine paged until it stopped responding. The main process would then have
converted the mesh again with no limit (`_warm` drops failures).

**The fix:**
- **Memory cap:** each mesh worker puts itself in a nested job capped at
  one-eighth of RAM, at least 2 GB (`core.process_job.limit_own_memory`;
  3.9 GB on the 31 GB build machine).
- **Too-large meshes:** an allocation past the cap is a `MemoryError` in
  that worker. `warm()` records the mesh in `TOO_LARGE`, and
  `cached_convert` faults it ("mesh too large to convert") instead of
  retrying.
  - The space station now stops at 3.9 GB after 8 s.
- **Priority:** `create_pool_job` puts the whole build job at below-normal
  priority.

Still open: a mesh that hits the cap is tried again on the next build.

#### <a id="frontier-parked"></a>The Frontier is parked

The Frontier (`The Frontier.esm`) stays out of the build queue for now. Its
whole-world build froze the machine again, even with the worker cap,
below-normal priority and a 24 GB job cap (`TESCONV_JOB_MEM_GB`). Which step
froze it is not measured. The likeliest suspect is the main build process,
holding 589,612 references.

What its builds found:
- **Fixed:**
  - gun parts under nested nodes (`gun._shape_parents`);
  - a receiver of a radio station with no free frequency (`Radio.receiver`).
- **Open: 118 meshes with unset Havok fields.** Their bodies carry motion
  system 205 or 154, quality 61 and deactivators 204 (`CC`/`CD`, MSVC's fill
  for uninitialized memory) on massless static bodies. `collision._motion`
  faults them, so these statics are left out. The fix to try is to read a
  massless body with an undefined motion system as fixed.
- **Open: the overlay check's memory.** `tfssspacestationext.nif` (61 MB)
  reads fine (pyffi: 3.7 s, 738 MB). `convert_static.overlay_layers` →
  `_surface_gaps` then allocates 3.88 GiB per 256-point chunk over its
  677,436 triangles ([station](research/fnv_nif_reader.md#station)).

To try it again, run a scoped build first: one small area, fewer workers and
a job cap around 12 GB.

## <a id="open"></a>Open questions

- Publish face fits as a release asset of this repository, as the navmesh
  cache is? (Our numbers and Fallout4.esm FormIDs only.)
- Is shipping patches against the user's own files wanted as a later option,
  or ruled out?
- How large is the journal for the whole game, and does it ship compressed
  beside the plugin or get rebuilt on the user's machine by the game build?
  (The spike gives the read counts; record bytes are the built plugin.)
- A mod converted against one release's journal and a game rebuilt with
  another: the same question as in
  [mod builds](fo4_mod_builds.md#open).
