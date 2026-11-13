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

## <a id="phase-1-our-own-facegeom"></a>Built in scratch: our own FaceGeom, and phases 2 and 3 (2026-11-11)

**Code:** `fo4_import/face/facegeom.py` (phase 1), `fo4_import/face/own_facegen.py`
(a test mod with phases 2 and 3). Nothing in the build calls either; they
write only where `--out` says (`temp/facegen_heads/`).

### Phase 1: the CK's FaceGeom, rebuilt

Checked against every CK export at hand: NVWillow's 11 NPCs (deployed
2026-11-11) and FalloutNV's Doc Mitchell. Every one comes out the CK's exact
size, with every block the same except:

| Difference | Why |
|---|---|
| Vertex positions | The CK applies the NPC's slider morphs; ours is the unmorphed head that phase 2 reshapes |
| `HEAD` (ours, as every FO4 mesh and skeleton spells it) vs the CK's `Head`; FalloutNV's `data\Textures` vs `Data\Textures` | The CK's case-insensitive string pool keeps the first spelling it met; the engine matches names case-insensitively |
| Hair cloth bone nodes, up to 0.00045 units | Not found; ours are the hair mesh's own nodes at the race height. Cloth physics moves these bones anyway |

`tests/test_fo4_facegeom.py` proves it for Willow: with the CK's vertex
positions and `Head` swapped in, ours is the CK's file byte for byte.
FalloutNV's exports predate its 2026-11-11 rebuild, so 14 of 25 sampled
there list other head parts and most others another skin tone; the 11 with
the same parts differ only as above.

What the CK does, as `facegeom.py` repeats it:

- **Parts:** the race's default head parts for types the NPC lacks (last
  first), then the NPC's own `PNAM`s (last first, extra parts dropped),
  each led by its `HNAM` extra parts.
- **Bone nodes:** a flat list under the root, first seen first, unrotated,
  at the race skeleton's bind positions with the skeleton root scaled by
  the race's height for the sex (`DATA`: 1.0 male, 0.98 female), composed
  in float32 as rotate, scale, translate. A bone the skeleton lacks (hair
  cloth) takes the part mesh's own node. Exact on every node of both sexes.
- **Each part** copies its mesh's shape bytes (vertices, triangles,
  segments), `BSSkin::BoneData` and extra data (eye centre, cloth; listed
  once from the root and again from the shape). It renames the shape to the
  `HDPT` EditorID, zeroes its bound (every vanilla skinned part's bound is 0)
  and sets the vertex descriptor's eye-data offset to 2 where it has none.
  `BSSkin::Instance` has the FaceGen node as its root and `(0, 1, 1)` per
  bone.
- **Shaders** are the mesh's own, with the material inlined (name and root
  material blanked):
  - type from the material: glow map 2, FaceGen 4, skin tint 5, hair tint 6,
    environment map 1, else 0;
  - flags from the material (Specular only when its strength is non-zero,
    Environment_Mapping, Hair, Glow_Map, Skew_Specular_Alpha);
    Eye_Environment_Mapping cleared; Transform_Changed set;
  - smoothness, specular, fresnel, backlight, alpha, emittance and UVs from
    the material; wetness from it, else its root material, else
    `(0.8, 0.7, 0.3, 1, 1.2, 0.1)`;
  - subsurface rolloff kept from the mesh;
  - `grayscale_scale` from the NPC's hair colour (`HCLF` → `CLFM` `CNAM`), on
    every lighting shader;
  - the rear head's skin tint from `QNAM`, rounded to bytes;
  - effect shaders take the BGEM's textures, colour (its alpha last),
    falloff and soft depth.
- **Textures:** the material's paths. The part's texture set (`TNAM`)
  replaces only the diffuse. A body-textured part (`DATA` 0x20) takes the
  skin's body addon's texture set (`BOD2` slot 33, `NAM0`/`NAM1`), or that
  set's material when it names no paths. The face material is the NPC's face
  set (`FTST`), else the race's default (`DFTM`/`DFTF`). Its slots 0, 1 and 7
  are `Data\Textures\Actors\Character\FaceCustomization\<plugin>\<id>_d,
  _msn, _s`.

**The first unknown** ([risks](#risks)): the game already draws a CK
FaceGeom NIF for an NPC whose record has sliders (every deployed plugin ships
them), and ours replaces that file under the same name. Only the in-game
test can show whether the game ever rebuilds the face from the record
instead.

### Phases 2 and 3 on Willow

- **Shape:** `bake.bake` C1 on our unmorphed head. It captures **100.0%** of
  FNV's face shape; the deployed slider fit captures 86.4%. The neck seam
  doesn't move (0.0000).
- **`_d`:** `texture.face_texture` T2 (FNV's whole face, race skin added)
  over the CK's default face export, at vanilla's DXT1 1024.
  - FNV's face texture carries her brows.
  - FO4's tint layers (lip colour, complexion) are not composited.
  - T2 wants Willow's skin tone ×(1.155, 1.167, 1.216); the test mod can't
    change her record, so it shows FO4's median face tone.
- **`_msn` is not a model-space map** ([phase 3](#phase-3)): the CK writes
  the face set's tangent-space normal plus tint-layer detail. Human NPCs'
  `_msn` correlate 0.91–0.94 with their sex's `BaseFemaleHead_n` /
  `BaseMaleHead_n`. A new shape needs no new normal map, so ours is the face
  set's normal (`TX01`) and `_s` its `TX07`, at vanilla's formats.

**Found in the deployed NVWillow build:** Willow's CK `_d`, `_msn` and `_s`
(`0047CBE4`) are byte-identical to the previous NPC's, `002B6C87`
(`FNV_WillowsPreviousTravelCompanion`, a ghoul), so she would show a ghoul's
face. The CK refused her face set texture (`fnv\own\face_0101ce58_f_…_d.dds`)
for its format; see
[a face set texture must match its race's format](#ck-face-texture-format). The
test mod's own files for her replace these.

### <a id="c2f-outline"></a>Second test mod: FNV's face outline (C2F) and T1 (2026-11-11, not yet played)

Played on the first test mod: Willow's, Sunny's and Doc's faces kept FO4's
narrower, longer outline; Doc's bald scalp showed an orange cap.

- **The outline in numbers** (FO4's head frame, FNV mapped by `bake.align`'s
  inverse; chin bottom z, then face half-width at z 0, -2, -3.5, -4.5; the
  eyes are at z 2.8):

  | | FO4 unbaked | C1 | C2F | FNV NPC |
  |---|---|---|---|---|
  | Willow | -5.45; 5.20 4.48 3.59 2.79 | -5.43; 5.21 4.45 3.42 2.57 | -5.50; 5.20 4.48 3.85 2.74 | -5.53; 5.25 4.51 3.62 2.82 |
  | Sunny | -5.45; 5.20 4.48 3.59 2.79 | -5.66; 5.05 4.67 3.84 3.00 | -5.77; 5.23 4.65 3.95 3.61 | -5.80; 4.96 4.81 4.07 3.43 |
  | Doc | -5.58; 5.05 4.51 3.80 3.49 | -5.70; 4.94 4.43 3.80 3.62 | -5.51; 4.98 4.48 3.88 3.60 | -5.47; 4.97 4.40 3.77 3.33 |

  After the similarity fit, FO4's unbaked outline already lies within
  0.1–0.6 units of FNV's on a face about 10 wide, and a per-axis fit gives
  scales 0.98–1.02. C2F brings the lower face nearer each NPC's own FNV
  outline than C1 (Sunny's lower-jaw width 3.61 against FNV's 3.43, C1's
  3.00), but the in-game "narrow and long" look is not mostly a difference
  in this outline. An earlier note here put FO4's jaw 0.5–0.7 off FNV's; that
  was measured on the throat, not the jaw.
- **C2F:** C2 (each vertex onto the NPC's own FNV surface) on the face below
  the eyes and on the jaw, C1 on the forehead, ears and skull, so the hair
  stays put. `bake.face_share` places the blend from the centre of the
  NPC's eyes head part (HDPT type 2; only the male head carries a
  `BSEyeCenterExtraData`, and only the male eyes the vertex eye-data flag):
  full below it, fading over 2.5 units above it; full in front of 4 units
  behind it, fading over 2.5 (FO4's ears lie 5.5–7.6 behind it); the jaw
  under the ears keeps C2 from 6 units below it. The constants are measured
  on FO4's male and female heads, not authored.
- **Doc's cap:** the rear head and body draw the record's skin tone (QNAM)
  while T2's face texture assumed it scaled; with no plugin the scale never
  happened. The second test mod uses T1 and ships `FaceGen Test.esp`.
  - T1 runs on the tint basis baseline (the CK's untinted face of the sex's
    template, DocWeathers or DoctorAmari), not the NPC's CK `_d`: today's
    records carry tint layers and a tone fitted to FNV's colour, so the
    CK's `_d` already holds the FaceGen offset and T1 on it applies it twice
    (Doc's blue came out x0.19).
  - The plugin overrides each NPC with QNAM and the Skin Tone layer set to
    the template's times T1's ratio (`own_facegen.with_template_tone`), as
    the build's untinted T1 copy would have them. The result lands near the
    build's own fit: Doc's QNAM (0.824, 0.646, 0.511) against his fitted
    (0.836, 0.663, 0.500), Sunny's (0.694, 0.498, 0.430) against (0.700,
    0.498, 0.430).
  - An NPC naming its own face set (FTST, made by own heads: Willow) already
    carries FNV's whole face and its tone; it keeps the CK's face texture and
    record, and only its shape changes.
- **Doc's grey mustache is the CK's too:** his head's shaders match the CK's
  in every field. The hair colour is matched on the head hair's diffuse
  (HairShaved06, grey 96) and FO4 draws facial hair in the same colour; his
  beard's FacialHair02 (grey 60) through HairColor04Silver comes out about
  RGB (80, 77, 74). Not changed here.

### <a id="rear-head-texture"></a>Third test mod: the rear head's own texture (2026-11-11, played)

**Played:** "the color looks good and the seams are gone". Left over: Sunny
shows an odd neck seam where her head meets her outfit's collar (see
[outfit neck](#outfit-neck)).

Played on the second test mod: Doc's face met an orange scalp in a sharp line
over the top of his skull, and Sunny showed a colour step at the back of her
neck. T1 and the tone plugin did not close either.

**What the seam was,** measured at the 39 vertices the face and rear head
share (`seam_colours.py` in scratch): Doc's test `_d` there was (165, 134,
115); the rear head draws the body texture (93, 68, 49) under the skin tint
(0.835, 0.663, 0.502); the CK's own face there was (138, 91, 49). Sunny: ours
(125, 97, 74), the CK's (120, 72, 49).

**How the game draws the two sides** (`draw_factor.py`, 24 CK faces of the
fresh FalloutNV export): the face texture as it is; a skin-tint part (rear
head, body) as texture × skin tint × a factor. At the face/rear seam the
CK's face over rear diffuse × tint is (1.75, 2.01, 2.32) per channel
(medians, ±5% between NPCs); at the face's neck ring over the body texture
at the same vertex × QNAM, (1.77, 1.95, 2.16). `skin_seams.SKIN_TINT_DRAW`
is their mean, (1.76, 1.98, 2.24). The body mesh is in the FaceGeom's own
frame (its vertices meet the face's neck ring at distance 0).

So T1 was wrong for the test: it divided the tone out of the face texture
(`face_colours`), expecting the game to multiply it back on the face; it
does not, so the face came out paler and bluer than the rear head and body
by the tone. `skin_seams` now:

- **Face:** T1 on the untinted template face as drawn (the tone kept in),
  fading over the last `NECK_BLEND` (3) units above the neck seam to the
  body's drawn colour at its nearest body vertex (body texture × QNAM ×
  factor).
- **Rear head:** its own texture per NPC (`<FormID>_rear_d.dds` under
  FaceCustomization, the rear's own format and size): its texture as the
  template's tint draws it plus FNV's colour offset and race skin, placed
  on FNV's head with the face's alignment (`texel_map`'s `frame`), fading to
  its own texture at the neck, then divided through the NPC's tint × factor.
  The NIF's rear shader points at it and takes the plugin's QNAM as its tint.
- **Load order:** the test mod reads an MO2 profile's active plugins and
  enabled mods as the CK does (`own_facegen.profile_order`,
  `facegeom.Sources(load_order=)`), our own test mod and plugin left out.
  CBBE.esp overrides `FemaleHeadHumanRearTEMP` with DATA 0x15 (no
  uses-body-texture bit) and its own texture set `SkinHeadRearCBBE`
  (`femalebhed_d.dds`), and ships its body loose; with CBBE active, the rear
  texture and the neck fade come from those.

**Checked** (`seam_check.py`, drawn colour, medians at each seam; the Play
profile):

| | face / rear head | face / body at the neck | rear head / body at the neck |
|---|---|---|---|
| Doc, ours | (144, 101, 74) / (151, 104, 65) | (132, 90, 57) / (136, 92, 60) | (141, 92, 56) / (139, 92, 57) |
| Doc, CK | (138, 91, 49) / (137, 89, 55) | (134, 91, 56) / (138, 95, 59) | (141, 94, 57) / (141, 95, 55) |
| Sunny, ours | (115, 69, 49) / (115, 69, 47) | (115, 69, 49) / (115, 68, 47) | (120, 69, 48) / (115, 69, 47) |
| Trudy, ours | (115, 74, 49) / (114, 77, 48) | (107, 73, 49) / (110, 73, 48) | (115, 73, 49) / (110, 74, 48) |

Ours now steps by 1–9 levels across each seam, the CK's own heads by 1–6.
With CBBE.esp loaded, Sunny's rear head takes `femalebhed_d.dds` and her
body its loose files.

#### <a id="outfit-neck"></a>Sunny's neck under her outfit: the outfit's fit, not the fade

In game, Sunny shows a lighter band along the bottom of her neck and a ragged
outline where her head meets the collar. She wears `FNV_ArmorLeather`
(`fnv\armor\leatherarmor\f\outfitf_female.nif`). Her bare neck there is the
outfit's own skin shape `Arms01`: 59 vertices, a 7-unit strip from z -13.8 up
to the head's ring at z -6.7. It draws with the skin-tint shader and
`FemaleBody_d.dds`, like the FO4 body. Measured (`sunny_neck*.py`, Play
profile, drawn colour):

| At the head's neck ring | head side | outfit skin | FO4 body (what the fade aims at) |
|---|---|---|---|
| face part, 13 points | (115, 69, 49) | (114, 66, 47) | (115, 68, 47) |
| rear head, 7 points | (120, 69, 48) | (115, 69, 47) | (115, 69, 47) |

Down the strip, the outfit skin stays within 3 levels of the FO4 body at the
same points. Each outfit vertex takes the UV of the nearest FO4 body point
(see [fo4_bodies_cbbe.md](fo4_bodies_cbbe.md)), so the fade target and what
the outfit draws agree. **The band is not the fade.** If they ever differ, the
fade should aim at the outfit skin's own drawn colour (its texture at its UV
× tone × draw factor) at the nearest outfit-skin vertex. The FO4 body is right
only where no outfit skin covers the neck.

The geometry is what differs:

- The strip sits 0.5–0.6 units off the FO4 body's surface. The head ring
  reaches it within 0.16 (rear) to 0.43 (face).
- **Its stored normals are 13° off its own surface** (median, max 28°). The FO4
  body is 1° off, our face 3°, our rear head 2°. Every converted shape of this
  outfit is 9–16° off (`Arms02` 12°, `Upperbody` 16°, `Arms` 9°).
  `outfit._fitted` carries FNV's normals through the retarget, but
  `fit.seamed` moves the positions after that without recomputing them. The
  skin is lit as though it faced another way, which matches the band. This is
  suspected, not yet shown in game.
- The leather collar (`Upperbody`, `outfitf.dds`) comes within 0.24 of the
  head's ring at 38 vertices. That is the ragged outline: FNV's collar edge
  lies over FO4's neck line.

This is the known outfit/neck fit ([fo4_bodies_cbbe.md](fo4_bodies_cbbe.md)),
not FaceGen. A fix would recompute the normals of fitted outfit shapes after
they move. Not done here.

### <a id="slider-test"></a>Fourth test mod: native sliders, never maxed (2026-11-11, not yet played)

Direction: if Willow's shape and look work this way, the rest is acceptable
drift. For a base NPC the goal is a natural face shape that is not pushed to
the slider limits, plus a better FNV tint. FO4's head stays.

#### <a id="morph-presets"></a>Morph presets, measured through the CK

HumanRace's morph groups (Eyes, Forehead, Nose, Ears, Cheeks, Mouth, Neck;
also Jaw and Chin for female, with no presets) hold 185 presets per sex. A
preset names a morph (`MPPM`) of the head's chargen `.tri`. Female has 41
morphs, male 43. An NPC picks presets as `MSDK` keys (the preset's `MPPI`) with
`MSDV` weights, written right after `QNAM`. Across Fallout4.esm's NPCs, no NPC
uses two presets of one group (0 of about 7,400 group uses), so the fit picks
at most one preset per group. A morph is a blend, linear in its weight, so the
CK exports one NPC per distinct morph at weight 1. The difference from the
baseline is the morph's effect.

#### <a id="proportions"></a>Proportions, not every vertex

The fit matches a few measures of the face, not every vertex. Each measure is
a mean over the face vertices that one of the race's named sculpt regions
moves (`FMRN`, from the string table). A region's set is the vertices it
moves by at least half its peak. Measures are linear in the vertex positions,
so they are linear in the controls. Cheek, jaw, eye and nose width are
right-side mean x minus left-side mean x of Cheekbones, Jaw - Outer, Eyes and
Nose - Full. Chin length is Mouth - Bottom minus the lower half of Chin
(mean z). Brow-to-chin height is Eyebrows - Full minus the lower half of Chin.
Nose length is Nose - Bridge minus Nostrils, nose depth is Nose - Tip minus
Cheekbones (y), and nose height is Nose - Tip minus Eyes (z). Lip fullness is
Mouth - Top and Mouth - Bottom minus Mouth - Corners (y). Lip height is Mouth -
Top minus Mouth - Bottom (z).

The target is FNV's proportions: the same measures on FO4's baseline face
moved by FNV's offset from its mean face (C1). The controls are sculpt values
within ±BOUND and preset weights within 0..BOUND. They are fitted by least
squares on the measures plus a ridge penalty on the values.

With one ridge for every control, the ridge that left nothing at the bound
lost the lips (Willow rms 0.051). So each control starts at RIDGE (0.002),
and only a control that sits at the bound has its ridge doubled, up to
RIDGE_MAX, until none does.

**Measured** (test mod 4, `F3NV - FaceGen Test 4`). Each value is the measure's
change from FO4's baseline face, in game units. "Old" is the deployed
record's fit, predicted linearly; "new CK" is the CK's export after one
refine round.

| | Willow | Kilborn |
|---|---|---|
| Controls at the bound | 0 (max 0.56); old fit: 9 at ±1 | 0 (max 0.55, one preset at 0.59); old fit: 8 at ±1 |
| Presets | DefaultFaceType0 0.23, LipFeature3 0.36 | two, 0.14 and 0.59 |
| rms vs FNV: none / old / new CK round 1 / round 2 | 0.232 / 0.022 / 0.023 / 0.014 | 0.178 / 0.037 / 0.035 / 0.025 |
| Largest miss, new CK | lower lip 0.231 for 0.272, lip height -0.078 for -0.103 | upper lip -0.335 for -0.412, jaw width 0.159 for 0.190 |

The CK-in-the-loop round helps both NPCs: it refits to the target moved by
the first export's miss.

- **Rear head:** an NPC's own type-9 part in PNAM replaces the race's. The CK
  drew `FaceGenTest4Rear_*` on its own `TX00` for both NPCs, so no FaceGeom
  patch is needed.
- **Hair:** the CK moved Willow's hair by at most 0.02. The `.tri` predicts
  0.019 at her preset weights (her two presets barely reach the hair). Hair
  points inside the scalp: 27 of 1,870 with the sliders, against 29 on the
  unmorphed head. For the 1,000 points within 1 unit of the scalp, the median
  clearance stays 0.55, and each point changes by -0.30 to +0.40.
- **Skin tone** over the tint basis template's: Willow ×(1.12, 1.15, 1.28),
  set so the body at the neck matches her face set's CK face texture there.
  Kilborn ×(1.09, 0.98, 0.92), from T1.

**Played** (test mod 4, beside FNV). Kilborn is accepted: "isn't bad at
all, he ain't perfect but is pretty close". Willow reads as too angular and
older than FNV's youthful Willow, beyond the hair.

#### <a id="willow-skin"></a>Why Willow looked older, measured

All units are game units, and each value is the change from FO4's baseline
female face.

- **Shape: the target was relative.** C1 is FNV's offset from FNV's mean face,
  carried onto FO4's base face, so FO4's own base shape stays. Against FNV
  Willow's absolute surface (C2), FO4's base is the one that differs:

  | Measure | C1 target | C2 (FNV's own face) | Test 4 (CK) |
  |---|---|---|---|
  | Chin point (Chin lower half minus Jaw - Middle, y) | +0.27 | -0.07 | +0.34 |
  | Jaw middle width | -0.03 | +0.20 | -0.04 |
  | Chin width | -0.15 | -0.02 | +0.01 |
  | Lower face (Mouth - Top minus the lower Chin, z) | -0.14 | +0.01 | -0.12 |
  | Cheek fullness (Cheeks minus Cheekbones, y) | +0.22 | -0.02 | +0.12 |

  FNV's base female face is rounder and wider in the lower jaw than FO4's.
  Willow's offset (a pointier chin than FNV's mean) made FO4's pointier
  still. Test mod 5 fits C2F, which is FNV's own surface below the eyes and
  on the jaw (as the third mod baked), and it adds these measures to the fit.
- **Eyes:** FNV Willow's eye openings (the head mesh's holes) are the FNV
  mean's size: 1.87 wide by 0.41 open, against 1.80 by 0.41. Her larger eyes
  in FNV are not a shape offset. Eye depth relative to the brow is +0.04 in
  C2, and test 4 already has +0.10.
- **Normal map:** her face set used `BaseFemaleHead_n` (the player's default
  face). Its fine detail (pores, the mean |xy| above a 1-texel blur, over the
  face) is 0.034. That is close to FO4's weathered (0.030) and old (0.047)
  female faces. Fallout4.esm's young female face set (`SkinHeadFemaleYoung`,
  `PiperHead_n`) is 0.010, with the same wrinkle-scale shape (0.034 against
  0.035). Its maps have the same format and size (BC5 1024, specular BC5
  512). Test mod 5 overrides her face set's normal and specular with those.
- **Colour:** her complexion tint layers are all 0. The CK's face texture
  from her face set has a median of (132, 105, 90) over the face, against FNV's
  whole skin at (144, 109, 88): cooler and greyer, (0.92, 0.96, 1.02) of FNV.
  The neck tone that matched it then needed a blue boost: ×(1.12, 1.15, 1.28)
  over the template. Test mod 5 scales the CK's face texture per channel to
  FNV's skin median before taking the neck tone, and paints the rear head in
  FNV's skin unscaled.

**Test mod 5** (Willow only, `F3NV - FaceGen Test 5`, `FaceGenTest5.esp`,
not yet played). A run now leaves out every earlier FaceGen test plugin
(description starting `FaceGen test`) and the mod folder holding it. A
first run read Willow through test mod 4's override and kept the race's rear
head.

- Shape (C2F, 19 measures): 0 controls at the bound, the largest 0.26, two
  presets at 0.04 and 0.10. rms against C2F: none 0.074, test 4's fit 0.210,
  CK round 1 0.016, round 2 0.004. Chin point -0.069 (test 4: +0.262), jaw
  middle width +0.179 (-0.024), cheek fullness -0.015 (+0.250), lower face
  +0.013 (-0.155).
- Skin: `_msn` fine detail 0.011 (test 4: 0.029). The face texture median is
  (140, 109, 90), against test 4's (132, 105, 90) and FNV's (144, 109, 88).
  The neck tone is ×(1.22, 1.18, 1.24) over the template, against test 4's
  ×(1.12, 1.15, 1.28).
- The rear head is her own part on its own texture. Hair points inside the
  scalp: 31 of 1,870, against 29 unmorphed. Each point within 1 unit of the
  scalp moves by -0.31 to +0.21.

Played: "That looks much better, the skin texture still isn't there, it reads
as a bit glossy". In game she had strong highlights on the nose, forehead and
lips, while FNV's skin is nearly matte.

#### <a id="fnv-shine"></a>FNV's skin shine as FO4's specular map

- **FNV's source.** The specular flag is on in the head shader
  (`BSShaderPPLightingProperty`), and the head's `NiMaterialProperty` has
  glossiness 10 and specular colour (0, 0, 0). This is the same in vanilla
  `headhuman.nif`, `headfemale.nif` and Willow's race head. The strength is
  the alpha of the head's normal map. That map is the race head texture's
  `_n` (Willow's race has its own) and is otherwise the mesh's own
  `HeadHuman_n`. As the static converter does
  ([spike 2](fo4_spikes.md#spike-2-static)), the material's colour is
  ignored.
- **Alpha means over the map:**

  | Normal map | Alpha mean | p10 | p50 | p90 |
  |---|---|---|---|---|
  | Willow's race | 11.3 | 1 | 12 | 19 |
  | FNV female | 16.0 | 14 | 17 | 18 |
  | FNV male | 12.4 | 9 | 12 | 16 |

  FNV's own skin shine is about 4 to 6% strength.
- **FO4's `_s` channels.** R is specular strength and G is smoothness. On
  `PiperHead_s`, R is highest on the nose tip (63.5) and forehead (50.6), the
  oily T-zone, and lowest on the chin (29.8). G is highest on the forehead
  (109) and cheeks (91). Means over the face:

  | Map | R (specular) | G (smoothness) |
  |---|---|---|
  | Piper (young female) | 34.7 | 67.2 |
  | Base female head | 23.3 | 74.2 |
  | Mid-aged female head | 23.6 | 63.9 |
  | Old female head | 22.8 | 73.3 |
  | 12 vanilla `FaceCustomization` `_s` | 16 to 26 | 59 to 88 |
  | Willow's CK `_s` in test 5 | 34.2 | 66.7 |

  The CK bakes its own `_s` per NPC from the face set's `TX07`, so test 5
  copied Piper's, the shiniest female head in the game.
- **Shader values add nothing.** On 44 sampled vanilla FaceGeoms, every face
  shader (type 4) and rear head shader (type 5) has smoothness 1.0, specular
  strength 1.0 and white specular colour. Willow's are the same. The `_s`
  maps alone set the shine.
- **The rear head.** `FemaleBody_s` over the rear head's texels: R 28.4 (35.9
  toward the hairline) and G 82.6. That is as shiny as Piper's face.
- **The map (`fnv_npc.fnv_shine`, `skin_seams.shine_texture`).** The FNV
  normal alpha goes through the static converter's rule (`spec_image`): R is
  the alpha × `specular_scale`, and G is `smoothness(glossiness)`. At
  glossiness 10, that is R = 0.52 × alpha and G = 92. Both face and rear head
  get it by the face colour's mapping (`texel_map`), faded at the neck into the
  body's `_s`. The face's map overwrites the CK's `_s`. The rear head gets its
  own `_s` in its texture set and FaceGeom. Normal maps are unchanged.

**Test mod 6** (Willow only, `F3NV - FaceGen Test 6`, `FaceGenTest6.esp`,
played) is test 5 with FNV's shine. Shape, `_d`, `_msn` and tone are
unchanged; `_d` and `_msn` are byte-identical to test 5's. Means over each
part's texels:

| Part | R (specular) | G (smoothness) |
|---|---|---|
| Face | 34.3 → 7.4 | 66.8 → 91.2 |
| Rear head | 28.4 → 4.2 | 82.6 → 91.6 |

The face set's `TX07` still names Piper's `_s`. The CK bakes from it, and
our map replaces that bake. The CK writes its BC5 `_s` with the legacy
`BC5U` four-character code, which `texture.LEGACY_FORMATS` now reads.

Played and accepted (2026-11-11): "Willow I think looks close enough to go
ahead with. Maybe in the future I'll spend more time trying for perfection,
but I think I'll take close enough to look at something else."

#### <a id="accepted-drift"></a>Accepted drift

Willow (test 6) and Sgt Kilborn (test 4) are accepted as close enough.
Neither is perfect. What remains is accepted, not a defect to chase:

- FNV's heavier lashes.
- FNV's warmer, flatter lighting.
- The difference between FO4's and FNV's base heads that the native sliders
  cannot reach within ±0.6.
- Willow's hair clipping is the same as on an unmorphed head (31 of 1,870
  points inside the scalp, against 29).

#### <a id="ck-staging"></a>Running the CK without touching a mod folder

MO2 sends the CK's new files to overwrite, but a file that already exists in
a mod is edited where it sits. The third test mod (deployed) has loose
FaceGen for Willow, `F3NV - Fallout New Vegas` has loose FaceGen for
`FalloutNV.esm`, and `F3NV - NVWillow` has loose face textures. An export of
overrides of those NPCs would rewrite them in place. So `face.slider_facegen`
has the CK export copies instead: the NPCs under new FormIDs (EditorID + `CK`)
in a staging plugin, `FaceGenTest4CK.esp`, written into overwrite with the
hair `.tri` and stand-in rear textures. Every file the CK writes is new. The
heads are then renamed to the real NPCs' paths in the test mod, with the
texture paths inside each FaceGeom rewritten to match, and everything staged
is removed. A plugin in overwrite that is not in `plugins.txt` loads as the
CK's active file (as the calibration plugins do).

#### <a id="rear-head-part"></a>Each NPC's own rear head part

On the slider route the CK builds the FaceGeom, so a per-NPC rear texture
needs a record. The test plugin gives each NPC a copy of its race's rear head
part (`*HeadHumanRearTEMP`, part type 9) in place of the race's in its PNAM. The
copy has its own texture set: the body's `_n` and `_s` with the NPC's own `_d`.
It also has the Uses Body Texture flag (0x20) cleared, because with that flag
the part takes the body's texture set.

#### <a id="hair-morphs"></a>Hair that follows the sliders

A head part follows the morph presets only through its own chargen `.tri`
(HDPT `NAM0` 2, `NAM1` the path under `Meshes`). Vanilla hair has none, and
it is skinned to `HEAD` alone, so sculpt regions (face bones) do not move it
either. Willow's hair gets a chargen `.tri`. The vertices and triangles are
its NIF shape's, and each morph of `BaseFemaleHeadChargen.tri` is copied to
each hair vertex from its nearest head points, inverse-distance weighted, the
way Outfit Studio copies slider data. Both files are in the same character
frame: the hair's nearest head point is 0.1 units away.

## <a id="build-faces"></a>Built: test mods 4–6 in the game build (2026-11-12)

The build now makes every face the way the accepted test mods did, and the
scratch tool (`face.slider_facegen`, `face.slider_records`) is gone.

| Step | Where | What |
|---|---|---|
| Slider fit | records stage: `spike.face_fit.sculpt_fit` → `face.slider_fit.fit` | Never-maxed fit (±0.6, a ridge per control, at most one morph preset per group) of FNV's own face (C2F) over the 19 [proportions](#proportions); written as FMRI/FMRS plus MSDK/MSDV |
| Own face set | records stage: `spike.own_heads` | The race's FTST gets Fallout4's young normal and specular (TX01, TX07) |
| Hair | records stage: `spike.own_heads` | Each converted hair gets `<mesh>Chargen.tri` ([hair morphs](#hair-morphs)), HDPT `NAM0` 2 / `NAM1` |
| CK export | faces stage: `spike.facegen` | As before |
| Refine | faces stage: `spike.facegen_skin.refine` | Each NPC refitted to aim + (record's predicted − CK's measured), keeping the record's preset keys so MSDV keeps its size; patched in place; CK exports again |
| Skin | faces stage: `spike.facegen_skin.skin` → `face.npc_skin` | Base NPCs: T1 with the tone kept in and FNV's brows. Own face sets: the CK's texture scaled to FNV's whole skin, and [FNV's shine](#fnv-shine) on face and rear head. Both: QNAM and Skin Tone TEND scaled to the tone, patched in place |
| Rear head | `face.npc_skin.rear_head` | Its own texture from FNV's colour, faded to the body at the neck |

Records and files are read as the CK sees them (MO2's profile), past any
plugin whose description starts `FaceGen test` and the mod folder holding it.
Test mods 4–6 still load in the CK through MO2, so disable them before the
faces stage.

### The rear head lives only in the FaceGeom

The test plugins gave each NPC a [rear head part](#rear-head-part) record.
The build does not: a per-NPC TXST cannot name a texture cut to the rear
head's UV island, because the part mesh's UVs still point into the full body
texture. So, as in the [third test mod](#rear-head-texture) (played, seams
gone), only the FaceGeom names it. The rear texture is cut to a square around
the shape's UV island (`ISLAND_PADDING` out), the shape's UVs are moved onto
it, and it is written at 512 (`REAR_SIZE`) in the body texture's format. On a
2048 body texture the island is about 400 texels across. Measured on Doc
Mitchell: the crop draws the same as the uncropped texture (float difference
0). The shipped 512 BC1 file is within 1.1 of 255 (median), 4.5 (p95) at the
rear head's vertices. The rear `_d` is 174,904 bytes, against 2.8 MB at 2048.

No new records come from this: the own face set TXSTs and own hair HDPTs
already exist (hashed FormIDs) and only gain fields. No existing FormID moves.

### Cost, measured on a dry run (Doc Mitchell base, Willow own)

| Work | Per NPC | FalloutNV.esm (2,957 fitted faces) |
|---|---|---|
| Slider fit at record time | about 0.3 s after a 1 s setup per worker | about 2 min on 8 workers |
| Refit to the CK's export | 0.12 s | under 1 min |
| Second CK export | 0.43 s | about 21 min (one process) |
| Skin (face, rear, tone) | 3.0 s base, 3.1 s own | about 19 min on 8 workers |
| Worker start | 2.5 s per worker | — |
| Disk | +175 KB rear `_d`; own face sets +350 KB rear `_s` | about 0.5 GB |

A converted hair's chargen `.tri` is about 576 KB. Only plugins with their own
hair have one; FalloutNV.esm has none.

### Published face fits

`FIT_VERSION` is 3. The sculpt entry is (FMRI/FMRS bytes, ((MSDK key,
weight), ...), rms): numbers and Fallout4.esm keys only, so the fits are still
publishable. The basis hash now covers the preset bases too. The refine round
is per machine (it reads the CK's export) and is not published. The fits file
must be re-exported and republished under version 3.

## <a id="sculpt-regions"></a>Decoded: sculpt regions through the face bones (2026-11-12)

**Code:** `fo4_import/face/face_bones.py`, called from `facegeom.build`.

Our FaceGeom now moves each part's vertices by the NPC's sculpt regions
(FMRI/FMRS) itself, as the CK does, without the CK. The mechanism, all read
from vanilla files:

- `meshes\actors\character\characterassets\humanracefacialboneregions{male,female}.txt`
  is JSON: 32 regions per sex, each with `ID` (the FMRI value), `Name`, and
  `BonesA`. Each bone has `Maxima` and `Minima` for Position xyz, Rotation
  xyz (degrees) and Scale xyz. `Defaults` is all zero in vanilla. The race
  record holds only FMRI and FMRN.
- FMRS holds 9 floats: position xyz, rotation xyz, scale, then two unused
  floats. A value v adds |v| times the bone's Maxima (v ≥ 0) or Minima,
  summed over every region that names the bone. The single scale control
  drives all three scale axes.
- Bone `bone_X` in the JSON is node `skin_bone_X` in
  `skeleton_facebones.nif` (`skeleton_female_facebones.nif`). A bone's node
  becomes `local @ T(pos) @ Rz @ Ry @ Rx (negated angles) @ diag(1 + scale)`,
  and the skeleton carries that down its hierarchy (`C_Chin` under
  `C_MasterBot`, the eyelids under the eyes; scale reaches children too).
- Every head part mesh has a `*_faceBones.nif` twin with the same vertices
  (gap 0.0 on Doc's 12 parts), skinned to the face bones. Each bone's move in
  its own frame (`rest⁻¹ @ moved`) is applied about the twin's bind
  (BSSkin::BoneData), weighted by the twin's skin weights.
- The twin's `CustomizationRemapData` (per vertex: 4 half weights and 4 bone
  bytes) and `CustomizationRemapNewBonesData` rebind the vertices to body
  bones (HEAD, Neck) after the bake. They don't change positions.

Doc Mitchell (32 regions, no morph presets) against the CK's own export:

| Part | Max | RMS |
|---|---|---|
| MaleHeadHuman | 0.044 | 0.0054 |
| MouthShadowMale | 0.043 | 0.0103 |
| HairMale08 | 0.041 | 0.0101 |
| BigBeard20_Hairline | 0.035 | 0.0054 |
| MaleHeadHumanRearTEMP | 0.032 | 0.0096 |
| BigBeard20, MaleMouthHumanoidDefault, MaleNeckGore | 0.030 | 0.003–0.008 |
| the four eye parts | 0.002 | ≤ 0.0005 |

Without the sculpt the head is up to 0.37 off. 0.045 units is about 0.6 mm.

The remainder is deterministic (left and right vertices match) but it is not
a bone effect:

- Vertices skinned to a single bone match within half-float precision.
- Vertices whose bones are all unsculpted (neck, rear head) still move up
  to 0.03. On the rear head the move is along mesh z only, and its sign
  follows each vertex's weight-sum error (half weights summing to 1 ± 0.0003).
- A free affine move per bone, fitted to the CK, lowers the error only
  slightly (neck gore 0.0068 → 0.0058 RMS).

Ruled out, each measured on Doc:

- dual-quaternion blending (no change);
- the race's body-weight bone scales (`humanracebonescales*.txt`, many times
  worse when applied);
- the chargen `.tri` morphs (0.0056 → 0.0054);
- a frame mismatch between the skeleton and the binds (relative transforms
  agree within 0.04°);
- `skeleton.nif` in place of the facebones skeleton (0.07° apart);
- rounding to half floats at character height.

The vertex reader also learned eye data (`VA_EYE_DATA`, a float after the
skin), which FO4 eye meshes carry. Before, every vertex after the first was
read 4 bytes off.

### <a id="sculpt-census"></a>Census: all 2,382 CK faces (2026-11-12)

`tools/nif/facegen_census.py` compared our positions with the CK's export
(`temp/ck_facegen_reference_2026-11-12`) for every NPC. All 2,382 were
measured with no errors. Every part matched the CK file's part list and
vertex counts.

| Parts | Count | Median max | 99th percentile | Worst | Unsculpted median |
|---|---|---|---|---|---|
| Faces, mouths, neck gore, rear heads | 11,701 | 0.033 | 0.045 | 0.045 | 0.23 |
| Eyes | 9,363 | 0.002 | 0.002 | 0.003 | 0.19 |
| Beards | 376 | 0.035 | 0.15 | 0.15 | 0.36 |
| Hairs | 6,784 | 0.043 | 0.28 | 1.38 | 0.24 |

The leftover is a fixed offset per part, not a slider effect: a part's
error hardly varies across the NPCs who use it (MaleHeadHuman 0.044 to
0.045 over 1,557 NPCs; HairMale06 0.282 over 138; HairMale22 0.289 over 53).
It is there even for NPCs with no sculpt: the CK writes HairMale01 0.111
away from its mesh, and its `_faceBones` twin is the same mesh. The
largest hair offsets sit at the back of the neck, pulled toward the neck's
axis.

The plugin gives almost every NPC one of two body weights (MWGT): 2,277
NPCs have (0.552, 0.266, 0.182) and 680 have (0.545, 0.041, 0.415). So a
body-weight effect would show up exactly like this, fixed per part.
Measured, each on one NPC with no sculpt:

- A free 3x4 move per bone, fitted to the CK over all its parts, leaves the
  max unchanged (0.111). So the offset is per vertex, not per bone.
- The body-weight tables' blended scales, applied in each bone's frame,
  make it worse (0.216).
- Skinning with those scales on the mesh weights, then rebinding with the
  twin's `CustomizationRemapData` weights, helps only a little (max 0.111 →
  0.084, RMS 0.0137 → 0.0131).
- The mod's own `skeleton*.nif` overrides (the files the CK read) have the
  same node transforms as vanilla.

Body weight is ruled out. Parts used under two different weights have the
same error under both:

| Part | (0.545, 0.041, 0.415) | (0.5, 0.5, 0.0) |
|---|---|---|
| FemaleHeadHuman | 0.0332 (680 NPCs) | 0.0332 (34) |
| HairFemale12 | 0.0442 (9) | 0.0442 (13) |
| HairFemale01 | 0.0474 (38) | 0.0469 (34) |

So does MaleMouthHumanoidDefault under (0.552, 0.266, 0.182) and (0.75, 0.25,
0.0): 0.0296 and 0.0293. The large male hair offsets occur only under the
male weight, but they behave the same way.

The CK does not re-bind the hair either. On an NPC with no sculpt, the CK's
HairMale01 and HairMale06 have the source mesh's bones, binds and per-vertex
weights exactly. Only the positions differ, most on vertices led by
`Neck_skin`: HairMale01's mean error is 0.034 there, 0.012 on `HEAD` and
0.005 on `Head_skin`.

So the offset is something the CK does to each part's positions,
independent of the NPC. The CK's export stays the reference. 4 mm at the
back of the neck is for play-testing to judge, not a blocker.

One outlier is a CK quirk on a test NPC, skipped: FNV_TestFemaleNVPGSimple
(`42B3DE`, all sliders zero) has its HairFemale32_Hairline1 1.38 off. The
other 14 NPCs with that hairline and the same weight are within 0.045 to
0.050.

### <a id="face-d-decode"></a>The CK's face `_d`, decoded and ported (2026-11-12)

*Superseded by [the CK's face bake, read from its shader](#ck-face-shader). These were fitted before the shader was read; kept as the record.*

Measured against the reference set's `_d` (2048, read at 256 to 512).
Errors are mean absolute per channel, out of 255; the CK's own DXT
compression costs about 2.

- **Base:** the face set's diffuse: the NPC's FTST, else the race's
  DFTM/DFTF, through `facegeom.txst_slots`.
- **Skin tone** (TETI slot 12, a colour layer): Soft Light of the tone
  colour over the base, Photoshop's formula, in sRGB, at the layer's value.
  Blending in linear space is about 10× worse. NPCs whose only active layer
  is the tone match to 2.1–2.7 over four tones and both sexes. The tone's
  mask (`SkinTone.dds`, grey channels) is not used as is. Read through a
  gamma curve it shortens the tail (99th percentile 10.4 → 7.4) but raises
  the mean over 60 NPCs (2.79 → 3.09). So the tone goes on unmasked for now.
- **Race defaults:** an option with a default value (TTED > 0), in a slot
  the NPC lists nothing for, is applied at that value. In HumanRace this is
  only the male Brow1 at 1.0; an NPC with no brow layer still gets brows.
- **No skin tone:** an NPC with no Skin Tone layer gets the tone option's
  first TTEC colour (HumanRace female: 1157, 247, 239, 238) at full value.
  The 47 toneless female speakers and holotapes go from 54.8 to 2.8 with it;
  the other 12 template colours give 9.4–81.9. Only the tone slot does
  this: unlisted face paints don't show in the CK's output.
- **Detail layers** (value-only): the texture's RGB blended by the option's
  TTEB (Default = replace, Multiply, Overlay, Soft Light, Hard Light), at
  strength value × alpha. For Default-blend details other than brows (the
  Splochy blotches), the CK's strength measures as value × √alpha, applied
  twice. For example, Splochy4 at value 0.61 measures 0.36, 0.56, 0.68, 0.77
  and 0.82 at alpha 0.2, 0.3, 0.5, 0.7 and 0.9. Soft Light details fit the
  plain value × alpha. Dropping each of Doc's layers in turn confirms every
  layer's own blend operation.
- **Colour layers** keep their mask in the grey channels (alpha is 1). In
  FalloutNV.esm only the skin tone is one, so the rest are untested.
- **Template colours:** a TEND template value is a TTEC entry's *Template
  Index* field (HumanRace's presets name 1657, 1658, ...), not its position
  in the TTEC list. LooksMenu's `CharGenTint.cpp` reads it the same way.

**Ported:** `fo4_import/face/face_tint.py` (`face_diffuse`; tests in
`tests/test_fo4_face_tint.py`). It isn't wired into the build yet. One 2048
face takes 6 s, plugin loading included.
`python -m tools.nif.facegen_census --textures` measured all 2,382 CK faces
at 256: no errors, mean 2.53, median 2.55, p90 3.03, worst 5.71; 6 NPCs
above 4 (burned bodies and scarred or painted faces). The median 99th
percentile is 13. The super mutants' face sets use `fnv\tinted` textures
that are only in the built mod, so the census needs
`--dirs <mod folder>` for them.

Most of the remaining tail is in two areas. Neither has an authored source
yet, so neither is in the model.

- **Lips: an unlisted lip colour.** With the tone model applied, the CK minus
  ours in the lips is nearly the same for every male, whatever the tone:
  about +2, +13, +11 on the lower lip and −2, +10, +10 on the upper. On 30
  males its average has exactly the shape of `LipColor1Male.dds` (HumanRace's
  slot 13 "Paint" option; xEdit names slot 7 "Lip Color"). Adding that option
  with each of its 11 TTEC colours, 12 of 15 sampled males fit best with
  entry 2 (the other three pick entries 0 or 8): colour 157, 177, 198, Soft Light, alpha 0.50. That cuts the error inside
  the mask from 13.9 to 4.8. No NPC lists the option, its TTED is 0, and the
  race's 15 male presets disagree on lip colour, so nothing authored picks
  entry 2. Females (`LipColor1.dds`) fit less clearly: 5.7–7.8 drops to
  4.0–5.1, with no single entry.
- **The lower-left island: the tone weight follows the SkinTone mask on a
  curve.** The island is where `SkinTone.dds` is black (0.03), and the CK
  leaves it near the base, so our unmasked tone is 20–40 too light there.
  Fitting the tone's weight per texel (CK = lerp(no tone, full tone, w)) over
  24 NPCs gives w = 0.28, 0.38, 0.47, 0.54, 0.60, 0.65, 0.69, 0.72, 0.76, 0.78
  for mask bins 0.025 to 0.475, then about 0.95–1.0 above a mask of 0.6. The
  map is sharp, so it isn't a blurred mask. Linear, gamma 1/2.2, √, linear
  space, a two-part model (masked soft light plus a 0.04 normal blend toward
  the tone: RMS 3.16 → 2.61), and a different base texture all fail to fit
  it. The face set has no alpha mask. Texels below a mask of 0.5 are almost
  all in the island, so this curve can't be told apart from "the island is
  special".

The island core is 348 of 262,144 texels at 512 (0.13%), so these areas
matter for how the face looks up close more than for the whole-texture mean.

### <a id="face-maps"></a>The CK's face `_msn` and `_s`, decoded and ported (2026-11-12)

*Superseded by [the CK's face bake, read from its shader](#ck-face-shader). These were fitted before the shader was read; kept as the record.*

Both are BC5 at 2048, so only red and green carry data.

- **Base:** the face set's slot 1 (`BaseMaleHead_n`, tangent space despite
  the `_msn` name) for `_msn`, and slot 7 (`BaseMaleHead_s`) for `_s`. A
  tone-and-brow NPC matches them to 0.2 and 0.7. The wrinkle map (slot 2)
  is not baked in (3.4–4.5 off).
- **Layers:** each value-only layer whose option has a second (`_n`) or
  third (`_s`) TTET texture lerps that texture's red and green in. The
  weight is value × √(alpha of the layer's own `_d`), once, for every blend
  operation. Colour layers (the skin tone) leave both alone. 97 of
  HumanRace's 143 male options carry `_n` and `_s`.
- **Measured on 40 NPCs at 256:** mean error 0.91 (`_msn`) and 0.99 (`_s`)
  with the diffuse's weights. With √alpha for all layers, five NPCs with
  20–36 Soft Light details went 2.69 → 2.06 on `_msn`. The exponent scan
  (0.35, 0.5, 0.65, 0.8, 1) has its minimum at 0.5 for `_msn`; `_s` is flat
  from 0.5 to 1 (3.1–3.2). Blending by the option's own operation is worse
  (`_s` 9.4 on those five), and so is weighting by the map's own alpha
  (`_msn` 7.0, `_s` 31.9).

Ported in `face_tint.face_map`; `facegen_census --textures` now measures
`_d`, `_msn` and `_s` per NPC. All 2,382 CK faces at 256, no errors:

| Texture | Mean | Median | p90 | Worst | NPCs above 4 |
|---|---|---|---|---|---|
| `_d` | 2.53 | 2.55 | 3.03 | 5.71 | 6 |
| `_msn` | 0.55 | 0.33 | 1.66 | 2.64 | 0 |
| `_s` | 0.87 | 0.46 | 2.47 | 4.86 | 110 |

The worst `_msn` and `_s` NPCs are fiends and gang members with many detail
layers (99th percentile 32–45, so the miss is local). Not chased further.

### <a id="own-stage"></a>The faces stage writing its own FaceGen (`--own-facegen`, 2026-11-12)

`python -m fo4_import.spike.facegen ... --own-facegen` writes the heads
itself. The CK route stays the default and the fallback.

- **Which NPCs:** the ones the CK exports. An NPC gets FaceGen when it
  takes no traits from a template (TPLT plus ACBS template flag Use Traits,
  u16 at byte 14) and its race has FaceGen Head (RACE DATA flags, u32 at
  byte 32, bit 0x2; xEdit's layout). On FalloutNV.esm this predicts the
  CK's 2,382 exported and 1,220 skipped NPCs exactly
  (`facegeom.exported`). Only NPCs the plugin adds are considered; the
  reference has no FaceGen for overridden master NPCs.
- **What is written:** per NPC, `facegeom.build`'s FaceGeom NIF and
  `face_tint`'s `_d`, `_msn` and `_s`, drawn at vanilla's sizes and
  encoded at vanilla's formats (`_d`, `_msn` BC1 1024, `_s` BC5 512, full
  mips; [audit fixes](fo4_pipeline.md#audit-fixes)), under the CK's names.
  The CK route's re-encode step is skipped for them.
- **Then as before:** the slider refit (against our heads now), a second
  pass for the refitted NPCs only, `npc_skin`'s FNV skin, rear head and
  tone, and packing.
- **Speed:** `facegen_skin.pool`, sized by `facegen_skin.workers` (half
  the cores, capped by free memory). That's the one place a shared worker
  setting hooks in.
- **Failures:** each NPC's error is caught in its worker and listed;
  texconv has a 120 s timeout, and a broken pool fails every NPC instead
  of hanging. Failed NPCs get the CK's export: our FaceGen is moved out of
  MO2's view, the CK runs, only the failed NPCs' files are kept and
  re-encoded, and ours goes back. If the CK fails too, those NPCs are
  reported without FaceGen.

**Proof (2026-11-12):** `facegen_own.write_face` over all 3,602
FalloutNV.esm NPCs on a scratch copy against tonight's CK reference, 8
workers (`facegen_skin.workers`):

- **Selection:** 2,382 written and 1,220 skipped, exactly the CK's set.
  No errors.
- **FaceGeom:** every head has the CK's shapes. Median worst vertex 0.076,
  one above 0.3 (the census's 1.38 hair outlier).
- **Encoded textures**, decoded at 256: `_d` mean 2.63 (worst 5.64),
  `_msn` 1.37 (worst 3.48), `_s` 1.23 (worst 4.46). That's slightly above
  the census because vanilla's `_msn` is BC1 where the CK writes BC5.
- **Time:** 31 minutes, a median 5.4 s per NPC in the pool (2.1–2.7 s
  alone). One CK export ran 0.43 s per NPC serially (293 in 127 s). The CK
  route exports every NPC twice; ours redoes only the refitted ones.

Not yet run: the stage itself (`facegen.py --own-facegen`) through MO2,
and a game build with it.

#### <a id="second-pass"></a>The second head pass draws meshes only (2026-11-12)

The faces stage draws every head (2,382 in the 2026-11-12 run), refits the
sliders, then draws the refitted ones again (2,237). The second pass used
to redraw their `_d`, `_msn` and `_s` too, about half the first pass's
680 s. But the refit (`facegen_skin.slider_edit`) writes only FMRS and
MSDV, and the face textures read neither: `face_tint` imports only
`facegeom`, and no texture code names FMRS, MSDV, MSDK or FMRI. Sliders
reach the FaceGeom NIF only, through `face_bones`.

Now `heads()` for the refitted forms passes `textures=False` down through
`own_export`, `export_own`, `own_face` and `write_face`, so
`face_files` draws the NIF alone and the first pass's textures stay on
disk for the skin step. The work cache keys on `textures` too, so a
mesh-only entry never stands in for a full one.

Proof on a scratch copy of the built plugin: 12 exported NPCs drawn, then
refitted by `refit_face`, with the sliders patched into the plugin and
reloaded, then drawn again. All 36 textures were byte-identical to the
first draw, and all 12 FaceGeom NIFs changed.

#### <a id="skin-speed"></a>The skin step's speed (2026-11-12)

`facegen_skin.skin_face` took 2.3 s a face in one process (12 faces),
more than drawing the head. Profiled over 11 faces, the time went to
mapping texels, not to colour:

- `texel_points` looped over every triangle in Python, solving each one's
  barycentrics (77,091 `linalg.solve` calls), once per call: the face, the
  rear head and the specular map each asked again.
- `texel_map` rebuilt FNV's mean-head surface and a k-d tree of it on every
  call, and `align` built another.
- `neck_weight` searched the full distance to the seam for every texel,
  and `body_at` built a k-d tree of the body and looked up every texel,
  though the fade only reaches texels within `NECK_BLEND` of the seam.

What changed. Every output is byte-identical:

- **`texture.texel_cover`** keeps, per UV layout (UVs, triangles, size),
  which texels fall in which triangle and their weights (`COVERS`, 8, per
  process; a 1024 face's is 800k texels, 37 MB). `texel_points` only weights the face's own points:
  `np.matmul` over the stacked weights gives the same floats as the
  per-triangle product.
- **`bake.mean_surface` and `bake.point_tree`** keep FNV's mean-head
  surface and the k-d trees of it and of a body. `texture.padding` keeps a
  layout's island padding.
- **`skin_seams.neck_weight`** stops its search at `NECK_BLEND`; a farther
  texel's weight was 0 already. **`skin_seams.faded`** draws the body's
  colour only where the weight is above 0. Elsewhere the old sum added
  `body × 0`, which changes nothing.
- `memo.by_content` takes how many results to keep.

Measured on a scratch copy of the built plugin: 13 exported NPCs, heads
drawn and then skinned in one process, by the old code (HEAD's tree) and
the new. The machine was busy with another build (82–90% CPU), so times
moved between runs:

| Run | Old, median a face | New, median a face |
|---|---|---|
| First pair | 3.36 s | 1.99 s |
| Back to back | 3.61 s | 2.28 s |
| Final code | | 1.92 s |

All 69 files (FaceGeom NIFs, `_d`, `_msn`, `_s`, rear head textures)
were byte-identical every time. What is left per face is real work: each
face's texels are matched to FNV's head by its own points (`texel_map`'s
query, about 0.29 s a call, twice a face), plus colour sampling, medians
and texconv. FalloutNV.esm has no fitted NPC with its own face texture set
(33 have FTST, none FMRI), so the own-set path (`own_face_texture`) wasn't
measured; its changed parts are the `texel_map` the base path proves.

#### <a id="own-cache"></a>Faces kept between builds (2026-11-12)

Every base build rewrites the plugin, so the faces stage used to redraw
all 2,382 heads. Now `facegen_own.cached_files` keeps each NPC's four
files (FaceGeom NIF, `_d`, `_msn`, `_s`) in the work cache (site
`own_face`), and a later build writes the kept files without drawing them.

- **Key:** the plugin, the NPC's local id, its NPC_ record as indexed
  (owner, signature, subrecords), every plugin's masters, and texconv's
  bytes. A refitted NPC has a different record, so the first pass and the
  second (refit) pass each keep their own entry.
- **Checked on use:** every other record and file the face read, by
  SHA-1. `Sources.record`, `get` and `read` note each one in
  `Sources.seen`; `Sources.stored` reads a file without noting it, for the
  check. The work cache's `.ran` record covers the code
  ([code identity](fo4_plugin_layout.md#code-identity)).
- **Per-process memos:** face code caches masks, gradients and skeletons
  per process, so a face can use a file an earlier face read. An entry
  therefore also lists everything earlier faces in the same worker read,
  except other NPCs' records. Without that exception, one changed NPC
  remade every face drawn after it in its worker; the proof caught it.
- **Where:** in `facegen_skin.pool`'s workers, which already hold the
  records. Refine, skin and pack run as before: they patch the plugin and
  the NIFs every build.

Proof on a scratch copy of the built plugin, six NPCs (three exported),
one process each run:

| Run | Result |
|---|---|
| Empty cache | 3 written, 3 skipped; 3.55 s for the first face (memos filling), then 0.54 s and 1.17 s |
| Again, new process | all kept: 0.47 s for the first (hashing the shared inputs), then 0.02–0.05 s; every file byte-identical to the first run and to an uncached draw in that process |
| One NPC's QNAM changed | that NPC written (0.66 s); the other two kept |

An entry is about 2 MB, so all 2,382 faces need about 5 GB; `prune`
drops entries no build used for 14 days.

Before the cache, the whole `--own-facegen` stage took 3,390 s end to end
(2,382 first heads, 2,193 refit, 2,237 second heads and skins, then
packing 22,674 textures and 152,521 Main and voice files). The log has no
per-step times. The first build with the cache fills it, so the cached
time comes from the build after that; not measured yet.

#### <a id="own-stage-speed"></a>Speed (2026-11-12)

Profiled per face, one worker, 42 different NPCs: tint 1.83 s, texconv
with its PNG hand-off 0.47 s, FaceGeom 0.08 s. Tint time was numpy
blending over the whole 1024² image for every layer (about 17 `_d` and 22
map layers a face), plus reloading masks: 68 distinct masks went through
a 24-entry cache (541 hits, 2,122 misses).

What changed. The output is byte-identical: every file of the whole set
matches the previous code's.

- **Each layer is drawn only inside its painted rectangle**
  (`face_tint.painted`). A colour layer is masked by its texture's red
  channel. A value-only layer and its `_msn`/`_s` maps are masked by the
  diffuse's alpha. Outside that rectangle the lerp weight is 0, so the
  pixels can't change. The median mask's rectangle is 15% of the square
  (10 of 68 cover over half). The skin tone stays whole-image.
- **Crops are cached once per worker** (`face_tint.crop`), as uint8, not
  whole float textures. That's 186 MB after 41 faces; whole uint8 images
  were 478 MB.
- **texconv gets an uncompressed TGA** instead of a PNG: saving drops from
  0.10 to 0.003 s a texture, and the DDS bytes are the same.
- **Tried and dropped:** batching several textures into one texconv call
  (0.06–0.09 s a texture either way) and `-singleproc` (no steady gain in
  the pool). Both kept identical bytes.
- **Worker memory:** a worker peaks at 1.84 GB loading `facegeom.Sources`
  (1.42 GB private after), so `facegen_skin.WORKER_BYTES` is 2 GB, up from
  1. Eight workers at the old 1 GB ran out of memory with 15 GB free.

Pool, 63 faces with warm workers: 0.90 s a face on 1 worker, 0.40 on 4,
0.33 on 6, 0.30–0.36 on 8. It levels off at about 6, so `workers()`
stays half the cores, capped by memory. Before, it was 0.82 s a face on
8 workers.

Whole set, every FalloutNV.esm NPC through `facegen_skin.workers` (6
workers, held down by memory, with 15 GB free): 2,382 written, 1,220
skipped, 0 errors in 680 s (0.29 s a written face, 11 minutes). All 9,528
files are byte-identical to the previous code's.

### <a id="ck-face-shader"></a>The CK's face bake, read from its shader (2026-11-12)

The two rules the sections above left out (the lips and the island) and
the odd ones they measured (√alpha twice, toneless NPCs) all come from
one GPU pixel shader and the CPU code that fills its constants. Both were
read, not fitted. `face_tint` now follows them.

**Where:** `Fallout 4 - Shaders.ba2` → `shadersfx\shaders011.fxp`, DXBC
blob 3582 (`ps_5_0`). `fxc.exe /dumpbin` from the Windows 10 SDK
disassembles it. One pass draws all three textures: o0 is `_d`, o1 the
`_msn` red and green, o2 the `_s` red and green.

- **Inputs:** t0 a texture array of masks, t1 the layers' diffuse, t2
  their normal maps, t3 their specular maps, t4 a plain 2D gradient. The
  constant buffer `CB12[320]` holds up to 128 layers: [0..31] flag words,
  [32..159] colours, [160..191] strengths, [192..319] array slices.
- **Flag bits per layer:**

  | Bit | Meaning |
  |---|---|
  | 1 | mask from t0's red |
  | 2 | texture set: colour from t1, mask from t1's alpha |
  | 4, 8 | also draw its normal (t2) and specular (t3) |
  | 16 | a constant colour (palette) |
  | 32 | brows: colour from the t4 gradient at (green^(1/2.2), the hair colour's row) |
  | 64 | write alpha |
  | 128 / 256 / 512 / 1024 / 2048 | Default / Multiply / Overlay / Soft Light / Hard Light |

- **Math:** every texture is decoded sRGB → linear by the GPU, and all
  blending is in linear light. A layer's weight is
  **mask^(1/2.2) × strength**, and `out = lerp(out, blend(out, colour),
  weight)`. The output is `out^(1/2.2)`. The maps lerp their raw red and
  green by the same weight.
- **Blends:** Overlay is keyed on the base (< 0.5), Hard Light on the
  layer. Soft Light raises both to 1/2.2, applies Photoshop's formula
  (with the square root), and raises the result back to 2.2.
- **Sampling:** textures are read with `ld`, the nearest texel at
  floor(uv × size), mip 0. No filtering.

That one weight rule explains three earlier measurements. A 0.5 mask
weighs 0.73, not 0.5, which is the island's curve
([above](#face-d-decode): w = 0.28 at a mask of 0.025 is 0.025^(1/2.2) = 0.19
mixed in linear light). Splochy's "√alpha twice" was alpha^(1/2.2) in
linear light. The maps' √alpha was the same alpha^(1/2.2).

### <a id="ck-layer-list"></a>Which layers the CK bakes

Read from `CreationKit.exe` (Steam). RVAs:

- **`0xabe160`** exports an NPC's face. It copies the NPC's own layers
  (TETI/TEND), then merges the race's defaults (`0xa9b540`, `0x41c760`).
- **`0x421070`** adds a default layer, built by `0x41d030`, for every race
  option the NPC doesn't list. Brow options (slot 23) are skipped when the
  NPC has a brow layer above 0.
- **`0x41d030`** picks the entry kind by TETI slot: below 7 a mask, 7–20
  a palette, 21 and up a texture set.
  - A palette's default is its **default entry**: TTED's float bits read
    as an integer index into TTEC. The layer's value is that entry's
    alpha. HumanRace's female LipColor1 has TTED bits 7, so entry 7 at
    0.30. With no TTED it is entry 0.
  - A texture set's default is TTED as a float.
  - A mask's default is 0.
- **`0x41cb30`** sorts the list by the option's position in the race. The
  data fits only the **reverse** of race order: race options drawn last to
  first. Record order and slot order both fit worse.
- **`0xed6890`** fills the constants. A palette layer whose template
  matches a TTEC entry takes that entry's colour and blend. Otherwise the
  layer's own colour is used, and the blend comes from slot 12 → Soft
  Light or a lookup (`0x18bc9`, not read). The brow slot gets bit 32.
  `0xed80f0` uploads them.

That is the lip answer. Every HumanRace NPC who doesn't list a lip option
gets it anyway, at the default entry:

- Male LipColor1Male (option 1558, slot 13) uses entry 0, alpha 0.52,
  Soft Light.
- Female option 1718, a second lip option, also uses entry 0, alpha 0.52.
- Female LipColor1 (option 1320) uses entry 7, alpha 0.30.

The "entry 2 fits best" measurement was entry 0 seen through the wrong
weight curve.

### <a id="face-d-revisit"></a>What we had wrong, and the CK's own quirks

Resolved 2026-11-12 (pinned earlier the same day as "to revisit").

**What the port had wrong.** Each is now replaced by the read rule:

- It blended in sRGB, not in linear light.
- It weighted by value × alpha, or √alpha twice, not mask^(1/2.2) ×
  value.
- It added only TTED > 0 defaults, so it missed every palette default:
  lips, and on some races more.
- Its "toneless NPC gets the first template" rule was the palette default
  rule seen once.
- It drew the tone unmasked; the tone's mask goes through ^(1/2.2) like
  any other.
- It drew layers in NPC record order instead of reverse race order.
- It keyed Overlay on `<=` (the shader uses `<`), drew Soft Light in
  sRGB, and resized masks bilinearly where the shader reads the nearest
  texel.

**The CK's quirks, which `face_tint` copies:**

- **Hidden lips.** No NPC chose them, the race's presets disagree on lip
  colour, and the race menu shows nothing. A converter or an editor that
  reads only an NPC's TETI list can't predict the CK's face.
- **TTED means two things.** It is a float strength for a texture set and
  an integer entry index, stored in a float field, for a palette. xEdit
  shows a palette's TTED 7 as a tiny denormal float.
- **The skin tone's blend.** HumanChildRace's tone entries 1216–1224 store
  blend 0 (Default) in TTEC, yet the CK's child faces are Soft Light. The
  tone is Soft Light whatever its entry says. Either the data or the CK is
  inconsistent here; we follow the CK's output.
- **Nearest-texel masks.** A 512 mask on a 2048 face gives 4×4 blocks at
  mask edges.

**Not ported** ([brows](#ck-brows) are, since):

- Mask-kind options (slots below 7); FalloutNV.esm sets none.
- The `0x18bc9` blend lookup for an own colour with no matching template.

`sRSMLipColor` in the CK is only the race menu's label.

**Measured** on 26 NPCs at 512 (mean / 99th percentile, out of 255): the
old port 2.59 / 14.8; the new rules 0.94–1.51 per NPC, 99th percentile
mostly 3–5. The lips went from about 13 to 1.4–3.2, and the island from
8–28 to about 1.0. The child 6EEA50, the one outlier before the tone was
forced to Soft Light, is 1.51.

**Whole set:** `facegen_census --textures`, all 2,382 CK faces at 256, no
errors. The earlier port's numbers are in brackets.

| Texture | Mean | Median | p90 | Worst | NPCs above 4 | Median 99th pct |
|---|---|---|---|---|---|---|
| `_d` | 1.59 (2.53) | 1.41 (2.55) | 3.00 (3.03) | 3.69 (5.71) | 0 (6) | 6.1 (13) |
| `_msn` | 0.31 (0.55) | 0.29 (0.33) | 0.51 (1.66) | 0.56 (2.64) | 0 (0) | 1.3 |
| `_s` | 0.48 (0.87) | 0.39 (0.46) | 0.89 (2.47) | 1.12 (4.86) | 0 (110) | 2.1 |

The census draws ours at 256 and shrinks the CK's 2048 with PIL's
bilinear filter. `face_tint.image` reads a texture texel by texel (as the
shader does) when the face is at least the texture's size, and shrinks it
with the same bilinear filter when the face is smaller. With nearest-texel
reads at 256 the maps alias (`_msn` 4.3, `_s` 3.2); with a box filter the
two sides disagree by about 0.7. At the stage's own sizes (1024, 512) most
masks are read texel by texel.

The worst `_d` faces are now Fiends and gang members with many detail
layers, and Duke. Brows still use their own texture colour rather than
the hair gradient, which is the next thing to check there.

### <a id="ck-brows"></a>Brows from the hair colour (2026-11-12)

The CK colours brows from the hair, not from the brow texture.

- **Shader** (bit 32, set for TETI slot 23): the brow texture's green,
  which the GPU reads decoded to linear, raised to 1/2.2, picks the
  column of t4. The layer's colour `.x` picks the row. Both are read with
  `ld` at floor(coordinate × size). The texel is lerped in with no blend
  operation, at the usual weight (alpha^(1/2.2) × value).
- **t4** is the race's HNAM, "Hair Color Lookup Texture" (HumanRace:
  `Actors\Character\Hair\HairColor_Lgrad_d.DDS`, 64 × 512, BC1). It
  fits only when decoded as sRGB, although its format is plain UNORM.
- **The row** (`0xed6890` at `0xed707f`): the hair colour from `0xa95450`
  (the NPC's HCLF, else a per-sex default from the race's head data,
  which we read as RACE HCLF). If that CLFM has FNAM flag 2 ("Remapping
  Index"), its CNAM read as a float is the row. Otherwise the row is
  FLT_MAX, off the texture.
- **Black brows.** An off-texture `ld` reads 0, so the CK draws brows
  black for a hair colour without a remapping index. It also draws them
  black for a race without HNAM: HumanChildRace has none, so every child
  gets black brows whatever its hair. Both match the CK's output (the
  child 6EEA50: brow region 7.8 → 0.8).

Ported as `face_tint.brow_colour`, with `Face.hair_row`. The maps are
unchanged (the brow's own `_n`/`_s` as before).

**Measured.** Brow region at 512, before → after:

| NPC | Hair | Before | After |
|---|---|---|---|
| Duke (BE740C) | PlatinumBlond, row 0.488 | 26.2 | 0.9 |
| DCBE56 | PlatinumBlond | 30.7 | 1.1 |
| 180A57 | JetBlack, row 0.613 | 4.9 | 0.8 |
| EEEDC9 | row 0.707 | 11.5 | 0.7 |
| 6EEA50 (child, no HNAM) | | 7.8 | 0.8 |

Whole set (`facegen_census --textures`, 2,382 faces at 256, no errors):
`_d` mean 1.59 → 1.55, median 1.41 → 1.38, worst 3.69 → 3.28; `_msn`
and `_s` unchanged. Brows are a small area, so the mean barely moves.

The census's remaining tail (182 faces above 3) comes from drawing
small, not from the model. Its two worst faces, C5E98E and 47E91A, score
3.28 at 256 but 1.29 when drawn at 1024 and compared at 512. Shrinking
the masks before the non-linear blends is not the same as shrinking the
CK's finished face. The stage draws at 1024 and 512.

The decode matters for the column. Raising the stored green to 1/2.2
without decoding it first gives 18.0 on Duke's brows. The plain stored
green gives 2.9; the decoded rule, 0.9.

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
- The CK needs the MO2 profile, and is a Windows-only stage of the app.
  It costs about 2 s per NPC on a small plugin, but 5.7 s per face on
  FalloutNV.esm: the overnight run of 2026-11-12 wrote 2,382 faces in
  3.8 hours. The timeout allows 6 s per NPC_ record.
- <a id="ck-exit-hang"></a>**The CK can hang on exit after a big export.**
  On that run it wrote its last face at 05:27, then stayed up until it was
  closed by hand at 07:21. It hit an access violation in `CreationKit.exe+38A466`
  with cell `FNVVault22d` loaded, and CKPE wrote the crash zip only on that
  close. Every NPC still missing a face had a creature race, so the export was
  complete. MO2's `run` waits for the CK, so the old timeout never ran.
  `creation_kit.run` now starts MO2 without waiting. Once the CK has written
  files and then gone `CK_QUIET` (15 min) without a new one, it counts as
  done and is closed. `facegen --collected` finishes a stage from files that
  an earlier CK run left in overwrite.
- **A CK stuck before its first file** (a load hang or an error dialog) is
  closed after `CK_FIRST` (30 min) and stops the stage. Before, only the
  overall timeout caught it, 6 s per NPC: about 6 hours for FalloutNV.esm.

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
- `_msn` and `_s` from the face set (`TX01`, `TX07`): the CK's `_msn` is
  the face set's tangent-space normal plus tint detail, not a model-space
  map, so a new shape needs no new one
  ([built](#phase-1-our-own-facegeom)).
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
