# Item replacements: the user-editable table (plan, step 1 built)

Status: step 1 built 2026-10-08 (the table and its modes, in the cell
spike). The GUI, profiles and modlist steps below are designed, not built.
Status lives in [ROADMAP.md](ROADMAP.md).

## Why

Converting FNV's items can only go so far automatically. Guns showed where
it stops: FNV's mesh on a Fallout 4 gun's skeleton renders, but FO4's
animations put the hands and the reload where that FO4 gun's parts are
(played twice: [guns](fo4_spikes.md#spike-4-guns)). So every FNV item
gets a stand-in the user can change: FO4's own record, a copy with FNV's
stats, FNV's own mesh, or another mod's record (a BB gun from a weapon
mod). The converter ships defaults that fit; the user, a GUI or a modlist
overrides them.

## Step 1: the table (built)

`fo4_import/data/item_replacements.json`, one entry per FNV item by
EditorID:

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
2. **GUI.** The conversion GUI lists every FNV item the export has, by
   category (from the export: WEAP, ARMO, ALCH, AMMO, MISC...), with its
   current stand-in and a picker: FO4 records by type and name, the
   installed mods' records (read from the MO2 profile's plugins), and the
   modes each allows. It saves the user's file.
3. **Wabbajack modlist.** An independent modlist that installs weapon and
   armor mods (permission permitting) plus a replacement profile naming
   their records. The converter only reads the profile; it never ships a
   mod's files. The modlist installs after the conversion, or the
   conversion is rerun with the profile.
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
   - **Permissions:** the mod pages ask permission for asset use. The
     author's About Me says they have retired, and reads as allowing use if
     the original mod is downloaded and credited. The modlist route
     (installing the original mod) fits that. Confirm the exact terms
     before shipping anything that depends on them.

## Defaults now

- Guns: FO4's guns (`stats`), the 9mm SMG on the submachine gun, the BB gun
  on the pipe bolt-action with a full stock.
- Melee weapons (bat, rolling pin, switchblade, tire iron) and headgear
  (hockey mask, pre-war hat, reading glasses): FNV's meshes (`fnv`).
- Outfits: the 12 pre-war outfits on FNV's meshes (`fnv`), their variants
  as material swaps ([outfits](fo4_spikes.md#spike-4-outfits)).
- The old stand-ins: FO4's records (`item`).
