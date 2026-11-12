# Animation and clip conversion on Fallout 4 (plan)

**Status:** planned, not built. Status lines live only in
[ROADMAP.md](ROADMAP.md). The detailed gun steps stay in
[fo4_gun_animation.md](fo4_gun_animation.md#order); this plan orders them
beside the melee, creature, idle and super mutant items and does not repeat
them.

## <a id="goal"></a>1. Goal

Play New Vegas's own motion wherever FNV has a clip for it, on Fallout 4's
unchanged behavior graphs. One clip map says, per actor kind, which FO4
graph clip each FNV clip fills and which FO4 clips still fall through to
vanilla, so each item below becomes a list of rows plus the converter that
already writes that kind of clip.

Issue-plan rows covered ([issue plan](fo4_issue_plan.md)):

| Row | Size | Doc |
|---|---|---|
| Super mutants unarmed with shotguns, the gatling laser, launchers, the Fat Man | S (rest of a built row) | [super mutants](fo4_build_next.md#super-mutants) |
| Seated and weapon-out idles | M | [furniture](fo4_idles.md#furniture), [trees](fo4_idles.md#trees) |
| Gun animation (third person) | L | [plan](fo4_gun_animation.md#order) |
| Own-rig creature reactions and sounds | L | [idles](fo4_own_rig.md#idles), [sounds](fo4_own_rig.md#sounds) |
| Melee and unarmed animations, unarmed specials | XL | [melee](fo4_spikes.md#spike-4-melee), [perks](fo4_perks.md#census) |

Not covered: scripts waiting on object animations
([census](fo4_idles.md#census)); it is a script flag, not a clip.

## <a id="exists"></a>2. What exists

**Clip writing.** Every converted clip goes through one chain:
`fo4_import/havok/kf_cache.py:decoded_clip` (FNV `.kf`),
`asset_convert/havok/clip_retarget.py:retarget_clip` (for humans with
`fo4_import/havok/human_clip.py:matching_pose`), then
`anim_fo4.write_fo4_animation`. `human_clip.HumanClips.write` blanks track
names (`TRACK_NAME`, the fix for the Havok heap crash:
[encoder test](fo4_idles.md#encoder-test)), writes unit scale
(`UNIT_SCALE`) and `HumanClips.seated` flags seated clips (`SEATED`).

**Guns, first person** (`fo4_import/havok/gun_clips.py`). `PLAN` is
already a clip map for one view: FO4 clip name, FNV clip pattern
(`{cls}aim`, `{cls}{attack}`, `{cls}reload{letter}`) and a piece rule
(`shot`, `bolt`, `still`, `loop`). `VIEWS` holds first person only; third
person keeps the template's clips with the left-hand target carried
(`GunClips._with_assembly`, `carried_target`).
`GunClips.template_entries` copies subgraph entries onto the gun's own
keyword, `GunClips._neutral_layers` blanks FO4's additive layers and
`GunClips.race` writes the additive race (SADD on `HumanRaceSubGraphData`).
`fo4_import/spike/guns.py:Guns._clips` trades the template's Anims keyword
for the gun's own (`Guns.anim_keywords`). FNV classes come from
`asset_convert/havok/gun_vocabulary_falloutnv.py:ANIM_TYPE_CLASS`, which
leaves out melee, thrown and mines.

**AnimTextData.** `fo4_import/havok/gun_anim_text.py:load_vanilla` reads
every vanilla AnimationOffsets file into `Vanilla.clips`: the clip names
each vanilla graph can play. `copied_entries` copies vanilla's files for
entries that play no FNV clip. Since 2026-11-11 `havok/anim_text.py` writes
first-person entries' offsets and own-rig creatures' files, with no Creation
Kit run; third-person entries that play an FNV clip get none yet
([ours](research/anim_text_data.md#ours)).

**Own rigs.** `fo4_import/data/creature_rigs.json` maps FO4 clip roles to
FNV files per rig. Across the 13 rigs the roles are Idle, turns, walk, run,
CombatIdle, attacks, ranged attacks and Talk: no hit reaction, stagger,
get-up or hurt walk. `fo4_import/rig/behavior.py:Builder` builds the graph
(`standing`, `locomotion`, `combat`, `attack`, `ranged`, the rig idle
states in `dynamic`, `ragdoll_and_getup` on a pose matcher over the Idle
clip, `death`); `Builder.triggers` turns FNV text keys into events and
`fo4_import/spike/creature_sounds.py:RigSounds.of` turns `Enum:` keys into
sounds. FNV's gecko folder holds 35 clips, among them six
`idleanims\hitreaction_*` (head, torso, each limb), `idleanims\getup`, hurt
walk and run (`locomotion\hurt\`) and combat hops. None is used.

**Idles** (`fo4_import/spike/idles.py:Idles`). `line` takes speaker and
listener idles, `named` a script's `Idle` property; `_played` picks
`ROOT_GRAPH`, `FURNITURE_GRAPH` or a rig's graph; `_ambient_tree` builds
FNV's `GeneralIdles` tree under `ActionIdle`. A seated clip plays only from
a script and only when in `SEATED_PLAYED` (the mirror). `needs_weapon`
drops every `IsWeaponOut == 1` node (`WEAPON_OUT`, not built).

**Melee.** `fo4_import/nif/weapon.py:HOLD_ANIMS` poses a melee mesh in
`1hmaim.kf` or `2hmaim.kf`; record, clips and keywords are the FO4
template's. FNV ships (export `meshes\characters`, counted for this plan):

| Class | `_1stperson` | `_male` |
|---|---|---|
| `1hm` | 27 | 41 |
| `2hm` | 23 | 45 |
| `h2h` | 28 | 54 |

Among them: block, recoil, jump, counter (`h2hcounter`) and the custom and
directional power attacks (`*attackcustom1power`, `*attackleftpower`).

**Super mutants** (`fo4_import/spike/mutant_subgraphs.py`).
`write_mutant_subgraphs` adds `FNV_SuperMutantRaceSubGraphDataAdditive`;
`mutant_entries` copies `SuperMutantRace`'s weapon entries per class;
`keyword_classes` maps each gun's own keyword to its class, and `NEAREST`
(nine rows) the FO4 kinds super mutants never had. That covers 104 of 119
guns in the 2026-11-08 build (103 by the earlier count, which missed the Fat
Man: see [phase 1](#p1)); phase 1's three rows (fixed 2026-11-09, not built)
raise it to 111.

## <a id="framework"></a>3. The framework

### <a id="clip-map"></a>3.1 The clip map

One census tool and one data table, beside the converters that exist.

- **FO4 side.** For each subgraph entry a converted actor can use: its
  graph's clip names from `gun_anim_text.load_vanilla` (no graph parsing
  needed), and its folder list from `gun_clips.subgraph_entries` over
  `HumanRaceSubGraphData`, `SuperMutantRace` and each rig template's race.
- **FNV side.** The `.kf` files per class folder (`_1stperson`, `_male`, a
  rig's folder).
- **The map.** One row per FO4 clip name and class: the FNV clip pattern,
  the piece rule (as `PLAN`'s) and the converter writing it (gun view,
  human clip, rig role). `gun_clips.PLAN` becomes the first view's rows;
  the rig table's `clips` are a rig's rows.
- **The report.** Per entry, the FO4 clips no row fills: they still play
  vanilla's motion (gun step 0's fall-through list).

It is a `tools/` script, since new input changes its answer, listed in
[python_tools.md](../reference/python_tools.md) when built.

**Why it covers these rows.** Each item is the same work: find which FO4
clip a state plays, name the FNV clip for it, write it under that name in a
folder searched first, let the CK regenerate AnimTextData. Guns in third
person are `PLAN` rows for a second view; melee and unarmed are rows for
the melee graphs on the additive-race route guns use; super mutants are
`NEAREST` rows checked against `SuperMutantRace`'s entries; creature
reactions are rig roles plus states in the rig graph we write ourselves;
weapon-out idles are dynamic-idle rows on `WeaponBehavior.hkx`. Vanilla
graphs stay unedited: editing one overrides a base-game file
([mechanism](fo4_gun_animation.md#mechanism)).

### <a id="dll"></a>3.2 DLL decisions

Each needs the user's approval. None is needed before phase 6.

| Candidate | When it comes up | Alternative first |
|---|---|---|
| Unarmed directional specials: picking FNV's forward, back, left, right, crouched and counter power attack (perk entry points 61-66) | Phase 6 finds no directional power attack in FO4's melee graph and actions | FNV's special clip on FO4's single power attack through an actor-keyword subgraph entry, its effect through a combat-hit perk entry; else drift |
| A timing hook for reloads and bolts ([gun step 10](fo4_gun_animation.md#timing)) | A reload still feels wrong after phase 3 | Clips held to vanilla's length plus the WEAP's speed fields (gun step 7) |

## <a id="phases"></a>4. Phases

### <a id="p1"></a>Phase 1 (S): super mutant rows

Add three `NEAREST` rows. Data only. **Fixed 2026-11-09, not built.** On
the 2026-11-08 build's 119 guns (WEAP animation type Gun) the rows newly
cover exactly 7: Gatling Laser, Caravan Shotgun and Cass's, Riot Shotgun,
Sawed-Off Shotgun and its unique, Grenade Launcher (a KWDA-only count, so
its totals, 76 to 83, leave out default parts' keyword adds; the delta is
the 104 to 111). `tests/test_fo4_mutant_subgraphs.py` checks the rows and,
against Fallout4.esm, that each key and class has super mutant entries.

**Measured** on the deployed plugin of the 10:22 2026-11-08 build: a gun
counts as covered when some `SuperMutantRace` entry, or a copy
`mutant_entries` makes (target: the one keyword), has its whole target set
among the gun's KWDA plus its default parts' keyword adds.

**The Fat Man was never uncovered.** The built
`FNV_SuperMutantRaceSubGraphDataAdditive` has entries targeting
`AnimsFatMan` alone, and the Fat Man (a `stats` replacement on FO4's
`Fatman`) carries `AnimsFatMan`. The earlier count was wrong: it checked the
vanilla target pair (`AnimsGripShoulderFired`, `AnimsMissileLauncher`)
instead of the copy's single keyword, and the Fat Man has no
`AnimsGripShoulderFired`. True coverage is 104 of 119.

**Rows to add** (key: the Anims keyword the gun carries or its own keyword
replaced). The evidence is the folder chain FO4's own human entries
(`HumanRaceSubGraphData`) fall back through for each kind:

| Key | Class | Guns | Vanilla evidence |
|---|---|---|---|
| `animsDoubleBarrelShotgun` (lower-case `a`, as in Fallout4.esm) | `AnimsHuntingRifle` | Caravan Shotgun (and Cass's), Sawed-Off Shotgun (and unique), Riot Shotgun | The human entry falls back DoubleBarrelShotgun → `Rifle\Neutral` → `GripRifleStraight`, the hunting rifle's chain. Super mutants hold hunting rifles in vanilla LVLIs |
| `AnimsGatlingLaser` | `AnimsMinigun` | Gatling Laser | Falls back GatlingLaser → `GripHeavy`, the same as Minigun. Super mutants hold miniguns in vanilla |
| `AnimsRailwayRifle` | `AnimsHuntingRifle` | Grenade Launcher (built on FO4's railway rifle: `FNV_AnimsRailwayRifle_WeapNVGrenadeLauncher`) | Falls back RailwayRifle → `Rifle\Neutral` → `GripRifleStraight`. FNV holds it as a rifle (`FNV_WeaponAnimRifleBallistic`), so not the missile launcher's class |

Three shotguns carry their own `FNV_animsDoubleBarrelShotgun_*` keyword and
two carry vanilla's. `keyword_classes` covers both, because the base build
passes `vanilla`. A census script that matches `FNV_Anims` case-sensitively
misses the own ones.

**Left uncovered (8):** creature weapons with no Anims keyword (Securitron
laser, SMG, launcher and missile; centaur and evolved centaur spit; spore
plant spit; `QueenAnt2HL`). No super mutant holds them.

- **Check:** the one-off count against the rebuilt plugin goes from 104 to
  111 of 119, with only the 8 creature weapons left;
  `tests/test_fo4_mutant_subgraphs.py` gains the rows. In game, a super
  mutant with a shotgun at Black Mountain fires it.
- **Depends on:** nothing; starts after the play test.

### <a id="p2"></a>Phase 2 (M): the clip map tool

Build [3.1](#clip-map); gun rows from `PLAN`, rig rows from
`creature_rigs.json`. This is [gun step 0](fo4_gun_animation.md#measure).
- **Check:** for the five played guns (9mm, Assault Carbine, Hunting
  Rifle, Flamer, Tesla Cannon) the first-person fall-through list matches
  what `gun_clips` writes, and every clip named is in `Vanilla.clips` for
  that graph. Third-person, melee, super mutant and gecko reports list the
  rows phases 3-7 fill.
- **Depends on:** nothing. It re-ranks phases 3-7 by fall-through count.

### <a id="p3"></a>Phase 3 (L): guns in third person

Gun steps [1](fo4_gun_animation.md#third-person-clips),
[2](fo4_gun_animation.md#entry-variants),
[3](fo4_gun_animation.md#third-person-ik) and
[5](fo4_gun_animation.md#anim-info): a third-person `View` with `_male` rows
(upper body only), every entry variant and power armor, the IK target on
states FNV has no clip for, the CK for entries now playing FNV clips.
- **Check:** no vanilla entry outranks the gun's (a SADD check over the
  built plugin). In game, the five guns keep the left hand on the gun in
  third person standing, walking, sighted, firing and reloading, and NPCs
  aim them at the player.
- **Depends on:** phase 2.

### <a id="p4"></a>Phase 4 (M): own-rig reactions and sounds

- Rig roles from FNV's files: a hit reaction per part (head, torso, each
  limb), `GetUp` (into the pose matcher in place of Idle), hurt walk and
  run.
- In `behavior.Builder`, a hit-reaction state per part and a stagger
  state, entered on the template graph's own events. Their names come from
  phase 2's read of the template graph and are *unverified* until then;
  prior art names `staggerStart` and similar
  ([technique notes](research/fo4_creature_rig_prior_art/fo4_creature_technique.md)).
- Sounds [not carried](fo4_own_rig.md#sounds): Hit as a reaction state
  starts, Aware as the combat state starts, Idle on the dynamic idle states.
- Jumps, side and back moves and kill moves: FNV ships no clip for them
  ([route B](fo4_spikes.md#route-b)). Left out as drift unless the play
  test shows a rig stuck at a jump link.
- **Check:** `tests/test_fo4_own_rig.py` finds the new states on FNV clips
  in the gecko's graph. In game, a gecko shot in the leg flinches that leg
  with its hit sound and gets up with FNV's get-up.
- **Depends on:** phase 2 (template events); the played rig idles (section 5).

### <a id="p5"></a>Phase 5 (L): melee and unarmed on FNV's clips

`1hm`, `2hm` and `h2h` rows for both views on the melee graphs' clip names
from phase 2; an own keyword per FNV class with entries in the human
additive race, as `Guns._clips` does for guns; the super mutant race copies
them through `mutant_subgraphs`. The hold takes the guns' Weapon-bone grip
rule.
- **Check:** the bat, the switchblade and the fists swing FNV's motion in
  both views, hit at FNV's `Hit` key, and block and recoil play.
- **Depends on:** phases 2 and 3 (the third-person view).

### <a id="p6"></a>Phase 6 (M): unarmed specials

Census FO4's power attack actions and the melee graphs' power attack clips
(phase 2 report). Then fill FO4's directional power attacks with FNV's
`*attackforwardpower`, `backpower`, `leftpower` and `rightpower` clips
under perk-gated conditions, or take the alternative in [DLL
decisions](#dll).
- **Check:** with Legion Assault, the forward power attack plays FNV's
  move and applies its effect.
- **Depends on:** phase 5; the user's call on any DLL row.

### <a id="p7"></a>Phase 7 (M): seated and weapon-out idles

- **Seated (S part).** One change: `VCG01DocShrug` (four lines) as a
  speaker idle on the furniture graph, now that the crash cause (named
  tracks) is fixed. If it holds, open the rest of the 22 lines; if it
  crashes, vanilla's seated-talk route (root graph, `dyn_talkGeneric`,
  [mechanism](fo4_idles.md#mechanism)).
- **Weapon-out.** The `IsWeaponOut` branches under a
  `WeaponAltIdleRoot`-shaped node on `WeaponBehavior.hkx`, FNV's weapon-type
  tests as `HasKeyword` on phase 2's class keywords. The event vanilla's
  weapon idles send is *unverified*: read `WeaponAltIdleRoot`'s children
  first.
- **Check:** Doc's shrug plays seated through the psych test, no crash at
  the stand-up or looks menu over three runs; the 2hr and 2ha loiters play
  on a guard with a drawn rifle.
- **Depends on:** the played ambient tree (section 5); phase 2's keywords.

## <a id="play-first"></a>5. What the play test should tell us first

- **Super mutants with pistols and the Multiplas** fire them
  ([super mutants](fo4_build_next.md#super-mutants)). If not, phase 1 fixes
  the mapping route instead of adding rows.
- **The Think Tank's special idles** play ([rig idles](fo4_own_rig.md#idles)).
  Phase 4's states use the same wildcard pattern; a failure blocks it.
- **The ambient idle tree** plays on the human root graph
  ([trees](fo4_idles.md#trees)). If the engine never offers it, the
  weapon-out half of phase 7 needs another route.
- **Doc's standing idles and props** play without a crash
  ([props](fo4_idles.md#props)). A new crash puts the clip writer under
  suspicion before anything here.
- **Third-person left hand** on converted guns (built 2026-10-31, not
  played: [gun clips](fo4_spikes.md#spike-4-gun-clips)). If it holds,
  phase 3's IK work shrinks.
- **Deathclaw charge attacks** still fire: not this plan's item, but a
  broken attack choice would show in phase 4's rig combat too.

## <a id="questions"></a>6. Open questions

- Which events does FO4 send a creature graph for a hit reaction and a
  stagger? Read before phase 4.
- Does FO4 pick directional power attacks for melee at all? This decides
  phase 6's DLL row.
- Melee keyword per FNV class or per weapon? Guns are per weapon because
  the mesh sets the hold; a melee hold may need only the class.
- Jumps, side moves and kill moves on own rigs: accept as
  [drift](fo4_drift.md#recorded)? FNV has no clip for them.
- FNV's female clips are not converted ([clips](fo4_idles.md#clips)). Do
  this plan's rows need them, or does the male set do?
- [Combat feel](fo4_combat_feel.md) keeps FO4's stagger in place of FNV's
  flinches for humans. Do phases 3 and 5 keep that, or add FNV's `*recoil`
  clips?
