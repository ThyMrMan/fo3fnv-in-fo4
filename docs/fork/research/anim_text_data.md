# AnimTextData: what the Creation Kit writes for our build, and writing it ourselves (research, 2026-11-06)

Status: investigated on the whole-map build's CK output (`temp/profile_data`,
21,452 files) and every vanilla AnimTextData file in the game's BA2s. Since
2026-11-11 the build writes every file itself and the CK stage is gone
([ours](#ours)); **not yet in a game build, not played**. Status lives in
[ROADMAP.md](../ROADMAP.md).

**Why.** The build runs `CreationKit.exe -GenerateAnimInfo` after the plugin
is written ([anim-info](../fo4_own_rig.md#anim-info)): 1,231 s on the
whole-map build of 2026-10-31. Fallout 34 writes AnimTextData itself
([prior art](../fo4_replacements.md#fallout34)), which suggested we could too.

## <a id="ids"></a>The file id rule (verified)

`<id>.txt`, id = `crc(folders) << 32 | crc(graph.lower())`; crc = CRC-32
with zero start and no final inversion (`gun_anim_text.entry_id`).

- **folders**: the subgraph entry's `SAPT` paths joined by `|`. **One folder:
  hashed in its authored case. Two or more: the joined string lower-cased.**
  Fallout 34's note (always lower case) and `gun_clips.crc` hold only for
  the multi-folder case, which every gun entry is.
- **Ids below 2³²** are a project's own files: crc of the lower-cased
  project path (`actors\fnvgiantant\fnvgiantantproject.hkx` → 229394221).
- Checked: all 3,144 Fallout4.esm entries. 2,786 have a file under this id;
  the other 358 are listed in the archives'
  `PersistantSubgraphInfoAndOffsetData.txt` instead. Folder lists with the
  case kept, or always lower-cased, explain fewer of the entries.
- For our plugin, all 8,401 entries are explained:
  - 6,184 got a CK file.
  - 2,063 got none: vanilla already ships a file under that id.
  - 154 got none: they are in vanilla's persistent list.
  - The 128 CK files with no subgraph entry are the projects.
- So the CK wrote nothing for ids whose data the load order already holds
  (in archives; whether a deployed loose file counts is not yet tested).

## <a id="what"></a>What the 21,452 files are

| Kind | Files | Size | Distinct contents |
|---|---|---|---|
| AnimationOffsets | 5,380 | 552 MB | 555 |
| AnimationSpeedInfo | 5,286 | 647 MB | 5,264 |
| AnimationStanceData | 5,368 | 148 MB | 1,539 |
| DynamicIdleData | 5,380 | 0.1 MB | 1 (`Version 1\n`) |
| FileData, EventInfo, ClipGeneratorData | 12 each | small | |
| SyncAnimData | 1 | | |

5,252 of the 5,380 entries are the **gun entries** on
`FNV_HumanRaceSubGraphDataAdditive` (7,775 entries; the injured-arm wrapping
graphs and `WeaponBehavior` lead). The 11 own-rig creatures are a few dozen
files. `FNV_SuperMutantRaceSubGraphDataAdditive`'s 608 entries got nothing;
vanilla covers every one of their ids. **98% of the CK's files, 1.35 GB, are
gun data**, not the own-rig creatures that `anim_info` runs for (time per
entry not measured). The gun entries' AnimationFileData is already ours:
`gun_clips._anim_text` copies the template's under the new id, pointing the
clips it wrote at the FNV folder.

**Where FNV clips land** (a 411-entry sample of the CK's files): no
third-person entry resolves an FNV clip (FNV third-person clips are not
built yet). Only first-person `GunBehavior` and
`Pistol_GunWrappingBehavior` entries do, 414 records in 10 files; those have
offsets and stance, no speed info.

## <a id="offsets"></a>AnimationOffsets V4 (decoded)

A string is a u8 length (including the NUL), then the bytes. The layout:

```
'V4\n', str graph
u32 n, n x (str clip name, str clip path)        name -> resolved file
u32 m, m x (str clip path, f32 duration,
            u32 t, t x (f32 time, x, y, z),        root translation keys
            u32 r, r x (f32 time, quaternion),     root rotation keys
            u32 e, e x (f32 time, str event))      annotations (FootLeft ...)
```

All 3,154 vanilla and 5,380 CK files parse to their last byte.

- The CK's files hold 1.49 M clip records:
  - 3,884 are FNV clips, which are new;
  - 1,187 are vanilla clips that no vanilla file has;
  - the rest are vanilla clips that vanilla already has.
- Vanilla clips against vanilla's own records:
  - Duration and events always match.
  - Translation and rotation match within 0.001 for 99.5% of records: float
    noise from recomputing.
  - 4,958 records differ by more.
- 4,817 CK files have a vanilla template: the same entry with the
  `Actors\FNV` folders dropped. All have the same clip set and the same
  length as their template. Only the order (hash order) and float noise
  differ.
- **An FNV clip's record**, all 414 sampled reproduced exactly:
  - the duration from our clip;
  - one zero translation key and one identity rotation key, at
    float32(frames × frame length) (90 × 0.033333335 = 3.0000002);
  - our clip's annotations, kept only when the graph or a graph it
    references names that event, spelled as vanilla's offsets files spell
    it (`weaponFire` → `WeaponFire`; sound events dropped).
- **The names list** is the clips the graph's clip generators play through
  the entry, narrower than every `hkbClipGenerator` in the graph and its
  references: `WPNAssemblyPose` is in the graph but in no list.

## <a id="root-keys"></a>Writing offsets: the CK's rules (found 2026-11-11)

`fo4_import/havok/anim_offsets.py` reads and writes V4. Checked on the
whole-map build's CK snapshot (`temp/profile_data`):

- **Reading.** All 5,381 CK files and every vanilla offsets file pack back to
  the same bytes.
- **Names.** For the 86 first-person gun entries, the names are exactly the
  entry's AnimationFileData clips (ours, from `gun_clips`) minus the behavior
  graphs, each named by its file stem. Their vanilla templates have no
  offsets file (persistent list only), so nothing can be copied.
- **Creatures' names are the clips each attack plays.** Take every event of
  the race's attack data (ATKE) and every fire event of the rig's guns (the
  fire IDLEs' ENAM, `behavior.fire_start`). Find the state the event's
  transition leads to (a state's own transitions, or a wildcard), then
  collect the clips beneath it, entering only each nested state machine's
  start state.
  - This matches all 12 own-rig creatures. A ranged attack's layer plays the
    combat locomotion state machine, which starts standing in `CombatIdle`,
    so ranged creatures list `CombatIdle` and melee-only ones don't. The
    raven, with no attacks, lists nothing.
  - Taking every IDLE's event is too broad: movement and turn idles pull in
    the walk and turn clips.
- **Stale ids pile up.** 116 offsets files in the 2026-11-11 morning snapshot
  match no subgraph entry in the plugin. Their file data dates from an older
  build; nothing deletes an entry's AnimTextData once the entry is gone. A
  writer that owns the whole file set can remove them.
- **Order can't be reproduced; we write sorted.** The names list is a
  `BSTScatterTable` hashed on the string pool's *handle pointers*, and the
  records follow the singleton's clip table, keyed the same way
  (CreationKit.exe writer `0x311bb0`, insert `0x2da360`). Pointers change per
  run: pairs of CK files from different runs share the order of shared
  entries only at chance (names 0.48, records 0.65), against 0.87 and 0.998
  within one run. The game reads both into lookup tables.
- **Root keys: `anim_offsets.clip_record`, bit for bit.** All 3,877 records
  of the current FNV clips in the snapshot (3,548 first person, the rest
  creatures) pack to the CK's bytes. The 7 others are records from 29 Oct
  files whose clips have since changed duration.
  - Input: the clip's `hkaDefaultAnimatedReferenceFrame` samples (x, y, z,
    yaw), its duration and up axis, and the animation's duration and frame
    count (`anim_offsets.motion`). No reference frame or under 2 frames: no
    keys.
  - Frames (CK `0x2ed600`): from frame 0, for each later end frame, the worst
    frame between is measured against the line from the last kept frame to
    the end. Over the tolerance (strictly), the frame before the end is kept
    and becomes the start; the last frame is always kept, so a still clip
    keeps one key of each kind. Translation and rotation are run separately.
  - Translation error (`0x2f8000`): distance from the point at the same
    *time* fraction along the line; tolerance 2.0 units.
  - Rotation error (`0x2f8210`, `0x2ed7b0`): twice the largest vector
    component of the frame's rotation against the slerp of the ends;
    tolerance `0.3f × 0.0174532924f`.
  - Every frame is read at time float32(frame) × float32(duration ÷ (frames
    − 1)) through Havok's `getReferenceFrame` (`0x2247730`), which
    interpolates between samples. That index lands a hair off the integer,
    so values differ from the raw samples in the last bits. Rotation is
    `setAxisAngle(up, yaw)`; a negative sine times 0 gives the CK's −0.0.
  - The earlier greedy on raw samples (index fraction, yaw degrees) picked
    the same frames on every clip tested, but not the CK's bits.
- **Vanilla clips need no computing.** The 11 Nov run did not recompute
  vanilla clips: all 1,374,220 vanilla-clip records equal vanilla's shipped
  record byte for byte, and the game keeps the first record it loads for a
  path anyway ([game use](#game-use)). Copy vanilla's record.
- **Events.** An annotation's name up to its first `.` (`weaponFire.2` →
  `weaponFire`) is kept when it is one of the 430 event names vanilla's
  offsets files carry. `SoundPlay.*` is dropped. This matches all 4,126
  vanilla-clip records and 3,774 of 3,778 FNV-clip records (the 4 are clips
  rebuilt since), ignoring case. The CK's spelling varies (`WeaponFire` vs
  the clip's `weaponFire`), and the game compares event names without case.

### <a id="ck-math"></a>The CK's float math (`fo4_import/havok/ck_float.py`)

Everything is float32 in the CK's operation order, including its horizontal
adds. Havok's reciprocal and 1/sqrt are one Newton step on `rcpps` and
`rsqrtps`, which are approximate instructions whose last bits differ between
CPU vendors. `ck_float_tables.py` holds AMD Zen's results, measured on the
CPU our CK runs on (Ryzen 7 9800X3D): each depends only on the exponent
(its parity, for rsqrt) and the top 12 mantissa bits, and the tables match
the native instructions on 20,000 random inputs. With exact math instead,
26 of 336 creature records miss in the last bits (all 300 first-person
records sampled still match). A CK run on an Intel CPU would write different
last bits, and so did Bethesda's for vanilla: 912,725 of the vanilla-clip
records differ from the model in the last bits.

`sincos` and `slerp` use the CK's own constants (sse_mathfun's sincos;
`hkQuaternion::setSlerp` `0x1c72380`, which lerps above a dot of 0.999 and
otherwise uses a polynomial asin). Cost: about 15 ms a clip in Python, 55 s
for all 3,683 FNV clips on one core.

## <a id="others"></a>Speed and stance data (decoded 2026-11-11)

Both layouts were read from the CK's own reader and writer in the
disassembly and proved on data. The speed parser rebuilds all 3,733 vanilla
and 5,286 CK files byte for byte. The stance parser reads all 3,440 vanilla
and 5,369 CK files to their last byte. A string is a u8 length (counting the
NUL) and the bytes; length 0 is empty, with no NUL. A transform is a
quaternion (w, x, y, z) and a translation, seven f32.

### <a id="speed"></a>AnimationSpeedInfo (`bsanimation\animationspeedinformation.h`)

| Part | Fields |
|---|---|
| File | u32 version 6; u32 count; entries |
| Entry | str `<graph file>.hkb/<state machine>`; contour; tail |
| Contour | str type, then its body |
| `CollectionAnimationSpeedContourName` | u32 n; n × (contour, tail); u8 kind (0 speed bins, 1 directions) |
| `IndividualClipAnimationSpeedContour` | f32 direction x, y, z; str playback-speed variable; f32 speed |
| `SpeedSampledAnimationSpeedContour` | u32 node index; f32 direction min, max, param min, max; u32 directions, each (f32 direction, u32 n, n × (f32 param, f32 speed)); u32 m, m × (f32 direction, f32 speed); u8 zero-centered |
| Tail | str event; str sync variable; i32 sync value (−1 none); f32 stop time (every tail from version 5; the game uses only the root's) |

- An entry is the innermost state machine that owns states with root
  motion. A collection's children are its moving states; each tail names
  the event that enters the state, the variable bound to the start state,
  and the state's id.
- An individual contour is one clip: its root translation normalized, and
  |translation| ÷ duration.
- A speed-sampled contour is a parametric blend the CK runs. It steps the
  blend parameter by 20 from the lowest child weight to the highest, and the
  direction by 15°. Each sample is 1 s of graph time at 30 Hz, its measured
  root speed recorded. The samples are then simplified.
  - The gecko: 62.5 is WalkForward's root speed, 578.6 RunForward's. The
    blend is linear, so only the end samples survive.
- The stop time is the root distance the graph travels after `MoveStop` at
  top speed, divided by that speed: 0.081 s for the gecko.
- **Own rigs:** every entry is one speed-sampled contour on
  `NonCombatLocomotionSM` and `CombatLocomotionSM` (node index 1 and 5).
  The spore plant and the raven (walk and run clips with no root travel) get
  no file.

#### <a id="speed-rules"></a>Writing it: `anim_speed.rig_speed`

`fo4_import/havok/anim_speed.py` reads and writes the format (all 5,383 CK
files of the 2026-11-11 snapshot and all 3,733 vanilla files pack back to
the same bytes) and writes an own-rig creature's file from its root graph
and its clips' root motion (`anim_offsets.motion`):

- **Entries:** each state machine with a state whose generator (under any
  modifier generators) is a parametric blender with two or more children and
  some root travel. Key `<graph file stem>.hkb/<machine name>`, in file order
  (the CK's order is hash order; the game looks entries up by name). Tail:
  no event, no sync variable, value −1.
- **Contour:** one speed-sampled contour, no collection. Parameter min and
  max: the lowest and highest child weight. Samples: the parameter stepped
  by 20 from the minimum while it stays at or under the maximum (float32, as
  the CK), the speed linear between the children's root speeds by weight,
  then the samples on the line between their neighbours dropped. One
  direction bin, at the children's mean heading (atan2(x, y) of the clip's
  root travel; 0 forward); the direction bounds both that heading. Outline:
  (heading, root speed) of the lowest and the highest child. Zero-centered 1.
  A clip's root speed is its reference frame's first-to-last distance over
  its duration.
- **Stop time:** the moving state's first transition blends it out over the
  effect's duration; summing the smooth curve's remaining weight
  (1 − (3u² − 2u³)) over its 30 Hz frames gives 5/12 of the duration,
  0.0833 s for our 0.2 s `MoveTransition`.
- **Node index:** the moving state's index in its machine (1). Not read by
  the game; the CK's rule was not found (it writes 1 and 5 on our rigs, 1,
  14, 15, 39, 40, 53 in vanilla; no pre-order count of state machines or
  modifier generators fits both our rigs and vanilla's radroach).

**Match against the CK's 10 files** (2026-11-11 snapshot, both entries of
each):

- Exact on all 10: keys and entry count, tails' event, sync variable and
  value, no collection, one direction bin, zero-centered, parameter min and
  max (bit for bit), file or no file (spore plant and raven: none).
- Node index: exact for `NonCombatLocomotionSM`, 1 against 5 for
  `CombatLocomotionSM`.
- Samples bit for bit on the linear blends (gecko, giant rat, nightstalker,
  spore carrier). The CK measures 1 s of its own blend and keeps 3 to 33
  noisy samples on the rest; ours (two) differ from the CK's curve by up to
  2 u/s (queen ant), 3 (centaur), 13 (Securitron), 26 (giant ant), 80
  (cazador) and 132 (mantis: the CK measures 315 at parameter 185 of a blend
  that tops out at 280). A 1 s window over the synced clips from phase 0 did
  not track the CK either.
- Outline: speeds within 6e-5; headings bit for bit on 7, within 3e-7 on the
  giant ant, nightstalker and centaur. Direction bin and bounds: the CK's
  are 0 to 4e-4 rad of drift; ours within that.
- Stop time: 0.0833 against the CK's 0.028 to 0.094: within 0.011 on 8, 0.02
  on the cazador, 0.055 on the mantis. Fitting the run clip's travel over
  the blend-out from several phases did not track the CK better.

### <a id="stance"></a>AnimationStanceData

| Part | Fields |
|---|---|
| File | str `AnimationBoneTransform`; u32 1; u32 poses; poses; u32 records; records |
| Pose (88 bytes) | u8 stance, u8 modifier, 2 zero bytes; head, torso and DirectAt transforms |
| Record (fire location) | u8 stance, modifier, attack type (0 fire, 1 auto, 2 throw), equip index; base transform; u8 heading and looking counts; f32 heading min, looking min, heading step, looking step; heading × looking transforms (looking fastest) |

- Stances: 0 normal, 1 sneaking, 2 very low, 3 low, 4 mid and 5 high cover.
  Modifier 1 is sighted.
- Head and torso are the race's body-part nodes: Camera and Chest in first
  person. DirectAt is identity unless an aim modifier is active.
- **The CK runs the graph to make these.** It sends the stance events and
  updates the graph for 10 s. For each fire location it sends the attack
  event and steps 0.01 s at a time until the attack's annotation, then reads
  the equip slot's bone. The grid aims at a target 4,096 units away, cell by
  cell. CK grids are 7 × 5 (−60° to 60°).
- **From our clips** (first person, checked on 90 CK files, within 0.01):
  - Head: the Camera bone's rest pose (90/90 unsighted, 82/90 sighted).
  - Torso: Chest at frame 0 of `WPNIdleReady` (89/90), or `WPNIdleSighted`
    when sighted (82/90).
  - Sneaking: the normal pose with z − 40 (133/133 vanilla).
- **Fire locations are not one clip frame.** They come from the graph's
  blending at the fire annotation; the nearest frame's Weapon bone is 0.6 to
  0.9 units off.
  - Against the vanilla templates, Fire records change in 336 of 340 and
    Auto records in 190 of 338. Throw records never change (342 of 342).
  - Bit-matching them would need a Havok behavior runtime.
- **Creature entries** (an own-rig race's subgraph entries on its root
  graph; checked on all 12 of the CK's):
  - One pose, stance 0, modifier 0, DirectAt identity. Rotations are stored
    w x y z.
  - Head: the race's BPTD node of part type 1 (Head1) at frame 0 of the
    clip the graph plays once settled with `weapEquip` sent (each machine's
    start state, or where its transition on `weapEquip` leads: the
    `Combat` side, `CombatIdle`). Within 0.7 units of the CK's on 9 of 12
    (0.25 on 7); the queen ant (16 units in x), giant ant (7) and raven (8)
    blend or idle differently in the CK.
  - Torso: we write the part type 0 (Torso) node at that frame. The CK's
    is a different bone per rig (Spine2 for the gecko and rat, Thorax01 for
    the mantis, Spine4 for the nightstalker), not the arms' common
    ancestor; the game never reads it.
  - Fire records: one per race equip slot (QNAM) that names a node (ZNAM),
    `0 0 0 <slot index>`, no aim grid. Slot 0, the hand slot, is posed at
    the node; the others are identity. The set matches the CK's on all 5
    ranged races; slot 0's transform is 1 unit off (Securitron), 36 (giant
    ant) and 64 (queen ant), since the CK samples the attack's fire moment.

## <a id="persistent"></a>The persistent list

`AnimationOffsets\PersistantSubgraphInfoAndOffsetData.txt`, one `<id>.txt`
per line. Each DLC archive ships its own (333 to 366 ids, 398 joined); a
loose copy replaces them all. The CK's for our build holds 768: the 333
every archive shares plus 435 of ours. **One of our entries is on it exactly
when its template is on vanilla's** (423 of 423, and none of the 4,817
others); the CK's 12 others are entries the CK keeps.

**The game never reads it.** Fallout4.exe's getter for the name (`1313340`)
has no call, pointer or other reference. Only the CK uses the list.

## <a id="project-files"></a>Event info, clip generator data and sync data (decoded 2026-11-11)

The game loads all three: each path is built by slot 1 of a loader's vtable
(`AnimEventInfo`: `BehaviorGraphSpecificDataLookupSingleton`, `2322e0`;
`ClipGeneratorData`: `AnimationClipDataSingleton`, `1313ac0`;
`SyncAnimData`: `BGSSynchronizedAnimationManager`, `813770`). The CK wrote
one event info and one clip generator file per own-rig creature, under the
CRC of the lower-cased root graph path, and none for gun entries. Base
Fallout4 ships 123 event info files and no clip generator data; the DLCs
ship 25 of each.

**AnimEventInfo** is text, `\n` lines: `V2`, the root graph, a line naming a
second graph (empty for ours; vanilla's Handy names `HandyBehavior.hkx`
beneath its wrapping graph), the attack count, then per attack its event,
`1` when the event's transition is a wildcard (ranged attacks) else `0`, the
clip count and the clip generators' names. Attacks and clips follow the
offsets names rule ([creatures](#root-keys)), in the graph's transition
order. Ours equal all 12 CK files byte for byte.

**ClipGeneratorData** is binary: `V4\n`, str graph, u32 count, then per clip
generator of each attack (in event info order, repeated when two attacks
play it, as `CombatIdle` is): str name, str animation file stem, f32
playback speed, crop start and crop end, u8 mirrored (`flags & 4`), u8
dynamic idle placeholder (a child of `DynamicAnimationTaggingGenerator`,
whose animation is written empty), u32 triggers, each str event, f32 time,
u8 relative to the clip's end. Triggers are the generator's first trigger of
each event vanilla's offsets name, spelled as they spell it (`weaponFire` →
`WeaponFire`; `SoundPlay.*` dropped). All 37 CK and DLC files parse; the two
bytes agree with the graph on all 254 generators found in their graphs. Ours equal
the CK's 12 except for trigger order, which follows the CK's hash table.

**SyncAnimData** is `ResolvedSyncAnimData<plugin>.txt`, text: `V4`, then the
synchronized (paired) animation groups. FNV and FO3 have none: the CK wrote
`V4\n0\n`.

## <a id="game-use"></a>What the game reads (Fallout4.exe, 2026-11-11)

Read statically from `Fallout4.exe.unpacked.exe` (RVAs, base 0x140000000);
the game was not run. "Suspected" means the reader or the purpose was not
found, not that it was proved.

**Offsets** (load `1312ed0` → `1314860`, into `AnimationClipDataSingleton`):
- Lookup by (graph id, clip name) through the names list (`1313f00`).
- **A clip path's record is shared, and the first file loaded wins**
  (`1314c80`, checked: it looks the path up and reuses a record already
  there). Our records for vanilla clips are ignored whenever vanilla's
  loaded first; FNV clip paths are ours alone.
- Root translation and rotation at time t (`1315760`, `13157b0`) feed
  root-motion prediction for animation-driven movement, NPC movement, melee
  lunges in the combat aim controllers, and magic. Duration clamps the time
  window.
- Events: event time by name (`13157e0`), the minimum of the clip
  generator's own triggers and these. Used for attack timing.
- A missing record: no root motion and no event, so prediction treats the
  clip as still.
- First-person entries: no reader found (suspected unused).

**Speed** (load `1335170`, lookup `1388870` by the active state machine's
name; a missing entry turns the system off for that actor and every
consumer falls back to defaults):
- Read: the key; individual-clip direction x, y (headings within 15°),
  speed and playback variable (sets the playback ratio, clamped −1 to 3);
  speed-sampled direction bins and samples (speed → blend parameter), the
  outline (per-direction speeds; gait multipliers only when exactly 4) and
  zero-centered; the collection kind; tail event and sync variable/value
  (sent when a child is chosen); the root's stop time (stop distance = speed
  × stop time, for follow and approach).
- Not read (suspected): node index, direction and param min/max, the
  individual direction z, children's stop times.

**Stance** (load `136abc0`, activated per actor through
`BSSubGraphActivationUpdate`; first or third person by view for the player):
- Poses: only translations count (rotations are applied to a zero offset).
  Head height feeds cover search and attack-location search; DirectAt is
  the aim height for about 12 line-of-sight sites, and a z of 0 falls back
  to the game's own height. Torso: no reader.
- Fire records (animation types ≥ 7: bow, staff, gun, grenade, mine): the
  base transform applied to the projectile node's offset, then the heading
  × looking grid interpolated. NPCs use them only when the weapon has no
  projectile node, and for AI aim, cover and line of fire. **The first
  person Throw record is the player's grenade launch point** outside VATS.

**What must be exact, then:**
- Keys and names: the speed key, tail events and sync values, playback
  variables, collection kind; the offsets names list, event names and times.
- Root keys of moving FNV clips (movement and melee prediction integrate
  them). We now write them bit for bit.
- First-person Throw records (already template-identical, 342 of 342).

Approximate is fine for speed samples, outline and stop time, fire record
transforms and grids (0.6 to 0.9 units is harmless), and pose heads. Keep
DirectAt at identity. Pose rotations and torso, the unread speed fields,
first-person offsets and the persistent list take any value.

## <a id="writer"></a>The writer (built 2026-11-06)

`fo4_import/havok/gun_anim_text.py` writes the entries the CK would compute
from vanilla clips only:

- **Which:**
  - third-person entries with FNV and vanilla folders, on a graph vanilla has
    offsets for;
  - none of the FNV clips in the entry's file data (gun_clips) is named in
    any vanilla offsets file of that graph.
- **What:** the template's offsets, speed, stance and dynamic idle files,
  byte for byte, under the entry's id. That is the data the game already
  uses for the template entry. The entry is added to the persistent list
  when its template is listed (`merge_persistent`). So do the master
  builds' listed ids, since a DLC build's loose list hides the base's.
- **When:** at the end of the plugin write (`build_finish._anim_text`);
  there is no CK step since 2026-11-11 ([ours](#ours)).
- **Checked against the CK snapshot:**
  - 5,154 entries copied. In the 411-entry sample, all 378 copied are
    entries where the CK resolved no FNV clip, and all 10 that resolve one
    are left to the CK.
  - The offsets have the CK's clip set in all 356 with a template file. The
    other 22 have persistent-only templates and, like vanilla, no offsets
    file.
  - The persistent ids match the CK's list.
  - Loading vanilla takes 1.1 s, choosing the entries 2.4 s warm, writing
    378 entries 1.2 s.
- Everything else is [ours](#ours) now.

## <a id="ours"></a>Everything ours: no Creation Kit (built 2026-11-11)

`fo4_import/havok/anim_text.py`, run by `build_finish._anim_text` after the
plugin is written. The `-GenerateAnimInfo` stage is gone.

| Entries | Files | Rule |
|---|---|---|
| Gun entries playing only vanilla clips | offsets, speed, stance, dynamic idle | the template's, copied ([writer](#writer)) |
| Own-rig creature projects (SGNM root graph in the data folder) | offsets, speed, dynamic idle under the project id; event info and clip generator data under the root graph id | [root-keys](#root-keys), [speed-rules](#speed-rules), [project-files](#project-files) |
| The creature's subgraph entries on its root graph | the project's offsets, speed and dynamic idle, byte for byte; a stance | the CK's 12 match this; [stance](#stance) |
| Any other entry vanilla has no file or persistent line for (first- and third-person guns on FNV clips, furniture) | offsets naming its file data's clips (`file_data_names`); the template's speed, stance and dynamic idle, or `Version 1` dynamic idle data without a template | the CK's third-person files: 5,245 of 5,370 speed and stance files equal a vanilla file, all dynamic idle files do |
| The plugin | `SyncAnimData\ResolvedSyncAnimData<plugin>.txt` = `V4\n0\n` | [project-files](#project-files) |

Then `prune` removes the files of these kinds no longer written (entries
gone, and what the CK left), and the persistent list is merged.

- **Offsets records.** Each clip's record is computed once per run and kept
  in the work cache (`anim offsets records`, keyed by clip path and bytes;
  any edit to `anim_offsets` or `ck_float` redoes them). Misses are made in
  a process pool: 2,304 clips in 34 s, 0.5 s from the cache. The current
  plugin's entries name 19,149 clips (562 with a vanilla record), so the
  first build takes about 5 minutes and later ones seconds, against the
  CK's 1,231 s every build. The CK math costs about 130 ms a clip in Python
  (`_kept` re-measures each span), the place to look if this gets slow.
- **Coverage on the 2026-11-10 plugin:** 4,541 distinct entries; 616 have
  vanilla files, 97 are copied, 3,828 play their own clips (13 without a template:
  the 12 creature entries and the `NVCrucified` furniture entry).
- **Furniture without a template** gets offsets and dynamic idle data but no
  stance: the CK's comes from running the vanilla furniture graph on the
  human rig.
- <a id="entry-file-data"></a>**A creature's subgraph entry's file data**
  (`anim_text.entry_file_data`, 2026-11-13). Until now nothing wrote it:
  - `rig.build` wrote only the project's list, and `gun_clips` only gun
    entries'.
  - The FNV build kept the CK's 12 as leftovers, because `prune` doesn't own
    `AnimationFileData`.
  - The Fallout 3 build's giant ant had none, which
    [the graph check](../fo4_own_rig.md#graph-check) found.

  The form is LF lines: `3`, `1`, the entry id, the count, then each
  `Animations\` clip of the project's list, under the project folder. Against
  the CK's 12, header, line endings and clips are equal; only the order
  differs. The CK's order follows neither the project list nor the graph, a
  hash order like the offsets records', and the game looks clips up by name.

**Drift from the CK, accepted:** record order (the CK's is a pointer hash),
the speed samples ([speed-rules](#speed-rules)), the creature stances' torso
and fire transforms, and the furniture stance. The game reads none of the
torso, and the fire records only as a fallback ([game-use](#game-use)).
