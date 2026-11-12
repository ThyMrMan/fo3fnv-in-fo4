# CommonLibF4 forks: AV against Dear-Modding (research, 2026-11-11)

Status: **decided 2026-11-11: Dear-Modding**, with the version-check fix
below; the plan is updated ([one base](../spin_offs.md#runtime)). Status lives in
[ROADMAP.md](../ROADMAP.md). Read from both repositories through the
GitHub API on 2026-11-11 (**V** = read in source, **S** = README or
search only).

**Why.** The [survey](fo4_open_landscape.md#commonlib) found our chosen
base, `LucaDotGit/CommonLibF4` ("AV"), quiet since May, while
`Dear-Modding-FO4/commonlibf4` is the most active fork and carries our
license. F3NV.dll hasn't moved off raw F4SE yet (about 40 `RelocAddr`
sites for 1.11.240 in `tes_runtime/fo4_condition/`), so switching now
costs nothing.

## <a id="table"></a>Side by side

| | AV (`LucaDotGit/CommonLibF4`) | Dear-Modding (`Dear-Modding-FO4/commonlibf4`) |
|---|---|---|
| License | MIT | GPL-3.0-or-later + modding and linking exceptions (same family as ours) |
| Lineage | alandtse's NG fork, rewritten ("Overhaul" 2026-04-26) | Fork of `libxse/commonlibf4`: 454 commits ahead, 0 behind; its `commonlib-shared` is 30 ahead / 8 behind libxse's |
| Activity | 20 commits in history (squashed), 2 contributors, 0 commits since 2026-08-01; last 2026-05-15 "Maintenance" | 1,480 commits, 24 contributors, 100+ since 2026-08-01; pushed 2026-11-11 |
| Used by (S, code search) | 17 repos incl. fo4-silhouette, PerkConditionsFrameworkF4, Mentats, F4MP | Addictol, DearModdingUI, the [OAR port](fo4_oar_port.md), F4SEMenuFramework |
| Runtimes | OG 1.10.163, NG 1.10.984, AE: any version **at or above** 1.11.191 (`InitRuntime`, `src/F4SE/Runtimes.cpp`, V) | OG 1.10.163, NG 1.10.980/984, AE 1.11.137–1.11.240 **exact list** (`REX::FModule::GetRuntimeForVersion`, V) |
| Unknown future version | Treated as AE; keeps working once Address Library ships its database | `REX::FAIL("Unsupported Fallout 4 runtime!")` then `std::terminate()` on first ID lookup |
| VR | Code path present: `RuntimeType::kVR`, `VRVariantId`, `CreateVRRuntime` (V); README sends VR developers to alandtse; untested | None |
| IDs | `RE::ID` + `Offsets.hpp`: about 1,100 entries | `RE::ID`: 1,803 `VariantID{og, ng}`; AE reuses the NG id (`REL::ID` fills missing slots with the last value) |
| Headers | 1,966 RE, 132 Scaleform, 32 F4SE; 295 `.cpp` | 1,672 RE, 130 Scaleform, 12 F4SE; 79 `.cpp` |
| Hook helpers | Own `REL/Hook*` classes (call5/6, jump5/6, vtable, IAT) | In `commonlib-shared`; plugins add MinHook (the OAR port does) |
| Build | CMake 4.3+ and vcpkg, as [our plan](../spin_offs.md#runtime) says | xmake 3; a CMake shim works (the OAR port and F4SEMenuFramework `add_subdirectory` it) |
| Extra dependency | fmt, spdlog | `DearModdingUI-API` linked publicly |

Neither fork varies struct layouts by runtime in the headers sampled
(`PipboyMenu`, `TESObjectREFR`): both assume one layout across OG, NG and AE.

## <a id="ours"></a>Coverage of what F3NV.dll calls

Name search over each fork's ID tables for the engine pieces behind our
raw addresses. Same result in both except the two camera rows:

| Ours | In both | Only Dear-Modding | Neither |
|---|---|---|---|
| Inventory | `FindAndWriteStackData`, `BGSInventoryInterface`, inventory item lookup | | `RemoveFromStack` |
| Dialogue | `MenuTopicManager`, `TESTopicInfo` responses, scene stop | Player dialogue camera, first/third-person state | Option select |
| UI | `EnableShadedBackground`, `PipboyDataManager`, container and barter menus | | |
| Combat | `GetDifficulty`, hit data | | Resist curve, max health, the combat-path setting |

So roughly half our addresses get a ready ID either way; the rest we find
ourselves (match in the 1.10.163 exe, as planned) and could send upstream.

## <a id="verdict"></a>Recommendation

**Move the plan to Dear-Modding, with one upstream change.**

- The shared core only pays off if its base keeps up with game updates
  ([strategy](../spin_offs.md#strategy)). Dear-Modding has 24 contributors
  and daily pushes; AV has one maintainer and nothing since May.
- Same license family as ours, so IDs and fixes we find go upstream and
  help Addictol, DearModdingUI and the OAR port too. It's also the base of
  the ImGui host we'd [use](fo4_open_landscape.md#for-us).
- More named IDs (1,803 against about 1,100), including two of ours AV lacks.

**The catch is the exact version list.** After a game update a
Dear-Modding DLL kills the game at load until it's rebuilt, which defeats
the reason we chose Address Library ([how it fits](../spin_offs.md#platforms)).
F4SE has to update first anyway, so the real cost is one more wait (our
rebuild). The fix is small: treat a version newer than the last known one
as that runtime, as AV does. Offer it upstream as a pull request (it may be
deliberate, since layouts can change); carry it locally if refused.

**What we give up:** AV's VR code path (untested, and VR is
[later anyway](../spin_offs.md#platforms)), and CMake as the native build
(the shim is proven by two projects).
