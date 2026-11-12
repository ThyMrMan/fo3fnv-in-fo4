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
- [One resource setting](#profiles)
- [Estimated time](#eta)
- [The machine benchmark](#benchmark)
- [The fit and its error](#fit)
- [Still open](#open)

## <a id="stage-memory"></a>Memory per stage

**How it is measured.** `stage_timer.sample()` starts a thread when the build
starts. Every 0.5 s it reads:
- the main process's committed memory (private bytes, `K32GetProcessMemoryInfo`);
- the same for every other process in the build's job object
  (`QueryInformationJobObject`). These are the pool workers and the tools the
  build starts (Caprica, Elric, LipGen). The Creation Kit breaks away from the
  job and is not counted.

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

**During a build:** `eta.Live` listens to every stage's end and ticks every
30 s. It prints `estimate: about N min left, M min so far (an estimate, ...)`.
- What is left: each group's plan times the pace of the groups already
  passed (actual over planned, held between 0.5 and 3), less what each group
  has spent, less the time since the last stage ended.
- The plan is the cached one when the plugin has a finished build record,
  else the cold one.
- The app shows the latest line under the controls.

## <a id="benchmark"></a>The machine benchmark

`python tools/release/machine_benchmark.py [--out FILE] [--dir FOLDER]` takes
about a minute. It writes `output/machine_benchmark.json` by default, which
is where the build and `eta` look for it. Point `--dir` at the drive the
build writes to. It needs only Python and numpy.

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
- **Elric's output varies run to run** ([byte check](#same-bytes)), so a
  build with a cold `elric_finish` cache is not byte-reproducible in its
  collision. Not looked into: whether Elric has a setting for one thread.
- **Cold gun clips in a mod build** are made mostly in the main process
  (700–833 s for Caravan Pack's 17 guns, one in the pool).
- **A mod's first build** is estimated from a typical region. Its build scope
  (`addons.build_scope`) and its masters' records could give its real
  region.
