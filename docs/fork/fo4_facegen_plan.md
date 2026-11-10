# Our own FaceGen heads, and FNV's hair

Plan, written 2026-11-10. Nothing here is built. To be read and decided
before work starts.

## <a id="goal"></a>Goal

Every converted NPC wears FNV's own face in Fallout 4: its full head shape,
its face colour and detail, and its own hairstyle and beard. Today the face
goes through FO4's sliders, and the hair is FO4's nearest match.

Two pieces, done in this order:

1. **Our own FaceGen heads.** We write the files the game draws per NPC,
   instead of the Creation Kit exporting them from slider values.
2. **FNV's hair as FO4 head parts.** Each FNV hairstyle and beard becomes an
   FO4 head part, used by those heads.

## <a id="today"></a>How faces work today

- The converted NPC record holds FO4 slider values: sculpt regions
  (FMRI/FMRS) for shape, tint layers and a skin tone for colour
  ([sculpt](fo4_spikes.md#spike-2-sculpt), [tints](fo4_spikes.md#spike-2-tints)).
- The CK exports what the game draws (`-ExportFaceGenData`, run through
  MO2; [facegen](fo4_spikes.md#spike-2-facegen)):
  - `Meshes\Actors\Character\FaceGenData\FaceGeom\<plugin>\<id>.nif`: every
    head part as a skinned BSSubIndexTriShape in one head-local frame;
  - `Textures\Actors\Character\FaceCustomization\<plugin>\<id>_d.dds`,
    `_msn.dds` and `_s.dds`, re-encoded at vanilla's sizes (`_d` and
    `_msn` BC1 1024, `_s` BC5 512;
    [sizes](fo4_pipeline.md#audit-fixes)).
- The sliders reach about 70% of an FNV face's shape (Doc: 56% → 69% → 70%
  with the CK in the loop) and about 11% of its colour variation. The rest
  is shape and colour FO4's systems cannot make, which is why converted
  faces read rounder and more generic than FNV's (Sgt Kilborn, 2026-11-09).
- Hair is chosen per NPC from FO4's own hairstyles: by name, then by style,
  then by drawn coverage ([hair styles](fo4_spikes.md#hair-styles)).
- The CK costs about 2 s per NPC, needs the MO2 profile, and is a
  Windows-only stage of the app.

## <a id="benefits"></a>What it would give

- **Full face shape**, 100% of FNV's by construction (the October bake, C1,
  showed this on Doc).
- **FNV's face colour and detail** as FNV draws it, not a tint-layer
  approximation.
- **FNV's own hairstyles and beards**, including mods' hairs; no
  nearest-match guessing.
- **No Creation Kit for faces:** no CK stage, no MO2 run, no CK crashes or
  timeouts. Works on a machine without the CK, which the
  [cross-platform app](fo4_gui.md) needs.
- **Repeatable and cacheable builds:** our own code, keyed like the other
  caches.

## <a id="not-included"></a>Not included

- **Bodies.** FNV has no per-NPC body shape: one body per race and sex, no
  weight slider. The one body link is skin colour, which the skin tone
  (QNAM) already carries to the body. Outfit and body replacers are the
  separate [CBBE and BodySlide](fo4_bodies_cbbe.md) plan.
- **Ghouls, super mutants, children** at first: they keep their current
  route until the human heads work.
- **The face-fit batch** (FNV's baked face textures as the colour source,
  the faster tint fit, unique fit answers). That comes first and stays:
  the record's slider values are the fallback the game uses whenever it
  rebuilds a face itself.

## <a id="phases"></a>Phases

### <a id="phase-1"></a>Phase 1: one head written by us, CK head beside it

Rebuild one CK-exported FaceGeom NIF ourselves, from the same inputs, and
compare.

- Read a CK export of a few NPCs (Doc, Kilborn, a female NPC) and list
  everything in it: the head parts and their extra parts, skin partitions
  and bone list, vertex format, segment data, shader and material paths,
  and the texture paths naming the plugin.
- Write the same file from the race's head part meshes and the NPC's head
  parts, with no shape change. Done when ours matches the CK's byte for byte
  apart from what the CK computes per NPC, and each difference is
  explained.
- Our FO4 NIF writer already rebuilds vanilla meshes byte for byte
  ([nif](fo4_spikes.md#spike-2-nif)), so most of the risk is assembling the
  parts the way the CK does, not the format.

### <a id="phase-2"></a>Phase 2: FNV's shape

- Move the head onto FNV's shape with the October bake
  (`fo4_import/face/bake.py`): FNV's mean head aligned to FO4's, each FO4
  vertex moved by FNV's displacement at its nearest point, the move faded to
  zero within 3 units of the body seam.
- Move every other head part by the same displacement field: eyes, mouth
  and teeth, brows, and FO4's hair and beard, so nothing floats or clips.
- Check facial expressions and lip sync in game. FO4 drives them through
  face bones and per-vertex morphs, which apply as offsets and should
  survive a changed rest shape, but this is unproven.
- Measure: shape captured against FNV's head (expect about 100%, as C1),
  and the seam distance at the neck (expect 0).

### <a id="phase-3"></a>Phase 3: FNV's face textures

- Write `_d` from FNV's own face colour: the race texture with the NPC's
  baked FNV face texture (`textures\characters\facemods\<plugin>\<id>_0.dds`,
  3,049 in FalloutNV.esm) laid onto FO4's UVs through the head alignment
  (`fo4_import/face/texture.py` already maps FNV colour onto FO4 texels).
- The hairline: the October tests showed a step where FNV's colour meets
  FO4's own skin parts (the rear head, the hairline strip). Owning every
  part of the head lets the blend run across them; the overall colour stays
  in the skin tone, which the game applies to face, hairline and body
  alike.
- `_msn` (model-space normals) recomputed for the new shape, with FO4's
  detail normals kept; `_s` from FO4's.
- Guard against the "dark face" problem: FO4 draws a face dark when its
  FaceGen textures and record disagree. Each NPC's files and record are
  written by the same build, and a check lists any NPC whose FaceGeom NIF
  or textures are missing or older than its record.

### <a id="phase-4"></a>Phase 4: FNV's hair and beards

How the games differ:

| | FNV | FO4 |
|---|---|---|
| Record | `HAIR` (67 in FalloutNV.esm): a mesh and a texture; beards and brows are head-part meshes | `HDPT` head part with extra parts (hairline, rear), a valid-race list and a material |
| Follows the face | FaceGen morphs (`.egm`, 164 under `meshes\characters\hair`; `.tri` for 21) | Skinned to the head's bones, `.tri` morphs for the face sliders, baked into the FaceGeom NIF |
| Colour | Hair shader: texture × 2 × the NPC's `HCLR` at full vertex green ([hair colour](fo4_spikes.md#spike-2-hair)) | Grayscale texture looked up in `haircolor_lgrad_d.dds`; the NPC names a `CLFM` hair colour |
| Material | NIF shader flags, alpha test | `.bgsm` with hair settings |

Steps:

- Convert each FNV hair and beard mesh to an FO4 head-part mesh, skinned to
  the head bones, moved from FNV's head onto FO4's with the same alignment.
- Colour: FNV's hair textures are mostly grayscale tinted by `HCLR`, which
  fits FO4's gradient. Each distinct FNV hair colour becomes its own `CLFM`
  if the gradient can carry it, else the nearest FO4 row; measured on the
  NPCs before choosing.
- One `HDPT` per hairstyle and beard, valid for the human races, with a
  `.bgsm`. The hairline extra part: FO4's closest by shape, or none where
  the phase 3 face texture already covers the hairline.
- `.tri` slider morphs only if needed. With our own heads the hair is baked
  onto the exact head, so the sliders matter only when the game rebuilds a
  face itself.
- The NPC record names the converted head part; the coverage match stays as
  the fallback for an FNV hair that fails to convert.

### <a id="phase-5"></a>Phase 5: the build and the app

- A build stage replaces the CK FaceGen stage, cached per NPC like the face
  fits (keyed on the NPC's face fields, head parts and the code).
- Stale files pruned as today (`facegen.prune`).
- The CK export stays available behind an option for comparison until the
  heads are played.
- The app drops the CK requirement for faces.

## <a id="risks"></a>Unknowns to settle first

- **When the game uses our files.** It draws the FaceGeom NIF when one
  exists. Which cases rebuild a face from the record instead (LooksMenu,
  missing files, some scripted changes) decides how much the slider fallback
  still shows.
- **Expressions and lip sync** on a reshaped head (phase 2).
- **Hair clipping** on headgear: FO4's hats hide hair through biped slots
  and head-part flags, which converted hair must set the same way.
- **The CK's per-NPC computed data** in the FaceGeom NIF (phase 1). If
  anything there can't be reproduced, a hybrid stays possible: the CK
  exports the head, and we only move its vertices and rewrite its textures,
  as the October bake did.

## <a id="checks"></a>How each phase is checked

- Byte comparison against the CK's export (phase 1).
- Measured shape and colour capture against FNV, on Doc, Kilborn and a
  sample of female, old and child NPCs.
- Side-by-side screenshots against FNV.
- A play test of each phase on the same NPCs before the next phase starts.

## <a id="order"></a>Order and size

After the face-fit batch, in the order above. Phases 1 to 3 are the large
part, about the size of a full pipeline stage. Phase 4 is about the size of
the clothing conversion. Each phase is useful on its own: phase 2 alone
fixes the generic face shapes.
