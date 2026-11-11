# The plugin layout, DLC, mod patches and incremental builds (2026-10-30)

Built: phases 1–4 (the game plugin as `FalloutNV.esm`, master-aware
FormIDs, layered export, Gun Runners' Arsenal and the courier packs) and
phase 5a ([part E](#which-builds)); the game and DLC plugins are not
played as built (only the renamed faces were, 2026-10-30). Not built: mod
patches, incremental records, the story DLC and the rules plugin
([phases](#phases)).

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
- [Part E: which plugins need a build](#which-builds)
- [Phases](#phases)
- [Save games](#saves)
- [Considered and left out](#left-out)
- [Open questions](#open)

## <a id="now"></a>Where things stand

Measured on the 2026-10-30 whole-map build, before this plan's phases.
Since then the game plugin is `FalloutNV.esm`, a DLC builds on a layered
source ([part A](#dlc)), and builds cache more work ([stage
times](#stage-times)); records are still not cached.

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
- <a id="master-copies"></a>**What the game mod ships stays out of the DLC's
  folder** (`pipeline.master_copies`, 2026-10-31). A DLC build remakes the
  game meshes, materials, gun clips, animation data, textures and sounds its
  records reach. Once the build is done, a loose file byte-identical to the
  game data folder's file at the same path is deleted (`drop_loose`). A
  texture the game's last pack staged with the same signature (source path,
  size and time, or work-cache key) is not staged
  (`ba2_pack.share_masters`). A sound from the game's export that the game
  converted is not converted, and an old copy is deleted (`master_sound`).
  Files that differ stay, such as GRA's own `1hp` aim clips. Measured on the
  2026-10-31 GRA folder before the change: 10,549 loose files identical to
  the game build's (5,327 animation data, 3,666 actor clips, 890 meshes, 662
  materials), 1,610 of 1,631 shared textures with the game's signature, and
  115 sounds.
- <a id="dlc-deleted"></a>**A record the DLC deletes.** FNV DLC delete game
  records with a bare Deleted (0x20) stub: Honest Hearts deletes 10
  references in `NorthernPassageINT` (its invisible cave door, a collision
  marker and 8 lamps). FO4 mishandles a plugin's deleted master reference,
  so the layered export reads such a placed reference as the game's, with
  Initially Disabled (0x800) set, which is xEdit's "undelete and disable"; the
  cell build then writes a disabled override. Any other deleted record is
  gone from the export view (`export_index._layered`).
- <a id="dlc-voice"></a>**Voice files by the plugin holding the line.** FNV
  files a line under `sound/voice/<plugin holding its INFO>/<voice type>/`,
  naming it by the INFO's FormID with the load-order byte 0: Honest Hearts'
  Joshua line `010101F6` is `honesthearts.esm/.../..._000101f6_1.ogg`, while a
  game line it changes stays in `falloutnv.esm`. `voice.fnv_folders` gives a
  voice type's folder in each plugin of the export in master-byte order, and
  `index_recordings` keys each file by its folder's byte. FO4 looks a line up
  under the plugin owning its INFO too, so a DLC build voices only its own
  INFOs (`voice.own_lines`); the master INFOs its builder carries are the game
  build's. Without that filter the first Honest Hearts build re-converted about
  180,000 of the game's lines under `Voice/HonestHearts.esm`.
- <a id="dlc-dialogue"></a>**Dialogue: only the DLC's lines.** A DLC build
  builds the lines its plugin holds (`say_topics.dlc_lines`): its own INFOs,
  and its overrides of game INFOs that change more than `PNAM` (the line
  before it, which FNV rewrites on a game line when a DLC inserts one beside
  it). Game quests the build reaches keep their scope and script names, but
  their lines, topics and scenes are the game build's. Honest Hearts holds
  1,238 INFOs: 1,236 its own (629 of them in 79 game topics such as Attack or
  PLAYERFIREWEAPON, all under its own quests) and 2 GREETING lines of
  `VDialogueMrHouse` that differ from the game's only in `PNAM`. Before this,
  the build rebuilt 6 game quests whole: 37,510 INFO and 18,199 DIAL
  overrides, plus 17,744 game lines minted again under DLC ids.
  `drop_unchanged` judges records inside a group as it does top-level ones
  (it used to keep a whole quest group as soon as one DLC record was in it).
  A game record whose children group keeps a DLC record stays, as the game
  plugin's own bytes when it changes nothing: the build's greeting and patrol
  quests and their topics hold the DLC's lines under the game's ids, the way
  an FO4 plugin adds a line to a master topic. The topic's TIFC count is
  left as the game's; xEdit compares it with `cpIgnore`. The masters' lines
  the build leaves out are still read for one judgment, whether a Choices
  menu's conversation can ever end (`Conversations._leaves`, through
  `Hub.outside`; `SayTopics.outside` keeps them from the one INFO pass):
  without them every menu answered by game lines looked never-ending, and
  YUP wrote `[Leave]` and a silent exit line on 682 menus (467 with no YUP
  line among their topics). With them, measured on the export without a
  build, none of the 682 keeps it; the game build has no outside lines and
  is unchanged. Left open: an ally's
  reply to a DLC bark ([bark replies](fo4_pipeline.md#bark-replies)) that
  only game quests answer is not copied, since the copy would hold the game's
  line under its game id. Honest Hearts has 6 such barks (3 Flee →
  FleeResponse, 3 AvoidThreat → AvoidThreatResponse).
- <a id="dlc-greeting"></a>**A dependent plugin opens the greeting with its
  own line** (2026-11-10, not yet played). Every talk starts from one silent
  Greeting line ([greeting scene](fo4_pipeline.md#greeting-scene)), which
  passes only for the speakers the GREETING lines name. A mod build keyed
  that line `INFO greeting GREETINGS`, so it took the game's id; its copy
  named only the mod's speakers, lost the game's conditions, and
  `drop_unchanged` dropped it. The game's line names only the game's
  speakers, so a mod's own NPC passed no Greeting line and activating her
  did nothing (NVWillow's Willow: FalloutNV.esm's line has 814 conditions,
  none hers; NVWillow.esp held no opener at all). Her GREETING lines did
  reach the game's greeting scene, under its topic. When the shared
  `FNV_Greetings` quest is a master's (`cell._opener_home`), the opener now
  sits in a start-game quest of the plugin's own, `FNV_Greetings_<plugin>`,
  keyed `GREETINGS <plugin>`, and still starts the game's greeting scene. It
  is a quest of its own because no Fallout4.esm quest holds two Greeting
  topics (325 topics, 325 quests). It names only the speakers the game's
  built opener does not (`conversation.opener_forms`; FalloutNV.esm's names
  584), so a game NPC a mod adds greetings to (YUP) still opens through the
  game's line and its force-greet lists; with none left, no opener is
  written, though the mod's lines still join the scene. Left open: a mod's
  force greet on a game NPC still opens nothing. The game build's keys are
  unchanged.
- <a id="dlc-prompts"></a>**A reworded option in a game menu keeps the
  game's place.** A menu's options and answers pair by position: the
  player's topic holds each option and its pads, the speaker's topic its
  answers in the same order, and the engine tries the answers from the
  picked option's place on. An option's FormID was keyed by its prompt text,
  so a plugin rewording a game line's prompt (YUP fixed spacing and case in
  21 Topic-list options, and reworded a few) wrote a new option, while its
  answer kept the game's id and place. YUP's plugin added 54 options and 31
  answers to the Topic list's two topics; every game option after them
  answered 23 places too far down, missed its line and fell through to the
  silent `[Leave]` exit. Vulpes Inculta's "I'll do as you ask." ended the
  scene without his farewell, whose result script ends his force greet, so he
  greeted again (Papyrus trace, 2026-11-10). Keying the option by the
  master's prompt (first fix) cut YUP's unbalanced game menus from 124 to 6,
  but Vulpes's hub still had 34 options to 31 answers: YUP gives two of
  Jimmy's three "I hear you were a slave of Caesar's Legion." lines
  (0015697A, a prompt and two pads in the game) a new prompt, "Tell me about
  yourself.", splitting one option into two, and the second took new ids
  while its answers sat in the game's pad slots. `Conversations._slot` now
  keys each option and pad by the game slot of the answer beside it: the
  master prompt's option or `pad N`, N its line's place among that topic,
  quest and prompt's master lines (`say_topics.prompt_places`, record
  order), falling back to the plugin's own text when the slot is taken. A
  build without masters is unchanged; on the exports the official DLCs move
  0 lines. The YUP build of 2026-11-10 19:36 has the shared Topic list
  balanced and 5 menus left (8 extra options), two causes:
  - **Shared Infos:** a topic borrowing another's lines (00167494, Francine
    Garret's `[Speech 35]` pair, a copy per quest) keys its copies by text,
    since `_slot` skips borrowed copies; YUP's single spaces miss the game's
    double-spaced prompts. `prompt_places` would need the copies, in
    SharedInfo order after the topic's own lines.
  - **The mod's ledger shadows the master's:** `derive_formid` takes the
    plugin's own kept id for a key before a master's, so a key YUP kept from
    an older build ("It's time for us to part ways. ... pad 4") stays a new
    record though the game has it. Every mod ledger holds such keys (YUP 572,
    52 INFO and 35 DLBR among them; most are `FNV gun anims KYWD`, in DLCs
    too). Taking the master's first is drift in every plugin: not done.
- <a id="dlc-placed"></a>**Game refs in the DLC's worldspace and cell groups.**
  The cell builder adds worldspaces and cells as pre-built groups
  (`add_raw_group`), which `top_records` and `patch_records` skip, so
  `drop_unchanged` never judged a placed ref, navmesh or LAND. Honest Hearts
  shipped 33,357 REFR, 969 ACHR, 69 NAVM and 2 PHZD overrides identical to
  FalloutNV.esm's, and Dead Money 30,352 REFR and 938 ACHR (found by
  `preflight --audit dlc`), though their sources override 94 REFR and 3 ACHR,
  and 165 REFR. `FO4PluginWriter.raw_groups` and `patch_groups` let it prune
  those groups like nested records: a game cell or worldspace heading a kept
  ref stays as the game's own copy. A masterless build never calls it.
- <a id="dlc-stale-ids"></a>**A master ledger id the master no longer holds.**
  A game ledger keeps every id an earlier game build derived, including ones
  for records it no longer writes: `FNV AMMO 1469274`
  (`AmmoSmallEnergyCellTurret`) keeps `EC9262`, but FalloutNV.esm no longer
  holds that ammo. Dead Money took that id, then `drop_unchanged` dropped its
  record as "not in its master", leaving 3 references dangling.
  `LedgerWriter.use_master_ledgers` now takes the built masters' FormIDs
  (`CellBuilder.in_masters`), and a master id only counts while its master
  holds it. Otherwise the key hashes to the DLC's own copy, as `fnv_id` does.
  No shipped id moves: the master never held the record, and a masterless
  build passes no FormID set.
- <a id="dlc-poses"></a>**A dead actor on a game base.** A DLC's placed corpse
  can use a game NPC or creature (a dead wastelander, a molerat). Its ragdoll
  pose needs the base's race skeleton, so `ragdoll_pose.Poses` also reads the
  built masters' NPC_, LVLN and RACE records (`_master`), and looks for a race's
  loose skeleton in their data folders too (a game own-rig race such as the
  nightstalker). Before this, Dead Money left out 41 poses as "no FO4 ragdoll":
  33 human, 3 molerat, 3 nightstalker, 1 Mister Gutsy, 1 sentry bot.
- <a id="dlc-lod"></a>**No LOD for a master's worldspace.** A DLC build that
  places refs in a game worldspace (Honest Hearts' Northern Passage corner of
  WastelandNV, built as a region) writes no object or terrain LOD for it
  (`cell._world_groups`). Its bake covered only the region, and the same tile
  names replaced the game build's whole-world tiles: Honest Hearts' 3
  WastelandNV object tiles were 3–8 times smaller than the game's. The DLC's
  own objects there get no distant LOD. Its own worldspaces (Zion) bake as usual.
  The texture staging prunes worldspace LOD textures a build no longer writes
  (`ba2_pack.OWN` includes `terrain/fnv_`); before, Honest Hearts' 3 old
  WastelandNV object-LOD textures stayed staged and packed into its
  `Textures.ba2` (`preflight --audit dlc`, master-files).
- <a id="dlc-lists"></a>**A game form list the DLC adds to.** Two plugins
  overriding one record do not stack: the last loaded wins, and the other's
  entries are gone. A play test found every DLC's weapons and armor without
  condition, because Honest Hearts (last in the load order) overrode the
  game's condition quest with only the game's and its own items
  ([the fix](fo4_condition.md#sources)). So a DLC build overrides no game form
  list it only adds to. `master_overrides.added_forms` finds the new entries
  (every other subrecord alike; kind "list entries added at run time", also
  for a list the DLC holds in its source), and `spike.list_adds` writes one
  start-game quest per DLC (`FNV_FormListAdds_<plugin>`) whose
  `F3NV_FormListAdds` script puts each one in its list (`FormList.AddForm`,
  kept by the save, stacking across plugins). An added entry naming a record
  of the DLC that the build never wrote is left out: Honest Hearts' copy of
  `FNV_StandingsCrimeFactions` names 4 game factions the game build left
  out, as copy ids the DLC build never makes. A list's added entries are not
  its authored ones (`BGSListForm::tempForms`, not `forms`), so native code
  must read both; the F3NV DLL's Pip-Boy tabs do (`pages.cpp` `ListIds`).
- <a id="dlc-perks"></a>**A game perk the DLC adds entries to.** Perk entries
  cannot be added at run time. Honest Hearts, Dead Money and Gun Runners'
  Arsenal each overrode `FNV_Ninja` and `FNV_CombatRules` with their own
  weapons' entries added (40 to 80 subrecords), and the last loaded won
  (`preflight --audit dlc`, shared PERK). Now a perk whose DLC copy keeps its
  head and every game entry and only adds entries
  (`master_overrides.added_perk_entries`, whole PRKE…PRKF blocks) is not
  overridden. `list_adds` writes a hidden perk of the plugin's own
  (`<EditorID>_<plugin>`) with those entries. Each entry gets `HasPerk <game
  perk>` first in its perk-owner tab (tab 0), so it applies exactly when the
  game perk would; FO4 evaluates OR before AND, so an AND-ed first condition
  gates the whole chain. The list-adds quest gives the player that perk at
  start.
- <a id="dlc-script-bases"></a>**An actor base a script names.** A script's
  `ActorBase` property (`GetDeadCount` on a spawn's base) was filled only
  from the bases the build had made when the property was filled. Honest
  Hearts' `NVDLC02MS02QuestSCRIPT` names five bighorner bases its build makes
  later, so all five were None. The quest is Start Game Enabled, as in FNV,
  and its five-second timer ran in Goodsprings, failing about 1,500 times in
  23 minutes of the user's log. `attach.ObjectScripts.actor_base` makes the
  named NPC or creature base on demand.
  - **First version.** It made the base through `builder.base`, as for a
    placed object. That never worked: `CellBuilder.base` makes only the
    `PLACED` types, and no NPC_ or CREA is among them. Its test stubbed
    `builder.base`. The user's 2026-11-04 log still showed `MS02` failing,
    plus Lonesome Road's Start Game Enabled `NVDLC04DivideSupport`. Its
    authored 0.1 s delay calls `GetDeadCount` on two templated tunneler
    creatures (`NVDLC04DivideCaveTBrute`, `...TVenom`) every pass: 4,266
    errors in 12 minutes. The script engine ran 0.5 to 1.9 s behind (a 3 s
    `Wait` came back after 3.5 and 4.9 s), and each talk paused about as
    long before the greeting's `OnBegin` started its scene.
  - **Now.** It makes the base through `Npcs.actor_form`, as a template
    does: an NPC's base, a creature's (a templated creature's template
    actor) or a leveled list's. A base that is already made keeps its
    FormID. A property filled before the people stage makes its Npcs stays
    None, counted in the build log (`ActorBase property filled before the
    people stage`).
  - `NVDLC02MS01`'s `GhostOfSheREF` and duplicates stay None while HH's yao
    guai creatures (`nvdlc02\creatures\yaoguai`) have no FO4 base: that is
    creature coverage.
- <a id="dlc-say-once"></a>**Say Once markers.** Quest stages cannot be added
  at run time, so a DLC whose master holds the Say Once marker quest
  (`FNV_TES4SayOnce`) gets its own (`say_once.SayOnce`: key
  `FNV_TES4SayOnce plugin`, EditorID `FNV_TES4SayOnce_<id>`), holding its
  lines' stages. Before this, each DLC overrode the game's quest with its
  stages merged in, and only the last-loaded DLC's lines kept their markers.
  (Before the merge, Honest Hearts' copy was dropped and FO4Edit found 866
  Say Once conditions naming a stage that never shipped.)
- **The game plugin's files stay the game's.** Only the game build writes
  LevelUpMenuEx's ini (a second one would point the level-up menu at the
  DLC's copy of the lists) and copies `F3NV.dll`.
- **Two DLCs overriding one record** (a form list, a merged quest): the one
  loading last wins, each holding the game's entries and its own. Met in play
  with seven DLCs and packs loaded: condition, the Ammo Type hotkey and
  challenges kept only Honest Hearts' items. Those systems now gather every
  plugin's rows at run time ([condition](fo4_condition.md#sources),
  [form lists](#dlc-lists), [Say Once](#dlc-say-once)), and no DLC overrides
  their quests or lists.

**Gun Runners' Arsenal, measured:** 979 records (38 guns, 160 weapon mods, 27
ammo, 131 leveled lists, 51 recipes, the vendor chest cell with 23
references, the setup quest and its 21 scripts, all compiling); FO4Edit 0
errors with FalloutNV.esm loaded (`tools.validate.fo4_check`; on 2026-10-30 FO4Edit twice stopped at its Module Selection window despite `-autoload` and wrote no result until OK was pressed). Overrides of the game: the 5 vendor loot
sacks (its 3 new items each), 32 form lists merged, Ninja and the combat
rules perk (supersets), and the three quests merged (2026-10-31): the Ammo
Type hotkey 20 → 21 lists and 68 → 96 rounds, condition 197 → 235 weapons and
20 → 27 round wear marks, challenges 61 → 78 (GRA's 17). Its own subgraph
race: 2,285 entries, all on GRA's 35 gun keywords. Its folder also held
4,190 loose files identical to the game mod's, remade on the way (left out
since 2026-10-31, [master copies](#master-copies); not rebuilt yet), and 179 first-person
pistol poses that differ on purpose: GRA ships its own `1hp` aim clips,
which FNV loads over the game's. Left out: the 94
references in `TestMentats`, a debug cell the game never built. GRA has no
voice files; voice is now filed by the plugin holding the line
([voice](#dlc-voice)).
Not played.

### <a id="courier-packs"></a>The courier packs (built 2026-10-31)

Caravan, Classic, Mercenary and Tribal: 5 to 19 records each, built as
four plugins in their own folders (`temp/profile_data_<pack>`):

```bash
py -3.14 convert.py --export-only -f CaravanPack.esm --data-dir <FNV>/Data
py -3.14 -c "from asset_convert.sources.bsa_extract import extract_assets_for_file; extract_assets_for_file('CaravanPack.esm', '<FNV>/Data', 'export')"
py -3.14 -m script_convert.pipeline export/CaravanPack.esm -o temp/fo4_scripts/CaravanPack.esm --target fallout4
py -3.14 -m fo4_import.pipeline.run --export export/CaravanPack.esm --out <pack data>/CaravanPack.esm --data <pack data> --scripts temp/fo4_scripts/CaravanPack.esm --plugin-dirs <game data> --mod-sources <app settings> --no-test-cell --replacements <table>
```

(`extract_assets_for_file` takes the export ROOT; it also copies FNV's
loose music, 522 MB, which a pack does not need.)

- **No cell.** A pack places nothing; `run.py`'s cell argument is optional
  and `cell.build(None)` builds only what the plugin holds: `interiors.reached`
  starts from no cell, `_rooms` places every interior as an ordinary one, and
  no CELL group is written when it would hold none.
- **Records in FalloutNV.esm's range.** Each pack's records carry master byte
  00 (the export calls them overrides) but FalloutNV.esm holds only one of
  them, `VDLCPackQuest` (the given-items flags). They build as the pack's own
  copies (`COPY_SITE`), as GRA's did. `VDLCPackQuest` too: the game build
  never reached it, so each pack carries its own copy, its flags its own.
- **Adopted scripts.** A game script a pack uses that no built master's
  Scripts folder holds (`FALLOUTNV_VDLCPackQuestSCRIPT`: its quest only a
  pack reaches) compiles into the pack's (`script.adopted_scripts`); before,
  the pack's quest named a script that existed nowhere and its `GameMode`
  check would never give the items.
- **Meshes FNV never shipped.** Classic Pack's 10mm pistol names seven
  mod-variant statics whose meshes are in no archive; a base whose model no
  export layer holds is left out, counted (`CellBuilder.record`), not a crash.
  A light or activator is made without the model instead, so it still works:
  Honest Hearts' hot plate (`NVDLC02CraftingOven01`) wears Dead Money's mesh,
  which only `DeadMoney - Main.bsa` ships.
- **Effects on the master's MGEF.** The export left every DLC effect naming a
  FalloutNV.esm effect blank (`EFID=`); fixed in the exporter
  ([master effects](../commentary/tes4_export_falloutnv.md#master-effects)),
  which also fills GRA's 34.
- **Plain spells.** A script's Spell property naming a spell that is no
  ability and not all script effects (the Vault 13 canteen's heal, cast every
  5 minutes while carried) converts as a fire-and-forget spell on self, its
  effects a consumable's (`ScriptEffects._plain_spell`); it was left out.
  The base game's scripts gain these too.

### <a id="multi-master"></a>A source with several masters

Every FNV DLC lists only FalloutNV.esm, but most mods list FalloutNV.esm and
the DLCs (all of Viva New Vegas: YUP, Better Brotherhood, Placement Fixes).
A FormID's top byte indexes its own plugin's master list, so a master read
behind the source names forms by its list, not the source's: Honest Hearts'
own `01xxxxxx` is `02xxxxxx` in a mod listing Dead Money first. One
master works only because FalloutNV.esm is `00` in both. SourceIds (FNV
to FO4) already handles any master count; what reads the masters' data
behind the source renumbers it.

- **The map.** `master_space.byte_map`: a master's index i is the
  source's index of that master's i-th master, its own index the source's
  index of it. A source must list its masters' masters (FNV requires it);
  one that does not stops the build. A master on masters of its own (a mod
  on YUP) composes: each export is renumbered into its child's numbering as
  it is layered. FalloutNV.esm and every DLC have one master, so their map
  is the identity and is never applied: nothing an existing build makes
  changes.
- **Exports** (`export_index.master_records`). Keys classified by
  `data/export_formid_keys.json`, from a census
  (`tools/generators/gen_export_formid_keys.py`) over the FNV, DLC,
  courier pack, FO3 and Anchorage exports: 151 keys only ever hold record
  FormIDs, 5 never do, and 6 were mixed and decided by hand (ACBS, PKDT and
  record flags whose values collide with record ids; Region[],
  Sound[].FormID and WNAM.Worldspace, FormIDs with dangling values).
  Conditions (`*Condition[].Raw`) renumber the global, the FormID
  parameters by xEdit's condition table and the Reference; navmesh door
  (NVDP) and edge (NVEX) links their FormIDs. Both lists are kept so neither
  failure is silent: an 8-hex key or raw dump in neither is counted
  (`master_space.UNCLASSIFIED`) and reported by the build, so a mod's
  new keys show what to classify. Renumbering is per record type, when the
  build reads it.
- **Plugin bytes** (`master_plugin.renumbered`, behind
  `install.source_stack` and the face fit's head parts). Each master file is
  rewritten once a run through its map: record FormIDs, FormID group labels
  (world, cell and topic children), and every subrecord FormID placed by
  `data/<game>_subrecord_formids.json`, generated from xEdit's definitions
  (`tools/generators/gen_fnv_subrecord_formids.py`, FNV and FO3, no
  subrecord left complex). Compressed records are written inflated. A union
  xEdit picks by a decider is a `select` + `cases` layout: package locations
  and targets (PLDT/PLD2/PTDT/PTD2) by their own Type field, a note's topic
  (TNAM) by its DATA type, a perk effect's DATA by PRKE and its function
  data (EPFD) by EPFT. A case never applies before its selector subrecord,
  which is what makes PERK's two DATAs exact: the 5-byte header comes before
  any PRKE. EPFD's switch of type 2 to 5 picks no FormID, so it is not
  modelled. Ownership (COED) is `owner_data`: the owner, and the value at 4
  (a global for an NPC owner, a rank for a faction), renumbered only when
  the map keeps index 0; a rank is below 2^24 or negative, so index 0 kept
  leaves every rank as is (otherwise the value is counted). Hand-set: DIAL
  INFC (xEdit also defines an unused raw copy) and REFR TNAM (a 2-byte map
  marker or a 4-byte topic: a FormID offset past the data is skipped).
  Checked over the five DLCs mapped to a moved index: ~328,000 own-range
  values moved, all naming a DLC record but 3 the DLCs author dangling
  (Dead Money INFO PNAM, Lonesome Road REGN RDID x2); a round trip is
  byte-exact. Better Brotherhood (FalloutNV.esm and the five DLCs) layers
  with no FormID collision and nothing unclassified.
- **Built FO4 masters** (`master_overrides.built_bytes`, behind
  `held_by`, `master_records` and the ragdoll poses' master lookup). The
  build reads the plugins it built earlier (`--plugin-dirs`) the same way.
  Each built DLC lists Fallout4.esm, FalloutHelpers.esl, XDI.esm and
  FalloutNV.esm and is `04` itself; a mod on several DLCs lists them after
  FalloutNV.esm, so Honest Hearts is `05` there. `byte_map` from the build's
  masters, then `renumbered(..., 'fo4')` with `data/fo4_subrecord_formids.json`
  (the same generator on `wbDefinitionsFO4.pas`, `--game fo4`: 139 records,
  2,191 subrecords, 66 left complex: VMAD, PACK CNAM/PDTO/PTDA/PLDT, NAVM
  NVNM, OBTS, OMOD DATA and others). FO4's MODS/MO2S-style subrecords are one
  material swap FormID, not FO3/FNV's alternate-texture list, so the
  `alt_textures` layout is FO3/FNV only. A complex subrecord is left as is
  and counted by the build (`master FormIDs not renumbered`); on Honest
  Hearts behind Dead Money 9,488 values in 40 kinds, mostly INFO VMAD and
  PACK CNAM, which the build reads only for record ids and overrides it
  compares whole. Checked on the five built DLCs in Better Brotherhood's
  numbering: Dead Money (its index unchanged) byte-identical, the other four
  ~256,000 own-range values moved, none dangling. A DLC build's own list is
  the identity, so nothing it makes changes. Before this, `held_by` read the
  raw ids, so a mod's override of a DLC record became a copy, and
  `master_records` stopped the build.
- <a id="multi-master-scripts"></a>**Script data (VMAD)** (`Renumbering.vmad`,
  2026-11-10, not rebuilt). VMAD is complex in the table but is renumbered:
  `dangling_scripts.object_offsets`, the one VMAD walker, gives every
  object's FormID offset (properties, arrays, struct members, the fragment
  script INFO, PACK, SCEN, TERM and PERK embed, a quest's stage script, each
  alias's own object and its scripts; object format 1 holds the FormID first,
  format 2 after the alias, xEdit `wbScriptPropertyObject`). A VMAD the
  walker cannot follow is left as is and counted as `<TYPE>.VMAD (script
  data not walked)`. Before this, a master record written as the master's
  own copy (a DLC quest heading lines the mod overrides) kept the DLC's own
  `04` in its properties while the record moved to `05`-`08`: YUP had 89
  such properties on 11 quests (72 dangling, 17 bound to a Dead Money
  record), DLC Enhancements 6 on 5, ExtraGoodies 3 on 1. Checked on the
  built DLCs in YUP's numbering: 12,351 VMADs walked, none left as is,
  16,077 object FormIDs moved, each naming a record its DLC holds, those 98
  included; no measurable added time (1.8 s for the four moved DLCs either
  way). The whole-body compare now also sees a script-only match: 4 YUP
  overrides (Honest Hearts keys, VMAD the only difference) become `same as
  master` and are dropped. Still left as is and counted, with the values in
  YUP's four moved DLCs that name one of the DLC's own records: NAVM NVNM
  18,540 in 1,210, PACK PLDT 226 and PTDA 177, WEAP OBTS 319 in 75, OMOD
  DATA 91 in 57, REFR PDTO 25, PGRE NAME 25, NOTE SNAM 11, NPC_ OBTS 12 in
  6, REGN RDSA 1; none in PACK CNAM/PDTO, SCEN HTID or TERM SNAM.

### <a id="edited-cells"></a>Edited cells outside the region (built 2026-11-10, not played)

A build places only the references of the cells it covers, and a DLC's
`--region` was picked around its entrance. Edits it makes elsewhere in its
master's worldspace were left out: Old World Blues swaps 46 skeletons to
SkeletonTorsoNaked across about 25 cells (12 at Boulder City 13,5) and moves
a deck of cards; none were built (0 of 47 in its plugin). Lonesome Road's
left-out cells hold no references, only a reordered region list.

So a source with masters adds to the first worldspace's region every grid
cell it holds itself, its own and its overrides (`run.edited_cells`), not the
persistent cell. A masterless plugin adds none: the base game's build is
unchanged. An added cell is built like one in the region; its references
that match the master's are dropped as unchanged overrides
(`master_overrides.drop_unchanged`).

Checked on the rebuilt Old World Blues (2026-11-10): 47 of 47 of those
references are in its plugin.

### <a id="asset-overlays"></a>Asset overlays (built 2026-11-10, not played)

A texture or mesh replacer with no plugin (NVTUP; NVMIM's meshes) changes
files the built plugins already ship, so no mod build picks it up.
`fo4_import.pipeline.overlay` converts it into a folder of its own:

- The replacer's folders go first in every source-file lookup
  (`export_index.export_file`, through `F3NV_OVERLAYS`, which worker
  processes inherit). The mesh cache keys on the source bytes and texture
  stamps, so an overlay file is a new entry, never the base one.
- Only files a named built plugin ships are converted (its
  `<plugin>.files.txt` and Textures archive record): textures copied to
  their FO4 path, a replaced normal map's specular maps derived again, and
  meshes shipped under their plain or load-door name converted with their
  materials and collision. Meshes shipped only as another variant (a posed
  weapon, a prop, a terminal, a creature part) stay as built.
- The folder gets an empty ESL with the built plugins as masters, so it
  loads after them, and its own Textures and Main archives.
- A mesh's bounds (OBND) stay the base record's.

NVTUP 2.0 holds 13,455 textures and no normal maps; 3,516 replace textures
FalloutNV.esm ships (12.8 GB against 1.1 GB). Its 6,357 face and body
textures are unused: FO4 faces come from the CK
([facegen plan](fo4_facegen_plan.md#phase-3)).

#### <a id="premultiplied-replacers"></a>Premultiplied replacer textures

**Code:** `fo4_import/base/premultiplied.py`, called from
`spike/statics.copy_texture`.

NVTUP 2.0 saved its textures premultiplied: color already multiplied by
alpha, so black wherever alpha is clear. FNV and FO4 both read diffuse color
as is, so an opaque material shows that black. Doc Mitchell's house
(`architecture/westside/craftsmanhomea.nif`, no NiAlphaProperty on any
shape) shows black boards across its siding: `craftsmansiding.dds` keeps an
alpha mask for alpha-tested ruins, and vanilla has wood under it. Measured
against vanilla, the NVTUP color divided by vanilla's follows alpha: 0.02 at
alpha 0, 0.16 below 32, 0.55 at 96 to 160, 0.79 at 160 to 224, 1.0 when
solid. The `apartmentpre01dcl` decal is the same: 0.00 at alpha 0. An
alpha-blended decal drawn from premultiplied color gets dark edges.

A texture that replaces one an earlier layer holds (an overlay over the
export, a plugin over its master; `export_index.replaced_file`) is tested
against it at the replacer's size. The test uses texels where the replacer's
alpha is not solid (224 or below) and the replaced color is lit (above 24).
Over them it asks which is nearer the replacer's mean color: the replaced
color times alpha (premultiplied), or the replaced color itself (straight).
The replaced color is first scaled to match where solid. At least 1% of
texels must qualify. A fixed darkness cutoff missed textures whose clear
areas are thin lines: there, DXT blocks average the black with the wood next
to it.

The mend writes `replacer + (1 - alpha) * replaced` (the replaced color
resampled to the replacer's size). This is exact where alpha is 0 or 1, and
between them it takes the replaced texture as the true color. Alpha is
unchanged. `encode_dds` filters color and alpha separately for the mips.
Pillow's RGBA resize premultiplies, which would put the black back in the
lower mips. A mend costs about 0.75 s for a 2048 texture, and a kept
texture's test about 0.07 s, so the overlay runs its texture writes in a
process pool (`ba2_pack.write_later`). Encoding with separate color and alpha
filtering changes the code identity of the work-cached maps that use
`encode_dds` (glow maps, object-LOD atlases, reframed maps), so they are made
again once.

Census (2026-11-10): NVTUP 2.0 and NVMIM's textures against the six NV
exports. Of 13,532 that have an alpha channel and replace an exported
texture, 1,557 test premultiplied. 845 of them are among the 4,641 the built
FNV and DLC plugins ship, so the overlay converts them. Most are alpha
cutouts and blended layers: tree and plant leaves, effects, graffiti and
signs, headgear, ruined walls. Spot checks of flagged textures show the
color-to-vanilla ratio rising with alpha band by band (about 0.1, 0.3, 0.55,
0.8, 1.0). The cases that change verdict between rules are DLC Pip-Boy
icons, whose edges are darker at low alpha and brighter in mid alpha. Either
verdict leaves them close to vanilla.

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
  so the first build after it compiles everything once. The headers' memo
  is one per header folder, shared by every plugin importing it
  ([header hashes](fo4_pipeline.md#own-source-first)).
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

## <a id="which-builds"></a>Part E: which plugins need a build, and code keys by what ran (built 2026-11-03)

Part D makes a build faster once it runs. Two things decide whether a build
should run at all, and both are guessed today.

**Measured, 2026-11-03.**
- *Base game:* of the last 13 whole-map builds (1101 to 1102m), 10 took
  18–38 min. Three took 105–119 min (1102c, 1102k, 1102m), all from caches
  thrown away: `people` 4,239–4,365 s against 196–317 s (face fits), and
  `item WEAP` 455–623 s against 43–81 s (gun clips).
- *Why the caches were thrown away:* every cache's `code_tag` hashes its
  whole import tree, and `fo4_import/nif/blocks.py` is in 12 of the 13
  trees (face fits: 36 files, gun clips 78, rig assets 79). One edit to the
  NIF block writer before 1102m (the screen glare fix) refit every face.
  This is [the audit's](fo4_tool_audit.md#rebuild) "cache keys too broad"
  finding, still open after the gun-clip and LOD cuts.
- *DLCs:* a base-game fix (the Ringo force greet) was followed by
  rebuilding all nine DLCs and packs. None of them writes the records the
  fix changed: `FNV_TES4ScriptPackages` and the greeting line are
  FalloutNV.esm's alone (a DLC's copy derives the master's FormID and
  `drop_unchanged` drops it). Seven of the nine rebuilds, about 50 min,
  changed nothing. Nothing records what a DLC build read from its master,
  so whoever starts the builds has to guess, and guesses wide.
- *At scale:* the app builds a plugin per mod. With 100 mods, guessing wide
  means a change to mod 52 rebuilds everything that loads after it.

**1. A build records what it depended on.** Beside the stamp,
`<plugin>.inputs.json` lists everything the build's output is a function of:
- *Files it opened*, from a `sys.addaudithook` `open` hook in the build
  process and each pool worker: the export files, Fallout4.esm, the
  replacement table, mod sources, static `.psc`, headers, native `.pyd`.
  Size, time and SHA-1 each.
- *Programs it ran*, from the hook's `subprocess.Popen` event: Caprica,
  Archive2, Elric, the Creation Kit, LODGen. Their exe hashes.
- *Its masters' builds, narrowed to what it asked.* A built master plugin
  is opened whole, so its file hash would change on every base fix. The
  reads Part D lists go through `held_by`, `master_records`,
  `master_ledgers` and the master's Scripts folder. Those log the FormIDs
  asked about and the answer each got (held or not, the record body's
  hash, the ledger id), and the master headers compiled against.
- *Code that ran,* by function (below).

**2. Code keys by what ran, not what was imported.** Python 3.12's
`sys.monitoring` (PEP 669) raises `PY_START` the first time each code object
runs. Return `DISABLE` and that function is never reported again, so the
cost is one event per function per process. The build keeps
`{module:qualname: SHA-1 of the function's source}` for every function that
ran. Module and class bodies run at import, so a changed constant counts.
The same record replaces `code_tag` for the work caches: a face fit's key
holds the functions that ran during a fit, recorded on the first fit and
checked on the next. An edit to an unrelated block writer in `blocks.py`
then leaves every face fit valid. A new function can only start running
when a caller that ran changes, or when data changes, so the record cannot
miss one.

**3. A build plan before any build.** `python -m fo4_import.pipeline.plan`
walks the plugins in master order. For each it re-hashes the recorded
functions and files, and re-asks the recorded master questions of the
masters' current builds. Then it prints *build* (with the first changed
input) or *current*. After a base-game fix that touches no DLC record,
every DLC prints current. After a code fix, only the plugins whose builds
ran the changed function print build. For an end user, the app's code is
fixed per release, so a change to mod 52 builds mod 52, then only those
later mods whose recorded questions get a different answer.

**Correctness, as in Part D.** Determinism makes a check possible: a plugin
the plan calls current, rebuilt clean, must come out byte for byte the
same. A test does that on the Rig Test region and one pack, and a
`--verify` option rebuilds one random current plugin per run and diffs it.
A difference means an input the record missed, which is a bug. Until the
check has passed on every plugin, the plan reports and the main session
decides.

### <a id="code-identity"></a>Code identity and what ran (built 2026-11-03)

- **`pipeline/code_identity.py`.** A function's identity is a SHA-1 of its
  syntax tree, leaving out positions, docstrings and the bodies of functions
  defined inside it, which run as code objects of their own. It also hashes
  the module-level definitions the function names:
  - every statement binding or changing that name (`X = ...`, `X += ...`,
    `X.update(...)`);
  - a class's body, with its methods' bodies left out;
  - a decorated function, since a `functools.cache` may answer without
    running it.

  Names are followed through imports, up to 4 definitions deep. The calls in
  an assignment's value count too, since `TABLE = make()` runs `make` at
  import. A key is `<repo path>::<qualname>`. A file edited after the process
  started gives no identity, because the code running is not the code on
  disk.
- **Tested:** a docstring, an unread constant or another function in the same
  module leave the identity alone. The function's body, a constant it reads,
  a class's fields, an import-time call it reads, or a constant imported from
  another module change it.
- **`pipeline/ran_code.py`.** It uses `sys.monitoring` tool 4 and `PY_START`,
  returning `DISABLE` from each report, so it costs one event per function
  per process. `capture()` re-arms the reports with `restart_events()` and
  collects the keys that start inside it. Lambdas, comprehensions and module
  bodies are left out: the function around them ran, and the definitions they
  name are in its identity.

### <a id="build-plan"></a>The inputs record and the plan (built 2026-11-03)

- **`pipeline/build_inputs.py`.** A recorded build calls `start(folder)`; each
  worker process resumes from the `F3NV_BUILD_INPUTS` variable and writes
  `<pid>.json` at exit. A `sys.addaudithook` hook notes `open` (read or
  written, by mode or flags), `os.listdir`, `os.scandir` and
  `subprocess.Popen`. `write()` merges the processes' records into
  `<plugin>.inputs.json`. Left out of it:
  - files the build wrote;
  - the build's data folder, the record folder, `output/fo4_cache` and
    Python's own folders;
  - `.py` files, which are covered by code identity;
  - folders the build wrote below.

  Files are kept by size and mtime, plus a SHA-1 up to 64 MB, so a master's
  script rewritten with the same text is no change. The record also keeps
  the native `.pyd` files loaded, Python's and third-party packages'
  versions, and the command.
- **`MasterLog`.** It keeps the questions the build asked its masters and
  the answers it got:
  - held FormIDs, through `Held`, the frozenset `held_by` returns;
  - ledger answers;
  - record bodies by SHA-1;
  - each master plugin's masters;
  - textures a master packed;
  - master scripts compiled against (`master_scripts`: the `.psc` files the
    compiled scripts name, followed through the ones those name).

  The plugin, ledger and manifest files behind those answers are left out of
  the file record, so a base rebuild that answers every question the same
  way leaves a DLC current.
- **Questions about mods** (`asked`). The app settings, MO2's ini and the
  profile's mod list are answered the same way: each plugin looked up and
  the file found, each Creation Kit file and the mod holding it
  ([MO2 answers](fo4_mod_builds.md#mo2-answers)).
- **`pipeline/build_plan.py`.** It orders plugins by the masters their records
  read. For each it checks the finished stamp, then code, environment, files,
  folders, programs, then the master questions, asked again of the masters'
  current builds. It prints `current`, `build (first change)` or
  `after <master>`. `--run` builds the first plugin needing it, then checks
  again, until none needs a build. `--verify` rebuilds one current plugin and
  compares its plugin and ledger bytes.
- **The plan reads the code on disk (fixed 2026-11-06).** Code identity is
  unknown for a file edited after its process started, which protects a
  build whose running code is not on disk. The plan process runs none of the
  code it checks, but it lives through a whole `--run`. A peer session's edit
  20 minutes into a 10-plugin run (`gun_anim_text.py`) left its identity
  unknown for the rest of the run, so Caravan Pack, built from that code,
  was "changed" after each build and rebuilt 8 times (about 7.5 min each).
  Each `plan()` now calls `code_identity.rebase()`: the code on disk is the
  code to compare, its identities computed afresh.
- **Tested** (`tests/test_fo4_build_plan.py`):
  - a DLC stays current after the game gains a record and changes one it did
    not read;
  - it needs a build after the game changes the record it read, or drops the
    one it asked about;
  - the plan puts it after a game that needs a build.

**Where the time goes after both** (estimates from the numbers above):
- *A base-game fix:* 18–38 min, not 105–119 min when a shared mesh file
  changed.
- *The DLCs:* those whose recorded reads changed, often none, against about
  60 min for all nine.
- *Part D:* still what takes a needed build from tens of minutes to
  minutes.

## <a id="phases"></a>Phases

| # | Work | Done when | Size |
|---|---|---|---|
| 1 | The game plugin as `FalloutNV.esm`, flagged master (built 2026-10-30, not played): voice and FaceGen folders filed under the old name move once, and the FaceGen meshes' face texture paths (the CK writes the plugin name into them; purple faces when stale, played 2026-10-30) follow (`spike/plugin_rename.py`) | The game plays as before | S |
| 2 | Master-aware FormIDs and ledgers read from masters (built 2026-10-30: `base/source_ids.py`; `LedgerWriter` reuses a master's generated id and leaves its record to the master; each FO4 plugin takes its source plugin's name) | The game rebuilt with 0 FormIDs moved; a unit test of a two-plugin build | M |
| 3 | Layered export and binary source (built 2026-10-30; [part A](#dlc)) | A DLC export resolves every FalloutNV.esm reference | M |
| 4 | Gun Runners' Arsenal (built 2026-10-30, FO4Edit clean, not played; [as built](#dlc-build)), then the courier packs (built 2026-10-31, no play recorded; [as built](#courier-packs)) | Built, FO4Edit clean, played | M |
| 5 | Proxy records and mod patch plugins; the app builds patches | The with-mods table as patches; the game plugin byte-identical with and without them | M-L |
| 5a | [Part E](#which-builds) (built 2026-11-03; `--verify` not yet passed on every plugin): each build's inputs record, code keys by functions that ran, the build plan | After a base-only fix the plan calls every DLC current, and rebuilding one clean matches byte for byte; an edit to an unrelated part of `blocks.py` refits no face | M |
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
  ledger give (phase 3 measures it)? (The ledger ships beside the plugin;
  see [FormIDs](#formids).)
