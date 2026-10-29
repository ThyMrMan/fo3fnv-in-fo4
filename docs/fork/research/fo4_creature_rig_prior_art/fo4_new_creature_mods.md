# FO4 mods and total conversions with genuinely new creatures (rigs, graphs, animation sets)

Research date: 2026-10-25. Method: web search plus fetches. **Nexus Mods pages, Nexus forums, the Nexus wiki, falloutck.uesp.net and nma-fallout.com all returned HTTP 403 to the fetch tool.** Facts attributed to those pages come from search-engine snippets, not from reading the full page. Treat them as "snippet-confirmed" and re-read the pages by hand before relying on exact wording.

Classification legend used below:
- **A**: vanilla rig and graph unchanged (new mesh or texture only)
- **B**: vanilla rig with new animations
- **C**: modified vanilla graph
- **D**: fully custom skeleton, ragdoll and graph

## Large projects: which new creatures each has and how they were built

### Takeaway
Only the GrilledTurkey / HcG x Grill / TheFriedturkey group (Capital Wasteland, Mojave creature mods, Project Mojave) has public claims of **custom skeletons with full new animation sets** (category D). The F4NV team said in about 2021–22 that creature animation had been "nearly impossible" until IceStormNG's tooling. Fallout: London has many new creatures, but I found no public statement on how they were rigged. Miami, Cascadia, Vault 13, Sim Settlements, The Frontier, Outcasts and Remnants, and Tales from the Commonwealth turned up no creature-rig information.

### Cited Findings

**GrilledTurkey group (HcG x Grill, TheFriedturkey; also C411um13 and MrColonelMustard on Project Mojave)**
- Mojave Geckos (Nexus 50275): described as a fully custom creature remaking New Vegas's geckos, with "a brand new custom skeleton, artwork and ... recreated animations". The credits list separate Havok ragdoll work. Page age points to about 2021. Category D (claimed). — [Nexus 50275 (search snippet)](https://www.nexusmods.com/fallout4/mods/50275)
- A separate Mojave Geckos listing (Nexus 50284, by JonySnowball) also exists. Its snippet only says it brings New Vegas geckos to the Commonwealth. Do not confuse the two. — [Nexus 50284 (search snippet)](https://www.nexusmods.com/fallout4/mods/50284)
- Capital Wasteland Centaurs (Nexus 59379): the listing claims a "custom skeleton" and a "Full new animation set to go along with the skeleton". Category D (claimed). — [Nexus 59379 (search snippet)](https://www.nexusmods.com/fallout4/mods/59379)
- Institute Centaurs (Nexus 49219, an earlier release by the same team): a centaur based on scrapped FO4 concept art, "with custom animations, a brand new sculpt and a spit attack". Credits: TheFriedturkey for 3D models, textures and rigging; HcG x Grill for scripting and implementation. Listed as the fourth release on their roadmap. The snippet does not say whether the skeleton is custom. — [Nexus 49219 (search snippet)](https://www.nexusmods.com/fallout4/mods/49219); [PwrDown list](https://www.pwrdown.com/gaming/top-10-best-fallout-4-animal-creature-mods-for-xbox-one/)
- Mojave Cazadores (Nexus 57161): five variants described as "fully animated" in TheGamer's article of 2022-01-08. The article does not say whether the rig is custom or a reused stingwing or bloatfly rig. — [TheGamer](https://www.thegamer.com/mojave-cazadores-mod-fallout-4-new-vegas/); [Nexus 57161](https://www.nexusmods.com/fallout4/mods/57161)
- Capital Wasteland Yao Guai (Nexus 58290): credits are TheFriedturkey for models, textures and rigging, and HcG x Grill for implementation, rigging and scripting. The snippet does not say whether it uses a custom skeleton or the vanilla yao guai skeleton. — [Nexus 58290 (search snippet)](https://www.nexusmods.com/fallout4/mods/58290)
- Other packs from the same group: Capital Wasteland Robot Pack (52147) and DC and West Coast Supermutants (49680). I found no rig details for either. — [Nexus 52147](https://www.nexusmods.com/fallout4/mods/52147); [Nexus 49680](https://www.nexusmods.com/fallout4/mods/49680)
- Project Mojave entered early access around 2021-10-24 with "10 custom creatures, of which 3 are brand new ones". The creatures were not named. — [DSOGaming, 2021-10-24](https://www.dsogaming.com/mods/fallout-4-project-mojave-mod-is-now-available-in-early-access/)
- A third-party replacer mod swaps vanilla creatures for Capital Wasteland versions (e.g. "Capital Wasteland Radscorpion by GrilledTurkey"). It notes that the author has retired the source mods and that the replacer relies on unpacked archive files. — [Nexus 76900 (search snippet)](https://www.nexusmods.com/fallout4/mods/76900)

**Fallout 4: New Vegas (F4NV)**
- A 2021–2022 F4NV dev update called creatures one of the great challenges of FO4 modding over the previous six years. It said the way creature animation data is built made new creature animations close to impossible, and that this "changed very recently". It credits IceStormNG's programming and writing, with backing from VelvetGoat and help from The Reclamationists. I could not open the original post, so this comes from search summaries of a Reddit mirror and an NMA repost. Dates are given as January 2022 in one source and about 2021 in another. — [NMA thread p.2 (403; search summary)](https://www.nma-fallout.com/threads/fallout-4-new-vegas.216599/page-2); [r/OfficialF4NV mirror (search summary)](https://nyc1.lr.ggtyler.dev/r/OfficialF4NV/top)
- I found no source naming specific F4NV creatures such as cazadors or nightstalkers, or how each was rigged.

**Fallout: London (released July 2024)**
- The wiki creature list has 33 entries. Apparently new: Gehenna, Thamesfolk, Lymer, Mittenlurk, Radger, Womble, Sleipnir, Lamprey Floater, Thameshound, Hellhound, Dryad, Famished, Pig Rat, Ladybird, Radshrew, Rad Rabbit, Aberration, Corgi, House Cat, Fox, Squirrel, Peacock and others. The page gives no build notes. Its image filenames hint at vanilla bases, e.g. "Mirelurk fo4.png" on Mittenlurk, but these are only leads. — [Fallout Wiki: FOLON creatures](https://fallout.wiki/wiki/Mod:Fallout_London/Creatures)
- Gehenna: one creature artist (oscarfoncu, a Voxel School student) describes it as "one of the creatures I made for the Fallout London Project". It was sculpted in ZBrush, retopologised in 3ds Max, textured in Substance Painter and rendered in Marmoset. Nothing is said about rigging or animation. — [The Rookies entry](https://www.therookies.co/entries/16109)
- The Gehenna and Thamesfolk were revealed in a 2021 progress video; the Thamesfolk were described as Lovecraft-inspired. — [NME, 2021](https://www.nme.com/news/fallout-london-reveals-cthulhu-inspired-monsters-new-music-and-more-2982061)
- Inverse's review says new creatures have new attack patterns, animations and mannerisms. This is a reviewer's impression, not a technical claim. — [Inverse review](https://www.inverse.com/gaming/fallout-london-review)

**Fallout: Miami**
- Press shows the Snapjaw (a "deathclaw crocodile") and the Mingo (from a 2020 trailer), and mentions a bipedal alligator. Nothing on rigs. A standalone episode, Miami Misadventures, credits animator MaxG3D. — [PCGamesN trailer](https://www.pcgamesn.com/fallout-miami/new-trailer); [PCPer 2020](https://pcper.com/2020/09/fallout-miami-ghouls-in-hawaiian-shirts-never-looked-so-good/); [Nexus 58073](https://www.nexusmods.com/fallout4/mods/58073)
- Inference only: "deathclaw crocodile" suggests, but does not show, that the Snapjaw reuses the deathclaw rig.

**Fallout: Cascadia**
- A GameStar preview says the lead developer presented new monster types. No details were found. — [GameStar video](https://www.gamestar.de/videos/fallout-cascadia-ein-echtes-neues-singleplayer-fallout,96930.html); [PCGamesN](https://www.pcgamesn.com/fallout-cascadia/fan-game-update)

**Standalone and other**
- Mutant Menagerie (StamperDoesMods; article dated 2023-08-29) claims more than 60 mutant creatures and 24 world bosses. The article says nothing about rigs. Given the count, it is probably mostly category A or B, but that is unverified. — [Gfinity](https://www.gfinityesports.com/article/fallout-4-mod-mutant-menagerie-creatures-world-bosses)
- Deathwing (deathclaw–stingwing hybrid) and Enhanced Creatures AI Overhaul (a Glowing Deathclaw race whose behavior changes are done in script) are vanilla-rig work. — [Nexus 78179 (search snippet)](https://www.nexusmods.com/fallout4/mods/78179)
- Wasteland Creatures Redone is a retexture compilation (category A). — [Nexus 7951](https://www.nexusmods.com/fallout4/mods/7951/)

### Inferences
- The GrilledTurkey group is the clearest public FO4 example of category D creatures: custom skeleton, new animation set and custom ragdoll. Their releases cluster around 2021–2022, the same window in which F4NV said IceStormNG's tooling made new creature animation feasible. That matches the timing, but I found no source linking the two.
- GrilledTurkey assets have been retired or removed from distribution, as the third-party replacer mod notes. Reusing them would need explicit permission. The user's memory file already lists permission terms for these mods as "to confirm".

### Gaps
- Fallout: London, Miami, Cascadia, Vault 13, Sim Settlements, The Frontier, Outcasts and Remnants, and Tales from the Commonwealth: no public technical statements found on creature rigs or graphs.
- Exact Nexus permissions text and dev time for any of the GrilledTurkey creatures; the pages could not be fetched.
- No reported problems (crashes, ragdoll, foot sliding) were retrievable from Nexus posts tabs, because of the 403s.

## Tooling, difficulty statements, blockers and workarounds

### Takeaway
The documented FO4 pipeline uses Havok Content Tools 2014 plus the Havok Animation Tool, which modders must find themselves. On top of that sit IceStormNG's new-creature tutorial and tools (Nexus 56676), ck-cmd style FBX→HKX conversion, regenerating AnimTextData from the CK, and more recently Behavior Graph Studio (a beta node editor for FO4 behavior HKX). The usual approach is a donor creature's behavior graph: the further a new creature's skeleton departs from the donor's, the more graph editing it needs.

### Cited Findings
- IceStormNG's "Tutorial and tools for adding in new creatures" (Nexus 56676): documentation and tools written by IceStormNG, commissioned by VelvetGoat and uploaded by TaeHyojin. It is aimed at advanced users and requires the Havok Animation Tool and Havok Content Tools. The page says that because of distribution restrictions on old Havok suites, users must find the Havok Animation Tool on their own. — [Nexus 56676 (search snippet)](https://www.nexusmods.com/fallout4/mods/56676/)
- IceStormNG also co-authored HKXPack and supplied animal behavior edits for Animal Posing Framework. — [Nexus 59341 (search snippet)](https://www.nexusmods.com/fallout4/mods/59341)
- The custom-creature guide (Beyond Skyrim Arcane University, mirrored in falloutck search results) recommends treating an existing creature as a donor whose behavior graph is the template. It says that the more the skeleton and animations differ from the donor's, the more behavior editing is needed later. It describes exporting the skinned mesh, the skeleton with collision, and each animation as FBX, then using ck-cmd `importskin`, `importrig` and `retargetcreature` to build a Havok project. **This guide originates in Skyrim, so it is a Skyrim precedent.** — [AU: Implementation of Custom Animations](https://wiki.beyondskyrim.org/wiki/Arcane_University:Implementation_of_Custom_Animations)
- The FO4 CK wiki has a Subgraphs page describing FO4's per-race and per-keyword animation subgraph system. I could not read the content (403). — [falloutck.uesp.net/wiki/Subgraphs](https://falloutck.uesp.net/wiki/Subgraphs)
- Behavior Graph Studio (Nexus 107691, by NomadsReach; HKX packer by DexesTTP): a beta visual node editor for FO4 behavior, character and project HKX files, for Windows and Linux. It edits in place, makes `.bak` backups, and its author claims it was tested against all 531 vanilla behavior graphs. — [Nexus 107691 (search snippet)](https://www.nexusmods.com/fallout4/mods/107691)
- Fallout 4 Animation Kit (F4AK) by ShadeAnimator: 3ds Max rig and Havok export kit. — [GitHub](https://github.com/ShadeAnimator/ShadeAnimator_Fallout4_AnimationKit); [Nexus 16694](https://www.nexusmods.com/fallout4/mods/16694?tab=docs)
- A custom-animation tutorial uses 3ds Max, F4AK and Havok Content Tools 2014. — [Nexus 41209 (search snippet)](https://www.nexusmods.com/fallout4/mods/41209)
- Nexus wiki: to work with a new skeleton, you must first convert it to 32-bit. — [Animation In Fallout 4 (search snippet)](https://wiki.nexusmods.com/index.php/Animation_In_Fallout_4)
- AnimTextData is regenerated with `CreationKit.exe -GenerateAnimInfo:MYPLUGIN.esp`; one commenter says the batch version fails on the next-gen CK. Missing or stale AnimTextData breaks a mod's animations, and folder ACL permissions caused one startup crash. — [Nexus forum: AnimTextData crashes](https://forums.nexusmods.com/topic/6668066-animtextdata-crashes-my-game/); [Nexus 18238 posts](https://www.nexusmods.com/fallout4/mods/18238?tab=posts)
- Reported problems:
  - A modder could not get a custom creature mesh working with the Protectron's animations. — [Nexus forum 13466964](https://forums.nexusmods.com/topic/13466964-need-help-with-rigging-creatures)
  - A race mod notes that a custom skeleton used for the player race crashes the game unless it is in the CharacterAssets folder. — [Nexus 26135 (search snippet)](https://www.nexusmods.com/fallout4/mods/26135)
  - A 2023-era forum question about animating custom creatures got only advice on meat caps. — [Nexus forum 13461133](https://forums.nexusmods.com/topic/13461133-hi-does-anyone-know-how-to-animate-custom-creatures-for-fallout-4-and-how-to-make-meat-caps)
  - Molerats and radscorpions "teleporting" is a known vanilla behavior issue, fixed by adding a race keyword. — [Nexus 12997](https://www.nexusmods.com/fallout4/mods/12997)
- Blender rig resource (Nexus 82537): a Blender rig plus Havok settings and skeletons for Havok tools. Its permissions forbid conversion to other games and require asking the author before reusing assets. — [Nexus 82537 (search snippet)](https://www.nexusmods.com/fallout4/mods/82537)

### Inferences
- The main blocker was creature animation data. The F4NV team's account, that it was "nearly impossible until IceStormNG", fits the legal unavailability of the Havok Animation Tool and the lack of a behavior editor before Behavior Graph Studio.
- Workarounds seen: donor graphs, retargeting onto a vanilla skeleton, script-driven behavior instead of graph edits, and regenerating AnimTextData.

### Gaps
- I found no first-person account of how long a full custom FO4 creature took.
- I found no public modder statement specifically about building ragdolls (as opposed to just crediting them).
- The contents of the IceStormNG tutorial (which donor graphs it uses, and how it handles AnimTextData) could not be read.

## Bethesda pipeline hints (DLC and Creation Club creatures)

### Takeaway
I found no sourced technical statements. Press coverage of the Far Harbor creatures (anglers, gulpers, fog crawlers, hermit crabs) describes gameplay only.

### Cited Findings
- Far Harbor's new creatures: anglers (a lure, absorbing fog and spitting it), gulpers (fast, charging and sliding, ambushing from trees), fog crawlers (large, with pincers) and hermit crabs. These are gameplay descriptions only. — [Siliconera](https://www.siliconera.com/surviving-encounters-fallout-4s-far-harbor-monsters/); [Twinfinite](https://twinfinite.net/guides/fallout-4-far-harbor-every-new-enemy/)
- Behind-the-scenes Far Harbor coverage exists but did not discuss rigs. — [TheSixthAxis](https://www.thesixthaxis.com/2016/05/18/peak-behind-the-scenes-of-fallout-4s-far-harbor-expansion/)

### Inferences
- These have not been checked against game data. I believe the Far Harbor creatures ship with their own skeletons and behavior projects, and that Nuka-World's gatorclaw reuses the deathclaw rig. Verify by listing `Meshes\Actors\*` and `*Project.hkx` in the DLC BA2s rather than citing this as fact.

### Gaps
- Bethesda creature-pipeline interviews: none found.
- Creation Club creatures: none researched or confirmed.
- Whether the CK's behavior features (subgraph data on RACE, AnimTextData generation) were officially documented for creatures: not confirmed, because the CK wiki pages could not be fetched.
