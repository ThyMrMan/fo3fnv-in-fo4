# Dynamic collision for Fallout 4: mod plan

An F4SE mod that changes an actor's movement collision while playing:
smaller when crouching, so the player fits under low openings, and later
for swimming, scaled actors and power armor. The Skyrim model is
[Dynamic Collision Adjustment](https://github.com/ersh1/DynamicCollisionAdjustment)
(DCA, GPL-3.0). No FO4 equivalent exists (searched 2026-10-08). Separate
from the FNV conversion; it only reuses what the conversion learned about
the engine. Part of the [spin-off plan](spin_offs.md). Engine findings:
[dynamic collision research](research/fo4_dynamic_collision.md) and
[player collision](research/fo4_target.md#player-collision). Status lives
in the [roadmap](ROADMAP.md#parked).
**P** = played, **R** = read in the exe (1.11.240 RVAs), **I** = inferred.

## <a id="dca"></a>How DCA does it in Skyrim

Read from its source (2026-11-11):

1. **Track controllers:** hooks the actor's Havok setup (`Actor::InitHavok`)
   and both controller destructors, keeping data per controller.
2. **Hook the triggers:** `Actor::SetSneaking` (sneak on and off), each
   character state's "wanted state" change (on ground, in air, jumping,
   swimming, climbing), and the sneak key handler.
3. **Swap the shape:** reads the controller's shape (a list with a convex
   shape), builds a new convex shape with its top vertex moved by a height
   multiplier (sneak, swim) and scale, and sets it on the proxy or rigid
   body. Shape code credited to adamhynek.
4. **Check before standing:** a ray up from the controller; if it hits,
   the sneak key won't stand the player up.
5. Settings by MCM, debug drawing through TrueHUD.

Skyrim's physics is Havok 2010 (`hkp*`); FO4's is Havok 2014's new physics
(`hknp*`). DCA's ideas carry over; its shape code does not.

## <a id="known"></a>What we know in FO4

| | FO4 | |
|---|---|---|
| Controller types | Player `bhkCharProxyController`, NPCs `bhkCharRigidBodyController`, chosen in the actor's controller setup (`0xc5f6b4`), setup filled by `0xcbfdb0` | R |
| The player's shape | A compound of three capsules (`0x189ee10` each) sized from the third-person skeleton's `BSBound` times scale: half extents 22, 14, 64, top 128; offsets ±8 front and back, 1 down | R, size P |
| The size lever | Lowering `BSBound` lowers the player's collision; the FNV build ships a top of 115 | P |
| Custom capsules | The skeleton's layer-30 `CharacterBumper` capsule is not used by the player's controller | P |
| Headroom margin | The player needs 13–17 units above the shape's top; its source isn't read | P (measured) |
| Scale pinned | `setscale` doesn't change the player's collision: scale forced to 1.0 under default object 202's keyword when virtual `0x3f0` is false | R, P |
| **Two shape slots** | The controller holds two shapes (`+0x360`, `+0x368`) and an active index (`+0x354`); `0x1899320` swaps them through the controller's virtuals `0x198` then `0x218` | R |
| Havok layouts | Our `hk2014_layouts.json` has `hknpCapsuleShape`, `hknpCompoundShape`, `hknpShape` and others (from the animation work) | Have |
| Measuring | The step test map's H and HS stations measure headroom directly (`fo4_import.spike.step_map`) | P |

## <a id="unknown"></a>What we don't know

1. ~~What the second shape slot is for.~~ Read: the engine can hold two
   shapes and switch, but fills and switches only at controller creation;
   slot 1 is free for us ([the read](research/fo4_dynamic_collision.md#the-second-shape-slot-read-2026-11-11)).
   Still open: what the switch's scratch buffer and `0xd4b6f0` are.
2. **Changing a shape while playing:** whether the controller's own swap is
   safe at any time, and what the physics world needs (locking, contact
   refresh) when a shape changes.
3. **Hooks in FO4:** sneak on and off, swimming, power armor enter and exit,
   the controller's state changes, controller creation and destruction.
4. **The stand-up check:** an upward cast through FO4's physics world.
5. **The headroom margin:** where the 13–17 units come from, so a requested
   height becomes a known gap.
6. **NPC controllers** (rigid body type): their shape path.
7. **Camera:** the first-person camera height while crouched under a low
   ceiling (clipping).

## <a id="spikes"></a>Spikes

Each is one change, played or measured.

1. **Does sneaking change headroom today?** In vanilla FO4 (vanilla
   skeletons; the FNV build's lowered box would hide the result), crouch
   under an opening that blocks the player standing. Fits: the second slot
   is likely a crouch shape. Blocked: crouch collision is ours to supply.
   No build needed.
2. **Read the second slot:** find what writes slot 2 and what asks for
   index 1 (disassembly from `0x1899320` and the setup at `0xcbfdb0`);
   name the trigger. Read 2026-11-11: nothing does while playing
   ([the read](research/fo4_dynamic_collision.md#the-second-shape-slot-read-2026-11-11)).
3. **Swap by hand:** a test DLL that, on a hotkey, gives the player's
   controller a smaller second shape (three capsules built with the game's
   own `0x189ee10`) and switches the index. Measured on the step map: does
   headroom drop at once, with no physics glitches, and come back?
4. **Stand-up check:** a hotkey that casts up from the player and logs the
   hit distance, compared against the step map's known ceilings.
5. **Sneak hook:** the switch from spike 3 driven by sneak on and off,
   with the stand-up check blocking standing under a low ceiling.

Spikes 1 and 2 need no DLL. Spikes 3–5 can run on a throwaway test DLL
with raw 1.11.240 addresses; the release moves to the
[shared base](spin_offs.md#runtime).

## <a id="build-out"></a>Build-out

Its own repo from day one; nothing here touches the converter or its
builds, so it runs beside the FO4 sessions without colliding.

### Phase 0: repo and a plugin that loads

1. **Repo** (name to pick) with `LICENSE`, `EXCEPTIONS` and a short
   `NOTICE` ([license](spin_offs.md#license)), README, `.gitignore`.
2. **Build:** CMake + vcpkg, LucaDotGit CommonLibF4 "AV" as a submodule or
   vcpkg port, Visual Studio 2022 (Community's `vcvars64`, as the converter's
   DLLs need). One command builds `<Name>.dll`.
3. **Hello plugin:** loads under F4SE on 1.11.240, writes its version and
   the game version to its log, declares Address Library use. Proves the
   toolchain before any hook.
4. **Address Library IDs** for the functions we use (controller setup,
   setup builder, capsule builder, apply-setup, the switch's helper):
   look each RVA up in the 1.11.240 database, then match the 1.10.163 and
   1.10.984 IDs.
5. **Deploy:** a small script that copies the built DLL and INI into an MO2
   mod folder (`<Name> - dev`), separate from the F3NV mods.

### Phase 1: spikes ([list](#spikes))

- Spike 1 (vanilla sneak test) can run any time; it needs only the user.
- Read the switch's scratch buffer and `0xd4b6f0`, then spike 3 (hotkey
  swap) as the first real code in the Phase 0 plugin, then spikes 4 and 5.
- **A test cell of our own:** the converter's step map is converter code,
  so build a small ESP with marked openings (heights 90 to 140 in steps of
  10, a vent, a low pipe) in the Creation Kit or from a script; it becomes
  the demo cell shipped with the mod.

### Phase 2: first release (player crouch)

- Sneak lowers the player's collision; leaving sneak under a low ceiling
  stays crouched; INI settings; log; every hook checks its bytes.
- Played on 1.11.240, then 1.10.984 and 1.10.163, with keyboard and a
  controller; with and without our FNV build's lowered skeleton box.
- Nexus as a beta: requirements, demo cell, source link, open permissions.

### Phase 3: more states and an API

Swimming, power armor, the Papyrus API and events, MCM page, debug view.

### Phase 4: further

NPCs (rigid body controllers), the scale fix, VR with the
[VR build](spin_offs.md#platforms).

## <a id="design"></a>Design

- **Player first.** NPCs walk by navmesh, so smaller NPC collision buys
  little until they can path through low gaps; they come later.
- **Shapes are the game's own:** three capsules built by the game's
  builder, with the height from settings. No custom Havok objects of ours.
- **States and multipliers** (settings, each switchable):

  | State | Height | Radius |
  |---|---|---|
  | Standing | 1.0 | 1.0 |
  | Sneaking (on ground) | e.g. 0.6 | 1.0 |
  | Swimming | e.g. 0.5 | 1.0 |
  | Power armor | 1.0 | e.g. 1.2 |

- **Stand-up rule:** leaving sneak under a ceiling lower than the standing
  shape keeps the player crouched, with a short HUD message; standing
  happens by itself once there's room (setting).
- **Scale fix (later):** apply the actor's real scale to its collision, for
  scaled races, large creatures and height mods. Needs the scale pin
  understood ([known](#known)).
- **Papyrus API:** `SetHeightMultiplier(actor, float)`, `GetHeight(actor)`,
  `IsBlockedFromStanding()`, an event on change, so other mods can drive it
  (vents, crawl spaces, quest scenes).
- **Settings:** MCM-ready INI ([settings pattern](dialogue_menu_mod.md#config)),
  with a debug view of the collision shape.
- **Safety:** every hook checks the bytes it patches and turns itself off
  with a log line when they differ.

## <a id="gameplay"></a>What it makes possible

- Crouching under low pipes, through vents and gaps in level design.
- New level design for mod authors: crawl spaces and sneak routes, through
  the Papyrus API.
- Collision that matches the actor's size: small and large races, power
  armor.

Out of scope: a crawl or prone pose. It needs new animations and behavior
graph work; this mod only shrinks collision for poses FO4 already has.

## <a id="compat"></a>Compatibility

- **Body and height mods** that edit the skeleton's `BSBound` change our
  standing size; read the standing shape from the controller, never assume
  128.
- **Our FNV build** lowers the human box to 115; the mod must work on top of
  that (multipliers, not fixed heights).
- **Third-person camera and sneak mods** may move the camera; test with the
  common ones.
- **Power armor** has its own skeleton and box; test enter and exit.
- **VR:** later, with the [VR build](spin_offs.md#platforms).

## <a id="release"></a>Release

- Its own repo, **GPL-3.0 with the modding exception**
  ([license](spin_offs.md#license)), the same as DCA, so we can follow DCA's
  logic openly and credit it. The FO4 physics code is ours either way.
- Nexus page with requirements (F4SE, Address Library), settings, and a
  test cell with marked openings (the step map, cleaned up as a demo).
- Played on the PC game versions ([platforms](spin_offs.md#platforms)) and
  once with a [controller](swf_framework.md#controller) (crouch toggle on a
  pad).

## <a id="decisions"></a>Open decisions

- Mod name.
- Whether the first release includes swimming and power armor, or sneak
  only.
