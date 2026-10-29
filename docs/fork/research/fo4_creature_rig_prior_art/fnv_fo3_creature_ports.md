# FNV / FO3 creatures in Fallout 4: community ports and how they solved skeleton, animation, ragdoll and behaviour

Research date: 2026-10-25. Nexus mod pages block WebFetch (HTTP 403). Mod text was read in two ways: from the built-in browser (the GrilledTurkey profile, mod lists and permission blocks) and from the public Nexus GraphQL API (`api-router.nexusmods.com/graphql`, which returns mod descriptions and collections). Dates are Nexus "original upload" dates unless marked otherwise. "e" = Nexus endorsements at research time.

Main finding: nearly all well-made FNV/FO3 creatures in FO4 come from one team, GrilledTurkey (TheFriedturkey + HcGxGrill, the "Capital Wasteland" / "Project Mojave" team). They are **scratch remakes, not ripped FNV meshes**. For creatures with no FO4 counterpart (gecko, mantis, cazador, bighorner, centaur, Securitron) the team built **new custom skeletons, Havok ragdolls, behaviour graphs and new animation sets** using 3ds Max 2013 and Bethesda's official exporter. Creatures that have an FO4 equivalent (radscorpion, yao guai, brahmin, mole rat, behemoth, super mutants, ferals) are new meshes rigged to the **vanilla FO4 rig**. Everyone else only reskins or swaps meshes on vanilla rigs: the Dogmeat rig for nightstalker, cyberdog, coyote; the Nuka-World ant; the bloatfly for floaters; Automatron robots.

## Q1. GrilledTurkey's FO3/FNV mods: creatures, rigs, animations, permissions

### Takeaway
GrilledTurkey released 34 FO4 mods between 2020-01-17 and 2022-05-08, then retired. Seven of them are fully custom creatures, each with its own skeleton, ragdoll, behaviours and new animations: Mojave Mantises, Mojave Geckos, the Securitron in the Robot Pack, Mojave Cazadores, Mojave Bighorners, Capital Wasteland Centaurs, and the "Abomination" in Project Zeta. The rest are classic-look meshes on vanilla rigs. The About Me text does **not** say "allowed if the original is downloaded and credited". It allows edits and patches, bans unedited reuploads, and says substantially changed reuploads must require the original. The Nexus permission block on each creature mod is stricter: asset use needs permission, or is not allowed at all, and conversion to other games is not allowed.

### Cited Findings
**Account and permission wording**
- Exact About Me text, as shown on the profile on 2026-10-25: "NOTE: We have both retired from modding so any messages sent to this account will probably not be seen. Thank you to everyone who downloaded and enjoyed our mods! If you would like to make edits to our mods or make patches that is totally fine, all we ask is that you don't upload any unedited files or ESMs! IMPORTANT: DO NOT repackage and reupload our mods, this does not count as editing. ONLY reupload files that have been changed in a substantial way (i.e a bodyslide conversion, retexture or mesh edit). you MUST require the original mod as a prerequisite. This is a shared account for TheFriedturkey and HcGxGrill. We will post our joint mods to this account." — [GrilledTurkey profile](https://www.nexusmods.com/profile/GrilledTurkey/about-me)
- The profile lists 34 mods, 4.2M downloads and a join date of 01 Jan 2020, with the location given as United Kingdom. — [GrilledTurkey mods](https://www.nexusmods.com/profile/GrilledTurkey/mods?gameId=1151)
- **Nexus permission blocks per mod** (these conflict with the looser About Me text):
  - Mojave Geckos, Mojave Mantises, Mojave Bighorners, Capital Wasteland Centaurs, Capital Wasteland Radscorpions, Capital Wasteland Robot Pack, DC and West Coast Supermutants, ED-E, Project Zeta:
    - Upload: "not allowed to upload this file to other sites under any circumstances".
    - Modification: "must get permission from me".
    - Conversion: "not allowed to convert this file to work on other games under any circumstances".
    - Asset use: "must get permission from me before you are allowed to use any of the assets".
    - No use in paid mods or donation-point mods. — [Mojave Geckos](https://www.nexusmods.com/fallout4/mods/50275), [Mojave Mantises](https://www.nexusmods.com/fallout4/mods/48442), [Mojave Bighorners](https://www.nexusmods.com/fallout4/mods/57991), [CW Centaurs](https://www.nexusmods.com/fallout4/mods/59379), [CW Robot Pack](https://www.nexusmods.com/fallout4/mods/52147)
  - Mojave Cazadores is different:
    - Modification: "allowed to modify my files and release bug fixes or improve on the features so long as you credit me".
    - Asset use: "You are not allowed to use assets from this file under any circumstances". — [Mojave Cazadores](https://www.nexusmods.com/fallout4/mods/57161)
  - Capital Wasteland Yao Guai and Classic Brahmin Replacer: asset use is "not allowed … under any circumstances". — [CW Yao Guai](https://www.nexusmods.com/fallout4/mods/58290), [Classic Brahmin](https://www.nexusmods.com/fallout4/mods/57825)
  - The Project Zeta description adds: "Everyone is free to make addons and Mods for this … But do not redistribute any unedited files or ESMs". — [Project Zeta](https://www.nexusmods.com/fallout4/mods/60267)
  - Every one of these pages says "This author has not provided any additional notes regarding file permissions". — [Mojave Geckos](https://www.nexusmods.com/fallout4/mods/50275)

**Fully custom creatures (new skeleton, ragdoll, behaviours and animations)**
- **Mojave Mantises**
  - Uploaded 2020-11-14, v1.2 (2020-11-17), e≈3.5k.
  - The page calls it "a completely new custom creature with a brand new skeleton and animation set faithfully recreated" and says it was made "over a span of a week" after "a year of research we now can make fully custom new creatures".
  - Split of work: TheFriedturkey did "art work, animations, rigging and a bit of skeleton work". Grill "did all the behaviours, skeleton and ragdoll setup".
  - Content: 5 variants, spawns with Bloodbugs, attacks workshops.
  - Tools: "3ds max 2013, with Bethesda official exporter", TopoGun, Substance Painter, ZBrush and the Creation Kit, "All done with official tools". — [Mojave Mantises](https://www.nexusmods.com/fallout4/mods/48442)
- **Mojave Geckos**
  - Uploaded 2021-02-21, e≈3.4k.
  - "a new fully custom creature … with a brand new custom skeleton, artwork and faithfully recreated animations".
  - Content: 11 variants, a follower that grows over time, gecko eggs that hatch at the workshop.
  - Credits: TheFriedturkey for "3D Models, Textures, Rigging, Animations and Skeleton". HcG x Grill for "Scripting, Implementing, Behaviours, Skeleton, Havok Ragdoll".
  - Tools: the same official-tools chain. — [Mojave Geckos](https://www.nexusmods.com/fallout4/mods/50275)
- **Capital Wasteland Robot Pack**
  - Uploaded 2021-05-17, requires Automatron, e≈3.7k.
  - Adds classic Mister Handy/Gutsy, classic Protectron, classic Eyebots and Securitrons.
  - "The Securitron is a brand new robot to Fallout 4 and has a fully new custom skeleton, animations and artwork … designed around the Create-A-Bot system".
  - Known issue: "Not all pieces are interchangeable with vanilla … due some animations and arm positioning that wasn't designed with the vanilla Fallout 4 Robots in mind".
  - The pack also adds Vendo-tron, a roaming vendor. — [CW Robot Pack](https://www.nexusmods.com/fallout4/mods/52147)
- **Mojave Cazadores**
  - Uploaded 2022-01-07, v1.1 (2022-01-14), e≈2.3k.
  - "Adds a fully custom new creature … Full new animations and skeleton faithfully recreated".
  - Content: 5 variants (standard, glowing, young, large), spawns with Stingwings, a companion "Caz", craftable antivenom.
  - Credits: Grill for "Behaviours, Skeleton and Havok Ragdoll". — [Mojave Cazadores](https://www.nexusmods.com/fallout4/mods/57161); press coverage in [TheGamer, 2022-01-08](https://www.thegamer.com/mojave-cazadores-mod-fallout-4-new-vegas/)
- **Mojave Bighorners**
  - Uploaded 2022-02-10, e≈1.7k.
  - "Adds a fully custom new creature … Bighorners have the ability to throw NPCs and the player … Full new animations and skeleton faithfully recreated".
  - Content: spawns with Radstags, a companion "Woolly". — [Mojave Bighorners](https://www.nexusmods.com/fallout4/mods/57991)
- **Capital Wasteland Centaurs**
  - Uploaded 2022-04-05, e≈3.1k.
  - Standard and evolved centaurs plus glowing, albino and gangrenous variants. They spawn in place of mutant hounds.
  - "Fully new custom creature with custom skeleton … Full new animation set … Spits without any use of scripts (basically fully native creature implemented using only official tools)".
  - Credits: Grill for "Implementation, Rigging, Behaviours and Scripting". — [CW Centaurs](https://www.nexusmods.com/fallout4/mods/59379)
- **Project Zeta**
  - Uploaded 2022-05-08.
  - Adds "2 New enemy types (Aliens and Abominations) one of which is a fully custom creature". — [Project Zeta](https://www.nexusmods.com/fallout4/mods/60267)
- **Project Mojave (early access)**
  - Uploaded 2021-10-23, updated 2021-11-12, e≈7.1k.
  - Feature list: "10 Custom Creatures (3 Brand new ones)". Its creatures "are specific to the Mojave and will not spawn in the Commonwealth".
  - Credits: TheFriedturkey for "Animations". HcG x Grill for "most of the rigging, Animations".
  - Team: HcG x Grill, TheFriedturkey, C411um13 and MrColonelMustard. — [Project Mojave](https://www.nexusmods.com/fallout4/mods/55215)

**Classic-look meshes (credits list models, textures and rigging only; no skeleton or animation credit)**
- **Capital Wasteland Radscorpions**, 2022-03-10: "Models, Textures and Rigging". Not on Bethesda.net. — [CW Radscorpions](https://www.nexusmods.com/fallout4/mods/58729)
- **Capital Wasteland Yao Guai**, 2022-02-20: "Models, Textures and Rigging". They are "a lot faster just like in Fallout 3". — [CW Yao Guai](https://www.nexusmods.com/fallout4/mods/58290)
- **Classic Brahmin Replacer**, 2022-02-03: "brand new 3D models made for the Capital Wasteland project". — [Classic Brahmin](https://www.nexusmods.com/fallout4/mods/57825)
- **DC and West Coast Supermutants**, 2021-01-26: DC, West Coast and Nightkin variants with "Stealth capabilities". They use FO4 armour, with "minor bits of clipping". — [DC and West Coast Supermutants](https://www.nexusmods.com/fallout4/mods/49680)
- **ED-E Companion**, 2020-10-19: credits TheFriedturkey for "3D models, Textures, Rigging, CK Implementation". Requires Automatron. — [ED-E Companion](https://www.nexusmods.com/fallout4/mods/48010)
- **Earlier work under TheFriedturkey's own account**, all from the 2019 Capital Wasteland roadmap:
  - Fallout 3 - NV Feral Ghouls Replacer, 2019-06-03, with "Full Dismemberment". — [Feral Ghouls Replacer](https://www.nexusmods.com/fallout4/mods/39290)
  - Capital Wasteland Behemoths, 2019-10-15. — [CW Behemoths](https://www.nexusmods.com/fallout4/mods/41549)
  - DC Molerats, 2019-10-22, adding the FO3/FNV molerat "along side their commonwealth counterparts". — [DC Molerats](https://www.nexusmods.com/fallout4/mods/41671)
  - Institute Centaurs, 2019-10-08. This is an FO4 concept-art centaur, not the FO3 one. It "comes with custom animations, a brand new sculpt … classic spit attack (which was a pain to get working)". Tools: official exporter, 3ds Max 2013/2018, NifSkope, Material Editor. — [Institute Centaurs](https://www.nexusmods.com/fallout4/mods/41476)
  - Lamprey Floaters, 2019-09-17. Based on scrapped FO3 floater concept art, "made this for Fallout 4 New Vegas … We also made custom animation edits of the bloatfly". — [Lamprey Floaters](https://www.nexusmods.com/fallout4/mods/41180)

**What users report**
- Nexus comments on Mojave Cazadores, summarised second-hand by the search engine: some users see bugged, white or pink textures and a mix of mismatched textures; others report no problems. — [Mojave Cazadores](https://www.nexusmods.com/fallout4/mods/57161) (comment summary via search engine; not read directly)
- Suinier's "Mojave Mantises - Reworked", 2025-07-31, e83, changes the mantis spawns:
  - removes the script injection into the Bloodbug levelled list;
  - hand-places spawn points;
  - removes settlement attacks ("didn't make sense").
  - It requires the original and replaces its plugin. — [Mojave Mantises - Reworked](https://www.nexusmods.com/fallout4/mods/95462)
- Mojave Geckos Cut Restoration, by PLSET, 2024-05-10, restores "green geckos" that were cut from Mojave Geckos. — [Mojave Geckos Cut Restoration](https://www.nexusmods.com/fallout4/mods/82483)
- Other modders build on these creatures by requiring the originals: "Stingwing cazador replacer" (requires Mojave Cazadores or Project Mojave), "Mantis Radroach Replacer", "Bighorners Only", "Cazadores Only", "Mutant Hound Centaur Replacer". — [Stingwing cazador replacer](https://www.nexusmods.com/fallout4/mods/56768), [Mantis Radroach Replacer](https://www.nexusmods.com/fallout4/mods/60197)
- Translations exist (RU, FR, ES, PT-BR, DE, ZH), along with Horizon patches. — [Mojave Geckos - RU](https://www.nexusmods.com/fallout4/mods/50284)

### Inferences
- GrilledTurkey consistently says "faithfully recreated" and lists ZBrush, TopoGun and Substance Painter. That suggests the art was remade, not imported FNV NIFs. Their asset bans also rest on that claim of original authorship.
- The pipeline is consistent: 3ds Max 2013 with the official Bethesda exporter for skeleton and animation HKX, Havok ragdoll set up by Grill, and behaviours built from vanilla graphs in the Creation Kit. FO4 needs no external behaviour-graph tool for this, as long as the team has the official 3ds Max/Havok toolchain.
- Reuse status: the About Me text allows edit or patch plugins that **require** the originals. Using or converting their assets is barred by each mod's permission block, and the authors cannot be reached. A conversion tool that ships GrilledTurkey assets would breach the posted terms. A user-installed dependency that the tool points at would fit the About Me terms.

### Gaps
- Which 10 creatures are in Project Mojave, and which 3 are "brand new", is not stated in the sections read. Coverage from DSOGaming and TechRaptor in 2021 does not name them either.
- No direct reading of Nexus comment threads or bug trackers on animation, ragdoll or AI quality. The GraphQL query used did not return comments, and the forum pages were not fetched.
- Whether the classic Mister Handy, Protectron and Eyebot reuse the vanilla Automatron skeletons is inferred from the page, not stated.

## Q2. Other porters and how complete their work is

### Takeaway
No one else has made FNV/FO3 creatures with custom skeletons. The rest falls into three groups:
- **Mesh swaps on the Dogmeat rig** (Shadowliger's nightstalker, cyberdog Rex and coyote; visual only).
- **Vanilla DLC creatures moved or rescaled** (Nuka-World ants posing as FO3 giant ants; bloatfly-based floaters).
- **Small 2025 mods with unstated rigs** (C Spore Carrier).

For lakelurk, giant rat, trog, tunneler, FO3 robobrain, Liberty Prime (it is already in FO4) and FNV deathclaws as a separate creature, there are only retextures or vanilla edits.

### Cited Findings
- **Nightstalker**
  - Shadowliger's "Nightstalker Dogmeat Replacer", 2017-12-29: "a Mesh and texture replacer for Dogmeat … This is a VISUAL. CHANGE. ONLY … a mesh experiment … there may occasionally be oddities in the mesh in certain poses". — [Nightstalker Dogmeat Replacer](https://www.nexusmods.com/fallout4/mods/28752)
  - Shadowliger's "Nightstrikers", 2017-03-27, v3.1 updated 2020-05-27, e≈5.2k: a creature "loosely" based on the nightstalker, with 5 variants plus legendaries and a companion. It "REQUIRES the Far Harbor DLC … mod uses assets [from] that DLC". The companion "can't wear armor … the default dog armor would not fit him". — [Nightstrikers](https://www.nexusmods.com/fallout4/mods/23004)
  - Chainn25's "Nightstalker Replacer", 2025-08-09, swaps the Nightstriker models for Shadowliger's nightstalker meshes. — [Nightstalker Replacer](https://www.nexusmods.com/fallout4/mods/95687)
- **Dogs and coyotes**
  - Shadowliger's "Dogmeat's Many Faces New Vegas Canine Edition", 2019-05-11: 8 full-body mesh replacers for Dogmeat, equipped in slot 33 (body). Includes coyote, Legion mongrel and Cheyenne/FO3 Dogmeat; base textures by bigcman123. "These are not just texture replacers … there will likely be clipping". — [Dogmeat's Many Faces NV](https://www.nexusmods.com/fallout4/mods/38824)
  - Shadowliger's Cyberdog Rex replacers, 2018-01-24 and 2019-10-20: Rex's ear movement was "severely reduce[d] … to avoid weird stretching with the glass dome". "None of my recreations are [1-to-1]". — [Project Cyberdog's Rex](https://www.nexusmods.com/fallout4/mods/29349), [Cyberdog Rex Dogmeat Replacer](https://www.nexusmods.com/fallout4/mods/41635)
  - radicalclownfriend's "Coyotes", 2022-07-28, e306: replaces mongrels with Shadowliger's coyote model. — [Coyotes](https://www.nexusmods.com/fallout4/mods/62685)
- **Giant ant / fire ant**
  - DirtyBadger's "Giant Ants of the Commonwealth", 2018-09-22, updated 2023-01-30: new worker, soldier and glowing ants built on the Nuka-World ants. Requires Nuka-World. A limit the author hit: "when scaling up the size of the ants … the bodies flicker and do not act like normal ragdolls, they float above the ground and spaz about" — so the ants are capped in size, and an ant queen "is going to take some time". — [Giant Ants of the Commonwealth](https://www.nexusmods.com/fallout4/mods/34860)
  - Watcherzero's "Ant Queen Modder's Resource", 2021-10-08: a rigged queen model. It "Can't be targeted in vats with guns. No idea why … Too large causes issues". Free to use with credit, not in paid mods. — [Ant Queen Modder's Resource](https://www.nexusmods.com/fallout4/mods/54958)
  - Simple spawn mods move the vanilla Nuka-World ants into the Commonwealth. — [Nuka-World Ants in the Commonwealth](https://www.nexusmods.com/fallout4/mods/27569), [Large Soldier Ants](https://www.nexusmods.com/fallout4/mods/92915)
  - No fire-ant port found.
- **Spore carrier**
  - Vallesi's "C Spore Carrier", 2025-07-19, e251: adds 7 spore carriers to the Radstag levelled list through a script, using a Vault 22 picture "as a template". The rig and animations are not stated. — [C Spore Carrier](https://www.nexusmods.com/fallout4/mods/95186)
- **Floaters** (a Fallout 2 creature)
  - InvokerGray's "Floaters", 2018-11-02: "Reskinned Fly's"; "a template for making new monsters on PS4". — [Floaters](https://www.nexusmods.com/fallout4/mods/35684)
  - PrincessAries' "Project NEMEAN", 2025-07-01, e459: adds a "Floater" with 6 variants as part of a FEV creature pack. — [Project NEMEAN](https://www.nexusmods.com/fallout4/mods/94729)
- **Securitron**
  - m150's "AutomatronSecuritron", 2016-04-12, v1.2 2017-07-01, e≈6.5k: adds a Securitron torso and "Securitron Tire" legs as Automatron parts, with face screens (Yes Man, Victor and others). The base rig is not stated. — [AutomatronSecuritron](https://www.nexusmods.com/fallout4/mods/11910)
  - GrilledTurkey's custom-skeleton Securitron is covered in Q1.
- **Deathclaw**
  - jaggedjoshart's "Classic Deathclaws Redux", 2022-07-09, e795: a mesh replacer for all vanilla deathclaw types, "Remade from scratch, esp-less". — [Classic Deathclaws Redux](https://www.nexusmods.com/fallout4/mods/62050)
- **ED-E**
  - mattsahuman's "ED-E the EyeBot", 2016-03-16: model by Stefan Engdahl, on the vanilla companion setup, requires Automatron. — [ED-E the EyeBot](https://www.nexusmods.com/fallout4/mods/10965)
- **Mantis, independent of GrilledTurkey**
  - Kudemborots Of The Commonwealth: "A retexture for Zuzuluk Kudemborot Mantis creature". The base mod by Zuzuluk was not traced. — Nexus API search result for fallout4 mod 70427 (unconfirmed primary page)
- **Big ecosystem mods**
  - StamperDoesMods' "Mutant Menagerie - Life Finds A Way", 2023-08-26, e≈3.9k: "over 60+ NEW and LORE-FRIENDLY creatures". The description read does not say whether any are FNV/FO3 ports. — [Mutant Menagerie](https://www.nexusmods.com/fallout4/mods/68187)
  - Thirdstorm's "Unique NPCs - Creatures and Monsters", 2018: variant and texture shuffling on vanilla creatures. — [Unique NPCs Creatures](https://www.nexusmods.com/fallout4/mods/24357)
- **Searches with no FO4 port**
  - Nexus API name searches on fallout4 returned no creature port for lakelurk, giant rat, trog, tunneler, fire ant, "mister gutsy" (only Gutsy fixes and retextures), or a FO3-style robobrain (only the "Classic Eyeless Robobrains" edit).
  - Liberty Prime results are retextures, sound mods and followers based on the vanilla FO4 Prime. — [Classic Eyeless Robobrains](https://www.nexusmods.com/fallout4/mods/82431), [SavrenX HD Liberty Prime](https://www.nexusmods.com/fallout4/mods/40305)

### Inferences
- In practice, porting a non-FO4 creature means either (a) GrilledTurkey-level custom skeleton work, or (b) borrowing the closest vanilla rig: dog for canines, bloatfly for floaters, Nuka ant for ants, Automatron for robots.
- Option (b) sets hard limits. The ant ragdoll breaks when scaled, the ant queen cannot be targeted in VATS, and Dogmeat mesh swaps are visual only.
- No other team has published FO4 versions of the more complex FNV creatures (lakelurk, nightstalker with its own rig, trog, tunneler, spore carrier with known animations).

### Gaps
- No primary page was found for a separate "Fallout 4: New Vegas" (F4NV) creature release. Only TheFriedturkey's note that the Lamprey Floaters were "made … for Fallout 4 New Vegas" and MrMadre's line "it will be a while until F4NV comes out" were seen. — [Lamprey Floaters](https://www.nexusmods.com/fallout4/mods/41180), [MrMadre's mods](https://www.nexusmods.com/profile/MrMadre/mods)
- No FO4 mods named "Mojave Imports", "FO3/FNV Creatures for FO4", "Lakelurks" or "Geckos of the Commonwealth" were found. They likely do not exist under those names.
- The rigs behind Nightstrikers (a Far Harbor asset), C Spore Carrier and the m150 Securitron are unconfirmed.

## Q3. Write-ups and tutorials on putting an FNV creature on an FO4 rig, and the limits authors hit

### Takeaway
No public step-by-step guide for porting an FNV creature to FO4 was found. The author notes that do exist describe a pipeline and its limits rather than full instructions.

### Cited Findings
- GrilledTurkey say custom creatures took "a year of research". After that, a mantis took about a week. Their tools are 3ds Max 2013 with Bethesda's official exporter and the CK. — [Mojave Mantises](https://www.nexusmods.com/fallout4/mods/48442)
- They describe a "native" centaur spit that needs no script, built "using only official tools". The spit on the 2019 Institute Centaur "was a pain to get working". — [CW Centaurs](https://www.nexusmods.com/fallout4/mods/59379), [Institute Centaurs](https://www.nexusmods.com/fallout4/mods/41476)
- Lamprey Floaters reused the bloatfly rig with "custom animation edits of the bloatfly". — [Lamprey Floaters](https://www.nexusmods.com/fallout4/mods/41180)
- Limits other authors hit:
  - ragdoll instability when a creature is scaled up;
  - VATS targeting failing on a large rigged model;
  - Dogmeat mesh oddities "in certain poses";
  - Rex's ears limited to avoid stretching. — [Giant Ants of the Commonwealth](https://www.nexusmods.com/fallout4/mods/34860), [Ant Queen Modder's Resource](https://www.nexusmods.com/fallout4/mods/54958), [Nightstalker Dogmeat Replacer](https://www.nexusmods.com/fallout4/mods/28752), [Cyberdog Rex Dogmeat Replacer](https://www.nexusmods.com/fallout4/mods/41635)
- On the robots, GrilledTurkey say custom Securitron parts don't mix freely with vanilla Automatron parts, because of animation and arm-position differences. — [CW Robot Pack](https://www.nexusmods.com/fallout4/mods/52147)
- General FO4 tutorials surfaced only through search snippets, not read directly:
  - a Nexus tutorial on custom animations using 3ds Max 2013–2015, the FO4 Animation Kit, NIFTools 3.8.0 and Havok Content Tools 2014;
  - a note that FO4's 64-bit HKX files must be converted to 32-bit for editing;
  - "Behavior Graph Studio", a beta node editor for FO4 behaviour graphs. — [Nexus FO4 43611](https://www.nexusmods.com/fallout4/mods/43611), [Nexus FO4 107691](https://www.nexusmods.com/fallout4/mods/107691) (unconfirmed: search-engine summaries only)

### Inferences
- The GrilledTurkey workflow appears to be: model and skin in 3ds Max 2013 with a new skeleton, export the skeleton, ragdoll and animations with Bethesda's Havok exporter, then clone and adjust a vanilla creature behaviour graph and set up the race in the CK.
- This is consistent with their credit lines, but they never document it step by step.

### Gaps
- No public tutorial, video or Discord write-up from HcGxGrill or TheFriedturkey on their custom-creature pipeline was found.
- No Blender-based FNV-to-FO4 creature retargeting write-up was found.

## Q4. Wabbajack lists and collections bundling these ports

### Takeaway
Several Nexus Collections bundle GrilledTurkey's creature mods. No Wabbajack list was found.

### Cited Findings
- "Fallout New Vegas in Fallout 4" by Gyzlad: e99, about 14.3k downloads, latest revision updated 2026-10-11, 113 mods. It includes:
  - Project Mojave, Mojave Mantises, Mojave Geckos, Mojave Cazadores, Mojave Bighorners;
  - CW Robot Pack, CW Yao Guai, CW Radscorpions, Classic Brahmin;
  - DC and West Coast Supermutants, "DC Creatures Only";
  - Project Cyberdog Rex, and both classic ghoul mods. — [Collection fgx1sr](https://www.nexusmods.com/games/fallout4/collections/fgx1sr) (mod list read through the Nexus GraphQL API)
- "Ultimate New Vegas Legacy" by MichaelCrypt, 306 mods, updated 2025-01-24. It includes:
  - the same GrilledTurkey creatures;
  - m150's AutomatronSecuritron;
  - Mutant Menagerie - Big Game Hunting;
  - Unique NPCs Creatures. — [Collection k8mbvc](https://www.nexusmods.com/games/fallout4/collections/k8mbvc)
- radicalclownfriend's "DC Creatures Only", 2021-12-18: replaces vanilla mole rats and behemoths with TheFriedturkey's versions. The author dropped the GrilledTurkey robots because "they were a pain". — [DC Creatures Only](https://www.nexusmods.com/fallout4/mods/56677)

### Inferences
- Collections like these show users install GrilledTurkey's mods as dependencies. That is the distribution model the authors' terms allow.

### Gaps
- No Wabbajack list containing these creatures was confirmed; the Wabbajack gallery was not searched directly.
- YouTube showcases were not reviewed.
