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
py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FNVCellSpike.esp --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV --around -18 0 --radius 1 GSDocMitchellHouse
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
  - Each copy carries the `TES4_SayOnce` script (properties: the marker
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
player read it). Its Pip-Boy Tabs page on STAT (`spike/karma_page.py`)
has two rows, actor values `TES4_KarmaPage` sets on the player each time
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
globals here have no Pip-Boy page yet.

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
  race and sex (`BODIES`: DocWeathers, DoctorAmari, the ghouls Jones and
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
    `TES4_ScriptPackages` script. Collection aliases use vanilla's layout
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
- <a id="combat-styles"></a>**Combat styles (built 2026-10-19, not yet
  played).** Converted NPCs are copies of four vanilla bodies with no ZNAM,
  so every one fought with the engine's default style, which weighs
  melee and guns alike (`DefaultCombatStyle`, Equipment Score Mult 1.0
  each). FNV and FO4 CSTY share almost no fields (FNV: dodge, block and
  attack chances, cover search, combat radius, weapon restriction; FO4:
  offensive and defensive mults, equipment score mults, close and long
  range behavior), so an FNV style maps to a vanilla one by its authored
  Weapon Restrictions (`npcs.COMBAT_STYLES`): Ranged Only to
  `csRaiderRanged` (Fallout4.esm's commonest human style, 242 NPCs;
  ranged 10, melee 1), Melee Only to `csRaider01Melee` (59; melee 10,
  ranged 0.01). None (52 of FNV's 84 styles) keeps the default. ZNAM is a
  traits part in FNV (xEdit hides it under Use Traits), so it comes from
  the traits source and goes before NAM5, where all 1,745 vanilla ZNAMs
  sit. FNV-wide 1,485 of 3,816 NPCs set a style: 933 Ranged Only, 25
  Melee Only; in the region 81 NPCs take `csRaiderRanged`, none is Melee
  Only. Dropped (drift): FNV's combat radius (2,000 for NCR
  troopers, 6,000 for faction squads), cover chances and flee flags.
  Package-level combat styles (FNV PACK CNAM) are not exported, so not
  carried.
- <a id="door-closer"></a>**Doors close behind NPCs (built and played
  2026-10-17).** FNV closes a door after the NPC who opened it walks
  through; FO4 leaves it open. In the Bison Steve a convict's patrol runs
  through the double door into the deputy's room (markers at (1432, −4276)
  and (783, −4217), the door at (1024, −4224)), so the room stood open.
  Every DOOR base now carries `TES4_DoorCloser` beside its own script: an
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
- One that is not built is dropped, so its child stays enabled.
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
not a true equivalent. A skill book instead runs `TES4_SkillBook`
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
  (Requires Key: 255) and Leveled (`0x4`). FO4's hacking needs the Hacker
  perk per level where FNV needed Science 25 per level. Password notes
  (PNAM) are not keys yet: FO4's are KEYMs.
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
the note's FormID. A script's AddNote of a voice note still declares a
`Book` property, which a holotape cannot fill (attach.py fills items by
`Book`, not `Holotape`).

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
  mode; an effect needing it is left out). HasPerk is written as FO4's on
  the effect, on the perk's first rank (2026-10-21: 129 tests in the region;
  a perk the build lacks counts as not held). See
  [perks](fo4_perks.md#hasperk).
- An item left with no effect carries `FortifyHealth` at magnitude 0 and
  duration 0, as vanilla's `VRWorkshopShared_MutfruitFake` (and
  `HC_SippableWater`, `DamageRadiationChem` at 0). xEdit requires one
  effect and reports an empty list as a NULL MGEF; vanilla leaves the list
  empty only on its two survival status potions, never on an item.
- Drift ([drift](fo4_drift.md#recorded)): Hardcore needs, addiction
  (FNV's `UMON` usage monitor and withdrawal spells), weapon poisons,
  Damage Threshold, critical chance, Rebound, Cateye, and the script-only
  effects (Fixer, antivenom, Steady, Super Stimpak's after-effect, repair
  kit, Stealth Boy's stop-combat).
- Region build (Goodsprings to Primm, 125 consumables): effect kinds
  dropped 44 → 20 (34 drops, all drift: 10 `UMON`, 11 on weapon
  poisons); consumables with no effect 31 → 11, now carrying the zero
  placeholder; 47 consumables changed; 6 MGEF copies added (Hydra), no
  FormID moved; FO4Edit 31 errors → 0.

## <a id="before"></a>Before the pipeline: build and research

In order. **Built** marks what is done.

1. **Stable FormIDs.** **Built 2026-10-10** ([FormIDs](fo4_spikes.md#formids)):
   - FNV's own ids for one-to-one records;
   - hashed ids for generated ones;
   - FalloutNV.esm's source ids reserved first, as the Skyrim pipeline
     does, so the hashed window (0x180000 to 0xF00000) is the one the
     pipeline will use.
2. **Record coverage census.** **Built 2026-10-10** ([census](#census)).
3. **Exterior navmesh across cells.** The spike converts one interior
   cell's navmesh. Exteriors need FNV's authored edge links (NVEX) carried
   into FO4's NVNM, and NAVI entries for every navmesh. The parsing is
   already in `navm_falloutnv.py`; FO4's edge-link and NAVI layout still
   needs to be read out of xEdit's definitions.
4. **Persistent references and the worldspace layout.** FO4's persistent
   cell, cell blocks and sub-blocks at full size, and which references
   must stay persistent (quest aliases, doors, map markers, enable
   parents).
5. **Map markers, locations, encounter zones.**
   - FO4 quests and aliases lean on LCTN records; FNV has none.
   - Design location records from FNV's map markers, encounter zones
     (ECZN) and interior ownership.
   - Also the worldspace map: the CK `-MapMaker` switch, or FNV's map art.
6. **Regions, climate, weather, water.** REGN, CLMT, WTHR, WATR conversion.
   The spike borrows the Commonwealth's.
7. **Performance without precombines.** Measure frame rate in the densest
   FNV areas once they exist (Freeside, the Strip, Novac), before deciding
   whether the precombine/previs stage is needed for the first release.
   FNV's world is sparser than the Commonwealth.
8. **LOD.** Terrain through xLODGen (FO4 supported) or our own terrain LOD
   generator with an FO4 BTR writer; object LOD from FNV's own LOD meshes
   ([fnv-to-fo4](research/fo4_target.md#fnv-to-fo4) renamed them).
9. **NPCs in general.** Real FNV NPCs, not stand-ins:
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

- **Switch.** `TES4Trace`, a global in TES4Helpers.esl (object id 0xA01),
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
- *Player-hit trace on old saves.* `TES4_NewGamePlayer` on the new game
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
  23).

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
| NPCs and AI | FACT 682, CLAS 74, RACE 22, CSTY 84, VTYP 100, LVLN 365, LVLC 343 (into LVLN), IDLE 1,597, ANIO 152, BPTD 49, HDPT 61, TACT 87 |
| Combat and effects | PROJ 95, EXPL 154, IPCT 125, IPDS 60, ENCH 145, EFSH 35, DEBR 6, ADDN 37, CAMS 276, PGRE 174, AMEF 54 (into OMOD), IMOD 50 (into OMOD) |
| World | REGN 276, WTHR 63, CLMT 31, ECZN 17, LGTM 31, ASPC 113, CPTH 418, MUSC 20, ALOC 89 (into MUSC), MSET 140 (into MUST), PWAT 29 (into ACTI), TXST 493, LSCR 208, FLST 464 |
| Crafting | RCPE 105 (into COBJ), RCCT 10 (into KYWD), INGR 1 |
| Settings | GMST 648, DOBJ 1 (overrides) |
| FNV systems | CCRD 270, CDCK 13, CSNO 5, CMNY 6, CHIP 5 (into MISC), CHAL 105, REPU 13, HUNG/DEHY/SLPD 5 each |
| Engine-held | RGDL 38, RADS 5, MICN 12, LSCT 1 |

## <a id="speed"></a>Speed

The spike rebuilds its 3×3 block and Doc's house in 362 s, converting
every mesh and running Elric over all of them each time. At 7,428
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
and 9 are not started.

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
| Terminal hum (FNV TERM looping sound) and Alternate Colors; FNV's 2 sound notes | Accepted drift ([fo4_drift.md](fo4_drift.md#recorded)). If wanted: write TERM's looping sound and test FO4 plays it, else a sound marker per terminal | [terminals](#terminals) |
