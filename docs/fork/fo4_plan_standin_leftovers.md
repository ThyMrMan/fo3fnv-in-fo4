# Stand-in leftovers on items (plan)

What converted items, armor, weapons and projectiles still inherit from the
Fallout 4 record they are copied from, and how to measure and fix it field by
field. Design only: building any phase needs the go-ahead. Status lives in
[ROADMAP](ROADMAP.md) only.

## Contents

- [Goal and rows](#goal)
- [What exists](#exists)
- [The framework](#framework)
- [Phases](#phases)
- [What the play test should tell us first](#play-test)
- [Open questions](#questions)

## <a id="goal"></a>1. Goal and rows

Every converted item is a copy of a Fallout4.esm record, or that record
itself, and any field the converter does not overwrite keeps FO4's value.
This plan extends the creature leftover check to items, so the build lists
what each converted record still inherits. The fixes then go field by field.

| Issue-plan row | Size | Doc |
|---|---|---|
| Aid item and armor models | M | [drift](fo4_drift.md#recorded) |
| Stand-in clothing bonuses | M | [damage threshold](fo4_pipeline.md#damage-threshold) |
| Outfits on FO4's body | M | [human clothing](fo4_build_next.md#human-clothing) |
| Projectile looks and sounds | L | [projectile copies](fo4_pipeline.md#projectile-copies) |
| Body choice: CBBE and BodySlide | L | [body plan](fo4_bodies_cbbe.md), kept as is |

The rows come from the [issue plan](fo4_issue_plan.md#medium) and its
[large](fo4_issue_plan.md#large) section.

## <a id="exists"></a>2. What exists

**The creature check.** `fo4_import/spike/stand_in_fields.py` holds
`FIELDS`, a map from each NPC_ subrecord to a mark (keep, fnv, drop, open)
and the template slots that supply it. `leftovers(stand_in, built, name)`
compares the stand-in's subrecords with the copy's and returns
`'<mark> <tag>'` for each fnv or open field kept whole and each drop field
with a value that survived. It raises ValueError on a field with no mark.
`checked(counts, stand_in, name, edit)` wraps a clone edit and counts
`stand-in leftover <mark> <tag>`. It runs in the `Creatures` writers
(`creatures.py`, four call sites) and `Npcs._template_actor` (`npcs.py`).
Tests: `tests/test_fo4_stand_in_fields.py`. The marks and their reasons are
in the [leftover check](fo4_creature_audit.md#leftover-check).

**Armor and weapons.** `fo4_import/spike/equipment.py`:
- `Equipment._copy` copies the template's subrecords, replaces those it is
  given, and leaves out `DROPPED` (VMAD, DAMA, INRD). Everything else is
  the template's.
- `Equipment.armo` writes FNV's value, weight, health (DATA) and DT as the
  rating (FNAM). `_headgear` and `_outfit` put FNV's mesh on it in `fnv`
  mode. When neither takes a piece, it keeps the template's models, counted
  as `ARMO on the template's models (<why>)` by `_on_template`.
- `Equipment._world` keeps the template's world model when FNV has none,
  counted as `ARMO on the template's world model (FNV has none)`.
- `Equipment._resist` replaces the template's EITM only when FNV gives a DR
  (6 armors). Every other copy keeps the template's EITM.
- `Equipment._addon` builds an ARMA keeping the template addon's RNAM,
  DNAM and MODL (`ADDON_KEPT`).
- `Equipment._weapon` writes FNV's weight, value, damage and criticals over
  the template's DNAM and CRDT. `_write` is the one place WEAP, ARMO and
  ARMA records are packed.

**Measured for this plan (Fallout4.esm, 2026-11-08).** Of the replacement
table's armor and weapon targets, these carry an EITM:

| Template | EITM |
|---|---|
| ClothesPrewarShortSleeves (the upper-body default rule) | EnchClothingCHR_END |
| ClothesMobsterhat (the head and hat rule) | EnchClothingLuck |
| ClothesEyeGlasses (the eyeglasses rule) | EnchClothingPerception |
| ClothesPrewarWomensCasual | EnchClothingPER_CHR |
| ClothesPreWarDress, ClothesPrewarSweaterVest, ClothesBathrobe, ClothesSuitDirty_Black, ClothesSuitDirty_Grey | EnchClothingCharisma2 |
| AlienBlaster, Flamer, WeapMirelurkhunter01 (weapons) | AlienDisintegrationEnch, FlamerFXEnchFireHit, MirelurkHunterSpitAttackSpell |

So every FNV upper-body piece, hat and pair of glasses the default rules
cover inherits an FO4 stat bonus unless it has a DR. The source stack has
186 ARMO with their own EITM (read through `source_walk`). The export's
`ARMO.txt` has no EITM line, so `_fnv_fields` would read it from the ESM,
as it reads DNAM.

**Aid items.** `fo4_import/data/replacements.json` names 7 consumables
`item` (Stimpak, Morphine as Med-X, RadX, BloodPack, Cram, PorkNBeans,
SugarBombs01), the lockpick as the bobby pin, and two armors (PipBoy,
VaultSuit21 as Vault 111's suit). `item` means the Fallout4.esm record
itself (`Items.shared`, from `replacements.items`). Every other ALCH is
built by `Consumables.alch` on FNV's own model, with only the preview
(PTRN) and sounds (YNAM, ZNAM, CUSD) copied from a category template. The
status page says "many aid items"; the table shows those 7.

**Projectiles.** `fo4_import/spike/projectile_copies.py`:
`ProjectileCopies.copy` copies the stand-in PROJ and writes FNV's range,
and speed and gravity for flying types (`flight`). `_explosion` copies the
stand-in's EXPL with FNV's force, damage and radius (`blast`). `with_model`
already puts FNV's model on thrown and `own_models` copies. FNV's PROJ
export carries `Model.MODL`, `NAM1` (muzzle flash model), `DATA.Light`,
`DATA.MuzzleFlashLight` and `DATA.Sound` for all 95 records.

**Converters to reuse.** `CellBuilder.mesh` (`cell.py`) converts an FNV
model once. `Sounds.descriptor` (`sounds.py`) turns an FNV SOUN into an
SNDR. The cell builder already makes LIGH bases (`CellBuilder.record`).

**Outfit fit.** `fo4_import/nif/outfit.py`: `BodyFit.skin` gives each
outfit vertex FO4's body weights at its nearest surface point, so a worn
mesh inherits FO4's body weights. `fo4_import/nif/creature.py`:
`Pair.own_weights` and `_targets` keep FNV's own weights for super mutants.

## <a id="framework"></a>3. The framework

**One check, per record type.** Generalize `stand_in_fields` from NPC_ to a
table per signature: `FIELDS[b'NPC_']` (today's), plus ARMO, ARMA, WEAP,
PROJ, EXPL. `leftovers` and `checked` take the signature. The marks keep
their meaning, and a field with no mark still stops the build, so a new
template brings its new fields to a decision.

Two additions the creature check does not need:
- **Packed fields.** PROJ DNAM holds the light, muzzle flash light, sound
  and explosion as FormIDs at fixed offsets; WEAP DNAM holds ammo, value
  and damage. A mark may name `DNAM@<offset>` as well as a whole subrecord.
  The offsets come from xEdit's FO4 definitions in `references/FO4Edit 4.1.5f`
  (not yet read for this plan).
- **A list, not only counts.** Besides the counts, each leftover is written
  as one row (signature, FNV EditorID, template EditorID, mark, field) to a
  file in the build output. `item`-mode entries go in as `whole` rows,
  since they inherit everything. The three `ARMO on the template's ...`
  counts become rows too.

**Where it runs.** `Equipment._write` (WEAP, ARMO, ARMA) and the two
writes in `ProjectileCopies` (PROJ, EXPL). Both already know the template:
`Equipment._template` and `ProjectileCopies.vanilla`.

**Why this covers the rows.** Each row is a field FO4 supplies: EITM on
clothing; MODL and MOD2 on `item` and template-model pieces; PROJ models,
lights and sounds. The list gives each row its measured size and closes it
when the count reaches zero. Outfit fit and CBBE are mesh data, not record
fields. The list only names which addons wear FO4-weighted meshes; their
measure is edge stretch, as in [human clothing](fo4_build_next.md#human-clothing).

### <a id="dll"></a>DLL decisions

None. Every row is record or mesh data the engine reads as written.

## <a id="phases"></a>4. Phases

1. **Clothing enchantments (S).** Add ARMO and ARMA marks (EITM `fnv`) and
   run the check in `Equipment._write`. Drop the template's EITM on every
   ARMO copy; `_resist` still adds the DR one.
   - Check: a test in `tests/test_fo4_stand_in_fields.py` for ARMO; the build
     count `stand-in leftover ARMO fnv EITM` is 0. In game: a converted
     pre-war outfit, a fedora and glasses show no FO4 stat bonus in the
     Pip-Boy.
   - Depends on: the play test only.
2. **The full audit (M).** WEAP, PROJ and EXPL marks with packed DNAM
   fields, the row file, and `item`-mode and template-model rows.
   - Check: tests for packed marks and the row file; the first measured
     list, recorded in this plan by signature and field.
   - Depends on: phase 1.
3. **FNV's own armor effects (M).** Read EITM in `_fnv_fields`; convert
   each FNV armor ENCH to an FO4 Constant Effect ENCH, as `_resist` builds
   one (`effect_pair`, `pack_explosion_ench` with `ENIT_ARMOR`), merged
   with the DR effect when both exist.
   - Check: a count of FNV armor effects made and dropped (by actor value);
     in game, one FNV piece with a stat effect from the measured list shows
     it.
   - Depends on: phase 1. How FNV's 186 effects map to FO4 actor values is
     not yet known.
4. **Projectile looks and sounds (M).** On each PROJ copy: FNV's model
   through `CellBuilder.mesh` and `with_model`, its muzzle flash model,
   lights through the cell's LIGH conversion, its sound through
   `Sounds.descriptor`. Per stand-in type, as phase 2's list shows; a
   hitscan beam may need to keep FO4's beam model.
   - Check: phase 2's PROJ rows for model, light and sound drop to the
     accepted ones; in game, the plasma rifle bolt and the 40 mm grenade
     look and sound like FNV's.
   - Depends on: phase 2.
5. **Aid items and the last armor models (M).** For each `item` row:
   census what Fallout4.esm ties to the record (perks, form lists, scripts,
   the stimpak keyword). Where nothing would break, move it to FNV's own
   record; where it would, a `stats` copy on FNV's model. Pieces left on
   the template's models get FNV's mesh where a mesh path exists.
   - Check: `whole` rows drop to the accepted ones; in game, the Stimpak
     heals, Med-X works, and both show FNV's models.
   - Depends on: phase 2. See [open questions](#questions).
6. **Outfit fit (M).** Steps 1 to 3 of
   [human clothing](fo4_build_next.md#human-clothing): FNV's own weights,
   sharing `creature._targets` with the super mutants; the wrist taper;
   dismemberment segments. Step 1 is played on its own.
   - Check: edge stretch with an arm raised and a leg forward on the dress,
     `BountyHunterDuster`, leather armor and a vault suit, old against new.
   - Depends on: nothing in this plan; can run beside phases 2 to 5.
7. **Body choice (L).** The [body plan](fo4_bodies_cbbe.md#plan), unchanged.
   - Depends on: phase 6 step 1, as that plan says.

## <a id="play-test"></a>5. What the play test should tell us first

- **Clothing bonuses.** Does a converted pre-war outfit show FO4's CHR/END
  bonus in the Pip-Boy? If not, phase 1 is smaller than measured.
- **Armor DR.** Does the trenchcoat or the rebreather show its DR
  enchantment (built 2026-11-08, not played)? Phase 3 builds on the same
  enchantment shape.
- **Aid items.** Which FO4 traits of the Stimpak and Med-X show (model,
  name, heal amount, use sound)? That sets how much phase 5 must keep.
- **Projectiles.** Which looks are wrong enough to matter: the plasma bolt,
  the laser beam, grenades in flight. That orders phase 4.
- **Outfits.** Skirts and coat tails splitting between the legs, and the
  wrist seam. That sets phase 6's priority against the others.

## <a id="questions"></a>6. Open questions

- Where FNV gives an armor no effect, is the FO4 bonus dropped (phase 1) or
  kept as a feature? This plan drops it.
- Which Fallout4.esm systems name the Stimpak and the other `item` aid
  records directly, rather than by keyword? Not yet measured.
- Do FNV models render on FO4's hitscan beam projectiles? Not yet tested.
- The status page says "many aid items" show FO4 models; the table names 7.
  Phase 2's list settles the count.
- Should the three weapon template enchantments (the Alien Blaster's
  disintegration, the flamer's fire) stay as `keep`? They are effects
  FNV's own guns also show, but this is not verified.
