# Plan: our own FO4 physics writer in place of Elric (2026-11-11)

Status: step 1 (convex bodies) being built; the rest planned. Status lives
in [ROADMAP.md](ROADMAP.md). Item 5 of the
[CK replacements](fo4_ck_replacements.md#options).

**Why.** Elric is the last Bethesda tool every mesh build runs. It writes
uninitialised bytes (162 of 946 files differed between two runs), deadlocks
above one instance, crashes on some input (those meshes ship without
collision), numbers ragdoll bodies at random, and needs the CK's Tools
folder, so it blocks the [cross-platform app](fo4_gui.md).

## <a id="have"></a>What we already have

- **The file format.** `havok/packfile.py` reads and `packfile_write.py`
  writes Havok 2014 packfiles from `data/hk2014_layouts.json` (368
  classes, every `hknp` one). Elric's convex-only physics systems come
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
own and `elric.finish`'s graft is unchanged. Wiring waits for the main
session's commit (it owns the pipeline files).

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
2. **Turn the scratch comparison into a tool** (`tools/`): our writer
   against Elric's cache, field by field, over any set of pairs. Steps 2–4
   need it.
3. **Wire Step 1 in** ahead of Elric in `elric_cache.process`, after the
   user rules on the [drift](#convex-drift); the main session runs the play
   test.
4. **Step 2, triangle meshes:** add `hknpBSMaterialProperties` to our
   class layouts, decode Elric's compressed mesh pairs, then read Havok's
   mesh-shape builder in `ElricInterop.dll` for its quantization and tree.
5. **Steps 3 and 4** in table order.

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
  properties `65535` (the game's preset), flags 0.
- **Material:** our friction (dynamic and static) and restitution as
  `hkHalf` (a float32's top 16 bits, rounded), welding tolerance 0.05, the
  rest constant.
- **Collision objects:** flags 128.

### <a id="convex-drift"></a>Built, and where it drifts from Elric

Built in `fo4_import/nif/hknp_hull.py` (Havok's hull simplification),
`fo4_import/nif/hknp_convex.py` (shape, mass properties) and
`fo4_import/nif/hknp_write.py` (bodies, motions, materials, the NIF
blocks); tests in `tests/test_fo4_hknp_write.py`. Not wired into
`elric_cache.process` yet. Covered: NIFs whose every collision is a
`bhkRigidBody(T)` with a box, convex-vertices or convex-transform shape;
anything with a constraint or a list shape falls back to Elric.

On the 228 pairs, 18 match Elric in every field (177 on every hull field,
221 on mass properties) and body placement matches
on all. What still differs, proposed as accepted drift
([accept drift](research/fo4_target.md)) and awaiting the user's decision:

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
  anything for compressed meshes.

## <a id="check"></a>How each step is checked

`tests/` compare our objects with Elric's on a handful of pairs; a scratch
census runs every pair in the cache. Fields Elric derives (mass
properties, motion records, face angles) are matched to its values, and a
value we cannot reproduce exactly is recorded here with its spread. The
first in-game build of each step is a play test of the meshes it covers.
