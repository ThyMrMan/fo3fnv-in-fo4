# Damage Threshold reference: Zoltanite's "Modular Damage Threshold System - F4SE"

**Credit:** the hook approach our Damage Threshold work follows (FO4's
damage-resistance curve patched at its call sites, returning our own
multiplier) comes from **Zoltanite's "Modular Damage Threshold System -
F4SE"** (Nexus Fallout 4 mod 109168, `DamageThresholdRebuilt.dll`).
Credit Zoltanite as the original creator wherever this approach ships.

**Permissions** (the mod's Nexus page, read 2026-10-29): modification and
conversion allowed with credit to the original creator; asset use allowed
with credit, including in paid or donation-point mods; uploading the file
itself elsewhere is not allowed. No source is published; our code is our
own, from our disassembly of Fallout4.exe 1.11.240. We do not ship their
DLL or ini.

Findings below: analysis of the mod's files and DLL, 2026-10-29.


Mod folder: `C:\Modlists\fo3fnv-in-fo4\mods\Modular Damage Threshold System - F4SE\` (read only, nothing modified).
Nexus mod id 109168, file id 412881, Nexus file version 3.0.0.0, uploaded 2026-09-25.
Tags: **[V]** verified from files or disassembly. **[I]** inferred. **[R]** from memory, not checked.

## 1. What the mod does (description, ini, MCM)

- [V] Description: "Customizable Damage Threshold system. Configurable through MCM. Only tested on 1.11.240."
- [V] Modes (`Mode` / MCM `iMode:General`): 0 off (vanilla DR), 1 Threshold Only (DT replaces DR), 2 "New Vegas" ("Calculates Damage Resistance first, then subtracts DT"), 3 "Classic" (Fallout 1/2/Tactics: DT first, then DR). Default is 2.
- [V] **DT is not separate data.** It is derived from the target's own resistance values: "DT is calculated from scaling any armor's DR". There are no keywords, no per-armor DT field and no new actor value.
  - `Specialized=1` (default): physical threshold = physical resist × `Ratio`; energy threshold = energy resist × `Ratio`.
  - `Specialized=0`: one DT = (phys + energy) / `Divisor` × `Ratio`.
  - `Ratio` defaults to 0.20 (MCM range 0–2). `Divisor` defaults to 1.5 (range 1–2).
- [V] `Locational=1`: "armor only guards what it covers". The threshold is scaled by how much worn armor covers the body part that was hit. Body-part names in the DLL: skull, brain, chest, torso, spine, pelvis, ribcage, shoulder, clavicle, thigh, finger, left/right arm, left/right leg, whole body.
  - `Spread=0`: armor covering several parts counts its highest value everywhere. `Spread=1` divides it across the parts.
  - `MinCoverage`: share of the threshold that still applies to an unarmored part.
- [V] `MinDamage=0.2`: "Smallest part of a hit that always gets through". The ini says to set 0.20 to match FNV and 0 for the classic games.
- [V] `PowerArmorIgnoresMinDamage=1`: in power armor the floor becomes 0, so a hit can be stopped completely.
- [V] Scope: "Does not apply to radiation, poison, fire, cryo and electrical resistances." Only physical and energy damage are affected.
- [V] UI: `ShowInMenus` adds a threshold row to item cards and Pip-Boy cards. `Debug` logs every hit to `Documents\My Games\Fallout4\F4SE\DamageThresholdRebuilt.log`.
- [V] Settings file order: it reads `Data\F4SE\Plugins\DamageThresholdRebuilt.ini`, then `Data\MCM\Settings\DamageThresholdRebuilt.ini` (the second one wins). MCM is optional.
- [V] Hidden settings that exist in the DLL but are absent from the shipped ini and MCM: `ShowInVats`, `ShieldOnPlayer`, `ShieldOnTarget`, `ShieldRatio`, `ShieldCrackedRatio`, `ShieldSeconds`, `ShieldScale`, `ShieldPlayerX/Y`, `ShieldTargetX/Y`. [I] These look like an unfinished or undocumented HUD "shield" indicator plus a VATS display option.
- Runtimes:
  - [V] Load-time message: "needs the next-gen update (1.10.980 or newer)". The plugin does nothing on OG 1.10.163, even though it carries OG IDs.
  - [V] `F4SEPlugin_Version.compatibleVersions`: 1.10.980, 1.10.984, 1.11.137, 1.11.159, 1.11.169, 1.11.191, 1.11.221, 1.11.240.
- Requirements:
  - [V] F4SE.
  - [V] Address Library for F4SE Plugins. The DLL loads `Data/F4SE/Plugins/version-*.bin` (or `versionlib-*`) and SHA-512-checks the file.
  - [V] MCM, optional.
  - [V] MSVC 2015–2022 runtime (imports MSVCP140/VCRUNTIME140).
- Author and licence:
  - [V] The author field in `F4SEPlugin_Version` is empty. meta.ini has no author.
  - [V] The build path inside the DLL is `C:\Users\State\Projects\DamageThresholdRebuilt\`, so the developer's Windows user is "State". [I] This may not be the Nexus username.
  - [V] No GitHub or source link, and no permissions text, in the description or the files.
  - **Not determined:** licence and permissions. Check the mod page's Permissions tab. Until then, treat the code as not reusable. The *idea* (the hook points and the formula) is general game-engine knowledge, documented below from our own disassembly.

## 2. DLL analysis

- [V] PE64, built with **CommonLibF4** (the new commonlib-shared REX/REL layer: `lib\commonlibf4\...`, `REL::IDDB`, `REL::Trampoline`, `REL::FHookStore`) plus spdlog and fmt.
- [V] Exports: `F4SEPlugin_Version` and `F4SEPlugin_Load` only. There is no `F4SEPlugin_Query`, so this is a new-style (NG) plugin.
- [V] Version data:
  - dataVersion 1.
  - pluginVersion 0x02010020, which is 2.1.2.0 in CommonLib packing.
  - name "DamageThresholdRebuilt".
  - addressIndependence 0x6 (Address Library 1.10.980 + 1.11.137).
  - structureIndependence 0.
  - seVersionRequired 0.
- [V] Address Library: yes. Each ID is a CommonLib `RelocationID`-style triple {OG, NG, AE}, each entry `{bool, u64 id}`.
  - The runtime index picks one entry.
  - `IDDB::offset(id)` resolves it.
  - The result is added to the module base.
  - The DLL uses no hard-coded game offsets.

### Address Library IDs the DLL resolves (1.11.240 offsets from `version-1-11-240-0.bin`)

| DLL fn (RVA) | OG id | NG id | AE id | 1.11.240 RVA | use |
|---|---|---|---|---|---|
| 0x127f0 InstallCombat | 420470 | 2209007 | 2209007 | **0x6CB2E0** | **damage-resist curve (the combat hook target)** [V] |
| 0x14e10 phys hook | 967277 | 2188681 | 2188681 | 0x22D060 | handle → ref lookup, called on `HitData+0x44` (target handle) [V use, I name] |
| 0x16470 ResolveForms | 405390 | 2189587 | 2189587 | 0x263440 | `ActorValue` singleton getter [V: the exe's own resist fn calls it and compares `+0xA8` etc.] |
| 0x121b0 | 1176757 | 2219437 | 2219437 | 0x9893F0 | power-armor check (result cached per thread) [I] |
| 0x12e80 menus | 1578434 | 2225235 | = | 0xB40070 | item-card hook site [I] |
| 0x12e80 menus | 475551 | 2222625 | = | 0xA41350 | item-card row fn [I] |
| 0x12e80 menus | 489521 | 2222648 | = | 0xA45580 | item-card resist fill [I] |
| 0x12e80 menus | 54211 | 2225266 | = | 0xB43B10 | Pip-Boy card site [I] |
| 0x12e80 menus | 1191786 | 2225267 | = | 0xB44A20 | Pip-Boy row fn [I] |
| others (menu/data) | 1204430, 856221, 422985, 691815, 1573164, 343176, 254218, 507142, 548587, 1425657, 1582181, 652767 | 2268720, 2286229, 2689178, 2689189, 2267897, 2193197, 2285791, 2268729, 2689028, 2192245, 2267874, 2267872 | AE ids where they differ: 4796465, 4796476, 4471522, 4796314 | 0x167D4A0, 0x1AD6BB0, 0x30EBEC8, 0x30EBF18, 0x1659400, 0x1E02A0, 0x1AC4A60, 0x167DD20, 0x30E8930, 0x2DD800, 0x1658240, 0x1657DE0 | not identified (Scaleform/Pip-Boy/MCM/settings) |

### The damage hook [V]

**Target function:** `Fallout4.exe+0x6CB2E0` (1.11.240; 1.10.984 is +0x677690; OG is +0x65FBE0).
- Signature: `float fn(ActorValueInfo* resistAV /*rcx*/, float damage /*xmm1*/, float resist /*xmm2*/)`. It returns a multiplier.
- It checks `resistAV+0x1B0 == 4` (a resistance-type AV).
- It compares `resistAV` against `ActorValue` singleton slots `+0xA8`, `+0x2E0`, `+0x2F0`, `+0x318`, `+0x2E8`, `+0x300`, `+0x308`, …, then loads per-type curve constants.
- [I] This is FO4's curved DR formula: game settings such as fPhysicalDamageFactor and fPhysicalArmorDmgReduceExp, with Energy/Rad/… variants.
- [R] I cannot confidently recall its CommonLibF4 name. Do not rely on one.

**Hooking method:**
1. Scan the game's `.text` for every `E8 rel32` call whose target is 0x6CB2E0. In 1.11.240 there are 5:
   - `+0x9778D1` in fn `0x977650`
   - `+0xCDEC7F` and `+0xCDECC4` in fn `0xCDEB90`
   - `+0xE38C3D` in fn `0xE38A00`
   - `+0xE3AF4A` in fn `0xE3AE80`
2. Choose the sites by the bytes that follow each call:
   - **Physical:** `F3 [REX] 0F 59 /r` with mod=10, reg=xmm0 and disp32 = 0x98, i.e. `mulss xmm0,[reg+0x98]`. In 1.11.240 this is **`+0xE38C3D`**, `mulss xmm0,[r13+0x98]`, where r13 is the HitData.
   - **Energy / typed damage:** within 0x30 bytes, `mov rax,[reg+0x10]`, then within 0x20 more bytes, `addss xmm0,[rax+0xA8]` (`F3 0F 58 80 A8 00 00 00`). In 1.11.240 this is **`+0xE3AF4A`**. Here rbx is a per-damage-type context and `[rbx+0x10]` is the HitData.
   - If either pattern matches more than once, the plugin refuses ("call site is ambiguous, not hooking").
3. For each chosen site, allocate a 15-byte stub from the trampoline: `mov r9, <captured base reg>` (49/4D 89 C?), then `mov rax, hook`, then `jmp rax`.
4. `write_call<5>` the original `E8` to that stub. The hook therefore receives the original (rcx, xmm1, xmm2) plus r9 = HitData* (physical) or the context struct (energy).
5. The original function pointer is kept, and the hook calls it.

This is a call-site patch through a trampoline. It is not a detour of 0x6CB2E0 itself, so the other three callers keep vanilla behaviour.

**What FO4 does at the physical site** [V, exe disassembly of 0xE38A00]:
- `xmm1 = [HitData+0x98]` (physical damage).
- `xmm2 = resist`. This is computed just before, through `call 0x618860` with `ecx=0x25`. [I] That is the perk entry point "Mod Target Damage Resistance", so armor-penetration perks already reduce `resist`.
- `rcx = ActorValue::singleton[+0xA8]`. [I] That is DamageResist.
- After the call: `[HitData+0x98] = mult × dmg`, `[HitData+0xA4] = resisted amount`, and `[HitData+0x90]` (total) is reduced by the resisted amount.

**Typed-damage site** (0xE3AE80, [I] a per-damage-type callback):
- `rcx` = the damage type's resist AV, `xmm1` = that type's damage, `xmm2` = resist.
- The result accumulates into `HitData+0xA8`.
- The mod's energy hook (DLL 0x16EA0) acts only when `rcx` is the energy-resist AV. Any other type goes straight to the original.

**The mod's math** (DLL 0xFBA0) [V]: inputs are d = damage, r = max(0, resist), T = threshold, PA = power-armor flag. It returns a multiplier, which the game then applies to d.

```
if d <= 0: return 1
Mode 2 "New Vegas": after = Orig(av,d,r)*d - T              (FO4 curved DR first, then DT)
Mode 3 "Classic":   x = max(0, d - T); after = x>0 ? Orig(av,x,r)*x : 0
Mode 1:             after = d - T                            (no DR)
floor = (PowerArmorIgnoresMinDamage && PA) ? 0 : MinDamage*d
return clamp(max(floor, after)/d, 0, 1)
```

**How T is built** (physical hook 0x14E10) [V structure, I details]:
- Look up the target through `HitData+0x44`.
- Get the hit body area from the HitData (DLL 0x103F0).
- Get the armor coverage factor for that area (DLL 0x10E10 / 0x10FC0, "CollectCoverage" over worn armor and its biped slots).
- Specialized: `T = coverage × r × Ratio`.
- Basic: the other resist is read live from the target's ActorValueOwner (`[actor+0x58]` vtable GetValue). Then `T = (cov×r + cov2×other) / Divisor × Ratio × d / (d + otherPartDamage)`. In other words, a combined DT is shared between the physical and energy parts of the hit in proportion to their damage.

## 3. Reuse in F3NV.dll (F4SE 0.7.9, 1.11.240, hard-coded offsets)

**Feasible.** Same F4SE, same runtime.
- Hard-code:
  - `kResistCurve = 0x6CB2E0`
  - `kPhysResistCall = 0xE38C3D` (call rel32 in fn 0xE38A00, HitData in r13)
  - `kTypedResistCall = 0xE3AF4A` (fn 0xE3AE80, context in rbx, HitData at `[rbx+0x10]`)
- Before patching, verify that each site's `E8` still targets 0x6CB2E0, the same way our plugin checks other sites.
- Use F4SE's `g_branchTrampoline` / `g_localTrampoline` to emit a small stub: `mov r9, r13 ; jmp Hook` (and `mov r9, rbx` for the typed site). Then `Write5Call` the site.
- The hook returns a multiplier. For exact FNV, don't call FO4's curve:

```
dt_eff  = max(0, DT - dtReduction)      // ammo/perk DT modifiers
after   = max(d * fMinDamMultiplier(0.2), d - dt_eff)
after  *= 1 - min(DR, fMaxArmorRating 85)/100
return after / d
```

  This is the order the caller described for FNV 0x9B5A30. Note the difference: the mod's mode named "New Vegas" does DR *first* and then DT. The mod's "Classic" order matches the caller's description, but it still uses FO4's curved DR. Verify which order FNV 0x9B5A30 really uses before relying on either.

**Data the converter must supply:**
- **DT per actor.** Simplest option: keep today's mapping (FNV armor DT → FO4 armor rating), so `DamageResist` on the target already equals summed worn DT plus DamageResist modifiers. The hook then reads `resist` (xmm2) as DT directly: Ratio 1, no locational split. FNV DT is not locational.
  - Caveat [I]: xmm2 has already passed through the 0x25 perk entry point, so FO4 armor-penetration perks would reduce DT. That may be acceptable if FNV DT-ignore perks are mapped to that entry point.
- **FNV DR.** It needs its own carrier, because DamageResist now holds DT. Options: a new AVIF such as "F3NV_DR" fed by FNV DR effects (Med-X, perks, armor DR on FO3/FNV items), or a FormID table.
- **Ammo DT modifiers** (AP, HP, …; FNV ammo effects "DT add/mult"). These need per-ammo data, for example a converter-written table keyed by FO4 ammo FormID. The hook reads `HitData`'s ammo/weapon to look them up. [I] HitData weapon/ammo offsets on 1.11.240 still need finding.
- **Energy weapons.** FNV DT covers *all* damage, including energy weapons. If the converter sends FNV energy-weapon damage as FO4 energy damage, also hook the typed site, apply DT to the energy-resist type, and supply DT for energy too (FO4 `EnergyResist` = the same DT, or read DamageResist in the hook).
- **NPCs.** NPC armor DT comes through worn ARMO (armor rating). FNV NPC base DT and creature DT (e.g. deathclaw DT 15) need the NPC/creature `DamageResist` AV set from FNV data.

**Pitfalls:**
- From the mod's own text:
  - Physical and energy only. Rad, poison, fire, cryo and electrical are untouched.
  - The power-armor floor option exists, i.e. FO4 power armor needs a decision. FNV has no zero-floor rule, so for exact FNV behaviour keep the floor in power armor.
  - "Only tested on 1.11.240."
- From the disassembly:
  - [V] Only two of the five callers of the resist curve are patched. `0x977650` (+0x9778D1) and `0xCDEB90` (two calls) keep FO4's curve. [I] These are probably AI/combat damage estimates and/or a VATS or UI preview, so AI threat or VATS numbers would ignore DT. The hidden `ShowInVats` setting points the same way.
  - [I] Explosions and limb damage: the physical site writes `HitData+0x98`, and HitData totals `+0x90/+0xA4` are updated by the game. Whether explosion HitData and limb-condition damage pass through 0xE38A00 was **not verified**.
- Not found anywhere in the description, ini or DLL strings: VATS, ammo piercing, explosions, limb damage.

## Not determined
- Licence/permissions and the Nexus author name (not in the local files).
- Engine names for 0xE38A00, 0xE3AE80, 0x977650, 0xCDEB90, and most of the menu IDs.
- Exact HitData field names beyond `+0x40` aggressor handle, `+0x44` target handle, `+0x90` total, `+0x98` physical damage, `+0xA4` resisted physical, `+0xA8` typed accumulator. The offsets are verified from code; the names are inferred.
- Whether FNV 0x9B5A30 applies DT before or after DR. That is the caller's claim; I did not check it here.
