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

## <a id="fall-through"></a>4. First-person fall-through audit

First person has no IK, so every clip the gun falls through to keeps FO4's
hands. Diff step 0's list against what `gun_clips` writes. For each clip still
falling through, either write it from FNV's nearest clip or carry the left
hand onto the mesh (`left_reach` and `handle_grip`). Leave sprint and bash to
vanilla only where the hand stays on the gun.

Done when the list is empty, or each clip left on it is recorded here with
the reason.

## <a id="anim-info"></a>5. Generate AnimTextData for guns

Gun entries copy the template's AnimTextData under the new folder list's id.
Once step 1 changes the third-person clips, the copied speed and stance data
no longer match them. Run the Creation Kit export (`rig/anim_info.py`, already
built for own-rig creatures, with `--speed --stance`) over the gun entries
too, and keep its input-key skip so an unchanged build doesn't pay for it.

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
