# FO3/FNV on Fallout 4: where play differs

The FO4 target prefers Fallout 4's own mechanism over an exact emulation of
FO3/FNV behavior when the emulation costs repeated play-test rounds
([drift policy](fo4_spikes.md#scene-census)). Every such change is listed
here, so a later patch can close the gap. Content is never dropped.

## <a id="recorded"></a>Recorded drift

| Area | FO3/FNV | On Fallout 4 | Where |
|---|---|---|---|
| Scripted conversations | Each line's result says the next; the first line whose conditions pass plays | One scene per run of steps, a phase per step; lines picked by scene order. Pacing between lines is FO4's | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Topic menus | Any number of topics; Tab leaves | XDI menus; a `[Leave]` option stands in for Tab | [spike 1](fo4_spikes.md#spike-1-design) |
| Vit-o-matic (SPECIAL) | FNV's menu, 40 points | FO4's SPECIAL menu and point budget | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Choosing sex | The Reflectron's race menu | A Male/Female box before the Reflectron opens FO4's appearance editor | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Naming the character | The Reflectron's name entry | FO4's SPECIAL menu name field, at the Vit-o-matic | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Skills page | Pip-Boy Skills tab | LevelUpMenuEx's menu; the Pip-Boy shows FO4's SPECIAL and perks | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Traits | Effects on pick | Picked through LevelUpMenuEx; no effects until perks are converted | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Skill points per level | Granted at the level-up | Added when LevelUpMenuEx's menu next opens | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Walking away mid-conversation | The talk ends | A one-menu scene ends; a multi-phase scene waits in its phase until the player returns | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Opening a talk | `StartConversation`, force greets and clicking all open the GREETING | A silent `...` greeting line starts the GREETING scene (its subtitle shows briefly) | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Force greets | Dialogue package: walk up and talk | FO4 ForceGreet (its approach distance, dialogue camera) | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| AI packages | FNV package types and flags | Copies of vanilla FO4 template instances; flags the games share; Travel to a chair is a Sit | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Player script packages (wake-ups, knock-downs, deaths) | Special idles with an animated camera | VCG01's bed wake-up seats the player on the bed's edge from the start; the player stands by moving; other player packages play nothing | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Idles played by script | FO3/FNV special idles (`.kf`) | No animation: FO4's give is a talk idle; set as the speaker idle of Doc's next line ("How'd I do?") it did not show. Others play nothing | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Imagespace modifiers | FNV's HDR (skin dimmer, target luminance, bloom alphas), cinematic contrast average, intro/outro sounds | Dropped; blur, double vision, tint, fade, radial blur, depth of field, eye adapt, bloom radius, saturation, contrast and brightness kept | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Items with an FO4 counterpart | FNV's own items, names and stats | The Fallout4.esm item: its name, stats and model (the 9mm pistol is the 10mm, energy cells are fusion cells, dynamite is the frag grenade, the Vault 21 suit is Vault 111's) | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Item condition | Leveled lists give an item at a condition | No condition: the item | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Weapons and armor without a stand-in | FNV's models, DT, criticals | FNV's name, value, weight, damage (and a gun's magazine and ammo) on an FO4 weapon or outfit's animations and sounds; melee weapons, headgear and the pre-war outfits show FNV's meshes, without FO4 mods, headgear fitted to FO4's head and not following facial animation, outfits moved onto FO4's body and skinned to it (no dismemberment cuts; the Pip-Boy sleeve always rolled; bare skin on FO4's body texture and shader, not FNV's skin texture, so FO4's painted underwear shows and FO4's hand meets FNV's thinner forearm; [CBBE and BodySlide](fo4_replacements.md#bodyslide) later); guns FO4's guns and their mods (FNV's mesh on an FO4 receiver only in the experimental `fnv` mode); outfits FO4's models; every stand-in set by the [replacement table](fo4_replacements.md); FNV's DT as the armor rating, unscaled | [equipment](fo4_spikes.md#spike-4-equipment), [melee](fo4_spikes.md#spike-4-melee), [headgear](fo4_spikes.md#spike-4-headgear), [outfits](fo4_spikes.md#spike-4-outfits) |
| Consumable effects | Health, rads, skill boosts, Hardcore needs, chem stats, limb and script effects | Health (FO4's food heal), rads, Nuka-Cola's cap, and skill boosts (Rad-X's timed boost on the skill) carry; perk variants act as without the perk; the rest is dropped | [exterior](fo4_spikes.md#spike-4-exterior) |
| Ammunition | FNV's rounds, with their own projectiles | FNV's name, model, value and weight on FO4's 5.56 round | [exterior](fo4_spikes.md#spike-4-exterior) |
| Quest objectives in conditions | Engine condition functions | Mirror globals the converted scripts set | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Race menu (Reflectron) | FNV's race/face menu | FO4's full LooksMenu, as the vault exit elevator | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Faces | FaceGen shape and texture | FO4 sculpt regions fitted to FNV (about 70% of the shape), matched hair and eyes | [sculpt](fo4_spikes.md#spike-2-sculpt) |
| Cell grading | Imagespace values | One LUT baked from FNV's grading | [imagespace](fo4_spikes.md#spike-2-imagespace) |
| Glass and blended surfaces | Alpha-blended lit surfaces | Decals, effect materials or cut-outs | [transparency](fo4_spikes.md#spike-2-transparency) |
| Collision | FNV Havok | Rebuilt through the CK's Elric | [collision](fo4_spikes.md#spike-2-collision) |
| Character collision height | FNV's controller fits a 139 opening | FO4's human skeleton box lowered from 128 to 115 so it does too; FO4's own NPCs get the same box | [player collision](research/fo4_target.md#player-collision) |
| Script timing | Per-frame GameMode blocks | Papyrus timers (0.1 s at the fastest) | [timing](fo4_spikes.md#spike-3-timing) |

## <a id="candidates"></a>Systems: FO4's or FNV's (decided 2026-10-08)

Not built yet. Size is the build estimate: S small, M medium, L large.
Counts are from the FalloutNV.esm export.

| System | Decision | What it takes | Size |
|---|---|---|---|
| SPECIAL, skills, traits, perks | FNV's system on LevelUpMenuEx ([decision](research/fo4_target.md#decisions)) | Skills in LevelUpMenuEx's menu; FO4's perk chart off | — |
| Speech checks, skill-gated lines | **FNV's**: deterministic skill checks, not FO4's Charisma chance (no reloading past them) | Already converted as dialogue conditions (spike 1, played); left: the `[Speech 50]` tag and how a failed check shows through XDI | S |
| Karma | **Build** | Karma as an actor value: 48 `RewardKarma`, about 200 reads in scripts and conditions. FNV's engine also moves karma on kills and thefts: FO4 story-manager kill and crime events with a script. Design borrowed from KARMA ([mods](research/fo4_target.md#mods)) | S-M |
| Faction reputation | **Build** | 13 REPU factions; 218 `AddReputation`, 81 `SetReputation`, 202 `GetReputation`, 135 `GetReputationThreshold`. Fame and infamy per faction plus a stored tier, so conditions can test it; scripts through the converter's helpers. Hit squads and gift givers are FNV content and convert with it. REPUTATION is closed to new factions | M |
| Disguises, faction armor | **Build**, after reputation | FNV's are records and scripts, not engine code: `DisguiseFactionQuestScript` watches faction gear form lists (`FactionGearNVNCR`...) and a scripted pulse (`DisguiseFactionPulse*`) drops nearby sniffers from the disguise faction, saving and restoring reputation. They convert as content | S |
| Companions | **FO4's** follower system | Drift: FNV's companion wheel options | — |
| VATS | **FO4's** slowed time | Suits FO4's faster combat | — |
| Weapon mods | **Build** | FNV's 50 IMODs as FO4 object mods (the receiver and part pipeline of the gun work); installed at a workbench, not from the Pip-Boy (drift) | M |
| Item condition | **Build** | FO4 keeps item health only for power armor. Weapons need per-item health storage, its effects (damage, spread, jams), wear, repair (kits, other weapons, Jury Rigging, vendors) and a display: likely an F4SE piece (Hydra or our own). Our own, from FNV's per-weapon health ([mods](research/fo4_target.md#mods)) | L |
| Hardcore | **FO4 Survival's needs** | Thirst, hunger and sleep map directly. Open: Survival's other rules (bed saves, no fast travel, damage) as Hardcore's drift, or its needs under our own Hardcore switch | S-M |
| Crafting | **FO4's benches**, menus showing FNV's recipes | 105 RCPE, 10 RCCT as COBJ. Converted benches as copies of FO4's with their own crafting keyword, so menus list FNV's recipes without editing vanilla's; the reloading bench needs a home (FO4 has none) | S-M |
| Pip-Boy pages | Open | XDI and MCM don't touch it; LevelUpMenuEx has its own menu; Hydra adds stats-page lines. Options: PipboyTabs (not installed; tabs for any actor value or global, LevelUpMenuEx fills a skills tab), our own Pip-Boy SWF pages, or PrismaUI (installed, off; HTML overlays). Proposed: PipboyTabs behind our API | — |
| Lockpicking, hacking | **FO4's minigames on FNV's skills** | FO4's tiers are gated by perk ranks: hidden ranks granted at Lockpick or Science 25, 50, 75. FNV has five tiers (locks: 0: 39, 25: 73, 50: 121, 75: 58, 100: 32, key only: 103), FO4 four: Very Hard would open at 75 without a small script holding it to 100 (32 locks, 18 terminals) | S-M |
| The player's voice | **Silent** | Silent voice files; needs a test | S |
| Ambient conversations | **FO4 scenes** | The scene converter exists; needs a test with two NPCs | S |
| Radio | **FO4's radio** | FNV's songs are dialogue: an INFO per song (`{Song 15 Blue Moon}`) voiced by the song, picked by conditions, said by a talking activator (87 TACT); the station quest's script tracks order and story (Kimball's death). FO4's stations are radio activators whose quest scenes play songs as radio actions (sound descriptors) between DJ dialogue. So: songs to sound descriptors, DJ lines through the dialogue, scene and voice pipeline, station logic as converted script. Not only importing the music | M |
| Level scaling | **FNV's** | 17 ECZN, 2,738 LVLI, 365 LVLN, 343 LVLC map one to one onto FO4's (minimum levels, match-PC-below-minimum, never resets), keeping FNV's difficult routes; none of FO4's legendary spawns are referenced | S |

Proposed order: reputation and karma, then disguises (one store); weapon
mods; crafting, lockpicking and hacking; radio; item condition last (it
settles the runtime question). The voice and ambient-conversation tests fit
any build.
