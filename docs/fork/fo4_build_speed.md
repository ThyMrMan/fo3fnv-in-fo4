# Plan: build time, first builds and rebuilds (2026-11-10)

Status: steps 1, 2, 3 and 5 of the [order](#order) are built, each section saying
what is measured; publishing face fits (4) and the journal (6, 7) are not. Numbers come from the
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

Related: [build resources](fo4_build_resources.md) (memory per stage, the Low/Balanced/Full setting, time
estimates), [mod builds](fo4_mod_builds.md) (the master kit, MO2, the app),
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

<a id="unseen-controls"></a>**Sculpt controls no measure sees (2026-11-13).**
The base build of 2026-11-13 refit 2,130 faces after `FIT_VERSION` 3 → 4
(the worn head parts): the people stage took 714 s on 4 workers (memory
held it to 4 with the main process at 7 GB), against 63 s with the fits
cached. The sculpt fit was most of a face's time, all of it in
`proportions._solve`'s bounded least squares (`lsq_linear`), called about
250 times a face by the greedy preset search and the ridge doubling.
- Only 94 of the 224 male sculpt columns move any of the 19 measures. The
  others enter the objective only through their ridge, so their best value
  is 0; `_solve` now solves only the seen columns and leaves the rest at 0.
- Measured on one process, one BLAS thread, against the old solve on 116
  faces (the six references, three slices of the game's faces, women
  among them): every stored value (FMRS, presets) the same, so
  `FIT_VERSION` stays. The sculpt fit took 102.7 s before and 40.3 s
  after; women are slowest (1.70 s a face before, 0.63 s after).
- With the tint fit and head-part choice unchanged (about 0.35 s a face
  together), a refit costs about 0.7 s a face instead of 1.3 s *(estimate,
  not built)*.

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
- <a id="collision-pool"></a>**Collision, one record a mesh, in a pool
  (2026-11-12).** The warm build of 2026-11-12 spent 477.6 s in
  `collision` because every one of the 7,707 `elric_finish` entries
  missed: merge 31e28b34 had changed the hknp writer. Three things made that
  miss total and slow:
  - One `ran_while` covered the whole batch, so every entry's record named
    every function any mesh ran (234 keys): an edit to ragdoll or
    constraint code voided plain meshes too.
  - Every record also named `core/process_memory.py`, `eta.py` and
    `stage_timer.py`. sys.monitoring reports starts on every thread, and
    the memory sampler and progress threads run beside each capture.
  - The finish ran in the main process, one mesh at a time.

  *Built:*
  - `ran_code` keeps a start only in captures of the thread it ran on.
    While another thread holds a capture, a start is reported again, so
    that capture still sees it.
  - `ran_code.ran_alone`: a record of what ran in this call, plus what ran
    for the site earlier in this process in a file this call ran in, or in
    a file holding a functools-cached function the site ran
    (`cached_function`). That keeps a memo's work (`packfile.classes` and
    its size table) without other meshes' code. `ran_while` still keeps
    everything for its other sites.
  - `elric_cache.finish_one` finishes one mesh with its own record.
    `finished_each` runs the misses in worker processes (`pool_workers`, 512
    MB each) once there are `POOLED` (16) or more. A mesh only a new Elric
    run can finish raises `NeedsElric` in its worker (`cached_process`) and
    joins one `_batch` after the pool, so Elric still runs as one instance.
    Faults a worker meets come back with its result and are counted in the
    main process.

  Measured on a scratch copy, pre-Elric meshes taken from the build's
  `mesh_files` cache, empty work caches:

  | Meshes | Old (one batch, main process) | New (per mesh, pool) | Output |
  |---|---|---|---|
  | 300 | 36.4 s | 6.2 s | all 300 byte-identical, same failures |
  | 53 (3 our writer leaves to Elric) | 10.7 s | 5.5 s | all 53 byte-identical |

  A second pass over the 300 (all hits) takes 2.8 s. A box mesh's record
  now names 11 files, without `hknp_ragdoll`, `hknp_round`,
  `hknp_compound`, `anim_blocks` or `particle_blocks`; the old batch
  record named 18. Only 3 of the first 1,500 cached meshes need Elric.
  Worker memory: 82 MB committed after imports with the build's one BLAS
  thread (`configure_multiprocessing`), 18 MB more for the largest of those
  1,500; without that setting, numpy alone commits 501 MB.
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

**Status: built and measured 2026-11-11.** Measured on scratch copies of two
deployed mods, with each one's own build arguments: Strip Lights Region Fix
(master: the game) and Better Brotherhood (the game and five DLC). Every
time below is a stage line from a second, warm build. One profiled build of
Strip Lights found the causes. The plugin came out byte-identical to the
build before the change in every run: 4 Strip Lights builds and 2 Better
Brotherhood builds. Better Brotherhood's also equals the deployed plugin.

| Cost | Before | After | What it was, and the fix |
|---|---|---|---|
| `ledger and cleanup` | 27.9 s (Strip Lights), 147.5 s (Better Brotherhood) | 1.7 s, 17.1 s | See [cleanup](#fixed-cleanup). |
| Mesh cache check (`mesh cache: … ready`) | 32.8 s | 24.1 s | See [mesh check](#fixed-mesh-check). |
| Master meshes (`collision`) | 78.8 s | 19.7 s | See [master meshes](#fixed-master-meshes). Takes effect once the masters are rebuilt. |
| Script compile | 92.0 s on a first build | 3.0–3.7 s | Nothing to fix. See [compile](#fixed-compile). |

Strip Lights built in 755 s before and 541 s after, against a master with its
mesh record. Its Main archive went from 622 MB to 268 MB.

<a id="fixed-cleanup"></a>**`ledger and cleanup`.**
- **The cache prune.** `prune_caches` walked every file of the mesh, work and
  Elric caches on every build (10.8 s of 17 s profiled). Now
  `work_cache.prune` sweeps at most once a day; the time of the `pruned` file
  beside the caches says when. An unused entry still goes after 14 days, at
  most a day later.
- **Finding the files a build made.** `stale_files.made` stats each file
  again after listing it; now it uses the listing's own stat
  (`file_stamps.files_under`).
- **Dropping files a master already has.** This was the 147.5 s on Better
  Brotherhood. Old World Blues was built straight into its MO2 folder, so
  about 18,000 of its files sit there loose: gun animation data, meshes, rig
  files. Each build of a mod on it writes 18,076 copies of them. Then
  `master_copies.drop_loose` reads each one and the master's copy and deletes
  it. The reads wait on opening files (about 4 ms each here), so they now run
  in 16 threads. Same files dropped.
- Left: not writing those copies at all. Each writer (gun animation data,
  rigs) would have to ask the master first.

<a id="fixed-mesh-check"></a>**Mesh cache check.** The step sent all 6,628
scoped meshes to the worker pool. Each worker hashed the whole NIF, read its
code record and unpickled the entry to throw it away.
- Now `mesh_cache.warm` keeps a memo per export and setting
  (`meshes/warm/*.json`, `file_stamps`). It holds each NIF's cache key, under
  the NIF's size-and-time stamp, and the texture stamps from the last time a
  worker had it.
- A mesh whose entry exists, whose code record is current and whose textures
  are unchanged stays out of the pool. It is never unpickled.
- That check costs about 4 ms a mesh in opening the code record, so it runs in
  16 threads: 7–9 s for 6,628 meshes, against about 16 s in the pool.
- A wrong "kept" costs only time: the build's own `cached_files` checks every
  mesh fully and converts a miss itself.
- The rest of the line is `scope_models` (13–20 s). It makes the scoped
  worldspaces' `Exterior` objects, and `cell.build` makes them again from
  other reference lists. Not shared yet.

<a id="fixed-master-meshes"></a>**Master meshes.** "Written, given collision,
then deleted" was wrong. A master's loose meshes are not in its MO2 folder,
only its archives. So `drop_loose` found none of them, and every mod shipped
its masters' meshes again in its own Main archive. In Strip Lights that was
6,771 meshes, all byte-identical to the game's archive.
- Every build now writes `<plugin>.meshes.json` beside its plugin, and the
  deploy carries it. It lists each mesh the build ships as Elric finished it,
  by path: `elric_cache.mark`, the `elric_finish` entry's key and code-record
  digest, plus whether collision worked.
- A dependent build reads its masters' records (`master_copies.theirs`). In
  `_collision` it neither writes nor finishes a mesh whose master gives the
  same mark (`elric_cache.LEFT`), and it deletes any copy already in its
  folder. Steps after `_collision` can still read such a mesh:
  `mesh_bytes` returns its finished copy from the `elric_finish` cache.
  Before this, Dead Money's 2026-11-12 build crashed. A repair list in
  `_closing_records` made the lingerie outfit's armor, which reads its world
  mesh `fnv\armor\lingerie\go.nif` for texture swaps, and that file had
  just been left to the game's archive.
- The records count only when every master in another folder has one, the
  last master's winning. So a master built before this change cannot hide a
  different copy of the same path.
- Weapon meshes (dressed after Elric) and object LOD meshes (read by the LOD
  bake) are always built.
- **Measured:** the game's record was simulated (a hard-linked copy of its MO2
  folder, the record holding only meshes byte-identical to its archive).
  Against it, Strip Lights left out 6,771 meshes, and collision went from
  78.8 s to 19.7 s. Every other output file is byte-identical, the Textures
  archive included.
- **Not active until the game and DLC are rebuilt.** Until then their folders
  have no record, so nothing is left out.

<a id="fixed-compile"></a>**Script compile.** A second Better Brotherhood
build compiled 0 of 68 scripts in 3.0–3.7 s, so the 2026-11-10 stamp fix
holds. The overnight 41–174 s came from that run rewriting every dialogue
script. The first build into a new folder compiled all 68 in 92 s: 18 Caprica
runs, because 3 scripts have source errors and Caprica stops at each.

On FalloutNV.esm (2026-11-12) two builds in a row compiled all 16,189
scripts (67.8 s and 73.0 s). That looked like every build, but it isn't:
the next build compiled 1 of 16,189, and earlier ones 15 and 2. The second
full compile followed commit 37e74d8e, which dropped LevelUpMenuEx's
header folder from the import list. `saved_state` keeps no results across
another import list, header contents or Caprica, because those can change
any script's compile. The `.pex` files were there all along:
`restore_packed` brought back 77,355 loose files at the next build's
start. One edit to `TES4Polyfill.psc` with unchanged declarations
recompiled only that script.

| Cost | Seen before the fixes above | Lead |
|---|---|---|
| `base STAT` on Goodies | 796 s, then 157 s ([audit](#audit-2026-11-11)) | Not explained. |

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

#### <a id="spike-result"></a>What the spike found (2026-11-11)

**Verdict: go for step 7, with four changes to the journal design below.**
A replayed mod build is predicted to rerun 0.04–11% of the game's units and
about 1.5–5 minutes of their time. The old-way builds took 7.4 and 13.8
minutes. Every record the two test mods' plugins hold is made by a unit the
replay reruns, with one exception: a region-build artifact that a replay
rightly leaves out.

**How it was run.** `fo4_import.pipeline.read_log --no-assets` (it skips the
file-only steps and the Creation Kit; plugin bytes unchanged) recorded:
- one whole game build, `--world WastelandNV reached --whole`, into a scratch
  folder;
- Landscape Disposition Fix (LDF) and Strip Lights Region Fix (SLRF), each
  built the old way with its deployed arguments, the scratch game as master.

`tools.audit.read_log_report --check` then sorted every record of each mod's
plugin by the unit that packed it (see
[python_tools](../reference/python_tools.md)). A recorded and an unrecorded
one-cell build wrote byte-identical plugins.

**The game's recording.** 97,139 units, 494,334 records packed, 7.8 M
(record, field) reads kept per unit, plus 45.7 M in 226 shared whole-type
reads.

**The journal is small.** For the whole game:

| | Raw | Zipped |
|---|---|---|
| Reads by field | 242 MB | 3.3 MB |
| Reads by record only | 180 MB | 2.8 MB |

That counts the reads, the FormIDs each unit packed, the units each asked,
the questions and the unit names. Record bytes are the plugin's own (347 MB
packed). Whole-type reads are 129 MB raw but 0.2 MB zipped: they are runs of
consecutive records. Not yet measured: the memo and shared-list entries a
unit adds (Part D's [shared state](fo4_plugin_layout.md#shared-state)).

**Units each mod reruns:**

| | LDF | SLRF |
|---|---|---|
| Records changed / added | 2,135 / 1 | 6,171 / 7 |
| Units reading a changed record | 721 | 1,000 |
| Units reading a changed field (plus askers) | 527 | 6 |
| Rerun by field reads alone | 538 units, 173 s | 41 units, 83 s |
| Rerun with binary walkers (change 2 below) | 10,932 units, 312 s | 4,663 units, 212 s |
| Records in the old-way plugin | 2,247 | 130 |
| Made by a rerun unit / the master's own group head | 1,747 / 500 | 127 / 1 |
| Missed | 0 | 1 (an artifact, below) |

The seconds are each unit's own time in the recorded game build. Field-level
reads matter: SLRF changes 6,168 cells, and 1,000 units read them, but only
6 read a field that differs.

**Where the rerun time goes.** A few coarse units:
- `world WastelandNV` (96 s): one unit for the whole worldspace;
- the `quest scope` (89 s), `closing records` (41 s) and `scope` (8 s)
  stages: setup that reads whole types.

The 30 readers of every REFR are the 12 world scopes, five setup stages, two
memos and the `CellBuilder` init. Each can be asked as a narrower question
("REFR by FormID", "REFR where ParentCELL, XTEL.Door = …").

**Four changes to the journal design** (each found by a miss in the check):
1. **A record belongs to the unit that packs it** (`writer.pack_record`), not
   the one that adds it. 78% of records were added by stages assembling
   groups (a quest's topics, an interior's references) after their units ran.
2. **Binary source walks must log per record.** Cell region lists
   (`regions.py`: XCLR through `source_walk`) and worldspace subrecords
   (`exterior.py`) come from the source plugin's bytes. The recorder logged
   only "walked CELL", so 2 CELL and 1 WRLD overrides of LDF and all 92 CELL
   overrides of SLRF were made by units nothing flagged. Counting each walker
   as a reader of every changed record of its type closes the gap. It is
   coarse, though: it is the jump from 538 to 10,932 units.
3. **Cell membership is a question.** LDF moves 8 REFRs to another cell. The
   new cell's unit never read them in the game build, since its references
   come from an index built once. "The REFRs whose ParentCELL is X" has to be
   recorded with its answer.
4. **The coarse units need splitting** before replay pays: the worldspace by
   cell, the setup stages into questions. Without that, a landscape mod
   reruns about 5 minutes; with it, likely under 2 (not measured).

**The byte-for-byte bar needs one adjustment.** SLRF's single miss is a TERM
copy that is unreferenced in the old-way plugin. The region build copies
master terminal `001672C6`, reached from `NellisArrayTerminal`, because the
game plugin left it out (`COPY_SITE`). The game build's own unit makes no
such copy. LDF's region build also made 3,651 master records differently
from the game "by the build alone" (dropped), even against a game built from
the same code. So the reference for step 7 should be the old way with its
region artifacts removed, or an old-way build at the game's own scope, not
the region build as it is.

**Recording cost.** About 28% on the record-making stages (1,201 s against
937 s for the same stages of the 11-11 overnight game build: other commit
and caches, so rough). The read-heavy stages cost 2–3 times as much
(`base STAT` 255 s against 104 s, `quest scope` 104 s against 37 s). On one
cell: 360 s against 346 s.

**Memory (separate finding).** In the game build,
`land_layers.limit_textures` (via `blend_borders`, `_shared` over every
border vertex of WastelandNV) takes the build from about 7 GB to over 15.5 GB
in 90 s. With `TESCONV_JOB_MEM_GB=16` the recorded game build died there
twice. It finished under 22 GB (14.7 GB sampled every 30 s); LDF peaked at
8.3 GB. Normal builds run uncapped.

<a id="land-memory"></a>**Fixed: the land texture step's memory.** The cause
was `blend_borders`, not `limit_textures` itself. At every vertex several
quadrants share, it gave each quadrant a 289-value array for every texture any
of the others had there, zero-filled where the quadrant had none. Because it
changes the mixes while it walks them, textures spread from quadrant to
quadrant. On WastelandNV (16,388 cells with land, 65,552 quadrants) that made
2,555,118 arrays, about 39 per quadrant and about 6 GB; `limit_textures` then
summed all of them. Now a texture a quadrant gains with a share of +0
everywhere points at one shared read-only zero array (`ZERO`), and gets an
array of its own only when a nonzero (or -0) share is written to it. The dict
keys and their order stay the same, because `kept_textures` can still fill a
slot with a zero-sum texture. `limit_textures` sums only the kept textures.

Measured on the real WastelandNV inputs, the step called directly on its land
data in a child process capped with `limit_own_memory` (16 GB), memory being
the process commit:

| | Before | After |
|---|---|---|
| Commit after loading the land | 4.33 GB | 4.33 GB |
| Peak after the step | 12.41 GB | 6.44 GB |
| The step's own peak | +8.1 GB | +2.1 GB |
| `blend_borders` | 61–84 s | 65 s |
| `limit_textures` | 22–28 s | 17.5 s |

The output is byte-identical: the SHA-1 over every cell's, quadrant's,
texture's shares from `limit_textures` is the same before and after. About
1.5 GB of the step's remaining peak is the `_shared` vertex index. With about
6 GB less, the game build, at about 7 GB before this step, should peak near
9–10 GB, under 16 GB; the next whole-map build confirms it.

**Estimate for step 7 (unmeasured, from the numbers above).** LDF by replay
is about 3–5 minutes as the units stand, against 7.4 minutes; SLRF about 2–4,
against 13.8. That is 2–4 minutes of reruns (less the 28% recording cost),
plus mesh checks, setup and ledger work over the mod's records only. With
change 4, both should be inside 1–2 minutes. Size: the journal L, as
planned, plus M for changes 2–4.

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
- **Fixed (2026-11-11): the overlay check's memory.** On
  `tfssspacestationext.nif` (61 MB), the distance test asked for 3.88 GiB
  per 256-point chunk over its 677,436 triangles
  ([station](research/fnv_nif_reader.md#station)). It now tests groups of
  nearby points against the triangles that can reach them, in 6 MB blocks
  ([overlay-layers](fo4_pipeline.md#overlay-layers)); output is unchanged.
  The 25 largest FO3/FNV/Frontier meshes, each converted alone under a
  4 GB cap:
  - **Station:** 35 s, 1.0 GB peak.
  - **Others:** at most 788 MB (`tfliberatorairshipscol`).
  - **Both motherships:** 7 s, 390 MB.
  - **Six Frontier meshes stop on the open Havok fault above** (motion
    system 205 or 154): `tfssrotatingtuberoom`,
    `tfscolmarketbuildingcomplete`, `tfanalgesisscol`,
    `tfscolwhitebuildinggroup01`, `tfscoldestroyedbuilding02`,
    `tfscolwsfactory03b`.

**Ready for a scoped retry.** The one per-mesh memory blow-up measured is
fixed. The whole-world freeze was never pinned to a step, and the main
process holding 589,612 references remains a suspect. So retry with a
scoped build first: one small area, fewer workers and a job cap around
12 GB.

### <a id="audit-2026-11-12"></a>Two stages that slowed down, 2026-11-12 (V)

The 2026-11-12 overnight base build took 32 min, but two stages grew. All
times below are under cProfile, on scratch copies of `temp/profile_data`'s
`FalloutNV.esm` and `FalloutNV - Main.ba2` (clips read through the archive)
and of the `anim offsets records` work cache.

#### <a id="anim-data-2026-11-12"></a>Animation data: 1,039.5 s to about 45 s warm

**Cause (measured).** `anim_text.compute()` ran once per entry: 3,913 entries
in the base game. Each call did three expensive things:
- read the 14.6 MB records table from the work cache again (0.1–0.3 s);
- stored the whole table again when it added a clip;
- started and stopped its own process pool when it had 16 or more new clips.

On the old code, the entries step took 990.6 s (the overnight build: 1,039.5 s).
Of that, 687 s was tearing down 293 pools.

Separately, `ba2_pack.data_file` built a new `Archive` for every read of a
file that is only in an archive, re-parsing the 150,202-entry index of the
5.1 GB Main each time. That hits creature graphs and clips once they are no
longer loose, and a DLC reading its master's clips.

**Fix.**
- `Known.table`: the table is read once per run, and `anim_text.save()`
  stores it once.
- `entry_files`: computes every entry's clips in one `compute()` (one pool),
  each spelled as the first entry names it, as before.
- `ba2_pack._archive`: each archive's index is kept per path, size and time.
- `anim_offsets.pack_string` and `anim_text._stem` are memoized.

| Step (s) | Old | New, cold | New, warm |
|---|---|---|---|
| vanilla, copies | 18.7 | 16.1 | 17.3 |
| creatures | 10.4 (100 in the 11-12 scratch run, archive per read) | 6.1 | 3.2 |
| entries (3,913) | 990.6 | 136.6 | 22.1 |
| Honest Hearts entries (302, master clips via the archive) | 115.0 | 25.2 | — |

- **Output unchanged:** all 4,018 computed files and the copied-entry list
  hash the same for old, new cold and new warm. Honest Hearts' 302 do too.
- **Not done:** keying the table by archive stamps instead of hashing. Warm,
  reading and hashing every clip costs about 7 s.
- **One cold run to come:** the `anim_offsets` edit changes the identity of
  the code that made the table, so the next build computes all ~19,000 clips
  again (about 2 min).

#### <a id="main-archive-2026-11-12"></a>Main archive: 36 s to 138 s is the disk

From 36.0 s (2026-11-11, 122,107 files) to 138.2 s (2026-11-12, 150,202
files, 5.08 GB).

**Where it goes.** `write_general` writes the whole archive again on every
build that changes anything. The 11-12 build touched 69,069 of its files
(2.25 GB):
- AnimTextData: 19,588 files, 1.21 GB;
- meshes: 29,515 files, 1.02 GB;
- scripts: 15,983 files;
- materials: 3,983 files.

Those files are read loose. The 75,166 sounds (2.65 GB; voices are 72,785
of them, 2.54 GB) were untouched, so they are block-copied out of the old
archive.

| `pack_main` on the scratch folder | Old | New |
|---|---|---|
| cold: every file read loose | 180.7 s | — |
| non-sound files touched (75,036), sounds kept | 213.5 s | 124.6 s |
| nothing changed (stats and the record only) | 14.4 s | 17.5 s |

The touched-case gap between old and new is mostly disk load, not the code.
- In the 213.5 s run, `write()` into the temporary archive took 145 s.
- Raw 16 MB-block writes to the same folder ran at 49–95 MB/s, with the
  overnight queue on the same NVMe drive.
- In the unchanged case, the same 150,203 `stat` calls took 5.5 s, then
  12.8 s.

So the stage is about writing 5 GB: it is inherent while one archive holds
everything. Why the 11-11 run took 36 s was not measured: page cache, or
less disk load.

**Fixed (Python overhead, about 7 s of every pack, and more on a repack).**
- `_tree` computes paths per folder instead of `relative_to` per file.
- `pack_main` passes its stat sizes to `write_general`, so each file is
  stat'ed once, not twice.
- The archive is unchanged: SHA-1 `e87c5e25…` from both old and new code.

#### <a id="textures-rewrite-2026-11-12"></a>Textures archive: 138 s was loose writers with new dates

**Cause (measured).** The 2026-11-12 base3 build spent 138.3 s in "FaceGen
and texture archive", writing the whole 4.8 GB `- Textures.ba2` again; base2
spent 46.7 s, when the archive was smaller. The pack record's dates show
base3 wrote only six textures: the super mutant tints in `fnv/tinted/`.
- `creature_tint.tinted_materials` writes its DDS files loose into the Data
  folder's `Textures` every build, and `own_heads._write_texture` goes
  through `write_new`, which touches a file with the same bytes.
- `pack_textures` then moved each loose texture into staging with its new
  date. The `[size, mtime]` state changed, so all 22,674 textures were
  written again for six unchanged ones.

**Already fixed** by the same-bytes rule in `_move_loose`
([faces-repack](fo4_pipeline.md#faces-repack)): a loose texture whose staged
copy has the same bytes is deleted and the staged copy keeps its date. Base4
(commit `b60c5931`, which has it) took 8.7 s for the stage. Drawing the
`sm3d1024_d` super mutant tint twice gave byte-identical DDS and BGSM files,
so the rule holds for that writer. A real change to any texture still
writes the whole archive, at this drive's write speed.

#### <a id="worlds-profile-2026-11-12"></a>Worlds stage: the land texture step is most of it

The worlds stage took 134.9 s in the warm base3 build (236.1 s cold), its own
time only: navmesh, object LOD and placed references are their own stages.

**The land texture step, profiled alone** on WastelandNV's real inputs: an
`Exterior` built from the export with no references, its mixes made as
`Exterior.group` makes them. 16,396 cells, 16,388 with land, 65,552
quadrants.

| Step | Time | Under cProfile |
|---|---|---|
| Loading cells, land and LTEX from the export | 10.3 s | — |
| `quadrant_mix` | 8.2 s | — |
| `blend_borders` | about 65 s (land-memory measurement) | 192.9 s |
| `limit_textures` | about 17.5 s | 36.6 s |

So the step is about 82 s of the 135 s. Of 229 profiled seconds:
- `blend_borders`' own loop 83.7 s, plus 84 million `sum` calls (75.8 s
  with their generators), 171 million `dict.setdefault` (17.3 s) and 76
  million `math.copysign` (6.3 s). That is one pass per shared border
  vertex, each texture averaged over the quadrants on it in Python.
- `_shared`, the border vertex index, 15.3 s for its two calls (once in
  each function).
- `limit_textures`' own work 8.0 s, its `max`/`sorted` per vertex 7.6 s,
  `numpy.delete` 3.9 s.

The step reads only the export's LAND and LTEX records, which a warm build
does not change, and makes the same output every build.

**Two ways to cut it:**
- *Cache the step's output per worldspace:* built, see
  [land-cache](#land-cache) below.
- *Vectorize `blend_borders` (not built).* It must give the same dict keys in the same
  order: a quadrant gains a texture key with a +0 share where a neighbor
  has the texture, and that key then spreads on through later shared
  vertices in visit order (ties in `kept_textures` follow key order). That
  makes an exact numpy version harder than the averaging itself.

**The other about 53 s** is not profiled yet. The next build run with
`F3NV_PROFILE_STAGES=worlds` ([stage-profile](fo4_plugin_layout.md#stage-profile))
writes `temp/stage_profiles/worlds.txt` with the whole stage.

<a id="land-cache"></a>**The land texture step is cached (2026-11-12, not yet
built).** `land_layers.land_textures` runs `quadrant_mix`, `blend_borders`
and `limit_textures` for a worldspace's land through `work_cache.cached`
(site `land textures`), and `Exterior.group` calls it. The key is a SHA-1
over the grassy texture set and, per cell in grid order, every LAND field
`quadrant_mix` reads (`LayerCount` and the `Layer[...]` fields). A height
or any other field leaves it, and the code record covers the code. It is
exact for a DLC too, since it keys on the layered records `Exterior`
holds, not on an export file.

Measured on WastelandNV's real inputs, the cache on D::

| Run | Time |
|---|---|
| The old call | 92.1 s |
| `land_textures`, empty cache (made and stored) | 106.6 s |
| `land_textures`, cached | 5.1 s |

The three outputs pickle to the same bytes. The entry is 461 MB. The first
run's 14.5 s more is recording the code that ran and writing the entry.
A warm build saves about 87 s of the worlds stage, and the step's memory
peak (about 2 GB, [land-memory](#land-memory)) with it.

#### <a id="voices-archive"></a>Voices in their own archive (built 2026-11-12)

**What changed.** `ba2_pack.pack_main` now packs two archives:
- `<plugin> - Voices_<language>.ba2`: the staged `Sound/Voice`. This is one
  of the three suffixes `Fallout4.exe` loads for a plugin
  ([main-archive](fo4_pipeline.md#main-archive)); the DLCs ship
  `DLCRobot - Voices_en.ba2` the same way.
- `<plugin> - Main.ba2`: everything else, as before.

How it works:
- Each archive keeps its own record, so the voices archive is rewritten only
  when a voice file changed.
- Every caller gets the split: the build, the faces stage's repack, the asset
  overlay and DLC and mod builds, each in its own Data folder.
- `drop_packed` covers the voices archive (`own_archives`).
- `restore_packed` restores only Main's meshes, materials and scripts; voices
  never sit loose in the Data folder, since they are staged outside it.
- Deploy copies the new archive like any top-level file. The rebuilt Main
  no longer holds voices, so an existing install ends with each voice in one
  archive (`test_fo4_deploy`).

**The language.** `install.game_language()` reads `sLanguage` from the game
folder's `Fallout4_Default.ini`, which Steam writes for the installed
language (`en` on this machine). It defaults to `en`.
- When the language changes, `pack_main` deletes the old language's voices
  archive and its record. Deploy then lists it as stale (`--delete-stale`
  removes it).
- **Drift from FNV:** the game loads only `Voices_<its sLanguage>`. A build's
  voices play only in the language the building machine's game is set to.
  A build shared with a player whose game uses another language plays no
  voices until it is renamed to their language.
- A `sLanguage` set only in the player's own `Fallout4.ini` (Documents or
  an MO2 profile) is not read.

**Shown on the scratch folder** (a copy of the 11-12 base build, 150,202
files):
- **Same files:** the scratch rebuild of the one-archive layout matches the
  real build's archive (SHA-1 `e87c5e25…`). After the split, each of its
  files is in exactly one archive with the same bytes: 77,417 in Main
  (2.55 GB), 72,785 in the voices archive (2.54 GB).
- **First build after the change:** 110.2 s. Main is rewritten without
  voices, and the voices archive is written from the staged files.
- **A build where no voice changed** (all 75,036 meshes, materials and
  scripts touched, as a build does):
  - writes 2.55 GB instead of 5.10 GB;
  - leaves the voices archive untouched (same SHA-1 `28f512b8…`, same time);
  - so deploy does not copy it again.

| `pack_main`, no voice changed | Time |
|---|---|
| one archive (old code) | 66.9 s |
| split, run 1 | 50.8 s |
| split, run 2 | 62.2 s |
| split, nothing changed | 12.1 s |

The halved write is certain. The wall-clock gain is within this disk's
noise while the overnight queue shares it: the same old-code case measured
124.6–213.5 s earlier in the day.

### <a id="weap-profile-2026-11-13"></a>The item WEAP stage, profiled (2026-11-13)

The 07:40 base build ran with `F3NV_PROFILE_STAGES=item WEAP`
([stage-profile](fo4_plugin_layout.md#stage-profile)): 100.1 s, 90 s of it
under `Guns.templates`. Shares overlap; the profiler slows pure Python more
than file calls.

| Part | Time |
|---|---|
| Clips (`_clips`: the guess pass 50 s, the pool warm-up 38 s, `GunClips.convert` 21 s) | 65 s |
| NIF reads (`read_tri_shape`, 2.9 million vertices, 24 million `Reader.take` calls) | 25 s |
| Cache files: 88,821 opens, 50,045 existence checks, 66,079 time stamps | about 25 s |
| Building the gun meshes (`nif.gun.gun`, `_merge_shape`) | 19 s |
| `copy.deepcopy` (14 million calls on 2,374 objects) | 8 s |

<a id="gun-parses"></a>**Three fixes (2026-11-13, not yet in a build).**
- **Shared parses.** A gun's converted mesh was parsed three times per gun
  and its receiver four (`fnv_layout`, `placement`, `gun`, `receiver_bones`,
  `pieces`). The readers that never change the NIF now share
  `gun.parsed()` and `gun.stripped()`, which keep the last 8 parses;
  `gun()` and `without()` still read their own copy, since they change it.
- **A lighter shape copy.** `_merge_shape` deep-copied the source shape,
  vertex dicts included, then replaced the vertices. It now copies every
  other field and reads the vertices from the source.
- **Fewer file calls per cached clip.** `work_cache.has_bytes` and
  `stored_bytes` check that the entry and its code record exist instead of
  reading and parsing the record, which is always empty for these entries.
  `current()` stats the entry once, and `mark_used` sets an entry's time
  only when it is a day old or more: `prune` counts whole days, so an entry
  any build used within 14 days still stays. `write_new` stats its target
  once.

The NIF block readers themselves (`Reader.take`, `read_tri_shape`,
`read_vertex`) were left alone, though vectorizing them is the bigger win.
They are in the code records of the FaceGen, Elric-finish and shape-material
caches (`own_face`, `sculpt_fit`, `tint_fit`, `head_parts`,
`elric_finish`), so any edit to them rebuilds all of those. So are
`work_cache.current_ran`, `ran_path` and `write_ran` (in 117,799
`mesh_files` records), which this change keeps as they were.

**Measured** (scratch harnesses, a build running at the same time):
- **The gun calls** of a build (`fnv_layout`, `draws`, `placement`, `gun`,
  `receiver_bones`, `pieces` of both NIFs, `receiver_layout`, `mesh_top`)
  on all 113 FNV guns with a mesh, each on a vanilla receiver: 22.95 s
  before, 19.42 s after; every output pickles to the same bytes.
- **The cache replay** of 3,000 copied `gun_clip_files` entries (`has_bytes`,
  `stored_bytes`, `write_new` onto unchanged files): 1.40 s before, 0.85 s
  after, the same values. A whole-map build replays about 21,600 of them.

### <a id="goodies-profile-2026-11-13"></a>Goodies.esp's stages, profiled (2026-11-13)

Goodies masters every New Vegas DLC, so its build makes much of its
masters' content again ([replay](#replay)). Profiled stages (the
profiler slows Python, so shares rather than seconds), from
`temp/stage_profiles_goodies`:

| Stage | Profiled | Where the time went |
|---|---|---|
| people | 206 s | creature bases 88 s (worn items 38 s, own rigs 32 s); `face_fits.fit_key` 57 s, 36 s of it `plugin_sources` rebuilt per NPC; 55 million `deepcopy` calls, 24 s of them `source_registry.load` copying the registry on each of 34,678 reads |
| item WEAP | 122 s | as the base build ([weap-profile](#weap-profile-2026-11-13)), before that fix |
| base STAT | 92 s | 1.1 million file-existence checks (47 s): `copy_texture` (33 s, 41,214 calls) and `_source` (11 s) look each texture up through every export layer, even when the run already staged it; `cached_files` 32 s |
| closing records | 36 s | 40 idle clips written (`human_clip.write`, 23 s) |
| animation data | 34 s | parsing 3,154 offsets files (18 s) |
| worlds | 27 s | land records 12 s, placement 9 s |
| item ARMO | 23 s | headgear and outfit fitting |

<a id="staged-first"></a>**Three fixes (2026-11-13, not yet in a build).**
- **A texture already staged this run is skipped first.** `copy_texture`,
  and `stage_files`' textures, specular and glow maps, ask
  `ba2_pack.staged` before finding their source; `stage_texture` makes the
  same check, so nothing written changes.
- **The head-part chain once per export.** `fnv_npc.head_parts` rebuilt
  `plugin_sources` and merged every plugin's head parts per NPC;
  `_head_chain` does that once.
- **Voice folders once per export.** `voice.fnv_folders` keeps each export
  plugin's voice root (`_voice_roots`).

Left alone because they are in cache code records (any edit rebuilds those
entries): `Layered.path`, `export_file`, `plugin_sources` and
`source_registry.load` / `directories` (`mesh_files`, `meshes`, 299 of 300
sampled). `fnv_npc.head_parts` is only in face-fit entries from before the
fits were versioned; every entry a build looks up now has an empty record.

**Measured** on Goodies.esp's export (scratch harness, old code against
new):

| Work | Old | New | Same output |
|---|---|---|---|
| `head_parts` for all 4,232 NPCs of the chain | 11.68 s | 0.01 s | yes |
| `fnv_folders` x 760 | 1.44 s | 0.00 s | yes |
| `write_assets`, 250 statics, textures new to the run | 4.39 s | 4.62 s | yes: 918 files, bytes, faults |
| the same again, textures already staged | 1.79 s | 0.94 s | yes |

Not changed yet: creature bases and outfits in the people stage, and
`cached_files` in base STAT, which are master content a mod build makes
again; that is [section 5](#replay)'s work.

### <a id="mesh-pool-profile-2026-11-13"></a>The mesh pool's work, profiled (2026-11-13)

What one pool worker does per mesh (`convert_static.convert`, as
`cached_convert` calls it, then `mesh_files`), run in one process on a
seeded sample of 300 of FalloutNV.esm's 7,973 placed and item models
(scratch `meshprof.py`; no cache read or written). Creatures, outfits and
heads go through other converters and are not in it.

**Per mesh, unprofiled:** 39.8 s for the 300, none failed. Median 37 ms,
p90 247 ms, max 5.1 s. The slowest 8 take 45% of the time. At that rate
the 7,973 meshes are about 18 CPU-minutes, about 70 s on 15 workers.

| Slowest | Time | Vertices |
|---|---|---|
| `scol\scolfreesidetrainstation01b.nif` | 5.10 s | 12,292 |
| `scol\scolcheckpointfreeside01b.nif` | 5.05 s | 12,441 |
| `architecture\suburban\houseruined01.nif` | 2.36 s | 14,280 |
| `architecture\hooverdam\nvhooverdamoverpass.nif` | 1.49 s | 19,115 |
| `architecture\generic\trainyardterminal.nif` | 1.39 s | 29,133 |

**Profiled** (78.5 s under the profiler):

| Part | Cumulative | What it is |
|---|---|---|
| Collision triangles (`collision._mesh_soup`, via `_stair_ramps`) | 49.1 s (65%) | |
| - winding repair (`repair_inverted_floors`) | 27.0 s | a nearest-face search per suspect triangle (20,589 `_nearest_says_inverted`), plain Python: 15 million `math.dist`, 15 million `round` |
| - the repair's visual triangles (`repair_oracle` → `visual_tri_soup_in`) | 14.0 s | rebuilt for every collision body of a mesh, then moved one vertex at a time |
| - stairs | 4.3 s | |
| Shapes (`_shapes`) | 22.5 s (30%) | vertex packing (`emit`, `vertices`) 9.4 s; reading geometry (`_geometry`) 9.5 s, 4.3 s of it 8.9 million per-element numpy-to-Python conversions in the reader (`fnv_schema` row getters); materials 2.6 s; overlay layers 4.7 s |
| Collision blocks (`collision_object`) | 1.1 s | |

**The two SCOL outliers** each have 55 collision bodies.
`visual_tri_soup_in(root, node)` calls `_visual_tri_soup(root)` per body,
so the whole mesh's visual triangles are gathered 55 times (7.3 of the
mesh's 11.3 profiled seconds). The soup depends only on the root.

**What this says about a native converter.** Two thirds of the time is the
collision repair, not NIF reading or writing, and much of it is avoidable
work before any language change:
1. Gather the visual triangles once per mesh, not once per body.
2. Do the nearest-face search on arrays (or a spatial index) instead of
   per-triangle Python. It must stay bit-exact: the soup is compared
   against a trust radius, so a different rounding flips different
   triangles (`_transform_verts`' docstring). Elementwise numpy in the same
   operation order as the Python sums gives the same doubles.
3. Hand geometry to the converter as arrays from the reader instead of
   per-element Python values.
4. Pack vertices per shape as arrays (`vertices`, `emit`).

Each changes code in the mesh cache's code records, so each makes the
mesh cache rebuild once; landing them together, with the export-layer
index, costs one rebuild. The collision repair is shared with the Skyrim
converter (`asset_convert/collision`), whose tests would cover it too.
Native code is worth sizing again only after these.

<a id="still-bodies-skip-repair"></a>**Done first: no repair for still
bodies.** A fixed or keyframed body's mesh gets both sides
(`collision.both_sides`), so the repair's winding choice never reaches
the game ([two-sided collision](fo4_pipeline.md#two-sided-collision)).
`_mesh_soup` now takes the authored soup (`asset_convert`'s `mesh_soup`)
for those bodies and repairs only dynamic ones.
- `convert` over 200 sampled placed meshes: 24.3 s → 11.3 s, single process.
- The stair pass took each riser's diagonal from its tread's winding;
  `stairs._ordered` now orders each edge's ends by coordinate.
- Over 500 sampled meshes (seeds 1 and 2, 435 collision meshes) every
  written collision mesh holds the same triangles, both windings, as with
  the repair. Up to 28 entries per mesh differ only in material: a riser
  the stair pass adds over an authored riser face. Before, each side kept
  both faces, one with the base material and one with the stairs material.
  Now the added riser's front faces out and the authored face backs it.

<a id="mesh-pool-arrays"></a>**Then: arrays and once-per-mesh work.**
Same sample code (`convert`, then `mesh_files`, single process). Every
`MeshFiles` field hashed against a baseline from the code before these
changes, on 300 (seed 1) and 600 (seed 2) meshes: none differ.

| Change | Where |
|---|---|
| Positions, normals, UVs, colors taken from the reader's columns, not one row object per vertex | `convert_static._fields` |
| Normal, tangent and color bytes rounded in numpy (`rint` is `round`'s half to even; NaN held as `min`/`max` hold it) | `convert_static.vertices` |
| Vertices and triangles packed as one structured array; a value `struct` would refuse or pack differently (NaN, out of range, a float for an integer, skin, eye data) falls back to `pack_vertex` | `blocks._vertex_array` |
| NIFs with an `NiTransformData` read with our reader: an empty key group's default looked up nif.xml's `Float`, pyffi's `float`, so 12 of 300 files fell back to pyffi | `fnv_schema.pyffi_type` |
| A normal map's spec-mask verdict kept per file, size and time (804 checks, 367 maps in the sample) | `convert_static._spec_masked` |
| The stair cover test's per-face terms worked out once per body; three reaches per edge tested together | `stairs.cover_frame` |
| Authored collision normals read only for the repair | `mesh_soup(normals=)` |
| One parent map per mesh, not one per shape (four copies folded into one) | `fnv_file.parent_map` |

- 300 meshes: 16.7 s → about 6 s (5.6 to 6.2 s across runs).
- 600 meshes: 41.0 s → 12.1 s.
- Profiled, 300 meshes: 31.2 s → 9.2 s. No single stage now passes 1.2 s:
  collision about 3 s in all (the stair pass 1.2, the collision soup 0.9),
  the specular scans 0.9, `_geometry` 1.1, `emit` 1.1.

## <a id="open"></a>Open questions

- Publish face fits as a release asset of this repository, as the navmesh
  cache is? (Our numbers and Fallout4.esm FormIDs only.)
- Is shipping patches against the user's own files wanted as a later option,
  or ruled out?
- ~~How large is the journal for the whole game?~~ About 3.3 MB zipped
  (242 MB raw) with reads by field, before memo and shared-list entries
  ([spike](#spike-result)). It can ship compressed beside the plugin. Still
  open: ship it, or let the user's game build write it? Recording costs that
  build about 28%.
- Should step 7's byte-for-byte reference be the old way at the game's own
  scope rather than the region build? The region build makes records the
  game build does not (an orphan TERM copy in Strip Lights;
  [spike](#spike-result)).
- A mod converted against one release's journal and a game rebuilt with
  another: the same question as in
  [mod builds](fo4_mod_builds.md#open).
- <a id="native-candidates"></a>**Idea, not started: profile first, then move
  the plain-Python hot spots to native code.** A wholesale move off Python
  would not pay: the measured wins so far came from work done once instead of
  many times, not from language speed ([routes not taken](#left-out)). Profile
  one whole base build split into plain Python, numpy and waiting (files, the
  Creation Kit), and look at a stage only when plain Python dominates.
  Candidates already in view:
  - **The export index's memory.** Some pool tools load about 2.1 GB per
    worker, a copy per process. Options: a compact memory-mapped store that
    all workers share, or Python 3.14's free-threaded build so workers share
    one copy (only if numpy and the other libraries support it).
  - **Mesh reading and writing.** Move the inner loops of our NIF reader into
    `native/` beside `nifgeom`. The Frontier needed 982 s for 13,625 meshes,
    and one 61 MB mesh used 738 MB to read with pyffi.
  - **Per-item maths over large sets:** AnimTextData's 19,149 clip records
    (about 2 min on a first build: [measured](#anim-data-2026-11-12)), the
    overlay check, collision.

  The cost: every native part must be built and shipped for each platform the
  app supports. Wait until the Creation Kit replacements have been measured
  in real overnight rebuilds.
