"""FNV furniture as FO4 FURN records, for the cell spike.

FNV marks each way into a seat or bed in the mesh (BSFurnitureMarker: offset,
heading toward the furniture, animation slot) and activates some of them in
the record (MNAM low bits). FO4 keeps one marker per seat in the record
(SNAM: offset, heading the actor faces, entry sides) and picks animations by
keyword. FNV's markers stand outside the furniture: a seat is FNV's
sit-from-front marker turned to face out and moved onto the seat, entered
from the sides of its active markers; a sleeper lies at FNV's sleep marker
moved to the middle of its lane across the bed.

See: docs/fork/fo4_spikes.md#spike-2-furniture
"""

import math

from fo4_import.face.fnv_head import NifFormat
from fo4_import.spike import records as R

#: FNV marker animation slots: sleep entered from the right and left, sit entered from the left, right and front.
SLEEP_RIGHT, SLEEP_LEFT, SIT_LEFT, SIT_RIGHT, SIT_FRONT = 1, 2, 11, 12, 14
#: FO4 SNAM entry sides.
FRONT, RIGHT, LEFT = 0x1, 0x4, 0x8
#: SNAM entry byte: the unused bits vanilla sets beside the sides, and Other, which it adds to seats with Front.
UNUSED_ENTRY, OTHER = 0xE0, 0x10
#: MNAM bits: FNV's and FO4's sit and sleep furniture flags (same bits), and FO4 Must Exit to Talk on beds.
SIT, SLEEP, MUST_EXIT_TO_TALK = 0x40000000, 0x80000000, 0x08000000
#: Record flag vanilla beds carry: Must Exit To Talk.
BED_RECORD_FLAGS = 0x10000000
#: Vanilla keywords: chairs and couches (sit animations, relaxation), beds (sleep, bed animations).
SEAT_KEYWORDS = ('AnimFurnChairSitAnims', 'FurnitureClassRelaxation')
BED_KEYWORDS = ('IsSleepFurniture', 'AnimFurnBedAnims')
#: The marker model vanilla beds name.
BED_MARKER = 'Markers\\SleepBed.nif'
#: How far behind its front edge vanilla puts a chair's seat marker (median of 129 sit markers).
SEAT_DEPTH = 18.0
#: FNV marker headings are in thousandths of a radian.
HEADING_UNIT = 0.001


def markers(path: str) -> list:
    """FNV mesh furniture markers in file order: (x, y, z, heading in radians, animation slot)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return [(p.offset.x, p.offset.y, p.offset.z, p.orientation * HEADING_UNIT, p.position_ref_1)
            for b in data.blocks if isinstance(b, NifFormat.BSFurnitureMarker) for p in b.positions]


def _right(heading: float) -> tuple:
    """The actor's right, facing `heading`."""
    return math.cos(heading), -math.sin(heading)


def seats(marks: list, active: int, bounds: tuple) -> list:
    """FO4 seat markers (x, y, z, heading, entry byte): FNV's sit-from-front markers, entered from their active ones.

    FNV's marker is where the actor stands, in front of the seat; FO4's sits
    SEAT_DEPTH behind the front of `bounds`, facing out.
    """
    fronts = [m for m in marks if m[4] == SIT_FRONT]
    sides = [0] * len(fronts)
    for i, (mx, my, _, _, slot) in enumerate(marks):
        if not fronts or not active >> i & 1 or slot not in (SIT_FRONT, SIT_LEFT, SIT_RIGHT):
            continue
        k = min(range(len(fronts)), key=lambda j: (fronts[j][0] - mx) ** 2 + (fronts[j][1] - my) ** 2)
        x, y, _, heading, _ = fronts[k]
        right = _right(heading + math.pi)
        sides[k] |= FRONT if slot == SIT_FRONT else RIGHT if (mx - x) * right[0] + (my - y) * right[1] > 0 else LEFT
    out = []
    for (x, y, z, heading, _), side in zip(fronts, sides):
        facing = (heading + math.pi) % math.tau
        if side:
            out.append(moved((x, y), facing, max(_corners(bounds, facing)) - SEAT_DEPTH)
                       + (z, facing, UNUSED_ENTRY | (OTHER if side & FRONT else 0) | side))
    return out


def _corners(bounds: tuple, facing: float) -> list:
    """How far each corner of `bounds` lies along `facing`."""
    return [across((bx, by), facing) for bx in (bounds[0], bounds[3]) for by in (bounds[1], bounds[4])]


def moved(point: tuple, facing: float, depth: float) -> tuple:
    """`point` moved along `facing` to `across` value `depth`, sideways kept."""
    ax, ay = math.sin(facing), math.cos(facing)
    along = point[0] * ay - point[1] * ax
    return depth * ax + along * ay, depth * ay - along * ax


def sleepers(marks: list, active: int, bounds: tuple) -> list:
    """FO4 bed markers (x, y, z, heading, entry byte) of FNV's active sleep markers, one lane each across `bounds`."""
    sleep = [(m, (m[3] + math.pi if m[4] == SLEEP_RIGHT else m[3]) % math.tau, i)
             for i, m in enumerate(marks) if m[4] in (SLEEP_RIGHT, SLEEP_LEFT)]
    out = []
    for lane, ((x, y, z, _, slot), facing, i) in enumerate(sorted(sleep, key=lambda s: across(s[0], s[1]))):
        if not active >> i & 1:
            continue
        corners = _corners(bounds, facing)
        depth = min(corners) + (max(corners) - min(corners)) * (lane + 0.5) / len(sleep)
        out.append(moved((x, y), facing, depth) + (z, facing, UNUSED_ENTRY | (RIGHT if slot == SLEEP_RIGHT else LEFT)))
    return out


def across(point: tuple, facing: float) -> float:
    """How far `point` lies along `facing`."""
    return point[0] * math.sin(facing) + point[1] * math.cos(facing)


def furniture(fid: int, rec: dict, model: str, bounds: tuple, marks: list, keyword_ids: dict) -> bytes:
    """The FO4 FURN of FNV furniture `rec` with converted `model` and `bounds` and its mesh's `marks`."""
    active = int(rec.get('MNAM.Flags', 0))
    bed = sleepers(marks, active, bounds)
    placed = bed or seats(marks, active, bounds)
    flags = (SLEEP | MUST_EXIT_TO_TALK) if bed else SIT
    keywords = [keyword_ids[k] for k in (BED_KEYWORDS if bed else SEAT_KEYWORDS)]
    return R.pack_furn(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds, keywords,
                       BED_RECORD_FLAGS if bed else 0, flags | (1 << len(placed)) - 1,
                       BED_MARKER if bed else '', placed)
