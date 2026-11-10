# World look and speed on Fallout 4 (plan)

**Status:** phase 0 built (2026-11-08); the rest planned. Status lines live only in
[ROADMAP.md](ROADMAP.md#fo4-next). The detailed look plan stays in
[fo4_look.md](fo4_look.md); this plan orders it beside the LOD, land and
speed items and does not repeat its steps.

## <a id="goal"></a>1. Goal

Make the converted Mojave look like New Vegas from near and far, and run
smoothly in its densest places. One frame-rate run decides whether
precombines and room culling are needed for the alpha; one fixed set of
comparison spots judges every visual change against FNV.

Issue-plan rows covered ([issue plan](fo4_issue_plan.md)):

| Row | Size | Doc |
|---|---|---|
| Frame rate (play test; gates two rows) | Play | [measured](fo4_pipeline.md#region-measured) |
| Distant land holes | Play, then M | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Distant water | M | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Soft land seams | M | [exterior](fo4_spikes.md#spike-4-exterior) |
| Room culling in 29 interiors | M | [rooms](fo4_pipeline.md#rooms) |
| The look pass | L | [look](fo4_look.md#order) |
| Precombines and previs | L | [before](fo4_pipeline.md#before) |
| Tree LOD | L (M on its own) | [object LOD](fo4_pipeline.md#object-lod) |

## <a id="exists"></a>2. What exists

**Terrain LOD** (`fo4_import/spike/terrain_lod.py`):
- `tiles` lists FNV's prebuilt tiles that have both textures;
  `lod_settings` writes the 16-byte `LODSettings` grid, rounded up to a
  power of two.
- `land_shape` takes each tile's shaded `NiTriShape`; the tile's other
  shape, the `BSSegmentedTriShape` LOD water, is read nowhere.
- `without_skirts` drops every triangle touching a skirt vertex (a border
  vertex under another at the same x, y).
- `btr` writes one `BSTriShape` "Land" per tile with shader type 18. No
  `WATER` shape is written, though Commonwealth tiles carry one.
- `lod_texture` turns both textures half a turn and swaps the normal map's
  green and blue. That fix is built and not played.

**Object LOD** (`fo4_import/spike/object_lod.py`, `fo4_import/pipeline/object_lod.py`):
- `ObjectLod.stat` keeps FNV's Has Distant LOD flag and writes `MNAM`;
  `ObjectLod.add` writes one LODGen row per placed reference whose base has
  `MNAM`; `ObjectLod.write` writes the list.
- `pipeline/object_lod.bake_all` runs LODGenx64 in FO4 mode per worldspace,
  with the atlas from `pipeline/lod_atlas.py`; `install` copies the kept
  tiles and `with_specular` fixes their specular slot.
- Trees are not in it. FNV has 3 TREE records (SpeedTree); its Joshua
  trees, palms and dead trees are ordinary statics
  ([trees](fo4_spikes.md#spike-4-trees)). `fo4_import/nif/tree.py` builds the
  SpeedTree meshes. The FNV export holds 10 billboard textures beside 10
  `.spt` files (`textures/trees/billboards/`, `trees/`).
- `tools/lod/spt_billboard_dump.py` turns billboards into PNGs (written for
  Oblivion; untested on FNV's).

**Land** (`fo4_import/spike/land_layers.py`): `layer_weights` turns FNV's
painted opacities into shares; `kept_textures` keeps each quadrant's 4
heaviest textures, grassy ones first; `_renormalized` keeps grassy shares;
`blend_borders` gives each shared vertex the average mix of only the
textures every quadrant on it keeps. 67 of 30,321 shared vertices in the
first region have no common texture.

**Rooms** (`fo4_import/spike/placement.py`): `_room_bound` keeps `XMBO` off
trigger boxes; `open_rooms` lists the room markers and portals of every
cell where a portal leads to no room (29 of 69 roomed interiors, 944
references), and the build leaves them out, so those cells draw whole.

**The look:** grass density and where grass grows (`spike/grass.py`,
`land_layers.py`), the weather's tint (`weather_imagespace.tinted`), night
ambient (`weathers.directional_ambient`), and glow and neon scaling
(`nif/glow_scale.map_keys`, `nif/shader_anim.py`) are built; their state is
in [fo4_look.md](fo4_look.md#order).

**Frame rate:** one run is measured: Goodsprings to Primm held the 118 cap
at a median 8.5 ms and 24% GPU ([measured](fo4_pipeline.md#region-measured)).
Freeside, the Strip and Novac are not measured.

**Tools (phase 0):** `tools/validate/frame_log.py` summarizes Afterburner
logs and `tools/validate/shot_boxes.py` measures the boxes of reference
shots ([phase 0](#p0)). The Goodsprings run's log is Afterburner's own
file, `C:\Users\thymr\OneDrive\Documents\Afterburner\HardwareMonitoring.hml`
(Afterburner's `LogPath`; logging is now switched off, `EnableLog=0`).

**Not found in the repo:** any precombine or previs code.
Precombines and previs are made by the Creation Kit (the FO4 CK wiki's
`Precombined_References` page: the World menu's PreCombine Geometry and the
Visibility menu). Whether the FO4 Creation Kit is installed here is
unverified.

## <a id="framework"></a>3. The framework

Two shared pieces, both outside the game's own data.

### <a id="gate"></a>3.1 The frame-rate gate

One Afterburner run, logged the same way as the first region's, through
three routes: Freeside (North Gate to the Old Mormon Fort), the Strip
(the gate to the Lucky 38 and back), and Novac (the motel courtyard).
`tools/validate/frame_log.py` reads the logs and prints, per route,
average fps, the 1% low (the slowest 1% of one-second polls), the share
of polls at the cap, median frame time, the busiest GPU's median load and
every spike over 100 ms.

Each route lies in one worldspace. Points from the FNV export (FNV units;
cell = floor(position / 4096); the FO4 worldspace is `FNV_<EditorID>`):

| Route | Worldspace | From | To |
|---|---|---|---|
| Goodsprings (done) | WastelandNV | Doc Mitchell's porch (not looked up) | Primm marker 000CDF46 (-56752, -52992), cell (-14, -13) |
| Freeside | FreesideNorthWorld | North Gate door 00116424 (8601, 6997), cell (2, 1); its pair outside is 00116420 | Old Mormon Fort door 00133966 (6517, 3420), cell (1, 0) |
| Strip | TheStripWorldNew | Gate door 0013BB0D (1246, 8743), cell (0, 2), from FreesideWorld's 00116425 | Lucky 38 door 0013BB17 (3453, 5938), cell (0, 1), and back |
| Novac | WastelandNV | Novac marker 0009289B (22205, -32624), cell (5, -8) | Dino Dee-lite front desk door 000B8585 (22893, -31835) and the room doors behind it |

**Logging the run.** Afterburner, Monitoring tab: switch on "Log history
to file" with the same columns and the 1000 ms poll period as the
Goodsprings run (Framerate, Frametime, GPU usage, memory, RAM).
Afterburner appends to the same file (`RecreateLog=0`), so the
Goodsprings run stays first in it; copy the file aside first as a backup.
Log each route as its own stretch: stop logging between routes (a gap of
over 10 s with no frames starts a new segment); or note each route's start
and end clock time and pass `--segment NAME=HH:MM:SS-HH:MM:SS`. Then:
`python tools/validate/frame_log.py HardwareMonitoring.hml --names
Goodsprings Freeside Strip Novac` (several files are read in order).

The rule, each route against Goodsprings's numbers on the same machine:
- **Every route holds the cap with GPU headroom:** precombines, previs and
  room culling move after the alpha; room culling stays recorded drift.
- **A route drops under the cap in the open:** precombines and previs on
  that area first ([phase 7](#p7)).
- **A drop only in one of the 29 open-room interiors:** room culling for
  that cell first ([phase 6](#p6)).

### <a id="spots"></a>3.2 The comparison spots

Every visual item is judged at the same named spots, at the same hour and
weather, in both games, set from the console (`set gamehour to N`,
`fw <weather>`, `cow` or a placed marker for the camera). The user keeps
the images in `C:\Coding\tes4skyrim\look_refs\`, outside the repo.
`tools/validate/shot_boxes.py` measures mean RGB, luminance, saturation
and hue in fixed boxes (sky, horizon, road, wall, window for `--spot
saloon`), each later image against the first, so a change is a number,
not a guess. Boxes are fractions of the image; FO4's framing differs from
FNV's, so check them with `--draw` and pass `--box` per image when needed.

Positions are FNV's (x, y, z), read from `export/FalloutNV.esm`
(REFR, CELL, WRLD, CLMT, WTHR); cell = floor(position / 4096). Weather:
FNV `fw <FormID>`, FO4 `fw FNV_<EditorID>`; camera `cow <world> x y`
(FO4: `cow FNV_<world> x y`).

| Spot | World, cell | From the export | Hours, weather | Judges |
|---|---|---|---|---|
| Saloon | WastelandNV (-17, 0) | Front doors 0010AEDC (-68266, 3356, 8381) and 0010636F (-67714, 3620, 8393); camera on the road east of them looking west-northwest (the shots' compass). The plan's earlier (-18, 0) is the Goodsprings marker 000CDF51's cell | 12, 0; NVWastelandClear 000FFC88 | Tone, weather tint, clouds, grass, glow ([reference shots](fo4_pipeline.md#reference-shots)) |
| Cemetery | WastelandNV (-16, 3), cell GSCemetery | Lantern 0010B18C (-61653, 13174, 10266); marker 001088F6 (-62219, 12673) | 0; NVWastelandClear | Lights, night ambient |
| Rail line | WastelandNV | **Not verified:** the 2026-11-06 report gives no position | 12; NVWastelandClear | Terrain LOD holes and dark blocks |
| The Fort | WastelandNV (22, 11) | Marker 000CDF0D (90975, 45082, 7770), outside TheFortWorld's door 0013D4A5. Hoover Dam (marker 00135E5F, 74712, 24848) lies southwest and Lake Mead Cave (0010C6C7, 78320, 55936) northwest, so the view is west, not east as first written | 12; NVWastelandClear | Distant water, terrain LOD skirts |
| Ivanpah | WastelandNV (-16, -21) | Highway SCOL ref 001658DE (-63983, -85045, 5716) | 12; NVWastelandClear | Object LOD at close range ([hiding](fo4_pipeline.md#lod-hiding)) |
| Black Mountain | WastelandNV (0, 2) | Marker 000CDEFB (3171, 11634, 10976); the Strip lies north | 12, 0; NVWastelandClear | Object LOD, tree LOD, night horizon glow |
| North Gate | WastelandNV (-3, 27) | Marker 0013A66A (-9670, 111810, 4356); gate door 00116420 (-10019, 111727) | 0; NVWastelandClear | Neon, glow, imposters left out ([imposters](fo4_pipeline.md#imposters)) |
| Strip | TheStripWorldNew (-1, 1) | Gomorrah's doors 0013BB08 (-1952, 6704, 1157) and 0013BB1D | 0; NVTheStripWeather 00161241 (the world's only climate weather) | Neon, tone |
| Seam | WastelandNV | **Not verified:** one of the 67 unmatched vertices, which `land_layers.limit_textures` does not list | 12; NVWastelandClear | Soft land seams |

NVWastelandClear is the weather fo4_look measured against; WastelandNV's
climate (NVDefaultClimate) lists NVWastelandClearNight (00176574) at 100,
so force the weather in both games. Freeside's worlds use NVUrbanClear
(00173564). **Why this covers the
rows:** each row asks "is it fast enough" (the gate, once for all three
speed rows) or "does it look like FNV from here" (one shot pair per change).

### <a id="dll"></a>3.3 DLL decisions

None proposed. Each item has an engine or tool route:

| Candidate | Engine route used instead |
|---|---|
| Logging frame time from F4SE | Afterburner's own log |
| A runtime tone curve ("FNV look") | A converted LUT per weather in the imagespace record, or a player option through an ini or mod setting ([tone](fo4_look.md#lighting)) |
| Runtime culling for open-room cells | Room markers and portals written as vanilla writes them ([phase 6](#p6)) |
| Grass sway | FO4 reads grass vertex alpha as sway weight ([flecks](fo4_look.md#grass-flecks)); data only |

## <a id="phases"></a>4. Phases

### <a id="p0"></a>Phase 0 (S): tools and spots

**Built 2026-11-08.** `tools/validate/frame_log.py` (tests
`tests/test_frame_log.py`) on the Goodsprings log reproduces the measured
run: 213 polls with frames, median 8.53 ms, 118 cap held 94% of polls,
GPU2 median 26% (the earlier note's 24%), spikes 1,739, 271, 126 and
370 ms (the earlier note named only the first and last).
`tools/validate/shot_boxes.py` (tests `tests/test_shot_boxes.py`) gives
the saloon road box (37, 38, 44) on `saloon_night_fnv.webp`, fo4_look's
value exactly. The spots table holds 7 of 9 spots verified from the
export; the rail line and the seam are not.

- **Delivers:** the Afterburner log summary tool and the shot box tool in
  `tools/`, both listed in `docs/reference/python_tools.md`; the spots table
  above with every coordinate it can fill from the export (cell and
  reference positions).
- **Checked by:** each tool's targeted test on a small fixture log and
  image; the box tool reproduces fo4_look's measured night road
  (FNV 37, 38, 44) from `saloon_night_fnv.webp` within 1 level.
- **Depends on:** nothing. Starts right after the play test.

### <a id="p1"></a>Phase 1 (S): the gate decision

- **Delivers:** the run summarized, the decision written into
  [measured](fo4_pipeline.md#region-measured), phases 6 and 7 kept or moved.
- **Checked by:** the tool's per-route table against Goodsprings's.
- **Depends on:** phase 0; the user's run.

### <a id="p2"></a>Phase 2 (M): distant land holes

- **Delivers:** the cause and fix of the holes and dark blocks at the rail
  line. Leads, in order, none confirmed: the texture half-turn not yet
  played; `without_skirts` opening cracks where FO4 draws neighbor tiles
  at different levels (FNV's skirts may have hidden exactly those); a
  missing or textureless tile in `tiles`. A per-tile audit (every level
  covers its parent's area, no tile left out) runs over the built
  `Meshes/Terrain` folder.
- **Checked by:** the audit's count of missing or uncovered tiles reaching
  0; the rail-line and Fort spots with no holes.
- **Depends on:** the play test's rail-line shot.

### <a id="p3"></a>Phase 3 (M): distant water

- **Delivers:** each FNV tile's LOD water (the `BSSegmentedTriShape`) as
  the FO4 tile's `WATER` shape in `terrain_lod.btr`, laid out as a vanilla
  Commonwealth tile's (shape type, shader and material read from
  `Fallout4 - Meshes.ba2` first). The lake-colored stand-in land under the
  water stays, as FNV's does.
- **Checked by:** a test that a converted Lake Mead tile (4.28.12) carries
  both shapes with vanilla's block layout; the Fort spot at noon.
- **Status:** code 2026-11-09, not built ([distant water](fo4_pipeline.md#distant-water)).
- **Depends on:** phase 2 (the same tiles and the skirt question).

### <a id="p4"></a>Phase 4 (M): tree LOD

- **Delivers:** first a census: which FNV statics that read as trees from
  far away (Joshua trees, palms, dead trees) carry Has Distant LOD and a
  `_lod.nif`, and how many SpeedTree references are placed per world. Then
  crossed billboard cards from FNV's 10 billboard textures as `_lod.nif`
  meshes, named in the TREE-derived statics' `MNAM`, so `ObjectLod.add`
  takes them with no new path.
- **Checked by:** the census counts; the LODGen tile count with trees
  against without; the Black Mountain spot.
- **Status:** code 2026-11-09, not built. The census found the trees are
  Has Tree LOD statics (Joshua A, dead trees) plus 3 SpeedTree TREEs, not
  the 10 billboards ([tree LOD](fo4_pipeline.md#tree-lod)).
- **Depends on:** phase 2, so tree cards are not judged over holes.

### <a id="p5"></a>Phase 5 (S): soft land seams

- **Delivers:** the 67 unmatched shared vertices listed with their
  quadrants' kept textures; where one quadrant can swap its lightest kept
  texture for one its neighbor keeps, `kept_textures` does so.
- **Checked by:** the count of unmatched vertices (67 now) and the share
  that moves; the seam spot.
- **Depends on:** nothing; can run beside phase 2.

### <a id="p6"></a>Phase 6 (M, only if the gate asks): room culling

- **Delivers:** the 29 open-room cells keep their rooms. Each portal to no
  room is given a room of its own built from the open space's bounds, so
  no corpse settles outside every room. Whether that keeps bodies drawn is
  unverified; Bison Steve's lobby is the test.
- **Checked by:** the count of open-room cells (29 to 0); Bison Steve's
  convicts drawn after death; frame rate in the worst cell from phase 1.
- **Depends on:** phase 1 naming a slow interior.

### <a id="p7"></a>Phase 7 (L, only if the gate asks): precombines and previs

- **Delivers:** a Creation Kit precombine and previs run on one Strip cell,
  then on the areas the gate named, written into the plugin and packed.
  The build must keep the CK's output across rebuilds, since a changed
  reference turns an area's precombines off.
- **Checked by:** frame time on the gate's route before and after; the CK's
  own output count of combined meshes and `.uvd` files.
- **Depends on:** phase 1; the FO4 Creation Kit (installed state
  unverified).

### <a id="p8"></a>Phase 8 (L): the look pass

- **Delivers:** fo4_look's [order](fo4_look.md#order), each step one play
  test: grass flecks, the weather modifier and clouds, glow and lights,
  then grass color, sway and the overall tone. Strip neon after the Strip
  is played.
- **Checked by:** each step's box numbers at the saloon, cemetery, North
  Gate and Strip spots against FNV's.
- **Depends on:** phase 0. Runs beside phases 2 to 5, one change per play
  test.

## <a id="play-first"></a>5. What the play test should tell us first

- **The frame-rate run** in Freeside, the Strip and Novac: it keeps or
  drops phases 6 and 7.
- **The rail-line spot with the half-turn fix:** if the holes are gone,
  phase 2 becomes the dark blocks alone; if not, the skirts lead goes
  first.
- **The Fort view:** whether the Lake Mead stand-in land reads as water
  from far away, which sets phase 3's priority.
- **Black Mountain toward the Strip:** whether missing trees are visible at
  all in a desert skyline, which may move phase 4 after the alpha.
- **Grass at the saloon at noon:** whether the flecks show with the
  density and ground fixes in, which is the look pass's first step.

## <a id="questions"></a>6. Open questions

- How Project Mojave shows distant water, since its tiles carry no `WATER`
  shape.
- Answered 2026-11-09: FNV has no tree LOD at all. 7 of the 10 billboards
  are Fallout 3's; Joshua trees B to E were already in object LOD, and A
  was not ([tree LOD](fo4_pipeline.md#tree-lod)).
- Whether the FO4 Creation Kit runs headless for precombines and previs,
  as LODGen does, or needs the user at the editor.
- Whether a converted plugin's precombines survive the user's other mods
  touching the same cells (the CK wiki says only one set exists per area).
- Answered in phase 0: the Strip route lies in TheStripWorldNew alone
  (gate cell (0, 2) to the Lucky 38 at (0, 1)), and the Freeside route in
  FreesideNorthWorld alone, so each is one run segment.
</content>
</invoke>
