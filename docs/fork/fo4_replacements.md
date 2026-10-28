# Replacements: the user-editable table and the modlist (plan, step 1 built)

Status: step 1 built 2026-10-08 (the table and its modes for items, in the
cell spike). Creature entries, profiles, the GUI and the modlist below are
designed, not built. Status lives in [ROADMAP.md](ROADMAP.md).

## <a id="direction"></a>Direction: the modlist is a soft requirement (2026-10-10)

The converter makes a complete, playable game on its own: every quest,
line, script, cell and item converts, and anything it cannot rebuild from
FNV's data stands in as Fallout 4's nearest record (an FO4 gun, an FO4
creature, FO4's body). That is FNV *playable*. A Wabbajack modlist is the
**full experience**: hand-made ports of what automation cannot reach
(guns with their own animations, creatures FO4 has no rig for, bodies and
clothing fitted by hand, higher quality assets), wired in by a replacement
profile. Without it the game runs; with it, it looks and plays as FNV.

Why the split: the work that does not automate is open-ended. Guns were
tried twice and parked (FO4's animations fit only FO4's layouts,
[guns](fo4_spikes.md#spike-4-guns)); a creature with no FO4 counterpart
needs a skeleton, ragdoll and behaviour graph made for it
([option 3](fo4_spikes.md#creature-option3)). Mod authors have already
hand-made many of these. The converter keeps what scales (dialogue,
quests, scripts, cells, items, FNV meshes on FO4 rigs: 78% of FNV's and
98% of FO3's creature placements) and leaves the rest to the table.

Rules:

- **Never required to run.** Every entry has a default the converter can
  build alone. A missing or removed mod falls back to the default; it
  never breaks the conversion.
- **Never ships a mod's files.** The modlist installs mods from their own
  pages; the converter only reads the profile and the installed plugins.
  Each mod's permissions are checked before the modlist names it.
- **Pinned versions.** Wabbajack pins each mod's exact files, so a profile
  names records that exist.
- **Coverage is checked, not assumed.** The creature census lists what
  needs a port (FNV geckos 256 placements, giant mantises 126, securitrons
  104, centaurs, spore carriers; FO3 centaurs 53); a profile is measured
  against it.

## <a id="how"></a>How it works

One table maps each FNV form to what shows up in its place. The converter
writes every reference, leveled list, container, outfit and script
property against the table's answer, so one entry changes the form
everywhere it appears.

```
FNV form (EditorID) --table--> stand-in --> converted plugin's records
                                           (placed refs, lists, scripts)
```

Layers, each over the one before, entry by entry:

1. **Converter defaults** (`fo4_import/data/replacements.json`; its layout
   by category and its `_rules` are in [fo4_gui.md](fo4_gui.md#replacement-data)):
   what the converter builds alone (FO4 records, FNV stats, FNV meshes on
   FO4 rigs).
2. **A profile** (`vanilla-fo4`, `fnv-look`, a modlist's), picked at
   conversion time.
3. **The user's file**, which a GUI writes.

A stand-in is a target and a mode. Items have them now (`item`, `stats`,
`fnv`, below). Creatures get the same shape: `item` uses an FO4 race's
own NPC; `fnv` puts FNV's mesh on an FO4 creature's rig (Cheyenne on
Dogmeat, [creatures](fo4_spikes.md#spike-4-creatures)), only where the FO4 creature is the same
animal: FNV's gecko on the deathclaw read as a deathclaw; `rig` keeps
FNV's own skeleton, clips and behaviour on a race of its own (the target is
the NPC copied onto it; [fo4_own_rig.md](fo4_own_rig.md#table), the gecko
first); another mod's record (`"use": "Port.esp|NVGecko"`) uses a port as
it is.
The mod's plugin becomes a master of the converted plugin, as items'
already do.

## <a id="gui"></a>The GUI

Designed in full in [fo4_gui.md](fo4_gui.md#replacements-screen) (two
columns, mods read from any folder, 3D previews); the outline below is the
first sketch.

The table is plain JSON keyed by EditorID, so a GUI is a front end over
it, with no conversion logic of its own:

- **Lists every FNV form by category** (weapons, armor, creatures,
  consumables...) from the export, each with its current stand-in and
  where that comes from (default, profile, user).
- **A picker per form:** FO4's records of the right type by name, the
  installed mods' records (read from the MO2 profile's plugins), and the
  modes that form allows. A preview shows the mesh.
- **Saves the user's file** and offers a reconvert of only what changed
  (the table's answer feeds record writing, so a swap rewrites those
  records and nothing else; FormIDs are hashed from FNV's, so a swap moves
  no other record).
- **A modlist ships a profile;** the GUI shows which entries it sets, and
  the user can still override any of them.

## Step 1: the table (built)

`fo4_import/data/replacements.json`, one entry per FNV item by
EditorID, under its category (since phase 2 of the [app](fo4_gui.md#replacement-data)):

```json
"WeapBBGun": {"use": "Fallout4.esm|PipeBoltAction", "as": "stats",
              "mods": ["mod_PipeBoltAction_Grip_StockFull"]}
```

- `use`: `Plugin|EditorID` of the target record.
- `as`:
  - `item` uses the target record itself (its name, stats, model): the
    old stand-ins (9mm pistol → 10mm, Stimpak → Stimpak, Vault 21 suit →
    Vault 111's);
  - `stats` writes a copy of the target with FNV's name and stats (value,
    weight, damage, magazine, ammo, armor rating): guns by default;
  - `fnv` writes a copy showing FNV's own mesh: melee weapons, headgear and
    the pre-war outfits by default; on an outfit it moves the mesh onto FO4's body
    ([outfits](fo4_spikes.md#spike-4-outfits)); on a gun it builds the mesh on the FO4 gun
    `spike.gun_choice` picks (experimental: hands and reload do not fit).
- `mods`: OMOD EditorIDs that replace a gun's default parts at the same
  attach points; with them only the default combination is kept, so a
  leveled list cannot hand out a variant with the old part. The BB gun
  takes the pipe bolt-action's full stock, for a rifle stance (its
  default grip adds AnimsGripPistol).
- A user file of the same shape (`--replacements file.json` on the cell
  spike) is laid over the defaults entry by entry.
- **Another mod's record** (`"use": "BBGunMod.esp|BBGun"`, `as: item`):
  the plugin is found in the game's Data folder or `--plugin-dirs`
  (MO2 mod folders), appended to the converted plugin's masters, and its
  record's FormID renumbered to ours. Only `item` mode: a `stats` or `fnv`
  copy would carry the other plugin's FormIDs, which would all need
  renumbering field by field. Appending a master changes only the top byte
  of the converted plugin's own FormIDs (the low 24 bits, which the hashing
  sets, stay), as adding a master in xEdit does.

Dropping a weapon mod into the load order does not replace an FNV item by
itself: the converted plugin's leveled lists, containers and placed
references name the converted record. The table entry is what points them
at the mod's record.

## Later steps (designed)

1. **Profiles.** Named tables (`vanilla-fo4`, `fnv-look`, a modlist's)
   that ship beside the defaults, picked at conversion time; the user's
   file still lies over the chosen one.
2. **GUI** ([above](#gui)).
3. **Wabbajack modlist** ([direction](#direction)): installs weapon,
   armor, body and creature mods (permission permitting) plus a profile
   naming their records. The converter only reads the profile; it never
   ships a mod's files. The modlist installs after the conversion, or the
   conversion is rerun with the profile.
3a. **Creature entries.** The table keyed by FNV CREA EditorID as well:
   `item` (an FO4 race's NPC), `fnv` (FNV's mesh on an FO4 rig), or a
   mod's record. Built: the `fnv` path for dogs (played) and the `item`
   path for geckos (an FO4 mole rat, played; FNV's gecko on the deathclaw was played
   and dropped), placed by the cell spike ([creatures](fo4_spikes.md#spike-4-creatures)).
4. **Copy mode for mods' records.** `stats` on another plugin's record
   needs its FormID fields renumbered (field layouts from xEdit's
   definitions); worth it only if users want FNV stats on a mod's model.
5. <a id="bodyslide"></a>**CBBE and BodySlide.** FNV's outfits are cut for
   FNV's body, and FO4's base body carries painted underwear
   ([outfits](fo4_spikes.md#spike-4-outfits)). CBBE, the common FO4 body
   replacer, brings its own body, textures without underwear, and
   BodySlide, which reshapes outfits to any body preset. The converted
   outfits are already FO4 worn meshes (skinned to FO4's body bones, FO4
   segments), so they fit its known pipeline:
   - **By hand, now:** open a converted outfit in Outfit Studio, load the
     CBBE reference (its vanilla-to-CBBE conversion reference, as the
     outfit sits on FO4's vanilla body), conform, fix by brush, save as a
     BodySlide project. The usual conversion process.
   - **Automated, later:** the converter writes the BodySlide project
     itself: the outfit as the project's shapes, CBBE as its reference
     (read from the player's install, never shipped), and the slider data
     made as Outfit Studio's conform makes it, each outfit vertex taking
     the slider moves of the reference vertices nearest it. Bare skin then
     uses the CBBE body: one body and texture for skin and hands, no
     painted underwear. Open: CBBE's permissions for generated
     conversions, and whether conform alone fits FNV's loose clothes
     (skirts, robes) or needs per-outfit fixes.
6. <a id="candidate-mods"></a>**Candidate mods (noted 2026-10-10).**
   - [GrilledTurkey](https://www.nexusmods.com/profile/GrilledTurkey): many
     FO3/FNV adaptations for Fallout 4. Candidates for the modlist, or as
     dependencies if creature conversion ([creatures](fo4_spikes.md#creature-census))
     keeps creatures with no FO4 counterpart through existing ports rather
     than rebuilt skeletons.
   - **Permissions (read 2026-10-25):** stricter than first noted. The
     About Me (retired) allows edits and patches, bans reuploading
     unedited files or ESMs, and allows reuploads only of substantially
     changed files that need the original as a requirement. Each creature
     mod's permission block is stricter still: asset use needs permission
     or is "not allowed … under any circumstances" (Cazadores, Yao Guai,
     Brahmin), conversion to other games is not allowed, and the authors
     no longer read messages. Only a user-installed dependency (the
     modlist names the mod; nothing of theirs ships) fits. Their custom
     creatures (new skeleton, Havok ragdoll, behaviours, animations; 3ds
     Max 2013 with Bethesda's official exporter): Mojave Mantises 48442,
     Geckos 50275, the Securitron in the Capital Wasteland Robot Pack
     52147, Cazadores 57161, Bighorners 57991, Capital Wasteland Centaurs
     59379. See the prior-art report `reports/FO4 custom creature rig prior art.md`.

## Defaults now

- Guns: FO4's guns (`stats`), the 9mm SMG on the submachine gun, the BB gun
  on the pipe bolt-action with a full stock.
- Melee weapons (bat, rolling pin, switchblade, tire iron) and headgear
  (hockey mask, pre-war hat, reading glasses): FNV's meshes (`fnv`).
- Outfits: the 12 pre-war outfits on FNV's meshes (`fnv`), their variants
  as material swaps ([outfits](fo4_spikes.md#spike-4-outfits)).
- The old stand-ins: FO4's records (`item`).
- **Anything the table leaves out** (2026-10-12, so real NPCs are dressed
  and armed): an armor goes on FNV's mesh (`fnv`) on a template for what
  it covers, by FNV's biped slots (the table's `_rules.armor`: upper body
  on ClothesPrewarShortSleeves, head, headband or hat on
  ClothesMobsterhat, eyeglasses on ClothesEyeGlasses, mask or mouth on
  Clothes_Raider_SurgicalMask); a gun is the FO4 gun gun_choice picks for
  it, with the parts it matched, under FNV's name and stats (`stats`); a
  melee weapon by its animation type (`_rules.melee`): hand to hand on
  FO4's Knuckles, one-handed on FNV's mesh on the TireIron, two-handed on
  the BaseballBat. A table entry still wins.
