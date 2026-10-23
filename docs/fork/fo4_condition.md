# Item condition on Fallout 4

**Status:** planned 2026-10-22, not built. The decision is in
[drift](fo4_drift.md#candidates) (Item condition: build, our own, with
F4SE). Mods read for method: [Armor and Weapon Condition](research/fo4_target.md#awc)
and [NV Ammo Crafting](research/fo4_target.md#nv-ammo).

Fallout 4 keeps no condition on weapons or armor, except power armor. This plan rebuilds FNV's condition
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
  set an item's health. Whether the engine keeps and shows health on a
  weapon is untested.
- **F4SE Papyrus:** `InstanceData` reads and sets an instance's damage,
  damage types, magazine size, armor rating and health, weight, value and
  keywords. Its owner is a weapon or armor form, or an actor plus an
  equip slot. `GetAllMods`, `AttachModToInventoryItem` and
  `GetInventoryItems` work on inventories. `UI.Get` reads menu values.
- **Native plugins:** F4SE 0.7.9 with its source, and the Address Library
  covers 1.11.240 (the installed runtime). Hydra and Addictol are F4SE
  plugins already running on it.

## <a id="options"></a>Two ways to build it

**A. Scripts on items (AWC's method), F4SE Papyrus only.** A script on every
converted weapon and armor base keeps a float per copy. Each change
attaches one of up to 101 condition object mods to that copy, which carries
the damage or DT multiplier. Wear comes from the holder's animation events
(`weaponFire`, `HitFrame`, `reloadStateEnter`).
- For: proven in play (AWC 2.0.2), no compiled code.
- Against: every scripted item is its own persistent reference. FNV
  places thousands of weapons and armor in NPCs and containers, which
  means save size and script load. Each weapon needs an attach point for
  the condition mod, and the condition mod competes with the weapon-mods
  work for the same instance. Display is a name suffix.

**B. Our own F4SE plugin on the engine's item health.** Condition lives in
the item's own health extra data, the one power armor uses. The engine
saves it, COED gives NPC gear its starting condition, and
`GetItemHealthPercent` lets records test it.
- The plugin wears the equipped item on firing and hits.
- It scales damage and DT, through perk entry points conditioned on item
  health if those read it, else in a damage hook.
- It rolls reload jams and exposes Papyrus natives for repair, kits and
  FNV's script calls.
- For: no per-item scripts, native saves, FNV's COED data used as is, and
  maybe the Pip-Boy's own condition bar.
- Against: compiled code to build and keep up with runtime updates. Three
  engine behaviors are untested (below).

**Proposal: B, decided by a spike.** B is the native mechanism and scales
to the whole Mojave; A stays the fallback if the spike fails.

## <a id="spike"></a>Spike: does the engine keep weapon health?

A small test plugin, one question per play-test:

1. A leveled list hands the player a weapon with COED condition 0.5. Does
   the item keep it (`GetItemHealthPercent` on the dropped reference), and
   does the Pip-Boy show a condition bar?
2. A perk with Mod Weapon Damage ×0.5, conditioned on
   `GetItemHealthPercent` < 0.75: does the weapon hit for less?
3. A minimal F4SE plugin built for 1.11.240 reads and writes the equipped
   weapon's health. Does it persist across a save and load?

Built 2026-10-22, not played. The files are in `temp/condition_spike/` (gitignored), installed as the
MO2 mod `Condition Spike`:
- `make_esp.py` writes `ConditionSpike.esp`: lists `CondSpike_Pistol50` and `CondSpike_LeatherTorso50`,
  and the perk `CondSpike_DamagePerk`.
- `plugin.cpp` and `build.bat` make `ConditionSpike.dll`. It is a standalone F4SE plugin with F4SE 0.7.9's
  1.11.240 addresses, so it runs on that runtime only.
- On each save load the plugin logs every carried weapon and armor's health to
  `My Games\Fallout4\F4SE\ConditionSpike.log`. It then multiplies the equipped weapon's health by 0.6,
  or gives it health 0.4 when it has none.

If 1 and 3 pass, B goes ahead; if 2 fails, B scales damage with a hook.
If 1 fails, the engine drops health off weapons and A is built instead.

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

## <a id="plan"></a>Build steps (B)

1. **Plugin groundwork:** an F4SE plugin project beside `tes_runtime/`
   (the Skyrim DLL's build setup), on CommonLibF4 or F4SE's own headers,
   with the Address Library. It ships in the generated mod folder.
2. **Records:**
   - Read WEAP and ARMO health and REPL from FalloutNV.esm, and stamp each
     converted item with its max health and repair list (a keyword or a
     form-list lookup the plugin reads).
   - Convert COED Item Condition on NPC, leveled-list and container
     entries, which `npcs.py` drops today.
3. **Wear:** per shot, `fDamageToWeaponValue` × the ammo's effect × the
   perk multiplier, over the item's max health. Melee wears per hit and
   armor per absorbed hit. Non-playable items don't wear, and an item
   breaks at 0 (unequipped, unusable until repaired).
4. **Effects:** FNV's damage curve and DT/DR curve, the reload jam table
   (jam idle and dry fire, skipped on No Jam After Reload weapons) and
   value × h^1.5.
5. **Repair:**
   - Repair kits through FNV's own script (a native for
     Get/SetWeaponHealthPerc).
   - Repair from a same-type item (REPL, or any same class with Jury
     Rigging), using FNV's formula.
   - Vendor repair for the 10 `ShowRepairMenu` lines, with FNV's cap and cost.
   - The menu is the open design question: a message-box list first, our
     own Pip-Boy page later.
6. **Scripts:** `AddItemHealthPercent`, `Get/Set/ModWeaponHealthPerc`
   and `ShowRepairMenu` convert to the plugin's natives.
7. **Display:** the Pip-Boy's bar if the spike shows one, else a line on
   the item card.

## <a id="built"></a>Weapons, built 2026-10-22

**Played 2026-10-22:** equipping shows the condition, firing wears it down, and
the Repair Weapon hotkey repairs it from a spare pistol. The first build looped
equip/unequip: `AttachModToInventoryItem` re-equips the weapon, so the
re-equip saw a stale tier and attached again. The script now records the tier
it attached per weapon before attaching, and a whole weapon gets no mod.
Untested: a weapon breaking at 0, wear perks, and ammo with a condition effect.

- **The plugin** (`tes_runtime/fo4_condition`, `FalloutCondition.dll`) adds
  four natives to `TES4_Condition`:
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
  - The quest `FNV_Condition`, whose player alias runs `TES4_ConditionPlayer`.
  - FNV's repair lists as FLSTs, and the Repair Weapon hotkey item.
  - The DLL is copied into the mod's `F4SE\Plugins`.
- **Wear** (`TES4_ConditionPlayer`, the player only):
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
- **FNV's commands** convert to `TES4_ConditionCalls`: `GetWeaponHealthPerc`,
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

## <a id="armor"></a>Armor, built 2026-10-22 (not yet played)

- **Records** (`condition.py`, `wire_armor`):
  - Every converted armor with FNV health (ARMO DATA, read from
    FalloutNV.esm) takes the same attach point and keyword as weapons.
  - Vanilla armor mods never multiply Rating: Fallout4.esm's 271 Rating
    properties are all integer adds. So armor tiers subtract, and there is
    one set per distinct armor rating: `FNV_mod_ArmorCondition<tier>_DT<r>`
    below 50%, where FNV's curve takes `r × (0.5 − h)` off. Tiers from 50%
    up change only the value and are shared by every rating.
- **Wear** (`TES4_ConditionPlayer.OnHit`, the player only):
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

Not yet played.

<a id="repair-choice"></a>Asked for: choose what gets repaired, and show condition in the Pip-Boy.
FNV repairs the item highlighted in the Pip-Boy. Built with no new mod: the
FalloutCondition plugin (`pipboy.cpp`) works inside FO4's own Pip-Boy movie.

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
  that wear (`TES4_Condition.Track`), and its stack (see the third play-test).
  - It keeps a `CND` line at the stack's condition in the card's `InfoObj`,
    and redraws the card (`onDataChange`) when it adds or changes the line.
  - The game's refill drops the line, and the next frame adds it back.
  - It logs the members of the first entry it reads to `FalloutCondition.log`.
    The game may give an inventory handle that would replace matching by name.
- On keyboard and mouse (`uiPlatform` 0), it adds a REPAIR hint (G) to the
  inventory page's `buttonHintDataV`, once per page, and rebuilds the hint bar. Clicking the
  hint sends the F4SE external event `FNVConditionRepair`.
- Natives: `PipboySelection` and `PipboyStack` (the highlighted item),
  `PipboyRefresh` (show the new value after a repair), and
  `GetStackHealth` and `SetStackHealth`.

**Papyrus:** `TES4_ConditionPlayer` tracks the items, registers G
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
  are logged. Not yet played.

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

Not yet played.

<a id="repair-list"></a>**The repair list (built 2026-10-23; played the same day: it repairs).** FNV's repair menu
lists every spare with its condition bar, previews the gain and shows the
Repair skill (asked for with a screenshot). Ours:
- G or the REPAIR hint on an item that wears opens a list on the item card.
  - First the Repair skill.
  - Then up to six spares: the item's other unequipped stacks, another copy
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
  - The Repair hotkey calls the same native: `TES4_ConditionCalls.RepairWithSpare`
    → `TES4_Condition.RepairWith`, on the worst copy of the first spare item.
  - `TrackRepair` gives the plugin the repair lists and the Repair skill.
- Played: the fade dimmed the card too, so G looked like a pop-up that never
  came. While the list is open, the card is now lifted above the fade
  (`setChildIndex` to the top, put back on close). A whole item says "REPAIR
  Not needed", not "No spare". Not yet played.
- Untested: removal skips `RemoveItem`'s own work, so no `OnItemRemoved` and
  no HUD line. Equipped stacks are never offered as spares.

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

Next:
- Jams.
- Vendor repair (`ShowRepairMenu`) and Jury Rigging.
- NPC weapons' wear.
- FNV's per-entry starting condition (COED) on NPCs, leveled lists and
  containers.
- A Pip-Boy display.

## <a id="drift"></a>Expected drift

- Repair happens in a menu of our own, not FNV's Pip-Boy repair screen.
- FO4 has no jam animation of its own; a jam is an interrupt idle plus dry
  fire, as AWC does it.
- Copies of a weapon in one inventory stack share one condition (FNV kept
  one per item).
- Only the player's weapons wear; a melee weapon wears per swing, not per hit.
- Condition shows as a notification on equip and repair, not in the Pip-Boy.
