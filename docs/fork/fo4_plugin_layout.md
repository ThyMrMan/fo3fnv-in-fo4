# Plan: the plugin layout, DLC, mod patches and incremental builds (2026-10-30)

How the converted game is split into plugins so FNV's DLC and other mods'
content convert on top of it, and how a build remakes only the records a
change touches. Status lives in the ROADMAP; this file holds the design.

## Contents

- [Where things stand](#now)
- [The layout](#layout)
- [FormIDs across plugins](#formids)
- [Part A: a source with masters (DLC)](#dlc)
- [Part B: mod patch plugins](#mods)
- [Part C: the rules plugin](#rules)
- [Part D: incremental records](#incremental)
- [Phases](#phases)
- [Save games](#saves)
- [Considered and left out](#left-out)
- [Open questions](#open)

## <a id="now"></a>Where things stand

Measured on the 2026-10-30 whole-map build:

- **One plugin**, `FalloutNV.esp` (438 MB): 694,264 records, all but 19
  its own (the 19 are overrides of Fallout4.esm settings). Largest kinds:
  REFR 301,320, INFO 207,486, DIAL 66,236, CELL 30,109, LAND 29,180, SCEN
  14,835. Masters: Fallout4.esm, FalloutHelpers.esl, XDI.esm, plus every
  plugin the replacement table names (`replacements.extra_masters`,
  `fo4_import/spike/cell.py` `MASTERS`).
- **FormIDs:** an FNV record made 1:1 keeps FNV's object id (`fnv_id`,
  which drops the master byte); a generated record's id is hashed from an
  authored key at a site (`derive_formid`) and kept in the ledger beside the
  plugin (`FalloutNV.formids.tsv`: 397,109 entries over 191 sites, 367,250
  of them `FNV made`).
- **One source plugin per build**, read without masters (`install.source_esm`
  and the export index see one plugin). A DLC can't be built.
- **Caching** covers work on assets and faces (`pipeline/work_cache.py`,
  keyed on inputs and `code_tag(module)`), not records. A whole-map rebuild
  is 29 to 34 minutes; the 2026-10-29 profile put 680 s in finishing,
  476 s in placed references' bases, 291 s in people, 288 s in the world,
  183 s in quests.

## <a id="layout"></a>The layout

| Plugin | Holds | Masters | Rebuilt when |
|---|---|---|---|
| `FalloutHelpers.esl` | Shared FO3/FNV helpers (actor values, helper quests, globals): as now | Fallout4.esm | Rarely |
| `FalloutNV - Rules.esl` | Our systems for FNV with no FNV record behind them: the combat rules perk, the player ability, game settings, type keywords, the skill gates perk | Fallout4.esm, FalloutHelpers.esl | A rules change: seconds |
| `FalloutNV.esm` | The converted game: every FalloutNV.esm record and what is generated from one | the above, XDI.esm | A content change |
| `DeadMoney.esm` etc. | One per FNV DLC, its records and its overrides of FalloutNV.esm's | the above, the game plugin | That DLC changes |
| `FalloutNV - <mod> Patch.esp` | One per replacement source: overrides of our records pointing at that mod's | The game plugin (and DLC), the mod | The user's table changes |

FNV's own layout carries over: the DLC master on the game as FNV's DLC
master on FalloutNV.esm. The game plugin never names another mod. It is
`FalloutNV.esm`, flagged master, since 2026-10-30 (phase 1; it was
`FalloutNV.esp`): no save that matters existed, so the rename was made
while it cost nothing ([save games](#saves)).

The rules plugin is the one split with no FNV counterpart; it is worth it
only if it holds what changes most. It is [part C](#rules), last, and
optional: [incremental records](#incremental) may make it unneeded.

## <a id="formids"></a>FormIDs across plugins

The rules that already hold stay: 1:1 records keep FNV's object id;
generated records hash an authored key; the ledger keeps every id once
given. Added:

1. **Master-aware 1:1 ids.** An FNV FormID's master byte picks the FO4
   plugin: master 00 in a DLC is FalloutNV.esm, so the record is
   the game plugin's with the same object id; the DLC's own byte is the DLC
   plugin's own index. `fnv_id` takes the source plugin's master list and
   the build's FO4 master list and maps between them, never dropping the
   byte.
2. **Generated ids look in the masters' ledgers first.** Before hashing a
   new id at a site and key, a build asks each FO4 master's ledger
   (`<master>.formids.tsv`); if one holds the key, the record is that
   master's and is referenced, not made again. So a DLC gun's
   `FNV_WeaponSkillGuns` keyword is the game plugin's. A ledger ships with
   its plugin (it is already written beside it) so a user's DLC or patch
   build can read it.
3. **Overrides keep the master's id.** A DLC record overriding a
   FalloutNV.esm record is written as an override of the game plugin's
   record (the master's FormID, the merged data).

## <a id="dlc"></a>Part A: a source with masters (DLC)

FNV's DLC are dependents of FalloutNV.esm. Everything today reads one
plugin; the CLAUDE.md's "master-export blindness" is the failure to avoid.

1. **Layered export index (built 2026-10-30).** `export_records` reads an
   export's masters from its `_HEADER.txt` (`Master[i]`) and returns the
   plugin's own records, then each master's it does not override, by
   FormID; the owner is the FormID's master byte, so no record is tagged.
   An export whose master is not exported stops the build. Left on the
   plugin's own export for now: the dialogue unlock plan (`load_records`)
   and the spike-only readers in `dialogue.py` and `statics.py`; phase 4
   decides what a DLC build converts from the stack.
2. **Layered binary source (built 2026-10-30).** `install.source_walk()`
   walks the source plugin, then its master, each FormID once; the 47
   readers of `source_esm()` in 36 modules go through it (helpers that take
   plugin bytes through `plugin_walk`, None meaning the stack). FNV's DLC
   each have one master, `FalloutNV.esm`, with none of its own, so its
   FormIDs already read as the DLC's; a deeper stack raises until needed.
   Proved on Gun Runners' Arsenal (829 records): `python -m
   tools.validate.export_master_refs export/GunRunnersArsenal.esm` resolves
   1,756 references into FalloutNV.esm, 940 into the DLC and 28 engine
   forms, 0 unresolved; the binary and export stacks give the same counts
   (WEAP 301, LVLI 2,869, IMOD 91). A master byte past the plugin's
   masters is the plugin's own, as the engine reads it (one REFR does it).
3. **Layered master builds.** A DLC build needs what the game build made.
   Its ids come from FormIDs (a base-game record's FormID maps through its
   master byte) and the game's ledger (generated records, type keywords
   among them), both built in phase 2. What else it needs (forms by FNV
   name for script properties, converted scripts' names) is measured on
   the first DLC build; a manifest beside the game plugin only if FormIDs
   and the ledger don't already give it.
4. **Scripts.** Each plugin's scripts convert under their own prefix
   (`FALLOUTNV_`, `DEADMONEY_`...); a property naming a master's form fills
   through the master's FormID (step 3).
5. **Per-DLC content.** Each DLC's new creatures, mechanics and worldspace
   get the same treatment as the base game's, one plugin at a time, in the
   order [phases](#phases) gives; the content list is in
   [fo4_build_next.md](fo4_build_next.md) and the DLC answer of 2026-10-30
   (bomb collar, holograms, Sierra Madre chips, the Sink, implants, the
   Divide's ending, level cap +5 each).

**Proving it:** Gun Runners' Arsenal first (items, weapon mods, few
references), then the courier packs, then Honest Hearts. Each DLC build:
0 references into FalloutNV.esm unresolved, the game plugin's FormIDs
unchanged, FO4Edit clean with both loaded.

### <a id="dlc-build"></a>A DLC build (phase 4, built 2026-10-30)

```bash
py -3.14 -m fo4_import.pipeline.run --export export/GunRunnersArsenal.esm --out <dlc data>/GunRunnersArsenal.esm --data <dlc data> --scripts temp/fo4_scripts/GunRunnersArsenal.esm --plugin-dirs <game data> --mod-sources <app settings> --no-test-cell --replacements <table> NVDLC05VendorChestsCell
```

Before it: the DLC exported (records), its archives extracted into its
export (`asset_convert.sources.bsa_extract.extract_assets_for_file`), its
scripts converted (`script_convert.pipeline <export> --target fallout4`, same
`FALLOUTNV_` prefix: the namespace is the chain's game), and the game plugin
built. The cell argument is the DLC's own interior.

- **Its own data folder.** The DLC builds into its own folder (its own mod),
  the game plugin and its ledger found through `--plugin-dirs`; texture and
  sound staging, stale-file lists and archives stay per plugin that way
  (`<dlc> - Textures.ba2`, `<dlc> - Main.ba2`).
- **Masters.** The game plugin's masters, then it, then the DLC's own
  replacement mods (`source_ids.dependent_masters`), so a game record's
  FormID reads the same in both. A DLC built before its game plugin stops.
- **Content is what it holds.** Every base and item the DLC's plugin holds,
  own or override, is made (`cell._held_content`), and its own quests are in
  the build (`QuestScope.included(held=)`): GRA's setup quest is reached by
  no placed reference.
- **Assets and scripts layer** file by file, the DLC's first, as FNV stacks
  archives (`export_index.export_file`, `Layered`, `asset_root`): GRA ships
  its own `characters/_1stperson` clips but not the skeleton beside them.
  Scripts resolve the DLC's converted folder, then the game's; only the
  DLC's compile into its folder, the game's imported (`compile_into(masters=)`),
  so no second copy of a game script overrides it.
- **Game records.** A game record the built game plugin left out is the
  DLC's own copy, hashed from its FNV FormID (`COPY_SITE`): GRA's setup
  script adds its guns to 22 form lists the game build never reached. A game
  record the DLC build remade goes to `master_overrides.drop_unchanged`:
  identical, dropped; changed and held by the DLC, an override; changed and
  naming a DLC record (a base gun's ammo mods, a list of every gun), a form
  list merged (the game's entries, then the DLC's) and any other kind kept
  only when it loses none of the game's subrecords; anything else changed is
  the DLC build's context, dropped. The early skip of a master ledger's ids
  is off in a DLC build, since the game writes weapons under generated ids.
- **Start-game quests merge row by row** (`base.quest_merge`). The Ammo
  Type hotkey, condition and challenges quests hold one array per column; the
  DLC build remakes them from only what it reached. A rule per script keeps
  the game's rows and adds the DLC's new ones: rounds inside their ammo list
  (`ammo_switch.merge`), weapons, armor, round wear and wear perks, the
  repair rows on their side, armor tier groups renumbered onto the game's
  same eleven tiers (`condition.merge`), challenges with their stat groups
  renumbered (`challenges.merge`). Papyrus cannot grow these arrays at run
  time (128 entries; the game's are larger), so the merge is static.
- **Its own subgraph race.** The engine adds every race carrying SADD on
  HumanRaceSubGraphData, as DLC06 does, so a DLC writes its own
  (`FNV_HumanRaceSubGraphDataAdditive_<plugin>`) holding only entries for its
  own guns' keywords (`guns.write_subgraphs`); the game's 6,767 stay its
  own.
- **The game plugin's files stay the game's.** Only the game build writes
  LevelUpMenuEx's ini (a second one would point the level-up menu at the
  DLC's copy of the lists) and copies `F3NV.dll`.
- **Two DLCs overriding one record** (a form list, a merged quest): the one
  loading last wins, each holding the game's entries and its own. Not met
  yet with one DLC built.

**Gun Runners' Arsenal, measured:** 979 records (38 guns, 160 weapon mods, 27
ammo, 131 leveled lists, 51 recipes, the vendor chest cell with 23
references, the setup quest and its 21 scripts, all compiling); FO4Edit 0
errors with FalloutNV.esm loaded (`tools.validate.fo4_check`; on 2026-10-30 FO4Edit twice stopped at its Module Selection window despite `-autoload` and wrote no result until OK was pressed). Overrides of the game: the 5 vendor loot
sacks (its 3 new items each), 32 form lists merged, Ninja and the combat
rules perk (supersets), and the three quests merged (2026-10-31): the Ammo
Type hotkey 20 → 21 lists and 68 → 96 rounds, condition 197 → 235 weapons and
20 → 27 round wear marks, challenges 61 → 78 (GRA's 17). Its own subgraph
race: 2,285 entries, all on GRA's 35 gun keywords. Its folder also holds
4,190 loose files identical to the game mod's, remade on the way (open: the
build should not write them; deployed without them), and 179 first-person
pistol poses that differ on purpose: GRA ships its own `1hp` aim clips,
which FNV loads over the game's. Left out: the 94
references in `TestMentats`, a debug cell the game never built. Voice files
still read `sound/voice/falloutnv.esm`; GRA has none, the story DLC will.
Not played.

## <a id="mods"></a>Part B: mod patch plugins

Today a replacement (an FO4 mod's gun, creature or outfit standing in for
FNV's) makes that mod a master of the game plugin, and in `item` mode
references point straight at the mod's record. Adding or removing a mod
rebuilds the whole game and moves references.

**The proxy rule.** The game plugin always has its own record for every
FNV form it converts, on the built-in stand-in (Fallout4.esm), and every
reference points at that record. A replacement never repoints references;
it overrides the proxy:

| Kind | The patch's override of our record |
|---|---|
| NPC or creature | TPLT to the mod's actor, with the template flags that take its traits and model |
| Weapon, armor, item | The mod record's model, data and parts (its OMODs are the mod's, so the mod is the patch's master) |
| Leveled list | Entries swapped where the table says |

A patch plugin holds those overrides for one source (or one combined
patch), with masters: the game plugin, the DLC it touches, the mod.
Building it reads the game build's ledger and the mod, not FNV's whole
export, so it takes seconds. The app's Replacements screen writes the
table as now and builds the patch; Required mods lists the patches' masters.

The pure build stays what ships; the patches are the user's. Mod authors
patch against the game plugin as against any master.

## <a id="rules"></a>Part C: the rules plugin

What goes in: records our systems make that no FNV record owns and no
game record must name back. The combat rules perk, `FNV_PlayerRules`, the
game settings (`GMST`), the skill gates perk, the type keywords (their
FNV names are keys, not records). Game records name them (an NPC's perk
list, a weapon's keywords), which is the allowed direction. What stays:
anything naming FNV content (the new-game quest names VCG00; the character
rules quest names FNV's perk list; aim models and projectile copies belong
to their guns).

An ESL holds 2,048 records in FO4 (object ids 0x800 to 0xFFF); the
candidates are a few hundred. Build it with the game plugin's build at
first; the gain is a separate rules-only build of seconds. Measure first
whether [incremental records](#incremental) already make a rules change a
short rebuild; if so, skip this part.

## <a id="incremental"></a>Part D: incremental records

### <a id="stage-times"></a>Stage times (built 2026-10-31)

A build prints `stage <name>: <s>` lines before its total
(`pipeline/stage_timer.py`). Each stage counts its own time only: a stage
run inside another is taken out of the outer one, so the lines add up to
the build less the mesh cache step printed before them. Stages are the
makers in `spike/cell.py` and the end of the build in
`spike/build_finish.py`. Base forms and items are charged by record type
wherever they are first made (`base NPC_`, `item WEAP`), as a base is made
on first request by whichever stage asks; those lines are what phase 6
caches. Export files read for the first time are charged to the stage that
read them.

**Measured, whole map, 2026-10-31** (3,023 s; meshes cached, 0 scripts
changed): the Creation Kit's own-rig animation data 1,231 s (the plugin
write itself 4 s; next build, 2,862 s in all), item WEAP 440, people 229,
worlds 183, voice 167, quests 165, script compile 143, assets 81, base STAT
74, collision 72, sounds 69, closing records 31, item ARMO 28, quest scope
23, the rest under 12 each. Item WEAP is mostly gun clips: 86 guns on FNV
clips at about 8–9 s each, retargeted and written again every build
(only the decoded FNV clips are cached; profile of two guns). The
108-minute build earlier that day was the first after gun-code edits.

**Profile of a whole-map rebuild (cProfile, 2026-10-31,** a scratch copy of
the data folder and its staging; profiled times, the whole build 2,147 s
against 2,862 s unprofiled the run before). The hot spots, by what fixing
each would save:
- *Dialogue options:* `conversation._option` 221 s over 10,513 calls,
  under `talk` (148 s) and `_greetings` (109 s): a rescan per option.
- *Land layers:* `land_layers.blend_borders` 218 s and `limit_textures` 65 s
  of the worlds stage's 314 s, per-texel Python (182 M `numpy.zeros`, 88 M
  `sum` calls).
- *Script names:* `attach.named_lower` 231 s (1.1 billion `str.lower`
  calls), the lower-cased name map rebuilt on each of 76,467 calls from
  `properties` and `mirror_global`.
- *Own rigs rebuilt every build:* `creatures._own_rig` 159 s (bodies
  105 s, skeleton NIFs through Elric 22 s, clips 18 s) with nothing changed.
- *File reads:* 261,521 opens at about 1.4 ms each (345 s): work-cache
  lookups 156 s (31,969 reads), `elric_cache.write_new` reading each target
  back to compare 64 s, the compile's source and header hashes 78 s,
  `script.with_types` re-reading every script 48 s.
- *Voice:* `voice.convert` 120 s writing nothing: 9 recordings fail every
  build and are tried again (about 13 s each).
- *Not a rebuild cost:* the CK's 220 s of polling (`creation_kit.run`) was
  the scratch copy missing its animation-data key; a real rebuild skips it.
  Caprica compiled all 13,523 scripts; `FormIDs from a counted key: 0`.

**Fixed from it (2026-10-31; none changes a record):**
- *Script names:* `attach.NameMap` keeps the lower-case index as names are
  set, the last spelling in insertion order winning as the rebuild did
  (checked against it over 2,000 random changes). This was also most of the
  dialogue time: `_option`'s cost was filling each line's script properties.
- *Land layers:* `blend_borders` makes a texture's zero array only when it
  is missing (`setdefault` built one per call), `limit_textures` sums each
  texture's shares once. Byte-identical on 625 WastelandNV cells, 3.8 s to
  2.8 s. The rest is the per-vertex average; vectorizing it has to keep the
  order textures join a quadrant (ties in kept_textures follow it), so it
  was left.
- *Voice:* `voice.convert_new` records each job that fails
  (`<staging>/VoiceFailed/<plugin>.json`, by destination, source and
  transcript hashes) and does not try it again until one changes.
- *Compile:* `fo4_import.base.file_stamps.Stamps` keeps the sources' hashes,
  declarations and words, the headers' hashes, Caprica's header digest and
  `with_types`' named types by file size and time; memos in
  `output/fo4_cache/compile_stamps` and beside the script stage, not in the
  deployed Scripts folder. The header digest now hashes each file's SHA-1,
  so the first build after it compiles everything once.
- *Own rigs:* a body (`rig_body`) and a skeleton.nif with its ragdoll bones
  (`rig_skeleton_nif`, the Elric run) are work-cache entries keyed by their
  FNV meshes, bones, body name and fire nodes; a body's textures are FNV's
  export, not keyed.
- *Not changed:* `elric_cache.write_new` reading each target to compare, and
  the work-cache reads, need a memo shared by the mesh pool's processes.

**The two caches built from it (2026-10-31):**
- *Gun clips* (`GunClips.convert`): each gun's conversion is a work-cache
  entry (site `gun_clips`, code tag of `havok.gun_clips`) keyed on the WEAP
  fields it reads, its keywords and the gun's own for each, the FNV NIF's
  bytes, the receiver, placement and surfaces (pickled: numpy's repr
  elides big arrays), and a hash of the FNV first-person clip folder (6 MB,
  read once a run). The value is the result, the entries the gun adds to
  the subgraph race, and every clip and AnimTextData file it wrote; a hit
  writes them again through `elric_cache.write_new` (touched when the same,
  so `stale_files` keeps them). Two guns through `gun_quick_convert`: 18.7 s,
  then 7.0 s.
- *The Creation Kit's animation data* (`anim_info.generate`): skipped when
  `inputs_key` matches the last run's (`<plugin>.animinfo.key`) and every
  file it listed is still there. The key hashes the plugin's RACE, IDLE,
  MOVT, KYWD and AACT records and every file under the data folder's
  `Meshes/Actors` (4,161 files, 50 MB), with the CK's arguments. Its output
  (17,892 files) covers the gun subgraph race too, so a gun-clip change
  still reruns it; a fix elsewhere does not. The key is the list of its
  5,071 inputs, one hash each (0.7 s), kept as `<plugin>.animinfo.key`; a
  rerun prints which inputs changed and which listed files went missing.
  The second whole-map build with the key still reran (434 s) with no
  input list yet to tell why; the rig graphs and skeleton NIFs differ from
  an older build's (2 and 4,814 bytes for the gecko's), not yet shown to
  differ build to build.

### <a id="shared-state"></a>Shared state a unit touches (survey, 2026-10-31)

What a unit writes that other units or the end of the build read, from a
read of `fo4_import` (the points marked V were checked against the code
a second time). Each needs one of:
**journal** (record and replay), **after assembly** (rebuild from the
written records at the end), **always run** (setup the units depend on).

- **Memos write records (V for `CellBuilder.base`).** Nearly every maker
  keeps a "made once" dict whose first call also adds the record
  (`builder.made`, `Items.made`, `Npcs.made`, `creatures.made`,
  `Packages.made`, `Sounds.made`, `AmmoMods.made`, `Condition.made`,
  weathers, imagespaces, music, swaps, terminals and about 25 more). A
  replay must restore the memo with the records, or the next live unit
  that asks writes the record twice. Journal.
- **Record order (V).** The plugin writes each group in `add_record` order
  (`tes5_import/base/writer.py` `write`), so a replay in another order
  gives a valid plugin with different bytes. Replay must keep first-request
  order, or the writer sorts each group by FormID (a one-time byte change,
  no FormID moves).
- **Counted FormIDs (V).** `CellBuilder.new_id(owner)` without a key gives
  `owner n` by call count (`owned`); 98 ids in the whole map
  (`FormIDs from a counted key`). Owners that repeat: INFO parts, greeting
  INFO/DIAL, `SPEL <owner>`, swaps, the stand-in door, radio program
  steps, emittance weathers. Whoever asks first takes n = 0, so a replay
  changes them unless the counter journals per unit. Better: key them on
  authored data and retire the counter (ledger-pinned, 0 FormIDs moved).
  `keyed` (duplicate check), `top` (max object id) and the writer's
  `_derived`/`_derived_taken` and ledger moves journal too.
- **Accumulators read at the end:** `scripts.used` (the compile and its
  stale-script removal), `scripts.named` (every later script fill),
  `scripts.talks`, `Equipment.by_anim`, `creature_guns` and `weapon_ammo`
  (read by creature units), gun-clip `added` entries (the subgraph race),
  `AmmoMods.loaded`, `Condition.weapons`/`armors`, `Consumables.pending`
  and `fired_by`, `poisons.coats` (unsorted), `Sounds.jobs`,
  `say.voiced`/`silent` (voice jobs, and the stale voice set-aside),
  `Idles.used`, `Packages.greets`/`topics`/`pending`/`scripted`,
  `Perks.pending`, `Radio.made`, `Poses.placed`, `Readiness.entries`,
  `builder.meshes` and `weapons` (Elric and weapon dressing), `npc_ids`,
  `actor_ids`, `held`. Journal.
- **First-wins snapshots.** `Readables.form_map` and `Items._built` copy
  `scripts.named`, `actor_refs`, globals and factions when first called; a
  package's plan comes from the first NPC that runs it; the first spelling
  of a scene keys it; `Idles.used.setdefault`; `Packages.topics.update`
  (last wins). Results depend on unit order: journal, and replay in order.
- **Files outside the builder (V for the last two).** `elric_cache._HELD`
  (pre-Elric bytes for `finish`), `ba2_pack._RUNS` staged textures (a
  texture not re-staged this run is deleted from the archive), and
  `stale_files.made` (files older than the build start are pruned). A
  replayed unit must re-stage its textures and touch its files, or both
  steps remove them. Journal.
- **After assembly already, or should be:** `CombatPerk.write` patches
  every NPC_, `clear_dangling`, `drop_unchanged`, challenges and standings
  (they read `creatures.made`, `npc_ids`, `items.made`), the anim lists
  (could be rebuilt from WEAP records).
- **One count decides behavior:** `build_finish._write_plugin` runs the
  Creation Kit's animation data only if `counts['own-rig creature races']`;
  a build replaying every own-rig creature would skip it. Read the written
  RACE records instead. Every other count is report only.
- **Always run:** `bases`, `parts`, `actor_refs` reservations, places and
  regions, `ref_ids`/`cell_ids`/`door_links`, `forms`, per-world
  imagespace; the setup singletons from `_object_makers` and `_cell_quests`.
- **Harmless:** the `functools.cache` readers in spike and pipeline are
  functions of file bytes; no module cache holds maker output. Per-asset
  caches in Equipment (poses, fits, worn paths) write files on first use
  (inferred).
- **What a recorder hooks:** `export_index.export_records`, `own_records`,
  `export_file`, `Layered`; `install.source_walk`, `plugin_walk`,
  `source_esm`; `tes5_reader.walk` over `builder.fo4`; FO4 `Archives`
  reads; `mesh_cache`/`work_cache` lookups; built-plugin reads
  (`built_plugins`, `master_ledgers`, `held_by`).

**What this changes in the plan.** Three changes before phase 6's recorder
(built 2026-10-31):
1. *The 98 counted FormIDs* were all one record: the TXST each worldspace
   made again for a land texture another had made (`TXST <LTEX> 1`), as
   `Exterior._ltex` kept its memo per worldspace. The whole map wrote 174
   LTEX records for 76 FormIDs, 98 of them duplicates. The memo is the
   build's now (`CellBuilder.land_textures`): one LTEX and TXST per FNV
   LTEX, no counted key left, and 98 duplicate LTEX and their TXST gone.
2. *The own-rig animation step* runs when a written RACE names in a
   subgraph entry a graph in the data folder (`anim_info.needed`), not on a
   count: the game plugin yes (15 races), GRA no.
3. *Record order.* `LedgerWriter.write` puts each top group of plain records
   in FormID order (stable); a group holding GRUPs (cells, worlds, topics)
   keeps its own, as its children follow their parents. A one-time byte
   change, no FormID moved.

The rest is the journal as designed, with the memo-plus-record pairing as
its core rule.

A build remakes only the records whose inputs or code changed and writes
the plugin from the rest as cached, byte for byte as a clean build would.
Hashed FormIDs already make a record independent of build order, which is
what makes this possible.

**Units.** The build is cut into units, each the records one authored
thing makes: a placed cell (CELL, its references, land, navmesh), a base
form (an NPC, a weapon, a container), a topic (DIAL, its INFOs, its
scenes), a quest (QUST, its aliases, fragments). These are the makers the
build already has (`cell._ref_ids`, `_people`, `_world_groups`,
`_quests`), run per key.

**A unit's journal.** A unit runs inside a recorder that keeps:

- the records it wrote (signature, FormID, bytes);
- the other units it asked for, with the FormIDs they returned (a cell
  asks for its references' bases);
- the export records it read, by FormID and content hash, and the
  Fallout4.esm records it read;
- counter increments, readiness entries, ledger entries and script names
  it added to shared lists.

**Its key** is the hash of: the unit's site and authored key, the code tag
of the modules it ran (`code_tag` as the work cache uses, per module), the
hashes of the export records it read, and the dependencies' FormIDs. The
read set is recorded, not declared: the export index and the Fallout4.esm
reader log each read to the running unit.

**A build** walks the units as now; a unit whose key is in the cache
replays its journal (writes its records, re-registers its requests, adds
its counts) instead of running. Requests replay too, so a cell that
replays still makes sure its references' bases exist.

**Passes that touch every record** (the combat perk added to every NPC,
dangling script properties cleared, room and portal fixes) run after
assembly on the written set, so a unit's output never depends on them;
each must be a cheap transform.

**Correctness first.** The check is the rule: an incremental build and a
clean build of the same tree write byte-identical plugins and ledgers.
A test runs both on the Rig Test region after every change to the build;
the whole map is compared before turning it on by default. A unit that
cannot be journaled (it reads a global the recorder doesn't see) is marked
always-run and counted, so the gap is visible.

**Order of units to cache**, by time: placed references' bases and items
(476 s, then 500 s inclusive in `items`), the world (288 s), people
(291 s), quests (183 s), then dialogue. *Revised 2026-10-31 from the stage
timer:* 440 s of the bases was gun clips (item WEAP), now in their own
cache, and the other base makers come to about 2 minutes (STAT 74 s, ARMO
28 s, the rest under 7 s each). So bases go last; people (229 s), worlds
(183 s), quests (165 s) and the voice step (167 s, outside the units)
come first. Re-rank on the first build with both caches warm. Finishing (680 s: script compile,
archives, plugin write) already caches its parts or is the write itself;
measure it again once the units cache.

**Expected:** a fix in one maker (dialogue options, a creature edit)
rebuilds that maker's units and replays the rest. A rules change, units
untouched, replays everything.

## <a id="phases"></a>Phases

| # | Work | Done when | Size |
|---|---|---|---|
| 1 | The game plugin as `FalloutNV.esm`, flagged master (built 2026-10-30, not played): voice and FaceGen folders filed under the old name move once, and the FaceGen meshes' face texture paths (the CK writes the plugin name into them; purple faces when stale, played 2026-10-30) follow (`spike/plugin_rename.py`) | The game plays as before | S |
| 2 | Master-aware FormIDs and ledgers read from masters (built 2026-10-30: `base/source_ids.py`; `LedgerWriter` reuses a master's generated id and leaves its record to the master; each FO4 plugin takes its source plugin's name) | The game rebuilt with 0 FormIDs moved; a unit test of a two-plugin build | M |
| 3 | Layered export and binary source (built 2026-10-30; [part A](#dlc)) | A DLC export resolves every FalloutNV.esm reference | M |
| 4 | Gun Runners' Arsenal (built 2026-10-30, FO4Edit clean, not played; [as built](#dlc-build)), then the courier packs | Built, FO4Edit clean, played | M |
| 5 | Proxy records and mod patch plugins; the app builds patches | The with-mods table as patches; the game plugin byte-identical with and without them | M-L |
| 6 | Incremental records: the recorder and journal, one unit kind (bases) | Rig Test incremental = clean, byte for byte | L |
| 7 | Incremental for every unit kind | Whole map incremental = clean; a one-maker fix rebuilds in minutes | M |
| 8 | Honest Hearts, Dead Money, Old World Blues, Lonesome Road | Each built and played, with its own mechanics | L each |
| 9 | Rules plugin, if 7 leaves rules changes slow | Built; game records name its forms | S-M |

Phases 2 and 3 come before any DLC; 5 and 6 don't depend on the DLC
phases and can run beside them.

## <a id="saves"></a>Save games

A save names records by plugin filename and object id. So:

- The game plugin became `FalloutNV.esm` on 2026-10-30, which breaks every
  earlier save; none mattered. From here its name is fixed.
- A record moved to another plugin (the rules plugin) is a new form to a
  save: the player's perks and ability come back through the new game
  script on load (`GivePerks` already re-adds), the settings need none.
  Measure the records that move, then ask before shipping it.
- DLC and patch plugins only add; the game plugin's records keep their ids.

## <a id="left-out"></a>Considered and left out

- **Plugins by record type** (creatures, world, dialogue): FO4 plugins
  reference only their masters, and FNV's content references in circles
  (quests alias placed actors whose packages and scripts name quests), so
  the seams would cut references; and each part reads most of the export,
  so it would not build faster.
- **Merging the DLC into one plugin:** every DLC object id would need a
  new range (FNV's DLC reuse low ids), fixed forever once saves exist, and
  users could not leave a DLC out.

## <a id="open"></a>Open questions

- Does the master flag change how FO4 loads the plugin's temporary
  references or navmesh (phase 1's play test)?
- One combined mod patch or one per mod source? One per source lets a
  user drop a mod by dropping its patch; one combined is simpler to load.
- Does a DLC build need more of the game build than FormIDs and the
  ledger give (phase 3 measures it), and does the ledger ship beside the
  plugin or in the app's work folder?
