# Build resources: memory per stage, one resource setting, time estimates

**Code:** `core/build_resources.py`, `core/process_memory.py`,
`fo4_import/pipeline/stage_timer.py`, `fo4_import/pipeline/eta.py`,
`fo4_import/pipeline/eta_inputs.py`, `tools/release/machine_benchmark.py`,
`tools/release/fit_build_eta.py`; the model is `fo4_import/data/build_eta.json`.

Related: [build speed](fo4_build_speed.md) (what the stages cost and why),
[stage times](fo4_plugin_layout.md#stage-times), [build stamp](fo4_pipeline.md#build-stamp),
[mesh worker memory](fo4_build_speed.md#worker-memory), [face pool](fo4_build_speed.md#face-pool).

The goal: a build that a lower-end PC can run, and a time to expect before
and during it. Raw speed on the build machine is not the goal.

## Contents

- [Memory per stage](#stage-memory)
- [The main process on a 16 GB PC](#lean-main)
- [One resource setting](#profiles)
- [Estimated time](#eta)
- [The machine benchmark](#benchmark)
- [The fit and its error](#fit)
- [Disk space](#disk)
- [Still open](#open)

## <a id="stage-memory"></a>Memory per stage

**How it is measured.** `stage_timer.sample()` starts a thread when the build
starts. Every 0.5 s it reads:
- the main process's committed memory (private bytes, `K32GetProcessMemoryInfo`);
- the same for every other process in the build's job object
  (`QueryInformationJobObject`). These are the pool workers and the tools the
  build starts (Caprica, LipGen). Elric and the Creation Kit, which broke
  away from the job, no longer run (2026-11-24).

Each reading goes to the innermost stage running at that moment, as stage
times do. Per stage it keeps the main process's peak, the workers' summed
peak, the largest single worker and the most worker processes seen. A stage
shorter than 0.5 s may get no reading. Off Windows nothing is read and the
lines carry times only.

**Where it shows.**
- The log: `stage people: 58.6s, peak 7.12 GB main, 3.20 GB in 8 workers`.
  The `stage total` line carries the whole build's peaks.
- The stamp, `<plugin>.build.json` ([build stamp](fo4_pipeline.md#build-stamp)),
  on a finished or failed build:
  - `stages`: `{name: {seconds, peak_main_gb, peak_workers_gb, largest_worker_gb, workers}}`.
    `outside stages` holds what was read between stages.
  - `counts`: every count the build prints, plus `meshes in scope`,
    `meshes converted`, `scripts changed`, `scripts` and
    `plugin has masters`. These are what the [estimate](#eta) reads.
  - `resources`: the profile, the logical cores and the memory.
- The mesh cache step is now a stage (`mesh cache`), so stages add up to the
  whole build.

**Measured** (CaravanPack scratch builds, cold cache) in
[the byte check](#same-bytes). The worker figures count every other process
in the job during the stage, including a pool that is still shutting down.

## <a id="lean-main"></a>The main process on a 16 GB PC

**The problem.** A whole FalloutNV.esm build (f3nv-0.3 code, desktop, 2026-11-23
stamp) peaked at 10.95 GB in the main process. A 13.7 GB laptop thrashed in it.
Main-process peaks by stage, highest first: animation data 10.95, plugin write
9.51, the archives and ledger about 9.4, worlds 9.07, placed references 8.79,
base STAT 8.74, item ARMO 8.67. The stamp keeps only peaks, and a stage nested
in another shares its readings, so an item stage's peak may come from either.
The floor rose from 1.05 GB (script conversion) to 4.51 GB at the mesh cache and
never came back down.

**What held it**, each measured in a probe process on the real FNV export and
the built 0.3 plugin (commit over the probe's start):

| Holder | Held |
|---|---|
| The parsed export, every type file, as `export_index` keeps it | 3.00 GB, LAND 2.17 and REFR 0.52 of it |
| LAND, read by `Exterior.__init__` in `run.scope_models` (before the mesh cache) and cached to the end | 2.17 GB of the above, for the whole build |
| The animation data stage: every offsets file (11,040 files, 1,389 MB) in one dict before the first write, and every clip's bytes (0.34 GB) at once to hash them | +2.30 GB held, 2.44 GB peak |

<a id="lean-export"></a>**Fix 1: leaner records.** `text_reader.parse_record_block`
interns each key (`Layer[0].VT[12].Pos` was a new string in every LAND
record) and, per file, keeps one object per value text (`1.0`, `0`,
`ALPHA`). The dicts are equal; a digest over every record of the FNV export
is the same before and after. Parsing the whole export takes 12.3 s instead of
8.5 s.

**Fix 2: LAND only while it is used.** `Exterior.land` reads the land on
first use: the people stage (an actor lifted onto the ground) or the worlds
stage. Every worldspace shares one read (`exterior.land_of`), parsed by
`export_index.fresh_records`, which no cache keeps. `cell._world_groups`
calls `drop_land()` after the last worldspace. Nothing reads land after it,
and a later read would only parse it again.

| Same input, probe on WastelandNV | HEAD | Changed |
|---|---|---|
| Whole export parsed and held | 3.00 GB | 1.31 GB (LAND 0.97, REFR 0.21) |
| After the scope step's `Exterior` (to the mesh cache and every item stage) | +3.01 GB | +0.49 GB |
| While its land is in use (people to worlds) | +3.01 GB | +1.46 GB |
| After the worlds stage | +3.01 GB | +0.49 GB |

Every grid's land is the same (digest over the 16,396 cells' records).

<a id="lean-anim-text"></a>**Fix 3: animation data one file at a time.**
`anim_text.entry_files` gives each offsets file as a `functools.partial`.
`anim_text.write` makes it as it writes it, so only one file's bytes exist at
a time. The keys, the merge in `build_finish._made` and the sorted write order
are unchanged. `compute` hashes each clip as it reads it and keeps the bytes
only of a clip the records table lacks (a cold clip, sent to the pool).

| Same input (the built 0.3 FalloutNV.esm, warm records table) | HEAD | Changed |
|---|---|---|
| Held after `entry_files` | +2.30 GB | +1.07 GB |
| Peak commit of the stage's work | +2.44 GB | +1.08 GB |
| Digest of every file made (11,156 files) | `8f87748faecc` | `8f87748faecc` |

**Projected whole build** (the 0.3 stamp's peaks less what each stage no
longer holds: 2.17 GB of LAND and 0.49 GB of other export records outside
people-to-worlds, 1.2 + 0.49 GB inside it, 1.36 GB more in animation data):

| Stage | 0.3 stamp | Projected |
|---|---|---|
| mesh cache | 4.51 | about 1.9 |
| item ARMO / base STAT | 8.67 / 8.74 | about 6.0 / 6.1 |
| people | 8.06 | about 6.4 |
| worlds | 9.07 | about 7.4 |
| animation data | 10.95 | about 6.9 |
| plugin write, archives | 9.4–9.5 | about 6.8 |
| **whole build** | **10.95** | **about 7.4 (worlds); about 6.9 with fix 4 below** |

Not yet measured in a whole build: how much commit Windows gets back when the
land is freed mid-build (other allocations between the LAND dicts can keep
pymalloc arenas alive; in the probe all of it came back). The next whole build's
stamp checks the projection.

<a id="mapped-plugins"></a>**The item ARMO and base STAT peaks.** A probe ran the
build's own setup (`cell._builder`, `cell._object_makers`) on the whole FNV
export into a scratch data folder. It then made every ARMO through
`Items.item` and every STAT through `CellBuilder.base`, sampled as the build
samples. Neither stage has a large spike of its own:

| Probe (whole export) | Before the stage | Stage peak | Held after |
|---|---|---|---|
| item ARMO, 389 armors | 2.10 GB | 2.62 GB | 2.52 GB |
| base STAT, 6,785 statics | 2.10 GB | 2.51 GB | 2.51 GB |

Their build peaks (8.67 and 8.74 GB) are what the build already held when the
late armors and statics were made: items are made on demand, and most statics
are made in the worlds stage, as `_world_groups` places each worldspace's
references. So the LAND and export fixes above are most of their fix. What
the stages add themselves:
- **Fallout4.esm read whole again** (315 MB, +0.31 GB) by
  `nif.addons._fo4_by_name`, while `CellBuilder.fo4` already held a copy
  for the whole build.
- **A fresh index of every game archive** (371,389 names, +0.17 GB) for each
  body fit, head fit and hat field; one at a time, freed after.

**Fix 4: plugins mapped, not read.** `install._read` maps a plugin file
read-only (`mmap`) instead of reading it into memory. `fallout4_esm()` gives
the same map to `CellBuilder.fo4`, `addons._fo4_by_name` and
`script.fo4_editor_ids`, and the source plugin (FalloutNV.esm) is mapped
too. A mapped file's pages are the file's, so they don't count as committed
memory and Windows can drop them without writing them to the page file.
`walk` only slices and unpacks a buffer, which a map supports, so the records
are the same.

Same probe on HEAD and on the changed code (all four fixes in), run one after
the other:

| Probe (whole export) | HEAD | Changed |
|---|---|---|
| After setup | 2.23 GB | 1.37 GB |
| After the makers | 2.58 GB | 1.56 GB |
| item ARMO peak (389 armors) | 2.95 GB | 1.99 GB |
| base STAT peak (6,785 statics) | 2.91 GB | 1.94 GB |
| base STAT time | 141.8 s | 132.6 s |
| Records made, digest | ARMO 1,931 `0de12a3c19e1`, STAT 7,633 `47d6940ecc21` | the same |

Of the 1.02 GB less after the makers, about 0.48 GB is the leaner export
records and about 0.54 GB the two mapped plugins. That 0.54 GB is held for the
whole build, so every stage's projected peak above drops by about as much: the
whole build to about 6.9 GB (worlds), item ARMO to about 5.5 and base STAT
(made during worlds) to about 6.9.

**Leads not taken yet:**
- The rest of the growth from about 4.5 to 8.7 GB: the plugin's records held in
  the writer until `plugin write`, and `builder.fo4` (Fallout4.esm's bytes).
- In animation data, the 0.33 GB index of every game archive (`Archives`)
  and the records table's parsed clips.

## <a id="profiles"></a>One resource setting

Every pool asks `build_resources.pool_workers(each, jobs, asked)` how many
workers to start. `each` is what one of its workers commits.

| Profile | Workers keep busy | The whole build may hold |
|---|---|---|
| `low` | half the logical cores | half of physical memory |
| `balanced` (default) | three quarters | three quarters |
| `full` (the build as it was) | every core but one | all free memory |

**The answer** is the smallest of:
- the jobs;
- the profile's cores, or an explicit count (`--workers`, the app's Workers
  box);
- what the memory budget holds at `each` a worker.

**The budget:**
- free memory less 2 GB, under every profile;
- under the profile's share of physical memory, less what the main process
  commits now;
- under a `TESCONV_JOB_MEM_GB` cap, less the main process, when one is set.

At least one worker always starts.

**Setting it.**
- `pipeline.run --resources low|balanced|full`;
- else the `TESCONV_RESOURCES` environment variable;
- else `balanced`.

The app's Setup screen has it under Other, saved in `fo4_app.json` as
`resources` and passed to the build as `--resources`. The build prints
`resources: <profile> (<n> of <m> cores, <x> GB for workers now)` first.

**The pools.**

| Pool | Worker | `each` |
|---|---|---|
| `pipeline/mesh_cache.py` warm | mesh conversion | 512 MB (`WORKER_BYTES`) |
| `havok/gun_clip_pool.py` | a gun's clips | 1 GB |
| `havok/anim_text.py` records | animation data records | 256 MB |
| `base/ba2_pack.py` write_later | overlay texture writes | 512 MB |
| `base/caprica.py` | one Caprica run | 512 MB (`CAPRICA_BYTES`) |
| `spike/npcs.py` face_workers | face fits, at most half the cores | 1 GB |
| `spike/facegen_skin.py` workers | own FaceGen faces, at most half the cores | 2 GB ([Sources peaks at 1.84 GB](fo4_facegen_plan.md#own-stage-speed)) |
| `base/ba2_textures.py` | threads (zlib frees the GIL): cores only | none |
| `spike/script.py`, `tools/release/fo4_hotfix.py` | the compile's worker count, cores only (Caprica then applies its own `each`) | none |
| `spike/voice.py` convert, `spike/terrain_lod.py`, `base/record_compression.py` | threads running tools or zlib: cores only | none |
| `build_steps.convert_scripts` | `script_convert.pipeline`'s processes, through `TESCONV_WORKERS` unless already set | none |

**Kept as it was, on purpose.**
- **Below-normal priority.** The whole build already runs at it
  (`create_pool_job`), under every profile.
- **The mesh worker's own cap**, `max(2 GB, RAM / 8)`
  ([worker memory](fo4_build_speed.md#worker-memory)). It is a guard against
  one runaway mesh, not a share of the budget. Lowering it per profile could
  make a mesh fault under Low that converts under Full, so the output would
  depend on the profile. Also, `cached_convert` names `worker_memory`, and
  [code identity](fo4_plugin_layout.md#code-identity) follows the names a
  function uses, so any edit to it would mark every cached mesh stale.

**Cache records are untouched.** 984 code records sampled from the work and
mesh caches (40 per work site, 200 meshes): 287 are stale under the
`fo4-2026-10-31` code and the same 287 under this change; none newly stale.

**Output does not depend on the profile:** [the byte check](#same-bytes).

## <a id="eta"></a>Estimated time

`fo4_import/pipeline/eta.py` estimates a build's time, cold and cached, per
stage group. It is always shown as an estimate.

**Stage groups** (`eta_inputs.GROUPS`): mesh cache, scripts (conversion and
compile), people, weapons (`item WEAP`), statics (`base STAT`), worlds
(worlds, navmesh, object LOD), collision, voice, animation (any stage named
`... animation data`), archives (main, FaceGen and texture archives, plugin
write), ledger, and records (every other stage).

**Features** of a build (`eta_inputs.features`, from its printed counts):

| Feature | Count |
|---|---|
| `npcs` | `NPC_` |
| `guns` | `guns on FNV clips` |
| `statics`, `land`, `cells`, `info` | `STAT`, `LAND`, `exterior cells`, `INFO` |
| `meshes` | `meshes in scope` (the log's `mesh cache: N meshes ready`) |
| `scripts`, `compiles` | `scripts`; whether any script changed |
| `compile_size` | `compiles` × thousands of meshes |
| `packed` | files packed into the Main and texture archives |
| `masters` | the plugin has masters |

Each group's time is a sum of `coefficient × feature`.

**Cold work** has features of its own:
- `faces_cold`: faces fitted in worker processes;
- `guns_cold`: guns whose clips were made in the pool;
- `voices_cold`: voice files written;
- `meshes_cold`: meshes converted;
- `scripts_changed`.

A cold estimate sets each to its warm bound (every NPC's face, every gun,
every mesh). A cached one sets them to 0 but keeps one script compile, since
nearly every logged build compiled something.

**Where the features come from.**
- **Its last finished build** (its stamp's counts): exact for a rebuild.
- **Else its export:** each feature is a ratio times the export's records of
  its types. Small files are counted record by record; files over 64 MB are
  sized against the median bytes a record (`LAND.txt` is 820 MB). Plus the
  mesh files under `meshes/`.
  - The ratios come from the whole game builds.
  - A plugin with masters that edits cells also gets the typical region a
    mod build takes from its masters: the median over the logged mod builds.
    A mod build is a [region build](fo4_build_speed.md#found), and its size
    is not known before it runs.

**Another machine.** Each feature's work scales by one of three speeds:
- the main process by one core (`serial`);
- cold work (`*_cold`, `scripts_changed`) by the pool (`pool`): the
  throughput, read off the benchmark's measured worker counts, of the workers
  the profile allows there;
- `packed` by disk writes (`disk`).

The reference is the build machine under `full`. Without a benchmark file
the reference machine is assumed and the live correction does the rest.

**Before a build:**
- `pipeline.run` prints
  `estimate: about N min cached, M min cold (from its last build; an estimate, ...)`.
- The app's Convert screen shows the same line for the chosen target
  (`stages.estimate`), under the controls.
- The command line, per plugin and in total:
  `py -3.14 -m fo4_import.pipeline.eta <export folders or .build.json stamps>... [--resources low] [--benchmark FILE]`.

**During a build:** see [live progress](#live-progress).

### <a id="live-progress"></a>Live progress

`eta.Live` hears every stage's end and checks every 10 s (`LIVE_SECONDS`).
The plan is the cached one when the plugin has a finished build record, else
the cold one. The estimate has to follow whatever else the machine is doing,
so it leans on the live rate more than on the model.

**The running stage counts as it runs.** Time since the last stage ended is
charged to the group of the innermost running stage
(`stage_timer.running()`), not held back until it ends.

**Stage progress.** A stage's long loop wraps its items in
`stage_timer.counted(items, total, unit)`. That records `done of total` on
the running stage until the loop ends. The loops counted:

| Stage | Loop | Unit |
|---|---|---|
| mesh cache | `mesh_cache.warm`'s pool | meshes |
| people | `npcs.warm_faces`'s face fits | faces |
| item WEAP | `gun_clip_pool.warm` | guns |
| collision | `elric_cache._run` | meshes |
| voice (and sounds) | `voice.convert` | voice files |
| worlds | `Exterior.group`'s cells, per worldspace | cells |
| script compile | `compile_papyrus._fo4_batches` | batches |

**What is left** (`Live.left`):
1. `first`: the pace of the groups not running (spent over planned, held
   between 0.5 and 3; 1 until 60 s are planned).
2. The running group: its plan times `first`, less what it has spent. Once
   5% of its counted loop is done (`TRUSTED_SHARE`), the loop's own
   remaining time at its rate so far (`step_left`) joins in. The plan's
   figure moves toward it as the loop's share done grows, and the result is
   never below it (`blended`).
3. `overall`: the pace of every group, the running one counted at its spent
   time plus step 2.
4. Every other group: its plan times `overall`, less what it has spent.

Why: on a laptop with no benchmark and 1.1 GB for workers, one stage ran
about 50 minutes (12 to 63 min) with no stage ending. The old estimate only
re-paced when a group ended, so it counted down to "about 1 min left" and
then jumped to 85. Now the running stage's overrun raises the pace as it
happens, and a counted loop gives its own rate.

**What it prints.**
- `estimate: about N min left, M min so far (...)` goes to the log only
  when the expected finish has moved by at least 2 min and 15% of the time
  left (`MOVED_SECONDS`, `MOVED_SHARE`), and on the first check.
- The app sets `F3NV_PROGRESS_LINES` (`eta.PROGRESS_ENV`) for its stages,
  and the build then prints a `progress:` line every check, for example
  `progress: Worlds: 412 of 1,180 cells, about 12 min left in this step, about 40 min overall`.
  "This step" is the running stage's group. The app's runner keeps
  `progress:` lines out of the run log, and the Convert screen shows them
  under the controls instead of in the scrollback.

## <a id="benchmark"></a>The machine benchmark

`python tools/release/machine_benchmark.py [--out FILE] [--dir FOLDER]` takes
about a minute. It writes `output/machine_benchmark.json` by default, which
is where the build and `eta` look for it. Point `--dir` at the drive the
build writes to. It needs only Python and numpy.

The app runs it once: when a plan holds a build (`build` or `update`) and the
work folder has no `output/machine_benchmark.json` (`eta.benchmark_path()`),
`stages.plan` puts the benchmark before the first build, writing there with
`--dir` the work folder.

| Measure | How |
|---|---|
| `single.python_units_s` | 20,000 records packed, parsed into dicts and indexed, a second, one core |
| `single.numpy_units_s` | a 400 × 400 product and a sort of 1M floats, a second |
| `workers.units_per_second` | Python units a second at 1, ¼, ½, ¾ and all but one of the logical cores, 12 units each |
| `workers.effective_cores` | the best of those over one core |
| `disk` | one 512 MB file written in 16 MB blocks and flushed, read back (may come from the cache), 2,000 files of 64 KB written and read |
| `memory` | physical and free GB; numpy copy GB/s over 256 MB |

It records CPU model, OS and Python version, never a user or machine name.
The user runs it on three machines (this one, a lower-end laptop, a low-end
machine that plays FO4) and sends the files back. Each one scales the
estimate for that machine and checks it ([still open](#open)).

**This machine** (16 logical cores, 31.1 GB), run twice on 2026-11-12 while
other sessions were working:

| | Run 1 | Run 2 |
|---|---|---|
| one core, Python units/s | 28.5 | 30.1 |
| 1 / 4 / 8 / 12 / 15 workers | 28 / 129 / 216 / 241 / 182 | 32 / 104 / 150 / 208 / 251 |
| effective cores | 8.5 | 8.4 |
| free memory | 11.1 GB | 16.8 GB |

The first run's disk test flushed every 1 MB file; it measured flush latency
(32.8 MB/s) and was replaced. Run 2 (the current test): 43 MB/s flushed
write, 130 small files a second. Both runs were slowed by other sessions
using the same disk. Run 2 is the reference in the model, so the scale is
"this machine, busy". A quiet rerun replaces it with
`fit_build_eta.py --benchmark`.

## <a id="fit"></a>The fit and its error

```
py -3.14 -m tools.release.fit_build_eta <overnight> <overnight2> --benchmark <reference result>
```

**Data.** The 2026-11-11 and 2026-11-12 overnight queues: 39 finished builds.
- The game twice;
- DLCs and packs (13, some twice);
- 22 mods and FO3's Vault 101 test block.

Each log gives its `stage` lines and counts. The mesh cache time is its line
less script conversion.

**Method.** Each group's coefficients are non-negative least squares over its
features (`fit_build_eta.FEATURES`). Each build is weighted by one over the
square root of its seconds, so small builds count too: plain least squares
put packs at 4 times their time, and fully relative weights cut large builds
by a quarter.

**Fixed, not fitted** (`FIXED`): measured outside these builds.
- **A cold mesh:** 0.072 s. 982 s for 13,625 Frontier meshes on 15 workers
  ([audit](fo4_build_speed.md#audit-2026-11-11)).
- **A cold face:** 0.12 s. 500 faces in 56–62 s on 7 workers
  ([face pool](fo4_build_speed.md#face-pool)).
- **Animation data:** 10 s + 0.4 s a gun, plus 1.5 s a cold gun. Its logged
  times (0 to 1,040 s) predate its [fix](fo4_build_speed.md#anim-data-2026-11-12)
  (now about 45 s warm, 160 s cold for the game). It is left out of every
  error below.

**Coefficients** (seconds, reference machine):

| Group | Coefficients |
|---|---|
| mesh cache | 6.4 + 0.0052 a mesh (+ 0.072 a cold mesh) |
| scripts | 5.3 + 1.5 if compiling + 17.7 a thousand meshes when compiling |
| people | 5.8 + 0.057 an NPC (+ 0.12 a cold face) |
| weapons | 1.31 a gun + 2.90 a cold gun |
| statics | 0.023 a static |
| worlds | 0.0043 a LAND + 0.0052 an exterior cell |
| collision | 0.0102 a mesh |
| voice | 0.0024 an INFO + 0.0077 a voice file written |
| archives | 0.00088 a packed file |
| ledger | 11.0 with masters + 0.0086 a mesh |
| records | 27.9 + 0.0029 an INFO + 0.023 a static |

**Error** (each build's total, animation left out, as a share of its time):

| Mode | Median | Mean | Builds |
|---|---|---|---|
| in sample, the build's own counts | 23% | 30% | 39 |
| that build left out of the fit | 24% | 40% | 39 |
| from its export alone, cached | 33% | 38% | 37 (not FO3's test block or Goodies, whose export is not found) |

Notable misses:
- **The game:** 1,946 s on 11-11 and 785 s on 11-12, both against 1,333–1,473.
- **Lonesome Road 11-12:** 1,186 s against 584.
- **Gun Runners' Arsenal 11-12:** 774 s against 343.
- **The packs:** about 65 s on 11-11 against about 130.
- **Weapons of the New Millenia** left out: 1,123 s against 338. Its 45 cold
  guns are most of what fits `guns_cold`.
- **From the export:** Sunshine On My Shoulders and ExtraGoodies (no
  `CELL.txt`, yet their builds take a region) at about 50 s against
  540–930 s; NVMIM at 664 against 400.

**Why it cannot do much better on these logs.** The same plugin built on the
two nights, with nearly the same counts, differed by 0–122% (median about
75% over the 7 plugins built both nights):
- Caravan Pack 68 s and 282 s;
- Gun Runners' Arsenal 352 s and 774 s;
- the game 1,946 s and 785 s.

Code changed between the nights, caches emptied, and the disk was shared
with other work. So the model's median of about a quarter sits well inside
the night-to-night noise. Every new finished build's stamp can be added to
the fit as a source.

## <a id="same-bytes"></a>Byte check: Full and Low

Two scratch builds of `CaravanPack.esm` on 2026-11-12:
- each with its own empty cache (only the face basis `.npz` files copied in),
  so every pool really ran;
- masters from `temp/profile_data`;
- one `--resources full`, one `--resources low`.

**What matched, byte for byte:**
- the plugin;
- `CaravanPack - Textures.ba2`;
- in `CaravanPack - Main.ba2` (8,039 files, the same names), every material,
  script and mesh without collision;
- the loose `Scripts` and `Music` files.

**What differed:**
- **187 meshes, all with collision,** each the same length with a few
  floats changed in its Havok physics.
  - Cause: **Elric is not deterministic.** Run twice on the same 80 pre-Elric
    meshes (taken from the scratch cache's `mesh_files`), Elric gave
    different bytes for 30 of them. Elric runs once over every mesh in one
    process, with no worker count of ours, so the profile cannot reach it.
  - On a warm build the `elric_finish` cache hands back the earlier output,
    so this only shows when that cache is cold.
- **Bookkeeping that holds times or process ids:** the stamp, the inputs
  record, the archives' and meshes' `.json` records, `compile_state.json`,
  and `CaravanPack.esm.record/<pid>.json`.

**Memory and time** (cold; another session's 8-worker pool was running
during the Full build):

| Stage | Full | Low |
|---|---|---|
| resources line | 15 of 16 cores, 9.6 GB for workers | 8 of 16 cores, 8.8 GB |
| script conversion | 11.4 s; 1.04 GB main, 1.23 GB in 17 processes | 16.7 s; 1.05, 0.84 GB in 10 |
| mesh cache (518 converted) | 30.9 s; 1.79 GB main, 1.35 GB in 8 workers | 52.8 s; 2.09, 1.28 GB |
| item WEAP (17 guns, 1 made in the pool) | 700 s; 6.13 GB main, 0.93 GB in 1 worker | 833 s; 6.59, 0.93 GB in 1 |
| people (54 faces in 2 workers) | 56 s; 6.12 GB, 1.57 GB in 2 | 44 s; 6.47, 1.51 GB in 2 |
| animation data | 176 s; 6.45 GB, 1.46 GB in 26 processes | 41 s; 6.44, 0.83 GB in 8 |
| sounds | 14.9 s; 0.35 GB in 40 processes (ffmpeg, xWMAEncode, LipGenerator from 20 threads) | 6.3 s; 0.13 GB in 16 |
| whole build | 1,401 s; peak 6.45 GB main, 1.57 GB in workers | 1,187 s; 6.59 GB, 1.51 GB |

What it shows:
- **Main process:** about 6.1–6.6 GB from the first base stage on. A small
  pack's build loads its masters' export like the game's does.
- **Workers:** a mesh worker 0.17 GB (1.35 GB over 8; `WORKER_BYTES` is
  512 MB for headroom). A face worker 0.8 GB, as measured before. The gun
  clip worker 0.93 GB.
- **Sounds and script conversion** were outside the six pools named at the
  start (a default-sized thread pool and `worker_count()`). They now follow
  the profile too, after this run:
  - `spike/voice.py` convert, `spike/terrain_lod.py` and
    `base/record_compression.py` run on `profile_cores()` threads;
  - `build_steps.convert_scripts` passes `TESCONV_WORKERS` (the profile's
    cores) unless it is already set.
- **Item WEAP was 700–833 s cold** for 17 guns with one made in the pool.
  Most of a mod's cold gun clips are made one at a time in the main process.
  This is a speed lead, not measured further here.

The estimate printed `about 1 min cold` from the export. A first build into
an empty cache also recomputes the animation records table and collision
for every mesh, which the cold model does not cover.

## <a id="disk"></a>Disk space

**Code:** `fo4_import/base/ba2_pack.py` (`prune_staging`),
`fo4_import/pipeline/work_cache.py` (`store_latest`), called from
`spike/build_finish.py`, `spike/facegen_own.py`, `spike/facegen_skin_cache.py`.

**Where it went on the build machine (2026-11-24, before cleanup).**
`output/fo4_cache` held 482 GB in 8.1 million files, `temp/` 145 GB:

| Cache | Size | What |
|---|---|---|
| `ba2` | 316 GB, 137 folders | archive staging: per Data folder, loose copies of what its archives hold |
| `work` | 152 GB | the work cache; `own_face` 82 GB and `face_skin` 32 GB of it |
| `meshes`, `object_lod`, others | 14 GB | |

- **Staging is a second copy of each built mod.** A staging folder holds the
  staged sounds, the textures and the `loose` stash of Main-archive files
  (FO3: Sound 12.3, Textures 4.0, loose 2.5 GB; FNV: 7.7, 5.3, 2.5 GB), about
  the size of the mod's archives. It stays between builds so a rebuild skips
  unchanged voices and textures. Its name is the Data folder's path hash, so
  every folder a build ever wrote to kept one: 75.8 GB belonged to folders
  that no longer existed (scratch builds, `temp/profile_data*`), and about
  42 GB to `C:\Modlists` copies of mods since built under `D:\Modlists`.
  Nothing removed them.
- **Faces were kept once per NPC record version.** An `own_face` entry is
  keyed on the NPC record as built and its masters (`facegen_own.cached_files`),
  so a converter change that touches NPC records, or a rebuilt master under a
  DLC, makes a new key for each face; the old entry (about 0.9 MB) waited out
  the 14-day prune. Of `own_face`'s 82 GB, 18.5 GB had been used in the last two
  days. `face_skin` keys on the head files' digests, so it grew the same way.

**What the build does now.**
- `ba2_pack._staging` writes `data_folder.txt` (the Data folder) into the
  staging folder each build that uses it, and the end of every build
  (`prune_staging(14)`) deletes a staging folder unused 14 days, or whose
  Data folder is gone from a drive that is present (an unplugged drive keeps
  its staging). A folder from before the record goes by its age. The cost of a
  wrong delete is one rebuild that stages everything again.
- `work_cache.store_latest` keeps each NPC's two newest face entries
  (`own_face`: plugin, FormID, kinds; `face_skin`: plugin, FormID) and deletes
  older ones when a new one is stored. Two, not one: builds alternating between
  two code versions (a test worktree sharing this cache) both hit, as
  `tests/test_fo4_facegen_own.py` requires.

**A conversion's disk use** (one game). New Vegas is a fresh build into an
empty work folder on the test laptop (2026-11-24, release
`f3nv-0.6-6-gd3a448bb`); Fallout 3 is the build machine's folders, its caches
estimated from New Vegas's plus its larger voice set:

| Part | Where | New Vegas | Fallout 3 |
|---|---|---|---|
| Export (records, archives extracted, music) | work folder | 9.2 GB | 7.8 GB |
| Archive staging (`fo4_cache/ba2`) | work folder | 15.2 GB | 18.9 GB |
| Work cache (`fo4_cache/work`) | work folder | 13.2 GB | about 15 GB |
| Other caches (`meshes`, `object_lod`, `pre_elric`, headers) | work folder | 2.3 GB | about 2.3 GB |
| Built mod folder | MO2 `mods` | 13.7 GB | 19.4 GB (voices 12.3) |
| **Total** | | **53.5 GB** | **about 63 GB** |

The work cache's largest sites after a fresh New Vegas build: `own_face`
4.3 GB, `face_skin` 3.6 GB, `voice_file` 1.9 GB, `land textures` and
`spec_map` 0.7 GB each, `mesh_files` 0.6 GB, `gun_clip_files` 0.6 GB. A
rebuild after a change to NPC records stores a second face per NPC (the two
kept by `store_latest`), so the face sites can grow to about 16 GB; the README
asks for about 70 GB per game to cover that.

## <a id="gun-clip-memory"></a>Gun clip workers

**Code:** `fo4_import/havok/gun_clips.py` (`_third_target`),
`fo4_import/havok/gun_clip_pool.py` (`WORKER_BYTES`).

On the test laptop's fresh New Vegas build (13.7 GB, 2026-11-24) the weapons
step (`item WEAP`) took 2,197 s, and its two gun clip workers committed
7.98 GB together beside a 6.65 GB main process: free memory reached 0.01 GB.
The pool had sized them at `WORKER_BYTES` = 1 GB each.

A worker kept every vanilla third-person clip it parsed (`third_clips`), the
whole clip, though it reads only the left-hand target track from most of them
(`_on_gun`), to decide which clips follow the gun. A shotgun reads 646 such
clips. Replaying the saved jobs of a one-cell build in one process, the commit
went 1.14 GB after two guns, 2.28 GB after the third (646 clips kept),
3.05 GB after the fifth (1,061 clips).

Now a worker keeps per clip only that track's translations
(`third_targets`), and parses a clip again when it writes a copy of it
(WPNAssemblyPose and the clips whose target stays on the gun). The same eight
guns replayed (`temp/gun_worker_mem.py`): each gun's clips, entries and files
hash the same as before; the commit stays at 1.13–1.14 GB where it climbed to
3.30 GB, and the eight take 97 s against 101 s. Both figures include about
1 GB of the replay's own saved jobs, so a real worker is smaller still, and
`WORKER_BYTES` stays at 1 GB.

## <a id="open"></a>Still open

- **The three reference machines.** With the laptop's and the low-end
  machine's benchmark files, check each one's estimate against a real build
  there, then refit with `--benchmark` per machine if the single scale does
  not hold.
- **A quiet benchmark** of the build machine for the reference.
- **Refit on stamps.** Now that stamps keep stage times, counts and memory,
  later builds (with the animation and voices fixes in) can replace the
  overnight logs. The `--main-gb` the pool estimate assumes (9 GB, the game's
  [land step](fo4_build_speed.md#land-memory)) should come from those stamps.
- **Elric's output varied run to run** ([byte check](#same-bytes)). Gone
  since 2026-11-24: Elric no longer runs, and our physics writer gives the
  same bytes every run ([seam](fo4_hknp_writer.md#seam)).
- **Cold gun clips in a mod build** are made mostly in the main process
  (700–833 s for Caravan Pack's 17 guns, one in the pool).
- **A mod's first build** is estimated from a typical region. Its build scope
  (`addons.build_scope`) and its masters' records could give its real
  region.
