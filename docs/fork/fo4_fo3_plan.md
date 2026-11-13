# Fallout 3 on Fallout 4: the Vault 101 spike

**Code:** `fo4_import/spike/new_game.py`, `fo4_import/spike/script.py` (`use_prefix`, `prefix`),
`fo4_import/nif/collision.py` (`_bhkConvexListShape`), `fo4_import/nif/tree.py` (`BODY_TEMPLATES`),
`fo4_import/spike/object_lod.py` (`CARD_TEMPLATES`), `fo4_import/spike/conditions.py` (`use_actor_values`),
`fo4_import/spike/quest_scope.py` (`STARTS`), `fo4_import/data/replacements.json` (`_rules.creature`).

The first Fallout 3 build on the FO4 pipeline, limited to Vault 101 and the
opening: the birth, Baby Steps, the 10th birthday, the G.O.A.T., the escape
and the vault door. Status is in [ROADMAP.md](ROADMAP.md#fo4-app).

## Contents

- [What FO3 shares with FNV](#shared)
- [What was FNV-only](#fnv-only)
- [The scoped build](#build)
- [The opening on a new game](#opening)
- [Creatures](#creatures)
- [Dialogue changes FO3 needs](#dialogue)
- [Tale of Two Wastelands](#ttw)
- [Next](#next)

## <a id="shared"></a>What FO3 shares with FNV

Measured against xEdit's two definitions (`wbDefinitionsFO3.pas`,
`wbDefinitionsFNV.pas`):

- **Actor values.** FO3's 73 actor values sit at the same indexes as FNV's
  first 73. Four names differ: 41 Small Guns (FNV Guns), 44 Throwing, unused
  (FNV Survival), 51 Detect Life Range (FNV Turbo), 72 Ignore Negative
  Effects (FNV Ignore Crippled Limbs). FNV adds 73-76 (the three Hardcore
  needs, Damage Threshold). The helper plugin keeps Small Guns as its own
  actor value (`SmallGuns`, which FO3's converted scripts read), so an FO3
  build names its actor values by FO3's list: `conditions.use_actor_values`
  sets `FNV_AV_NAMES` from the source game once per build, beside
  `use_prefix`. FNV's builds keep FNV's list. Before this, the character
  rules failed on FO3's `SmallGuns` and a condition on actor value 41 would
  have read FNV's Guns.
- **Condition functions.** Every FO3 function number names the same function
  in FNV, except FNV-only additions (objectives, reputation, Hardcore,
  casino, challenges) and the script extenders' numbers above 1024
  (FOSE's `IsKeyPressed` 1082 is not NVSE's). FO3 plugins never author the
  FNV-only ones.
- **Character rules.** `spike/character.py` already has Fallout 3's skill
  governance and rates (`GOVERNING`, `RATES` keyed `Fallout3.esm`).
- **Source plugin.** `base/source.py` already resolves `export/Fallout3.esm`
  to Fallout 3's Data folder, so fields read from the plugin (regions,
  weathers, factions...) come from Fallout3.esm.

## <a id="fnv-only"></a>What was FNV-only

| What | Where | Fix |
|---|---|---|
| <a id="script-prefix"></a>Converted script names | `FALLOUTNV_` written into `attach`, `quest`, `quest_scope`, `packages`, `perks`, `terminals`, `patrol_topics`, `say_topics`, and two validate tools. FO3's converted scripts are `FALLOUT3_*` (the script converter names them by the game's namespace, `namespace_for`) | `script.use_prefix(export_dir)` sets the run's prefix once, beside `install.use_source`; callers ask `script.prefix(kind)`. Every FNV, DLC and mod build keeps `FALLOUTNV_` (their namespace is New Vegas's), so their output does not change. `say_topics.py` is [left to the dialogue rewrite](#dialogue) |
| The opening | `new_game.START` named only `VCG00` | `Fallout3.esm: ('CG00', 0)`, [below](#opening) |
| `bhkConvexListShape` collision | FO3 meshes use it (FNV's never do); the FO4 collision writer raised on it | Written as the `bhkListShape` of its convex sub-shapes |
| Tree collision body | `nif/tree.py` copied the body settings of FNV's `nvgreybirch01.nif`, which FO3 lacks | `BODY_TEMPLATES` by source game: FO3's own `treedead01.nif` (the same fixed body, on FO3's Trees layer 9 where the birch has Static 1) |
| Tree LOD cards | `object_lod.card_nif` copied FNV's lit `treejoshanv_lod.nif`; FO3's 10 billboard trees would have crashed | `CARD_TEMPLATES` by source game: FO3's own `treedead02_lod_flat.nif`, unlit as FO3 draws its LOD trees; `_card_texture` names the billboard on a lit or unlit shader |
| Creature rules | yao guai, Liberty Prime and ZAX had no rule | [below](#creatures) |
| A stale export | `export/Fallout3.esm` dated 2026-10-02: its 350 placed grenades (PGRE) carried no base or position, so the exterior pass crashed | Re-exported with today's exporter (`convert.py -f Fallout3.esm --export-only`, 13 s). The 16 types FNV has and FO3 lacks are all FNV-only records |

Still FNV-shaped, not blocking the spike (drift, listed for later):

- Engine defaults read from `FalloutNV.exe` where a GMST is absent
  (`combat_styles.fnv_settings`, criticals, hardcore, sneak attacks). FO3's
  plugin authors most of these GMSTs; the rest take New Vegas's value.
- Record EditorIDs are `FNV_*` in an FO3 build too, and the new-game quest
  is `FNV_NewGame` (so `setstage FNV_NewGame 10` starts FO3 by hand). Renaming
  them would rename every FNV record.
- Hardcore, reputation, challenges and the casino build nothing for FO3
  (no records), as they should.

## <a id="build"></a>The scoped build

```bash
py -3.14 -m fo4_import.pipeline.run --export export/Fallout3.esm --out <data>/Fallout3.esm --data <data> --scripts temp/fo4_scripts/Fallout3.esm --world Wasteland --around -4 -4 --radius 1 --no-test-cell Vault101d
```

`Vault101Exterior` (the vault door) is grid -4,-4 of `Wasteland`; the
interior cells come in through the opening's quests and doors. Measured on a
scratch build (863.7 s, stamp `finished`, 0 source faults):

- 142 quests: CG00-CG04, CGTutorial, MQ00-MQ09 and the quests they start.
  Cells: `Vault101a`, `b`, `d` and their MS16 copies, plus what the opening's
  quests reach (Raven Rock, Vault 112, the reactor).
- 236 actors, 229 faces fitted; 4,715 of 4,721 converted scripts compile.
  The six that fail are none of the opening's: `FFER05LootBoxSCRIPT` (an
  `OnDeath` block on a container), `FFEU02DeathclawSCRIPT`,
  `FFEU05RadscorpionSCRIPT` and `MS01QuestScript`
  (`TES4Polyfill.MirrorPlayerFactionRelation` is missing), `MQ01Script` (a
  Form passed as an ObjectReference in Lyons' Pride's `SayWhenFree`) and
  `MQ11PPurityControlPanelScript` (`Apply`).
- With the [dialogue prefix change](#dialogue) applied locally: 18,178 line
  fragments named `FALLOUT3_TIF__*`, none `FALLOUTNV_*`. Without it the
  plugin had no line fragments (0 `FALLOUT3_TIF__`) and 196 references
  named New Vegas scripts.

**Preflight** (`python -m tools.validate.preflight`): 2,306 errors over the
whole plugin, almost all from the quests the scope pulls in beyond the
opening (MQ, MS16, Raven Rock), whose cells and actors are not built. On the
opening's own quests (CG00-CG04, CGTutorial, MQ01, the new-game quest):

| Audit | Errors | What |
|---|---|---|
| quest | 36 | Mostly MQ01's later stages; CG04 110/120 wait on the reactor switch |
| properties | 5 | `CG04`'s dummy `Vault101` cell (FO3 uses it only for `GetInCell`), `Vault101Demo`, `CG04RadroachSpawn`, the reactor package and marker |
| behavior | 37 | `Find` packages; CG02's talk packages name no topic |
| dialogue | 9 | lines whose speaker is out of scope |
| timing | 3 | CG00 0/61 and CG01 0 ran in `MenuMode`, now on the stage |
| menus | 2 | the race and SPECIAL menus, through the polyfill |

The quest scope missed `CG03Test` (the G.O.A.T. answers): `CG03Script` sets
its stages through `TES4Polyfill.SetStage(CG03Test, 9)`, which the scope's
pattern read as a call on a quest named `TES4Polyfill`. The pattern now reads
the quest argument (`quest_scope.STARTS`), so CG03 starts CG03Test and CG04.
On FalloutNV.esm's converted scripts this form names 21 quests; 5 are not
started any other way (`CG02`, `Doctors`, `VDoctors`,
`VES02DialogueGeckoman`, `VVault21Tour`), so a whole-map FNV build may gain
up to those 5 quests. New records only: no existing FormID moves.

## <a id="opening"></a>The opening on a new game

`new_game.START['Fallout3.esm'] = ('CG00', 0)`, as `VCG00` for FNV: the new
game quest's stage 0 runs Fallout 3's own opening. FO3's engine started
`CG00` itself (it is not start-game enabled), so nothing else in the plugin
starts it. `setstage FNV_NewGame 10` starts it by hand.

Only play can check:

- The birth to the escape plays in order: CG00 (birth) → CG01 (Baby Steps)
  → CG02 (the birthday) → CG03 (the G.O.A.T.) → CG04 (the escape), stages
  set by 44 of the plugin's dialogue lines and by quest scripts.
- `AgeRace` is not converted, so the 10th birthday plays on the adult
  race, and the child jumpsuit does not draw on it; the age-1 scale does
  convert ([child player plan](fo4_fo3_child_player.md#route)).
  `SetLocationSpecificLoadScreensOnly` is dropped and
  `PipBoyRadioOff` is not converted yet.
- **IgnoreCrime** is converted ([how](fo4_plan_script_functions.md#ignore-crime)):
  CG02 and CG03 clear the crime faction of almost everyone in the vault
  (Butch, Wally, Paul, Dad, Amata...), so hitting Butch at the birthday
  and before the G.O.A.T. is a fight, not an assault the vault reports.
- **SetInCharGen** is converted to a remembered flag (CG00-CG03 on, CG04's
  end off) with Fallout 4's own chargen state off. FO3's hold on leveling
  is not: a level gained in the vault arrives at once.
- Fallout 4's own intro movie plays first; Fallout 3's is not built.
- The race and SPECIAL menus open through the polyfill.
- **Profile:** FalloutNV.esm and Fallout3.esm both carry a new-game quest
  (`FNV_NewGame`), so the FO3 test runs in its own Mod Organizer profile
  with no New Vegas plugins.

## <a id="creatures"></a>Creatures

Fallout3.esm's 533 creatures by skeleton folder (the `_rules.creature` key),
measured on the export:

| Folder | Creatures | Fallout 4 stand-in |
|---|---|---|
| `creatures\smspinebreaker` (super mutants) | 43 | `EncSuperMutantTemplate`, FO3's mesh |
| `creatures\protectron` | 37 | `EncProtectron01Template` |
| `creatures\mistergutsy` (Gutsy and Handy) | 27 | `encMrGutsy01Template` |
| `creatures\dog` | 25 | `dogmeat`, FO3's mesh |
| `creatures\ghoul` | 24 | `encFeralGhoul01Template` |
| `creatures\radroach` | 23 | `EncRadRoach` |
| `creatures\giantant`, `creatures\queenant`, `creatures\centaur` | 21, 3, 3 | own rig (FNV's rule) |
| `creatures\sentrybot` | 19 | `EncSentryBot01Template` |
| `creatures\brahmin` | 17 | `EncBrahminTemplate` |
| `creatures\sentryturret`, `creatures\minisentryturret` | 15, 4 | `EncTurretBubbleLaserTemplate` |
| `creatures\deathclaw` | 12 | `EncDeathclaw01Template` |
| `creatures\yaoguai` | 11 | **new:** `EncYaoGuai01Template` (Honest Hearts' folder already had it) |
| `creatures\robobrain` | 11 | `EncProtectron01Template` |
| `creatures\eyebot` | 9 | `EncEyeBot` |
| `creatures\molerat` | 8 | `EncMolerat01Template` |
| `creatures\mirelurk`, `creatures\mirelurkking` | 7, 3 | `EncMirelurk01Template`, `EncMirelurkKing01` |
| `creatures\smbehemoth` | 7 | `EncSMBehemoth01Template` |
| `creatures\radscorpion` | 5 | `EncRadscorpion01Template` |
| `creatures\zaxeye` (ZAX, a talking computer) | 3 | **new:** a speaker, as FNV's Mr. House screens |
| `creatures\blowfly` (bloatfly) | 1 | `EncBloatfly01Template` |
| `creatures\libertyprime` | 1 | **new:** `EncLibertyPrime` |
| `creatures\failedfevsubject` (Vault 87's FEV subject) | 1 | **no rule:** Fallout 4 has nothing like it |
| no model (144) and `marker_creature.nif` (49) | 193 | templated or leveled creatures: they take their template's folder |

The three new rules name folders no FNV, DLC or pack creature uses
(checked on FalloutNV.esm and the four story DLC), so no FNV FormID moves.
Vault 101's own creatures are radroaches (the escape) and Mister Handy
(`mistergutsy`), both covered.

## <a id="dialogue"></a>Dialogue changes FO3 needs

`say_topics.py`, `conversation.py` and `say_once.py` are being rewritten (XDI
dropped), so they are not edited here. FO3 needs one change there:

- `say_topics.FRAGMENT_PREFIX` and `say_topics.SCRIPT_PREFIX` hard-code
  `FALLOUTNV_`. They become `script.prefix(FRAGMENT)` and `script.prefix()`
  ([script prefix](#script-prefix)). Without it an FO3 line loses its
  result script, and the opening is driven by them: 44 of Fallout3.esm's
  lines set a CG00-CG04 stage.
- Any new dialogue code naming a converted script takes `script.prefix()`
  the same way.

## <a id="ttw"></a>Tale of Two Wastelands

Not measured: TTW is not installed on this machine (not in the MO2 mods
folder or the Steam library), so this is a judgement from how TTW is built.

**What TTW is.** Its installer reads the user's Fallout 3 and builds
`TaleOfTwoWastelands.esm`, an FNV-format master on FalloutNV.esm and the
FNV DLC and packs, holding Fallout 3 and its five DLC as New Vegas records
(new FormIDs in TTW's own space), plus BSAs repacked from Fallout 3's.

**Through the FNV path it is close: a big mod build, not a new game.**

- The record formats are FNV's, so every converter already reads them. The
  plugin has masters, so it builds like a DLC or mod (`--import-mod`, the
  masters' ledgers, master-export lookups), after FalloutNV.esm and every
  DLC, which the overnight builds already make.
- Its namespace is New Vegas's (the master chain roots at FalloutNV.esm), so
  its scripts convert as `FALLOUTNV_*` beside FNV's with today's code.
- What this spike added carries over, because TTW's meshes are Fallout 3's:
  convex-list collision and the FO3 creature rules (keyed by skeleton
  folder, which TTW keeps).

**What will cost work:**

- Scale: about Fallout3.esm plus its DLC (Fallout3.esm alone exports
  808,699 records against FalloutNV.esm's 542,016), in one mod build.
- TTW's own scripts: the travel between the wastelands, its start chooser,
  DLC compatibility, all leaning on NVSE and JIP functions; the
  [NVSE language support](nvse_script_language.md) covers part of them.
- No shared saves with a standalone Fallout 3 build: TTW renumbers FO3's
  records, so a TTW conversion and this one are two different plugins.
  EditorIDs survive, so replacement entries keyed by EditorID still apply.
- The opening: TTW starts both games from its own quests, not `CG00` or
  `VCG00` directly, so `new_game.START` would need TTW's start quest.

**First step when TTW is available:** export it with `--import-mod`, run
`fo3_skeletons`-style and record censuses against this doc's tables, then a
scoped build of Vault 101 from it, as here.

## <a id="next"></a>Next

1. Play the spike: a new game from the main menu, through the birth, Baby
   Steps, the birthday, the G.O.A.T. and the escape to the vault door
   ([what only play can check](#opening)).
2. The whole Capital Wasteland: `--world Wasteland --whole` and the
   reached worldspaces, as FNV's [whole map](fo4_pipeline.md#whole-map).
3. Fallout 3's five DLC, as FNV's ([plugin layout](fo4_plugin_layout.md#dlc)).
4. Mart's Mutant Mod, an FO3 mod build on the built Fallout3.esm
   ([mod builds](fo4_mod_builds.md)).
5. Tale of Two Wastelands once it is installed ([above](#ttw)).
