# FO4 pipeline: from the spike to the whole of FNV

Design only; status is in [ROADMAP.md](ROADMAP.md). This is the
[decision point](fo4_spikes.md#decision) the spikes were building to: the
spikes proved each piece on Doc Mitchell's house and a 3×3 block of
Goodsprings; this plan turns them into a converter for whole plugins.

## Contents

- [Scale](#scale)
- [Is this the right base?](#base)
- [The pipeline](#pipeline)
- [Before the pipeline: build and research](#before)
- [Record census](#census)
- [Speed](#speed)
- [Stability](#stability)
- [Order](#order)
- [Parked](#parked)

## <a id="scale"></a>Scale (measured 2026-10-10)

| | Spike | FalloutNV.esm |
|---|---|---|
| Exterior cells | 9 (one 3×3 block) | 16,397 in WastelandNV; 4,097 each in TheStripWorldNew, WastelandNVmini, Lucky38World |
| Interior cells | 1 + QASmoke | 388 |
| References | ~1,500 | 165,148 exterior + 142,562 interior REFR; 3,386 ACHR; 2,999 ACRE |
| Placed base records | a few hundred | 13,073 (6,414 STAT, 1,722 NPC_, 1,095 ACTI, 650 CONT, 604 CREA, 403 LIGH, 316 DOOR …) |
| Distinct placed models | ~300 | 7,428 (6,282 of them STAT) |
| NAVM / LAND | 1 / 9 | 4,771 / 29,363 |
| QUST / NPC_ / CREA records | 5 / a few / 2 | 436 / 3,816 / 1,578 |

## <a id="base"></a>Is this the right base?

Yes: grow the FO4 converter on this repo's own stack, but not on the spike's
`cell.py`.

**What already exists here.** The Skyrim converter this repo was copied from
already converts all of FalloutNV.esm, every worldspace and interior, at
full scale. Several parts of it are shared with the FO4 path:

- the neutral export (`tes4_export`);
- the shared readers (`MasterExport`, folder tables, each file read once a
  run);
- the stable-FormID writer (`derive_formid`, `reserve_source_ids`);
- worker pools with containment and the machine-wide heavy-job lock;
- the FNV navmesh repack, with authored edge links between cells
  (`navm_falloutnv.py`);
- the script front end (already emitting FO4 Papyrus, 99.9% of FNV's
  scripts compile);
- dialogue unlock plans and the condition remaps;
- the versioned caches.

The spike layer (`fo4_import/spike`, 6,700 lines) holds the FO4 knowledge:
record layouts, the NIF/BGSM/BGEM writers, Elric, FaceGen, scenes, XDI
menus. The pipeline is the Skyrim pipeline's shape with the spike's FO4
knowledge moved into per-record-type converters.

**Alternatives considered:**

| Option | Verdict |
|---|---|
| **Mutagen (C#)**, strongly typed plugin read/write | It covers Oblivion, Skyrim and Fallout 4 (the FO4 package is still alpha) but not FO3/FNV, so it could replace only our FO4 writer, which already works and is tested. It would mean rewriting the spike in C# and losing the shared Python stack (script converter, dialogue plans, navmesh, export). No |
| **xEdit scripting** (the [fnv-to-fo4](research/fo4_target.md#fnv-to-fo4) approach) | Pascal scripts run inside xEdit: slow at 300k references, hard to test, and that project stopped before actors, quests and navmesh. No |
| **nifly / PyNifly** (C++ NIF library, FO4 read and write) | Our NIF writer rebuilds 32,397 vanilla meshes byte for byte and handles what nifly does not (FO4 collision). Keep ours. nifly is the fallback if a measured mesh-speed problem can't be fixed in numpy |
| **Hand-made ports** (Fallout 4: New Vegas, Project Mojave) | Not converters. They are the modlist's job: replacements laid over the converted world ([direction](fo4_replacements.md#direction)) |
| **The engine's own tools** for engine-made data | Yes, as pipeline stages: the CK for FaceGen (`-ExportFaceGenData`, already used), precombines and previs (`-GeneratePreCombined`, `-GeneratePreVisData`, automated by PJM's scripts, which need CK Platform Extended); xLODGen for terrain LOD (it supports FO4) |

## <a id="pipeline"></a>The pipeline

Stages, each scoped and cached on its own so a fix rebuilds only its stage:

1. **Export:** shared, unchanged.
2. **Index:** read the export once into the shared readers. These are
   references bucketed by cell, bases by type, and the cross-reference
   graph. The spike parses `REFR.txt` (308k records) several times a build.
3. **Records:** one converter per FNV record type over the whole plugin
   (and its masters), writing one FO4 plugin per FNV master.
   - FalloutNV.esm becomes its own FO4 master, and each DLC its own plugin.
     Records keep FNV's object id, and two masters would collide in one
     file.
   - Region filtering is a scope on this stage, not a separate code path.
4. **Assets:** meshes, materials, textures, trees, sounds and voice, each
   keyed by its source file and converted once into a cache. Elric and
   BA2 packing run on the cache's output.
5. **Scripts:** the existing FO4 target, compiled incrementally.
6. **Engine passes:** CK FaceGen, LOD (terrain, then objects), then
   precombines and previs last, since any change to a cell's statics
   makes them stale.
7. **Pack:** BA2s per plugin.

## <a id="skeleton"></a>The skeleton (built 2026-10-10)

```bash
py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FalloutNV.esm --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV --around -18 0 --radius 1 GSDocMitchellHouse
```

`fo4_import/pipeline/` runs the spike's converters (`spike.cell.build`)
with the pipeline's infrastructure under them. It replaced the spike's own
command line.

- **The export read once** (`export_index.export_records`): the spike's
  74 parses (several files read two or three times) became one per type
  file.
- **A mesh cache** (`mesh_cache.cached_convert`). A converted mesh is kept
  under `output/fo4_cache/meshes`.
  - Its key: the source NIF's bytes, the call's pose and animation flag,
    the winding-repair switch, and a code tag. `code_tag` is a SHA-1 over
    the converter's source and every repo module it imports (42 files), so
    no version is bumped by hand.
  - An entry also keeps each FNV texture's size and time; a changed
    texture is a miss.
  - `mesh_cache.warm` fills it first in worker processes, from the meshes
    of the bases the scope places (`run.scope_models`).
- **An Elric cache** (`elric_cache.process`). Elric's output is kept per
  pre-Elric NIF, keyed by its bytes and a SHA-1 over Elric's exe, DLLs and
  settings; a NIF Elric crashes on is remembered as a crash.
  - Elric writes uninitialized bytes into its physics: two fresh builds
    differed in 162 of 946 files, only inside `bhkPhysicsSystem` (32 bytes
    in `flamerfuel.nif`, 3 in `woodplanks01nv.nif`). Our own blocks were
    identical. With the cache, every rebuild after the first is byte for
    byte the same.
  - Elric runs as one instance. Four at once never finished: no CPU after
    nine minutes.
  - <a id="held-meshes"></a>*Only finished NIFs reach the data folder.*
    A NIF with Havok input is held in memory (`elric_cache.write_mesh`)
    until `finish()` writes its finished bytes, and only when they
    changed. Each build used to write every Havok NIF twice, first
    pre-Elric, a form FO4 cannot load. Played (2026-10-21): during a build
    that rewrote 2,139 meshes, a game left running drew the red "!"
    missing-model marker on Primm's fence beams and utility poles, though
    the files were whole afterwards. Code reading a mesh the build just
    made uses `mesh_bytes()`.
  - <a id="stale-files"></a>*Stale meshes, materials and clips (built
    2026-10-21).* A mesh, material or idle clip a build stops making
    stayed in the data folder (the encoder probe's clips, worn meshes
    renamed, meshes of cells a region no longer covers). `stale_files`
    lists what a build made under `Meshes/fnv`, `Materials/fnv` and the
    plugin's clip folder (every writer there rewrites its file or, holding
    its bytes, touches it, so files dated from the build's start) beside
    the plugin as `<plugin>.files.txt`; the next build of that plugin
    deletes what the last list named and the new one does not, unless
    another plugin's list names it (a DLC build shares these folders). No
    earlier list, nothing deleted. FaceGen and voice keep their own
    pruning; scripts and textures are not covered.
- **Scripts compiled only when changed.** `script.compile_into` stages the
  needed scripts in a folder that stays put
  (`output/fo4_cache/script_stage`) and compiles through the corpus gate's
  incremental compiler (`tools/script/compile_papyrus.compile_fallout4`),
  in parallel batches. Its state file sits in the data folder's `Scripts`.
- **Voice files kept.** Lines' FormIDs no longer move, so a `.fuz` that
  exists is kept (sounds already were).

**Measured** (the 3×3 block and Doc's house):

| Build | Time | Plugin |
|---|---|---|
| Spike, before | 362 s | (reference) |
| Pipeline, empty caches | 168 s (389 meshes converted in 26 s on all cores) | byte-identical to the spike's |
| Pipeline, rebuilt | 108 s (meshes ready in 8 s, 0 of 440 scripts recompiled) | byte-identical, every mesh too |

Profiled, the spike spent 267 of its 592 profiled seconds in collision
(the shared winding repair, `collision_winding.py`, pure Python), and 113
in the Papyrus compiler. The winding repair now hands each rule only the
render faces that could decide it: the same verdicts, 6.4x less CPU on the
block's meshes, 16 s instead of 26 s to convert them all
([render oracle](../commentary/asset_convert_collision.md#the-render-oracles-grids)).
What a rebuild still spends, profiled:

- outfits and the test chest's armor fitted again every build (38 s);
- the export parse (21 s);
- texture copies and spec maps rewritten (18 s);
- Elric's read and graft over every mesh (15 s);
- voice (29 s, now skipped for existing files).

## <a id="converters"></a>Per-type converters and the region scope (built 2026-10-10)

**Converters.** `fo4_import/pipeline/converters.py` holds `PLACED`: each
FNV base type a reference can place, mapped to the cell builder's
converter for it. `CellBuilder.base()` dispatches on that table instead of
its chain of type checks.

| Converter | Types |
|---|---|
| `record` (its FO4 record; `_make`) | STAT, MSTT, SCOL, LIGH, DOOR, FURN, ACTI |
| `readable` (`spike.readables`, [below](#readables)) | BOOK, NOTE, TERM |
| `idle` (a vanilla idle marker) | IDLM |
| `pickup` (the FO4 item, else a static) | ALCH, AMMO, WEAP, ARMO, KEYM |
| `item` (`spike.items`) | MISC, CONT |
| `tree` (a static from the SpeedTree) | TREE |
| `sound` (a sound marker) | SOUN |

The census tool's new `Placed` column reads the same table, so it can't
disagree with the code. A type gets its own converter by adding a builder
method and pointing its entry at it; a stand-in type leaves
`STATIC_STAND_INS` when it does. The record types that aren't placed
(quests, dialogue, packages, NPCs) are next. They are still built for the
spike's cell quests and stand-ins only.

**Region scope.** `--region X0 Y0 X1 Y1` builds any rectangle of a
worldspace's cells (`exterior.Exterior` takes the two corners).
`--around X Y --radius R` remains as the square shorthand.
`--region -19 -1 -17 1` is the spike block, and it builds the same plugin
byte for byte as `--around -18 0 --radius 1` did.

**Growing the area moves nothing.** A 5×5 build (`--region -20 -2 -16 2`):
25 cells, 5,102 records, no FormID duplicated, built in 147 s with the 3×3
block's meshes cached. Every one of the 3×3 build's 3,772 records keeps its
FormID, type and EditorID in it. The first try found two that didn't: a
static collection's part base took a hashed id when it was first reached
as a part, and FNV's id when first placed by itself. A part's base now
always takes FNV's id. That moved the block's 20 part-only bases once.

## <a id="exterior-navmesh"></a>Exterior navmesh (built 2026-10-10)

`spike/navmesh.py` converts every navmesh in the build in one pass: the
interior's and each exterior cell's. An exterior navmesh goes in its cell's
temporary group. Its pathing cell is the worldspace plus the grid, stored
Y then X as in all 7,113 of Fallout4.esm's exterior navmeshes. One NAVI
override registers them all.

**Edge links.** FNV's NVEX links a triangle's edge to a triangle in a
neighboring navmesh (type, navmesh, triangle), and so does FO4's NVNM. FO4
adds one byte: which edge of the linked triangle faces back. A census of
Fallout4.esm's 283,269 links:

- Where the two edges share both ends, the byte is the shared edge in
  207,727 of 207,776.
- Most of the rest are borders split differently on each side. The edge
  nearest the middle of the linking edge matches vanilla's byte in 269,093
  of 269,278 portal links, and 13,080 of 13,991 ledge links.

`facing()` uses that nearest-edge rule. Link types (portal, ledge up,
ledge down) are the same in both games and carry over. A link to a
navmesh outside the build is dropped and its edge left open, as
before. A NAVI entry lists the navmeshes its navmesh links to; vanilla's
do in 5,882 of its 7,113 exterior entries (962 of the rest also list
preferred links, which FNV doesn't author).

**Measured.**
- Goodsprings to Primm (x −21…−10, y −16…4): 252 cells, 370 navmeshes,
  8,501 FNV links, 8,065 kept (the rest leave the rectangle), in 0.5 s.
  Of the 8,045 portal links kept, 7,951 have the linking edge's middle
  within 1 unit of the facing edge (256 share both ends).
- The spike block (`--region -19 -1 -17 1`): 17 exterior navmeshes added
  with 340 links, all to navmeshes in the plugin. Against the previous
  build only the NAVI record changed; nothing else moved.

**Not done yet.** Door references carry no XNDP (the navmesh triangle at
the door), on the interior or outside; FNV has none to copy, and the
interior worked without it. NVMI island data and the Is Island flag are
not written.

## <a id="interiors"></a>Interiors reached by doors (built 2026-10-10)

A build now includes every interior a door leads into, not just the named
cell (`spike/interiors.py`). Starting from the exterior block's doors and
the named cell's, each door's partner door names a cell. When that cell
is an interior, it is built and its doors are followed in turn. Doors into
another worldspace, or into exterior cells outside the block, are not
followed. A door that leads out of the build still leads to a stand-in in
QASmoke.

Each interior gets:
- its references;
- FNV's lighting and imagespace (one FO4 imagespace per FNV one, shared);
- its water height, when the cell has water (the water type is FO4's
  default until WATR converts);
- its navmesh.

Actors and quests are still the named cell's only.

**Height fog.** FO4's XCLL has height fog FNV lacks: a second pair of fog
colors (bytes 100–107) blended in with height (near height 0, range
10,000 in QASmoke's template). The cell took them from QASmoke, whose
near fog is green (75, 99, 97). Doc's house stands about 7,400 units up
in FNV (the saloon ~3,500, the store ~600), so it showed the green
almost fully. Both height-fog colors are now the cell's FNV fog color,
so the fog is the same at every height, as in FNV.

**FNV's fog, read from its shaders and exe** (GOG FalloutNV.exe, shader
package 019):
- The engine sets the shader constant `FogParam` (global `0x11FD934`,
  written at `0xB7AF0A`) to (far, far − near, power, 0) and `FogColor` to
  the fog color.
- The vertex shader computes
  `fog = (1 − saturate((far − d) / (far − near)))^power`.
- A fog-variant pixel shader blends `lerp(lit, FogColor, fog)`. Only 14
  of package 019's 203 standard-lighting pixel shaders read the fog.
- Nothing caps the fog: past the far distance it is the fog color alone.
  So XCLL's fog max is 1.0 (vanilla FO4 writes 1.0 in 307 of 606
  interiors).
  - QASmoke's 0.7 let Doc's house show bright background past its
    1,500-unit fog clip distance: the white shapes at the end of its hall.

Doc's fog values (near 100, far 1,500, power 0.6) are among FNV's
foggiest; FNV's p10/median/p90 far is 1,600/4,000/10,000. In FNV the
fog color (77, 62, 32) is near the room's own brightness, so the fog
barely shows. In FO4 the same color renders as a bright beige haze. The
cause, likely FO4's linear HDR lighting and exposure, is not confirmed:
FO4's shaders carry no constant names to read.

| Scope | Interiors | References in them |
|---|---|---|
| Spike block (`--region -19 -1 -17 1`) | 9 (Doc's house, the saloon, the store, the school, the gas station, 4 houses) | 2,227 |
| Goodsprings to Primm (x −21…−10, y −16…4) | 27 (adds Primm's houses, sheriff, Bison Steve's two floors, Vikki and Vance, the cave, the shacks, the Prospectors' den) | 6,791 |

The spike block built in 104 s (680 meshes). Against the previous build:
- added: 8 cells, 1,764 references, 9 navmeshes and the bases they place;
- removed: nothing; no FormID moved;
- changed:
  - 13 exterior doors, which had no destination and now lead into the
    new interiors (3 take a static load-door copy);
  - 2 scripts, whose properties naming the saloon's references
    (`GSJoeCobbTriggerRef`, `GSRadioRef`) are now filled.

## <a id="region"></a>Goodsprings to Primm (built 2026-10-10)

`--region -21 -16 -10 4` (the [interiors](#interiors) table's second row):

| | |
|---|---|
| Exterior cells | 252 (LAND 252, 37 landscape textures) |
| Interiors | 27 |
| References placed | 20,725 (72 static collections split into 588 parts) |
| Navmeshes | 400 (370 exterior, 30 interior), 8,067 edge links, all resolved |
| Meshes | 1,630; textures packed 2,312 |
| Scripts | 516 compile |
| Plugin | 9.5 MB |
| Build, meshes cached | 177 s (mesh cache 8 s) |

Against the spike-block build:
- **Removed:** one QASmoke stand-in door, because its door now leads to
  its real partner.
- **Changed:**
  - 13 border navmeshes now link outward;
  - two markers now have their linked reference;
  - the worldspace's bounds grew.
- No record that is still built changed its FormID.

<a id="region-measured"></a>**Measured 2026-10-11** ([order](#order) step 1).
- **Frame rate:** a run from Doc's porch down the main road to Primm,
  logged by Afterburner (RTX 5070 Ti, 315 one-second samples). The game
  held its 118 cap with a median frame time of 8.5 ms and the GPU at
  24%. It used 2.9 GB of RAM and 1.3 GB of VRAM. The only spikes were
  cell loads: 1.7 s just after the start and 370 ms entering Primm. So
  this region needs no precombines or previs; denser places (Freeside,
  the Strip) still need their own measurement.
- **Build, meshes cached:** 183 s; peak memory 5.8 GB over all the
  build's processes, with the main process near 3.6 GB throughout.
  Under cProfile (268 s, so shares rather than seconds):

  | Share | Where | Cached? |
  |---|---|---|
  | 25% | Specular maps from FNV normal-map alpha (`write_normal_dds`: BC4 encode and resizing), 2,142 a build | No: re-encoded every build |
  | 20% | `elric.finish` reading every mesh back (the pure-Python vertex reader) | Elric's physics is cached; the read and graft are not |
  | 16% | The QA test chest's outfits and headgear (`equipment.test_items`, pyffi reads) | No |
  | 9% | Parsing the export text (`text_reader`, 50 files; `scope_models` alone 19 s) | Parsed once a run |
  | 6% | Texture BA2 packing | No |
  | 3% | Face tint fit for Doc | No |

  A rebuild with nothing changed still spent most of its time on assets
  the mesh cache already covers in spirit.
- **Work cache (built 2026-10-12).** `pipeline/work_cache.py` keeps a
  piece of work's result on disk, keyed by its site, the `code_tag()` of
  the module doing it, and every byte it reads. It now holds:
  - the specular maps (`normal_dds`) and glow maps (`encode_dds`), keyed
    by the image;
  - each finished mesh after Elric (`elric_cache.finish`), keyed by the
    pre-Elric NIF and Elric's files, with its failed flag;
  - the outfits moved onto FO4's body, their shape materials and the
    rigid-headgear check, keyed by the converted and FNV meshes.

  Region rebuild with meshes cached: 183 s → 86 s (empty work cache: 132
  s; the cache is 220 MB). Both builds wrote all 2,910 output files byte
  for byte as before.
- **Doc's sculpt fit changed once.** One warm build of four wrote
  different sculpt values (FMRS) for Doc. Every other build matched. So
  did 10 parallel standalone fits, a build with the fit's inputs hashed,
  and builds under different memory layouts. The fit
  (`sculpt.fit`, `lsq_linear` with bounds) solves a rank-deficient
  system (the basis's condition number is infinite), so equally good
  answers exist; many values sit on the ±0.9 bound. Not reproduced. A
  small ridge term would make the answer unique, but would change Doc's
  played face.

<a id="audit"></a>**Audit before step 2 (2026-10-12).** Several bugs this far
were one small thing left unconverted with a large effect (portals, XLOC,
add-on nodes, colliders, joints). Two tools now look for them on every
build:
- `tools/validate/fo4_check.py`: FO4Edit's own "Check for errors",
  headless, over the built plugin.
- `tools/validate/fo4_coverage.py`: FNV's references and fields against
  the plugin's, paired by FNV's object ids.
- `tools/validate/fo4_audit.py` (2026-10-13): the defect classes play-testing
  found, checked before playing. It looks for:
  - script properties left unfilled (split into names FNV has outside the
    build and names it has nowhere) or naming no record;
  - creatures keeping their own stats with Health 0;
  - actors left with the copied body's TurretTripodClass;
  - creatures with no factions or combat style that no template supplies;
  - living actors of a burrowing race;
  - FNV package sections with no package VMAD;
  - package targets that lost FNV's Persistent flag;
  - unique actors placed twice;
  - script hazards: patterns where FNV's one-script-at-a-time model breaks
    under Papyrus threads (a cross-script add left non-atomic, a counter
    tested with `==` after its add, a Say in a dialogue result), and
    GetFormFromFile naming a file outside the load order.

  Seconds. Its first run found two counters the atomic-add pass missed
  because FNV wrote them in parentheses (`set VMS16.nGangerDeathCount to
  (VMS16.nGangerDeathCount + 1)`, the snow globes); `find_adds` now takes
  them.
- `tools/validate/fo4_value_census.py` (2026-10-13): what the plugin writes
  that no Fallout4.esm record of the same type does: tags, sizes other than
  vanilla's one fixed size, header flags, and bits in flag/enum words. Leads,
  not defects. Engine semantics leak through this way: PKDT's Continue if PC
  near is set by 0 of 3,828 vanilla packages (and by Sunny's sneak-to-well
  package before it was dropped). First run on the region build: 37 findings, among them NPC_ SNAM
  written at FNV's 8 bytes on 808 faction entries where vanilla writes 5, and
  FACT MNAM/FNAM rank titles no vanilla faction writes. About 5 s.

Found and fixed:
- **Links to references never built.** `ids` held every reference in
  scope, including those `_placed()` skips (a base that doesn't convert,
  a static collection split into parts). So 4 linked references (XLKR,
  furniture to idle markers) and the script properties of 14 activators
  and a door pointed at nothing. `cell._built` now
  keeps only references that are written, and the existing "not built,
  dropped" rule does the rest.
- **Scripts on containers and misc items.** Of 5 scripted containers
  and 5 scripted misc items, none had its script: the graves
  (`GraveContScript`), the schoolhouse safe, the Mojave Express box, the
  mantis ootheca, `VCG02TargetSCRIPT`, the snow globe and the star caps.
  `pack_cont`, `pack_misc` and `pack_keym` now take a VMAD. 15 more
  scripts compile (531), with 7 messages and a book they use.
- No FormID moved, nothing was removed; FO4Edit then reports only the 23
  consumables with no effect left (below).

Found and left for their step (counts for Goodsprings to Primm):

| Gap | Count | Step |
|---|---|---|
| Idle markers (IDLM): placed as vanilla markers by what they play, 2026-10-17 ([audit fixes](#audit-fixes)); 12 protectron markers left out | 185 | 3 (NPCs) |
| Actors | 206 creatures, 153 NPCs | 3 |
| Ownership (XOWN) on references and cells | 87 + 14 | 2 |
| Map markers (XMRK, TNAM, FULL) | 15 | 2 |
| Consumable effects with no FO4 effect: done 2026-10-14 ([consumable effects](#consumable-effects)); 20 kinds left are recorded drift | 20 kinds | 2 |
| Leveled-list chance-none globals (LVLG) | 18 | 2 |
| Door navmesh links (XNDP), patrol data (INAM, SCHR, XPPA, XPRD) | 70, 68 | 3 |
| Placeable water (PWAT): built 2026-10-19 as FO4's water tiles ([placeable water](#placeable-water)) | 13 | world gaps |
| Placed mines (PGRE): built 2026-10-19 on FO4's mine projectiles ([placed mines](#placed-mines)) | 11 | world gaps |
| Music zones: FNV audio markers name a media location controller (ALOC, MMRK): built 2026-10-19 ([music](#music)) | 45 | world gaps |
| Looping sounds: statics (RNAM), movable statics and lights (SNAM), doors (BNAM): built 2026-10-19 ([looping sounds](#looping-sounds)) | 256, 13, 6, 3 | world gaps |
| Cell acoustic space (XCAS): interiors built 2026-10-19 ([acoustic spaces](#acoustic-spaces)); cell music (XCMO) built 2026-10-19 ([music](#music)) | 275, 27 | world gaps |
| The Goodsprings store radio (TACT) | 1 | 4 (quests) |
| Radiation on references (XRAD): built 2026-10-19 as vanilla hazards ([radiation](#radiation)) | 6 | world gaps |
| Doors open by default (ONAM), item counts (XCNT), occlusion planes (base 0x17), blood decals (TXST): built 2026-10-19 ([reference fields](#reference-fields)) | 3, 1, 3, 2 | world gaps |
| Billboard nodes (4 glow and dust meshes), the school globe's hinge, heat shimmer controllers | 4, 1, 4 | parked |

Meshes: of the region's 1,630 FNV meshes, no block type is lost beyond
the parked ones above and the damage stages and phantom already noted.
Standalone transform and visibility controllers sit in weapon,
clothing and skeleton meshes FNV animates only from actor animations.

<a id="quest-scope"></a>**Quests by reference (built 2026-10-14).** The
build's quests were a hand list of 18; region scripts named 58 quests
outside it, so their stages, variables and objectives did nothing and
conditions on them read 0. `spike/quest_scope.py` now includes every quest
the build's content names, and every quest those name in turn. The content
is the scripts of the placed bases, of the placed actors and of their
packages, the actors' package conditions, and the dialogue lines whose
conditions name a placed actor, base, reference or built cell. A quest is
named by a converted script's property of its EditorID (attach.py fills
properties by name) or by a condition parameter; lines count when their
speaker or cell test (GetIsID, GetIsReference, GetInCell) names a placed
actor, reference or built cell. Each such quest adds the quests its own
scripts start or set a stage on, one step (VCG01 starts VGenericTimer to
give the controls back), but not quests it only reads: following every
reference pulled in 272 quests, the main quest to the Strip; any-parameter
line matches (a caps or weapon check) 154. The rule gives 60 for
Goodsprings to Primm. FNV FormIDs stay one to one.

*Writes count (built 2026-10-18).* A quest whose variables a built script
writes (an atomic add or an assignment) is built too, as one it starts:
VCG01's psych test answers tally in `VCG01Test`, which was left out, so
Doc's stage 85 tag skills read zeros. Goodsprings to Primm gains 9 quests
(69 FNV quests): VCG01Test (VCG01), Generic (Doctors, VDoctors),
VDialogueArcadeGannon, VDialogueCass and vDialogueLily (VNPCFollowers),
VEFR02NCRBad2MostWanted (VFactionSquad), VFreeformNellis
(VDialogueCrimsonCaravan), VMS08 (VFreeformMcCarran) and
vFreeformTheStreet02 (the three Victor quests); 3,203 new FormIDs (2,239
topics, 489 scenes, 270 lines, 174 globals), none moved. VCG01's unfilled
properties drop from 74 to 3, the intended Pip-Boy glove and hand-over idle.

The shared greeting and the scenes it leads to belonged to the highest
priority built quest and were keyed on it, so a higher-priority quest
joining moved all of them (917 topics and 208 scenes when VMS38 joined).
They now live in a generated start-game quest, `FNV_Greetings`
(`cell._greetings`), keyed on itself; each line keeps a GetQuestRunning on
its own quest. Re-keyed once with approval on 2026-10-14.

<a id="readiness"></a>**Per-quest readiness (built 2026-10-14).** Each
tutorial snag was something converted silently left out. The build now
records, per FNV quest, its lines built and left out with the blocking
condition, choices left with no reply, and objective targets not built,
and per NPC the packages left out (`spike/readiness.py`, written to
`temp/fo4_readiness/<plugin>.json`).
`tools/validate/fo4_quest_readiness.py` joins them with the plugin's
unfilled script properties (by owning quest: stage results, quest script,
its lines' results) and the packages of each quest's speakers, and marks
each quest clear or to check before it is played.

<a id="named-references"></a>**References past the edge (built 2026-10-14).**
Packages aimed at a marker past the build's cells were left out as
location or target not built (Ringo's caravan, Hayes' Forlorn Hope trip),
and GetDistance from one could not convert (the prospectors' meal and sleep
packages measure from `VProspectorDenCampsiteMarkerREF`, 472 units past the
region's south edge). FNV keeps those references persistent in the
worldspace's persistent cell; `spike/named_refs.py` places the ones a
placed actor's packages (its own or its template chain's) name as
location, target or condition parameter there too. FNV's Find package
(the prospectors loot 5 containers, Allow Killing and Stealing) has no FO4
equivalent: FO4's Find procedure only picks a spot or seat for Sandbox and
Sit ([drift](fo4_drift.md#recorded)).

<a id="dialogue-conditions"></a>**Dialogue conditions (built 2026-10-14).**
Lines were left out when a condition named something the build lacks.
Three fixes (`conditions.without_absent`, `spike/condition_forms.py`):
- *Settled when the form is not in the build.* A test of an actor, voice
  type, cell, worldspace, quest (stage, variable, objective, running,
  completed), script variable, perk or casino the build leaves out reads 0
  here, as FNV reads an unrun quest's variable as 0: `GetIsID Other == 0`
  holds and drops out, `== 1` never holds and the line goes. OR groups
  settle as a whole (an always-true member satisfies its group). The
  engine's own forms (below 0x800, the player) are never settled.
  A test **run on** a reference the build does not write reads 0 the same
  way (`conditions.unbuilt_reference`); before, it kept FNV's raw FormID,
  which names whatever Fallout4.esm form has that id. One compared with a
  global cannot settle and leaves its line out, counted.
- *Script variables of placed objects.* GetScriptVariable converts on any
  placed reference whose base runs a converted script (actors, creatures,
  activators, containers, doors and the other scripted base types), not only
  on placed NPCs.
- *Made on demand.* An item a line counts or checks worn (GetItemCount,
  GetEquipped, and GetHasNote, which becomes GetItemCount on the player:
  notes are inventory items here) and a form list of items convert when a
  line names them; voice types, map regions' locations, the built cells and
  the worldspace join the lines' form map.
- *Renamed.* PlayerInRegion is GetInCurrentLocation on the player, of the
  location made from that map region (a cell takes the region holding its
  centre, so it is cell-grained where FNV tests the polygon).
- *Quest conditions.* An FNV quest's own conditions gate all its dialogue
  (vDialogueEDE: `GetIsID` ED-E; Doctors: DoctorsDialogueFaction, not Doc
  Mitchell's voice type). `say_topics.with_quest` ANDs them into each line,
  because the shared greeting quest and the Hub have no FNV quest to carry
  them. Without them, ED-E's beeps greeted everyone and doctor topics showed
  on every NPC. A player option is made per prompt **and quest**, so its
  shown conditions (the OR-groups its lines share, plus speakers) can scope
  it. One option for lines from several quests had none, and showed on
  every NPC: 37 prompts before, 1 after (`[Leave]`). When each line adds
  one test of its own to what they share, the option also needs one of
  those tests (an OR group, `Conversations._either`): Johnson Nash's "How's
  Primm these days?" has answers only once Primm has a sheriff, and showed
  with none before (fixed and played 2026-10-17).
  When lines add more than one test, the "some answer passes" test is
  spread into OR-groups: one per pick of a group from each line (an OR of
  ANDs as FO4's AND of ORs), up to `MAX_CLAUSES` (16). Nash's "How can I
  bring rule of law back to Primm?" showed after Beagle's rescue with no
  answer passing (each needs stage 100, or Meyers 2 and NCR 0), and
  choosing it stalled the talk; FNV hides such a topic. 8 options in the
  region changed (fixed and played 2026-10-18).
  Past `MAX_CLAUSES` the option had no such test at all: Tommy Torini's
  "Let's talk about the acts I recruited." (10 lines, 6 needing
  `VMSTopsTalentPool` stage 10) showed as soon as the quest ran (whole
  map, 2026-10-24). It now gets one OR-group of one group per line, the
  one most lines share (`conversation.one_each`): looser than the full
  spread, but false whenever no line could pass.

<a id="blank-choices"></a>**Blank choices (fixed 2026-10-24, not yet played).** On the whole
map, Cliff Briscoe offered one choice reading "dialogueentry" (FO4's
text for a choice with no prompt) and Manny Vargas an empty one. A
choice is a player line with the prompt and the answers' conditions
(`Conversations._prompt`), then one empty "pad" line per further answer,
so the player lines pair up with the NPC's. The pads had no conditions.
FO4 shows a topic's first player line that passes; when the prompt's
conditions failed (a topic not yet unlocked), the pad passed instead and
showed blank. Cliff's choice topic holds 11 prompts and their pads. Each
pad now carries its prompt's conditions.

<a id="one-option-per-topic"></a>**One option per topic (built 2026-10-26; Jason Bright's pair played 2026-10-26, Doc Mitchell's not yet).** FNV
shows a topic once, with the prompt of its first passing line. The build
makes an option per prompt and quest (`Conversations._option`), and the
whole-map path had dropped the spike's "no earlier option could be chosen"
test (`dialogue.exclusivity`), so a topic whose lines carry two prompts
showed both whenever both could pass. Found in the records while auditing
the [menu audit plan](fo4_menu_audit.md#exclusion): Jason Bright offered
"Sorry. Not interested." and "Like I said, not interested." together before
the first (Say Once) was said; Doc Mitchell offered "Okay, fix me. Here's
100 caps." beside "Sorry, I don't have 100 caps." to a player holding 100
caps. Up to 167 FNV topics have two prompts for one named speaker that can
pass together.
- *The test.* An option now also needs each line of another option of the
  topic that FNV tries before one of the option's lines to fail, unless a
  line of the option before it passes (`Conversations._earlier`). A line
  fails when a test of each condition group fails (the negated tests as
  one OR-group, or one per pick of a test from each group), its Hub quest
  is stopped, or, Say Once, its marker stage is done (`_unpassed`); "a line
  of the option before it passes" ORs in a group of each such line
  (`_unless`, Nash's "How can I bring rule of law back to Primm?", whose
  lines sit before and after four other prompts). A line whose conditions
  always pass leaves the option a never-true test (GetIsID of the player's
  base on the NPC), as FNV never reaches it.
- *Which lines count.* Only a line that can pass for the same actor
  (`_together`): the same speaker by a lone GetIsID, or a named speaker
  whose fixed facts let the other line pass (`speaker_facts`: its GetIsID,
  voice type and factions, through its templates). A faction any script
  changes (AddToFaction, RemoveFromFaction, SetFactionRank, ModFactionRank
  in scripts, lines, quests, packages and terminals) is never settled.
  (`_can_say` settles the line with `settled_on`, shared with holotapes.)
  Tried and dropped (third build, 2026-10-26): settling an earlier line
  naming no speaker on each of the option's speakers, one OR-group each
  guarded by "the speaker is not them". On FNV's records with every form
  built it cut GOODBYE by a fifth; on the real build it added 23% more
  tests (701,128 against 568,860), as one OR-group per speaker outweighs
  one shared one.
- *The cap.* The first build (2026-10-25) had neither and no cap: options'
  conditions grew from 476,319 to 3,578,008 (27.9 MB to 145.8 MB of the
  plugin), 99% of it in the shared GOODBYE topic, whose generic options
  came after dozens of named NPCs' own lines, every pad copying the tests.
  An option's test now takes at most `MAX_CLAUSES` OR-groups, earliest
  lines first; one past it is not tested (counted). On FNV's records (every
  form treated as built) a GOODBYE menu's share fell from 77,276 tests to
  10,723.
- *Not tested (counted):* a line whose negation does not convert or would
  need more than `MAX_CLAUSES` OR-groups, and one past an option's cap.
  Those options can still show beside the earlier one, as before.
- *Measured on the whole-map build (2026-10-26).* Menus where two options
  of one FNV topic can pass at once, by their built conditions alone: 760
  menus in 113 topics before, 152 in 8 after; Jason Bright's and Doc
  Mitchell's menus now exclusive. Of the 8: GOODBYE (the cap); three
  doctor topics the count reports only because it does not know speakers'
  fixed facts (Ada Strauss and Linda Schuler are not in
  DoctorsDialogueFaction, Doc Mitchell has the voice type the Doctors
  quest excludes); four (Big Sal, Gloria Van Graff, Diane, Primm's deputy)
  where the earlier option's own gate is looser than its lines (its "one
  answer unsaid" OR-group or speakers judged apart from the answers), so
  it shows with no answer passing. Options' tests: 476,319 before (27.9
  MB), 1,242,864 after (57.1 MB, 95% GOODBYE); the plugin went from 403 to
  432 MB.

<a id="say-once"></a>**Say Once across copies (built 2026-10-15; markers moved to their own quest 2026-10-19).**
In FNV, Say Once belongs to the NPC's line. Once it's said, the topic
drops out of every menu.
- **The problem.** The build makes a copy of a line for each menu or step
  it plays in. Sunny's "survive in the desert" topic sits in her greeting's
  choices and in the topic menu. FO4's Say Once (ENAM `0x4`) hid only the
  copy said, and FO4 has no condition reading whether an INFO was said.
- **Size (2026-10-15).** 234 Say Once lines; 84 had more than one copy
  (61 two, 14 three, 4 four, 5 seven).
- **The fix (`spike/say_once.py`).** A Say Once line gets one marker stage
  in one marker quest, `FNV_TES4SayOnce` (start game enabled).
  - Each copy carries the `F3NV_SayOnce` script (properties: the marker
    quest and the stage), whose `OnBegin` sets the stage as the copy
    begins; `OnBegin` runs beside the line's own fragments (vanilla's
    `TopicInfo.psc`). It plays only while the stage is not done
    (GetStageDone == 0 on the marker quest).
  - A player option whose answers are all Say Once shows while one of them
    is unsaid (one OR-group).
  - One marker per line, so a line with copies in two quests (the greeting
    quest and VFreeformGoodsprings) hides in both once said.
- **Why not the line's own quest (the first build, played 2026-10-19).**
  The markers first sat in the quest of each copy, set by TIQS (which can
  set only the INFO's own quest). FO4's GetStage, in scripts and conditions
  alike, reads a quest's *highest done* stage (CK wiki,
  `GetCurrentStageID`), so the first marker said stood in for the story
  stage: VCG01 read 22583 after "You're awake", its timer's
  `GetStage() == 5` never held and the intro stalled, while every
  `GetStage >= n` condition passed, so Doc stood up and gave his "please,
  have a seat" greeting. Any quest with a Say Once line was affected.
  Saves that heard a Say Once line under that build keep such a stage.
- **Stage numbers.** Each is hashed from the FNV line: 10000 + CRC32 mod
  55000. They stay put as content arrives; a collision moves up one.
- **Gap.** On an existing save, a line already heard through one copy can
  show once more through another.

<a id="karma-page"></a>**Karma page (built 2026-10-14).** Karma is the
`TES4Karma` global the scripts' RewardKarma sets (Karma conditions on the
player read it). Its Pip-Boy tab, KARMA on STAT (`spike/karma_page.py`; [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md)),
has two rows, actor values `F3NV_KarmaPage` sets on the player each time
the Pip-Boy opens (it cannot hook every change: karma moves through a
global, and the level on its own): Karma, very evil to very good by
FNV's thresholds (`fAlignVeryEvilMaxKarma` -750, `fAlignEvilMaxKarma`
-250, `fAlignGoodMinKarma` 250, `fAlignVeryGoodMinKarma` 750, from the
engine settings file), and Title, FNV's karmic title for that kind (evil,
neutral, good) and the player's level (capped at 30). FNV's titles are the
settings `sKarmicTitle<Kind><nn>`: FalloutNV.esm sets 53 of the 90 (the
Mojave titles: Samaritan, Mojave Legend, Vegas Crimelord), the rest keep
the engine's defaults, Fallout 3's titles (Vault Guardian, Urban Legend),
read from New Vegas's GECK (`oblivion_engine_extract.py --settings
sKarmicTitle`). The KARMA mod (Nexus 80425) shows its own Commonwealth
titles the same way, on STAT.

<a id="reputation"></a>**Reputation (built 2026-10-14).** FNV's reputations
take the Skyrim build's design
([fallout reputation](../commentary/tes5_import_character_data.md#fallout-reputation)):
each REPU is a FormList on FNV's own object id listing six globals
(infamy, fame, the mixed, good and bad threshold, the maximum,
`reputation_falloutnv.SLOTS`), `TES4_Reputation` keeps them in step and
re-derives the title from FNV's fame-by-infamy grid, the script
converter's AddReputation family calls it, a script property naming the
REPU gets the list, and GetReputation / GetReputationThreshold read a
global (`spike/reputation.py`). Two FO4 mods were read for reference:
REPUTATION (Nexus 79394) and KARMA (Nexus 80425) keep fame, infamy and
karma as actor values on the player, which their Pip-Boy pages (the Pip-Boy
Tabs F4SE plugin, a 4×4 title grid in `RPTN_ReputationTab.ini`) list. The
globals here show on the REPUTATION tab ([fo4_pipboy_tabs.md](fo4_pipboy_tabs.md)).

**Karma page redraw (2026-10-22).** In play, `set TES4Karma to 500` left
the page unchanged: `F3NV_KarmaPage` set its rows as the Pip-Boy opened,
after Pip-Boy Tabs had drawn them. Since 2026-10-23 our own plugin draws
the tab, filling its rows each time it shows
([fo4_pipboy_tabs.md](fo4_pipboy_tabs.md#how)), so that no longer
applies.

<a id="standings"></a>**Karma and infamy from kills and crimes (built
2026-10-22; kill karma played 2026-10-22: Powder Ganger kills raised karma).** `spike/standings.py`. FNV's engine scores
these itself. FalloutNV.exe's rules were read for the Skyrim build's
character rules
([karma and infamy](../commentary/character_rules.md#fallout-karma-and-infamy)),
and the FO4 build ports them; FO4 has all the events they need:
- **Data.** The same character data (`character_data`) and amounts
  (`amount_table`): the actors of each alignment (FNV's karma through
  trait templates: 32 very evil, 1,196 evil, 302 good, 10 very good in
  FalloutNV.esm; the lists hold those the build made); 188
  crime-tracking and 44 evil factions; for each reputation, the 37
  crime-tracking factions answering to it (FACT WMI1).
- **Amounts.** Karma per kill of a victim a crime-tracking faction
  claims: evil +100, very evil +2, good -50, very good -100; neutral
  0. Theft -5 unless the owner is evil; karma kept within -1,000 to
  1,000. Infamy: 30 for a reported murder, 2 for a kill in a fight or a
  reported theft or pickpocketing.
- **Rules.** `F3NV_FalloutStandings` on a start-game quest
  (`FNV_Standings`). It is `FalloutRules_Main`'s karma and infamy half;
  a leveled victim is sorted by its leveled base as well as its own.
  Karma moves through `TES4Polyfill.SetKarma` (traced `karma`), infamy
  through `TES4_Reputation.AddExact` (traced `rep`).
- **Kills and crimes.** Two event quests, `FNV_StandingsKill` (event
  KILL, `OnStoryKillActor` with its crime status) and
  `FNV_StandingsAdcr` (ADCR, `OnStoryCrimeGold`). Each is started by a
  Story Manager quest node added after the last child of Fallout4.esm's
  own event node (Kill Actor 00034A37, CrimeGoldEvent 00245FD3), sharing
  the event so vanilla's nodes still run.
- **Thefts.** The quest's player alias (`F3NV_FalloutStandingsPlayer`,
  all items through `AddInventoryEventFilter(None)`) reports each item
  taken. A rise in FO4's `Items Stolen` stat makes it a theft, charged
  to the owner: the container's, the item's, else the cell's.
- **Open.** Converted crime factions carry vanilla's no-crime-gold values
  (FNV has no bounty), so FO4 may never add crime gold and the ADCR
  event, the reported-theft infamy, may not fire. A reported murder
  comes through the kill event's crime status either way.

<a id="disguises"></a>**Disguises and faction armor (built 2026-10-22, not yet
played).** FNV's disguises are content, not engine code, and convert as
such ([drift](fo4_drift.md#candidates)):
- **FNV's mechanism.** Each faction outfit (the five `FactionGearNV*` form
  lists: NCR, Legion, Brotherhood, Great Khans, Powder Gangers; the White
  Glove set) carries an object script (`NCRFactionOutfitWarningScript`...)
  whose `OnEquip Player` saves the five reputations into
  `DisguiseFactionPulseQuest`, zeroes them, starts that quest and allies
  `PlayerFaction` with the outfit's armor faction (`ArmorNCRFactionNV`,
  which 860 NPC_ carry), and puts the player in its enemy twin
  (`ArmorNCRFactionNVEnemy`, the Legion's foe); `OnUnequip` undoes it and
  adds the saved reputations back. The quest's script (delay 1 s) casts
  `DisguiseFactionPulseActorEffect` on the player: a Touch spell of area
  25 and 5 s whose script effect (`DisguiseFactionPulseScript`) takes a
  sniffer (`VNCRSnifferFaction`...) out of the armor faction while it is
  near, and puts it back when the effect ends. Companions drop faction
  armor given to them (`OnAdd` + `DropMe`).
- **What was missing.** The scripts converted already (FO4's
  `OnEquipped`/`OnUnequipped`, reputation through `TES4_Reputation`,
  `SetAlly`/`SetEnemy` with FNV's friend and neutral flags, `GetEquipped`
  of a form list as `IsEquipped`). Three things kept them from running:
  - *Weapons and armor dropped their script.* A copy drops its FO4
    template's VMAD and now carries FNV's own instead
    (`Equipment._script`), filled like any object's (attach.py).
  - *The quest stayed out.* Quest scope saw only placed bases and actors,
    and outfits are carried. It now also reads the scripts of the items the
    build's placed actors and containers hold: inventories, leveled entries
    and inventory templates (TPLT when the Use Inventory flag is set), at
    any depth (`QuestScope._held`).
  - *The pulse spell was never made.* `spike/script_effects.py` converts a
    spell a script names (a Spell property) when every effect is a script
    effect (MGEF DATA.AssocItem is a SCPT), unconditioned, whose script
    converted: an FO4 Script-archetype effect carrying the converted
    `ActiveMagicEffect` script, on the DATA of Fallout4.esm's
    `BloodyMessNearbyEffect` (Script, fire and forget, Touch, its spell
    area 25: the same shape as FNV's pulse) with FNV's flags mapped bit by
    bit; the spell keeps FNV's FormID, type, magnitude, area and duration,
    fire and forget (an ability: constant), delivered at the effect's
    range. FalloutNV.esm has 86 script effects; 47 spells are all script
    effects with no conditions (11 of them abilities). A spell with another effect or a condition
    is left out, counted.
  - *`DropMe`* converts to `ObjectReference.Drop()` (FO4's and Skyrim's),
    where it was a TODO.
- **Region build (Goodsprings to Primm).** Against the deployed plugin:
  32 records added (`DisguiseFactionPulseQuest`, the pulse spell and its
  effect, 20 messages, `FactionGearNVBrotherhood` and the 4 armor pieces
  it lists), none removed, no FormID moved or reused. 30 armor and 3
  weapons gained FNV's script (the outfits; `WeapNVDetonator`,
  `WeapNVBoxingTape`, `VFSWeapLaserRifleVanGraff`); one VMS23 line's
  `DisguiseFactionPulseQuest` property is now filled. 16 spells scripts
  name are left out (not all script effects). Converted scripts: only the
  6 outfit scripts changed (`DropMe`). FO4Edit: 0 errors.
- **Who it affects there.** The armor factions' members, as in FNV: the
  generic Powder Gangers (`PowderGangerGun*` templates; the leveled pair
  at cell -11,-7, `VES04FactReactPowderGanger01`-`03` at -11,-16) and
  Primm's NCR. Joe Cobb's Goodsprings gang (`GoodspringsPowderGangFaction`)
  and Primm's convicts are not members, so an outfit does not calm them.
- **To check in play.** FO4 applying a Touch spell's area around the
  player when a script casts it on the player, and `Actor.IsEquipped` taking a form list (Skyrim's wiki says it
  does; FO4's is silent).

<a id="challenges"></a>**Challenges (built 2026-10-23, not yet played).**
`spike/challenges.py`, `F3NV_Challenges`, `F3NV_ChallengesPlayer`. FNV's
engine counts its 105 challenges (CHAL) itself; on FO4 a start-game quest
does, and they show on a CHALLENGES tab on STAT after KARMA
([tabs](fo4_pipboy_tabs.md#data)).
- **The record.** DATA is type, threshold, flags (start disabled,
  recurring, show zero progress), interval (a progress message every
  so many), then two u16 and a u32 whose meaning depends on the type; SNAM
  and XNAM are form links, also by type
  ([export](../commentary/tes4_export_falloutnv.md#challenges)). Read from
  the 105 records and their descriptions:
  - kill (types 0-2): Value2 a weapon skill (actor value: 34 Energy
    Weapons, 35 Explosives, 38 Melee, 41 Guns), Value3 a weapon type (FNV
    animation type + 1: 1 hand-to-hand, 4 one-hand pistol, 6 rifle,
    14 thrown), XNAM a weapon list; type 2's Value2 a creature type + 1;
    type 1's SNAM the actor;
  - hit (3): Value1 a body part (0 any, 1 head, 2 torso, 4 right arm),
    Value2 the kind (0 damage, 1 critical, 2 knockdown, 3 cripple), Value3
    and XNAM the weapon;
  - damage (8): as hit, Value2 the skill; discover (4): SNAM a map marker;
    use (5, 9): SNAM an item or a list;
  - misc stat (11): Value1 an index into the engine's 43 stats
    (FalloutNV.exe's table, `FNV_STATS`).
- **Census (FalloutNV.esm).** 41 misc stat, 18 damage, 16 kill with a
  weapon, 16 hit, 5 kill a creature type, 5 discover, 3 use an item, 1 use
  from a list. 39 are recurring, 35 start disabled (unlocked by another's
  reward), 35 show at zero progress. 99 name a reward script (58
  scripts), all effect scripts: `RewardXP`, `AddPerk` of a
  challenge perk with `ShowMessage`, `UnlockChallenge`,
  `RemoveRecurringFromChallenge` (when the perk's last rank is reached),
  `AddAchievement` (dropped).
- **Counting.** 61 are kept (26 recurring, 19 start disabled), each
  counted by one event:
  - *kills* (24: 16 with a weapon, 5 of a creature type, 3 any kill):
    `OnKill` on the player's alias. The weapon is the player's equipped
    one (`UnarmedHuman` when none), checked against a form list of the
    build's weapons of that skill, type and list (FNV's WEAP `DNAM.Skill`
    and animation type); the victim's base (or leveled base) against the
    creatures the build made of that type (CREA `DATA.CreatureType`,
    a Use Traits template's).
  - *FO4 tracked stats* (26): `RegisterForTrackedStatsEvent` on each,
    re-registered one above its value, the rise added. 20 FNV stats have an
    FO4 stat of the same name; Books Read is Skill Books Read, Weapon
    Modifications Weapons Improved, Items Crafted Chems Crafted plus Food
    Cooked. FNV's 5 critical-hit challenges count Critical Strikes with
    the weapon check.
  - *uses* (4): `OnItemEquipped` of a potion in the build's items for
    SNAM; *discoveries* (5): on each Locations Discovered rise, a marker
    the player can fast travel to; *Tough Guy*: `OnCripple` on the
    player; *Up to the Challenge*: each completion.
- **State.** Progress is an actor value on the player (the CHAL's FormID:
  the tab's row, FNV's name, description and "Goal: n"). A global per
  challenge (`FNV_<EditorID>`, the tab's shown global) holds -2/-1 while
  locked (hidden/shown once unlocked), 0 counting but hidden (FNV hides a
  challenge with no progress unless Show Zero Progress), 1 shown, 2 no
  longer recurring, 3 and 4 the same once completed. A non-recurring
  challenge stops at its threshold; a recurring one completes at each
  multiple.
- **Rewards.** The SCRI script, converted, runs as a fire-and-forget self
  spell cast on the player (`ScriptEffects.script_spell`, one per script:
  39 for the 56 kept challenges naming one), then the
  notification "Challenge Completed: <name>" (FNV's `sChallengeComplete`)
  and, each interval, "Challenge Progress: <name> n/goal". The converted
  scripts' `UnlockChallenge` (38 calls), `RemoveRecurringFromChallenge` (5)
  and `GetChallengeCompleted` (20, all in 5 rewards guarding a commented-out
  achievement) call `F3NV_Challenges.Unlock` / `StopRecurring` /
  `Completed` on the state global (a
  property named for the challenge); a left-out challenge's property stays
  empty and the call does nothing.
- <a id="challenges-left-out"></a>**Left out (44), no FO4 event:** damage
  dealt (18), hits by body part, cripples and knockdowns (11; FO4's hit
  event needs a target registered), and 15 misc stats FO4 does not track:
  caravan (3), casino (3), Barter Amount Traded, Health From Stimpaks and
  Food, Speech Failures, Disintegrations, Dismembered Limbs, Items
  Repaired, Miss Fortunate Occurrences, Doctor Bags Used. They have no
  row. Damage and hits would need a combat-hit perk entry point with a
  script per hit, measuring the target's health. Explosives kills count
  only with an explosive equipped (a thrown grenade is not the equipped
  weapon). A use or discovery whose item or marker is outside the build
  cannot progress.

<a id="globals"></a>**Globals (step 2, built 2026-10-12).** Only dialogue
unlocks, objective mirrors, helper globals and the engine globals were
made, so a script property naming one of FNV's own globals read None, and
every condition comparing against a global (the use-global flag, the
global's FormID in the value) dropped its line.
- `spike/globals.py` writes all 218 FNV globals on FNV's FormIDs with
  type, value and the Constant flag (`0x40` in both games). The six
  both games define (GameHour, GameDaysPassed, GameDay, GameMonth,
  GameYear, TimeScale) stay Fallout4.esm's.
- They join the shared `form_map`, so GetGlobalValue resolves; a
  property of type GlobalVariable takes the FNV global of its name.
- `conditions.fo4_value` keeps the use-global flag and maps the
  global's FormID through `form_map`, for both condition converters
  (say_topics' and conditions.convert); a global with no conversion
  still drops the line.

<a id="factions"></a>**Factions (step 2, built 2026-10-12).** `spike/factions.py`
writes all 682 FNV factions on FNV's FormIDs, read from FalloutNV.esm (the
export keeps rank numbers but not their titles).
- Relations (XNAM: faction, modifier, combat reaction) and ranks (RNAM,
  MNAM, FNAM) have the same layout in both games. A relation names a
  converted faction; one naming a race is dropped. INAM (insignia) is
  unused in FO4.
- DATA: FNV's two flag bytes become FO4's u32: hidden (`0x1`), special
  combat (`0x2`), track crime (`0x40`). Evil (karma) and Allow Sell
  have no FO4 bit; vendors come with merchants (step 3).
- FO4 requires crime values (CRVA) and vendor values (VENV). Vanilla's 699
  factions: 556 use "arrest, attack on sight, no gold", while
  crime-tracking ones mostly use "attack on sight, no arrest" (123), and
  443 have empty vendor values. The converted factions take those.
- Can Be Owner (`0x8000`, on 270 vanilla factions) is set on each faction
  FNV names as an owner (XOWN on 4,505 references and 158 cells), so
  ownership can follow.
- Factions join `form_map`, so GetInFaction and faction parameters
  resolve.

<a id="vendors"></a>**Vendors (built 2026-10-15, played 2026-10-21).**
Barter worked on the vanilla stand-in vendors, which brought their own FO4
vendor factions. The real FNV NPCs had none, so the barter menu was empty
on both sides.
- **Where FNV keeps it.** The merchant container is on the vendor's placed
  reference (ACHR `XMRC`): 76 vendors. The chests stand in
  `NVVendorChestsCell`. What the vendor trades is its AI services
  (`AIDT.Services`).
- **What we write.** `spike/vendors.py` gives each built vendor NPC its own
  FO4 vendor faction, rank 0. It uses the shape of 57 of vanilla's 92
  vendor factions:
  - DATA Vendor + Can Be Owner;
  - VEND, the buy/sell list, and VENC, the placed chest;
  - VENV: 0–24 h, radius 500, buys stolen and non-stolen items;
  - PLVD type 12.
- **Buy/sell list.**
  - A vendor whose services include weapons, armor, books or misc is a
    general store, like 61 vanilla vendors: `VendorItemsMisc` (no-sale and
    key items) with Everything Not In List.
  - A consumables-only vendor lists FO4 keywords: alcohol; food, drink and
    water; chems; stimpaks. Our consumables carry these keywords.
  - Example: Trudy (`0x14`, alcohol and food) gets the keyword list; Chet
    (`0x47F`) is a general store.
- **Placing the chests.** Each built vendor's chest, and only that chest, is
  added to the build with its holding cell.

<a id="ownership"></a>**Ownership and map markers (step 2, played 2026-10-12: owned doors, beds and a Goodsprings house's items show as owned; markers discovered, fast travel works).**
Both are copied from FalloutNV.esm by `spike/placement.py`, like the room
fields.
- **Ownership.** FNV's XOWN is the owner's FormID (4 bytes); FO4's is 12
  (owner, 4 unused, a No Crime byte, 3 unused), as all 5,909 of vanilla's.
  The owner maps to its converted faction or NPC (today only the stand-in
  clones); an owner not converted is dropped with its rank (XRNK, the same
  in both). Interior cells take their owner too (`pack_cell`). Goodsprings
  to Primm: 74 of 87 owned references and 11 of 14 owned cells; the rest
  are NPCs' (step 3).
- **Map markers.** Both games mark one with an empty XMRK, then FNAM flags
  (visible, can travel, "show all" hidden: the same bits), FULL and a
  2-byte TNAM whose first byte is the type. FNV's types map to FO4's of
  the same kind (`MARKER_TYPES`: settlement 2 → 13, cave 5 → 0, metro
  13 → 6, vault 14 → 15, …). The discovery radius (XRDS) is kept, as on
  246 of vanilla's 315 markers. FNV also puts TNAM and XRDS on other
  references (68 patrol points), so these fields are kept only beside
  XMRK. The region's 15 markers carry them (Goodsprings, Primm, the
  cemetery, Goodsprings Source, the Powder Ganger camps, …).
- Locations and encounter zones: [below](#locations).

<a id="locations"></a>**Locations and encounter zones (step 2, built 2026-10-12).**
FNV has no location records; FO4's quests, aliases and level ranges lean
on them. `spike/locations.py` builds them from what FNV authored:
- **Places.** FNV's regions with a map name (RDMP, the name FNV shows for
  where the player stands, 55 in FalloutNV.esm, Goodsprings and Primm
  among them) are polygons over a worldspace (RPLD points, world units).
  Each becomes a location under a root location named for the worldspace
  ("Mojave Wasteland"), which the WRLD names (XLCN). Its map marker
  (MNAM) is the built marker of the same name.
- **Cells.** An exterior cell takes the region whose polygon holds its
  centre, else the root. An interior takes the location of the exterior
  door leading into it (doors by FormID, nearest first), passed on through
  interior doors, as `interiors.reached` walks them.
- **Fields.** Vanilla's commonest layout: EDID, FULL, PNAM parent, MNAM
  marker, RNAM, ANAM 1.0 (393 vanilla locations; keywords left out until a
  quest needs one). The CK-computed reference lists (LCPR, LCUN, LCEC …)
  are left out, as a plugin may. Locations are generated, so their ids are
  hashed from the region's (or worldspace's) FormID.
- **Encounter zones.** All 17 FNV zones on FNV's ids: owner (through the
  converted factions and NPCs), rank, minimum level and flags (Never
  Resets, Match PC Below Minimum: the same bits); FO4's location and
  maximum level are 0. Cells keep their XEZN (84 in FalloutNV.esm, all
  interiors; Bison Steve's and Vikki and Vance's in the region).

<a id="npcs"></a>**NPCs (step 3, in progress).** `spike/npcs.py` replaces the
spike's stand-in actors with every FNV NPC placed in the built cells.
- **The body.** Each FNV NPC base becomes a copy of a vanilla NPC for its
  race and sex (the replacement table's `_rules.body`: DocWeathers, DoctorAmari, the ghouls Jones and
  Holly), keeping that NPC's outfit, class and voice for now. FNV's name,
  factions (SNAM with rank, through the converted factions), AI packages
  and script replace the copy's; its factions and crime faction are left
  out.
- **Outfit and inventory.** FNV keeps worn and carried items in one list.
  Its armor, and leveled lists of only armor (`Items.wearable`), become
  the NPC's outfit (OTFT, keyed by the NPC's FNV id); the rest its
  inventory (CNTO); both replace the body's. Items the replacement table
  leaves out take its defaults ([replacements](fo4_replacements.md)), so
  81 of the region's 84 NPCs wear FNV's clothes and 46 weapons convert
  (3 skipped). Caravan cards and money (CCRD, CMNY: 342 entries) wait for
  the Caravan system.
- **The face.** A male human takes FNV's face fitted to FO4's sculpt
  regions, tints and head parts, as Doc's was. Each fit is cached
  (work_cache), since the tint fit takes about 8 s. The fits are calibrated
  for male humans only, so women and ghouls keep their body's face.
- **Templates.** FNV's template flags (ACBS) are followed per part:
  traits (race, face, sex), factions, AI packages, script. An NPC whose
  traits come from a leveled list (LVLN) is left out until leveled NPCs
  convert.
- **Placement.** Every ACHR in a built cell, persistent as in FNV, with
  its parents, ownership and linked reference. The ids keep the spike's
  keys (`NPC_ <FNV id> STH`, `ACHR <FNV id> STH`), so Doc's moved
  nowhere.
- **Conversation ids keyed on authored data** (approved drift, 2026-10-12).
  With real speakers, 300 dropped lines returned, and 165 of VDoctors'
  generated scene and topic records moved id while 271 were replaced: a
  step's key listed the lines found that build (the Hub's topic list, a
  script's topic), so any line arriving shifted it. `Conversation._key`
  now keys the Hub's menu as `menu hub` and a script-started step by its
  topic (`talk <topic>`); FNV's follow-up, choice and part steps keep their
  authored contents; a player option is keyed by its FNV topic and prompt
  text. Content arriving later adds records without moving any.
- **First NPC play-test (2026-10-12), fixed:**
  - *Doctors' options on everyone.* A menu option answered by several
    speakers' lines is gated by those speakers (GetIsID). A line whose
    speaker is not built gave up the gate ("anyone may answer"), so Doc's
    "I need medical supplies" showed on Chet and Easy Pete. Such lines are
    now left out of the gate; only a line with no speaker test opens it.
  - *Invisible dresses, missing arms* (Trudy, Sunny Smiles).
    `outfit.worn` paired converted shapes with FNV's by name, but FNV
    names some alike: Trudy's dress and shoes are both "arms", so the dress
    (1,786 vertices) was fitted onto the shoes and collapsed at the feet.
    Shapes now pair by name in tree order (`outfit.in_order`, also for
    material swaps).
  - *The menu behind barter.* A line whose FNV result script opens barter
    (`ShowBarterMenu`: 86 in end scripts, 4 in begin) now ends the
    conversation scene (End Running Scene, as vanilla's vendor lines), so
    barter shows alone. FNV returned to the talk after barter; in FO4 the
    player talks again. Played 2026-10-19: Johnson Nash's barter
    (`PrimmNashDialogue`, three lines, all end scripts) still opened over
    the talk. `TES4Polyfill.ShowBarterMenu` waited at most 2 s for the
    dialogue menu to close, and it had not. It now stops the vendor's
    current scene first (`GetCurrentScene().Stop()`), which closes the
    menu, then waits and opens barter.
  - *NPCs standing still:* see [packages](#packages).

<a id="script-packages"></a>**Script packages on NPCs (built 2026-10-16, played 2026-10-21).**
FO3/FNV's `AddScriptPackage <package>` gives an actor a package that
outranks all its others. An actor holds one at a time: a second replaces
the first. `RemoveScriptPackage` takes it away.
- **Size.** FalloutNV.esm has 1,114 `AddScriptPackage` calls on NPCs (516
  packages, 352 actors) and 127 `RemoveScriptPackage` calls.
- **The failure.** The FO4 target converted both commands to
  `EvaluatePackage()`, so no script package ever ran. Example, VMS16:
  Ringo's "Let's do this" moves Sunny to her spawn marker and gives her a
  dialogue package to grab the player. She appeared at the gas station
  and walked straight back out on her own packages.
- **The fix, FO4's own mechanism.** An alias whose package list holds a
  package runs it ahead of the actor's own packages.
  - `spike/script_packages.py` writes one start-game quest,
    `FNV_TES4ScriptPackages`: an empty collection alias per package any
    converted script names. Alias i runs `Packages[i]` of its
    `F3NV_ScriptPackages` script. Collection aliases use vanilla's layout
    (CZ_Arena's Crowd: ALCS, ALMI, ALST, ALID, FNAM, ALPC, VTCK).
  - Converted `AddScriptPackage` is `TES4ScriptPackages.Add(actor,
    package)`. It takes the actor out of every alias, adds it to the
    package's alias and re-evaluates.
  - `RemoveScriptPackage` is `Remove(actor)`.
  - The player's own script packages keep their seat handling.
- **Drift.** FNV also drops a finished script package without "must
  complete" at the next re-evaluation. Here it stays until replaced or
  removed: a Travel package's actor keeps standing at its destination
  until the script moves it on.

<a id="overlay-decals"></a>**Overlays as decals (built 2026-10-16, played 2026-10-21).**
FNV's graffiti, posters, stains, grave text and blood splats are blended,
lit, flat sheets set just in front of a surface. Most carry no decal flag:
47 of 55 FNV graffiti meshes don't.
- **What we did before.** They took the cut-out path
  ([blended lit surfaces](fo4_spikes.md#spike-2-transparency)): alpha test at
  128, with their mostly see-through triangles split off to the
  translucent BGEM.
- **What the player saw** (Lone Wolf Radio trailer, 2026-10-16). Half-lit
  graffiti cut by a diagonal, which is the triangle edge between the two
  materials. "LET IT ALL END" was mostly missing, since faint strokes fell
  under the cut-out threshold.
- **Placement was ruled out.** FO4 stores reference rotations as FNV does:
  in 24 of 25 vanilla references found in precombined meshes, the stored
  matrix is FNV's convention (X, then Y, then Z, angles negated). The
  graffiti's FNV transforms lay it flat, about 2 units off the trailer
  wall.
- **The fix.** `convert_static.overlay_sheet` treats a blended lit shape
  that is flat (every vertex within 0.5 units of one plane) and still (no
  controller or skin) as a decal: a blended BGSM with the Decal flags, like
  FO4's own placed decal meshes (`effects\decalsplaced`).
- **Census** (the region's meshes; the scan stopped at its 110 s limit
  partway through). 36 flat blended shapes: graffiti, grave text, the
  Vault 87 blood splats, posters and sign stains. Also two animated flags,
  which are excluded because they have controllers, plus a freezer lid, a
  pinto bean pod and a scope part. 90 non-flat blended shapes (plants,
  hotel walls, trees) keep the cut-out.

<a id="still-bodies"></a>**Bodies that collide with nothing (built 2026-10-16, played 2026-10-21).**
FNV's Broc Flower and White Horse Nettle plants had a dynamic physics body
(motion 4, mass 45, BSX Dynamic) on layer 15, NONCOLLIDABLE.
- **What happened.** FNV left those bodies asleep. In FO4 the body fell
  through the ground, since a body on that layer touches nothing. The
  plant then reset to its placed spot and fell again.
- **Census.** Of FNV's 261 ACTI models, only these two have a moving
  body on a non-collidable layer; every other moving body is on a real
  layer. Vanilla FO4's harvestable plants (hubflower, bloodleaf,
  carrotplant, tato) all have a fixed body on layer 15, BSX 130.
- **The fix.** `collision.moves` treats a body as moving only when it is
  neither keyframed nor fixed, and it either sits on a colliding layer or
  hangs on a constraint. The constraint case is a hanging light,
  `offrmlighthanging01`: its non-collidable bulb swings on a constraint.
- **Blast radius.** Of the build's 2,040 FNV meshes, four change: Broc
  Flower, White Horse Nettle, dead Xander root and `maizewitheredgroup2b`
  (48 maize bodies).
  - A body that doesn't move is written fixed, unless it is keyframed on
    an animated node.
  - A mesh whose bodies are all still drops BSX Dynamic.

<a id="actors-on-the-ground"></a>**Actors on the ground (built 2026-10-16, played 2026-10-21).**
FNV's records place some actors slightly below the landscape, and FNV set
them on the ground as they loaded. FO4 places an actor where its record
says, so such an actor started underground and fell through. Example: a
leveled gecko spawn at z 6668 over ground at 6672.
- `Exterior.on_ground` raises an exterior actor standing below the ground
  to it. The ground height is the highest corner of the landscape square
  the actor stands in, from FNV's own height map (VHGT, decoded with the
  navmesh code's `decode_vhgt`). On a slope that drops it a few units onto
  the ground instead of starting it inside the hill.
- Actors standing above the ground (rooftops, ledges) and actors in
  interiors keep their recorded position.

<a id="creature-stats"></a>**Creature stats (built 2026-10-15, played 2026-10-21).**
A converted creature is a copy of its FO4 stand-in with FNV's stats written
into PRPS (`creatures.with_stats`). FO4 adds two things on top of the NPC's
own health: its race's starting health (RACE PRPS) and a per-level bonus.
- **Measured (trace, 2026-10-15).** The base health of FNV's well-3 gecko
  (20 health, level 3, on the vicious dog: race 30) read 60. The Goodsprings
  settler (100, level 1, human race 40) read 140. Your varmint rifle took
  6–15 off a gecko per hit, so one needed 4–6 hits, against about 2 in FNV.
- **The per-level bonus is a reading, not yet confirmed.** We use
  (level − 1) × `fNPCHealthLevelBonus` (5.0); the gecko's extra 10 fits it.
  (level − 1) × (Endurance / 2 + 2.5) fits the same point, so another
  creature's trace decides.
- **Health.** The NPC's health is now FNV's less the race's and the level
  bonus, so in game the creature has FNV's health.
- **Attack damage.** FNV's `AttackDamage` replaces the stand-in's
  `UnarmedDamage`, which its unarmed attack deals (the vicious dog's 10 bit
  the settler for 9).
  - The trace showed a giant mantis nymph, on the stingwing's attack, taking
    20–28 off a 105-health level-1 player.
  - FO4's player starts with about half of FNV's health (FO4 105 against
    FNV about 200 at Endurance 5). That gap is not converted yet.

<a id="packages"></a>**AI packages (played 2026-10-12: NPCs sandbox, sit
and sleep).** `spike/packages.py` copies a vanilla instance of the
matching FO4 template per FNV type (`PLANS`): Travel (a seat: Sit),
Sandbox, Wander (as Sandbox), Sleep, Eat, Guard (HoldPosition), Patrol,
Follow (FollowNPC), UseItemAt a seat (Sit), Dialogue with the player
(ForceGreet). The copy takes FNV's first input, schedule, conditions and
shared PKDT flags, and drops its owner quest and scripts. The build log
counts each left-out package by reason. In the region 45 of 110 convert;
49 wait on quests not built (VFreeformGoodsprings, VMS16, nVPrimmDeputyConv:
Trudy, Joe Cobb, Ringo, Sunny, McGee).
- **The month.** Form version 122+ records store PSDT's month one higher
  (xEdit `wbPackagePSDTMonthValueToStr`): Any is 0, as in all vanilla
  packages of that version; −1 in older ones. Writing FNV's −1 made every
  package's schedule fail, so no NPC moved: this hid the fixes below until
  it was found. The minute is −1 (242 of vanilla's 252 timed schedules),
  the duration FNV's hours × 60.
- **Places.** NPC packages see the exterior block's references and every
  built cell (FNV's "in cell"); seats are every FURN reference in the build.
  An in-cell Sleep goes to a bed in that cell the NPC owns, else an unowned
  one (`_bed`, FNV's choice), as a near-reference Sleep: with the cell
  alone Chet and Easy Pete stopped at the door.
- <a id="in-cell-places"></a>**In-cell places (built 2026-10-16, played
  2026-10-17: Chet walks his store).** NPCs with an FNV "in cell" package stood still or bunched up
  in cells whose navmesh doesn't cover the cell's origin: Chet in the
  General Store and the Vikki and Vance residents in a corner. The Prospector Saloon, whose navmesh covers the
  origin, worked. So such a package now becomes "near reference": the
  cell's built reference nearest the middle of its navmesh's bounds, with
  a radius reaching the navmesh's farthest vertex (`Packages._in_cell`).
  Without a navmesh or a built reference, the in-cell location is kept.
  - *Persistent anchors.* The first anchors were the nearest reference of
    any kind (a mannequin in the casino). Chet then moved, but the casino
    residents bunched at the casino door: FO4 keeps a non-persistent
    reference unloaded while its cell is, so while the player was outside
    the package had no place and the residents fell to their next one
    (FNV's DefaultSandboxLinkedMarker1024, to markers in their Primm
    houses), heading out the door. The CK makes a reference a package
    points at persistent; the anchor is now a persistent reference (flagged,
    or a teleport door) when the cell has one.
- <a id="sandbox-allows"></a>**Sandbox switches (built and played
  2026-10-17: the casino residents spread out).** Every Sandbox copy came from one vanilla instance,
  MinutemenRadioOperatorSandboxDefault, whose Allow inputs leave only
  conversation and wandering on (eating, sleeping, idle markers, sitting
  and special furniture off). The Primm residents, who sandbox with their
  weapons drawn (FNV general flag 0x800000, Weapon Drawn in both games),
  then had nothing to do and stood where they were: at the casino door,
  inside the anchor's radius, in the save. FNV authors these per package as
  type-specific No flags (No Eating 0x1, No Sleeping 0x2, No Conversation
  0x4, No Idle Markers 0x8, No Furniture 0x10, No Wandering 0x20, xEdit
  `wbDefinitionsFNV`), so an FNV Sandbox or Wander now sets each FO4 Allow
  input to the negation of its flag (`ALLOWS`; No Furniture covers Allow
  Sitting and Allow Special Furniture). The inputs are found by the
  Sandbox template's data names (`value_slots`), not by position.
- <a id="greet-trigger"></a>**A force greet waits for its trigger (built
  2026-10-19, played 2026-10-21).** A ForceGreet copy kept vanilla's Target
  Trigger Location (near its editor location, 250), so FNV's trigger was
  lost: the Primm warning trooper (`PrimmWarningPackage`) reacted only
  within 250 units of his post. FNV's Dialogue package names it as PLD2
  (210 FNV packages), the second location input of FO4's ForceGreet
  template (`Packages._trigger`, as the Skyrim side's `_greet_at_place`).
  The trooper's is near `PrimmWarningMarker` with radius 0: a trigger box
  (XPRM half extents 2,513 by 1,875, centred about 415 units from him).
  FO4 has no "inside a box" location, so a box with radius 0 reaches its
  smaller half extent (1,875): he runs out once the player is within it.
  The leash (player, 5,000) and the greet distance (player, 200) stay
  vanilla's.
  - *Greet distance (tried and reverted 2026-10-19).* FNV's Dialogue
    package keeps its Activate Distance in PTDT's count ("how close to
    the target the actor needs to be before initiating dialogue", GECK;
    239 of FNV's 293 player Dialogue packages set one, 256, 512 and 1,024
    commonest). FO4's ForceGreet has a Forcegreet Distance, its third
    location input (near PlayerRef; 122 of vanilla's 217 instances use
    225, 3 use 1,000). Given FNV's count, the Primm trooper ran out, showed
    his "..." prompt at 1,024 units and never spoke (played): FO4 stops the
    actor at that distance but starts the conversation only once the
    player is in talking range. FNV pulls the player into dialogue from
    the activate distance; FO4 does not, so the template's 200 stays.
- <a id="hit-proof"></a>**Actors a script keeps alive (built 2026-10-19,
  played 2026-10-21).** Six FNV scripts reset their actor's health in an
  OnHit block (`ResetHealth`), used by 7 actors: Sunny's Well 3 geckos and
  the settler fighting them (`VFreeformGoodspringsGeckoWell3DeathSCRIPT`,
  `VCG02GSSettlerSCRIPT`: neither dies until the player, Sunny or Cheyenne
  hits a gecko), Doc Mitchell during his intro, Max and Stacey, the VMS18
  assassin and a child. FNV runs OnHit before the hit can kill; FO4's
  Papyrus OnHit is queued after the damage, so the converted reset came
  too late: one or two hits killed a 20-health gecko, the settler then
  had no package (his three wait on objective 50) and went on to Well 2
  (played 2026-10-19: the geckos were dead when the player arrived). These
  actors are now Protected (ACBS 0x800, `actor_data.hit_proof`): only the
  player kills them; anyone else's hits leave them in bleedout. The script
  still runs.
- <a id="package-flags"></a>**Package flags (built 2026-10-19, not yet
  played).** Bit meanings from xEdit's `wbPackageFlags` (one table, per
  game), xNVSE/JIP `kPackageFlag_*`, the GECK wiki and the Skyrim CK
  wiki's Package Flags page (FO4 shares Skyrim's); counts are FNV's 4,163
  packages and Fallout4.esm's 3,828.
  - *Behavior flags.* FNV's PKDT "Fallout Behavior Flags" (Hellos To
    Player, Random Conversations, Observe Combat, Greet Corpse, Reaction To
    Player Actions, Friendly Fire Comments, Aggro Radius, Idle Chatter) are
    FO4's PKDT Interrupt Flags bit for bit (xEdit names them alike). They
    count only when general flag 0x1000 is set (xEdit: Skip Fallout
    Behavior; the GECK's checkbox is "Enable Fallout Behavior"): all 812
    FNV packages with authored nonzero behavior flags set it, and the
    2,500 without it hold 0 or uninitialized 0xCDCD (276 FO3 leftovers).
    So with 0x1000 FNV's eight bits replace the copy's low byte
    (`_pkdt`); without it the vanilla instance's flags stay. Avoid
    Radiation (0x100, 659) has no FO4 bit.
  - <a id="combat-override"></a>*Continue During Combat (0x4000000, 399).*
    FNV keeps running the package in combat, fighting as it goes. FO4 has
    no such flag; its mechanism is an NPC's Combat Override Package List
    (ECOR, a form list): in combat the first valid package there runs
    instead of combat AI. That fits a hold: the Skyrim CK wiki says a
    HoldPosition there keeps the actor fighting inside its radius, while
    a Travel there stops the actor attacking. So an FNV Guard (HoldPosition)
    with the flag (87 packages) gets a second copy with interrupt override
    Combat (4, as all 14 packages on vanilla's 9 override lists) and
    without fragments, and its NPC gets an ECOR list of them
    (`Packages.combat_list`; ids hashed from the FNV package and NPC). The
    other types (Travel 153, UseWeapon 43, Follow 57, Patrol 32 ...) stay
    drift: they drop the flag and fall to FO4's combat AI. Creatures don't
    get the list yet. Only FNV Guards qualify, not every HoldPosition copy:
    the Goodsprings settlers' cowering flee (`GoodspringsFleePackage`, a
    HoldPosition with the Cowardly script) carries the flag too, and a
    combat copy without that script would have them fight.
  - *In the region build.* 91 of 197 packages take FNV's behavior flags
    (42 Travel, 18 ForceGreet, 10 Sandbox, 8 HoldPosition ...); 4 Guards
    get combat copies, listed on Trudy and three settlers for the
    Goodsprings gunfight. No existing FormID moved; no other NPC field
    changed.
  - *Dropped, no FO4 meaning.* Defensive Combat (0x400000, 158) is
    "Unused" (GECK). No Warn/Attack Behavior (0x10000000, 250), Pretend In
    Combat (0x2000000, 53) and No Idle Anims (0x1000000, 29) sit on bits
    FO4 leaves unnamed; Head-Tracking Off (0x100000, 114) is FO4's Ignore
    Combat bit, so it must stay dropped. Recorded in the
    [drift table](fo4_drift.md#recorded).
- <a id="follow-distance"></a>**Follow distance (built 2026-10-19, not yet
  played).** FNV's Follow and Accompany keep their distance in PTDT's
  count (125 of 132 Follows and all 14 Accompanies set one, 50 to 768).
  FO4's Follow procedure takes Min Radius ("too close, the follower will
  not walk") and Max Radius ("too far away, the follower will begin
  running"); FNV's follower closes to within its distance, so the
  distance is Min Radius and Max Radius stays the instance's 600 unless
  FNV's distance is farther (`Packages._radii`). Vanilla's 26 FollowNPC
  packages pair them with no fixed ratio (200/500 most often). In the
  region 5 FollowNPCs change (128 to 512).
- <a id="combat-styles"></a>**Combat styles (built 2026-10-25, not yet
  played; replaced the 2026-10-19 vanilla-style-by-weapon-restriction
  mapping).** `spike/combat_styles.py`: each FNV CSTY becomes its own FO4
  CSTY (`FNV_<EditorID>`, derive_formid site `FNV CSTY`, key the FNV
  FormID), written when an actor first names it. NPCs and creature
  stand-ins take their traits source's style (creatures replace their
  vanilla stand-in's, e.g. csDeathclaw); an actor with no ZNAM gets FNV's
  form 0x3D `DefaultCombatstyle`, as FalloutNV.exe does (NPC load
  0x603558, creature 0x5f9601, both `0x505000` = lookup 0x3D). The method
  is the Oblivion one ([tes5_import_actors.md](../commentary/tes5_import_actors.md#combat-styles)):
  invert each FNV per-decision chance onto the FO4 multiplier that gives
  it. Fields FNV has no source for keep Fallout4.esm `DefaultCombatStyle`'s.
  - **FO4's side** (Fallout4.exe 1.11.240 unpacked). Every multiplier
    feeds `lerp(min, max, mult)` (0x101b540, unclamped) of two
    `fCombat*Min/Max` settings; Fallout4.esm overrides none of them.
    TESCombatStyle offsets: CSGD +0x20, CSME +0x50, CSRA +0x78, CSCR +0x7c,
    CSLR +0xa8, CSCV +0xbc, CSFL +0xc0, DATA +0xe0.

    | Chance | Getter | Min–Max | Mult |
    |---|---|---|---|
    | Melee attack | 0x101c700 | 0.025–1.0 (Min read from the image, the dump shows no thunk) | Offensive × group term; × max(Attack/PA Staggered) on a staggered target |
    | Block | 0x101cb52 | **0–0** | Defensive: never blocks in vanilla |
    | Block threat | 0x101cb14 | 0–1 | Defensive |
    | Dodge / avoid / evade threat | 0x101d564 / 534 / 594 | 0–1 | CSGD Dodge / Avoid / Evade |
    | Circle, fallback (Dueling) | 0x101b8a4, 0x101b7e4 | 0–0.75, 0–0.5 | CSCR |
    | Cover search distance | 0x101bf40 | 128–4096 | CSCV; 0 or less takes no cover |
    | Optimal range | 0x101cff0 | three-point 0.1 / 1.0 / 1.5 of 2·mult − 1 (0x101b5a0) | CSLR Range |

    Defensive − Offensive is a stance (0x101b16e, 0x101b1ae) and scales
    the optimal range, so Defensive is capped at Offensive for a style that
    attacks, as in Skyrim. Gun fire waits are `lerp(2.0, 0.0, Offensive)`
    (0x101d8c7): no field of their own for FNV's fire timers.
  - **FNV's side** (GOG FalloutNV.exe; a subagent's trace, the default
    style, attack score and roll re-read). Melee re-decides each AI update:
    attack score A = (Attack% + recoil, knockdown and hand-to-hand bonuses
    + skill base + skill mult × skill/100) × under/not-under-attack mult ×
    (target blocking ? during-block mult : 1) (0x644680); block B = (Block%
    + base + mult × 0.5, skill fixed at 50) × under/not-under mult ×
    fBlockScoreNoShieldMult 0.5 × (target attacking ? 1 : 0.25)
    (0x644580); hold H = max(100 − A − B, fCombatMaxHoldScore 30); one
    `rand() % int(A + B + H)` picks (0x9cc8de). Dodge (melee only, while
    the target swings): D = (Dodge% + fatigue and speed terms) × mult,
    passing `rand() % 100 <= D` (0x644990); direction by three 1–5 draws ×
    fAIDodgeDecisionBase 10: back if back ≥ forward and > side, forward
    only beyond 1.5 × reach, else side on the Left/Right% roll (0x644a70).
    Ranged: take cover re-rolled every 10 s; cover search radius in units;
    range mults scale the weapon's min/max range; weapon restrictions
    divide the other kind's weapon score by 10,000 (0x6461cb). Flags: bit 0
    picks power-attack directions only; Ignore Threats stops threat
    detection; no reader of Acrobatic Dodge% or Melee Alert OK.
  - **The mapping:** Offensive from A's share not under attack, Defensive
    from B's share under attack (both with weapon skill 50); Attack
    Staggered from the share with the recoil bonus over the share without;
    Power Attack Staggered (PA% + fatigue base + bonus) / (PA% + fatigue
    base); Dodge from the under-attack dodge × the chance a direction is
    taken (exact over the 125 draws, at melee range against a melee
    target), Circle and Fallback from the not-under-attack side and back
    dodges; a Ranged Only style dodges, circles and falls back 0 (FNV's
    ranged procedure never dodges); Ignore Threats writes Avoid and Evade
    0; cover 0 without a take-cover chance, else the radius on 128–4096
    (at least 1e-4, so a radius under 128 still searches); Range Mult from
    FNV's mean range mult; Melee Only scores ranged 1e-4, Ranged Only melee
    and unarmed 1e-4. CSME and CSLR are written at vanilla's commonest
    sizes, 10 and 5 floats.
  - **Values** (all 84 finite): DefaultCombatstyle (2,904 actors) Offensive
    0.49, Defensive 0.37, Dodge 0.53; CSDeathclaw Offensive 0.78,
    Defensive 0.08, Dodge 0.14 (FO4's csDeathclaw: 0.7, 0, 1.0).
  - **Dropped** (drift): per-actor terms (weapon skill at 50, speed and
    fatigue terms: FNV adds `int(CalculateWalkSpeed) × mult + base` and the
    fatigue fraction); fire/wait/hold timers; rushing attacks and
    power-attack direction weights (FO4 takes attacks from the race's
    attack data); combat radius; Max Targeting FOV; flee, stealth-boy and
    ignore-damaging flags; partial take-cover chances. Package-level
    combat styles (FNV PACK CNAM) are not exported, so not carried.
  - **Template actors.** FNV keeps ZNAM under Use Traits (0x5fb9c5); the
    FO4 CK wiki puts Combat Style on the AI Data tab, so FO4 inherits it
    with Use AI Data (not confirmed in the exe). A template actor therefore
    gets the style its FNV traits chain reaches as its own ZNAM
    (`npcs._template_style`), which FO4 reads only when AI Data is its
    own; a chain that reaches a leveled list gives none (FNV takes the
    drawn actor's). Whole-map build 2026-10-25: 48 styles; 1,674 plain
    actors and 179 template actors on converted styles (0 template actors
    before `_template_style`), 576 template actors with none and 2 on their
    creature body's vanilla style; the 24 plain NPCs without one are
    holotape and radio speakers. FNV-wide, 924 list-templated actors also
    take AI Data from the list (FO4 then inherits the drawn actor's
    style); 179 keep their own and fight with FO4's default style.
- <a id="creature-attacks"></a>**Creature attacks (built 2026-10-25, not
  yet played).** `spike/creature_attacks.py`: a converted creature keeps
  its stand-in's behaviour graph, so it can only play the attack events its
  race lists; each creature gets its own attack list (ATKR its stand-in's
  attack race, then every one of that race's events), each event kept or
  set to chance 0 by what FNV lets the creature do.
  - **FO4's side** (Fallout4.exe; a subagent's trace, the pick loop
    re-read). BGSAttackData is 0x60 bytes: event +0x10, ATKD from +0x18
    (chance +0x1c, flags +0x28, attack angle +0x2c, strike angle +0x30,
    recovery time +0x44 used as the attack's cooldown). An NPC with ATKR
    merges: its entries whose event the attack race lacks are dropped, then
    the race's entries it lacks are added (0x6ffb2f–0x6ffddc), so a race
    attack is suppressed only by listing it at chance 0; ATKD without ATKR
    is the NPC's alone. The chooser (0xf7b5c0) pools the entries whose
    time-to-hit (the clip's `HitFrame`; continuous 1.5 s) is over 0, whose
    cooldown has passed and whose weight (chance × the style's Attack /
    Power Attack Staggered or Power Attack Blocking mult, 0x101c890) is
    over 0; it picks `r = rand(0, total)` by running sum, then rejects when
    `rand01() > weight` or the cone (|target heading − (facing + attack
    angle)| ≤ strike angle × mult, 0xef3030), reach and path checks fail,
    and picks again from the rest. Power and normal attacks share the pool:
    no separate power roll (fAIPowerAttack* have no readers). Power attacks
    and bashes cost action points and are skipped at 0. Bash attacks are a
    list of their own for blocking; charge attacks also feed the charge
    behaviour.
  - **FNV's side** (FalloutNV.exe). A creature's normal attack is
    AttackLeft or AttackRight by its movement clip's `m:` text key
    (0x9ccb20), the `_A`/`_B` variant uniform (0x48f450); power attacks are
    AttackPower/Forward/Back/Left/RightPower by direction; a group with no
    animation means no attack that time. The hit: reach from CREA RNAM,
    a 35° cone (fCombatHitConeAngle, 0x9a6ae0), damage the creature's own
    attack damage with no power bonus (0x8ae98a skips it for creatures).
  - **The mapping.** Off (chance 0): an attack aimed outside FNV's cone
    (|attack angle| > 35); a power attack when the style's power attack
    chance is 0 or the creature has no power-attack animation (by its
    `.kf` groups); a charge attack when the style has no rushing attack;
    whatever vanilla already disables. Kept: damage mult 1; normal and
    power entries weighted so power attacks take FNV's share of attacks,
    (PA% + Power Attack Fatigue Mod Base + 1) / 100 at full fatigue
    (0x644810), the smaller weight 1 so FO4's acceptance roll never
    rejects; entries uniform within each kind, as FNV's variants are.
  - **Not carried:** FNV's power-attack direction weights (FO4's numbered
    events name no direction), the left/right foot rule, rushing attack
    chance and reach (the next step, with movement speeds), FO4-only front
    attacks that look like nothing FNV has (the deathclaw's horn ram and
    tail combo pass every test). Unverified: whether converted creatures
    have action points for power attacks.
  - <a id="attack-spells"></a>**Attack spells (built 2026-10-27; the deathclaw knockdown played).** FNV casts a
    creature's unarmed attack effect (CREA EITM, a SPEL; part of the Actor
    Effect List template part) on every unarmed hit. The export never
    carried it (217 creatures: radscorpion poison 39, bark scorpions 11,
    cazadores 21, nightstalkers 28, the glowing ones' burst 27, deathclaw
    and bighorner knockdowns 19 and 19, Legion mongrel hamstring 20, golden
    geckos' radiation 10); `attack_spells` reads it from FalloutNV.esm.
    FO4 casts an attack's ATKD spell on its hit: Fallout4.esm's radscorpion
    stings carry `PoisonRadscorpion`, the mole rat's every bite
    `PoisonMolerat` (with the `MS19Infect` disease), so stand-in copies
    poisoned with FO4's numbers, and anything on a mole rat stand-in got its
    infection. Every attack of a stand-in copy (`attack_list`) now casts
    FNV's spell, or none: on `PoisonRadscorpion`'s shape (fire and forget),
    delivered by FNV's range. Poisons and drains are FNV's Touch and land on
    the victim; every knockdown (deathclaw, bighorner, Rex, the mongrel
    hamstring) and the spore and glowing-one bursts are Self, whose script
    pushes its own combat target away. FO4 casts an attack's spell on the
    actor hit whatever its delivery: with the knockdown self-delivered on
    the attack, Quarry Junction's mother and alpha male flung the other
    deathclaws (played 2026-10-27: the player, hit, pushed away its own
    combat target). So a Self spell is written self-delivered and the
    attack carries a touch relay (`FNV_<spell>OnHit`, script
    `F3NV_CastOnAttacker`) that casts it on its caster, the attacker,
    where FNV's script expects to run. With the relay the knockdown landed
    on the player, at FNV's force (20; FNV's and FO4's scales agree: a
    rifle knockdown is 5 in both, FO4's Pain Train 9), and on getting up
    the player fell through the ground (played 2026-10-27). Fallout 4 never
    pushes the player by script (every vanilla `PushActorAway` is the
    player's on an NPC; its heavy hits stagger the player), so a converted
    `PushActorAway` is `TES4Polyfill.PushActorAway`: the player is staggered
    by Fallout4.esm's `PerkStagger` (StaggerEffect 2, as the yao guai's and
    Mirelurk King's hits), anyone else pushed (played 2026-10-27: the mother
    and alpha male stagger the player, no deathclaw flung). With `set
    TES4Trace to 1` the relay logs `attack` lines and the push `push` lines. Each detrimental touch value effect on vanilla `crPoisonEffect`
    (damage per second; Health) or `StingwingPoisonEffectNPC` (lowered,
    then recovered) or a copy on its actor value, script effects by
    `script_effects`, magnitudes and durations FNV's. A creature FNV gives
    none loses its stand-in's: mantises the stingwing's poison, mole rats
    and anything on the mole rat its infection, deathclaws without FNV's
    knockdown FO4's `abDeathclawClawsSCRIPT`. Rig Test (bark scorpions
    near Hidden Valley, `OVWestSewers03b`): `FNV_BarkScorpionPoison`,
    `FNV_RadScorpion1Poison`, `FNV_RadScorpion2Poison`, none left out;
    Quarry Junction: the mother and alpha male self-cast
    `FNV_DeathClawKnockback`, other deathclaws and Vault 22c's mantises
    cast none. Mantises kept the
    stingwing's body in `stats` mode; since 2026-10-27 they are an own rig
    (played, [fo4_own_rig.md](fo4_own_rig.md#mantis)). Own-rig races
    (nightstalkers, geckos) write attacks with no spell and are not yet
    given FNV's; template actors take their template's list.
  - <a id="template-actors"></a>**Template actors** (played 2026-10-27).
    A template actor is a clone of its creature's stand-in, so it kept the
    stand-in's ATKR, and FNV has no template flag for attack data, so TPTA
    never takes it from the template. Jacobstown's nightstalkers (own rig,
    template FNVNightstalkerRace) therefore pulled `MoleratRace`'s attacks,
    whose events their graph lacks: in combat, seeing and facing the player
    at 123 units, they never attacked, while `sae meleeStart_Left` bit.
    `npcs.with_template` drops ATKR, so attacks come from the race the
    template gives, as on the list-templated geckos (no ATKR) that bite;
    confirmed in game. Single-variable tests that changed nothing first:
    combat style circle/fallback, aggro radii, the attack offsets' sideways
    motion, dodge chance, the gecko's whole style, the gecko's race.
    The same pass gives a templated creature its own AI packages
    (`npcs._packages`, `source` reading creature records): FNV's template
    flags left Jacobstown's nightstalker its own sandbox package (349, no
    Use AI Packages), which the creature path dropped.
- <a id="creature-speed"></a>**Creature speed (built 2026-10-25, not yet
  built into a plugin or played).** `spike/creature_speed.py`: a converted
  creature's own SpeedMult (PRPS, AVIF 0x2DA; 3,015 vanilla NPCs list it)
  makes its FO4 forward run FNV's.
  - **FNV's side** (FalloutNV.exe; a subagent's trace, the run formula
    re-read at 0x8d4f10). A creature moves by its movement clips' root
    motion: run = int(FastForward clip root speed) × actor value 0x15 (ACBS
    Speed Multiplier) × 0.01 (0x8d4f10, 0x494300); a group with several
    variants reads speed 0 and its clips play at rate 1, so it moves at the
    clips' own speed. Every direction plays at that rate, so walk, side and
    back keep the clips' ratios. Scale is the reference's × BNAM base
    scale. Turning: TNAM degrees/s (45 when 0), × fCreatureTurnSpeedScale
    1.25 in place. NPCs use a settings formula instead (fMoveBaseSpeed,
    fMoveRunMult...), not touched here.
  - **FO4's side** (Fallout4.exe; a subagent's trace, the multiply re-read
    at 0xcb270d). The movement type comes from the behaviour graph: its
    `iState` value names a state `<X>` (variables `iState_<X>`), and the
    MOVT whose MNAM is `<X>` is used, else the race's WKMV, else DOBJ DMWL
    (0xca5c90); so a new race WKMV would not change a creature on a vanilla
    graph. Speeds are capped by the graph's clip speeds, then every
    translation is × scale (reference × NPC height NAM6..NAM4 × race
    height) × |SpeedMult| / 100, 0 read as 100 (0xcb25f0). SpeedMult does
    not touch turning (MOVT yaw). SPED layouts: 112 bytes (form version
    104+) forward run float 10; older 40–68 bytes float 5.
  - **The mapping.** SpeedMult = 100 × FNV run / (FO4 run × the stand-in's
    mean scale, its NAM6..NAM4 midpoint × race height); the placed
    reference's scale is in both and cancels. FO4's movement type: the
    race's WKMV when the graph names it or names none; else the graph's
    `<kind>Default` state (vanilla's name for a base state: DeathclawDefault,
    DogDefault, NPCDefault), else the state the others extend (FeralGhoul
    over FeralGhoulSprint), else the only one. That order stands in for the
    graph's iState initial value, which needs a Havok 2014 reader.
  - **Size (2026-10-27).** FNV's BNAM base scale (from the traits
    template) multiplies the stand-in's height range (NAM6 min, NAM4 max,
    added after NAM7 when missing), since the stand-in's body is sized for
    itself; SpeedMult is computed at that size. On an own rig the body is
    FNV's mesh, so height = base scale ÷ the race's height (its DATA's first
    float, the template's copy) and SpeedMult is FNV's own multiplier.
  - **Not carried:** walk, side and back speeds and turning (one SpeedMult
    scales all four directions alike, and turning only lives in the MOVT
    yaw); FO4's clip-speed cap, which can hold a fast creature below its
    SpeedMult; FNV NPCs' formula speeds.
- <a id="door-closer"></a>**Doors close behind NPCs (built and played
  2026-10-17).** FNV closes a door after the NPC who opened it walks
  through; FO4 leaves it open. In the Bison Steve a convict's patrol runs
  through the double door into the deputy's room (markers at (1432, −4276)
  and (783, −4217), the door at (1024, −4224)), so the room stood open.
  Every DOOR base now carries `F3NV_DoorCloser` beside its own script: an
  NPC's OnOpen registers a distance event, and once the NPC is 200 units
  away the door closes if still open. Doors the player opens stay as left.
- **Patrol start (played 2026-10-17: Victor runs his circuit).** An FNV Patrol starts at its location reference (FNV
  PLDT near reference, e.g. Victor's circuit marker). The FO4 copy's
  Patrol Start is that reference; before, it was the actor's linked
  reference, which Victor doesn't have, so he never ran his circuit.
- **Force greets to a topic (played 2026-10-17: the Primm trooper warns
  the player).** An FNV Dialogue package that opens a named
  topic, not GREETING (114 in FNV, e.g. the Primm trooper's warning),
  becomes a ForceGreet like the others. Its topic's lines go first in the
  greeting scene, each needing that package current
  (GetIsCurrentPackage), so the force greet opens on them.
- **The list.** PKIDs follow AIDT, as in all 1,120 vanilla NPCs with
  packages (the body, DocWeathers, has none, so they had gone last).
- **Floor beds.** FNV sleep slots 3–6 (bedrolls, mattresses, bare floor)
  become FO4 floor beds (`AnimFurnFloorBedAnims`, `MarkerSleep01.nif`),
  their marker facing along the mattress as vanilla's (heading 0 where a
  bed's is π/2).

<a id="voice-types"></a>**Voice types (played 2026-10-12: NPCs speak in
their FNV voices).** `spike/voice_types.py` writes each FNV voice type an
NPC uses as an FO4 VTYP on FNV's FormID: EditorID and DNAM flags (Allow
Default Dialog 0x1, Female 0x2, the same in both games), read from
FalloutNV.esm because the export doesn't decode VTYP. The NPC's VTCK
(from its traits template) replaces its body's, so a line's recording is
found under its own voice type; `cell._voice` converts the built lines for
every such type (region: 21 types, 610 files; Doc's 197 moved from
`NPCMDocWeathers`). Every other folder in the plugin's voice directory is
swept as stale. FO4's generic barks are tied to vanilla voice types, so
converted NPCs speak none until FNV's own arrive with its dialogue.

**Two mesh faults found at this size.**
- `traps/beartrap01.nif` is the only mesh in the region with a Havok
  phantom: the pressure plate's trigger volume
  (`bhkSPCollisionObject` → `bhkSimpleShapePhantom` →
  `bhkTransformShape`). `collision_nodes` converts rigid bodies only, so
  the phantom is left out. The trap's base and jaws keep their collision.
- Elric writes a node named `Head` as `HEAD`, so its collision didn't
  match ours. `elric.graft` now matches names ignoring case. This hit 5
  skeleton and corpse meshes.

<a id="rooms"></a>**Rooms, portals and ragdolls** (found playing the region).
- **White boxes:** Vikki and Vance's side rooms and Bison Steve's halls
  showed a white box past each doorway, but only from inside a room.
  FNV divides those cells with room markers (`0x1F` RoomMarker, `XMBO`
  bounds) joined by portals (`0x20`, `XPOD` naming the two rooms).
  - Two links were missing:
    - **The portal base:** FNV's portal marker is built into its engine
      (FalloutNV.esm has no `0x20` record), so every portal was skipped.
    - **The room links:** the export keeps `XPRM` but not `XMBO` or `XPOD`.
  - With rooms and no portals, FO4 drew only the room the player stood
    in.
  - Fixes:
    - `items.PORTAL_MARKER` maps `0x20` to Fallout4.esm's PortalMarker
      (`0x20`);
    - `spike/placement.py` copies `XMBO`, `XPRM`, `XPOD` (rooms renumbered)
      and `XRGD` from FalloutNV.esm itself.
  - Vanilla has the same layout: 1,725 portals are `NAME XPRM XPOD DATA`;
    601 room markers are `NAME XMBO XPRM DATA`.
  - **Trigger boxes keep no XMBO (2026-10-31).** FNV's GECK writes `XMBO`
    on trigger boxes too (873 activator primitives, Ringo's gas-station
    trigger among them), and the copy carried it. In Fallout4.esm, none of
    the 5,335 activator primitives has `XMBO`; the 1,817 references with
    one are room markers (1,816) and a multibound marker. Ringo's trigger
    never fired (no `OnTriggerEnter`: its script package never reached the
    trace in a played Papyrus log), so he sat in his sandbox instead of
    meeting the player at the door with his gun drawn. A reference on an
    activator now keeps its `XPRM` but not its `XMBO`
    (`placement._room_bound`). The same test keeps triggers out of
    `open_rooms`: 126 of them sat in cells with an open portal and were
    left out of the build as rooms.
- **Corpses vanishing as the player walks up (fixed and played
  2026-10-18: Bison Steve's convicts).** The bodies stayed lootable but
  went undrawn. Bison Steve's two FNV rooms leave its lobby in no room;
  the convicts died there. A patch turning the cell's 2 room markers and 6
  portals into XMarkers (8 bytes) kept the bodies drawn. Our rooms match
  vanilla's (XMBO half extents, XPRM equal to XMBO, persistent markers in
  the persistent group), and vanilla has portals to no room too (51 of
  1,726). The reading: a corpse that settles outside every room stays with
  the room it left, culled once the camera is outside that room. In 29 of
  FNV's 69 roomed interiors a portal leads to no room (188 of 849
  portals); their room markers and portals (944 references) are left out
  (`placement.open_rooms`), so FO4 draws the whole cell: no room culling
  there, which the region's frame rate allows (118 cap at 24% GPU). The
  region leaves out 14. Recorded in [drift](fo4_drift.md#recorded).
- **A skeleton standing upright** (`Skeleton50sCasualMale` near Goodsprings):
  FNV lays a ragdolled object down with the reference's `XRGD` bone pose
  (bone id, 3 unused bytes, position, rotation: 28 bytes, as in FO4).
  Without it FO4 shows the mesh's bind pose. Vanilla puts `XRGD` on 4,081
  MSTT references and 1,301 statics.

<a id="effects"></a>**Effect meshes and the interior fog clip** (interior lighting
pass, step 1).
- **White shapes at the end of Doc's hall.** These were left after the
  portal fix: Doc's house has no rooms. FNV clips interior drawing at
  `XCLL` fog clip distance (Doc's: 1,500), where its fog is already the
  full fog color, so the cut never shows. FO4 shows bright background
  past a clip. Interiors now write clip 0, as 578 of 606 vanilla FO4
  interiors do; with fog max 1.0, everything past FNV's far distance is
  pure fog color, as in FNV.
- **View falloff of unlit shapes.** The region places 414 ambient
  effect meshes indoors and 64 outside: light rays (`IndFXLightRays01`),
  dust, haze cards. FNV draws them with `BSShaderNoLightingProperty`,
  usually additive (alpha flags `0x100D`: source alpha, one) with faint
  vertex alpha (the beams: 0–0.1). They already became inline FO4
  effect shaders with that blend, vertex alpha and colors, but without
  FNV's view falloff.
  - In FNV's shader package 019, every one of the 14 unlit vertex
    shaders with a normal input uses the `Falloff` constant, and none of
    the 14 without normals do. The variants differ only by inputs, so FNV
    fades every unlit shape that has normals.
  - The formula, as `NOLIGHT004.vso` computes it:
    `t = saturate((|n·v| − start angle) / (stop angle − start angle))`;
    opacity = start opacity + smoothstep(t) × (stop opacity − start
    opacity), on cosines.
  - Such a shape now gets FO4's `Use_Falloff` (flags1 `0x40`) and FNV's
    four values. Of the region's 313 unlit shader blocks, 244 have FNV's
    default (1, 0, 1, 0): opaque face-on, gone edge-on. The beams have
    (0.98, 0.17, 1, 0).

<a id="lights"></a>**Lights** (interior lighting pass, step 2). FNV's 501 LIGH
records and vanilla FO4's 694 (with a full DATA) use about the same
values:
- radius p10/p50/p90: FNV 128/200/512, FO4 128/256/512;
- fade (FNAM): FNV 0.75/1.2/2.5, FO4 1.0/1.0/4.0.

Two fields were dropped:
- **Falloff exponent and FOV:** written as 1 and 90 for every light. 28
  FNV lights use another exponent (2.0 ×12, 0.5 ×4, 5.0 ×4); spotlights
  have their own FOV. Both are now FNV's.
- **Flicker and pulse:** FO4 drives them by period, intensity amplitude
  and movement amplitude, and every light got period 1 and amplitudes 0,
  so none moved.
  - FNV has 50 flickering lights, 12 slow-flickering, 5 pulsing and 11
    slow-pulsing.
  - FNV's flicker is procedural: sines with random phase rates, in
    `0x50DE60`. The slow flag (0x40) halves its clock (`fdiv 2` at
    `0x50DF15`), and `fFlickerMovement` (8) is its movement.
  - A flickering light now takes vanilla's most common flicker (period
    0.33, intensity 0.45; 31 of 182) with movement 8. A pulsing light
    takes that period and intensity without movement. A slow one doubles
    the period.
  - This is FO4's own flicker, not FNV's exact curve.

<a id="lighting-templates"></a>**FNV lighting templates** (played 2026-10-10). An FNV cell's `LTMP` names an LGTM,
and its `LNAM` flags pick which `XCLL` fields come from the template. The
export has no `LNAM`, so it is read from FalloutNV.esm.
- 273 FNV interiors use a template; the most common flags are `0x9F`
  (68 cells) and `0x98` (28).
- Doc's house (`0x9F`) inherits from `EnclaveLightingTemplate01`:
  - fog from 64 to 5,000 units, where the cell's own values said 100 to
    1,500;
  - ambient (31, 31, 45), where the cell's own color was teal
    (47, 70, 69).
  Converting the unused cell values buried the far end of the hall in fog
  that FNV never shows.
- The converter now resolves each field the way FNV does
  (`spike/lighting_template.py`).

<a id="weathers"></a>**Exterior climate and weathers** (played 2026-10-11; a new save is
needed, since a save keeps its current weather). The exterior used the
Commonwealth's climate: a grey sun (225, 225, 225) and neutral ambient.
WastelandNV's `NVDefaultClimate` lists `NVWastelandClear` and
`NVWastelandClearNight`; the regions over Goodsprings add `NVWastelandGS`
and `NVWastelandBorders`. All four share their colours (sun 255, 227, 170;
ambient 87, 105, 138) and differ only in fog.
- Each climate weather becomes a copy of `CommonwealthClear` with FNV's
  colours (`weathers.py`; FNV's 10 colour types into FO4's 19: fog fills
  near, far and both high fogs; sunlight also fills effect lighting) and
  FNV's fog distances and power (× 2.2). Clouds and imagespaces stay
  vanilla's, as Project Mojave's do.
- The climate copies `DefaultClimate` with FNV's weather list and sun
  timing; the worldspace points at it.
- The region weathers are converted ([region weather](#region-weather)). Not yet: FNV's weather imagespace
  modifiers (`IAD`). These two are most of FNV's "dirty" outdoor haze:
  - every wasteland weather plays `NVWastelandIS` (0x0CEE18; sunrise
    `NVWastelandSunriseIS` 0x0CEE1A). It tints toward amber (1.0, 0.737,
    0.051) at 0.392 and multiplies brightness by 1.3 → 1.1, with HDR
    pairs 2 (0.35 → 0.6), 4 (1.8), 7 (0.4), 8 (0.8) and 11 (1.1). How FNV
    evaluates a weather's modifier over its keys is unconfirmed;
  - `NVWastelandGS` fogs fully at 120,000 (power 0.5) against the clear
    weather's 200,000 (power 0.6);
  - FNV's HDR bloom also softens the image (see [color drift](#color-drift)).
  The tint is a candidate for a player option (an "FNV filter").

<a id="emittance"></a>**Light brightness and emittance** (played 2026-10-10).
- FO4's tiled light shader (`shaders011.fxp`, compute shader 3584) uses
  `att = (1 − saturate(constant + scalar · (d/r)^exponent))^2.2`, with
  vanilla's 0, 1, 2. FNV's (`SM3000`) is `1 − saturate(d/r)²` in display
  space. FO4's falloff is therefore FNV's in linear light, and no
  falloff conversion is needed.
- A reference's `XEMI` takes its color from another light or a region's
  daylight; FNV and FO4 both use it.
  - Region: 2,276 of FNV's 8,376 light references have one.
  - Doc's house: 23 of its 25 lights (Doc's "warm" lights shine as
    `DLC01FXLightMillSmoke`, 255, 162, 85).
  - Vikki and Vance: all 25 (`NellisGeneratorFillWarm` and others).
  - FO4: vanilla uses it on 8,456 lights.
- Dropping `XEMI` left those lights on their pale base colors. It now
  points at the emittance light's FO4 LIGH.
- **Region emittance (daylight; in test).** FO4's 7,797 sunlight-region
  lights point at `FXLightRegionSunlightWhite` (or its bounce variant).
  That region has one weather, `FXWthrSunlightWhite`, which holds only a
  Sunlight and an Effect Lighting color per time of day.
  - Each FNV region used as emittance becomes such a region, and its
    weather a copy of that weather (`spike/emittance.py`). The copy gets
    the Sunlight of the FNV region's first weather, read from
    FalloutNV.esm because the export misreads FNV's 12-byte `RDWT`
    entries.
  - FO4's early and late sunrise and sunset take FNV's sunrise and
    sunset.
  - `NewVegasRegion` gives (255, 227, 170) by day; the inverted-daylight
    regions are black by day and white at night.

<a id="refraction"></a>**Refraction surfaces (built 2026-10-27, not played).** An FNV lit
shape whose `BSShaderPPLightingProperty` sets `sf_refraction` draws only a
distortion of what is behind it (heat shimmer, gas, explosion waves, Mr.
Handy jets). It used to fall through to an opaque BGSM of its texture: a
solid blob (Vault 34b's `TrapGasFire01`, 2026-10-27: `fxparttinyglowy` at
2x scale). No vanilla BGSM (6,616) or BGEM (283) sets refraction; vanilla's
gas leak (`effects\gasleakanim.nif`) is a lighting shader with no material
file, flags1 Refraction | z-test (`0x80008000`, plus vertex alpha with
colours), flags2 Double_Sided and vertex colours, no z-write, and a
refraction strength. `convert_static._refract_blocks` writes that, at FNV's
`refraction_strength`, on FNV's diffuse and normal. FNV has 84 such shapes
in 69 meshes (explosions, the glowing ones' burst, Mr. Handy and Mr. Gutsy
jets, the ghoul body effects of Point Lookout and Dead Money, the Helios
laser, Zeta shields, the gas traps); 47 have strength 0 and refract only by
`sf_fire_refraction`'s animation, which is not carried, so in FO4 they
draw nothing.

<a id="glow"></a>**Glow maps** (lighting pass, step 3). FNV lights a lit shape's glow
map (texture set slot 2) with the shape's `NiMaterialProperty` emissive
color and multiplier. None of these shapes sets the glow shader flag, so
the texture's presence is what turns it on.
- In Goodsprings to Primm, 125 shapes in 55 meshes have one: the saloon
  neon (white), the Mojave Express sign (1, 0.35, 0), the hospital light
  (0.26 grey), recessed lighting.
- The BGSM kept only diffuse and normal, so none glowed. It now takes the
  glow map with `glowmap` and `emittance` on, FNV's emissive color
  (clamped to 0–1; the briefcase detonator's is −0.14) and multiplier,
  and `external_emittance` where FNV sets it (18 shapes).
- Vanilla's 209 glow-textured BGSMs mostly turn on `glowmap`. The lit
  ones also turn on `emittance` (white ×1.0 is the most common). Vanilla
  fixture shaders already carry Own_Emit in flags1 (`0x80400201`, as
  ours).
- The material path gains `_glow<rgb>` so shapes sharing a diffuse but
  glowing differently keep their own material.
- **The glow is baked, and a cut-out glow is a neon overlay (played 2026-10-10).** The
  OPEN 24 HOURS sign showed blurry colored blocks on a yellow panel.
  - FNV's glow shader (`SLS2004`) adds `EmittanceColor × glow` to the
    light sum, which then multiplies the diffuse. So FNV's glow is
    diffuse × glow-map color.
  - FO4 adds the glow map as emission without the diffuse, so each glow
    map is now baked: diffuse × glow, at the diffuse's resolution
    (`<diffuse>_<glow>.dds`).
  - The sign's diffuse hides a yellow, blotched panel behind alpha 0, cut
    away by FNV's alpha test (threshold 64). Our material, alpha block
    and packed texture all carried that test.
  - Glow shapes are written as vanilla's alpha-tested glow mesh
    (`cagebulb01.nif`): glow shader, type 2, flags2 Glow_Map `0x40`.
    That did not restore the cut, and neither did a default shader.
    - A one-change test settled it: the sign drew correctly with only its
      glow removed (glow-free BGSM, default shader, empty glow slot).
    - Our glow BGSM's flags all fall inside what vanilla's 54
      glow-and-alpha-test BGSMs use, and vanilla's glow maps are opaque
      BC1 like ours, so the cause is not identified.
  - Vanilla's own OPEN sign (`signgeneralopen.nif`) is not a glow-mapped
    BGSM. Its neon is `NeonRed01.BGEM`: additive (src alpha, one), unlit,
    no z-write.
  - An alpha-tested glow shape is therefore now two shapes: the lit BGSM
    without glow (keeping the cut), and the same triangles with an
    additive BGEM shaped like that neon. The BGEM's base texture is the
    baked glow, colored by FNV's emissive color and multiplier. Black
    adds nothing, so only the glowing parts light.
  - The overlay shares its triangles' depth, and drawn plain it
    z-fought (rapid flicker). It is a decal: BGEM `decal` and the shader's
    Decal and Dynamic_Decal flags (`0x0C000000`), as vanilla's
    `eyeao.bgem` overlays the eye.

<a id="effect-animation"></a>**Effect animation (played 2026-10-10: OPEN sign, saloon ON and windows).** Dust clouds and other effects stood still.
- In the region's FNV meshes, 117 are animated (701 references). Beyond
  the door and container motion already converted, they animate:
  - emissive color (`NiMaterialColorController` `SELF_ILLUM`): 52 meshes,
    263 references;
  - single-node motion: 52 meshes, 221 references;
  - alpha (`NiAlphaController`): 15 meshes, 146 references;
  - emittance (`BSMaterialEmittanceMultController`): 8 meshes, 102
    references;
  - particle systems: 12 meshes, 69 references;
  - texture scroll (`NiTextureTransformController` `0-0-TT_TRANSLATE_U`):
    19 meshes, 56 references;
  - visibility, refraction, morphs, light color: 8 meshes or fewer each.
- The converter kept a mesh's animation only when every channel moved a
  node, so any effect channel dropped the whole animation.
- It now keeps every node motion and every shader channel FO4 has
  (`nif/shader_anim.py`), and leaves out the rest (particles, for now).
  FO4 drives the same values on the shape's shader property, as vanilla
  `sentrybotfacelight.nif` and `ashpile01.nif` do: a
  `BS{Effect,Lighting}ShaderProperty{Float,Color}Controller` on the
  shader. Its controlled block names the shape, the property and the
  controller type; its controller ID is the variable's number.

  | FNV channel | Effect shader variable | Lighting shader variable |
  |---|---|---|
  | Alpha | 5 | 12 |
  | U and V offset | 6 and 8 | 20 and 22 |
  | U and V scale | 7 and 9 | 21 and 23 |
  | Emissive color | color 0 | color 1 |
  | Emittance | 0 | 11 |

  The interpolators and keys carry over (`NiFloatInterpolator` and
  `NiFloatData`, `NiPoint3Interpolator` and `NiPosData`). The animated
  shapes join the object palette. An emissive channel of a cut-out glow
  shape drives its neon overlay, named `<shape>Glow`.
- A controller's own interpolator is a blend interpolator, idle until a
  sequence plays: manager-controlled, size 2, value −FLT_MAX, as vanilla's.
  The first build gave it the first sequence's interpolator, so it ran
  that sequence's keys on its own. The saloon window glass played its
  `Left` light-on state forever (solid yellow), and the OPEN sign its
  flicker at full white.
- Scripts play these sequences through `PlayGroup`, as the saloon's
  `Lucky38LightScript` plays `Left` (on, 20:00 to 06:00) and `Right`
  (off). The script converter wrote `PlayAnimation`, which on FO4 sends a
  behavior-graph event and does nothing on an object without a graph.
  For Fallout 4 it now writes `PlayGamebryoAnimation`, which plays the
  NIF's own sequence, as vanilla scripts do
  (`DN158_YangtzeReactorScript`). The sequence keeps FNV's name, where
  Oblivion's case-folding would have made `SpecialIdle` into
  `Specialidle`. That changed 109 of the FNV scripts, and all of them
  compile.
- That build also turned emittance on for lit shapes with an animated
  emissive color but no glow map. It was dropped: FNV's lit shaders
  without a glow map have no emittance input (`SLS2000` takes no
  `EmittanceColor`).

<a id="particles"></a>**Particle systems (played 2026-10-11: Goodsprings loads).** The region places 12 FNV meshes with particle
systems (69 references). Some are particles only, such as the wide light
dust, and drew nothing; the whirlwind's dust puffs went missing.
- **Layouts:** FO4 still uses Gamebryo's `NiPSys` family.
  - The modifiers and controllers have no Bethesda-version conditions in
    nif.xml, so FNV's values fill the same fields.
  - `NiParticleSystem` takes BSGeometry's fields: bound, skin, shader,
    alpha, vertex description and LOD distances.
  - `NiPSysData` keeps counts, flags and subtexture offsets, but no
    per-particle arrays.
  - `nif/particle_blocks.py` writes 22 block types. Each round-trips
    every instance in the first 1,500 vanilla effect meshes byte for
    byte (729 particle systems).
- **Conversion** (`nif/particles.py`):
  - Each modifier and controller carries FNV's values; pyffi's older
    field names are mapped.
  - References go to the converted system, its modifiers, and the kept
    emitter, gravity and drag nodes.
  - FO4-only fields take vanilla's values: the same vertex description
    and zero bound as all 729 systems, and no LOD distances and aspect 1
    as most.
  - The system's material goes through the shapes' path, which makes an
    FNV no-lighting shader an unlit effect shader.
- **Grow and fade:** FO4 never uses `NiPSysGrowFadeModifier` (0 of 729),
  so FNV's grow and fade times become a `BSPSysScaleModifier` curve (33
  points over the first emitter's life span).
- **Animation:** sequences drive the emitter's `BirthRate` and
  `EmitterActive`, and a modifier's activity, through the converted
  controllers. Those controllers' own interpolators are idle blends, as
  vanilla's 1,162 `NiBlendBoolInterpolator`s are (manager-controlled,
  value 2). A mesh whose sequences only drive particles counts as
  animated.
- **Mesh emitters and bombs (played 2026-10-11: loads).** The whirlwind's wisps and debris
  emit from the faces of a hidden mesh and are pushed by a bomb.
  - Vanilla's mesh emitter (`fxbitsdebrisspiral01.nif`) points at a
    hidden `BSTriShape` with no shader and no vertex data, only counts.
    The shape's `BSPositionData` (`BSPosData`, half floats) lists every
    triangle corner unshared: 5 triangles give 15 positions, then 15
    normals (the face's), then 15 zeros.
  - An FNV emitter mesh becomes that shape (16 strip triangles give 48
    corners), made once even when two systems share it, under its kept
    parent.
  - The bomb's node is kept like the emitter's. The mesh emitter, bomb
    and position data round-trip vanilla's 9, 24 and 3 instances.
  - The emitter shapes are made before the system's modifiers are
    numbered. The first build made one partway through, which shifted
    every later modifier onto the shape and its `BSPositionData`, and FO4
    crashed loading the whirlwind.
- **Colliders (played 2026-10-11: the snow globe's flakes stay in the
  glass).** The Goodsprings snow globe's 5 snow systems each have a
  `NiPSysColliderManager` with a chain of 15 colliders (the glass sphere,
  planes for the base and the scene inside). They were dropped, so the
  flakes fell through.
  - The manager, `NiPSysPlanarCollider` and `NiPSysSphericalCollider`
    have no version conditions, and their layouts round-trip all 134 of
    vanilla's (63 managers, 68 planar, 3 spherical in 32 effect meshes).
  - A system's colliders follow its modifiers; each names its manager
    (parent), the next collider, its spawn modifier and its node, which is
    kept like the emitter's.
- A controller of a modifier that was left out is left out too. The
  whirlwind's `NiPSysModifierActiveCtlr` named its bomb modifier, and FO4
  crashed entering Goodsprings looking it up
  (`NiPSysModifierActiveCtlr::InterpTargetIsCorrectType`, null modifier).

<a id="parents"></a>**Enable and activate parents (in test).** FNV's `XESP` (enable
parent: reference, flags) and `XAPD`/`XAPR` (parent-activate-only flag,
then reference and delay, repeating) have FO4's layout. They are copied
from FalloutNV.esm like the room fields.
- The reference is renumbered through every reference the build makes:
  interiors, exterior and actors.
- One that is not built is dropped. Its child then starts as that
  parent's chain leaves it (`placement.starts_disabled`: disabled when
  the parent starts disabled, flipped by the opposite bit), not by its own
  flag (fixed 2026-10-25). Whole map: 236 references showed at the start
  that FNV hides, nearly all under unbuilt parents in cells no door
  reaches (Hoover Dam's dummy cell: 168 power-plant pieces, NCR markers;
  NVWildwastelandCell: 15 Wild Wasteland items); 255 now start disabled,
  10 enabled. Actor-to-actor parents are still dropped (the actors' ids
  are not in the map yet); those children now take the same fallback.
- FalloutNV.esm has 2,484 references and 647 actors with an enable
  parent, and 216 references with activate parents. Actors (here only
  the stand-in speakers) do not carry theirs yet.

<a id="lighting-colors"></a>**Cell lighting colors stay as authored** (Vikki and Vance washed
out against FNV).
- FO4's fog formula, from shader 38 of `shaders011.fxp`:
  `t = d·k − c`; `fog = min(cap, t^power)`, with the cap the fog max,
  rising to 1 over the last quarter. That is FNV's formula with a cap, so
  with the same values FO4's fog is never denser than FNV's.
- Converting the XCLL colors from sRGB to linear was tried and rejected:
  the casino went dark wherever no light fell directly. Vanilla authors
  these bytes at FNV's scale: Fallout4.esm's 66 LGTM records have a median
  ambient of 33, directional ambient 29 and fog 70, against FNV's 388
  interiors at ambient 49 and fog 48. So FO4 reads them as display colors.
- The washed-out look was exposure instead; see
  [spike-2-imagespace](fo4_spikes.md#spike-2-imagespace).
- **Fog power is FNV's × 2.2.** FNV blends fog into display colors, FO4
  into linear light, so the same fog amount lifts a dark pixel further
  (36% fog shows black at 63% of the fog color). Raising the amount to the
  2.2 power makes the two match exactly on black; bright pixels get a
  little less fog than in FNV. In the casino, the mid-ground's contrast
  was half FNV's (std. dev. 10–13 against 19–24) with blacks lifted to 23;
  the haze was gone in play after the change. Doc's house stays foggy
  because its lights come out dimmer than FNV's (next step).

<a id="color-drift"></a>**Colour drift from FNV (parked, noted 2026-10-11).** Side by side,
the converted region reads less warm and yellow than FNV, and more
"realistic". Both are accepted for now; worth a later look, possibly as a
player option to match FNV's look more closely.
- **Overall image:** FNV's interiors and exteriors are warmer and more
  yellow. Exposure, fog and the cinematic grade already follow FNV
  ([spike-2-imagespace](fo4_spikes.md#spike-2-imagespace)); what is left is
  the colour itself (FO4's tone curve and LUT against FNV's straight,
  clipped display colours).
- **Grass:** FNV's Mojave grass is dry and yellow; in FO4 the same grass
  reads green and alive. Not measured yet (grass shader tint and lighting
  are the first places to look).
- **Bright ground in exteriors:** the dirt path up the Goodsprings water
  tower hill shows near-white (screenshot 198, 195, 178) where FNV shows
  soft tan (141, 124, 86), while the ground beside it matches (about 85
  in both): road over ground 2.4× in FO4, 1.9× in FNV. The land data is
  not the cause: where we draw the road above 0.5 (1,390 vertices), FNV
  paints it at 0.75 and we write 0.79. A colour-tinted test build showed
  the path is `LDirtPathWasteland01`; ground smoothness at vanilla's 0.17
  changed nothing. The exterior uses the Commonwealth's climate (and so
  FO4's weather imagespaces: eye adaptation, contrast, LUT), not FNV's;
  interiors get FNV's grading. Converting the exterior weathers and
  imagespaces is the first thing to try.
- **Reference: Project Mojave** (`mods/Project Mojave/ProjectMojave.esm`,
  master Fallout4.esm). Its Mojave worldspace has its own climate
  (`00DCMojaveClimate`: `00DCNVWastelandClear`, `00DCOrangeColouredSky01`).
  The weathers keep vanilla's record layout and clouds; the look is in the
  NAM0 colours. Day, against vanilla `CommonwealthClear` and FNV's
  `NVWastelandClear`: ambient (92, 114, 150) / (93, 93, 93) / FNV
  (87, 105, 138); sunlight (255, 249, 242) / (225, 225, 225) / FNV
  (255, 227, 170); sky upper (67, 98, 155) / (38, 64, 99) / FNV
  (50, 71, 135). Its imagespaces are vanilla's with small tweaks
  (saturation and contrast 1.025, eye adaptation) and vanilla's
  `LUT_CW_ClearDAY`. So: clone a vanilla weather and put FNV's colours in,
  as the emittance region weathers already do
  ([emittance](#emittance)); FNV's sun is warmer than Project Mojave's.
- <a id="reference-shots"></a>**Reference shots (2026-10-23).** The user took
  matching FNV and FO4 shots of the Prospector Saloon at noon and midnight
  and of the Goodsprings cemetery lantern at night. What they show:
  - **Noon:** FNV is hazy and muted: grey-amber clouds, soft shadows, the
    brick a dull ochre. FO4 has a saturated blue sky with white clouds,
    hard shadows, and the brick a bright, saturated yellow. The weathers
    may also have differed in that moment (FNV cloudy, FO4 clear).
  - **Midnight:** FNV's night is dark and blue-grey, and the saloon's windows
    are a dim, pale green-yellow with the panes and grime still visible.
    FO4's windows are solid, saturated bright yellow (no detail), the
    ground is lit a bright blue-white, the "ON" bulbs are blown out, and
    the street lamp and its cone are much brighter.
  - **Lantern:** FNV's makes a small warm pool on a dark ground. FO4's
    blooms into a bright yellow sphere and lights the whole ground yellow,
    under a purple sky. Open water shows on the horizon past the region's
    edge, and dark triangle-shaped flecks float around the water tower
    (a particle drawing without its texture, not yet identified).
  - The NPCs' purple faces in these shots were the plugin rename: the
    FaceGen heads named `FaceCustomization\FNVCellSpike.esp`
    ([names](#f3nv-names)).

<a id="addons"></a>**Add-on nodes** (the trash-can fire outside Vikki and Vance showed
its light but no flame).
- The burning barrels are LIGH records whose model, `Barrel02fireLight`,
  holds a `BSValueNode` (`AddOnNode14`). FNV attaches ADDN index 14's
  particle effect there (`MPSFireSmall01`). FO4 uses the same mechanism,
  and the mesh converter dropped the node.
- FO4's ADDN indices differ, so the FNV index's ADDN EditorID picks
  Fallout4.esm's ADDN of that name (`nif/addons.py`):
  `MPSFireSmall01` 14 → 4, `MPSFireMed01` 0 → 5. The smoke add-ons
  (`MPSSmokeMed01`, `MPSSmokeSmall01`) have no FO4 namesake and stay out.
- An add-on node under a hidden node is left out. `car03`'s six fires
  sit under `BSDamageStage` nodes FNV shows only once the car is damaged,
  and damage stages are not converted.
- Region: 1 barrel fire kept. The car, truck, motorcycle, electric box
  and fusion generator add-ons are hidden or have no FO4 namesake.
- The node is written as vanilla's: a NiNode, the index, a flags byte 0.

<a id="mixed-collision"></a>**Mixed collision under a MOPP** (walk-through stove in Bison
Steve). The collision converter treated any body whose shape is a MOPP
tree as one triangle mesh. FNV also puts a MOPP over a list of mixed
shapes, and then the mesh reader found no triangles and the whole body
was dropped. That happened to 10 bodies in Goodsprings to Primm:
- `CookingStove` and 6 rubble chunks: a convex hull plus a MOPP mesh;
- `bigpot01`: 7 boxes and 2 hulls;
- the bear trap's base: two MOPP meshes, one under a transform.

The MOPP is only a lookup structure. Now `collision.is_mesh` tells the two
apart:
- a MOPP over a list converts the list;
- a MOPP inside a list converts its triangles through the same winding
  repair as a whole body's;
- a `bhkTransformShape` in a list becomes a convex transform over a
  convex shape, or is baked into a mesh's triangles.

Elric turns each into a compound (`hknpDynamicCompoundShape`). The
stove's children match its render bounds: hull −41…41 × 21…95 × 0…91,
mesh −38…37 × 25…91 × 0…91, render −41…41 × 12…95 × 0…94.

<a id="two-sided-collision"></a>**Collision from both sides** (wall behind the Bison Steve stove).
FNV collides with both sides of a mesh triangle; FO4's character only
with its front. The winding repair fixes a face from its render twin,
but a collision-only box has none.
- `FacRmWallONLY01` is a 12-triangle box (±16 × ±129 × 0–256) inside
  render faces 53 units out. FNV authored 4 of its triangles facing in,
  including half the face toward the stove, so the player walked
  through.
- A fixed or keyframed body's mesh now also gets a reversed copy of each
  triangle not already present (`collision.both_sides`). Dynamic bodies
  keep one side, so their mass is not changed.
- Elric accepts the doubled meshes; the wall's physics bounds are
  unchanged.

<a id="ragdolls"></a>**Joints** (skeletons standing up in Bison Steve).
The `XRGD` pose was copied, but FO4 has nothing to pose: the bodies
were converted and the joints between them dropped.
- `SkeletonMale50sCasual` has 16 dynamic bodies, 9 limited hinges and 2
  ragdoll joints. Vanilla's `SkeletonClothed01` (824 placements with
  `XRGD`) has 17 bodies, 6 hinges and 10 ragdoll joints in its physics,
  and BSXFlags `0xEA`; ours had no joints and `0x4A`.
- `collision.joints` now writes FNV's `bhkRagdollConstraint` and
  `bhkLimitedHingeConstraint` in FO4's pre-Elric layout (nif.xml
  "Fallout 3 and later", Havok 2010: per body, the twist or axis vectors,
  then the pivot) and lists them on their body.
  - FNV stores pivot, plane, twist, then the motors. This was checked on
    the data: twist, plane and motor are mutually perpendicular for each
    body.
  - Pivots are scaled to FO4 units. A baked `bhkRigidBodyT`'s transform
    moves its side's vectors.
  - The motor is written as none.
- A mesh with joints sets Articulated (`0x80`).
- **Played: still a solid object with glitchy physics.** The collision
  converter hung each body on a new node off the root, and the visible
  parts stayed on the root, so the bones moved and the mesh did not.
  A jointed mesh now keeps every node with a rigid body, and the nodes
  between it and the root, as animated meshes keep theirs
  (`animation.with_parents`). Each part goes under its bone and each body
  on that bone's node, as vanilla's skeleton has a node per bone.
  `SkeletonMale50sCasual` keeps Torso → Head and both arms, Pelvis →
  right leg, and the left leg and Skull01 as root nodes.
- Elric's output now has `hkpLimitedHingeConstraintData` and
  `hkpRagdollConstraintData`, as vanilla's skeleton does.

<a id="locks"></a>**Locks and keys** (everything open; the maintenance key on a table
could not be taken).
- **Locks:** `XLOC` was never written. FNV has 426 locked references.
  FO4's XLOC (16 bytes: level, key, flags, 4 more) numbers its levels as
  FNV does: 0, 25, 50, 75, 100, and 255 for "requires key". Vanilla uses
  level 0 on 490 of its 1,358 locks, so 0 is a lock tier, not "none".
  The level and flags are copied, and the key is made as an FO4 key.
- **Keys:** KEYM was placed as a static stand-in. It is now an item:
  `pack_keym`, laid out as 134 of vanilla's 177 keys (preview
  KeyChainsAlt, the most common), made by `Items` like a misc item.

<a id="lock-script"></a>**Skill gates and the lock script (built 2026-10-22,
not yet played).** FNV opens a lock of level L (0 to 100) at Lockpick L and
a terminal at Science L. FO4's lockpicking and hacking keep their own
minigames; their tiers are held by the hidden `FNV_SkillGates` perk
([fo4_perks.md](fo4_perks.md#skill-gates)): Advanced (50), Expert (75) and
Master (100) open at the FNV skill of the same number, read live. That
leaves two things FO4's tiers cannot say:
- **Easy (25).** FO4's Novice tier holds both 0 and 25 (xEdit's FO4 XLOC
  enum: 1 and 25 Novice, 50 Advanced, 75 Expert, 100 Master) and has no
  gate. FalloutNV.esm: 73 placed locks and 17 placed locked terminals at 25.
- **Password notes.** An FNV terminal's PNAM names a note that unlocks it.
  FO4's passwords are KEYMs (39 of vanilla's 177 keys, EditorID
  `*Password`, 37 on `Holotape_Prop.nif`), which have no text, so the note
  stays a note. FalloutNV.esm: 23 TERMs have one, on 22 placed locked
  terminals (4 of them key-only).

`spike/locks.py` gives such a reference `F3NV_FalloutLock`
(`static_scripts/fallout4/`). While the reference is locked, it blocks
activation (`BlockActivation`, set on load and on every lock change). On the
player's activation it unlocks when the player holds the password note. It
refuses with "Requires Lockpick 25" (or Science) when the skill is below the
current lock level. Otherwise it passes the activation on to the game
(`Activate(ref, true)`, vanilla's HaircutScript pattern), which starts the
minigame. FNV has no leveled locks (0 of 426), so the live lock level is
FNV's. The note is whatever the note converted to: a paper note (BOOK) or a
holotape (NOTE), both inventory items.

Drift: a password note opens the terminal on activation rather than showing
FNV's password menu entry; an Easy lock shows FO4's Novice prompt and is
refused by a notification, not greyed out.

<a id="readables"></a>**Books, notes and terminals (built 2026-10-14, played 2026-10-21).**
They were statics of their meshes. `spike/readables.py` now makes each
one FNV's FormID keeps, whether a reference places it or a script gives it
(`Items` hands BOOK and NOTE to it). Each FO4 target was checked against
Fallout4.esm and xEdit's layouts:

| FNV | FO4 | Evidence |
|---|---|---|
| Text note | Paper note (BOOK), FNV's mesh when it has one | as before; vanilla's note fields (BoS302BIngramBackupNote) |
| Image note (5) | Paper note showing the image: `<img src='img://Textures/...'>` | vanilla's 2 notes with images use that tag |
| Voice note (34) | Holotape (NOTE, [below](#holotapes)) | vanilla's 133 voice holotapes |
| Sound note (2) | left out | no vanilla holotape is type Sound (0 of 167) |
| Book | BOOK: FNV's mesh, name, text (DESC), value, weight, script; Can't Be Taken (FNV DATA 0x2 = FO4 DNAM 0x2) | xEdit both games |
| Terminal | TERM ([below](#terminals)) | 778 vanilla terminals |

<a id="skill-books"></a>**Skill books.** FNV raises the skill by 3
(`fBookPerkBonus`; Comprehension's entry point adds 1) for every copy read,
and uses the copy up. FO4's teach-on-read is DNAM Add Perk: 113 of
vanilla's 327 books, every magazine; Advance Actor Value and Add Spell are
on none. A perk is added once per book record, so it cannot count copies:
not a true equivalent. A skill book instead runs `F3NV_SkillBook`
(ObjectReference's OnRead, raised on every read): the helper
plugin's skill actor value + 3, and the copy removed. Comprehension is
not converted, so its extra point is missing.

<a id="terminals"></a>**Terminals** (`spike/terminals.py`). Field by field
against FNV's TERM:
- **Text.** DESC is FNV's welcome text, shown above the menu of that
  terminal page; it becomes BTXT (body text), as vanilla's sub-menus carry
  theirs (538 of 778 have BTXT). NAM0 is left empty, so FO4 shows its own
  RobCo header where FNV showed its server lines.
- **Menu items.** ITXT, RNAM (FNV's result text), ITID (item i is ID i+1,
  vanilla numbers from 1) and the item's conditions (converted as a
  line's; an item whose conditions cannot convert is left out). The type
  (ANAM): a sub-menu is 4 with TNAM, as vanilla's 350; a displayed note is
  8 (Display Text) with the note's text in UNAM, as vanilla's 1,804; Force
  Redraw (FNV item flag 0x2) is 6, which vanilla uses on toggles whose
  conditions change; `ForceTerminalBack` is 5 (Return to Top Level, used on
  vanilla's Yes/No confirmations; FNV goes back one level, so deeper menus
  differ); anything else is 8 with no text, as vanilla's script-only items.
- **Item scripts.** FO4 runs `Fragment_Terminal_NN(ObjectReference
  akTerminalRef)` of the TERM's fragment script for item ID NN. The VMAD
  is xEdit's wbVMADFragmentedPERK (bind version 3, the script entry, then
  per fragment its ID, a 1, script and function), as all vanilla terminal
  VMADs. For the FO4 target, script_convert now writes one fragment script
  per TERM (`script_convert/terminal_fragments.py`, `FALLOUTNV_TM__<id>
  extends Terminal`): the item's script converts as a TopicInfo fragment
  whose subject is the terminal, and Add Note adds the note. FalloutNV.esm:
  140 TERMs have one.
- **The user's spot.** A FO4 terminal is furniture: vanilla's carry
  keywords (AnimFurnDeskTerminal, PlayerPathToFurniture,
  FurnitureForce1stPerson), MNAM `0x40000001`, a marker model and one
  marker (SNAM: offset, heading, all entry sides). These are copied from
  DN054_ZekesTerminal (TerminalOn.nif). The marker stands where vanilla's
  stands relative to its screen: 55.2 out along the screen's facing and
  79.3 below its centre (TerminalOn.nif's screen centre (0, -5.8, 79.3),
  marker (0, -61, 0)), facing it. FNV's six terminal meshes face +X,
  FO4's -Y.
- <a id="terminal-facing"></a>**Facing -Y (built 2026-10-16, not yet
  played).** FO4 offers a terminal only to a player standing within about
  60° of its mesh's -Y side.
  - **Where that comes from (exe, 1.11.240).** In the crosshair pick's
    target filter (0x996E30), a TERM (form type 0x37) is rejected unless
    -(the mesh's local Y axis · the flat direction from the terminal to the
    player) is at least `fMinTerminalActivateDotProduct` (0.5).
  - **Vanilla agrees.** All 777 vanilla TERM markers sit straight out
    along -Y.
  - **The failure.** Our terminals kept FNV's +X screens, so they showed
    no prompt from the front.
  - **The fix.** `nif/terminal.py` turns each child of the root about Z so
    the screen faces -Y. Elric bakes those transforms into the physics,
    as it does any node's. The marker then sits vanilla's way:
    (0, -55.2, -79.3 from the screen centre), heading 0.
  - **Placement.** Each placed terminal's heading takes the turn back
    (`Terminals.turn`), so it stands where FNV placed it. 216 of FNV's 219
    terminal references turn only about Z; the 3 tilted ones are turned
    about Z only and counted.
  - **Not turned.** A mesh whose root itself carries collision would not
    turn with its children, so it is left facing +X.
- **The screen.** FO4 draws the terminal menu onto the terminal's shape
  named `Screen:0`: the exe's terminal menu code looks the name up, and
  the vanilla terminal meshes checked (TerminalOn, TerminalWall01,
  TerminalOnCorded, TerminalDesk01) have it, lit by
  `Materials\Interface\PipScreenTerminals.BGSM`. FNV draws its menu over
  the whole view, so its meshes mark no screen. `nif/terminal.py` takes
  the largest unlit, textured shape (the glass FNV textures with its
  screen texture), names it `Screen:0` with vanilla's shader and texture
  set, and lays its UVs 0 to 1 as vanilla's (u left to right, v top to
  bottom). The mesh is written as `<name>terminal.nif`; the plain mesh
  stays for statics.
- **Locks.** FNV locks the base (difficulty, Leveled, Unlocked); FO4 locks
  each reference (XLOC, vanilla's 623 terminal references: levels 0, 25,
  50, 75, 100, 255). A placed terminal takes XLOC level difficulty × 25
  (Requires Key: 255) and Leveled (`0x4`). Science opens the tiers
  ([lock script](#lock-script)), and a password note (PNAM) unlocks the
  terminal through the lock script.
- **Left out:** FNV's looping sound (FO4's TERM field is unused by vanilla),
  Alternate Colors, the server type.

<a id="holotapes"></a>**Holotapes** (`spike/holotapes.py`). FO4 plays a
voice holotape (NOTE DNAM 1) by starting its scene (SNAM). Vanilla's
(DN150_BonnieHolotape in HolotapesQuest) has one phase per line, an actor
of none (alias -2), and Radio actions (type 6) naming each line's topic
and SOMDialogue2D_Holotape as output (stored in DMAX, which xEdit reads as
a float). Each line is a scene topic (DATA category 2, subtype 0x11) with
one INFO whose speaker (ANAM) is an NPC carrying the voice type the
recording is filed under (535 of HolotapesQuest's 536 lines). An FNV voice
note names its topic and speaker: each of the topic's INFOs becomes a line
(`say.info`, so its recordings convert under the speaker's voice type),
and the speaker is a copy of vanilla's DN150_BonnieTournquist with FNV's
name and voice type. The quest, scene, topics and speaker are hashed from
the note's FormID. A script's AddNote declares its note as a `Form`
property on Fallout 4 (`command_rows_fallout4`; the FNV row's `Book` is the
Skyrim target's). attach.py fills a `Form` item with whatever the note
became, paper note or holotape, so FNV's one script-given holotape (Hanlon's
Confession, `TIF__00158676`) is given as a holotape (checked 2026-10-22).

A holotape line's own speaker tests are settled before conversion
(`spoken_by`). FNV says a voice note's lines as its speaker (SNAM), and 8 of
the 9 voice notes with lines test exactly that: `GetIsID <SNAM> == 1` on
Subject, always true in FNV. Kept, the test names the FO4 copy of that NPC
while the line is said by the stand-in speaker (or no actor), so it is never
true: the scene had no line to play, the holotape stayed silent and the End
fragment never ran (Deputy Beagle's journal never completed VMQ01's
objectives 30-38). Subject `GetIsID` and `GetIsVoiceType` tests now resolve
against the note's speaker record (true tests dropped, a line for another
speaker left out); every other test converts as before. Vanilla gives no
counter-example: 5 of HolotapesQuest's 536 lines have conditions, none a
Subject identity test.

**Measured** (Goodsprings to Primm): the region places 4 books, 1 note and
4 terminals; all were statics and all are now their records (2 TERMs, 3
references locked, the Easy desk terminal's unlock item a fragment; the 4
skill books; Bison Steve's ransom note). Scripts now also get 7 books and
1 holotape (Deputy Beagle's journal: 6 lines, 6 recordings under
MaleAdult11) that were skipped before. No FormID moved and nothing was
removed: the 7 records replacing statics keep the static's FNV FormID.

Census of the region's 1,630 meshes' Havok blocks: MOPP/packed strips
941, rigid bodies 928 (+503 T), convex vertices 360, boxes 111, lists 27,
capsules 14, convex transforms 11, spheres 4, constraints 26, phantom and
transform shape 1 each.

<a id="consumable-effects"></a>**Consumable effects (built 2026-10-14, played 2026-10-21).**
`spike/consumable_effects.py` gives each FNV consumable (ALCH) effect a
Fallout4.esm effect only where it is a true equivalent: the same actor value
and the same kind, read field by field from both games' MGEF DATA (xEdit's
layouts: FNV archetype and actor value at 0x40/0x44, FO4's at the same
offsets). FNV's timed boosts (Value Modifier with Recover) become FO4's
timed boosts of that actor value (Peak Value Modifier with Recover, as
FO4's own chems); FNV's restores and damages without Recover over a duration
are per-second changes in both games; instant ones have duration 0 in both.
FNV's magnitude and duration are kept, except Turbo (FNV's magnitude is an
on/off actor value; FO4 Jet's time scale 0.3, the wiki measures FNV's world
at about 35%), Psycho (FNV adds `PsychoPerk`, Calculate Weapon Damage ×1.25;
FO4's `ExtraDamage25Psycho` applies `ChemPsychoDamage`, Mod Weapon Attack
Damage ×1.25, shown as 25) and the all-limbs restore (its script restores
each limb by 100).

- Carried as FO4's own effect: health (food heal; the stimpak's absolute
  heal as `RestoreHealthGeneric`, since FO4's Stimpak archetype heals a
  share of maximum health), rads up and down, Rad-X, SPECIAL and action
  point boosts (the alcohol, Buffout and Mentats ones on FO4's alcohol,
  Buffout and Mentats variants), SPECIAL reductions, damage, fire, poison and
  energy resistance, Stealth Boy's Chameleon, Turbo (FO4 Jet's slow time),
  Psycho (+25% damage), both cap adders (Sunset's script adds a cap 95% of
  the time, a star cap otherwise; FO4's adds a cap), and the all-limbs
  restore (FO4's six `RestoreCondition*`).
- Copied and retargeted: skill boosts (FO4's `FortifyStrength` on the
  helper plugin's skill; was Rad-X's dual-value boost) and Hydra's limb
  restore over time (`RestoreHealthFood` on each limb condition: FO4's own
  limb restores take no duration).
- Effect conditions: IsHardcore counts as false (FO4 has no Hardcore
  mode; an effect needing it is left out), except on the need effects,
  which go to Survival mode ([survival needs](#survival-needs)). HasPerk is written as FO4's on
  the effect, on the perk's first rank (2026-10-21: 129 tests in the region;
  a perk the build lacks counts as not held). See
  [perks](fo4_perks.md#hasperk).
- An item left with no effect carries `FortifyHealth` at magnitude 0 and
  duration 0, as vanilla's `VRWorkshopShared_MutfruitFake` (and
  `HC_SippableWater`, `DamageRadiationChem` at 0). xEdit requires one
  effect and reports an empty list as a NULL MGEF; vanilla leaves the list
  empty only on its two survival status potions, never on an item.
- Drift ([drift](fo4_drift.md#recorded)): addiction
  (FNV's `UMON` usage monitor and withdrawal spells), weapon poisons,
  Damage Threshold, critical chance, Rebound, Cateye, and the script-only
  effects (Fixer, antivenom, Steady, Super Stimpak's after-effect, repair
  kit, Stealth Boy's stop-combat).
- Region build (Goodsprings to Primm, 125 consumables): effect kinds
  dropped 44 → 20 (34 drops, all drift: 10 `UMON`, 11 on weapon
  poisons); consumables with no effect 31 → 11, now carrying the zero
  placeholder; 47 consumables changed; 6 MGEF copies added (Hydra), no
  FormID moved; FO4Edit 31 errors → 0.

<a id="chem-addiction"></a>**Chem addiction (built 2026-10-29, not yet played).**
`spike/addiction.py`. FNV's ALCH `ENIT` names a withdrawal spell and an
addiction chance (the export drops both; read from FalloutNV.esm). FO4's
chems carry three parts of one addiction: `ENIT`'s addiction spell
(`AbAddictionJet`...) and chance, an `AddictionOdds*` effect raising that
addiction's actor value (25 on Jet), and an `AddictionKeyword*` keyword
(alcohol has none). FO4 has the same addictions as FNV for alcohol, Psycho,
Jet, Mentats, Buffout and Med-X. A chem whose withdrawal is one of those
takes the counterpart chem's spell, effect and keyword at FNV's chance:
morphine counts as Med-X and Ultrajet as Jet. FNV's Hydra, Turbo, Steady,
tobacco, ant nectar and Quantum withdrawals have no FO4 addiction and are
counted (`ALCH addiction left out`). Fixer is its converted script.

<a id="survival-needs"></a>**Survival needs (built 2026-10-23, not yet played).**
`spike/survival_needs.py` feeds FNV's Hardcore need effects on consumables
into FO4's Survival mode, kept as it is (decided 2026-10-22). FalloutNV.esm
has 155 need effects on its consumables: 95 lower Hunger
(`RestoreStarvationLevel`), 25 lower Dehydration, 27 raise it
(`DamageDehydrationLevel`: alcohol, Nuka-Cola, salty food) and 8 lower
Sleep Deprivation (Nuka-Cola, Quantum, Atomic Cocktail, coyote tobacco).
Every one but unpurified irradiated water's is gated on IsHardcore, which
now counts as on for these effects (Survival gates them itself).

How vanilla Survival works (`Hardcore:HC_ManagerScript` on the
`HC_Manager` quest, read from the `.psc` and Fallout4.esm's VMAD, which
overrides no number): on `OnItemEquipped` it feeds the food pool by the
item's **price** when it has `ObjectTypeFood`, and the drink pool by its
price when it has `HC_SustenanceType_QuenchesThirst` or `AnimFurnWater`
(`ObjectTypeDrink` does nothing). `ObjectTypeAlcohol`, `ObjectTypeChem`,
`ObjectTypeStimpak` and `HC_SustenanceType_IncreasesThirst` cost half the
price in drink; `ObjectTypeCaffeinated` takes one sleep tier off and delays
the next by 2.333 hours (7 with `ObjectTypeExtraCaffeinated`). Both pools
lose 4 per game hour; an item with a `NonFoodKeywords` keyword, such as
`HC_IgnoreAsFood` (on 21 vanilla items, wild crops included), is skipped.

What the build does:

- **Amounts by hours.** FNV's needs rise one point per `fHCStarvationRate`
  (25), `fHCDehydrationRate` (not in the ESM; FalloutNV.exe's default is 10)
  and `fHCSleepDeprivationRate` (50) real seconds, at TimeScale 30: 4.8
  hunger, 12 thirst and 2.4 sleep points per game hour (the wiki's table
  agrees). An amount is the hours it covers at that rate, times Survival's 4
  per hour: purified water 50 → 17 (vanilla's purified water: 20), Brahmin
  steak 50 → 42, whiskey's +25 dehydration → −8. Keeping a stage-for-stage
  scale instead (FNV's 200 points against Survival's first 16-24) would make
  FNV food feed about a seventh of its worth, since Survival's stages come
  about 7 times sooner.
- **Hunger and thirst** run `F3NV_SurvivalNeed`, a Script-archetype effect
  (fire and forget, self), one per FNV effect and amount: FO4's Papyrus
  cannot read an effect's magnitude, so the Survival amount is the script's
  `Amount` property, as vanilla's `AddictionOddsScript` carries its
  `Magnitude` (the item's magnitude shows the same number). It calls
  the manager's own `ModFoodPoolAndUpdateHungerEffects` and
  `ModDrinkPoolAndUpdateThirstEffects` (raises negative), plus its
  `FillDiseaseRiskPool` on eating and drinking, as vanilla food does, only
  while `HC_Rule_SustenanceEffects` is on. Vanilla has no effect that feeds
  by an amount (its pools take the price), so this script is the one piece
  of our own.
- **Sleep** goes through vanilla's caffeine: the effect equips a hidden,
  weightless potion carrying `ObjectTypeCaffeinated` (and
  `ObjectTypeExtraCaffeinated` from 4.67 hours, the middle of the two
  delays), which the manager handles as it does `HC_SippableWater`, only
  while `HC_Rule_SleepEffects` is on. The magnitude shown is the delay.
  Nuka-Cola's 15 points (6.25 hours) are extra caffeine, as are every other
  Nuka-Cola's, the Atomic Cocktail's and coyote tobacco's; only Rum &
  Nuka's 5 (2.1 hours) is plain caffeine.
  FNV raises Sleep Deprivation on no consumable; it would be dropped.
- **No price feeding.** An item with need effects carries
  `HC_IgnoreAsFood` beside its category keyword, so Survival does not also
  feed or dehydrate by its price; its vendor and category keywords stay.
  Chems and stimpaks without FNV needs keep Survival's own thirst cost.
- A HasPerk test on a need effect is kept (water's +7 with a perk).
- Region build (Goodsprings to Primm, 125 consumables): 81 consumables
  carry need effects (105 uses of 32 `F3NV_SurvivalNeed` effects, one per
  FNV effect and amount; 6 of them caffeine) and are the only consumables
  changed; one hidden potion added (extra caffeine; the plain one has no
  user in the region); no FormID moved; 1,786 of 1,786 scripts compile;
  FO4Edit 0 errors.

## <a id="sex-change"></a>Sex change without Garden of Eden (built 2026-10-29, not yet played)

FNV changes the player's sex in Doc Mitchell's intro (VCG01's message box),
before every `ShowRaceMenu` (the converted race menu asks the sex first), and
in six test-quest lines. FO4 Papyrus has no sex setter, so
`TES4Polyfill.SetSex` ran the console's `sexchange` through Garden of
Eden's `ExecuteConsoleCommandSilent`, the build's only use of that mod.

The F3NV F4SE plugin now does it (`tes_runtime/fo4_condition/sex.cpp`):
`F3NV_Sex.ChangeSex(actor)` queues the game's own `SexChange` script command
on the main thread. In Fallout4.exe 1.11.240 the command is opcode 0x11E6 in
F4SE's script command table (`g_firstObScriptCommand`), with two optional
parameters (Sex, Integer) and its handler at 0x5C5B00. The handler reads its
arguments with the engine's argument reader (0x5B3600), which takes a count
of 0 as success. With no sex given it toggles: it reads the actor's sex
(0xC5D930), flips the base's female flag (0x30A6F0 on `actorData`), rebuilds
the head and resets the 3D (0xC742F0). It acts on the calling reference when
that is an actor (form type 0x41), else on the player (`g_player`,
0x32DD370). That is what the console's `sexchange` does, so the behavior is
unchanged; `SetSex` still calls it only when the sex differs. The script
compiler no longer reads Garden of Eden's sources.

## <a id="before"></a>Before the pipeline: build and research

In order. **Built** marks what is done.

1. **Stable FormIDs.** **Built 2026-10-10** ([FormIDs](fo4_spikes.md#formids)):
   - FNV's own ids for one-to-one records;
   - hashed ids for generated ones;
   - FalloutNV.esm's source ids reserved first, as the Skyrim pipeline
     does, so the hashed window (0x180000 to 0xF00000) is the one the
     pipeline will use.
2. **Record coverage census.** **Built 2026-10-10** ([census](#census)).
3. **Exterior navmesh across cells.** **Built 2026-10-10** ([exterior navmesh](#exterior-navmesh)). The spike converted one interior
   cell's navmesh. Exteriors need FNV's authored edge links (NVEX) carried
   into FO4's NVNM, and NAVI entries for every navmesh. The parsing is
   already in `navm_falloutnv.py`; FO4's edge-link and NAVI layout still
   needs to be read out of xEdit's definitions.
4. **Persistent references and the worldspace layout.** FO4's persistent
   cell, cell blocks and sub-blocks at full size, and which references
   must stay persistent (quest aliases, doors, map markers, enable
   parents).
5. **Map markers, locations, encounter zones.** **Built 2026-10-12** ([locations](#locations)); the worldspace map art is not.
   - FO4 quests and aliases lean on LCTN records; FNV has none.
   - Design location records from FNV's map markers, encounter zones
     (ECZN) and interior ownership.
   - Also the worldspace map: the CK `-MapMaker` switch, or FNV's map art.
6. **Regions, climate, weather, water.** **Built:** FNV's climate and weathers ([weathers](#weathers)), region
   weathers ([region weather](#region-weather)), water heights ([water](#water-heights)).
7. **Performance without precombines.** The region holds the 118 cap ([measured](#region-measured)); the denser areas wait for the whole map. Measure frame rate in the densest
   FNV areas once they exist (Freeside, the Strip, Novac), before deciding
   whether the precombine/previs stage is needed for the first release.
   FNV's world is sparser than the Commonwealth.
8. **LOD.** Terrain through xLODGen (FO4 supported) or our own terrain LOD
   generator with an FO4 BTR writer; object LOD from FNV's own LOD meshes
   ([fnv-to-fo4](research/fo4_target.md#fnv-to-fo4) renamed them).
9. **NPCs in general.** **Built from 2026-10-12** ([npcs](#npcs)). Real FNV NPCs, not stand-ins:
   - FO4 races and head parts, with the face fit from spike 2;
   - packages, factions, inventories;
   - LVLC → LVLN;
   - creatures through the replacement table.

## <a id="atomic-adds"></a>Cross-script increments (built 2026-10-13, played 2026-10-21)

`set Q.v to Q.v + 1` on another script's variable read and wrote it in one
step: FO3/FNV run scripts one at a time. Papyrus runs each event on its own
thread, and reading a property and writing it back are two calls into the
owner. So two geckos dying together both read 1 and both wrote 2.
VFreeformGoodsprings then counted 2 of the 3 second-well geckos, and 1 of
the third well's 2, and the gecko hunt stalled.

`script_convert/atomic_adds.py` fixes this. A pre-pass finds every
increment whose owner (a quest's script, or a scripted reference's base
script) declares the variable: 322 sites on 57 variables. The owner then
gets `TES4Add_<v>(by)`, which also keeps the variable's mirror global in
step. Each caller's write becomes a call to it, which Papyrus runs one at a
time per object.

## <a id="trace"></a>Session trace (built 2026-10-13)

Quest bugs in the opening chain showed in game only as "she stands there".
Examples: a line said twice, kills counted once, geckos already dead in an
old save. Each needed a play-through and console checks to narrow down. The
converted scripts now trace what they do, and a reader turns a session's
Papyrus log into a timeline.

- **Switch.** `TES4Trace`, a global in FalloutHelpers.esl (object id 0xA01),
  off by default. Turn it on with `set TES4Trace to 1` in the console. While
  it is off, each trace point costs one call and one global read, and builds
  no text.
- **Trace points** (`script_convert/trace_points.py`, TES4Polyfill
  `Trace*`):
  - every converted SetStage: the quest, the stage asked, whether it was
    set, and the stage it ends at;
  - every atomic add: owner, variable, new value;
  - every mirror global write;
  - each converted line's begin and end: speaker and FNV INFO;
  - each `SayWhenFree`: asked, started, not started, or dropped as a
    duplicate;
  - each package fragment: actor, fragment, current package;
  - each scripted OnDeath: who died, and the killer.
- **Reader.** `tools/validate/fo4_trace.py` prints the timeline, filtered
  with `--grep` and `--kind`. It flags:
  - a stage not set, or one that goes back;
  - a Say that never started or was dropped;
  - a line begun twice within 30 s;
  - a counter that skips or goes back.

## <a id="formid-ledger"></a>FormID ledger (built 2026-10-17)

Generated FormIDs are hashed from authored keys (`derive_formid`), and a
collision goes to whichever key asks first. So a build that adds content
could move an existing record's id, and some keys counted copies in build
order ([audit](fo4_tool_audit.md#formids)). Simulated with the real writer,
growing today's 11,302 hashed ids tenfold moved 34–70 of them.

- **The ledger** (`fo4_import/base/ledger.py`) is `<plugin stem>.formids.tsv`
  beside the plugin. Each build reads it first: a key it holds keeps its id,
  and its ids are reserved so no new key can take one. A key it lacks is
  hashed as before and added. The file is sorted text, one line per id.
- **Stable numbers** (a quest's alias ids, Say Once marker stages) are kept
  in the same file (kind `n`).
- **Replacing a key keeps its id.** A call site moving to an authored key
  passes the key it replaces as `legacy`: with no ledger entry yet, the id is
  the old key's hash, so the build that switches keys moves nothing.
- **The writer.** `LedgerWriter` (in `ledger.py`, not `writer.py`) is the
  plugin writer that keeps a ledger. It stays out of `writer.py` because the
  face-fit cache's code tag covers `writer.py` (through `spike/records.py`):
  a ledger change there reran all 165 of the region's face fits.
- **Keys that counted copies now name them** (`CellBuilder.new_id(owner,
  key)`; a key given twice raises, since two records would share an id):
  - a copy of a line: the FNV line, its part and where it sits (the quest
    and conversation step, or the quest's topic);
  - a menu option and its padding: the step, the topic, the prompt and the
    line's quest;
  - a menu's five topics (four player topics, then the NPC's): the step and
    the topic's slot;
  - the greeting scene, when force-greet topics join it: labelled
    `greeting` instead of its list of lines, which grows with content.
- **Kept numbers.** An objective target's alias id is the lowest free one
  from the first target alias, kept per quest; a Say Once line's marker
  stage is its hash moved up past the stages already given or kept.
- **What still counts.** `FormIDs from a counted key` in a build's counts is
  how many generated records still take a count-based key.

## <a id="worldspaces"></a>Several worldspaces, and builds without the test cell (built 2026-10-17)

`--world` takes any number of worldspaces (`all`: every one with grid
cells). The first keeps `--region`/`--around`; the others, and the first
with `--whole`, are built whole. Each worldspace gets its own WRLD group,
persistent cell, root location and map-region locations.
- **Doors.** A door's teleport now leads to its partner wherever the build
  placed it: interior, exterior, or another built worldspace. Before, an
  exterior door paired with another exterior door lost its teleport
  (14 WastelandNV doors: the Hoover Dam ladders, FortMainCampGate,
  VHDLegateCampGate, vCCFortGate and NVCCBarge).
- **Doors leading out of the build** are counted. With `--no-test-cell` an
  interior door whose partner is not built keeps no teleport, and QASmoke,
  its stand-in doors and the test chest are left out. Without the switch,
  region builds keep them as before.
- **Interiors.** Every interior a built worldspace's doors reach is built.
  Today's single-worldspace build leaves out 109 of FNV's 388 interiors
  (44,498 references) and the Strip, Lucky 38 and Freeside worldspaces.

## <a id="source-plugin"></a>The source plugin (built 2026-10-17)

Fields the export lacks (reference room and ownership data, static
collection parts, factions, weathers, regions, voice types, imagespace
modifiers, consumable and armor fields) were read from a fixed
FalloutNV.esm, so a Fallout 3 or DLC build would have read another game's
records for its FormIDs. A build now reads the plugin its export came from:
`base/source.py` resolves it through the source registry (Fallout3.esm to
Fallout 3's Data folder), and `build()` hands it to `install.use_source`,
which `install.source_esm()` reads (once a run). One build converts one
plugin, so the readers' run caches hold one plugin's records.

## <a id="water-heights"></a>Water heights (built 2026-10-17)

The worldspace copied the Commonwealth's DNAM (default water 450) and every
exterior cell wrote XCLW FLT_MAX, which FO4 reads as "the worldspace's
default" (36,320 of Fallout4.esm's 36,865 exterior cells do the same). FNV's
WastelandNV defaults to −2300 and 412 cells set 2600 (Lake Mead, the
Colorado). So 134 cells dry in FNV fell under 450 and flooded, and 346 lost
their water. The worldspace now takes FNV's default land and water heights
(DNAM) and LOD water height (NAM4), and each cell its own XCLW. The region
had 2 cells losing water and none flooding.

## <a id="placeable-water"></a>Placeable water (built 2026-10-19, played 2026-10-21)

FNV places pools, springs and puddles as PWAT references: a flat mesh, and
the record's water type (DNAM). The export now writes DNAM (flags and water
type); before, PWAT was a bare static and every reference was skipped.
FO4 places water as an activator with a water type (ACTI WNAM) on a generic
tile the reference scales: 33 of Fallout4.esm's 45 use `Water\Water1024.nif`
and 4 `WaterCircle1024.nif`. The tile carries the water shader and a
convex volume on collision layer 11 (water), so swimming and wading come
with it. FNV's meshes are 512 squares, 512-wide strips (1×2 to 1×4), a
2048 square, a 512 circle and a bathtub (46×114).
`fo4_import/spike/placeable_water.py`:

- Each PWAT is a copy of the vanilla tile activator with FNV's EditorID and
  a water type. The circle is picked when the FNV mesh's triangles fill
  under 90% of its extent (a circle fills π/4).
- Each reference becomes tiles placed through the SCOL parts path: squares
  the width of the mesh's shorter side, in a row along the longer side. A
  1×4 strip is four tiles at scale 0.5, the 2048 square one tile at 2, and
  the bathtub three overlapping 46-unit tiles.
- The water type is a copy of the Fallout4.esm placeable water type nearest
  in shallow and deep color (FNV WATR DNAM bytes 40 and 44, FO4's 4 and 8).
  The copy takes FNV's drinking effect: clean (`WaterFountainCleanDrinking`,
  no contact spell) for FNV's Purified water, else irradiated
  (`WaterRadiationDrinking`, `WaterRadiationHazard`). This is the same test
  the drinkable activators use. Nearly every vanilla type is lightly
  irradiated, so taking one as is would have made Goodsprings' spring
  radioactive.
- Part references now keep their source reference's persistence. Before,
  they were always temporary, and `Exterior.group` keeps only the persistent
  part of the persistent cell, so the region's 8 exterior water references
  (in WastelandNV's persistent cell) placed nothing. No SCOL reference in the
  region was affected (616 parts before and after).

Region: 4 water activators and their water types; 28 tiles from 13
references (blood 5, Goodsprings' clean water 20, dirty 1, toxic 2). Whole
game: 29 PWATs on 27 water types.

## <a id="region-weather"></a>Region weather and sounds (built 2026-10-19, played 2026-10-21)

A region with a weather list overrides the climate in the cells that list
it: Goodsprings' `GSWeatherRegion` plays `NVWastelandGS` (FNV's thicker
fog there), and `NVBorderRegion` plays `NVWastelandBorders`. FO4 does the
same, through a REGN record and each exterior cell's region list (XCLR,
after XCLW; 9,264 of Fallout4.esm's cells carry one). The REGN layout is
FNV's: colour (RCLR), worldspace (WNAM), areas (RPLI edge falloff and RPLD
points, one pair per area), then an 8-byte RDAT (type, flags, priority)
before each data entry, with weather entries in RDWT (weather, chance,
global; 12 bytes each). `fo4_import/spike/regions.py`:

- A region FNV's built cells list (XCLR, 4,363 of FNV's 30,497 cells, read
  from FalloutNV.esm because the export has none) is written once, if it
  has a weather entry. It keeps FNV's colour, areas, flags and priority;
  its worldspace and weathers become the converted ones; a global the
  build lacks reads 0. Its other data (map name, sounds, objects, land,
  grass, imposters) is left out; map names are the locations' own.
- The record is on its own hashed FormID (site `FNV weather region`),
  apart from the emittance's daylight copy of the same FNV region: 6 FNV
  regions are both.
- Each weather is written once per build (`weathers.fnv_weather`), whether
  the climate or a region names it first.

Region: 2 weather regions, Goodsprings' on 27 of the 253 exterior cells and
the border on 21; 2 more weathers (4 in all). Whole game: 24 FNV regions
with a worldspace carry weather, 3 of their entries name a global.

**Sounds.** A sound entry (RDAT type 7) is FNV's RDSD: sound, weather flags
(pleasant, cloudy, rainy, snowy) and chance as a percentage × 10,000. FO4's
is RDSA: a sound descriptor, the same flags, and chance as a fraction
(0.01 to 1.0 in Fallout4.esm's 220 entries, median 0.05). So FNV's 200000
is 0.20. A region with weather or sounds is written. Its music (RDMO,
RDSI, RDSB) is left out; music comes from audio markers ([music](#music)). FNV's interior sound regions
(`AudioInt*`) have no worldspace and reach interiors through acoustic
spaces ([acoustic spaces](#acoustic-spaces)). The ledger site keeps its
first name (`FNV weather region`), so the regions built first keep their
FormIDs. Region: 8 regions, 6 of them with 67 sounds.

## <a id="vertex-alpha"></a>Vertex alpha on lit shapes (built 2026-10-19, played 2026-10-21)

Victor's shack (`NV_ShackVictor.NIF`) still showed rusty metal sticking out
after its material was split ([audit fixes](#audit-fixes)). Its triangles,
UVs, texture (DXT5, alpha kept) and alpha test (threshold 100) all match
FNV's. The one difference: the rusty-metal shape's vertex colours carry
junk alpha (as low as −3.3e38). FNV ignores it, because that shader has
`sf_vertex_alpha` off, but the converter clamped it into 605 of the shape's
1,173 vertices at 0. A lit shape's FO4 shader (`SHADER_FLAGS`) never sets
vertex alpha. Vanilla agrees: of 600 Architecture meshes, alpha-tested lit
shapes without the flag have vertex alpha 255 in 84 of 93 cases, and low
alpha goes with the flag (103 shapes). A lit shape's vertex alpha is now
written as 1 (`convert_static.opaque`). Unlit shapes keep their vertex
alpha rules (FNV's baked soft shadows fade by it). Grass
(TallGrassShaderProperty) keeps FNV's vertex alpha too: a height ramp FO4's
grass needs to sit on slopes ([spike 4](fo4_spikes.md#spike-4-exterior)). Not yet confirmed in
game as the cause of the shack's strips.

## <a id="acoustic-spaces"></a>Acoustic spaces (built 2026-10-19, played 2026-10-21)

FNV gives an acoustic space (XCAS) to 373 interiors and 17,112 exterior cells.
FO4 gives one only to interiors (282 of Fallout4.esm's cells) and leaves the
outdoors to region sounds, so only an interior's XCAS converts.
`fo4_import/spike/acoustics.py`:

- FNV's ASPC has four loops by time of day, a walla sound, the region whose
  sounds play inside (RDAT; 112 of 113 name one) and an environment type
  (ANAM, an EAX preset). FO4's has one loop (SNAM), the region (RDAT), a
  reverb record (BNAM), the interior flag (XTRI) and weather attenuation
  (WNAM, 0 as 46 of 84 vanilla).
- A space takes FNV's dawn/default loop, its region (`regions.py`; an
  interior region has no worldspace and is written without one), and the
  vanilla reverb `REVERBS` names for its environment type.
- Spaces and the cells' XCAS are read from FalloutNV.esm (the export has
  neither).

Region: 9 acoustic spaces on 27 interiors.

## <a id="looping-sounds"></a>Looping sounds (built 2026-10-19, played 2026-10-21)

FNV's statics (STAT RNAM), movable statics (MSTT SNAM), lights (LIGH SNAM)
and doors (DOOR BNAM) can carry a looping sound. FO4 has the slot on
movable statics (SNAM), lights (SNAM, after FNAM) and doors (BNAM), not on
statics. A static with a loop is written as a movable static on the same
FormID with the loop, as vanilla's humming and whirring objects are. The
export drops STAT RNAM and MSTT SNAM, so `sounds.looping_sounds` reads them
from FalloutNV.esm. The light and door loops come from the export.

Region: 256 statics now movable statics with their loop, 13 movable
statics, 6 lights, 3 doors. Each loop plays at FNV's own volume and reach
([sounds](fo4_spikes.md#spike-4-sounds)); first play, they all took the
steam-pipe template's, and the casino's hums were far too loud.

Also fixed: two FNV sounds naming the same file queued the same converted
file twice, and the second copy failed on itself (`voice.convert`). Region
sounds were the first to share files.

## <a id="log-noise"></a>Papyrus log noise (2026-10-19)

Played 2026-10-19 with some stutter: Papyrus.0.log had 28,266 lines in five
and a half minutes, most of them errors with stack traces. Grouped by
message and first script frame:

| Errors | Script | Cause | Now |
|---|---|---|---|
| 3,825 | `Lucky38LightScript` (OnTimer, every 0.5 s per light) | FNV's IsAnimPlaying became `GetAnimationVariableBool("bAnimPlaying")`, a Skyrim-side graph variable; FO4's objects play NIF sequences (PlayGamebryoAnimation) with no graph, so every read errored and returned false | IsAnimPlaying is 0 on FO4 (`command_rows_fallout4`): the same value without the error. FO4 has no way to ask a NIF sequence, so a script waiting for one to end does not wait (35 FNV scripts use it; unchanged behavior) |
| 675 | `GenericScript` (OnTimer) | Addiction checks through effect-family keywords (`TES4FX_addict*`, `HasMagicEffectWithKeyword`); FNV effects become vanilla FO4 effects, which carry none, so the properties stay unfilled | Guarded on FO4: `(kw && ref.HasMagicEffectWithKeyword(kw))` |
| about 2,500 | quest timers: followers, the Primm deputy, Arcade, ED-E, VMQ01/05, Victor in the boulder | Calls on references and forms outside the region build (None) | Not changed: a region build lacks them; a whole-map build fills most |
| 210 | vanilla `DLC04_GZSetConsciousOnHit` | A Nuka-World script's properties on a vanilla reference | Not ours |

## <a id="radiation"></a>Radiation (built 2026-10-19, played 2026-10-21)

FNV gives a reference a radiation rate (XRAD, rads a second; 119 in
FalloutNV.esm) over its radius (XRDS). FO4 has no such field: it places
hazards (PHZD; 981 in Fallout4.esm, nearly all its generic
`RadiationHazard<Light|Strong|Deadly><256..2048>`). Their spells deal 1, 3
and 6 a tick (with 10, 30 and 60 beside). `fo4_import/spike/radiation.py`
places the hazard whose grade is nearest the reference's rate and whose
radius is nearest its own (256 without one). The hazard stands at the
reference's position, persistent and initially disabled as the reference
is, whether or not the reference's base converts.

Region: 6 hazards.

## <a id="reference-fields"></a>Item counts, open doors, occlusion planes, decals (built 2026-10-19, played 2026-10-21)

FO4's REFR keeps these in FNV's layout, so `placement.py` copies them from
FalloutNV.esm:

- XCNT (item count): 33 in FNV.
- ONAM (open by default): 185.
- XOCP and XORD (an occlusion plane's size and its four linked planes,
  renumbered as portal rooms are).

FNV's plane marker (engine form 0x17) has no record in FalloutNV.esm. It
is Fallout4.esm's `PlaneMarker` on the same FormID (187 placed in vanilla),
shared as the portal marker is (`items.PLANE_MARKER`).

Region: 1 item count, 3 doors open by default, 3 occlusion planes.

**Placed decals.** FO4 places texture sets as decals as FNV does (24,718
in Fallout4.esm; FNV has 2, the blood in Vikki and Vance, enabled after the
robbery). `fo4_import/spike/decals.py` writes the texture set: FNV's
diffuse and normal (staged as any texture), and its decal data (DODT,
the same layout in both games), with three changes. Shininess is FO4's
1.0 (FNV's 300 is a specular exponent; 132 of vanilla's 180 decals use
1.0). Flags keep alpha blending, alpha testing and no subtextures (FNV's
bit 0 is parallax, FO4's POM shadows). FNV's two junk bytes are 0. The
references place as any reference, enable parent included. Region: 1
texture set, 2 decals.

## <a id="nv-ammo"></a>Ammo subtypes, ammo effects and casings (built 2026-10-22, not yet played)

`spike/ammo_mods.py`, `spike/ammo_casings.py`,
`static_scripts/fallout4/F3NV_AmmoCasings.psc`; export:
`tes4_export/record_types/ammo_falloutnv.py`.

**Projectile (creature guns played 2026-10-28).** A converted FNV ammo is
FO4's 5.56 round (`Consumables.ammo`), and FO4 fires a gun's ammo's
projectile unless a mod overrides it, so the securitron laser fired 5.56
bullets. Ammo a creature's embedded gun fires now takes the projectile of
its FO4 template's ammo (`fired_from`; the lowest FNV weapon FormID's when
several do): the securitron's micro fusion cells fire `LaserRifleBeamRed`
(`Protectron01LeftArmLaserGun`'s `AmmoFusionCell`), its rockets
`MissileProjectile`. Ammo is written after every gun (`write_ammo`).
Taking a human gun's template's ammo projectile was wrong (micro fusion
cells got `RailwayRifleProjectile`, since `gun_choice` picks the FO4 gun
by how it is held and fired, not what it shoots).

<a id="nv-projectiles"></a>**Projectile (human guns, built 2026-10-28, not
yet played).** `spike/projectiles.py`, `data/projectiles.json`. FNV names
the projectile on the gun (WEAP `DNAM` +36), and one round feeds guns that
fly different ones: micro fusion cells feed lasers, plasma rifles, the Gauss
rifle, the tri-beam and the plasma caster. A round overrides its gun's only
for subtypes (AMMO `DAT2` Projectile: 12/20 ga slugs, coin shot, bean bag,
incendiary and HE grenades, HE/HV missiles; 8 rounds). Fallout 4 names it on
the round (AMMO `DNAM`), and a gun overrides it in its own `FNAM`
(`Override Projectile`, right after `# Projectiles`; 47 Fallout4.esm guns
use it, among them the playable Institute laser and the minigun), and a mod
through `OverrideProjectile` (property 80, 73 vanilla properties, all FORM
SET with value 2 = 440). So:

- The table maps each FNV projectile EditorID to a Fallout4.esm one (51
  entries): bullets to the tracer of the nearest caliber, `AutoTracer` to
  `AssaultRifleProjectile`, the minigun's to `MiniGunProjectile`, Gauss to
  `GaussRifleProjectile`, buckshot and slugs to `ProjectileShotgun`; lasers
  to `LaserRifleBeamRed` (the tri-beam to the splitter's
  `LaserSmallBeamRed`, the pulse gun and Tesla cannon to blue beams);
  plasma to `PlasmaProjectileLarge` (the pistol's `PlasmaProjectile02` to
  `PlasmaProjectileSmall`); flamers to the flamer streams; 25/40 mm
  grenades to `BroadsiderProjectile` (an arcing shell exploding on impact,
  75 damage; FNV's are 50 and 100; FO4's frag grenade is a fused lobber,
  its missile flies flat); missiles to `MissileProjectile`; the Fat Man to
  `FatManProjectile`. A target Fallout4.esm lacks fails the build; an FNV
  projectile left out is counted (`projectile not mapped`).
- A converted gun whose template is playable takes its FNV projectile's as
  its `FNAM` override and FNV's projectile count (`DNAM.ProjectileCount`)
  as `FNAM`'s; vanilla's splitters and plasma shotgun barrels multiply that
  count (MUL+ADD), so they still work. A default-combination part setting
  `OverrideProjectile` would beat `FNAM`, so such a vanilla part becomes a
  copy without it (`Guns.own_projectile`), and an `fnv`-mode part copy drops
  it. Creature guns (template not playable) are left as above.
- A round with its own FNV projectile has its ammo mod SET
  `OverrideProjectile` to it, so slugs fly as slugs (a mod's property beats
  the gun's `FNAM`). Swapping back to the plain round drops the mod.
- The round itself (`write_ammo`) flies a creature gun's template's
  projectile (above), else its own override's, else that of the
  lowest-FormID FNV gun FNV does not mark Embedded (`DNAM` Flags1 0x20)
  loading it first, else 5.56.

Swapping a part at the workbench to a vanilla one with its own
`OverrideProjectile` (a suppressor) flies that part's, as in Fallout 4.

<a id="projectile-copies"></a>**Projectile copies (built 2026-10-29, not yet played).**
`spike/projectile_copies.py`. Each FNV projectile flies a copy of its
stand-in (FormID hashed from FNV's) with FNV's range, which suits beams too.
A stand-in that flies (Missile or Lobber: grenades, missiles, plasma, the
Fat Man, the alien blaster) also takes FNV's speed and gravity. FO4's
bullets and lasers are hitscan beams, and their speed means nothing. An
explosion is copied when the stand-in has the Explosion flag and FNV's
projectile has one. The copy takes FNV's force, damage and radius as the
outer radius, the inner radius scaled with it: the 40 mm grenade does 100
(the Broadsider shell 550), the missile 200. Plasma stand-ins carry
`ExplosionMissileShell` without the flag, so they still don't explode.
Models, lights, sounds and impacts stay the stand-in's.

**Build check (2026-10-28).** GSDocMitchellHouse with every FNV gun in the
test chest (a scratch harness): 134 WEAP, 82 AMMO, 68 ammo mods. 98 of
the 110 guns on a playable template fly their FNV projectile's stand-in from `FNAM`
(lasers, RCW, gatling `LaserRifleBeamRed`; plasma rifles and caster
`PlasmaProjectileLarge`; plasma pistol, defender, multiplas
`PlasmaProjectileSmall`; tri-beam `LaserSmallBeamRed` x3; shotguns
`ProjectileShotgun` x7; grenade launchers `BroadsiderProjectile`; missile
launchers `MissileProjectile`), and the three missile launchers include a
copy of `mod_PlasmaGun_BarrelPlasma_Short_A` without its
`PlasmaProjectileLarge`. Eight ammo mods carry a round's own projectile
(slugs, coin shot, bean bag, HE/HV missiles, incendiary and HE grenades).
The other 12 name no projectile (detonators, binoculars, the camera,
Euclid's C-Finder) or an unmapped one (7, counted: the MS-22 film, the
four Tesla chain effects, the Nellis artillery, the satellite strike;
scripted effects, not carried). The sawed-off shotguns (14 pellets) match no FO4 gun and are
skipped, as before.

**Export.** FNV's AMMO `DAT2` past the weight (Consumed Ammo: the casing,
and its chance in percent), `ONAM` (short name), `QNAM` (HUD abbreviation)
and every `RCIL` (ammo effect) were dropped, and AMEF was dumped as sizes
only. Both now export (`DAT2.Casing`, `DAT2.CasingChance`, `ONAM`, `QNAM`,
`RCIL[i]`; AMEF `FULL`, `DATA.Type`, `DATA.Operation`, `DATA.Value`). The
change only adds lines. FalloutNV.esm: 92 AMMO, 111 RCIL, 52 rounds with a
casing; 54 AMEF: damage x (19), DT - (15), condition x (11), spread x (5),
DT x (3), fatigue + (1); no DR effect.

**Census: how Fallout 4 changes a gun's ammo.** Fallout4.esm has 11 weapon
OMODs with an `Ammo` property, all `SET`, each with `NPCAmmoList` `SET`:
the Alien Blaster's `AmmoStandard` / `AmmoConversion` pair at `ap_gun_Mag`,
and nine .38/.308/.45/.50 conversion receivers at `ap_gun_receiver`. Each is
crafted at the weapons workbench from a COBJ with no bench keyword. The
Alien Blaster lists `ap_gun_Mag` in its `APPR` and its default combination
includes `AmmoStandard`. 69 of the mod recipes have no components (no
`FVPA`).

**What is built.** Each FNV ammo list (a gun's `NAM0` FLST) that a converted
gun loads, with two or more of its ammo converting, becomes:

- a mod-association keyword `FNV_ma_<list>`, added to every gun loading it;
- one OMOD per ammo, `FNV_mod_<list>_<ammo>`, at our attach point
  `FNV_ap_Ammo` (TNAM 2, named "Ammo"), setting `Ammo` to the converted
  round, with FNV's effects as properties; its name is the round's and
  its description lists the effects;
- a free recipe per mod (`FNV_co_mod_...`: CNAM, INTV 1; no components,
  no bench), as vanilla's free mod recipes.

The gun gains `FNV_ap_Ammo` in `APPR` (inserted before its object template
when it has none) and its default combination includes the list's first
ammo's mod, which is the gun's own `DNAM` ammo. FormIDs are hashed from the
FNV list and ammo FormIDs; existing records keep theirs.

| FNV effect | Fallout 4 property |
|---|---|
| Damage x v | `AttackDamage` MUL+ADD v - 1 |
| Damage +/- v | `AttackDamage` ADD +/-v |
| Spread x v | `AimModelMinConeDegrees` and `AimModelMaxConeDegrees` MUL+ADD v - 1 |
| DT - v | `ActorValues` ADD `FNV_AmmoDTReduction` v, plus `Enchantments` ADD `FNV_enchAmmoDT` |
| DT x v | `ActorValues` ADD `FNV_AmmoDTMultiplier` v - 1, plus the enchantment |
| Projectiles per shot n | `NumProjectiles` SET n (slugs 1, coin shot 8) |
| Condition, fatigue | none; counted as `ammo effect left out` |

DT follows vanilla's armor-piercing receivers exactly: they add
`enchModArmorPenetration` and the weapon actor value `ArmorPenetration`; the
enchantment's effect (`ModArmorPenetrationAddPerkEffect`) applies
`ModArmorPenetrationPerk`, entry point 37 Mod Target Damage Resistance,
function 14 Multiply 1 + Actor Value Mult over that actor value. Ours are
copies with our own actor values and one perk `FNV_AmmoDTPerk` of two
entries: function 5 Add Actor Value Mult (`FNV_AmmoDTReduction` x -1: the
target's resistance less the DT taken off, flat, as converted armor rates
FNV's DT unscaled) and function 14 (`FNV_AmmoDTMultiplier` x 1). Vanilla
uses function 5 with EPFT 8 in 16 perk entries.

**Casings.** GECK: the casing is "randomly created in the user's inventory
every time the weapon is fired" at the percent chance. Hand Loader (Guns)
and Vigilant Recycler (Energy Weapons) multiply it by 2: entry point 57
Modify Chance for Ammo Item, conditioned on `IsWeaponSkillType`. Fallout 4
has no such field; `OnPlayerFireWeapon` fires only out of combat, on a
timer. So a start-game quest `FNV_AmmoCasings` runs `F3NV_AmmoCasings` on
its player alias: it listens for the `weaponFire` animation event (as the
NV Ammo Crafting mod does), finds the group of the equipped gun's base ammo
(a group is a gun's FNV ammo list, keyed by its first ammo), and 0.5 s
after the last shot reads each group member's count; the drop is the rounds
fired, each rolling FNV's chance (times the group's perk multiplier when
the player holds it). Ammo gained, dropped, handed over or used while a
menu is open (crafting, barter) moves the counts, so it is not taken for
firing; ammo a script removes during play is. This needs no F4SE: the mod used F4SE instance data to
learn the loaded ammo, which the count drop gives here. Arrays: the casing
ammo (`FNV_CasingAmmo`), casings, chances, each group's first ammo,
member ranges, perk and multiplier. A group's perk is the FNV perk of
entry point 57 for the skill of the first gun (lowest FormID) loading it.

Not carried: FNV's projectiles' own explosions and speeds (each flies its
Fallout 4 stand-in's, [above](#nv-projectiles)), `QNAM` (Fallout 4's HUD shows no abbreviation), condition effects (no weapon
condition), the bean bag's fatigue, `NPCAmmoList` on the mods, and casings
for NPCs (FNV gives them to the player only). Swapping ammo needs the
weapons workbench. Since 2026-10-22 no FNV weapon or round is a Fallout4.esm record itself
(`item` mode): the 9mm and laser pistols, dynamite, the three mines, the
straight razor, boxing gloves and knife are copies (`stats`), so they carry
FNV's names and stats and take FNV's mods and ammo. The 9mm round and the
small energy cell left the table and convert as every other FNV round
does ("9mm Round", "Energy Cell"): as Fallout 4's "10mm Round" and "Fusion
Cell" they shared names with other ammo. Rows in [drift](fo4_drift.md#recorded).

**Region build (2026-10-22).** 36 of 79 weapons take the ammo slot (19
lists): 65 ammo mods, 65 recipes, 10 more rounds made (the subtypes), 20
condition effects and 1 fatigue effect left out; the casing quest tracks 51
rounds. 167 records added, none of the deployed build's 42,227 FormIDs
moved (its ledger seeded the build). FO4 check: 0 errors; 1,790 of 1,790
scripts compile.

<a id="ammo-switch"></a>**The Ammo Type hotkey** (`spike/ammo_switch.py`,
`F3NV_AmmoSwitch.psc`, `F3NV_AmmoSwitchItem.psc`; built 2026-10-22, not yet
played).
- **What FNV does:** the Ammo Type hotkey reloads with the next round of the
  gun's list that the player carries.
- **How it is built:** Loads of Ammo v2's method, in vanilla Papyrus
  ([read](research/fo4_target.md#ammo-switching)).
  - A start-game quest holds each list the build made ammo mods for: the
    list keyword its guns carry, and each round's item, mod, "loaded"
    keyword and notification.
  - `Cycle()` finds the equipped gun's list by that keyword on its weapon
    record (`Weapon.HasKeyword`), and the round
    it holds by the keyword each round's mod adds (`AmmoMods.mark`,
    `FNV_AmmoLoaded_<ammo>`, one per FNV round). Without either keyword it
    takes the first.
  - It then steps to the next round the player carries, wrapping round,
    attaches that round's mod (`AttachModToInventoryItem`), equips the
    ammo and shows the round's FNV name.
- **The hotkey:** an aid item, "Ammo Type", for the Favorites wheel. The
  quest gives the player one. Its script effect gives the item back and
  calls `Cycle()`.
- **The Pip-Boy:** V on a gun lists its rounds and loads the one chosen
  through the same quest ([fo4_condition.md#ammo-list](fo4_condition.md#ammo-list)).
- **Messages:** "No other ammo for this weapon", "This weapon takes one
  kind of ammo".
- **Drift:**
  - With two of the same gun carried, the switch refuses ("drop one"),
    since `AttachModToInventoryItem` cannot pick a copy, as in Loads.
  - Choosing ammo in the Pip-Boy has no counterpart: Fallout 4 cannot
    equip ammo there.
  - The loaded round shows as a notification, not on the HUD.

## <a id="new-game"></a>Starting the source game (`spike/new_game.py`)

`FNV_NewGame` is a start-game quest running `F3NV_NewGame`.
- **New Game:** Fallout 4 runs MQ101 stage 0, its intro movie and then
  character creation. The script waits that out, undoes it and stops Fallout
  4's opening quests. It then sets the player's SPECIAL to FNV's player
  record and sets VCG00 stage 0, which moves the player to Doc Mitchell's
  and plays FNV's intro.
- **A coc from the main menu** runs no MQ101 stage 0. Until 2026-10-22 that
  started FNV at once, which pulled a `coc qasmoke` test out of its room.
  Now nothing starts; the log says `TES4NewGame|no New Game opening`.
- **Starting by hand:** `setstage FNV_NewGame 10`. Its fragment
  (`F3NV_NewGameStart`) calls `F3NV_NewGame.Begin()`, the same start, once
  only.
- A save where FNV's opening or Fallout 4's own game is under way is left
  alone.

## <a id="music"></a>Music (built 2026-10-19, played 2026-10-21)

**How FNV plays music.** FNV plays its music through audio markers: 572
placed references to the engine's marker 0x23, with MMRK set. Each names a
media location controller (ALOC, 89) over a radius (XRDS) with two layer
boundaries (MNAM, NNAM).

- A controller picks media sets (MSET, 140) by the player's standing with
  a faction (neutral, ally, friend and enemy sets), plus location sets and
  battle sets.
- A set is one of four types:
  - battle (32): one loop;
  - location (81): low, mid and high stems by distance from the marker,
    day and night;
  - dungeon (23): explore, suspense and battle loops;
  - incidental (4): random one-shot sounds.
- A cell's own music type (XCMO, a MUSC) is mostly one of FNV's defaults
  (no music 159, dungeon 63, explore 35, public 26, base 9). Those name
  folders FNV ships no files for, so in FNV they play nothing.

**How FO4 plays music.** FO4 plays a music type (MUSC): flags, priority,
fade and a track list (TNAM) of tracks (MUST). A track is a single file
(ANAM, `data\Music\...wav`, read as .xwm), a palette or silence, chosen
by conditions. Fallout4.esm's explore tracks test day as `GetCurrentTime`
>= 6 and <= 20, and night as < 6 or > 20. Vanilla tracks carry no
duration.

**The mapping** (`fo4_import/spike/music.py`):

- **Controllers.** A controller takes its first location set, else its
  first neutral set. Standing variants, battle sets (FO4's own combat
  music plays) and incidental sets are left out. A controller with neither
  kind of set is silent; `musCtrlAAAntiMusic` has only battle sets.
- **Location sets.** A location set becomes a music type of its outer layer
  (the low stem, heard across the whole radius): a day track and a night
  track, each if FNV enables it (PNAM). FNV stacks mid and high stems
  closer in; FO4 cannot layer by distance.
- **Dungeon sets and music types.** A dungeon set plays its explore loop.
  An FNV MUSC naming a file plays it; one naming a folder, or none, is
  silence.
- **Interiors.** An interior's music (XCMO) is its audio marker's, else
  its MUSC's. Every built interior has exactly one marker.
- **Outdoors.** Each audio marker becomes a music region: a 16-sided
  polygon of its radius, with the sound entry (RDAT type 7) naming the
  music (RDMO). Its priority rises as radii shrink (10 for the widest), so
  a town's zone wins over the desert around it. Every cell it reaches
  lists it (XCLR). The worldspace's music (ZNAM) is silence, as FNV is
  between zones.
- **Files and sources.** Music files convert to `Data\Music\FNV` with the
  sound jobs. Media sets, controllers and markers are read from
  FalloutNV.esm (the export does not decode MSET or ALOC).

Region: 14 music types, 22 tracks on 16 files (14 MB), 20 music regions;
28 interiors with music, 9 of them silent.

## <a id="placed-mines"></a>Placed mines (built 2026-10-19, played 2026-10-21)

FNV arms a mine as a PGRE reference on a projectile (PROJ). FO4 does the
same with its own mine projectiles (Fallout4.esm: 395 PGREs, 340 of them
`FragMineProjectile`). The export now writes PGRE like any placed reference;
before, it was an unknown record type. The cell build reads PGRE with REFR,
and `pack_refr` writes the record type it is given.
`fo4_import/spike/mines.py` takes the FNV weapon that throws the projectile
(WEAP DNAM), converts it through the replacement table, and places the FO4
weapon's projectile (WEAP FNAM, byte 29). Table entries: frag mine →
`fragMine`, bottlecap mine → `BottlecapMine`, powder charge → `fragMine`
(FO4 has none). Two FNV items naming the same `item` target used to keep
only the last one (`replacements.items`); both now get it.

Region: 11 frag mines at the Powder Ganger camps. Whole game: 174 placed
(frag 131, powder charge 33, bottlecap 3). The 7 C4 charges at Hoover Dam
are left out, because no weapon throws their projectile.

## <a id="weapon-mods"></a>Weapon mods (built 2026-10-22, not yet played)

`spike/weapon_mods.py`. FNV keeps a mod's effect on the gun, not the mod:
WEAP's slots `WMI1`-`WMI3` name an IMOD, and DNAM gives each slot an effect
and a value (offsets 140 and 152; xEdit's `wbModEffectEnum`). FalloutNV.esm:
35 guns name all 50 IMODs; 9 IMODs sit on two guns, 2 of them with
different values (the recycler: 1 shot on the RCW, 3 on the recharger
pistol). So each (gun, slot) becomes its own OMOD. The export dumps IMOD
as sizes only, so names, models and the slot data are read from the
plugin.

- **The item.** An IMOD becomes the loose mod: a MISC on FNV's FormID
  with FNV's name, model, value and weight and `ObjectTypeLooseMod`, as
  vanilla's 1,481 loose mods. It converts wherever FNV puts one
  (containers, leveled lists, vendors, placed in the world), and the
  test chest holds one of each.
- **The recipe, locked.** The workbench lists a weapon mod only through a
  recipe (COBJ, no bench keyword, as all 1,481 vanilla mod recipes). With
  none, a converted gun showed its Ammo slot but none of its FNV mods,
  carried items or not (played 2026-10-22). With a recipe taking the loose
  item, which no vanilla COBJ does (0 of 1,273), each mod showed both a
  build and an attach entry (played 2026-10-22). So a recipe has no
  components and one condition, `HasPerk FNV_WeaponModFound` ("Mod Item"),
  a hidden perk no one holds, as vanilla's perk-gated recipes lock a mod.
  A carried mod item is expected to fit it all the same, as Fallout 4 lets
  a loose mod past its recipe's perk requirements (built 2026-10-22, not
  yet played). FNV's mods are never crafted. A mod
  replaced at the bench comes back as its item (`LNAM`).
- **Which gun takes it.** Each converted gun gets its own
  mod-association keyword (`FNV_ma_<gun>`, KYWD type 5 as vanilla's 163
  `ma_` keywords), which its FNV mods target (`MNAM`); its vanilla `ma_`
  keywords go, so a converted gun lists only FNV's mods (FNV guns took
  only their own). This applies to every gun copy, mods or none. Weapons used
  as FO4's own record (`item` in the table) are not copies, so FNV mods
  attach to nothing there. The 9mm pistol was one until 2026-10-22, when
  it became a copy of the 10mm (`stats`), as did the laser pistol.
- **Where it attaches.** By effect, at the point vanilla gives that part
  (`POINTS`): capacity at the magazine (else the barrel, as a tube
  magazine, then the receiver: the railway rifle and double-barrel
  shotgun have no magazine point), zoom at the scope, silence at the
  muzzle, spread, projectile speed and split beam at the barrel, weight at
  the grip (stock), the rest at the receiver; the first in that list that
  the gun's record (`APPR`) or default parts offer and no earlier slot of
  the gun took. The .357 revolver's condition mod takes the receiver, so
  its long barrel's damage goes on the barrel; the service rifle's forged
  receiver goes on the barrel behind its springs.
- **What it copies.** The FO4 gun's own part of that kind (its `ma_`
  keywords in the part's `MNAM`): its largest magazine, its scope (night
  vision first when FNV's has it) or its suppressor (`HasSilencer`), lowest
  FormID on ties. The copy keeps the part's model, attach slots, includes
  and its keyword, bool and form properties (the scope's overlay, the
  suppressor's quieter projectile) but not its numbers, which are FO4's
  balance. Without such a part it copies the gun's default part at that
  point whole, since installing it removes that part; without one, no
  model.
- **The effect** (FNV's semantics checked against the wiki dump):

  | FNV effect | FO4 properties |
  |---|---|
  | Clip capacity +A | `AmmoCapacity` ADD A |
  | Damage +A | `AttackDamage` ADD A |
  | Weight −A | `Weight` ADD −A |
  | Spread −A | `AimModelMin/MaxConeDegrees` MUL+ADD −A ÷ FNV's spread (DNAM 16): the 10mm laser sight halves both cones |
  | Rate of fire +A (a fraction) | automatic: `Speed` MUL+ADD A (vanilla's faster automatic receivers); else `AttackDelaySec` MUL+ADD −A ÷ (1 + A) (vanilla's hair trigger) |
  | Split beam A | `NumProjectiles` ADD A, `AttackDamage` × 1 ÷ (1 + A): A + 1 beams sharing the damage, as FNV's engine does |
  | Zoom A (the scope's FOV, degrees) | `HasScope`, `ZoomData` the vanilla preset nearest (night vision ones when FNV's DNAM Flags2 0x1000), `ZoomDataFOVMult` 70 ÷ A (FO4's default world FOV, so the view is FNV's A degrees), keywords `HasScope`, `dn_HasScope`, `dn_HasNightVision` |
  | Silence | `SoundLevel` Silent, keywords `HasSilencer`, `s_20_Silenced` (a sound keyword, type 6), `dn_HasMuzzle_Suppressor`: what the 10mm's suppressor adds; a copied suppressor also keeps its projectile override |
  | Max condition, ammo regeneration, projectile speed | none: FO4 has no item condition yet ([drift](fo4_drift.md#candidates)), no ammo regeneration, and no projectile speed property; the mod installs with no effect (counted) |

  A FormID property's second value is vanilla's (440 on keyword ADDs,
  441 on ZoomData), as is a bool's (1).

FormIDs are hashed from FNV's (`FNV weapon mod` and `FNV weapon mod
recipe`: the gun's FormID and slot; `FNV weapon mod lock`: its EditorID; `FNV weapon mod keyword`: the gun's),
so nothing else moves. Tests: `tests/test_fo4_weapon_mods.py`.

Goodsprings to Primm (2026-10-22): 44 mods and recipes on the region's
guns, every slot placed, all 50 loose items; 8 of the 44 have no FO4
effect (condition 4, projectile speed 2, ammo regeneration 2); FO4Edit
check 0 errors. The varmint rifle (on the pipe rifle) takes the pipe
rifle's drum magazine (+3), its zoom scope (night vision preset, 15°)
and its silencer.

## <a id="weapon-criticals"></a>Weapon criticals and AP cost (built 2026-10-29, not yet played)

A converted weapon is a copy of an FO4 weapon, so it carried that weapon's
critical data and V.A.T.S. AP cost; the export did not carry FNV's
([export](../commentary/tes4_export_falloutnv.md#weapon-criticals)).
`spike/weapon_vats.py` now writes FNV's onto every copy (FNV stats on an FO4
gun, and FNV guns on their own mesh):

- **AP cost** (DNAM 112): FNV's own on the 203 of 261 weapons with "Override
  - Action Points" (13 to 25 for most guns); the other 58 (creature guns,
  fists) take their class's `fActionPointsAttack*` setting (unarmed 22, one-
  and two-hand melee 15 and 30, pistol 20, rifle 25, handle 20, launcher 40,
  grenade 35, mine 10, thrown the engine's default).
- **Crit Damage Mult** (CRDT 0): FO4 multiplies a critical hit's damage by it
  (the CK's definition; 251 of Fallout4.esm's 252 weapons use 2.0); FNV adds
  its Critical Damage, so the multiplier is (damage + critical damage) /
  damage. FNV: 117 weapons double (2.0), 46 add nothing (1.0), the uniques
  between (1.07 to 3.0); 17 with no base damage keep the FO4 weapon's.
- **Crit Charge Bonus** (CRDT 4): FO4's meter fill multiplier (1.0 on 244
  vanilla weapons, 0 to 80 on the rest) takes FNV's Crit % Mult (1 on 150
  weapons, 0 on 19 that never crit, up to 100).
- **Crit Effect** (CRDT 8): FNV's 8 critical effects (on 64 weapons) are
  self spells on the victim: laser, plasma and alien disintegration, two
  flamer effects, the nuke, and two knockdowns (Rex's bite, the Victory
  rifle). FO4's energy weapons carry their own disintegration effects, so a
  weapon with an FNV effect keeps its FO4 weapon's effect and on-death flag;
  one without has none. Drift: the two knockdowns, and FNV effects on a gun
  whose FO4 weapon has none.

FO4's V.A.T.S. meter still works as FO4's; FNV's random roll is the next
section.

<a id="random-criticals"></a>**FNV's random critical roll (built 2026-10-29, not yet played).**
FalloutNV.exe (GOG 1.4.0.525) rolls a critical on every hit, each bullet
of an automatic its own roll, at 0x9B7060: `rand() % 1000` against the
chance x 10. The chance:

1. the base (0x646D80): the CritChance actor value (14) divided by the
   weapon's Fire Rate when it is automatic (Flags1 0x2; a rate of 0 counts
   1), times its Crit % Mult (skipped below 0). No condition term: the
   GECK wiki's `fWeaponConditionCriticalChanceMult` is Fallout 3's;
2. the attacker's perks on entry point 1, Calculate My Critical Hit Chance
   (`ApplyPerkModifiers` 0x5E58F0, with the weapon and the target), then the
   target's on 0x24, Modify Enemy Critical Hit Chance;
3. plus `fVATSCriticalChanceBonus` in V.A.T.S. (5 in FalloutNV.esm; the
   wiki's 15 is Fallout 3's).

CritChance is `fAVDCritLuckBase` + `fAVDCritLuckMult` x Luck (0 + 1 x
Luck), plus abilities: Finesse +5, True Police Stories, Built to Destroy.
FNV's entry point 1 perks: Laser Commander (+10), Set Lasers for Fun (+2,
+4), Ninja (x1.15, melee and unarmed).

FO4 rolls every hit, in and out of V.A.T.S., on its own entry point 1, Mod
Critical Chance, from 0: vanilla Overdrive's `FortifyCritChance25xChemPerk`
adds 25 there (the "Critical Hits Outside of VATS" mod adds Luck x 1 the
same way). `spike/criticals.py` makes the entries of the hidden perk
`FNV_CombatRules` (`spike/combat_perk.py`, which also carries the [weapon
skills](#weapon-skills)):

- **Weapon factors.** Crit % Mult over Fire Rate when automatic, 32
  distinct values in FalloutNV.esm (124 weapons at 1, 19 at 0, the assault
  rifle's 1/8, uniques up to 100). `type_tests` stamps each weapon with
  `FNV_CritFactored` and its factor's keyword (none at 1).
- **The perk** adds, for each factor f (its keyword on the weapon tab; a
  weapon without `FNV_CritFactored` counts 1): Luck x f x
  `fAVDCritLuckMult`, the helper plugin's `CritChance` x f, and f x
  `fAVDCritLuckBase` when it is not 0. Only additions, so FO4's order of
  perk entries (priority, which the CK wiki leaves unclear) cannot change
  the result.
- **FNV's crit chance multipliers** (Ninja's x1.15) become, in their own
  perk, additions of (multiplier - 1) x the same base, by factor; the
  converted perk keeps its rank and weapon conditions. FNV's additions
  (Laser Commander, Set Lasers for Fun) convert as they did.
- **CritChance** is a new helper actor value (`FalloutHelpers.esl`, object
  id 0x81F, appended), so FNV's crit chance abilities and consumables, which
  were dropped for want of one, now convert onto it.
- **Who holds it:** the player (F3NV_NewGame, on a new game and every load)
  and every NPC and creature record the build writes (PRKR added before the
  plugin is written; a templated actor's comes from its template).

Left as FO4's: the V.A.T.S. meter (with FNV's charge rate per weapon,
above). In V.A.T.S. the perk adds `fVATSCriticalChanceBonus` (5), as FNV
does after the perks and whatever the weapon's factor; the owner tab tests
`GetVATSMode` not 0, which no vanilla perk uses (not yet played).

<a id="requirement-spread"></a>**Requirement spread (built 2026-10-29, not yet played).**
`spike/requirement_spread.py`. FalloutNV.exe's gun spread (0x646910) is a
sum: `fStandingSpreadPenalty` (0.1) unless crouched,
`fUnaimedSpreadPenalty` (0.2) unless aiming, walking 0.1 and running 0.2
divided by the perk-modified move mult, crippled arms 0.2-0.6, then
`fWeapStrengthReqPenalty` (FalloutNV.esm 0.025) per point of Strength short
of the weapon's requirement (WEAP `DNAM` +168) and the same per started 10
points of its skill short of its skill requirement (+200). The sum is then
scaled by the skill and floored at `fMinGunSpreadValue`. The caller
(0x8B0F99) applies Calculate Gun Spread perks and stores it on the actor.
FalloutNV.esm's 217 weapons need Strength 1-10 and skill 25, 50, 75 or 100.

FO4's Mod Cone-of-fire Mult (134) only multiplies, so a shortfall
multiplies the cone by 1 + penalty / `fStandingSpreadPenalty`: FNV's ratio
for a standing, aimed shooter, 1.25 per point of Strength. Moving or
hip-firing, FNV's ratio is smaller (drift). Weapons carry
`FNV_StrengthReq_<n>` and `FNV_SkillReq_<n>` keywords (`type_tests`).
`FNV_CombatRules` holds one Multiply Value entry per requirement and band:
Strength exactly n short (owner `GetValue Strength ==`), and skill k steps
short (two owner conditions, under and at least), whose weapon tab also
tests the weapon's skill keyword. That is 45 Strength entries and about 160
skill entries. They commute with the skill's multiply.

<a id="sneak-attacks"></a>**Sneak attacks (built 2026-10-29, not yet played).**
FalloutNV.exe flags a hit a sneak attack (0x400) when the attacker sneaks
and the living target has not detected it (0x9B7060), then:

- multiplies the critical chance, V.A.T.S. bonus included, by
  `fCombatSneakAttackBonusMult` (100 in FalloutNV.esm): in practice a
  critical hit, except with an automatic of small factor or a weapon that
  never crits;
- multiplies the hit's damage (0x9B73D0) by
  `fCombatDamageBonusMeleeSneakingMult` (the engine's 5; FalloutNV.esm
  leaves it) with no weapon or a hand-to-hand or melee one (animation
  types 0-2, 0x6450C0), else by `fCombatDamageBonusSneakingMult` (1).
  `fDamageSneakAttackMult` is registered but never read.

FO4 multiplies a sneak attack's damage by its own `fCombatSneak*Mult` (guns
2, melee and unarmed 3). `spike/sneak_attacks.py` gives `FNV_CombatRules`:

- the critical part as additions, as Ninja's multiplier folds: the base
  terms by factor and the V.A.T.S. bonus, each x (100 - 1), under owner tab
  conditions vanilla's `FortifySneakAttackBonus2xChemPerk` uses (IsSneaking,
  and GetDetected of the player run on the target equal to 0) plus
  GetIsID Player. GetDetected names the player, so this is the player's;
  FNV's perks' additions (Laser Commander) are not multiplied by it;
- Mod Sneak Attack Mult (18), Set Value: FNV's 1 with a weapon of a ranged
  FNV animation type (its keyword), else 5 (FO4's fists and creatures'
  attacks carry no FNV keyword, and FNV counts no weapon as melee). This
  replaces FO4's 2 and 3 for everyone holding the perk.

<a id="weapon-poisons"></a>**Weapon poisons (built 2026-10-29, not yet played).** FNV counts an
ingestible a poison when every effect is hostile (MGEF flag 0x4; JIP's
`AlchemyItem::IsPoison`): Tremble, Mother Darkness, Silver Sting, Bleak
Venom and the scorpion poison (and its dummy). FalloutNV.exe's Pip-Boy
(0x95E6F0) puts one on the equipped weapon only when its skill is Melee
Weapons (0x26) or Unarmed (0x2D), else shows `sPoisonNoWeaponMessage`; a
weapon already poisoned is refused (`sPoisonAlreadyPoisonedMessage`, the
exe's "The current weapon is already poisoned."); the weapon holds one
poison (`ExtraPoison`, no charges), spent on its next hit. FO4 cannot coat
a weapon, so these were converted with no effect. Now
(`spike/weapon_poisons.py`):

- the poison item carries one script effect, `F3NV_WeaponPoison`: with an
  equipped weapon carrying FNV's Melee Weapons or Unarmed skill keyword and
  no coat on (any perk of `FNV_WeaponPoisonCoats`), it gives the player the
  poison's hidden coat perk; otherwise FNV's message shows and the item
  comes back;
- the coat perk casts the poison's spell on the actor hit (Apply Combat Hit
  Spell, 51, Select Spell; its weapon tab tests the same keywords);
- the spell is the poison's effects by touch on the victim, whatever FNV's
  range (`attack_spells.poison`: detrimental value effects on FO4's poison
  effects, script effects converted), plus `F3NV_PoisonSpent`, which takes
  the coat perk from the attacker: one hit, as FNV.

Drift: the coat is the player's, not the weapon's, so it stays through a
switch to another melee or unarmed weapon; FNV's confirm box before
applying (`sPoisonConfirmMessage`) is not shown.

<a id="damage-threshold"></a>**Damage Threshold and Damage Resistance (built 2026-10-29, not yet played).**
The hook approach is Zoltanite's "Modular Damage Threshold System - F4SE"
(Nexus Fallout 4 mod 109168; credit Zoltanite as its creator; permissions
and our analysis of it in
[research](research/fo4_damage_threshold_reference.md)). Our code and
formula are our own, from Fallout4.exe 1.11.240 and FalloutNV.exe.

FalloutNV.exe (GOG 1.4.0.525) at 0x9B5A30, per hit: DR first, then DT, then
the floor.

1. DR: the target's DamageResist actor value (0x12) / 100, changed by the
   ammo's DR effect, capped at `fMaxArmorRating` / 100 (85 in
   FalloutNV.esm); damage x (1 - DR).
2. DT: the target's DamageThreshold (0x4C), at least 0, changed by the
   ammo's DT effect, less the attacker's perks' ignored DT (entry 58), plus
   the target's DT perks (entry 0x38, 56), at least 0, divided by the
   weapon's projectile count (a shotgun's pellets each face a share).
3. damage - DT, at least `fMinDamMultiplier` (0.2) x the hit as it came.

FO4 instead scales a hit by its resistance curve, `Fallout4.exe+0x6CB2E0`
(actor value, damage, resistance; returns the share that gets through),
called for physical damage at `+0xE38C3D` (the resistance after the
attacker's Mod Target Damage Resistance perks, entry 37; the target in rsi)
and per damage type at `+0xE3AF4A` (the target's object at [[rbx]]). The
F3NV plugin (`tes_runtime/fo4_condition/damage.cpp`) points both calls at
stubs that add the target and jump to `FalloutDamage`, which for physical
damage and EnergyResist returns FNV's share: max(damage x (1 - DR) - DT,
floor x damage) / damage, DT the physical resistance (energy: the target's
DamageResist), DR the target's FalloutDamageResist. Radiation, fire, cryo
and poison keep FO4's curve. It patches a call only while it still calls
the curve, and stays off until `F3NV_NewGame` calls
`F3NV_Damage.SetRules` (FNV's floor and cap, the three actor values) at a
new game and each load.

The data:

- FO4's DamageResist carries FNV's DT: armor's rating is its DT (FNV
  armor: 203 with DT; FO3 armor, which has no DT field, keeps its DR), and
  FNV's DamageThreshold actor value is renamed to it, so DT abilities (20
  spells, creatures' among them) and consumables (Whiskey and the other
  `IncreaseDamageThreshold` items) convert onto it; they were dropped.
- FNV's DamageResist (a percentage) is the helper's new
  `FalloutDamageResist` (0x820): Med-X's and Psycho's DR effects are copies
  of FO4's DR effects on it, and converted scripts and conditions reading
  DamageResist read it. 9 FNV armors carry DR (8 of them with no DT, Fallout
  3 leftovers); their DR is left out.
- Ammo DT effects were already FO4's entry 37; FNV's attacker DT perks
  (58: Piercing Strike 15, Shotgun Surgeon 10, the companion suite 10) now
  are too, FNV's Set Value x as Add Value -x.
- Converted actors' own stat lists replace their FO4 stand-ins' (1,151
  Fallout4.esm NPCs carry DamageResist, up to 175 on sentry bots); a
  stand-in race's small DamageResist (Brahmin 10, Bloatfly 5) stays.

Not converted: the defender DT perks (56: Toughness 3/6, Stonewall 5 vs
melee, Hit the Deck 25 vs explosives, the DT implant 4, Bonds of Steel 4,
Kamikaze -2), which FO4 has no defender entry point for (abilities on
DamageResist would carry the unconditioned ones); the per-pellet DT share;
ammo DR effects.

<a id="weapon-skills"></a>**Weapon skills in combat (built 2026-10-29, not yet played).**
Read from FalloutNV.exe (GOG 1.4.0.525); the GECK wiki's formulas are
Fallout 3's in places:

- **Damage** (0x644CE0): every weapon but hand-to-hand (animation type
  0) does base x (`fDamageSkillBase` + 0.01 x skill x `fDamageSkillMult` x
  the condition penalty), then the attacker's Calculate Weapon Damage perks.
  FalloutNV.esm sets 0.5 and 0.5: half damage at skill 0, full at 100. The
  skill is the weapon's (its DNAM skill), 100 with no weapon. The condition
  penalty scales only the skill part; the condition plugin's own damage
  effect scales all of it (drift at low condition).
- **Spread** (0x646910, the gun spread FNV's Calculate Gun Spread perks then
  modify): standing, walking, running and unaimed penalties, the limbs, then
  `fWeapStrengthReqPenalty` (FalloutNV.esm 0.025) per point of Strength
  short of the weapon's requirement (at most 10), the same setting per
  started 10 points of skill short of its skill requirement (weapon +0x1BC;
  `fWeapSkillReqPenalty` is registered but never read), all of it x (1 -
  `fWobbleToSkillConversion` (0.5) x skill / 100), at least
  `fMinGunSpreadValue`. Fallout 3's `fGunSpreadSkillBase`/`Mult` are
  registered but never read.

FNV's 40 Calculate Weapon Damage perk effects are all multiplies, and of
its 4 gun spread effects only Steady sets (to 0, whatever the order) and
one penalty adds. `spike/weapon_skills.py` gives `FNV_CombatRules`, for
each skill FalloutNV.esm's weapons use (its helper actor value), entries
whose weapon tab tests the weapon's `FNV_WeaponSkill*` keyword and whose
owner tab tests the skill above 0:

- Mod Weapon Attack Damage (35), not on `FNV_WeaponAnimHandToHand`
  weapons: Multiply Value `fDamageSkillBase`, then Multiply 1 + Actor Value
  Mult by the skill x `fDamageSkillMult` / (100 x `fDamageSkillBase`); the
  product is FNV's term, and multiplies commute with FNV's damage perks.
- Mod Cone-of-fire Mult (134): Multiply 1 + Actor Value Mult by the skill x
  -`fWobbleToSkillConversion` / 100.

Converted NPCs carry their FNV skills (`npc_skills.py`), the player theirs
through the character rules. Drift: creatures, which FNV gives one Combat
skill instead, keep full damage and spread (their skill tests fail at 0);
the Strength and skill requirement penalties are left out, being additions
in FNV's spread units, which FO4's cone of fire does not share.

## <a id="audit-fixes"></a>Audit fixes (built 2026-10-17)

The [tool audit](fo4_tool_audit.md)'s findings, as fixed. FormIDs, world
building and dialogue are above ([ledger](#formid-ledger),
[worldspaces](#worldspaces), [water](#water-heights),
[conditions](#dialogue-conditions)).

**Dialogue.**
- *Menu options* take their topic's lines from an index by topic
  (`Hub.by_topic`, in Hub order), as do menu steps and the greeting order,
  instead of scanning every Hub line each time (the audit's model: about
  1.1 billion compares, ~92 s, for the whole game).

**Scripts.**
- *Mirror after an atomic add.* A direct write of a counter after its add in
  the same function sets the kept value first, so the mirror global and
  later reads see the assigned value. 16 writes in 3 FNV scripts; VMS21a's
  Omerta thug now mirrors 4, so INFO 0012745D (`OmertasDead == 4`) can pass.
- *Adders* keep the sum in a local and write, mirror, trace and return it,
  so two adds at once cannot both return the final value (192 adders).
- *Counters on placed references* (`VTopsBlackjackDealer01REF.nPlayersAtTable`
  and others) are atomic too: the adds' owners come from the cross-reference
  graph. 22 more increments in FNV, on 13 owner scripts, with 60 callers.
- *Quest delay.* `SetQuestDelay X 0` means the 5 s default; other values are
  floored at 0.1 s. After a gap over 2 s (a menu, a load), GetSecondsPassed
  counts the quest's current `TES4_Delay`, not the compile-time interval
  (58 quest scripts).
- *Incremental compile.* The saved state carries a hash of every header
  `.psc` (10,284 files, under 1 s), so a changed header recompiles
  everything. A script that fails with no error of its own (a script it
  uses failed, or the compiler died) is compiled again at once in one batch,
  and again on the next build if it still fails; one with its own errors
  waits for a change. Out of memory is the usual cause: the 15 parallel
  compilers peak at 10.8 GB together (0.94 GB each), on top of the build;
  two runs on a busy machine lost 37 and 61 scripts. So the batches now run
  as many at once as free memory holds (`core.memory_budget.memory_workers`),
  keeping 2 GB free: one compiler measured 0.93 GB on 84 scripts and 1.02 GB
  on 300, so each is counted as 1 GB plus 0.5 MB per script. A compile deletes the `.pex` of a script it compiled last time
  and no longer has; another plugin's scripts in the same folder are never
  touched. The spike compile takes the script prefix from the plugin's
  namespace (`FALLOUT3_` as well) and adds Doc Mitchell's script only when
  it exists.
- *Player-hit trace on old saves.* `F3NV_NewGamePlayer` on the new game
  quest's Player alias starts the trace on every load.

**Items.**
- *Script form lists* hold every entry the build makes (items, placed
  bases, actors and their bases, globals, factions, creatures, messages);
  dropped entries are counted by type, and a list with none left is not
  made. Of FNV's 464 lists, 389 are made when the placed forms are built.
  NVRatList keeps its 9 creatures and DLC03TeslaExplosionList its 12.
- *Armor that kept the template's models* (98 of 389): 47 skinned headgear
  now sit on FO4's head through FNV's Bip01 Head skin transforms; 30 with no
  world model wear their FNV mesh; 21 stay on the template (19 with slots
  that are neither headgear nor upper body, 2 with no FNV model). Each kind
  is counted.
- *Headgear alternate textures* convert as material swaps, as outfits'
  do (HeadWrap02/03/04, HelmetNVNCRTrooperMP).
- *Worn headgear meshes* are `<static>_worn_<slots>[_female].nif`, one per
  slot set, so two hats on one mesh no longer overwrite each other or the
  world mesh.
- *Guns.* Choosing an FO4 gun writes no FNV assets (region: 48 guns, 0
  files). A part copy (experimental `fnv` mode) is keyed on the FNV gun and
  attach point. 68 of 110 guns tie at the best distance (28 across FO4
  weapons); ties still go to the lower FO4 FormID.

**Faces, voice and NPCs.**
- *Skin Tone layers* come from the builder's Fallout4.esm bytes once a build
  (they reread the whole file for every face: 78 ms each).
- *The shared half of a face fit* (the texel to FNV UV mapping, alignment,
  masks, head meshes, FO4's head-part candidates) is kept per process
  (`face/memo.py`). After the first face of a sex and FNV head, a male tint
  fit takes 5.1 s (7.9 before), a female one 1.6 s (4.5), a head-part choice
  about 1.5 s (5.8–6.7). The fitted values are byte-identical (5 NPCs
  compared).
- *Face fits in worker processes.* Before actors are written,
  `Npcs.warm_faces` fits the faces the work cache lacks for every base the
  build reaches (through traits templates and leveled lists), in at most
  6 processes (`FACE_WORKERS`): each holds about 1.26 GB, and BLAS already
  spreads one fit over every core, so more workers gain little (12 faces: 1
  worker 102 s, 4 workers 74 s, 12 workers 67 s). Results match the serial
  fits only at the same BLAS thread count: a sculpt fit has many equally
  good answers and another thread count picks another one (one thread
  changed 163 of the region's 165 faces, by up to 1.8 in a control).
  `configure_multiprocessing` pins child processes to one OpenBLAS thread,
  so the face pool starts its workers with the count the main process
  loaded with (`npcs.MAIN_BLAS_THREADS`).
- *The CK FaceGen timeout* is 2 s per NPC_ record, at least 900 s (the
  region measured 0.43 s per record).
- *Stale FaceGen.* Each build deletes the plugin's FaceGen files it no
  longer uses (`facegen.prune`): a FaceGeom NIF of an NPC_ the plugin no
  longer has, and a face texture, loose or staged for the BA2, whose
  FaceGeom NIF is gone. An export writes both for every face and clears the
  NIFs first, so a texture without one is an older export's. The region's
  staging held 186 faces against the last export's 165 (21 from exports of
  Oct 7–12, one of them for no NPC_).
- *FaceGen textures at vanilla's sizes.* After the CK export,
  `facegen.vanilla_textures` re-encodes the plugin's face textures as
  vanilla does: `_d` and `_msn` BC1 1024 with full mips, `_s` BC5 512 with
  mips. 12.6 MB per NPC became 1.75 MB (about 3.9 GB for 2,247 faces).
- *Voice converted once per recording and transcript*, then copied to every
  line copy that plays it. LipGenerator is not deterministic (two runs of
  one line gave lip tracks of 1,758 and 1,746 bytes), so copies used to
  differ.
- *Vendors* read their services through the template chain
  (`npcs.template_source`, shared with `Npcs.source` and
  `Creatures.source`). No vendor changes: 6 of the 7 templated vendors end
  in leveled lists whose entries trade goods, so a general store is right.
- *Idle markers by what they play.* An FNV idle marker lists idles and
  plays one at random; the export leaves the list out, so `idle_markers`
  reads it (IDLA) from FalloutNV.esm. A placed marker becomes the
  Fallout4.esm marker that plays the like of most of its idles (`PLAYS`, by
  the idle's animation file name, or a creature's skeleton folder); idles
  FO4 has nothing for don't vote, a tie goes to the first idle, and a marker
  with no idles becomes `EmptyIdleMarker`. Weapon-ready idles and ghoul,
  deathclaw and super mutant idles take `PatrolIdleMarker` (which holds
  flavor idles for all three); general fidgets `NPCStandingExamineIdleMarker`;
  smoking, hand warming, sweeping, cowering, dogs, bar tending, reading,
  terminals, healing, repairs, bench work, welding and drinking the marker
  or marker furniture vanilla places most for it. Two earlier choices stay by
  EditorID (the shopkeeper's push broom, MS16's cower). Of FalloutNV.esm's
  1,424 placed idle markers, 1,316 are placed (671 before); WastelandNV 545
  of 590; the region 173 of 185. The 108 left out are counted as `idle
  marker left out: <what it plays>`: protectron idles 55 (FO4 has no
  protectron marker), watering plants 18, Mr Gutsy 15, picking up from the
  ground 7, the Mesmetron daze 5, 8 single scene idles. References keep
  FNV's FormIDs, and the 671 placed before keep their stand-in.
- *Creatures with no FO4 base* are counted by skeleton folder (`ACRE
  skipped (no FO4 base): <folder>`): 283 of FNV's 2,999 placed creatures
  in 32 folders (nvraven 43, smspinebreaker 38, mistergutsy 34, giantant
  23). The whole-Mojave build left out 1,024 placed creatures in 121 bases,
  every super mutant and nightkin among them (Westside's
  `WestsideMeanSonofabitch`, Black Mountain, REPCONN), played 2026-10-25.
  The defaults now give the folders whose creature FO4 has a rule of
  their own, in stats mode as the deathclaw's: `smspinebreaker`
  (`EncSuperMutantTemplate`), `smbehemoth`, `mistergutsy`, `sentrybot`,
  `mirelurk`, `mirelurkking` (super mutants played 2026-10-25, Westside's
  among them; placed creatures left out fell from 1,024 to 341). Still
  without one: the close body plans
  (giant ant, giant rat, night stalker, cazador, raven), turrets, robobrain
  (Automatron's), and the creatures with no FO4 counterpart.

**Meshes and assets.**
- *Files named by their contents.* A BGSM's name adds a tag for an unusual
  normal map (not the diffuse's `_n`), a decal, the spec map's glossiness or
  an unusual glow map; a BGEM's for its blend, normal and env map. A spec map
  is `x_s.dds` at glossiness 10 (the default and commonest), else
  `x_s_g<value>.dds`. Over the region's 2,040 source meshes, names shared by
  different contents went from 16 BGSM, 1 BGEM and 66 spec maps to none (2
  spec maps are one file reached by two spellings). About half the names
  changed (668 BGSM, 477 spec maps, all 89 landscape spec maps), mostly for
  glossiness; 1,297 NIFs change only in those names.
- *Mesh files kept.* `write_assets` takes a mesh's NIF and material bytes
  and its OBND from the work cache (`mesh_cache.cached_files`, site
  `mesh_files`), keyed by the mesh key and checked against the same texture
  stamps, so a current mesh is not unpickled, serialized or bounded again; a
  hit marks its mesh entry used. A NIF or material file that already holds
  its bytes is not rewritten, finished ones included ([held meshes](#held-meshes)). Over 223
  region meshes rebuilt, the step went from 1.45–1.50 s to 0.89–0.90 s
  (13.2–13.7 s to 8.1–8.2 s at the region's 2,028 calls), output
  byte-identical before and after Elric; entries are about 35 KB a mesh.
  Most of what is left is the derived maps' signatures (2.3–2.5 s): each
  spec and glow map reads and hashes its FNV images every build. The
  audit's 61 s was mostly texture copies and decodes, fixed earlier.
- *A weapon's posed mesh* is its own `<name>_weapon.nif`, so a static
  placing the same model no longer gets the dressed weapon mesh.
- *Elric one file at a time.* `elric.finish` keeps only file bytes and parses
  each file again to graft it: over 600 meshes, 823 MB held became 136 MB,
  output unchanged. `without_havok` refuses a block after the Havok input it
  cannot renumber. `elric_cache.finish` keys a NIF by the SHA-1 of the bytes
  the build wrote, so it reads nothing back (600 cached meshes: 2–5 s to
  0.5 s).
- *Code tags* read CRLF as LF (a fresh git checkout writes CRLF, which reran
  all 186 region face fits), hash the native extensions a module names, and
  skip four import edges into code no FO4 converter calls. The mesh key holds
  the ADDN mapping. Closures: convert_static 59 to 33 files, face_fit 51 to
  34, outfit 68 to 43, headgear 66 to 41. This change reran every cache once.
- *Cache pruning.* Entries are touched when used; each build deletes mesh,
  work and Elric entries unused for 14 days (`elric_cache.prune_caches`).
  After a break longer than that, a small build lets a bigger area's entries
  go.
- *Textures.* Every texture goes through `ba2_pack.stage_texture`: written
  once a run, and not at all while its staged copy in `_ba2` matches its
  recorded source (`_ba2/manifest.json`). The archive is repacked only when
  the staged set changed (`<archive>.json`), and staged `fnv` textures no
  build wrote or confirmed are pruned (FaceGen is never touched). For 150
  meshes a rebuild went from 673 copies to none and the pack from 2.5 s to
  0.1 s.

## <a id="published-face-fits"></a>Published face fits (built 2026-10-17, not yet published)

A face fit costs about 2.6 s of wall time in the worker pool, so the game's
~2,247 distinct faces take an estimated 1.5–2 h on a 16-core machine, once
per user and again after any edit to the 34 files in the fit's code tag.
The fits are small numbers, so like the [navmesh cache](../../CLAUDE.md#shared-navmesh-cache)
they can be computed once and installed (`fo4_import/spike/face_fits.py`):

```bash
py -3.14 -m fo4_import.spike.face_fits export --export export/FalloutNV.esm --out face_fits.json.gz
py -3.14 -m fo4_import.spike.face_fits verify face_fits.json.gz   # which sexes this machine can take
py -3.14 -m fo4_import.spike.face_fits install face_fits.json.gz  # -> output/fo4_cache/face_fits.json.gz
```

- **Keyed only on what every user shares.** The work cache keys a fit on
  the basis files' bytes, which hold FO4's baseline head NIF and face
  texture and so can never ship. The file instead carries the fit code
  version (`fit_code`: a SHA-1 of `FIT_SITES`' modules' code tags, so any
  edit to the fit's files changes it, as the navmesh cache's source tag),
  each sex's basis hash (`basis_hash`: a SHA-1 of the basis arrays' names,
  types, shapes and values, never the arrays) and, per sex, each face under
  a SHA-1 of its `FIT_FIELDS` values (no FNV data in the file).
- **Only our numbers and Fallout4.esm FormIDs.** Gzipped JSON, read without
  pickle, so a downloaded file runs no code. A sculpt fit is its FMRI region
  numbers and seven controls each (`encode_sculpt` refuses any other
  subrecord); a tint fit its floats; a head part choice its four FormIDs and
  two coverage distances. `HeadChoice.unmapped` (FNV head part EditorIDs,
  read by no build) is left out. Decoding refuses anything but numbers where
  numbers go. The region's file, read back: 133 faces, the only strings its
  own key names and SHA-1s, FormIDs at most 0x1ED510.
- **Byte for byte.** `export` refuses a fit that does not decode to the same
  value bit for bit (`same`). The one exception is a NaN fraction captured
  (a face with nothing to fit: 0/0), whose sign bit JSON cannot keep; no
  record reads the captured fraction.
- **Fallback.** `Npcs.warm_faces` takes a face the work cache lacks from the
  installed file (`face_fits.take`) and stores it under the local work-cache
  key, so later builds read it as their own. A face the file cannot give is
  fitted locally and counted by why: `faces fitted locally (published fits:
  none installed | fit code differs | male/female basis differs | face not in
  file)`; a taken one as `faces from published fits`.
- **Same faces for everyone.** Fits are not thread-count stable (see [face
  fits in worker processes](#audit-fixes)), so local fits on two machines
  can differ; installed ones are the publisher's for every user.
- **Measured (region, 2026-10-17).** The work cache held 133 current face
  keys (90 male, 43 female) for the region's 165 fitted faces: NPCs with the
  same face fields share one. File: 238 KB (615 KB of JSON). Built twice
  into scratch copies of the mod folder: once with the work cache, and once
  with no face entries in it and the file installed. The second build fitted
  0 faces (133 taken), and all 293 NPC_ records, indeed the whole plugin,
  were byte-identical (276.5 s against 327.0 s).
- **Calibration repeats byte for byte.** All four bases measured twice
  more through the CK on 2026-10-17 (CK 1.11.246 after a Steam update,
  CKPE updated that day) came out byte-identical to each other and to the
  calibrations of 2026-10-06 (male) and 2026-10-12 (female), every array
  and the `.npz` files themselves (`np.savez_compressed` writes no time).
  So users with the same game files should get the same basis hash. Two
  machines were not compared. A sculpt calibration took 389–432 s, and 842
  s with a region build running beside it, close to the CK's 900 s timeout
  floor (`run_ck` gets no plugin from `calibrate`, so it waits only the
  floor).
- **Publishing** is left to the user: upload the exported file as a release
  asset, as `navmesh_cache.py publish` does for the navmesh cache.
  Republish after any edit that changes `fit_code`.

## <a id="census"></a>Record census (2026-10-10)

`fo4_import/record_routes.py` routes every FO3/FNV record type to its
Fallout 4 type; the pipeline dispatches from it. Run the census with
`python -m tools.esm.fo4_record_census export/FalloutNV.esm
export/Fallout3.esm`; it prints the counts and fails on a type with no
route or a target Fallout 4 lacks. Today: all 107 FalloutNV.esm types
routed (Fallout3.esm's are a subset), every target real. The Anchorage
and CaravanPack exports hold assets only.

Kinds: **same** (FO4 has the type), **into** (another FO4 type),
**override** (FO4's own singletons and settings), **system** (an FNV game
system FO4 has no record for: rebuilt from quests, globals and scripts),
**engine** (FO4 makes or holds the data elsewhere).

| Status | Types | FNV records | FO3 records |
|---|---|---|---|
| Converter in the spike | 27 | 398,376 (86%) | 673,329 |
| Partly converted | 23 | 58,168 | 40,463 |
| Not started | 57 | 8,472 | 5,159 |

The records that are not started are few but are the game's rules
(factions, races, combat, weather), and the next phase (AI, quests,
NPCs) needs most of them.

**Converter in the spike** (scoped to the spike's cells, but general):

| Types | Where |
|---|---|
| CELL, WRLD, LAND, LTEX, GRAS, REFR, ACHR | `cell.py`, `exterior.py`, `grass.py` |
| NAVM, NAVI | `navmesh.py` (interior only so far: [exterior navmesh](#before)) |
| STAT, MSTT, DOOR, LIGH, FURN, TREE (as STAT), SCOL | `cell.py`, `furniture.py`, `scol.py`, the NIF writers |
| ACTI | `activators.py` |
| CONT, MISC, LVLI | `items.py` |
| ALCH, AMMO | `consumables.py` |
| SOUN (as SNDR) | `sounds.py` |
| IMGS, IMAD | `imagespace.py`, `imods.py` |
| MESG | `attach.py` |
| SCPT (as Papyrus) | `script_convert` FO4 target, 99.9% compile; attached by `attach.py` |

**Partly converted:**

| Types | FNV | What's missing |
|---|---|---|
| DIAL, INFO, QUST | 18,215 / 23,247 / 436 | Built for the five cell quests (scenes, XDI menus, fragments, objectives). Aliases, quest targets and the remaining 431 quests |
| PACK | 4,163 | Travel, sandbox and force-greet packages only |
| NPC_ | 3,816 | Vanilla stand-ins with FNV's face fitted; real NPCs need race, class, factions, inventory and AI data |
| CREA, ACRE | 1,578 / 2,999 | Dogs on Dogmeat, geckos as mole rats; the rest by the replacement table ([creatures](fo4_replacements.md)) |
| WEAP, ARMO, ARMA | 261 / 389 / 131 | FO4 stand-ins by default; melee, headgear and pre-war outfits on FNV's meshes; guns parked |
| NOTE | 894 | Text notes as paper; holotapes (voice, sound, image) left |
| BOOK, KEYM, TERM, IDLM | 27 / 283 / 344 / 211 | Placed as statics only |
| HAIR, EYES | 67 / 12 | Matched to FO4 head parts per NPC |
| PERK, AVIF | 176 / 64 | Traits by name; FNV skills as helper actor values; perk effects left |
| MGEF, SPEL, GLOB, WATR | 289 / 270 / 218 / 78 | Only what the spike's items and scripts use |

**Not started**, by what needs them:

| Need | Types |
|---|---|
| NPCs and AI | FACT 682, CLAS 74, RACE 22, VTYP 100, LVLN 365, LVLC 343 (into LVLN), IDLE 1,597, ANIO 152, BPTD 49, HDPT 61, TACT 87 |
| Combat and effects | PROJ 95, EXPL 154, IPCT 125, IPDS 60, ENCH 145, EFSH 35, DEBR 6, ADDN 37, CAMS 276, PGRE 174, AMEF 54 (into OMOD), IMOD 50 (into OMOD) |
| World | REGN 276, WTHR 63, CLMT 31, ECZN 17, LGTM 31, ASPC 113, CPTH 418, MUSC 20, ALOC 89 (into MUSC), MSET 140 (into MUST), PWAT 29 (into ACTI), TXST 493, LSCR 208, FLST 464 |
| Crafting | RCPE 105 (into COBJ), RCCT 10 (into KYWD), INGR 1 |
| Settings | GMST 648, DOBJ 1 (overrides) |
| FNV systems | CCRD 270, CDCK 13, CSNO 5, CMNY 6, CHIP 5 (into MISC), CHAL 105, REPU 13, HUNG/DEHY/SLPD 5 each |
| Engine-held | RGDL 38, RADS 5, MICN 12, LSCT 1 |

## <a id="speed"></a>Speed

**Built:** 1 to 5 below (the asset and work caches, the Elric cache, the
process pool, the one export index, `--region`); 6 stays the rule. The spike
rebuilt its 3×3 block and Doc's house in 362 s, converting every mesh and
running Elric over all of them each time. At 7,428
distinct models, rebuilding every mesh on every run stops working. In
order of payoff:

1. **An asset cache.** Each converted mesh, material and texture is keyed
   by its source bytes' hash plus a converter version. A rebuild converts
   only what changed. The same rule as the navmesh cache: no mtimes,
   paths or worker counts in the key.
2. **An Elric cache.** Elric's physics is keyed by the pre-Elric NIF's
   bytes and Elric's version, so Elric runs only on meshes whose collision
   input changed. Today it runs once a build over every mesh.
3. **Parallel work.**
   - Mesh, texture and tree conversion run in a process pool (pure
     Python, `cpu_count() - 1` workers).
   - Elric cannot: several instances at once deadlock
     ([skeleton](#skeleton)), so its cache carries it.
4. **Read once.** One index of the export per run (the
   [import-once](../commentary/performance.md#import-once-per-run) rule),
   instead of each spike module parsing the text files itself.
5. **Stage and region scoping.** `--records-only`, `--meshes-only`, and
   `--region` (a grid rectangle) so a test build of one area takes
   seconds, not the whole map.
6. **Native code last.** numpy first (as the Skyrim mesh path did: 2.4x),
   C++ only for a measured hot loop.

## <a id="caprica"></a>Caprica ahead of FO4's compiler (built 2026-10-31)

**Why.** FO4's `PapyrusCompiler` takes about 0.25 s a script plus about
3 s per batch (300 converted scripts in 75 s; 5 in 3.4 s); memory caps the
parallel batches near 11 scripts a second, so the 17,425 converted scripts
take 25–30 minutes on a first build. Caprica v0.3.0 (Orvid King, MIT,
`external/caprica`, SHA-256 of the release 7z `0037E54C…4EE559`) compiled
the same 299 in 2.1 s serial, 0.6 s parallel.

**Equivalence (2026-10-31, 299 scripts).** Both compilers' .pex as
Champollion assembly, case, temp numbers and declaration order folded: 12
identical; the rest differ only in code generation read as equivalent:
Caprica types `None` and constants (`0.0`, not a cast of `0`), assigns
where FO4's compiler casts to the same type, drops unused temps, and its
user-flag table lists only the flags used. It writes some type names with a
lower-case first letter (`tES4Polyfill`); Papyrus names are not
case-sensitive, not yet confirmed in game.

**Differences handled (`fo4_import/base/caprica.py`):**
- Header constructs Caprica rejects are patched in a copy of F4SE, Base and
  LevelUpMenuEx (`safe_headers`, `output/fo4_cache/caprica_headers`): text
  before `Scriptname` (5 vanilla sources, `TestKevinActivationScript`), a
  struct member named `parent` (F4SE `ObjectReference.ConnectPoint`, now
  `parentNode` in the copy) and `Var x = None` parameters (F4SE
  `ScriptObject.RegisterForFurnitureEvent`). A script using what a patch
  changed fails in Caprica and falls back.
- Caprica stops at the first failing script, and its parallel mode crashes
  there (exit 0xC0000409), so it runs serial: each run's failures are
  dropped and the rest run again. What never compiles (all of it when a
  header breaks Caprica) goes to FO4's compiler, whose messages stay the
  diagnostics and the gate's (`compile_papyrus._compile_chunks`).
  `--no-caprica` runs FO4's compiler only.
- Caprica is stricter in places: `SunsetSarsparillaAddCap_1001` (a new
  event on a non-native script) fails in both.

## <a id="stability"></a>Stability

- **FormIDs never counted** ([FormIDs](fo4_spikes.md#formids)), guarded by
  a determinism test.
- **Byte-reproducible output.** The same input and converter version give
  the same plugin and meshes. Test it by building twice.
- **The spike block as the golden test.** The pipeline must first rebuild
  the played 3×3 block and Doc's house with the same FormIDs and
  records, or differences that are each explained, before it builds
  anything new.
- **Versioned caches.** A converter change that alters output bumps that
  cache's version.
- **Preflight audits** after each build, for the record links the engine
  rejects silently: missing masters, unresolved FormIDs, NAVI entries
  without a NAVM.

## <a id="order"></a>Order (reworked 2026-10-11)

**The first order (2026-10-10), and where it stands.**
1. FormIDs: built.
2. Record census and the pipeline skeleton: built, with per-type
   converters for placed bases and `--region`.
3. Goodsprings to Primm: the world is built and played. Its other two
   goals were not reached: the opening quests (VCG02, Ghost Town
   Gunfight, the road south), and frame rate and build time measured at
   region scale.
4. The whole Mojave; 5. NPCs, AI and quests; 6. engine passes: not
   started.

Of [before the pipeline](#before): 1–3 are built, and 6 partly
([climate and weathers](#weathers); not regions or water). 4, 5, 7, 8
and 9 were not started then; 3, 5, 6 and 9 are built since (see
[before](#before)).

**What happened instead.** From 2026-10-10 to 2026-10-11, each region
play-test found something in the world that didn't look or behave like
FNV's. Each was fixed before moving on: rooms and portals, ragdolls and
joints, mixed and two-sided collision, locks and keys, lights and
lighting templates, emittance, glow maps, effect animation, particles,
add-ons, land texture blending and weathers (sections above).

**What that taught.**
- Almost every fix was a general converter that the whole map needs, so
  none of it is wasted. The region turned up the mesh and record long
  tail at about one fix per kind of asset, not per cell; the whole map
  will turn up more of the same kind.
- Visual parity has no natural end. FNV's exact look (HDR bloom, warm
  display colours, dry grass) fights FO4's renderer. Each round costs a
  build and a play-test, and the last several moved the image less and
  less. Per [accept drift](fo4_drift.md), these wait in
  [parked](#parked), possibly as a player option.
- The region builds in about 180 s with meshes cached.
- NPCs, factions and quests are the census's 57 untouched types and the
  largest unknown left. The world converters are now proven at region
  scale.

**The new order.**
1. **Close the region's world** (short).
   - Measure frame rate in Goodsprings and Primm, and the build's time
     and memory.
   - The two pieces still in test (enable parents, region emittance)
     ride along with the next play-test.
   - From here on, triage each play-test finding: fix a crash, a blocker
     or anything that breaks play now; send a look that differs from FNV
     to [parked](#parked).
2. **The records NPCs and quests stand on** ([before](#before) 4, 5
   and 9):
   - persistent references and the worldspace layout;
   - FACT, CLAS, RACE, CSTY, VTYP, LVLN (with LVLC), FLST, and GLOB in
     full;
   - locations from FNV's map markers, encounter zones and ownership;
     map markers;
   - ownership on references and cells (XOWN), leveled lists' chance-none
     globals, and consumable effects (MGEF, SPEL), from the
     [audit](#audit).
3. **Real NPCs in the region.** Goodsprings' and Primm's people as their
   own records (FO4 race and head parts with the spike-2 face fit, class,
   factions, inventory, packages) in place of the stand-ins; creatures
   through the replacement table; idle markers, door navmesh links and
   patrol data ([audit](#audit)).
4. **The opening quests:** VCG02 (Sunny Smiles), Ghost Town Gunfight and
   Primm's quests. This brings quest aliases and targets in general, the
   [force greet](fo4_spikes.md#spike-1-force-greet), terminals and the
   rest of the dialogue. The region is then a playable slice from Doc's
   house to Primm.
5. **The whole Mojave:** every WastelandNV cell and interior, then the
   other worldspaces; regions and water; the worldspace map; build time
   and memory at full size; the [audit](#audit)'s world gaps (placeable
   water, mines, music zones, looping sounds, acoustic spaces).
   Placeable water and mines show in the region already and can come
   sooner.
6. **Engine passes:** terrain and object LOD (Project Mojave's terrain
   LOD as the FO4 format reference), then precombines and previs if
   step 1's frame rate says they are needed.

Steps 2–4 come before the whole map (the reverse of the first order).
This tests the remaining unknown where the world already works.
The whole-map step then carries NPCs and quests with it, rather than
converting the world twice.

## <a id="whole-map"></a>The first whole-map build (2026-10-24)

`--world WastelandNV --whole` into a scratch Data folder (`temp/whole`).
Each run stopped at one bug the region never had; all were general:

| Run | Stopped after | Cause | Fix |
|---|---|---|---|
| 1 | 2 min | the looping-activator check read a mesh not yet written | read it from the mesh cache |
| 2 | 3 min | a huge activator's bounds overflowed OBND's 16 bits | `mesh_cache.mesh_bounds` clamps |
| 3 | 44 min | a fitted skin tone went negative | `tint.scaled_tone` clamps at 0 |
| 4 | 52 min | a line lists one Choice twice: two INFOs on one key | `conversation._next` lists each once |
| 5 | 64 min | a talk scene added talks while they were built | `cell._all_talks` runs to a fixed point |
| 6 | 7 min | a merchant chest in an exterior cell made it an "interior" | `vendors.with_chests` keeps interior cells |
| 7 | 84 min | Archive2 fails on relative paths | `ba2_pack._pack` passes absolute ones |

Run 8 finished: 6,204 s; peak 15.6 GB over all processes, 12.7 GB in the
build process; 508,186 records, a 258 MB plugin, a 1.2 GB texture archive,
3.8 GB of sound (150,375 voice files), 8.1 GB in all (2.0 GB of it the
texture staging); 9,920 of 9,920 scripts compile. The other worldspaces
(the Strip, Freeside, Lucky 38 and the rest) are separate in FNV and were
not in it.

<a id="dangling-script-properties"></a>**Dangling script properties.**
FO4Edit found 1,001 unresolved references, 991 of them script properties
naming a record the build never wrote: 752 placed creatures with no FO4
base (`npcs.placed` skips them after `actor_refs` gave them an id), 191
references to talking activators that are not radio stations (REPCON,
Hidden Valley and Hoover Dam intercoms), 52 packages left out. Each
kind reserves its id before knowing the record converts.
`base/dangling_scripts.clear_dangling` runs after the plugin is written:
every VMAD object property naming this plugin's index but no record in it
becomes None, in place (the size does not change). On run 8's plugin:
957 cleared, every VMAD read, 1.4 s; FO4Edit then reports 44 (conditions
whose subject is an unbuilt actor or reference: Black Mountain radio
lines, two terminals, one package), from 1,001.

<a id="reached-worlds"></a>**`--world reached` (2026-10-25).** A whole build from the app passed
only `--world WastelandNV`. When it ran into the MO2 folder, it replaced
the 12-world deploy with WastelandNV alone (285 MB against 383), and
Westside could not be entered: its 44 doors had no worldspace to lead to.
`run.reached_worlds` names the worldspaces a build needs:
- each worldspace a load door leads into (11 worlds: WastelandNV 373
  doors, WastelandNVmini 44, TheStripWorldNew 25, GreenhouseWorld01 22,
  and others);
- each worldspace holding a reference that a script names in its SCRO
  list, on scripts or quest stages. FFEncounterWorld, the freeform
  encounters' holding pen, is reached only by its scripts' MoveTo
  (8 scripts).

TestMap01 and FXInvertedDaylightWorld are reached by nothing and are not
built. The app's whole build passes `--world WastelandNV reached`, which
yields the same 12 worldspaces as the hand-picked list below. With the
12-world build restored, Westside could be entered (played 2026-10-25).

**Every worldspace a door reaches** (WastelandNV, TheStripWorldNew,
Lucky38World, the three Freeside worlds, GamorrahWorld,
GreenhouseWorld01, TheFortWorld, BoulderCityWorld, WastelandNVmini, and
FFEncounterWorld, the freeform encounters' holding pen; not TestMap01 or
FXInvertedDaylightWorld). The first run hit a recursion: a package's
fragment script names a package that names it back, and each was written
again before the other finished; `packages.package` now takes the id
before writing. Then: 7,181 s; peak 12.9 GB (12.8 in the build process);
a 361 MB plugin, a 1.3 GB texture archive, 179,299 voice files; 13,140 of
13,140 scripts compile; 1,080 dangling properties cleared. Dialogue lines
dropped as never true (`GetIsID` on an unbuilt speaker) fell from 24,531
to 3,274, doors leading out of the build from 52 to 0, packages for an
unbuilt location from 58 to 3. Still left out: 1,036 placed creatures of
121 kinds with no FO4 base (the replacement table's gap).

**Where the time goes.** About an hour of each run is LipGenerator, once
per voice line. A voice file is skipped when it already exists, so a
rebuild into the same Data folder skips it; these runs cleared the
folder each time.

<a id="voice-cache"></a>**Voice files kept aside, not deleted (2026-10-25).** Each whole build
ran about 80,000 lines back through LipGenerator: 81,370 voice files
written and 31,972 deleted as stale in the 12-world build, and 76,981 and
65,793 in the one-world build before it. Lines keep their FormIDs (the
ledger; 98 of them counted), and two identical test-block builds showed
the skip works: 1,963 files, then 0 (694 s, then 100 s). The churn came
from scope. A line's .fuz is written for each FO4 voice type a built NPC
uses, so a build with fewer or other NPCs (one world against twelve, a
replacement table swapping NPCs for a mod's) deleted still-valid files,
and the next build to need them converted them again. `voice.remove_stale`
now moves such a file to `_ba2/VoiceCache/<plugin>/<voice type>/`,
outside what the Main BA2 packs, and `voice.restore` moves it back when a
line needs it. Build log: `voice files kept aside`, `voice files
restored`.

<a id="sound-archive"></a>**Sounds go in the Main BA2 (2026-10-24).** The
first launch of the full build sat on a black screen at 1% CPU. It was
not hung: the main thread was in `ZwCreateFile` under MO2's
`usvfs_x64.dll`, opening the loose voice files one by one in name order
(sampled from the thread's `OBJECT_ATTRIBUTES`), about 290 a second,
so roughly 10 minutes for 179,414 files. After the last one the
game went on to render. Vanilla keeps its voices in a BA2
(`Fallout4 - Voices.ba2`). The build now writes voice and sound-effect
files to the staging folder (`ba2_pack.sound_root`, `<staging>/Sound`)
and packs them as `<plugin> - Main.ba2` (`pack_sounds`; General,
uncompressed, since .fuz and .xwm are already compressed), which the game
loads with the plugin. A previous build's loose files in the plugin's own
folders (`Sound/Voice/<plugin>`, `Sound/FX/FNV`) are moved into the
staging folder first (`stage_loose_sounds`), so LipGenerator still skips them.

**The staging folder lives outside the Data folder (2026-10-29).** It held
292,898 files (9.3 GB: sounds 248,028, textures 12,897, the voice cache
31,972) inside the mod folder, all already in the two BA2s. MO2 lists
every file of an enabled mod in its virtual Data folder, so the Creation
Kit sat at "Initializing Archive" and the game's launch paid the same.
`ba2_pack.staging_root` now keeps it in `output/fo4_cache/ba2/<data folder
name>-<hash>`; an old `<data>/_ba2` moves there on the next build (or goes
when the new one exists), so a build into the mod folder leaves none.

**We write the sound archive ourselves (2026-10-29).** A sampled whole-map
build (128 min) spent 56 min in Archive2 packing the Main BA2: 248,028
files, 5.9 GB, about 1 MB/s, all per-file overhead. One added, moved or
restored voice file repacked all of it, so most rebuilds paid it.
`base/ba2_write.write_general` writes the uncompressed general archive
directly: version 8, flags `0x00100100`, the `0xBAADF00D` marker, data back
to back, then the name table, with both name hashes CRC-32 without the
starting or final inversion over the lowercase backslashed stem and folder.
On that build's sounds it gave Archive2's archive exactly (same size, all
248,028 entries and every file's bytes identical). The archive's record
(`<archive>.json`) now keeps each file's size and time, and a repack copies
the files unchanged since, in contiguous blocks, out of the previous
archive, reading only the rest from disk, 16 at a time. Measured: a first
pack from cold files 607 s (opening 248,028 files dominates); a pack with
nothing changed is skipped after listing the files (21 s). The texture
archive stays on Archive2 (DX10 chunking), and was not a measured cost.

<a id="clip-cache"></a>**FNV clips decoded once (2026-10-29).** The same
build spent about 12 min decoding FNV `.kf` clips (guns, idles, creature
rigs), most of it the B-spline basis computed one sample at a time in pure
Python. `kf_decode.basis_matrix` computes every sample's weights at once
(the same recurrence, zero-division guards and half-open base case): 45 real
clips (2,850 tracks) decode 4.7 times faster, the samples within 1.1e-13 of
before. `fo4_import/havok/kf_cache.decoded` keeps each `.kf`'s decoded clips
in the work cache by the file's bytes and the decoder's code tag, and the
last 256 in memory (one gun reads its aim clip several times); each caller
gets fresh copies, since `split_root_motion` works in place.

Measured on the same whole-map build, rebuilt with both changes (clip cache
filled during the run): 7,712 s to 2,046 s. Largest left: gun clip
retargeting (430 s, the retarget math, not decoding), placed references
(476 s), NPCs (291 s), worldspace groups (288 s).

<a id="terrain-lod"></a>**Terrain LOD from FNV's own tiles (built 2026-10-24, not yet played).**
FNV ships its terrain LOD prebuilt: per worldspace,
`meshes/landscape/lod/<world>/<world>.level<L>.x<X>.y<Y>.nif` (1,360 for
WastelandNV: 1,024 level-4, 256 level-8, 64 level-16, 16 level-32, the
whole 128 by 128 cells from (-64, -64)) and a diffuse and normal map per
tile. FO4's layout, read from vanilla (`Fallout4 - Meshes.ba2`) and
Project Mojave:
- `Meshes/Terrain/<world>/<world>.<L>.<X>.<Y>.btr`, named by the tile's
  south-west cell as FNV's are. One `BSMultiBoundNode` "chunk", one
  `BSTriShape` "Land" with scale L and positions in tile units (world / L),
  vertex layout `0x300000000203` (half position, UV; no normals, as FNV's
  tiles have none), shader type 18 (LOD land), a `BSMultiBoundAABB` in
  world units. Commonwealth tiles add a `WATER` shape; Mojave's do not.
- `Textures/Terrain/<world>/<world>.<L>.<X>.<Y>.dds` and `_msn.dds`.
- `LODSettings/<world>.lod`, 16 bytes: south-west cell (two int16), size
  in cells, lowest and highest level (Commonwealth -96, -96, 256, 4, 32;
  Mojave -50, -50, 128, 4, 32).
- The WRLD record needs nothing for it: Mojave's has no field ours lacks
  but `MHDT` and `ICON`.

`spike/terrain_lod.py` converts each tile's land shape (its largest; a
second 3-triangle shape some tiles carry is dropped). FNV's UVs run
mirrored (u = 1 - x, v = y; FO4's u = x, v = 1 - y). Each FNV tile holds
two shapes: the land (a shaded NiTriShape with UVs) and its LOD water (a
BSSegmentedTriShape with no properties: Lake Mead flat at 2600, the
Colorado at -2300). Taking the larger shape picked the water on 17 tiles
around Lake Mead and Hoover Dam (x 12 to 28; e.g. 4.28.12: water 3,825
vertices, land 1,773), drawn with the land texture; through the holes it
left, the tile skirts (edge vertices dropped to -14098, on every FNV
tile) showed as grey walls from The Fort. `land_shape` now takes the
shaded shape. That alone left The Fort's view unchanged: the land shapes
carry skirts too, each border vertex repeated at -14098 (FO4's tiles,
vanilla's and xLODGen's, have none), and where FO4 lowers or hides a
neighbour they stand as walls. `without_skirts` drops every triangle
touching a border vertex that lies under another at the same x, y (4.20.8:
4,207 to 4,044 triangles, lowest vertex -14098 to 2600). The water shapes are not converted yet (FO4's tiles carry a
`WATER` BSSubIndexTriShape); FNV's land under the lake is flattened to
its surface with a lake-coloured diffuse, so it stands in. The
dark rectangles in the tiles east of The Fort are the Legion tents'
footprints baked into FNV's LOD diffuse, which FNV's object LOD covers. The
first play-test (FNV's UVs and textures kept as they were) showed the LOD
dark blue and pushing through the land near the player. FO4 reads a tile's
normal map by name (`Data\Textures\Terrain\%s\%s.%u.%i.%i_msn.DDS` in
Fallout4.exe), not only through the mesh, so both textures now turn half a
turn into FO4's layout and the UVs follow (u = x, v = 1 - y, checked on
every vertex); a model-space normal does not change when its image turns.
Not yet played. FO4 lowers LOD land under loaded cells in its shader
(`fLODLandDropAmount`); the heights need nothing: both FNV's and Project
Mojave's level-4 tiles sit exactly on their land (median difference 0). Both normal maps are model space;
correlating each texel with its triangle's face normal on one tile per
game showed FNV stores x, y, z in R, G, B (blue the up axis, mean 0.81)
and FO4 x, z, y (green up, mean 0.90; blue follows y), so the normal map's
green and blue swap. Textures go through `stage_texture` into the texture
BA2; the meshes are loose. A full WastelandNV run takes 97 s cold (most of
it the 1,360 normal maps through texconv); the meshes are work-cached and
the textures skipped while staged and current. The first every-world build
after this stopped on Lucky38World: 6 of its 135 tile meshes have no
textures (level 4, x-16 y-12 among them). `tiles` now leaves out a tile
missing its diffuse or normal map; every other world keeps all its tiles.

<a id="imposters"></a>**FNV's imposters are left out (built 2026-10-24, not yet played).**
Playing the whole map showed grey, low-detail copies of the Freeside
overpass and the Strip wall standing over the real ones at the North Gate
(`OverpassRampLo01Imposter01`, `NVStripWallImposter*`, textured with
`McCarranWall_Imposter.dds`). FNV places 216 such references in
WastelandNV (210 persistent) beside the real objects, and shows each only
from inside a region that lists it: region data type 8 (Imposter), an
`RDID` list of references, in 18 regions naming 290 references
(`StripImposter` 222, `StripImposterBlackMountain` 195,
`StripImposterJacobstown` 190, the Freeside worlds' 3 to 9 each). That is
how the Strip's skyline shows from Black Mountain without doubling up
close. FO4 has no region-gated references, so `regions.imposters()` reads
the lists from FalloutNV.esm and `Exterior` leaves those references out;
the distant skyline is object LOD's job.

<a id="outfit-slots"></a>**One item per slot in an outfit (built 2026-10-25, not yet played).**
Red Lucy wore FO4's sleepwear stand-in: her FNV inventory holds both
`BountyHunterDuster` (DT 6, value 70) and `OutfitPrewarNegligee` ("Sexy
Sleepwear", DT 0, value 6), both upper body (BipedFlags 4). FNV equips the
better one; her script changes her for the bedroom scene. `_inventory` put
every wearable into the FO4 outfit, and FO4 equipped the sleepwear.
193 of 2,303 outfits had two items on one slot (Joana and Martina
Groesbeck the same sleepwear; dirty and clean business wear; the two
Centurion armors). `NPCs._dressed` now keeps, per biped slot, the armor
with the best rating, then value, as FNV does; the rest are carried, so
scripts can still equip them. Leveled lists stay in the outfit.

<a id="collision-nodes"></a>**Collision nodes keep their transform (fixed 2026-10-25, the pipe played).** In the
East Central Sewers the player fell through a walkable pipe
(`utlbaycorintalltoppuritypipe.nif`, 00169FD5). Its collision sits on a
child node with no render children, `LPipe1Way02` at x -128.
`elric.graft` reset such collision-only nodes to identity, on the theory
that Elric bakes the node transform into the physics. It does not: Elric
keeps the node's transform, writes the body's vertices local to it, and
copies the node's translation and rotation into the body position, which
FO4 ignores (vanilla `pgaragetoprail1x1str01.nif`: only node × vertices
fits the render shape). So the reset moved the pipe's collision 128 units
to the side. Restoring the node's translation in the deployed mesh let the
player walk inside (played 2026-10-25). The Goodsprings fence collection
(`Havok0`… up to 2,000 units out, rotated) comes out of Elric in exactly
the same layout, so the graft now keeps every node's transform.
`tools/nif/fo4_collision_audit.shipped_parts` placed vertices by the node
and the body position together, which matched FNV only because of the
reset; it now uses the node alone. The SCOL walls that stayed after the
reset until the collections were split into parts
([spike 4](fo4_spikes.md#spike-4-exterior)) fit the same cause.

<a id="stair-helper-pitch"></a>**Stair helpers at the flight's pitch (built 2026-10-25, not yet played).** The player
stuck about 70% up The Thorn's catwalk stairs (`utlcatstairsfull01.nif`,
00133C33): 16 risers of 24 over 24 (45°), then a last step of 8 onto the
landing. The stair-helper slab ([stair ramps](fo4_spikes.md#stair-ramps))
ran through the first and last nosings, so the short last step tilted it
to 43.8° and each nosing stood about 1 unit higher above it per step (10.9
at step 11, 14.9 at step 15); the character riding the slab met them. FNV
has no helper. `stairs._ramp` now takes the median step's rise over run,
lifts the slab so no nosing stands above it, and spans the widest step
edge (the treads ran 8 past the first step's edge on each side). The Novac
motel's stairs are a plain 38° collision ramp behind a plain 16-unit riser,
with no treads for the pass to find; the stuck spot there is not pinned
down.

<a id="stairs-audit"></a>**Stairs audit (tool, 2026-10-25).** `tools/nif/stairs_audit.py` runs
every FNV mesh's collision through the stairs pass and ranks by placements
three kinds of step FO4's character may refuse:
- **Open foot:** a flight whose ramp foot stands more than 32 units above
  the mesh's lowest point. The flight's first steps belong to another
  reference, as with `utlcatstairshalftop` (foot 48, the small Thorn stairs
  09133bb8). The working `utlcatstairsfull01` ends one 26.3-unit floor
  step up (played).
- **Tall risers:** a plain step 16 to 28 units tall that the pass left
  unmarked. It is an upright face whose top meets a walkable face (a tread,
  or a ramp up to 50°) with no stairs material, and whose bottom meets a
  walkable face or the ground. Novac's motel and houses lead this list (the
  motel's 16-unit riser in front of its 38° ramp).
- **Over max:** the same, 28 to 40 units tall: ledges, or steps too tall.

Trial on `architecture/novac` and `dungeons/utility/catwalks` (69 meshes
with mesh collision): 7 with an open foot, 33 with tall risers, 16 over
max. A working flight can still show a riser or two where its top or
bottom step leaves the pass's pairing, so the list is for triage, not a
defect count. It runs in the overnight script after the build
(`temp/overnight/stairs_audit.txt`).

<a id="open-foot"></a>**Helper slabs reach the floor (built 2026-10-25, not yet played).** The
small Thorn stairs (09133bb8, `utlcatstairshalftop`) could not be climbed
at all. Their lowest tread stands 48 above the body's lowest point, with a
22-unit first riser off the catwalk base. The helper slab started at that
tread, out of the character's reach. Vanilla's helper slabs run down into
the floor. `stairs._foot` now starts a flight's slab at the body's lowest
point, at the flight's pitch, so it rises out of the floor where the
flight begins. The exception is a lowest tread that is a landing (a tread
at its level still beyond its edge by 48): that flight starts from its
landing, as the upper hotel and office hall flights do. The whole-export
audit before the change: 52 meshes with an open foot (176 placements);
after, 21 (92), each a flight off a landing. Played 2026-10-25: the small
Thorn stairs still could not be climbed. The user's ID, 09133bb8, is a
bay wall (`UtlBayWallMidTR01`). Its collision and that of every piece
around it match FNV's boxes, and the shipped half-top's helper runs from
-164 to the landing, so its foot was not the cause.

<a id="short-flights"></a>**Two-step runs get a helper (built 2026-10-25; the small Thorn stairs played).** Beside
the half-top, the catwalk turn `UtlCatStairsTurnHalfL01` (00133C2B) climbs
two runs of two 24-unit steps with a landing between them. Flights needed
three steps, so neither run had a helper. Without one, FO4's character
does not climb 24-unit steps (the big Thorn stairs before theirs). A run
of two now gets a helper when both steps rise at least 16, the height FO4
refuses as a plain step. Census over every FNV mesh:
- With two-step runs allowed, 102 meshes (318 placements) gain helpers.
  Most are catwalk turn, half and end pieces, step-downs and wooden steps.
- The 16-unit floor leaves out the display cases (a 22 step, then an
  8 lip).
- It keeps the ruined slide's ladder steps (22 to 24) and the train
  station bench (15 and 18, within 1 unit of 16).

<a id="glass-texture"></a>**Textured glass at full strength (built 2026-10-25; Madrid played).** FNV glass
converts to vanilla's beaker BGEM, whose base colour is a dark grey (0.18,
0.19, 0.20) at scale 0.2: it multiplies FNV's glass texture (the Madrid
building's dirty `apartmentpre01gla.dds`, 63% alpha) to near black, and
the windows read as empty. With base colour white at scale 1 the Madrid
glass looked right in game (2026-10-25). `_effect` now keeps the beaker's
tint only for glass with no texture of its own.

<a id="falloff-panes"></a>**Black window panes (built 2026-10-25, not yet played).** FNV fills a
broken shop window with an untextured, black, blended unlit pane whose
view falloff makes it opaque face-on (`BldgCorner04_NV:5`: vertex colour
0.03, falloff 1.0 / 0 / 1.0 / 0): pure black behind the shards, the wires
in front (FNV screenshot, 2026-10-25). Converted as an untextured effect
shader with the same falloff, it vanished face-on; with the falloff
cleared it showed a see-through tint. Every vanilla effect shader with
falloff (a sample of 8,000 meshes) has a source texture, the same values
included (`lightoillampon.nif`: 1.0, 0, 1.0, 0). An untextured unlit shape
with falloff now draws through vanilla's `textures\shared\flatwhite01_d.dds`
(alpha 1). Played 2026-10-25: no change, still a see-through tint. The
pane over the hole (`BldgCorner01_NVs01:5`) blends by vertex alpha (mean
0.34, flagged in FNV too), so FNV draws the same partial pane; its black
is the room behind, which FNV leaves unlit and FO4 lights with the
exterior's ambient. Recorded as drift, not converted further.

<a id="black-fill"></a>**Black fills as vanilla's black flat (built 2026-10-25; played).** The
drift note above was wrong. The black box (`BldgCorner04_NV:5`) is an
unlit, untextured, blended shape whose every vertex and material alpha
is 1 (vertex colour at most 0.19), so FNV's blend never shows through.
FO4 drew it see-through as a blended effect shader; dropping the alpha
property and turning on depth writes did not help either (played
2026-10-25). Vanilla fills such holes with a lit opaque shape on
`materials\shared\black flat.bgsm` (`hitextawindowadmg01black.nif`, the
`hitextskylight*black` meshes: flags 0x80400000 / 0x1, no alpha
property). With that material the box drew solid black (played
2026-10-25). `convert_static.black_fill` now picks every such FNV shape:
unlit, untextured, blended, all alpha 1, vertex colours at most 0.25.
It points at vanilla's material, so no BGSM of ours is written. Census of
14,909 FNV meshes: 6 blended unlit opaque shapes at 0.22 or darker
(`bldgcorner04_nv`, `apartmentpre02`, `bld03stairs01`, `offrmfreecol03`,
`offrmpipes03ralt`, plus `workbenchmarker`'s editor marker). The next
brightest are mist, smoke and bubble effects, from 0.31 up, which stay
effect shaders.

<a id="overlay-layers"></a>**Grime and plaster layers as decals (built 2026-10-24, not yet
played).** Westside row houses (`rowhousebasebred01_nv`, `rowhouse02_nv`)
showed black with orange flecks, and the Madrid building
(`apartmentpre01`) a wrongly coloured, Z-fighting concrete layer. FNV
lays a lit, alpha-blended grime shell (`ApartmentPre01dcl.dds`, 80% of it
clear) over the building's own walls. It is not flat, so
`overlay_sheet` passed it over, and being mostly see-through it went to
the insect-wing BGEM (`_translucent`), which drew it dark. Hiding that
shape in game showed the walls right (played 2026-10-24).
`convert_static.overlay_layers` now marks a blended lit shape whose area
lies on the mesh's opaque triangles (at least half of it within 4 units,
measured at triangle centres, projection inside a triangle) as a layer,
converted as a decal: a BGSM with FO4's decal flags, blended. Measured:
the three grime shells 1.0, 0.91 and 0.99 of their area within 4 units;
free-standing blended shapes 0 (an NCR flag; the building's own glass,
`ApartmentPre01c`) and 0.03 (REPCONN's pod window glass).

<a id="wall-lean"></a>**Wall leans face the wall (built 2026-10-24, not yet played).** NPCs
leaned on air facing the wall (Freeside, 001381D2 and others). All 352
FNV wall leans use FURN `WallMarker`: one marker, heading 0, slot 19
(wall lean), at the spot the actor walks up to, facing the wall (its
EditorMarker sits at y +41). FNV's `wallfrontentry.kf` then moves the
actor 31.2 units forward and turns it 180° onto the wall. FO4's
`NPCInvWallLean01` (449 vanilla references) has no enter offset: the
actor leans at the marker, facing its heading. Wall-lean furniture now
moves and turns its markers by that enter motion, as stools and floor
seats already did (`furniture.entered`): `FNV_WallMarker`'s marker
becomes (0, 31.2, 0, 180°). Only the FURN record changes.

<a id="rest-alpha"></a>**Effects hidden at rest (built 2026-10-24, not yet played).** The
Freeside North Gate showed a permanent electric web: its load door's mesh
is `forcefieldrightimpact01.nif`, whose two unlit shapes have
`NiMaterialProperty` alpha 0. FNV keeps them invisible until a sequence's
NiAlphaController flashes them (0 → 1 → 0 in 0.433 s, when touched). The
unlit conversion wrote base colour alpha 1.0 and never read the material
alpha, so the effect showed all the time. `_unlit` now carries the
material alpha into the effect shader's base colour alpha (the variable
the converted NiAlphaController drives). 26 FNV meshes have an alpha-0
shape, used by 62 DOOR, ACTI and STAT records: the force-field impact and
glow meshes, vault gear doors, the Lucky 38 lights, the Freeside welcome
sign. The material's emissive tint (the field's cyan) is still dropped.

<a id="old-texturing"></a>**Shapes textured the old way (built 2026-10-24, not yet played).** A
purple part on the East Central Sewers' door (`utldoor01.nif`) and on a
rubble pile (`utlrubblepilereg01.nif`): FNV shades some visible shapes
with a Gamebryo `NiTexturingProperty` (base texture) and no BS shader
(`UtlDoor01:12`; the pile's four `debris` shapes). They were converted,
but only a BS shader's texture set was read, so they got the untextured
material and FO4 drew them purple. `_material` now takes the
NiTexturingProperty's base texture as the diffuse. (The door's other two
shader-less shapes, `door_temp10` and `Object281`, carry FNV's hidden
flag and were already left out.)

<a id="world-map"></a>**The Pip-Boy world map (built 2026-10-24, not yet played).** The
Pip-Boy showed the Commonwealth's map with FNV's markers, Freeside East
Gate at its very top. FO4's WRLD names its map image in `ICON`
(`Interface\Pip-Boy\WorldMap_d.dds`, 2048 by 2048, BC1) and its cell
bounds in `MNAM` (two int32 zeros, then the north-west and south-east cell
as int16: -33, 25 and 28, -36). The WRLD copied both from the Commonwealth.
FNV's WastelandNV has its own: `interface\worldmap\wasteland_nv_1024_no_map.dds`
and cells -35, 35 to 25, -25. `exterior._world_map` writes FNV's (the
image staged into the texture BA2 under `fnv\`). Only WastelandNV has a
map in FNV; Freeside, the Strip and the rest use their parent world's, not
converted yet.

**Run it inside a build, not alone.** `pack_textures` deletes every staged
`fnv/` texture the current run did not write, which is right for a build
but wrong for a run that only wrote terrain LOD. Writing LOD into the
deployed folder by hand and then packing pruned 7,347 of its 7,437
textures; they came back from the build folder, copied in as loose files,
which the packer moves and keeps.

## <a id="parked"></a>Parked

Found and deliberately left for later. Each needs its own look, not a
quick fix.

| Item | State | Where |
|---|---|---|
| Overall warmth: FO4's tone curve and LUT against FNV's clipped display colours | Not measured; a candidate player option ("FNV look") | [color drift](#color-drift) |
| FNV's weather imagespace modifier: the amber tint (`NVWastelandIS`, 39%) and brightness × 1.3 | Values read; not converted | [weathers](#weathers) |
| Region weathers: Goodsprings' thicker fog (`NVWastelandGS`) | Built 2026-10-19, played 2026-10-21 | [region weather](#region-weather) |
| Grass reads green, FNV's dry yellow | Not measured | [color drift](#color-drift) |
| Bright dirt road | Re-check now that the weathers are FNV's | [color drift](#color-drift) |
| Bright lamps blown out (the Goodsprings lantern) | FNV multiplies an emissive shape by 15 with HDR on (`0xBC6FE0`) and then clips; FO4 blooms the same energy. A rescale was tried and reverted. Tied to the tone question | [emittance](#emittance) |
| Last land seams: soft edges, the road near the graveyard fading more than FNV's | 67 shared vertices have no common texture | [land seams](fo4_spikes.md#spike-4-exterior) |
| FNV's HDR imagespace fields (skin dimmer, target luminance, bloom alphas) | Dropped | [drift](fo4_drift.md) |
| Bear trap's trigger volume (Havok phantom) | Left out; base and jaws collide | [region](#region) |
| Damage stages (car fires) and smoke add-ons with no FO4 namesake | Left out | [add-ons](#addons) |
| NPCs catch on steps (Vikki and Vance's front steps, about 30 s, 2 of 6) | Lead: FNV's stepped collision against FO4's ramped stairs; not measured | [packages](#packages) |
| The saloon's night windows read flat yellow | FNV's own colour (1, 0.98, 0.29) × 3; total glow within vanilla windows' 0.05–0.26, so no global rescale | [glow](#glow) |
| Placed guns lie wrong (the store's .22 stands on its grip) | FNV's reference rotation fits FNV's model, not the FO4 gun built in its place | [guns](fo4_spikes.md#spike-4-guns) |
| FNV's guns on FO4 receivers; creatures with no FO4 rig | The replacement table and the modlist | [guns](fo4_spikes.md#spike-4-guns), [replacements](fo4_replacements.md) |
| Terminal Alternate Colors; FNV's 2 sound notes | Accepted drift ([fo4_drift.md](fo4_drift.md#recorded)). The hum stays out: TERM's Looping Sound crashed the game on load (2026-10-30). If wanted: a sound marker per terminal | [terminals](#terminals) |

<a id="f3nv-names"></a>**Names (2026-10-23).** The Fallout 4 build's own names
dropped the inherited "TES4":
- The 32 static scripts in `script_convert/static_scripts/fallout4/` are
  `F3NV_*` (they were `TES4_*`). The shared converter's names stay:
  `TES4Polyfill`, the top-level `TES4_*` scripts and their `overrides/`
  copies, since the Skyrim converter emits them too.
- The helper plugin is `FalloutHelpers.esl` (was `TES4Helpers.esl`); its
  object ids are unchanged.
- The F4SE plugin is `F3NV.dll`, logging to `F3NV.log` (was
  `FalloutCondition.dll`).
- The built plugin is `FalloutNV.esm` since 2026-10-30 ([layout](fo4_plugin_layout.md#layout)); it was
  `FalloutNV.esp`, and `FNVCellSpike.esp` before that. Its
  ledger, voice and FaceGen folders are named after it, so they moved to
  the new name with it. Measured on the first renamed build: all 43,002
  records and the helper's 30 kept their FormIDs.

The CK's FaceGen heads name the plugin in their face texture paths
(`FaceCustomization\<plugin>\`), so the rename left 167 heads pointing at the old
folder and the faces drew purple. They were repointed in place (a one-off);
a fresh CK FaceGen export writes the new name.

A rebuild deletes the old copies a mod folder still holds:
- `F4SE\Plugins\FalloutCondition.dll`, by `condition.LEGACY_PLUGIN`;
- each `Scripts` `.pex` with no source left, the old `TES4_` names among
  them (the compile step's own cleanup: 32 in the first renamed build).

Existing saves don't carry over: a save names its plugins, and the
scripts on its running quests.
