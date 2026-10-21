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
- **Not covered yet:** FNV's props (the Reflectron mirror rides on
  `Weapon` and a dummy node; FO4 shows props through ANIO and
  `AnimObjLoad`/`AnimObjDraw` events), creature clips (18 of the 115 line
  idles), female-only clips, and root motion (FO4's dynamic idle plays in
  place; the clip's root track is dropped).

## <a id="records"></a>2. Records: FNV IDLE as an FO4 dynamic idle

`spike/idles.py`, `Idles`: an FNV idle the build uses becomes an FO4 IDLE
on FNV's own FormID (a new record; nothing already built moves).

- **Used:** a converted script's `Idle` property (by EditorID, through
  `attach`) and a line's speaker and listener idles (`pack_info` writes
  `SNAM`/`LNAM` per response, as FNV has them). `VCG01DocGiveMirror` now
  rides "How'd I do?" as FNV's own speaker idle, replacing the earlier
  stand-in (`DialogueGiveItem`).
- **Fields:** `DNAM` the root graph (seated clips are left out,
  [seated](#furniture)), `ENAM` `dyn_Activation`
  (`dyn_ActivationLoop` with 255/255 seconds when FNV loops forever),
  `GNAM` the clip under `Actors\Character\Animations\<plugin>\` (FNV's path
  below `characters\_male\`), FNV's conditions (`conditions_of`, the
  dialogue's form map), `ANAM` FNV's parent and previous when they are
  built (else 0, loose flag 0x01), FNV's replay delay. FNV's loop counts
  other than "forever" play once.
- **Left out:** an idle whose clip is missing (2 of Doc's) or is not a
  human clip.
- **Idle trees (planned, not built).** FNV's conditioned idles (the 1,098)
  are trees whose roots have no parent; FO4 hangs its ambient idles under
  actions (`ActionIdle` `00013002`, 27 vanilla children; the graph
  initialise, stagger, death and flinch actions hold the rest). The tree
  build converts every human FNV idle tree under `ActionIdle`, keeping
  parent, previous and conditions, so the engine's own idle selection
  plays them; the run order of siblings follows FNV's `Previous` chain.
  Each tree's root group (FNV's `AnimGroupSection`) decides whether it is
  an ambient, dialogue or furniture tree.

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

`idles.CONVERT` is off: builds write no IDLE, clip or line idle, as before
this work. Next test, one change: a vanilla clip re-encoded by our writer
played as the mirror (isolates the encoder), then the scale-fixed FNV clip.

## <a id="encoder-test"></a>Encoder test (built 2026-10-19, not yet played)

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
(stage 30 at 09:09:37, stage 35 at :41, `TES4_PlayerControls.Stand` at
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
lines use. Doc's to check in game: the card points and shrug through the
psych test, "Whoa there", and the mirror hand-over on "How'd I do?".
