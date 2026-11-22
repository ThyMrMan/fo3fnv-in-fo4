# Race looks: FNV and FO3 skin, faces and tattoos on Fallout 4's own system (plan, rewritten 2026-11-21)

Designed, not built. It replaces the first version of this plan, which gave
each FNV race with its own body a Fallout 4 race ("look race") and an addon
in every outfit. That version was dropped after four in-game rounds of neck
seams ([what the test showed](#test-plugin)), in favor of Fallout 4's own
rules, which every vanilla NPC already follows.

Background: [fo4_facegen_plan.md#skin-swap-test](fo4_facegen_plan.md#skin-swap-test).

## <a id="rule"></a>The rule

**The neck stays stock on both sides. Only the skin tone crosses it.**

- The skin tone (`QNAM` plus the Skin Tone tint layer) tints the face and
  the body alike. It carries everything that changes a person's color as a
  whole: ethnicity, FaceGen's overall shift, a race's overall shade.
- Every extra (grime, paint, tattoos, burns, a person's local FaceGen color)
  fades out before the neck, on the face and on the body.
- So at the seam both sides are Fallout 4's own skin times the same tint,
  exactly as for a vanilla NPC. Nothing depends on predicting how the engine
  draws a color.

This is how Fallout 4 is built, measured in Fallout4.esm:

- **Face extras are tint layers baked into the face texture, and none reach
  the neck.** The five dirt masks (`Dirt1`–`Dirt5.dds`) average 0 to 0.7 of
  255 on the face texture's neck strip; the Skin Tone mask is 255 there, and
  so is `NeckMask.dds`, which marks the neck (255 on the strip, 235 over the
  bottom tenth of the texture).
- HumanRace's tint options, and how many vanilla NPCs use each kind:

  | Kind (TETI slot) | Options | NPCs |
  |---|---|---|
  | Skin tone (12) | 2 | 699 |
  | Face paint (13) | 71 | 491 |
  | Dirt (20) | 10 | 474 |
  | Scars, with their own normal and shine maps (21) | 42 | 370 |
  | Face tattoos (22) | 120 | 753 |
  | Brows (23) | 33 | 738 |
  | Blush, eyeliner (8, 9) | 14 | 117 |

- **The body has no tint layers.** An NPC's naked body comes from its skin
  (`WNAM`). 337 vanilla NPCs wear `SkinNakedDirty`; `SkinRaider` (19) is the
  clean naked body.
- **Outfits show only their own skin.** An outfit's bare skin takes its
  addon's skin textures (`NAM0`/`NAM1`), never the wearer's skin (test 3 of
  the [skin swap test](fo4_facegen_plan.md#skin-swap-test)). So vanilla
  raiders have clean arms in their harness, and 255 of the 337 dirty-bodied
  NPCs have no face dirt either.

## <a id="what"></a>What FNV and FO3 bring, and where each goes

| FNV/FO3 | Fallout 4 |
|---|---|
| Ethnicity: race head texture and the NPC's FaceGen color, as a whole | Skin tone. Done today. |
| A person's local FaceGen color | The face texture, faded out at the neck ([face](#face)) |
| A race's head extras: raider grime, tribal paint, face tattoos, Marked Men burns, mods' races | The face texture, faded out at the neck ([face](#face)) |
| A race's body extras: raider grime, White Legs, Sorrows and Dead Horses tattoos, burns | The NPC's own skin (`WNAM`) on Fallout 4's body, faded out at the neck ([body](#body)) |
| The race's body inside outfits | Not carried: clean, as in vanilla ([outfits](#outfits)) |
| Hair, eyes, brows, head parts | Fallout 4 head parts and tint layers. Done today. |
| Children, ghouls | Fallout 4's own races (`HumanChildRace`, `GhoulRace`). Done today. |

Every NPC stays on its Fallout 4 race. No new races, so none of the first
version's costs: no idle or head-part list overrides, no addon per race in
every outfit, and Fallout 4 mods' armor still fits converted NPCs.

## <a id="face"></a>Face

Today the faces stage writes FNV's whole color into the face texture (T1:
Fallout 4's face plus the FaceGen offset plus the race skin minus stock) and
fades it at the neck to the color it predicts the body is drawn with
(`skin_seams.body_drawn`: body texture × `QNAM` × `SKIN_TINT_DRAW`). That
prediction is what failed in game.

The change:

- The overall shift keeps going into the skin tone, as now.
- Everything FNV adds on top of Fallout 4's face (the FaceGen offset's local
  detail and the race skin difference) is multiplied by `1 − NeckMask`,
  Fallout 4's own neck mask, before it is added. At the neck the face
  texture is then Fallout 4's template face under the NPC's skin tone, which
  is what the CK writes for a vanilla NPC.
- `skin_seams.body_drawn`, `faded` and the body sampling the face no longer
  needs go away.

These stay baked into our own FaceGen, as the CK bakes tint layers. Making
them real tint options instead would mean overriding `HumanRace` (or new
races) to add the options. That conflicts with any mod that edits
`HumanRace`, and gains only that LooksMenu could edit them. Vanilla's own dirt
layers can't stand in: five masks per sex can't draw FNV's grime pattern.

### <a id="skin-tint"></a>How the game draws the skin tint (measured 2026-11-22)

`fo4_import/face/skin_tint.py`. The deferred lighting pixel shaders in
`Fallout4 - Shaders.ba2` (e.g. blob 2733 of `shaders011.fxp`, disassembled
with `d3dcompiler_47`'s `D3DDisassemble`) blend the skin tint over the diffuse
by soft light in gamma space: both are taken to 1/2.2, then
`t < 0.5: 2bt + b²(1 − 2t)`, else `2b(1 − t) + √b(2t − 1)`, back to linear,
mixed by the tint's alpha. A tint of 0.5 leaves the texture as it is.

- The CK bakes a face's skin tone the same way: over 946 vanilla HumanRace
  faces, the soft light of the face set's untinted diffuse
  (`BaseMaleHead_d` / `BaseFemaleHead_d`) with the NPC's QNAM matches the
  CK's neck within 1.5 levels (red, green) and 4 (blue). A power curve fitted
  to the same faces missed by 4–7 levels at QNAM 0.4–0.9 of the template's.
- In game (Freeside Thug, QNAM 0.515/0.468/0.535): the body at the neck seam
  drew as about 96/66/59 against soft light's 95/68/55. Earlier models were
  6–14 levels off there: texture × QNAM × `SKIN_TINT_DRAW`, and its power
  curve.
- So the face's neck is the soft light of the untinted face with the NPC's
  QNAM, and QNAM is solved (`tint_for`) so that neck is the template's neck
  darkened by T1's tone and the race shade. The rear head is untinted through
  the same blend.

## <a id="body"></a>Body

Built (`fo4_import/spike/race_skins.py`); confirmed in game on FNV's raiders
(2026-11-22).

- **One skin per distinct set of FNV body and hand textures,** shared by
  every race using it (FNV's four raider races share one). A race on FNV's
  stock textures gets nothing new. The skin copies the human race's clean
  skin (`HumanRace`'s `WNAM`, `SkinNaked`) and its two addons; each addon's
  texture set for a part FNV changes is a copy of the clean set
  (`SkinBodyMale_1` and the rest) with only the diffuse changed. **Not the
  dirty sets:** their shine map is glossier than the face at the neck
  (smoothness 101–103 against the face's 80–81; the clean body's is 82–84).
- **The diffuse** is the [body transfer](#body-transfer), faded in from the
  body's neck edge, so the body side of the seam is the clean body.
- **The NPC's `WNAM`** names that skin, for a human NPC only (`Npcs._skin`);
  it replaces step 1's `SkinNakedDirty`. FalloutNV.esm: 1 skin, 314 NPCs.
- **Textures** go to `Textures\FNV\Skin\<FNV texture path>_d.dds`, staged
  like the build's other textures (`stage_texture`) and packed in the
  plugin's texture archive.
- **Not yet:** a ghoul look race (`MarkedMenGhoul`), since only human NPCs
  take a race skin; the CBBE body below.
- **Which races:** every FNV/FO3 race whose body texture differs from its
  kind's stock body (the race census of the first version still holds):

  | FNV/FO3 races | NPCs (own records) |
  |---|---|
  | The four `*Raider` races | FNV 538, FO3 214, Goodies 42, YUP 39, NVBII 81, Master Build 218 and others |
  | `DeadHorseCaucasian`, `DeadHorseAfricanAmerican` | HH 43, YUP 2 |
  | `SorrowCacasian`, `SorrowAfricanAmerican` | HH 56, YUP 53 |
  | `WhitelegsCacasians`, `WhiteLegsAfricanAmerican` | HH 60, YUP 8 |
  | `MarkedMenGhoul` (on `GhoulRace`'s body) | LR 84, YUP 165 |
  | `WillowRace` | NVWillow 3 |
  | Mods' body races (Russell's `aaSandWolves`, Master Build's `TF*`) | by the rule |

- **CBBE:** the transfer fits the body the player has
  ([bare skin](fo4_bodies_cbbe.md#bare-skin)): with CBBE installed, the
  female skins are built on CBBE's body, UVs and clean texture.
- **FormIDs:** each skin and texture set is hashed from the FNV body texture
  paths (authored), so they are stable across builds.

## <a id="outfits"></a>Outfits: clean, as in vanilla

An outfit's bare skin stays Fallout 4's clean body. A clothed raider has
clean arms and a tattooed White Legs warrior shows no tattoos on bare arms,
as vanilla raiders do. Accepted for now. The face and the naked body keep
the race look.

### <a id="cbbe-research"></a>Research: a way around it with CBBE (2026-11-21)

No route found. In detail:

- **CBBE doesn't change the rule.** Its outfits draw bare skin as a trimmed
  copy of CBBE's body, with the body's material and texture path
  ([bare skin](fo4_bodies_cbbe.md#bare-skin)). The engine still takes that
  skin's texture from the outfit's addon, so CBBE outfits have the same
  limit as ours.
- **LooksMenu (F4EE, an F4SE plugin)** is the only tool found that touches an
  actor's skin at runtime. The installed CBBE's `F4SE\Plugins\F4EE` folder
  holds only its slider files. LooksMenu offers:
  - **Body overlays:** textures drawn over the actor's body. Whether they draw on an
    outfit's bare skin is documented nowhere I could reach (Nexus refuses
    automated reads). Users report overlays vanishing under body-covering
    items such as the hazmat suit and power armor.
  - **Skin override** (`F4SE\Plugins\F4EE\Skin\*.json`): replaces an actor's
    skin form. One user reports the override is replaced when clothing is
    equipped, so tattoos made this way don't show on outfits' bare skin.
  - Either would make converted NPCs depend on a third-party DLL, and
    LooksMenu isn't installed here to test.
- **Without a DLL,** the routes all fail a requirement already set:
  - a race per look with an addon per race in every outfit (the first
    version: idles, head-part lists, mods' armor);
  - a copy of an outfit per look (the player picks up the dirty copy);
  - an object mod with a material swap on the NPC's outfit (the same:
    the item keeps it when picked up).

**Next step, if wanted:** install LooksMenu and test one overlay on one
converted NPC wearing an outfit with bare arms. If it draws there, an
optional "race looks in outfits" setting could write LooksMenu overlay
files for each skin from the same transferred textures.

## <a id="body-transfer"></a>Body transfer (`fo4_import/face/race_body.py`)

- **Dirt:** per channel, FNV's race texture over its stock texture, both
  blurred past the DXT blocks over the stock's bare-skin texels only, at
  most 1 (lighter paint, such as other underwear, isn't dirt), divided by
  the race's overall shade (`fnv_npc.body_shade`), which the NPC's skin
  tone already carries ([face](#face)).
- **Bare skin** is a stock texel at least half the stock's median
  brightness. FNV's underwear and shadowed areas are dark in both
  textures, so their ratio is noise; drawn, it showed as olive patches on
  the armpits and underwear. Those texels take their nearest skin texel's
  dirt.
- **Carried:** each Fallout 4 body texel is a point on Fallout 4's body,
  projected onto the nearest triangle of FNV's body (moved onto Fallout
  4's by the outfit body fit) and read through FNV's UVs
  (`texture.surface_uv`). Reading the nearest surface sample's UV alone
  showed square blocks.
- **Fade at the neck:** vanilla's dirty body is clean at the neck edge and
  dirty within about 10 units: the mean |dirty − clean| per unit of
  distance from the edge rises from 3 at the edge to its plateau of about
  19 by 9–10 units (male; female by 5–6). `fade_curve` takes that curve
  from vanilla's own clean and dirty textures, over the whole body's mean
  difference, never falling and at most 1; the dirt is faded by it.
- **Drawn:** the texture is the one the race's skin tint draws as the
  clean body's drawing times the faded dirt, through the soft light
  ([skin tint](#skin-tint)); the tint is the one a race NPC of T1 tone gets
  (the tint basis template's neck times the race shade). Hands take the
  median dirt of FNV's hand textures, unfaded.
- About 2 s per body and 5 s per hand texture, once per FNV texture set.

## <a id="order"></a>Order

1. **Face:** the `NeckMask` fade in the faces stage; `body_drawn` and its
   neck sampling removed. Rebuild the faces of FalloutNV.esm's test NPCs:
   a regular NPC, a raider and an old NPC, and check the neck in game.
2. **Body:** the skins, the neck fade in the transfer, `WNAM` on the NPCs,
   step 1's `SkinNakedDirty` gone. Test plugin first: the two raiders of
   the [test plugin](#test-plugin), back on `HumanRace` with the new skin
   and faces, naked and in an outfit.
3. **The converter:** skins for every race in [body](#body), in the plugin
   that owns the FNV race; rebuild FalloutNV.esm and Fallout3.esm, then the
   add-ons.
4. **Optional:** the LooksMenu test ([research](#cbbe-research)).

## <a id="test-plugin"></a>What the look race test showed (2026-11-21)

`spike.look_race_test` writes `F3NV_LookRaceTest.esl` (mod folder
`F3NV - Look Race Test`): `F3NV_RaiderRace`, a `HumanRace` copy wearing its
own skin; FNV's raider armor 04 with an addon on the race; two converted
raiders copied onto the race (FE-prefixed IDs `FE00CF89`, `FE00CC15`); the 18
idles and two head-part lists overridden to accept the race. Played four
times, neck seam each time:

1. Fallout 4's dirty body: far milder than FNV's raider face. Seam.
2. FNV's grime carried onto the body as a brightness ratio: the body
   darkened, but lost FNV's color; the faces are gray-green. Seam.
3. The grime per channel, as the face does it: offline the neck matched
   within 5%. Seam.
4. The clean shine map in place of the dirty one: still a seam.

Each time the face's neck was faded to the predicted body color, and each
time the game drew the body lighter than predicted. The prediction, not the
texture, is what fails, which is why the [rule](#rule) removes it. The race
itself worked: the faces loaded and the race's addon drew in the armor.

## <a id="sources"></a>Sources

- [LooksMenu](https://www.nexusmods.com/fallout4/mods/12631?tab=description)
  (the page refuses automated reads; features from its search summary)
- [LooksMenu Skin Override Tutorial](https://www.nexusmods.com/fallout4/mods/31554?tab=posts)
- [Looksmenu body skin issue](https://forums.nexusmods.com/topic/12368758-looksmenu-body-skin-issue/)
  (the `F4EE\Skin` folder)
- [How to make LooksMenu body overlays](https://www.nexusmods.com/fallout4/mods/25125?tab=posts)
- [Overlays and facepaint won't show up](https://forums.nexusmods.com/topic/12487213-overlays-and-facepaint-wont-show-up)
