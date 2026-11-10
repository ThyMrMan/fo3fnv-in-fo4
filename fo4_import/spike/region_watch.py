"""FO3/FNV region tests on Fallout 4: one global per tested region, 1 while the player stands inside its polygons.

FNV tests the player's position against a region's polygons (`PlayerInRegion` in conditions, `IsPlayerInRegion` in
scripts). Each region a record condition or a script tests gets a global (`TES4Region_<EditorID>`); a
start-game quest's `F3NV_RegionWatch` keeps them set from the polygons, carried as array properties. Conditions read
the global (say_topics), converted scripts the region's global property (TES4Polyfill.InRegion). A DLC testing its
master's region gets the master's global (derive_formid), so each plugin watches only the regions it owns.

See: docs/fork/fo4_regions.md#built
"""

import re
import struct

from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_global, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C

#: derive_formid sites: a region's global (key: the region's EditorID), a plugin's watch quest (key: its stem).
GLOBAL_SITE, QUEST_SITE = 'FNV region global', 'FNV region watch'
SCRIPT, GLOBAL_PREFIX = 'F3NV_RegionWatch', 'TES4Region_'
#: Form map key head of a tested region's global: (REGION_KEY, FNV region FormID).
REGION_KEY = 'region'
#: Papyrus array size limit; the watch script's point arrays (X0..X3, Y0..Y3) hold CHUNKS of it.
CHUNK, CHUNKS = 128, 4
#: FNV's region test in a script, and its region.
SCRIPT_TEST = re.compile(r'\bIsPlayerInRegion\s+(\w+)', re.I)
#: Record types whose conditions FNV writes PlayerInRegion in.
CONDITION_TYPES = ('INFO', 'PACK', 'MESG', 'QUST', 'IDLE', 'PERK', 'TERM', 'NOTE', 'CHAL')
PLAYER_IN_REGION = C.FNV.index('PlayerInRegion')


def polygons(rec: dict) -> list:
    """[[(x, y), ...]] of FNV region `rec`'s areas (Area[i].PointsHex: little-endian float pairs)."""
    out = []
    for i in range(int(rec.get('AreaCount', 0) or 0)):
        raw = bytes.fromhex(rec.get(f'Area[{i}].PointsHex', ''))
        out.append([struct.unpack_from('<2f', raw, at) for at in range(0, len(raw) - 7, 8)])
    return [poly for poly in out if len(poly) >= 3]


def tested(export_dir: Path) -> set:
    """FNV FormIDs of the regions `export_dir`'s record conditions test with PlayerInRegion."""
    func = struct.pack('<H', PLAYER_IN_REGION).hex().upper()
    out = set()
    for sig in CONDITION_TYPES:
        for rec in export_records(export_dir, sig):
            for key, raw in rec.items():
                if key.endswith('.Raw') and raw[16:20].upper() == func:
                    out.add(C.parse(raw)['p1'])
    return out


class RegionWatch:
    """Region globals of one build, made as conditions and scripts name them, and the watch quest."""

    def __init__(self, builder, export_dir: Path):
        """Index `export_dir`'s regions with polygons, and give a global to each its conditions or scripts test."""
        self.builder, self.made = builder, {}
        self.regions = {int(r['FormID'], 16): r for r in export_records(export_dir, 'REGN') if polygons(r)}
        self.names = {r['EditorID'].lower(): fid for fid, r in self.regions.items() if r.get('EditorID')}
        named = {m.group(1).lower() for r in export_records(export_dir, 'SCPT') for m in SCRIPT_TEST.finditer(
            r.get('SCTX', ''))}
        for fid in sorted(tested(export_dir) | {self.names[n] for n in named if n in self.names}):
            self.global_of(fid)

    def global_of(self, region) -> 'int | None':
        """The global of FNV region `region` (FormID or EditorID, any case), made once; None for no such region."""
        fid = self.names.get(region.lower()) if isinstance(region, str) else region
        if fid not in self.regions:
            return None
        if fid not in self.made:
            edid = f'{GLOBAL_PREFIX}{self.regions[fid]["EditorID"]}'
            self.made[fid] = glob = self.builder.writer.derive_formid(GLOBAL_SITE, self.regions[fid]['EditorID'])
            self.builder.writer.add_record('GLOB', pack_global(glob, edid))
        return self.made[fid]

    def form_map(self) -> dict:
        """{(REGION_KEY, FNV region FormID): its global} for conditions."""
        return {(REGION_KEY, fid): glob for fid, glob in self.made.items()}

    def write(self) -> None:
        """The watch quest over the regions whose globals this plugin owns; nothing without any.
        See: docs/fork/fo4_regions.md#built
        """
        own = self.builder.writer.own_index
        watched = [fid for fid, glob in sorted(self.made.items()) if glob >> 24 == own][:CHUNK - 1]
        props = self.properties(watched)
        if not props:
            return
        plugin = plugin_stem(self.builder.export_dir)
        fid = self.builder.writer.derive_formid(QUEST_SITE, plugin)
        vmad = quest_fragments('', [], scripts=[(SCRIPT, {}, props)])
        self.builder.writer.add_record('QUST', pack_script_quest(fid, f'FNV_RegionWatch_{plugin}', vmad))
        self.builder.scripts.used.append(SCRIPT)
        self.builder.counts['regions watched'] = len(props['Globals'][1])

    def properties(self, watched: list) -> dict:
        """F3NV_RegionWatch's value properties for FNV regions `watched` (ending at CHUNKS * CHUNK points; a region
        past that is left out, counted); {} for none."""
        rows, points = {key: [] for key in ('Globals', 'Worlds', 'RegionFirst', 'PolyFirst', 'MinX', 'MaxX', 'MinY',
                                            'MaxY')}, []
        for fid in watched:
            polys = polygons(self.regions[fid])
            if len(points) + sum(map(len, polys)) > CHUNKS * CHUNK:
                self.builder.counts['region left out (watch arrays full)'] += 1
                continue
            rows['RegionFirst'].append(len(rows['PolyFirst']))
            for poly in polys:
                rows['PolyFirst'].append(len(points))
                points += poly
            xs, ys = [x for poly in polys for x, _ in poly], [y for poly in polys for _, y in poly]
            rows['Globals'].append(self.made[fid])
            rows['Worlds'].append(self.builder.fnv_id(self.regions[fid].get('WNAM.Worldspace', '0')))
            for key, value in (('MinX', min(xs)), ('MaxX', max(xs)), ('MinY', min(ys)), ('MaxY', max(ys))):
                rows[key].append(value)
        if not rows['Globals']:
            return {}
        rows['RegionFirst'].append(len(rows['PolyFirst']))
        rows['PolyFirst'].append(len(points))
        kinds = {'Globals': 'objects', 'Worlds': 'objects', 'RegionFirst': 'ints', 'PolyFirst': 'ints'}
        out = {key: (kinds.get(key, 'floats'), value) for key, value in rows.items()}
        for i in range(CHUNKS):
            part = points[i * CHUNK:(i + 1) * CHUNK]
            out[f'X{i}'], out[f'Y{i}'] = ('floats', [x for x, _ in part]), ('floats', [y for _, y in part])
        return out
