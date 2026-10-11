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
| `record`, as a static stand-in (`STATIC_STAND_INS`) | BOOK, KEYM, NOTE, TERM, IDLM |
| `pickup` (the FO4 item, else a static) | ALCH, AMMO, WEAP, ARMO |
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
- **Left out:** colliders (one mesh in the region).
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

Census of the region's 1,630 meshes' Havok blocks: MOPP/packed strips
941, rigid bodies 928 (+503 T), convex vertices 360, boxes 111, lists 27,
capsules 14, convex transforms 11, spheres 4, constraints 26, phantom and
transform shape 1 each.

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

## <a id="order"></a>Order

1. FormIDs. **Built.**
2. Record census (**built**), then the pipeline skeleton (**built**, [skeleton](#skeleton)):
   - built: the export read once, the mesh and Elric caches, meshes
     converted on every core, scripts compiled only when changed; it
     rebuilds the spike block byte for byte;
   - left: converters per record type dispatched from `record_routes`
     (the spike's code runs as it was), and a region scope (`--region`).
3. **Goodsprings to Primm:** the first region, a few hundred cells
   (**built**, [region](#region)).
   - Brings in the opening quests (VCG02's wells, Ghost Town Gunfight,
     the road south) and the exterior navmesh (**built**,
     [exterior navmesh](#exterior-navmesh)).
   - Measures frame rate and build time at region scale.
4. The whole Mojave, then the other worldspaces and every interior.
5. NPCs, AI and quests across it, starting with Sunny Smiles and VCG02.
6. Engine passes: LOD, then precombines and previs if
   [performance](#before) needs them.
