# Weapons with no rule: an automatic route

Status: BUILT, not played

**Code:** `fo4_import/spike/weapon_routes.py`, `fo4_import/spike/weapon_checks.py`,
`fo4_import/havok/gun_view.py`, `Equipment._weapon_route` (`spike/equipment.py`),
`gun_choice.paced`, `projectiles.kind_of`, `data/replacements.json` `_rules.weapon`,
`data/projectiles.json` `kinds`.

A modded weapon used to convert only if the hand table named it, or if it was
a melee weapon or a gun the build could place on a Fallout 4 template. Nobody
looks at the result, so the conversion picks a safe route itself, checks what it
made, and says what it did. This is the weapon counterpart of
[the creature routes](fo4_auto_rig_plan.md#order).

## <a id="today"></a>What happened before

1. The hand table (`replacements.json` `weapon`, by source EditorID).
2. The melee rule for animation types 0–2 (`_rules.melee`, now read as
   `_rules.weapon` with a `DEPRECATED` warning).
3. An automatic gun for animation types 3–9 with a model (`spike/gun_choice.py`).
4. Otherwise skipped (`item skipped (WEAP)`): guns with no model, guns no
   template matched, thrown weapons and mines the table left out.

## <a id="census"></a>Census (2026-11-26)

Each plugin's own WEAP records, by the route the old code gave them:

| Plugin | Own | Hand table | Melee rule | Automatic gun | Gun, no model (skipped) | Thrown/mine, no entry (skipped) |
|---|---|---|---|---|---|---|
| Fallout3.esm | 160 | 89 | 47 | 0 | 23 | 1 (`LibertyPrimeWeapBomb`) |
| Anchorage.esm | 44 | 0 | 11 | 26 | 3 (chimera guns) | 4 |
| BrokenSteel.esm | 25 | 2 | 2 | 17 | 2 (turrets) | 2 |
| PointLookout.esm | 23 | 0 | 12 | 7 | 1 | 3 |
| ThePitt.esm | 10 | 0 | 5 | 5 | 0 | 0 |

## <a id="principle"></a>The rule: gameplay from the source, looks from the template

| From the source WEAP and its PROJ | Where |
|---|---|
| damage, crit, AP cost, clip size, ammo, min spread, range | already |
| projectile count, speed, gravity, explosion damage and radius | projectile copies |
| semi-automatic fire rate | [fire rate](#fire-rate) |
| the projectile's kind, for one not listed | [projectiles](#projectiles) |

The template supplies the mesh (when not the source's own), animations, sounds
the source lacks, impact data and the projectile's look.

## <a id="order"></a>The route, in order

Each weapon takes the first route that works (`WeaponRoutes`):

1. **Its hand entry.**
2. **A listed weapon with the same model path** (`Model.MODL`, any case or
   slash), from the plugin's and its masters' WEAP records: that weapon's entry.
   Mods mostly add variants (new stats, a texture, a unique name).
3. **Its own mesh on the automatic template** (`gun_choice`), if it passes the
   [checks](#checks).
4. **That template's own mesh** (`stats`), when it fails one.
5. **The stand-in of its animation type** (`_rules.weapon`, all 14 types) for
   anything else: a gun with no model, a gun no template takes, a thrown weapon
   or mine with no entry. Unarmed, guns, grenades and mines stand in as
   `stats`; one- and two-handed melee and thrown weapons keep `fnv` (their own
   mesh on the tire iron, bat or grenade).

One kind is left out, as before: a creature's modelless attack gear (FNV
Non-Playable or Embedded, no model: turret lasers, robot guns, the fire gecko's
flame, ED-E's zap gun; 28 in FalloutNV.esm). The creature fights with its
stand-in's own gear. A playable stand-in would be carried by an armed creature
(`Creatures._carried` keeps its guns) and dropped as loot; the first FNV build
made all 28. Listed as `left out (attack gear)`.

Each route is counted as `weapon route (<route>)`.

## <a id="checks"></a>Checks that stand in for looking

A gun on its own mesh (step 3) is measured before anything is written
(`WeaponChecks.failed`); a failure drops it to step 4.

| Check | Measured by | Fails when |
|---|---|---|
| muzzle | `ProjectileNode` among the FNV mesh's nodes | absent: FO4 fires from that node, so shots would leave from the template's muzzle |
| aim_hand | the share of FO4's right hand (its vertices) in view in the converted `WPNIdleSighted`, camera lift applied (`gun_view.Arms.hand_share`, the measure `tools/nif/gun_quick_convert.py` reports) | a rifle over `AIM_HAND_LIMIT` 0.09 |

The aim limit comes from played results, not vanilla: Fallout 4's own sighted
clips are not spline clips, so `parse_fo4_animation` reads none of the 32. The
rifle grips played and kept measure 0–9% (the carbine at 8% played fine); the
pipe gun at 23% blocked the view. A pistol is aimed with its whole hand in view
(FNV's pistols measure 45–100%), so a pistol's share is reported, never failed.
The first FNV build failed every pistol on this until the stance was added. A
gun whose clips do not convert plays the template's, so it has nothing to fail
(`clips=template` in the report).

Grip, on-screen share, the graph check and a damage-per-second check stay
[open](#open).

## <a id="projectiles"></a>Projectiles by kind

A source projectile not in `projectiles.json` `map` takes the stand-in of its
kind (`kind_of`): FNV `DATA.Type` (missile, lobber, beam, flame; continuous beam
counts as beam), a missile with Hitscan as a bullet, and the Explosion flag
choosing the explosive stand-in. Counted as `projectile by kind, <kind>`.

## <a id="fire-rate"></a>Fire rate

FNV's `DNAM.ShotsPerSec` (xEdit "Attack Shots/Sec") is the gun's real rate:
12.0 for the automatic carbine, 3.125 for the 9mm, 0.448 for the anti-materiel
rifle. The GECK computes it from the attack animation and its multiplier.

Fallout 4's rate, from `Fallout4.exe` (the Pip-Boy rate at `0x4796d0` is
`fDispRoFMult` 10 × shots a second; it matched the wiki's figures for nine guns
and three receivers):

- semi-automatic: Speed / Attack Delay;
- automatic: `fDispRoFShotsPerFile` 20 × Speed / attack seconds. The game
  measures the attack seconds from the behavior graph at load (`0x47ee50`), not
  from the record;
- bolt action: 1 / (bolt clip / Speed + attack seconds).

`gun_choice.paced` sets a semi-automatic gun's Attack Delay to Speed /
ShotsPerSec, counted as `guns paced to FNV fire rate`. Automatic guns and
bolt-action copies keep the template's rate:

- an automatic receiver OMOD sets Speed itself (10mm, SMG and pipe gun to 1.4,
  assault rifle to 1.25), so the WEAP's Speed is ignored;
- that the real automatic rate follows the `WeaponFire` events in the loop is
  inferred, not measured.

## <a id="report"></a>The report

Every build writes `<plugin>.weapons.tsv` beside the plugin in its build
records: EditorID, FormID, route, target, why it dropped a step, and each
check's value. Sort by route to find the drops and stand-ins, then promote any
fix to a hand entry.

First builds (2026-11-26), routes per plugin's own weapons:

| Plugin | Hand table | Hand table, own mesh | Same model | Own mesh | Template mesh | Type rule | Attack gear left out | Paced |
|---|---|---|---|---|---|---|---|---|
| FalloutNV.esm | 67 | 49 | 7 | 20 | 7 | 72 | 32 | 65 |
| Fallout3.esm | 56 | 29 | 7 | 0 | 0 | 38 | 19 | 41 |

Template-mesh drops in FalloutNV.esm: four rifles over the hand limit (riot
shotgun 57%, silenced .22 SMG 45%, both marksman carbines 15%), Lily's carbine
at 9% (just over 0.09), and both detonators (no `ProjectileNode`). Fallout 3's
only new weapon is `LibertyPrimeWeapBomb` (thrown, on the frag grenade).

## <a id="later"></a>Later: an automatic firing test

The autoplay harness ([autoplay](fo4_autoplay.md)) could equip each new weapon
in a test cell, fire it once, and log that a projectile spawned and the ammo
count dropped.

## <a id="saves"></a>FormIDs and saves

Weapons keep their ids from their source FormIDs (`tests/test_fo4_weapon_ids.py`).
A weapon that changes route changes its record's contents, not its id. A weapon
that starts converting gets an id no save can hold.

## <a id="open"></a>Open questions

- **Automatic fire rate.** Count the `WeaponFire` events in vanilla's automatic
  loop, then write Speed on the receiver OMOD the copy attaches.
- **Grip and on-screen checks**, with limits from played guns.
- **Damage-per-second check**, once both rates are carried over.
- **Same assets by bytes.** Mods that copy a vanilla model under a new path.

## <a id="steps"></a>Build order

Built: route logging and the report, the stand-ins by type, the same-model
route, the checks with the drop to the template's mesh, semi-automatic fire
rate, projectiles by kind. Left: the [open](#open) items and the firing test.
