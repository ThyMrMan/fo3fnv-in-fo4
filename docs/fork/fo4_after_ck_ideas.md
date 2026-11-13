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

The CK exports every NPC's FaceGen on every run. Our own faces now keep
each NPC's files in the work cache, keyed by its record and checked
against every other record and file it read, so a build redraws only the
faces whose inputs changed
([own-cache](fo4_facegen_plan.md#own-cache)). Collision already had its
own per-mesh caches (`elric_cache`, `mesh_cache`).

- **Built:** faces (2026-11-12). Kept faces take 0.02–0.05 s each against
  0.5–1.2 s to draw.
- **Left:** the faces stage's end-to-end time with the cache, from the
  second build after it. Without it: 3,390 s.

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

## <a id="by-step"></a>Ideas from the other replaced steps

Each step in [the replacements table](fo4_ck_replacements.md#today) gives
something beyond the conversion. Faces and collision are covered above.

### <a id="ba2-ideas"></a>Archives (our BA2 writer)

Open BA2 libraries already exist
([survey](research/fo4_open_landscape.md#tools)), so a packer alone is not
new. What we learned while replacing Archive2 is
([texture BA2](fo4_ck_replacements.md#ba2)).

- **<a id="ba2-check"></a>An archive check for modders.** Archive2 left out
  every 24-bit BGR texture and still exited 0: an ending slide in
  AutumnLeaves, 12 textures in Weapons of the New Millenia, and the Classic
  Look's 54 LUTs. A checker could read a mod's loose files and its BA2s and
  list what Archive2 would drop: textures in a format with no DXGI match.
  Any mod author could run it before release. Other silent losses can be
  added as they turn up.
  - **Have:** the format census and the format mapping (`expand_bgr`, and
    the pack stopping with the file's path on a format it cannot name).
  - **Size:** small.
- **Archives that only change what changed.** Our writer already copies
  unchanged textures out of the old archive still compressed. The same idea
  makes a small update for players: two builds' archives differ only in the
  files that changed, so an update could ship only those.
  - **Size:** small for the diff, medium for an updater that applies it.
- **Pack a loose-file mod.** Players with many loose-file mods could have
  them packed into BA2s for faster loading, with a check that no file loses
  to another mod's loose copy after packing.
  - **Unknown:** the game's archive count limit in a large load order, and
    how mod managers treat the result.
  - **Size:** medium; the load-order rules are the work, not the packing.

### <a id="caprica-ideas"></a>Scripts (Caprica only)

- **<a id="caprica-upstream"></a>Our Caprica fixes upstream.** Caprica has
  been quiet since 2024 ([survey](research/fo4_open_landscape.md#tools)).
  Our build adds relational operators on strings and fixes a temp-reuse bug
  that silently miscompiled 59 FalloutNV scripts
  ([our Caprica](fo4_pipeline.md#caprica-ours)). Every FO4 modder who
  compiles with Caprica has that bug too. Offer both as pull requests, or
  publish our build if upstream stays quiet.
  - **Size:** small; the fixes exist.
- **A miscompile scanner.** Released mods compiled with an unfixed Caprica
  may carry the same bug. A scanner that reads `.pex` files and flags the
  instruction pattern the bug produces would tell authors which scripts to
  rebuild.
  - **Unknown:** whether the bad pattern can be told apart from correct
    code in the compiled file without the source. Needs a spike on our 59.
  - **Size:** medium.
- **Scripts written in Papyrus assembly.** Caprica assembles hand-written
  `.pas` files (tried with a string `COMPARELT`). Small helpers Papyrus
  can't express could be written that way instead of needing a DLL native.
  - **Size:** small per helper, once the build carries `.pas` files.

### <a id="anim-text-ideas"></a>Animation data (our AnimTextData writer)

The survey lists no open AnimTextData writer. Today a modder adding a new
weapon, creature or animation set needs the CK's `-GenerateAnimInfo`, and a
missing entry shows in game as a frozen or wrong animation.

- **<a id="anim-text-tool"></a>AnimTextData for any mod.** Point it at a
  mod's behavior graphs and clips, get the AnimTextData files, without the
  CK. Ours writes every file the conversion needs, with the offsets' root
  keys bit for bit the CK's ([ours](research/anim_text_data.md#ours)).
  - **Need:** a check on vanilla FO4 animation mods, not just converted
    FNV content.
  - **Fits:** [the spin-off strategy](spin_offs.md#strategy).
  - **Size:** small to medium.
- **A missing-animation finder.** The same code can list, for a load order,
  the behavior graphs and clips that have no AnimTextData entry, before
  anyone sees a frozen animation in game.
  - **Size:** small, after the tool above.

### <a id="lip-ideas"></a>Lip files (no LipGenerator)

LipGenerator only runs on Windows, sometimes isn't installed, and gave 1,746
and 1,758 bytes for the same line on two runs. Our loudness lips need only
the audio ([lips](fo4_ck_replacements.md#lips)).

- **<a id="lip-tool"></a>Lips for voice mods.** New voiced-line mods
  (recorded or generated voices) need a `.lip` per line. A tool that makes
  them from the audio alone, the same every run and on any OS, would help
  every one of them.
  - **Have:** `lip.from_loudness`, and the converter from FNV's `.lip`
    format ([lips](research/lip_format.md#built)).
  - **Unknown:** how a loudness lip reads in game next to LipGenerator's.
    That check is already on the replacements list.
  - **Size:** small.
- **Lips that follow the words.** Loudness only opens and closes the mouth.
  Aligning the line's text to its audio would give real mouth shapes per
  sound.
  - **Need:** an open aligner whose license fits ours, and a map from its
    sounds to FO4's lip targets.
  - **Size:** medium.

### <a id="later-steps"></a>The steps not started yet

- **Voice audio (6).** If the game plays a codec other than xWMA inside
  `.fuz`, voice mods could be built on any OS, and a tool could re-encode
  oversized voice packs. That depends on the spike
  ([table](fo4_ck_replacements.md#today)).
- **Precombines and previs (8).** Today a mod that edits a precombined
  cell breaks its precombines, and the fix is a CK rebuild. Our own baker
  would make "rebuild the precombines this load order broke" possible
  without the CK. Very large, and the CK route comes first.

## <a id="toolkit"></a>All of it together

### <a id="ck-free-kit"></a>A CK-free build kit for mods

One command that takes an FO4 mod's sources and writes the finished mod:
archives, compiled scripts, AnimTextData, lips, FaceGen and collision, on
any OS, the same bytes every run. Each piece above is one part of it.

- **Gains:** mods that build on Linux and the Steam Deck; release builds
  anyone can repeat and check; mod authors without the CK installed.
- **Size:** medium on top of the pieces; it is mostly a front end and the
  load-order reading the [dark-face fixer](#dark-face) needs too.

### <a id="ci"></a>Mods built by continuous integration

Repeatable output means a mod's repository can build and check itself on
every push (for example on GitHub's Linux runners): compile the scripts,
pack the archives, bake new faces, and compare against the last release.
No Bethesda tool can run there today.

- **Size:** small once the [build kit](#ck-free-kit) exists.

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
would make problems visible at a glance, such as the faces the census still
ranks worst after the [shader port](fo4_facegen_plan.md#ck-face-shader).

- **Size:** small if it shows the textures flat; medium with rendered
  heads (it shares a renderer with [portraits](#portraits)).
- **As a spin-off:** the same viewer comparing any two load orders, such as
  two character replacement mods, is planned as its own tool
  ([appearance comparison](appearance_compare_tool.md)).

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
4. **[Our Caprica fixes upstream](#caprica-upstream):** the fixes exist,
   and every Caprica user has the miscompile.
5. **[The archive check](#ba2-check):** small, and it catches a silent
   Archive2 loss that any mod author can hit.
6. **[AnimTextData for any mod](#anim-text-tool):** nobody else offers it,
   and most of it is built.
