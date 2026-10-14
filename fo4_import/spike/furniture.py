"""FNV furniture as FO4 FURN records, for the cell spike.

FNV marks each way into a seat or bed in the mesh (BSFurnitureMarker: offset,
heading toward the furniture, animation slot) and activates some of them in
the record (MNAM low bits). FO4 keeps one marker per seat in the record
(SNAM: offset, heading the actor faces, entry sides) and picks animations by
keyword. FNV's markers stand outside the furniture: a seat is FNV's
sit-from-front marker turned to face out and moved onto the seat, entered
from the sides of its active markers (a chair FNV enters only from the sides,
such as one pushed under a table, gets the front marker midway between them);
a stool, a floor sit or a restrained sit sits where FNV's enter animation
leaves the actor, with vanilla's keywords for it; a sleeper lies at FNV's sleep marker
moved to the middle of its lane across the bed. Standing furniture (a wall
lean, a special idle such as tending bar) keeps FNV's markers and takes the
keywords of vanilla's equivalent, so a package can send an actor to it.

See: docs/fork/fo4_spikes.md#spike-2-furniture
"""

import math
from pathlib import Path

from fo4_import.face.fnv_head import NifFormat
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R

#: FNV marker animation slots: sit entered from the left, right and front.
SIT_LEFT, SIT_RIGHT, SIT_FRONT = 11, 12, 14
#: FNV sleep slots entered from the right and left (a bed's 1 and 2, a bedroll's 4 and 3, the floor's 6 and 5).
SLEEP_RIGHT, SLEEP_LEFT = (1, 4, 6), (2, 3, 5)
#: FNV sleep slots on the floor (bedrolls, mattresses, bare ground).
SLEEP_FLOOR = (3, 4, 5, 6)
#: FO4 SNAM entry sides.
FRONT, RIGHT, LEFT = 0x1, 0x4, 0x8
#: SNAM entry byte: the unused bits vanilla sets beside the sides, and Other, which it adds to seats with Front.
UNUSED_ENTRY, OTHER = 0xE0, 0x10
#: MNAM bits: FNV's and FO4's sit and sleep furniture flags (same bits), and FO4 Must Exit to Talk on beds.
SIT, SLEEP, MUST_EXIT_TO_TALK = 0x40000000, 0x80000000, 0x08000000
#: Record flag vanilla beds carry: Must Exit To Talk.
BED_RECORD_FLAGS = 0x10000000
#: Vanilla keywords: chairs and couches (sit animations, relaxation), beds and floor beds (sleep, their animations).
SEAT_KEYWORDS = ('AnimFurnChairSitAnims', 'FurnitureClassRelaxation')
BED_KEYWORDS = ('IsSleepFurniture', 'AnimFurnBedAnims')
FLOOR_BED_KEYWORDS = ('IsSleepFurniture', 'AnimFurnFloorBedAnims')
#: A floor bed's marker turned from a bed's: vanilla floor beds face along the mattress (0), beds across it (pi/2).
FLOOR_TURN = math.pi / 2
#: The marker models vanilla beds and floor beds name.
BED_MARKER, FLOOR_BED_MARKER = 'Markers\\SleepBed.nif', 'Markers\\MarkerSleep01.nif'
#: How far behind its front edge vanilla puts a chair's seat marker (median of 129 sit markers).
SEAT_DEPTH = 18.0
#: FNV marker headings are in thousandths of a radian.
HEADING_UNIT = 0.001
#: FNV marker slots of standing furniture: wall leaning, and the special idle (an IDLE naming the furniture plays).
WALL_LEAN, SPECIAL = 19, 22
#: Standing furniture's FO4 keywords, as vanilla's NPCInvWallLean01: by FNV marker slot.
SLOT_KEYWORDS = {WALL_LEAN: ('AnimFurnWallLean', 'FurnitureClassRelaxation', 'FurnitureSpecial',
                             'FurnitureScaleActorToOne')}
#: A special idle's FO4 keywords by the FNV idle group whose IsCurrentFurnitureObj names it (NPCBartender, NPCPushUps).
IDLE_KEYWORDS = {'BarKeeping': ('FurnitureScaleActorToOne', 'AnimFurnBartender', 'FurnitureClassWork', 'FurnitureSpecial'),
                 'PushUps': ('AnimFurnPushUps',)}
#: SNAM entry byte of vanilla's standing furniture (NPCBartender, NPCPushUps): every side.
ANY_ENTRY = 0xFF
#: FNV marker slots (FNV's GetFurnitureMarkerID idles): stool sitting, floor sitting, restrained sitting.
SIT_STOOL, FLOOR_SIT, RESTRAINED_SIT = 15, 17, 18
#: Their FO4 (keywords, marker model), as vanilla's NpcStoolDinerIntSit01, NPCInvGroundSit, NPCPrisonerFloorSit.
SLOT_SEATS = {SIT_STOOL: (('AnimFurnBarStool', 'AnimFurnAllowEating', 'FurnitureClassRelaxation',
                           'FurnitureScaleActorToOne'), 'Markers\\MarkerBarHeight.nif'),
              FLOOR_SIT: (('AnimFurnGroundSitAnims', 'FurnitureClassRelaxation'), 'Markers\\MarkerGroundSit01.nif'),
              RESTRAINED_SIT: (('AnimFurnPrisonerFloorSit',), 'Markers\\MarkerPrisonerFloorSit.nif')}
#: The FNV animation (under meshes) that takes an actor from each slot's marker onto the seat.
ENTER_ANIMS = {SIT_STOOL: 'characters\\_male\\idleanims\\stoolenter.kf',
               FLOOR_SIT: 'characters\\_male\\idleanims\\sitfloorenter.kf',
               RESTRAINED_SIT: 'characters\\_male\\idleanims\\restrainedsitenter.kf'}
#: FNV furniture animations turn the actor in quarter turns; the seated pose adds a few degrees of twist.
QUARTER = math.pi / 2


def markers(path: str) -> list:
    """FNV mesh furniture markers in file order: (x, y, z, heading in radians, animation slot)."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return [(p.offset.x, p.offset.y, p.offset.z, p.orientation * HEADING_UNIT, p.position_ref_1)
            for b in data.blocks if isinstance(b, NifFormat.BSFurnitureMarker) for p in b.positions]


def enter_motion(path: str) -> tuple:
    """(right, forward, turn) an FNV enter animation moves the actor from its marker: Bip01's travel in the
    actor's frame and Bip01 NonAccum's turn, to the nearest quarter turn."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    nodes = {cb.get_node_name().decode(): cb.interpolator for b in data.roots
             if isinstance(b, NifFormat.NiControllerSequence) for cb in b.controlled_blocks}
    moves, turns = list(nodes['Bip01'].get_translations()), list(nodes['Bip01 NonAccum'].get_rotations())
    yaws = [math.atan2(*_rotated(q, (0.0, 1.0, 0.0))[:2]) for q in (turns[0], turns[-1])]
    return (moves[-1][0] - moves[0][0], moves[-1][1] - moves[0][1],
            round((yaws[1] - yaws[0]) / QUARTER) * QUARTER % math.tau)


def enter_motions(meshes_dir) -> dict:
    """{marker slot: enter_motion()} of the ENTER_ANIMS under FNV's `meshes_dir`."""
    paths = {slot: Path(meshes_dir) / anim for slot, anim in ENTER_ANIMS.items()}
    return {slot: enter_motion(str(path)) for slot, path in paths.items() if path.is_file()}


def _rotated(q: tuple, v: tuple) -> tuple:
    """Vector `v` rotated by quaternion `q` (w, x, y, z)."""
    w, qv = q[0], q[1:]
    c = _cross(qv, v)
    return tuple(a + 2 * (w * b + d) for a, b, d in zip(v, c, _cross(qv, c)))


def _cross(a: tuple, b: tuple) -> tuple:
    """a x b."""
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _right(heading: float) -> tuple:
    """The actor's right, facing `heading`."""
    return math.cos(heading), -math.sin(heading)


def _side_fronts(marks: list, bounds: tuple) -> list:
    """Sit-from-front markers of a seat FNV enters only from its sides: one midway between each left marker and the
    nearest right one facing the same seat, a lone side marker's on its line nearest the middle of `bounds`.

    A side marker faces the seat; the seated actor faces a quarter turn from
    it (Chair_LeftEnter.kf and Chair_RightEnter.kf turn -90 and +90 degrees).
    """
    sides = [(m, (m[3] + (-QUARTER if m[4] == SIT_LEFT else QUARTER)) % math.tau)
             for m in marks if m[4] in (SIT_LEFT, SIT_RIGHT)]
    lefts = [s for s in sides if s[0][4] == SIT_LEFT]
    rights = [s for s in sides if s[0][4] == SIT_RIGHT]
    out = []
    for (x, y, z, _, _), facing in lefts:
        match = [r for r in rights if math.isclose(math.cos(r[1] - facing), 1.0, abs_tol=1e-3)]
        if match:
            r = min(match, key=lambda s: (s[0][0] - x) ** 2 + (s[0][1] - y) ** 2)
            rights.remove(r)
            out.append(((x + r[0][0]) / 2, (y + r[0][1]) / 2, z, (facing + math.pi) % math.tau, SIT_FRONT))
            continue
        out.append(_on_line((x, y, z), facing, bounds))
    return out + [_on_line(m[:3], facing, bounds) for m, facing in rights]


def _on_line(point: tuple, facing: float, bounds: tuple) -> tuple:
    """A sit-from-front marker at the point nearest the middle of `bounds` on the line through side marker `point`
    across the seat facing `facing`."""
    cx, cy = (bounds[0] + bounds[3]) / 2, (bounds[1] + bounds[4]) / 2
    rx, ry = _right(facing)
    t = (cx - point[0]) * rx + (cy - point[1]) * ry
    return point[0] + t * rx, point[1] + t * ry, point[2], (facing + math.pi) % math.tau, SIT_FRONT


def seats(marks: list, active: int, bounds: tuple) -> list:
    """FO4 seat markers (x, y, z, heading, entry byte): FNV's sit-from-front markers, entered from their active ones.

    FNV's marker is where the actor stands, in front of the seat; FO4's sits
    SEAT_DEPTH behind the front of `bounds`, facing out. Without a front
    marker the seat comes from the side markers (_side_fronts).
    """
    fronts = [m for m in marks if m[4] == SIT_FRONT] or _side_fronts(marks, bounds)
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
    sleep = [(m, (m[3] + math.pi if m[4] in SLEEP_RIGHT else m[3]) % math.tau, i)
             for i, m in enumerate(marks) if m[4] in SLEEP_RIGHT + SLEEP_LEFT]
    out = []
    for lane, ((x, y, z, _, slot), facing, i) in enumerate(sorted(sleep, key=lambda s: across(s[0], s[1]))):
        if not active >> i & 1:
            continue
        corners = _corners(bounds, facing)
        depth = min(corners) + (max(corners) - min(corners)) * (lane + 0.5) / len(sleep)
        out.append(moved((x, y), facing, depth) + (z, facing, UNUSED_ENTRY | (RIGHT if slot in SLEEP_RIGHT else LEFT)))
    return out


def across(point: tuple, facing: float) -> float:
    """How far `point` lies along `facing`."""
    return point[0] * math.sin(facing) + point[1] * math.cos(facing)


def slot_seats(marks: list, active: int, motions: dict) -> 'tuple | None':
    """(seat markers, keywords, marker model) of FNV furniture whose markers are all one SLOT_SEATS slot: each
    active marker moved and turned as the slot's enter animation (`motions`, enter_motions()) moves the actor,
    entered from every side as vanilla's; None for other furniture."""
    slots = {m[4] for m in marks}
    slot = slots.pop() if len(slots) == 1 else None
    if slot not in SLOT_SEATS or slot not in motions:
        return None
    right, forward, turn = motions[slot]
    out = []
    for i, (x, y, z, heading, _) in enumerate(marks):
        if active >> i & 1:
            (rx, ry), (fx, fy) = _right(heading), (math.sin(heading), math.cos(heading))
            out.append((x + right * rx + forward * fx, y + right * ry + forward * fy, z, (heading + turn) % math.tau,
                        ANY_ENTRY))
    return (out,) + SLOT_SEATS[slot]


def standing(marks: list, idles: tuple) -> 'tuple | None':
    """The FO4 keywords of FNV standing furniture with mesh `marks`, its special idle from FNV idle groups `idles`
    (furniture_idles); () for a special idle FO4 has no furniture for; None when it is not standing furniture."""
    slots = {m[4] for m in marks}
    if slots == {SPECIAL}:
        return next((IDLE_KEYWORDS[i] for i in idles if i in IDLE_KEYWORDS), ())
    return SLOT_KEYWORDS.get(slots.pop()) if len(slots) == 1 else None


def furniture_idles(idles: list) -> dict:
    """{FNV FURN FormID (hex, upper): (idle group EditorIDs)} of FNV IDLE records whose IsCurrentFurnitureObj
    names it."""
    out = {}
    for rec in idles:
        for i in range(int(rec.get('ConditionCount', 0) or 0)):
            cond = C.parse(rec[f'Condition[{i}].Raw'])
            if cond['func'] == 'IsCurrentFurnitureObj':
                out['%08X' % cond['p1']] = out.get('%08X' % cond['p1'], ()) + (rec.get('EditorID', ''),)
    return out


def furniture(fid: int, rec: dict, model: str, bounds: tuple, marks: list, keyword_ids: dict,
              idles: tuple = (), motions: dict = None) -> bytes:
    """The FO4 FURN of FNV furniture `rec` with converted `model` and `bounds` and its mesh's `marks`; a stool,
    floor sit or restrained sit takes slot_seats() by the enter `motions` (enter_motions()); standing furniture
    (standing()) keeps each active marker where FNV has it, entered from any side."""
    active = int(rec.get('MNAM.Flags', 0))
    bed = sleepers(marks, active, bounds)
    slotted = None if bed else slot_seats(marks, active, motions or {})
    placed = bed or (slotted[0] if slotted else seats(marks, active, bounds))
    floor = any(m[4] in SLEEP_FLOOR for m in marks)
    placed = [(x, y, z, (h - FLOOR_TURN) % math.tau, e) for x, y, z, h, e in placed] if bed and floor else placed
    flags = (SLEEP | MUST_EXIT_TO_TALK) if bed else SIT
    words, marker = ((FLOOR_BED_KEYWORDS, FLOOR_BED_MARKER) if floor else (BED_KEYWORDS, BED_MARKER)) if bed \
        else slotted[1:] if slotted else (SEAT_KEYWORDS, '')
    stand = None if placed else standing(marks, idles)
    if stand is not None:
        placed, words = [(x, y, z, h % math.tau, ANY_ENTRY) for i, (x, y, z, h, _) in enumerate(marks)
                         if active >> i & 1], stand
    return R.pack_furn(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds,
                       [keyword_ids[k] for k in words], BED_RECORD_FLAGS if bed else 0,
                       flags | (1 << len(placed)) - 1, marker, placed)
