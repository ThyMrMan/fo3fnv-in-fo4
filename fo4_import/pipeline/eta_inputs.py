"""What the time estimate is given about a build: its features (how many NPCs, guns, meshes, scripts and so on), read
from a build's counts (a finished build's record, or a build log) or estimated from a plugin's export before its
first build; and each stage's group.

See: docs/fork/fo4_build_resources.md#eta
"""

import json
import re
from pathlib import Path

#: Stage groups the estimate models, each with the build stages charged to it; any other stage is 'records'.
GROUPS = {'mesh cache': ('mesh cache',), 'scripts': ('script conversion', 'script compile'), 'people': ('people',),
          'weapons': ('item WEAP',), 'statics': ('base STAT',), 'worlds': ('worlds', 'navmesh', 'object LOD'),
          'collision': ('collision',), 'voice': ('voice',), 'archives': ('main archive', 'FaceGen and texture archive',
                                                                         'plugin write'),
          'ledger': ('ledger and cleanup',)}
#: Stage names holding this text go to the animation group (its stages were renamed over time).
ANIMATION = 'animation data'
#: Features of a build and the count names (a build's printed counts) summed for each.
COUNTS = {'npcs': ('NPC_',), 'guns': ('guns on FNV clips',), 'statics': ('STAT',), 'land': ('LAND',),
          'cells': ('exterior cells',), 'info': ('INFO',), 'scripts': ('scripts',), 'meshes': ('meshes in scope',),
          'packed': ('files packed into the Main archive', 'textures packed'),
          'faces_cold': ('faces fitted in worker processes',), 'guns_cold': ('guns whose clips were made in the pool',),
          'scripts_changed': ('scripts changed',), 'voices_cold': ('voice files written',),
          'meshes_cold': ('meshes converted',)}
#: Each cold feature and the warm feature that bounds it (all of it is cold work on a cold build).
COLD = {'faces_cold': 'npcs', 'guns_cold': 'guns', 'scripts_changed': 'scripts', 'voices_cold': 'info',
        'meshes_cold': 'meshes'}
#: Export record types (one file each) counted for each feature estimated from an export.
EXPORT_TYPES = {'npcs': ('NPC_', 'CREA'), 'guns': ('WEAP',), 'statics': ('STAT',), 'land': ('LAND',),
                'cells': ('CELL',), 'info': ('INFO',), 'scripts': ('SCPT', 'INFO', 'QUST')}
RECORD_BEGIN = b'---RECORD_BEGIN---'
#: The count a build's record keeps of whether its plugin has masters (1) or not (0).
MASTERS_COUNT = 'plugin has masters'
#: Export files up to this size are counted record by record; larger ones are estimated from their size.
COUNTED_BYTES = 64 << 20
_STAGE = re.compile(r'^stage (.+?): ([0-9.]+)s')
_COUNT = re.compile(r'^([^ ].*?): (\d+)$')
_LOG_FACTS = ((re.compile(r'^mesh cache: (\d+) meshes ready in ([0-9.]+)s'), ('meshes in scope', 'mesh ready')),
              (re.compile(r'^(\d+) of (\d+) scripts changed'), ('scripts changed', 'scripts')),
              (re.compile(r'^built in ([0-9.]+)s'), ('built',)))


def group_of(stage: str) -> str:
    """The group stage `stage` is charged to."""
    if ANIMATION in stage:
        return 'animation'
    return next((group for group, stages in GROUPS.items() if stage in stages), 'records')


def grouped(stages: dict) -> dict:
    """{group: seconds} summed from {stage: seconds}."""
    out = {}
    for stage, seconds in stages.items():
        if stage != 'total':
            out[group_of(stage)] = out.get(group_of(stage), 0.0) + seconds
    return out


def features(counts: dict, masters: bool) -> dict:
    """The features of a build with printed `counts` (`masters`: its plugin has some)."""
    out = {name: float(sum(counts.get(key, 0) for key in keys)) for name, keys in COUNTS.items()}
    return sized({**out, 'one': 1.0, 'masters': float(masters), 'compiles': float(out['scripts_changed'] > 0)})


def sized(feats: dict) -> dict:
    """`feats` with 'compile_size': compiles times thousands of meshes."""
    return {**feats, 'compile_size': feats.get('compiles', 0.0) * feats.get('meshes', 0.0) / 1000}


def log_build(path: Path) -> 'tuple | None':
    """({stage: seconds}, counts) of build log `path`, the mesh cache's time among the stages when the log has it
    only as a line; None when the build did not finish."""
    stages, counts = {}, {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if (m := _STAGE.match(line)) is not None:
            stages[m[1]] = float(m[2])
        elif (m := _COUNT.match(line)) is not None:
            counts[m[1]] = int(m[2])
        for pattern, names in _LOG_FACTS:
            if (m := pattern.match(line)) is not None:
                counts.update({name: float(value) for name, value in zip(names, m.groups())})
    if 'built' not in counts:
        return None
    if 'mesh cache' not in stages and 'mesh ready' in counts:
        stages['mesh cache'] = max(0.0, counts['mesh ready'] - stages.get('script conversion', 0.0))
    return stages, counts


def record_build(path: Path) -> 'tuple | None':
    """({stage: seconds}, counts) of a finished build's stamp (`<plugin>.build.json`); None otherwise."""
    try:
        stamp = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if stamp.get('status') != 'finished' or 'stages' not in stamp:
        return None
    return {name: row['seconds'] for name, row in stamp['stages'].items() if 'seconds' in row}, stamp['counts']


def record_count(path: Path, per_record: float) -> float:
    """Records in export file `path`: counted when it is small, else its size over `per_record` bytes."""
    size = path.stat().st_size
    if size > COUNTED_BYTES and per_record:
        return size / per_record
    return float(path.read_bytes().count(RECORD_BEGIN))


def export_counts(export_dir: Path, per_record: dict) -> dict:
    """{record type: records} of the types EXPORT_TYPES names in `export_dir`, with 'meshes': its mesh files."""
    kinds = {kind for kinds in EXPORT_TYPES.values() for kind in kinds}
    out = {kind: record_count(export_dir / f'{kind}.txt', per_record.get(kind, 0.0)) for kind in sorted(kinds)
           if (export_dir / f'{kind}.txt').is_file()}
    meshes = export_dir / 'meshes'
    out['meshes'] = float(sum(1 for p in meshes.rglob('*.nif'))) if meshes.is_dir() else 0.0
    return out


def has_masters(export_dir: Path) -> bool:
    """Whether the export's header names a master."""
    header = export_dir / '_HEADER.txt'
    return header.is_file() and 'Master[0]=' in header.read_text(encoding='utf-8', errors='replace')


def export_features(own: dict, masters: bool, model: dict) -> dict:
    """A build's features estimated from its export's counts `own` (export_counts): each feature `model`'s ratio
    times the export's records of its types, plus, for a plugin with masters that edits cells, the typical region
    its build takes from them (`model`['region']); every cold feature as large as the warm one bounding it."""
    out = {name: model['ratios'].get(name, 1.0) * sum(own.get(kind, 0.0) for kind in kinds)
           for name, kinds in EXPORT_TYPES.items()}
    out['meshes'] = model['ratios'].get('meshes', 1.0) * own.get('meshes', 0.0)
    if masters and own.get('CELL'):
        out = {name: value + model['region'].get(name, 0.0) for name, value in out.items()}
    out['packed'] = out['meshes'] * model['ratios'].get('packed', 1.0)
    return sized({**out, **{cold: out[warm] for cold, warm in COLD.items()}, 'one': 1.0, 'masters': float(masters),
                  'compiles': 1.0})
