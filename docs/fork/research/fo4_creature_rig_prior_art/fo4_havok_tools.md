# Fallout 4 Havok 2014 (hk_2014.1.0-r1, 64-bit) creature tooling inventory

Research date: 2026-10-25. Nexus pages were read in a browser (WebFetch is blocked with 403 there); GitHub data came from the GitHub API (`gh api`). "Pushed" means the date of the last push to the repository.

## 1. Behaviour Graph Studio (BGS): what it reads and writes, its class tables, round-trip guarantees, CLI and library use, licence, gaps, activity

### Takeaway
BGS is the most capable open FO4 Havok codebase found. It is MIT-licensed C#/.NET 8 with its own native packfile reader and writer and needs no Havok SDK. It reads all five FO4 behaviour-stack file types (behaviour, character, project, skeleton, animation) and edits them in place byte-exactly. It cannot write ragdoll physics or skeleton mappers. It refuses bone-index changes in a skeleton that also holds physics or mapper data. Its scripting surface is a headless scanner, a large developer CLI (`symrm`) and an MCP server. There is no documented library API. It is very new (created 2026-08) and still beta.

### Cited Findings
**Identity, licence, platform, activity**
- Repository G-A-R-D-E-N/BGS: C#, licence MIT, created 2026-08-11, last push 2026-10-22, 6 stars, about 25 commits. Releases: v1.0.5 (2026-08-15) and v1.1.0 (2026-09-15). Version 1.3.0 is synced on main (the commit "sync: prepare Behaviour Graph Studio 1.3.0" is dated 2026-10-01) — [GitHub API, repos/G-A-R-D-E-N/BGS](https://github.com/G-A-R-D-E-N/BGS)
- Nexus mod 107691 "Behavior Graph Studio - Havok Tooling", by NomadsReach. Version 1.3.0, uploaded 2026-08-04, updated 2026-10-01. Labelled "BETA RELEASE"; licence given as "Free / Open Source"; the page credits "Core HKX packer by DexesTTP" — [Nexus 107691](https://www.nexusmods.com/fallout4/mods/107691)
- Platforms are Windows x64 and Linux x64. The UI uses Avalonia. Building needs the .NET 8 SDK. It needs "No separate Havok tools, Java runtime, game SDK" — [README](https://github.com/G-A-R-D-E-N/BGS/blob/main/README.md)
- The Nexus description still says a JRE is needed "for edits that add, remove or rename". The GitHub THIRD_PARTY_NOTICES says the hkxpack executable and Java integration "are retired and are not included in this repository, application builds, or releases". The Nexus text therefore lags the current code — [Nexus 107691](https://www.nexusmods.com/fallout4/mods/107691) vs [THIRD_PARTY_NOTICES.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/THIRD_PARTY_NOTICES.md)

**What it reads and writes**
- It opens FO4 behaviour, character, project, skeleton and animation `.hkx` files. It can read vanilla files directly from `.ba2` archives, read-only. Editable items: "values, names, symbols, bindings, states, transitions, generators, and arrays". It also previews animation on a skeleton or skinned mesh, compares two graphs, and checks a graph or project for broken references — [README](https://github.com/G-A-R-D-E-N/BGS/blob/main/README.md)
- Write model, per the Nexus description:
  - A value edit is written in place, and "every other byte of the file is left exactly as it shipped".
  - Structural edits (add, remove, rename) rebuild the file, and they "are still refused on files holding compressed animation".
  - Author's test: "15,320 animation files rebuilt, all byte for byte identical", including 856 spline-compressed files.
  - Coverage: 531 vanilla behaviour graphs, with every one of 5,329 states resolved to its generator.
  - Caveat from the author: "proven against the files themselves, which is not the same as the game accepting the result."
  — [Nexus 107691](https://www.nexusmods.com/fallout4/mods/107691)
- Save safety: the original is kept as a `.bak`. An edit that cannot be written safely makes the app refuse to save and leaves the source unchanged. Unsupported layouts, classes and conversion paths "fail closed. BGS does not write guessed data" — [README](https://github.com/G-A-R-D-E-N/BGS/blob/main/README.md)
- Source files cover the following:
  - packfile layout, fixups and conversion: `PackfileConverter.cs`, `PackfileLayout.cs`, `FixupOrder.cs`
  - spline decode, encode and fit: `HkxBinaryReader.Spline.cs`, `SplineEncoder.cs`, `SplineFit.cs`
  - root motion: `RootMotion.cs`
  - skeleton authoring and mirroring: `SkeletonAuthoring.cs`, `SkeletonMirror.cs`
  - skeleton mappers: `SkeletonMapperReader.cs`, `SkeletonMapperAuthor.cs`
  - physics extraction and ragdoll simulation: `HavokPhysicsExtractor.cs`, `RagdollSimulation*.cs`
  - Havok 2015 tagfile reading: `TagfileImage.cs`
  - FO4 NIF skin weights: `src/Nif/*`
  — [repo tree via GitHub API](https://github.com/G-A-R-D-E-N/BGS/tree/main/src/Hkx)
- In 1.3.0, skeleton authoring covers bone names, reference transforms, translation locks, reparenting, and validated save and reopen. "Standalone skeletons support bone addition/removal and reordering. Dependent rigs refuse edits that need animation, mapper or physics index remapping." NIF skin-weight saving targets FO4 BSVersion 130 and writes only the weight and index slots — [RELEASE-NOTES.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/RELEASE-NOTES.md); [guide/rig-authoring.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/guide/rig-authoring.md)
- Havok 2015.1.0 tagfiles (Fallout 76) are readable for evidence, and "Havok 2018 support is incomplete" — [havok-tagfiles.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/docs/havok-tagfiles.md)

**The HavokClassTypes.json class tables**
- `src/Hkx/HavokClassTypes.json` declares `"havokVersion":"hk_2014.1.0-r1"`. Its embedded note says:
  - member types, which members are serialised, inline-struct classes and enum values "come from published class-description metadata (MIT…)";
  - "The instance sizes come from HavokClassLayouts.json, which was read out of Fallout 4 itself";
  - defaults "come from the game's own class registrations".
  Entries carry parent, signature and size, for example `BGSGamebryoSequenceGenerator` with parent `hkbGenerator`, signature `0x4e708fb6`, size 184 — [HavokClassTypes.json](https://github.com/G-A-R-D-E-N/BGS/blob/main/src/Hkx/HavokClassTypes.json)
- "`src/Hkx/HavokClassTypes.json` is derived from hkxpack's published class-description metadata and carries the same licence" (MIT, Copyright (c) 2016 DexesTTP). BehaviourClasses.json shares the same measurement provenance — [THIRD_PARTY_NOTICES.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/THIRD_PARTY_NOTICES.md)
- Other bundled licences: Avalonia (MIT) and BepuPhysics 2.4.0 (Apache-2.0, used for the physics preview). The notice also states that nothing in the repository "is derived from their [Bethesda's] code or ships their assets" — [THIRD_PARTY_NOTICES.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/THIRD_PARTY_NOTICES.md)

**CLI and automation surface**
- The app runs headless with `--scan-archives`, `--scan-modlist` and `--scan-clips`, each returning exit code 0, 1 or 2 and accepting `--json`. These modes only scan; they do not author anything — [README](https://github.com/G-A-R-D-E-N/BGS/blob/main/README.md)
- `symrm` is a developer CLI ("primarily a developer/reverse-engineering tool") with about 60 commands. Examples:
  - archives and inspection: `ba2`, `extract`, `packfile`, `skeleton`, `spline`, `splinestats`, `motion`
  - round-trip and layout checks: `nullsave` (no-op save plus byte comparison), `convert` (32↔64-bit pointer layout), `compare`, `classcheck`, `defaults`
  - edit-and-verify passes: `savespline`, `editframe`, `trim`, `retime`, `delete`, `paste`, `template`, `conditions`, `savedelete`
  - FO4 AnimTextData subgraph hashes: `hash`, `crash`
  - behaviour simulation: `run`
  — [guide/cli/symrm.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/guide/cli/symrm.md)
- The repository also contains an MCP server (`tools/mcp/BehaviourGraph.Mcp.csproj`, `McpTools.cs`) and an AI-assistant bridge in the app — [repo tree](https://github.com/G-A-R-D-E-N/BGS/tree/main/tools/mcp)

**Stated gaps (README, release notes, docs, open issues)**
- "Skeleton-mapper serialization/write-back and chain-mapper authoring are not complete… automatic bone pairing is not proven" — [README](https://github.com/G-A-R-D-E-N/BGS/blob/main/README.md)
- `SkeletonMapperAuthor`:
  - computes SimpleMapping rows as `inverse(modelSpace_A[boneA]) * modelSpace_B[boneB]` in model space. Checked against the 18 rows of each vanilla human mapper, the worst error was about 4e-5;
  - refuses reference scale outside 1e-3;
  - does not derive pairs from bone names (the caller must supply the pairing);
  - does not create chain mappings;
  - "Writing the rows back into a packfile is not implemented."
  The doc also reports "Fallout 4 performs no validation at load time" on mappers — [skeleton-mapping-authoring.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/docs/skeleton-mapping-authoring.md)
- Ragdoll: it is a "read-only engineering preview… It does not add HKX authoring, serialized physics edits, body-to-body collision, or a production Havok solver." In 1.3.0, the physics settings stay in the preview window and "do not write HKX physics data". Compound and mesh hull geometry are refused — [ragdoll-preview-engineering.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/docs/ragdoll-preview-engineering.md); [guide/rig-authoring.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/guide/rig-authoring.md)
- Open issues (snapshot 2026-10-25):
  - #60 "Write hknp ragdoll physics to skeleton.hkx"
  - #61 "Write the skeleton mapper back to skeleton.hkx"
  - #63 "Import animation from glTF and FBX"
  - #65 "Export imported animation to a game-ready HKX"
  - #53 "Decode hkaQuantizedAnimation and hkaPredictiveCompressedAnimation"
  - #52 "Collect community custom skeleton and HCT export fixtures"
  - #28 "Build the full character/race authoring workspace"
  - #13 "Build Ragdoll Studio"
  — [GitHub issues](https://github.com/G-A-R-D-E-N/BGS/issues)

### Inferences
- BGS's class table (hk_2014.1.0-r1 member descriptions plus sizes measured from FO4) and its spline encoder are the most reusable assets for a Python pipeline. MIT permits porting them, keeping the hkxpack/DexesTTP notice.
- Today BGS cannot produce a new creature's ragdoll or mappers. It can, however, add bones to a standalone skeleton.hkx, which is a skeleton-only file with no physics.
- Driving it from Python means shelling out to `symrm`, the scan modes or the MCP server, or calling the .NET assembly through pythonnet. None of these is a documented stable API.

### Gaps
- No public report found of BGS being used to author a new creature graph that worked in game.
- Whether BGS can create a new behaviour, character or project file from scratch (rather than editing or templating an existing one) is not stated.

## 2. Other tools: what each reads and writes, maturity, licence, platform, scriptability

### Takeaway
Two families of open tools handle FO4 hk_2014 binaries without the Havok SDK:
- the hkxpack line (Java, HKX↔TagXML, which includes behaviours and skeletons);
- PyNifly's native Python readers and writers (spline animation, skeleton-only hkx, and hknp collision inside NIFs).

Everything else is either Skyrim hk_2010 only (hkxcmd, ck-cmd, HKX2, hkxconv, Pandora, Nemesis, blender-hkx) or depends on Havok Content Tools (HCT) 2014, which is proprietary, unobtainable officially and not redistributable.

### Cited Findings
**hkxpack (Dexesttp)**
- "made to be used with the hk_2014.1.0-r1 file format, commonly used in Fallout 4". Converts HKX↔TagXML (the hkxcmd XML style). CLI is `java -jar hkxpack-cli.jar unpack|pack <file|dir>`, with `-o`, `-t` (threads) and `-d` options. Needs Java 8. Licence MIT. Known bug: some cloth data nodes come out partly missing. The classXML files "are obtained from the Fallout 4 game… they're not included in the sources" — [hkxpack README](https://github.com/Dexesttp/hkxpack)
- Last release v0.1.6-beta on 2020-11-11; the one before that was 0.1.5 in 2016-11. 74 stars. Open issues include requests for Havok 2015 and Skyrim SE support (2023–2024). Effectively dormant — [GitHub API](https://github.com/Dexesttp/hkxpack/releases)
- BGS's author explains why the rebuild path was moved away from XML: with an unpack/repack, "anything the text form cannot carry perfectly is lost… why animation files could only be opened read only" — [Nexus 107691](https://www.nexusmods.com/fallout4/mods/107691)
- hkxanim (Dexesttp): "HKX animation creator for Fallout 4" (FBX→HKX). No licence stated; last push 2016-07-15. Stale — [GitHub](https://github.com/Dexesttp/hkxanim)

**HKXPack Plus (Alfred-DMB)**
- A heavily modified MIT fork of hkxpack, created 2026-08-05. Main changes:
  - "908 Havok class definitions bundled" (the original makes users extract them from the game);
  - `verify` and `quick` commands;
  - PS4 layout support;
  - a fat JAR.
  It needs no Havok SDK. Also listed on Nexus 107755 as "(PC-PS4) HKX unpacker and packer NO SDK", "tested in fallout 4 and elden ring" — [GitHub](https://github.com/Alfred-DMB/HkxPack-Plus); [Nexus 107755](https://www.nexusmods.com/fallout4/mods/107755)
- Used by F4-PS4-AnimationPorter (Nexus 107715) — [Nexus 107715](https://www.nexusmods.com/fallout4/mods/107715)

**havok-ps4-pipeline (DevNvll)**
- MIT, standard-library Python, created 2026-08. Converts FO4 PC behaviour HKX (hk_2014.1.0-r1, packfile version 11, layout `08 01 00 01`) to the PS4 layout. "does not convert animation, character, project, or skeleton HKX files". Small, but useful as a Python packfile reference — [GitHub](https://github.com/DevNvll/havok-ps4-pipeline)

**PyNifly (BadDogSkyrim)**
- GPL-3.0 Blender add-on, very active: V29.1.0 released 2026-10-04, last push 2026-10-26, 323 stars. FO4 features: "Direct import/export to hkx files for FO4, SE, and LE, and exports hkx skeletons for Skyrim and FO4". Also exports FO4 native physics collision inside NIFs — [PyNifly README](https://github.com/BadDogSkyrim/PyNifly)
- HKX animation import and export is done "natively in Python -- no external tools like hkxcmd are required". FO4 (64-bit) is supported for both. Annotations round-trip as pose markers. Other Havok versions cannot be imported — [ANIMATIONS.md](https://github.com/BadDogSkyrim/PyNifly/blob/main/ANIMATIONS.md)
- `io_scene_nifly/hkx/anim_fo4.py`:
  - `write_fo4_animation` writes `hkaSplineCompressedAnimation` with extractedMotion pointing to `hkaDefaultAnimatedReferenceFrame`;
  - `write_fo4_skeleton` writes a skeleton-only file (hkRootLevelContainer → hkaAnimationContainer → hkaSkeleton, plus an empty hkMemoryResourceContainer);
  - spline decompression is credited as "Based on spline decompression from Dagobaking's skyrim-fo4-animation-conversion".
  — [anim_fo4.py](https://github.com/BadDogSkyrim/PyNifly/blob/main/io_scene_nifly/hkx/anim_fo4.py)
- FO4 skeleton format doc:
  - covers all 8 vanilla skeletons, with hkaSkeleton signature `0xFEC1CEDB` and 7 arrays (one extra `partitions` array);
  - `localFrames` and `partitions` are "not preserved";
  - hkxcmd support for FO4 is "None (64-bit only)";
  - the doc describes only skeleton-only files, with no ragdoll, mapper or hknp content.
  — [hkx_skeleton_format_fo4.md](https://github.com/BadDogSkyrim/PyNifly/blob/main/docs/hkx_skeleton_format_fo4.md)
- A separate doc covers the hknp packfile embedded in NIF `bhkPhysicsSystem` blocks: hknpPhysicsSystemData plus ConvexPolytope, CompressedMesh, Sphere and DynamicCompound shapes — [fo4_havok_packfile_format.md](https://github.com/BadDogSkyrim/PyNifly/blob/main/docs/fo4_havok_packfile_format.md)

**Skyrim-only tools (hk_2010; precedent only)**
- hkxcmd (figment): built on the Havok 2010.2.0 SDK, converting HKX to XML or KF. Licence NOASSERTION; last push 2017-08. Per PyNifly, it reads 32-bit LE files only and has no FO4 support — [hkxcmd](https://github.com/figment/hkxcmd); [PyNifly doc](https://github.com/BadDogSkyrim/PyNifly/blob/main/docs/hkx_skeleton_format_fo4.md)
- ck-cmd (aerisarn): GPL-3.0 C++, last push 2025-01-27. Made for Skywind and TES games. No FO4, Fallout or 2014 references appear in the README or file tree (searched via the GitHub API). Treat it as Skyrim-only — [ck-cmd](https://github.com/aerisarn/ck-cmd)
- HKX2Library and hkxconv (ret2end): MIT C#, last pushed 2023-01. "pack and unpack hkx for skyrim se"; a fork of Katalash's HKX2 (from DSMapStudio) — [HKX2Library](https://github.com/ret2end/HKX2Library); [hkxconv](https://github.com/ret2end/hkxconv)
- Pandora Behaviour Engine+: GPL-3.0, "for Skyrim Special Edition", very active (pushed 2026-10-25) — [GitHub](https://github.com/Monitor221hz/Pandora-Behaviour-Engine-Plus)
- Nemesis: GPL-3.0, Skyrim, pushed 2026-02 — [GitHub](https://github.com/ShikyoKira/Project-New-Reign---Nemesis-Main)
- No FO4 support was found for any of these Skyrim tools.
- jgernandt/blender-hkx: MIT, for Skyrim animations, and it requires building against a Havok SDK that cannot be redistributed — [GitHub](https://github.com/jgernandt/blender-hkx)

**Havok Content Tools 2014 and the proprietary chain**
- FO4 animation authoring has historically meant 3ds Max 2013–2015 + HCT 2014 64-bit + niftools. HCT's basic version "was actually available for free from the official site. Until Microsoft bought them… they officially allow those people, who still have them, to keep using them… redistribution is not allowed by the license". Blender "does not have HCT plugin". Dated 2016 — [F4AK docs, Nexus 16694](https://www.nexusmods.com/fallout4/mods/16694?tab=docs)
- F4AK is by ShadeAnimator, not Dexesttp. It bundles 3ds Max scenes, HCT presets and rig files, the HKXPack GUI and the niftools plugin. Last updated 2016-08-27. The GitHub kit repo is MAXScript with no licence (pushed 2020) — [Nexus 16694](https://www.nexusmods.com/fallout4/mods/16694?tab=docs); [GitHub](https://github.com/ShadeAnimator/ShadeAnimator_Fallout4_AnimationKit)
- An HCT workflow tutorial (2020) needs `HavokContentTools_2014-1-0_20140830_64Bit_PcXs.exe`. Animations are taken 64-bit → 32-bit HKX (HCT "ConvertAnimation_x32") → FBX (HKXPack GUI) → 3ds Max. Rig `.txt` files define the HCT skeleton export — [Nexus 41209](https://www.nexusmods.com/fallout4/mods/41209)
- Blender route (Nexus 82537, updated 2026-09-17): Blender 4.1 + HCT 2014 64-bit (v1.0 or v1.1) + Autodesk FBX Converter + PyNifly. Credits andrelo1's FBXImporter and Highflex's havok2fbx (BSD-3, 2015) — [Nexus 82537](https://www.nexusmods.com/fallout4/mods/82537); [havok2fbx](https://github.com/Highflex/havok2fbx); [fbximporter](https://github.com/andrelo1/fbximporter)
- IceStormNG's "New Creature Behavior and Implementation Tutorial" (Nexus 56676, 2021-12-17): "Requires Havok Animation Tool and Havok Content Tools". It warns that "Due to copyright/distribution restrictions on old havok suites, you'll have to search for the Havok Animation Tool on your own" — [Nexus 56676](https://www.nexusmods.com/fallout4/mods/56676)

**Bethesda CK tools**
- Elric processes model and texture files "into a more optimized form". No source says it handles HKX authoring — [CK wiki: Elric](https://falloutck.uesp.net/wiki/Elric)
- AnimTextData is generated by the Creation Kit. Subgraphs (SubGraphAdditive) attach animation paths without editing the graph — [CK wiki: Subgraphs](https://falloutck.uesp.net/wiki/Subgraphs); [Nexus forum](https://forums.nexusmods.com/topic/7747383-fixing-third-person-animation-bugs/page/3)
- BGS's `symrm hash` and `crash` compute and resolve FO4 AnimTextData subgraph ids — [symrm.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/guide/cli/symrm.md)

**Outfit Studio/BodySlide and NifSkope**
- BodySlide/Outfit Studio: GPL-3.0, active (pushed 2026-10-25). It handles NIFs. No HKX skeleton, behaviour or animation authoring was found in its description; nifly is the NIF layer PyNifly builds on — [GitHub](https://github.com/ousnius/BodySlide-and-Outfit-Studio)
- NifSkope: last push 2024-06 — [GitHub](https://github.com/niftools/nifskope)

### Inferences
- For an automated Python pipeline, the usable open pieces are:
  - PyNifly's `anim_fo4.py` writers (spline animation with root motion; skeleton-only hkx), which are GPL-3.0;
  - hkxpack or HKXPack Plus as a Java subprocess for HKX↔XML of behaviour, character and project files, which is MIT;
  - BGS's C# native writer and class tables, also MIT.
- None of them writes hknpRagdollData, constraints or hkaSkeletonMapper into skeleton.hkx. That remains the unfilled gap. The ragdoll can come only from HCT (proprietary) or from reusing or modifying vanilla data.
- The "classxml from the game" in hkxpack/HKXPack Plus is game-derived reflection data. Redistributing those bundled files carries more legal risk than the MIT code itself.

### Gaps
- The following tools from the brief were not found as distinct projects. Each may be a misnomer or a Discord-only tool:
  - "HavokBehaviorPostProcess": no documentation found;
  - "FO4 Havok Behavior Tool": not found;
  - "hkxtool": a Nexus commenter mentions it as an annotation editor, without a source;
  - "HKX2E": no GitHub repository found.
- Dagobaking's "skyrim-fo4-animation-conversion" repository could not be located; it is known only from PyNifly's credit line.
- The Havok Animation Tool (HAT) and the HCT "Preview Tool" exist only inside the proprietary suites. No licensing statement from Microsoft or Havok was found beyond F4AK's 2016 account.

## 3. Which tools have produced a working custom FO4 creature (skeleton + ragdoll + graph)

### Takeaway
The only confirmed fully custom FO4 creature found, Mojave Cazadores (2022), was made with proprietary tools: 3ds Max 2013 with "Bethesda official exporter" (HCT) and the Creation Kit. No open-source tool has been reported to produce a working custom creature ragdoll.

### Cited Findings
- Mojave Cazadores (Nexus 57161), by HcGxGrill and TheFriedturkey (GrilledTurkey), uploaded 2022-01-07:
  - claims "a fully custom new creature" with "Full new animations and skeleton";
  - credits HcG x Grill for "Behaviours, Skeleton and Havok Ragdoll";
  - tools: "3ds max 2013, with Bethesda official exporter… Creation Kit (All done with official tools)".
  — [Nexus 57161](https://www.nexusmods.com/fallout4/mods/57161)
- The IceStormNG tutorial (commissioned by VelvetGoat for The Reclamationists, 2021) documents new-creature behaviour implementation. It depends on the Havok Animation Tool plus HCT — [Nexus 56676](https://www.nexusmods.com/fallout4/mods/56676)
- BGS's own open issue #52 asks to "Collect community custom skeleton and HCT export fixtures", which implies the author has no open-tool custom rigs to test against — [GitHub issues](https://github.com/G-A-R-D-E-N/BGS/issues)

### Inferences
- The proven route today is HCT 2014 (plus HAT for graphs) under 3ds Max. Open tools can at most produce animations (PyNifly), skeleton-only hkx (PyNifly, BGS) and edited behaviour graphs (BGS, hkxpack).

### Gaps
- Other GrilledTurkey or Capital Wasteland creature ports probably used the same pipeline, but this was not checked page by page.
- No author post was found describing a ragdoll built without HCT.

## 4. Licensing: what can be reused in an open-source converter

### Takeaway
MIT: BGS, hkxpack, HKXPack Plus, havok-ps4-pipeline, HKX2Library and hkxconv.
GPL-3.0: PyNifly, ck-cmd, Pandora, Nemesis and BodySlide.
BSD-3: havok2fbx.
Proprietary and not redistributable: the Havok SDK, HCT 2014 and HAT. The Bethesda exporter is HCT-based.

### Cited Findings
- BGS is MIT. Its class table is MIT via hkxpack, and its sizes were measured from FO4 — [THIRD_PARTY_NOTICES.md](https://github.com/G-A-R-D-E-N/BGS/blob/main/THIRD_PARTY_NOTICES.md)
- hkxpack is MIT, and its class XML was deliberately not shipped "to prevent possible legal issues" — [hkxpack README](https://github.com/Dexesttp/hkxpack)
- HKXPack Plus is MIT, but bundles 908 class definitions — [GitHub](https://github.com/Alfred-DMB/HkxPack-Plus)
- PyNifly is GPL-3.0 — [GitHub](https://github.com/BadDogSkyrim/PyNifly)
- HCT: "redistribution is not allowed by the license" (2016) — [F4AK docs](https://www.nexusmods.com/fallout4/mods/16694?tab=docs)
- Havok suites have "copyright/distribution restrictions" (2021) — [Nexus 56676](https://www.nexusmods.com/fallout4/mods/56676)
- blender-hkx needs the non-redistributable Havok SDK — [GitHub](https://github.com/jgernandt/blender-hkx)

### Inferences
- An MIT or permissive converter can port BGS or hkxpack logic freely, with attribution. Copying PyNifly's `anim_fo4.py` code would make the converter GPL-3.0. Its documentation can still be used as a format reference, and the code can be called as an external tool.

### Gaps
- No current Microsoft/Havok statement on HCT 2014 end-user licensing was found.
