# FNV's look on Fallout 4: grass and lighting

**Code:** `fo4_import/spike/grass.py`, `land_layers.py`, `weathers.py`,
`weather_imagespace.py`; `fo4_import/nif/glow_scale.py`, `shader_anim.py`.

**Status:** partly built. Played 2026-10-23/24: night brightness, windows,
animated signs and lanterns. Built, not played: grass density (step 1) and
where grass grows (step 2). Not done: grass flecks, colour and sway; FNV's
cloud layers; the overall tone. The weather modifier carries only its tint
([night](#night)). Neon is parked until the
Strip converts. Status also lives in [ROADMAP.md](ROADMAP.md). The design
below was written as a plan on 2026-10-23.

**Direction changed 2026-11-09:** FO4's rendering, FNV's colours and art
([FO4 route](#fo4-route); drift recorded in
[fo4_drift.md](fo4_drift.md#candidates)). The work left follows that
section's plan; parts A and B below stay as the record of what was
measured and built.

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
- **Values come from the games, not from tuning.** Colours, textures and
  timing are FNV's authored values. Brightness, exposure, bloom and
  material response follow FO4's conventions: FO4's engine default, or
  vanilla's range for the same kind of thing (a census by kind, as
  `glow_scale` does), never a number chosen over plays. The old grass
  density factor (× 0.25, chosen over three plays) was the example;
  [step 1](#grass-density) replaced it.
- **Judge hue and mood against FNV, brightness against vanilla FO4.**
  `shot_boxes.py`'s hue and saturation compare with FNV's shot; its
  luminance compares with a vanilla Commonwealth shot at the same hour and
  clear weather, so a scene lands where FO4's own scenes do.
- **Kept as FO4's:** the grass fade distance (`fGrassStartFadeDistance`
  7000; decided 2026-10-23), and anything that is a player setting in an
  ini.

## <a id="fo4-route"></a>The FO4 route (decided 2026-11-09)

Reproducing FNV's flat, clipped display pixels through FO4's renderer is
what kept failing: the neon "O" dim at every bake, the hazy OPEN panel,
lamps blowing out. Each fix moved the trade-off rather than closing it,
and the clipped target stops FO4's bloom from firing. So the look now
keeps FO4's rendering and carries FNV's colours and art.

| Kept as FO4's | Carried from FNV |
|---|---|
| The filmic curve, bloom (exposure stays pinned: [tone](#route-tone)) | Grading: the worldspace imagespace's and weather modifier's tint and saturation, in each imagespace's LUT |
| Glow and light brightness, by vanilla's range per kind | Light colours, placement, radius; emittance sources |
| Neon built as vanilla's (lit letter, additive tube) | Each sign's textures, colours and flicker keys |
| Shadows, god rays, material response | Fog, sky, sun, ambient (DALC) and cloud colours |
| Cloud layers (FNV's textures seam on FO4's dome) | Grass textures and vertex colour |

### <a id="fo4-route-today"></a>What is built today

- **Tone (until 2026-11-09):** every imagespace's LUT was
  `grade(fnv_tone(identity))`, undoing FO4's Hable curve for FNV's
  straight one, with exposure pinned at 1.40. Interiors
  (`BASE_IMAGESPACE`) and weathers (`weather_imagespace`) both go through
  `imagespace.py`. Step 1 below replaced it.
- **Night and noon brightness** come from the weathers' DALC taking FNV's
  ambient ([night](#night)). That is FNV's light colour in FO4's own
  field, so it stays.
- **Glow strengths** already follow the FO4 route (`glow_scale`, decided
  2026-10-23; windows, lanterns and bulbs played right).
- **Clouds** already are FO4's layers in FNV's colours (`weather_clouds`).
- **Lights:** `records.pack_ligh` carries FNV's radius, colour, flags,
  falloff and fade (FNAM) on vanilla's commonest omni light's DATA.

### <a id="fo4-route-plan"></a>Plan

Each step is one change and one play-test (or none), with shots at the
[comparison spots](fo4_plan_world_look.md#spots). No step adds or moves a
FormID, and none needs a new save: imagespaces, LUTs, lights and
materials are read when a cell loads.

1. **<a id="route-tone"></a>Tone: FO4's curve and bloom, FNV's grading**
   (built 2026-11-09, not played).
   - `write_lut` writes `grade(identity(), grading)`; `fnv_tone` is gone,
     so FO4's Hable curve and the template's bloom act. `Cinematic` holds
     only saturation and tint: FNV's contrast and brightness are tone, now
     FO4's.
   - **Exposure stays pinned.** FO4's auto exposure (0.5–15× in
     `BASE_IMAGESPACE`) washed out Vikki and Vance on 2026-10-10: FNV
     does not brighten a dark room ([exposure](fo4_spikes.md#spike-2-imagespace)).
     Vanilla rarely pins (6 of Fallout4.esm's 292 IMGS) but mostly keeps
     narrow ranges (1–2×, 1–3.5×, 1.75–3×). `fixed_exposure` now solves
     FO4's own curve so middle grey shows at FNV's 0.459: 1.46 (Tonemap
     E 0.02). Shadows stay close (exposed 0.01 shows 0.13 against FNV's
     0.12), so the night and noon matches ([night](#night)) hold; white
     shows 0.80 instead of clipping, leaving room for bloom.
   - Tests: `tests/test_fo4_spike.py` (exposure, LUT grading),
     `tests/test_fo4_weather_imagespace.py`, `tests/test_lut_preview.py`.
   - **Offline grading:** FO4 applies the LUT last, to display colours.
     `tools/validate/lut_preview.py neutral` writes identity LUTs under
     the built LUTs' names; installed as a loose-file mod over
     `Textures\Effects\LUTs\FNV`, shots show FO4's frame before grading.
     `lut_preview.py apply` puts any LUT on such a shot exactly, so a
     grading change is judged on images; a chosen LUT ships as loose
     files to confirm in game.
   - Play check: saloon at 12 and 0, cemetery at 0, one interior (Doc
     Mitchell's). Hue and saturation against FNV, luminance against a
     vanilla Sanctuary shot at the same hours in clear weather. Also the
     saloon window at night: on the old tone (2026-11-09) no longer blown
     out but still far too yellow; the graveyard lantern looks right.
     FO4's shoulder compresses bright channels, so check the window here
     before touching its glow.
2. **<a id="route-neon"></a>Neon, starting at Goodsprings** (built
   2026-11-09, not played). The saloon's OPEN sign never looked right and,
   with the flashing "SAL", read dim, not lit. Found by running
   `convert_static.convert` on the meshes (ref 0016B5E6
   `NV_Open-24-Hours_Sign.NIF`; ref 0016B5E4
   `NV_ProspectorSaloon-Neon_Lights.NIF`):
   - **SAL** (`Shape05:0`, `:1`): unlit tubes, a normal alpha blend
     (0x10ED), emissive 0.955 × 7.5 animated (7.5 for 2.3 s, then 1). We
     drew them as a normal blend at scale 1 and dropped the emittance
     channel (`shader_anim.blended_unlit`): about 0.77 in one channel at
     most. Vanilla's tubes (`neonsign-animatedopen.nif`, NeonRed01 ×2,
     Mackie's ×4.75) are additive near-white texels × a coloured base at
     ×2 or more, about 1.6 linear, enough to bloom.
   - **OPEN and `Shape1:2`:** the overlay bake was stored as linear (^ 2.2),
     taking its median texel to 0.40; × 1.53 × the flicker's 0.51 average is
     about 0.32 linear.
   - **Built:** an unlit shape whose alpha property blends and whose
     emission above 1 is animated (a BSMaterialEmittanceMultController) is
     vanilla's tube: additive (`NEON_ALPHA`), FNV's emissive colour, scale
     `fo4_glow('neon', ×)` (×7.5 → 9), its emittance keys on the neon curve
     (`convert_static._unlit`, `shader_anim._emittance_keys`). Mr. House's
     screen faces (no alpha property, they fade) and its additive scanline
     (emission not animated) are untouched. `glow_image` keeps the alpha
     cut and the raise to white but no longer linearises. The overlay stays
     a decal over the letter's own triangles (vanilla's tube is its own
     shape; without the decal flags the copy may z-fight, untested).
   - Risk to judge: faint glow texels can show again (the old OPEN haze,
     the box around the tubes). Judged at the saloon at 0 for colour and
     pop, against a vanilla Diamond City night shot; then North Gate and
     the Strip.
   - **Played 2026-11-09, against an FNV night shot:**
     - *The "ON" bulbs dark* (fixed, not built). The second O and the N are
       lit by `Bulbs_135:0`–`:2`, unlit alpha-tested shapes (threshold 70)
       with FNV's default falloff, two-sided. The light-cone fix made every
       two-sided falloff shape soft (soft depth 150). The bulbs sit 4–7
       units in front of the letter, so the fade put them under their alpha
       test. Soft_Effect now needs a blend too (`_unlit_shader`). Of 376
       candidate meshes, 30 shapes in 7 meshes change: the bulb signs
       (`nv_prospectorsaloon-neon_lights`, `lucky38entsignglow`,
       `lucky38signglow`, `nv_thetops-sign_lights`) and 3 opaque effects.
     - *OPEN's box* (cause found, not fixed). 13 triangles of
       `Object02:0` (about 107 × 64 units) map a faint full copy of the
       sign (bake median 0.071, 90th 0.133, alpha 255). The bake without
       the ^2.2 shows them at 0.36–0.67 linear at ×5, against 0.015–0.06
       before. The fix wants a floor that keeps the tubes' 0.4–1 cores;
       pick it from authored data first.
     - *SAL's box* (not found). Its texture is ruled out: the tube band's
       alpha is 173–255 and the tubes are thin ribbons. The flash peaks at
       about 4.4–8.6 linear red against vanilla tubes' ~1.6, so bloom is
       the lead.
     - *Windows:* FNV's are pale yellow-green too, with the grime of the
       glass visible; ours read flatter and brighter. Brightness and lost
       detail, not hue.
3. **<a id="route-horizon"></a>The night horizon glow** (built 2026-11-09,
   not played).
   - **Found:** FNV draws it with placed cards, not a weather colour or
     LOD: in WastelandNV's persistent cell, `NVStripLightsPollition` (×2),
     `…Dim`, `…RoundDim` (flat vertical cards up to 122k × 50k units,
     unlit, alpha-blended, vertex colour (0.89, 0.75, 0.60) at alpha 0.12
     fading to 0) and four `FXGlowSimpleFillHalf01Imposter` sheets. Every
     base runs `Lucky38LightScript` (0011B039): from 20:00 to 06:00 it
     plays `Left` (lit), else `Right` (alpha 0). All are region imposters
     (`StripImposterBlackMountain` and others), which the build left out
     with the skyline copies ([imposters](fo4_pipeline.md#imposters)).
   - **Built:** `spike/glow_cards.py` keeps an imposter whose mesh is only
     light (every shape unlit and alpha-blended) and places it Is Full LOD
     (REFR 0x10000) with persistent, as Fallout4.esm's `GSCraterClouds01`
     glow (0x10400; 1,309 vanilla refs are Full LOD). 38 of FNV's 290
     imposters qualify: the 8 glow cards in WastelandNV, their Dim copies
     in the Freeside and North Gate worlds, and 22 casino light overlays
     (Ultra-Luxe window glows, Tops and Gomorrah lights). The overlays'
     lit skyline buildings stay out, so their lights may float at night
     where FNV shows the building; judge from Freeside, North Gate and
     Black Mountain at 0. FO4 has no region gating, so the cards also show
     close by (FNV's `StripImposterClose` already lists Dim and RoundDim).
   - Suspected: a far Full LOD ref's script may skip its animation when
     its 3D is not loaded (`Is3DLoaded`), leaving it at its day state.
   - **Played 2026-11-09:** the Strip's glow from afar looks right. Close
     to Freeside the cards show as floating yellow lights and a solid
     yellow sheet (`FXGlowSimpleFillHalf01Imposter`, refs `001711BB` to
     `001711C2`): the "also show close by" above. Object LOD cannot stand
     in, since it is baked and cannot follow the night animation.
   - **The gate (built 2026-11-09, not played):** `spike/imposter_gate.py`.
     A card some region lists starts disabled. Cards listed by the same
     regions form a group (12 for FalloutNV.esm's 38). Each group gets a
     player ability of two `F3NV_ImposterGate` effects: one enables the
     group while one of its regions' watch globals is 1, the other disables
     it while all are 0, so a save made with the cards on corrects itself.
     The globals are [the region watch's](fo4_regions.md#built), polled
     from FNV's polygons; the 11 regions add 89 points. A start-game
     quest's player alias gives the abilities (ALSP). FNV's own cell region
     lists name the same regions, but the region watch is the build's one
     region mechanism. Also open, the user's call:
     FNV hid the distant view in fog at a shorter view distance; ours shows
     plain, low-detail object LOD instead. Either distance fog or better
     LOD.
4. **<a id="route-lights"></a>Modern lighting, with a Classic switch**
   (built 2026-11-09, not played).
   - **Found (census 2026-11-09).** None of FNV's 8,376 placed lights
     casts a shadow or is a spotlight (`cell.light_data` carries FNV's
     flags, so every one converts as a non-shadow omni light), which is
     much of why interiors look flat beside vanilla. FNV's EditorIDs name
     each light's role: Amb 2,174 placed, Key 1,527, Fill 1,498, Kicker
     772, other 2,405 (fire, barrel, lamplight, neon, office, sewer…);
     warm 2,582 and cool 1,434 name the mood. Fallout4.esm's 801 LIGH:
     595 without shadow, 112 shadow spot, 86 shadow omni, 8 shadow hemi;
     non-specular 141, no rim 88, ambient only 6 (flag names from
     xEdit's `wbDefinitionsFO4.pas`). Vanilla's fill, bounce and ambient
     lights are nearly all plain shadowless lights (bounce: 67 of 74 no
     shadow, 9 non-specular). Shadowed lights per lit interior
     (Fallout4.esm, 442 cells): median 1, 75th percentile 4, 90th 6, max
     34; FNV's Key lights per interior: median 1, 75th 4, 90th 9, 95th 17.
   - **Built (`spike/light_roles.py`):** each Key light (a word "Key" in
     its EditorID) gets a copy casting an omni shadow (Shadow
     OmniDirectional 0x1000, `<EditorID>_Shadow`, FormID site `FNV shadow
     light`). In each cell the 6 widest Key references (a reference's own
     radius first; vanilla's 90th percentile) place the copy; the rest,
     and every Fill, Amb and Kicker light, keep FNV's shadowless light as
     vanilla's fills are. Colour, radius, position and fade stay FNV's.
     New records only; no existing FormID moves.
   - **Later, separately:** a small non-shadow light at glowing objects
     with no light of their own (vending machines, neon signs; Fallout 34
     does the machines by hand), and FO4's fire add-on effects for FNV's
     flame cards and particles.
   - **The switch (built):** `py -3.14 -m fo4_import.classic_look
     --plugin <built FalloutNV.esm> --out <folder>` writes
     `FalloutNV - Classic Look.esl`, also the converter app's optional
     "Classic Look plugin" stage. Its masters are the built plugin's
     masters then the plugin, so it overrides on the built FormIDs:
     - every `_Shadow` light with its shadow flags cleared;
     - every FNV imagespace (TX00 under `Effects\LUTs\FNV`) on a
       Classic LUT (`Effects\LUTs\FNVClassic`): the built LUT after
       FNV's straight curve (`classic_look.fnv_tone`), exposure pinned at
       the old 1.40 (`classic_exposure`).
     FNV's interior contrast and brightness, which the old LUTs carried,
     are not restored. Ticking it on or off needs no new save.
   - **Checks:** the Prospector Saloon and Doc Mitchell's at night, the
     Lucky 38 casino and Vault 34 (dense lights), each Modern against
     Classic and FNV; frame rate on the same routes as the
     [speed gate](fo4_plan_world_look.md#goal).
   - Fallout 34 for contrast: interior knobs tuned by eye (light colour
     strength, ambient, per-cell exposure), fill "bounce" lights, and an
     optional Reactor ENB preset.
5. **<a id="route-grass"></a>Grass** (built 2026-11-09, not played): the
   flecks and the tip triangle ([grass 3](#grass-flecks)), colour and
   sway (grass 4 and 5). FO4's grass lighting (subsurface, backlight)
   stays.
6. The "flat New Vegas" look as a player choice is the Classic switch in
   [step 4](#route-lights).

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
3. **<a id="grass-flecks"></a>Dark flecks and the tip triangle** (built
   2026-11-09, not played).
   - **FNV's grass shader** (`GRASS2000.vso`, `GRASS2001.pso`,
     `shaderpackage019.sdp`): vertex alpha only weights sway (sin × wind ×
     alpha², sideways); vertex RGB scales the sunlight term only; the pixel
     shader never reads vertex alpha. So FNV draws every triangle; the
     old lead (vertex alpha cuts triangles) was wrong.
   - **Cause: FNV clamps the grass texture, we wrapped it.**
     `TallGrassShader` (FNV decomp, `tallgrassshader.cpp` 0x00bac160)
     sets stage 0 to address pair 0, filled with D3DTADDRESS_CLAMP (3) in
     both directions; our grass BGSMs tiled (tile_flags 3) and the shader
     wrapped (clamp 3). UVs just past 0–1 then sample another grass in the
     atlas. The tip triangle is `GrassWasteland02.nif` (GrassWasteland02,
     02b): each of its 6 single-triangle blades has tip v = −0.013, so
     the top ~5% sampled the atlas's dark bottom row (140 opaque texels per
     blade, mean (77, 63, 33); clamped: 0). Also GrassWasteland04 (81
     texels, 18 of 54 triangles), 07 (140, orange), NVGrassGolf02.
   - **Built:** grass BGSMs `tile_flags` 0 and the shader `clamp` 0
     (`convert_static.GRASS_MATERIAL`, `_lit_blocks`), as vanilla's
     driedgrassobj01 and meadowgrassobj01 (20 vanilla BGSMs tile in
     neither direction; 16 of 81 vanilla grass shaders clamp 0). Grass
     BGSMs now carry `_grass` in their path, so no other shape shares one.
4. **Grass colour** (FNV's dry yellow reads green).
   - Not the textures (same as FNV's; wasteland atlas mean (115, 96, 66)),
     not which grass grows (40 of 52 ground links use the brown atlas),
     not GRAS colour range (a per-tuft brightness in FNV's shader).
   - FNV's vertex colour is warm and dark (red/blue 1.08–1.15, bases to
     0.18). Our grass lacked the lighting shader's Vertex_Colors flag
     (flags2 0x20), which every vanilla grass mesh with vertex colours sets
     (0x31, 0x21, 0x20000031); **built:** `VERTEX_COLORS` on grass shapes.
     FO4 then tints all light by it where FNV tinted sunlight only, so
     shaded bases come out a little darker (drift).
   - The rest is the tone: judge after [step 1](#route-tone).
5. **Sway.** GRAS wave period is already carried (`grass.pack_data`;
   FNV 10–100, vanilla 8–200). The Vertex_Colors flag lets FO4 read the
   colour stream for the sway weight. Whether FO4 weights by alpha or
   alpha² (FNV's) is unread (`Fallout4 - Shaders.ba2`); alpha stays as is.
   Vanilla grass with FNV-like shapes (MeadowGrassObj01, DriedGrassObj01…)
   was weighed as a replacement and rejected: GRAS colour range only
   scales brightness, recolouring means shipping altered Bethesda
   textures, and FNV's shrubs, stalks, lawn and golf grasses have no
   match.

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
   - A flat rescale was tried and reverted. The first plan was to derive
     each shape's emittance from both pipelines: the FO4 value whose output
     through FO4's tone curve equals FNV's clipped display colour, at the
     exposure FO4 uses for that scene. The FO4 route above (`glow_scale`,
     decided 2026-10-23) replaced it.
5. **Lights** (the lantern lighting the whole ground). Compare the
   lantern's LIGH (radius, fade, colour) and its emittance against FNV's.
   FO4's falloff already matches FNV's in linear light
   ([emittance](fo4_pipeline.md#emittance)), so a difference points at
   intensity, or at night exposure (step 3).
6. **The overall tone.** FO4's filmic curve and LUT against FNV's straight,
   clipped display colours. Decided 2026-11-09: FO4's curve and exposure
   stay, FNV's grading rides in the LUT ([tone](#route-tone)); the old
   flat look returns as the Classic switch ([lights](#route-lights)).

## <a id="found"></a>Also in the shots

- **Open water on the horizon** past the region's edge: the worldspace's
  default water plane where no land is built. A region-build artifact;
  the whole Mojave (and LOD) covers it.

## <a id="order"></a>Order

Superseded 2026-11-09 for lighting by the [FO4 route plan](#fo4-route-plan);
grass 1 to 3 below stand. The original order, kept for the record. Grass 1 and 2 are built, not played; grass 3 is not
done. Lighting 3 and 4 are played (neon parked); lighting 1 carries only
the tint; lighting 2 and 6 are not done.

1. Grass 1 (density) and 3 (flecks): small; one play-test each.
2. Grass 2 (where it grows): measure, read both exes, then fix.
3. Lighting 1 (the weather modifier), then 2 (clouds): the biggest
   change to the noon look.
4. Lighting 3 (night), then 4 (glow), then 5 (lights).
5. Grass 4 (colour) and lighting 6 (tone), judged on the result.

Each step ends with new FO4 shots beside the FNV ones, and the measured
boxes, in the same folder.
