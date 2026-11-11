# Light plugins for converted mods (research and design, 2026-11-11)

**Question:** can converted FO3/FNV plugins be built as Fallout 4 light plugins (ESL-flagged), so a large or
Tale of Two Wastelands–sized load order fits under FO4's 254 full plugins? Asked from
[the load order plan](../fo4_load_order.md#light). Research and design only: no build, no FormID changes.

**Answer:** yes. A converted plugin keeps its name and extension (`.esm` or `.esp`) and gains the ESL flag. Its own
records get object ids 0x001–0xFFF (4,095 of them) from the same hashed scheme, kept in its ledger. Today 13 of the
21 converted mods, Gun Runners' Arsenal and the four courier packs fit. Every plugin already built stays a full
plugin unless the user accepts that its ids move ([recommendation](#recommendation)).

## Contents

- [Engine rules, per runtime](#rules)
- [How our FormIDs are made today](#today)
- [Census of the built plugins](#census)
- [Design: a light FormID scheme](#design)
- [Tale of Two Wastelands–sized load order](#ttw)
- [Risks](#risks)
- [Size of the work](#size)
- [Recommendation](#recommendation)

## <a id="rules"></a>Engine rules, per runtime

| Rule | Value | Sources |
|---|---|---|
| Flag | Record flag `0x200` on the TES4 header. The file can stay `.esm` or `.esp`; `.esl` implies it | xEdit `TwbMainRecordStructFlags.IsLight` (`$00000200` for every game but Starfield); F4SE 0.7.9 `GameData.h` `kRecordFlags_ESL = 1 << 9`; CK wiki *Data File*, "Light Plugin" (an ESL-flagged ESP) |
| Header version | HEDR 1.0. FO4 has no later bump like Skyrim's 1.71; 0.95 is the pre-1.10 version (FO4 VR, and the DLC Bethesda never resaved) | xEdit `wbDefinitionsFO4.pas` (1.0, or 0.95 for VR); read from the install: Fallout4.esm and DLCRobot.esm 1.00, DLCCoast/NukaWorld/workshop02/03 0.95, every CC `.esl` 1.00. Our writer already writes 1.0 (`HEDR_VERSION_FO4`) |
| New-record range | Object ids **0x001–0xFFF** (4,095; 0x000 is null) when the plugin has HEDR ≥ 1.0 and **at least one master**; 0x800–0xFFF (2,048) without a master. Nothing reaches above 0xFFF (FO4 has no medium plugins) | xEdit `GetAllowHardcodedRangeUse` (`gmFO4` and version ≥ 1.0 and master count > 0) and the light check `ObjectID > $FFF` → invalid; CK 1.11.240 "ESL Capable - %d IDs remaining" is `0xFFF − forms the active file owns` (function at RVA 0x86F580); F4SE `GetFormID` masks `formLower & 0xFFF`; CK wiki: "4096 forms … 0x000 to 0xFFF". Bethesda's own files: ccFSVFO4007-Halloween.esl has 2,078 new records (above the old 2,048), 2,047 of them below 0x800; Remnants 1,288, all below 0x800 |
| Runtime FormID | `0xFE` · light index (12 bits) · object id (12 bits) | F4SE `ModInfo::GetFormID`/`IsFormInMod` (`lightIndex` UInt16, `0xFE000000 \| lightIndex << 12 \| id & 0xFFF`); CK wiki "Light Master Runtime" |
| Light plugins loaded | Up to 4,096 (the 12-bit light index); in practice fewer (the wiki cites file-handle and reference limits) | F4SE `lightIndex` width; xEdit `MaxLightSlot = $FFF`; CK wiki "Light Master Budgets" |
| Full plugins | 254 (slots 0x00–0xFD; 0xFE holds every light plugin, 0xFF runtime forms) | xEdit `MaxFullSlot` (`$FE`, less one with light support); CK wiki (the 8-bit id) |
| Overrides | **Don't count.** Only the plugin's own new records take ids; overrides keep their master's | xEdit checks only records whose FileID is the file's own; the CK counter counts forms owned by the active file; Bethesda's Remnants has 62 overrides beside 1,288 new records |
| As a master | Allowed: FalloutHelpers.esl is already a master of every converted plugin, and Bethesda's CC files are ESM+ESL. A light master should not have a plain-ESP master (it would pull that ESP early) | CK wiki "Light Master Notes"; xEdit counts light masters separately (`GetLightMasterCount`) |

**Per runtime.** We support OG 1.10.163, next-gen 1.10.98x and AE 1.11.x. Only 1.11.240 is installed, so only it
was disassembled (the CK) and read through F4SE 0.7.9. The other two rest on: the CK wiki snapshot (2021-05-20, the
OG 1.10.163 era), which already gives 4,096 forms from 0x000; xEdit, which applies one rule to every FO4 runtime
(header ≥ 1.0); and the nine Creation Club `.esl` files in the install, which use ids from 0x001 under HEDR 1.00. ESL
support arrived with FO4 1.10, so all three runtimes have it. Nothing found extends the range on any runtime.

## <a id="today"></a>How our FormIDs are made today

- **1:1 records keep FNV's object id** (`CellBuilder.fnv_id` → `SourceIds.fo4`, `fo4_import/base/source_ids.py`):
  the FNV FormID's master byte picks the FO4 plugin, and the low 24 bits pass through unchanged. FNV mods put
  their records anywhere from 0x000800 up, mostly far above 0xFFF.
- **Generated records hash an authored key.** `derive_formid(site, key)` (`tes5_import/base/writer.py`): md5 of
  `site\0repr(key)`, mod the plugin's hash window; on a collision, a salted rehash (up to 64). The window is the
  longest run of 64K blocks under 1% full, below a 1M runtime headroom (`_RUNTIME_HEADROOM`), so generated ids land
  in 0x000800–0xEFFFFF (most built plugins' highest new id is 0xE9F0C4–0xEFFFF7). `FORMID_SCHEME_VERSION = 1`.
- **The ledger** (`fo4_import/base/ledger.py`, `<plugin>.formids.tsv` beside the plugin) keeps every id a build
  gave, by kind, site and key, and is read back first. Its ids are reserved before hashing, so an id never moves
  once given, even if a later key would hash onto it. Ledgers only grow: entries of records no longer written stay
  (CaravanPack writes 21 records; its ledger holds 669 ids).
- **Ledger shadowing:** before hashing, a build asks its masters' ledgers (`LedgerWriter.from_master`). If one holds
  the key and the built master still has the record, the record is the master's: it is referenced, not made
  again, and the build's own entry is dropped ([dlc-shadowed-ids](../fo4_plugin_layout.md#dlc-shadowed-ids)).

**What a light plugin needs:** every own record must land in 0x001–0xFFF. Generated records only need a smaller
window. 1:1 records can't keep FNV's object ids, so they become keyed records too: site `FNV 1:1`, key the
FNV FormID (authored), through the same ledger. A dependent then resolves a light master's 1:1 record through that
master's ledger, not by passing the object id through.

## <a id="census"></a>Census of the built plugins

Read 2026-11-11 from `C:\Modlists\fo3fnv-in-fo4\mods\F3NV - *` (read-only; every `.build.json` "finished" except
The Frontier, which failed and has no plugin). "New" = records in the plugin's own index. "1:1" are FNV records
keeping their object id; "copies" are a master's records the built master left out (`FNV master record copy`);
"generated" are the rest of the ledger's ids. All three kinds take light ids. **Fits** = new ≤ 4,095;
**with room** = new ≤ 3,071 (75%, leaving a quarter for updates, see [overflow](#overflow)). Switching a plugin that
is already built moves **all** of its new records' ids, so "new" is also the drift count.

| Plugin | New | 1:1 | Copies | Generated | Overrides | Fits | With room |
|---|---:|---:|---:|---:|---:|:-:|:-:|
| FalloutNV.esm | 494,313 | 380,057 | 0 | 114,256 | 19 | no | no |
| OldWorldBlues.esm | 56,750 | 48,033 | 94 | 8,623 | 124 | no | no |
| DeadMoney.esm | 41,807 | 32,468 | 45 | 9,294 | 123 | no | no |
| LonesomeRoad.esm | 38,815 | 32,075 | 89 | 6,651 | 78 | no | no |
| HonestHearts.esm | 37,833 | 32,257 | 70 | 5,506 | 49 | no | no |
| GunRunnersArsenal.esm | 971 | 420 | 39 | 512 | 5 | yes | yes |
| ClassicPack.esm | 29 | 0 | 9 | 20 | 0 | yes | yes |
| MercenaryPack.esm | 26 | 0 | 5 | 21 | 0 | yes | yes |
| CaravanPack.esm | 21 | 0 | 5 | 16 | 0 | yes | yes |
| TribalPack.esm | 12 | 0 | 3 | 9 | 0 | yes | yes |
| Fallout3.esm (Vault 101 spike, scoped) | 43,343 | 15,222 | 0 | 28,121 | 19 | no | no |
| AutumnLeaves.esp | 39,221 | 4,397 | 28 | 34,796 | 17 | no | no |
| NewVegasBountiesIII.esp | 36,293 | 29,317 | 101 | 6,875 | 73 | no | no |
| NewVegasBountiesII.esp | 30,220 | 22,462 | 166 | 7,592 | 227 | no | no |
| Russell.esp | 16,499 | 12,192 | 85 | 4,222 | 84 | no | no |
| YUP - Base Game + All DLC.esm | 9,562 | 1,601 | 535 | 7,426 | 20,805 | no | no |
| Goodies.esp | 7,605 | 2,589 | 254 | 4,762 | 1,368 | no | no |
| TLD_Travelers.esm | 7,347 | 3,544 | 85 | 3,718 | 501 | no | no |
| NVWillow.esp | 5,967 | 1,155 | 38 | 4,774 | 51 | no | no |
| DLC Enhancements.esp | 3,784 | 259 | 2 | 3,523 | 193 | yes | no |
| JSawyer Ultimate.esp | 2,988 | 124 | 139 | 2,725 | 562 | yes | yes |
| ExtraGoodies.esp | 2,701 | 10 | 3 | 2,688 | 471 | yes | yes |
| Placement Fixes.esm | 2,470 | 9 | 0 | 2,461 | 2,417 | yes | yes |
| NewVegasBounties.esp | 2,465 | 956 | 9 | 1,500 | 27 | yes | yes |
| Better Brotherhood.esm | 1,811 | 40 | 361 | 1,410 | 42 | yes | yes |
| AguaFria.esm | 1,707 | 42 | 11 | 1,654 | 257 | yes | yes |
| Weapons.of.the.New.Millenia.esm | 1,378 | 277 | 11 | 1,090 | 0 | yes | yes |
| Sunshine On My Shoulders.esm | 999 | 1 | 0 | 998 | 9 | yes | yes |
| NVMIM.esp | 672 | 2 | 1 | 669 | 53 | yes | yes |
| Strip Lights Region Fix.esm | 35 | 5 | 0 | 30 | 94 | yes | yes |
| Landscape Disposition Fix.esm | 8 | 1 | 0 | 7 | 2,239 | yes | yes |
| SomeguySeries.esm | 7 | 1 | 0 | 6 | 0 | yes | yes |

Already light (hand-numbered, no hashing): FalloutHelpers.esl (ESM+ESL, 42 new, 0x800–0xC01), FalloutNV - Classic
Look.esl and F3NV - NVTUP and NVMIM.esl (overrides only), F3NV_Trace.esl (empty, no master).

**Totals:** of the 21 mods, 13 fit (12 with room); of FNV's 10 DLC and packs, the 5 small ones fit. Generated
records are most of a small mod's count: the converter adds outfits, object mods, globals and `FNV made` records
for each converted actor and gun, so a mod with a few hundred FNV records reaches 1,000–3,000. The counts can still
change: copies shrink when the game build includes what a mod needs, and any new generator adds to every mod.

**Masters among converted plugins:** FalloutNV.esm and the story DLC are masters of most mods; GunRunnersArsenal.esm
of six; SomeguySeries.esm of NewVegasBounties I–III and Russell. The census tools are scratch one-offs (not
in `tools/`); rerun with the [preflight](#size) addition below.

## <a id="design"></a>Design: a light FormID scheme

### The scheme

1. **Same hash, smaller window.** In a light plugin `derive_formid` hashes `site\0repr(key)` exactly as now, mod
   4,095, plus 1 (0x001–0xFFF). Collisions rehash with the same salt sequence, with no 64-probe cap: the build
   fails only when every slot is taken. Full plugins don't change: same window, same `FORMID_SCHEME_VERSION`, so
   nothing already built moves.
2. **Every own record is keyed.** A 1:1 FNV record in a light plugin takes site `FNV 1:1`, key its FNV FormID
   (`fnv_id` asks the writer instead of passing the object id through). Copies and generated records already have
   keys.
3. **The ledger keeps every id, and is required.** As today, its ids are reserved before hashing, never reused, and
   saved before the plugin is written. Slots a removed record held stay taken, so a plugin's budget is its
   ledger's id count, not its record count.
4. **Dependents read the master's ledger.** `SourceIds.fo4` maps a light master's record through that master's
   ledger (`FNV 1:1` key); `from_master` is unchanged. A missing entry is an error, not a fallback to the raw
   object id.
5. **The header:** ESL flag `0x200` with the source's ESM bit kept; same filename; HEDR 1.0; next object id =
   highest own id + 1 (at most 0x1000). Every converted plugin masters Fallout4.esm, so 0x001–0x7FF is open.

### <a id="guarantees"></a>The guarantees, checked

- **Same ids on every machine for the same inputs.** A first build is deterministic: same keys in the same order
  (byte-reproducible builds, `tests/test_formid_determinism.py`) give the same probes. Two fresh builds of the same
  mod version agree.
- **Stable across rebuilds and updates:** through the ledger. The difference from full plugins: with 16 million
  slots, a fresh build almost always reproduces an id without the ledger. With 4,095 slots it often can't. Measured by
  simulation on real ledger keys (`esl_sim.py`, scratch): when an update adds 10% more keys, a fresh build of the
  new version and an upgrade build that kept the old ledger give different ids for:

  | Plugin | Keys | Fill | Ids that differ |
  |---|---:|---:|---:|
  | GunRunnersArsenal.esm | 971 | 24% | 20 (2.1%) |
  | Better Brotherhood.esm | 1,811 | 44% | 102 (5.6%) |
  | NewVegasBounties.esp | 2,465 | 60% | 174 (7.1%) |
  | JSawyer Ultimate.esp | 2,988 | 73% | 325 (10.9%) |
  | DLC Enhancements.esp | 3,784 | 92% | 738 (19.5%) |

  No scheme avoids this in a small space: an id that depends on the key alone needs a space too big to collide
  in. A layout that depends only on the current key set (ordered hashing, rank by key) has to move old ids when
  keys are added. So the ledger is the save contract for light plugins. The user's own saves are always safe
  because their machine keeps its ledger. What can differ is a second machine that converts the new version
  fresh. **Rule:** if a light plugin's mod folder has a built plugin but no ledger, the build stops and asks; it
  never quietly rebuilds a fresh numbering. A converted plugin that is shared must ship with its ledger (it
  already sits beside it).
- **No drift for plugins people already have saves on.** Light vs full is decided at a plugin's first build and
  recorded in `<plugin>.build.json`. A later build keeps it. Changing it moves every new record's id ([census](#census)
  gives the count), so it follows the [FormID drift](../../../CLAUDE.md#formid-drift) rule: measure, stop, ask.

### <a id="collisions"></a>Collisions in 4,095 slots

Collisions are normal, not rare. The simulation's mean probes per key were 0.13 at 24% full, 0.76 at 73% and 1.85
at 92% (worst key: 43 probes). Probing is cheap, so the limit that matters is the drift above, not speed. This
is why the default leaves a quarter of the space free ([who decides](#who-decides)). A collision never lands on
another plugin's id: each plugin's 0x001–0xFFF is its own.

### <a id="overflow"></a>When an update pushes a plugin past the limit

A light build that would need more than 4,095 ids (ledger ids plus new keys) stops before writing anything. The
ledger is saved only by a successful build, so it is unchanged. The build reports the count and the two ways
out:

- **Become a full plugin:** every id moves (the plugin's whole new-record count); saves on it break. The user must
  say yes; the converter never does this on its own.
- **Stay light and keep the old version** of the mod until it is reduced.

There is no compacting option. Reusing a removed record's slot would hand a save's form to a different record,
which is the bug the CK wiki warns about ("Light Master Updating").

### <a id="who-decides"></a>Who decides: the converter proposes, the user can override before the first build

- **Default:** at a plugin's first build the converter builds it light when its own ids fit in 3,071 (75% of
  4,095), else full. A trial is cheap: the build runs in light mode and, if it runs out of ids, starts over as full.
  No save exists yet, so nothing drifts. Overrides-only plugins (the [merged patch](../fo4_load_order.md#merged-patch),
  replacement patches, Classic Look) are always light: they place no ids.
- **The user** can force full (a mod expected to grow) or force light (up to 4,095) in the app, before the first
  build. After that the choice is fixed, and changing it is the drift question above.

### <a id="masters"></a>A plugin that is a master of other converted plugins

- A light master is fine (FalloutHelpers.esl is one). Dependents name its records by its master index in their
  own list plus the light id, through its ledger ([scheme](#design) item 4).
- Its type matters more than a leaf plugin's: switching it moves the ids that every dependent references, so every
  dependent must be rebuilt and every save on any of them breaks. Decide a master's type before anything depends on
  it. FalloutNV.esm and the story DLC are full by size anyway. Today's candidates are GunRunnersArsenal.esm (master
  of six mods) and SomeguySeries.esm (master of four).
- A light plugin keeps its ESM bit from the source (ESM+ESL, like Bethesda's CC files), so it still loads with the
  masters. None of our light candidates has a plain-ESP master.

## <a id="ttw"></a>Tale of Two Wastelands–sized load order

A TTW-style setup carries both games in one load order. Following
[the FO3 plan](https://github.com/ThyMrMan/fo3fnv-in-fo4/blob/claude/agitated-carson-c1d28c/docs/fork/fo4_fo3_plan.md#ttw),
FO3 then comes in through TTW's own master, `TaleOfTwoWastelands.esm`, built like a big FNV mod. A standalone
`Fallout3.esm` can't share a load order with FalloutNV.esm (both carry `FNV_NewGame`). Fallout3.esm alone exports
808,699 records; the Vault 101 spike's scoped build already has 43,343 new ones. So the FO3 side is full whichever
route is taken.

| Group | Full | Light |
|---|---:|---:|
| Fallout 4: Fallout4.esm and its 7 DLC masters | 8 | |
| Creation Club `.esl` files | | each |
| Ours: FalloutHelpers.esl, the planned rules `.esl`, the Trace switch | | 3 |
| FalloutNV.esm and the 4 story DLC | 5 | |
| Gun Runners' Arsenal and the 4 courier packs (light only if decided before release, or if the user accepts the drift) | 0 (5 today) | 5 |
| TaleOfTwoWastelands.esm (FO3 and its 5 DLC) | 1 | |
| Merged patch and replacement patches | | each |
| **Fixed cost** | **14** (19 today) | |

That leaves 240 full slots for mods, the user's own FO4 mods included. In this census 8 of 21 converted mods
(38%) need a full plugin. If a big list has the same mix, about **630 converted mods** fit (240 / 0.38) before FO4's
limit, against 235 if every plugin stays full. The large mods (quest and world mods like NVB II/III, Russell,
AutumnLeaves) are what fill the full slots. Small fixes, gear and NPC mods, the most common kind on a big list,
go light.

## <a id="risks"></a>Risks

- **The ledger becomes the save contract** ([guarantees](#guarantees)). Losing it and rebuilding renumbers the ids
  added since the first build (2–20% in the simulation). Mitigation: the build refuses to renumber without the
  ledger, and the ledger travels with the plugin.
- **Runtime coverage:** only 1.11.240 was checked in the exe and F4SE source. OG 1.10.163 and next-gen 1.10.98x rest
  on the wiki, xEdit and Bethesda's CC files. A play test on each runtime with a light plugin whose ids start
  at 0x001 would close it.
- **xEdit version:** the rules come from xEdit's current source in `references/xEdit`. Whether the bundled FO4Edit
  4.1.5f accepts ids below 0x800 in an FO4 light plugin was not tested. Users who check plugins in an older xEdit may
  see errors.
- **Users compacting by hand:** xEdit's "Compact FormIDs for ESL" or Vortex's "make light" renumbers the plugin
  behind the ledger's back, so the next build's dependents and patches disagree with it. The converter should
  check that the built plugin's own ids match the ledger before trusting it.
- **Code that assumes the master byte:** `SourceIds.fo4`, `from_master` (`index << 24 | oid`), `CellBuilder.fnv_id`,
  `master_overrides` and the conflict report all build FormIDs as master index plus object id. That stays true for
  a light master inside a plugin file (the master index is file-local), but each place that turns an FNV object id
  into ours needs the ledger path. Runtime sidecars (`F3NV_Menus` rows, the DLL's `LookupFormByID` callers) name
  forms by plugin plus object id or resolve at load, so a light id passes through; the dialogue menu's
  docstring already says it resolves "under any load order or ESL". This was read, not tested.
- **Practical light limits:** the wiki notes file-handle and reference limits well below 4,096 files. Not a concern at
  hundreds of plugins; not measured.

## <a id="size"></a>Size of the work

About 250–350 lines plus tests, one session, no change to any full plugin's ids:

| Piece | Where | About |
|---|---|---|
| Light window and uncapped probing in `derive_formid` when the writer is light | `LedgerWriter` (`fo4_import/base/ledger.py`) | 40 lines |
| `FNV 1:1` keying of own records in a light build | `CellBuilder.fnv_id` (`fo4_import/spike/cell.py`) | 15 lines |
| Light masters through their ledger | `SourceIds.fo4`, `master_ledgers` (`fo4_import/base/source_ids.py`) | 40 lines |
| ESL flag, ESM bit kept, next id | `FO4PluginWriter` header (already has `is_esl`) | 10 lines |
| Decision: first-build trial, `light` in `.build.json`, refuse to flip, refuse without ledger, overflow stop | build finish and stamp (`spike/build_finish.py`, `fo4_pipeline.md#build-stamp`) | 80 lines |
| App switch (force full / force light, before the first build) | `fo4_import/app` | 40 lines |
| Preflight audit: own ids within 0x001–0xFFF in a light plugin; own ids match the ledger | `tools/validate/preflight` | 50 lines |
| Tests: light determinism (same keys, same ids), dependent resolution through a light master, overflow stop | `tests/` | 80 lines |

## <a id="recommendation"></a>Recommendation

1. **Build light plugins, with the scheme above:** ESL flag on the same-named plugin, HEDR 1.0, ids 0x001–0xFFF
   hashed from the same keys, every own record keyed, the ledger required. It is the FO4-native mechanism and costs
   nothing in full plugins.
2. **Default light at a plugin's first build when it fits in 75% of the space**, full otherwise; the user can
   override before the first build; the choice is then fixed. Overrides-only plugins are always light.
3. **Never switch a built plugin silently.** Changing a built plugin's type is FormID drift, and every new record
   counts. **Open for the user:** switch the ones already built that fit, while no saves matter? That would move
   GunRunnersArsenal.esm 971, the four courier packs 88, and 12 mods 17,241 (or 13 mods 21,025 with DLC
   Enhancements). Gun Runners' and SomeguySeries are masters, so their dependents must be rebuilt too. If any of
   these has saves the user cares about, leave it full; new builds still get the default.
4. **Build order:** with the [merged patch](../fo4_load_order.md#merged-patch) (always light), then the
   [preflight](#size) audit, before the first public release of mod conversions. Play-test one light plugin with
   ids below 0x800 on each supported runtime.
