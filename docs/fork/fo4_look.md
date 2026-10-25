# FNV's look on Fallout 4: grass and lighting (plan, 2026-10-23)

**Code:** not built. Status lives in [ROADMAP.md](ROADMAP.md).

The converted region plays right but doesn't look like FNV. The user's
matching shots (2026-10-23: the Prospector Saloon at noon and midnight, the
cemetery lantern at night) are described in
[reference shots](fo4_pipeline.md#reference-shots). Earlier notes:
- [color drift](fo4_pipeline.md#color-drift);
- [weathers](fo4_pipeline.md#weathers), [emittance](fo4_pipeline.md#emittance)
  and [glow](fo4_pipeline.md#glow);
- the [parked](fo4_pipeline.md#parked) table.

This plan replaces those piecemeal items with one pass.

## <a id="rules"></a>How the pass works

- **Reference shots first, every step.** The same spots and times in both
  games, set from the console so they repeat:
  - FNV: `set gamehour to 12` (then 0); `fw <weather>`; the saloon from the
    road; the lantern at the cemetery.
  - FO4: the same commands, the converted weather's EditorID.

  The user keeps the image files in one folder (proposed
  `C:\Coding\tes4skyrim\look_refs\`, outside the repo since they hold
  Bethesda art). Each step is judged from those files: the mean luminance,
  saturation and hue of fixed boxes (sky, wall, ground, window), measured
  by a small script, not by eye alone.
- **One change per play-test,** so each shot shows one cause.
- **Values come from the games, not from tuning.** A number is either
  FNV's authored value, FO4's engine default, or derived from both shaders'
  formulas. The current grass density factor (× 0.25, chosen over three
  plays) is the example to remove.
- **Kept as FO4's:** the grass fade distance (`fGrassStartFadeDistance`
  7000; decided 2026-10-23), and anything that is a player setting in an
  ini.

## <a id="grass"></a>Part A: grass

Both engines grow grass at runtime:
- each ground texture (LTEX) lists its grasses;
- a grid every `iMinGrassSize` units is walked over the loaded land;
- at each point the texture there rolls its grass's density as a percent,
  and the slope and water limits apply;
- a tuft goes down with random jitter, height and colour variance.

So individual tufts never land in the same place in both games. The
amount, where grass can grow, and what a tuft looks like can match.

1. **<a id="grass-density"></a>Density from the two grids.** The games ship
   `iMinGrassSize` 80 (FNV, `Fallout_default.ini`) and 20 (FO4,
   `Fallout4_Default.ini`). FO4 therefore tries (80 / 20)² = 16× as many
   points on the same ground. The density scale becomes 1/16, written as
   that ratio in `grass.py`, in place of × 0.25 (which left the grass about
   4× too thick).
   - Density is a whole number. FNV's common 25–40 become 2, and the
     sparse 3–4 grasses keep a floor of 1, so the result is close but not
     exact.
   - Played check: the saloon shots, judged on how much of the ground the
     grass covers.
2. **<a id="grass-ground"></a>Where grass grows (bare patches).** Ground
   that is grassy in FNV is bare in ours (the saloon's front, the sign).
   The lead is the land texture conversion: FNV paints layers over each
   other, and FO4 stores shares, so we give each layer what the layers
   above leave showing ([land layers](fo4_spikes.md#spike-4-exterior)). A
   grassy layer under dirt or a road gets a small share.
   1. **Measure:** for every vertex of the saloon's cell, compare the
      dominant texture, and whether it carries grass, in FNV against ours.
   2. **Read both exes:** how a grass point picks its texture. It may take
      the highest weight, the top painted layer, or a roll by share.
      FalloutNV.exe and Fallout4.exe each need reading (the land weight
      code sits near `0x4B3A90` in FO4).
   3. **Fix in `land_layers.py`,** so the texture FO4 picks at a point is
      the one FNV's rule picks. Grass must not change the ground's look,
      so a layer's share moves only where the two rules disagree, and the
      change is measured as the count of vertices whose visible texture
      changes.

   **Found (2026-10-24):** the cause was the 4-texture limit, not the
   pick rule. In the saloon's cell 3 of 4 quadrants hold 7 textures and
   lost their only grassy one (`ScrubBarrenWastes02Grass`); over the
   region 345 quadrants lost one, grassy share fell from FNV's 17,543 to
   14,120 and vertices with any grass from 50,421 to 37,283. Now a grassy
   texture painted inside a quadrant (not only on its border, where
   `blend_borders` brings a neighbour's) replaces the lightest kept
   non-base, non-grassy one (`kept_textures`), and grassy textures keep
   FNV's share when the rest is renormalized (`_renormalized`; the
   leftover goes to the heaviest non-grassy texture). Result: grassy
   share 17,496, vertices with grass 50,159, grass dominant at 15,675
   against FNV's 16,908; 4.4% of all share moves; 22 quadrants still
   lose a grassy texture. Neither exe was read: keeping FNV's shares
   holds under either pick rule.
3. **<a id="grass-flecks"></a>Dark flecks on the grass.** Black,
   triangle-shaped bits hang on some tufts and have been there all along.
   - Already ruled out: the atlas texture (FNV's own file, unchanged) and
     the alpha-test threshold (FNV's 92, 100 and 128, carried).
   - Next: the grass meshes' vertex colour and alpha. FNV's
     `TallGrassShaderProperty` cuts triangles with vertex alpha. FO4 reads
     vertex alpha as sway weight and multiplies vertex colour into the
     blade, so triangles FNV hides, or darkens to black, can show. Read the
     17 grass meshes' vertex data and FNV's grass shader (`shaderpackage`).
     Carry FNV's meaning: drop or cut those triangles, and keep vertex
     alpha for placement as it is now
     ([floating grass](fo4_spikes.md#spike-4-exterior)).
4. **Grass colour** (FNV's dry yellow reads green). Judge it after 1 to 3
   and part B's weather work, since lighting tints it too. Then compare
   vertex colour, the colour range, and our subsurface and backlight
   settings (`convert_static.GRASS_LIGHTING`).
5. **Sway.** FNV's grass sway is not carried. Later, after the rest.

## <a id="lighting"></a>Part B: lighting and colour

The steps run from the widest effect to the narrowest.

1. **<a id="weather-imagespace"></a>The weather's imagespace modifier** (the
   noon haze). Every FNV wasteland weather plays `NVWastelandIS`:
   - a tint toward amber (1.0, 0.737, 0.051) at 0.392;
   - brightness × 1.3 → 1.1;
   - HDR pairs 2, 4, 7, 8 and 11.

   Our weathers keep vanilla's imagespaces, so FO4's noon is clean, blue and
   saturated, and FNV's is hazy amber. How FNV evaluates a weather's
   modifier over its keys is unconfirmed, so that gets read from
   FalloutNV.exe first. Then the modifier converts into the FO4 weather's
   imagespace per time of day, through `imagespace.py`'s FNV-to-FO4 grading
   ([imagespace](fo4_spikes.md#spike-2-imagespace)).
2. **Sky and clouds.** Our weathers keep vanilla's cloud layers, so a clear
   FO4 noon has white cumulus on blue where FNV has grey-amber streaks.
   Convert FNV's cloud textures and colours into the FO4 weather's cloud
   layers. FNV's sky colours are already carried.
3. **<a id="night"></a>Night brightness.** Measured 2026-10-23 on matched
   saloon shots (`look_refs\saloon_night_fnv.webp`, `..._fo4_2026-10-23b`):
   - The road is FNV (37, 38, 44), nearly neutral; ours was (10, 19, 30),
     2× darker and blue.
   - The modifier's blue alone would make FNV's night strongly blue
     (red/blue 0.53); FNV measures 0.86. The GECK's rule fits instead:
     active tints average by their alpha, and `NVDefaultExterior`'s own
     orange tint (0.98, 0.57, 0) at 0.33 counts although its flags are 0.
     Night averages to (0.48, 0.50, 0.61) at 0.627, which predicts red/blue
     0.88. Day averages to a strong amber, as FNV's noon (road (112, 98, 63))
     shows; dropping the grading entirely made the day sky clean blue.
   - The modifiers' brightness (×1.3 by day) and contrast (×1.2 at night)
     don't fit FNV's measured levels, so only the tint carries
     (`weather_imagespace.tinted`).
   - With that tint our night road predicts (22, 24, 26) against FNV's
     (37, 38, 43): the right hue, about 40% darker. The gap is not FNV's
     eye adaptation: its blend's exposure is TargetLum ÷ max(adapted,
     TargetLum), at most 1, so adaptation only darkens a bright scene and
     never lifts a dark one (our dump and
     [NewVegasHDR](https://github.com/masonpetrosky/NewVegasHDR) agree; the
     bloom adds bloom × 0.5 over the same divisor). A night scene is shown
     at exposure 1, so the 40% comes from the light itself (the night
     weather's ambient and moonlight against ours) or from our fixed FO4
     exposure. NewVegasHDR names `shaderpackage017.sdp` as the package
     current GPUs load; our reads are from 019.
   - **The cause: ambient.** FO4 lights an exterior with the weather's DALC
     (six directional ambient colours per FO4 time), not NAM0's ambient
     type. Our weathers kept vanilla `CommonwealthClear`'s DALC, about
     (16, 21, 27) at night, where FNV's night ambient is (172, 170, 215):
     FNV's night is lit mostly by ambient, which is why its road shows a
     third of noon's (37 against 112). By day the two nearly agree (vanilla
     75–130, FNV (87, 105, 138)), which is why noon already matched. Each
     DALC now takes FNV's ambient at that time in all six directions, as
     interiors' XCLL does (`weathers.directional_ambient`). The fixed
     exposure is unchanged: noon matched with matching ambient.
     **Played 2026-10-23:** night and noon both close to FNV's shots
     (noon maybe slightly more yellow).
   - FNV's HDR, read from `shaderpackage019.sdp`: an adaptation pass
     (`ISHDRADAPT`, length clamped from 0.01 to the upper clamp), then a
     blend that scales the scene by TargetLum ÷ the adapted luminance and
     adds bloom, then the cinematic. Grading comes before the output clips,
     so `imagespace.fnv_tone` no longer clips before `grade` (bright lights
     kept their colour and detail).

   The plan's original list follows. FNV's night is dark and blue-grey.
   Ours lights the ground blue-white and the sky purple. Likely causes,
   checked in this order:
   1. FO4's auto-exposure lifting a dark scene. FNV's HDR eye-adaptation and
      target-luminance fields were dropped; map them onto the FO4
      imagespace's exposure range.
   2. The night weather's sunlight and ambient (moonlight) colours.
   3. The vanilla night imagespace.
4. **<a id="emissive"></a>Glowing surfaces** (windows, the "ON" bulbs, the
   lamp head).
   - **What FNV computes** (read 2026-10-23). The lit glow pixel shader
     (`SLS2004`, `shaderpackage019.sdp`; `tools/disasm/sdp_extract.py
     --dir`) is `diffuse × (ambient + EmittanceColor × glow map + sun ×
     N·L)`, with no clamp of its own. The HDR pass clips later. There is
     no ×15 anywhere in this path (the old note was wrong).
     `EmittanceColor` comes from `0xBC6FE0`:
     - the shape's emissive colour (an animated one when a sequence plays),
       times its emittance multiplier;
     - the multiplier is skipped only when every channel is above 0.1 and a
       renderer flag (`0x11F941E`, set at `0x4DB0DE`) is off.
   - **Ruled out in play (2026-10-23).** Porting "skip the multiplier on a
     bright colour" took the saloon window's ×3 off and kept its grime. But
     it put out the neon "SALOON" letters (near-white colours with ×7.5),
     which FNV draws lit. So in normal play the flag is on and FNV applies
     the multiplier. The rule was reverted.
   - The window's grime shows in FNV, though, so something after the
     shader keeps it under white. Not eye adaptation, which leaves a night
     scene at exposure 1 (step 3); the lead is the shader's own sum
     (FNV lights in gamma space, so ×3 on a dim glow map stays under 1).
   - **The flag is `bDoHighDynamicRange`** (`0x4DB0DE` stores
     `bDoHighDynamicRange:BlurShaderHDR` and a runtime check), on in
     normal play: FNV applies the multiplier. The neon going dark under
     the skip rule was the activator not playing its loop (below).
   - **FO4's effect shader** (`shaders011.fxp`, the family at
     `0x249948`): texture × base colour × scale, then a lerp toward
     `colour × cb2[13]` by the lighting influence, then fog; no gamma
     step. FNV's multiplier scales a display colour and FO4's a linear
     one, so a neon overlay's scale is FNV's ^ 2.2 (OPEN ×2 → ×4.59;
     vanilla's neon BGEMs use 2 to 4.75). The lit glow's multiplier is
     unchanged for now: the window measures 1.17× FNV's mean already.
   - With ×4.59 the OPEN sign glowed and flickered, with a faint box
     around the tubes (played 2026-10-23): the shader shows its texture
     as linear, so a dim texel b shows as (b × scale)^(1/2.2). The
     overlay's baked texture, colour and animated keys are now all FNV's
     ^ 2.2 (`glow_image` with a cut, `shader_anim.to_linear`), so it shows
     FNV's b × colour × multiplier before the clip.
   - **The "O" stayed dim:** FNV adds the glow inside the light sum,
     d × (L + g × E), and clips; FO4 adds the overlay to the lit
     surface in linear light, and (d L)^2.2 + (d g)^2.2 is well under
     (d L + d g)^2.2 (the "O": red 0.6 against 0.87 at full flicker; its
     flicker keys average 0.51). An added amount can match only at one
     light level L. The overlay is now baked against FNV's wasteland night
     ambient (`NVWastelandClear` NAM0 night, 172, 170, 215:
     `shader_anim.NEON_REFERENCE`): each texel holds
     min(1, d (L + g E))^2.2 − min(1, d L)^2.2, FNV's clip included, with
     colour and scale 1. Flicker keys k map through
     ((L + k)^2.2 − L^2.2) / ((L + 1)^2.2 − L^2.2) (`neon_level`; at
     k = 0.5, 0.38). Vanilla builds neon the same additive way
     (DLC02 `NeonLetterKit01`: a lit letter plus an additive BGEM tube at
     ×1.25–1.5), as does the SelFNV sign mod (lit glow maps at ×1–3).
     Interiors are darker than L, so their overlays come out a little
     bright. **Played 2026-10-23: too dim to read as lit; replaced.**
   - **The FO4 route (decided 2026-10-23).** Matching FNV's display numbers
     through FO4's lighting only moves the trade-off, and stops at FNV's
     clipped value, so FO4's bloom never fires: no "pop", which the Strip
     needs. Glows now follow vanilla's own conventions per kind, ranked by
     FNV's multipliers (`nif/glow_scale.py`): FO4 = median_fo4 ×
     (FNV / median_fnv)^s through both games' median and 90th percentile,
     clamped to vanilla's range. Texture (diffuse × glow) and colour are
     FNV's, as vanilla neon uses its texture as authored.
     - Census, FNV (14,909 meshes): alpha-tested glows 1,224 shapes, median
       ×1.1, 90th ×2 (max 15, `clutter/signnv`); lit glows 1,853, median
       ×1, 90th ×10 (the ×10 are dungeon utility bays); unlit tubes 634,
       median ×1, 90th ×7 (`architecture/strip` 15 of the 88 at ×5+).
     - Census, FO4 + DLC (one per material family): additive glow BGEMs
       24, median ×1.8, 90th ×5, range 0.39–9 (neon letter kit 1.25–2,
       Mackie's Packie 4.75); lit glow BGSMs 150, median ×0.8, 90th ×1.7,
       range 0.05–10; lit windows ×0.5–1.
     - Result: neon ×1 → 1.53, ×2 → 5, ×3 and up → 9; lit ×1 → 0.8, the
       saloon window's animated ×3 → 1.15, ×10 → 1.7. Animated emittance
       keys map the same way (`glow_scale.map_keys`); colour keys stay.
       Unlit tubes keep FNV's values (blended ones drop the multiplier).
     - Played 2026-10-23: windows right; the "O" still flat and the OPEN
       panel hazy (raw faint glow texels × 5). Neon is parked until the
       Strip is converted. Last change made: an overlay bake is raised
       so its brightest texel is white (vanilla's tubes are full-range;
       the "O"'s glow map peaks at 0.47) and stored as linear light, which
       drops the faint panel glow to near black.
   - **<a id="lanterns"></a>Lanterns (2026-10-24).**
   - **Graveyard lantern** (`GraveLantern.NIF`, ref 0010B18C): its flame
     is an opaque unlit card, `LanternBloom`, texels (1, 0.95, 0.46),
     whose `Idle` loop holds emittance 14–15. The static conversion draws
     unlit shapes at ×1 but the animation carried ×15, which FO4's bloom
     blew out. Vanilla's lanterns and bulbs are lit glows at ×1–3
     (`metallantern01on` ×1), so an unlit shape's emittance keys now map
     through the lit-glow curve (×15 → ×1.9; the saloon's "ON" bulbs ×7.5
     → ×1.6). Played 2026-10-24: lantern right, but the bulbs went dark:
     their texels × vertex colour peak at 0.49 (the flame's at 1.0), so
     ×1.6 left them grey. The curve's value now applies to the shape's
     brightest texel (`convert_static.texel_peaks`, divided in
     `glow_scale.map_keys`): bulbs ×3.2, the flame unchanged.
   - **Saloon street lamp's light cone** (`IndFXLightRays01`, ref
     00109756): a two-sided, view-falloff beam (FNV's 0.985 → 0.174, the
     same values vanilla's beams use) cutting into the ground and lamp
     with a hard edge, seen as a ring from above. All 31 vanilla beam
     BGEMs set Soft_Effect (flags1 bit 30), depth median 150; an unlit
     falloff shape now does too.
   - **Animated signs (played 2026-10-23).** FO4 plays a mesh's own
     `Idle`/`SpecialIdle` loop on a static (vanilla: 30 of 31 such meshes
     are STAT or MSTT), not on an activator; an FNV activator with no
     script, name, water or station whose mesh loops is now a static
     (`Activators.ambient`): the saloon's "SAL" flickers. Its tubes are
     alpha-blended unlit strips whose texture fades to a faint glow; with
     FNV's ×7.5 emittance keys the faint texels lit a box. FNV clips the
     colour before blending, so a blended unlit shape drops the emittance
     channel (`shader_anim.blended_unlit`); alpha-tested ones (the "ON"
     bulbs) keep it, since their ×7.5 only clips to white.
   - FO4 keeps the energy and tone-maps and blooms it, so the same window
     is a solid, saturated yellow block.
   - A flat rescale was tried and reverted. The plan is to derive each
     shape's emittance from both pipelines: the FO4 value whose output
     through FO4's tone curve equals FNV's clipped display colour, at the
     exposure FO4 uses for that scene. Built after step 3, since exposure
     feeds it.
5. **Lights** (the lantern lighting the whole ground). Compare the
   lantern's LIGH (radius, fade, colour) and its emittance against FNV's.
   FO4's falloff already matches FNV's in linear light
   ([emittance](fo4_pipeline.md#emittance)), so a difference points at
   intensity, or at night exposure (step 3).
6. **The overall tone.** FO4's filmic curve and LUT against FNV's straight,
   clipped display colours. Decided last, once steps 1 to 5 are in: either
   a converted LUT per weather, or a player option ("FNV look").

## <a id="found"></a>Also in the shots

- **Open water on the horizon** past the region's edge: the worldspace's
  default water plane where no land is built. A region-build artifact;
  the whole Mojave (and LOD) covers it.

## <a id="order"></a>Order

1. Grass 1 (density) and 3 (flecks): small; one play-test each.
2. Grass 2 (where it grows): measure, read both exes, then fix.
3. Lighting 1 (the weather modifier), then 2 (clouds): the biggest
   change to the noon look.
4. Lighting 3 (night), then 4 (glow), then 5 (lights).
5. Grass 4 (colour) and lighting 6 (tone), judged on the result.

Each step ends with new FO4 shots beside the FNV ones, and the measured
boxes, in the same folder.
