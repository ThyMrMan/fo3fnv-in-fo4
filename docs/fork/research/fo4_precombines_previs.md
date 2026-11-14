# Precombines and previs: what they are, how the game uses them, and whether we could make them (research, 2026-11-13)

Status: research only; the converter writes neither today (our `CELL`
writes no `XCRI`, `XPRI`, `PCMB`, `VISI` or `RVIS`, `spike/exterior.py`
`_cell`). Whether the first release needs them is still the
[frame-rate gate](../fo4_plan_world_look.md#gate)'s call. Status lives in
[ROADMAP.md](../ROADMAP.md).

**Sources.** `references/xEdit/Core/wbDefinitionsFO4.pas`,
`references/NifSkope/nif.xml`, the offline FO4 CK wiki
(`Precombined_References.html`, `Editor_Interface.html`), the real plugins
and BA2s in the game's Data folder (read with `tes5_reader.walk` and
`ba2.Archive`), and a static read of `Fallout4.exe.unpacked.exe` 1.11.240
and `CreationKit.exe`. **V** = read in a definition, file or the
disassembly; **I** = inferred or community-reported. Scratch scripts:
`previs_formats/`, `previs_census/` and `previs_engine/` in the session
scratchpad (not kept).

**In short.**
- **Precombines** merge a cell's static references into a few meshes, with
  one merged collision file per cell. Every part is decoded; we could
  write them ourselves ([own](#own-precombines)).
- **Previs** is a precomputed visibility file per 3×3 cells. It is an
  Umbra 3 "tome", a licensed middleware format only the CK can write.
- **Without them** the game draws every reference on its own and culls by
  view frustum, rooms, portals and occlusion planes. Nothing is wrong,
  only slower in dense places.
- **FNV and FO3 are sparser** than the Commonwealth's dense cells
  ([density](#density)).

## <a id="records"></a>The record data (V)

| Where | Field | Layout | Meaning |
|---|---|---|---|
| CELL header | flag 0x80 | bit 7 | "No Pre Vis": the game skips the cell's previs load. 66 vanilla interiors set it, no exterior |
| CELL | `PCMB` | u16 packed date | precombined files' timestamp (vanilla 7972 = 2015-09-04) |
| CELL | `VISI` | u16 packed date | previs files' timestamp; **0 turns previs off** where the player stands |
| CELL | `RVIS` | FormID (CELL) | the cell whose `.uvd` holds this cell's previs |
| CELL | `XCRI` | `u32 meshes, u32 refs, u32 key[meshes], {FormID ref, u32 key}[refs / 2]` | combined reference index; `refs` is twice the pair count (4,600 of 4,600 vanilla cells) |
| CELL | `XPRI` | sorted FormID array | previs reference index: the uncombined refs previs knows by id |
| CELL | `CNAM`, `ZNAM` | u8 each | "precombined object level" XY and Z; in no vanilla cell |

Packed date: `day = v & 0x1F`, `month = (v >> 5) & 0xF`, `year = 2000 +
(v >> 9)` (`wbInterface.pas:23500`). FO4 has no per-reference or
per-base "no precombine" flag; Fallout 76 added one (`XALG` 0x2000).

## <a id="files"></a>The files (V)

- **Meshes.** `Meshes\PreCombined\[<plugin>\]<cell & 0xFFFFFF>_<key>_OC.NIF`,
  one per `XCRI` key, plus one `<cell>_Physics.NIF` per cell. The folder is
  the plugin that **owns the cell's FormID**; Fallout4.esm's cells get none.
  So one set of files per cell exists, whoever overrides it. 120,294 of
  120,319 vanilla (cell, key) pairs have their file.
- **The `_OC` NIF.** NiNodes holding `BSMeshLODTriShape`s (no vertices),
  each with `BSPackedCombinedSharedGeomDataExtra` named `PCD`, plus the
  usual shader, texture set and alpha. The extra data:
  - vertex description, total vertices and triangles, two floats (15.0 and
    4.0 in vanilla, meaning unknown), and a count;
  - per object, `{u32 file hash, u32 offset}` into the `.csg`, then
    vertices, three LOD levels of `(triangle count, offset)`, and one
    72-byte record per merged reference: grayscale scale, transform,
    bounding sphere.
  - The file hash is Bethesda's CRC32 (start 0, no final XOR) of the
    lowercased `.csg` name without extension: `fallout4 - geometry` gives
    0xDDF19A67, the value in every vanilla NIF (checked).
  - `BSPackedCombinedGeomDataExtra` is the same with the vertices and
    triangles inside the NIF. The CK writes that form first; vanilla ships
    only the shared form.
- **`_Physics.NIF`.** NiNode, BSXFlags, bhkNPCollisionObject,
  bhkPhysicsSystem: one hknp blob for every combined ref's collision.
- **`<plugin> - Geometry.csg`.** `bcsg`, `u32 objects` (32,370),
  `u32 chunks` (6,841), the chunk table `{u32 size, u32 offset}`, 20-byte
  object records `{u32 offset, u64 vertex desc, u32 vertices,
  u32 indices}`, then zlib chunks of 64 KiB each (about 448 MB unpacked).
  Geometry is vertices then u16 indices.
- **`<plugin>.cdx`.** `bcdx`, `u32 count` (1,460,027), 16-byte entries
  `{u32 a, u32 cell or world, u32 offset, u32 file hash}`. Field `a` is not
  decoded; a per-cell streaming index (I).
- **`Vis\<plugin>\<RVIS & 0xFFFFFF>.uvd`.** An Umbra 3.3.17 tome behind a
  small Bethesda header (`0xD6000012`, a hash, the file size, bounds) and
  the build string `T 512.0 SO 128.0 SH 16.000 BF 100 F 0 CS 0.0 - 3.3.17
  F 1 0 OG 0`. 966 vanilla files, 1 KB to 8 MB. No documentation exists.

## <a id="census"></a>Vanilla's scale (V)

| | Commonwealth exterior | Interiors |
|---|---|---|
| Cells with `XCRI` | 4,160 of 36,865 (4,707 hold any refs) | 313 of 1,195 |
| Combined meshes per cell, median / p90 / max | 22 / 40 / 138 | 37 / 163 / 645 |
| Combined refs per cell, median / p90 / max | 70 / 303 / 3,127 | 451 / 3,203 / 8,704 |
| Share of placed refs combined | 88% | 69% |

- **What gets combined:** only STAT (96.4%) and SCOL (3.6%) references.
  Never a light, moving static, furniture or item.
- **Previs clusters:** 717 exterior `.uvd` files, 715 of them 3×3 blocks
  named after the center cell, whose grid x and y are both multiples
  of 3. Member cells point `RVIS` at the center.
- **Files:** 120,387 `_OC` NIFs (1.33 GB) and 4,484 physics NIFs in
  `Fallout4 - MeshesExtra.ba2`, plus 966 `.uvd` (962 MB). The DLCs follow
  the same pattern.
- **Overrides re-list everything.** A DLC or CC cell override writes a
  full new `XCRI` that includes vanilla's refs; DLCRobot's exterior
  overrides list 32,829 refs, 330 of them its own.
- **The installed load order:** of 87 mods only the Unofficial Fallout 4
  Patch carries this data (1,425 cell overrides, one precombined NIF).

## <a id="runtime"></a>How the game uses them (V unless marked)

Read statically from `Fallout4.exe.unpacked.exe` 1.11.240.

- **Loading the fields.** `TESObjectCELL::Load` (0x4C2780) keeps `PCMB`
  at +0xEE, `VISI` at +0xEC, `RVIS` at +0xE8; `XCRI` becomes
  ExtraCombinedRefs (0xC5), `XPRI` ExtraPreVisRefs (0x15). A later
  override's `XCRI` replaces the earlier one.
- **A combined ref draws nothing itself.** `TESObjectCELL::AddReference`
  (0x4E8AF0) diverts a ref whose FormID is in the cell's `XCRI` (when
  `bUseCombinedObjects:General` is on and the ref is not persistent): it
  never joins the cell's list and never loads its own 3D (0x4C9520,
  0x4CBB20). The match is by FormID only; nothing compares position,
  scale or enable state.
- **A non-ESM winning override** (0x4C3580 → 0x4C9660) puts the diverted
  refs back on the cell's list, but they still load no 3D (I).
- **So edits to a combined ref don't show** (I, from the above): a moved,
  scaled, disabled or deleted ref keeps its baked look and collision. New
  refs a plugin adds are not in `XCRI` and draw normally. The CK wiki says
  the game switches both systems off for an edited area; the code doing
  that was not found.
- **A missing `_OC` NIF is skipped silently** (0x4C9C70 → 0x4CA163): its
  refs stay diverted, so they are invisible and have no collision (I,
  strong).
- **Previs** loads after the combined meshes (cell finish-load 0x4C7940).
  It is active only with `bPreCulledObjectsEnabled:General` and
  `bUsePreCulledObjects:Display` on and the player's cell having
  `VISI` ≠ 0, loaded vis data, and the player inside the tome's bounds
  (0x0D5A7C0, 0x21AE520). Otherwise culling falls back to the frustum and
  the authored rooms, portals and occlusion planes, which load
  independently (I).
- **Previs object ids:** an uncombined ref is known to previs only if it
  is in its cell's `XPRI`; a combined mesh's id is `0xFD000000 | (x & 31)
  << 19 | (y & 31) << 14 | index`, which caps a cell at 16,384 combined
  meshes (the CK's "too many precombined meshes" error).
- **Console:** `TogglePreCulling` (0x5FA430) switches previs; there is no
  console switch for precombines, only the ini's `bUseCombinedObjects`.

## <a id="ck"></a>The Creation Kit route (V)

Run from the command line (handler CK 0x489830, `bgsautomatedprocesses.cpp`),
on a plugin flagged ESM:

1. `-GeneratePreCombined:<plugin> clean all`: the `_OC` and physics NIFs,
   `<plugin> - Geometry.psg`, and `CombinedObjects.esp` (the new cell
   fields, merged into the plugin afterwards, by xEdit script in the
   community's tools).
2. `-CompressPSG:<plugin>`: `.psg` → `<plugin> - Geometry.csg`.
3. `-BuildCDX:<plugin>`: `<plugin>.cdx`.
4. `-GeneratePreVisData:<plugin> clean all`: `Vis\<plugin>\*.uvd` and
   `PreVis.esp`, merged the same way.

CKPE's `[PreCombined] bGenerateForPC` fixes the collision the CK writes
and should be on only for step 1 ("harmful to PreVis"). The CK ignores
material swaps; the community applies them first.

**What the CK leaves out** (collect predicate CK 0xD79F80; logged as
"Failed to collect ref" with `bOutputCollectObjectFailure:General`): any
base that isn't STAT or SCOL, and refs with no 3D, initially disabled,
havok animation, cloud, a non-occluder base (STAT flag 0x10), scripts, an
occlusion shape, a location ref type, linked refs either way, an enable
parent, attach refs, external emittance, a destructible base, a recipe,
dynamic havok, or no geometry.

**Existing tools:** PJM's scripts and the ModernPrecombines manual drive
those CK steps; the Previs Repair Pack is a full CK rebuild; xEdit's
"Disable PreVis" script sets the 0x80 flag and strips the fields.
**No open generator exists** for either system.

## <a id="density"></a>How dense FNV and FO3 are (V)

References per exterior cell that holds any, from the exports (scratch
`previs_density/density.py`) and the census:

| World | Cells | Median | p90 | Max |
|---|---|---|---|---|
| FO4 Commonwealth | 4,707 | 63 | 329 | 3,441 (Mass Fusion) |
| FO4 Diamond City location cells | 4 | 847 | – | 1,489 |
| FNV WastelandNV | 3,559 | 32 | 91 | 454 |
| FNV Freeside (north, south) | 41 each | 5–6 | 128–147 | 252 |
| FNV The Strip | 44 | 4 | 126 | 180 |
| FNV Lucky38World | 1 | – | – | 1,743 |
| FO3 Wasteland | 3,399 | 86 | 171 | 513 |
| FO3 DC ruins (DCworld05–18) | 30–109 | 3–16 | 95–172 | 332 |

FNV and FO3's densest cells sit near the Commonwealth's 90th percentile,
not its downtown. Goodsprings held the 118 cap with the GPU at 24%
([measured](../fo4_pipeline.md#region-measured)). FO3's Wasteland, at
2.7 times FNV's median, is where a need would show first.

## <a id="own-precombines"></a>Making precombines ourselves

Feasible from what is decoded; nothing here needs Umbra.

- **Embedded geometry.** Write `BSPackedCombinedGeomDataExtra` (geometry
  in the NIF), as the CK does before compressing. No `.csg` or `.cdx`
  needed (I: the engine reads both forms, per the CK's "both formats"
  check; not tried in game).
- **The key is ours to pick** (I). The engine uses it only to name the
  file and to look it up from `XCRI`; vanilla keys repeat across cells
  (2,867 of 12,845). A hash of our authored data per cell keeps builds
  byte-stable. The CK's own key rule is unknown.
- **Grouping:** the CK's exclusion list above, plus one mesh per shared
  material and texture set (I; the CK's real grouping rule is unknown).
- **Collision:** one hknp physics system per cell from the refs'
  collision, which our collision writer already makes per mesh.
- **The fields:** `XCRI` and `PCMB` on the cell.

**The catch: edits from other plugins stop showing.** Every converted mod
that moves, disables or deletes a combined static (Placement Fixes, the
FNV bug-fix plugins, YUP) would have its edit hidden. Because we convert
the whole load order, the fix is ours to make: bake precombines last over
the final load order into one patch plugin owning the winning `XCRI` for
every cell, as the Previs Repair Pack does. A light patch can't own them
([light plugins](fo4_light_plugins.md#problems)), but an override of
FalloutNV.esm's cells can, since the files follow the cell's owner.

## <a id="open"></a>Open questions

- How the game reacts to an override that drops `XCRI` (the wiki's
  "switch both off"), and who reads `PCMB` (no reader found).
- The CK's mesh key and grouping rules; `.cdx` field `a`; the two floats
  in the combined extra data; `CNAM`/`ZNAM`.
- Whether embedded-geometry NIFs work in the game without a `.csg` (the
  first thing to test before writing our own).
- Whether the CK runs headless on our plugin for previs, and how long it
  takes on WastelandNV.
- The `.uvd` tome itself: not to be written by us.
