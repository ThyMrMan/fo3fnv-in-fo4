# FNV thrown weapons, mines and placed explosives (2026-11-05)

**Status.** All parts are built 2026-11-06, not deployed or played
([as built](#built)). The parts below are the design record; where they
differ from what was built, [as built](#built) wins.

**Goal.** FNV's grenades, mines, placed explosives and thrown melee weapons
are real items: picked up where they lie, carried by the NPCs and lists that
give them, thrown or placed with FNV's damage, and countable by scripts and
conditions.

## Contents

- [Where things stand](#now)
- [Part 1: grenades, mines and placed explosives on FO4 templates](#templates)
- [Part 2: FNV's projectiles and explosions](#projectiles)
- [Part 3: effects](#effects)
- [Part 4: thrown melee weapons](#thrown-melee)
- [Drift](#drift)
- [Checks](#checks)
- [Order](#order)
- [Open questions](#open)
- [As built](#built)

## <a id="now"></a>Where things stood (census 2026-11-05, before the build)

Since built: the thrown types convert through 44 table entries and placed
ones are written as references to the weapon ([as built](#built)).

An FNV weapon converts only as a gun (animation types 3 to 9,
`gun_choice.GUN_TYPES`) or through the replacement table
(`fo4_import/data/replacements.json`, `equipment._weapon`). FNV's thrown types
are neither:

| FNV animation type | Kind | FalloutNV.esm | DLC (own) |
|---|---|---|---|
| 10 | Grenade (thrown, explodes) | 12 | 7 |
| 11 | Mine (placed, proximity) | 4 | 3 |
| 12 | Placed explosive (C4, time bomb, Nellis munitions) | 4 | 3 |
| 13 | Thrown melee (knife, spear, hatchet) | 3 | 10 |

Four already convert through the table, in `stats` mode (a copy of an FO4
weapon with FNV's name and stats): dynamite on `fragGrenade`, the frag mine
and powder charge on `fragMine`, and the bottlecap mine on `BottlecapMine`.
Placed mines (PGRE) fly the converted weapon's projectile
([placed mines](fo4_pipeline.md#placed-mines)).

What the rest costs in FalloutNV.esm (census 2026-11-05):
- **Placed references:** 174 became statics that could not be picked up
  (now references to the weapon, [as built](#built)): frag 59,
  dynamite 43, plasma grenade 21, C4 16, pulse grenade 12, plasma and frag
  mines 7 each, pulse mine 3, Holy Frag 3, time bomb 2.
- **Inventories and lists:** they appear 178 times, 22 on NPCs, 2 on
  creatures, 48 in containers and 106 in leveled lists. Most often: frag
  grenade 48, throwing spear 21, pulse grenade 17, plasma grenade 12, plasma
  mine 11, C4 10, pulse mine 10, frag mine 9, dynamite 8, throwing knife 7,
  incendiary 5.
- **Message buttons:** the trap computer's grenade rearm
  (`TrapComputerRearmGrenadeTypeMsg`, 3 buttons) counts grenades, so it
  stays ungated ([message buttons](fo4_pipeline.md#message-buttons)).

Fallout4.esm's playable grenades: `fragGrenade`, `PlasmaGrenade`,
`PulseGrenade`, `PulseGrenadeInstitute`, `CryoGrenade`, `nukaGrenade`,
`MolotovCocktail`, `BaseballGrenade`, `ArtillerySmokeFlare`,
`DN102_FrenzyGrenade`, and quest beacons. Its mines: `fragMine`,
`PlasmaMine`, `PulseMine`, `CryoMine`, `NukeMine`, `BottlecapMine`. It has no
thrown melee weapon type.

## <a id="templates"></a>Part 1: grenades, mines and placed explosives on FO4 templates

Table entries in `stats` mode, as dynamite has, each on the nearest FO4
weapon:

| FNV | FO4 template |
|---|---|
| `WeapGrenadeFrag`, `WeapGrenadeFragMisfits`, `WeapNVLongFuseDynamite`, `WeapNVDynamiteNoDrop`, `NVDLC05WeapGrenadeTin` | `fragGrenade` |
| `WeapGrenadePlasma`, `NVDLC05WeapGrenadeMFC` | `PlasmaGrenade` |
| `WeapGrenadePulse` | `PulseGrenade` |
| `WeapNVGrenadeIncendiary`, `NVDLC02WeapFireBomb` | `MolotovCocktail` |
| `WeapNVGrenadeFragHoly`, `NVDLC05WeapGrenadeNuka` | `nukaGrenade` |
| `WeapGrenadeGas`, `NVDLC01WeapGhostGasBomb` | `fragGrenade` (see [effects](#effects)) |
| `WeapNVGrenadeStun`, `NVDLC04WeapGrenadeFlashBang` | `fragGrenade` (see [effects](#effects)) |
| `TrapBaseball` (trap only) | `BaseballGrenade` |
| `WeapMinePlasma` | `PlasmaMine` |
| `WeapMinePulse` | `PulseMine` |
| `NVDLC01WeapDemoCharge`, `NVDLC03WeapMeatMine`, `NVDLC04WeapSatchelCharge` | `fragMine` |
| `WeapNVC4PlasticExplosive`, `WeapNVTimeBomb`, `NVDLC05WeapNVTimeBombCustom`, `NVDLC01weapgasbomb` | `fragMine`, on a timer ([timers](#timers)) |
| `WeapMineNellisMunition`, `NVDLC05WeapMineFat` | `NukeMine` |
| `NVDLC05WeapMineMFCCluster` (FNV type 13) | `PlasmaMine` |

The DLC entries go in the same table; a DLC build reads it like the game's.
Once these convert, placed grenades are items (the cell build places a
converted WEAP as it does a gun), and NPC and container inventories and
leveled lists carry them, with no change of their own.

## <a id="projectiles"></a>Part 2: FNV's projectiles and explosions

`stats` mode copies the template's DNAM and takes FNV's damage, weight and
value, but a grenade's damage is its explosion's. The gun path already
gives a weapon FNV's projectile as its `FNAM` Override Projectile, and
[projectile copies](fo4_pipeline.md#projectile-copies) gives a copy FNV's
range, speed and gravity, and its explosion FNV's damage, force and radius
(the 40 mm grenade: 100).

1. Check what dynamite flies in today's build: the WEAP's `FNAM` projectile,
   FO4's `FragGrenadeProjectile` or a copy of FNV's
   `NVDynamiteFragProjectile`. Placed mines read the same byte (WEAP FNAM,
   byte 29).
2. Map each FNV grenade and mine projectile in `data/projectiles.json` to its
   template's own projectile (the frag grenade's, the plasma mine's, and so
   on), so the copy keeps FO4's model, light, sound and fuse.
3. Give `stats`-mode thrown weapons their FNV projectile's copy as `FNAM`, as
   the gun path does. Then FNV's explosion numbers come through the copy:
   frag 125, plasma 225, Holy Frag 800, C4 250, Nellis munitions 500, Fat
   Mine 450.

<a id="timers"></a>**C4 and time bombs explode on a timer (decided 2026-11-05).** FNV's
projectiles carry a fuse in `DATA.AltTriggerProximity` and
`DATA.AltTriggerTimer`:
- `TimeBombProjectile`: proximity 0, timer 15 s, so it never triggers on
  approach;
- `C4Projectile`: proximity 100, timer 3 s, set off by FNV's detonator;
- `MineFragProjectile`, for comparison: proximity 100, timer 3 s.

FO4's PROJ has the same pair ("Explosion Alt. Trigger" proximity and timer,
xEdit `wbDefinitionsFO4`). The projectile copy takes FNV's: the time bombs
keep 0 and 15 s. C4 takes proximity 0 and the time bomb's 15 s (settled
2026-11-06, [open questions](#open)), since FO4 has no detonator. Check in game that an
FO4 mine projectile with proximity 0 counts down. If it does not, the
fallback is a script: the placed explosive's weapon starts a timer when
placed and detonates the projectile it finds near the player (Papyrus has no
event for a placed projectile, so this needs a measured design first).

## <a id="effects"></a>Part 3: effects

What the template brings carries over: fire (Molotov), EMP against robots
(pulse), plasma's goo death, the Nuka blast. FNV effects FO4 has no
grenade take FNV's damage, and their enchantments now convert too
([as built](#built), Part 3):
- gas (`GrenadeGasExplosion`, the ghost gas bomb: poison over time);
- stun: `GrenadeStunExplosion` (15 damage, 450 radius) carries
  `EnchStunGrenadeEffect` (`GrenadeStunEffect`, magnitude 100);
- flashbang: `NVDLC04FlashBangExplosion` (15 damage, 768 radius, no force)
  carries `NVDLC04WeapGrenadeFlashBangEnch`: a 10 s blinding effect, and
  Energy Weapons and Explosives skills cut by 50 for 10 s.

Stun and flashbang go on `fragGrenade`, not `PulseGrenade`. FO4's pulse
grenade is an EMP: heavy damage to robots, synths and power armor, nothing
like either FNV grenade, and its damage would remain even with FNV's
explosion numbers. The frag grenade copy carries FNV's 15 damage and radius
cleanly, and their stun comes with the enchantment conversion below (the
flashbang's blinding only if its script converts).

FNV's explosion enchantment (EXPL `EITM`) is converted as the explosion
copy's own (FO4 EXPL has an Object Effect): 31 of 993 FNV explosions name
one ([as built](#built), Part 3).

## <a id="thrown-melee"></a>Part 4: thrown melee weapons

The throwing knife, spear and hatchet, Honest Hearts' tomahawk and spears,
Old World Blues' proton axes and Dead Money's ghost spears (13). FO4 has no
thrown weapon type, so each would be a grenade-type weapon throwing a
projectile that sticks and does impact damage, without an explosion. Built
in full ([as built](#built), step 5 and Part 4):
- the stand-in is the Railway Rifle's spike projectile,
  `RailwayRifleProjectile` (type Arrow; whether it sticks in actors is
  still to check in game);
- the projectile shows FNV's projectile model
  (`projectile_copies.with_model`);
- the weapon's own model is FNV's (`equipment._weapon` takes FNV's mesh for
  any non-gun `fnv` template).

The interim step (thrown melee on `fragGrenade` with no explosion copy)
became the built design: `fnv`-mode entries on `fragGrenade`.

## <a id="drift"></a>Drift

- FO4 throws grenades and places mines from the grenade slot while the gun
  stays drawn; FNV equips them as weapons. FO4's way stays (FO4-native).
- C4 explodes on a timer instead of FNV's detonator ([timers](#timers)).
- Gas, stun and flashbang: their enchantments convert as attack poisons
  ([as built](#built)); an effect with no Fallout 4 counterpart (the
  flashbang's blinding, unless its script converts) is left out.

## <a id="checks"></a>Checks

- Build counts: WEAP made per FNV animation type 10 to 13, and no
  `item skipped (WEAP)` for them; placed thrown weapons written as REFR on a
  WEAP, not STAT (174 in FalloutNV.esm).
- `message button not gated` no longer lists
  `TrapComputerRearmGrenadeTypeMsg`.
- 0 FormIDs moved: a thrown or placed weapon (FNV animation type 10 to 13)
  is written on FNV's object id (`equipment._thrown`), where every other
  WEAP takes a hashed one. The statics they replace were written under that
  id (`STAT FNV_WeapGrenadeFrag` 0x004330), so a save holding a placed
  static gets a weapon there. The first build (2026-11-06) hashed them and
  moved 34 ids; the drift check caught it before deploy.
- Play: pick up a frag grenade at Goodsprings or Primm, throw it, check its
  damage against FNV's 125; an NCR trooper or Legionary throws grenades;
  plasma and pulse grenades show their FO4 effects; a placed frag mine
  arms.

## <a id="order"></a>Order

Steps 1–3, 5 and 6 built 2026-11-06 ([as built](#built)); step 4's build
checks and play test are not reported yet.

| Step | What | Size |
|---|---|---|
| 1 | Part 2.1: what dynamite flies today | S |
| 2 | Part 1: table entries, game and DLC | S |
| 3 | Part 2.2 and 2.3: projectiles and `FNAM` for thrown weapons, with FNV's fuse ([timers](#timers)) | M |
| 4 | Build, checks, play test | M |
| 5 | Part 4's interim (thrown melee on `fragGrenade`) | S |
| 6 | Part 4 in full, Part 3's enchantments | M-L |

## <a id="open"></a>Open questions

- C4's timer: settled 2026-11-06 as the time bomb's 15 s, proximity 0
  (`data/projectiles.json` `fuses`). FNV's `C4Projectile` (flags 0x462) has
  no Alt. Trigger flag; FNV's detonator sets it off.
- The replaced statics' references: censused 2026-11-06. None of
  FalloutNV.esm's 174 is Initially Disabled; 17 have an enable parent (fine
  for an item); 5 are persistent and named (`VBSOscarMine1REF`-`5REF`,
  frag mines, which already converted). Nothing blocks the switch.

## <a id="built"></a>As built (2026-11-06, not yet played)

- **Step 1.** Dynamite and the converted mines threw Fallout 4's own
  projectiles (`fragGrenadeProjectile`, `FragMineProjectile`,
  `BottlecapMineProjectile`) with FO4's explosions; FNV's weapon damage is 1,
  since an FNV grenade's damage is its explosion's.
- **Step 2.** 44 new `stats` table entries (`replacements.json`), game and
  DLC: 17 grenades, 12 mines and placed explosives, 15 thrown melee weapons.
  Corrections from the census: `WeapMineBottlecap` is FNV type 12 (already
  converted); the thrown melee projectiles name an explosion
  (`NVDynamiteExplosion`) without FNV's Explosion flag.
- **Step 3.** Each FNV thrown projectile maps to its template's own
  projectile (`projectiles.json`), so the copy keeps FO4's model, light and
  sound. A grenade or mine copy (FO4 animation type 10 or 11) throws its
  FNV projectile's copy as its `FNAM` override (`projectiles.thrown`,
  `equipment._thrown`). On this path only (`ProjectileCopies.copy(...,
  is_thrown=True)`), the copy takes FNV's fuse at DNAM 24 and 28 when the
  stand-in has an Alt. Trigger (FNV's own when FNV sets the flag, else the
  `fuses` table: C4), and drops its explosion when FNV's projectile has no
  Explosion flag (thrown melee). Guns are unchanged: the Tesla cannon's and
  plasma caster's projectiles also name an explosion without the flag, and
  explode today.
- **Step 5, then Part 4 (2026-11-06).** The 15 thrown melee weapons are
  `fnv`-mode entries on `fragGrenade`: thrown from the grenade slot, showing
  FNV's own mesh (`equipment._weapon` now takes FNV's mesh for any non-gun
  `fnv` template, grenades included; FNV has no hold pose for type 13, so
  the mesh is unposed). Their projectiles (FNV type Missile, speed 1,600 to
  3,200, gravity 1, no Explosion flag) fly a copy of the Railway Rifle's
  spike, `RailwayRifleProjectile` (type Arrow, which sticks; flags Muzzle
  Flash and Pins Limbs; no explosion, no fuse). Arrow now counts as flying
  (`projectile_copies.FLYING`), so the copy takes FNV's speed and gravity;
  no gun maps to an Arrow stand-in. An inert thrown copy (FNV's projectile
  has no Explosion flag) shows FNV's projectile model
  (`projectile_copies.with_model`: MODL and OBND replaced in place, MODT
  dropped) and takes FNV's Muzzle Flash, Can Be Picked Up and Pins Limbs
  (`THROWN_FLAGS`; the spear's 0x144 gives pick-up and pinning, no flash).
  To check in game: the throw animation with FNV's mesh in hand (its
  orientation is unposed), that a spear sticks and deals the weapon's
  damage on impact, and whether picking one up gives the weapon back.
- **Part 3 (2026-11-06).** 31 of FNV's 993 explosions (game and DLC) name
  an enchantment (21 enchantments). Fallout 4's explosions name an ENCH
  as their object effect (all 24 of Fallout4.esm's that have one: EDID,
  OBND, ENIT, effects; EITM before MNAM and DATA, no EAMT). An explosion
  copy whose stand-in names none now takes FNV's enchantment converted
  (`ProjectileCopies._effect`, `AttackSpells.explosion`), laid out as
  `EnchPlasmaGrenadeEnergyDmg` (`ENIT_EXPLOSION`: Fire and Forget, Touch,
  type 6). Its effects convert as a poison's on the actors caught
  (`AttackSpells.effect_pairs`, the creature attack effects' rules): a
  detrimental value effect becomes `crPoisonEffect` or
  `StingwingPoisonEffectNPC` on its actor value, a scripted one its
  converted script effect; the rest are left out and counted
  (`attack effect left out`). A stand-in with its own object effect keeps
  it (FO4-native: the plasma grenade's energy damage, the pulse grenade's
  EMP). So:
  - **stun** (`EnchStunGrenadeEffect`): 100 Fatigue damage, the helper
    Fatigue actor value the [knockouts](fo4_pipeline.md#fatigue) read;
  - **flashbang** (`NVDLC04WeapGrenadeFlashBangEnch`): Energy Weapons,
    Explosives, Guns, Melee and Unarmed lowered 50 for 10 s, recovering;
    its blinding effect (no actor value) only if its script converts;
  - **incendiary, ghost gas bomb, firebomb**: FNV's fire damage over time
    where the stand-in (Molotov, frag) has no effect of its own;
  - the 40 mm incendiary and GRA's pulse 25/40 mm launcher grenades, gun
    explosions on effect-less stand-ins, also take FNV's.
  - **Gas** (`WeapGrenadeGas`): its explosion (`GrenadeGasExplosion`, 0
    damage, radius 128) names no enchantment in FNV either, so it stays a
    harmless puff.
