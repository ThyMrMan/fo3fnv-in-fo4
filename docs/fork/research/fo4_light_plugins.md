# Light plugins for converted mods (research and design, 2026-11-11)

**Question:** can converted FO3/FNV plugins be built as Fallout 4 light plugins (ESL-flagged), so a large or
Tale of Two Wastelands–sized load order fits under FO4's 254 full plugins? Asked from
[the load order plan](../fo4_load_order.md#light). Research and design only: no build, no FormID changes.

**Answer:** yes, as an opt-in. A converted plugin keeps its name and extension (`.esm` or `.esp`) and gains the ESL
flag. Its own records get object ids 0x001–0xFFF (4,095 of them) from the same hashed scheme, kept in its ledger.
Today 13 of the 21 converted mods, Gun Runners' Arsenal and the four courier packs fit.

**Decided (user, 2026-11-11): full plugins by default; light only when the user opts in for a mod**, before that
mod's first build. Reason: a mod with an odd light-only problem would break in an odd way, and the user, not the
converter, should take that risk knowingly. Users should not compact converted plugins in xEdit either: the next
rebuild writes the full numbering again and breaks saves and dependent mods
([design](#design), [light-only problems](#problems)).

## Contents

- [Engine rules, per runtime](#rules)
- [How our FormIDs are made today](#today)
- [Census of the built plugins](#census)
- [Design: full by default, light by opt-in](#design)
- [Light-only problems: what the app warns about](#problems)
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

## <a id="design"></a>Design: full by default, light by opt-in

### <a id="policy"></a>The policy

1. **Full plugins by default** for every converted plugin. Nothing in today's numbering changes.
2. **An opt-in "build as light" switch per mod in the app**, set before that mod's first build. The app shows:
   - whether the mod fits: its own-record count against 4,095, and the 3,071 line that leaves a quarter for
     updates ([census](#census); before a first build the count comes from a light trial, see
     [who decides](#who-decides));
   - the [light-only problems](#problems) the mod has, each as a warning.
   With the switch on, the converter gives the mod light-range ids from its ledger, stable across rebuilds
   ([scheme](#scheme)), and dependent converted mods find its records through that ledger.
3. **Locked after the first build.** Switching later moves every own record's FormID, so the app allows it only
   after an explicit "this breaks saves that use this mod" confirmation (the [drift](../../../CLAUDE.md#formid-drift)
   rule, with the count shown).
4. **The converter reads light plugins either way** ([reading](#reading)): a light master of a converted mod, and
   light FO4 or Creation Club plugins in the load order.
5. **Override-only plugins are light automatically:** the [merged patch](../fo4_load_order.md#merged-patch),
   replacement patches, and any converted plugin that makes no new records. They place no ids, so the flag moves
   nothing ([override-only](#override-only)).

### <a id="scheme"></a>The light scheme (for an opted-in mod)

1. **Same hash, smaller window.** In a light plugin `derive_formid` hashes `site\0repr(key)` exactly as now, mod
   4,095, plus 1 (0x001–0xFFF). Collisions rehash with the same salt sequence, with no 64-probe cap: the build
   fails only when every slot is taken. Full plugins don't change: same window, same `FORMID_SCHEME_VERSION`, so
   nothing already built moves.
2. **Every own record is keyed.** A 1:1 FNV record in a light plugin takes site `FNV 1:1`, key its object id in
   its source plugin (six hex digits; the master byte differs between a plugin and its dependents, the object id
   does not). `fnv_id` asks the writer instead of passing the object id through. Copies and generated records
   already have keys. Built 2026-11-12: [light builds](../fo4_pipeline.md#light-builds).
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
is why the app advises leaving a quarter of the space free ([who decides](#who-decides)). A collision never lands on
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

### <a id="who-decides"></a>Who decides: the user, before the first build

- **Default full.** The converter never makes a plugin with new records light on its own.
- **The count before a first build.** The census counts built plugins. For a mod not built yet, the app can run
  the build's record stage with a scratch ledger and count own ids. It then discards the ledger, so the real first
  build starts clean. A full first build reports the same count afterwards. If the user turns the switch on later,
  that is the locked-switch case: the full build may already be in a save.
- **The user** opts in per mod, up to 4,095 own ids; the app advises against going over 3,071. After the first
  build the choice is locked, and changing it is the drift question above.

### <a id="reading"></a>Reading light plugins either way

The converter already reads plugin files by their in-file FormIDs (master index plus object id), which mean the same
for a light master as for a full one. What changes:

- **A light converted master** (an opted-in mod that others depend on): a dependent maps that master's 1:1 records
  through the master's ledger (`FNV 1:1` keys, [scheme](#scheme) item 4), never by passing FNV's object id through.
  The master's light flag comes from its header (`0x200`), not its extension.
- **Light FO4 and Creation Club plugins in the load order** (the nine CC files, FalloutHelpers.esl, users' own ESL
  mods): they take no full slot. Load-order code (`fo4_import/app/mo2_setup.py`, the [conflict
  report](../fo4_load_order.md#conflicts), slot counts) must count only unflagged plugins against 254 and must not
  treat `.esl` as the only light marker (an ESL-flagged `.esp` or `.esm` is light too). Records are keyed by plugin
  name plus object id (`fo4_import/app/catalog.py` already keys `plugin|id`), which needs no change.

### <a id="override-only"></a>Override-only plugins

A plugin with no new records places no ids, so it can be light with no FormID change. That holds both at its first
build and later: a full plugin with no new records can be flagged light without moving anything. Today that covers
FalloutNV - Classic Look.esl and the NVTUP+NVMIM merge (already light), and in future the merged patch and the
replacement patches. If an update to such a plugin adds new records, it is then an opted-out mod with records. It
becomes full, which moves nothing either, because no save can hold a record it never had. The converter can make
that switch on its own.

### <a id="masters"></a>A plugin that is a master of other converted plugins

- A light master is fine (FalloutHelpers.esl is one). Dependents name its records by its master index in their
  own list plus the light id, through its ledger ([scheme](#design) item 4).
- Its type matters more than a leaf plugin's: switching it moves the ids that every dependent references, so every
  dependent must be rebuilt and every save on any of them breaks. Decide a master's type before anything depends on
  it. FalloutNV.esm and the story DLC are full by size anyway. Today's candidates are GunRunnersArsenal.esm (master
  of six mods) and SomeguySeries.esm (master of four).
- A light plugin keeps its ESM bit from the source (ESM+ESL, like Bethesda's CC files), so it still loads with the
  masters. None of our light candidates has a plain-ESP master.

## <a id="problems"></a>Light-only problems: what the app warns about

What can go wrong in an ESL-flagged plugin that would not go wrong in a full one, from engine data first. "Engine"
rows were read in `Fallout4.exe` 1.11.240 (`Fallout4.exe.unpacked.exe`), where `TESFile::IsLight` is the function at
RVA 0x2F91A0 (record flags at +0x334, bit 9, the offset F4SE's `ModInfo::recordFlags` gives). "Works" rows rest on
Bethesda's nine ESL-flagged CC files in the install, censused for their own records (scratch `esl_features.py`).

### Problems with evidence

| Setup | What goes wrong | Evidence | Our light candidates that have it |
|---|---|---|---|
| **Precombined meshes on the plugin's own cells** | The game builds the file name from the cell's FormID `& 0xFFFFFF`, with no light check: `%s\%08X_%08X_OC.NIF` and `_Physics.NIF`. For a light plugin that id carries the 12-bit light slot, which changes with load order. Files made for one slot are not found in another, and the CK can't generate them for a light plugin (it won't edit one) | Engine: path built at RVA 0x48BEA0 (`and r14d, 0xffffff`; the light branch is used only to find the plugin's folder name). Vanilla names: `Meshes\PreCombined\000118FD_3A310FC0_OC.NIF` (Fallout4 - MeshesExtra.ba2). Bethesda's CC files hold no precombines for their own cells, only for vanilla cells they override (PCMB/XCRI on 1–11 overridden cells each) | None today: the converter makes no precombines. Becomes a rule if a precombine stage is added: no precombines on a light plugin's own cells |
| **Previs on the plugin's own cells** | Same: `Data\Vis\%s\%08X.uvd`, id `& 0xFFFFFF`, no light check | Engine: RVA 0x4C7CD4 (`and ecx, 0xffffff`). Vanilla: `Vis\DLCCoast.esm\00000801.uvd` | None today (no previs stage) |
| **New cells in an ESM+ESL plugin that another mod overrides** | xEdit's own ESL script warns these "won't work … due to a bug in the engine". The script is shared by every game and the bug is documented for Skyrim SE. **Not confirmed in FO4's exe: a lead** | `references/xEdit/Build/Edit Scripts/Find ESP plugins which could be turned into ESL.pas`. Counter-evidence: ccFSVFO4007-Halloween.esl (ESM+ESL) adds a cell, but no other plugin overrides it | GunRunnersArsenal.esm (1 new cell; ESM; master of six mods, some overriding cells), JSawyer Ultimate.esp (1), NewVegasBounties.esp (3, with 10 new navmeshes; ESP, so not ESM+ESL) |
| **More than 4,095 own records, or growth past it** | The plugin can't be written | [Rules](#rules); [overflow](#overflow) | DLC Enhancements.esp at 3,784 has the least room |
| **A light plugin with a plain-ESP master** | Loading the light plugin early pulls the ESP early too | CK wiki "Light Master Notes" | None |
| **Hand compacting (xEdit "Compact FormIDs for ESL", Vortex "make light")** | Renumbers behind the ledger; the next rebuild writes the converter's numbering again, breaking saves and dependents | [Scheme](#scheme); user's decision | Any |

### Works in a light plugin (Bethesda ships it)

| Setup | Evidence in the CC `.esl` files |
|---|---|
| Quests with aliases and scripts | All nine with records; Remnants 15 quests (14 with aliases), X02 6 |
| Scripted forms (VMAD) | Remnants 35 scripted refs, 11 NPCs; terminals, activators, magic effects, a weapon |
| Persistent references and actors | Remnants 105 refs, 17 actors; Halloween 75 refs, 8 actors |
| New NPCs, packages, scenes, dialogue | Remnants 87 NPCs, 15 packages; TesCan and X02 scenes with INFO/DIAL |
| New navmesh | Halloween, Remnants, Grenade: 1 each, with NAVI overrides |
| A new cell | Halloween: 1 (ESM+ESL) |
| Overriding vanilla cells with their precombine and previs data | TesCan 10 cells, Remnants 11, X02 5 |
| FaceGen, voice and lip files, SCOL meshes | Engine checks `IsLight` and masks `0xFFF`: FaceGeom path RVA 0x658ED4, FaceCustomization textures RVA 0x655897 and 0x6F43BA, voice `%08X_%u` RVA 0x693E00, `SCOL\%s\CM%08X.NIF` RVA 0x43B278. Our voice (`spike/voice.py`) and FaceGen (`spike/facegen.py`) names use the plugin-local id, which is the same value for a light plugin's own records |

### Not covered by any example

- **New worldspaces, new landscape, LOD for them:** no CC file adds a WRLD or LAND, and none of our light candidates
  does either. LOD paths are named by worldspace EditorID, not FormID, so the slot problem above should not apply.
  Not tested; the app should warn "untested in a light plugin".
- **CommonLibF4:** not in `references/`; F4SE 0.7.9 (`GameData.h`) is the only extender source read.
- **Community reports** were not used as evidence here. Leads to check if one comes up: settlement/workshop data
  on light-plugin cells, and the Skyrim-era cell-override bug above.

**What the app shows:** for a mod with the switch on, one warning per row of the first table that applies, plus
"untested" for a new worldspace. The counts come from the light trial's records: new CELL with or without ESM,
precombine or previs data on own cells, and ESP masters.

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
| Gun Runners' Arsenal and the 4 courier packs (full by default; light if the user opts in) | 5 | (5) |
| TaleOfTwoWastelands.esm (FO3 and its 5 DLC) | 1 | |
| Merged patch and replacement patches | | each |
| **Fixed cost** | **19** (14 if the user opts the five small DLC in) | |

With full plugins by default, 235 full slots are left for mods, the user's own FO4 mods included. That is the
ceiling a TTW-sized list hits first, and the opt-in is what lifts it. In this census 8 of 21 converted mods (38%)
can't be light; the other 13 can if the user opts them in. If a big list has the same mix and the user opts in
every mod that fits, about **630 converted mods** fit (240 / 0.38) instead of 235. Each mod opted in frees one full
slot. The large mods (quest and world mods like NVB II/III, Russell, AutumnLeaves) always take full slots. Small
fixes, gear and NPC mods, the most common kind on a big list, are the ones a user can opt in.

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
  behind the ledger's back. The next rebuild writes the converter's numbering again, which breaks saves and
  dependent mods. The app tells users to use the opt-in switch instead. The converter checks that a built plugin's
  own ids match its ledger before a rebuild, and stops with that explanation when they don't.
- **Code that assumes the master byte:** `SourceIds.fo4`, `from_master` (`index << 24 | oid`), `CellBuilder.fnv_id`,
  `master_overrides` and the conflict report all build FormIDs as master index plus object id. That stays true for
  a light master inside a plugin file (the master index is file-local), but each place that turns an FNV object id
  into ours needs the ledger path. Runtime sidecars (`F3NV_Menus` rows, the DLL's `LookupFormByID` callers) name
  forms by plugin plus object id or resolve at load, so a light id passes through; the dialogue menu's
  docstring already says it resolves "under any load order or ESL". This was read, not tested.
- **Practical light limits:** the wiki notes file-handle and reference limits well below 4,096 files. Not a concern at
  hundreds of plugins; not measured.

## <a id="size"></a>Size of the work

About 300–400 lines plus tests, one session, no change to any full plugin's ids:

| Piece | Where | About |
|---|---|---|
| Light window and uncapped probing in `derive_formid` when the writer is light | `LedgerWriter` (`fo4_import/base/ledger.py`) | 40 lines |
| `FNV 1:1` keying of own records in a light build | `CellBuilder.fnv_id` (`fo4_import/spike/cell.py`) | 15 lines |
| Light masters through their ledger | `SourceIds.fo4`, `master_ledgers` (`fo4_import/base/source_ids.py`) | 40 lines |
| ESL flag, ESM bit kept, next id | `FO4PluginWriter` header (already has `is_esl`) | 10 lines |
| Policy: `light` in `.build.json`, locked after the first build, flip only with the confirmation, refuse without ledger or after hand compacting, overflow stop, override-only plugins flagged light | build finish and stamp (`spike/build_finish.py`, `fo4_pipeline.md#build-stamp`) | 80 lines |
| App: per-mod opt-in switch, fit count from a light trial, the confirmation, the [light-only warnings](#problems) | `fo4_import/app` | 80 lines |
| Load order: count only unflagged plugins against 254; light flag from the header | `fo4_import/app/mo2_setup.py`, the conflict report | 20 lines |
| Preflight audit: own ids within 0x001–0xFFF in a light plugin; own ids match the ledger | `tools/validate/preflight` | 50 lines |
| Tests: light determinism (same keys, same ids), dependent resolution through a light master, overflow stop | `tests/` | 80 lines |

## <a id="recommendation"></a>Recommendation

Following the user's decision ([policy](#policy)):

1. **Full by default; a per-mod "build as light" opt-in in the app**, before the mod's first build, showing the
   fit count and the [light-only warnings](#problems). An opted-in mod uses the [light scheme](#scheme): ESL flag
   on the same-named plugin, HEDR 1.0, ids 0x001–0xFFF hashed from the same keys, every own record keyed, the
   ledger required.
2. **Locked after the first build**; switching needs the "breaks saves that use this mod" confirmation, with the
   count of ids that move.
3. **Override-only plugins are light automatically** (merged patch, replacement patches, converted plugins with no
   new records): no id moves.
4. **The converter reads light plugins either way**: light converted masters through their ledger, and light FO4
   and CC plugins counted correctly in the load order.
5. **Plugins already built stay full.** Nothing switches unless the user opts a mod in and confirms; the census
   gives each plugin's count of ids that would move.
6. **Before the first public release of mod conversions:** the [preflight](#size) audit (light ids in range, ledger
   matches the plugin), a play test of one opted-in plugin with ids below 0x800 on each supported runtime, and a
   play test of an ESM+ESL plugin whose new cell another plugin overrides. That last one settles the xEdit lead,
   which affects Gun Runners' Arsenal if it is ever opted in.
