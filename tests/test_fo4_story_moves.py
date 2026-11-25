"""The story cases' world steps without a game: source records filled in, walking, activating."""
import math

import pytest

from fo4_import.base.ledger import ID, Ledger, ledger_path
from fo4_import.spike.cell import MADE_SITE
from fo4_import.spike.npcs import ACHR_KEY
from tools.live import fo4_story_moves as M
from tools.live import hidden_launch
from tools.live.game_bridge import BridgeError


class World:
    """A bridge for a flat room: the player at `me`, refs at fixed spots; holding W moves the player one stride
    the way it faces, unless a wall at y = `wall` stops it."""

    def __init__(self, refs: dict, wall: float = math.inf):
        """`refs`: {FormID hex: (x, y)}; the player starts at 0, 0 facing north."""
        self.me, self.angle, self.refs, self.wall, self.lines, self.track = [0.0, 0.0], 0.0, refs, wall, [], []
        self.crosshair = lambda: 'Activate'

    def request(self, cmd: str, text: str = '', command: str = '') -> dict:
        """`form`, `where`, `invoke` (the HUD: `crosshair`'s state, name 'Desk') and `console` as the test DLL
        answers them."""
        if cmd == 'invoke':
            return {'result': self.crosshair() if text.endswith('requestedState') else 'Desk'}
        if cmd == 'form':
            plugin, oid = text.split()
            return {'form': '%02X%06X' % (0x0B, int(oid, 16)), 'type': 'REFR'}
        if cmd == 'where':
            x, y = self.me if not text else self.refs[text]
            return {'x': x, 'y': y, 'z': 0.0, 'angle': self.angle, 'loaded': True, 'cell': '00000001'}
        self.lines.append(command)
        if command.startswith('player.setangle z'):
            self.angle = float(command.split()[-1])
        return {'output': ''}

    def stride(self, scan: int, seconds: float) -> None:
        """W moves 20 units the way the player faces, S back; up to the wall."""
        rad, step = math.radians(self.angle), -20 if scan == hidden_launch.SCANCODES['s'] else 20
        self.me = [self.me[0] + step * math.sin(rad), min(self.me[1] + step * math.cos(rad), self.wall)]
        self.track.append(tuple(self.me))


@pytest.fixture
def no_console(monkeypatch):
    """T.send answers from the fake console; the path polls without waiting."""
    monkeypatch.setattr(M.T, 'send', lambda bridge, line: bridge.request('console', command=line)['output'])
    monkeypatch.setattr(M, 'PATH_POLL_SECONDS', 0)
    monkeypatch.setattr(M, 'PATH_RETRY_SECONDS', 0)
    monkeypatch.setattr(M, 'HUD_SECONDS', 0)


def test_source_records_become_the_running_games_formids(tmp_path):
    """`{Plugin.esm:id}` is looked up once per record through the bridge's `form`."""
    asked = []

    class Bridge:
        """Answers `form` and counts the asks."""

        def request(self, cmd, text=''):
            """The plugin at index 0x0B."""
            asked.append(text)
            return {'form': '0B' + text.split()[1].zfill(6)}

    refs = M.Refs(Bridge(), tmp_path)
    assert refs.fill('walk {Fallout3.esm:02EA54} 64; {Fallout3.esm:2ea54}') == 'walk 0B02EA54 64; 0B02EA54'
    assert asked == ['Fallout3.esm 2EA54']


def test_converted_gear_is_found_at_its_types_ledger_site(tmp_path):
    """ArmorVault101Security (01CBDD) is built under a made id kept at FNV ARMO; a kept record stays itself."""
    (tmp_path / 'Fallout3.esm').write_bytes(b'TES4' + bytes(20))
    ledger = Ledger(None)
    ledger.put(ID, 'FNV ARMO', 0x1CBDD, 0xE4608B)
    assert M.local_id(tmp_path / 'Fallout3.esm', ledger, 0x1CBDD) == 0xE4608B
    assert M.local_id(tmp_path / 'Fallout3.esm', ledger, 0x47803) == 0x47803


def test_a_placed_actor_is_found_through_the_build_ledger(tmp_path):
    """An actor reference's FormID is made, so the ledger's id is asked for, not the source's."""
    (tmp_path / 'Fallout3.esm').write_bytes(b'TES4' + bytes(20))
    ledger = Ledger(ledger_path(tmp_path / 'Fallout3.esm'))
    ledger.put(ID, MADE_SITE, ACHR_KEY.format('000309A8'), 0x2BF4F0)
    ledger.save()

    class Bridge:
        """Echoes the asked id at index 0x0B."""

        def request(self, cmd, text=''):
            """The plugin at index 0x0B."""
            return {'form': '0B' + text.split()[1].zfill(6)}

    assert M.Refs(Bridge(), tmp_path).fill('{Fallout3.esm:0309A8} {Fallout3.esm:02EA54}') == '0B2BF4F0 0B02EA54'


def test_a_record_the_game_lacks_fails_the_step(tmp_path):
    """E_NOFORM from the DLL is a case failure."""

    class Bridge:
        """Knows no form."""

        def request(self, cmd, text=''):
            """Always E_NOFORM."""
            raise BridgeError('no form', 'E_NOFORM')

    with pytest.raises(M.CaseFailed):
        M.Refs(Bridge(), tmp_path).fill('{Fallout3.esm:1}')


def test_walk_faces_the_target_and_strides_until_there(monkeypatch, no_console):
    """The heading points at the target (FO4: 0 is north, clockwise); the walk ends within the radius."""
    world = World({'0B000001': (300.0, 400.0)})
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001', lambda: None)
    assert math.dist(world.me, (300.0, 400.0)) <= M.ARRIVE_UNITS
    assert world.lines[3] == 'player.setangle z 36.9'


def test_walk_has_the_engine_path_the_player_first(monkeypatch, no_console):
    """AI-driven, PathToReference to the ref, then the player's control back, before any stride."""
    world = World({'0B000001': (0.0, 400.0)})
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001', lambda: None)
    assert world.lines[:3] == ['cgf "Game.SetPlayerAIDriven" 1', 'player.cf "Actor.PathToReference" 0B000001 1.0',
                               'cgf "Game.SetPlayerAIDriven" 0']


def test_an_all_digit_formid_is_the_walks_target_not_its_seconds(monkeypatch, no_console):
    """`walk 08047803 64`: the FormID, then the radius."""
    world = World({'08047803': (0.0, 100.0)})
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '08047803 64', lambda: None)
    assert world.me[1] >= 100.0 - 64


def test_walk_fails_when_blocked(monkeypatch, no_console):
    """A wall short of the target stops the walk with where it got stuck."""
    world = World({'0B000001': (0.0, 400.0)}, wall=100.0)
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    with pytest.raises(M.CaseFailed, match='stuck 300 units'):
        M.walk(world, '0B000001 16', lambda: None)


class Crowd(World):
    """A room with someone standing at x -30..30 just short of y 100; A and D strafe 40 units left or right."""

    def stride(self, scan: int, seconds: float) -> None:
        """W moves 20 north unless the stander is in the way; A and D move sideways (facing north)."""
        side = {hidden_launch.SCANCODES['a']: -40, hidden_launch.SCANCODES['d']: 40}.get(scan)
        if side is not None:
            self.me = [self.me[0] + side, self.me[1]]
        elif abs(self.me[0]) >= 30 or self.me[1] + 20 < 80:
            self.me = [self.me[0], self.me[1] + 20]


def test_a_stuck_walk_sidesteps_around_someone_in_the_way(monkeypatch, no_console):
    """The Overseer between the player and Mrs. Palmer: stuck behind him, the player strafes left and walks on."""
    world = Crowd({'0B000001': (0.0, 200.0)})
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001 64', lambda: None)
    assert world.me[0] == -40 and world.me[1] >= 200 - 64 - 40


class Held(World):
    """A player held in place (a talk just closed) until the engine is asked to path it a second time."""

    def __init__(self, refs: dict):
        """Held from the start; `paths` counts PathToReference lines."""
        super().__init__(refs)
        self.paths = 0

    def request(self, cmd: str, text: str = '', command: str = '') -> dict:
        """As World, counting the paths asked for."""
        self.paths += 'PathToReference' in command
        return super().request(cmd, text, command)

    def stride(self, scan: int, seconds: float) -> None:
        """No key moves the player until the second path."""
        if self.paths >= 2:
            super().stride(scan, seconds)


def test_a_held_player_is_pathed_again_before_the_walk_fails(monkeypatch, no_console):
    """After Beatrice's poem the player stood still; the sidesteps do nothing, the second path frees it."""
    world = Held({'0B000001': (0.0, 200.0)})
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001 64', lambda: None)
    assert world.paths == 2 and world.me[1] >= 200 - 64 - 20


@pytest.mark.parametrize('angle, me, expected', [
    (0.0, (10.0, 20.0), 0.0),
    (0.0, (100.0, 0.0), 30.0),
    (0.0, (0.0, -100.0), 65.0),
    (90.0, (0.0, -100.0), 30.0),
    (90.0, (-100.0, 0.0), 65.0),
])
def test_gap_is_to_the_box_turned_by_the_heading(angle, me, expected):
    """A 140 x 70 box; turned 90 degrees, its long side runs north-south."""
    there = {'x': 0.0, 'y': 0.0, 'angle': angle, 'min': [-70.0, -35.0, 0.0], 'max': [70.0, 35.0, 0.0]}
    assert M.gap({'x': me[0], 'y': me[1]}, there) == pytest.approx(expected)


def test_gap_to_a_sphere_is_radial():
    """A sphere of radius 69: its box's corner is outside it."""
    there = {'x': 0.0, 'y': 0.0, 'angle': 0.0, 'primitive': 2, 'min': [-69.0] * 3, 'max': [69.0] * 3}
    assert M.gap({'x': 60.0, 'y': 60.0}, there) == pytest.approx(math.hypot(60, 60) - 69)
    assert M.gap({'x': 10.0, 'y': 0.0}, there) == 0


def test_a_walk_into_a_trigger_ends_at_its_box(monkeypatch, no_console):
    """The player only has to get inside the trigger's box, not to its center."""
    world = World({'0B000001': (0.0, 400.0)}, wall=345.0)
    world.request = lambda cmd, text='', command='', inner=world.request: (
        {**inner(cmd, text, command), 'primitive': 1, 'min': [-70.0, -70.0, -70.0], 'max': [70.0, 70.0, 70.0]}
        if cmd == 'where' and text else inner(cmd, text, command))
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001', lambda: None)
    assert 400.0 - 70.0 <= world.me[1] <= 345.0


def test_a_walk_into_a_trigger_the_player_stands_in_steps_out_and_back(monkeypatch, no_console):
    """Entering is what fires: the player backs out past ARRIVE_UNITS, then walks in again."""
    world = World({'0B000001': (0.0, 30.0)})
    world.request = lambda cmd, text='', command='', inner=world.request: (
        {**inner(cmd, text, command), 'primitive': 1, 'min': [-100.0, -40.0, -9.0], 'max': [100.0, 40.0, 9.0]}
        if cmd == 'where' and text else inner(cmd, text, command))
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001', lambda: None)
    assert min(y for _, y in world.track) < 30.0 - 40.0 - M.ARRIVE_UNITS and world.me[1] >= 30.0 - 40.0


def test_a_walk_held_at_a_triggers_edge_has_arrived(monkeypatch, no_console):
    """Someone standing in the trigger stops the player at its edge: within ARRIVE_UNITS that is arrival."""
    world = World({'0B000001': (0.0, 400.0)}, wall=320.0)
    world.request = lambda cmd, text='', command='', inner=world.request: (
        {**inner(cmd, text, command), 'primitive': 2, 'min': [-69.0] * 3, 'max': [69.0] * 3}
        if cmd == 'where' and text else inner(cmd, text, command))
    monkeypatch.setattr(hidden_launch, 'tap_key', world.stride)
    M.walk(world, '0B000001', lambda: None)
    assert world.me[1] == 320.0


def test_activate_looks_at_the_ref_and_presses_e(monkeypatch, no_console):
    """The player faces the ref and presses E, as a player would; no console activation."""
    world = World({'0B047803': (100.0, 0.0)})
    pressed = []
    monkeypatch.setattr(hidden_launch, 'tap_key', lambda scan, seconds=0: pressed.append(scan))
    M.activate(world, '0B047803', lambda: None)
    assert pressed == [hidden_launch.SCANCODES['e']]
    assert 'player.setangle z 90.0' in world.lines
    assert not any('.activate' in line for line in world.lines)


def test_activate_looks_across_the_bounds_until_the_prompt_shows(monkeypatch, no_console):
    """CG03's school desk: its bounds' middle is the air between top and seat, so the crosshair shows no prompt
    there; the player looks further into the bounds until it does, then presses E once."""
    world = World({'0B02B793': (100.0, 0.0)})
    world.request = lambda cmd, text='', command='', inner=world.request: (
        {**inner(cmd, text, command), 'min': [-26.0, -21.0, -34.0], 'max': [26.0, 75.0, 32.0]}
        if cmd == 'where' and text else inner(cmd, text, command))
    world.crosshair = lambda: 'Activate' if sum('setangle x' in line for line in world.lines) >= 3 else 'Standard'
    pressed = []
    monkeypatch.setattr(hidden_launch, 'tap_key', lambda scan, seconds=0: pressed.append(scan))
    M.activate(world, '0B02B793', lambda: None)
    assert pressed == [hidden_launch.SCANCODES['e']]
    assert sum('setangle x' in line for line in world.lines) == 3


def test_activate_keeps_the_middle_when_the_hud_cannot_be_read(monkeypatch, no_console):
    """No HUD answer: the player looks at the middle once, as before, and presses E."""
    world = World({'0B000001': (100.0, 0.0)})
    inner = world.request

    def request(cmd, text='', command=''):
        """The HUD path is missing."""
        if cmd == 'invoke':
            raise BridgeError('HUDMenu has no object CenterGroup_mc', 'E_NOPATH')
        return inner(cmd, text, command)

    world.request = request
    monkeypatch.setattr(hidden_launch, 'tap_key', lambda scan, seconds=0: None)
    M.activate(world, '0B000001', lambda: None)
    assert sum('setangle x' in line for line in world.lines) == 1


def test_the_middle_of_a_box_is_turned_by_its_heading():
    """CG01's playpen gate: hinged at its origin, 64 units long, turned east."""
    gate = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'angle': 90.0, 'min': [-2.0, -2.0, 2.0], 'max': [2.0, 64.0, 51.0]}
    there = M.inside(gate)
    assert (there['x'], there['y'], there['z']) == pytest.approx((31.0, 0.0, 26.5))


def test_a_scaled_down_player_aims_from_its_own_eye(no_console, monkeypatch):
    """The baby in CG01 (scale 0.40): its eye is 0.4 of the bounds' height, so a gate at that height is level."""
    world = World({'0B000001': (100.0, 0.0)})
    world.request = lambda cmd, text='', command='', inner=world.request: (
        {**inner(cmd, text, command), 'max': [10.0, 10.0, 100.0]} if cmd == 'where' and not text
        else {**inner(cmd, text, command), 'z': 100.0 * M.EYE * 0.4} if cmd == 'where'
        else {'output': '( REF * BASE = CURRENT ) ( 0.40 * 1.00 = 0.40 )'} if command == 'player.getscale'
        else inner(cmd, text, command))
    M.aim(world, '0B000001')
    assert any(line in world.lines for line in ('player.setangle x -0.0', 'player.setangle x 0.0'))


def test_shoot_aims_down_at_a_lower_target_and_clicks_each_shot(no_console, monkeypatch):
    """A target 100 units off and 100 below the eye: heading east, pitch 45 down, one click per shot."""
    world = World({"0B000002": (100.0, 0.0)})
    world.request = lambda cmd, text="", command="", inner=world.request: (
        {**inner(cmd, text, command), "max": [10.0, 10.0, 100.0 / M.EYE]} if cmd == "where" and not text
        else inner(cmd, text, command))
    clicks = []
    monkeypatch.setattr(M.game_input, "send_mouse", lambda button, hold_ms: clicks.append(button))
    monkeypatch.setattr(M.time, "sleep", lambda seconds: None)
    M.shoot(world, "2 0B000002", lambda: None)
    assert clicks == ["left", "left"]
    assert "player.setangle z 90.0" in world.lines and "player.setangle x 45.0" in world.lines
