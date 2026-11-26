# Plan: our own Fallout 4 terrain LOD, better than vanilla (2026-11-12, refreshed 2026-11-26)

Status: Phase 0 built. Phases 1 and 2 and Phase 3's normal map built and
measured offline (2026-11-26), behind `F3NV_TERRAIN_FROM_LAND=1`, not
played. Phase 3's diffuse and Phases 5 and 6 planned. Status lives in
[ROADMAP.md](ROADMAP.md).
Research behind it: [LOD research](research/fo4_lod_research.md).
Replaces the converted FNV tiles in [terrain LOD](fo4_pipeline.md#terrain-lod).

**Goal.** Distant land with no gaps between tiles, built the way FO4's own
LOD is built, from the land itself rather than from FNV's prebuilt tiles,
with a little more detail and texture than vanilla, and showing mods' land
edits. Fancier versions (dynamic LOD, terrain shadow heightmaps, higher
presets) can come later on the same code.

**Why not keep FNV's tiles.** They share no edge points (gaps up to 1,968
units, [measured](research/fo4_lod_research.md#gaps)), carry 256² textures
baked by FNV's own renderer, and never change when a mod reshapes the land.
Building from LAND fixes the edges by construction and lets us pick the
budget.

## <a id="target"></a>What we build, against vanilla

| | Vanilla Commonwealth | FNV tiles today | Ours |
|---|---|---|---|
| Source | the CK, from LAND | FNV's prebuilt tiles | LAND (FNV's VHGT, VCLR and texture layers) |
| Surface triangles per tile | about 1,900 to 2,000 at every level (4.0.0: 3,880) | about 1,500 at levels 4 and 8, 2,000 at 16 | about 3,800 at level 4, 2,950 above (measured) |
| Tile edges | unmatched (13 to 22 irregular points a side), skirts over them | unmatched, vanilla-depth skirts (Phase 0) | same points on both sides at every level, skirts as vanilla |
| Cell borders inside a level-4 tile | not kept (1 to 6 points on an inner cell line) | not kept | not kept |
| Skirts | 1,000 units per level step (1,000 to 4,000) | as vanilla (Phase 0) | as vanilla |
| Diffuse | 512² BC3 | 256², FNV's bake, BC1 | 1,024² at level 4, 512² above (Phase 3, planned); FNV's until then |
| Normal map (`_msn`) | 512² BC3 | 256², FNV's, BC1 | 512² from VHGT at every level, BC1 (built) |
| Water | `WATER` node, segmented at level 4 | `WATER` node from FNV's water shapes, 16 cell segments at level 4 ([distant water](fo4_pipeline.md#distant-water)) | the same, carried over from FNV's tile |

Rough size for WastelandNV's 1,360 tiles, with mipmaps: level 4's 1,024
tiles at 1,024² diffuse and 512² normal map come to about 1.7 GB in BC3
(about 1 GB with a BC1 diffuse); the 336 higher tiles at 512² about
0.25 GB. Vanilla's 2,304 level-4 tiles take about 1.6 GB. Measured so far:
a 512² BC1 normal map with mips is 170 KB, 231 MB for the world (FNV's
256² ones: 43 KB). Frame time and video memory still to be measured in
game before the diffuse size is fixed ([checks](#checks)).

## <a id="refresh"></a>What the code changed since 2026-11-12

Checked against the code on 2026-11-26:

- **Tiles in world coordinates.** Fallout 3's `washmontop` authors its
  tiles in world coordinates; `tile_origin` takes the corner off
  ([world frame](fo4_pipeline.md#terrain-lod-world-frame)). Tiles from
  LAND are built in the tile's own frame, so this stays only on the FNV
  tile path and on the water read from FNV's tiles.
- **Distant water is built** (`WATER` node, level 4 cut into 16 cell
  segments). LAND has no water mesh, so a LAND-built tile carries the FNV
  tile's water (`land_btr` reads it). A world with no FNV tiles has no
  distant water yet (Phase 5).
- **Fallout 3's 15 LOD worlds** go through the same code: 14 in the tile
  frame, `washmontop` in world coordinates. Phase 1 reads any world's LAND
  the same way, so none needs its own path.
- **Object LOD trims against the `.btr`** and its run's cache key includes
  the worldspace's `.btr` ([object LOD](fo4_pipeline.md#object-lod)), so
  switching to LAND tiles re-bakes object LOD once. The masters' LOD meshes
  are staged before the run
  ([master meshes](fo4_pipeline.md#object-lod-masters)); Phase 5's bake
  needs the same.
- **Tree LOD** is object LOD (cards and `_lod.nif` through LODGen,
  [tree LOD](fo4_pipeline.md#tree-lod)); nothing here touches it.
- **`LODSettings` grid rounding.** The grid's size is rounded up to a
  power-of-two count of top-level tiles across, or the game crashes in
  `BGSBtrDB` (Freeside, [terrain LOD](fo4_pipeline.md#terrain-lod)).
  Phases 1 to 4 keep FNV's tile list, so `lod_settings` and its grid are
  unchanged. A world with no FNV tiles (Phase 5) needs our own list: tiles
  aligned to the grid's south-west cell, written through the same
  `lod_settings`.
- **A mod's build writes no LOD for a master's worldspace**
  (`cell._world_groups`, [DLC LOD](fo4_plugin_layout.md#dlc-lod)), so a
  mod reshaping WastelandNV changes no distant land. That is Phase 5.

## <a id="phases"></a>Phases

### <a id="p0"></a>Phase 0 (S): skirts on FNV's tiles, now

Replace `terrain_lod.without_skirts` with vanilla-depth skirts: keep each
tile's surface, drop FNV's -14,098 skirt and hang a new one under every
border point, 1,000 units per level step (level 4: 1,000; 8: 2,000; 16:
3,000; 32: 4,000). This closes today's gaps with FNV's tiles and is kept as
the fallback for a world whose LAND we cannot read.

- **Checked by:** the edge measurement ([checks](#checks)) showing every
  crack covered; The Fort, where the old full-depth skirts stood as walls;
  the rail-line spot.
- **Risk:** a 1,000-unit skirt can still show as a wall where FO4 hides a
  neighbouring tile; vanilla lives with the same.

**Built** (`terrain_lod.with_skirts`, which calls `hang_skirts`): FNV's
skirt goes, and each border edge of the surface (as its triangle runs it,
strip stitches skipped) gets two triangles down to copies of its points
`skirt_depth(level)` below, with the same UVs, facing out. Only used
vertices are kept, so the tile's bound no longer reaches -14,098.

**Measured offline** around Goodsprings (cells x -32 to -1, y -16 to 15;
the 158 tiles touching x -36 to 3, y -20 to 19 written to
`D:\scratch\terrain_lod_skirts\before` and `after`), heights every 64 units
along each shared edge with `tools/lod/terrain_lod_edges.py`. "Open" is the
part of a gap no skirt covers, over 1 unit:

| Edge | Edges | Samples | Worst gap per edge, median | Worst gap | Open samples before | Edges / tiles open before | Open after |
|---|---|---|---|---|---|---|---|
| level 4 beside 4 | 144 | 36,864 | 87 | 329 | 28,550 | 144 / 96 | 0 |
| level 4 beside 8 | 160 | 40,960 | 185 | 792 | 37,724 | 160 / 128 | 0 |
| level 8 beside 8 | 40 | 20,480 | 243 | 701 | 17,267 | 40 / 32 | 0 |
| level 8 beside 16 | 48 | 24,576 | 421 | 1,083 | 22,920 | 48 / 44 | 0 |
| level 16 beside 16 | 12 | 12,288 | 647 | 1,209 | 11,259 | 12 / 12 | 0 |
| level 16 beside 32 | 16 | 16,384 | 946 | 1,733 | 16,041 | 16 / 18 | 0 |
| level 32 beside 32 | 5 | 10,240 | 1,388 | 1,634 | 10,002 | 5 / 6 | 0 |

Every gap is under the higher tile's skirt (worst 1,733 against level 16's
3,000). Cost per tile, land shape: level 4 1,514 to 1,767 triangles
(+17%), 8 +8%, 16 +7%, 32 +5%; vertices slightly fewer (FNV's unused skirt
points dropped); files +7% at level 4. Not yet checked in game: The Fort
and the rail-line spot.

### <a id="p1"></a>Phase 1 (M): heights from LAND — built 2026-11-26, not played

`terrain_land.cell_heights` decodes each grid cell's `VHGT`
(`decode_vhgt`, as `exterior` reads it), 33 × 33 points per cell;
`tile_heights` lays a tile's cells out on one grid, every land point at
levels 4 and 8, every 2nd at 16 and every 4th at 32 (at most 257 a side).

- **A plugin with masters** takes its masters' LAND under its own: the
  build passes `Exterior.cells` and `Exterior.land`, which come from
  `export_records` and `land_of` → `fresh_records`, layered over every
  master's export with the plugin's own record winning per cell
  (`export_index._layer`, [master blindness](../../CLAUDE.md#master-blindness)).
  A child worldspace that uses its parent's land (`PNAM` Use Land Data) has
  no LAND of its own and keeps FNV's tiles.
- **Cells that disagree on a shared edge.** 40 of WastelandNV's 32,515
  shared cell edges differ (28 by over 64 units, worst 1,312, mostly on the
  world's rim at ±64). A shared point takes the east, then north, cell's
  height, and a tile reads the cells past its east and north edges too, so
  both tiles beside an edge take the same row. Before this rule the
  whole-world measurement showed same-level gaps up to 861.
- **Cells with no LAND:** a hole the land encloses (`holes`) gets heights
  spread in from the cells around it (`filled`), once per world, so every
  tile sees the same; past the land's edge the tile leaves no ground. The
  Skyrim generator edge-extended both, which invented cliffs past the coast
  ([lesson](../commentary/asset_convert_terrain.md#lod-invents-terrain-over-cells-with-no-land)).
  WastelandNV has 16,386 land cells and no holes.
- **Under water:** heights kept as they are; the `WATER` node covers them.

### <a id="p2"></a>Phase 2 (M): the tile mesh — built 2026-11-26, not played

`terrain_land.tile_mesh`, then `terrain_lod.land_btr`:

- **A right-triangle hierarchy** (as Mapbox's Martini, RTIN) over the
  tile's grid: each point's error is how far it lies off its triangle's
  hypotenuse, at least its descendants', and the points over a threshold are
  added. That keeps the mesh watertight inside the tile with no T-junctions.
- **Fixed border.** Every tile edge has a point every `level × 128` units
  (33 a side) and no other: those are forced in, every other edge point is
  never added, nor any point whose adding would need one (its cone). So
  same-level neighbours share every edge point, and a coarser neighbour's
  points are every other one of a finer one's.
- **Budget** by threshold: the triangles of a triangulated square are
  2V − B − 2, so the threshold falls out of the sorted errors. Level 4:
  4,000; above: 3,000 (`BUDGET`, `DEFAULT_BUDGET`); never under 1 unit of
  error. At 2,048 above level 4 the tiles were only even with FNV's (level
  8 median off VHGT 39 against FNV's 36), since this hierarchy spends
  triangles less freely than FNV's simplifier; at 3,000 they beat it at
  every level.
- **No cell borders at level 4.** The plan had level 4 built cell by cell
  so it matches the loaded land; vanilla does not (its level-4 tiles have 1
  to 6 points on an inner cell line, gaps up to 2,496 tile units), and
  keeping them every 512 units put the worst error at 644 against 336
  without. `CELL_LINES` can turn it back on per level.
- **Skirts** as Phase 0, hung on the tile's square (`hang_skirts`), so a
  tile whose land stops short of its edge hangs none there.
- **Precision:** no shift needed. Positions are half floats in tile units;
  VHGT heights are multiples of 8, so every height is exact below 16,384
  units (measured: 0 error on every vertex, WastelandNV's Goodsprings
  window up to 15,112). Translation stays 0, as in every vanilla tile.
- **Layout** as `terrain_lod.btr` writes it (land shape, texture set,
  `WATER` node, multi-bound; `_tile` writes both); UVs u = x, v = 1 − y.

**Measured offline, WastelandNV** (scratch, no game build). Edges, the
whole world's 1,360 tiles, every 256 units:

| Edge | Edges | Worst gap per edge, median | Worst gap | Open |
|---|---|---|---|---|
| level 4 beside 4 | 1,984 | 0 | 0 | 0 |
| level 4 beside 8 | 1,920 | 108 | 1,113 | 0 |
| level 8 beside 8 | 480 | 0 | 0 | 0 |
| level 8 beside 16 | 448 | 327 | 1,904 | 0 |
| level 16 beside 16 | 112 | 0 | 0 | 0 |
| level 16 beside 32 | 96 | 776 | 2,884 | 0 |
| level 32 beside 32 | 24 | 0 | 0 | 0 |

Around Goodsprings (the Phase 0 window, 158 tiles) the cross-level medians
drop against FNV's tiles (4 beside 8: 139 from 185; 8 beside 16: 351 from
421; 16 beside 32: 595 from 946) and every same-level gap goes to 0.
Surface against VHGT at every land point of the tiles wholly inside the
window, with tile size:

| Level | Tiles | Triangles (FNV / ours) | Off VHGT median (FNV / ours) | 95% | 99% | Worst | File KB |
|---|---|---|---|---|---|---|---|
| 4 | 64 | 1,499 / 3,775 | 13.7 / 8.0 | 56.5 / 40.0 | 88 / 60 | 516 / 336 | 20 / 49 |
| 8 | 16 | 1,498 / 2,916 | 36.3 / 31.0 | 141 / 132 | 217 / 189 | 735 / 520 | 20 / 39 |
| 16 | 4 | 1,994 / 2,962 | 93.8 / 72.5 | 367 / 284 | 549 / 391 | 1,266 / 912 | 26 / 39 |

Freeside (FreesideWorld, 39 tiles): 0 gaps both ways. Time: the whole
world in 62 s on one thread, cold (FNV's path: 53 s); the work cache keeps
each tile after. The FNV-tile path's bytes are unchanged (three tiles
compared with the user's 2026-11 build's archive).

### <a id="p3"></a>Phase 3 (M): textures — normal map built 2026-11-26, diffuse planned

- **Normal map, built** (`terrain_land.normal_map`, `terrain_lod.normal_plan`):
  from the tile's full-resolution heights (every land point, so the land's
  own detail lights distant hills), 512² at every level, FO4's model-space
  layout: R x, G up, B y, image column along x, row 0 at the north edge,
  BC1 as today's. Checked against FNV's own normal maps in the same layout
  ([terrain LOD](fo4_pipeline.md#terrain-lod)): per-channel correlation
  0.89 to 0.98 on five tiles across the levels, same means (Lake Mead's flat
  tile: green 0.37, nearly constant). 0.01 s a tile at level 4, 0.08 s at
  32.
- **Diffuse, planned:** composited from the land's own textures and layers.
  Start from the FO4 side's own reading of FNV's layers
  (`land_layers.land_textures`: each quadrant's base and painted layers as
  blended shares, what the loaded land draws), not the Skyrim compositor
  (`asset_convert/lod/terrain_lod_textures.composite_cell`), which decodes
  TES4 binaries. Shade by `VCLR`; sample FNV's landscape textures through
  `export_file`, so a texture replacer overlay (NVTUP) also changes
  distant land. This replaces FNV's own LOD diffuse, so the Legion tents'
  baked footprints and other baked objects go; object LOD carries those.
- **Formats** as today (BC1) first; vanilla's BC3 only if a play test shows
  banding.
- **Colour check:** the composited level-4 diffuse against a screenshot of
  the loaded land at the same spot, so distant ground does not turn darker
  or lighter than near ground (a common xLODGen complaint).

### <a id="p4"></a>Phase 4 (S): into the build — built behind a switch, default off

- `cell._world_groups` passes each owned worldspace's `(cells, land)` to
  `terrain_lod.write`. With `F3NV_TERRAIN_FROM_LAND=1`, `ground_heights`
  fills the world's heights once and each tile's land and normal map come
  from them (`made`, `normal_plan`); a tile with no land there keeps FNV's,
  and the diffuse stays FNV's until Phase 3's. Unset, the build is as
  before (FNV tiles with Phase 0 skirts).
- Each tile's mesh is work-cached on its sampled heights, the FNV tile's
  bytes (its water), level and texture names, with the generator's code;
  each normal map is staged under a hash of its full-resolution heights. A
  rebuild touches only tiles whose land changed.
- `LODSettings` is unchanged (FNV's tile list, same grid, same levels).
- **Object LOD** re-bakes once (its key includes the `.btr`), then trims
  against the new ground.
- **To switch the default:** play WastelandNV with the switch on (the rail
  line, The Fort, Freeside, the Strip's edge, [world look](fo4_plan_world_look.md#p2)),
  then make `ground_heights` unconditional and drop the switch.
- Tiles still build one after another, as today's; the worker pool under
  the [resource setting](fo4_build_resources.md#profiles) is worth adding
  only if the cold 62 s matters.

### <a id="p5"></a>Phase 5 (M): a master's worldspace, baked once for the load order

A mod's build writes no LOD for a worldspace it does not own
([DLC LOD](fo4_plugin_layout.md#dlc-lod)): two builds writing the same tile
names would replace each other's whole tiles. So a mod that reshapes
WastelandNV changes no distant land, and its placed objects get no object
LOD. The Skyrim side solved the same with one bake per worldspace
(`tools/release/create_lod.py --worldspaces`): records from the plugin that
owns it, every other enabled plugin applied as an overlay in load order,
written once into a standalone LOD folder installed after the plugins.

- **One bake per worldspace** across the user's enabled converted plugins:
  the owner's cells and LAND, each later plugin's LAND overriding per cell
  (last wins, as the game loads them), through the same `cell_heights`,
  `filled` and `tile_mesh`.
- **Its own output folder** (for example `F3NV - LOD`), loading after every
  plugin, holding `Meshes\Terrain`, the terrain textures and `LODSettings`
  of each baked worldspace. The game and mod builds stop writing terrain
  LOD for a world the bake covers.
- **Cheap reruns:** the per-tile cache key is the tile's sampled heights,
  so a mod that touches 20 cells rebuilds only the tiles over them (about
  20 level-4 tiles and their parents), not the world.
- **Grid:** the owner's FNV tile list and `LODSettings` when it ships
  tiles; otherwise tiles aligned to the land's south-west cell at levels 4
  to 32 (fewer for a small world), kept where they hold land, written
  through `lod_settings` (power-of-two rounding).
- **Water:** FNV's tile water when the owner ships tiles; a new world needs
  its water from the cells' water heights (`XCLW`, the world's default),
  cut into the same 16 segments.
- **Object LOD** in the same bake: every plugin's placed references with
  `MNAM` into one LODGen list per worldspace, the masters' LOD meshes
  staged as today ([master meshes](fo4_pipeline.md#object-lod-masters)).
- **Checked by:** a test mod editing a few WastelandNV cells: only the
  tiles over them change, the edge tool shows no new gaps, and the mod's
  objects appear in the distance.

### <a id="p6"></a>Phase 6 (S): plugin-less LOD replacers

A replacer with new tiles under `meshes\landscape\lod` and no plugin does
nothing today: `terrain_lod.tiles` and `_texture_jobs` read `asset_root`
(the plugin's export chain), not the overlays (`export_file`,
`F3NV_OVERLAYS`, [asset overlays](fo4_plugin_layout.md#asset-overlays)),
and `overlay.py` converts only files a built plugin lists, which the
`.btr` are not. Once tiles come from LAND such a replacer's meshes matter
only as the fallback for a world whose LAND cannot be read (a child world
on its parent's land), and its textures only until Phase 3's diffuse
replaces FNV's. So: read the fallback tiles and LOD textures through
`export_file`, so an overlay wins there, and do nothing more for them.

## <a id="checks"></a>How it is checked

- **Edge gaps, measured** (`python -m tools.lod.terrain_lod_edges
  <Meshes/Terrain/World folder> [--cells X0 Y0 X1 Y1] [--step 64]`): the
  height gap along every shared edge, same level and across levels. Target:
  0 between same-level tiles, and every cross-level gap under the coarser
  level's skirt. Met on all of WastelandNV ([Phase 2](#p2)).
- **Heights against the land:** each tile's surface against `VHGT` at every
  land point, beside FNV's tiles ([Phase 2](#p2); the scratch script is not
  a tool yet).
- **Tests:** `tests/test_fo4_terrain_land.py` (watertight tiles with only
  their fixed border points at every level, neighbours sharing edges,
  coarser edges a subset, cells disagreeing on an edge, holes, land
  missing, the normal map's layout) and `tests/test_fo4_terrain_lod.py`
  (a LAND tile's layout, UVs and skirts beside the FNV tile tests).
- **In game:** the rail line, The Fort and Freeside spots
  ([world look](fo4_plan_world_look.md#p2)); frame time and video memory at
  The Fort and on the Strip's edge, vanilla-size textures against ours.

## <a id="later"></a>Later, on the same code

- Presets in the app (vanilla, high, ultra) for texture size and triangle
  budget.
- A heightmap per worldspace for Community Shaders' terrain shadows, which
  ships them only for the base game and DLC.

## <a id="not"></a>Not in this plan

Object LOD and tree LOD (separate; Phase 5 only feeds the bake), dynamic LOD
(needs runtime help), and runtime terrain like OpenMW's (needs the
renderer).
