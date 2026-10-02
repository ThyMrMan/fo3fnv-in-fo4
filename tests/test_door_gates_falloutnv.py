"""FO3/FNV packages wait behind a locked door their actor cannot open.

See: docs/commentary/tes5_import_package.md#locked-door-gates
"""
from tes5_import.packages.door_gates_falloutnv import CellNavmesh, Door, _blocking

#: Vault101ExitDoor's base bounds (VDoor01) and placement.
_BASE = {'OBND.X1': '-78', 'OBND.Y1': '-8', 'OBND.Z1': '0', 'OBND.X2': '91', 'OBND.Y2': '46', 'OBND.Z2': '177'}
_REF = {'PosX': '10752', 'PosY': '4480', 'PosZ': '2816', 'RotZ': '3.1416'}


def _tri(x: float, y: float, z: float) -> list:
    """A 20-unit triangle centred near (x, y) at height z."""
    return [(x - 10, y - 10, z), (x + 10, y - 10, z), (x, y + 10, z)]


def test_a_door_is_over_the_triangles_its_turned_bounds_reach():
    """Turned half a circle, the exit door's bounds span x 10661-10830, y 4434-4488: not the far side's."""
    door = Door(_REF, _BASE)
    assert door.under(_tri(10773.0, 4486.0, 2816.0)) and door.under(_tri(10731.0, 4463.0, 2821.0))
    assert not door.under(_tri(10714.0, 4368.0, 2821.0))
    unturned = Door(dict(_REF, RotZ='0.0'), _BASE)
    assert door.under(_tri(10760.0, 4430.0, 2816.0)) and not unturned.under(_tri(10760.0, 4430.0, 2816.0))


def test_a_door_takes_the_floor_it_stands_on_not_the_storey_below():
    """Of two floors under the door, the one at its bottom is the door's; the cellar beneath stays open."""
    door = Door(_REF, _BASE)
    mesh = CellNavmesh([], {})
    for i, z in enumerate((2816.0, 2818.0, 2600.0)):
        mesh.points[(1, i)] = _tri(10760.0 + i, 4470.0, z)
        mesh.centre[(1, i)] = (10760.0 + i, 4470.0, z)
    mesh.next[(1, 0)].append((1, 1))
    mesh.next[(1, 1)].append((1, 0))
    assert mesh._floor_under(door) == {(1, 0), (1, 1)}


def _corridor(side_room: bool) -> CellNavmesh:
    """A line of triangles 0-1-2-3 with a door over 2, and optionally a way round it through 4."""
    mesh = CellNavmesh([], {})
    for i in range(5):
        mesh.centre[(1, i)] = (float(i), 0.0, 0.0)
    links = [(0, 1), (1, 2), (2, 3)] + ([(1, 4), (4, 3)] if side_room else [])
    for a, b in links:
        mesh.next[(1, a)].append((1, b))
        mesh.next[(1, b)].append((1, a))
    mesh.door[7] = {(1, 2)}
    return mesh


def test_a_package_waits_only_when_every_route_crosses_a_door_its_actor_cannot_open():
    """The door blocks the corridor; a way round it, or the door's key, frees the actor."""
    npc, keyed = {'FormID': '00000100'}, {'FormID': '00000100', 'Item[0].FormID': '00000AAA'}
    locks = {7: (0xAAA, 0)}
    assert _blocking(_corridor(False), (0.0, 0, 0), (3.0, 0, 0), locks, npc) == {7}
    assert _blocking(_corridor(True), (0.0, 0, 0), (3.0, 0, 0), locks, npc) == frozenset()
    assert _blocking(_corridor(False), (0.0, 0, 0), (3.0, 0, 0), locks, keyed) == frozenset()
