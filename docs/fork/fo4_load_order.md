# Load order for converted mods (plan, 2026-11-11)

**Code today:** `fo4_import/app/mo2_setup.py` appends a built target's plugins to the end of the MO2 profile's
`plugins.txt` and `loadorder.txt`, and its mod folder to the top of `modlist.txt`. Nothing orders converted mods
against each other yet.

FNV players sort their load order with LOOT (its FNV masterlist), by hand, or both, and patch the rest with Wrye
Flash's Bashed Patch. None of that reaches a converted load order: LOOT's FO4 masterlist knows nothing about
converted plugins, and the FNV tools don't read FO4 plugins. This plan makes the converter order and patch its own
output, without depending on any one mod manager ([app](fo4_gui.md)).

## Contents

- [What makes this easier than a normal load order](#why-easier)
- [1. Mirror the FNV load order](#mirror)
- [2. A conflict report from the converter](#conflicts)
- [3. A merged patch](#merged-patch)
- [4. LOOT rules for people who use LOOT](#loot)
- [Light plugins](#light)
- [Order](#order)

## <a id="why-easier"></a>What makes this easier than a normal load order

- **One converted plugin per FNV plugin**, with the same name and the same masters. Its place in the order can
  come straight from the FNV order the user already sorted.
- **Converted mods touch only converted records.** A converted plugin overrides `FalloutNV.esm`, its DLC and other
  converted plugins, never Fallout4.esm's records. So converted mods only need ordering among themselves, not
  against the user's FO4 mods (except FO4 mods made to patch converted ones).
- **The converter knows every override.** Each build reads every record it writes and what that record overrides,
  so the conflict list costs nothing extra to collect.

## <a id="mirror"></a>1. Mirror the FNV load order

The app reads the FNV order from where the user keeps it:
- the FNV MO2 profile's `loadorder.txt` and `plugins.txt` (the app already knows the FNV instance from the
  [mod sources](fo4_mod_builds.md#mo2-answers));
- otherwise FNV's own `plugins.txt` (`%LOCALAPPDATA%\FalloutNV\plugins.txt`), with file dates for the order, as
  FNV loads.

It then writes the converted plugins in the same relative order:
- **MO2:** into the FO4 profile's `plugins.txt` and `loadorder.txt` after the game's plugins, and each converted
  mod folder in `modlist.txt` in the same relative priority as its FNV mod folder, so loose files and archives win
  the same way they did in FNV. Plugins and folders already in the profile that aren't converted keep their place.
  Backups as `mo2_setup` makes them today.
- **No MO2:** FO4's own `plugins.txt` (`%LOCALAPPDATA%\Fallout4\plugins.txt`, `*` for enabled).
- **Masters always load first.** A converted plugin's masters are checked against the written order, and an order
  that breaks one is reported, not silently fixed.

Re-running it after the user reorders FNV updates only the converted entries.

## <a id="conflicts"></a>2. A conflict report from the converter

Each build writes the records it overrides (`<plugin>.overrides.tsv`: FormID, record type, EditorID, which
master's record). The app joins these across every converted plugin in the order and shows, per record two or
more plugins change:
- which plugin wins under the current order;
- what each losing plugin changed that the winner doesn't carry (by field, as the export text compares);
- whether it is an "adds only" kind that [part 2 of the mod-builds plan](fo4_mod_builds.md#stacking) makes stack
  at run time, in which case it isn't a conflict at all.

This is xEdit's conflict view, made by the build. It also finds the cases ordering can't fix, which part 3 handles.

## <a id="merged-patch"></a>3. A merged patch

FNV players make a Bashed Patch so that two mods editing the same leveled list both count. FO4 has no such tool for
converted plugins, but the converter builds records anyway, so it can write one more plugin:
`F3NV - Merged Patch.esp`, loaded last among converted plugins.

- **Merged kinds** (the ones Wrye Flash merges): leveled lists (LVLI, LVLN, LVSP), containers' items, form lists,
  NPCs' inventories and factions, and the other list-shaped fields it supports. Each entry added or removed by any
  plugin, against the master's version, lands in the merged record.
- **Everything else** is left to the order: the last plugin wins, as in FNV.
- **No FormIDs of its own:** it only overrides existing records, so rebuilding it never moves an ID and a save
  survives it being rebuilt or removed.
- **Rebuilt** whenever the order or a converted plugin changes. It's small, so building it is seconds.

Wrye Flash's source is GPL; read it for which fields it merges and how, and credit it if any code is used
(see [license](spin_offs.md#license)).

## <a id="loot"></a>4. LOOT rules for people who use LOOT

LOOT and Vortex re-sort FO4's load order and would scramble converted plugins they know nothing about. LOOT reads a
per-user rules file, `userlist.yaml` (in LOOT's `Fallout 4` folder), with `after` rules and groups.

- The app writes one `after` rule per converted plugin, naming the converted plugin before it in the mirrored
  order, plus a "Converted New Vegas" group placed after the game's plugins.
- **Not shipped:** rules taken from LOOT's FNV masterlist. Its license needs checking before anything derived from
  it is distributed; the app may read the user's own local copy instead.

## <a id="light"></a>Light plugins

FO4 allows 254 full plugins but about 4,000 light (ESL) ones. A Tale of Two Wastelands–sized conversion with a
large FNV mod list would hit the full-plugin limit, so making small converted mods light matters. Whether our
hashed FormIDs can fit a light plugin's range without moving IDs in existing saves is investigated separately:
see [research/fo4_light_plugins.md](research/fo4_light_plugins.md).

## <a id="order"></a>Order

| # | Step | Size |
|---|---|---|
| 1 | [Mirror the FNV load order](#mirror) | S |
| 2 | [Conflict report](#conflicts) | M |
| 3 | [Merged patch](#merged-patch) | M |
| 4 | [LOOT rules](#loot) | S |

Steps 1 and 2 go with the app's mod-build work ([mod builds](fo4_mod_builds.md#order)); 3 follows once the
conflict report shows which kinds are worth merging.
