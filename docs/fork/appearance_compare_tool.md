# Appearance comparison for Fallout 4: tool plan (2026-11-12)

A stand-alone tool that loads two load orders, for example the same game
with two different character replacement mods, and shows every NPC either
one changes side by side. Separate from the FNV conversion; it reuses the
conversion's FO4 readers and face code. Part of the
[spin-off plan](spin_offs.md#strategy); grew out of the
[comparison gallery idea](fo4_after_ck_ideas.md#gallery). Status lives in
the [roadmap](ROADMAP.md). Ideas only, no code yet. Name to pick.

**Why.** Today the only way to compare character replacers is to install
one, walk around the game, swap, and remember. Nothing shows two load
orders' NPCs next to each other. The same reading also catches the most
common FO4 face bug: a replacer whose face files don't match its records
(the dark-face bug).

## <a id="tiers"></a>Two tiers

Nothing but the game renders exactly like the game, so the tool has two
modes:

| Tier | Shows | Speed | Needs |
|---|---|---|---|
| **Viewer** (the everyday one) | Every NPC either side changes, rotatable, neutral light | Seconds for hundreds of NPCs | The game's files only |
| **In-game capture** | The game's own render, from fixed angles | Minutes per side: one game launch each | The game installed, a profile per side |

## <a id="viewer"></a>The viewer

1. **Resolve each side.** For each load order: the winning NPC, race,
   head-part, hair color and armor/skin records per NPC, and which mesh and
   texture wins from loose files and BA2s.
2. **Pair NPCs.** Every NPC either side touches. An NPC only one side
   changes shows "unchanged" on the other.
3. **Show what the game loads.** The game reads each NPC's pre-baked
   FaceGen (FaceGeom NIF, FaceCustomization `_d`/`_msn`/`_s`) from disk, so
   the viewer shows those files, not a fresh bake. Beside it, optionally,
   our own bake of the winning records ([own FaceGen](fo4_facegen_plan.md#own-stage)).
   When the two differ, the NPC is flagged as a dark-face mismatch, which
   ties into the [dark-face fixer](fo4_after_ck_ideas.md#dark-face).
4. **Render.** Head, hair, beard, eyes, brows and body meshes with their
   textures, hair color and skin tone, under one fixed studio light so the
   sides are compared fairly.

**Have already:** FO4 plugin, BA2 and loose-file reading
(`facegeom.Sources`), FO4 NIF reading (`fo4_import/nif`), the CK's FaceGen
export rule (`facegeom.exported`), our face baker, and the face census's
texture comparison (`tools/nif/facegen_census.py --textures`).

**Renderer:** a browser viewer (three.js) is the most portable and needs
no install. Blender shades better but makes every user install it.
Browser first.

## <a id="limits"></a>What the viewer can't show

- **FO4's own shading.** The skin, hair and eye shaders aren't public;
  skin softness, specular, hair transparency and eye reflections are
  approximated. Good enough to see shape and texture changes, not exact
  color under in-game light.
- **Lighting and post-processing:** weather, interiors, the imagespace's
  color grading, ENB and ReShade.
- **Anything applied while the game runs:** LooksMenu body morphs and
  overlays (tattoos, makeup) from F4SE plugins, jiggle physics,
  expressions and idles. A few expression morphs could be added later.
- **Bodies past what's on disk.** Body replacers depend on the user's
  BodySlide build; the viewer shows the built meshes, not morphs applied in
  game.

## <a id="capture"></a>In-game capture

For exact results: launch FO4 with side A's profile, load a plain test
cell, place each NPC in turn, hide the HUD, take screenshots from fixed
angles, then repeat with side B. It includes everything the viewer can't:
the real shaders, the user's ENB, LooksMenu overlays and physics.

**Open questions:**
- Whether the vanilla console's batch files (`bat`) plus a startup command
  can drive it with no DLL. If it needs an F4SE plugin, that's a new DLL
  for a stand-alone tool, to be agreed before building it.
- Switching profiles: MO2 takes a profile on its command line; Vortex
  deploys into Data and is rougher.
- Camera placement that frames every race the same way (super mutants,
  children).

## <a id="practical"></a>Practical limits

- **Mod managers.** MO2's virtual file system means reading its profiles
  and mod folders; Vortex mostly links files into Data. The
  [conversion app's](fo4_gui.md) mod-manager-neutral design covers the
  same ground.
- **Mods needing F4SE plugins** for their look only show right in capture.
- **Scale.** The viewer handles hundreds of NPCs; capture wants a short
  list.
- **Assets stay local.** It reads only the user's own installed files and
  writes nothing into their game. Sharing screenshots of other people's
  mods is up to the user and the mod authors.
- **License:** like the other spin-offs ([license](spin_offs.md#license)).

## <a id="order"></a>Order

1. Resolve two load orders and list the NPCs that differ (text only). That
   alone answers "what does this replacer touch".
2. The dark-face check on that list (on-disk FaceGen against the winning
   records).
3. The browser viewer for heads, then hair and bodies.
4. In-game capture, after the console-batch question is answered.
