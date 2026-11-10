# Perk, challenge and effect gaps on Fallout 4 (plan)

**Status:** planned, not built. Status lines live only in
[ROADMAP.md](ROADMAP.md#fo4-next). This plan is design only; each phase
starts after the next play test, and each DLL item waits for the user's
decision.

## <a id="goal"></a>1. Goal

Close the FNV perk effects, challenges, weapon mods, addictions and Hardcore
rules that still do nothing on Fallout 4. Most of them need to know when the
player lands a hit: with which weapon, on which body part, for how much, and
whether it crippled or knocked down. One combat-hit event gives that once,
and challenges, perks and weapon mods all read it.

Issue-plan rows covered ([issue plan](fo4_issue_plan.md)):

| Row | Size | Doc |
|---|---|---|
| Perk effects with no FO4 match | XL | [census](fo4_perks.md#census) |
| Challenges left out (44), with the "3/10" display | L | [challenges](fo4_pipeline.md#challenges-left-out), [tab](fo4_pipboy_tabs.md#data) |
| Chem addiction | M | [addiction](fo4_pipeline.md#chem-addiction) |
| Hardcore leftovers | M | [Hardcore](fo4_hardcore.md#built) |
| Weapon mods that do nothing (9) | M | [mods](fo4_pipeline.md#weapon-mods) |
| NPCs firing a gun's first ammo | M | [ammo](fo4_pipeline.md#ammo-switch) |

The census's "no FO4 counterpart" list is out of date in one way: item
condition (entry point 68), Jury Rigging (48) and the casing perks Hand
Loader and Vigilant Recycler (57) are now covered by the
[condition system](fo4_condition.md#jury-rigging) and the
[casings script](fo4_pipeline.md#nv-ammo). That leaves 23 of the 29
effects: attack speed (8), equip speed (1), aiming move speed (1), unarmed
specials (5), Miss Fortune (1), Long Haul (1), detection and spotting (3),
V.A.T.S. helper chance (1), and two that need nothing (See Enemy Health,
strength requirements).

## <a id="exists"></a>2. What exists

**Perks** (`fo4_import/spike/perks.py`):
- `ENTRY_POINTS` maps FNV entry points to FO4's by meaning; `STAT_ENTRIES`
  turns stat entry points into abilities; `VANILLA_EFFECTS` copies a
  Fallout4.esm perk's effect.
- `Perks._entry_point` counts each effect it cannot place as
  `perk effect left out (FNV entry point N)`. That count is the audit for
  every perk phase below.
- Knockdown (52, Super Slam) and Meltdown (46) are in the census as "with
  changes" to Apply Combat Hit Spell (51), but neither is in `ENTRY_POINTS`,
  so both are still left out.

**The combat rules perk** (`fo4_import/spike/combat_perk.py`): `CombatPerk`
writes the hidden `FNV_CombatRules` perk (criticals, weapon skills, sneak
attacks, requirement spread). The player gets it from `F3NV_NewGame`, and
`with_perk` adds it to every NPC record. `sneak_attacks.sneaking` shows how
an entry is limited to the player (`PLAYER_REF` owner conditions).

**Apply Combat Hit Spell in use:**
- `weapon_poisons.WeaponPoisons._coat` writes a hidden perk with entry 51
  (Select Spell, weapon tab testing FNV skill keywords). The spell lands on
  the actor hit. Built, not played.
- Fallout4.esm uses entry 51 in 23 perk effects, guns included
  (`Gunslinger04`, `Commando05`, `Sniper02`, `FortuneFinder04`), so it fires
  on gun hits, not only melee.

**FO4 conditions a hit spell can test** (`conditions.FO4`):
`GetHitLocation` (390; the race's body part type, -1 for none; the CK wiki
says explosions do not set it), `GetLastHitCritical` (508),
`GetKnockedState` (107), `GetVATSMode` (224), `GetInIronSights` (773),
`IsOverEncumbered` (769), `GetRandomPercent` (77).

**Challenges** (`fo4_import/spike/challenges.py`):
- `counting` turns each CHAL into an event or a reason it is left out.
  `HIT` (type 3) is kept only for critical hits on any body part; damage
  (type 8, in `LEFT_OUT`) and other hit kinds return a reason string.
- `F3NV_ChallengeSource.Note(event, group, amount, victim, item, held)`
  matches a row's weapon, victim and item lists and adds progress.
  A kill check through `IsKillerObject` was tried and removed: the engine
  reads the killer data without a null check and crashed on a dynamite kill
  ([challenges](fo4_pipeline.md#challenges-left-out)). Never use it.
- `F3NV_ChallengesPlayer` hears kills, potions and the player's own
  cripples (`OnCripple`).

**The Pip-Boy tab** (`tes_runtime/fo4_condition/pages.cpp`, in F3NV.dll):
`SetTab` takes rows, one string list shared by the whole tab, and shown
globals. A row shows a number or one of those strings, so "3/10" cannot be
drawn per row today; the goal is in the row's description.

**Hits the player takes and shots fired:**
- `F3NV_ConditionPlayer` registers `RegisterForHitEvent` on the player and
  the `weaponFire` and `HitFrame` graph events. Its `HitDamage` reads the
  attacker's instance damage through F4SE's `InstanceData`.
- `F3NV_AmmoCasings` hears `weaponFire` and counts rounds fired from the
  drop in ammo counts.
- FO4's `RegisterForHitEvent` needs a target named (CK wiki), so a script
  cannot hear "any actor the player hits" that way.

**DLL damage hook** (`tes_runtime/fo4_condition/damage.cpp`):
`FalloutDamage` replaces FO4's resistance curve for every physical and
energy hit, and the projectile path reads the hit's weapon (`HIT_WEAPON`).
It already sees each hit's final damage, but it raises no event.

**Weapon mods** (`fo4_import/spike/weapon_mods.py`): `WeaponMods` counts
`weapon mod with no FO4 effect (...)` for max condition, ammo regeneration
and projectile speed. FO4's weapon OMOD properties include
`OverrideProjectile` (80) and `NPCAmmoList` (75) (xEdit
`wbWeaponPropertyEnum`).

**Ammo** (`fo4_import/spike/ammo_mods.py`, `AmmoMods`): one OMOD per round,
the gun's default being its first. Vanilla's 11 ammo OMODs each set
`NPCAmmoList`; ours do not.

**Addiction** (`fo4_import/spike/addiction.py`): `COUNTERPARTS` maps seven
FNV withdrawals onto FO4 chems' addiction spell, odds effect and keyword;
every other withdrawal gets an FO4-style addiction of its own (fixed
2026-11-09, not built: [addiction](fo4_pipeline.md#chem-addiction)).

**Hardcore** (`fo4_import/spike/hardcore.py`, `F3NV_Hardcore.psc`):
`SetHardcore` and `IsOn` exist. `SetPlayerTeammate` converts as a plain
call (`script_convert/constants_falloutnv.py`), so no teammate is made
essential.

**F4SE Papyrus** (`InstanceData.psc`, F4SE 0.7.9): `SetSpeed`,
`SetAttackDelay`, `SetReloadSpeed` and `SetSightedTransition` exist on a
weapon instance. Nothing in the build calls them yet.

## <a id="framework"></a>3. The framework: one combat-hit event

**Mechanism.** A hidden perk `FNV_CombatHits`, given to the player by
`F3NV_NewGame` as `FNV_SkillGates` is, holds one Apply Combat Hit Spell
entry and one Apply Bashing Spell entry (52; a bash takes 52 instead of
51, [engine](#engine)). Its spell `FNV_CombatHit` lands on the actor hit and carries
several script effects of one script, `F3NV_CombatHit`, each under its own
conditions:
- one always: the hit itself (caster, victim, the caster's equipped
  weapon);
- one per FNV body part group, on `GetHitLocation` (head, torso, each arm,
  each leg);
- one on `GetLastHitCritical`, one on `GetKnockedState`;
- a short delay, then a cripple check on the victim's limb condition values.

Each effect hands `F3NV_Combat` (a start-game quest) one call:
`Hit(victim, weapon, part, kind, damage)`. `F3NV_Combat` passes it on to
the challenge sources, the perk scripts and the weapon-mod scripts. The
`weaponFire` side stays where it is (`F3NV_AmmoCasings`) and gains one call
to `F3NV_Combat.Fired(gun, rounds)`.

**One spell per hit.** The engine keeps one spell per hit
([engine](#engine)), so every Apply Combat Hit Spell use in the build
(the weapon poison coats too) has to become a conditioned effect on
`FNV_CombatHit`; two perks with the entry would take hits from each other.

**Damage.** The engine applies the hit before it picks the spell
([engine](#engine)), so a health drop measured from the effect's start
likely misses the hit itself. The probe measures it. Fallback: the weapon
instance's damage, as `F3NV_ConditionPlayer.HitDamage` already reads it.
Exact damage needs the DLL ([D5](#dll)).

**Explosions.** No explosion reaches the entry ([engine](#engine)): a
grenade's or mine's blast, or a missile's splash. Explosives hits need
another host. The candidate is the explosion's object effect (EXPL `EITM`,
applied to actors in the blast). Vanilla uses it on 24 of 238 EXPLs
(`cryoMineExplosion`, `plasmaGrenadeExplosion`). `projectile_copies` already
writes FNV's enchantment there. It needs its own probe after phase 1: who
the caster is, and whether it fires on a kill. Never use the killer
conditions for it ([challenges](fo4_pipeline.md#challenges-left-out)).

**Why it covers the rows:**
- Challenges: the 18 damage and 11 hit challenges become a `HIT` event
  with body part and kind columns, matched by `F3NV_ChallengeSource`.
- Perks: Super Slam (knockdown), Meltdown and Miss Fortune become
  conditioned effects on the same spell instead of three perk entries.
- Weapon mods: ammo regeneration reads `Fired`; Miss Fortune's weapon break
  reuses `F3NV_ConditionCalls`.
- Misc stats: Disintegrations, Dismembered Limbs and Miss Fortunate
  Occurrences count from the same calls.

It is records and Papyrus only: the engine's own entry point, as vanilla's
Gunslinger and Sniper perks use it.

### <a id="dll"></a>DLL decisions

Each needs the user's approval. The alternative is what gets built if the
answer is no.

| # | Item | DLL work | Alternative |
|---|---|---|---|
| D1 | Attack speed (entry 43: Fast Shot, Loose Cannon, Slayer, challenge perks; teammates Old Vaquero, Causeless Rebel) | Scale the weapon speed the engine reads for the attacker | F4SE Papyrus `InstanceData.SetSpeed` / `SetAttackDelay` on the equipped instance while the perk holds, reset on unequip (unverified: whether it applies without a re-equip and stays on that copy only); else drift |
| D2 | Equip speed (38, Quick Draw) | Scale the draw and holster animation rate | The `weaponSpeedMult` graph variable through `SetAnimationVariableFloat` (unverified; the engine may overwrite it each frame); else drift |
| D3 | "3/10" on the CHALLENGES tab | `SetTab` takes a second list, a goal per row, and draws "progress/goal" | Keep "Goal: n" in the row's description (built) |
| D4 | Hip-fire and iron-sight sway by skill | Scale FO4's wobble by the weapon skill | Scoped sway is built on entry 102 ([sway](fo4_build_next.md#sway)); the rest stays drift |
| D5 | Exact hit damage | A native `LastHitDamage(target)` fed by `FalloutDamage` in `damage.cpp` | The health drop or the instance damage (above) |

## <a id="phases"></a>4. Phases

| # | Size | Delivers | Checked by | Depends on |
|---|---|---|---|---|
| 1 | S | The [hit probe](#probe): a test plugin `F3NV_HitProbe.esl` (own MO2 mod) giving the player a perk with entries 51 and 52 and one spell of 16 logging effects (each body part group, critical, V.A.T.S., knocked, dead) | One play session of [ten steps](#probe-steps); each Papyrus log line answers one [question](#probe-proves) | The current rebuild |
| 2 | M | `combat_hits.py` (perk, spell, effects), `F3NV_CombatHit`, `F3NV_Combat` | `tests/test_fo4_combat_hits.py` (records and conditions); the probe's checks repeated on the real build | 1 |
| 3 | M | Hit and damage challenges: `counting` keeps type 8 and every hit kind; body part and kind columns in `F3NV_ChallengeSource` | Build count of challenges left out goes from 44 to 15; in game, a "Challenge Progress" line for a damage challenge | 2 |
| 4 | M | Hit perks: Super Slam, Meltdown, Miss Fortune on the hit spell; Run 'n Gun as an ability under `GetInIronSights`; Long Haul as a CarryWeight raise while the Pip-Boy map is open | `perk effect left out` counts for entry points 41, 46, 52, 54 and 51 reach 0; in game, a Super Slam knockdown and a fast travel while overencumbered | 2 |
| 5 | S | Weapon mods: ammo regeneration from `Fired` and a timer; projectile speed as an `OverrideProjectile` copy; max condition read by the condition script | `weapon mod with no FO4 effect` reaches 0; `tests/test_fo4_weapon_mods.py`; in game, the recharger pistol's mod | 2 |
| 6 | S | Misc stats: Disintegrations, Dismembered Limbs, Miss Fortunate Occurrences from `F3NV_Combat`; Doctor Bags Used, Health From Stimpaks, Health From Food from `OnItemEquipped`; Items Repaired from the repair calls | Challenges left out goes from 15 to 8 (casino and caravan 6 wait on the [casino plan](fo4_casino_plan.md)); Barter Amount Traded and Speech Failures stay open | 3 |
| 7 | M | Chem addiction: Hydra, Turbo, Steady, tobacco, ant nectar and Quantum as FO4-style addictions (own actor value, odds effect, keyword, withdrawal ability), after reading how vanilla rolls an addiction | `ALCH addiction left out` reaches 0; in game, Turbo addiction and a doctor's cure | Play-test result for Jet |
| 8 | S | Hardcore leftovers: converted `SetPlayerTeammate` goes through `F3NV_Hardcore`, which sets a teammate protected outside Hardcore (FNV builds only, not FO3) | A unit test on the converted call; in game, a companion outside Hardcore goes down and gets up | The companion check |
| 9 | S | NPC ammo: census of how FNV picks an NPC's round, then `NPCAmmoList` on our ammo OMODs and, if FNV varies it, object-template combinations | A test on the OMOD properties; in game, an NPC with hollow points in inventory | None |
| 10 | M each | The DLL items the user approves (D1 to D5) | Each its own in-game check | User decision |

Phase 1 is the gate: if the hit spell cannot report body part or criticals,
phases 3 and 4 change (see below).

### <a id="engine"></a>Phase 1, part 1: what disassembly settled

Read from Fallout4.exe 1.11.240 (RVAs), checked against Fallout4.esm. The
disassembly scripts are not kept; the addresses below are enough to redo it.
- **One call site.** The only Apply Combat Hit Spell call is at 0xCD7B03 in
  the actor-hit function 0xCD7670 (attacker, target, weapon slot,
  projectile). It goes through `HandleEntryPoint` (0x618860) with tabs
  owner, weapon, target. If the attacker is bashing (`[actor+0x130]` attack
  state `0xC000000`), 0xCD7AE4 asks Apply Bashing Spell (52: owner and
  target, no weapon tab) instead.
- **Who reaches it.** 0xCD7670 has three callers:
  - melee: 0xCD5110, twice, for every actor in the swing;
  - projectile impact: 0xE4D060, from the base projectile's impact
    function 0xE44930 (vtable slot 208 of `Projectile`, `GrenadeProjectile`,
    `BeamProjectile` and `FlameProjectile`). `MissileProjectile` (0xE3C8D0)
    and `ConeProjectile` (0xE21A00) call it too.
  - `Explosion` has its own slot 208 (0xE2EF50) and never calls 0xCD7670.
  So bullets, lasers, flames, melee and a grenade or missile striking a
  body fire the entry. A blast does not: thrown grenade, mine or missile
  splash. That matches the CK wiki ("bullets count as hits"; explosions do
  not set the hit location).
- **One spell per hit.** Select Spell (function 10, 0x6196A0) writes the
  spell into the single result (`*out = spell`). The perk visitor
  (0x618AF0) runs every matching entry and always continues. So of several
  perks with the entry, the last one visited wins, and only that spell is
  cast (0x509D40 at 0xCD7B21). The coat and the probe cannot both land on
  one hit.
- **The hit is recorded before the spell.** At 0xCD7A41 the hit goes to
  0xC45DD0, which runs message 0xE right away on the main thread (or queues
  it from another thread). Message 0xE calls the actor's hit handler
  0xCD2CA0. Early on, at 0xCD2D72, that handler copies the hit into the
  victim's last-hit data (0xD3AD30: `process→middleHigh+0x228`). Only then
  is the entry asked (0xCD7B03). So `GetHitLocation` and
  `GetLastHitCritical` see this hit when the spell's conditions are first
  checked, unless the hit was queued. Vanilla relies on the same order:
  `ench_mod_LegendaryWeapon_Cryo`, `_Frenzy` and `OnCritRefillAP` test
  `GetLastHitCritical` on the weapon's object effect, which 0xCD7670 casts
  right after the entry (0xCD7B46 on). The same order means the hit's
  damage is likely already applied when the spell starts. Measure it, not
  assume it.
- **Knocked down comes later.** `GetKnockedState` reads the victim's own
  state (`[actor+0x130]`, mask `0x1E00000`), which the hit sets only when
  physics takes over. Its effect therefore needs a duration, so the
  condition is checked again (every `fActiveEffectConditionUpdateInterval`).
- **No null reads** in the conditions the probe and phase 2 use. Each
  condition function comes from the script function table (0x50 per entry,
  condition function at +0x40); each was disassembled:

| Function | Condition fn | Reads | Null-safe |
|---|---|---|---|
| GetHitLocation (390) | 0x5A32F0 | last-hit data +0xD0 via 0xCD1BB0 | yes: subject, process and middle-high process each checked; -1 when missing |
| GetLastHitCritical (508) | 0x5A4240 | last-hit data +0xC4 bit 3 | yes, the same checks; 0 when missing |
| GetKnockedState (107) | 0x59F2A0 | `[actor+0x130]` | yes: subject checked, nothing deeper |
| GetDead (46) | 0x59BB80 | actor vfunc 0x600 | yes |
| HasKeyword (560) | 0x5A4F00 | subject's keyword form | yes: subject and keyword checked |
| GetVATSMode (224) | 0x5A1100 | the V.A.T.S. singleton +0x40 | singleton not checked (made at startup, vanilla-wide use) |
| IsKillerObject (comparison) | 0x5A36D0 | killer data +0x38 after 0x28D7E0 | **no** (0x5A372A); never use |

### <a id="probe"></a>Phase 1, part 2: the probe

Built right after the current rebuild, as the [condition spike](fo4_condition.md#spike)
was: a separate light test plugin in its own MO2 mod, so the built
plugin is untouched and one checkbox removes it. The one variable is the
probe perk on the player. Enable `F3NV - Hit Probe` last, play, then
disable it.

**Records** (`F3NV_HitProbe.esl`, light, master Fallout4.esm only, written
with the build's own packers: `perks.pack_perk` and `pack_effect`,
`records.pack_ctda`, `perks.pack_spell`, `script_effects` MGEF DATA):
- QUST `F3NVProbe_Start`: start game enabled, run once; script
  `F3NV_HitProbeStart` with `Perk Property Probe`. `OnQuestInit` gives the
  player the perk and traces `F3NV HitProbe on`. A start-game quest from a
  newly added plugin also starts in an existing save.
- PERK `F3NVProbe_Hits`: hidden, unplayable, one rank, two entries, no
  conditions:
  - entry 51, function 10 (Select Spell), 3 tabs, EPFT 5, EPFD the spell;
  - entry 52, function 10, 2 tabs, the same spell.
- SPEL `F3NVProbe_Hit`: the shape of Fallout4.esm `PoisonRadscorpion`
  (fire and forget, touch), as `attack_spells` copies it. It holds 16
  effects, one MGEF each. Conditions run on the subject (the actor hit);
  "A–B" means `>= A` AND `<= B`:

| # | MGEF label | Conditions | Duration |
|---|---|---|---|
| 1 | `Hit` | none | 0 |
| 2 | `PartNone` | GetHitLocation == -1 | 0 |
| 3 | `Torso` | GetHitLocation == 0 | 0 |
| 4 | `Head1` | == 1 | 0 |
| 5 | `Eye` | == 2 | 0 |
| 6 | `Head2` | == 5 | 0 |
| 7 | `Brain` | == 16 | 0 |
| 8 | `LeftArm` | 6–7 | 0 |
| 9 | `RightArm` | 8–9 | 0 |
| 10 | `LeftLeg` | 10–12 | 0 |
| 11 | `RightLeg` | 13–15 | 0 |
| 12 | `PartOther` | 3–4 or >= 17 | 0 |
| 13 | `Critical` | GetLastHitCritical == 1 | 0 |
| 14 | `VATS` | GetVATSMode != 0 | 0 |
| 15 | `Knocked` | GetKnockedState == 1 | 3 s |
| 16 | `Dead` | GetDead == 1 | 0 |

- MGEF `F3NVProbe_<label>` ×16: Script archetype, fire and forget, touch.
  DATA as `ScriptEffects.effect_data` makes it, plus hide-in-UI and no hit
  shader. VMAD: `F3NV_HitProbe` with `String Label` and
  `ActorValue Health` (Fallout4.esm 0x0002D4).

**Papyrus.**

```papyrus
Scriptname F3NV_HitProbe extends ActiveMagicEffect
String Property Label Auto Const
ActorValue Property Health Auto Const

Event OnEffectStart(Actor akTarget, Actor akCaster)
    float t = Utility.GetCurrentRealTime()
    Debug.Trace("F3NV HitProbe " + Label + " t=" + t + " victim=" + akTarget + " caster=" + akCaster \
        + " weapon=" + akCaster.GetEquippedWeapon() + " hp=" + akTarget.GetValue(Health) + "/" \
        + akTarget.GetBaseValue(Health) + " dead=" + akTarget.IsDead())
    If Label == "Hit"
        Utility.Wait(0.5)
        Debug.Trace("F3NV HitProbe Hit+0.5 t=" + t + " victim=" + akTarget + " hp=" + akTarget.GetValue(Health))
    EndIf
EndEvent
```

`F3NV_HitProbeStart` is `Event OnQuestInit()` →
`Game.GetPlayer().AddPerk(Probe)` and the trace. It needs Papyrus logging
on (`bEnableLogging=1`), as in earlier play tests. Lines from one hit share
one `t`.

<a id="probe-steps"></a>**What the user does** (one session, any save past
Goodsprings, Papyrus.0.log afterwards):
1. Load the save and wait 5 s. (Line: `F3NV HitProbe on`.)
2. Hip-fire one pistol shot into the torso of an unhurt enemy.
3. Aim and fire one head shot (not V.A.T.S.).
4. In V.A.T.S., one shot at a leg, then one at an arm.
5. One melee hit, then one power attack (any melee weapon).
6. One gun bash (melee button with a gun out).
7. Throw one frag grenade at a group of enemies, away from your bullets.
8. Place one frag mine and lure an enemy onto it.
9. Finish a hurt enemy with a pistol shot (the kill shot).
10. Note any enemy you saw knocked down, with the weapon.

<a id="probe-proves"></a>**What each line proves:**

| Step | Expected | If it differs |
|---|---|---|
| 1 | `on` | The quest did not start, so the rest is void |
| 2 | `Hit` + `Torso`, one `t` | No `Hit`: a player perk's hit spell does not fire, so the framework needs another host. `Hit` but `PartNone`: the hit was queued and read the previous hit, so the body part needs a delay |
| 2 | `hp` at start below base | The hit was applied before the spell, so damage comes from instance damage or D5. Base equal and `Hit+0.5` lower: the health drop works |
| 3 | `Head1`, `Head2` or `Brain` | Settles which part types FNV's "head" gets ([questions](#questions)) |
| 4 | `VATS` + leg / arm | V.A.T.S. kinds and limbs can be counted |
| 2–5 | `Critical` on criticals only | `GetLastHitCritical` counts critical challenges; compare with the Critical Strikes stat |
| 5 | `Hit` + part, caster = player | Melee and power attacks fire 51 |
| 6 | `Hit` from entry 52 | A bash fires 52, not 51; with no line, bashes need another path |
| 7, 8 | No line, or only from a grenade striking a body | Blasts never fire the entry: explosives move to the [explosion's object effect](#framework) |
| 9 | `Hit` with `dead=True` and `Dead`, or nothing | Whether a kill shot is seen; either way, kills stay with `OnKill`/`OnDeath` |
| 10 | `Knocked` within 3 s of the knock | `GetKnockedState` works on a timed effect, so Super Slam and knockdown challenges can use it |

## <a id="play-test"></a>5. What the play test should tell us first

- **The hit probe** ([steps](#probe-steps), [what each line proves](#probe-proves)).
  It shows whether a hidden player perk's hit spell fires, which body parts
  and kinds it can tell apart, whether the hit is read in time, whether the
  damage is already applied, bashes (52), kill shots and knockdowns.
  Disassembly has already settled the rest ([engine](#engine)).
- **Weapon poison coat lands.** It is our only entry 51 perk, so play it
  with the probe disabled. A coat that never applies, while the probe's
  `Hit` line does show, points at the coat's weapon-tab keywords, not the
  entry.
- **A coat and another hit spell together: settled, one per hit.**
  Select Spell keeps one spell, and the last matching perk wins
  ([engine](#engine)). The poison effects move into `FNV_CombatHit` behind a
  condition in phase 2.
- **Explosives kills: settled, not through this entry.** `IsKillerObject`
  is ruled out (it crashes). No blast reaches Apply Combat Hit Spell
  ([engine](#engine)). Explosives move to the explosion's object effect,
  with a probe of their own ([framework](#framework)).
- **Critical challenges count.** The five built ones use FO4's Critical
  Strikes stat; if that stat lags, criticals move to `GetLastHitCritical`.
- **Casings drop in combat.** Ammo regeneration reads the same
  `weaponFire` listener.
- **Jet addiction and a doctor's cure.** If FO4's own addiction path works
  for converted chems, phase 7 copies it; if not, phase 7 grows.
- **Companions.** Whether Cass or Boone already counts as protected
  outside Hardcore changes phase 8.

## <a id="questions"></a>6. Open questions

- Is a health-drop damage figure close enough for damage challenges, or
  is D5 wanted? FNV counts damage dealt; an estimate may make "deal 10,000
  damage" challenges finish early or late.
- `GetHitLocation` gives part types such as Head1, Head2 and Brain; FNV
  counts head, torso and limbs. Which FO4 part types count as FNV's
  "head" for creatures with their own body part data is unverified.
- The issue plan's Hardcore row names an MCM switch; the Hardcore doc chose
  the aid item. Is an MCM line still wanted?
- What FNV entry point 54 (Run 'n Gun) changes is taken from the census
  ("aiming move speed"); check it against xEdit and the wiki before phase 4.
- Long Haul through a CarryWeight raise while the map is open is
  unverified: FO4 may test encumbrance after the map closes.
- Unarmed specials (61 to 66) need their attack animations and stay with
  the [melee row](fo4_spikes.md#spike-4-melee). Detection and spotting
  (69 to 71) and V.A.T.S. helper chance (67) have no plan here.
- Barter Amount Traded and Speech Failures have no FO4 stat or event; they
  stay left out unless the DLL's barter code ([transfer menus](fo4_condition.md#transfer-menu))
  reports trades.
