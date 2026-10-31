# FNV combat feel on Fallout 4 (plan, 2026-10-29)

FO4's combat is faster and more about the player's own aim. FNV's is slower
and decided more by the character's stats. This plan lists what already
carries FNV's rules, what is still FO4's, and a first pass that changes
data only (settings, records, perks), with no DLL work. Status lives in
[ROADMAP.md](ROADMAP.md).

## <a id="done"></a>Already converted

Checked against the code on 2026-10-29. None of the combat rules below has
been played yet unless it says so.

| Piece | Where it stands |
|---|---|
| Damage Threshold and Resistance | FNV's order and 20% floor, through the F3NV DLL's resistance hook ([damage threshold](fo4_pipeline.md#damage-threshold)) |
| Weapon skills | Skill scales damage and the cone of fire on every NPC and the player ([weapon skills](fo4_pipeline.md#weapon-skills)); creatures keep full damage and spread |
| Critical hits | FNV's random roll and V.A.T.S. +5 beside FO4's meter ([random criticals](fo4_pipeline.md#random-criticals)) |
| Sneak attacks, weapon poisons | Built ([sneak attacks](fo4_pipeline.md#sneak-attacks), [weapon poisons](fo4_pipeline.md#weapon-poisons)) |
| V.A.T.S. AP costs | Each weapon's AP cost is FNV's ([weapon criticals](fo4_pipeline.md#weapon-criticals)) |
| Combat styles | Each FNV style is its own FO4 style, chances inverted from both exes ([combat styles](fo4_pipeline.md#combat-styles)). Dropped: combat radius, fire and wait timers (FO4 ties gun waits to Offensive), rushing attacks, flee and Stealth Boy flags |
| Creature health and attack damage | FNV's, with FO4's race and level bonus taken off (played 2026-10-21, [creature stats](fo4_pipeline.md#creature-stats)) |
| Mod and ammo spread | Multipliers on the FO4 gun's own aim cones ([weapon mods](fo4_pipeline.md#weapon-mods), [ammo](fo4_pipeline.md#nv-ammo)) |
| Level scaling | FNV's leveled lists and encounter zones, no legendaries |
| Requirement spread, chem addiction | Built into the whole map 2026-10-29 and deployed, not played ([requirement spread](fo4_pipeline.md#requirement-spread), [chem addiction](fo4_pipeline.md#chem-addiction)) |

## <a id="gaps"></a>Still FO4's (before the first pass)

Items 1 to 6 are built since ([first pass](#built)); 7 is open.

1. **Base accuracy.** A converted gun keeps its FO4 stand-in's aim model,
   so its cone of fire, recoil and sway are FO4's. FNV's own spread (WEAP
   DNAM Min Spread and Spread) only reaches FO4 as the divisor for mod
   spread. FNV's walking, running and unaimed penalties are not converted.
   This gap does the most to make guns feel like FO4's.
2. **The player's health.** FO4's player starts near 105 health against
   FNV's roughly 200 at Endurance 5 ([creature stats](fo4_pipeline.md#creature-stats)).
   Creatures already have FNV's health, so FNV enemies hit the player twice
   as hard as they should.
3. **Difficulty multipliers.** FO4's damage-by and damage-to multipliers per
   difficulty are its own; FNV's (`fDiffMultHPByPC*`, `fDiffMultHPToPC*`)
   are not written.
4. **V.A.T.S. time.** FNV pauses while you pick targets; FO4 slows time to
   4% (`fVATSTimeMultTargetSelect` 0.04). The damage the player takes in
   V.A.T.S. is FO4's (`fVATSPlayerDamageMult` 0.1). The hit chance is FO4's
   Perception and distance formula (`fVATSChance*`), not FNV's skill-based
   one.
5. **Sprint.** FNV has none. FO4's sprint drains AP
   (`fSprintActionPointsDrainMult` 12) and speeds up fights.
6. **Movement speed.** FO4's walk and run speeds are its own; FNV's
   (`fMoveRunMult` and the rest) are not compared yet.
7. **Creatures' Combat skill.** FNV gives creatures one Combat skill;
   whether it scales their damage and accuracy is unchecked.

Staying FO4's (accepted drift): reload, fire and melee animation speed
(FO4's clips), jump and camera feel, stagger in place of FNV's flinches,
the V.A.T.S. camera and kill cams, FO4's core combat AI (pathing, cover
search).

## <a id="plan"></a>Plan

A first pass, all data, built and played together:

1. **Base accuracy from FNV's spread.** Find in FalloutNV.exe (spread
   0x646910 down to the projectile's angle) what unit FNV's spread is in.
   Then write each converted gun's aim model with a min and max cone from
   FNV's Min Spread and Spread, keeping the FO4 stand-in's recoil and sway.
   FNV's movement and unaimed penalties go on the combat rules perk as
   cone-of-fire entries, if FO4 has a movement condition for them;
   otherwise they are drift. The weapon-skill cone entry then narrows it as
   FNV's does.
2. **Player health.** Read FNV's player health formula (FalloutNV.esm's
   `fAVDHealth*` settings and the exe) and FO4's, then match it: FO4's
   settings where they line up, else a helper ability on Health.
3. **Difficulty.** Write FNV's damage multipliers onto FO4's very easy to
   very hard settings, after reading FO4's defaults from the exe (the esm
   sets only Survival's). Survival keeps FO4's, as Hardcore maps onto
   Survival.
4. **V.A.T.S.** Lower `fVATSTimeMultTargetSelect` toward a pause; the
   lowest value that works needs a test. Set `fVATSPlayerDamageMult` to
   FNV's. Add FNV's skill term to the hit chance through Mod VATS Hit
   Chance (entry 123) on the combat rules perk, once the FNV formula is
   read from the exe.
5. **Sprint.** Either turned off for the player (Papyrus
   `InputEnableLayer.EnableSprinting(false)` at the new game) or kept with
   FO4's AP cost. Needs the user's choice; a global could make it a
   setting.
6. **Movement speed.** Compare FNV's and FO4's player walk and run speeds
   and match them through FO4's settings or the player's SpeedMult.

After the play test:

7. **Combat style tuning.** Only if enemies still fight like FO4's
   (flanking, cover) once the rest is in. The fields to try are FO4's
   cover and flanking fields that FNV's style has no source for.
8. **Creatures' Combat skill.** Check the exe; if FNV scales creature
   damage or spread by it, give creatures the weapon-skill entries on it.

## <a id="built"></a>First pass built (2026-10-29, not yet played)

`spike/combat_feel.py`, `spike/aim_models.py`, the V.A.T.S. entries in
`spike/weapon_skills.py`.

- <a id="base-accuracy"></a>**Base accuracy.** FalloutNV.exe fires within
  `(Min Spread + Spread × the actor's spread) × π/180` radians of the aim
  (0x523A0C; the projectile at 0x9AB715 takes a uniform radius and angle),
  so the cone is a half-angle in degrees. The actor's spread there is mode 1
  of `Actor::GetSpread` (0x8B0DD0), which nothing computes: it stays 0. So
  the player's cone is Min Spread whatever the stance, aiming or skill. The
  stance, skill and requirement sum (0x646910) reaches the player as sway
  (PlayerCharacter's update 0x962DE0: hip and iron sights scale a wobble
  animation, scoped rotates the view), the V.A.T.S. hit chance (mode 3,
  × `fNPCMaxGunWobbleAngle` 5, 0x7F14CA), and NPC shots as + 5° × the sum
  (mode 2, 0x524014) ([sway](fo4_build_next.md#sway)). Unverified: a live
  read that the actor's +0x178 stays 0.
  Each converted gun gets a copy of its stand-in's aim model (AMDL) with
  min = max = FNV's Min Spread, no increase per shot, sneak and iron-sights
  mults 1; recoil, sway and stability stay the stand-in's. FO4's angle is
  taken as a half-angle too (unverified: the CK wiki doesn't say). Copied
  stand-in parts lose their cone properties (33-35, 38, 47), so a barrel no
  longer rescales the cone; FNV's own mods and ammo still do. Drift: the
  weapon-skill and requirement cone entries still scale the player's cone
  where FNV scales sway, and FO4's AI accuracy offsets decide NPCs' extra
  spread in place of FNV's 5° term.
- **Player health.** FNV: base + (Endurance + offset) × 20 + (level − 1) × 5
  (0x6436E0); FO4: base + Endurance × `fAVDHealthStartEndMult` + (level − 1)
  × (Endurance × `fHealthEnduranceMult` + `fHealthEnduranceOffset`)
  (0x1406C9E10). Written: 20, 0, 5. FNV's player record has base 100 and
  FO4's player and race PRPS 80, so the `FNV_PlayerRules` ability adds +20
  Health: 200 at Endurance 5, level 1; 345 at level 30, as FNV.
- **Movement.** FNV runs at `fMoveBaseSpeed` 77 × `fMoveRunMult` 4 = 308
  (0x647D10, 0x647F00); FO4's `Player_Default_MT` at 372.98. The ability's
  SpeedMult −17.4 matches walk and run with a weapon drawn. Drift: FNV is
  10% faster holstered; FO4's weapon movement types scale too; sprint drops
  from 500 to about 413. The new-game script nudges CarryWeight when it
  adds the ability, so the speed takes.
- **Difficulty.** Nothing written: FO4's five non-Survival `fDiffMultHPByPC*`
  and `fDiffMultHPToPC*` defaults are FNV's numbers (2/1.5/1/0.75/0.5 and the
  reverse). Survival keeps FO4's.
- **V.A.T.S.** `fVATSTimeMultTargetSelect` 0.02 (Fallout4.esm 0.04; FNV
  pauses); `fVATSPlayerDamageMult` FNV's 0.75 (FO4 0.1). FNV's skill reaches
  V.A.T.S. through spread; Mod VATS Hit Chance (123) multiplies by
  1 − `fWobbleToSkillConversion` × (1 − skill / 100) when the worn weapon has
  that skill's keyword: × 0.5 at skill 0, × 1 at 100. FNV's spread enters
  squared; this is linear (drift).
- **Sprint.** FO4's, with its AP drain (the user's choice).

## <a id="questions"></a>Open questions

Answered by the user on 2026-10-29:

- Sprint: kept, with FO4's AP cost.
- V.A.T.S.: FO4's slowed time, at a lower value.
- Survival difficulty: FO4's multipliers (this plan's default, not
  overridden).
