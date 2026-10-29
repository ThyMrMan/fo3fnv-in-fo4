# FO4 custom creature from scratch: engine expectations for skeleton, ragdoll, behaviour graph, animations and records, plus known failure modes

Research date: 2026-10-25. Method: web search and fetch. **Access caveat:** nexusmods.com (mod pages, forums, wiki), falloutck.uesp.net (most pages) and web.archive.org all returned HTTP 403 or were blocked for the fetch tool. Several of the most relevant primary sources therefore come only through search-result snippets, and are marked "(snippet)". These sources include IceStormNG's *New Creature Behavior and Implementation Tutorial* (Nexus FO4 mod 56676, 2021-12-18), the *Fallout 4 HAVOK Guide* forum thread, F4AK docs and the Nexus wiki "Animation In Fallout 4". The coordinator should treat those as leads to read by hand. Skyrim-only facts are marked **[Skyrim]**.

## Behaviour graph contract (variables, events, annotations, project/character/behaviour files, subgraphs, AnimTextData)

### Takeaway
An FO4 creature is a Havok 2014 *project* hkx, which points to a *character* hkx (rig/skeleton name, character properties), which points to a root *behaviour* hkx. Further behaviours hang off the race as **subgraphs**, chosen by keyword and role (MT, Weapon, Furniture, Pipboy). These subgraphs must be shipped as subgraphs of the race's root project. A creature also needs an **AnimTextData** cache that the CK generates with `-GenerateAnimInfo`. Without it the engine has no speed, stance or sync data for the clips. No public, complete FO4 list exists of the graph variables and events the engine reads and writes. The best available evidence is a community-compiled annotation list, plus the Skyrim CK variable list, which the FO4 graphs largely share by name.

### Cited Findings
**File set and roles**
- A FO4 Havok guide describes a set of 3 core files: a Behavior File, a Character File and a Project File. Skeleton and animation files are optional extras, and the character file's `rigname` entry points to the skeleton file (snippet) — [Fallout 4 HAVOK Guide, Nexus forums](https://forums.nexusmods.com/topic/9329348-fallout-4-havok-guide/)
- One modder's custom-project folder layout under `Data\Meshes\GenericBehaviors\`: `Animations` (only if you have HKX animations), `Behaviors`, `CharacterAssets` (only if you use your own skeleton), `Character`, with the project file at the top level (snippet; a personal layout, not official) — [Nexus forums: import fbx/hkx into Fallout 4](https://forums.nexusmods.com/topic/6585491-import-fbxhkx-into-fallout-4)
- Behaviour graph paths are given relative to `Data\Meshes`. Example: `Actors\Character\Behaviors\FurnitureBehavior.hkx` (snippet) — [Custom Furniture Animation Tutorial, Nexus 41209](https://www.nexusmods.com/fallout4/mods/41209)
- NAF sets a race's root behaviour graph through a `graph` attribute in raceData XML. Its human example is `Actors\Character\Behaviors\RaiderRootBehavior.hkx`. This shows the "root behaviour" naming convention (snippet) — [Native Animation Framework, Nexus 73889](https://www.nexusmods.com/fallout4/mods/73889)
- FO4 hkx must be the 64-bit, binary-packed files that HCT 2014.1 r1 64-bit writes. Earlier formats are not read (snippet) — [Nexus forums: import fbx/hkx into Fallout 4](https://forums.nexusmods.com/topic/6585491-import-fbxhkx-into-fallout-4)
- FO4 Havok is hk_2014.1.0-r1, packfile version 11. The header is 0x40 bytes, followed by a 16-byte padding block that Skyrim lacks. Section headers are 0x40 bytes (Skyrim: 0x30). The file has `__classnames__`, `__types__` (empty) and `__data__` sections, with local, global and virtual fixups — [PyNifly wiki: HKX Animation Format (FO4/Skyrim)](https://github-wiki-see.page/m/BadDogSkyrim/PyNifly/wiki/HKX-Animation-Format-(FO4---Skyrim))

**Subgraphs (RACE "Subgraph Data", i.e. SGNM and related fields)**
- Subgraphs split the character behaviour graph into parts that are attached dynamically, so one graph serves many animation sets. Animation *file names* are fixed by the graph logic, but their *paths* can change. Modders can therefore add content through standard FO4 graphs without Havok Behavior — [Fallout Wiki CK mirror: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs) (same text as [falloutck.uesp.net/wiki/Subgraphs](https://falloutck.uesp.net/wiki/Subgraphs))
- Roles: **MT** (no weapon readied, changed by ChangeAnimArchetype or ChangeAnimFlavor), **Weapon**, **Furniture**, **Pipboy** (first person only), and **Linking Only** (reserved for Bethesda's build). Perspective applies only to the player race; non-playable races use third person — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- Selection: every Actor Keyword must be present on the actor. The entry matching the most actor keywords wins, and the target-keyword count breaks ties. A full tie is undetermined. The Weapon role targets the equipped weapon and the Furniture role targets the furniture; target keywords must all match — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- **Behaviour Path restriction:** "only behavior graphs shipped as subgraphs to the race's root project are supported". For projects listed on the body data tab, you must use a behaviour graph already listed in that project's Behavior Paths. Others "will not work correctly" — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- Animation Paths are searched in order, and the first match wins — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- Additive races add subgraph data to an existing race. Template races reuse another race's subgraph animation data; their Skeleton and Behavior Graph must match the template — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- The Papyrus `AttemptAnimationSetSwitch` loads new graphs for both the MT and Weapon subgraphs — [falloutck.uesp.net: AttemptAnimationSetSwitch](https://falloutck.uesp.net/wiki/AttemptAnimationSetSwitch_-_Actor)
- A mod author warns that "you cannot change anything referenced in the subgraph data" without regenerating AnimTextData (snippet) — [Misc anim tweaks and fixes, Nexus 53597 posts](https://www.nexusmods.com/fallout4/mods/53597?tab=posts)

**AnimTextData**
- Command: `CreationKit.exe -GenerateAnimInfo:<ESMFilename> <DataFilepath> <OutputFilepath> [--speed] [--stance] [--forceAll]`. The ESM name must have no spaces. Flags by role: MT `--speed`, Weapon `--speed --stance`, Furniture none. The output provides speed translation, furniture entry/exit calculations, and weapon sight lines and fire locations. Example output path: `..\Data\Meshes\AnimTextData`. Create Archive should pack it — [Fallout Wiki: Subgraphs](https://fallout.wiki/wiki/Resource:Creation_Kit/Subgraphs)
- Subfolders: AnimationFileData, AnimationOffsets, AnimationSpeedInfo, AnimationStanceData, AnimEventInfo, ClipGeneratorData, DynamicIdleData, SyncAnimData. Generated files land in a nested `Meshes/AnimTextData` and have to be copied into the mod's folders (snippet) — [langnao, Using GA custom animations on custom weapons, Nexus article 548](https://www.nexusmods.com/fallout4/articles/548)
- The cache files have 19-digit numeric names (snippet) — [Custom Furniture Animation Tutorial, Nexus 41209](https://www.nexusmods.com/fallout4/mods/41209)
- Failure modes: generation is "not pretty consistent". If an animation plays in slow motion, regenerate with different flags (e.g. drop `--stance`) (snippet) — [Nexus article 548](https://www.nexusmods.com/fallout4/articles/548). If not all animation files the graph needs are present, no data is generated. AnimationFileData shows which clips the graph actually uses (snippet) — [Nexus 41209](https://www.nexusmods.com/fallout4/mods/41209). A modder reported "no new data was generated" after deleting the old AnimTextData (snippet) — [Nexus forums: fixing third-person animation bugs p3](https://forums.nexusmods.com/topic/7747383-fixing-third-person-animation-bugs/page/3). The batch-file workflow reportedly breaks on the "next gen" CK (snippet) — [Nexus 53597 posts](https://www.nexusmods.com/fallout4/mods/53597?tab=posts)

**Variables (engine and graph contract)**
- The CK animation-variable list (written for Skyrim, partly guesswork) includes floats `Speed`, `Direction`, `VelocityZ`, `camerafromx/y/z`, `bodyMorphWeight`, `IsInCastState` and others. `bAnimationDriven` makes animations such as SprintStart actually move the actor instead of "moonwalking" — [ck.uesp.net: List of Animation Variables](https://ck.uesp.net/wiki/List_of_Animation_Variables) **[Skyrim]**. The FO4 wiki mirror shows the same getter and setter used on `bAnimationDriven` — [Fallout Wiki: SetAnimationVariableBool](https://fallout.wiki/wiki/Resource:Creation_Kit/SetAnimationVariableBool_-_ObjectReference)
- An open-source reimplementation groups the engine-shared variables. Engine-written inputs: `iCombatStance`, `iState` (+ `iState_NPC*`), `bHeadTracking`, `TargetLocation`, `camerafrom*`, `Pitch`, `iSyncIdleLocomotion`. Graph outputs the engine reads: `bAnimationDriven`, `bMotionDriven`, `bAllowRotation`, `bInMoveState`, `bSprintOK`, `bEquipOK`, `IsRecoiling`, `bIsSynced`. Also listed: `iGetUpType`, `IsBleedingOut`, `iSyncTurnState`, `TurnMin`, `fMinSpeed` — [opensky issue #1357](https://github.com/jjgroenendijk/opensky/issues/1357) **[Skyrim, inferred]**
- FO4 console: `SetAnimGraphVar` (sgv) sets a graph variable and `ToggleMotionDriven` (TMD) toggles motion-driven animation. These are useful for debugging a new graph — [reg2k FO4 console command dump](https://gist.github.com/reg2k/bad5567d30787067dcaa42ba948ce87e)
- The INI `[Animation] bAllowGraphDriven=1` turns off animation-driven motion and speed. A mod describes it as a workaround for a movement-lock bug (snippet) — [Disabled Animations Graph Driven Movement, Nexus 73873](https://www.nexusmods.com/fallout4/mods/73873)

**Events and annotations**
- Annotations are stored in the clip on a note track attached to the Root bone (snippet) — [Nexus forums: havok annotations](https://forums.nexusmods.com/topic/13103574-havok-annotations/). PyNifly writes all annotation events to track 0 — [PyNifly wiki](https://github-wiki-see.page/m/BadDogSkyrim/PyNifly/wiki/HKX-Animation-Format-(FO4---Skyrim))
- Example tags on a melee swing: `weaponSwing`, `HitFrame`, `EarlyExit`, `PairEnd`. Killmoves use `HitFrame` plus `SyncDeferDeath`, `PairEnd` (snippet) — [Nexus wiki: Animation In Fallout 4](https://wiki.nexusmods.com/index.php/Animation_In_Fallout_4)
- Community-compiled FO4 annotation and event list (unverified, no author or date). Entries relevant to creatures:
  - Locomotion: `FootLeft/FootRight/FootFront/FootBack/FootDown/FootSprintLeft/FootSprintRight`, `SyncLeft/SyncRight/SyncCycleEnd`, `MoveStart/MoveStop`, `turnLoop/turnStop`, `StartAnimationDriven`, `StartAllowRotation`.
  - Attack: `preHitFrame`, `HitFrame`, `attackStart`, `attackStop`, `AttackEnd`, `attackWinStart/attackWinEnd`, `attackPowerStart`.
  - Stagger: `staggerStart*`-type `staggerBackSmall/Medium/Large`, `staggerForwardSmall/Medium`, `staggerStop`, `staggerExit`, `MT_stagger*`.
  - Other: `Ragdoll`, `KnockDown`, `KillActor`, `KillMoveStart/End`, `Recoil`/`recoilStop`, `jumpStart/jumpFall/jumpLand`, `SoundPlay`, `SoundPlayAt`, `CullBone`/`UncullBone`, `HeadTrackingOn/Off`, `CharFXOn/Off`.
  - Creature paired names such as `pa_KillMoveFeralGhoulBiteNPCVictim` and `PairedYaoGuaiKillHumanStanding`.
  - Source: [Pastebin: FO4 Animation Annotations](https://pastebin.com/Z6qxqbNU)
- F4-OAR's runtime notes: the engine builds trigger arrays from clip annotations (`SoundPlay.*` and events such as `WeaponFire`). Behaviour-authored triggers are separate from clip annotations. Hardcoded graph transitions (e.g. exit at a fixed time) follow the graph, not the clip length — [F4-OpenAnimationReplacer](https://github.com/DCCStudios/F4-OpenAnimationReplacer)
- CK Actor "Attack Data" lists *animation attack events* with per-event overrides (damage mult, attack chance, strike angle, default 35°). It is used only when the event is a combat event — [falloutck.uesp.net: Actor](https://falloutck.uesp.net/wiki/Actor); "continuous" is misspelled "continous" in the CK — [Fallout Wiki: Actor](https://fallout.wiki/wiki/Resource:Creation_Kit/Actor)

### Inferences
- The "from scratch" graph must still follow FO4 conventions: one project per race (RACE behaviour graph), with all MT, Weapon and other behaviours registered as subgraphs of that project. Otherwise subgraph data on the race is unsupported. The practical route that the evidence supports is to clone a vanilla creature project (e.g. a quadruped such as the Deathclaw or Yao Guai) and rename or replace clips. Building a fresh graph is the hard path.
- Attack data on the RACE/Actor is keyed by the behaviour's attack event names. A new graph's attack events therefore need matching ATKD/ATKE entries. The engine only treats an attack as one when the event is listed as a combat event (inferred from the CK Attack Data description).
- AnimTextData is generated per plugin from the RACE subgraph data. A new creature needs its own generation run after the race, subgraphs and all clips exist. A missing or failed run is the likely cause of sliding or slow-motion locomotion and of furniture or sync misalignment (inferred from the listed outputs: speed translation, offsets, sync).

### Gaps
- I found no authoritative FO4 list of which graph variables and events the engine reads or sends for **creatures** specifically, e.g. `TurnDelta`, `IsAttacking`, `bSpeedSynced`, getup and ragdoll events, `iGetUpType` values. The likely primary sources are IceStormNG's tutorial (Nexus 56676) and Behaviour Graph Studio (a validator over the 531 vanilla graphs), but neither was readable. The next step is to dump the variable and event tables of a vanilla creature project with BGS or hkxpack.
- How the 19-digit AnimTextData file names are derived (CRC or hash of path?) is not documented in anything I could reach.
- I found no explicit statement of what the engine does when AnimTextData is missing entirely. Only symptoms appear (slow motion, no generation).
- Exact RACE field signatures (SGNM/SAPT/SRAF etc.) are not covered by the CK wiki text I could read. xEdit definitions would be the source.

## Skeleton and ragdoll (skeleton.hkx contents, editing, pitfalls)

### Takeaway
A creature's `CharacterAssets\skeleton.hkx` carries an animation `hkaSkeleton`, a separate ragdoll skeleton with hknp physics, and skeleton mappers in both directions, next to a `skeleton.nif`. Mappers are model-space transforms that pair bones with *different names* (`LArm_UpperArm` ↔ `Ragdoll_NPC L UpperArm`). FO4 does **no** load-time validation of mappers, so mistakes fail silently or at ragdoll time. No public tool yet writes FO4 hknp ragdolls or mappers back into a skeleton.hkx (BGS lists both as unfinished milestones). The established community route is HCT 2014 inside 3ds Max with a `rig.txt` bone list. Even so, I found no FO4-specific public guide for authoring a ragdoll.

### Cited Findings
- Each creature has its own `skeleton.nif` (e.g. `Meshes\Actors\Deathclaw\CharacterAssets\skeleton.nif`) and a `skeleton.hkx`, which supplies the joint order for `rig.txt`. Guides say "don't change the hierarchy of objects under the Root" (snippet) — [Nexus wiki: Animation In Fallout 4](https://wiki.nexusmods.com/index.php/Animation_In_Fallout_4)
- Rig workflow: unpack skeleton.hkx to XML (hkxpack) and keep only the `hkaSkeleton` bone list, in its original order. Wrap it in `[HAVOK SKELETON DEFINITION FILE]` / `[BONES START]` / `[END]`. In 3ds Max, run HCT `ExportSceneHkx` with Build Rig "From File" + "Use File Order", then "Write To Platform".
  - Pitfalls: bone names are case-sensitive (`LThigh` ≠ `LTHIGH`). Missing bones (camera bones, animobjects) must exist as dummy helpers under Root. Bone order must match the 64-bit skeleton. HKXPackGUI accepts only 32-bit hkx.
  - Source: [sfmnauts: fallout-4/animations.md](https://github.com/ballerfuturistic/sfmnauts/blob/master/fallout-4/animations.md)
- Filter order in the HCT Filter Manager matters (top to bottom). Power armour has its own skeleton and rig file (snippet) — [F4AK by ShadeAnimator, Nexus 16694](https://www.nexusmods.com/fallout4/mods/16694?tab=docs)
- A bone needs to exist in the skeleton even without geometry, e.g. for dialogue camera targeting. A single-bone skeleton cannot be adjusted, so at least one parent and one child bone are needed (snippets) — [Nexus forums: Custom skeleton/Animations tutorial](https://forums.nexusmods.com/topic/8813863-custom-skeletonanimations-tutorial/); [Fallout 4 HAVOK Guide](https://forums.nexusmods.com/topic/9329348-fallout-4-havok-guide/)
- `hkaSkeleton` layout (FO4 64-bit): name @+0x10, parentIndices (int16, -1 root) @+0x18, bones @+0x28, referencePose (hkQsTransform, 48 B) @+0x38 — [PyNifly wiki](https://github-wiki-see.page/m/BadDogSkyrim/PyNifly/wiki/HKX-Animation-Format-(FO4---Skyrim))
- **Mappers** (from the BGS engineering doc on the vanilla human `skeleton.hkx`): there are two mappers with 18 rows in total. Each row is `inverse(modelSpace_A[boneA]) * modelSpace_B[boneB]` in **model space**. Local-space reading gives errors up to 13.3 units and 2 rad. Each direction (A→B, B→A) needs its own mapper object, and shipped reverse mappers are not always mirror images (different row counts and pairings).
  - The ragdoll skeleton is unit-scaled to 5.96e-8. A 1% scaled rig exceeds the 1e-3 scale tolerance.
  - Shipped mappers contain **chain mappings**, whose semantics are not yet worked out, and exact duplicate rows.
  - Animation and ragdoll bone names differ, so name-matching cannot rebuild the pairings.
  - "Fallout 4 performs no validation at load time on the traced paths". Mapper checks exist only as debug-build warnings, so a malformed mapper is never reported in game.
  - Source: [BGS docs: skeleton-mapping-authoring.md](https://raw.githubusercontent.com/G-A-R-D-E-N/BGS/main/docs/skeleton-mapping-authoring.md)
- BGS 1.1.0 limits: skeleton-mapper write-back and chain-mapper authoring are incomplete. Ragdoll and physics are inspect/preview only; body-to-body collision and full ragdoll authoring are not implemented. Open milestones include "Write hknp ragdoll physics to skeleton.hkx" (#60), "Write the skeleton mapper back" (#61), "Explain why a skeleton's physics or ragdoll did not load" (#50) and "Collect community custom skeleton and HCT export fixtures" (#52) — [BGS repo](https://github.com/G-A-R-D-E-N/BGS); [BGS issues](https://github.com/G-A-R-D-E-N/BGS/issues?q=is%3Aissue)
- Ragdoll tuning mods write values directly into the Havok physics data embedded in the skeleton files. They warn that the modified skeleton must be the one the game actually uses (snippet) — [Ragdoll Physics, Nexus 76461](https://www.nexusmods.com/fallout4/mods/76461); [More Flexible Ragdoll 2, Nexus 110154](https://www.nexusmods.com/fallout4/mods/110154)
- In a third-party reimplementation, FO4 skeleton NIFs carry no per-bone bhk bodies. All ragdoll physics lives in the hkx, so without the hkx a death is a single capsule — [ByroRedux issue #6070](https://github.com/matiaszanolli/ByroRedux/issues/6070) (third-party engine, not vanilla behaviour)
- Older guides use the HCT "Rag Doll Toolbox" (3ds Max tools) for ragdolls. These predate FO4 and hknp, so they are not confirmed to apply (snippet) — [Sins of a Solar Empire forum: Havok export](https://forums.sinsofasolarempire2.com/398524/reply/2795946)
- **[Skyrim]** Beyond Skyrim's method for proportion changes inserts proxy nodes above bones in skeleton.nif and skin NIFs (ck-cmd `retargetskin`) and touches no hkx. Vanilla animations override bone transforms but not the proxies. You can discard body-plan parts or adjust proportions, but **you cannot add new bones** this way — [Beyond Skyrim AU: Editing Animation Skeletons](https://wiki.beyondskyrim.org/wiki/Arcane_University:Editing_Animation_Skeletons)
- **[Skyrim]** ck-cmd `importrig` builds skeleton NIF+HKX, including ragdoll and constraints, from an FBX. Colliders and constraints come from a named empty hierarchy, with ragdoll and hinge constraints set by custom properties. The pipeline also needs a `BoundingBox`/`BoundingBox_Box` empty and an `hkbMirroredSkeletonInfo.bonePairMap` in the character file for mirroring — [Beyond Skyrim AU: Implementation of Custom Animations](https://wiki.beyondskyrim.org/wiki/Arcane_University:Implementation_of_Custom_Animations)
- Gender skeletons are shared in FO4, so a skeleton edit affects both genders (snippet) — [Gender-Specific Skeletons, Nexus 40866](https://www.nexusmods.com/fallout4/mods/40866?tab=posts)

### Inferences
- A from-scratch FO4 ragdoll currently needs either HCT 2014 (3ds Max) physics authoring, which is not documented publicly for FO4, or a custom hknp writer. Writing both mappers by hand risks silent wrong ragdoll poses ("exploding" or twisted corpses), because the engine does not validate them.
- Cloning a vanilla creature skeleton.hkx with a similar body plan and keeping bone names and order lets the vanilla ragdoll and mappers survive. The cost is the same "no new bones" limit as Skyrim's proxy approach. Any added bone means rebuilding the animation skeleton, the ragdoll skeleton and both mappers.

### Gaps
- I found no FO4-specific report naming a "crash on death", "exploding ragdoll" or bone-count limit for custom creature skeletons, or a fix for them. Searches returned only general or Skyrim ragdoll-conflict notes.
- I could not confirm the hknp class layout in FO4 skeleton.hkx (e.g. `hknpRagdollData`, `hknpPhysicsSystemData`, constraint types, collision layers) from a readable source. The BGS ragdoll doc deliberately does not state it.
- I could not confirm whether HCT 2014's 3ds Max physics filters produce FO4-loadable hknp ragdolls. IceStormNG's tutorial probably covers this but was unreadable.

## Animations (compression, extracted motion, annotations, additive, retargeting tools)

### Takeaway
FO4 clips are `hkaAnimationContainer` files holding a binding plus an animation. Most clips are spline-compressed, but a large share of vanilla clips are `hkaLosslessCompressedAnimation`. Locomotion, killmoves and some furniture clips carry root motion in `hkaDefaultAnimatedReferenceFrame`, which HCT extracts from the Root bone. That root motion includes yaw for turn clips. The proven export path is 3ds Max + HCT 2014 64-bit (F4AK presets). Blender reaches it via FBX → HCT, or directly via PyNifly's new pure-Python HKX I/O. PyNifly does not yet write root motion, though.

### Cited Findings
- `hkaSplineCompressedAnimation` (FO4 64-bit offsets): duration, numTransformTracks, numFloatTracks, extractedMotion @+0x20, annotationTracks @+0x28, numFrames, numBlocks, maxFramesPerBlock (typically 256), blockOffsets, and the data blob.
  - Per-track 4-byte mask with quantisation: position 8/16-bit, rotation typically 48-bit (three 15-bit components plus a dropped largest one).
  - `hkaAnimationBinding` has `transformTrackToBone` and `blendHint` (0 normal, 1 **additive**).
  - PyNifly limitations: no root motion export, no float tracks, spline degree 0/1 only, all annotations on track 0.
  - Source: [PyNifly wiki: HKX Animation Format](https://github-wiki-see.page/m/BadDogSkyrim/PyNifly/wiki/HKX-Animation-Format-(FO4---Skyrim))
- Shiagur's request list (2026-03-19):
  - FO4 motion data are uncompressed coordinates in `hkaDefaultAnimatedReferenceFrame` (third-person run/walk, killmoves, some furniture). Havok extracts it from the Root bone.
  - Additive clips subtract the first frame from every frame (e.g. `MinigunTurretSweep.hkx`, `WPNFireAutoAdditive.hkx`).
  - Paired clips hold a 4×4 offset in `hkSimpleLocalFrame`.
  - F4AK uses rotation tolerance 0.000010 instead of HCT's default 0.001. 48-bit instead of 40-bit quantisation fixed weapon jitter.
  - Sample: `Animations\MT\Neutral\RunForward.hkx`.
  - Source: [PyNifly issue #381](https://github.com/BadDogSkyrim/PyNifly/issues/381)
- In a vanilla census, 856 FO4 clips are `hkaLosslessCompressedAnimation`, and 744 of them pair with `hkaDefaultAnimatedReferenceFrame`. The rest are spline — [ByroRedux issue #5897](https://github.com/matiaszanolli/ByroRedux/issues/5897). Turn clips put their rotation in the reference-frame yaw (0 → −1.5708 rad, translation <5e-5), so a converter that drops the yaw makes turn clips not turn — [ByroRedux issue #6241](https://github.com/matiaszanolli/ByroRedux/issues/6241). Malformed reference-frame data silently drops root motion — [ByroRedux #5894](https://github.com/matiaszanolli/ByroRedux/issues/5894) (third-party audits, Oct 2026)
- F4-OAR's `preserveExtractedMotion` keeps the replacement's `hkaDefaultAnimatedReferenceFrame`. The author says to enable it only for root-motion donors. Replacement bone names must match the skeleton. A startup crash in `ReadBoundAnimDataBinary` is attributed to corrupt or unrelated hkx in the load order — [F4-OpenAnimationReplacer](https://github.com/DCCStudios/F4-OpenAnimationReplacer)
- Tools:
  - F4AK (ShadeAnimator) targets 3ds Max and is "a bit outdated" (some tools need compatibility mode). HCT 2014 is not included (snippet) — [F4AK, Nexus 16694](https://nexusmods.com/fallout4/mods/16694)
  - Blender has no HCT plugin. The workaround is to export FBX with Andrelo1's FBXImporter and convert through HCT (snippet) — [Blender Rig Framework (deprecated), Nexus 60005](https://www.nexusmods.com/fallout4/mods/60005)
  - Blender Animation Rig and Guide 2.6.0 (snippet) — [Nexus 82537](https://www.nexusmods.com/fallout4/mods/82537)
  - hkxpack (Dexesttp) packs and unpacks hk_2014.1.0-r1 TagXML. Animation export moved to hkxanim, and partial cloth data is a known issue — [Dexesttp/hkxpack](https://github.com/Dexesttp/hkxpack)
  - HkxPack-Plus (unpack/pack/quick/verify, 0.1.6-beta) — [Nexus 107755](https://www.nexusmods.com/fallout4/mods/107755)
  - Behaviour Graph Studio 1.1.0 (.NET 8, MIT) edits behaviour, character and project files. It validates broken references and missing clips and scans the mod list (`--scan-modlist`, `--scan-clips`). Animation import, retargeting and HKX export are future milestones (#63–65) — [BGS repo](https://github.com/G-A-R-D-E-N/BGS)
  - A Skyrim↔FO4 bidirectional animation converter (dagobaking, Patreon) exists but was not examined — [Patreon post](https://www.patreon.com/dagobaking/posts/bidirectional-4-152761722)
- An IceStormNG tutorial notes that, because of distribution restrictions, you must find the Havok Animation Tool yourself (snippet) — [Nexus 56676](https://www.nexusmods.com/fallout4/mods/56676)
- **[Skyrim]** HKX clips keep only root Z translation and X/Y rotation. The engine drives the rest, so movement-type walk and run speeds must match the clips, and blend weights in the graph must match the authored speeds — [Beyond Skyrim AU: Custom Animations](https://wiki.beyondskyrim.org/wiki/Arcane_University:Implementation_of_Custom_Animations)

### Inferences
- FO4 differs from that Skyrim rule: its locomotion clips *do* carry extracted motion. AnimTextData `--speed` (AnimationSpeedInfo) is what translates clip speed into movement. Getting a new creature's walk and run right therefore needs extracted motion on the clips, MOVT speeds that agree with it, and a regenerated AnimTextData with `--speed` (inferred from the subgraph-wiki outputs and the clip census).
- To produce root motion today you need HCT's motion-extraction filter. PyNifly cannot write it yet.

### Gaps
- I found no documented HCT filter settings for FO4 motion extraction (e.g. which axes are allowed) or a "required annotation" set for creature locomotion. The F4AK guide on Scribd was truncated.
- The exact FO4 behaviour of `bSpeedSynced` and clip speed sync is undocumented in anything I could reach.

## Records (RACE fields, attack data, MOVT, BPTD, CK issues)

### Takeaway
On the record side, a creature needs:
- A RACE with Skeleton (`skeleton.nif`) and Behavior Graph (root project) on its body data.
- Subgraph data whose Behavior Paths are subgraphs of that project.
- Animation attack events in Attack Data that match the graph's events.
- Movement types whose speeds match the clips.
- A BodyPartData (BPTD) whose part nodes name skeleton bones, for VATS, dismemberment and gore.

Public FO4 CK documentation for the individual RACE subrecords is thin. The usual community advice is to duplicate a vanilla creature race, which also satisfies the template constraints.

### Cited Findings
- The Race page on the CK wiki mirror lists only top-level fields: Base Actor Values, Movement, Specials, Flags, XP Value, Size, Flight, Orientation Limits, Copied Data, Keywords. It has no detail on body data or behaviour — [Fallout Wiki CK mirror: Race](https://fallout.wiki/wiki/Resource:Creation_Kit/Race)
- The Actor and Race pages cover the Race's Behavior Graph (.hkx) and Skeleton (.nif) entries (snippet) — [falloutck.uesp.net: Actor](https://falloutck.uesp.net/wiki/Actor)
- BodyPartData is a skeleton model plus body-part entries. Each entry has a VATS/CK name, a part type (the limb according to the skeleton model, used by `Dismember()`), a part node marking where gore appears and where severable limbs are cut, VATS targeting, geometry segment indices for dismemberment, actor-value crippling conditions, and explosion settings (snippet) — [falloutck.uesp.net: BodyPartData](https://falloutck.uesp.net/wiki/BodyPartData). Part-type strings such as `Torso`, `Head1`, `LeftArm1`, `RightLeg3` must match what scripts pass to `Dismember` — [falloutck.uesp.net: Dismember](https://falloutck.uesp.net/wiki/Dismember_-_Actor)
- A custom creature mod reported only decapitation working, with a floating vertex on the head stump. This is a typical segment-index/BPTD mismatch symptom (snippet, anecdotal) — [Nexus 53407](https://nexusmods.com/fallout4/mods/53407)
- A custom "mannequin" race got aggressive behaviour by reusing Feral Ghoul attack templates and AI (snippet) — [Nexus forums: custom races in FO4](https://forums.nexusmods.com/topic/8370183-custom-races-in-fo4)
- A one-field RACE edit in FO4Edit (the animation multiplier) slows ghouls to 70–80%. The RACE carries a global animation speed multiplier (snippet) — search result for Feral Ghoul Slower Speed Fix, via the movement search ([Nexus 105948](https://www.nexusmods.com/fallout4/mods/105948), page not verified)
- Renamed or new graphs were reportedly "not recognized" by the CK. The usual advice is to copy an existing race's behaviour files and animations, then edit. This comes from a thread possibly about Skyrim (snippet) — [Nexus forums: animations in skyrim](https://forums.nexusmods.com/topic/3367530-animations-in-skyrim)
- IceStormNG's FO4 tutorial (2021-12-18, v1.00, commissioned by VelvetGoat) is "strictly for advanced users". It covers new creatures and NPC behaviours and is the only dedicated FO4 new-creature guide found. Its content could not be read (snippet) — [Nexus 56676](https://www.nexusmods.com/fallout4/mods/56676); mirror listing [Schaken-Mods](https://schaken-mods.com/forums/topic/12021-new-creature-behavior-and-implementation-tutorial/)
- BGS plans a "full character/race authoring workspace" (#28, opened 2026-08-15) and "Resolve race to skeleton and body mesh" (#56). No such tool exists yet — [BGS issues](https://github.com/G-A-R-D-E-N/BGS/issues?q=is%3Aissue)
- **[Skyrim]** ck-cmd `retargetcreature` copies a donor Havok project and generates an ESP with idles, sound descriptors and movement types. `importanimation` converts FBX clips using the donor behaviour folder and retargeted cache.
  - Pitfalls: a trailing slash in folder paths crashes ck-cmd. An uppercase letter in the project filename stops animationdata from being generated. SE hkx can't be turned back to XML with ck-cmd (use hkxconv).
  - Tools: Skyrim Behavior Tool (use Jonahex's fork) and Haviour.
  - Source: [Beyond Skyrim AU: Custom Animations](https://wiki.beyondskyrim.org/wiki/Arcane_University:Implementation_of_Custom_Animations)
- **[Skyrim]** "Creating a completely new graph for a completely new creature is nigh-impossible"; start from an existing race (snippet) — [Nexus forums: creatures with custom skeletons and animations to skyrim](https://forums.nexusmods.com/topic/702503-creatures-with-custom-skeletons-and-animations-to-skyrim)
- I found no evidence that ck-cmd, HKX2E or hkxconv support FO4's hk_2014 files. Searches turned up only FO4-specific tools (hkxpack, HkxPack-Plus, BGS, PyNifly) — [search summary; PyNifly wiki](https://github-wiki-see.page/m/BadDogSkyrim/PyNifly/wiki/HKX-Animation-Format-(FO4---Skyrim))

### Inferences
- Skyrim made custom creatures feasible through a toolchain of donor-project retargeting (ck-cmd), a GUI behaviour editor and open 2010 class definitions. FO4 lacks most of it: there is no ck-cmd equivalent, hknp physics replaces hkp, and mappers and ragdolls cannot be written by open tools. BGS (2026) is the first FO4 behaviour editor, but ragdoll and mapper writing are still on its roadmap. FO4 "from scratch" in practice means: own mesh and skin, a cloned and renamed vanilla project, behaviour and skeleton.hkx (with ragdoll) from a similar body plan, new clips from HCT, and a new RACE with subgraph data plus regenerated AnimTextData.
- Duplicating a vanilla creature RACE in the CK keeps the Skeleton, Behavior Graph and subgraph template consistent. The wiki notes duplication does this automatically. It is the lowest-risk start before you repoint paths.

### Gaps
- I found no readable documentation of the FO4 RACE subrecords (MODL after NAM3, SGNM/SAPT/SAKD/STKD/SRAF), MOVT fields, impact data sets or the hit/ragdoll settings for creatures. xEdit's FO4 definitions are the authoritative next source.
- I found no FO4 forum report of CK crashes when adding a new race or creature that I could read.
