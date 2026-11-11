# Our own FNV/FO3 NIF reader (spike)

**Code:** `fo4_import/nif/fnv_schema.py`, `fo4_import/nif/fnv_reader.py`;
checks `tools/nif/fnv_reader_check.py`, `tools/nif/fnv_convert_check.py`;
test `tests/test_fo4_fnv_reader.py`. **Not used by the build, deploy or
app.** Measured 2026-11-11.

**Short version.** The reader matches pyffi field for field on 420 meshes,
and the converter makes byte-identical FO4 meshes from it on 230. Reading
is 8× faster over the sample and up to 100× on big meshes. Peak read memory
drops from about 12× the file size to about 2×. It does **not** fix The
Frontier's space-station freeze: pyffi reads that mesh in 3.7 s at 738 MB.
The freeze is in the converter's
[overlay check](#station), not in reading.

## <a id="census"></a>Census

A header-only scan (block-type table only) of every `.nif` under the
FO3/FNV export folders: 55,136 files.

| Version / user / BSVER | Files |
|---|---|
| 20.2.0.7 / 11 / 34 | 55,078 |
| 20.2.0.7 / 11 / 21, 14, 26 | 36, 16, 4 |
| 20.0.0.4 / 11 / 11 | 2 (refused by our reader; pyffi reads them) |

FO3 and FNV use the same format, so FO3 support came free. The files use
**161 block types**. pyffi's nif.xml declares all of them, so nothing
needs hand-written layouts. The most common types (files):
BSShaderTextureSet and BSShaderPPLightingProperty 52,163, NiMaterialProperty
40,395, NiTriStrips/Data 36,998, BSFadeNode 36,650, BSXFlags 31,285,
NiStringExtraData 28,282, bhkCollisionObject 27,818, NiAlphaProperty 25,508,
bhkRigidBody 21,792, bhkPackedNiTriStripsShape / hkPackedNiTriStripsData /
bhkMoppBvTreeShape about 20,680, NiTriShapeData 17,413, NiNode 15,782,
NiTriShape 15,496.

Largest meshes: The Frontier's `tfssspacestationext.nif` 63.1 MB,
`tfssarchimedesstationscol` 32.4, `tffinalbossworldrocksscol` 29.6,
`tfssrotatingtuberoom` 26.6, `tfscolmarketbuildingcomplete` 24.5. The
largest vanilla FNV meshes are about 11 MB (`scolrrcprovingring`,
`dlc05mothership01`, `villatest`, LR's `silo-elevator-shaft`).

## <a id="schema"></a>Schema

The layouts come from **pyffi's own nif.xml class tables, read after the
converter's `pyffi_monkey_patch` has run**. The reader sees the same field
names and the same patched layouts as today's code. Names matter because the
converter reads fields by pyffi's names (`unknown_short_2` on range nodes,
`emit_multi`, ...); `references/nif.xml` renames many of them.
`fnv_schema.plan(cls, (version, user, bsver))` compiles one struct type
for one file version:
- version, user-version and `vercond` checks are applied once;
- `cond`, `arr1` and `arr2` become Python lambdas;
- a field after a same-named field with no condition is dropped.

pyffi's helper mixins list every field twice. Dropping the dead copies is
what lets most structs take the numpy path.

pyffi details mirrored, each found by a field-by-field diff:
- **pyffi's patched UV-set count** (`NumUVSets`): in a 20.2.0.7 Bethesda
  file only bit 0 of the byte counts
  ([BSGeometryDataFlags](../../commentary/asset_convert_nif.md#bethesda-geometry-data-flags)).
  A basic type with its own `read` that the reader doesn't know is refused
  (`TypeError`), so a new pyffi patch can't be misread silently.
- **Bitfield bits no field names are dropped** (pyffi's `int()` of a
  bitstruct): `BSSegment.flags` 0xAE00 reads 0x200.
- **`get_refs()` / `get_links()` walk the attribute list unfiltered by
  version** (pyffi calls them without file data). So on
  NiControllerSequence the old `text_keys` field comes before
  `controlled_blocks`. `tree()` order, and with it the FO4 output's block
  order, depends on this.
- A field that is never read returns pyffi's default (from a cached
  default-constructed pyffi instance), as pyffi's objects do.

## <a id="reader"></a>Reader

`fnv_reader.read(path)` returns a `NifData` with pyffi's attribute names
(`version`, `user_version`, `user_version_2`, `blocks`, `roots`). Blocks are
our classes from `fnv_schema.klass`: same name and bases as pyffi's, fields
as plain attributes.
- **Number arrays are numpy arrays.** `Values` holds plain numbers.
  `Records` holds a struct whose layout never varies: Vector3, Triangle,
  hkTriangle, TexCoord, SkinWeight, MatchGroup rows, ... Iterating or
  indexing gives Python numbers, or our structs, as pyffi's arrays do;
  `.array` is the numpy array.
- **Blocks are read by their header size.** An unknown type, or a block
  that fails to read, is kept as `Unread` and listed in `skipped`. A block
  read to another size is listed in `resized`; pyffi skips the same way.
  Production falls back to pyffi when `skipped` is not empty. In the whole
  sample, `skipped` was always empty. `resized` was set once:
  `triggers/trigplayerbox01.nif`, where pyffi reads the same short sizes.
- Kept from `fnv_file`: stray bytes before the header line are skipped, and
  a string index past the table reads `b''` (WNM's AK47/FNC/FNCSIL).

## <a id="compat"></a>Converter compatibility

Each class also gets pyffi's own helper methods: `tree`, `get_transform`,
`get_properties`, `get_triangles`, Matrix44 math, and so on. They are copied
with their `NifFormat` global pointed at `fnv_schema.FORMAT`, a stand-in
that returns our class for a struct name and pyffi's attribute for anything
else. So converter code that says `isinstance(g, NifFormat.NiTriBasedGeom)`
or `NifFormat.Matrix44()` works unchanged once its `NifFormat` is `FORMAT`.
The float math is pyffi's own code, so results are bit for bit the same.

One difference: writing to a `Records` element (`data.vertices[i].x = 1`)
does not reach the array. pyffi's `nif_geom_array` views write through.
`convert_static` never writes to them (its output is byte-identical); other
converters must be checked before they switch ([integration](#integration)).

## <a id="proof"></a>Proof against pyffi

`fnv_reader_check.py` diffs every field pyffi reads, recursively: links by
block index, the `get_refs()` order of every block, and the roots. Sampled
for variety (a file bringing an unseen block type first), in workers capped
at 4 GB:

| Group | Meshes | MB | Files that differ | Ours (s) | pyffi (s) |
|---|---|---|---|---|---|
| FalloutNV.esm | 120 | 18.9 | 0 | 0.64 | 5.82 |
| Fallout3.esm | 80 | 18.0 | 0 | 0.47 | 4.25 |
| NV DLC + Anchorage | 70 | 10.3 | 0 | 0.54 | 3.26 |
| Mods (NVMIM, YUP, WNM, NVB, Willow, ...) | 70 | 26.6 | 0 | 0.75 | 6.33 |
| The Frontier | 70 | 11.1 | 0 | 0.63 | 4.54 |
| WNM AK47/FNC (header quirks) | 10 | 4.4 | 0 | 0.06 | 0.67 |
| **Total** | **420** | **89.3** | **0** | **3.09** | **24.87** |

Times are summed read times per file, the first read in each worker
included. Warm, a typical small mesh reads in 1 ms with ours and 2–50 ms
with pyffi (FNC.nif: 0.85 ms against 46 ms). The schema compile costs a few
milliseconds per worker; importing pyffi and the schema, 0.3 s.

**Big meshes**, one child process per reader, capped at 4 GB. Peak is the
committed memory over the process's start:

| Mesh | MB | Ours | pyffi |
|---|---|---|---|
| tfssspacestationext (Frontier) | 63.1 | 0.03 s, 121 MB | 3.72 s, 738 MB |
| tfssarchimedesstationscol | 32.4 | 0.02 s, 63 MB | 2.08 s, 379 MB |
| tffinalbossworldrocksscol | 29.6 | 0.02 s, 56 MB | 2.02 s, 381 MB |
| tfssrotatingtuberoom | 26.6 | 0.06 s, 56 MB | 2.02 s, 346 MB |
| tfscolmarketbuildingcomplete | 24.5 | 0.15 s, 52 MB | 1.76 s, 305 MB |
| tfliberatorairshipscol | 21.8 | 0.04 s, 42 MB | 2.87 s, 369 MB |
| tftraincarrow1 | 20.8 | 0.02 s, 40 MB | 1.47 s, 279 MB |
| scolrrcprovingring (FNV) | 11.0 | 0.02 s, 22 MB | 0.72 s, 140 MB |
| dlc05mothership01 (FNV) | 10.9 | 0.15 s, 39 MB | 1.50 s, 199 MB |
| villatest (FNV) | 10.7 | 0.06 s, 25 MB | 0.93 s, 143 MB |
| nvdlc04_silo-elevator-shaft (LR) | 10.9 | 0.04 s, 24 MB | 0.87 s, 146 MB |
| nvlucky38reactor (FNV) | 5.0 | 0.03 s, 12 MB | 0.50 s, 70 MB |
| scolgthotel01 (FO3) | 6.2 | 0.01 s, 12 MB | 0.38 s, 75 MB |

Ours peaks at about twice the file: the file's bytes plus the copied
arrays. Reading arrays as views of the file bytes would bring it to about
1×. pyffi already keeps Vector3, Color4, TexCoord and Vector4 arrays in
numpy (`nif_geom_array`, patch 14). Its remaining 12× is per-element
objects: triangles, strip points, hkTriangles, MOPP bytes, skin weights.

### <a id="station"></a>What freezes on the space station

**The reader isn't the cause.** Converting `tfssspacestationext.nif` with
our reader under a 4 GB cap reaches `convert_static.overlay_layers` in 3.1 s.
Then `_surface_gaps` asks for one array of 256 points × 677,436 triangles
× 3 float64: **3.88 GiB for a single temporary**, and more for the next
ones. The same check runs out of memory on NVMIM's `dlc05mothership01.nif`
under the cap. The "about 1 GB per second" growth in
[worker-memory](../fo4_build_speed.md#worker-memory) is this check, not
pyffi's read.

## <a id="integration"></a>Integration plan

`fnv_convert_check.py` runs `convert_static.convert` twice in one process:
once as today, once with `fnv_file.read` → `fnv_reader.read` and
`NifFormat` → `fnv_schema.FORMAT` in the converter's modules only. It then
compares the FO4 NIF bytes (SHA-1) plus `materials`, `effects`, `textures`,
`spec_maps`, `glow_maps` and `animatable`:

| Group | Meshes | Identical / converted | Fail in both | Ours (s) | pyffi (s) |
|---|---|---|---|---|---|
| FalloutNV.esm | 60 | 58/58 | 2 | 7.00 | 9.77 |
| Fallout3.esm | 40 | 39/39 | 1 | 8.06 | 9.59 |
| NV DLC + Anchorage | 40 | 40/40 | 0 | 5.72 | 7.88 |
| Mods | 40 | 39/39 | 1 | 9.49 | 11.88 |
| The Frontier | 40 | 39/39 | 1 | 8.43 | 10.48 |
| WNM AK47/FNC | 10 | 10/10 | 0 | 15.40 | 12.16 |
| **Total** | **230** | **225/225** | **5** | **54.1** | **61.8** |

Every mesh that converts gives byte-identical output. The five failures
fail the same way under both readers (only the message differs). They are
existing converter errors:
- `bhkLiquidAction` / `bhkOrientHingedBodyAction` have no `entities`
  (`dlc03flamerexplosion`, Frontier `turretscorcher/skeleton`);
- a KeyError on `westfathercorpse`;
- a float overflow on FO3 LOD `wasteland.level4.x0.y-20`;
- the overlay check running out of memory on NVMIM's mothership.

Conversion is 12% faster in total, because reading is a small part of
converting. The rest is per-vertex Python: `vertices()` builds one dict per
vertex, plus the DXT5 alpha scan for specular masks. Timed alone, three
times each, warm: FNC 0.40 s vs 0.45 s, AK47+RD+SIL 0.62 vs 0.65,
nvlucky38reactor 4.37 vs 6.53. The WNM group's slower total comes from 14
workers sharing the CPU over 10 files, not from the reader.

**Switching the build over:**
1. **Freeze the schema.** A `tools/generators` script writes the compiled
   plans to a data module, so reading no longer imports pyffi. The borrowed
   helpers still come from pyffi. Porting the ~15 the converter uses (tree,
   transforms, Matrix44/33, strip triangulation, ...) is a later step, and
   must keep pyffi's float order.
2. **`fnv_file.read`** returns `fnv_reader.read(path)`. It falls back to
   pyffi when anything is `skipped`.
3. **`NifFormat` → `FORMAT`** in the modules that read FNV data:
   `fo4_import/nif/*` (convert_static, collision, animation, particles,
   shader_anim, gun, weapon, outfit, headgear, creature, tree, terminal,
   clip_shaders), `fo4_import/face/{fnv_head,hair}`,
   `fo4_import/havok/gun_clips`, `fo4_import/rig/assets`, the eleven
   `fo4_import/spike` users, and
   `asset_convert/collision/collision_falloutnv` (shared with the Skyrim
   converter, so only its FNV entry points). That is one import line each.
4. **Write-through `Records` elements**, as pyffi's views, before any
   converter other than `convert_static` switches. Then run
   `fnv_convert_check`-style side-by-sides for creature, gun, outfit,
   headgear, face and tree.
5. **The mesh cache needs no version bump**: the output is byte-identical.

**Size:** about two days. Steps 1–3 are about half a day of mostly
mechanical change. Step 4, plus side-by-sides of the other converters over
a full export, is the rest. No FormIDs, records or deployed files change.

## <a id="verdict"></a>Verdict

**Go**, for speed and memory headroom, not for the freeze. It is a drop-in
with proof (0 field differences in 420 meshes, 225/225 byte-identical
conversions). Reads get 8–100× faster and use 6× less memory, and
conversion gets 12–33% faster. The space-station freeze needs its own fix
in `overlay_layers` / `_surface_gaps`: test points against nearby triangles
only, in chunks sized by triangle count. Without that fix, the switch
leaves the freeze in place.
