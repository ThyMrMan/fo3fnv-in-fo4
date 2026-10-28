"""FNV creatures' run speed on their FO4 stand-ins, through the NPC's SpeedMult.

FNV moves a creature by its movement clips' root motion: run speed is the
FastForward clip's root speed (truncated to an integer) times its ACBS speed
multiplier / 100 (FalloutNV.exe 0x8d4f10, 0x494300), times its scale; a group
with several variants plays at rate 1, the multiplier unused. FO4 takes speed
from the movement type the behaviour graph names (an `iState_<X>` variable
naming a MOVT by MNAM, else the race's WKMV, else DOBJ DMWL; Fallout4.exe
0xca5c90) and multiplies every translation by scale and |SpeedMult| / 100
(0xcb25f0). The converted creature's SpeedMult makes its FO4 forward run
FNV's.

See: docs/fork/fo4_pipeline.md#creature-speed
"""

import functools
import re
import struct
from pathlib import Path

from asset_convert.havok.kf_decode import decode_kf, split_root_motion
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm AVIF SpeedMult.
SPEED_MULT = 0x2DA
#: FNV's run group (FastForward, 7) by its clip name, cut at the first '_' as FNV loads it.
RUN_GROUP = 'fastforward'
#: SPED forward-run float by size (form version 104+: 112 bytes, 7 x 4 floats; older 40 to 68 bytes: f5).
FORWARD_RUN = {112: 10}
OLD_FORWARD_RUN = 5
#: An iState graph variable's name: the MOVT MNAM it selects; the ending vanilla gives a graph's base state.
ISTATE, BASE_STATE = re.compile(rb'iState_([A-Za-z0-9_]+)'), 'default'
#: RACE subrecords naming its behaviour project (MODL after NAM3) and subgraphs (SGNM).
PROJECT_MARK, SUBGRAPH = b'NAM3', b'SGNM'


def forward_run(sped: bytes) -> float:
    """A MOVT SPED's forward run speed (Fallout4.exe 0x620ce0's layouts)."""
    index = FORWARD_RUN.get(len(sped), OLD_FORWARD_RUN)
    return struct.unpack_from('<f', sped, index * 4)[0]


def fnv_run_speed(export_dir: Path, folder: str, stats: dict, scale: float) -> 'float | None':
    """FNV creature's forward run in units/s: its `folder` FastForward clips' root speed, by its ACBS speed
    multiplier (`stats`) when the group has one clip, times `scale`; None without a FastForward clip."""
    speeds = run_clip_speeds(Path(export_dir), folder)
    if not speeds:
        return None
    if len(speeds) > 1:
        return sum(speeds) / len(speeds) * scale
    return int(speeds[0]) * float(stats.get('ACBS.SpeedMultiplier', 100) or 100) / 100.0 * scale


@functools.cache
def run_clip_speeds(export_dir: Path, folder: str) -> tuple:
    """Root speeds (units/s) of skeleton folder `folder`'s FastForward clips, hurt variants left out."""
    root = export_dir / 'meshes' / folder
    out = []
    for kf in sorted(root.rglob(f'*{RUN_GROUP}*.kf')) if root.is_dir() else ():
        if 'hurt' in (p.lower() for p in kf.parts):
            continue
        for clip in decode_kf(str(kf)):
            motion = split_root_motion(clip) if clip.name.lower().split('_', 1)[0] == RUN_GROUP else None
            if motion and motion['translations'] is not None and clip.duration > 0:
                travel = motion['translations'][-1] - motion['translations'][0]
                out.append(float((travel ** 2).sum() ** 0.5) / clip.duration)
    return tuple(out)


class Fo4Speeds:
    """FO4 creature races' forward run speed as their behaviour graph selects it, read once per race."""

    def __init__(self, fo4: bytes):
        """Index Fallout4.esm's movement types, races and default movement type."""
        self.movt, self.races, self.default, self.made = {}, {}, 0, {}
        for rec, _ in walk(fo4, b'MOVT', b'RACE', b'DOBJ'):
            subs = list(subrecords(rec.body))
            if rec.sig == b'MOVT':
                found = dict(subs)
                self.movt[rec.form_id] = (found.get(b'MNAM', b'').rstrip(b'\0').decode('cp1252').lower(),
                                          found.get(b'SPED', b''))
            elif rec.sig == b'RACE':
                self.races[rec.form_id] = subs
            else:
                self.default = _dobj(dict(subs).get(b'DNAM', b''), b'DMWL') or self.default
        self.by_name = {name: fid for fid, (name, _) in self.movt.items() if name}
        self._archives = None

    def speed_mult(self, npc_subs: dict, fnv_run: 'float | None') -> 'float | None':
        """The SpeedMult giving `npc_subs` FNV's forward run `fnv_run`; None if unknown."""
        race = struct.unpack('<I', npc_subs[b'RNAM'])[0]
        fo4 = self.run(race)
        return 100.0 * fnv_run / (fo4 * fo4_scale(npc_subs, self.race_height(race))) if fnv_run and fo4 else None

    def race_height(self, race: int) -> float:
        """Race `race`'s height (its DATA's first float), 1 when unknown."""
        data = dict(self.races.get(race, [])).get(b'DATA', b'')
        return struct.unpack_from('<f', data)[0] if len(data) >= 4 else 1.0

    def run(self, race: int) -> 'float | None':
        """Race `race`'s forward run speed (units/s) before scale and SpeedMult; None when unknown."""
        if race not in self.made:
            fid = self._movement_type(race)
            self.made[race] = forward_run(self.movt[fid][1]) if fid in self.movt else None
        return self.made[race]

    def _movement_type(self, race: int) -> int:
        """The MOVT FO4 gives race `race` walking: see movement_type."""
        subs = self.races.get(race, [])
        found = dict(subs)
        own = struct.unpack('<I', found[b'WKMV'])[0] if b'WKMV' in found else 0
        names = self._graph_states(subs)
        return movement_type(names, self.by_name, self.movt.get(own, ('',))[0], own, self.default)

    def _graph_states(self, subs: list) -> set:
        """The iState names (lower case) in race `subs`' behaviour project folder and subgraphs."""
        project, files, marked = '', [], False
        for tag, data in subs:
            if tag == b'MODL' and marked and not project:
                project = data.rstrip(b'\0').decode('cp1252')
            marked = marked or tag == PROJECT_MARK
            if tag == SUBGRAPH:
                files.append(data.rstrip(b'\0').decode('cp1252'))
        archives = self._archives = self._archives or Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Animations.ba2')
        folder = 'meshes\\' + project.rsplit('\\', 1)[0] + '\\behaviors\\' if project else None
        paths = [n for n in archives.names(folder) if n.endswith('.hkx')] if folder else []
        paths += [n for n in ('meshes\\' + f.lower() for f in files) if n in archives.by_name]
        return set().union(*(self._states(archives, p) for p in set(paths)))

    @functools.cache
    def _states(self, archives: Archives, path: str) -> frozenset:
        """The iState names (lower case) in behaviour file `path`, read once."""
        return frozenset(m.decode().lower() for m in ISTATE.findall(archives.read(path)))


def movement_type(states: set, by_name: dict, own_name: str, own: int, default: int) -> int:
    """The MOVT a race walks with: its WKMV when its graph names it (or names none); else the graph-named MOVT
    called `<kind>Default`, else the one whose name the others extend, else the only one; else DOBJ DMWL.
    The engine starts the graph at its iState variable's initial value, which needs a Havok 2014 reader; the
    order here stands in for it.
    See: docs/fork/fo4_pipeline.md#creature-speed
    """
    named = sorted(s for s in states if s in by_name)
    if own and (own_name in named or not named):
        return own
    base = [s for s in named if s.endswith(BASE_STATE)] or [s for s in named if all(o.startswith(s) for o in named)]
    if base or len(named) == 1:
        return by_name[(base or named)[0]]
    return default


def _dobj(dnam: bytes, key: bytes) -> int:
    """The form DOBJ DNAM (key, FormID pairs) holds for `key`; 0 without one."""
    for i in range(0, len(dnam) - 7, 8):
        if dnam[i:i + 4] == key:
            return struct.unpack_from('<I', dnam, i + 4)[0]
    return 0


def heights(npc_subs: dict) -> tuple:
    """An NPC_'s (min, max) height: NAM6, NAM4 (min when absent); 1 without NAM6."""
    low = struct.unpack('<f', npc_subs[b'NAM6'])[0] if b'NAM6' in npc_subs else 1.0
    return low, struct.unpack('<f', npc_subs[b'NAM4'])[0] if b'NAM4' in npc_subs else low


def fo4_scale(npc_subs: dict, race_height: float) -> float:
    """The stand-in's mean scale: mid height range (NAM6..NAM4) x `race_height`."""
    return sum(heights(npc_subs)) / 2.0 * race_height


def with_height(low: float, high: float):
    """A record edit setting NPC_ height min (NAM6) and max (NAM4, added after NAM6/NAM7 when absent)."""
    values = {b'NAM6': struct.pack('<f', low), b'NAM4': struct.pack('<f', high)}

    def edit(subs: bytes) -> bytes:
        """The subrecords with NAM6 and NAM4 set."""
        tags = [t for t, _ in subrecords(subs)]
        after = b'NAM7' if b'NAM7' in tags else b'NAM6'
        out = b''
        for tag, data in subrecords(subs):
            out += pack_subrecord(tag.decode(), values.get(tag, data))
            if tag == after and b'NAM4' not in tags:
                out += pack_subrecord('NAM4', values[b'NAM4'])
        return out
    return edit


def with_speed_mult(value: float):
    """A record edit setting PRPS's SpeedMult to `value` (added when absent; PRPS added before AIDT if none)."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with SpeedMult set."""
        out, placed = b'', False
        for tag, data in subrecords(subs):
            if tag == b'PRPS':
                pairs = {**dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8)),
                         SPEED_MULT: value}
                data, placed = b''.join(struct.pack('<If', av, v) for av, v in pairs.items()), True
            elif tag == b'AIDT' and not placed:
                out, placed = out + pack_subrecord('PRPS', struct.pack('<If', SPEED_MULT, value)), True
            out += pack_subrecord(tag.decode(), data)
        return out if placed else out + pack_subrecord('PRPS', struct.pack('<If', SPEED_MULT, value))
    return edit
