# Research: Fallout 4 terrain and object LOD, before we build our own (2026-11-12)

Status: research only, nothing built. Status lives in [ROADMAP.md](../ROADMAP.md).
Feeds [terrain LOD](../fo4_pipeline.md#terrain-lod) and [object LOD](../fo4_pipeline.md#object-lod).

**Why.** Distant land shows gaps between tiles, and FNV's LOD is coarse next
to what FO4 and today's machines can draw. Before writing our own generator
we measured vanilla FO4's LOD and FNV's, read the existing tools, and listed
their known problems.

## <a id="gaps"></a>Why our terrain LOD has gaps

FNV simplified each LOD tile on its own, so neighbouring tiles do not share
edge points. FNV hid the cracks with skirts: every edge point repeated at
-14,098. We remove those skirts (`terrain_lod.without_skirts`), because
FO4 lowers or hides LOD tiles near the player and the full-depth skirts
then stood up as grey walls ([The Fort](../fo4_pipeline.md#terrain-lod)).
With them gone, the cracks show.

Measured on WastelandNV's own tiles, skirts removed, 40 shared edges each,
heights compared every 64 units along the edge:

| Edge | Edge points | Worst gap per edge, median | Worst seen | Edges over 64 units |
|---|---|---|---|---|
| level 4 beside level 4 | 28 vs 25 | 60 | 344 | 19 of 40 |
| level 4 beside level 8 | 26 vs 9 | 183 | 1,968 | 40 of 40 |

Level changes open and close these as the player moves, which matches the
2026-11-06 report of holes that close up on approach.

## <a id="vanilla"></a>Vanilla FO4 (Commonwealth), measured

Read from `Fallout4 - Meshes.ba2` and `Fallout4 - Textures*.ba2`:

| | Level 4 | Level 8 | Level 16 | Level 32 |
|---|---|---|---|---|
| Tiles | 2,304 | 576 | 144 | 36 |
| Triangles per tile, median (8 sampled) | 2,044 | 1,411 | 2,080 | 2,187 |
| Diffuse and `_msn` | 512², BC3 | 512², BC3 | 512², BC3 | 512², BC3 |
| Skirt depth (world units) | 1,000 | 2,000 | 3,000 | 4,000 |

- **Vanilla has skirts.** Every edge point appears twice: on the surface and
  straight below it, 1,000 units per level step deeper.
- **Vanilla's edges do not match either.** Surface points only: level 4
  beside level 4, worst gap per edge median 11 (worst 426, 13 of 40 over 64);
  level 4 beside level 8, median 103 (worst 3,264, 23 of 35 over 64). The
  engine relies on the skirts.
- Every level gets about the same triangle and texture budget, so the
  detail per cell drops fourfold with each level.

FNV's tiles for comparison: about 3,556 triangles per tile at every level
and 256² textures at every level.

## <a id="tools"></a>Existing tools

| Tool | What it is | Use to us |
|---|---|---|
| sheson's LODGen ([GitHub](https://github.com/sheson/LODGen)), the engine behind xLODGen | C#, writes FO4 `.btr` and `.bto`. **No license file: read and cite, never copy** | The reference for how a working generator does it |
| xEdit `Core/wbLOD.pas` ([TES5Edit](https://github.com/TES5Edit/TES5Edit), MPL-2.0) | The export side of object LOD: which references, which LOD models, the atlas | Rules for choosing objects and models |
| The CK's own generator | No documentation found; forum reports of crashes and TGA output | None |
| DynDOLOD | Does not support FO4; FO4 users use xLODGen plus DynDOLOD's TexGen | None |
| Our Skyrim converter (`asset_convert/lod/terrain_lod.py`, `terrain_nif.py`, `terrain_lod_textures.py`) | Our own terrain LOD from LAND for Skyrim: a texture compositor over the real land textures, height-derived normal maps, water segments ([notes](../../commentary/asset_convert_terrain.md)) | Our own code to start from; it builds every tile as a 33 × 33 grid, diffuse 256² at level 4 up to 2,048² at level 32 |

xLODGen's terrain texture baking lives in a closed xEdit module; only its
mesh side is in LODGen.

## <a id="lessons"></a>Lessons and pitfalls

From LODGen's source (`TerrainLOD.cs`, `changelog.txt`) and its author's
[xLODGen thread](https://stepmodifications.org/forum/topic/13451-xlodgen-terrain-lod-beta-for-fnv-fo3-fo4-fo4vr-tes5-sse-tes5vr-enderal/),
checked against our measurements where we could:

1. **Fixed points on every tile border, at every level.** LODGen inserts a
   regular set of border points before simplifying (`TerrainLOD.cs`, "make
   sure cell borders match each other so there are no holes"), so
   neighbours of the same level always match.
2. **Skirts hide the rest.** LODGen's default is 256 tile units, minus 63
   per level (1,024, 1,544, 2,080 and 2,144 world units at levels 4 to 32;
   `AddSkirts`). Vanilla's are 1,000 to 4,000. Short skirts, not FNV's
   -14,098, avoid the walls we saw at The Fort.
3. **Level 4 is built cell by cell at full resolution** ("protect cell
   borders"), so it matches the loaded land at the cell edges.
4. **Half-float range.** Positions are half floats in tile units; LODGen
   moves each tile's height range to centre on 0 and puts the offset in the
   shape's translation, and switches to full-precision vertices when the
   range exceeds 131,008 (`Geometry.ShiftZ`).
5. **Limits:** at most 65,535 vertices per shape (16-bit indices).
   Simplification is by allowed height error; the author's suggested
   quality is 5 at level 4, then 10 for higher levels.
6. **Object LOD depends on terrain LOD.** LODGen removes object triangles
   under the terrain LOD, so terrain is generated first and must agree with
   it, or objects lose their bases.
7. **Object LOD:** `BSSubIndexTriShape` with one segment per cell at level 4
   (as our terrain water already does); vertex alpha forced to 1; atlas
   default 4,096² with 512 per texture; one guide warns of mipmap faults
   past the atlas size.
8. **No tree LOD format in FO4.** Trees are object LOD with 3D models
   (vanilla's have invisible branch backsides). Our tree cards go the same
   route ([object LOD](../fo4_pipeline.md#object-lod)).
9. **LOD must win its file conflicts** and is best packed in a BA2; loose
   copies were reported to flicker.
10. **Texture budgets people use:** 512 at level 4 and 256 higher, or 512
    everywhere (vanilla). DXT1 diffuse and 565 normals in xLODGen for FO4.
    Very large outputs (one report of about 300 GB) come from oversized
    textures.

Runtime (FO4 ini, `[TerrainManager]`,
[STEP guide](https://stepmodifications.org/wiki/Guide:Fallout4Prefs_INI/TerrainManager)): `fBlockLevel0Distance` 14,336,
`fBlockLevel1Distance` 27,876, `fBlockLevel2Distance` 83,232,
`fBlockMaximumDistance` 161,232, `fSplitDistanceMult` 0.75 (Ultra 1.5).
The LOD area starts outside `uGridsToLoad`. No source describes morphing
between levels.

## <a id="plan-inputs"></a>What this means for our generator

- **The gaps, now:** put skirts back at vanilla's depths (1,000 per level
  step) instead of removing them. This keeps FNV's tiles and needs no new
  generator.
- **Our own terrain LOD later:** build from LAND with fixed border points at
  every level and vanilla-depth skirts; level 4 cell by cell; heights
  centred per tile for half-float precision. Start from the Skyrim
  converter's compositor and normal maps.
- **Quality:** vanilla spends about 2,050 triangles and 512² per tile at
  every level. More is affordable: for example several times the triangles
  at level 4 and 1,024² or 2,048² textures there, falling off with level.
  Budgets to be set by measuring frame time and VRAM in game, not guessed.
- **Object LOD after terrain**, since it trims against it.

## <a id="open"></a>Open questions

- How the engine hides level-4 terrain under loaded cells (a land drop or
  per-cell segments); vanilla's land shape is a plain `BSTriShape`.
- How xLODGen bakes the diffuse, `_msn` and vertex colour (closed source).
- How Project Mojave, Fallout: Miami and Capital Wasteland built theirs; no
  write-ups found.
