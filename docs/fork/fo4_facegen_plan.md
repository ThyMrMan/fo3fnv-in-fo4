# Our own FaceGen heads, and FNV's hair

Plan, written 2026-11-10. Nothing here is built. To be read and decided
before work starts. [Willow's diagnosis](#willow) fixed two bugs in the
slider route and led to the [revisit](#direct) framing the plan around
mods' own characters.

## <a id="goal"></a>Goal

Every converted NPC wears FNV's own face in Fallout 4: its full head shape,
its face colour and detail, and its own hairstyle and beard. Today the face
goes through FO4's sliders, and the hair is FO4's nearest match.

Two pieces, done in this order:

1. **Our own FaceGen heads.** We write the files the game draws per NPC,
   instead of the Creation Kit exporting them from slider values.
2. **FNV's hair as FO4 head parts.** Each FNV hairstyle and beard becomes an
   FO4 head part, used by those heads.

## <a id="willow"></a>What went wrong with Willow (2026-11-10)

NVWillow's Willow came out of the FO4 build as an older woman: wrinkled
skin, a rounder face, and a straight bob. Her FNV data: her own race
(`WillowRace`) whose female head mesh is FNV's stock `headfemale.nif`
(0.000 surface distance, measured) with the male head's `.egm`/`.tri` beside
it and no `.egt`, her own head skin (`characters\willow race\headhuman.dds`,
2048 px), her own hair (`WillowAlita`, `hairwillowalita.nif`) and eyes. Each
symptom has its own cause:

| Symptom | Cause | Kind |
|---|---|---|
| Aged, wrinkled skin | <a id="body-skin"></a>Every converted woman is a copy of Fallout4.esm's `DoctorAmari` (the `human_female` body rule), and her face texture set `FTST = SkinHeadFemaleOld` stayed on the copy. Men copy `DocWeathers`, who has none. The face fit never touched FTST. | Bug, fixed: a fitted copy drops the body's FTST, so the face uses HumanRace's default (`SkinHeadFemaleHero`), as the men's already did. |
| Her skin colour lost | <a id="race-skin"></a>The colour fit (variant T1) carried only the NPC's `.egt` offset onto FO4's own skin and threw the race's head texture away. Willow has no `.egt`, so her target was all zero: no tint layers, skin tone ×1.0 (Cass, a vanilla woman, gets 19 layers and a tone). The same loss hit 803 FalloutNV.esm NPCs on races with their own head skin (raiders' grime: 529; the Old and OldAged races: 211; children and ghouls are not fitted). | Bug, fixed: the race's skin minus FNV's stock skin of that sex (`characters\<sex>\headhuman.dds`, which every playable race uses) is added to the face texture the tint layers are fitted to, after the skin tone is taken. It never moves the tone: FO4's tone colours the body too, and FNV's body takes FaceGen colour (the race's body `.egt`) but not the head texture. With it in the tone, a Viper leader's tone fell to ×0.47/0.30/0.18; split, every sampled tone is unchanged. |
| Rounder face | The 28 sculpt regions captured 90.6% of her FaceGen shape (Cass: 90.9%), many controls pinned at ±1. Her head mesh is stock, so nothing was lost reading it. The rest is shape FO4's sliders cannot make. | Limit of the slider route; the [plan below](#direct) removes it. |
| A bob instead of her hair | Her hair is the mod's own; no FO4 hair shares its name or style group, so the coverage matcher picked the nearest FO4 cut (`HairFemale15`, colour `HairColor19DirtyBlond`). | Limit of the slider route ([phase 4](#phase-4)). |
| Shape and colour drawn by the game, not baked | Her build ran no FaceGen stage (`spike.facegen`), so FO4 built her head from the record at run time. | Build step, not code. |

Not a cause: her race's FaceGen data is read correctly (the race's own
head, `.egm` and skin are the ones `fnv_npc` resolves), and the eyes match
(`FemaleEyesHumanBlue`).

Blast radius of the race-skin fix, two NPCs per race kind, tint fit before
→ after (share of the target captured; skin tone identical in all twelve):

| NPC (race) | Target, mean \|Δ\| /255 | Captured | Layers |
|---|---|---|---|
| NVMerchantMale (HispanicOld) | 6.1 → 8.9 | 34% → 26% | 17 → 25 |
| VStreetSS6Gambler01 (AfricanAmericanOld) | 5.6 → 7.7 | 20% → 23% | 26 → 25 |
| VStreetSS6Traveler02 (CaucasianOld, F) | 9.1 → 10.0 | 7% → 20% | 22 → 26 |
| VES09MerchantFem04 (AsianOld, F) | 0.2 → 5.7 | 0% → 34% | 3 → 23 |
| Narrator (CaucasianOldAged) | 6.4 → 17.5 | 22% → 31% | 20 → 29 |
| VFSGrannyGanger2 (CaucasianOldAged, F) | 8.6 → 10.0 | 9% → 11% | 19 → 21 |
| VFSGrannyGanger3 (CaucasianOldAged, F) | 8.5 → 10.0 | 2% → 6% | 22 → 24 |
| VViperGangLeaderMalePers (CaucasianRaider) | 5.4 → 54.3 | 23% → 40% | 23 → 35 |
| VViperGangLeaderFemalePers (CaucasianRaider, F) | 14.4 → 42.4 | 16% → 24% | 22 → 31 |
| Willow (WillowRace, F) | 0 → nonzero | 0% → 12% | 0 → 20 |

Raiders now wear their grime as tint layers on the face. FNV's raider races
have dirty bodies too (`Characters\Raider\UpperBodyMale.dds`), which FO4's
clean bodies don't carry, so the grime stops at the face, as it does on
FO4's own dirt-tinted raiders. A stock-skin face is bit for bit unchanged
(three of the six fit-version references; the other three are on Old and
OldAged races). `FIT_VERSION` is 2: every face refits once, and published
fit files of version 1 no longer install.

The female tint basis was measured on a copy of Amari with her old skin. At
the fit's 256 px working size the two skins differ by 2.35/255 on average
(95th percentile 6.6), against 4.8 for a typical face's target (Cass), so the
basis still serves; a female tint recalibration
(`sculpt_calibration --what tints --female`) brings it in line, and the
calibration template now drops FTST too.

## <a id="direct"></a>Revisited: characters from their own data and assets

Revisited 2026-11-10 after Willow. The phases below stay; this section
reframes them around a mod's characters. Today a face reaches FO4 through
FO4's presets: sculpt sliders for shape, tint layers for colour, the nearest
FO4 hair. Whatever a mod authored that FO4 has no preset for is lost. The
direct route converts what the NPC and its race actually name:

| FNV authored source | FO4 output | Existing code | Today instead |
|---|---|---|---|
| The race's head mesh (a mod's own included) plus the NPC's FaceGen shape (FGGS/FGGA through the head's `.egm`) | The NPC's FaceGeom NIF, FO4's head with FNV's shape baked in, every part moved with it | `face.fnv_head`, `face.bake` (C1; C2 for a head of another topology) | sculpt sliders: 90.6% of Willow's shape by the fit's own measure; Doc measured 70% through the CK |
| The race's head skin (a mod's own included) plus the `.egt` colour, or the GECK's baked face (`textures\characters\facemods\<plugin>\<id>_0.dds`) when the plugin ships it | FaceCustomization `_d` (and `_msn`, `_s`) | `face.texture` (T2), `vanilla_face_texture` | tint layers: 12% of Willow's colour, 6–40% of the NPCs sampled above |
| The NPC's HAIR mesh and texture (a mod's own included), its HCLR | A hair HDPT per FNV hair, its `.bgsm`, a hair colour (CLFM) per distinct HCLR | `nif.headgear.worn` (FNV head-frame mesh onto FO4's head, skinned to HEAD), `face.hair` (FNV hair colour) | nearest FO4 hair by name, style, then coverage |
| The NPC's head parts (PNAM: brows, beards, lashes) and EYES texture | HDPTs of the same kind; eyes as a texture set on FO4's eye part | `fnv_npc.head_parts` reads them; `headgear.worn` places them | nearest FO4 beard; brows drawn into tints; nearest eye colour |

The slider fit stays and still writes the record: FO4 falls back to it
whenever it builds a face itself (no FaceGen file, or a mod like LooksMenu).
Both are written by the same build, so record and files cannot disagree
(the "dark face" cause).

**Cost, measured per NPC** (this session, one process, after its first
face; the first face per process pays 2.3–2.6 s more for the shared texel
map):

| Step | Time |
|---|---|
| Read the FNV head and FaceGen shape | 0.00–0.46 s (the head mesh is read once per process) |
| Bake the shape into a FaceGeom head (C1) | 0.15–0.24 s |
| Colour pieces (race skin, `.egt`, stock skin) | 0.16–0.36 s |
| Face texture at vanilla's 1024 px (T2) | 0.8 s |
| `_d` to DDS, then the vanilla re-encode | 0.3–0.8 s + 0.7–0.85 s (one texconv run would do both) |

About 2 s per NPC per worker, against the slider fit's 0.45 s
([pool](fo4_build_speed.md#face-pool)) and the CK's ~2 s per NPC run
serially through MO2. *Estimate, not run:* the game's 2,130 faces on 8
workers is about 9 minutes cold; a mod pays only for its own NPCs (NVWillow
has 11 NPC_ records). After that the files are cached per NPC, keyed on its
face fields, head parts and race assets. Unlike the face fits, the files
cannot be published: they are made from Bethesda's head meshes and
textures, so each machine builds its own (the collision cache's rule).
Hairs and head parts convert once per asset (FalloutNV.esm has 67 HAIR,
NVWillow 2), not per NPC.

**What it fixes beyond Willow:**

- Every converted face's full shape and colour, not FO4's preset space;
  today's game build ships no FaceGen at all, so the game builds every face
  from the record at run time.
- Every mod's own heads, skins, hairs, brows, beards and eyes, which have
  no FO4 preset by definition: companion mods, race mods, hair packs.
- FNV's own raiders (grime), Old and OldAged races (wrinkles) exactly,
  where the tint layers above capture 6–40%.
- No Creation Kit or MO2 for faces, so the [app](fo4_gui.md) can build
  faces on any machine.

**Order:** phase 1 (write the FaceGeom NIF ourselves, checked against a CK
export), then phase 2 (shape) and phase 3 (texture) together, since
Willow's look needs both; phase 4 (hair and head parts) last. Unknowns are
listed [below](#risks); the first to settle is whether the game draws our
FaceGeom NIF for an NPC whose record also carries sliders (it should, as it
does the CK's).

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
