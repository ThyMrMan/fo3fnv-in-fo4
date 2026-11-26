# Plan: converting a whole FO3/FNV modlist (2026-11-25)

Status: planned, nothing built. Builds on
[converting one mod against a built game](fo4_mod_builds.md), whose open
parts a modlist meets all at once, and on the
[load order plan](fo4_load_order.md) (mirroring the order, the conflict
report, the converter's merged patch, LOOT rules, light plugins), which this
plan uses as it stands.

**Goal.** A user points the app at the modlist they already play in New
Vegas or Fallout 3 and gets the same list in Fallout 4: each mod converted,
in the same order, switched on and off the way it was, with a clear report
of what could not come across and why. The user converts their own
installed list; nothing converted is shared, since converted mods carry
their authors' assets.

## Contents

- [What exists](#exists)
- [The input: an MO2 profile](#input)
- [Sorting mods into kinds](#kinds)
- [The output: a mirror of the source](#output)
- [Converting the list](#convert)
- [The main risk: overrides that do not stack](#stacking)
- [Order](#order)
- [Open questions](#open)

## <a id="exists"></a>What exists

- **One mod folder at a time.** The app imports a mod folder
  (`convert.py --import-mod`), exports it and builds it as an add-on into
  its own `F3NV - <mod>` folder beside the game's output
  ([DLC and mods](fo4_gui.md#addons)). An asset-only mod is a pseudo-plugin
  and runs the asset stages alone.
- **MO2 profiles are read.** `core/mod_sources.py` reads an instance's
  `ModOrganizer.ini` and a profile's `modlist.txt` (`enabled_mods`: enabled,
  highest priority first). Today that serves only Fallout 4 side replacement
  lookups ([mod sources](fo4_gui.md#mod-sources)).
- **Ordering and resuming.** `build_plan --run` builds masters first and
  rebuilds only what changed ([rebuild](fo4_gui.md#rebuild)); a build stamp
  says whether each plugin finished. The developer chain's `others` step
  already rebuilds the 30 or so FNV mods in the developer's MO2 setup this
  way (`tools/release/fo4_chain.py`).
- **Light plugins** are a per-mod opt-in ([light](fo4_gui.md#light)).
- **Not built yet** ([mod builds order](fo4_mod_builds.md#order)): the census
  of overrides that only add, the master kit, the shared-file guard,
  Creation Kit steps without MO2, and mods that need other mods.

## <a id="input"></a>The input: an MO2 profile

Most FNV and FO3 lists, every Wabbajack list among them, are MO2 instances.
A profile already holds what a conversion needs:

- `modlist.txt`: which mods are on, and their priority, which settles
  loose-file conflicts;
- `plugins.txt` and `loadorder.txt`: the plugin load order;
- one folder per mod: each converts on its own.

So the entry point is **Import an MO2 profile**: pick the FNV or FO3
instance and profile; the app lists every enabled mod in priority order.

**Fallback for Vortex and hand installs:** the game's Data folder plus its
load order. That converts as one "everything else" mod: it works, but
single mods can no longer be switched off.

## <a id="kinds"></a>Sorting mods into kinds

A real list is maybe half things that cannot or should not be converted.
The first screen sorts each mod by what its folder holds and shows the
result before anything runs:

| Kind | Examples | What happens |
|---|---|---|
| Plugin mod | quest, item and NPC mods, YUP | Converted as an add-on (exists) |
| Asset replacer | texture and mesh packs | Asset-only conversion (exists) |
| Script extender plugin (DLL) | JIP LN, kNVSE, NVTF | Skipped: "needs a Fallout 4 equivalent" |
| UI mod | Vanilla UI Plus, MCM menus | Skipped: Fallout 4's interface is separate |
| Engine, ini or ENB | the 4GB patch, ENB presets | Skipped, listed |
| Merged or bashed patch | an FNVEdit merged patch, a Wrye Bash bashed patch | Skipped: the converter writes its own [merged patch](fo4_load_order.md#merged-patch) from the converted plugins |
| Body or animation replacer | body replacers, kNVSE animation packs | Later, with the [body plan](fo4_bodies_cbbe.md) |

A mod can be several kinds (a plugin with a DLL beside it): its parts are
handled each by its kind, and the report says which part was left out. The
skip report matters as much as the conversion.

## <a id="output"></a>The output: a mirror of the source

**One converted mod per source mod**, not one merged mod:

- each source mod becomes `F3NV - <mod name>`, in the same priority order,
  under an MO2 separator named after the list;
- the app writes the mods and plugins into a Fallout 4 MO2 profile in the
  source's order, as [mirroring the load order](fo4_load_order.md#mirror)
  plans (or FO4's own `plugins.txt` without MO2). This extends today's "Set
  up in MO2" (`app/mo2_setup.py`) from one target to the list.

What it buys: switching a mod off works as it did in FNV, an updated mod
rebuilds alone, and the user sees the layout they built. One merged mod
would be simpler to install, but every change would rebuild everything and
one broken mod could not be switched off.

## <a id="convert"></a>Converting the list

1. **Queue in load order.** The game and its DLC first (already required),
   then each plugin mod, masters before the mods that need them. A mod
   whose master is a mod the list turns off is reported, not built.
2. **Asset conflicts follow MO2 priority.** Each mod converts its own files,
   and the mirrored priority picks the same winner in Fallout 4 as in FNV.
   No conflict logic of our own.
3. **Resumable.** Each mod's build stamp says whether it finished, so a run
   that stops partway picks up where it left off, through `build_plan`.
4. **A per-mod report** on the Finished screen: converted, skipped and why,
   or failed with the log lines that say why.
5. **Plugin count.** Fallout 4 loads at most 254 full plugins; a large list
   plus the converted game can come close. The
   [light plugin policy](fo4_load_order.md#light) stands: full by default,
   a per-mod opt-in before the first build, plugins that only override
   light automatically. The list screen counts full plugins before
   anything runs and, near the limit, shows which mods fit as light so the
   user can opt them in.
6. **Run time.** Each mod build reads its masters' export index; many small
   builds in a row repeat that read. Measure on the reference list before
   deciding whether builds share one process.

## <a id="stacking"></a>The main risk: overrides that do not stack

In FNV many mods add to the same game record; in Fallout 4 the last one
loaded wins and the others' additions are lost. Form lists, perks,
conditions and DLC dialogue are already handled
([Part 2](fo4_mod_builds.md#stacking)). A full list meets every remaining
kind at once, so the census in Part 2 runs on a real list first: for each
kind of record the list's plugins override, how many plugins touch it and
whether they only add. Each "adds only" kind gets a mechanism like the
form-list adds. Leveled lists and the other kinds Wrye Flash merges go to
the converter's [merged patch](fo4_load_order.md#merged-patch); the
[conflict report](fo4_load_order.md#conflicts) shows what is left.

## <a id="order"></a>Order

| Step | What | Size |
|---|---|---|
| 1 | Census on a reference list (Viva New Vegas for FNV) | S |
| 2 | Read and classify a profile: a read-only screen of its mods, kinds and plan | S |
| 3 | Batch conversion through the add-on path, with the per-mod report | M |
| 4 | Write the Fallout 4 profile: mirrored folders and separator, with [load order step 1](fo4_load_order.md#order) | S |
| 5 | Fix what the census finds that only adds; the conflict report and merged patch ([load order](fo4_load_order.md#order) steps 2 and 3) | M, by its count |
| 6 | The master kit, body and animation mods | M each |

Step 2 is useful on its own: it tells a user what their list would become
before they spend hours converting it.

## <a id="open"></a>Open questions

- Which FO3 list or guide is the reference for Fallout 3?
- A shareable "recipe" (which mods, which options, no converted files) on
  top of converting one's own list: wanted, and when?
- Mods with installer options (FOMOD): MO2 already installed the chosen
  files, so the folder is what converts. Is anything lost by not reading
  the installer?
- When a source mod updates, does the app notice (the folder's files
  changed) and offer to rebuild just that mod?
