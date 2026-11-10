# Bodies, CBBE and BodySlide for converted outfits (planned 2026-11-07)

How the FO3/FNV → Fallout 4 converter can use CBBE, a male body and
BodySlide with Outfit Studio to fix the clothing problems of converted
outfits: painted underwear, the wrist seam, body shape and clipping. This is
the detail behind option C of
[human clothing](fo4_build_next.md#human-clothing) and
[CBBE and BodySlide](fo4_replacements.md#bodyslide). Status lives in
[ROADMAP](ROADMAP.md) only.

## Contents

- [Summary](#summary)
- [1. The problem as it stands](#problem)
- [2. What CBBE and BodySlide offer](#offer)
- [3. Males](#males)
- [4. The approach](#approach)
- [5. Per-world and all-worlds profiles](#profiles)
- [6. Plan, step by step](#plan)
- [7. Risks and open questions](#open)
- [Sources](#sources)

## <a id="summary"></a>Summary

- **Whose underwear.** FNV and FO3 *model* their underwear: the naked
  body's whole torso is a tank-top-and-briefs shape with its own texture.
  The underwear painted onto skin is **Fallout 4's** (bra and briefs on
  the female body texture, briefs on the male). It shows wherever an FNV
  outfit shows skin, because that skin is drawn with FO4's body texture.
- **CBBE active today breaks converted bare skin.** CBBE uses its own UV
  layout; our outfits' skin uses vanilla's UVs on the same texture path.
  The user has CBBE enabled in the `Replacements` profile.
- **Plan.** A Body choice per sex: vanilla FO4 by default, or a BodySlide
  body found in the player's mods (CBBE; for men BodyTalk, A-Body or SHB).
  Route 1: our existing fitting code targets the chosen body's NIF (shape,
  UVs, seams), so bare skin shows its nude texture: no painted underwear.
  Route 2: BodySlide projects per outfit, made by Outfit Studio's own
  headless automation (or our Python writer as fallback), which the player
  batch-builds with their preset and LooksMenu morphs. FNV's underwear
  becomes clothing on converted NPCs' skin, so naked NPCs look as in FNV.
- **Males.** CBBE is female only; BodySlide handles any body with a slider
  set. BodyTalk and A-Body (built on Atomic Muscle) are the maintained
  male bodies; SHB is older. Vanilla men need none of this.
- **Dependency only.** CBBE's files are read on the player's machine and
  never shipped; BodySlide (GPL-3) is run as a separate program.

## <a id="problem"></a>1. The problem as it stands

### How each game draws underwear (measured 2026-11-07)

**FNV and FO3 model their underwear as part of the naked body.** Their
naked body NIFs (`characters\_male\upperbody.nif`,
`femaleupperbody.nif`, identical in both games) hold two skinned shapes
besides the gore caps:

| Body | Torso shape (body part 0) | Limb shape (arms, legs) |
|---|---|---|
| Female | `UpperBody`, 950 vertices, drawn with `textures\armor\underwear\UnderwearF.dds` (a tank top and briefs) | `Arms01`, 1,464 vertices, `UpperBodyFemale.dds` |
| Male | `Arms:0`, 602 vertices, `UnderwearM.dds` (a vest and boxer shorts) | `Arms:1`, 650 vertices, `UpperBodyMale.dds` |

So the whole torso of a naked FNV character *is* underwear: geometry
shaped as a top and briefs, with its own texture. The skin texture
`UpperBodyFemale.dds` also has dark briefs painted at the crotch, a
backup under the modelled briefs. Why: FO3 and FNV show no nudity, a
naked actor shows the race's body model, and every outfit replaces the
whole upper body (slot Upper Body) with its own mesh, which carries its
own bare skin as separate skin shapes on `UpperBodyFemale.dds` /
`UpperBodyMale.dds`. Underwear only has to exist on the naked body, so it
was built into it.

**Fallout 4 paints its underwear onto the body texture, for both sexes.**
Vanilla `basehumanfemale\femalebody_d.dds` has a bra and briefs painted on
(diffuse and normal map); `basehumanmale\basemalebody_d.dds` has briefs
painted on (rendered from `Fallout4 - Textures*.ba2`). FO4's body mesh is
one shape with no underwear geometry. FO4 outfits draw bare skin by
carrying a fitted copy of the body (`BaseFemaleBodyFitted` and the like)
that uses the same body texture, so whatever is painted on the body
texture shows wherever an outfit shows skin. Vanilla outfits are cut so
the painted bits stay covered.

The task's framing ("FNV's underwear painted into the body texture") is
half right: FNV's underwear is fused into the body *mesh* (plus a painted
backup at the crotch). The painted underwear our players see is
**Fallout 4's**.

### How the converter handles bodies and outfits now

From [outfits](fo4_spikes.md#spike-4-outfits),
[human clothing](fo4_build_next.md#human-clothing) and
`fo4_import/nif/outfit.py`:

- **Bodies, heads and hands are FO4's own.** A converted human wears
  Fallout 4's body (from `Fallout 4 - Meshes.ba2`), head (FaceGen,
  LooksMenu) and hands. FNV's naked body, underwear shape included, is not
  converted. A converted NPC with no outfit therefore shows FO4's painted
  underwear: a woman loses FNV's tank top for FO4's bra; a man loses FNV's
  vest and boxers for FO4's briefs.
- **Outfits are FNV's meshes moved onto FO4's body.** Each FNV outfit is
  retargeted from FNV's skeleton to FO4's, conformed to FO4's body by the
  smoothed offsets between FNV's and FO4's bodies, seamed to FO4's wrist
  and neck edges, and skinned with FO4's body weights at each vertex's
  nearest surface point (`BodyFit`, `worn()`). Segments by strongest bone;
  no dismemberment cut data. Written per sex as `<static>[_female].nif`
  and `_1stperson.nif` (`equipment._body_worn`).
- **Bare skin inside an outfit** keeps FNV's skin mesh but is drawn with
  FO4's body shader, material and texture; each vertex takes the UV of the
  nearest point on FO4's body. The FO4 body is always read from the
  vanilla archive, so the UVs are vanilla's.
- **Planned (A, 2026-11-02):** FNV's own weights for clothes, a tapered
  forearm at the wrist, dismemberment segments. Option C (CBBE with
  BodySlide) kept as an opt-in.

### Recorded clothing problems

| Problem | Where recorded | State |
|---|---|---|
| **Painted underwear** shows where FNV clothes leave skin bare (the sexy sleepwear's chest shows FO4's painted bra) | [outfits](fo4_spikes.md#spike-4-outfits), [drift](fo4_drift.md) | Accepted 2026-10-08; "a body texture replacer the player installs covers it". Masking by colour misses shadows and strap edges |
| **Wrist seam:** FO4's hand is larger than FNV's forearm | same | Accepted; taper planned (A step 2) |
| **Arms through sleeves** when FO4's own body replaced FNV's skin | same (tried and dropped) | Dropped: FNV clothes are cut for FNV's body |
| **Loose cloth off the body:** the dress hem up to 13 units | [human clothing](fo4_build_next.md#human-clothing) | Open |
| **Stretching / splitting** of skirts and coat tails by nearest-surface weights | same; the super mutants measured 34.5x stretch | A step 1 (FNV's own weights) |
| **Dismemberment** does not cut outfits | same | A step 3 |
| **Left sleeve snapped to the neck** (seam pairing) | [outfits](fo4_spikes.md#spike-4-outfits) | Fixed 2026-10-18 |
| **Shine** too strong | same | Fixed |
| **Body shape:** outfits fit vanilla FO4's shape only; no body-weight morphs, no body presets | not recorded before this doc | New, below |

### A new finding: CBBE breaks today's bare skin

Checked 2026-11-07 against the user's installed CBBE 2.7.2 (MO2 mod
`Caliente's Beautiful Bodies Enhancer -CBBE-`, enabled in the
`Replacements` profile, disabled in `Play`):

- CBBE's `FemaleBody.nif` has **its own UV layout**, not vanilla's
  (vanilla: one 1,723-vertex shape in a cross layout; CBBE: a 10,729-vertex
  `BaseFemaleBody:0` with the torso, legs and feet in separate islands).
  Its `FemaleBody_d.dds` replaces vanilla's at the same path.
- Our converted outfits' bare skin points at `femalebody_d.dds` with
  **vanilla** UVs. With CBBE active, that skin samples CBBE's texture at
  the wrong places: scrambled skin on every FNV outfit that shows skin.
  This is why CBBE ships converted copies of all vanilla outfits.
- The installed body also carries an `Undies` shape (9,427 vertices,
  `Female_Underwear_d.dds`): the installer's modelled-underwear option, much
  like FNV's own approach.

So "a body texture replacer covers the painted underwear" is only true for
replacers that keep vanilla's UVs. CBBE is not one of them, and it is the
replacer most players have. Whatever else is chosen, the converter must
take bare-skin UVs from the body the player actually uses.

## <a id="offer"></a>2. What CBBE and BodySlide offer

### CBBE (Nexus fallout4/mods/15)

- **Version 2.7.2** (2025-12-22), by Ousnius and Caliente; the user has it
  installed. **Female only:** it replaces the vanilla female body that
  every adult woman shares; its FAQ sends men elsewhere.
- **Contents:** three nude body shapes (Slim, Curvy, Vanilla) and
  "NeverNude" versions wearing underwear made from Bethesda's unused
  underwear meshes; nude textures with no painted underwear; converted
  copies of all vanilla and DLC outfits; BodySlide add-ons for the body
  and outfits; `.tri` morphs and F4EE files for LooksMenu. `CBBE.esp` is
  optional (it fixes the texture seam at the back of the player's head).
  Since 2.7 the high-poly body exists only through BodySlide.
- **Its own UVs.** FAQ Q4: CBBE has different UV maps, so outfits that show
  skin must be made CBBE-compatible. Measured here too
  ([new finding](#problem)). Vanilla textures on CBBE's mesh give the
  painted-on underwear (FAQ Q2).
- **On disk** (the user's install): `Tools\BodySlide\SliderSets\CBBE.osp`
  (5 sets: CBBE Body, Body Physics, Body Reduced, NeverNude, NeverNude Alt;
  426 slider entries), `ShapeData\CBBE\CBBEBody.nif/.osd`,
  `RefTemplates\CBBE.xml`, `SliderPresets\CBBE.xml` (Zeroed Sliders, Curvy,
  and more), `SliderGroups\CBBE*.xml`, and the body at
  `meshes\actors\character\characterassets\FemaleBody.nif` (shapes
  `BaseFemaleBody:0` and, with the underwear option, `Undies`).

### BodySlide and Outfit Studio (Nexus fallout4/mods/25, GitHub `ousnius/BodySlide-and-Outfit-Studio`)

- **GPL-3.0.** Latest v6.1.0 (2026-11-04); the user has 5.9.1. A native
  Linux build exists (wxWidgets 3.2 GTK); nothing official for macOS or
  Wine (one ProtonDB report calls BodySlide usable and Outfit Studio
  "janky").
- **Files** (formats read from the source, `dev` branch):
  - `.osp` slider set (XML, `SliderSet.cpp`): `<SliderSet name>` with
    `DataFolder`, `SourceFile` (the base NIF), `OutputPath`,
    `OutputFile`, `<Shape target>`, and `<Slider name ...>` holding
    `<Data name target local>` entries that point into the `.osd`.
  - `.osd` shape data (binary, `DiffData.cpp`): `"OSD\0"`, `uint32`
    version 1, `uint32` entry count; per entry a `uint8` name length, the
    name (target plus slider), a `uint16` count, and that many packed
    `{uint16 vertex; float x, y, z}`. Vertex indices are 16-bit, so a
    shape over 65,535 vertices cannot carry sliders.
  - `SliderPresets` (`<Preset name set>` with `<SetSlider name size value>`),
    `SliderGroups` (`<Group name><Member name/>`), `RefTemplates`
    (`<Template sourcefile set shape>`).
  - Conversion references ship with BodySlide in
    `ConversionSets\References.osp`: `VanillaToCBBE`, `CBBEToVanilla`,
    Skyrim-to-FO4 CBBE and others (on the user's disk).
- **Presets:** a preset is a value per slider; building applies each
  slider's diff times its value to the base mesh. FO4 sets build one NIF
  (no `_0`/`_1` weight pair, `GenWeights` off).

### <a id="outfit-studio"></a>Outfit Studio: conform and weights

From `OutfitProject.cpp`, `Automorph.cpp`, `ConformOptions.h`:

- **Conform** (copying the body's sliders onto an outfit): for each outfit
  vertex, the reference vertices within a proximity radius (default 10)
  are found in a kd-tree; the nearest 10 that have a diff for the slider
  are blended by inverse distance (an exact match weighs 1000); if the
  nearest has none the vertex gets zero. Options: smoothing (2 passes,
  0.5), no-squeeze, solid mode, per-axis, fix clipping.
- **Copy Bone Weights:** the same machinery, each bone's weight treated as
  a diff, then normalized; masked vertices keep theirs.
- This is the same idea as our conform (smoothed offsets of the nearest
  body vertices, `outfit._anchors`), so a Python re-implementation is
  small, but it does not have to be ours ([headless](#headless)).

### <a id="headless"></a>Command line and headless use

- **BodySlide** batch-builds from the command line: `--groupbuild <groups>`,
  `--build <names>`, `--filter <text>` (5.9.0+), `--targetdir <path>`,
  `--preset <name | file.xml?Name>`, `--trimorphs` (LooksMenu morphs),
  `--quiet` (6.1.0: no dialogs, real exit codes; before 6.1 the exit code
  was always 0), `--conformaddons` (6.1.0). It still creates and shows its
  window, then closes it, so it is not truly headless.
- **Outfit Studio** runs **automation scripts** without user input:
  `OutfitStudio -a <script>` with input files (added in 5.8.0). Scripts
  are XML lists of steps (`Automation.h`), among them `LoadReference`,
  `ImportFile`, `ConformSliders`, `CopyBoneWeights`, `SetBaseShape`,
  `SaveProject` and `ExportFile`, each with the options above, and batch
  modes over a folder of files or over slider sets. So a converted
  outfit can be conformed to CBBE and saved as a project by Outfit Studio
  itself, on the player's machine, with no clicks.
- 6.1.0 also adds an MCP server (`--mcp`); not needed here.

### LooksMenu morphs (Nexus fallout4/mods/12631)

An outfit follows in-game body morphs when it has a `.tri` beside it, a
`BODYTRI` string on its root node naming it, dynamic shapes, and slider
names matching the body's. BodySlide's "Build Morphs" (`--trimorphs`)
writes all of that; built with "CBBE Zeroed Sliders" it is the usual
LooksMenu setup. We never write `.tri` ourselves.

### Body weight (thin, muscular, large)

Vanilla FO4 has no weight morph files: one body per sex, and the engine
scales the body's `_skin` helper bones by the NPC's weight (`MWGT`, three
values summing to 1) through the race's bone scale data. An outfit skinned
to those helpers follows the weight like the body. Our outfits take the
body's bones, helpers included, so they should follow it already
(inferred, not checked in play: [open](#open)).

### <a id="licensing"></a>Licensing and permissions

- **BodySlide/Outfit Studio:** GPL-3. We only run it as a separate
  program on the player's machine and write data files it reads; no code
  is linked or shipped, so our MIT licence is unaffected (the app already
  avoids GPL viewers: [preview](fo4_gui.md#preview)).
- **CBBE** (block read from the official SFW edition page, 107978, same
  authors; the adult page's block could not be read logged out, assumed
  the same):
  - "You're free to use the CBBE body for outfits and NPCs ... Just credit
    us and provide a link back here!";
  - re-uploading the mod or parts of it without notable edits needs
    permission; distribution by or sub-licensing to parties not given
    permission is disallowed; a body mesh modified outside sliders needs
    permission to upload;
  - nothing may be sold, nor outfits using the CBBE body;
  - textures: optional variants may be distributed with credit and links;
    the `.psd` sources may not.
- **What that allows us**, as with [GrilledTurkey](fo4_replacements.md#candidate-mods):
  CBBE is a **dependency only**. The converter reads the player's CBBE
  files and writes fits and projects into the player's own output; it
  never ships a CBBE mesh, texture, `.osd` or slider set, and the output's
  readme credits and links CBBE. Generated `.osd` files hold CBBE's slider
  diffs carried onto our meshes, so a converted output built for CBBE
  must not be redistributed (a Wabbajack list rebuilds it on the user's
  machine instead). Whether publishing generated projects is allowed is
  not stated: ask Ousnius before anyone shares one.

## <a id="males"></a>3. Males

**CBBE is female only. BodySlide is not:** it works with any body that
ships a slider set, and its own Nexus page lists male add-ons (Super Hero
Bodies, Nude SHB, A-Body, BodyTalk). There is no male body as dominant as
CBBE; the field is split.

| Body | Nexus / author | BodySlide | Underwear | Vanilla outfits | Notes |
|---|---|---|---|---|---|
| **BodyTalk** (BT3, BT4) | 72310, DemiDemonArt, v4.0.1 (2026-01) | Yes, plus BodyGen | Adult-flagged (nude) | "Vanilla clothing supported"; BT4 morphs 107550 | Actively kept; the usual choice in 2024-26 guides |
| **A-Body** | 66788, Allnarta, v2.1.1 (2026-09) | Yes, about 190 sliders, LooksMenu | Nude and NeverNude | Vanilla armor adaptation | Built on Atomic Muscle; EVB-compatible UVs; needs the ZeX skeleton and FSMP |
| **Atomic Muscle** | Not on Nexus: Ulfberto, Patreon, v2.0+ | Unverified | Unverified | Unverified | Licence unverified; reachable through A-Body |
| **Super Hero Bodies (SHB)** | 10360, MentalHygiene / smorris2012 (2016) | Yes ("male equivalent of CBBE") | Underwear; Nude SHB is 18071 | A few, plus the user's installed all-outfits conversion 42708 | Old; assets free to use with credit to Leito. The user has the 42708 outfit conversion in MO2 but not the SHB body itself |
| **Enhanced Vanilla Bodies (EVB)** | 22110, Leito86 | No (the base the others build on) | Nude | — | Male and female; "free to use these assets" |

**Vanilla FO4 men without a body mod:** one male body with briefs painted
on its texture, no underwear mesh. Vanilla clothing carries fitted pieces
of that body for bare skin (same texture, same UVs), and weight comes from
bone scaling, so vanilla men need no BodySlide at all. That is exactly the
case our converter handles today (A).

**How males fit the same workflow.** The plan's code is not CBBE-specific:

- route 1 fits FNV's outfits from FNV's own body onto *whatever* body NIF
  is chosen (it already does so for vanilla's), so it needs no vanilla-to-X
  conversion reference, only the body NIF with FO4's skeleton;
- route 2 needs the body's slider set, shape data and reference template,
  which BodyTalk, A-Body and SHB all ship;
- the app detects each body by its slider set file and lists what it
  finds. BodyTalk and A-Body (and through it Atomic Muscle) are the
  male bodies to support first; SHB works the same way.

Men stay on vanilla by default. A male body is less needed than CBBE:
vanilla men show only painted briefs, which FNV's men also wear (as
boxers), so the painted-underwear problem is mostly female. The male
option is for body shape and LooksMenu morphs.

A-Body's dependencies (the ZeX skeleton, FSMP physics) change the
skeleton; whether our retarget still holds on it is an open check.

## <a id="approach"></a>4. The approach

### A "Body" setting, vanilla by default

One setting per sex, chosen in the app and stored with the replacement
profile: **Vanilla FO4** (default) or a **BodySlide body** found in the
player's mod sources (CBBE for women; for men, whichever supported body
they have, [males](#males)). Reasons for vanilla as the default:

- it needs nothing installed and always builds, headless, on every OS;
- CBBE is a player's choice that changes the whole game, vanilla FO4's
  women included; we follow it, never install it;
- CBBE's permissions forbid shipping its files ([licensing](#licensing)), so
  CBBE fits can only be made on the player's machine.

The app detects a body by its files in the mod sources (CBBE:
`Tools\BodySlide\SliderSets\CBBE.osp`, `ShapeData\CBBE\CBBEBody.nif`,
`RefTemplates\CBBE.xml`, the `VanillaToCBBE` conversion reference shipped
with BodySlide), reads its version from the slider set, and greys the
choice out without them. "Required mods" lists it like any other required
mod ([required mods](fo4_gui.md#required-mods)).

### What each body choice changes

| Piece | Vanilla FO4 (A) | CBBE / male body (C) |
|---|---|---|
| Outfit fit target | FO4's vanilla body | the chosen body's zero-slider shape |
| Bare-skin UVs and texture | vanilla body's UVs; painted underwear shows | the chosen body's UVs and its nude texture |
| Body shape | vanilla, fixed | the player's BodySlide preset, via BodySlide projects |
| Naked NPCs | FO4's painted underwear (drift from FNV, below) | the body's own (nude, or its underwear option); FNV underwear armor recommended |
| Weights | A's: FNV's own, blended to the body's near the skin | same, with the chosen body's weights near the skin |
| Seams | to vanilla's wrist and neck edges | to the chosen body's edges (CBBE keeps vanilla's hands; check) |

### Converting outfits to the chosen body

Two routes, and the plan uses both, in this order.

**Route 1: our own Python fit to the body's zero shape (always).** The
fitting code already works against any FO4 body NIF: `body_fit()` reads a
body, its bones, weights, UVs and edges. Point it at the chosen body (read
from the player's mod folder, never copied into the output) instead of the
archive's vanilla body. This alone gives:

- outfits shaped to the chosen body at its zero-slider shape;
- bare skin with the chosen body's UVs on its nude texture, so no painted
  underwear and no scrambled skin;
- seams to the chosen body's wrist and neck.

It is headless, cross-platform and needs no BodySlide. It does not follow
the player's preset.

**Route 2: BodySlide projects the player builds (for presets).** Two ways
to make the projects, both on the player's machine:

- **2a, Outfit Studio does it (preferred where it runs).** The converter
  writes one automation script and runs `OutfitStudio -a` over route 1's
  meshes: `LoadReference` (the body's reference template, e.g. CBBE Body),
  `ImportFile` (the outfit), `ConformSliders`, `SaveProject` (into our
  slider set and shape data folder). The conform is then BodySlide's own,
  exactly as a modder's by hand. Windows, and Linux with the native build.
  The script keeps FNV-based weights: no `CopyBoneWeights` step.
- **2b, our own writer (fallback, any OS).** Python writes the same files
  using the conform rule above. Used where Outfit Studio cannot run
  (macOS) or fails.

Either way, for each converted outfit a BodySlide slider set sits beside
it in the output:

- `Tools\BodySlide\SliderSets\F3NV <source>.osp` (one file per source game
  and sex), one `<SliderSet>` per outfit, `OutputPath` and `OutputFile`
  naming the converted outfit's own path (`Meshes\<static>_female.nif`), so
  a build overwrites only our file;
- `ShapeData\F3NV\<outfit>.nif`: route 1's mesh, the zero-slider base;
- `ShapeData\F3NV\<outfit>.osd`: per slider, per outfit shape, the vertex
  moves, made as Outfit Studio's **Conform** makes them: each outfit vertex
  takes the inverse-distance mix of the chosen body's slider diffs at its
  nearest reference vertices, within a proximity radius
  ([Outfit Studio](#outfit-studio));
- `SliderGroups\F3NV.xml`: the outfits in a group "F3NV <source>" plus
  the body's group (CBBE), so the player's CBBE presets list them.

The player then batch-builds the group with their own preset in BodySlide
(with "Build Morphs" for LooksMenu), or the app runs BodySlide's command
line for them ([headless](#headless)). Route 1's mesh is already in the
output, so a player who never builds still gets a fitted outfit.

**Why not by hand?** The usual modder process (load outfit, load
reference, conform, brush, save) does not scale to FNV's 98 armors times
two sexes, plus FO3's. Automation runs the same steps without hands; the
player can still open any project and brush a bad one.

**Why not apply presets in Python and skip BodySlide?** Possible and small
(a vertex is the base plus each slider's diff times its value), and a
useful fallback on macOS and Linux. But BodySlide is the tool players know,
it writes LooksMenu `.tri` morphs and zap sliders, and it re-runs on a
preset change without reconverting. Keep a Python preset build as a later,
optional fallback only.

### Removing the painted underwear

- **Chosen body (C):** fixed by route 1: bare skin uses the body's nude
  texture with its own UVs.
- **Vanilla body (A):** options, in order of preference:
  1. *Leave it* (accepted 2026-10-08) and say so in the app's Body choice.
  2. *Our own skin texture for FNV outfits' bare skin:* FO4's body texture
     with the underwear painted out, made by our code from vanilla's
     texture. Masking by colour misses the shadows and strap edges, so
     this needs inpainting from the surrounding skin per UV island. A
     derived vanilla texture is ours to ship (Bethesda's own content
     converted, like everything else), but painted-out results are rarely
     clean. Not planned.
  3. *Point A's bare skin at FNV's skin texture* (`UpperBodyFemale.dds`,
     FNV's UVs, FO4's skin shader). Tried: patchy and unlike FO4's hands
     ([history](fo4_spikes.md#spike-4-outfits)). Not planned.

So the real fix for painted underwear is the chosen body. A stays as is.

### FNV's underwear as clothing (both bodies)

Naked converted NPCs should wear what FNV's naked NPCs wear: its modelled
tank top and briefs (female), vest and boxers (male). Convert FNV's
underwear torso shape (`UpperBody` / `Arms:0`, `UnderwearF/M.dds`) once per
sex through the outfit path, as an armor addon with no slot conflict (an
underwear slot such as 36 or 54, checked against FO4's slot use), and give
converted NPCs a skin armor (`WNAM`) of our own: FO4's body addons plus the
FNV underwear addon, as vanilla's `SkinNaked` lists several addons. Only
converted NPCs use it; vanilla races and `SkinNaked` stay untouched.

- On the vanilla body it covers FO4's painted underwear with FNV's.
- On CBBE it keeps naked NPCs dressed as in FNV (CBBE's nude default would
  otherwise be a content change), and it gets a BodySlide project like any
  outfit.
- The player character is the open case: the player's skin comes from
  FO4's race, which we don't override. A player who wants FNV's underwear
  equips it as an item (added to the start inventory), or the player keeps
  their body mod's look.

### How the app offers it

On Setup ([choices](fo4_gui.md#choices)), a **Body** row per sex:

- Vanilla FO4 (default), or each detected body with its version
  ("CBBE 2.7.2 found in MO2 mod 'Caliente's Beautiful Bodies Enhancer
  -CBBE-'"); undetected bodies greyed out with a link to the mod page.
- **Build with BodySlide after converting:** off by default; on shows the
  BodySlide path (detected in the mod sources), the preset (read from the
  player's `SliderPresets`), and where its output goes (a folder the player
  picks; default the output folder's own `Meshes`). On macOS and Linux it
  runs through Wine or Proton, or is marked unavailable
  ([cross-platform](fo4_gui.md#cross-platform)).
- On the Finished screen, when projects were written but not built: "Open
  BodySlide, choose group 'F3NV FalloutNV' and preset X, Batch Build",
  with the command line to copy.
- The choice changes the build's cache keys (outfit meshes depend on the
  body file's hash), so switching bodies rebuilds only the outfits.

Mod-manager neutral: everything reads plain folders and writes into the
output folder; nothing assumes MO2 ([app plan](fo4_gui.md#principles)).

## <a id="profiles"></a>5. Per-world and all-worlds profiles

For FO4, a per-world profile loads one converted game (FNV or FO3) on
Fallout 4; an all-worlds profile loads both, so one character can travel
([target](research/fo4_target.md)). The body plan works in both:

- **No base-game overrides from us.** We write only our own outfit
  meshes, our own ARMA/ARMO, and the converted NPCs' own skin armor.
  `FemaleBody.nif`, `HumanRace` and `SkinNaked` are never touched by the
  converter. CBBE does override vanilla's body, but that is the player's
  mod, installed by them.
- **A body mod is global; the outfits must agree with it.** CBBE replaces
  the body for every woman in every loaded world, vanilla FO4's included.
  So in an all-worlds profile, FNV's and FO3's outfits must be built for
  the same body. The body choice belongs to the output/profile, not to the
  source game: the app records it in each conversion's build manifest and
  warns when two conversions in one output disagree.
- **Per-world:** each profile can pick its own body (an FNV profile on
  CBBE, an FO3 profile vanilla), since each has its own mod list.
- **Keyed per character's starting world:** nothing here needs it. Body
  and outfit meshes are file-level and identical for every character.
- **BodySlide groups per source** ("F3NV FalloutNV", "F3NV Fallout3")
  keep the two games' outfits separately buildable in either profile kind.

## <a id="plan"></a>6. Plan, step by step

Each step is played on its own before the next, one change per play
test. Steps 1 and 2 come after A's step 1 (FNV's own
weights, [human clothing](fo4_build_next.md#human-clothing)), since every
route reuses A's weights and seams.

1. **Know which body the game will draw (S).** A resolver that finds the
   body NIF and texture that win in the player's setup: the mod sources'
   loose files over the archive, in source order (the app's existing
   resolver, `fo4_import/app/files.py`). Record the result and its file
   hash in the build manifest and the outfit cache keys. If the chosen
   Body is Vanilla but a mod overrides `femalebody_d.dds` with a different
   UV layout (CBBE), warn in the app and the build log: today that
   scrambles bare skin. Test: a fake mod folder holding a body NIF with
   moved UVs flips the warning.
2. **Route 1: fit to the chosen body (M).** `body_fit()` takes the body
   NIF (and hands, for the wrist edge) from step 1 instead of always the
   archive's vanilla body. Bare skin takes the chosen body's UVs and
   texture paths; seams pair with its edges. Measure as the spike did, per
   body: mean and 90th-percentile distance of outfit to body, longest
   edges, seam gaps, UV-stretch fallbacks, on the dress, a duster
   (`BountyHunterDuster`), leather armor, a vault suit and the sexy
   sleepwear. Play: CBBE active, CBBE body chosen, the sleepwear and the
   dress worn; no painted bra, no scrambled skin, no gap at wrists and neck.
3. **FNV's underwear as clothing (S-M).** FNV's underwear torso shapes
   through the outfit path, one armor and addon per sex, and a skin armor
   for converted NPCs (FO4 body addons plus the underwear addon). Count
   converted NPCs with no upper-body outfit first, to see how often it
   shows. Play: a naked FNV NPC, on vanilla and on CBBE.
4. **BodySlide projects (M).** `fo4_import/nif/bodyslide.py`:
   - 2a: write the Outfit Studio automation script and the group XML, run
     `OutfitStudio -a` over route 1's meshes (the user's install, path
     from the app), check its exit and that each project exists. First
     check the installed 5.9.1 against the source's step names (the
     source read was 6.x `dev`).
   - 2b: write `.osp`, `.osd` and the group XML in Python; read the body's
     slider set and `.osd` from the player's install (never copied);
     conform each outfit shape per slider with Outfit Studio's defaults.
   - Tests: a round trip of our `.osd` against BodySlide's reader layout; a
     synthetic body whose one slider moves one vertex moves the nearest
     outfit vertex by the same amount and distant ones not at all; 2a and
     2b on the same outfit agree within a small tolerance. By hand: open a
     generated project in Outfit Studio and move sliders.
5. **BodySlide build and morphs (S).** Batch build the group with CBBE
   Zeroed Sliders: the output must equal route 1's meshes (same vertices
   within float error). Then a curvy preset, with "Build Morphs" for
   LooksMenu. Play: a converted woman in an FNV outfit with a non-zero
   preset; a LooksMenu body morph on an NPC moves the outfit with the body.
6. **The app (S-M).** The Body row, detection, Required mods entry, the
   optional BodySlide run, and the Finished screen's instructions
   ([how the app offers it](#approach)). Test off screen, as the other
   screens are.
7. **Males (S-M).** The same steps against the chosen male body
   ([males](#males)). Vanilla FO4 stays the male default.
8. **Docs.** Record the body choice and what each one changes in
   [drift](fo4_drift.md); update [human clothing](fo4_build_next.md#human-clothing)
   and [CBBE and BodySlide](fo4_replacements.md#bodyslide) to point here;
   ROADMAP rows.
## <a id="open"></a>7. Risks and open questions

**Risks**

- **CBBE's permission for generated projects is unstated.** Making them on
  the player's machine fits "free to use the CBBE body for outfits" with
  credit; publishing them may count as distributing "parts of it". Until
  Ousnius says otherwise: never ship, and say so in the output's readme.
- **Loose clothes.** Conform moves each vertex with the nearest body
  vertices; skirts, robes and coat tails far from the body (the dress hem,
  13 units off) may pull oddly under big sliders. Outfit Studio's usual fix
  is masking or brushing per outfit; ours would be a reduced conform
  weight with distance from the body. Measure on the dress and duster.
- **Bare skin seams.** CBBE's neck differs from vanilla's (CBBE.esp
  patches the player's head texture seam); whether CBBE's hands and wrist
  edge match vanilla's is unverified. Route 1 seams to the chosen body's
  edges, so FO4's own hands must match that body.
- **Body updates.** A new CBBE version can change the body or sliders; the
  cache key on the body file's hash makes the converter refit, and the app
  should say "CBBE changed since the last build".
- **16-bit vertex indices** in `.osd`: an outfit shape over 65,535
  vertices needs splitting (none of FNV's comes close).
- **Wine and macOS:** BodySlide and Outfit Studio have no macOS build and
  only anecdotal Proton reports. Route 1 and 2b keep the option working
  without them; only the preset build needs BodySlide.
- **Content drift with nude bodies:** with CBBE's nude body, naked
  converted NPCs would be nude where FNV showed underwear, unless step 3's
  FNV underwear skin is in. Record in [drift](fo4_drift.md) either way.

**Open questions**

1. Ask Ousnius whether converter-generated BodySlide projects referencing
   CBBE may be shared (for a future Wabbajack list).
2. Does FO4's bone-scale weight (`MWGT`) move our outfits with the body?
   Check in play on a heavy and a thin converted NPC, vanilla body.
3. CBBE's hands and wrist edge against vanilla's: measure (read-only)
   before step 2.
4. Which underwear slot for FNV's underwear addon, so it neither hides
   nor is hidden by FO4 and mod items (checked against vanilla's slot use).
5. The player's own body: the player's skin comes from FO4's race, which
   we don't override. Is an FNV underwear item in the start inventory
   enough?
6. A-Body's ZeX skeleton and physics bones: does our FNV-to-FO4 retarget
   and weight mapping still hold on it?
7. Are the automation step names the same in 5.9.1 as in the 6.x source
   read? Read the installed version's changelog or run a one-outfit test.
8. Should one Body choice cover both sexes' defaults (CBBE plus vanilla
   men) as a preset in the app, to keep Setup short?

## <a id="sources"></a>Sources

Read 2026-11-07. Adult-flagged Nexus pages were read through Nexus's
public GraphQL API (name, version, description; no permissions block).

- CBBE: https://www.nexusmods.com/fallout4/mods/15 (description, FAQ
  Q2, Q4, Q5); permissions from the SFW edition
  https://www.nexusmods.com/fallout4/mods/107978; the user's install
  (`C:\Modlists\fo3fnv-in-fo4\mods\Caliente's Beautiful Bodies Enhancer -CBBE-`,
  `meta.ini`, the texture permission text).
- BodySlide and Outfit Studio: https://www.nexusmods.com/fallout4/mods/25,
  https://github.com/ousnius/BodySlide-and-Outfit-Studio (licence,
  releases, wiki "Command-line arguments", "Installation on Linux",
  changelog); source on `dev`: `src/program/BodySlideApp.cpp`,
  `src/program/OutfitProject.cpp`, `src/components/Automation.h`,
  `Automorph.cpp`, `ConformOptions.h`, `DiffData.cpp`, `SliderSet.cpp`,
  `SliderPresets.cpp`, `SliderGroup.cpp`, `RefTemplates.cpp`.
- ProtonDB report: https://www.protondb.com/users/1627290122.
- Male bodies: BodyTalk https://www.nexusmods.com/fallout4/mods/72310;
  A-Body https://www.nexusmods.com/fallout4/mods/66788; Super Hero Bodies
  https://www.nexusmods.com/fallout4/mods/10360 (Nude SHB 18071, SHB
  outfits 42708); EVB https://www.nexusmods.com/fallout4/mods/22110; Atomic
  Muscle https://www.patreon.com/ulfberto (unverified); 2024 body guide
  https://www.nexusmods.com/fallout4/articles/5215.
- LooksMenu: https://www.nexusmods.com/fallout4/mods/12631.
- Body weight: https://forums.nexusmods.com/topic/3419015-scaling-body-parts,
  https://falloutck.uesp.net/wiki/BodyWeight_Struct_-_ActorBase, F4SE
  `GameForms.h` (TESRace bone scale maps).
- Measured here: FNV and FO3 body NIFs and textures in `export/`;
  FO4's body NIF and textures from `Fallout 4 - Meshes.ba2` and
  `Textures*.ba2`; the installed CBBE body's UVs and shapes.
