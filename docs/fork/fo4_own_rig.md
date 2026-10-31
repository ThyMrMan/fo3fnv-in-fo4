# FNV creatures on their own rig (design)

A fourth creature mode beside `fnv`, `stats` and `item`
([fo4_replacements.md](fo4_replacements.md)): the FNV creature keeps its own
skeleton, body, clips and behaviour, written as Fallout 4 files, on a race
copied from a vanilla template. The gecko is the first and only one played
([fo4_spikes.md#own-rigs](fo4_spikes.md#own-rigs), tests 18–51). Everything
the played gecko needed, and why, is in
[fo4_spikes.md#own-rig-ragdoll](fo4_spikes.md#own-rig-ragdoll) and the
notes before it.

## <a id="stages"></a>Stages

1. **Havok 2014 files** (done): `fo4_import/havok/packfile.py`,
   `packfile_write.py`, `graph.py`
   ([fo4_spikes.md#own-rig-code](fo4_spikes.md#own-rig-code)).
2. **The gecko through a rig table**, as mode `rig` in `creatures.py`.
3. More creatures: each a table entry plus whatever its body plan needs.

## <a id="table"></a>The rig table

`fo4_import/data/creature_rigs.json`, keyed by FNV skeleton folder
(`creatures\\nvgecko`). An entry names what FNV's files cannot say:

| Key | Gecko | Use |
|---|---|---|
| `project` | `FNVGecko` | file and folder names (`Actors\FNVGecko\…`), MOVT `MNAM`, `iState_<project>` |
| `template` | `MoleratRace` etc. | the vanilla race, body parts, skin, movement type and NPC copied |
| `clips` | `Idle: mtidle.kf`, … | FO4 clip role → FNV `.kf` (roles: Idle, TurnLeft, TurnRight, WalkForward, RunForward, CombatIdle, attacks) |
| `attacks` | `AttackLeft: meleeStart_Left`, … | attack clip → melee event, power or not, label |
| `parts` | `Pelvis: Bip01 Pelvis`, … | template body-part node → our bone |
| `pose_bones` | `Bip01 Pelvis`, `Bip01 Spine4`, `Bip01 R UpperArm` | the pose matcher's ragdoll bones, in the template's roles (pelvis, chest, upper arm) |

The mode's entry in `replacements.json` reads
`{"use": "Fallout4.esm|EncMolerat01Template", "as": "rig"}`: the NPC to copy,
as `stats` does; the race comes from the rig table.

## <a id="modules"></a>Modules

- `fo4_import/rig/assets.py`: `skeleton.hkx` (animation skeleton only,
  `anim_fo4`), clips with root motion (`kf_decode` → `anim_fo4`, motion
  patched with `packfile`), `skeleton.nif` (FNV's ragdoll through Elric, plus
  `CharacterController`/`CharacterBumper` phantoms, BSXFlags 0xC6, `BSBound`),
  the skinned body and its materials.
- `fo4_import/rig/behavior.py`: the root graph (creature states inline,
  `RagdollAndGetUp` on a pose matcher, the `DeathAnimation` step), character
  and project from the template's files in the game archives.
- `fo4_import/rig/records.py`: RACE, BPTD, ARMO/ARMA, MOVT (the form
  version's `SPED` layout) and the action IDLEs, on the template's records.
- `fo4_import/rig/anim_text.py`: AnimTextData's text files (project file
  data, the entry's file data by the CRC rule, dynamic idle data). The
  Creation Kit's binary speed and stance data is not written; whether a
  creature needs it is settled by a play test.
- `creatures.py`: mode `rig` calls these once per skeleton folder and writes
  the NPC as `stats` does, on the rig's race.

### <a id="body-parts"></a>Body part names (V.A.T.S.)

A rig's BPTD is the template race's on the creature's bones (the table's
`parts`). V.A.T.S. shows each part's name (BPTN), and until 2026-10-31 that
name was the bone's (`Bip01 Head`): the template's is a Fallout4.esm string
ID. Now each part takes the name of FNV's part covering its bone: FNV's
BPTD on the rig's skeleton folder (its MODL) names each part (BPTN) and the
node it starts at (BPNN), and a part covers that node's subtree, so the
bone and its ancestors are searched nearest first (`part_name`; the gecko's
Head sits on `Bip01 Neck1`). A bone no FNV part covers (Root, a pelvis
above FNV's parts, all of the raven's and spore carrier's) takes the
template's own name through Fallout4.esm's strings.

## <a id="anim-info"></a>AnimTextData from the Creation Kit

The game reads a race's graphs through AnimTextData, mostly binary files
the Creation Kit writes (`-GenerateAnimInfo:<plugin> <data> <output>
[--speed] [--stance] [--forceAll]`): animation offsets, speed info, stance
data, clip generator data, event info, file data, dynamic idle data and the
persistent subgraph list. The played gecko had them all. So the build runs
the CK (`fo4_import/rig/anim_info.py`) after the plugin is written, when it
made an own-rig creature, the way FaceGen runs it
(`fo4_import/pipeline/creation_kit.py`): through MO2, so the CK loads the
profile's plugins. MO2 sends the files the CK creates to the selected
profile's custom overwrite for the Creation Kit, else to `overwrite`
(`creation_kit.output_dir`), and the CK edits an existing file in place,
so last run's files (listed in `<plugin>.animinfo.txt`) are deleted first
and the new ones moved into the mod folder. *Deleting them from the build's
folder is not enough once the build is deployed (found 2026-10-31):* the
deployed MO2 mod holds the same files, the CK edits those in place, and
nothing reached `overwrite`: two rebuilds collected 0 files, the build's
folder lost its 17,892, the list came back empty, so the skip never held
and the CK ran on every build (233 s). The files dated from the run's start
are now collected from `overwrite` (moved) and from every enabled mod
(copied, so the deployed copy stays): `creation_kit.written_since`. The CK also edits
`CreationKitPrefs.ini`, `ckpe.log` and the `Logs` folders in the game
folder in place.

## <a id="nightstalker"></a>Second creature: the nightstalker (2026-10-27)

A table entry only, to check the gecko's code holds for another ground
biter. The nightstalker shares 14 of its 53 bones with the gecko (its back
legs are `Bip01LCalf…`, its front legs `Bip01LUpperArm…`, with a five-bone
tail, a seven-bone spine and a five-bone neck). It has every clip role the
gecko uses (FNV spells its walks `mtfoward.kf` and `mtfastfoward.kf`), with
footfall, hit and `Enum: Auxiliary` sound keys, and one body NIF. Its
ragdoll covers pelvis, spine 1 and 4, neck, head, the legs and the tail,
so the pose bones are `Bip01 Pelvis`, `Bip01 Spine4` (the top spine body)
and `Bip01RUpperArm`. Template: the mole rat's, as the gecko's. Its 38
FNV creatures are placed in caves (Jacobstown, Sulfur caves, Vault 19,
the sewers).

## <a id="mantis"></a>Third creature: the giant mantis (played 2026-10-27)

A table entry only, on the mole rat template as the gecko and nightstalker
(it was a `stats` copy of the stingwing, so it had the stingwing's body).
It has every clip role the gecko uses (`locomotion\mtforward.kf`,
`mtfastforward.kf`). Its 41 bones are an insect's: `Bip01 Root` (the
pelvis role), `Thorax00`/`Thorax01`, neck, head with antennae, the
raptorial arms `LeftArm00-02`/`RightArm00-02` (the template's front legs),
four walking legs `Front/Back Left/Right Leg00-03` (the back pair the
template's back legs), the abdomen `Gaster00-01` and four wing bones. Its
ragdoll has 25 bodies; pose bones `Bip01 Root`, `Bip01 Thorax00`, `Bip01
RightArm00`. Checked before play against every rule the gecko's tests
found: the pose bones are in the written ragdoll (0, 2, 9), the graph
carries only `iState_FNVMantis`, the four `meleeStart_*` events and
`attackStop`, and the movement type is the 28-float layout (walk 44.9,
run 279.8, sprint 489.6 from the FNV clips' root speeds).

## <a id="cazador"></a>Fourth creature: the cazador (played 2026-10-27: moves, attacks, its poison and FNV's woozy screen effect land)

A table entry, on the mole rat template; it had no rule, so no cazador
converted. FNV's cazador, like FO4's flying insects, is a ground actor whose
clips hold the body in the air, so the mole rat's movement type carries it.
It has the gecko's clip roles (`locomotion\mtforward.kf`,
`mtfastforward.kf`; `h2h*` attacks). Its 62 bones hang from `Bip01 Root`
(the thorax: the pelvis role): six legs `Front/Mid/Back Left/Right
Leg01-04` (front as the template's front legs, back as its back legs), the
neck and head (with antennae and mandibles), a four-bone tail ending in
`Bip01 Stinger` (the spine roles), four wings. Its ragdoll has 42 bodies;
pose bones `Bip01 Root`, `Bip01 Neck`, `Bip01 FrontRightLeg01`.

**Attack spells on an own rig.** A rig's race lists its attacks with no
spell, so FNV's unarmed attack effect (the cazador's `CazadorPoison`, the
nightstalker's `NightstalkerPoison`, the golden gecko's radiation) never
landed. A rig creature with one now gets its own attack list, as a stand-in
copy does: ATKR its race, the race's attacks at its combat style's
power-attack share, each casting its spell (`Rigs.attacks`,
`creature_attacks.with_spell`; [attack spells](fo4_pipeline.md#attack-spells)).

## <a id="remaining"></a>The remaining creatures (built 2026-10-27, not played)

Every FNV creature folder with no rule, decided by body plan and attack:

| Folder | Mode | Why | Pose bones |
|---|---|---|---|
| `nvgiantrat` | rig | the gecko's clip set, a ground biter | `Spine0`, `Spine3`, `R UpperArm` |
| `giantant` | rig | the gecko's clip set; the fire ant's breath (`2hl`, `ProjectileNode_Fire`) is ranged and not carried, so fire ants bite | `Spine`, `Head`, `R UpperArm` |
| `queenant` | rig | three attacks (no forward power); her body hangs off a tail chain under the root | `Spine1`, `Head`, `R Thigh Front` |
| `nvsporecarrier` | rig | a biped; turns in `locomotion\` | `Bip`, `Spine1`, `R UpperArm` |
| `centaur` | rig | power attacks `h2hattackleft/rightpower`; front legs `L/R Thigh`, back legs `L2/R2 Thigh`; its spit is ranged, not carried | `Spine`, `Neck`, `R UpperArm` |
| `nvsporeplant` | rig, immobile | every movement role its idle (root speed 0: `Builder.root_speed`), the melee lash `h2hattackright` only; its spore spit is ranged, not carried | `Spine02`, `Neck02`, `LeafR1 01` |
| `nvraven` | rig, immobile | only `mtidle.kf`; no attacks | `RigPelvis`, `RigTorso`, `RigTail02` |
| `sentryturret`, `minisentryturret` | stats on `EncTurretBubbleLaserTemplate` | FO4's own ceiling/wall turret, its own weapon; the other bubble turrets are template actors on it | |
| `robobrain` | stats on `EncProtectron01Template` | a gun user (the rig is melee only); FO4's robobrain is DLCRobot's | |

Scratch builds of Vault 22e, the Nellis generator, the rat cave, the South
Vegas ant mound, the Securitron vault, a North Vegas house and two centaur
cells: every rig's pose bones are in its written ragdoll, its graph carries
only its own `iState_`, and its movement type is the new layout. Two fixes
on the way: a clip with no root motion (the immobile rigs' idle in every
movement role) has speed 0, and `ragdoll_bones` decodes only
`hknpRagdollData` (the centaur's ragdoll has `hknpSphereShape` bodies,
which the layout table lacks: `packfile.read(only=...)`). Stand-in copies
now drop the stand-in's short name too (SHRT: the turret's and
protectron's, which the leftover check caught).

Not creatures and not converted: the `marker_creature.nif` records (33
Fallout 3 leftovers, none placed in FNV) and FNV's talking machines (Mr.
House's screen 365 lines, Yes Man's mainframe 134, Festus 91, Mr. House's
pod 10: no ragdoll, two to seven body parts).

## <a id="ranged"></a>Ranged attacks (securitron SMG and launcher played 2026-10-28)

**Played:** Victor (Goodsprings) fires his SMG repeatedly, walking or
standing, his gun arm aimed at the target, and fires rockets level from his
left arm.

**One gun per slot, as the robots (played 2026-10-28).** With all of
Victor's guns in the right hand he only ever held the SMG (he chased the
player with it at 1333 units, past its FNV max of 1024): only one gun fits
a slot. FO4's robots never switch guns: each sits
in its own equip slot, all equipped at once, and the AI fires whichever
suits, passing its slot with the fire action. So each securitron gun copies
an FO4 gun in the slot FNV mounts it on: the SMG `SentryBotRightMinigun`
(right hand, 0), the launcher `SentryBotLeftMiniRocketLauncher` and the
laser `Protectron01LeftArmLaserGun` (left hand, 1: FNV's
`ProjectileNode_Launcher` and `_GatlingLaser` are both under `Bip01 LHand`),
the missile `SentryBotRightShoulderClusterLauncher` (right shoulder, 3:
FNV's `ProjectileNode_Missle` is on `Bip01 Body`).

**Equipping them all (`rig/gun_mods.py`).** Guns in the NPC's inventory
list are not all equipped: FO4 equips the one it rates best, and with the
SMG and launcher in two slots Victor still fired only the SMG (one rocket
in one test, none in the next; played 2026-10-28). A robot's guns come from
its part mods instead: `Bot_HandLeftProtectronClaw_Lasergun01` is an actor
object mod (form type `NPC_`) at attach point `ap_Bot_HandLeft` whose one
property, ForcedInventory (value type form, function Add, second value
440), adds `Protectron01LeftArmLaserGun` forced equipped. The bubble
turrets do the same without robot parts: the NPC offers `ap_TurretWep`
(APPR) and its object template's default combination includes
`Bubble_Turret_Ballistic3shot`; the vertibird offers two gun points. So a
rig NPC offers one attach point per equip slot (`FNV_ap_GunSlot<EQUP>`) and
includes one ForcedInventory mod per embedded gun copy (`FNV_mod_Gun<FNV
FormID>`), the guns left out of its inventory list (their ammo stays). Our
combination and mod DATA match the turret's byte for byte. FO4's WEAP
Min/Max Range is damage falloff, not an AI range (CK wiki, Weapon), so FNV's
ranges below change no gun choice.

**Each slot's node (race ZNAM).** A race names the node each equip slot's
gun hangs on in a ZNAM after that slot's QNAM: the robots' `C-HandRight`,
`C-HandLeft` (connect points in their part meshes), the vertibird's
`GunParent_R` and `GunParent_L`. The eyebot names none and has one gun.
With ZNAM dropped, Victor's force-equipped launcher never reached the left
hand: `GetEquippedWeapon` (equip index 0-4, `TraceEquipped`) showed the
SMG in 0 and nothing in 1 (played 2026-10-28). So each gun's slot names its
node: `WEAPON` for slot 0, `WEAPON<slot>` for the others
(`table.weapon_node`), each on the FNV node that gun fires from (the
table's third gun field).

**Range.** FNV's AI picks the gun whose Min/Max Range (WEAP DNAM at 44)
covers the distance to its target: the securitron SMG 128-1024, laser
0-1750, launcher 10-2000, missile 50-1536. An embedded gun copy takes FNV's
range over its FO4 template's (`Equipment._weapon`). FO4 also scales damage
past Max Range; the export drops both fields, so they are read from
FalloutNV.esm (`_fnv_fields`). Human guns keep their FO4 ranges (FO4's
damage falloff balance).

How a Fallout 4 creature fires a built-in gun, from the eyebot, the
turrets, the robots (`Actors\CreateABot`) and the Capital Wasteland
Centaurs mod's spit (a working custom-rig ranged creature):

- **The weapon** is an embedded gun in the creature's inventory, in an
  equip slot its race lists (QNAM), the race's equip types (VNAM) allowing
  Gun (0x200). Every vanilla creature gun has a magazine of 0 (never
  reloads) and none but the turrets' has Charging Attack (0x200, fired
  through `TurretFireCharge` → `attackCharge`). FO4 does not spend a
  creature gun's rounds.
- **The start is an IDLE**: action `ActionFireSingle` (or `ActionFireAuto`
  for an automatic gun) → an IDLE whose DNAM is the creature's root graph.
  The robots hold a root IDLE with no event under the action and one child
  per slot under it, `GetActionDataByte == <slot>` (function 747: the
  firing gun's slot, 0 right arm, 1 left arm, 2 head, 3 right shoulder, 4
  left shoulder, the race's QNAM order), each sending its slot's event.
- **The shot** is the event `weaponFire`, its payload the slot (a robot
  clip's annotation `weaponFire.<slot>`; single-gun creatures use plain
  `weaponFire`).
- **The graph around it**: the firing state raises `AttackState<slot>`
  "Enter"/"Exit" (single-gun creatures `attackState`), and the combat idle
  raises `ReadyState` "Enter". FO4 fires once per `ReadyState`: raised only
  on entering combat, Victor fired once; raised again after each shot, he
  fires steadily. The robots' firing is a layer over their arms
  (`RightArmAttack` and the like, blended with bone weights over combat
  locomotion, idling on that same locomotion), so they aim while walking.

The rig, for a table entry with `guns` (clip role → equip slot):

- **Records** (`records.fire_idles`): for `ActionFireSingle` and
  `ActionFireAuto`, the robots' tree, each gun's child sending
  `rangedAttackStart<slot>`; the race adds Gun to its equip types. The
  securitron's template race is `ProtectronRace` (talking needed it:
  [talk](#talk)), whose QNAM gives the slot numbers.
- **Graph** (`behavior.Builder.arm_layer`): combat locomotion blended with an
  arm machine over its guns' bones' subtrees (every bone without any). The
  arm machine idles on the locomotion itself, raising `ReadyState` "Enter"
  on each return, and enters a gun's state on its `rangedAttackStart<slot>`
  from anywhere: that gun's clip, blended over the locomotion on that gun's
  own bones only, with `weaponFire` (payload the slot) at each FNV `Hit`
  key, `AttackState<slot>` around it, `AttackEnd` 0.2 s before the clip's
  end but after its last shot (`ranged_end`: FNV's `1hpattackleft` is
  0.17 s long). A shot carried as a `weaponFire` annotation in the clip file
  never fired; the graph trigger does. Each clip moves only its own arm
  (the securitron's guns: `Bip01 RShoulder` for the SMG, `Bip01 LShoulder`
  for the launcher and the missile): with the launcher's clip on both arms
  and every shot leaving the right arm, its right arm turned 35-46° per
  joint from the aim and Victor fired one rocket into the ground (played
  2026-10-28). A gun fires no sooner than the blend into its state ends
  (`shots`, `ATTACK_BLEND` 0.1 s): FNV's launcher barrel is level in
  `2hlattackleft` (-1.4° pitch) but 29° down in the combat idle `1hpaim`,
  and its `Hit` key at 0.033 s caught the arm a third of the way up (-17.6°),
  so the rockets hit the ground ahead of him (played 2026-10-28). The SMG's
  barrel is level in both.
- **Skeleton** (`assets.move_weapon`, `add_fire_node`): each gun's node
  (`weapon_node`; FNV's `WEAPON` moved for slot 0, a new node otherwise) sits
  on that gun's FNV fire node, turned so its +Y runs level ahead (model +Y)
  with +Z up in its clip's pose at the first shot, the root unmoved
  (`aim_turn`, `build.gun_nodes`), with `ProjectileNode` under it; FNV's keys
  for `WEAPON` are dropped. FNV takes only the fire node's place and fires
  at its target; FO4 fires along the node. Through the securitron FNV's
  nodes' +X ran down the barrel (6° off level ahead for the SMG), but the
  spore plant's points 84° up at its shot.
- **Inventory** (`Creatures._ammo`, `Equipment._weapon`): FNV's guns on
  table copies of FO4 creature guns (not playable: embedded or not), with
  FNV's count of their ammo (else `ARMED_AMMO`, 100); a creature gun copy
  keeps its template's magazine of 0.
- **Slots** (`records.with_slots`): the table names each gun's equip slot
  by its EQUP EditorID; it becomes the slot's index in the race's QNAM list,
  a slot the template race lacks added after its own (the mole rat's race
  has only RightHand and LeftHand; the mirelurk hunter's spit is MiddleHand).

**Creature guns (played 2026-10-28: fire ants flame, centaurs and spore plants spit, level at the player).** A clip fires on `Hit`
and on `Fire` (an attack loop's start: `SHOT_KEYS`). Each plays over every
bone (no `bones` in the table: the whole attack).

| Rig | FNV weapon | FO4 template | Slot | Clip | Fire node |
|---|---|---|---|---|---|
| `giantant` | fire ant `Flame2HL` (worker, soldier, guard) | `Protectron02RightArmFlamer` | RightHand | `2hlattackspin` (`Fire` at 0.367 s) | `ProjectileNode_Fire` |
| `queenant` | `MS04FireAntQueenFlame2HL`; `QueenAnt2HL` (acid, not placed in FNV) | the flamer; `WeapMirelurkhunter01` | RightHand; MiddleHand | `2hlattackright` | `ProjectileNode_Fire` |
| `centaur` | `CentaurSpitMissile`, `CentaurEvolvedSpitMissile` | `WeapMirelurkhunter01` (acid spit) | MiddleHand | `2hlattackleft` | `ProjectileNode` (head) |
| `nvsporeplant` | `SporePlantSpitMissile` | `WeapMirelurkhunter01` | MiddleHand | `2hrattackleft` | `ProjectileNode` (orifice) |

Fallout4.esm has no embedded spit gun; the mirelurk hunter's is a creature
gun (not playable, magazine 0, `AmmoMirelurkHunter` → `MirelurkHunterSpitProj`)
without the Embedded flag, as are the bloatfly's and mirelurk queen's.

FNV picks a gun's clip by its animation type, each aiming its own arm or
mount: the securitron SMG (pistol, type 3) `1hpattackleft`, the right-arm
machine gun; the laser (type 7) `2hrattackleft`, the left arm; the launcher
(type 9) `2hlattackleft`, the left arm; the missile (type 8) `2hhattack*`,
the body. The table has one clip per slot: `RangedAttack` (slot 0,
`1hpattackleft`), `RangedAttackLeft` (slot 1, the launcher's
`2hlattackleft`, also played for the laser: drift) and
`RangedAttackMissile` (slot 3, `2hhattackleft`, its body motion outside
the arm layer). Its body
is several NIFZ parts merged into one (`build.body_name` joins them with
`+`); rigid parts are not yet carried on a rig body, so its face screen is
missing.

## <a id="talk"></a>Talking (played 2026-10-28: Victor talks in Goodsprings)

**What made it work:** the race. On a race copied from the mole rat's
Victor never spoke; with `ProtectronRace` as the securitron's template race
(the race he talked on as a stand-in) his greeting played and the whole
Goodsprings conversation works. The talk states below were built first and
are kept (the robots' graph has them); whether the engine needs them was
not split out.

Victor (a securitron on the rig) kept his Talk prompt but never opened
dialogue, though his force greet ran, the greeting accepted him and his
voice folder had the silent greeting file. He had talked as a protectron
stand-in, whose race borrows the robots' graph (`ProtectronRace` SRAC →
`AssaultronRace` → `CreateABot\Behaviors\ProtectronWrappingBehavior.hkx`).
That graph carries `DialogueBehavior.hkx`; a rig's graph had no talk
handling at all.

- **The start is an IDLE**: action `ActionTalking` holds one
  tree per talking graph (`CreateABotTalkRoot`, `RaiderTalkRoot`,
  `DogTalkRoot`, `RobotTalkingRoot`...); the robots' children send
  `dyn_talkGeneric`.
- **The graph's answer**: `DialogueBehavior` enters `DynamicAnim` on
  `dyn_talkGeneric` and `PCapDynamicAnim` on `dyn_Talk`, the latter raising
  `StartVoice` and `PCapEnter`; both leave on `00NextClip`, `idleStop` or
  `InstantExitClip`.

Every rig now gets an `ActionTalking` IDLE sending `dyn_talkGeneric`
(`records.ACTIONS`) and, in its non-combat standing machine, two talk
states entered from anywhere on those events, playing the table's `Talk`
clip (else the idle) and leaving on the same three events
(`Builder.talking`). The securitron's talk clip is FNV's
`idleanims\specialidle_talk01.kf`. Whether the engine waits on these
before it opens dialogue is the theory under test.

Played 2026-10-28: no change, and the securitron's guns still did not fire
though everything checked offline matched the eyebot. The next test swaps
the race: the securitron's template race is `ProtectronRace` (the race
Victor talked on as a stand-in), keeping the rig's skeleton, graph and
clips. A template race's subgraph template race (`SRAC`) is replaced by the
rig's entry, its equip slot nodes (`ZNAM`) and movement type (`WKMV`) are
left out, its `Anims*` keywords go with its `ActorType*` ones, and an
own-rig NPC's height is taken against the template race (the protectron is
0.93 tall, the mole rat 1.0).

## <a id="sounds"></a>Creature sounds (every mode; the graph on an own rig)

**Code:** `fo4_import/spike/creature_sounds.py`.

FNV gives a creature a sound set: per sound type (CSDT 0-21) one SOUN and a
chance. A creature without one inherits another's (`CSCR`); a templated
creature takes its template's with Model/Animation (flag 0x40): of
FalloutNV.esm's 1,578 creatures, 467 templated ones with that flag carry no
sounds of their own, and only one templated creature without it lacks them. 86 creatures hold a set; none repeats a
type, 51 have a chance under 100. Animation text keys `Enum: <type>`
(`Left`, `Attack`, `Auxiliary1`...) play a type and `Sound: <EditorID>` a
SOUN; Death plays on dying and the conscious loop while alive (GECK
"Sounds Tab").

FO4 has no per-type table. Fallout4.esm's creature audio templates
(`AudioTemplateMolerat`) hold one actor sound, a loop (`CS2H 1`, `CS2D
NPCMoleratBreatheLP`, `CS2E`, `CS2F 0`, after `NAM8`); only Dogmeat keys
actor sounds (`CS2K`), by anim archetype. Every other creature sound is a
`SoundPlay.<SNDR EditorID>` event in its graph.

- **Every mode:** the NPC's inherited sounds (`CSCR`) give way to FNV's
  conscious loop (none without one; 2,285 vanilla NPCs carry no actor
  sounds), and it carries its set's keyword `FNV_<set>Sounds`. A stand-in's
  other sounds stay its own: they are in its vanilla graph.
- **Own rig:** a rig's race and graph serve several FNV sets (green, fire,
  golden geckos). Each type the rig's creatures use becomes a compound SNDR
  `FNV_<project>_<type>` with one layer per set: a copy of the type's SOUN
  under `HasKeyword <set keyword>` and, below 100, `GetRandomPercent <
  chance`. That is vanilla's layering (392 compounds; `UIPerkNerdRage`
  picks its male or female layer by `GetIsSex`, 30 SNDRs roll
  `GetRandomPercent`). The graph raises `SoundPlay.<compound>` on each
  `Enum:` key, `SoundPlay.FNV_<SOUN>` on each `Sound:` key, and the Death
  compound as the death step starts. When the rig plays FNV foot sounds,
  its skins' addons drop the template's footstep set (`SNDD`), so feet are
  not heard twice.
- **Not carried:** Hit, Idle and Aware have no `Enum:` keys in the gecko's
  clips and FO4 has no hook for them outside a graph state; the movement
  loop (type 10) has no FO4 actor-sound slot.

## <a id="parity"></a>Stage 2 against the played gecko (2026-10-27)

Built for `creatures\nvgecko` and compared with test 51's files:

- **Byte for byte:** the root graph, character, project and body NIF.
- **Same content:** `skeleton.hkx` and all ten clips (fixups in another
  order).
- **Records** (by EditorID, FormIDs mapped): race, body parts, skin, addon,
  movement type and all 15 IDLEs match; the attack weights come from the
  FNV creature's combat style.
- **`skeleton.nif`:** the same blocks, ragdoll and friction (joint friction
  now converted with the other lengths in `collision._joint`), but Elric
  orders the ragdoll's bodies differently from run to run. So the pose
  matcher's bones are looked up by name in the file just written
  (`assets.ragdoll_bones`): the played file had pelvis, chest and arm at 0,
  6, 11; a fresh build gives 0, 7, 12.
- **Wired** as mode `rig` (`creatures.Creatures._own_rig`, `rig/build.py`),
  `creatures\nvgecko` its default (the target NPC `EncMolerat01Template`).
  Run end to end into a scratch folder: the race's files once, a body NIF
  and skin per FNV body (green, fire, golden), 15 IDLEs; the graph's pose
  bones match the written skeleton.nif. The FNV gecko's 54 creatures each
  get their body's skin (`WNAM`, after `RNAM`).
- **The Creation Kit step** ran once through MO2 on the test plugin: it
  loads for about 15 minutes, and without `--forceAll` it writes nothing for
  a race whose AnimTextData the load order already has (the test plugin's
  archive did), so a build's own files must be gone first (they are: last
  run's list is deleted before the run). A full build with it is not run.
