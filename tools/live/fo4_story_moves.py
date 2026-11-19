"""What a story case does in the world as a player would: name source records, walk to one, use one.

A case names a source record as `{<plugin>:<object id>}` (the plugin the record comes from, e.g.
`{Fallout3.esm:047803}`); the step gets the running game's FormID in its place, looked up by the test DLL
wherever the plugin loads (a light plugin's id through its ledger). `walk` has the engine path the player to a
reference over the navmesh, then turns the player toward it and holds W until it arrives, so triggers fire as they
do for a player; `activate` is the player's own activation.

See: docs/fork/fo4_opening_progression_plan.md#verbs
"""
import math
import re
import time
from pathlib import Path

from fo4_import.base.ledger import ID, ONE_TO_ONE, Ledger, ledger_path
from fo4_import.base.source_ids import is_light
from fo4_import.spike.cell import MADE_SITE
from fo4_import.spike.equipment import SITES
from fo4_import.spike.npcs import ACHR_KEY
from tools.live import fo4_test_instance as T
from tools.live import game_input, hidden_launch
from tools.live.game_bridge import Bridge, BridgeError

#: `{<plugin>:<object id>}`: a source record by the plugin it comes from and its object id (hex).
SOURCE_REF = re.compile(r'\{([^{}:]+\.es[mpl]):([0-9A-Fa-f]{1,8})\}', re.I)
#: Seconds a `walk` may take when the case names none.
WALK_SECONDS = 60
#: How near (units, level distance) counts as arrived when the case names no radius.
ARRIVE_UNITS = 32
#: Seconds W is held per stride before the heading is set again.
STRIDE_SECONDS = 0.3
#: Primitive types (BGSPrimitive) measured as an ellipse around the center: sphere, ellipsoid.
ROUND = (2, 5)
#: Seconds between position checks while the engine paths the player.
PATH_POLL_SECONDS = 1.0
#: Checks without getting 5 units nearer before the engine's path counts as done.
PATH_STILL = 4
#: Strides without getting 5 units nearer before the walk counts as stuck.
STALL_STRIDES = 8
#: A stuck walk's tries before it fails: strafes around someone in the way, then the engine's path again (unstick).
UNSTICK = ('a', 'd', 'd', 'path', 'path')
#: Seconds a stuck walk waits before pathing again (a talk that just closed holds the player while its NPC finishes).
PATH_RETRY_SECONDS = 5.0
#: Seconds each sidestep holds its strafe key.
SIDESTEP_SECONDS = 0.8
#: Seconds after drawing the weapon and between shots (FO3's BB gun took every other click 1.5 s apart).
SHOT_GAP = 3.0
#: The player's eye above its position, as a share of its bounds' height.
EYE = 0.9
#: The current scale in the console's `GetScale` answer: `( REF * BASE = CURRENT ) ( 0.40 * 1.00 = 0.40 )`.
SCALE = re.compile(r'=\s*([0-9.]+)\s*\)\s*$')


class CaseFailed(Exception):
    """A step that did not hold; the message says which and why."""


def local_id(plugin: Path, ledger: Ledger, oid: int) -> int:
    """`plugin`'s own object id for source record `oid`: a placed actor's or converted gear's (equipment.SITES)
    from the ledger (its id is made, not kept), a light plugin's through the ledger, else itself."""
    made = [ledger.get(ID, MADE_SITE, ACHR_KEY.format(f'{oid:08X}'))] + [ledger.get(ID, s, oid) for s in SITES.values()]
    found = next((fid for fid in made if fid is not None), None)
    if found is not None:
        return found
    if not plugin.is_file() or not is_light(plugin):
        return oid
    kept = ledger.get(ID, ONE_TO_ONE, f'{oid:06X}')
    if kept is None:
        raise CaseFailed(f'{plugin.name} is light and its ledger has no id for {oid:06X}')
    return kept


class Refs:
    """Source records in step text (`{Plugin.esm:id}`) as the running game's FormIDs, each looked up once."""

    def __init__(self, bridge: Bridge, data: Path):
        """Looks up through `bridge`; the plugins' ledgers from `data`, each read once."""
        self.bridge, self.data, self.known, self.ledgers = bridge, Path(data), {}, {}

    def ledger(self, plugin: Path) -> Ledger:
        """`plugin`'s build ledger (empty when it has none), read once."""
        if plugin not in self.ledgers:
            self.ledgers[plugin] = Ledger(ledger_path(plugin) if plugin.is_file() else None)
        return self.ledgers[plugin]

    def fill(self, text: str) -> str:
        """`text` with each source record replaced by its FormID (hex)."""
        return SOURCE_REF.sub(lambda m: self.runtime(m.group(1), int(m.group(2), 16) & 0xFFFFFF), text)

    def runtime(self, plugin: str, oid: int) -> str:
        """The running game's FormID of `plugin`'s source record `oid`."""
        key = (plugin.lower(), oid)
        if key not in self.known:
            try:
                path = self.data / plugin
                found = self.bridge.request('form', text=f'{plugin} {local_id(path, self.ledger(path), oid):X}')
            except BridgeError as err:
                raise CaseFailed(str(err)) from err
            self.known[key] = found['form']
        return self.known[key]


def where(bridge: Bridge, ref: str = '') -> dict:
    """Reference `ref`'s (the player's when '') position, heading, 3D and cell, from the test DLL."""
    try:
        return bridge.request('where', text=ref)
    except BridgeError as err:
        raise CaseFailed(str(err)) from err


def activate(bridge: Bridge, rest: str, front) -> None:
    """`<ref>`: the player looks at it and presses E in the game window (brought to the front), so it takes the
    activate prompt and reach a player needs; `run <ref>.activate player` is the console's way.
    See: docs/fork/fo4_test_layers_plan.md#tutorial-harness
    """
    target = rest.split()[0]
    aim(bridge, target)
    front()
    hidden_launch.tap_key(hidden_launch.SCANCODES['e'])
    print('    E at %s' % target, flush=True)


def gap(me: dict, there: dict) -> float:
    """Level distance from `me` to reference `there`'s bounds, turned by its heading (0 inside): a box, or a
    round primitive's ellipse (ROUND); a reference without bounds is a point."""
    turn = math.radians(there['angle'])
    dx, dy = me['x'] - there['x'], me['y'] - there['y']
    local = (dx * math.cos(turn) - dy * math.sin(turn), dx * math.sin(turn) + dy * math.cos(turn))
    low, high = there.get('min', (0, 0)), there.get('max', (0, 0))
    if there.get('primitive') in ROUND and min(high[:2]) > 0:
        return max(math.hypot(local[0] / high[0], local[1] / high[1]) - 1, 0) * min(high[:2])
    return math.hypot(*(max(low[i] - local[i], 0, local[i] - high[i]) for i in (0, 1)))


def path(bridge: Bridge, target: str, near: float, deadline: float) -> None:
    """The engine walks the player, AI-driven, toward `target` (PathToReference: the navmesh, doors on the way)
    until within `near` of it or no nearer for PATH_STILL polls; then the player has control again."""
    lines = ['cgf "Game.SetPlayerAIDriven" 1', f'player.cf "Actor.PathToReference" {target} 1.0']
    begun, best, still = gap(where(bridge), where(bridge, target)), math.inf, 0
    try:
        print('    path: %s' % ' | '.join(repr(T.send(bridge, line).strip()) for line in lines), flush=True)
        while time.time() < deadline and still < PATH_STILL and best > near:
            time.sleep(PATH_POLL_SECONDS)
            distance = gap(where(bridge), where(bridge, target))
            best, still = (distance, 0) if distance < best - 5 else (min(best, distance), still + 1)
    finally:
        T.send(bridge, 'cgf "Game.SetPlayerAIDriven" 0')
        print('    path: %.0f units from %s, then %.0f' % (begun, target, best), flush=True)


def face(bridge: Bridge, me: dict, there: dict) -> None:
    """Turns the player toward `there` (FO4 heading: 0 north, clockwise)."""
    T.send(bridge, 'player.setangle z %.1f' % (math.degrees(math.atan2(there['x'] - me['x'], there['y'] - me['y'])) % 360))


def step_out(bridge: Bridge, target: str) -> None:
    """A player standing in trigger `target` backs out of it (S, facing it) until ARRIVE_UNITS clear, so walking in
    fires OnTriggerEnter as it does for a player coming in; a player outside it stays put."""
    me, there = where(bridge), where(bridge, target)
    strides = STALL_STRIDES if gap(me, there) == 0 else 0
    while strides and gap(me, there) <= ARRIVE_UNITS:
        face(bridge, me, there)
        hidden_launch.tap_key(hidden_launch.SCANCODES['s'], STRIDE_SECONDS)
        me, there, strides = where(bridge), where(bridge, target), strides - 1


def walk(bridge: Bridge, rest: str, front) -> None:
    """`[seconds] <ref> [radius]`: the engine paths the player to the ref (path), then it faces the ref and holds
    W, stride by stride, until within radius of its bounds or position (default: inside a trigger's primitive, or
    held at its edge by whoever stands in it, else ARRIVE_UNITS); stuck, it tries UNSTICK (unstick), then fails."""
    words = rest.split()
    seconds = float(words.pop(0)) if len(words[0]) < 8 and words[0].replace('.', '', 1).isdigit() else WALK_SECONDS
    target, radius = words[0], float(words[1]) if len(words) > 1 else None
    deadline, best, stalled, tries = time.time() + seconds, math.inf, 0, list(UNSTICK)
    near = radius if radius is not None else 0 if where(bridge, target).get('primitive') else ARRIVE_UNITS
    front()
    if near == 0:
        step_out(bridge, target)
    path(bridge, target, near, deadline)
    while True:
        me, there = where(bridge), where(bridge, target)
        distance = gap(me, there)
        if distance <= near:
            return
        if time.time() >= deadline:
            raise CaseFailed('still %.0f units from %s after %g s' % (distance, target, seconds))
        best, stalled = (distance, 0) if distance < best - 5 else (best, stalled + 1)
        if stalled >= STALL_STRIDES and there.get('primitive') and distance <= ARRIVE_UNITS:
            return
        if stalled >= STALL_STRIDES and unstick(bridge, target, (near, deadline), (me, there), tries):
            best, stalled = math.inf, 0
            continue
        if stalled >= STALL_STRIDES:
            raise CaseFailed('stuck %.0f units from %s (bounds %s to %s) at %.0f, %.0f' % (
                distance, target, there.get('min'), there.get('max'), me['x'], me['y']))
        face(bridge, me, there)
        hidden_launch.tap_key(hidden_launch.SCANCODES['w'], STRIDE_SECONDS)


def unstick(bridge: Bridge, target: str, goal: tuple, spot: tuple, tries: list) -> bool:
    """The next of a stuck walk's `tries` (UNSTICK): a sidestep from `spot` (me, there) while facing the target, or
    the engine's path to `goal` (near, deadline) again; False when none is left."""
    if not tries:
        return False
    way = tries.pop(0)
    if way == 'path':
        time.sleep(PATH_RETRY_SECONDS)
        path(bridge, target, *goal)
        return True
    face(bridge, *spot)
    hidden_launch.tap_key(hidden_launch.SCANCODES[way], SIDESTEP_SECONDS)
    return True


def middle(there: dict) -> dict:
    """The middle of reference `there`'s bounds in the world (x, y, z): the box's center turned by its heading, as
    gap() turns the other way; its position when it has no bounds."""
    low, high = there.get('min', (0, 0, 0)), there.get('max', (0, 0, 0))
    mid = [(low[i] + high[i]) / 2 for i in range(3)]
    turn = math.radians(there['angle'])
    return {'x': there['x'] + mid[0] * math.cos(turn) + mid[1] * math.sin(turn),
            'y': there['y'] - mid[0] * math.sin(turn) + mid[1] * math.cos(turn), 'z': there['z'] + mid[2]}


def scale(bridge: Bridge) -> float:
    """The player's current scale (SCALE); 1 when the console gives none."""
    found = SCALE.search(T.send(bridge, 'player.getscale'))
    return float(found.group(1)) if found else 1.0


def aim(bridge: Bridge, target: str) -> None:
    """Turns the player (heading, then pitch: FO4's angle x, down positive) from its eye (its bounds' height at its
    scale: a baby's is low) toward the middle of `target`'s bounds."""
    me, there = where(bridge), middle(where(bridge, target))
    eye = me['z'] + EYE * me.get('max', (0, 0, 0))[2] * scale(bridge)
    level = math.hypot(there['x'] - me['x'], there['y'] - me['y'])
    face(bridge, me, there)
    T.send(bridge, 'player.setangle x %.1f' % -math.degrees(math.atan2(there['z'] - eye, level)))


def shoot(bridge: Bridge, rest: str, front) -> None:
    """`[shots] <ref>`: the player draws its weapon, then aims at the ref and clicks attack, `shots` times (default
    1), SHOT_GAP seconds apart."""
    words = rest.split()
    shots, target = (int(words[0]), words[1]) if len(words) > 1 else (1, words[0])
    front()
    T.send(bridge, 'player.cf "Actor.DrawWeapon"')
    time.sleep(SHOT_GAP)
    for _ in range(shots):
        aim(bridge, target)
        game_input.send_mouse('left', hold_ms=100)
        time.sleep(SHOT_GAP)
