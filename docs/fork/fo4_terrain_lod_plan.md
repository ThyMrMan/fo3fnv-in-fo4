# Plan: our own Fallout 4 terrain LOD, better than vanilla (2026-11-12)

Status: planned, nothing built. Status lives in [ROADMAP.md](ROADMAP.md).
Research behind it: [LOD research](research/fo4_lod_research.md).
Replaces the converted FNV tiles in [terrain LOD](fo4_pipeline.md#terrain-lod).

**Goal.** Distant land with no gaps between tiles, built the way FO4's own
LOD is built, from the land itself rather than from FNV's prebuilt tiles,
with a little more detail and texture than vanilla. Fancier versions
(dynamic LOD, terrain shadow heightmaps, higher presets) can come later on
the same code.

**Why not keep FNV's tiles.** They share no edge points (gaps up to 1,968
units, [measured](research/fo4_lod_research.md#gaps)), carry 256² textures
baked by FNV's own renderer, and give every level the same 3,556 triangles.
Building from LAND fixes the edges by construction and lets us pick the
budget.

## <a id="target"></a>What we build, against vanilla

| | Vanilla Commonwealth | FNV tiles today | Ours |
|---|---|---|---|
| Source | the CK, from LAND | FNV's prebuilt tiles | LAND (FNV's VHGT, VCLR and texture layers) |
| Triangles per tile | about 2,050 at every level | about 3,556 at every level | about 4,000 at level 4, about 2,050 above |
| Tile edges | matched at shared points, skirts over the rest | unmatched, no skirts (removed) | fixed border points at every level, skirts as vanilla |
| Skirts | 1,000 units per level step (1,000 to 4,000) | none | as vanilla |
| Diffuse | 512² BC3 | 256² | 1,024² at level 4, 512² above |
| Normal map (`_msn`) | 512² BC3 | 256² | 512² at every level |
| Water | `WATER` node, segmented at level 4 | FNV's water shapes ([distant water](fo4_pipeline.md#distant-water)) | unchanged |

Rough size for WastelandNV's 1,360 tiles, with mipmaps: level 4's 1,024
tiles at 1,024² diffuse and 512² normal map come to about 1.7 GB in BC3
(about 1 GB with a BC1 diffuse); the 336 higher tiles at 512² about
0.25 GB. Vanilla's 2,304 level-4 tiles take about 1.6 GB. To be measured, with frame time and video
memory, before the sizes are fixed ([checks](#checks)).

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

### <a id="p1"></a>Phase 1 (M): heights from LAND

One height grid per tile from each cell's `VHGT` (`decode_vhgt`, as
`exterior` reads it), 33 × 33 points per cell, cells sharing their edge
rows.

- **A plugin with masters** takes its masters' LAND under its own, as the
  build already does for cells ([master blindness](../../CLAUDE.md#master-blindness)).
- **Cells with no LAND:** a hole inside the land takes its neighbours'
  heights; past the land's edge the tile leaves no ground. The Skyrim
  generator edge-extended both, which invented cliffs past the coast
  ([lesson](../commentary/asset_convert_terrain.md#lod-invents-terrain-over-cells-with-no-land)).
- **Under water:** heights kept as they are; FNV's water shapes cover them.

### <a id="p2"></a>Phase 2 (M): the tile mesh

- **Border first.** Every tile edge gets the same fixed points at its
  level: one every `level × 128` units (33 a side), which is also every
  other point of the next finer level. Neighbours of the same level then
  share every edge point, and a coarser neighbour's points are a subset of
  a finer one's.
- **Inside, by height error.** Simplify the interior to the triangle budget
  by allowed height error (greedy insertion from the border, or edge
  collapse on the grid), never moving a border point.
- **Level 4 cell by cell**, so its edges also match the loaded land at
  every cell border, as LODGen's "protect cell borders" does.
- **Skirts** as Phase 0.
- **Precision:** positions are half floats in tile units; centre each
  tile's heights on 0 and move the offset into the shape's translation
  (LODGen's `ShiftZ`), and check no tile's range needs full-precision
  vertices.
- **Limits:** at most 65,535 vertices a shape.
- The file layout stays as `terrain_lod.btr` writes it today (land shape,
  texture set, `WATER` node, multi-bound), so only the land shape changes.

### <a id="p3"></a>Phase 3 (M): textures

- **Diffuse** composited from the land's own textures and layers, as the
  Skyrim generator does (`asset_convert/lod/terrain_lod_textures.composite_cell`):
  each quadrant's base and alpha layers from `ATXT`/`VTXT`, shaded by
  `VCLR`, sampled from FNV's landscape textures as the build copies them.
  This replaces FNV's own LOD diffuse, so the Legion tents' baked
  footprints and other baked objects go; object LOD carries those.
- **Normal map** from the heights (`terrain_lod._heightmap_normal_rgb`),
  in FO4's model-space layout: green up, blue along y
  ([terrain LOD](fo4_pipeline.md#terrain-lod)), UVs and image orientation as
  today's tiles.
- **Formats** as vanilla (BC3) first; BC1 for the diffuse only once a
  play test shows no difference.
- **Colour check:** the composited level-4 diffuse against a screenshot of
  the loaded land at the same spot, so distant ground does not turn darker
  or lighter than near ground (a common xLODGen complaint).

### <a id="p4"></a>Phase 4 (S): into the build

- `terrain_lod.write` builds tiles from LAND for every world whose LAND it
  can read and falls back to Phase 0 for the rest.
- Each tile's mesh and textures are work-cached on its cells' LAND bytes,
  its textures' signatures and the generator's code, so a rebuild touches
  only tiles whose land changed.
- Tiles build in the worker pool under the [resource setting](fo4_build_resources.md#profiles).
- `LODSettings` is unchanged (same grid, same levels).
- **Object LOD** is generated after terrain LOD; if LODGen's unseen-face
  removal runs against our terrain, it now trims against matching ground.

## <a id="checks"></a>How it is checked

- **Edge gaps, measured.** The scratch measurement from the research
  becomes a tool (`tools/lod/terrain_lod_edges.py`, entered in
  `python_tools.md`): for a world's built tiles, the height gap along every
  shared edge, same level and across levels. Target: 0 between same-level
  tiles, and every cross-level gap under that level's skirt.
- **Heights against the land:** level-4 surface against `VHGT` at sampled
  points, within the chosen error.
- **Tests:** a tile's border points; skirt depth per level; a tile next to a
  missing cell; one built tile's layout against today's.
- **In game:** the rail line, The Fort and Freeside spots
  ([world look](fo4_plan_world_look.md#p2)); frame time and video memory at
  The Fort and on the Strip's edge, vanilla-size textures against ours.

## <a id="later"></a>Later, on the same code

- Presets in the app (vanilla, high, ultra) for texture size and triangle
  budget.
- A heightmap per worldspace for Community Shaders' terrain shadows, which
  ships them only for the base game and DLC.
- Fallout 3's worlds and mods' worlds, through the same LAND reading.

## <a id="not"></a>Not in this plan

Object LOD and tree LOD (separate, after this), dynamic LOD (needs runtime
help), and runtime terrain like OpenMW's (needs the renderer).
