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
  - The condition mod is swapped as a tenth is crossed.
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

Next:
- Armor (wear by damage taken, DT/DR curve).
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
