"""The player's FO3/FNV script packages on FO4, for the cell spike: seats instead of their special idles.

A player script package with a pose here becomes a seat
(`F3NV_PlayerControls.HoldPlayer`), initially disabled: FNV's marker stands
outside the bed and its idle moves the player onto it, so the seat moves
back from the marker to a chair seat's depth inside the edge of the
furniture behind it.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import math

from fo4_import.face.fnv_head import NifFormat
from fo4_import.spike import records as R
from fo4_import.spike.furniture import FRONT, OTHER, SEAT_DEPTH, SEAT_KEYWORDS, SIT, UNUSED_ENTRY, across, moved
from script_convert.constants import FALLOUT4_POSE_PREFIX

#: Player script package (lowercase) -> the FNV marker its seat stands on: VCG01's wake-up on the bed's edge.
SEATED_PACKAGES = {'vcg01playersection0': 'VCG01PlayerStartMarkerREF', 'vcg01playersection1': 'VCG01PlayerStartMarkerREF'}
#: Keywords letting the player sit and stand through the bed the seat lies in (NpcChairVaultSitThruGeom03's).
THROUGH_GEOMETRY = ('FurnitureAllowEnterThroughGeometry', 'FurnitureAllowExitThroughGeometry')
#: The seat's model (vanilla's NPC marker furniture) and bounds.
SEAT_MODEL = 'Markers\\InvisibleGeneric01.nif'
SEAT_BOUNDS = (-16, -16, 0, 16, 16, 32)
#: How far to either side of the marker the furniture's edge is measured (about a sitting actor's half width).
SIDE_REACH = 24.0


class Poses:
    """The player's seats: one FURN, and a reference of it per marker, made on first use; `placed` holds the REFRs.

    `markers` is {FNV EditorID: (position, rotation)}, `furniture` [((position, rotation), FNV mesh path)].
    """

    def __init__(self, builder, markers: dict, furniture: list):
        """Seats for `builder`'s plugin among the cell's `markers` and `furniture`."""
        self.builder, self.markers, self.furniture = builder, markers, furniture
        self.base, self.seats, self.placed = None, {}, b''

    def pose(self, prop: str) -> 'int | None':
        """The seat reference a `TES4Pose_<package>` property holds the player in; None when that package has none."""
        marker = SEATED_PACKAGES.get(prop[len(FALLOUT4_POSE_PREFIX):].lower())
        if marker not in self.markers:
            return None
        if marker not in self.seats:
            self.seats[marker] = self.builder.new_id(f'REFR seat {marker}')
            place = seat_place(self.markers[marker], self.furniture)
            self.placed += R.pack_refr(self.seats[marker], self._base(), *place, disabled=True)
        return self.seats[marker]

    def _base(self) -> int:
        """The seat FURN, written once."""
        if self.base is None:
            self.base = self.builder.new_id('FURN TES4PlayerSeat')
            keywords = [self.builder.keywords[k] for k in SEAT_KEYWORDS + THROUGH_GEOMETRY]
            marker = (0.0, 0.0, 0.0, 0.0, UNUSED_ENTRY | OTHER | FRONT)
            self.builder.writer.add_record('FURN', R.pack_furn(self.base, 'TES4PlayerSeat', '', SEAT_MODEL, SEAT_BOUNDS,
                                                               keywords, 0, SIT | 1, '', [marker]))
            self.builder.counts['FURN'] += 1
        return self.base


def _local(point: tuple, place: tuple) -> tuple:
    """World `point` (x, y) in the frame of a reference at `place`."""
    (fx, fy, _), (_, _, turn) = place
    c, s, dx, dy = math.cos(turn), math.sin(turn), point[0] - fx, point[1] - fy
    return dx * c - dy * s, dx * s + dy * c


def _world(point: tuple, place: tuple) -> tuple:
    """Local `point` (x, y) of a reference at `place` in the world."""
    (fx, fy, _), (_, _, turn) = place
    c, s = math.cos(turn), math.sin(turn)
    return fx + point[0] * c + point[1] * s, fy - point[0] * s + point[1] * c


def _vertices(path: str) -> list:
    """(x, y) of every vertex of an FNV mesh, shape translations applied."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return [(v.x + b.translation.x, v.y + b.translation.y) for b in data.blocks
            if isinstance(b, (NifFormat.NiTriShape, NifFormat.NiTriStrips)) and b.data for v in b.data.vertices]


def _gap(point: tuple, vertices: list) -> float:
    """How far `point` lies outside the box of `vertices`."""
    xs, ys = [v[0] for v in vertices], [v[1] for v in vertices]
    return math.hypot(max(min(xs) - point[0], 0, point[0] - max(xs)), max(min(ys) - point[1], 0, point[1] - max(ys)))


def seat_place(marker: tuple, furniture: list) -> tuple:
    """(position, rotation) of the seat for `marker`: moved along its facing to SEAT_DEPTH inside the mesh edge of
    the nearest furniture, measured within SIDE_REACH to either side; the marker itself when there is none.
    """
    if not furniture:
        return marker
    (mx, my, mz), rot = marker
    meshes = [(place, _vertices(path)) for place, path in furniture]
    place, vertices = min(meshes, key=lambda m: _gap(_local((mx, my), m[0]), m[1]))
    local, facing = _local((mx, my), place), rot[2] - place[1][2]
    side = facing + math.pi / 2
    edge = max(across(v, facing) for v in vertices if abs(across(v, side) - across(local, side)) < SIDE_REACH)
    x, y = _world(moved(local, facing, edge - SEAT_DEPTH), place)
    return (x, y, mz), rot
