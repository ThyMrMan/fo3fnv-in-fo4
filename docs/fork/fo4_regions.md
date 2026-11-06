# FNV region tests on Fallout 4 (planned 2026-11-05, built 2026-11-06)

**Status:** approach C built 2026-11-06, not played ([as built](#built)).

**Goal.** Everything FNV gates on the player being inside a region works on
Fallout 4: the NCR emergency radio's support area, the reputation
messengers' and hit squads' "wasteland only" area, and the scripts that test
a map region (Victor in Novac and Boulder City, the Hidden Valley dust
storm). Conditions and scripts give the answer FNV would.

## Contents

- [Where things stand](#now)
- [What FNV tests](#census)
- [Approaches](#approaches)
- [Plan](#plan)
- [Checks](#checks)
- [Open questions](#open)

## <a id="now"></a>Where things stand

An FNV region (REGN) is a set of polygons on a worldspace (`Area[i].PointsHex`,
x and y pairs, each with an edge falloff), plus data entries: map name,
weather, sounds and so on. FNV tests the player's position against the
polygons: `PlayerInRegion <region>` in conditions, `IsPlayerInRegion` and
`GetInRegion` in scripts.

The build converts **map regions** only (a region with a Map data entry, such
as `VMapGoodspringsRegion`). Each becomes an FO4 location, and each world
cell joins the location whose region holds the cell's centre.
A `PlayerInRegion` condition on a map region becomes `GetInCurrentLocation` of
that location ([dialogue conditions](fo4_pipeline.md#dialogue-conditions)).
That is cell-grained where FNV tests the polygon.

What is lost:
- **Conditions on a region with no map data** cannot convert, because
  there is no location to test. A message button with one shows always
  ([message buttons](fo4_pipeline.md#message-buttons)).
- **Every region test in a script** is dropped. The converter writes
  `;NE: && IsPlayerInRegion <region> - Skyrim has no region query` and leaves
  the rest of the `If`, so the script acts as if the player were inside.
  This happens in 9 converted FalloutNV.esm scripts, map regions and others
  alike.

## <a id="census"></a>What FNV tests

FalloutNV.esm, 2026-11-05 (`PlayerInRegion` in record conditions; the
region named after the three script functions):

| Region | Map region | Conditions | Scripts | What depends on it |
|---|---|---|---|---|
| `vMapCanSupportPCHere` (3 polygons) | no | 14 (MESG) | 2 | The NCR emergency radio's support buttons (`VEFR01NCREmergencyRadioMSG`, `VEFR01NCRGood2RadioMSG`); outside, only "Outside NCR Operational Area" shows |
| `vMapCanAttackPCHere` (7 polygons) | no | 0 | 4 | The reputation event quests (`VEFR00LegionMix2`, `VEFR01LegionGood2`, `VEFR01NCRGood2`, `VEFR02LegionBad2`, `VEFR02NCRBad2`): messengers, gifts and hit squads appear only in "valid wasteland" (FNV's comment: no cities, interiors or high-traffic areas) |
| `vMapCottonwoodCove` | yes | 27 (QUST 23, PACK 4) | | converts today |
| `VMapTheFortRegion` | yes | 23 (QUST) | 3 | conditions convert; scripts drop it |
| `VMapCampMcCarranRegion` | yes | 6 (QUST) | | converts today |
| `VMapGoodspringsRegion` | yes | 4 (INFO) | | converts today |
| `MapHooverDam`, `VMapJacobstownRegion`, `VMapHiddenValleyRegion`, `VMapNCRCFRegion`, `VMapNovacRegion`, `vMapVault3FiendRegion`, `vMapNellisAFBRegion`, `VMapBoulderCityRegion`, `VMapCampForlornHopeRegion` and others | yes | | 2 to 4 each | scripts drop it (Victor in Novac and Boulder City, the Hidden Valley dust storm, Cato Hostilius, VMQ03a) |

The DLC are to be counted the same way (`region_tests` census in the
scratchpad: run it per export).

## <a id="approaches"></a>Approaches

**A. A location per tested region, as parents.** Make an FO4 location for
each non-map region a condition or script tests, and assign cells by centre
as map regions are. In FO4 a cell has one location, and the support and
attack areas overlap many map regions (Primm, Nipton, the Mojave Outpost).
That works only if each overlapped map location can take the region's
location as its parent and FO4's location test matches children.
`vMapCanSupportPCHere` and `vMapCanAttackPCHere` overlap each other and cut
across map regions, so the tree would not nest. Cell-grained.

**B. Location keywords.** Keep one location per cell, and give each map
location a keyword for every tested region covering its cells. The
conditions test the player's current location for the keyword. This needs an
FO4 condition that tests the current location's keywords; check which one
(`LocationHasKeyword` on the current location, or `GetInCurrentLocType`). It
is cell-grained, and a location is split when a region covers only part of it.

**C. The polygons, tested in Papyrus (recommended).** One quest script keeps
one global per tested region, 1 while the player is inside its polygons:
- The polygons come from the export (`Area[i].PointsHex`) as script
  properties. The worldspace is checked, then point-in-polygon on the
  player's x and y.
- The script re-tests on the player's location and cell changes
  (`OnLocationChange`, plus a slow timer while in an exterior of a tested
  region's worldspace), not every frame
  ([Papyrus cost](performance.md#papyrus)).
- Conditions test the global (`GetGlobalValue`, as quest variables do
  already). Scripts call `TES4Polyfill.PlayerInRegion(region)`, which reads it.

C is FNV's own test, not a cell-grained stand-in. It needs no location
changes, handles overlapping regions, and fixes conditions and scripts with
one mechanism. Its costs are the polling and a short delay after crossing an
edge. FNV's edge falloff is ignored, as it only softens weather and sound.

## <a id="plan"></a>Plan

1. **Census** every export (game and DLC): the regions conditions and scripts
   test, their polygon point counts (Papyrus arrays hold 128 entries), and
   their worldspaces.
2. **Data:** the export already has the polygons. The build writes one global
   per tested region (`TES4Region_<EditorID>`) and a quest
   `FNV_RegionWatch`. Its script, `F3NV_RegionWatch`, gets each region's
   points (flat x, y arrays, with an offset array per polygon), worldspace and
   global.
3. **`F3NV_RegionWatch.psc`:** on start and on the player's location or cell
   change, and every few seconds while in an exterior of a watched
   worldspace, test each region and set its global.
4. **Conditions:** `say_topics._fo4_condition` maps `PlayerInRegion <region>`
   to `GetGlobalValue TES4Region_<region> == 1` when the region is watched.
   Map regions keep their location test, as it already works; switching them
   too is an option for exactness.
5. **Scripts:** the converter's `IsPlayerInRegion` and `GetInRegion` rows
   become `TES4Polyfill.PlayerInRegion(<region>)`, reading the global. The
   regions scripts name are watched too (step 1's list).
6. **Docs, tests and a build:** the converter row test, a point-in-polygon
   test on one exported polygon, and the build counts.

Size: M (a quest script, records, a converter row, the condition mapping).

## <a id="checks"></a>Checks

- The NCR emergency radio offers support near Primm or the Mojave Outpost and
  only "Outside NCR Operational Area" on the Strip.
- `message button not gated` no longer lists `VEFR01NCREmergencyRadioMSG`.
- The 9 scripts compile with no `;NE:` region marker left.
- A Legion messenger (Legion Mixed or Good, no faction armor) appears in the
  open wasteland, not in Novac or Primm.
- The watch quest's script time in a Papyrus profile stays small while
  walking the Mojave.

## <a id="built"></a>As built (2026-11-06, not played)

**Census** (`region_census` in the scratchpad, every export): 38 regions
tested in FalloutNV.esm and the packs, 3 more in Honest Hearts (Zion). All
are small: the largest polygon has 21 points (the NCR support area), 330
points in all. All but Camp McCarran's are in WastelandNV; Camp McCarran's
is in its own worldspace, so the worldspace is tested. Script names that are
no region (`Goodsprings`, `Primm`, `IvanpahRegion`, `ElDoradoRegion`) are
left as they are.

**The pieces** (`fo4_import/spike/region_watch.py`):
- `RegionWatch` indexes the plugin's regions with polygons and gives each
  region a record condition tests (`PlayerInRegion`, read straight from the
  raw CTDA's function bytes) or a script names (`IsPlayerInRegion`) a global,
  `TES4Region_<EditorID>` (site `FNV region global`, key the EditorID). A
  DLC testing a master's region gets the master's global through the
  masters' ledgers, so it adds no copy.
- A start-game quest per plugin, `FNV_RegionWatch_<plugin>`, runs
  `F3NV_RegionWatch` over the regions whose globals the plugin owns. Its
  array properties carry them: `Globals`, `Worlds`, the bounds, and the
  polygons as `RegionFirst` and `PolyFirst` indexes into the points, which
  are split into 128-point chunks (`X0`-`X3`, `Y0`-`Y3`) for Papyrus's array
  limit. A region past 512 points would be left out, counted.
- The script tests on start, on each location change of the player, and
  every 2 s: the worldspace, the bounds, then a ray-crossing test per
  polygon. It writes a global only when it changes. In an interior every
  global is 0, as FNV's regions are worldspace areas.
- **Conditions:** `PlayerInRegion` on a watched region is `GetGlobalValue`
  of its global (`say_topics._form_value`). Map regions switch too
  (open question 3: one mechanism, FNV's exact edges); the location test
  stays for a region no condition or script names.
- **Scripts:** the FO4 row of `IsPlayerInRegion` is
  `TES4Polyfill.InRegion(<region>)`, a GlobalVariable property named after
  the region, which the build fills with its global (`attach._global_form`).
  An unwatched region's property stays None and reads False.

Open questions settled: no region spans worldspaces; the re-test runs on
location change and a 2 s timer (a coarse area such as the support region
also needs the timer, as one location covers much of it).

To check in game: the NCR emergency radio's support buttons near Primm and
not on the Strip; the reputation messengers away from towns; Victor in Novac
and Boulder City; the watch script's cost in a Papyrus profile.

## <a id="open"></a>Open questions

- Do any regions span worldspaces, or name worldspaces the build places
  differently (FO4 coordinates are FNV's, so polygons carry over unchanged)?
- Re-test interval: on cell change only (the support area is coarse), or a
  timer too?
- Switch the map regions' conditions to the polygon test as well, for one
  mechanism and exact edges?
