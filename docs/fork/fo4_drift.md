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
| Weapons and armor without a stand-in | FNV's models, DT, criticals | FNV's name, value, weight, damage (and a gun's magazine and ammo) on an FO4 weapon or outfit's animations and sounds; melee weapons and headgear show FNV's meshes, without FO4 mods, headgear fitted to FO4's head and not following facial animation; guns FO4's guns and their mods (FNV's mesh on an FO4 receiver only in the experimental `fnv` mode); outfits FO4's models; every stand-in set by the [replacement table](fo4_replacements.md); FNV's DT as the armor rating, unscaled | [equipment](fo4_spikes.md#spike-4-equipment), [melee](fo4_spikes.md#spike-4-melee), [headgear](fo4_spikes.md#spike-4-headgear) |
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

## <a id="candidates"></a>Systems where FO4's own version is the likely answer

Not built yet. Each names the FO4 mechanism to take and the drift to note.

- **SPECIAL, skills, traits, perks.** Decided: FNV's system on
  LevelUpMenuEx ([decision](research/fo4_target.md#decisions)). Drift:
  skills appear in LevelUpMenuEx's menu rather than a Pip-Boy page; FO4's
  perk chart is turned off.
- **Speech checks and skill-gated lines.** FNV shows `[Speech 50]`; FO4
  colors persuasion by Charisma. Keep FNV's checks as conditions, shown
  through XDI.
- **Karma and faction reputation.** FO4 has neither; globals or actor
  values with a status display (FO4 affinity is per companion only).
- **Companions.** FNV's companion wheel versus FO4's command mode and
  affinity: use FO4's follower system and note the lost wheel options.
- **VATS.** FO4's slowed time versus FNV's pause.
- **Weapons and armor.** FNV mods and item condition versus FO4's object
  mods (no condition or repair): mods become OMODs; condition is dropped
  or kept as a script value.
- **Hardcore mode.** Thirst, hunger and sleep onto FO4 Survival's needs.
- **Crafting.** Workbenches, campfires and reloading benches as FO4
  crafting stations (COBJ recipes).
- **Pip-Boy, map and fast travel.** FO4's Pip-Boy and world map;
  FNV-specific pages (reputation, radio list) need a place.
- **Lockpicking and hacking.** FO4's minigames; FNV's skill gates become
  perk or skill-value checks.
- **The player's voice.** FO4's voiced player says "Hi" before a greeting
  ([spike 1](fo4_spikes.md#spike-1-design)); silence it or accept it.
- **Ambient NPC conversations and barks.** FO3's 204 NPC-to-NPC Dialogue
  packages as FO4 two-actor scenes ([census](fo4_spikes.md#scene-census)).
- **Disguises and faction armor.** FO4 has no disguise system.
- **Radio.** Stations as FO4 radio scenes.
- **Level scaling.** Leveled lists and encounter zones under FO4's rules.
