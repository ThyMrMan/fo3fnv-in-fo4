# Item condition on Fallout 4

**Status:** built 2026-10-22/23 in the F3NV F4SE plugin
(`tes_runtime/fo4_condition/`); each part's play state is in its heading. The
decision is in [drift](fo4_drift.md#candidates). Mods read for method: [Armor and Weapon Condition](research/fo4_target.md#awc)
and [NV Ammo Crafting](research/fo4_target.md#nv-ammo).

Fallout 4 keeps no condition on weapons or armor, except power armor. The build rebuilds FNV's condition
from FNV's own data: each item's health, wear per shot or hit, the
effects of low condition, NPCs' worn gear, and repair.

## <a id="fnv-rules"></a>What FNV does

Read from FalloutNV.esm and the GOG `FalloutNV.exe` (2026-10-22, notes in
the session scratchpad). Tags: **ESM** parsed from the plugin, **EXE**
disassembled, **I** inferred. The text export leaves out ARMO DATA and
DNAM, WEAP REPL and most of WEAP DNAM, so the converter must read those
from the plugin.

| Rule | FNV | Source |
|---|---|---|
| Item health | WEAP DATA Health: 256 of 261 between 2 (Fists) and 10,000; 5 broken display copies at 0. ARMO DATA Health: 386 of 389 between 1 and 1e8 (Pip-Boy 100,000); 3 broken at 0 | ESM |
| Repair lists | REPL (a form list): 177 weapons over 93 lists, 288 armors over 69 lists | ESM |
| Gun wear | `fDamageToWeaponValue` (0.2 in the ESM) per shot × the ammo's condition effect (11 AMEF, ×0.75 to ×3) × perk entry point Modify Item Damage (Built to Destroy ×1.15, Regular Maintenance ×0.5, Full Maintenance ×0.25). Non-playable weapons don't wear; health below 1 becomes 0 | EXE, ESM |
| Melee wear | The same value per hit | I |
| Armor wear | Hit damage × the absorbed fraction (capped) × `fDamageToArmorPercentage` (0.35) | EXE |
| Weapon damage | ×1 at 75% and above, then 1 − (0.75 − h) × 0.67, about ×0.5 at 0 | EXE |
| Armor DT and DR | ×1 at 50% and above, then 1 − (0.5 − h), ×0.5 at 0 (the wiki's 0.66 is wrong) | EXE |
| Reload jam | Chance by condition: 0%: 1.0, to 20%: 0.75, 20–30%: 0.5, 30–40%: 0.25, 40–50%: 0.1, above 50%: never. 17 weapons are flagged No Jam After Reload. Firing jams: the table is all 0, so never | EXE, ESM |
| Spread, rate of fire | Not changed by condition | EXE |
| Value | About value × h^1.5 | EXE |
| NPC gear | Authored per inventory entry (COED Item Condition): 1,345 NPC entries, 1,926 leveled-list entries (mostly 0.35–0.55), 94 container entries. No random range | ESM |
| Repair (player) | New % = max + 5 + 0.15 × Repair + 0.05 × the lower of the two items; the cap the engine computes isn't applied to the player | EXE |
| Repair (vendor) | Cap 40% + 0.6% per vendor Repair point; cost 2 × value × (cap − current) / 10 | EXE (value: I) |
| Repair kit | `NVRepairKit` runs `RepairKitEffectSCRIPT`: +10/15/20/25/30% at Repair <25/25/50/75/100 | ESM |
| Jury Rigging | Entry point Has Jury Rigging: repair with any item of the same class | ESM, wiki |
| Scripts | `AddItemHealthPercent` 127 calls (SCPT 61, INFO 43, QUST 23), `ModWeaponHealthPerc` 6, `GetWeaponHealthPerc` 3, `SetWeaponHealthPerc` 1, `ShowRepairMenu` in 10 INFO scripts. Users: the tutorial (under 25%), Miss Fortune (breaks the target's weapon), ED-E's upgrades, a broken SMG handed over at 40% | ESM |

## <a id="fo4-pieces"></a>What Fallout 4 gives

Checked 2026-10-22 against `wbDefinitionsFO4.pas`, Fallout4.esm and
F4SE 0.7.9's Papyrus sources.

- **Engine item health:** FO4 records an item condition per inventory
  entry (COED Item Condition, a float), and conditions have
  `GetItemHealthPercent` (function 723). Vanilla wires both only to power
  armor: 60 leveled-list entries carry a condition, and one perk
  condition (`PowerArmorPerk`) tests it. Papyrus has
  `ObjectReference.GetItemHealthPercent()` and `Repair()`, but no way to
  set an item's health. The engine keeps a weapon's health and saves it
  ([spike results](#spike-results)).
- **F4SE Papyrus:** `InstanceData` reads and sets an instance's damage,
  damage types, magazine size, armor rating and health, weight, value and
  keywords. Its owner is a weapon or armor form, or an actor plus an
  equip slot. `GetAllMods`, `AttachModToInventoryItem` and
  `GetInventoryItems` work on inventories. `UI.Get` reads menu values.
- **Native plugins:** F4SE 0.7.9 with its source, and the Address Library
  covers 1.11.240 (the installed runtime). Hydra and Addictol are F4SE
  plugins already running on it.

## <a id="options"></a>Two ways to build it

Two were weighed: **A**, AWC's scripts on every item (a float per copy and
up to 101 condition mods, but every scripted item a persistent reference),
and **B**, the engine's own item health through an F4SE plugin. The spike
below settled it for B.

## <a id="spike"></a>Spike: does the engine keep weapon health?

A small test plugin, one question per play-test:

1. A leveled list hands the player a weapon with COED condition 0.5. Does
   the item keep it (`GetItemHealthPercent` on the dropped reference), and
   does the Pip-Boy show a condition bar?
2. A perk with Mod Weapon Damage ×0.5, conditioned on
   `GetItemHealthPercent` < 0.75: does the weapon hit for less?
3. A minimal F4SE plugin built for 1.11.240 reads and writes the equipped
   weapon's health. Does it persist across a save and load?

Built and played 2026-10-22 as the disabled MO2 mod `Condition Spike`
(`temp/condition_spike/`).

<a id="spike-results"></a>**Played 2026-10-22** (the plugin's log and the console):
- **3 passed: weapon health is stored and saved.** The plugin gave the equipped
  Varmint Rifle `ExtraHealth` 0.4. After a game restart the rifle still had
  0.400. The plugin then wrote 0.24, and the next load read 0.240.
- **The condition test cannot read it on a weapon.** `GetItemHealthPercent` on
  the dropped rifle gave -1 while the rifle carried health. Vanilla wires it
  only to power armor (one perk condition), so question 2 cannot pass for
  weapons: a perk cannot scale damage by condition.
- **No display.** The Pip-Boy shows nothing for a weapon's health.
- **1 inconclusive.** `player.additem` of the leveled list gave a 10mm with no
  health. Console-added leveled lists may skip COED; untested in a container or
  an NPC's inventory.

So the build is a hybrid of B and A:
- Storage is the engine's item health, written by our plugin and kept by
  the save, with no per-item scripts.
- The effects come from our plugin: it reads the equipped weapon's health
  and applies FNV's curves, as condition-tier object mods (A's method) or a
  damage hook.
- Wear, jams, repair, FNV's script calls and the display are the plugin's
  and ours.

## <a id="built"></a>Weapons, built 2026-10-22

**Played 2026-10-22:** equipping shows the condition, firing wears it down, and
the Repair Weapon hotkey repairs it from a spare pistol. The first build looped
equip/unequip: `AttachModToInventoryItem` re-equips the weapon, so the
re-equip saw a stale tier and attached again. The script now records the tier
it attached per weapon before attaching, and a whole weapon gets no mod.
Untested: a weapon breaking at 0, wear perks, and ammo with a condition effect.

- **The plugin** (`tes_runtime/fo4_condition`, `F3NV.dll`) adds
  four natives to `F3NV_Condition`:
  - `GetHealth` and `SetHealth` read and set an item's health. They work on
    its equipped stack, else its first, and add `ExtraHealth` when the item
    has none.
  - `GetEquippedWeaponHealth`.
  - `StackCount`: copies in one stack share one condition.
- **Records** (`fo4_import/spike/condition.py`):
  - Every converted weapon with FNV health that is not thrown or placed takes
    our attach point `FNV_ap_Condition` and keyword `FNV_ma_Condition`.
  - Eleven condition mods `FNV_mod_Condition000`…`100`, one per tenth, set at
    the tenth's middle: value × h^1.5 always, and FNV's damage curve below
    75%. The whole one has no effect.
  - The quest `FNV_Condition`, whose player alias runs `F3NV_ConditionPlayer`.
  - FNV's repair lists as FLSTs, and the Repair Weapon hotkey item.
  - The DLL is copied into the mod's `F4SE\Plugins`.
- **Wear** (`F3NV_ConditionPlayer`, the player only):
  - Each `weaponFire` (gun) or `HitFrame` (melee swing) takes
    `fDamageToWeaponValue` (0.2) over the weapon's FNV health.
  - The loaded round's condition effect multiplies it, found by its ammo mod's
    keyword, as do held perks on entry point 68: Full Maintenance ×0.25,
    Regular Maintenance ×0.5, Built to Destroy ×1.15.
  - The condition mod is swapped as a tenth is crossed, but not mid-fight:
    attaching re-equips the item (played: the pistol fired twice, then
    re-equipped on the first shot). Wear marks the item, and the mod goes on
    at the next holster (`weaponSheathe`), reload end (`reloadStateExit`),
    Pip-Boy opening or equip. From 90% up an item takes no mod, so value
    there is whole (drift: FNV's value starts falling at once).
  - At 0 the weapon is unequipped as broken, and a broken weapon will not stay
    equipped.
  - Equipping shows the condition.
  - An item with no health set yet is whole.
- **FNV's commands** convert to `F3NV_ConditionCalls`: `GetWeaponHealthPerc`,
  `SetWeaponHealthPerc`, `ModWeaponHealthPerc` (Miss Fortune's -100 breaks)
  and `AddItemHealthPercent`. So FNV's own Weapon Repair Kit script works as
  written.
- **Repair from a spare:** the Repair Weapon hotkey uses another copy of the
  weapon, else an item of its repair list. FNV's rule gives the better
  condition, plus 5, plus 0.15 per Repair point, plus 0.05 of the worse, in
  percent.

<a id="plugin-build"></a>**Building the plugin.** `tes_runtime/fo4_condition/build.bat` links against
F4SE 0.7.9's source (`Fallout 4\src\f4se-0.7.9.tar.gz`, unpacked) and
ianpatt's `common`, both built as static libraries with CMake as F4SE's README
gives (`-DF4SE_STATIC_LIB=ON`), under `TOOLS_EXT`
(default `C:\Coding\tes4skyrim\tools_ext`). Its addresses are F4SE 0.7.9's, so the
DLL loads on Fallout4.exe 1.11.240 only.

## <a id="sources"></a>Every plugin's items: sources gathered at run time

**Bug (play test, 2026-11-02):** with FalloutNV, Gun Runners' Arsenal, the four
courier packs, Dead Money and Honest Hearts loaded, no DLC item had condition
(Mercenary's Grenade Rifle, Caravan's Sturdy Caravan Shotgun, every DLC armor).
Each DLC build overrode the game's `FNV_Condition` quest with the game's items
plus its own (FalloutNV 197 weapons; Mercenary Pack 198; Honest Hearts 231, none
of Mercenary's). Overrides do not stack, so the last plugin loaded, Honest
Hearts, decided. The Ammo Type hotkey and challenges were merged the same way
and broke the same way.

**Built (no DLL change):** a plugin's items are its own quest's.
- `F3NV_ConditionSource` (on a start-game quest) holds one plugin's rows:
  weapons, their FNV health and jam times, round wear marks, wear perks,
  armors, their health and tier groups and tiers, repair lists and Jury
  Rigging groups. The game's are on `FNV_Condition` itself, a DLC's on
  `FNV_Condition_<plugin>` (`Condition.write` writes only that when its master
  holds the quest).
- As it starts, it adds itself to `FNV_ConditionSources`, an empty game form
  list (`FormList.AddForm`, kept by the save; additions stack for any number
  of plugins, in any load order), and gives the DLL its items:
  `Track`/`TrackRepair` add to what the DLL holds.
- `F3NV_ConditionPlayer` finds an item's rows through that list
  (`WeaponSource`, `ArmorSource`), multiplies every source's wear marks and
  perks, and gathers worn armor from each. On every game load it registers
  every source again (the DLL forgets its items).
- The ammo hotkey (`F3NV_AmmoSwitchSource`,
  [ammo switch](fo4_pipeline.md#ammo-switch-sources)) and challenges
  (`F3NV_ChallengeSource`, [challenges](fo4_pipeline.md#challenges)) work the
  same way; game form lists a DLC adds to get its entries at run time
  ([lists](fo4_plugin_layout.md#dlc-lists)).

## <a id="armor"></a>Armor, built 2026-10-22, played

- **Records** (`condition.py`, `wire_armor`):
  - Every converted armor with FNV health (ARMO DATA, read from
    FalloutNV.esm) takes the same attach point and keyword as weapons.
  - Vanilla armor mods never multiply Rating: Fallout4.esm's 271 Rating
    properties are all integer adds. So armor tiers subtract, and there is
    one set per distinct armor rating: `FNV_mod_ArmorCondition<tier>_DT<r>`
    below 50%, where FNV's curve takes `r × (0.5 − h)` off. Tiers from 50%
    up change only the value and are shared by every rating.
- **Wear** (`F3NV_ConditionPlayer.OnHit`, the player only):
  - FO4's hit event carries no damage, so it is rebuilt. The hit's damage is
    the attacker's equipped weapon instance's (F4SE `InstanceData`, slot
    32 + `GetEquippedItemType`, AWC's method), else the weapon form's own.
  - The share the armor stopped comes from FO4's armor formula: damage taken
    = damage × clamp((damage × 0.15 / DR)^0.365, 0.01, 0.99), with the
    player's DamageResist. It is capped at FNV's `fMaxArmorRating` (85%).
  - Every worn armor piece with health loses damage × share × 0.35
    (`fDamageToArmorPercentage`) over its FNV health. FNV's exe stores one
    wear value per hit; which pieces it goes to is inferred.
  - Armor at 0 stays on with half its DT, as FNV's curve gives.
- **Repair:** the Repair hotkey (renamed from Repair Weapon) repairs the
  equipped weapon when it is below whole and has a spare, else the worn
  armor piece in the worst condition that has one (ARMO REPL lists). It
  names what it repaired and puts the new condition mod on at once.
- **The region build:** 136 armors wired, all with the keyword. The 4
  unwired ARMO are creature skins. There are 92 armor tier mods, 81 of which
  cut DT. All 1,810 scripts compile, and FO4Edit reports 0 errors.
- **Drift:** physical damage and DamageResist only, since converted armor
  keeps only physical resistance. Armor penetration is ignored.

## <a id="pipboy"></a>Pip-Boy, built 2026-10-22

**First play-test, 2026-10-22:** nothing showed, and T opened the perk grid. The log
had "Pip-Boy hook registered" but no "hooked the Pip-Boy menu". Rebuilt with
the open-event hook and the G key.

**Second play-test, 2026-10-23:** still nothing. The log said "its root has no
BGSCodeObj" on all 4 opens. The hook now looks for the menu's instance at
`root` and at `root.Menu_mc`, by path (as F4SE's `UI.Get` does), and logs the
root's members when neither has it.

**Third play-test, 2026-10-23:** CND showed, and the menu's instance is at
`root.Menu_mc`. G did nothing. With two 9mm pistols at 100% and 97%, both
entries showed 100%, because matching by name found the first stack for
both. So G on the 97% one hit "needs no repair", and that notification is
hidden in the Pip-Boy.

The log gave each entry's members: `favorite`, `taggedForSearch`,
`isLegendary`, `count`, `nodeID`, `filterFlag`, `equipState`, `text`,
`clipIndex`, `formID` and `canFavorite`. There is a form ID, but no stack index.
- Entries now match by `formID`.
- An equipped entry is the equipped stack.
- An unequipped entry is the stack of its position among that form's
  unequipped entries (`entryList` order, taken as the inventory's; unverified).
- Each match is logged.
- In the Pip-Boy a failed repair shows a message box.

Played in the fourth play-test, 2026-10-23 (below).

<a id="repair-choice"></a>Asked for: choose what gets repaired, and show condition in the Pip-Boy.
FNV repairs the item highlighted in the Pip-Boy. Built with no new mod: the
F3NV plugin (`pipboy.cpp`) works inside FO4's own Pip-Boy movie.

**How the Pip-Boy works.** Read from `interface\pipboymenu.swf` and
`pipboy_invpage.swf` (Fallout4 - Interface.ba2), decompiled with JPEXS FFDec
26.4.0 (`tools_ext\FFDec`, `ffdec-cli.jar -export script <out> <swf>`):
- The menu's root (`PipboyMenu`) keeps its pages in `PageA`, the shown one in
  the `CurrentPage` getter, and the game's data in `DataObj` (`InvItems`).
  Pages share the root's `BGSCodeObj`, a plain object of native functions
  that `BGSExternalInterface.call` calls by name.
- The inventory page (`Pipboy_InvPage`) has `List_mc` (a `BSScrollingList`;
  its `selectedEntry` has `text`, `count`, `equipState`, `nodeID`) and
  `ItemCard_mc`. On a selection change it calls the native
  `onInvItemSelection(index, ItemCard_mc.InfoObj, …, page)`. The game
  refills that array and calls back `onListSelectionChangeCallback`, which
  marks the card dirty.
- The card (`Components.ItemCard`) draws one line per `InfoObj` element at
  its next render: `{text, value}`, with `showAsPercent` adding "%".
- Keys in use there: Enter, X, R, Q, C, Tab, Z, and T, which is the menu's own
  Grid View (`PipboyMenu.GridViewButton`; Y on a gamepad). G is free. No
  gamepad button is free.

**What the plugin does:**
- When `PipboyMenu` opens (a menu open event, then an F4SE UI task), it adds
  a native `enterFrame` listener on the menu's root, once per menu: a flag
  on its `BGSCodeObj` marks it. The first build hooked F4SE's per-menu
  Scaleform callback instead. In play it never matched the Pip-Boy, whose
  root members are not set yet when that callback runs.
- Each frame on the inventory page, it reads the highlighted entry. It finds
  that entry's item in the player's inventory by `formID`, among the forms
  that wear (`F3NV_Condition.Track`), and its stack (see the third play-test).
  - It keeps that stack's condition for the `CND` line, which our movie
    draws (below).
  - It logs the members of the first entry it reads to `F3NV.log`.
    The game may give an inventory handle that would replace matching by name.
- On keyboard and mouse (`uiPlatform` 0), it adds a REPAIR hint (G) to the
  inventory page's `buttonHintDataV`, once per page, and rebuilds the hint bar. Clicking the
  hint sends the F4SE external event `FNVConditionRepair`.
- Natives: `PipboySelection` and `PipboyStack` (the highlighted item),
  `PipboyRefresh` (show the new value after a repair), and
  `GetStackHealth` and `SetStackHealth`.

**Our own movie in the Pip-Boy** (2026-11-12, spike 4 of the
[menu framework](swf_framework.md#spikes), played under the vanilla Pip-Boy: works): the same
once-per-menu hook loads `Interface\F3NV_Pipboy.swf` into the menu instance
with a `Loader` (`LoadOverlay`). Since 2026-11-12 (built, not played) it
draws the CND line: each frame it calls the native `PipboyCardLines`, which
gives `[{text: "CND", value, showAsPercent}]` for an item that wears, and
keeps those lines in the card's `InfoObj`, redrawing the card
(`onDataChange`) when it adds one or a value changes. The game's refill
drops the line and the next frame adds it back. While a repair or ammo list
draws the card, the native gives null and the movie leaves the card alone.
Without the movie there is no CND line in the Pip-Boy (the container and
barter menus still draw theirs from C++, `transfer.cpp`). Hints and lists
are still drawn from C++ ([framework](swf_framework.md#pipboy)).

**Papyrus:** `F3NV_ConditionPlayer` tracks the items, registers G
while the Pip-Boy is open, and listens for the hint's event. Each of them
repairs the highlighted stack from a spare. The Repair hotkey item now calls
the same alias code (`RepairFromHotkey`).

**Fourth play-test, 2026-10-23:**
- The game's stack lookup worked. The log matched each line to its stack
  (lines 13970 and 14067 of the 9mm pistol: stacks 0 and 1, at 1.000 and 0.979).
- Two whole pistols picked up together share one stack (count 2), and one
  health. Firing the equipped one wore both to 98%.
  - First fix (reverted after the fifth play-test): park the other copies in
    a holding container and bring them back.
- G never reached Papyrus: the log had no repair trace. G is now heard two
  ways:
  - Papyrus `OnKeyDown`, traced;
  - a native `keyUp` listener on the menu (Flash key code 71), which sends
    `FNVConditionRepair`.
  A second request within 0.3 s is ignored. Menu events, keys and each send
  are logged. Played in the fifth play-test (below).

**Fifth play-test, 2026-10-23:**
- G reached the repair: the trace showed "Pip-Boy repair … stack 0".
- The parking unequipped the pistol after a couple of shots. `RemoveItem`
  moved every other 9mm pistol ("parked 4"), the worn one among them.
- Condition then landed on the wrong copies: the repair hit several pistols,
  and there ended up two stacks of two whole ones.

<a id="stack-writer"></a>**The engine's stack writer** (replaces the parking):
- The game writes an item's health with
  `TESObjectREFR::FindAndWriteStackData` (RVA 0x502560). It passes the
  reference's inventory list to 0x34E870, with five arguments: the object, a
  compare functor, a write functor, an object compare function and an
  always-continue flag.
- `BGSInventoryItem::CheckStackIDFunctor` (vtable 0x247A038, countdown at +8)
  accepts the stack its countdown reaches. Its compare at 0x34BE90 decrements
  and matches at 0.
- `BGSInventoryItem::SetHealthFunctor` (vtable 0x252B680) has two flags at +8
  and +9 and the health at +0x10.
  - Its write method (0x34C070) sets the stack's extra data health
    (0x27B440).
  - Read from CommonLibF4's names, not verified: the flags split one copy off
    a shared stack, then move the equipped flag to it.
  - The game's own call at 0x98E750 sets both flags.
- `WriteHealth` in `plugin.cpp` builds the two functors with our own
  same-object compare and calls it. So wear and repair change one copy
  only, and the one in hand stays equipped.

**Sixth play-test, 2026-10-23:**
- The stack writer worked: firing kept the pistol equipped, and three
  pistols ended up as separate 100%, 99% and 98% lines.
- G sent the event eight times (plugin log), but no repair trace followed. The
  double-press guard compared the real-time clock with the last repair's
  time, which the save keeps from an earlier session. The clock restarts at
  each launch, so the difference came out negative, and every press was
  taken for a repeat. Fixed: a time before the stored one is a new press.
- Equipping another copy left the Pip-Boy's equipped mark on the old line
  until it was reopened. On a tracked item's equip or unequip, the plugin now
  sets each line of that form from its own stack (`FixEquipMarks`), then
  calls the list's `UpdateList`.
- Papyrus `OnKeyDown` never fired in the Pip-Boy (no key trace). The
  native key listener carries G.

Not played on their own; the next build, with the repair list below, was
played 2026-10-23.

<a id="repair-list"></a>**The repair list (built 2026-10-23; played the same day: it repairs).** FNV's repair menu
lists every spare with its condition bar, previews the gain and shows the
Repair skill (asked for with a screenshot). Ours:
- G or the REPAIR hint on an item that wears opens a list on the item card.
  - First the Repair skill.
  - Then the spares (six at a time; eight since the movie draws them): the item's other unequipped stacks, another copy
    in its own stack, and unequipped stacks of items in its FNV repair list.
    Each shows its name, a count when more than one, and its CND.
  - Then the item's CND before and after, and "ENTER) REPAIR / ESC) CANCEL".
- The page's own modal is on meanwhile: `ModalFadeRect_mc` visible, which
  its quantity and favorites pop-ups use and which makes `ProcessUserEvent`
  skip its actions, and `List_mc.disableInput`.
- Keys, heard by the native `keyUp` listener: Up or W and Down or S move,
  Enter or E repairs, Esc, Tab or G cancels. Closing calls the page's
  `onListSelectionChange`, so the game refills the card.
- The default spare is the worst one that still gives the best result
  (`repair.cpp` `DefaultSpare`).
- Repairing (`RepairWith`) uses up one copy of the chosen stack with the
  engine's remove-from-stack, `BGSInventoryList` 0x34E020.
  - Its arguments: the list, the object, the stack index, the count and a
    more-stacks flag.
  - `TESObjectREFR::RemoveItem` calls it once per stack ID, at 0x50162C.
  - It sends the inventory event, marks the list weight dirty (+0x70 =
    -1) and drops an emptied stack.
  - Then the item's stack is written through the stack writer, its index
    shifted down when an earlier one-copy spare stack of the same item was
    removed.
- FNV's rule now lives only in the plugin: `RepairResult`, the better plus
  5, plus 0.15 per Repair point, plus 0.05 of the worse, capped at 100.
  - The Repair hotkey calls the same native: `F3NV_ConditionCalls.RepairWithSpare`
    → `F3NV_Condition.RepairWith`, on the worst copy of the first spare item.
  - `TrackRepair` gives the plugin the repair lists and the Repair skill.
- Played: the fade dimmed the card too, so G looked like a pop-up that never
  came. While the list is open, the card is now lifted above the fade
  (`setChildIndex` to the top, put back on close). A whole item says "REPAIR
  Not needed", not "No spare". Not yet played.
- Untested: removal skips `RemoveItem`'s own work, so no `OnItemRemoved` and
  no HUD line. Equipped stacks are never offered as spares.
- **Since 2026-11-12 (built, not played) our Pip-Boy movie draws the list**
  as a pop-up over the card, from the native `PipboyList`
  ([framework](swf_framework.md#pipboy)); the card is no longer replaced or
  lifted, and "Not needed" / "No spare" come through `PipboyCardLines`. The
  keys, the spares and the repair are unchanged.

<a id="ammo-list"></a>**The ammo list (built 2026-10-23, not yet played).** FNV picks a gun's
ammo in the Pip-Boy. Asked for: the same on the inventory page, opened the
way the repair list is. The ammo itself still switches through the Ammo
Type hotkey's Papyrus ([fo4_pipeline.md#ammo-switch](fo4_pipeline.md#ammo-switch)):
each FNV round is one ammo mod.
- **Key:** B, or the AMMO hint beside REPAIR (keyboard and mouse only, like
  REPAIR). The Pip-Boy uses T, G, Q, E, R, X, C, Z, Tab and Enter, and V
  (Toggle POV) is its own "Pipboy Zoom": with V the list zoomed the screen,
  which cut the list's right side off, and a list closed by Esc or Tab or
  by leaving the Pip-Boy left the zoom on (P, 2026-11-12; B since then, not
  played). Like G, it is heard by the native `keyUp` listener, since
  Papyrus `OnKeyDown` never fires in the Pip-Boy.
- **The list** (`tes_runtime/fo4_condition/ammo.cpp`), under the page's
  modal; since 2026-11-12 (built, not played) our Pip-Boy movie draws it
  from `AmmoView` as the repair list is drawn. It reuses the repair list's
  helpers in `pipboy.cpp` (`CurrentPage`, `SetModal`, `SayOnCard`,
  `MakeHint`, `SendExternal`):
  - "AMMO TYPE / CARRIED", then the rounds of the gun's FNV ammo list the
    player carries, and the loaded one (eight at a time): name, the count
    carried over all stacks, and "(loaded)" on the round the gun holds.
    Until 2026-11-12 every round of the list showed, carried or not (P).
    Last, "ENTER) LOAD / ESC) CANCEL"; ENTER is left out on the loaded
    round, which may be one the player has none of.
  - Keys: Up or W and Down or S move, Enter or E loads, Esc, Tab or B
    cancels. Enter on the loaded round just closes.
  - The loaded round: the highlighted line's stack (`LineStack`), then the
    first of the list's ammo mods among the mods in that stack's
    `BGSObjectInstanceExtra`. With none, the first round, which the gun's
    default combination holds (`AmmoMods.wire`).
  - A gun of a single ammo type says "AMMO One type only" on the card.
    Carrying two copies says "Drop a copy first": Papyrus's
    `AttachModToInventoryItem` takes a form, not a copy, so the hotkey
    refuses that case too.
- **The gun's list:** the gun's record carries the list keyword
  (`TESObjectWEAP` keywords at +0x150), as `Cycle()` finds it.
- **Papyrus:** `F3NV_AmmoSwitch` hands its `Lists`, `Starts`, `Rounds` and
  `Mods` arrays to the plugin (`F3NV_PipboyAmmo.SetLists`) at quest start and
  on each game load (a remote `OnPlayerLoadGame` on the player), and registers
  for the external event `FNVAmmoSwitch`. Confirming sends it; `OnPipboyAmmo`
  reads `ChosenGun` and `TakeChoice` (the round's index in `Rounds`) and calls
  `Load`, the code `Cycle()` now uses too. `Load` equips the rounds only when
  the gun is the one in hand.
- Untested: whether the item card and the gun's line refresh after the mod
  goes on while the Pip-Boy is open. A save made before this build already ran
  the quest's `OnQuestInit`, so it never hands over the lists; every gun then
  says "One type only". Start a new game.

<a id="pipboy-lines"></a>**The game's link from a line to its stack** (Fallout4.exe 1.11.240,
disassembled 2026-10-23; the `.text` section is not encrypted):
- The line builder (RVA 0xB433C0; unnamed in the exe) is called once per line
  (from 0xB42C30). Its arguments: the `BGSInventoryItem`, one of its stacks,
  the line's `PipboyObject`, a handle and the stack's index. It writes
  `formID`, `text`, `count`, …, `HandleID` and `StackID`. `StackID` is a
  `PipboyArray` holding that index.
  - 0xB43A80 merges a further stack into an existing line: it adds the count
    and appends the index. So a line lists every stack it shows.
  - The Pip-Boy movie gets none of `HandleID` or `StackID`. Its entry members
    were logged: `formID`, `nodeID`, … (third play-test).
- The `PipboyDataManager` pointer is the global at RVA 0x30E8AF8, set at
  0xC386BF. Its `PipboyInventoryData` sits at +0x358, built at 0xB3D4E9, with
  primary vtable 0x2544750.
- At `PipboyInventoryData` +0xF8 is a hash map from form ID to that form's
  lines. It has F4SE's `tHashSet` layout: size at +4, end marker at +0x10,
  slots at +0x20, each slot 0x18 bytes (key, value, next).
  - The value points to the head of a circular list. Each node holds next,
    prev, then a record whose first field is the line's `PipboyObject`.
- A `PipboyObject`'s ID (`PipboyValue` +0x08) is taken to be the movie's
  `nodeID`.
  - `StackID`'s array keeps its elements in a `BSTArray` at +0x18 (count at
    +0x28).
  - Each element is a `PipboyPrimitiveValue<UInt32>` with its value at +0x18.
- `pipboy.cpp` `LineStack` walks this path.
  - It first checks the vtable, so another game build falls back to the
    equipped or first stack, logged once.
  - Each match is logged as "Pip-Boy line <nodeID> of <form>: stack <n>".

**Limits:**
- Repairing a stack from a same-form spare removes "one of the item", and the
  engine picks which stack loses it.
- The hint shows on every inventory item, including ones that don't wear,
  which get no repair.
- There is no gamepad key, since every button is taken there.

<a id="entry-condition"></a>**Starting condition, built and played 2026-10-23.**
- FNV authors an inventory entry's condition as a COED after its CNTO
  (containers, NPCs, creatures) or LVLO (leveled lists). The export leaves it
  out.
- `spike/entry_condition.py` reads it from FalloutNV.esm, per record and entry.
  Containers, leveled items and NPC carried items now write FO4's COED (same
  layout: owner, global or rank, condition) after each entry that has one.
- NPCs' worn armor goes into an outfit (OTFT), which has no COED, so it starts
  whole.
- The region build: 682 entries carry a COED (678 leveled-list entries,
  3 NPC, 1 container), from 15% to 75%, median 45%. FO4Edit reports 0 errors.
- Played 2026-10-23: many NPCs' weapons came at 100%. FNV's data is there:
  in FalloutNV.esm, 1,039 of 1,146 weapon entries in leveled lists have a
  COED. In the build, all 159 NPCs with weapons reach them through entries
  with one (127 for every weapon, 32 for some).
- The game drops it for weapons. The spawn routine (0x271570) applies an
  entry's COED only when the item has a maximum health. That comes from
  0x316940, by form type: armor (0x1D) reads its own DATA health, ammo (0x2C)
  its charge at +0x168, anything else a health component, which weapons
  lack. So a weapon reports 0.
- Fixed in the plugin: its one call there (0x271611) is redirected through
  F4SE's branch trampoline, and a weapon answers 1. Vanilla puts COED only on
  power armor entries.
- Armor got its health field from the FO4 template, sometimes 0. It now gets
  FNV's own (ARMO DATA health).
- NPCs whose inventories were rolled before this build keep what they have.

<a id="transfer-menu"></a>**Transfer and barter menus (built and played 2026-10-23).** These had no
CND (played).
- `containermenu.swf` (`ContainerMenu`, which `BarterMenu` extends) shows the
  highlighted line's `ItemCardInfoList` on `ItemCard_mc`. Its lists are
  `ContainerList_mc` and `PlayerInventory_mc.PlayerList_mc`.
- The game builds each Flash line with slot 28 of the menu's vtable:
  `ContainerMenu` 0x103E690, `BarterMenu` 0xA4B500 (pure in
  `ContainerMenuBase`).
  - Its arguments: the menu, the owner's handle, the game's line record and
    the Flash line.
  - The record is an `InventoryInterface` handle, resolved by 0x347C10 on the
    singleton at 0x30EC470, then the line's stack indices (count at +8;
    inline at +0x10 when negative, else a pointer there).
- `transfer.cpp` replaces both slots. After the original, it stamps the line
  with `fnvCND`, the condition of its first stack.
- A native `enterFrame` listener on each opened menu keeps a CND line at the
  stamped value on the card, for the line whose `ItemCardInfoList` the card
  shows. The CND drawer is shared with the Pip-Boy (`ShowLine`).
- Played 2026-10-23: the hook never attached ("neither root nor root.Menu_mc
  has its item card"), because `HasMember` does not see a display object's
  named child clips. It now reads `<base>.ItemCard_mc` by path, as the
  Pip-Boy hook does, and logs the root's members if that fails too.
- Played again: still not found. The transfer menu's root holds only `f4se`
  and `FilterHolder_mc`, so the menu sits under it. The hook now tries
  `root.FilterHolder_mc.Menu_mc` and `root.FilterHolder_mc` first, and logs
  the holder's members otherwise. Played: it shows CND.

<a id="jury-rigging"></a>**Jury Rigging, built and played 2026-10-23.** FNV's perk (entry point
48, Has Jury Rigging) lets an item be repaired with "a roughly similar item".
FalloutNV.exe's "can this spare repair that item" test (0x47BB50, GOG build):
1. The same item: yes.
2. The item's repair list contains the spare (0x47BAC0, 0x47BA80): yes.
3. With entry point 48 above 0: both of one form type, the spare not
   persistent or a quest item (vtable +0x94), and then:
   - weapons (form type 0x28): the spare playable (Flags 1 bit 0x80 clear,
     +0x100), with the same weapon animation type (+0xF4, DNAM 0) and the
     same skill (+0x15C, DNAM 104);
   - armor (0x18): the spare playable (biped general flags bit 0x40 clear),
     with the same weight class (heavy, bit 0x80: 1; medium, 0x08: 2; else 0)
     and the same equipment type (ETYP, +0x154).

Ours:
- `condition.jury_groups` reads each item's group from FalloutNV.esm.
- The player alias carries them (`JuryGroups`, parallel to the repair lists)
  and the converted perk (`JuryRigging`).
- The plugin offers a spare of the same group while the player has the perk.
- The quest-item test is not carried over.

<a id="jams"></a>**Reload jams, built 2026-10-23, played briefly (needs longer play).**
- FNV jams on reload (FalloutNV.exe 0x92B9E0, roll at 0x4DFF00). The
  condition index is i = ceil(percent / 10), minus 1 when above 1. The chance
  is `fWeaponConditionReloadJam[i]`, whose exe defaults (FalloutNV.esm sets
  none) are 1, 0.75, 0.5, 0.25, 0.1, then 0.
  - So a weapon at 0% always jams, up to 20% 75%, then 50%, 25% and 10%,
    and above 50% never.
  - Weapons with "No Jam After Reload" (DNAM Flags 2 bit 0x4, 17 weapons)
    never jam.
  - The jam lasts the weapon's Jam Time (DNAM offset 96).
  - Firing jams are in FNV's tables, but every value is 0.
- Fallout 4 has no jam animation, idle or sound. AWC's jam (on firing):
  - a hand-interrupt idle (`1stPRightInterrupt`, `RaiderRightInterrupt` in
    third person) and the dry-fire sound twice;
  - then a forced reload idle (`1stPReloadNonLM`, `RaiderReload`), with
    the magazine capacity set to the rounds left so the reload is allowed.
- Ours jams the reload itself, as FNV does. On `reloadStateEnter` it rolls
  FNV's chance for the equipped weapon (`JamTimes`, `JamChances`). On a
  jam:
  - the hand-interrupt idle stops the reload;
  - the dry-fire sound plays, with a "jammed" notice;
  - after the weapon's Jam Time, the reload idle plays the reload again,
    and that one is not rolled.
  - The interrupted reload never added rounds, so no capacity change is
    needed.

<a id="vendor-repair"></a>**Vendor repair, built 2026-10-23 (unplayed: no repairer in the built region).**
- **FNV's rule** (FalloutNV.exe 0x648230, called per item by
  `RepairServicesMenu` at 0x7B7920):
  - The vendor reaches `fRepairSkillBase + (fRepairSkillMax -
    fRepairSkillBase) x Repair / 100` tenths of condition. FalloutNV.esm sets
    those to 4 and 10 (the exe's defaults are 4 and 9), so the vendor reaches
    40% plus 0.6% per Repair point.
  - The price is `fItemRepairCostMult` (2 in the ESM, 1 in the exe) x the
    item's value x the tenths gained / 10.
  - A price of 0.5 or less means the vendor can't help. Any other price is
    rounded, with a minimum of 1 cap.
  - The Repair skill is the repairer's: the speaker,
    `SatoREF.ShowRepairMenu`'s Sato, or the player in
    `player.showrepairmenu`.
- **The repairers' skills.** FNV keeps an NPC's skills in its NPC record:
  14 values, then 14 offsets, in skill order from Barter. A skill is value
  plus offset, at most 100. The export leaves these out, so
  `fo4_import/spike/npc_skills.py` reads them from FalloutNV.esm. Each
  converted NPC carries them as actor values in its own list (PRPS), or in
  its stats template's. The 10 repairers are:

  | Repairer | Repair |
  |---|---|
  | Sato (Paladin) | 100 |
  | Major Knight | 100 |
  | Raul | 90 |
  | Mick | 75 |
  | Old Lady Gibson | 65 |
  | Calamity | 60 |
  | Samuel | 40 |
  | Barton | 30 |

  Raul's skills are auto-calculated in FNV, so his stored 90 is the
  Creation Kit's last calculation.
- **In game.** `ShowRepairMenu` converts to
  `F3NV_ConditionCalls.ShowRepairMenu(<repairer>)`, which sets the vendor
  (`F3NV_Condition.SetVendor`) and shows a notice to open the Pip-Boy.
  - It first opened the Pip-Boy itself with F4SE's `UI.OpenMenu`. Played
    2026-10-23 from the console: that opens the menu without raising the
    Pip-Boy, and input locks (Tab does nothing). The player opens it now.
  - Untested in play beyond that: none of the 10 repairers are in the built
    region. Test with the larger world.
- **On the Pip-Boy** (`vendor.cpp`, `pipboy.cpp`), until it closes, G (or
  the REPAIR hint) on an item shows the vendor's offer on the item card:
  - the vendor's name and Repair skill;
  - CND before > after;
  - the price, and the caps you carry;
  - "ENTER) REPAIR", or "NOT ENOUGH CAPS".

  Enter sends the repair to Papyrus, which calls `PipboyRepair`. That pays
  the caps through the engine's remove-from-stack, then writes the stack's
  health. An item the vendor can't improve says "Beyond the vendor's skill"
  (or "Not needed" when it's whole).
- **Found on the way:** the converter's undeclared-owner check
  (`pipeline._comment_dangling`) only knew the top-level static scripts. It
  had been commenting out every statement call to a Fallout 4 static
  script: 130 `AddItemHealthPercent` calls, 6 `ModWeaponHealthPerc` and 1
  `SetWeaponHealthPerc`. `STATIC_SCRIPT_CLASSES` now walks each target's
  folder, and none are commented out.

<a id="npc-wear"></a>**NPC weapons don't wear in FNV.** Both of FalloutNV.exe's
weapon wear sites call the per-shot wear (0x646260, `fDamageToWeaponValue`)
only after the attacker's `IsPlayerRef` (vtable 0xD8, named in xNVSE's
`GameObjects.h`):
- 0x524A28, a melee hit;
- 0x9B55C4, the hit data of a shot.

An NPC's weapon keeps the condition it spawned with (its entry's COED,
[#entry-condition](#entry-condition)), so there is nothing to build.

Next: none for condition. The plugin also draws the Pip-Boy's SKILLS,
REPUTATION, KARMA and CHALLENGES tabs ([fo4_pipboy_tabs.md](fo4_pipboy_tabs.md)), which
replaced Pip-Boy Tabs.

## <a id="drift"></a>Expected drift

- Repair is a list on the Pip-Boy's item card (G), not FNV's own repair screen.
- FO4 has no jam animation of its own; a jam is an interrupt idle plus dry
  fire, as AWC does it.
- Copies of an item stack only while their condition matches; a change
  splits one copy off through the engine's stack writer ([stack
  writer](#stack-writer)). FNV keeps one condition per item.
- A melee weapon wears per swing, not per hit. (Only the player's weapons wear, as
  in FNV: [#npc-wear](#npc-wear).)
- Condition shows as a CND line on the Pip-Boy, transfer and barter item cards, and as a notification on equip.
- Vendor repair is offered item by item on the Pip-Boy's item card, not in
  FNV's list with Repair All. The caps leave the player but don't go to the
  vendor (FO4 vendors keep caps in their own container).
