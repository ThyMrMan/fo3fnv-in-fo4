# Open FO4 frameworks and tools on GitHub: who covers what (research, 2026-11-11)

Status: a survey, nothing built. Status lives in [ROADMAP.md](../ROADMAP.md).
Licenses come from the GitHub API, plus a check of the repository root
when the API says none. "none" = no license field and no LICENSE/COPYING
file. **(inf)** = taken from a README or inferred, not checked. Stars and
dates are from 2026-11-11 and go stale fast.

**Why.** Our [strategy](../spin_offs.md#strategy) is open, drop-in
replacements for unlicensed frameworks. Before building one, find who
already covers the area openly (reuse or contribute instead) and where
nobody is working. Under [our license rules](../spin_offs.md#license),
GPL-3.0, MIT, BSD, Apache and MPL-2.0 code is reusable with credit; code
with no license is for reading only.

## <a id="summary"></a>Summary

- **The live open hub is the Dear-Modding-FO4 organization:**
  `commonlibf4`, `Addictol` (engine fixes + crash logger) and
  `DearModdingUI` (shared ImGui menu host), all GPL-3.0 with an
  `EXCEPTIONS` file, the same terms as ours. All pushed today; one DLL for
  OG 1.10.163, NG 1.10.984 and AE 1.11.240.
- **Our CommonLibF4 base was the wrong line.** `LucaDotGit/CommonLibF4`
  (MIT) was last pushed 2026-05-15. `Dear-Modding-FO4/commonlibf4` is 454
  commits ahead of `libxse/commonlibf4` and 0 behind. Compared and
  switched the same day ([CommonLibF4 forks](commonlibf4_forks.md)).
- **Our own plan's targets are confirmed open gaps:** no open dialogue
  menu, no Scaleform HUD widget framework, no Pip-Boy tab framework, no
  open Scaleform MCM.
- **Nobody, for any Creation Engine game, has an in-game test harness.**
- **CK-only bakes with no open replacement:** FaceGen, precombines and
  previs, navmesh, LOD, and Havok ragdolls and skeleton mappers.
- **The best new find for our pipeline:** `Kalmarv/havok-formats`
  (GPL-3.0, Rust), which reads `hk_2014` packfiles and writes them back
  byte for byte ([Havok](#havok)).

## <a id="commonlib"></a>CommonLibF4, F4SE and engine fixes

| Repo | What | License | Last push | Verdict |
|---|---|---|---|---|
| Dear-Modding-FO4/commonlibf4 | Fork of libxse, 454 ahead / 0 behind; OG+NG+AE in one DLL | GPL-3.0 + EXCEPTIONS | 2026-11-11 | **Our base** ([why](commonlibf4_forks.md)) |
| libxse/commonlibf4 | Shared upstream (shad0wshayd3's redirects here) | GPL-3.0 + exceptions | 2026-09-23 | Contribute |
| LucaDotGit/CommonLibF4 | "AV" fork, our base until 2026-11-11 | MIT | 2026-05-15 | Replaced by Dear-Modding |
| alandtse/CommonLibF4 | Multi-runtime incl. VR | MIT | 2026-11-08 | Reference for VR later |
| ianpatt/f4se | F4SE | none (README terms) | 2026-09-06 | Read-only, alive |
| Dear-Modding-FO4/Addictol | Engine fixes + crash logger | GPL-3.0 + EXCEPTIONS | 2026-11-11 | Contribute |
| shad0wshayd3-FO4/Baka* (about 15) | Small fixes and features | GPL-3.0 | 2026-09 | Reuse |
| AntoniX35/High-FPS-Physics-Fix | HFPF | MIT | 2026-01-04 | Reuse |
| perchik71/X-Cell-FO4 | Optimizations | GPL-3.0 | archived 2026-01 | Reuse |

Buffout 4 NG's source isn't on GitHub (inf).

## <a id="ui"></a>UI and menus

| Repo | What | License | Last push | Verdict |
|---|---|---|---|---|
| Dear-Modding-FO4/DearModdingUI (+API) | Shared ImGui settings and overlay host, versioned C ABI; an `mcm/` bridge shows existing MCM `config.json` menus | GPL-3.0 | 2026-11-11 | Build on it for ImGui needs; no third host |
| DeisDev/Menu-Helper | Main/pause menu entries, settings pages and dialogs on vanilla Scaleform panels; C++, Papyrus or JSON | GPL-3.0 | 2026-11-09 | Contribute; closest to a Scaleform MCM. 1.11.240 only (inf) |
| DCCStudios/F4SEMenuFramework | Port of SKSE Menu Framework 3 (GPL upstream); can stand in for MCM's Papyrus API | none | 2026-09-07 | Read-only; same authors as the [OAR port](fo4_oar_port.md) |
| wushen233/ItemIntegrationFramework | Shared item-card injection, with AS3 for FallUI's card | GPL-3.0 | 2026-10-13 | Contribute; an open Extra-Item-Info piece |
| wushen233/Fallout4WheelMenu-Native | CommonLibF4 backend for an unlicensed wheel menu | GPL-3.0 | 2026-08-20 | Reuse |
| DCCStudios/F4-PIP-OS, shad0wshayd3-FO4/BakaFullscreenPipboy | Fullscreen Pip-Boy | MIT / GPL-3.0 | 2026-09 | Reuse as references |
| ReynnSolaris/quest-log-sorter | Grouped quest log in the Pip-Boy (AS3 + F4SE) | GPL-3.0 | 2026-11-02 | Reference for Pip-Boy injection |
| Scrivener07/FO4_Games, FO4_Overlays | Custom AS3 menus and HUD overlays from Papyrus | MIT | 2022 / 2019 | Ideas |
| reg2k/f4mcm, reg2k/xdi, reg2k/hudframework | MCM, XDI, HUDFramework (README only) | none | 2024 / 2020 / 2017 | Read-only |
| Kraken-collab/xdi | reg2k's XDI history (first commit reg2k, 2017-10-11) with an MIT LICENSE "Copyright 2026 Kraken" added | MIT claimed | 2026-08-27 | **Treat as unlicensed**: reg2k never granted it |
| F4CF/Interface | Decompiled vanilla interface AS3 | NOASSERTION | 2023-12 | Read-only; Bethesda-derived |

**Nothing open and active:** a dialogue menu, a Scaleform HUD widget
framework, a Pip-Boy tab/page API, a full inventory UI (FallUI/DEF_UI
class), a flat-PC control-map remapping framework, an open AS3 component
library, and any UI framework that lists FO4VR.

## <a id="runtime"></a>Runtime frameworks

| Repo | What | License | Last push | Verdict |
|---|---|---|---|---|
| shad0wshayd3-FO4/BakaFramework | Papyrus/native framework | GPL-3.0 + EXCEPTIONS | 2026-09-22 | Contribute; the live open extender |
| GELUXRUM/LighthousePapyrusExtender | Papyrus extender | GPL-3.0 | 2024-02-01 | Reuse or fork; frozen |
| powerof3/SPID-F4, powerof3/BaseObjectSwapperF4 | SPID and BOS ports | none | 2025-11 | Read-only, frozen |
| alandtse/SPID-F4 | Fork of SPID-F4 labelled MIT | MIT claimed | 2026-11-08 | **Treat as unlicensed** (parent has none) |
| WirelessLan/TullPatcherF4 | Record patcher | none | 2026-11-08 | Read-only, active |
| SilentlyGayming/PerkConditionsFrameworkF4 | Custom perk conditions | MIT | 2026-09-30 | Reuse; overlaps our condition functions |
| wushen233/ConditionSystemFramework, WeaponRequirementsFramework | Durability, weapon requirements | GPL-3.0 | 2026-10 | Watch: overlaps FNV's condition and Strength requirements |
| expired6978/F4SEPlugins | Holds f4ee (LooksMenu) source | none | 2026-06-05 | Read-only; nobody may continue it |
| ReidenXerx/fo4-silhouette, fo4-complexion | Body distribution, skin overlays | GPL-3.0 | 2026-11 | Watch; early |
| 80x08/DynamicRagdollSystem-F4 | Hit and death reactions | GPL-3.0 | 2026-11-11 | Watch |
| passed111/Subgraph-Accelerator--F4SE | Animation subgraph caching | MIT | 2026-08 | Reuse |
| qudix/f4se-custom-camera, DCCStudios/F4-FPCameraOverhaul | Cameras | GPL-3.0 / MIT | 2026-09 | Reuse |
| kinggath/WorkshopFramework | Workshop scripts | none | 2026-10-02 | Read-only, active |
| Monitor221hz/Pandora-Behaviour-Engine-Plus | Behavior patcher | GPL-3.0 | 2026-10-26 | Skyrim only (inf); upstream target for FO4 support |

Not on GitHub (inf): Garden of Eden PSE, RobCo Patcher, CBP for FO4,
LL_FourPlay (`Lkdb5RDr/LL_FourPlayAndTools` has no license and may not be
the real source).

**Skyrim has it open, FO4 doesn't:** per-form key/value storage
(StorageUtil/JContainers), KID, licensed SPID and BOS, CBPC/SMP body
physics, a Nemesis/Pandora behavior patcher, a RaceMenu-class morph and
overlay runtime, an open MCM, a licensed OAR ([port asked](fo4_oar_port.md#license)).

## <a id="tools"></a>Offline tools

| Area | Best open option | License | Last push | Gap |
|---|---|---|---|---|
| <a id="havok"></a>Havok `hk_2014` | **Kalmarv/havok-formats** (Rust): reads `hk_2013`/`hk_2014` packfiles, writes them back byte for byte, encodes spline animation, builds hknp collision meshes into tagfiles, reads ragdolls and constraints. Written against Sekiro and Elden Ring; FO4 files untested | GPL-3.0 | 2026-11-06 (created 10-27) | No writer for FO4 ragdolls or skeleton mappers anywhere; see [creature rig prior art](fo4_creature_rig_prior_art.md) |
| BA2 | Ryan-rsm-McKenzie/bsa (C++), northaxosky/rust-crates `btdx` (Rust, GNRL + DX10, also an ESL writer) | MIT / Apache-2.0 | 2025-02 / 2026-07 | None |
| Plugins | Mutagen (C#, FO4 read/write), esplugin (Rust), libloot | GPL-3.0 | 2026-11 | None |
| Papyrus | Caprica (compiler), joelday/papyrus-lang (LSP + debugger, FO4) | MIT | 2024-06 / 2026-11 | Caprica quiet since 2024 |
| Strings | KNY00/lib-bethesda-strings; xTranslator source | MIT / MPL-2.0 | 2023 / 2024 | No maintained cross-platform translator |
| Saves | mdfairch/FallrimTools (ReSaver, covers FO4) | Apache-2.0 | 2023-10 | Quiet |
| Materials | ousnius/Material-Editor (BGSM/BGEM spec) | MIT | 2026-05 | Windows GUI only |
| Audio | 595554963github/Xwma-Codec | GPL-3.0 | 2026-10 (created 10-27) | Unvetted, no README; otherwise only Microsoft's xWMAEncode |
| Crash logs | CLASSIC-Fallout4 (Rust port) | NOASSERTION; CC BY-NC per the agent, not confirmed | 2026-10-30 | Possibly not GPL-compatible |
| FaceGen | none for FO4 | – | – | CK only |
| Precombines/previs | Scripts that drive CK.exe (ToastPRPScript, MIT); Collective Modding Toolkit (GPL-2.0) scans but doesn't generate | – | – | CK only |
| Navmesh | IronAdamant/AgentCreationKit drives the CK GUI | MIT | 2026-10-14 | CK only |
| LOD | TES5Edit/xLODGen 2016 snapshot (no license); sheson's xLODGen is binary-only | none | 2016 | No open FO4 LOD generator |
| In-game tests | chesko256/LilacFO4 (Papyrus unit tests in game) | MIT | 2016 | **Nothing live for any Creation Engine game** |

## <a id="for-us"></a>What this means for us

1. **CommonLibF4: done.** The plan now uses the Dear-Modding fork
   ([comparison](commonlibf4_forks.md)).
2. **Keep our order** ([strategy](../spin_offs.md#strategy)): the dialogue
   menu, Pip-Boy, HUD and Scaleform MCM are real gaps. For MCM, look at
   Menu-Helper first (open, Scaleform, settings pages) before writing our own.
3. **Use DearModdingUI** for any ImGui debug or settings panel instead of
   writing a host.
4. **Try havok-formats on FO4 files.** If it round-trips our
   `hk_2014` clips, skeletons and behaviors, it may serve the creature-rig
   and collision work; it is GPL-3.0, so code reuse is allowed.
5. **Unclaimed areas worth owning:** an in-game test harness, a
   FaceGen baker, per-form storage, licensed SPID/KID/BOS
   reimplementations. The first two serve the converter directly.
6. **Watch overlaps with FNV systems:** `ConditionSystemFramework` and
   `WeaponRequirementsFramework` (wushen233) and `PerkConditionsFrameworkF4`
   touch the same ground as our condition and requirement work.
