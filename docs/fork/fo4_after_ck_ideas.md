# Ideas: what owning the CK's steps makes possible (2026-11-12)

Status: ideas only, nothing built. Status lives in [ROADMAP.md](ROADMAP.md).

**Why now.** The build has taken over most of what the Creation Kit, Elric
and Bethesda's other tools did ([CK replacements](fo4_ck_replacements.md#today)):
BA2 packing, Caprica-only scripts, AnimTextData, lips, our own FaceGen heads
and face textures ([own stage](fo4_facegen_plan.md#own-stage)), and an hknp
collision writer ([plan](fo4_hknp_writer.md)). These steps now run as
ordinary Python: per record or per mesh, in a process pool, with no CK
window, no MO2 round trip, and the same bytes every run. A face takes
0.29 s, and all 2,382 FalloutNV.esm faces take 11 minutes
([speed](fo4_facegen_plan.md#own-stage-speed)). That makes things possible
that the CK made impractical. Some are for the conversion, some stand on
their own.

Sizes below are rough guesses, not measurements.

## <a id="build"></a>Faster, steadier builds

### <a id="incremental"></a>Rebuild only what changed

The CK exports every NPC's FaceGen on every run. We can hash each NPC's
inputs (its record, race, head parts, tint layers, and the textures and
meshes they name) and rebuild only the faces whose hash changed. Collision
can do the same per mesh. Most rebuilds after a small change would then
take seconds instead of minutes.

- **Have:** byte-identical output run to run, which is what makes a hash
  trustworthy; per-NPC `write_face`; per-mesh collision.
- **Need:** a list of everything a face or mesh reads (the hash inputs),
  and a stored hash per output file. The CLAUDE.md rule on caches between
  runs applies: this one has to earn its keep with a large win.
- **Size:** small to medium.

### <a id="anywhere"></a>Builds off Windows

With the CK and Elric gone, texconv is the last Windows-only tool in the
face and collision steps. A BC1/BC5/BC7 encoder in our own code (or an
open library) would let both run on Linux and the Steam Deck, which the
[app](fo4_gui.md) needs anyway.

- **Need:** an encoder whose output the game accepts. It doesn't have to
  match texconv's bytes, but the faces census
  (`tools/nif/facegen_census.py --textures`) should show no loss against
  texconv.
- **Size:** medium. Its own spike first: an open encoder's quality and
  speed against texconv on the face set.

### <a id="regression"></a>Standing byte checks

The whole-set comparison used to prove the speed-up (9,528 files, all
identical) could become a standing check: a fixed sample of NPCs and meshes
rebuilt after a change and diffed against the last accepted output. Any
change to a face or a collision mesh would then be seen, not guessed at.

- **Size:** small. The compare already exists as scratch scripts; it would
  become a tool in `tools/` with a `python_tools.md` entry.

## <a id="faces"></a>Better faces than the CK makes

### <a id="resolution"></a>Higher resolution and better formats, as an option

We now choose each face texture's size and format instead of taking the
CK's. A user option could write `_d` at 2048, or BC7 instead of BC1 for
less color banding on skin. Vanilla stays the default
([vanilla formats](fo4_pipeline.md#audit-fixes)).

- **Unknown:** the game's memory and load cost at 2048 for every NPC in a
  crowded cell.
- **Size:** small.

### <a id="fnv-look"></a>An "FNV look" option

`face_tint` copies how the CK blends tint layers. FNV drew faces its own
way (FaceGen's EGT texture offsets, `face/texture.py`). An option could draw
`_d` from FNV's own data instead, for players who want the original look
over FO4's.

- **Size:** medium. The two pieces exist separately; the work is picking
  per NPC and checking a few in game.

### <a id="variants"></a>Variants made at build time

At 0.3 s a face, extra versions cost little. Ideas: dirt and grime for
wastelanders, scars, radiation burns, ghoul decay stages, faction war
paint. Each variant is a tint layer we add before drawing, then an NPC (or
a leveled copy) points at it.

- **Unknown:** how many extra faces the game handles before load times
  suffer.
- **Size:** medium. Authoring the layers is the bulk of it.

### <a id="unique-generics"></a>Unique faces for generic NPCs

Leveled raiders, Powder Gangers and caravan guards share a few templates.
Seeded per NPC (by FormID, so it's the same every build), we could vary
their tint layers and face sliders and bake each one.

- **Check first:** what FNV authored. Template NPCs that take traits get no
  FaceGen of their own (`facegeom.exported`), so this means giving those
  NPCs their own traits, which is a record change and needs the same care
  as any [FormID](../../CLAUDE.md#formid-drift) work.
- **Size:** medium.

## <a id="tools"></a>Tools for all of FO4

### <a id="dark-face"></a>A dark-face fixer for any load order

Mismatched FaceGen (the "dark face" bug) is FO4's most common modding
problem, and today's fix is to open the CK and re-export. A tool that reads
a load order, finds the NPCs whose winning record no longer matches the
FaceGen on disk, and rebuilds only those, without the CK, would help nearly
every FO4 player who uses mods.

- **Have:** the CK's export rule, matched exactly on FalloutNV.esm
  (`facegeom.exported`); the head builder (`facegeom.build`); the face
  textures (`face_tint`); the per-NPC CK fallback.
- **Need:** load-order reading (the winning NPC, race and head-part
  records), a "does this match" check that doesn't just rebuild everything,
  and a check on vanilla FO4 NPCs. So far we've only proven it on our own
  FNV NPCs.
- **Fits:** [the spin-off strategy](spin_offs.md#strategy), open and
  drop-in. No open FO4 FaceGen baker exists
  ([survey](research/fo4_open_landscape.md#tools)).
- **Size:** medium. Most of it is built; the vanilla-FO4 check decides it.

### <a id="replacers"></a>Faces rebuilt for head and skin replacers

High-poly head meshes and skin retextures cause the same mismatches. The
same tool could rebuild FaceGen against whatever head and skin a load order
ends up with, at install time.

- **Size:** small once the [dark-face fixer](#dark-face) exists.

### <a id="collision-tool"></a>Collision for modders

The hknp writer could become a stand-alone tool: give it a mesh, get FO4
collision, with no CK or Elric. Useful for mod assets that ship without
collision, or with broken collision.

- **Size:** small once the writer covers spheres, capsules and ragdolls
  ([writer plan](fo4_hknp_writer.md)).

## <a id="fun"></a>Fun extras

### <a id="courier"></a>Bring your Courier's face

Read an FNV save's player face and turn it into a starting face in FO4,
through the same face fits the conversion uses (`face_fit`).

- **Unknown:** where FNV's save keeps the player's FaceGen values, and
  which FO4 route takes a face (a character-creation preset, or a record
  the player starts with). Both need a spike.
- **Size:** medium.

### <a id="companion-faces"></a>Play as a companion

Export Cass's, Veronica's, Boone's (or anyone's) converted face as a
character-creation preset.

- **Unknown:** the preset format, the same spike as [the Courier](#courier).
- **Size:** small after that spike.

### <a id="portraits"></a>NPC portraits

We have each finished head mesh and its textures, so portraits can be
rendered offline. Uses: a dialogue menu with the speaker's portrait (our
own [Flex menus](fo4_dialogue_menu_plan.md)), a "people you've met"
holotape, or a gallery page.

- **Size:** medium. The renderer is the work; Blender is one route.

### <a id="gallery"></a>A comparison gallery

The CK's face, ours and FNV's original, side by side for every NPC. It
would make problems visible at a glance and help with the pinned lip-color
and tone-mask work ([revisit](fo4_facegen_plan.md#face-d-revisit)).

- **Size:** small if it shows the textures flat; medium with rendered
  heads (it shares a renderer with [portraits](#portraits)).

## <a id="later"></a>Further out

- **Other games' content in FO4.** The collision writer and the face code
  don't care where a mesh came from, which makes Oblivion or Skyrim content
  more realistic later.
- **Faces picked at runtime.** Pre-baked face pools that a spawner draws
  from, for settlers or wanderers.

## <a id="picks"></a>Suggested first picks

1. **[The dark-face fixer](#dark-face):** the most value to the most
   people, and mostly built already.
2. **[Rebuild only what changed](#incremental):** it speeds up every build
   after it.
3. **[The comparison gallery](#gallery):** cheap, and it doubles as a check
   on our faces.
