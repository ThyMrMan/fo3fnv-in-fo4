# FNV idle animations on Fallout 4

**Code:** `fo4_import/havok/human_clip.py` (clips), `fo4_import/spike/idles.py`
(records), `tes4_export/record_types/dialog_misc.py` (line idles in the export).
Status lives in [ROADMAP.md](ROADMAP.md#fo4); this file holds the design and
measurements.

## <a id="census"></a>What FNV has (measured 2026-10-19)

- **1,597 IDLE records.** 1,212 point at a `.kf`, 807 of them under
  `characters\_male`. 1,098 carry conditions; 30 test a named actor,
  reference, quest stage or variable (Doc's chair moments among them). 512
  have no parent: loose idles and the roots of FNV's idle trees.
- **Who plays them.** Converted scripts make 199 `PlayIdle` calls in 84
  scripts. Dialogue plays more: an FNV response can name a **speaker idle**
  (INFO `SNAM`) and a **listener idle** (`LNAM`), 333 and 1 of them in 320
  INFOs, 115 distinct idles (97 human, 18 creature). The exporter dropped
  both until 2026-10-19; it now writes `Response[i].SpeakerIdle` /
  `.ListenerIdle` (the SNAM or LNAM after the i-th TRDT).
- **Doc's 23.** All are loose. The psych test plays its idles as speaker
  idles, not by script: `VCG01DocCardPoint01-03` (14 lines),
  `VCG01DocShrug` (4), `VCG01DocWhoaThere` (1) and `VCG01DocGiveMirror`
  ("How'd I do?", `00104BF8`). The result scripts that would play
  `VCG01DocRorschachTest1-3` are commented out in FNV itself; the
  Rorschach clips are reached only through their animated objects (ANIO
  `VAODocRorschach1`). Every one of these clips is **seated**: FNV's pelvis
  sits at z 36.8 over the actor's origin with the feet 21-31 units
  forward. `VCG01DocGiveMirror` also animates `Weapon` and
  `##Dummy01_Reflectron01` (the mirror). `SpecialIdle_NVDocHelpPlayerup.kf`
  and `SpecialIdle_NVDocChairLeftExit.kf` are missing from FNV's archives.
- **Scripts that wait on animations.** 69
  `GetAnimationVariableBool("bAnimPlaying")` object-animation checks in 34
  scripts always read false on FO4: about 44 test "not playing" and go on,
  about 10 test "playing" and never fire. No quest waits on an actor's idle
  finishing.

## <a id="mechanism"></a>How Fallout 4 plays an arbitrary clip

No behavior graph is edited. 235 vanilla IDLEs are **dynamic idles**:
`DNAM` names a behavior graph, `ENAM` a dynamic-idle event the graph
declares (`dyn_Activation`, `dyn_ActivationLoop`, `dyn_Flavor`,
`dyn_talkGeneric`...), `GNAM` the clip, loaded by path. For humans,
`RaiderRootBehavior.hkx` with `dyn_Activation` (55 records; 128 vanilla
INFOs use such an idle as a speaker idle, for example `IdlePointing`,
`MTCoughing`). A loose one has parent 0, DATA flag 0x01 and no loop
seconds (91 of 98 vanilla loose `dyn_Activation*` idles).

**Seated actors.** The furniture graphs (`FurnitureBehavior.hkx`,
`FurnitureNoMirrorBehavior.hkx`) declare the same `dyn_*` events. Vanilla's
seated talk idles (`RaiderTalkFurniture_PoseB_*`) name the root graph, but
with `dyn_talkGeneric` and a `$(Subgraph)\...` clip. Every vanilla seated
`dyn_Activation` idle names the furniture graph with an absolute clip
(`IdleSitFemaleReactingToViolence`, `IdleExtractionChair`,
`IdleCryoBangOnGlass`, `FurnitureBehavior.hkx`). Chairs
(`AnimFurnChairSitAnims`, which converted FNV seats carry) select
`FurnitureBehavior.hkx` in `HumanRaceSubGraphData`. No vanilla speaker idle
names a furniture graph.

## <a id="clips"></a>1. Clips: FNV .kf to FO4 .hkx

`HumanClips.write` decodes the `.kf` (`kf_decode`), retargets it onto FO4's
`Actors\Character\CharacterAssets\skeleton.hkx` (95 bones, read once from
`Fallout4 - Animations.ba2`) and writes a Havok 2014 64-bit spline clip,
one track per FO4 bone (`anim_fo4.write_fo4_animation`).

- **Retarget.** `clip_retarget.retarget_clip` repeats each FNV bone's
  world rotation change on its FO4 bone, measured from a pose of FNV's
  skeleton that matches FO4's rest pose. The matching pose
  (`matching_pose`) turns each FNV part (limbs, spine, neck, each finger
  joint, the hand toward the middle finger) about its joint onto the
  direction of the FO4 part it maps to; toes, the head and finger tips take
  their leader's turn. FNV's pelvis drives FO4's `COM` (both carry the
  whole body), which also takes the pelvis's translation change. Unmapped
  FO4 bones (twist bones, weapon and camera bones) keep their rest pose.
- **Measured** on `SpecialIdle_CardPoint01` and `..._DocGiveMirror`: FO4's
  joints land within 1-5 units of FNV's (FO4's torso is about 8 units
  taller, so the head and hands sit higher). FO4's own neutral chair loop
  holds `COM` at z 36.3 with the feet 27 forward; the converted FNV seated
  clips hold it at 38.0 with the feet 21-30 forward, so FNV's seated
  clips fit FO4's seat height. Each clip converts in about 0.7-0.9 s.
- **Events.** Every clip carries `HeadTrackingOff` at its start and
  `HeadTrackingOn` at its end, as vanilla dynamic idles do. The vendored
  writer wrote no annotations; it now writes them on track 0, where vanilla
  keeps them. FNV's text keys (sounds, `blend:`) are not carried yet.
- **Round trip.** The writer's output reads back through the vendored
  reader with rotation error under 1e-7 (vanilla `Hancock_PlayingKnife`
  and `IdleSitFemaleReactingToViolence`).
- **Not covered yet:** a prop's motion below its chain and its visibility
  keys ([converted props](#converted-props)), creature clips (18 of the 115 line
  idles), female-only clips, and root motion (FO4's dynamic idle plays in
  place; the clip's root track is dropped).

### <a id="props"></a>Props

FNV pairs a prop mesh with an idle through an ANIO record (`DATA.Idle`);
the smoking idles (`NPCSmokingIdle`, `WallLeanSmoking`,
`LooseSmokingStanding`) show `AnimObjects\aoCigarette.NIF`, hung from
`Bip01 R Hand` (its `Prn`). The clips themselves name no prop.

FO4 loads a prop by events in the clip that name its ANIO's EditorID.
Vanilla `to_smoking.hkx` carries `AnimObjLoad.AnimObjectCigarette` at 0,
`cigOn` and `AnimObjDraw.AnimObjectCigarette` at 0.67 s, and `cigDrag` on
a puff (the prop's own graph lights the tip). `to_normal.hkx` carries
`AnimObjUnequip`, the ANIO's unload event. The prop hangs from
`AnimObjectR1`, a bone under `RArm_Hand` at rest on the hand. Every vanilla
smoking clip holds it at t (11.01, 0, -1.34), turned -35° about z.

`havok/anim_props.py` plays FNV's prop as vanilla's own object
(`data/anim_props.json`), with no ANIO record or mesh converted. A
converted clip whose idle has a listed prop gets:

- the load and draw events at its start, plus the object's start events;
- FNV text keys turned into the object's events (the inhale sound
  `NPCIdleSmokingIn` → `cigDrag`);
- `AnimObjUnequip` at its end;
- the prop bone held as the table's vanilla clip holds it, read at the
  frame that clip draws the object (frame 0 when it never does);
- every prop its ANIO records name, one per prop bone (the scientist
  terminal idles show a clipboard in the left hand and a pencil in the
  right) with a single `AnimObjUnequip`.

**Finding a vanilla object:** `tools/creature/vanilla_anim_props.py` scans
`Fallout4 - Animations.ba2` for `AnimObjLoad.<object>`. For each object it
lists the model and the bone its mesh's `Prn` names, then the clips that
load it, earliest draw first, and the events beside the draw. A row's
bone must be on the same hand as the FNV mesh's `Prn`. A vanilla mesh
hangs from its own bone, so a left-hand object can't stand in for a
right-hand FNV one. Most events beside the draw belong to the actor
(`HeadTrackingOff`, `PathTweenerEnd`). Only the object's own (`cigOn`,
`On`) go in `start`.

| FNV mesh | FO4 object | Bone | Idles |
|---|---|---|---|
| `aoCigarette`, `Benny_cigarette` | `AnimObjectCigarette` | R1 | smoking |
| `RepairTool01` | `AnimObjectWrench` | R1 | repair floor/wall, workbench |
| `aoSyringe` | `AnimObjectMedX` | R1 | doctor heal, revive |
| `Stempax` | `AnimObjectStimpak` | L1 | `3rdPSpecialIdleStimpak` |
| `aoScientistClipboard` | `AnimObjectClipboardLeftHand` | L1 | scientist inspect terminal |
| `aoExamPencil` | `AnimObjectPencil` | R1 | exams, inspect terminal |
| `aoChalk` | `AnimObjectChalk` | R1 | blackboard |
| `aoBarDishRag`, `BarKeepRag` | `AnimObjectDishRag` | R1 | bartender wipes |
| `SandManKnife` | `AnimObjectSandmanKnife` | R1 | Mister Sandman kills |

These have no vanilla stand-in and are converted instead:

- `aoTestPaper`: it's a right-hand prop, and FO4's `AnimObjectPaper` is
  left-hand only.
- `aoBarGlassEmpty`: it's a left-hand prop, and `AnimObjectDishRag_glass`
  is right-hand only.
- `BlacksmithHammer`: `AnimObjectBlacksmithForgeHammer`
  (`AnimObjectHammer_Wall.nif`) is loaded by no clip, so there's no hold to
  copy.

A prop with no entry in the table is converted instead ([converted props](#converted-props)).

### <a id="converted-props"></a>Converted props

`havok/fnv_props.py` and `spike/idle_props.py` convert an FNV prop the table
has no vanilla stand-in for. It needs its mesh in the export and a `Prn`
naming an FNV skeleton bone.

**How FNV places a prop.** FNV hangs a prop's mesh from that skeleton bone.
An idle's clip can also move the mesh's own nodes:
- Doc's Reflectron, the Pip-Boy, the Rorschach cards, the guitar and Benny's
  9mm all move this way;
- the test papers, chalk, meals and drinks hold still.

**How FO4 places a prop.** FO4 hangs a prop from a prop bone that the clip
moves. `AnimObjectR1` and `L1` rest exactly on the hands (identity under
`RArm_Hand`/`LArm_Hand`). `AnimObjectA` rests on `Root`.

**What the conversion does.**

- **Record:** an FO4 ANIO on FNV's FormID and EditorID. Its model is the
  converted mesh, and BNAM is `AnimObjUnequip`. Record flag `0x200` comes
  from Fallout4.esm, where all 145 ANIO records carry it.
- **Mesh:** `<name>_prop.nif`, converted with its chain flattened. The chain
  runs from the root down to the node that holds every shape. The mesh is
  hung (`Prn`) from the FO4 prop bone: R1 or L1 for an FNV hand, A for
  anything else. It is hung as it is written (`statics.prop_assets`),
  because idles are written after the build's Elric pass; a prop with Havok
  input runs through Elric right then.
- **Clip:** the prop bone's track carries the chain's transform on every
  frame, with FNV's clip channels where the clip moves a chain node.
  - On a hand, the transform is turned from FNV's hand frame into FO4's, by
    the same fixed rotation the retarget gives the hand.
  - That rotation is about a half-turn about the hand's long axis, plus a
    3.5° tilt.
  - On another bone (the guitar's pelvis), the transform is in the clip's
    root space, following that FNV bone.

Lost: motion below the chain's end, such as a single card's own swap or the
9mm slide, and visibility keys (the Pip-Boy is hidden for a tenth of
`GivePipBoy` in FNV).

Not converted: a prop whose `Prn` is missing. Benny's two
`weapons\1handpistol\9mm.nif` ANIOs are like this, and the same idle shows
`nv_9mm.nif` on the right hand.

**Checked offline:** in 2026-11-07, the built idles had six props converted:
- the test paper and the Rorschach card are held still;
- the Pip-Boy sits 10 units off the left hand;
- the guitar is on the root at hip height (79 to 83 units up);
- Doc's mirror is within 5 units of the hand for most of the clip, and 183
  units away before he picks it up, where FNV puts it too;
- Benny's 9mm sits 9 units off the hand.

On every sampled frame, each one's world turn matches FNV's
(`tests/test_fo4_idle_props.py`). None has been played in game.

## <a id="records"></a>2. Records: FNV IDLE as an FO4 dynamic idle

`spike/idles.py`, `Idles`: an FNV idle the build uses becomes an FO4 IDLE
on FNV's own FormID (a new record; nothing already built moves).

- **Used:** a converted script's `Idle` property (by EditorID, through
  `attach`) and a line's speaker and listener idles (`pack_info` writes
  `SNAM`/`LNAM` per response, as FNV has them). `VCG01DocGiveMirror`
  replaced the earlier stand-in (`DialogueGiveItem`); being seated, it plays
  only from VCG01's stage-30 script, not on "How'd I do?" ([seated](#furniture)).
- **Fields:** `DNAM` the root graph (seated clips are left out,
  [seated](#furniture)), `ENAM` `dyn_Activation`
  (`dyn_ActivationLoop` with 255/255 seconds when FNV loops forever),
  `GNAM` the clip under `Actors\Character\Animations\<plugin>\` (FNV's path
  below `characters\_male\`), FNV's conditions (`conditions_of`, the
  dialogue's form map), `ANAM` FNV's parent and previous when they are
  built (else 0, loose flag 0x01), FNV's replay delay. FNV's loop counts
  other than "forever" play once.
- **Left out:** an idle whose clip is missing (2 of Doc's) or is neither a
  human clip nor in an own rig's folder. A rig's idles play on that rig's
  graph with vanilla creatures' `dynamicAnim` events
  ([rig idles](fo4_own_rig.md#idles), built 2026-11-06).
- **Idle trees:** only the ambient one is built ([trees](#trees)).

## <a id="trees"></a>Ambient idle tree (built 2026-11-06, not played)

`Idles._ambient_tree`. FNV's 1,098 conditioned idles sit in 109 trees,
but most of them are not ambient:

- 394 furniture idles (seated; they crashed in October, [seated](#furniture));
- 160 dialogue gestures, 60 hit reactions and 44 V.A.T.S. melee moves,
  which FO4's own graphs already play.

The FNV root's `AnimGroupSection` does not tell them apart (hit reactions
and `GeneralIdles` both read 135), so the ambient root is named by EditorID:
`GeneralIdles` (Fallout3.esm uses the same name). It is built only by the
plugin owning it; DLC exports carry their master's idles.

**What vanilla does.** `ActionIdle` (AACT `00013002`) has 27 children:
one root per creature graph, plus three human ones.

- `WeaponAltIdleRoot` names `WeaponBehavior.hkx`, `MeleeAltIdleRoot` names
  `MeleeBehavior.hkx`, and `FurnitureIdleRoot` names `FurnitureBehavior.hkx`.
  So the engine runs `ActionIdle` for humans, picking roots by graph.
- A group node holds only EDID, conditions, DNAM (the graph), ANAM and DATA:
  no event (ENAM), no clip (GNAM), not loose.
- The roots' parent is `ActionIdle`, and each root's previous is 0.

No vanilla root names the human root graph (`RaiderRootBehavior.hkx`), so
whether the engine plays this tree is untested. If it doesn't, nothing else
changes.

**What is built.** FNV's root goes under `ActionIdle`, with group nodes
shaped as vanilla's. Leaves are the standing dynamic idles ([records](#records)),
each played once. Each node keeps FNV's conditions and replay delay; its
previous is FNV's, skipping left-out siblings. A node is left out, with
everything below it, when:

- its conditions don't convert (counted `ambient idle left out
  (conditions)`);
- it needs the weapon drawn (`IsWeaponOut == 1`, not ORed). FO4 plays those
  on the weapon graph (`WeaponAltIdleRoot`), and FNV's weapon-type values
  don't map;
- it is a group with nothing kept below it.

**Sitters stay seated.** FO4 played the tree on seated NPCs: they stood
up, played the idle and sat down again. FNV's root has no sitting test,
because FNV's engine never offered that tree to a sitter. Vanilla FO4 gates
its standing talk roots with `GetSitting == 0` (`CreateABotTalkRoot`,
`PowerArmorTalkWeaponRoot`). The root and every loose idle on the standing
graph (a line's speaker or listener idle) now carry that test first, ahead
of FNV's own conditions so their OR groups stay intact (`idles.STANDING`).

**Retry rate (2026-11-08, after play: Captain Parker and Bert Gunnarsson
in Aerotech swatted and scratched every 2–10 s, initiateStart in the trace).**
An idle actor retries its idle tree every `fAIIdleWaitTime`: 1.0 s in FNV
(the `fld1` default where FalloutNV.exe registers it, setting object
`0x11CDD30` per JIP's `settings_enum.h`), 0.1 s in FO4 (Fallout4.esm GMST).
FNV's own throttle is a `GetRandomPercent < 1` on `NPCGeneralIdles`, sized
for one try a second, so FO4 passed it ten times as often.
- *A second random gate failed (1108d, played 2026-11-09).* A
  `GetRandomPercent < 10` on the root left the gaps unchanged (Bert: 5.2,
  3.9, 4.8 s before; 2–10 s after). A random test cannot space FO4's idles:
  its tries are too frequent, or the tests share one draw.
- *Replay delays instead (built 2026-11-09, not played).* Vanilla spaces
  ambient-tree leaves by Replay Delay (`FeralGhoulSitIdle` 21 s,
  `DogIdleFlavorDefault_PoseASit` 25 s; humans have no random ambient tree).
  `Idles._space` gives each kept leaf of a group FNV's mean gap for that
  group, `FNV_IDLE_WAIT` over the chance of the `GetRandomPercent <` tests on
  it and its parents, times its kept leaves, or FNV's own delay if longer.
  `NPCGeneralIdles` (1%, 6 leaves): 600 s each, so at most six general
  idles per 10 minutes, against FNV's mean of one per 100 s.

The tree's own idles are in the form map, for `IsLastIdlePlayed`. Its
form-list tests (`GetEquipped`, for example `FistWeaponsList`) are made the
way a line's are ([condition forms](fo4_pipeline.md#dialogue-conditions)).

Expected from FNV's 31 nodes:

| Branch | Result |
|---|---|
| Drunk walk ×3 (`NVDrunks`, `NVBuzzed`) | Built |
| Smoking (`SmokerFaction`) | Built |
| Swatting, scratching ×2, nose-picking ×2, nail-biting (`GeneralIdleFaction`) | Built |
| Pip-Boy (`GetStageDone` on no quest) | Left out: it never passes in FNV either |
| Weapon loiters (2hr, 2ha) | Left out: they need the weapon drawn |
| `PlayerOrNPCIdles` / `SIRelaxed` | Left out: `GetArmorRating` has no FO4 function |

**Unverified.** The tree passes `GetCurrentAIProcedure != 4 / != 10` (FNV:
dialogue, eat) through unchanged. Those values come from the Oblivion
lineage. Vanilla FO4 tests only 47 and 50, and no FO4 value list exists
offline.

## <a id="furniture"></a>3. Seated idles (Doc's chair)

- Doc sits through FO4's own furniture: the chair keeps FNV's markers and
  FO4's sit animations play ([furniture](fo4_spikes.md#spike-2-furniture)).
- A seated FNV clip carries the whole seated pose; its `COM` height
  matches FO4's chair loop (above), so Doc stays on the seat.
- **Root graph on a seated actor crashed (played 2026-10-19).** The first
  build named the root graph for every idle. Four seated speaker idles
  played on Doc (`VCG01DocWhoaThere`, `SitChairTalkPlayerD`,
  `SitChairTalkPlayerA`, `VCG01DocGiveMirror`). When his package changed
  at VCG01 stage 40 and he left the chair, FO4 reset his graph to its base
  state (`ActionInitializeGraphToBaseState`, `InitializeMTGraph`), and
  Havok crashed cloning nodes in that reset (`hkThreadMemory::blockAlloc`
  under `hkbBehaviorGraph::getOrCreateNodeClone`). The clips' array
  headers all carry Havok's do-not-free flag, which rules the files out as
  the source. Vanilla never plays a root-graph `dyn_Activation` on a
  seated actor.
- **The furniture graph crashed too (played 2026-10-19).** Named
  `FurnitureBehavior.hkx`, as vanilla's seated `dyn_Activation` idles
  (played by script, never as speaker idles) are, `VCG01DocGiveMirror` on
  "How'd I do?" did not play (the line ended in 0.2 s). About 2 s later
  the game crashed freeing a behavior graph on a job thread
  (`~hkbBehaviorGraph` → `hkThreadMemory::getMemoryStatistics`, from
  `BSResource::EntryDB<BShkbHkxDB>::FlushReleases`). That looks like the
  idle's graph loaded as a resource of its own. A vanilla clip round-tripped
  through our writer matches FO4's object headers byte for byte, apart
  from the spline data's size and a null resource name, so the clips are
  not the suspect.
- **Seated clips are left out of lines** (`idle left out (seated)`). Played
  2026-10-19 with every seated clip left out: no crash at the hand-over or
  the stand-up.
- **Played by script on the furniture graph, a seated clip works (played
  2026-10-19).** Single-change test: `VCG01DocGiveMirror` names
  `FurnitureBehavior.hkx` (`dyn_Activation`, absolute clip) and is played
  only by FNV's own VCG01 stage-30 script (`PlayIdle`); no line carries
  it. The hand-over played, with no crash then or at the stand-up. That
  is vanilla's shape for scripted seated idles. So the earlier crash came
  from the trigger, a seated clip as a line's speaker idle, which vanilla
  never does. `Idles.named` (a script's `Idle` property) builds seated
  clips this way; `Idles.line` still leaves them out.
- **Seated line idles by script crashed (played 2026-10-19, removed).**
  Each line whose first-response speaker idle was seated carried a helper,
  `TES4_LineIdle` (TopicInfo; `OnBegin` played the idle on the speaker),
  and no `SNAM`. That covered 22 lines (card points 14, shrug 4, "Whoa
  there", `SitChairTalkPlayerA`/`D`, "How'd I do?"). The animations played
  through the psych test. Then the game crashed in a plain per-frame graph
  update on Doc (`hkbStateMachine::updateSync` under
  `hkbBehaviorGraph::update`, a job thread) during the trait intro, whose
  lines carry no idle. Suspected, not confirmed: many furniture-graph
  dynamic idles back to back, a line's idle starting while the last still
  plays, leave the graph broken. The single scripted mirror call never did
  that. Removed: seated line idles stay left out, and only a script's
  `Idle` property plays a seated clip. Untried: the vanilla seated-talk
  route (root graph, `dyn_talkGeneric`) and special furniture (a base-game
  `HumanRaceSubGraphData` edit). A clip is seated when its first frame has
  both thighs near level (drop over length under 0.5) and the pelvis
  below 0.75 of its rest height (`human_clip.SEATED`). Over the 20 clips
  the region uses, the split is clean: Doc's 4 and FNV's `SitChairTalkA`/
  `D` measure 0.54 pelvis and 0.04-0.21 drop; standing clips measure
  0.94-0.98 and 0.92-1.00; the crouching thug clips measure 0.66-0.83.
  It is measured from the clip, not authored: FNV plays a special idle
  over whatever the actor is doing.
- FNV's own chair stand-up (`NVchairStandDoc`, a tree idle conditioned on
  Doc) is left to FO4's furniture exit.

## <a id="off"></a>Switched off (2026-10-19)

With the line route removed, the mirror on its stage-30 script still
crashed once, intermittently: in the player's furniture-graph release as the
looks menu opened (`hkThreadMemory::blockAlloc` under
`BSBehaviorGraphSwapSingleton::KillSDM`), seconds after Doc's clip played. All
four crashes are in Havok memory or graph code after an FNV clip played,
across three graph routes, which points at the clip data (heap corruption
from a clip the engine decodes badly) more than at any route. One structural
difference was found: our clips carried a constant scale channel on 55 of 95
tracks (skeleton.hkx's bone scales are off 1 by up to 4e-5), which vanilla
clips never have. Fixed in code (`human_clip.UNIT_SCALE`); the track masks
now match vanilla's shape. That it was the cause is unproven.

`idles.CONVERT` was off then (removed 2026-10-21: [standing](#standing)):
builds wrote no IDLE, clip or line idle, as before this work. Next test, one change: a vanilla clip re-encoded by our writer
played as the mirror (isolates the encoder), then the scale-fixed FNV clip.

## <a id="encoder-test"></a>Encoder test (built 2026-10-19, played 2026-10-21)

**Question.** Do clips our writer encodes break Havok, whatever the
motion? All four crashes came after an FNV clip played, on three graph
routes, in Havok memory or graph code. A clip is two things: the motion
(FNV's, retargeted onto FO4's skeleton) and the encoding (our Havok 2014
spline writer, `anim_fo4.write_fo4_animation`). This test keeps the
motion vanilla's and the encoding ours.

**Setup** (`idles.PROBE`). With `CONVERT` off, only the idles PROBE
names are built: `VCG01DocGiveMirror`, by the route already played
without a crash at the time, played only by FNV's VCG01 stage-30 script
(`PlayIdle`) on `FurnitureBehavior.hkx` with `dyn_Activation`, no line
carrying it. Its clip is vanilla's `IdleSitFemaleReactingToViolence`
(Kellogg's synth scene, a seated `dyn_Activation` on the furniture graph
in Fallout4.esm), read from Fallout 4 - Animations.ba2, decoded and
written again by our writer (`Probe\IdleSitFemaleReactingToViolence.hkx`
under the plugin's clip folder). Everything else matches the build that
played without a crash.

**Offline check of the re-encoded clip:** duration (10.7 s), 322 frames,
95 tracks, 2 blocks, bone names, binding, skeleton name (`Root`) and its
HeadTrackingOff event are vanilla's; the first 64 header bytes are
identical; decoded, rotations differ by at most 2.9e-4, translations by
2.9e-6, scales not at all. Ours is 80,584 bytes against vanilla's 67,440
(our writer compresses less).

**To play:** a save before Doc's hand-over ("How'd I do?", VCG01 stage
30). Doc should play the Kellogg-scene seated reaction in place of the
mirror hand-over. Play past it: the stand-up, the looks menu (where the
last crash happened), and leaving the house. Repeat from the save two or
three times, as the last crash was intermittent.

**Reading the result.**
- Crash: the encoder is the suspect. Next, the control: the same clip
  unencoded (PROBE's flag False, GNAM naming vanilla's own file). If the
  control is clean, the encoder is confirmed; if it also crashes, the
  route is at fault.
- No crash: the encoder is cleared. Next, the scale-fixed FNV mirror
  clip alone (PROBE emptied for that idle, its own clip converted), which
  tests the retargeted motion and the scale fix.

**Played 2026-10-19: no crash.** The re-encoded vanilla clip played as
the hand-over, then the stand-up, the looks menu and leaving the house:
the first run and a couple more from the save. The encoder is cleared: our writer's files play
safely on this route. (One run lost the player's controls after the
Vit-o-matic, not reproduced; see
[vcg01](fo4_spikes.md#spike-2-vcg01).)

**Next arm, built 2026-10-20:** `PROBE` names the mirror with no vanilla
clip (None), so it plays its own FNV clip, retargeted and written with
the scale fix (`human_clip.UNIT_SCALE`); everything else is unchanged.
This tests FNV's retargeted motion alone. No crash over a few runs clears
the FNV seated clip on this route; a crash puts the motion (or the old
scale channel's fix) in question.

**Played 2026-10-20: crashed on the second run.** The first run played
through; the second crashed at 09:09:43, a second after the player stood
(stage 30 at 09:09:37, stage 35 at :41, `F3NV_PlayerControls.Stand` at
:42). The crash had the same stack as the looks-menu crash of 2026-10-19
14:58: `hkThreadMemory::blockAlloc` reading a corrupt free-list link
(`0x005D002800290091`, packed 16-bit values) while the player's
`Set3D` released a subgraph. That is the player's graph, so Havok's heap
was already corrupt when the player stood up. The clip itself is clean:
95 tracks bound 0 to 94 as in vanilla, no NaNs, unit quaternions, scales
of 1, largest translation 120 units, splines well formed. Its position
masks are all ones vanilla uses (a census of 3,000 vanilla clips: even the
rarest it uses appears in 221 clips). Two things differ from the cleared
arm:
- **Length.** The FNV clip is 3.0 s; the vanilla clip was 10.7 s. In
  every run the player stands 6 to 7 s after stage 30, so the vanilla clip
  was always cut off by the stand-up, and the FNV clip always ended on its
  own first. The cleared arm never tested a clip ending on this route.
- **Track names.** The FNV clip names its 95 annotation tracks after the
  bones; vanilla leaves them blank (0 of 1,500 vanilla clips name them).

**Next arm, built 2026-10-20:** the cleared vanilla clip, re-encoded,
cut to its first 3.0 s (`idles.trimmed`): vanilla motion, blank track
names, the encoder already cleared; only the length changes, so it ends
before the stand-up as the FNV clip did. A crash means a seated clip
ending on its own on this route is the fault, whatever its source; no
crash over a few runs points at the FNV clip's motion or its named tracks,
tested next by blanking the names.

**Played 2026-10-20: no crash, five runs back to back** through the
character creator. A seated clip ending on its own before the stand-up is
cleared.

**Next arm, built 2026-10-20:** the FNV mirror clip again, its annotation
tracks now blank as vanilla's are (`human_clip.TRACK_NAME`, for every
converted clip). Motion, length and events are unchanged from the arm that
crashed. No crash over several runs points at the names; a crash leaves
FNV's retargeted motion itself.

**Played 2026-10-20: no crash.** With blank track names the FNV mirror
clip played through the hand-over, the stand-up and the character
creator. The named annotation tracks were the fault; every converted
clip now writes them blank.

## <a id="standing"></a>Standing idles back on (built 2026-10-21, played: Doc's intro, no crash)

`CONVERT` is gone: every standing idle the build uses converts again, from
lines (speaker and listener idles) and scripts (Idle properties), on the
root graph. A seated idle converts only when a script plays it and it is
in `SEATED_PLAYED` (the mirror hand-over, played safely); every other
seated idle stays out until it is played. `PROBE` is empty.

In the Goodsprings-Primm region: 12 standing idles added (talk head nod
and shake, shrug, arms folded, hands up, angry, NPC giving, Doc's heal and
Pip-Boy hand-over, the opening thugs' hood and pistol whip), plus the
mirror; 35 lines gain speaker or listener idles. Left out: 8 seated, 5 with
no human clip. No FormID moved (41,389 kept, 12 added); FO4Edit clean.

**To play:** a new game through Doc's intro (the Pip-Boy hand-over, his
heal) and the opening scene, then talk around Goodsprings and Primm,
watching for the gestures and for any crash.

## <a id="spike"></a>Spike: Doc's idles in the Goodsprings-Primm build

Built 2026-10-19: the region build converts the idles its scripts and
lines use. Of Doc's, the card points, shrug and "Whoa there" are seated and
left out of lines, and the mirror hand-over plays from the stage-30 script
([seated](#furniture)); his standing idles played 2026-10-21 ([standing](#standing)).
