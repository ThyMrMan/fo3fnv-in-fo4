"""What a build changed against the last accepted one, with FormID drift as a gate.

A snapshot keeps every record's FormID, signature and EditorID. A FormID
that is gone, now holds another signature, or an EditorID that moved to
another FormID is drift: saves and other plugins point at the old FormID,
so it needs approval. The baseline advances by itself while a build shows
no drift, and only on `--accept-build` once it does. A content hash per
record beside it counts the records each build changed, by type.

See: docs/commentary/tools_preflight.md#build-diff
"""

import json
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from tools.validate.preflight.findings import Finding

#: FormIDs listed per drift finding before the rest are counted.
SAMPLES = 8


def snapshot(index) -> dict:
    """{FormID hex: 'SIG|EditorID'} of every record in the build."""
    return {f'{fid:08X}': f'{rec.type}|{index.edid(fid)}' for fid, rec in index.by_fid.items()}


def load_baseline(path: Path):
    """The accepted snapshot, or None before the first run."""
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def save_baseline(path: Path, snap: dict) -> None:
    """Accept `snap` as the baseline the next build is compared with."""
    Path(path).write_text(json.dumps(snap, sort_keys=True, indent=0), encoding='utf-8')


def drift(before: dict, after: dict) -> dict:
    """{kind: {signature: [description]}} for removed, retyped and moved records."""
    out = {'removed': defaultdict(list), 'retyped': defaultdict(list), 'moved': defaultdict(list)}
    new_home = {v: fid for fid, v in after.items() if v.split('|', 1)[1]}
    for fid, was in before.items():
        sig, edid = was.split('|', 1)
        now, home = after.get(fid), new_home.get(was) if edid else None
        if now is None and home:
            out['moved'][sig].append(f'{edid}: {fid} -> {home}')
        elif now is None:
            out['removed'][sig].append(f'{fid} {edid}'.rstrip())
        elif now.split('|', 1)[0] != sig:
            out['retyped'][sig].append(f'{fid} {edid}: now {now.split("|", 1)[0]}')
    return out


def added(before: dict, after: dict) -> Counter:
    """How many records of each signature the build added."""
    return Counter(v.split('|', 1)[0] for fid, v in after.items() if fid not in before)


def contents(index) -> dict:
    """{FormID hex: CRC-32 hex} of every record's subrecords, types and data."""
    out = {}
    for fid, rec in index.by_fid.items():
        crc = 0
        for sub in rec.subrecords:
            crc = zlib.crc32(sub.data, zlib.crc32(sub.type.encode('latin-1'), crc))
        out[f'{fid:08X}'] = f'{crc:08X}'
    return out


def changed(before: dict, after: dict, snap: dict) -> Counter:
    """How many records of each signature kept their FormID and changed their contents."""
    return Counter(snap[fid].split('|', 1)[0] for fid, crc in after.items()
                   if fid in before and before[fid] != crc)


_WHAT = {'removed': 'records were removed', 'retyped': 'FormIDs now hold another record type',
         'moved': 'EditorIDs moved to a new FormID'}


def audit(game: str, before, after: dict) -> list:
    """Drift findings for one game, one per kind and signature; none on a first run."""
    if before is None:
        return []
    out = []
    for kind, by_sig in drift(before, after).items():
        for sig, rows in sorted(by_sig.items()):
            detail = rows[:SAMPLES] + ([f'... {len(rows) - SAMPLES} more'] if len(rows) > SAMPLES else [])
            out.append(Finding('build', f'build|{game}|{kind}|{sig}', 'error',
                               f'{len(rows)} {sig} {_WHAT[kind]}; approve with --accept-build',
                               tuple(detail)))
    return out
