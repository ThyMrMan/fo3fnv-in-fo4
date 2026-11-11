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
| A bob instead of her hair | Her hair is the mod's own; no FO4 hair shares its name or style group, so the coverage matcher picked the nearest FO4 cut (`HairFemale15`, colour `HairColor19DirtyBlond`). | Limit of the slider route; her own hair now converts ([own heads](#own-heads)). |
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

<a id="race-bodies"></a>**Race bodies: the rest of a custom character.**
Asked 2026-11-10: should the direct route cover bodies too, for a fully
custom character? FNV authors bodies per race, not per NPC, and mods do
ship them. Census of the exported plugins' races naming body or head assets
FalloutNV.esm doesn't (shipped in each export):

| Plugin | Races | Own body assets |
|---|---|---|
| NVWillow | WillowRace | `femaleupperbody.nif` and both hands, `upperbodyfemale.dds` and `handfemale.dds` (2048 px), plus her head and teeth textures. Her body mesh is not FNV's: 10,109 vertices against the stock 4,023, mean 1.06 units off the stock body's vertices (95th percentile 2.7, max 4.6), no `UpperBody` underwear shape |
| HonestHearts.esm | 6 tribal races (White Legs, Dead Horses, Sorrows) | `femaletribalupperbody.nif`, `nvdlc02sorrowupperbody.nif`, tattooed body, hand and head textures per tribe and sex |
| LonesomeRoad.esm | MarkedMenGhoul | body, hand and head textures |
| DeadMoney.esm, OldWorldBlues.esm | Christine; Lobotomites | head textures only (the [race-skin](#race-skin) fix already carries them) |

Today all of these become FO4's own body (the `human_female` or
`human_male` copy's) and FO4's body texture: Willow's body, the tribes'
tattoos and the Marked Men's skin are lost.

FO4's mechanism for an NPC's own body is its skin: the NPC's `WNAM` names
an ARMO whose ARMA holds the body mesh and texture. Vanilla uses it at
scale: 375 HumanRace NPCs in Fallout4.esm name one (`SkinNakedDirty` 337,
`SkinRaider` 18, `SkinNaked` 16, `SkinOldNaked` 3), the same dirty, raider
and old bodies FNV makes with races. So a race with its own body assets becomes
one FO4 skin per race and sex: its body mesh retargeted onto FO4's skeleton
with its own UVs, so its own texture applies as is, and its NPCs' `WNAM`
names it. The retarget is the outfit code's job already (`nif.outfit`: FNV
mesh onto FO4's skeleton and body, FO4's weights at each vertex).

Where it belongs: **the race skin with the direct route** (it is the same
input, the race record's parts, converted once per race like the head
skin, and it is what makes a mod's character whole), **the mechanics with
the [CBBE and BodySlide](fo4_bodies_cbbe.md) plan** (the body choice, bare
skin inside outfits, FNV's underwear shapes, weights). The two meet at bare
skin: an outfit's bare skin is drawn with FO4's body texture today, so a
tattooed tribe loses its tattoos wherever an outfit shows skin, as FO4's
own body texture does with CBBE. FO4's ARMA has Skyrim's answer:
`NAM0`/`NAM1` (male/female skin texture) and `NAM2`/`NAM3` (skin texture
swap lists; xEdit `wbDefinitionsFO4.pas`), present in Fallout4.esm's ARMAs.
Unverified in game: that an outfit's bare skin takes the wearer's skin
texture through them.

**Order:** phase 1 (write the FaceGeom NIF ourselves, checked against a CK
export), then phase 2 (shape) and phase 3 (texture) together, since
Willow's look needs both; phase 4 (hair and head parts); then race bodies,
once the CBBE plan's body choice exists for them to follow. Unknowns are
listed [below](#risks); the first to settle is whether the game draws our
FaceGeom NIF for an NPC whose record also carries sliders (it should, as it
does the CK's).

## <a id="own-heads"></a>Built: a mod's own hair, eyes and face skin (2026-11-11)

**Code:** `fo4_import/spike/own_heads.py`, `fo4_import/nif/hair_mesh.py`,
`fo4_import/face/eyes.py`.

The play test after the fixes above still did not read as Willow: an FO4
bob, darker and older skin, FO4 eyes. What the mod ships and why each was
lost:

| Part | NVWillow ships | Lost because | Now |
|---|---|---|---|
| Hair | Its own HAIR (`WillowAlita`: `hairwillowalita.nif`, `hairalita.dds`) | FO4 has no preset for it; the matcher picks the nearest vanilla cut | The mod's mesh, worn on FO4's head, as a new hair head part |
| Face skin, freckles | Its own race skin (`characters\willow race\headhuman.dds`) | Tint layers approximate a texture with 20 sliders; FO4's face set is FO4's skin | A per-NPC face texture set whose diffuse is FNV's whole face |
| Eyes | Its own EYES (`willow race\eyes\bluedarkeye.dds`) | The matcher picks the nearest vanilla eye colour | A copy of the chosen eyes on FNV's eye texture |
| Face shape | Stock head, FaceGen shape | Sliders capture 90.6% | Unchanged (sliders; see below) |

The trigger is authored: the NPC's HAIR, EYES or RACE record is one the
plugin makes (its FormID in the plugin's own load slot, so not an override
of a master's record: YUP's fixes to vanilla ghoul races would otherwise
qualify), the plugin has masters, and for the face skin the race names a
head texture other than FNV's stock one (a new race on the stock skin
gains nothing over the sliders). A game plugin (masterless) keeps the
slider route for every NPC, so FalloutNV.esm's output is unchanged.

Census of the exported plugins (NPCs reached; new records at most, as only
placed, face-fitted NPCs are built):

| Plugin | Hair | Eyes | Face skin | New records |
|---|---|---|---|---|
| NVWillow | 1 | 1 | 2 | 5 |
| HonestHearts.esm (tribes' war paint) | 0 | 0 | 159 | 9 |
| OldWorldBlues.esm (Lobotomites) | 0 | 0 | 59 | 10 |
| LonesomeRoad.esm (Marked Men) | 0 | 0 | 84 | 2 |
| DeadMoney.esm (Christine) | 0 | 0 | 2 | 1 |
| every other export | 0 | 0 | 0 | 0 |

A face set depends only on the race, sex and FaceGen colour (FGTS), so
NPCs sharing them share one: Honest Hearts' 159 NPCs need 9. Cost per new
part: 1.7 s for a face set (a White Legs guard), 8.6 s for Willow's three
(the first hair also pays the head fit and 3.6 s reading vanilla's split
hairs: 342,286 triangles, 66% of them in the top).

The game builds every face from the record at run time (no FaceGen files
ship), so each part goes in through the record:

- **Hair:** `Equipment.head_worn` puts the mod's hair mesh on FO4's head
  as headgear already is (fit of FO4's base head onto FNV's, skinned to
  HEAD). Vanilla hairs split their triangles into slot 30 (the top, hidden
  under hats) and slot 31; a converted triangle takes the split of the 25
  nearest vanilla hair triangles (both sexes' split hairs; leaving each
  vanilla hair out in turn, 90.5% of its triangles agree). FO4 tints hair
  by HCLF through the hair shader; FNV draws texture × 2 × HCLR blended
  with its `_hl` layer, which no FO4 hair colour matches, so the colour is
  baked into a copy of the texture and the material does not tint. The
  material copy is set as vanilla human hair's (alpha test at 90,
  two-sided, no glow; the converted static had made FNV's `_hl` layer a
  glow map) and the shapes take vanilla hair's commonest NiAlphaProperty
  (4844, 90: alpha-tested, unblended; 62 of 92 hair shapes, FaceBones copies left out). A vanilla hair HDPT is only EditorID,
  model, DATA and PNAM (no morphs, no RNAM: `HairFemale15`), so the new one
  is the same. It replaces the chosen vanilla hair and its extra parts (its
  hairline belongs to that cut). HCLF stays: it colours facial hair.
- **Face skin:** a copy of HumanRace's default face set (`DFTF`/`DFTM`)
  whose diffuse is `texture.face_texture` T2 (race skin, FaceGen colour) on
  FO4's face UVs; FTST names it. FTST is what gave every woman Amari's old
  skin ([above](#body-skin)), so the game draws it. The texture holds the
  colour the tint layers approximated, so their complexion layers go to 0
  (brows stay: FNV draws brows as meshes, not in the texture) and the skin
  tone takes T2's scale.
  - The game draws a face set's raw diffuse brighter than the file: at the
    default tone, the CK's export of a default face (the tint basis
    baseline) is the raw `basefemalehead_d` ×1.32/1.43/1.51 per channel
    (male ×1.57/1.77/2.07), within 5/255 on average. T2's tone compares
    FNV's face with that drawn colour (`face_texture(..., shown)`); against
    the raw file Willow's tone came out ×1.6–1.8.
  - As in T1 ([race skin](#race-skin)), the race's own skin never moves
    the tone, which colours the body too: with it in, a White Legs guard's
    war paint took the tone to ×0.55/0.34/0.32. Without it: White Legs
    ×1.08/1.08/1.15, Willow ×1.16/1.17/1.22 (FNV's stock skin is a little
    paler than FO4's default). Willow's paler race skin stays on her face
    only until her race body converts ([race bodies](#race-bodies)).
  - Shape stays with the sliders: the stock head plus sliders is 90.6% of
    her FaceGen shape; the rest needs our own FaceGeom NIF ([phase 1](#phase-1)).
- **Eyes:** FNV paints lashes and shadow round a centred iris; FO4's eye
  texture is a clean sclera with the iris low. `face.eyes` carries the
  colour by geometry: each FO4 eye texel's direction from its eyeball's
  centre (least-squares sphere) picks the FNV eye sample facing the same
  way. The chosen vanilla eyes and their texture set are copied, the copy's
  `TX00` the result, its extras (wetness, lashes) kept.

Every record is new, keyed by authored data (`derive_formid`, site
`FNV own head`): no existing FormID moves.

### <a id="own-hair-hat"></a>An own hair under a hat: FNV's Hat shape

FNV hair NIFs have two shapes: `NoHat`, drawn bareheaded, and `Hat`, drawn
under a hat. The `Hat` shape is the same mesh, squashed under the brim.
Willow's `hairwillowalita.nif` has both, with 3,232 triangles each. Its `Hat`
leaves the vertices below about z 5.5 alone and moves the crown down by up to
1.1 units. FO4 has no hat swap: a hat hides the hair's slot-30 sub-segment.
The CK's FaceGeom keeps one shape per head part, so a second shape never
reaches the game.

The vanilla-hair vote (`hat_field`) put 2,270 of `NoHat`'s 3,232 triangles in
the top, down to the shoulders at the sides. Under her bowler hat, the cards
were cut along a jagged line: torn strips and a bare head (in-game, 2026-11-11).

`hair_mesh.as_hair` now merges the pair into one shape. `NoHat`'s triangles
are the top (30) and `Hat`'s the rest (31), so under a hat the game draws FNV's
`Hat` hair. Bareheaded, it draws both: `Hat` lies inside `NoHat`, and only 318
of its 1,870 vertices sit farther out, by 0.14 units at the median and 0.28 at
the 90th percentile. The `Hat` shape is detached from the root (unreferenced
blocks stay in the file). A hair without the pair keeps the vote.

The texture's alpha is not the cause. FNV's `hairalita.dds` alpha is 79% under
90 and 17% at 255, ours is the same, and FNV's NIF has no NiAlphaProperty, so
the threshold of 90 drops nothing FNV draws.

### <a id="ck-face-texture-format"></a>A face set texture must match its race's format

In the 2026-11-11 NVWillow build, Willow's (`0047CBE4`) CK `_d`, `_msn` and `_s`
came out byte-identical to `002B6C87`'s, the ghoul the CK exported just before
her. The CK's log (`ckpe.log`, `-ExportFaceGenData:NVWillow.esp`) says why:

```
[FACEGEN] Face customization texture fnv\own\face_0101ce58_f_8aab388173a7_d.dds for NPC FNV_Willow failed to load due to format mismatch with fnv\own\face_0101ce58_f_8aab388173a7_d.dds.
[FACEGEN] Face customization texture fnv\own\face_0101ce58_f_8aab388173a7_d.dds for NPC FNV_Willow failed to load due to unknown error.
[FACEGEN] Face customization texture Actors\Character\Character Assets\FaceDetails\FemBrow1_d.DDS for NPC FNV_Willow failed to load due to unknown error.
```

When a face texture fails, the CK writes the last face it drew. The same log
shows it loading `NVWillow - Textures.ba2` with the plugin, so where the texture
sits does not matter: loose copies (tried in `a7d0e465`) changed nothing.

The face set texture was BC1, 1024, 11 mips, which `encode_dds` picks for an
opaque image. HumanRace's default face sets (`DFTM` `0001FA47`, `DFTF`
`0004D0EA`) are BC3, 1024, 11 mips, as are those of every human, synth and
power-armor race in Fallout4.esm and the DLC. The CK has a sibling check, "Face
customization texture %s differs from other textures on race '%s' with regards
to number of mipmaps", so face textures on a race must agree with each other.
The format check is in `CreationKit.exe` at `0xED7CE6` (flag `+0x24` of the
40-byte per-texture record); the size check is the next block (`+0x14`/`+0x18`
against `+0x1C`/`+0x20`).

`own_heads` now writes a face or eye texture with `texture.dds_like`: the
format, size and full mip chain of the vanilla texture set texture it takes the
place of. Willow's face is now BC3, 1024, 11 mips.

Her face set's `TX04`, `Actors\Character\HumanCommon\BlankDetailmap.dds`, is in
no archive and is not a loose file. This is harmless and vanilla-legal:
HumanRace's own default face sets (`0001FA47`, `0004D0EA`) and 10 of
Fallout4.esm's 382 texture sets name it at `TX04`, and the own face set copies
vanilla's.

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

- **A per-NPC body shape or weight.** FNV has none: one body per race and
  sex, no weight slider, so there is nothing authored for FO4's `MWGT` to
  carry. Body weight and body presets stay in the
  [CBBE and BodySlide](fo4_bodies_cbbe.md#body-weight) plan. A race's own
  body *assets* are a different matter: [race bodies](#race-bodies).
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
