# Converted FNV guns: grip, third person and FNV feel (plan, 2026-10-31)

**Code today:** `fo4_import/havok/gun_clips.py` (clips, subgraph entries,
AnimTextData), `fo4_import/nif/gun.py` (mesh placement),
`fo4_import/spike/gun_choice.py` (template choice), `fo4_import/spike/guns.py`
(records). What is built and played:
[spike 4](fo4_spikes.md#spike-4-gun-clips).

Three problems remain on converted FNV guns:
- hands that don't hold the gun;
- third-person animations that don't line up with it;
- motion that feels like FO4 rather than FNV.

This plan fixes them in order of effect, all from data and per gun, with no
script-extender plugin and no base-game file override.

## <a id="mechanism"></a>What the plan rests on

Researched 2026-10-31. The full report is outside the repo, at
`C:\Coding\tes4skyrim\reports\FO4 animation system for FNV weapons.md`. Nexus
pages refused automated access, so its Nexus facts come from search snippets.

- **Clips can all be replaced, graphs effectively not.** Each RACE subgraph
  entry names a vanilla graph and ordered clip folders. The clip names are
  fixed by the graph, so a gun's own folder, searched first, can replace every
  clip in both views. Editing `GunBehavior.hkx` or `WeaponBehavior.hkx`
  overrides a base-game file that only one mod can win (Tactical Reload and
  Modern Weapon Behavior both ship one). Out of scope here.
- **Entry choice.** The entry matching the most actor keywords wins, and the
  target-keyword count breaks ties. A vanilla Player, Synth or injured entry
  can therefore beat a gun's keyword-only entry.
- **IK exists only in third person.** First person has no left-hand IK:
  `LeftHandTarget` is only a variable, and only the Pip-Boy graph has a
  hand-IK modifier. A first-person clip's hands are final, additive layers
  included. Third person IKs the left hand to `WeaponIKTargetL`, which
  `WPNAssemblyPose` places. The `AnimationDrivenLeftHandIK` names suggest some
  states take the hand from the clip instead (inferred).
- **Third-person clips live in grip folders.** `Weapon\GripRifleStraight`
  holds 584 files: cover, kneel, blind fire, hit reactions, and the `Player`,
  `Synth` and `Injured` subfolders. Per-gun folders are small (HuntingRifle 24,
  SubmachineGun 13). A converted gun inherits all of these, authored for
  another gun's hold.
- **Timing.** The graph exits states on timers counted back from the clip's
  end, so a replacement keeps vanilla's length and events. AnimTextData
  (`--speed --stance`) also holds sight lines and fire locations.
- **Feel.** FO4 draws first person at FOV 80 against FNV's 55, which makes
  FNV's gun about 1.6× larger on screen (tan 27.5° / tan 40°). Recoil and
  bloom are AimModel (AMDL) data, sighting speed is the WEAP's Sighted
  Transition Seconds (default 0.25), and zoom is ZOOM data.

## <a id="order"></a>Order

Each step is played on its own before the next one ships, one change per
play test, on one gun per FNV class as in spike 4 (9mm Pistol, Assault
Carbine, Hunting Rifle, Flamer, Tesla Cannon).

| # | Step | Problem | Size |
|---|---|---|---|
| 0 | [Measure first](#measure) | all | S |
| 1 | [FNV's own third-person clips](#third-person-clips) | 3rd person, feel | M |
| 2 | [Every entry variant, and power armor](#entry-variants) | 3rd person, grip | S |
| 3 | [Left hand in third-person states FNV has no clip for](#third-person-ik) | grip, 3rd person | M |
| 4 | [First-person fall-through audit](#fall-through) | grip | S |
| 5 | [Generate AnimTextData for guns](#anim-info) | 3rd person (aim) | S |
| 6 | [FNV's on-screen size](#fov) | feel | M |
| 7 | [Records from FNV data](#records) | feel | M |
| 8 | [Right-hand coverage in template choice](#coverage) | grip | S |
| 9 | [A keyword per attachment combination](#omod-keywords) | grip | S |
| 10 | [Timing a clip can't fix](#timing) | feel | last resort |

## <a id="measure"></a>0. Measure first

Three measurements, each a one-off script (findings go into this doc).
- **What a converted gun falls through to.** Behaviour Graph Studio
  ([G-A-R-D-E-N/BGS](https://github.com/G-A-R-D-E-N/BGS), MIT, headless scan
  modes) or our own reader lists every clip each graph can play. Diff that
  against each converted gun's folder per view: these are the clips still
  showing FO4's hold.
- **Every vanilla weapon clip's annotations.** Dump them with
  `anim_fo4.fo4_animation_header` (or PyNifly) to close the gap on which events
  each state needs.
- **The binary stance data.** Decode AnimationStanceData to confirm what NPC
  aim reads.

Done when the fall-through list exists per class, and steps 1 to 5 are
re-ranked from it.

### <a id="measured"></a>Measured (2026-11-11, last night's build, not played)

One-off scripts over the built `FalloutNV.esm`, its Main BA2 and
`tools.nif.gun_quick_convert` output, on the five test guns. Units are game
units; "finger" is each hand's middle-finger base, the spike's grip measure.

**Keywords don't lose the first-person entry.** Applying the CK rule (most
actor keywords, then most targets) to every weapon entry of Fallout4.esm, the
six DLC masters and our additive race, for all 50 actor-keyword sets found
(Player, Synth, Confident, every injured combination): the gun's own entry
wins in first person for every set and every test gun, and its AnimTextData
file exists and points 39–46 of the graph's 88–90 clips at the gun's folder.
The user's lead, a vanilla entry or the template keyword beating ours, is not
what moves the hands in first person.
- Third person: 14 of 86 converted guns get no entry at all, and play the
  template's clips with vanilla's `WPNAssemblyPose`: the replaced keyword
  keys only first-person entries (`AnimsFP10mm` on the 9mm and .22 pistols)
  or is a part's (`AnimsLaserBarrelShort` on the Tesla Cannon Unique,
  Tri-beam). The 9mm, Veronica's 10mm, the 12.7mm, the Recharger Rifle,
  Laser Rifle Unique, detonators, artillery and two debug guns. The others,
  the Tesla Cannon included, win for every actor set (player, synth and
  injured entries already copied).
- Not ours: the 9mm receiver's null keyword is vanilla's own
  (`mod_10mm_Receiver_Standard` adds 00000000).

**First person: FNV's clips hold where FNV does.** In every clip
`gun_clips` writes, each finger sits a constant 2.4–5.3 units from FNV's own
finger on the same mesh (9mm 2.4, carbine 3.8/4.0, Hunting Rifle 4.5/4.2,
Flamer 4.1, Tesla 5.3/4.9 right/left): the two skeletons' hands differ, and
the right hand holds the template's grip by the trigger. FNV's fingers sit
0.2–2.7 from the mesh, ours 1.5–4.2. The Flamer's left hand is on vanilla's
handle grip (`handle_grip`), FNV's 22 units off.
- **What falls through, per class** (whole poses the graph plays from the
  template's folder): `WPNSprint`, `WPNRunGunDown`, `WPNIdleGunDown`,
  `WPNEquipFast`, `WPNJumpImpactLand`, `WPNMelee`, `WPNMeleeBayonet`,
  `WPNGrenadeThrow`, `WPNMineThrow`, and on semi-automatic guns the
  `WPNFireAuto*` clips; the paired kills (the Paired folder is searched
  before ours); `Recoil`, `SneakOffset` and the `Stagger*Add` layers. These
  are FO4's hold: the carbine's left finger 5.7 off our mesh in sprint,
  landing and bash, the Hunting Rifle's 4.1, the Tesla's 4.3, the Flamer's
  9.7. `WPNIdleGunDown` is lossless-compressed and can't be read.
- `Recoil` turns the spine and moves the camera, `SneakOffset` lowers the
  root 40 units: neither moves a hand against the gun.

**Third person: the clip's own hand is on its own target.** In the
template's idle, walk, run, sneak, sighted and fire clips the left hand sits
within 0.7 of the clip's own `WeaponIKTargetL` (the Hunting Rifle's
GripRifleStraight 5–9, its IK pulling the hand). Those targets differ from
`WPNAssemblyPose`'s by 2–7 units, so moving only the pose cannot move them.
Clips holding the target at the skeleton's rest sit 17–22 off (sprint,
grenade, jumps), hit reactions 90–150. On our meshes the template's finger
is 5.6 off the carbine, 1–3 off the Hunting Rifle, 3–4 off the Tesla, 16.5
off the Flamer (GripHeavy idle and walk).
- **A shipped bug:** `left_targets` read "our" left hand from the clip's
  `WeaponIKTargetL` track. A hand on vanilla's grip (pistols, heavy guns on
  `handle_grip`) writes none, and `fill_from` filled vanilla's in: the 9mm's
  read the gun's origin, the Flamer's 90 units off its hand. Every such gun
  with a third-person entry carried `WPNAssemblyPose`'s target that far (the
  Flamer's 83 units off our mesh). Now read from the posed clip.

**Ranked from this** (steps 1–5): first-person grip is the fall-through
clips (step 4), not the keywords; third person's largest measured gap is
the left target (the bug, then step 3), largest on heavy guns; step 1 (FNV's
own third-person motion) is feel, unmeasured; step 2 is done for actor sets
(power armor unchecked); step 5 follows from 3, since entries now playing
FNV-folder clips go to the CK's AnimTextData run.

| Rank | Change | Status |
|---|---|---|
| 1 | Our left hand read from the pose (third person, pistols and heavy guns) | built |
| 2 | [Step 4](#fall-through): vanilla fall-through clips with the left hand carried | built |
| 3 | [Step 3](#third-person-ik): every on-gun third-person clip's target carried | built |
| 4 | A third-person keyword for the 14 guns without an entry | follow-up |
| 5 | [Step 1](#third-person-clips): FNV's own third-person clips | open |

## <a id="third-person-clips"></a>1. FNV's own third-person clips

Today third person plays the template's clips, with only the left-hand target
moved. Retarget FNV's third-person weapon clips (aim, iron-sight aim, attack,
reload, equip, unequip, per class) onto FO4's human skeleton. Use the existing
`human_clip` bone map and matching pose (the path idles already use), under
the vanilla third-person names, in the gun's folder.
- Both views then play FNV's motion on the same placed mesh, fixing the
  mismatch at its source.
- Same rules as first person: vanilla length and events, timed from FNV's text
  keys; the right hand on the Weapon bone at the template's grip; and
  `WeaponIKTargetL` taken from FNV's left hand in each clip, not only in
  `WPNAssemblyPose`.
- Upper body only. Third person layers the weapon clips over separate
  locomotion, so the lower body keeps FO4's walk.
- Done when the five played guns look the same in third person as in first:
  the left hand on the gun while standing, walking, sighted, firing and
  reloading.

## <a id="entry-variants"></a>2. Every entry variant, and power armor

`GunClips.template_entries` copies the keyword-only entry and the player's
entry per view. Copy every entry whose targets the template carries, not just
those two: the actor-keyword variants (Synth, injured, any others the
step 0 scan finds), each with the gun's folder first. Add the power-armor
entries the same way. Power armor uses its own graphs and drops
`WPNAssemblyPose` finger data, so it needs its own folder of corrected clips.

Done when no vanilla entry outranks the gun's for any actor, in or out of
power armor (a check over the built plugin's SADD entries).

## <a id="third-person-ik"></a>3. Left hand in third-person states FNV has no clip for

Cover, kneel, blind fire, hit reactions and injured have no FNV source. In the
gun's folder, override each one the gun falls through to (from step 0) with a
copy whose `WeaponIKTargetL` track is moved onto our mesh. This is the same
carry `carried_target` does for `WPNAssemblyPose`. Where a state's hand turns
out to come from the clip rather than IK (the walk case played on the carbine),
move the left arm with the two-bone IK the first-person clips use.

Done when the left hand stays on the gun in every third-person state from
step 0's list.

**Built 2026-11-11, not played** (`_with_targets`). Every whole-pose clip
of a third-person entry whose target stays within 12 units of
`WPNAssemblyPose`'s (`ON_GUN`; [measured](#measured)), outside Paired, is
copied with its target carried, into the gun's mirror of the clip's vanilla
folder (`gun_folder`: `Actors\FNV\Character\Animations\<gun>\<folder under
Actors\Character\Animations>`), searched just before that folder; one copy
per gun, shared by its entries. A gun whose left hand is vanilla's (a pistol
on vanilla's grip) carries nothing. The clip-driven arm itself is not moved.
- Our hand against vanilla's grip, in the Weapon frame: carbine 4.0 units
  and 23°, Hunting Rifle 1.8 and 20°, Flamer 18 and 72°, Tesla 27 and 120°.
- The Flamer's targets, from our mesh: `WPNAssemblyPose` 11.4 → 5.8 (83
  with the shipped bug), GripHeavy idle, walk and sneak 20.4 → 10.1. The
  carbine's 6.7 → 5.1; the Hunting Rifle's distance unchanged.
- Cost: 122–254 copies per gun, 2.2–5.4 MB uncompressed (carbine 191 and
  3.9 MB), so about 300 MB over the 72 guns with an entry; each vanilla clip
  is parsed once per worker.

## <a id="fall-through"></a>4. First-person fall-through audit

First person has no IK, so every clip the gun falls through to keeps FO4's
hands. Diff step 0's list against what `gun_clips` writes. For each clip still
falling through, either write it from FNV's nearest clip or carry the left
hand onto the mesh (`left_reach` and `handle_grip`). Leave sprint and bash to
vanilla only where the hand stays on the gun.

Done when the list is empty, or each clip left on it is recorded here with
the reason.

**Built 2026-11-11, not played** (`_carried`, `carried_left`). Each
whole-pose clip of the template's that the gun doesn't write, outside
Paired, is copied with its left arm bent so the hand keeps the hand-local
offset it has from vanilla's grip, on our grip: fully within 4 units of
vanilla's grip, eased out by 12 (a grenade throw keeps its swing). Measured:
the carbine's left finger 5.7 → 3.5 off our mesh in sprint, landing, bash,
throws and gun-down (our idle's gap); the Tesla's 4.3 → 1.7 in sprint and
gun-down (its bash and throws can't reach); the Hunting Rifle's distance
unchanged (4.1 → 4.2) but the hand turned 20° to ours.
Left on the list:
- a clip whose carried hand the arm can't reach (1 unit, `REACHED`) stays
  vanilla: all of the Flamer's (its handle is far from the FO4 flamer's;
  vanilla's hand stays 9.7 off);
- `WPNIdleGunDown` (unreadable), the paired kills, the additive layers
  above;
- a pistol on vanilla's grip has nothing to carry.

## <a id="anim-info"></a>5. Generate AnimTextData for guns

Gun entries copy the template's AnimTextData under the new folder list's id.
Once step 1 changes the third-person clips, the copied speed and stance data
no longer match them. Write those entries' offsets the way
`havok/anim_text.py` writes first-person entries' and own-rig creatures'
([ours](research/anim_text_data.md#ours)); the Creation Kit export is gone
(2026-11-11).

Done when the gun entries' AnimTextData comes from the CK, and NPCs aim the
converted guns at the player (played).

## <a id="fov"></a>6. FNV's on-screen size

FO4's first person at FOV 80 shows FNV's gun at about 0.62 of its FNV size.
Per clip, bring the gun and arms toward the `Camera` bone to match FNV's
on-screen size at 55, keeping the sight line on the camera's axis. A converter
must not change `fDefault1stPersonFOV`: it's a user ini setting and breaks the
Pip-Boy at low values. Check the longest guns for clipping through the
camera's near plane.

Done when a sighted screenshot of each played gun matches FNV's within a few
percent of screen height, with nothing clipped.

## <a id="records"></a>7. Records from FNV data

- **Sighted Transition Seconds:** FNV's time to raise the sights. Measure
  where it comes from first (an FNV game setting, or the blend into the
  `*aimis` clip).
- **Zoom:** FNV's Sight FOV becomes the ZOOM FOV multiplier (75 means none).
  Built-in scopes already take FNV's magnification
  ([scope zoom](fo4_build_next.md#scope-zoom)).
- **Recoil and bloom:** FNV has no spring recoil. Set AMDL spring recoil near
  zero and take the kick from FNV's attack clip. FNV's spread maps onto the AMDL
  cone. No published mapping exists, so choose a formula, document it here,
  and tune it in play.
- **Speeds:** where a clip is held to vanilla's length, set WEAP reload and
  attack speeds so the motion runs at FNV's pace.

Done when the five played guns sight, kick and reload at FNV's pace (played
side by side with FNV).

## <a id="coverage"></a>8. Right-hand coverage in template choice

`gun_choice` scores templates by layout. Add the right hand's share of the
screen while sighted (`gun_quick_convert`'s aim_hand: 0–9% on the Hunting and
Assault Rifle grips, 16–57% on the pipe, Railway and double-barrel grips) as a
scoring term. Of two templates that fit, the one hiding FO4's bulkier hand
wins. Today's 20–40% cases (lever actions, single and riot shotguns, BB guns,
the .22 SMG) are the test set.

## <a id="omod-keywords"></a>9. A keyword per attachment combination

A keyword set applies only when all of its keywords are present. Where an FNV
weapon mod changes the grip or adds a foregrip, give each combination its own
keyword and entry.

## <a id="timing"></a>10. Timing a clip can't fix

The graph's states and exits stay vanilla. If a reload or bolt still feels
wrong once steps 1 to 7 are played, consider these, in this order:
1. an F4 Open Animation Replacer config
   ([DCCStudios](https://github.com/DCCStudios/F4-OpenAnimationReplacer); no
   license file, newest hooks not yet validated in game);
2. a small hook in `tes_runtime`.

Either one needs the user's OK first (the DLL rule in CLAUDE.md). An edited
`GunBehavior.hkx` is not on this list: it overrides a base-game file and
conflicts with other weapon mods.
