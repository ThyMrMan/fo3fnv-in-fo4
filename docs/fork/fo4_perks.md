# FNV perks on Fallout 4

**Status:** step 1, the census, done 2026-10-20. Nothing built.

Today no FNV perk converts. The level-up menu's perk list (`FNV_Perks` in
LevelUpMenuEx's ini) is empty, FO4's perk chart is off, the 10 traits are
perks with a name and description only, and every `HasPerk` condition counts
as false, so perk-gated dialogue never shows and consumable effects that need
a perk are left out ([character menus](fo4_spikes.md#spike-2-vcg01)).

## <a id="plan"></a>Plan

1. **Census** (below): FNV's perk effects against FO4's entry points.
2. **PERK records**: FNV's perks on their own FormIDs, with ranks, level and
   skill requirements, and the effects the census maps; abilities and quest
   stage effects carried over.
3. **The menus**: `FNV_Perks` filled (requirements, ranks, a perk every
   other level as FNV), and the traits' effects.
4. **Tests of perks**: `HasPerk` real in dialogue, recipes, idles and
   scripts, and the consumable effects left out for it brought back.
5. **Play-test** in the region: take a perk at a level-up, see a line it
   gates (Lady Killer, Confirmed Bachelor), and a trait's effect.

## <a id="records"></a>PERK records (step 2)

`fo4_import/spike/perks.py`. Every FNV perk keeps its FormID, name,
description, minimum level, playable and hidden flags, and its requirements
(the perk's conditions, through the dialogue condition converter).

- **Ranks.** FO4 chains ranks as separate records (NNAM: vanilla's
  `QuickHands01` → `QuickHands02`, each carrying the chain's rank count),
  and an actor keeps every rank taken. FNV keeps ranks in one record, and
  only the current rank's effects apply: Swift Learner is ×1.1, ×1.2, ×1.3
  and Toughness +3 then +6, Action Boy's abilities +15 then +30 AP. So
  each FNV rank is its own record (FNV's FormID for the first), and an
  earlier rank's effects carry one more condition, `HasPerk <next rank> ==
  0`: on the owner tab of an entry point, on each effect of an ability.
- **Entry points** keep FNV's function, value and condition tabs (both
  games' tab 0 is the perk owner, then weapon and target). FO4's tab count
  per entry point is read from Fallout4.esm's perks; one vanilla never uses
  takes the owner tab only. An effect testing a tab FO4's entry point lacks
  (FNV's To Hit Chance has weapon and target tabs, FO4's Mod VATS Hit
  Chance only the owner) is left out, counted.
- **Vanilla effects.** Computer Whiz, Paralyzing Palm, Concentrated Fire
  and Grim Reaper's Sprint carry the effect of `Hacker04`,
  `IronFist05`, `ConcentratedFire01` and `GrimReaperSprint01` on the same
  FO4 entry point, conditions and value included.
- **Abilities** become FO4 abilities (SPEL, `AbPerkQuickHands`'s type):
  each FNV effect on vanilla's constant effect of the same FO4 actor value
  (`AbFortify*`/`AbReduce*`, by the Detrimental flag 0x4 both games use),
  or a copy of `AbFortifyStrength`/`AbReduceCarryWeight` on it. Script
  effects (Calm Heart, the regeneration implant) are left out.
- **Quest stages** stay quest stage effects, on a quest the build has.
  FNV stores the stage as one byte with `0xCD` fill above it (the export
  reads Scrounger's as 0xCD46; Generic's stage is 70, and Intense
  Training's 0xCD65 to 0xCD6E are Generic's 101 to 110), so the low byte
  is the stage.
- **FNV type tests**: keyword tests ([type tests](#type-tests)).
- **Shared fixes.** `GetPermanentActorValue` is FO4's `GetPermanentValue`
  (it carries 99 of the requirements: 74 perks' requirements failed
  before); FNV's `RadResist` is FO4's `RadResistExposure` (0x2EA), as the
  consumables already map Rad-X.

**Built 2026-10-20** (Goodsprings to Primm region, not played): 207 PERK
records (176 perks, 31 later ranks), 41 ability spells, 25 copied constant
effects; 0 FormIDs from counted keys; FO4Edit's check clean.
Requirements convert for 175 of 176 perks. The 35 effects on FNV's type
tests convert since the [type tests](#type-tests) (34; one more now fails
on another condition): 79 weapons and 21 creatures carry the keywords, and
no condition in the plugin uses the three functions. Left out: 10
effects on other conditions, 3 on tabs FO4 lacks, 2 quest stage
effects on quests outside the build, and the entry points with no
counterpart or still to design ([census](#census)); ability effects on
crit chance (5, FO4 has no actor value: its crit chance is an entry
point), Damage Threshold (1) and the script effects (5).

## <a id="type-tests"></a>Weapon and creature type tests

`fo4_import/spike/type_tests.py`. Three FNV condition functions test
data FO4's records do not carry: `IsWeaponSkillType` (a weapon's skill,
WEAP DNAM +104), `GetWeaponAnimType` (FNV's 14 animation types, DNAM +0)
and `GetIsCreatureType` (FNV's 8 creature types, CREA DATA +0; FO4 marks
kinds of actor with `ActorType*` keywords). FO4 still lists all three, so
they converted by name and were never true. FNV uses them in 35 perk
effects, 13 dialogue conditions and 21 idle conditions (2026-10-20
census).

The build stamps a keyword for each on what it converts, from FNV's own
fields (the export omits both, so they are read from the source plugin):
`FNV_WeaponSkill<skill>` and `FNV_WeaponAnim<type>` on every converted
weapon, `FNV_CreatureType<type>` on every converted creature. A test
becomes a keyword test as vanilla writes them (a census of Fallout4.esm's
perks, idles and lines): `HasKeyword` on a perk's weapon or item tab (the
subject is the weapon: vanilla's 67 `WeaponTypeHeavyGun` tests) and on a
creature, `WornHasKeyword` on an actor for the weapon it holds (vanilla's
idles test `WeaponTypePistol` that way). Which perk tabs hold an item comes
from xEdit's FNV table (`wbPERKCondition`: Weapon, Item, Attacker Weapon).

An animation type compared by range (`<= 3`, `!= 8`) becomes the OR of the
matching types' keywords, or, when more than half match, the AND of the
others' keywords absent; an AND inside an OR group cannot be written and is
left out. Our own keywords rather than FO4's `WeaponType*`: they carry
FNV's authored type exactly (an FNV rifle on an FO4 template keeps FNV's
skill), where FO4's keywords describe the template.

## <a id="census"></a>Census (2026-10-20)

Sources: the FalloutNV.esm export (`export/FalloutNV.esm/PERK.txt`), FNV's
and FO4's entry-point lists in xEdit (`wbDefinitionsFNV.pas`, 74 entry
points; `wbDefinitionsFO4.pas` `wbEntryPointsEnum`, 158), the Fallout4.esm
dump (538 perks).

**FNV's 176 perks:** 101 playable, 10 traits, 65 others (challenge rewards,
quest, companion and implant perks, the hidden ones). Their effects: 143
entry points, 49 abilities, 20 quest stages. 16 perks have no effect at all
and exist only to be tested (Wild Wasteland, Child at Heart, Terrifying
Presence, the recipe perks such as Nuka Chemist).

FO4's perk records keep FNV's three effect types (quest stage, ability,
entry point), so abilities and quest stages carry over as they are; an
ability needs its spell's effects converted, as for consumables.

### Entry points

FO4 renumbered and renamed the list (Skyrim's plus Fallout's), so each FNV
entry point maps by meaning. Of the 143 entry-point effects:

| Class | Entry points | Effects |
|---|---|---|
| Direct: an FO4 entry point of the same meaning | 18 | 85 |
| With changes: another FO4 entry point, an ability, or our own system | 16 | 29 |
| No FO4 counterpart | 19 | 29 |

**Direct** (FNV → FO4): Calculate Weapon Damage (0) → Mod Weapon Attack
Damage (35, 40 effects in 26 perks, the largest); critical chance 1 → 1;
critical damage 2 → 2; mine explode chance 4 → 3; limb damage 6 → Mod
Incoming Limb Damage 4; To Hit Chance (V.A.T.S. accuracy) 8 → Mod VATS Hit
Chance 123; experience 9 → Mod Exp 22; book skill points 11 → Mod Book
Actor Value Bonus 5; recovered health 12 → 6; addiction chance 23 → 11;
positive chem duration 25 → 13; ignore running during detection 31 → 15;
ignore broken lock 32 → 16; gun spread 34 → Mod Cone-of-fire Mult 134;
enemy critical chance 36 → 17; Action Point Cost 40 → Mod VATS Attack
Action Points 79; throwing velocity 59 → Mod Actor Grenade Speed Mult 103;
explosion radius 72 → Mod Player Explosion Scale 100.

**With changes:**
- Damage Threshold: defender (56, 7 effects: Toughness, Stonewall, Hit the
  Deck, implants) and attacker (58, 3: Piercing Strike, Shotgun Surgeon).
  FO4 has no Damage Threshold; the nearest are Mod Armor Rating (85) or Mod
  Incoming Weapon Damage (36), and Mod Target Damage Resistance (37). Drift,
  decided with the armor rules.
- Activate (27, 5: Cannibal, Mister Sandman, Robotics Expert, Ghastly
  Scavenger) → FO4's Activate (14): the activation choice runs a script
  fragment, from FNV's result script.
- Reload speed (37, Rapid Reload), AP regeneration (39, Nerves of Steel) and
  run speed (42, Travel Light) → abilities, as FO4's own perks do
  (`AbPerkQuickHands` carries `AbFortifyReloadSpeedMult`; also
  `AbFortifyActionPointRate`, `AbFortifyActorSpeedMult`).
- Radiation consumed (44, Lead Belly) → an ability on `RadResistIngestion`,
  as FO4's Lead Belly.
- Knockdown chance (52, Super Slam, 2) and Meltdown (46) → Apply Combat Hit
  Spell (51), a spell that knocks down or explodes.
- Paralyzing Palm (29) → VATS Apply Paralyzing Palm Spell (155); Concentrated
  Fire (33) → Mod VATS Concentrated Fire Chance Bonus (109); Grim Reaper's
  Sprint (35, +20 AP per V.A.T.S. kill) → Mod VATS Player AP On Kill Chance
  (107), which in FO4 restores all AP: drift.
- Mysterious Stranger (28) → FO4's own Mysterious Stranger mechanism.
- Computer Whiz (20, retry a locked terminal) → Mod Terminal Lockout Time
  (127).
- Pack Rat (55, half weight for light items) → a weight entry point (31 or
  32) with a condition on the item's weight.
- Educated (10, +2 skill points per level) → the character rules, which
  hand out FNV's skill points.

**No FO4 counterpart** (29 effects): attack speed (43, 8 effects:
Fast Shot, Loose Cannon, Slayer, challenge perks); equip speed (38, Quick
Draw); aiming move speed (54, Run 'n Gun); item condition (68, 3) and Jury
Rigging (48), as FO4 has no weapon condition; ammo items (57, Hand Loader,
Vigilant Recycler: casings); the five unarmed special attacks (61-66,
faction moves such as Legion Assault, Khan Trick); Miss Fortune (41); Long
Haul (51, fast travel when overencumbered); detection and spotting (69-71,
companion perks); V.A.T.S. helper chance (67). Two need nothing: See Enemy
Health (47, FO4 always shows it) and weapon strength requirements (53, FO4
has none). The rest are drift; some could come back as a script or a
weapon-speed spell later.

### Where FNV tests perks

`HasPerk` (condition function 449) in 142 conditions: 123 dialogue lines
(Wild Wasteland 26, Terrifying Presence 26, Black Widow 18, Confirmed
Bachelor 12, Child at Heart, Lady Killer and Cherchez La Femme 9 each,
Cannibal 6, Animal Friend and Power Armor Training 3), 17 recipes (Vigilant
Recycler 8, Hand Loader 6, Nuka Chemist 3), one perk and one idle. Scripts
call `HasPerk` 51 times (Wild Wasteland 14, Stonewall 9, Light Step 10, the
challenge perks once each). All of these become real once the perks exist:
FO4 has `HasPerk` as a condition and in Papyrus.
