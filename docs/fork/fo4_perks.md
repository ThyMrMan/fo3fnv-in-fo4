# FNV perks on Fallout 4

**Status:** census done 2026-10-20; PERK records (step 2), the level-up list (step 3) and real `HasPerk` (step 4) built 2026-10-20/21, not played. Next: the play-test (step 5).

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
  and kind (`AbFortify*`/`AbReduce*`/`abRestore*`, by the Detrimental 0x4
  and Recover 0x2 flags both games use), or a copy of `AbFortifyStrength`,
  `AbReduceCarryWeight` or `abRestoreHealth` on it. An effect without
  Recover changes the value every second (FNV's `Regen`, the limb
  restores, `GhoulRadHeal`; FO4's `abRestoreHealth`); until 2026-10-27
  those became permanent raises. Script effects (Calm Heart, the
  regeneration implant) are left out.
- **Actors' abilities** (FNV creatures' actor effect lists, from the
  template with Use Actor Effect List 0x8) convert the same way
  (`Perks.ability`): the NPC's spell list (`SPCT`, `SPLO` after `RNAM`)
  gets the ability's FNV FormID at once, and the record is written with
  the perks, when its conditions' form map exists. FalloutNV.esm's
  creatures carry 38 spells, all abilities: resistances (Rad, Poison and
  Fire Immunity at FNV's number, as Rad-X), Damage Resistance, crit
  chance, water breathing, regeneration. Left out, as for perks: Damage
  Threshold (17 spells) and crit chance, which FO4 has no actor value
  for. A script-effect ability (the glow, `GlowingOneGlowSpell`) is
  `script_effects`' constant script effect (`Perks.ability` falls back to
  it). FNV's `GetRadiationLevel` condition is FO4's `GetValue Rads`
  (`conditions.AS_VALUE`), so the ghouls' `GhoulRadHeal` (heal while
  irradiated, burning the rads off) keeps its two effects; it was written
  empty before.
- <a id="script-abilities"></a>**Abilities a script adds** (a Spell
  property naming an FNV ability, `Perks.named_ability`, after
  `script_effects` for script-effect spells) convert the same way. FNV's
  Chameleon effect `StealthBoyInvis` has no FO4 actor value; it becomes
  `AssaultronStealthEFFECT` (`CONSTANT_EFFECTS`), Fallout4.esm's constant
  Chameleon effect behind `assaultronStealthSpell`, vanilla's NPC cloak
  ability (the other constant one, `ChameleonEffectArmorMod`, carries the
  armor's script). Magnitude stays FNV's: FO4 reads it as the stealth
  percentage (Stealth Boy 99, armor 20 and 50). So Jacobstown's
  nightstalkers (`JacobstownNightstalkerScript`) get
  `StealthBoyInvisibilitySpell` again, cloaked at 95 with Sneak +100 until
  hit (played 2026-10-27); before then its property was empty.
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

## <a id="hasperk"></a>The level-up list and HasPerk (steps 3 and 4)

- **Level-up list.** LevelUpMenuEx reads `FNV_Perks` (the PRKF INI's
  `PerksList`) and, per perk, its rank count, required level and next rank
  (its strings: `numranks`, `reqlevel`, `ranksInfo`; ownership through
  `GetPerkRank`), so FO4's rank chains fit it as they are. The list holds
  FNV's playable perks that are not traits or hidden, first ranks only,
  by level then name: 91 (`perks.Perks.playable`). Traits stay on
  `FNV_Traits`. A perk point comes every `LevelsPerPerk` levels (FNV: 2)
  from `F3NV_CharacterRules`; the INI's own `PPPerLevel` stays 0.
- **HasPerk.** FNV's HasPerk holds at any rank, and an FO4 actor keeps
  every rank of a chain, so an FNV perk is its first-rank record
  everywhere (`Perks.form_map`):
  - dialogue, idle and perk conditions (the condition form map): the 32
    region lines blocked on `HasPerk` now pass it (8 build; the rest stop
    on other conditions);
  - recipes (`crafting._condition`): the 17 perk-gated recipes, Vigilant
    Recycler, Hand Loader and Nuka Chemist, were skipped and now build;
  - consumable effects (`consumable_effects`): 129 effect tests in the
    region. Before, an effect needing a perk was dropped and one needing
    a perk's absence ran for everyone;
  - converted scripts' `Perk` properties fill by FNV EditorID
    (`Perks.named`; `WildWasteland` alone in 13 scripts).

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

## <a id="skill-gates"></a>Lock and terminal gates (built 2026-10-21, not yet played)

FNV opens a lock or terminal of level L (0 to 100) only at Lockpick or
Science L or more. FO4 numbers lock levels alike (xEdit: 0 and 25 Novice,
50 Advanced, 75 Expert, 100 Master; vanilla places 0 and 25 freely) and our
build already writes FNV's levels unchanged. FO4 gates the tiers by perk
entry points, not ranks: each Locksmith rank sets Set Player Gate Lockpick
(62) to 1, 2, 3 (Fallout4.esm Locksmith01-03), each Hacker rank Set Player
Gate Hacking (98) the same.

`FNV_SkillGates` (`perks.gate_effects`) is one hidden, unplayable perk of
six entry-point effects: each gate Set Value 1, 2 and 3 on the condition
GetValue(Lockpick or Science) >= 50, 75 and 100 (the helper plugin's skill
actor values), the higher tier at a higher priority so it applies last. The
conditions are read live, so the gate follows the skill (and its buffs) as
it changes. `F3NV_NewGame` gives the player the perk as it starts and on
every load (a save from before it gets it too). FO4's own Locksmith and
Hacker perks are untouched (the FO4 perk chart is off).

FNV's Easy tier (25) needs Lockpick or Science 25, but FO4's Novice tier
has no gate. Those locks run `F3NV_FalloutLock`, which refuses the player
below the skill ([fo4_pipeline.md](fo4_pipeline.md#lock-script)).

## <a id="teammate-perks"></a>Teammate perks (companion side built 2026-10-22, not yet played)

FNV's `AddPerk <perk> 1` and `RemovePerk <perk> 1` (the teammates flag) put
a perk on the player's teammate list. FNV applies its entry points to each
active companion, never to the player, and each perk's owner tab names its
companion (`GetIsID`). The flag is on 11 calls in 10 scripts and line
results, on 6 perks:

| Perk | Companion | FNV effect | On FO4 today |
|---|---|---|---|
| Hand of Vengeance | Cass | Guns damage ×1.15 (entry point 0) | Mod Weapon Attack Damage (35) |
| Old Vaquero | Raul | attack speed ×1.33 (43) | left out: no FO4 counterpart ([census](#census)) |
| Causeless Rebel | Veronica | attack speed ×1.3 (43) | left out, as Old Vaquero |
| Bonds of Steel | Veronica | DT +4 (56) | left out: Damage Threshold waits on the armor rules |
| Companion Suite | Cass | Shotgun Surgeon's target DT (58), an ability | left out: DT; the ability, as below |
| Calm Heart | Cass (wiki) | an ability: `CalmHeartScript` sets Health base +50 | left out: a script effect, and no companion named |

**How FO4 does it.** FO4 has no teammate flag; a perk acts on its holder
only. Vanilla's Inspirational is the pattern: the player holds
`Inspirational01`, and the companions' NPC records hold
`CompanionInspirational` (PRKR on 9 NPCs), whose entry points test
`PlayerRef.HasPerk(Inspirational0x)`. Neither other option fits: adding the
perk to each follower by script needs a list of followers and a re-add
when one joins, and a player perk's entry points act on the player (the
ability types too).

**What the build does** (`fo4_import/spike/teammates.py`):
- `teammate_edids` reads the flagged calls in the export's scripts and line
  results (SCPT, INFO, QUST). Those perks are the player's, with no
  effects: holding one only switches its companion perk on. They are
  hidden (DATA), since FNV kept them on its teammate list, not the
  player's. Companion Suite showed in the perk list before that
  (played 2026-10-22).
- Each one gets a companion perk, `FNV_<perk>_Teammates` (FormID from
  `PERK <FNV FormID> teammates`, hidden, unplayable). It carries FNV's entry
  points, their owner tab gated first by `GetPlayerTeammate == 1` and
  `PlayerRef.HasPerk(<the FNV perk>) == 1`, so it works only while the
  companion follows, as FNV's. Abilities are left out (counted): FNV never
  applied Companion Suite's (the wiki calls it "a bugged perk with no real
  effects"), and Calm Heart's is a script effect.
- The companions the owner tabs name (`GetIsID == 1`) hold it: PRKZ and
  PRKR on their NPC record (`npcs.with_perks`). A perk naming none (Calm
  Heart) gets no companion perk (counted).
- The converter turns the flagged call into the player's
  `AddPerk`/`RemovePerk`, as without the flag, so a script's
  `Player.HasPerk CalmHeart` reads true too.

Doc Mitchell's exit trigger (`VCG01RemoveDocCarebearModeTriggerSCRIPT`)
runs `Player.AddPerk CompanionSuite 1`. Before 2026-10-21 the player got
its ability (`PerkCompanionSuite` 0015C570: carry weight -75, DR +50, Sneak
+100) and Sneak showed 115. Now the player's Companion Suite has no effects,
so a save that holds it from then is fixed too. FNV's other
`AddPerk CompanionSuite` calls name the companion (`CraigBooneREF.AddPerk`):
the companion holds the effectless perk, as FNV's companions held one that
did nothing.

The region build has no FNV companion that a perk names (Cass, Raul and
Veronica live outside it). Their `GetIsID` cannot convert there, so the
companion perks are written without effects and no NPC holds one.
- **Calm Heart.** The +50 Health is a script effect; it needs Cass named and
  the effect as a Health ability.
- **Attack speed and Damage Threshold.** These entry points come with the
  census's open rows.

## <a id="stat-abilities"></a>Stat abilities (built 2026-10-29, not yet played)

FNV entry points on the holder's own stats have no FO4 entry point; each
becomes an ability, as FO4's own perks do it (`AbPerkQuickHands`). The
perk's effect turns into a spell of one constant effect on the FO4 actor
value, under the effect's owner conditions (`STAT_ENTRIES` in
`fo4_import/spike/perks.py`):

| FNV entry point | FO4 actor value | Multiply Value m becomes |
|---|---|---|
| 37 reload speed (Rapid Reload ×1.25) | ReloadSpeedMult (0x2D3) | m − 1 (Quick Hands writes 0.35) |
| 39 AP regeneration (Nerves of Steel ×1.2) | ActionPointRate (0x2D8) | (m − 1) × 6 |
| 42 run speed (Travel Light) | SpeedMult | (m − 1) × 100 |
| 44 radiation consumed (Lead Belly) | RadResistIngestion (0x2E9) | −(m − 1) × 100 |
| 56 defender Damage Threshold (Toughness, implants) | DamageResist (FNV DT) | Add Value as is |

An Add Value keeps its value. The AP-rate units are inferred: Action Boy's
+25% writes 1.5, so FO4's base rate is taken as 6. The effect is
Fallout4.esm's own on that value when one exists (`AbFortifyReloadSpeedMult`,
`AbFortifyActionPointRate`); a value with none, given by FormID, is left out
and counted. Effects that test the attacker or weapon tab (Stonewall, Hit the
Deck) cannot be an ability and stay drift. The attacker's DT (58, Piercing
Strike) becomes Mod Target Damage Resistance (37) Add −value, which the DT
hook reads ([damage threshold](fo4_pipeline.md#damage-threshold)).

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
