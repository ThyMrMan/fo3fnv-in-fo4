# FNV creatures in Fallout 4: field audit (2026-10-27)

Every piece of data FNV gives a placed creature, followed through the export
and each converter path into Fallout 4, against FalloutNV.esm, the export,
the whole-map build of 2026-10-26 and Fallout4.esm. Started after three
dropped fields broke the nightstalkers in one day
([template actors](fo4_pipeline.md#template-actors),
[script abilities](fo4_perks.md#script-abilities)).

**Marks.** **V**: re-measured in this audit with a second script, or the code
line read. **R**: reported from a code trace or census, not re-measured.
Counts are FalloutNV.esm's unless marked as the build's.

## Contents

- [How the two games place creatures](#placement)
- [The four converter paths](#paths)
- [Findings, by effect in game](#findings)
- [Lost in the export](#export)
- [Fixed this audit](#fixed)
- [The leftover check](#leftover-check)
- [Not measured](#open)

## <a id="placement"></a>How the two games place creatures

**FNV.** A placed creature is an ACRE (2,999) on a CREA (1,578) or, through
the CREA's template, a leveled creature list LVLC (343). A templated CREA
(1,150) takes each part its ten template flags name (Traits, Stats,
Factions, Actor Effect List, AI Data, AI Packages, Model/Animation, Base
Data, Inventory, Script) from the template and keeps its own for the rest. A
list "chance none" is a void entry: `CRVoid` or `VCrILikeOblivionChancedSpawns`,
whose `OblivionSpawnTestScript` kills and destroys itself on load; LVLD
ChanceNone is 0 in all 343 lists. Difficulty comes from the ref's level
modifier (XLCM, 119 refs) and encounter zones (cell XEZN 84, ref XEZN 11).

**Fallout 4.** Everything is an NPC_ placed by an ACHR. A template actor has
thirteen template slots: FNV's ten plus Def Pack List, Attack Data and
Keywords. Vanilla creature template actors set Attack Data on 435 of 444,
Def Pack List on 418 and Keywords on 239, and never Model/Animation. Vanilla
puts XLCM on 2,389 of 2,957 placed creatures and gives 59% of them an
encounter zone, mostly through location-linked ECZN records (271 of 276).

## <a id="paths"></a>The four converter paths

| Path | Code | FNV records (placed refs) |
|---|---|---|
| P1 plain base: a copy of the folder's stand-in, mode `fnv`/`stats`/`item`/`rig` | `creatures.Creatures.base` | 385 (R) |
| P2 template actor: a creature whose traits are templated | `npcs.Npcs._templated`, `with_template` | 1,007, 2,208 refs (R) |
| P3 leveled list | `npcs.Npcs._list` | 343 LVLC; 181 LVLN built |
| P4 placed ref | `npcs.Npcs.placed`, `_actor`, `placement.py` | 2,999 ACRE |

A P2 creature with no rule for its own folder (543, 1,883 refs, R) is a
clone of Doc Weathers, the human male body, so anything of his the template
does not override stays on the creature.

## <a id="findings"></a>Findings, by effect in game

1. <a id="void"></a>**Leveled lists always spawn (V).** `_list` drops entries that do not
   convert, and the void creatures have no FO4 base, so their entries go:
   109 built lists lost exactly their void entries (237 entries). FNV's
   chance of nothing (half of `VEncTier1FeralGhoulMed50`) became a spawn
   every time; about 1,157 refs reach these lists (R). Fix: a void entry
   is FO4's LVLD chance none for that share, or a list entry of a
   disabled-on-load actor.
2. **No creature spawned from a list or template runs its script (V).** All
   3,253 `FNV_` NPC_ records in the build lack VMAD: every clone drops it
   (`STAND_IN_TIES`, `DOGMEAT_TIES`, `BODY_TIES`), and a script is attached
   only to an ACHR whose own base names one. Lost on leveled spawns:
   `vGlowingOneSCRIPT` (11 glowing-one records: regeneration and the
   radiation aura), `CrNightkinSCRIPT`, `StasisProtectronSCRIPT`,
   `NVCrGiantMantisScript` (R). Fix: the script on the base NPC_, where
   vanilla's 79 scripted creature NPCs carry it.
3. <a id="unique"></a>**Almost every FNV actor is Unique (V).** FNV has no Unique flag, and
   `actor_data.acbs` keeps every body flag outside the few it converts, so
   the clone's Unique (Doc Weathers' ACBS is 0x820) stays: 798 of 868
   template actors and 2,299 of 2,385 plain `FNV_` NPCs, against 696 of
   3,015 vanilla NPCs. Effect in game not measured (respawn, leveled
   actors, aliases). Also kept from bodies: Dogmeat's 0xB2 on FNV dogs,
   Auto-calc stats (0x10) on mole rat, brahmin and radroach stand-ins (R).
4. <a id="template-slots"></a>**Template actors never use FO4's last three slots (V, code).**
   `TEMPLATE_PARTS = 0x3FF` (`npcs.py`) covers FNV's ten bits only, so
   Keywords, Attack Data and Def Pack List come from the clone:
   - Keywords: P2 creatures get no `FNV_CreatureType*` keyword (no
     `_keywords` call in `own_parts(templated=True)`), so converted
     `GetIsCreatureType` tests fail on 1,007 records (R); Doc Weathers'
     `AnimArchetypeFriendly` and `AnimFaceArchetypeSarcastic` sit on 301
     creatures in the build (R).
   - Attack Data: the base creature's tuned list (`creature_attacks`) is not
     inherited; attacks come from the race the template gives.
   - Def Pack List: 331 of 356 creature template actors have neither DPLT
     nor the slot; vanilla has DPLT on 440 of 444 (R).
5. <a id="inventory"></a>**Creature inventories are not converted (V, code).** `creatures.py`
   never reads `Item[i]` (484 creatures carry items: leveled loot, weapons,
   ammo). The stand-in's own inventory and outfit stay instead
   (`MoleraVariantsOutfit` on the rig nightstalker and gecko,
   `FeralGhoulOutfit`, `SuperMutantOutfit`; P2 clones keep
   `WastelandDoctorOutfit` on 25) (R).
6. **Placed-ref data dropped (R).** XSCL scale (56 refs; `pack_achr` has no
   scale), the No AI Acquire flag (10), linked refs and enable parents that
   point at an actor (51 and 29: `ids` holds only REFR and PGRE, so an
   enable parent becomes a fixed start state), and the ref EditorID (702).
7. <a id="own-size"></a>**A templated creature with its own stats loses speed and size (R).**
   `own_parts` writes Health, S.P.E.C.I.A.L. and damage only: 87 records
   with their own SpeedMult (bark scorpions 250, fire geckos 75) and 75 with
   their own base scale (`VCrUniqueTier5NightStalkerLargeNRPers` 1.5)
   lose them. SpeedMult is an FO4 Stats field and can be written; height
   is a Traits field in FO4, so it comes from the template.
8. <a id="base-data"></a>**P1 reads three parts through the wrong template chain (R).** The death
   item through Inventory (FNV: Traits, 23 records differ), Essential and
   Respawn through Stats (FNV: Base Data, 18 differ), base scale through
   Traits (FNV: Stats, no difference today). The NPC path splits them
   right (`npcs._actor_data`).
9. **FNV flags FO4 has at the same bit are dropped (R).** Invulnerable
   (bit 31, 10 records: Mr. House, Yes Man, ARCHIMEDES, the camp
   securitrons) and Is Ghost (bit 29). With no direct FO4 flag: No Low
   Level Processing, Can't Open Doors (563), Allow PC Dialogue (170),
   Immobile (50), No Knockdowns (7).
10. **Stand-in leftovers (R).** Stats and rig stand-ins keep their perks
    (PRKZ/PRKR); 71 creature template actors keep the human Citizen class
    where Stats is off. The combat override list (ECOR) the stand-ins keep is
    not one: every one names FO4's generic `DefaultCombatMasterPackageList`
    and FNV has none (V, 2026-10-27). Now counted by the
    [leftover check](#leftover-check).
11. **Dropped everywhere (R):** attack reach (RNAM), turning speed, foot
    weight, AI mood (39), disposition, fatigue.
12. **Suspected (R):** P2's health correction subtracts the clone's race
    health (HumanRace on Doc Weathers clones), not the template's race,
    on 238 records with their own stats.

## <a id="export"></a>Lost in the export (V)

The exporter never dumps these, so no converter path can see them (counts
re-measured on FalloutNV.esm; the same gaps on NPC_/ACHR):

| Record | Field | Count | Matters for |
|---|---|---|---|
| CREA | DATA combat, magic, stealth skill (bytes 1-3; DATA is 17 bytes, the shared ≥20 guard skips it) | 1,578, all non-zero | hit chance and damage |
| CREA | EITM unarmed attack effect | 217 | glowing-one radiation, poison bites |
| CREA | EAMT unarmed attack animation | 198 non-default | attack choice |
| CREA | PNAM body part data | 1,578 (43 BPTD) | dismemberment, limbs, VATS |
| CREA | DEST destructible | 55 | turrets, robots |
| CREA | LNAM melee weapon list, CNAM impact data, NAM4 impact material, NAM5 sound level | 475, 793, 1,578, 24 | impacts, weapons |
| ACRE | XLCM level modifier | 119 | difficulty |
| ACRE | XRGD / XRGB ragdoll pose | 109 / 14 | placed corpses' poses (since 2026-11-01 read from FalloutNV.esm: [dead-at-start poses](fo4_spikes.md#spike-4-creatures)) |
| ACRE | XEZN encounter zone | 11 | level range |
| ACRE | XMRC merchant container | 1 | the Vendortron |

LVLC loses nothing. No struct field the export does dump is misread (ACBS,
AIDT, DATA, sound types and LVLO offsets match xEdit's).

## <a id="fixed"></a>Fixed this audit

Template actors drop the clone's attack race; templated creatures keep
their own AI packages ([template actors](fo4_pipeline.md#template-actors));
a script's ability property converts ([script abilities](fo4_perks.md#script-abilities)).
All played 2026-10-27.

**Built and played 2026-10-27** (F3NV Rig Test, Jacobstown region: the
nightstalkers cloak from their base's script, gecko and bighorner spawns
sometimes come up empty as in FNV):

- **Void entries** (finding 1): every void creature is one FO4 actor
  (`spike/void_actors.py`): a copy of the mole rat on `FNV_VoidRace` (a
  `MoleratRace` copy) in an empty skin, no factions, packages, items or
  aggression, running `F3NV_VoidActor`, which disables and deletes it on
  load. Neither Skyrim (0 of 527 lists) nor Fallout 4 gives a placed actor's
  list a partial chance none, so FNV's own way is kept. A template actor
  whose list can draw it and which runs its own script (no Use Script) also
  runs the check, by race: a leveled actor's base is a generated record, but
  its race is the drawn entry's. Region build: 6 lists hold the void actor;
  their template actors take scripts from the list (flags 991), so none
  needs the check there.
- **Scripts on bases** (finding 2): an NPC's or creature's FNV script is its
  base NPC_'s VMAD (its script chain's on a plain base, its own on a template
  actor without Use Script), as FNV keeps it on the base; an ACHR carries one
  only when its base is a vanilla record (`item` mode). Region build: the
  Jacobstown nightstalker script moved from 10 ACHRs to its base.
- **Unique** (finding 3): `actor_data.acbs` and `with_template` clear the
  clone's Unique flag. Region build: 24 of 41 `FNV_` NPCs Unique before, 15
  after, all copies of vanilla's holotape speaker (`holotapes.speaker_npc`),
  which keep vanilla's flags.

**Built and played 2026-10-27** (F3NV Rig Test: nightstalkers, geckos and
bighorners attack and behave normally):

- **Template slots** (finding 4, `npcs._template_flags`): a template actor
  taking Traits also takes Attack Data and Def Pack List (FNV keeps attacks
  and creature type under Traits; vanilla sets them on 435 and 418 of 444
  creature template actors), and Keywords, except a creature whose traits
  come from another creature: 81 such creatures (37 refs) play their own
  sound set, which their keywords carry, so they keep their own keywords:
  the clone's, without a human body's (`without_keywords`), plus their
  traits' type keyword (`Creatures.own_parts`). A list template actor takes
  all thirteen. `type_tests.keywords_edit` now gives a record without
  keywords a KSIZ/KWDA after its last AIDT/PKID (it added nothing before;
  `creature_sounds.with_keyword` had its own copy). Region build: 18
  template actors; Doc Weathers' `AnimArchetypeFriendly` and
  `AnimFaceArchetypeSarcastic` on 8 before, 0 after; the 10 on creatures
  carry their type keyword beside their sound keyword.

**Built and played 2026-10-27** (F3NV Rig Test: creatures drop FNV loot,
super mutants use FNV weapons, everything fights normally):

- **Inventories** (finding 5, `Creatures.inventory`): a creature carries the
  items of its Inventory chain that convert, except its attack gear: FNV's
  non-playable or embedded weapons and non-playable ammo (`EyeBot1HP` 0xA8,
  `Ammo5mmRobot` 0x2), which the stand-in's own gear replaces. Of the
  stand-in's items only that gear stays: Fallout4.esm marks every stand-in
  attack weapon, ammo and shield Non-Playable (record flag 0x4:
  `WeapEyebot`, `DeathclawDirtThrow`, `MirelurkShield`), and none of its
  loot lists (`LLI_Supermutant_*`, `LL_*`). The stand-in's default outfit
  stays only in `stats` mode, whose point is FO4's look; own-mesh and
  own-rig creatures and human-body clones drop it. `npcs.with_inventory`
  puts items before AIDT on a body without any (the mole rat). Region
  build: 24 of 42 `FNV_` NPCs changed: 8 list spawns lost Doc Weathers'
  outfit and `LLG_Pistol_Auto`; 11 geckos and nightstalkers lost
  `MoleraVariantsOutfit`; bighorners carry their meat; super mutants carry
  FNV's weapons and loot lists in place of FO4's, and the Jacobstown
  nightkin its quest item `VMS41ChewedStealthBoy`; 15 items kept, 16 left
  out as gear.

**Built 2026-10-27, not played** (scratch builds of three interiors):

- **Placed actors** (finding 6, `Npcs.placed`, `_actor`, `records.pack_achr`):
  `placed` resolves every actor's base and FormID before writing any, so a
  linked ref (XLKR) or enable parent (XESP) naming an actor placed later
  resolves instead of being dropped (an enable parent was frozen into a
  start state); ACHR FormIDs are hashed from the same keys, so none moves.
  FNV's No AI Acquire flag (0x2000000, FO4's same ACHR bit) and scale (XSCL,
  before DATA as xEdit orders it) carry over. Scratch builds:
  `Lucky38BasementFloorB2` 9 of 9 No AI Acquire; `Vault34a` 3 of 3 scales
  and 2 of 2 actor links; `Vault22c` 5 of 5 actor enable parents (2 scaled
  Lucky 38 actors have no FO4 base yet). Rig Test region: its 54 ACHRs keep
  their FormIDs and have none of these.
- **Own speed and size** (finding 7, and finding 8's base scale; played
  2026-10-27 in F3NV Rig Test: small and medium fire geckos and bighorners
  look and move right): a creature's
  base scale is read through its Stats chain, where FNV keeps it
  (`Creatures._base_scale`; no base creature changes). A template actor with
  its own Stats gets its own SpeedMult (`Creatures._own_speed`): FNV's run at
  its own size on its traits creature's stand-in, FNV's SpeedMult itself on a
  rig. FO4 keeps height under Traits, so one whose own scale differs from its
  traits creature's takes Traits from a copy of that creature's base built at
  its scale (`Creatures.traits_variant`, `base(..., stats)`, kept apart from
  `made`); its Traits slot names the copy while TPLT names the template, as
  653 vanilla template actors name another Traits template. FNV: 93 such
  creatures by scale (52 refs, 23 in lists), 50 by speed. Region build: 9
  template actors had SpeedMult 100, now FNV's (fire geckos 75, small ones
  65; the super mutant 158.5, as its template's from the same FNV stats); 4
  `...Traits` copies (small fire geckos at 1.0 where they took the big
  gecko's 1.5, the small bighorner at 0.72 of the bighorner's 1.35).

**Built 2026-10-27, not played:**

- **Base Data and death item chains, Invulnerable and Is Ghost** (findings 8
  and 9): a plain copy takes Essential, Respawn, Is Ghost and Invulnerable
  through its Base Data chain and PC Level Mult and its level band through
  Stats (`Creatures._actor_data`, as `Npcs._actor_data` already did), and its
  death item through Traits (`own_parts`; a template actor drops its own,
  which Traits from the template replaces). FNV's creature Is Ghost and
  Invulnerable are bits 29 and 31 (xEdit's FNV list repeats bit 27, shifting
  its names; the data shows it: Mr. House, Yes Man, the camp securitrons on
  31; tumbleweeds, Festus, the Vendortron on 29), FO4's same bits, now kept
  (`actor_data.CREATURE_FLAGS`). FNV-wide, of 385 plain copies: 19 change
  flags (the Quarry Junction deathclaws and Shakes lose a Respawn their Stats
  template gave; the Strip and Vault 21 securitrons gain theirs; the
  Vendortron is Is Ghost and Invulnerable), 23 change death item (large and
  small mole rats, small mantises, bark scorpions now drop their own). Rig
  Test region: 5 of 46 `FNV_` NPCs changed, all template actors dropping
  their own death item.

<a id="ghouls"></a>**Ghouls and glowing ones, built and played 2026-10-27** (Vault 34b in Rig Test;
scratch build; FNV has 71 ghoul creatures, 21 with a script, none with an
unarmed attack effect):

- The glow: FNV marks a glowing one with the ability
  `GlowingOneGlowSpell` (31 creatures, 14 owning their look). The rule
  `_rules.ability` sends those 14 to FO4's `encFeralGhoulGlowing01`
  ([ability rules](fo4_gui.md#ability-rules)): `FeralGhoulGlowingRace`, its
  glowing skin, its `crGlowingOneCloak` radiation aura, `crGlowingOneBurst`
  and the `crGlowingOne` perk. Their template actors follow. Before, every
  ghoul was the plain feral.
- Script-effect abilities (the glow, the reaver glow `DLC03ReaverGlowSpell`
  on 7, ED-E's `EDERadioBroadcast` on 3) were left out; `Perks.ability`
  now hands them to `script_effects`. The glow scripts play an FNV effect
  shader (`GlowingOneFXShader`, `DLC03GhoulFXShader`) and the build
  converts no EFSH, so those properties were empty (one Papyrus error per
  spawn) and reavers did not glow. Since 2026-11-01 every script
  `EffectShader` property gets a Fallout4.esm shader
  ([effect shaders](script_markers.md#effect-shaders), via
  [creatures](fo4_spikes.md#spike-4-creatures)).
- `GhoulRadHeal` (all 71: heal 10 a second while Rad Level > 1, remove 100
  rads a second while above 0) was written empty: its conditions test
  `GetRadiationLevel`, which FO4 lacks. It is now `GetValue Rads`
  (`conditions.AS_VALUE`; the only FNV record using it). Its remove-rads
  effect is a non-detrimental value modifier on Rads, the kind FO4's own
  RadAway (`RestoreRadsChem`) is.
- `vGlowingOneSCRIPT` (19: regeneration, the radiation aura explosion
  every 3 seconds) is on the base NPC since the [scripts fix](#findings);
  on the glowing stand-in it runs beside FO4's own aura.
- Vault 34b: the four glowing Vault 34 records and `GhoulRadHeal` change,
  nothing else; Rig Test is byte-identical.

<a id="talking-machines"></a>**FNV's talking machines (mode `speaker`, built 2026-10-27; played in the
Lucky 38 penthouse: the screen and console stand, no protectron, activating
them opens Mr. House's dialogue; the screen showed no image, fix built
2026-11-02, not played).**
Mr. House's screen (`MrHouse`, 365 dialogue lines by GetIsID; `MrHouseOFFLINE`
and `NVCRPenthousemaincomputer` share its model), Yes Man's mainframe (134),
Festus (91) and Mr. House's pod (`NVCRMrHouse`, 10) are FNV creatures with
no ragdoll, two to seven body parts, and screens that are rigid shapes
animated by their own controllers (alpha, texture transform, transform,
emittance: `nvdefaultscreen.nif`, `nvhousecomputerscreen.nif`; the pod's
beating `nvmrhouse_heart.nif`); frames, House's body and Festus are skinned.
None converted, so none of their lines could play. An own rig keeps only
skinned shapes and needs a ragdoll, so `talking_machines` makes each an
unseen speaker plus its look: the NPC copy as `stats` writes it, on
`FNV_SpeakerRace` (`ProtectronRace`, which allows player dialogue and has no
FaceGen head, with an addon-less skin and Immobile, `void_actors.invisible_race`
shared with the void actor; the copy also loses its object template block,
OBTE ... STOP, `records.without_object_templates`: FO4 builds robots from
template parts attached apart from the skin, so with only the skin emptied
a protectron still stood in Mr. House's console, played 2026-10-27), and each FNV part as a static, placed with the
speaker and enable-parented to it (Lucky 38 swaps online and offline screens
by enabling one and disabling the other). In FNV the screen is the actor, so
it is what the player activates to talk; each look is an activator named as
the machine (prompt Talk) whose reference script `F3NV_SpeakerLook`
activates its speaker, which starts FO4's conversation. Where they stand:
`Lucky38MrHouseREF` and `YesManMainframeREF` (the penthouse screen that
greets the player) in the worldspace `Lucky38World`, cell (-1, 1); the
basement's two only speak through the securitron upgrade terminal's script
(Mr. House's quest at stage 25, Yes Man's at 75; played 2026-10-27: no
lines there otherwise, as in FNV); the pod in `Lucky38ControlRoom`; Festus
in `SSHQ01`. A rigid part names its parent bone
in a `Prn` string extra data (the heart `Bip01 Heart`, the helmet `Bip01
Helmet`, the screen `Bip01 Yaw`), and FNV attaches the part's root there;
none of those root names (`HeartRoot`, `HelmtlRoot`) is a skeleton node, so
the part is converted with its root posed at the `Prn` bone's world
transform (`convert_static.posed`: the pose's `ATTACH` entry moves the
root's children; a pose naming the root by name, as a weapon's hold
animation does with a translation only, moves just the root). Checked by bounds: the heart, helmet and stomach pump sit
inside Mr. House at chest and head height. A part a record lists with no
file (`MrHouseOFFLINE`'s `NVPentHouseMainComputer_HouseScreen.NIF`) is
left out, counted. Lost: the skinned parts' idle and talking motion, and
the screens' animation: their controllers sit on nodes and properties with
no controller manager, which the static conversion keeps only under one.
In game the penthouse screen showed no image at all (its face layers are
effect shapes whose alpha and texture controllers set what shows). Those
controllers are now kept, and the layers blend
([free controllers](fo4_pipeline.md#free-controllers), built 2026-11-02, not
yet played).

## <a id="leftover-check"></a>The leftover check

Most of this audit's bugs are one kind: a converted creature is a copy of a
Fallout 4 NPC (its stand-in, or the male body under a template actor), and a
field nothing overwrites keeps the stand-in's value (the mole rat attack
race, Unique, outfits, Doc Weathers' keywords). `stand_in_fields.FIELDS` marks
every NPC_ subrecord a stand-in carries, and every copy is checked as it is
written (`checked`, in the three `Creatures` writers and
`Npcs._template_actor`):

| Mark | Fields | Why |
|---|---|---|
| keep | EDID, FULL, ACBS, TPLT, TPTA | written for every copy |
| keep | RNAM, WNAM, ANAM, OBND, heights (NAM4-6), MWGT, NAM8, DNAM, face (FTST, HCLF, BCLF, PNAM, MSDK, MSDV, MRSV, FMRI, FMRS, TETI, TEND, NTRM, QNAM), APPR, object templates (OBTE-STOP), DATA | the stand-in's body and engine data |
| keep | ATKR and the attack list | the attack list is rebuilt on the stand-in's attack race (`_attacks`); template actors drop ATKR |
| keep | VTCK, CSCR, DOFT, SOFT | FNV's voice, sounds and (rig) outfit replace them when FNV has its own (SOFT: the glowing one's sleep outfit) |
| keep | DPLT, ECOR | every stand-in names FO4's generic `DefaultMasterPackageList` and `DefaultCombatMasterPackageList` (Dogmeat's own override is dropped with him); FNV has neither |
| keep | KSIZ, KWDA | the stand-in's type keywords (NoStagger, ImmuneParalysis, HeavyKnocker); FNV's type keyword is added |
| fnv | AIDT, SNAM, PKID, ZNAM, INAM, CNTO, COCT, PRPS | written from FNV; the stand-in's value surviving whole is a leftover |
| drop | VMAD, CRIF, SHRT, LTPT, LTPC | the stand-in's scripts, crime faction, short name, and legendary template and chance (FO4's feral ghouls; FNV has no legendaries) |
| open | SPCT, SPLO, PRKZ, PRKR, CNAM | not decided: the stand-in's type abilities (the glowing one's `crGlowingOneCloak` aura and `crGlowingOneBurst`; FNV's are added beside them), immunity perks (ImmuneToRadiation, ImmuneToPoison, crNoFallDamage) next to FO4 damage tuning (crDamage15 on protectrons, crDamage125 on super mutants, crRangedDmgPerk), and the stand-in's class (BoSScribeClass on super mutants, the human Citizen class on template actors) |

Known case: a stand-in whose whole inventory is its attack gear (the
deathclaw's `AmmoDeathclawThrow` and `DeathclawDirtThrow`, kept on purpose
by `Creatures.inventory`) counts as `fnv CNTO`/`COCT` on an FNV creature
carrying nothing. A field with no mark stops the build (ValueError naming the creature), so a
new stand-in or body brings its new fields to a decision. A fnv, drop or open
field that survives is counted in the build output as
`stand-in leftover <mark> <tag>`. A field whose template slot a template
actor takes from its template is skipped. Slots are assigned where the
converter already reads them: combat style counts as Traits or AI Data,
perks as Spells, class as Stats.

## <a id="open"></a>Not measured

1,033 FNV creatures have no same-named NPC_ in the build (unplaced, or
reached only through lists that drop them); what Unique does to a respawning
or leveled actor; whether FO4 takes attacks or package lists from a template
without its slot; robot and super mutant refs.
