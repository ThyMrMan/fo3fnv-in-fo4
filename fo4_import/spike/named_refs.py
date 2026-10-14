"""Persistent FNV references outside a build's cells that its actors' packages name, placed with it.

A package aimed at a marker past the build's edge (a prospector's campsite,
Ringo's caravan, Forlorn Hope) was left out as location or target not
built, and a condition measuring from one (GetDistance) could not convert.
FNV keeps such references persistent, in the worldspace's persistent cell,
so the build places them there too: the references a placed actor's
packages (its own, or its template chain's) name as location, target or
condition parameter.

See: docs/fork/fo4_pipeline.md#named-references
"""

from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.quest_scope import PARAMS

#: The REFR record flag Persistent.
PERSISTENT = 0x400
#: FNV package location and target types naming a reference.
NEAR_REFERENCE, SPECIFIC_REFERENCE = '0', '0'
#: How far a template chain is followed for an actor's packages.
TEMPLATE_DEPTH = 4


def named_markers(export_dir: Path, actors: list, persistent_cell: str, placed: set) -> list:
    """FNV REFR records in `persistent_cell` (persistent) that `actors`' packages name, not in `placed` FormIDs."""
    refs = {r['FormID']: r for r in export_records(export_dir, 'REFR')
            if r.get('ParentCELL') == persistent_cell and int(r.get('RecordFlags', 0)) & PERSISTENT}
    bases = {r['FormID']: r for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}
    packs = {r['FormID']: r for r in export_records(export_dir, 'PACK')}
    named = set()
    for actor in actors:
        for pack in _packages(bases, actor.get('NAME', '')):
            named |= _named(packs.get(pack, {}))
    return [refs[fid] for fid in sorted(named - placed) if fid in refs]


def _packages(bases: dict, base: str) -> list:
    """FNV package FormIDs of actor base `base` and its template chain."""
    out = []
    for _ in range(TEMPLATE_DEPTH):
        rec = bases.get(base)
        if rec is None:
            break
        out += [rec[f'AIPackage[{i}]'] for i in range(int(rec.get('AIPackageCount', 0) or 0))]
        base = rec.get('TPLT.Template', '')
    return out


def _named(pack: dict) -> set:
    """FormIDs (hex, upper) of the references FNV package `pack` names: location, target, condition parameters."""
    out = {pack['PLDT.Location'].upper()} if pack.get('PLDT.Type') == NEAR_REFERENCE else set()
    out |= {pack['PTDT.Target'].upper()} if pack.get('PTDT.Type') == SPECIFIC_REFERENCE else set()
    i = 0
    while f'Condition[{i}].Raw' in pack:
        raw = bytes.fromhex(pack[f'Condition[{i}].Raw'])
        out |= {'%08X' % int.from_bytes(raw[at:at + 4], 'little') for at in PARAMS if len(raw) >= at + 4}
        i += 1
    return out
