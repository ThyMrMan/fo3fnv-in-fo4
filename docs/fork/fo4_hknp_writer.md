# Plan: our own FO4 physics writer in place of Elric (2026-11-11)

Status: step 1 (convex bodies) built and wired in, awaiting its play test; step 2 (triangle meshes
on fixed and massless keyframed bodies) built and wired in, awaiting its play test; step 3's spheres and
capsules built and wired in, awaiting their play test; step 3's compounds (lists) built and wired
in, awaiting their play test; step 4 (constraints and ragdolls) built and
wired in, awaiting its play test; the [last gaps](#gaps) (flat and thin shapes, phantom
triggers, motion 6) built, awaiting their play test. Status lives
in [ROADMAP.md](ROADMAP.md). Item 5 of the
[CK replacements](fo4_ck_replacements.md#options).

**Why.** Elric is the last Bethesda tool every mesh build runs. It writes
uninitialised bytes (162 of 946 files differed between two runs), deadlocks
above one instance, crashes on some input (those meshes ship without
collision), numbers ragdoll bodies at random, and needs the CK's Tools
folder, so it blocks the [cross-platform app](fo4_gui.md).

## <a id="have"></a>What we already have

- **The file format.** `havok/packfile.py` reads and `packfile_write.py`
  writes Havok 2014 packfiles from `data/hk2014_layouts.json` (370
  classes: every `hknp` one, and Bethesda's material table). Elric's convex-only physics systems come
  back byte for byte through them: 616 of 616 in a 3,000-entry sample of
  the Elric cache (`keep_order`).
- **The input.** `nif/collision.py` writes FNV's collision as FO4's
  pre-Elric blocks; every value Elric reads is ours to read back.
- **The answer key.** The Elric cache (`output/fo4_cache/elric`, 12,390
  entries) is keyed by the pre-Elric bytes, so converting a mesh again
  finds Elric's output for it without running Elric: 228 convex pairs
  from 600 clutter meshes in 12 s.
- **References.** NifSkope Wild Wasteland Edition's encoders
  ([tested](research/nifskope_wwe_test.md#verdict), BSD-3: keep its notice
  on ported code) and havok-formats (GPL-3.0, untested on FO4).
- **Elric's quirks**, recorded across the build docs: node transforms
  baked into the physics, `Head` written `HEAD`, layer-30 controllers made
  trigger bodies, random ragdoll order (`nif/ragdoll_order.py`).

## <a id="seam"></a>Where it goes

`nif/hknp_write.py` takes a pre-Elric NIF and returns the NIF Elric would
have made, or None for input it does not cover yet. `elric_cache.process`
asks it first and sends only the rest to Elric, so each step ships on its
own and `elric.finish`'s graft is unchanged (it grafts our finished NIF
as it would Elric's). Our output is not put in the Elric cache, and the
finished-NIF work cache (`elric_finish`) records `hknp_write` among the code
that ran, so a writer change refinishes the meshes it covers.

## <a id="steps"></a>Steps

| # | Covers | Done when |
|---|---|---|
| 1 | Convex bodies: `bhkConvexVerticesShape`, `bhkBoxShape`, a convex transform; static, dynamic and keyframed; one or several bodies | Every convex pair's objects equal Elric's (floats within tolerance), and a build plays in game |
| 2 | Triangle meshes: `hknpCompressedMeshShape` with per-triangle materials and `hknpBSMaterialProperties` (missing from our layouts: 2,285 of 3,000 cache entries hold it) | Same, on the mesh pairs; the game accepts our quantisation and tree |
| 3 | Spheres, capsules, compounds (`bhkListShape`) | Same |
| 4 | Constraints and ragdolls (`hknpRagdollData`, the hinge and ragdoll constraint data) | Creature skeletons, in game |

### <a id="queue"></a>Work queue

In order; each item starts when the one above is done. Code edits under
`fo4_import/` wait for the main session's go (no edits there while a
build queue runs); reading and scratch work don't.

1. ~~**Finish Step 1's hull.**~~ Done: read, built in
   `nif/hknp_hull.py`, and it beats the exact hull ([results](#hull-scratch)).
2. ~~**Turn the scratch comparison into a tool.**~~ Done:
   `tools/nif/hknp_compare.py` ([check](#check)).
3. ~~**Wire Step 1 in**~~ ahead of Elric in `elric_cache.process`: done
   after the user accepted the [drift](#convex-drift); the main session
   runs the play test.
4. ~~**Step 2, triangle meshes:**~~ built (`nif/hknp_mesh.py`) and wired
   in ahead of Elric ([mesh writer](#mesh-writer)); the main session runs
   the play test. A mesh on a body with a full motion (dynamic, or
   keyframed with mass) still goes to Elric.
5. **Step 3:** ~~spheres and capsules~~ built (`nif/hknp_round.py`) and
   wired in ([round](#round)); ~~compounds (`bhkListShape`)~~ built
   (`nif/hknp_compound.py`) and wired in ([compound](#compound)).
6. ~~**Step 4:**~~ constraints built (`nif/hknp_constraint.py`) and wired
   into `hknp_write` ([constraints](#constraints)); ragdolls built
   (`nif/hknp_ragdoll.py`) and wired into `rig/assets.write_skeleton_nif`
   ([ragdolls](#ragdolls)). The main session runs the play test.
7. ~~**The last gaps:**~~ flat and thin convex shapes, phantoms outside a
   skeleton, motion 6 ([gaps](#gaps)). The main session runs the play test.

## <a id="convex"></a>Step 1: what Elric writes for a convex body

Read off 228 convex pairs (600 clutter meshes); "Elric" below means its
output for our pre-Elric NIF.

- **Shape.** One `hknpConvexPolytopeShape` per body: flags 323, dispatch
  type 1, our convex radius, the material CRC in `userData`. Vertices are
  our hull's (a box's eight corners at its half extents, no radius taken
  off; a convex transform applied), each with `0x3F000000 | index` in its
  fourth word, the array padded to a multiple of four by repeating the last.
  One plane `(n, d)`, `n·x + d = 0`, per face, padded to a multiple of four;
  faces `(first index, count, min half angle)` with their loops counter-
  clockwise seen from outside; then the index bytes. Vertex and face order
  differ from ours (Elric's hull), which is the same shape.
- **Face angle byte** (Havok's rule, [read from Elric](#elric-code)): for
  each edge of another face with exactly one end on this face, the rise of
  its far end to its closest point on this face, `asin` of the smallest
  such sine, `trunc(angle × 255/π + 0.5)`. Box faces 128, a 45° bevel 64,
  a corner dropped by the 16-corner cap (below) 0.
- **At most 16 corners per face.** A face with more drops, one at a time,
  the corner spanning the least area with its two neighbours; the shape
  then loses flag `0x40` (323 becomes 259).
- **Mass properties** (`hknpShapeMassProperties` through an
  `hkRefCountedProperties` entry, key `0xF100`), density 1: the volume of
  the hull with every face plane pushed out by the convex radius (sharp
  corners; matches Elric to a median 4e-7, 95th percentile 6e-5); mass the
  same; the centre of mass of that hull; its principal inertia ×1.5 (median
  3.6e-5; the 1.5 is Havok's default mass-config inertia factor); the
  principal frame from Havok's float32 Jacobi, moments left in diagonal
  order. Vectors pack as three int16
  over `2^e` with `(e + 96) << 7` in the fourth; the frame packs each
  component as `0x8000 + floor(q × 30000)` (identity: `0xF530800080008000`,
  vanilla's commonest value). Elric ignores the inertia tensor we pass.
- **Bodies,** in collision object order: the filter word (layer, flags,
  group), quality 255, material index one per body (not shared). Position
  and orientation are the owner node's world transform, translation over
  69.99125; Elric ignores our body's own translation. Fixed: no motion,
  flags 0. Dynamic: flags 128, a motion with inverse mass `1/mass`,
  `massFactor = mass / volume`, inverse inertia `1/(principal × massFactor)`,
  the centre of mass, the principal frame, and one motion-properties entry
  (our damping as halves; max linear speed 104.375 whatever we pass;
  deactivation constants). Keyframed with mass (the fridge doors, 50): the
  dynamic motion, flags `0x10080`. Keyframed without mass (stall door, gate,
  tape machine): a motion with zero inverse mass, `massFactor` 1 and motion
  properties `65535` (the game's preset), flags 0, its centre of mass the
  body's position and its orientation the body's (all 43 such bodies in
  `clutter`, `furniture`, `dungeons`, `architecture`, `weapons`; writing
  the origin instead put door motions up to 1.6 Havok units off).
- **Material:** our friction (dynamic and static) and restitution as
  `hkHalf` (a float32's top 16 bits, rounded), welding tolerance 0.05, the
  rest constant.
- **Collision objects:** flags 128.

### <a id="convex-drift"></a>Built, and where it drifts from Elric

Built in `fo4_import/nif/hknp_hull.py` (Havok's hull simplification),
`fo4_import/nif/hknp_convex.py` (shape, mass properties) and
`fo4_import/nif/hknp_write.py` (bodies, motions, materials, the NIF
blocks); tests in `tests/test_fo4_hknp_write.py`. Wired in ahead of
Elric: `elric_cache.process` asks `hknp_write.finish` first and sends only
what it does not cover to the Elric cache and Elric. Covered: NIFs whose every collision is a
`bhkRigidBody(T)` with a box, convex-vertices or convex-transform shape;
anything with a constraint or a list shape falls back to Elric.

On the 228 pairs, 18 match Elric in every field (177 on every hull field,
221 on mass properties) and body placement matches
on all. What still differs, **accepted as drift by the user on
2026-11-12** ("yes, accept all four and wire it in";
[accept drift](research/fo4_target.md)). The play test watches round
objects (pool balls, barrels) rolling and settling:

- **Hull ties and rounding (51 shapes).** We run Havok's own
  simplification ([below](#elric-code)); 30 shapes still differ in corner
  or face count, mostly round ones (pool balls, bottles, fire ant eggs)
  where face pairs score exactly the same and Havok's triangle order,
  which we don't have, picks the first merge. 21 differ only in corner
  position, under one grid step. Mass and the motion follow the hull, so
  7 shapes differ there.
- **Face angle byte at exactly 90°.** Faces matched by normal: 1,101
  exact, 471 one apart at 127/128, 2 off by more (hull). Recomputed from
  Elric's own vertices the rule matches 2,232 of 2,360 faces and every
  miss is a 128 Elric wrote as 127: Havok's closest-point code divides
  with `rcpps`, the CPU's approximate reciprocal, so a corner exactly
  under an edge end lands on it or a hair inside depending on the edge
  length and the processor. Elric itself is not reproducible there across
  machines.
- **Principal frame on equal moments (2 shapes with a matching hull).**
  Havok's Jacobi turns 45° whenever float noise leaves any off-diagonal
  term above its threshold; which way the noise falls depends on Havok's
  own float32 integration of the hull.
- **Max angular speed (2 barrels).** Elric writes 549.25 for our 514.1; the
  other 226 pairs match the 12-bit rounding. Not read yet.

<a id="clutter-census"></a>**All of FNV `clutter`** (`hknp_compare`,
tolerance 1e-4; 1,716 meshes: 679 pairs we cover, 672 Elric-only shapes,
313 without Havok, 50 not in the cache, 2 skinned corpses the static
converter rejects):

| Pairs | What differs |
|---|---|
| 121 | nothing |
| 360 | only face angle bytes, every one by 1 (the 90° case above) |
| 118 | hull corner or face counts (ties; mass and motion follow) |
| 36 | hull corner positions or planes only, under a grid step |
| 41 | hull matches; mass properties or motion beyond 1e-4 (inverse inertia alone in 11; principal frame in 22) |
| 2 | max angular speed (the barrels) |
| 1 | restitution: Elric writes 0.9 (`0x3F666666`) as hkHalf `0x3F67`, not the nearest `0x3F66`; friction on the same body rounds to nearest. Not read yet |

Angle bytes off by more than 1 (17 pairs) are all on hulls whose face
counts differ, so faces are paired across different hulls.

**`furniture`, `dungeons`, `architecture`, `weapons`** (5,359 meshes, 420
pairs we cover, 4 min): 65 match every field, 192 more only in angle
bytes; the rest are the accepted hull, mass and frame drift, plus the
throwing axe's body orientation 1.1e-4 off in one component (not read).

**Flat shapes** were left to Elric at this step; they are written now
([flat](#flat)).

### <a id="elric-code"></a>Read from Elric's code

`Elrich.exe` is a 117 KB .NET front end; the work is in
`ElricInterop.dll` (12.9 MB, 32-bit x86, Havok 2014.1 linked in, Havok's
source file names and assert strings intact). Elric converts the old
2012-style shapes with Havok's own `hkpPhysicsMigrationUtils`
(`0x10904af0`), which calls `hknpConvexShape::createFromVertices`
(`0x10180090`) and the polytope builder (`0x103bc7f0`). Read with
capstone (scratch scripts: string and absolute-address cross references,
linear disassembly); `tools/disasm/ob_xref_abs.py --exe` works on it too.
Read and re-implemented, never copied.

- **Build config** (defaults at `0x10180010`; the converter then clears
  `+0x04` and sets `+0x28`): `+0x00` simplification tolerance **0.01**,
  `+0x04` shrink by convex radius (**off** for converted shapes, which is
  why corners keep the radius in), `+0x0c/+0x0d` build mass properties and
  faces, `+0x10` mass config `{2, 1.5, -1}` (the 1.5 inertia factor),
  `+0x20` 80, `+0x24` at most **252** vertices.
- **Polytope builder** `0x103bc7f0`: simplifies the hull at the tolerance
  (`0x10396c40`, vertex cap 65535), again at `min(tolerance, 2^-23)` with
  the 252 cap if still over it; skips both when the hull has degenerate
  triangles (a warning). Faces over 16 corners are cut by `0x103bd650`;
  each face's angle byte comes from `0x103bd870`; flag `0x40` is set when
  no face was cut.
- **Mass properties:** `hkgpConvexHull::buildMassProperties`
  (`0x103a2700`) diagonalizes with `hkMatrix3::diagonalizeSymmetric`
  (`0x10178450`: Jacobi on the largest off-diagonal term, at most 128
  steps, epsilon `2^-23`, no sorting), transposes and converts to a
  quaternion (`0x1013cd40`).
- **Hull simplification is two passes,** both on Havok's own hull
  (`hkgpConvexHull`), which works on points snapped to a ±8191 integer
  grid with 64-bit integer plane tests, so its faces are exactly coplanar
  groups on that grid. Elric feeds it FNV's original vertex list
  (`getOriginalVertices`, `0x10967440`), not the plane list we build from.
  1. **Vertex pass** `0x10396c40`, read in full: quadric edge collapse
     (Garland–Heckbert). Tolerance `min(0.01, half the hull's smallest
     extent)`. Each hull vertex sums `p·pᵀ` over its distinct touching
     planes (equal within `√2⁻²³ ≈ 3.45e-4`). Candidates are edges between
     triangles on different planes. An edge's new point is the quadric
     optimum when the 4×4 system inverts cleanly and the point lies inside
     every original plane grown by the tolerance, else the midpoint; cost
     `vᵀQv`. The cheapest edge collapses (first on a tie: the larger index
     goes, the smaller moves to the new point, quadrics add) while more
     vertices than the cap remain, or while the cost is under `tolerance²`
     and more than 6 edges remain. The surviving points are hulled again.
     This is what cuts the corners off small shapes (jet: 12 corners to 8).
  2. **Plane pass** `0x10398870`, read in full, run after the vertex pass
     when the hull is 3-D, with the same 0.01:
     - *Size.* `S` = sphericity (`(36π)^⅓ V^⅔ / A`, `0x1039e080`) × the
       smallest half extent of the hull's oriented box (`0x1039db20` →
       `0x103ad620`: of the boxes aligned to each hull face, the one of
       least volume). Merging stops once the cheapest score reaches
       `min(2 × tolerance, S)`.
     - *Pairs.* One directed pair `(a, b)` per pair of different planes
       that share a hull edge, in triangle order. Its cost is the deepest
       any corner of face `a` sits below plane `b` (at least 0); its score
       is cost ÷ `nₐ·n_b`, or never (2⁶⁴) when the cost exceeds `S` or the
       dot product is under `2⁻²³`.
     - *Merge.* Take the lowest score (first on a tie). With `w =
       cost(a,b) / (cost(a,b) + cost(b,a))`, plane `a` becomes `w·a +
       (1−w)·b`, normalized on its normal, with its offset pulled in to
       the farthest hull vertex if it lies beyond it; `b` is dropped. Both
       directions of the pair are retired. Every pair that named `b` now
       names `a`, duplicates go, and each pair touching `a` adds the
       merged score to its cost and is rescored with the new normals
       (costs are not re-measured from vertices).
     - *Rebuild* (`0x103962e0`): the surviving planes are intersected
       three at a time in float32, points within 1e-5 welded, and hulled
       again (so on a fresh grid); under 4 planes keeps the old hull.
  3. **Integer grid** (`0x103af380`): per axis, centre and half size of
     the points' box (half at least 1e-5); a point becomes
     `(p − centre) × 8191 / half`, rounded half away from zero, and is read
     back as `q × half / 8191 + centre`.
  4. **Degenerate skip** (`0x103bd7b0` → `0x105d5540`; the converter's
     config `+0x28` turns it on): if any hull triangle's squared cross
     product is under 1e-7 (absolute, so small shapes trip it) or its
     `|u|²|v|² − (u·v)²` is exactly 0, both passes are skipped and the
     exact hull is kept (the drinking glass: all 36 FNV points).

  <a id="hull-scratch"></a>**Result** (`nif/hknp_hull.py`, fed FNV's
  original vertex list; a box is its 8 corners, as Elric's migration
  makes it). On the 228 pairs:

  | | Exact FNV hull (before) | Havok's simplification |
  |---|---|---|
  | Every hull field matches Elric | 109 | 177 |
  | Mass properties match | 191 | 221 |
  | All fields but angle byte and axis | 108 | 172 |
  | Face count differs | 41 | 23 |

  The 177 include taking each corner's faces from the planes that made it
  (scipy's `dual_facets`) instead of the 1e-5 on-plane test, which fixes
  all 13 playing cards: they are 1.4e-6 thick, so with the old test both
  layers landed on each big face. Of the 51 left, 21
  differ only in corner position, under one grid step (ammo box: 2–3e-5,
  from the float32 rebuild); 30 differ in counts, mostly round shapes
  (7 pool balls, bottles, fire ant eggs) where several pairs score
  exactly the same and Havok's triangle order picks which merges first.
  We use half the hull's least width for the oriented box's smallest half
  extent. The vertex cap (252, a second vertex pass) is ported but no pair
  reaches it.
- **Not read yet:** Havok's triangle order (ties on round shapes), the
  oriented box fit (`0x103ad800`), the max-angular-speed path, and
  the compressed-mesh builder ([mesh](#mesh)).

## <a id="mesh"></a>Step 2: what Elric writes for a triangle mesh

Read off 654 mesh pairs (FNV `clutter` and `architecture/barrier`: every
mesh whose Elric output holds an `hknpCompressedMeshShape`). Our input is a
`bhkNiTriStripsShape` with one `NiTriStripsData` per material, each strip
with its own collision filter (`collision.py`).

- <a id="bs-material"></a>**`hknpBSMaterialProperties`** (Bethesda's
  class, signature `0xa3e47a9a`; no Havok class description has it, and
  Elric registers its classes in code rather than static tables, so the
  layout is read off the data): an `hkReferencedObject`, then one array at
  +0x10 of 0x18-byte entries, one per input strip in strip order: 16 bytes
  always zero, the strip's collision filter (u32), its material CRC (u32).
  All 654 pairs match that exactly (two list a body's tables in another
  object order). Over 1,500 cache entries (2,509 tables, 1 to 9 entries)
  the zero bytes never vary; the filter is the layer alone in 86%, else a
  layer with flag bits (`0x2001`, `0x8001`). Added to
  `tools/generators/hk2014_layouts.py` (`BETHESDA`) and our layouts as
  `hknpBSMaterialProperties` / `hknpBSMaterial` (`reserved`,
  `collisionFilterInfo`, `materialCrc`). With it every one of the 654
  pairs' physics systems reads and writes back byte for byte
  (`packfile_write`, `keep_order`).
- **The shape** (701 compressed meshes in 650 pairs; 4 pairs have a
  different number of mesh bodies than we sent, not read yet): flags 516,
  dispatch type 2, convex radius 0, `numShapeKeyBits` equal to the tree's
  `bitsPerKey`, `userData` a first strip's material CRC (all 701), the material
  table through an `hkRefCountedProperties` entry with key `0xF601`. Edge
  welding map empty; the `hkcdSimdTree` two empty nodes (bounds ±FLT_MAX).
- **Tree box:** the input points' bounding box, nothing added (99.3% within
  1e-5; the rest are bodies paired in the wrong order by the census).
- **Quantization:** a section's vertices pack 11/11/10 bits;
  `codecParms` is (offset, scale) per axis. In a one-section mesh the
  offset is the box minimum and the scale its extent over 2047, 2047, 1023
  (exact to float rounding), and a vertex is `round((p − offset) / scale)`
  (98.4% of 15,692 points; floor gives 15%). In a mesh of several
  sections, 31% of sections' codecs differ from the section's own box,
  which is the tree's quantized node box rather than its vertices'; not
  read yet. 118 meshes also use shared vertices (21/21/22 bits over the
  tree box).
- **Primitives:** four indices each, a triangle repeating its third (index
  2 = 3); Elric pairs triangles into quads, two shape keys each, so the
  triangle count is unchanged (99.1% of meshes). `bitsPerKey` is the bit
  length of `maxKeyValue` in 650 of 701 (one more in 51; not read).
  Up to 210 packed vertices per section (median 26); 83% of meshes are one
  section.
- **Elric's random bytes:** `quadIsFlat` and `triangleIsInterior` are
  `hkBitField`s whose last word carries junk above `numBits` (532 of 661
  and 308 of 635 such words): the uninitialised bytes behind Elric's
  run-to-run differences. Our mesh writer will zero them.
- **Quad pairing** (495 one-section meshes without shared vertices,
  input triangles matched to primitives by their packed corners): 16,018
  of 16,163 quads are two input triangles `(a, b, c)` and `(a, c, d)`
  joined on the `a–c` diagonal; 14,710 of those are consecutive input
  triangles, the rest up to dozens apart, so the pairing searches
  neighbours rather than taking the next triangle. 2,824 triangles stay
  single. Primitives come out in tree order, not input order (491 of 495
  meshes).
- <a id="cms-builder"></a>**The builder in `ElricInterop.dll`.** The
  section encoder is the function holding the `Promoted … vertices in
  order to comply with compression error constraint.` message (loop at
  `0x10260a30`, inside a build function starting before `0x1026056b`); the
  statistics printer (`Number of sections`, `Quads: …`) is `0x1025c061`.
  Read so far: for each primitive corner, `t = clamp((p − min) × r, 0, 1)`
  per axis against the section box, where `r` is the box extent's
  reciprocal by `rcpps` plus one Newton step (`r(2 − e·r)`, zero on a
  flat axis); the packed value is `trunc(t × N + 0.5)` (N = 2047, 2047,
  1023) through `fistp` with truncation; the decoded corner is
  `min + q/N × extent`, and a corner whose decoded distance from the
  original exceeds the cinfo's error tolerance (config `+0x28`, checked
  only when below FLT_MAX) is promoted to a shared vertex. Shared vertices
  are mostly corners used by several sections (1,262 in the pairs, many
  with no packing error at all), so promotion is the lesser source. As
  with the face angle byte, `rcpps` makes exact ties CPU-dependent.
- **Keys and bit fields** (708 meshes): `numPrimitiveKeys` is the triangle
  count (707; the other is a junk primitive, below), not `maxKeyValue + 1`;
  `quadIsFlat` holds `(maxKeyValue + 2) / 2` bits and `triangleIsInterior`
  `maxKeyValue + 1` (708 each).
- **One junk primitive:** `dumptruck01` has a primitive `[222, 173, 222,
  173]` in a 51-vertex section (1 of 1,016 sections); `hknp_mesh.triangles`
  skips a primitive naming a vertex its section lacks.
- **Not read:** the tolerance Elric passes, how it splits sections, its node
  boxes, which neighbour a triangle pairs with, and `triangleIsInterior`'s
  meaning. The writer takes WWE's choices for these instead (zero interior
  bits, as WWE writes and the game accepts), and is checked by the triangles
  it decodes to.

### <a id="mesh-writer"></a>Built, and how it compares with Elric

`nif/hknp_mesh.py` ports WWE's encoder (`src/gl/hknpencode.cpp`; its
BSD-3 notice is `nif/NIFSKOPE_LICENSE.txt`), with Elric's details where the
census reads them:

- **Input:** each `NiTriStripsData` strip's points over Elric's 69.99125
  game units per Havok unit; one material-table entry per strip (filter,
  CRC), the shape's `userData` the first strip's CRC.
- **Quads:** in triangle order, each unused triangle takes the unused
  triangle of its own strip across a shared edge (opposite direction,
  different third corner) whose normal is closest to its own, when the
  quad they make is flat and convex; stored `(a, b, c, d)` read back as
  `(a, b, c)` and `(a, c, d)`; a lone triangle repeats `c`. A quad is flat
  when `d` is within 0.01 of the first three's plane (Elric's rule,
  [above](#mesh)). The game collides a quad as the hull of its four
  corners, so any other pair is a solid the mesh does not have: WWE's
  pairing (any neighbour) closed the doorways of the craftsman and
  Goodsprings room kits and lidded `offrmmidstairsdown01`'s stairwell
  (play test 2026-11-13); Elric's output for those meshes has no such quad
  but 1-unit slivers.
- **Sections:** primitives sorted along the mesh's longest axis by their
  first three corners, cut at 128 primitives or 255 vertices; each
  section's own vertices (none shared), quantized as Elric does
  (`trunc(t × N + 0.5)` on the section box).
- **Trees:** both split at the median along the widest axis; each node's
  box coded as square-root insets of its parent's decoded box, rounded so
  the decoded box always holds its geometry (WWE adds 1e-6 instead). A
  section-tree node holds 15 bits over `hiData`/`loData`, the top one
  marking an inner node.
- **Data runs:** consecutive same-strip primitives; identical run lists
  shared between sections.

**Result** (`hknp_compare`, FNV `clutter` and `architecture/barrier`,
1,748 meshes, 1,327 pairs compared, mesh pairs included): every
compressed mesh but one decodes to Elric's triangles, strip for strip,
within one quantization step of the coarser tree; the exception is
`dumptruck01`, whose extra triangle on Elric's side is the junk primitive.
Over the 654 saved pairs, the median largest distance from Elric's
triangle is 2e-7 (the same packing), the largest 0.018 Havok units. The
writer takes 6 ms per mesh (median; 341 ms at most, 7.3 s for 648). It
writes no stray bits past a bit field's end, so its output is the same
on every run.

## <a id="round"></a>Step 3: spheres and capsules

Read off 25 pairs from FNV `clutter`, `weapons`, `furniture`, `dungeons`,
`architecture` and `effects` (every mesh whose pre-Elric NIF holds a
`bhkSphereShape` or `bhkCapsuleShape`: 104 capsules, 4 dynamic spheres,
98 dynamic capsules, most of them ragdoll parts). Neither shape gets a
mass-properties object (`properties` is null); Elric works a dynamic
body's mass out from the shape.

- **Sphere** (`hknpSphereShape`, flags 273): the convex radius is the
  input radius unchanged; four vertices, all the center (the convex
  transform's translation, else the origin), each tagged index 0. Mass: a
  solid sphere's volume; inertia 1.5 × 2/5 r² × volume on every axis
  (all 4).
- <a id="capsule"></a>**Capsule** (`hknpCapsuleShape`, flags 451, a
  polytope): `a` and `b` are the input end points (w 1). Elric takes 1% off
  the radius, and Havok takes 1% of the rest as a core box's padding, the
  remainder the convex radius: `r1 = R − R·0.01`, `pad = r1·0.01`,
  `convexRadius = r1 − pad`, all in float32 (99 of 104; the other five share
  one input radius yet come out as three different values, within 3e-8,
  so no rule of R reproduces them). The core is a box around the segment,
  one padding out on every side and past each end: corner `i` is end `a`
  (bit 0 set) or `b`, plus or minus `pad` along `e1` (bit 1) and `e2`
  (bit 2), where `u = (a − b)/|a − b|`, `e1` is Havok's perpendicular of
  `b − a` (its smallest component zeroed, the later axis on a tie, the
  other two swapped and the later of them negated), normalized, and
  `e2 = e1 × u` (all 104 within float32 rounding, 4.8e-7; the classic
  tie-to-the-earlier-axis rule gets 34). Faces always in the order `+e1,
  −e2, +e2, −e1, +u, −u`, loops `7 6 2 3`, `3 2 0 1`, `7 5 4 6`, `1 0 4 5`,
  `1 5 7 3`, `2 6 4 0`, angle byte 4; the two spare plane slots hold
  `(0, 0, 0, −FLT_MAX)` (all 208; a polytope's spare slots hold whatever
  was in memory). Mass (all 98 dynamic capsules): the analytic capsule of
  the convex radius over the segment `a–b` (volume `πr²L + 4/3 πr³`),
  inertia 1.5 × its axial and transverse moments, centered on the
  segment's middle, the tensor diagonalized by Havok's float32 Jacobi
  (`hknp_convex.principal`), which gives Elric's motion frame on all 98
  to 1e-5.

**Built:** `nif/hknp_round.py`; `hknp_write` takes a sphere or capsule on
any body, alone or under a `bhkConvexTransformShape` (the transform moves
the center or end points). Against all 104 capsules and 4 spheres in the
pairs: every convex radius equal, sphere shapes byte for byte, capsule
tails within float32 rounding (4.8e-7; signed zeros in plane normals
differ, and our tail runs 8 bytes of padding longer). `hknp_compare` on
the 25 meshes: 9 covered (the rest have constraints or lists), 6 match in
every field; the other three differ only in what Step 1 already records
(a restitution of 0.9 one hkHalf step below Elric's on `ball01` and
`tumbleweednv`; `globe01`'s convex body's hull).

## <a id="compound"></a>Step 3: lists (compounds)

Read off 51 pairs (every FNV mesh in `clutter`, `weapons`, `furniture`,
`dungeons` and `architecture` whose pre-Elric NIF holds a `bhkListShape`;
54 lists, each held directly by a rigid body). Elric writes an
`hknpDynamicCompoundShape` for every motion system (2, 3, 4 and 5 all seen):

- **Shape:** flags 4, dispatch type 2, convex radius 0, `userData` the
  list's material CRC, no properties, `isMutable` 1, an empty welding map,
  `shapeTagCodecInfo` 0xFFFFFFFF, `numShapeKeyBits` the bit length of the
  instance count (all 54).
- **Instances:** one per list child, in list order (48 of 48 single-list
  pairs). A `bhkConvexTransformShape` child puts its matrix in the
  instance and keeps its shape in its own frame (50 of 50 boxes, 25
  turned); any other child sits in place under the identity. Scale 1,
  both tags 65535, padding zero. The transform's w words are packed
  integers (`0x3F000000 |` value): column 0 `0x40`, column 1 zero, column
  2 the child's memory size (class plus tail rounded up to 16 on all 143
  polytopes; 0x90 on all 46 compressed meshes), column 3 the instance's
  leaf node.
- **Tree** (`hknpDynamicCompoundShapeData`): `2n + 1` nodes, node 0 and
  the last empty, root 1, `firstFree` `2n`; min.w packs the parent, max.w
  `child0 | child1 << 16`, a leaf `0 | instance << 16`; parents come
  before their children. A leaf box is the child's box placed by its
  instance (polytope corners ± convex radius; a mesh's domain). How
  Havok picks its splits is not read: we split at the median center on
  the longest axis, and the compare tool checks leaf boxes per instance,
  not the layout.
- **Bounds:** the union of the leaf boxes; min.w is the smallest leaf
  parent, packed (54 of 54), max.w 0.
- **Mass** (all 12 dynamic list bodies, exact): a solid box over the
  compound's bounds, centered in it, inertia 1.5 × the box's, no rotation,
  whatever the children (neither their summed masses nor their hull come
  near).

**Built:** `nif/hknp_compound.py`; `hknp_write` takes a list of convex
shapes (under a convex transform or not) and meshes on any body;
a list with a flat child still goes to Elric (one
pair, `vdnwallwindow01`). On the 51 pairs, 50 covered: 14 match in every
field; the instance words, sizes, bounds and motions match on all but
those that follow a child's hull. What still differs: the accepted Step 1
drift inside the children (the 90° angle byte on 27, hull ties on 9,
which move a leaf box and, on two dynamic bodies, the motion), and on 4
mesh children Elric drops some of the reverse-wound copies of our
double-sided triangles (every surface stays on both sides; standalone
meshes keep them all, so the rule is compound-only and not read).
FNV `clutter` plus `architecture/barrier`: 1,347 pairs compared (16 more
than before), 757 match in every field (753 before); none of the 679
clutter pairs compared at Step 1 differs in a field it matched then.

## <a id="constraints"></a>Step 4: constraints

Read off 25 pairs (every FNV mesh outside the creature skeletons whose
pre-Elric NIF holds a constraint: the skeleton clutter piles, hanging
lights, swinging-beam traps, the chandelier), 119 constraints. Our input is
`collision.py`'s `_joint`: a `<I2iI` head (2, body A block, body B block,
priority), side A's three axes and pivot, side B's, then the limits (a
ragdoll's cone, plane min and max, twist min and max, friction; a hinge's
min, max, friction) and a motor byte. Elric writes an
`hknpConstraintCinfo` (body ids, flags 0) and an
`hkpRagdollConstraintData` or `hkpLimitedHingeConstraintData` (`userData`
0, not in `referencedObjects`), all exact on 119 of 119:

- **Transforms:** each side's axes and pivot are its transform's columns,
  copied as they are (differences ≤3e-7). The w words are not zero: column
  0 holds the third axis's y, column 1 its x, columns 2 and 3 zero (238 of
  238 sides).
- **Constant atoms:** setup stabilization (enabled, impulses `FLT_MAX`,
  max angle 1.8e19) and the ball socket (velocity stabilization factor 48,
  breach impulse `FLT_MAX`).
- **Limits:** the input's angles in their atoms. Tau is 1.0 on a hinge and
  0.8 on a ragdoll's twist, cone and planes. The cone's min angle is −100
  (unused) with memory offset 56; the planes limit uses angle mode 1.
- **Friction:** the input's torque, over 1 axis on a hinge and 3 on a
  ragdoll. Motors: disabled; a hinge's slot is empty outside a ragdoll.
- **Order:** Elric writes the cinfos in random order; we write block order,
  and `hknp_compare` sorts both by (body A, body B).

**Quaternions follow Havok's rule.** A body's orientation from its matrix:
with a positive trace w is positive, otherwise the component of the
largest diagonal term is. Our old "w ≥ 0" rule flipped 24 constraint-pair
orientations; on clutter it fixes 6 fields and moves 4 clipboards' motion
orientation just over tolerance (1.2e-4, bodies that already follow hull
drift).

**Built:** `nif/hknp_constraint.py`; `hknp_write` writes ragdoll and
limited hinge constraints between its bodies, and leaves any other kind
(or one that names a body outside the system) to Elric. On the 25 pairs
every constraint field matches; what differs is `centerOfMassWorld.w`
(19 pairs: Elric leaves a nonzero leftover there that is neither input nor
a component of the local center of mass; we write 0), the Step 1 drift
(the 90° angle byte, small inertia drift on 4 bodies ≤0.6%, the
restitution half step, the chandelier's hull). FNV `clutter` plus
`architecture/barrier`: 1,367 compared (20 more meshes covered), 758 match
in every field.

## <a id="ragdolls"></a>Step 4: ragdolls

Read off 7 creature rig pairs (`rig/assets.write_skeleton_nif`'s input to
Elric, against the rig work cache). Elric turns a skeleton into a
`bhkRagdollSystem` (`hknpRagdollData`) and a `bhkPhysicsSystem` for the
phantoms:

- **The ragdoll** is the physics system of the rigid bodies and
  constraints, as above, plus a `skeleton` and an identity
  `boneToBodyMap`. Every constraint's motor slots name one shared
  `hkpPositionConstraintMotor` (type 1, force −1e6 to 100, tau 0.8, damping
  1, recovery velocities 5 and 0.2); the motors stay disabled.
- **The skeleton** (`hkaSkeleton`) has one unnamed bone per body.
  `parentIndices[A] = B` for each constraint (A, B), else −1 (7 of 7);
  `lockTranslation` 0 on a root bone, 1 on the rest. The reference pose is
  each body's place in its parent body's frame (translation, rotation,
  scale 1); the w lanes of its translation and scale hold leftovers, which
  the compare tool leaves out.
- **Phantoms:** the `bhkSimpleShapePhantom`s (CharacterController,
  CharacterBumper) become trigger bodies of their own system: their shape,
  their filter, flags 16, no motion, placed by their node, a material with
  flags 0x200000, trigger type 2, friction 16128, restitution 0.
- Collision objects are `bhkNPCollisionObject`s with flags 128 pointing at
  their system, as on every mesh.

**Built:** `nif/hknp_ragdoll.py`; `write_skeleton_nif` asks it first and
sends only what it does not cover to Elric. All 12 rigs in the table are
covered. End to end through `write_skeleton_nif` on the 7 cached rigs, the
ragdoll bones and the collision objects equal Elric's on all 7; the
fields that differ are `centerOfMassWorld.w` and, on 3, the 90° angle
byte.

## <a id="gaps"></a>The last gaps: flat shapes, phantoms, motion 6

A census of all 14,909 FNV meshes (each converted as the build does, then
asked of `hknp_write.physics`) found what our writer still left to Elric:
phantom triggers on 31 meshes (9 with an Elric entry: 7 traps, 2 trigger
boxes), two `bhkRigidBody`s with motion system 6 (`clutter/junk/woodplank01`
and `02`), and 11 meshes with a flat or thin convex shape. None of them had
a flat shape on a body that moves with mass. All 44 are ours now, every
number finite.

- <a id="motion6"></a>**Motion 6** is Havok's thin-box-inertia dynamic
  body. Elric writes it as any dynamic body: both planks match except the
  usual inertia drift (≤0.05%) and one angle byte. `DYNAMIC` holds 2, 3
  and 6.
- <a id="phantoms"></a>**Phantoms outside a skeleton** join the mesh's one
  physics system as trigger bodies (the ragdoll's phantom body and
  material, [ragdolls](#ragdolls)) after its rigid bodies, in block order
  (all 7 traps with an Elric entry: mailbox bomb, grenade bouquet, bear
  trap, pressure plate, two tripwires, gas trap). 2 match in every field, 4
  differ only by one angle byte, the bear trap by its known hull drift. A
  phantom-only mesh
  (laser tripwire) is a system of triggers alone. Two trigger boxes
  (`triggers/trigactorbox03`, `trigplayerwall01`) carry FNV garbage
  (a box half size of 0xCDCDCDCD, ≈ −4.3e7); Elric's output for them is
  garbage too (mass ~1e33), so there is nothing to match.
- <a id="flat"></a>**Flat and thin convex shapes.** Elric runs every
  convex shape through Havok's hull, which works on the integer grid
  ([elric-code](#elric-code)), and three cases follow:
  - *Planar on the grid* (the points' grid steps lie exactly in one
    plane: the Lucky 38 floor, ceiling and two mid floors, the sewer door,
    5 of the automat's 7 slats): an `hknpConvexShape` (flags 1), its
    vertices the input points as given, padded to 4 like a polytope's. Its
    mass properties are those of the fan of triangles from the first point
    in input order, an even surface of mass 2: so a quad listed as a bow
    tie (the mid floors) has its centre of mass a third of the way off its
    middle, exactly as Elric's. `mass` is 2, `volume` the fan's area times
    the convex radius. All 4 Lucky 38 pairs and the sewer door match in
    every field.
  - *Thinner than float precision but 3-D on the grid* (the metro pillar
    fence, a Lucky 38 corridor floor, the Nipton sign post, 2 automat
    slats): Qhull's float test may reject the hull, so `hknp_hull.convex_hull`
    takes the triangles from Qhull on the grid steps and the planes from
    the points. The plane pass leaves 2 planes, and under 4 Havok keeps the
    hull it had: a polytope of two back-to-back faces holding every corner.
    Havok pads a polytope under 4 faces to 4 by copying face 0's header
    before any angle byte is written, so the padding faces' angle bytes are
    left over memory (64, 63, 60, 59, 255 seen; the compare tool reads them
    as 0); their planes are (0, 0, 0, −1.8e19). The vertex pass collapses
    nothing on such a hull only because Havok computes an edge's cost
    vᵀQv in float32: on a hull 1.5e-8 thick the tolerance² is 1.4e-17 and
    float32 leaves ~1e-10 even on the plane; in float64 the sign post lost
    a corner. All 5 match in every field.
  - *Degenerate* (a hull triangle under the 1e-7 test): Havok skips both
    passes and keeps the exact hull, so the faces are the hull's own, each
    with the corners of its triangles, not rebuilt from the planes. That
    also fixed the corner count on 4 clipboards. The vault window
    (`dungeons/vaultruined/room/vdnwallwindow01`, a list child 1e-7 thick)
    matches but for its two big faces' corner lists (9 and 7 corners, Elric
    6 and 6: which triangles Havok's own triangulation puts on them is not
    read).
  - *Mass of a thin or degenerate hull whose faces do not close a solid*
    (`hknp_convex.closed`: the face normals do not surround the origin):
    the points' axis-aligned box grown by the convex radius, density 1,
    inertia × 1.5, as a solid box (fence, corridor floor, sign post, automat
    slats, vault window: all exact).
  - A flat or thin shape on a body with a full motion goes to Elric: none
    exist in FNV, and Elric's mass for one is unread.

On FNV `clutter` plus `architecture/barrier` none of the 724 pairs both
runs could compare differs in a field it matched before (643 more no longer
have an Elric entry, because other changes moved their pre-Elric bytes;
our writer covers them, the compare cannot check them). In FNV nothing
reaches Elric after this; what our writer would still refuse (a constraint
other than ragdoll and limited hinge, a flat shape on a moving body) does
not occur. Four meshes used to fail conversion before any physics (the
sentry turret skeletons and two explosions: `collision.py` read their Havok
actions as constraints, [fixed](fo4_pipeline.md#ragdolls)); all four now
convert and are ours. FO3 was not censused.

## <a id="check"></a>How each step is checked

`tests/` compare our objects with Elric's on a handful of pairs;
`tools/nif/hknp_compare.py` runs any set of meshes against the Elric cache
([catalogue](../reference/python_tools.md)): it converts each FNV mesh as
the build does, finds Elric's output by the pre-Elric bytes, and walks both
physics systems from the root through their pointers, so object names and
order don't count. A convex hull (a capsule's core box too) is compared as a set (corners paired by
position, faces by normal; angle bytes, offsets and corner counts on the
paired rows), a compressed mesh as the triangles it decodes to (per
strip, each corner allowed one quantization step of the coarser tree; key
bits and the two bit fields, which follow the tree's layout, left out),
packed mass properties unpacked, constraint cinfos sorted by their bodies,
a ragdoll compared with its skeleton (pose w lanes left out), and each
collision object's owner, system and body checked. FNV `clutter` runs in 33 s on 7 workers. Fields Elric derives (mass
properties, motion records, face angles) are matched to its values, and a
value we cannot reproduce exactly is recorded here with its spread. The
first in-game build of each step is a play test of the meshes it covers.
