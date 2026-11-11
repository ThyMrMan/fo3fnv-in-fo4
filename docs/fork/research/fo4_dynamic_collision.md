# Dynamic character collision for Fallout 4 (parked idea)

Status: **parked for future development** (2026-10-08). Not needed for the
FNV conversion, which uses a fixed smaller skeleton box instead
([player collision](fo4_target.md#player-collision)). Kept because the
engine findings make a general Fallout 4 mod practical. The mod plan,
with spikes, is [dynamic_collision_mod.md](../dynamic_collision_mod.md).

## The idea

An F4SE plugin that resizes an actor's movement collision at runtime, as
Skyrim's
[DynamicCollisionAdjustment](https://github.com/ersh1/DynamicCollisionAdjustment)
and [VariadicCollisionDynamics](https://github.com/legendman89/VariadicCollisionDynamics)
do. No Fallout 4 equivalent was found (searched 2026-10-08): height mods
scale the look, not the collision, and `setscale` does not change the
player's collision.

Gameplay it would open up:

- crouching or crawling under low openings and through vents;
- collision that follows the actor's real size (scaled NPCs, small or
  large races, power armor);
- per-situation shapes (sneaking, swimming, ladders), driven by state or by
  Papyrus;
- a player height option that changes collision as well as the look.

## What the engine does (Fallout4.exe 1.11.240)

RVAs from `Fallout4.exe.unpacked.exe`; full reading in
[fo4_target.md](fo4_target.md#player-collision).

- **Creation.** `0xc5f6b4` builds the controller when the actor's 3D loads:
  `bhkCharProxyController` for the player, `bhkCharRigidBodyController` for
  NPCs. The setup is filled by `0xcbfdb0(actor, setup,
  bUseCustomCCShapes)`; the actor's scale goes in setup `+0x4c`
  (`0x4ff850`, reference scale times the base's height).
- **Shape.** `0x1892de0` looks for a layer-30 capsule on the 3D
  (`0x189c560`). Human actors do not end up using it (editing it changes
  nothing, played). They get the fallback: a compound of three capsules
  (`0x189ee10`) from the 3D's `BSBound` half extents times the scale, or
  from the constants 23, 17.5, 64.
- **Proved in game:** shortening the human skeleton's `BSBound` shortens the
  player's collision (top 128 to 98 and to 115, played).
- **Scale is pinned for the player.** `setscale` (even with a reload) does
  not change it. The setup sets the scale to 1.0 when the actor has default
  object 202's keyword (table `0x30e78e0`, `+0x670`) and its virtual `0x3f0`
  is false. Which keyword that is was not read.
- **Shape switching already exists.** The controller has two shape slots
  (`+0x360`, `+0x368` from its base) and an active index (`+0x354`). When
  the setup asks for the other index, `0x1899320` swaps shapes through the
  controller's own virtuals (`0x198`, then `0x218` with the new shape). A
  plugin can use that path instead of building its own.
- **Headroom.** The controller needs about 13–17 units more than its shape
  (128 box, 141–145 measured with the [step map](../fo4_spikes.md#step-map)).
  Where that margin comes from (likely a step-up cast) was not read.
- **Unused keyword.** `ScaleCustomCharController_DO` (`00249F53`) scales
  only the custom capsule, which human actors do not use.

## What a mod would still need

- Find what the second shape slot is for, and what selects it.
- Find the margin, so a requested height turns into a known headroom.
- Hooks: on controller creation and on state changes (sneak, swim, power
  armor), plus a Papyrus API.
- Address Library IDs for both live runtimes (old-gen 1.10.163 and
  next-gen 1.10.984+/1.11), as CommonLibF4 targets.
- Testing: reuse the step map (`fo4_import.spike.step_map`), whose H and
  HS stations measure headroom directly.
