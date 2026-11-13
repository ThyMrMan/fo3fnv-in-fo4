# Fallout 3's child player on Fallout 4

**Code:** `script_convert/command_rows.py` (`setscale`), `script_convert/command_rows_fallout4.py`
(no rows yet for `AgeRace`, `SetPCToddler`, `SetPCYoung`, `MatchRace`),
`fo4_import/spike/npcs.py` and `equipment.py` (child NPCs on `HumanChildRace`).

How the Vault 101 childhood (and Tranquility Lane) should play in the FO4
conversion. A plan: the age-1 scale already converts; the age-10 child
race is designed here and needs an in-game spike before it is built.
Status is in [ROADMAP.md](ROADMAP.md#fo4-app); the spike itself is
[fo4_fo3_plan.md](fo4_fo3_plan.md).

## Contents

- [What Fallout 3 does](#fo3)
- [What we convert today](#today)
- [Player scale on Fallout 4](#scale)
- [The toddler walk](#toddler)
- [A child race for the player](#child-race)
- [The route per age](#route)
- [The child-race spike](#spike)
- [The in-game test](#spike-test)

## <a id="fo3"></a>What Fallout 3 does

Read from `export/Fallout3.esm` (QUST stage result scripts, SCPT):

| Quest | Age | Player changes |
|---|---|---|
| CG00 | birth | `DisablePlayerControls`, scripted packages (`CG00PlayerSection0`-`5`) hold the view, imagespaces `CG00BlackScreenISFX`, `CG00BirthISFX`, `CG00BirthBaseISFX`; stage 12 `ShowRaceMenu`; stage 15 `MatchRace`/`MatchFaceGeometry` the four Dads to the player; stage 19 `SetPCYoung 1` |
| CG01 | 1 | stage 0 `player.setscale .4`; stage 1 `SetPCToddler 1` (toddler walk), `SetPCYoung 1`, `SetNoActivationSound QSTBabyBabble`, look-only controls; stage 19 `player.setscale 1`, `SetPCToddler 0` |
| CG02 | 10 | stage 1 `SetPCYoung 1`, **`player.AgeRace -1`** (to the child race), removes all items, equips `KIDVaultSuitChild101` and the Pip-Boy; stage 30 **`player.AgeRace 1`** back to adult, `vaultsuit101` |
| CG03 | 16 | stage 1 `SetPCYoung 1` only: adult race, full size |
| CG04 | 19 | stage 0 `SetPCYoung 0` |
| MQ04 (Tranquility Lane) | child | `MQ04Script`: `SetPCYoung 1`, `player.AgeRace -1`, `MQ04PlayerOutfit`; `MQ04PlayerContainerScript`: `Player.AgeRace 1` on return to Vault 112 |

So the 10-year-old is a child race, not full size; the brief that started
this plan had it wrong. `AgeRace` follows the race's Older/Younger links
(GECK wiki, `AgeRace`); FO3's `CaucasianChild`, `AfricanAmericanChild`,
`AsianChild`, `HispanicChild` have the Child flag (DATA flag 4), not
Playable, height 0.8. `SetPCYoung` gives the player default hair and no
face attachments (GECK wiki). `SetPCToddler 1` picks the toddler walk
animation set. No stage changes the camera, collision or the playpen
beyond the gate's open state.

**Export gap:** `tes4_export` writes no RACE `ONAM`/`YNAM` (older/younger
race), so `AgeRace`'s authored links are missing from the export.

## <a id="today"></a>What we convert today

Measured in `temp/fo4_scripts/Fallout3.esm` (the 2026-11-12 spike build):

- `player.setscale .4` / `1` → `Game.GetPlayer().SetScale(0.4)` / `(1)`
  (the shared `setscale` row, `actor_only objref_shared`).
- `SetPCToddler`, `SetPCYoung`, `AgeRace` and `MatchRace` → `;NE: TODO:`
  comments, so they do nothing.

Consequence at age 10: the player stays on `HumanRace` and is given the
converted child jumpsuit (`KIDVaultSuitChild101` → a copy of
`Armor_Vault81_UnderwearChild`, [child bodies](fo4_pipeline.md#child-bodies)),
whose only addon `AAVault81SuitChild` draws on `HumanChildRace` (and
`GhoulChildRace`). The player shows a naked adult body at the birthday,
and the same in Tranquility Lane with `MQ04PlayerOutfit`.

## <a id="scale"></a>Player scale on Fallout 4

- `ObjectReference.SetScale` works on any reference (FO4 CK wiki,
  `SetScale_-_ObjectReference`). Vanilla never scales the player: no
  `GetPlayer().SetScale` or `PlayerRef.SetScale` in the Fallout4.esm and
  DLC sources (`references/fo4_scripts/Base`).
- Community reports, not engine evidence:
  - first person sees the smaller size ("everyone ... taller than you in
    first person", Player Scale Compatibility,
    [nexus 48350](https://www.nexusmods.com/fallout4/mods/48350));
  - movement speed and jump scale with size (the same mod compensates
    both);
  - furniture, terminal and power-armor entry animations misalign, and
    aiming down sights is off (48350 scales the player back to 1 inside
    furniture; Custom Scale Fix, nexus 56827, targets ADS);
  - the collision capsule does not follow `SetScale`: a tiny player walks
    through rocks (Steam discussions).
- A reference's scale is saved with it, so `SetScale(1)` must run before
  the age-1 section can end any other way.

For CG01 none of that bites: Baby Steps has no furniture, terminal, weapon
or power armor, the room is small and walled, and the toddler is meant to
be slow. An unscaled capsule can only be too big, which a vault door and the
playpen gate (an adult-sized door) still pass. Play has to confirm it.

## <a id="toddler"></a>The toddler walk

Fallout 4 has no toddler or crawl locomotion. `ChangeAnimArchetype` takes
the core archetypes (Confident, Depressed, Elderly, FastWalk, Friendly,
Irritated, Nervous, Player, Scared, Shocked) and `ChangeAnimFlavor` the
flavors (Smoking, HoldingBaby, HandsBound...) (FO4 CK wiki); none is a
toddler, and they change the third-person MT subgraph only, which the
first-person toddler never sees. A new toddler set would mean authored
animations. **Accepted drift:** `SetPCToddler` stays unconverted.

## <a id="child-race"></a>A child race for the player

From `references/Fallout4.esm` (RACE, ARMA):

| | HumanRace `00013746` | HumanChildRace `0011D83F` |
|---|---|---|
| DATA flags | `0x50A08943` (Playable, FaceGen Head, Walks, ...) | `0x50208947` (the same plus **Child**, minus Allow Pickpocket) |
| Height M/F | 1.0 / 0.98 | 0.825 / 0.825 |
| Skeleton / behavior | `CharacterAssets\skeleton.nif`, `RaiderProject.hkx` | the same files |
| Tint templates (TETI) | 306 | 46, different indices |
| Face morph regions (FMRI) / presets (MPPI) | 64 / 370 | 0 / 0 |
| Skin | `SkinNaked` | `SkinChildNaked`: `NakedChildTorso` and `NakedChildHands` carry **first-person** models (`1stPersonMaleBody.nif`, `1stPersonMale/FemaleHands.nif`) |
| `PipboyAA` (the player's Pip-Boy) | listed | **not listed** (only `PipboyVault81AA` lists it) |

So `HumanChildRace` is flagged Playable, shares the player's skeleton and
behavior graph (every first-person, Pip-Boy and locomotion animation
loads), has first-person skin, and Bethesda's child vault suit has a
first-person model. Missing: the Pip-Boy addon, the face sculpt, and the
player's tints.

The crash: Custom Playable Children
([nexus 19401](https://www.nexusmods.com/fallout4/mods/19401), read-only
for ideas) says `player.setrace` to the vanilla child races crashes the
game, and blames tinting: the player's tint layers name templates the
child race lacks (306 against 46 above). Its fix is its own race with its
own presets, plus `SetScale 0.825` on the player, and `SetRace` back to
`HumanRace` for an adult. Its notes add that the female lipstick tint
turns black across the switch, so tint data survives a race change. That
matches vanilla: `SystemPowerArmorScript` swaps the player to
`PowerArmorRace` and back with `SetRace` and keeps the face, and
`PowerArmorRace` has FaceGen Head with **no** tint templates (0 TETI) and
HumanRace's 64 morph regions. The `scale 0.825` step suggests the race's
height is not applied to the player; the spike measures it.

## <a id="route"></a>The route per age

| Age | Route | Why |
|---|---|---|
| birth (CG00) | as converted: held packages, imagespaces, the race menu | nothing age-specific beyond the camera hold, already `TES4PlayerControls.HoldPlayer` |
| 1 (CG01) | **scale only**, as FO3: `SetScale(0.4)`, back to 1 at stage 19 (converted today) | FO4-native, no furniture or weapons in the section; toddler walk is [drift](#toddler) |
| 10 (CG02) and Tranquility Lane (MQ04) | **a child race** of our own, `F3NV_PlayerChildRace`, through `AgeRace` | the child outfits only draw on child races, and FO3 makes a child here; scaling an adult would still be naked |
| 16 (CG03) | **as FO3**: adult race, full size | FO3 changes nothing but hair |
| `SetPCYoung` | drift, no conversion | default hair and no face attachments for the teen and child; the child race brings its own head |

No DLL: every step is a record or Papyrus.

## <a id="spike"></a>The child-race spike

Built only after one in-game check, since the crash is a community report:

1. **Race record.** A copy of `HumanChildRace` written into the game
   plugin as `F3NV_PlayerChildRace` (FormID derived from that EditorID):
   Child flag kept, 0 tint templates and HumanRace's 64 morph regions as
   `PowerArmorRace` has, so the player's tint layers resolve to nothing
   instead of a missing template. The head stays the child race's default
   (FO3's `SetPCYoung` shows default hair too). Generated by the converter
   from Fallout4.esm, not shipped as an asset.
2. **Pip-Boy.** An addon copy of `PipboyAA` drawing on the new race,
   added to the converted Pip-Boy armor, so the age-10 Pip-Boy shows in
   first person and the menu.
3. **Clothes.** The new race added to the additional races of the child
   addons our replacements already use (`AAVault81SuitChild`, the kid
   clothes), in our copies only (no base-game override).
4. **`AgeRace`.** A Fallout 4 row: `TES4Polyfill.AgeRace(ref, steps)`:
   a younger step from `HumanRace` sets `F3NV_PlayerChildRace` (and
   `SetScale` to the race height if the spike shows the height is not
   applied), an older step from it sets `HumanRace` and scale 1. FO3's
   authored Older/Younger links decide which races pair once the exporter
   writes RACE `ONAM`/`YNAM`; until then the polyfill knows the one pair.
   A change to `static_scripts` rebuilds every masterless plugin's scripts
   ([rule](../../CLAUDE.md#static-scripts-rebuild-all)).
5. **`MatchRace`.** `CGnnDadREF.MatchRace player` at the birth matches
   the Dads to the player's race; on FO4 every human is `HumanRace`, so it
   stays a no-op.

The [in-game test](#spike-test) comes first.

## <a id="spike-test"></a>The in-game test

**The result decides the route.** If `F3NV_PlayerChildRace` plays
cleanly (no crash, body and Pip-Boy drawn, face back after the switch),
the [spike](#spike) is built as written. If only the tinted variant
works, the spike keeps the tint templates. If both crash, the fallback is
the 19401 approach: child face presets on the race and a `ShowRaceMenu`
limited to them at the birthday, which is a larger piece.

**The kit.** `F3NV_ChildRaceTest.esl` (`fo4_import/spike/child_race_test.py`),
a light master on Fallout4.esm only, so it loads beside any save:

```
py -3.14 -m fo4_import.spike.child_race_test --out D:\scratch\child_race_test
```

| Record | Object id | What it is |
|---|---|---|
| `F3NV_PlayerChildRace` "Player Child (no tints)" | `E43` | HumanChildRace copy, no tint templates, HumanRace's 64 morph regions |
| `F3NV_PlayerChildRaceTints` "Player Child (tints)" | `BD0` | plain HumanChildRace copy (46 tint templates) |
| `F3NV_SkinChildNaked` | `B31` | the child skin, its torso and hands addons copied to draw on both races |
| `F3NV_ChildRaceTestVaultSuit` "Vault 81 Jumpsuit" | `A86` | the Vault 81 child jumpsuit, its addon drawing on both races |
| `F3NV_PipboyChildAA` | `C23` | the Pip-Boy addon on both races |
| `Pipboy` (Fallout4.esm `00021B3B`) | override | lists `F3NV_PipboyChildAA` after vanilla's addon |

In game a light plugin's FormID is `FE`, its 3-digit slot, then the
object id; `help` prints it. Deploy it as the MO2 mod
`F3NV - Child Race Test`, enabled, below the other plugins.

**Steps.** Write down each "note" line; on a crash, stop and send the logs
listed at the end.

1. Load a Fallout 4 save past Vault 111 (Pip-Boy on the wrist), or a
   Vault 101 save if the Fallout 3 build exists. Save it as
   `childtest-base`. Note: which save.
2. Open the console: `help F3NV_PlayerChildRace 4`. Note the two RACE
   FormIDs and the ARMO FormID of `F3NV_ChildRaceTestVaultSuit`.
3. `player.setrace <no-tints race id>`. Note: crash or not; how long the
   body took to appear.
4. First person: look down and at the hands, walk, run, crouch. Note: are
   hands and arms drawn; camera height (lower than adult?); any stretched
   or missing parts.
5. Third person (F): turn the camera around the player. Note: body size
   (child or adult height), head (child head, adult head or none), hair,
   skin color of face against body.
6. If the body is adult height: `player.setscale 0.825`, and note whether
   that is needed. Leave it for the rest of the test.
7. Open the Pip-Boy (Tab). Note: is the device drawn on the wrist, do the
   tabs work, close it again.
8. `player.additem <suit id> 1`, then equip "Vault 81 Jumpsuit" from the
   Pip-Boy. Note: drawn in first and third person.
9. Walk through a door into another cell and back. Note: crash or not;
   anything changed after the load.
10. Save as `childtest-child`, load it. Note: race, size, suit and Pip-Boy
    after the load.
11. `player.setrace 00013746` (HumanRace), `player.setscale 1` if step 6
    used it. Note: is the original face back (shape, skin tone, makeup,
    hair), any black or missing tints.
12. Save as `childtest-adult`, load it. Note: the face again.
13. Load `childtest-base` and repeat steps 3-12 with the tints race id.

**On a crash,** send from `Documents\My Games\Fallout4\F4SE\` (or the
OneDrive `Documents` copy):

- the newest `crash-<date>.log`: its first 30 lines (the exception and the
  call stack) and the PROBABLE CALL STACK and REGISTERS sections; a stack
  through `BSFaceGen`, `TintTemplate`, `BGSCharacterTint` or a
  `FaceGen`/`Tint` name points at tints, as 19401 reports;
- `F3NV.log` only when the save also runs our converted game plugins (the
  plain FO4 save writes nothing there);
- which step crashed and which race id was set.
