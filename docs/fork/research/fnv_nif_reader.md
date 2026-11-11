# Our own FNV/FO3 NIF reader

**Code:** `fo4_import/nif/fnv_schema.py`, `fo4_import/nif/fnv_reader.py`,
`fo4_import/nif/fnv_layouts.json` (made by
`tools/generators/gen_fnv_nif_layouts.py`), used through
`fo4_import/nif/fnv_file.read`. Checks: `tools/nif/fnv_reader_check.py`,
`tools/nif/fnv_convert_check.py`. Test: `tests/test_fo4_fnv_reader.py`.
Measured 2026-11-11.

**Short version.**
- **Switched over.** Every FNV/FO3 NIF and KF the FO4 converter reads goes
  through `fnv_file.read`, which uses our reader. It falls back to pyffi only
  for a file of another version, or one with a block ours could not read.
- **Accuracy.** It matches pyffi field for field on 420 varied meshes. Every
  converter gives byte-identical results on real inputs: statics 225/225,
  outfits 14/14, headgear 14/14, guns 14/14, creatures 14/14, face parts
  14/14, trees 12/12, KF clips 14/14.
- **Speed and memory.** Reading is 9× faster over the sample and up to 80×
  on big meshes. Peak read memory falls from about 12× the file size to about
  3×. Converting gets 13% faster for statics, 46% for outfits and 31% for
  creatures.
- **What it doesn't fix.** The Frontier's space-station freeze is in the
  converter's [overlay check](#station), not in reading: pyffi reads that
  mesh in 4 s at 739 MB.

## <a id="census"></a>Census

A header-only scan (block-type table only) of every `.nif` under the
FO3/FNV export folders: 55,136 files.

| Version / user / BSVER | Files |
|---|---|
| 20.2.0.7 / 11 / 34 | 55,078 |
| 20.2.0.7 / 11 / 21, 14, 26 | 36, 16, 4 |
| 20.0.0.4 / 11 / 11 | 2 (refused by our reader; pyffi reads them) |

FO3 and FNV use the same format, so FO3 support came free. The files use
**161 block types**, all declared in pyffi's nif.xml. The most common, by
number of files:

| Block types | Files |
|---|---|
| BSShaderTextureSet, BSShaderPPLightingProperty | 52,163 |
| NiMaterialProperty | 40,395 |
| NiTriStrips/Data | 36,998 |
| BSFadeNode | 36,650 |
| BSXFlags | 31,285 |
| NiStringExtraData | 28,282 |
| bhkCollisionObject | 27,818 |
| NiAlphaProperty | 25,508 |
| bhkRigidBody | 21,792 |
| bhkPackedNiTriStripsShape, hkPackedNiTriStripsData, bhkMoppBvTreeShape | about 20,680 |
| NiTriShapeData | 17,413 |
| NiNode | 15,782 |
| NiTriShape | 15,496 |

Largest meshes:
- The Frontier's `tfssspacestationext.nif` 63.1 MB,
  `tfssarchimedesstationscol` 32.4, `tffinalbossworldrocksscol` 29.6,
  `tfssrotatingtuberoom` 26.6 and `tfscolmarketbuildingcomplete` 24.5.
- The largest vanilla FNV meshes are about 11 MB: `scolrrcprovingring`,
  `dlc05mothership01`, `villatest`, and LR's `silo-elevator-shaft`.

## <a id="schema"></a>Schema

`fnv_layouts.json` is **pyffi's own nif.xml class tables, read after the
converter's `pyffi_monkey_patch` has run**, frozen by
`gen_fnv_nif_layouts.py`. So the reader sees the same field names and the
same patched layouts as pyffi. Names matter because the converter reads
fields by pyffi's names (`unknown_short_2` on range nodes, `emit_multi`,
...); `references/nif.xml` renames many of them.

What the file keeps:
- each field's type, template, argument, counts and condition, as Python
  source;
- each field's version gate;
- the link kind of each field.

It is narrowed to what the reader reads (20.2.0.7, user 11, BS versions
0–34): 472 KB instead of 991 KB. Narrowing drops exact repeats, and fields
no such version has. It keeps any field whose name holds a link at some
version, because pyffi's `get_refs` walks every version (see below). A
test fails when the file differs from what the generator makes.

`fnv_schema.plan(name, (version, user, bsver))` compiles one struct type for
one file version:
- the version gates are applied once;
- `cond`, `arr1` and `arr2` become Python lambdas;
- a field after a same-named field with no condition is dropped.

pyffi's helper mixins list every field twice. Dropping the dead copies is
what lets most structs take the numpy path.

pyffi details mirrored, each found by a field-by-field diff:
- **The patched UV-set count** (`NumUVSets`): in a 20.2.0.7 Bethesda file,
  only bit 0 of the byte counts
  ([BSGeometryDataFlags](../../commentary/asset_convert_nif.md#bethesda-geometry-data-flags)).
  The generator refuses any other basic type that has its own `read`; a block
  using one is skipped, so pyffi reads that file. A new pyffi patch therefore
  can't be misread silently.
- **Bitfield bits that no field names are dropped**, as pyffi's `int()` of a
  bitstruct does: `BSSegment.flags` 0xAE00 reads 0x200.
- **`get_refs()` / `get_links()` walk the attribute list unfiltered by
  version** (pyffi calls them without file data), taking the first field of
  each name. So on NiControllerSequence the old `text_keys` field comes
  before `controlled_blocks`. `tree()` order depends on this, and with it the
  block order of the FO4 output.
- **A field that is never read gives pyffi's default.** It comes from a cached
  pyffi instance built with the struct's own template; `Key<string>`'s
  `forward` needs it.

## <a id="reader"></a>Reader

`fnv_reader.read(path)` returns a `NifData` with pyffi's attribute names:
`version`, `user_version`, `user_version_2`, `blocks`, `roots`. Blocks are
our classes from `fnv_schema.klass`, with the same name and bases as
pyffi's and fields as plain attributes.
- **Number arrays are numpy arrays, read and written through.**
  - `Values` holds plain numbers.
  - `Records` holds a struct whose layout never varies: Vector3, Triangle,
    hkTriangle, TexCoord, SkinWeight, MatchGroup rows, and so on.
  - An element is a row view (`row_class`): `v.x = 1` writes into the array,
    as pyffi's `nif_geom_array` views do. Vector3, Color4, TexCoord and
    Vector4 rows compare by value, as pyffi's views do.
  - **Floats are held as float64**, as pyffi holds them (Python floats), so a
    value the converter computes and stores keeps its full precision.
  - `.array` is the numpy array.
- **Blocks are read by their header size.** An unknown type, or a block that
  fails to read, is kept as `Unread` and listed in `skipped`. A block read to
  another size is listed in `resized`; pyffi skips the same way. In the whole
  sample, `skipped` was always empty. `resized` was set once, on
  `triggers/trigplayerbox01.nif`, where pyffi reads the same short sizes.
- **Header quirks are handled as before.** Stray bytes before the header line
  are skipped, and a string index past the table reads `b''` (WNM's
  AK47/FNC/FNCSIL).

## <a id="compat"></a>Converter compatibility

The converter's code is unchanged; only `fnv_file.read` changed. Three
things make that work:
- **Helpers.** Each class gets pyffi's own helper methods (`tree`,
  `get_transform`, `get_properties`, `get_triangles`, the Matrix44 math, and
  so on). They are copied with their `NifFormat` global pointed at
  `fnv_schema.FORMAT`: a struct name gives our class, anything else gives
  pyffi's. The float math is pyffi's own code, so results match bit for bit.
- **isinstance works both ways.** Our metaclass accepts pyffi's instance of
  the mirrored struct. pyffi's struct metaclass gets an `__instancecheck__`
  that accepts ours. So `isinstance(block, NifFormat.NiNode)` holds for our
  blocks, and a pyffi `NifFormat.Matrix44()` made beside them works with our
  helpers, and the reverse. The shared Skyrim collision code
  (`asset_convert/collision`) also works unchanged on our blocks.
- **Retyping maps to ours.** Shared code retypes a body
  (`rb.__class__ = NifFormat.bhkRigidBody`); assigning a pyffi class to our
  block gives our class of that name.

An error on a missing field reads as pyffi's (`'bhkLiquidAction' object has
no attribute 'entities'`), so failure logs stay the same.

Still read with pyffi directly, and unchanged: the `fo4_import/spike`
modules that call `NifFormat.Data().read` themselves (furniture, poses,
placeable_water, object_lod, terrain_lod, step_map).

## <a id="proof"></a>Proof against pyffi

`fnv_reader_check.py` diffs every field pyffi reads, recursively: links by
block index, the `get_refs()` order of every block, and the roots. Files were
sampled for variety (a file bringing an unseen block type first), in workers
capped at 4 GB:

| Group | Meshes | MB | Files that differ | Ours (s) | pyffi (s) |
|---|---|---|---|---|---|
| FalloutNV.esm | 120 | 18.9 | 0 | 0.74 | 5.91 |
| Fallout3.esm | 80 | 18.0 | 0 | 0.41 | 4.49 |
| NV DLC + Anchorage | 70 | 10.3 | 0 | 0.51 | 3.51 |
| Mods (NVMIM, YUP, WNM, NVB, Willow, ...) | 70 | 26.6 | 0 | 0.76 | 7.25 |
| The Frontier | 70 | 11.1 | 0 | 0.44 | 4.43 |
| WNM AK47/FNC (header quirks) | 10 | 4.4 | 0 | 0.05 | 0.74 |
| **Total** | **420** | **89.3** | **0** | **2.91** | **26.33** |

Times are summed read times per file, including the first read in each
worker. Warm, a typical small mesh reads in 1 ms with ours and 2–50 ms with
pyffi (FNC.nif: 1 ms against 46 ms). Importing the schema takes 0.3 s; it
imports pyffi for the helpers. The layouts load in 4 ms.

**Big meshes**, read once per reader in its own child process, capped at
4 GB. Peak is the committed memory above the process's starting level:

| Mesh | MB | Ours | pyffi |
|---|---|---|---|
| tfssspacestationext (Frontier) | 63.1 | 0.05 s, 181 MB | 4.00 s, 739 MB |
| tfssarchimedesstationscol | 32.4 | 0.04 s, 94 MB | 1.91 s, 379 MB |
| tffinalbossworldrocksscol | 29.6 | 0.02 s, 86 MB | 2.03 s, 380 MB |
| tfssrotatingtuberoom | 26.6 | 0.08 s, 83 MB | 1.94 s, 346 MB |
| tfscolmarketbuildingcomplete | 24.5 | 0.08 s, 76 MB | 1.69 s, 304 MB |
| tfliberatorairshipscol | 21.8 | 0.05 s, 65 MB | 2.89 s, 368 MB |
| tftraincarrow1 | 20.8 | 0.04 s, 62 MB | 1.49 s, 277 MB |
| scolrrcprovingring (FNV) | 11.0 | 0.03 s, 33 MB | 0.71 s, 140 MB |
| dlc05mothership01 (FNV) | 10.9 | 0.17 s, 40 MB | 1.47 s, 199 MB |
| villatest (FNV) | 10.7 | 0.07 s, 38 MB | 0.93 s, 143 MB |
| nvdlc04_silo-elevator-shaft (LR) | 10.9 | 0.05 s, 35 MB | 0.89 s, 146 MB |
| nvlucky38reactor (FNV) | 5.0 | 0.04 s, 20 MB | 0.48 s, 69 MB |
| scolgthotel01 (FO3) | 6.2 | 0.03 s, 19 MB | 0.38 s, 75 MB |

Ours peaks at about three times the file: the file's bytes plus its arrays
with floats widened to float64. Before the widening, during the spike, it
was about twice (station 121 MB). pyffi's 12× is per-element objects:
triangles, strip points, hkTriangles, MOPP bytes, skin weights. pyffi
already keeps Vector3, Color4, TexCoord and Vector4 arrays in numpy
(`nif_geom_array`, patch 14).

### <a id="station"></a>What freezes on the space station

**The reader isn't the cause.** Converting `tfssspacestationext.nif` with
our reader under a 4 GB cap reaches `convert_static.overlay_layers` in
3.1 s. Then `_surface_gaps` asks for one array of 256 points × 677,436
triangles × 3 float64: **3.88 GiB for a single temporary**, and more for the
next ones. The same check runs out of memory on NVMIM's
`dlc05mothership01.nif` under the cap. The "about 1 GB per second" growth in
[worker-memory](../fo4_build_speed.md#worker-memory) is this check, not
pyffi's read.

## <a id="integration"></a>Integration and side-by-side

`fnv_file.read(path)` returns `fnv_reader.read(path)`. It falls back to
`fnv_file.read_pyffi(path)` when the header is not a version the reader
takes, or when anything was `skipped`. `weapon.held_pose` and
`tree._collision`, which read with pyffi directly, now go through it too.
No FormIDs, records or cache versions change: the output is byte-identical.
The work cache keys on the code that ran, so the cached converter results
are made again once.

`fnv_convert_check.py <converter>` runs one converter on real inputs,
reading with pyffi in one set of worker processes and with
`fnv_file.read` in another, and compares a hash of everything the converter
returns. Statics are the spike's 230 varied meshes. The other converters use
14 inputs each from the FalloutNV.esm export's own ARMO, WEAP and TREE
records and folders; trees add Fallout3.esm's, since FalloutNV.esm has
only 3. Times cover the conversion only, summed over the inputs; each mode
uses 14 workers:

| Converter | What runs | Same / inputs | pyffi (s) | Ours (s) |
|---|---|---|---|---|
| static | `convert_static.convert` | 225/225 converted (+5 failing in both) | 98.7 | 85.8 |
| outfit | `outfit.worn` (3rd + 1st person), `shape_materials`, `body_fit` | 14/14 | 75.5 | 40.9 |
| headgear | `headgear.rigid`, `head_frame`, `worn`, `head_fit` | 14/14 | 16.9 | 13.7 |
| gun | `gun.fnv_nodes`, `fnv_layout`, `placement`, `gun`; `gun_clips.fnv_frames` | 14/14 | 17.7 | 16.6 |
| creature | `creature.creature_fit`, `creature_mesh`, `skeleton_parents`, `skin_texture` | 14/14 | 37.0 | 25.4 |
| face | `hair.fnv_shape`, `fnv_head.head` | 14/14 | 2.8 | 0.7 |
| tree | `tree.tree_mesh` (FNV 3, FO3 9) | 12/12 | 5.2 | 5.0 |
| clips | `clip_shaders.clip_channels`, `weapon.held_pose` | 14/14 | 1.5 | 2.0 |

- **Statics.** The five failures fail the same way under both readers, and
  are existing converter errors:
  - `bhkLiquidAction` / `bhkOrientHingedBodyAction` have no `entities`
    (`dlc03flamerexplosion`, The Frontier's `turretscorcher/skeleton`);
  - a KeyError on `westfathercorpse`;
  - a float overflow on FO3 LOD `wasteland.level4.x0.y-20`;
  - the overlay check running out of memory on NVMIM's mothership.
- **Guns** are placed on FO4's hunting rifle receiver (`run_gun`). The
  pipeline picks the receiver per gun from its table, which reads no FNV
  data.
- **Clips are slower** on these tiny KFs: each fresh worker builds its
  classes once.
- **Most of converting is per-vertex Python, not reading**: `vertices()`
  builds one dict per vertex, plus the DXT5 alpha scan for specular masks.
  That is why statics gain only 13%.

The field compare caught one gap, now fixed. A field left out by its
condition, such as Key's `forward` when `arg` ≠ 2, read pyffi's default
from a pyffi Key built without its template, which pyffi can't construct.

## <a id="verdict"></a>Status and what's left

Switched, on the evidence above. Left for later:
- **Port the borrowed pyffi helpers** (tree, transforms, Matrix44/33, strip
  triangulation, ...), keeping pyffi's float order, so reading no longer
  imports pyffi at all.
- **Move the six spike modules** that read with pyffi directly
  ([compat](#compat)) onto `fnv_file.read`, each with its own side-by-side.
- **Fix the space-station freeze** in `overlay_layers` / `_surface_gaps`
  ([station](#station)): test points against nearby triangles only, in
  chunks sized by triangle count. The reader switch leaves it in place.
