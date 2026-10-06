#!/usr/bin/env python3
"""Compile converted Papyrus .psc scripts and report categorized error statistics.

Usage:
    python tools/script/compile_papyrus.py [--src DIR] [--out DIR] [--headers DIR]
    python tools/script/compile_papyrus.py --errors-detail  # first failing file per error category

    # Fallout 4 (the corpus from `script_convert.pipeline --target fallout4`):
    python tools/script/compile_papyrus.py --game fallout4 --src temp/fo4_scripts/FalloutNV.esm \\
        --out temp/fo4_pex --baseline tools/script/fo4_compile_baseline.json

Fallout 4 compiles with the game's own PapyrusCompiler.exe against F4SE then
Base, in one `-all` batch per worker over chunk folders, and reports each
failing file's own errors apart from files that fail only through a script
they use. `--baseline` makes it a gate: more failing files, or any error kind
that grows or is new, exits 1; `--write-baseline` records the current run.

See: docs/fork/fo4_spikes.md#spike-3-gate
"""
import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from core.subprocess_flags import windows_cmd
from fo4_import.base.papyrus import compile_folder, header_dirs

#: One FO4 compiler diagnostic: `<path>\<Script>.psc(line,col): message`.
_FO4_LINE = re.compile(r'[\\/](\w+)\.psc\(\d+,\d+\): (.+)')
#: Converted script names, folded so one missed construct is one error kind.
_CONVERTED_NAME = re.compile(r'\b(?:falloutnv|fallout3|tes4)_\w+', re.I)
_WORD = re.compile(r'\w+')
#: Per-script results of the last Fallout 4 run, in --out, so the next run compiles only what changed.
_STATE_FILE = 'compile_state.json'


def find_compiler():
    """The vendored Skyrim papyrus.exe."""
    p = _PROJECT_ROOT / 'external' / 'papyrus-compiler' / 'papyrus.exe'
    if p.exists():
        return str(p)
    raise FileNotFoundError('papyrus.exe not found')


def find_skyrim_headers():
    """The vanilla .psc headers, via the pipeline's own lookup.

    Shared with the compile phase so this tool cannot disagree with a real
    build about where the headers are; off Windows it resolves the install
    from conversion_config.json's tes5DataPath.
    """
    from convert import load_config
    from papyrus_compile import find_skyrim_source_scripts
    try:
        cfg = load_config()
    except (FileNotFoundError, OSError):
        cfg = {}
    headers = find_skyrim_source_scripts(cfg)
    if headers:
        return headers
    p = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition\Data\Source\Scripts')
    if (p / 'Debug.psc').exists():
        return str(p)
    raise FileNotFoundError('Cannot find Skyrim papyrus headers')


def compile_one(args):
    """('ok'|'err', error key, raw error, file name) for one file with the Skyrim compiler."""
    f, compiler, out_dir, headers, polyfill_dir = args
    cmd = [compiler, 'compile', '-i', str(f), '-o', str(out_dir), '-h', headers]
    for extra in (polyfill_dir or '').split(';'):
        if extra:
            cmd.extend(['-h', extra])
    r = subprocess.run(windows_cmd(cmd), capture_output=True, text=True, timeout=15)
    if r.returncode == 0:
        return ('ok', None, None, f.name)
    combined = r.stdout + '\n' + r.stderr
    for line in combined.split('\n'):
        m = re.search(r'error:\s*(.+)', line)
        if m:
            raw = m.group(1).strip()
            key = re.sub(r"'[^']*'", 'X', re.sub(r'\d+', 'N', raw))
            return ('err', key, raw, f.name)
    return ('err', 'UNKNOWN', combined[:200], f.name)


def compile_skyrim(args) -> tuple:
    """(ok count, total, Counter of error keys, {key: (raw, file)}) for the Skyrim compiler."""
    compiler = find_compiler()
    headers = args.headers or find_skyrim_headers()
    src_dir = Path(args.src)
    polyfill_dir = str(src_dir) if (src_dir / 'TES4Polyfill.psc').exists() else None
    if args.extra_headers:
        polyfill_dir = f'{polyfill_dir};{args.extra_headers}' if polyfill_dir else args.extra_headers
    files = sorted(src_dir.glob('*.psc'))
    print(f'Compiling {len(files)} files with {args.workers} workers...')
    errors, samples, ok = collections.Counter(), {}, 0
    work = [(f, compiler, str(args.out), headers, polyfill_dir) for f in files]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for status, key, raw, fname in ex.map(compile_one, work):
            if status == 'ok':
                ok += 1
            else:
                errors[key] += 1
                samples.setdefault(key, (raw, fname))
    return ok, len(files), errors, samples


def fo4_key(message: str) -> str:
    """An FO4 diagnostic as an error kind: converted script names and numbers folded."""
    return re.sub(r'\d+', 'N', _CONVERTED_NAME.sub('<script>', message))


def _fo4_chunks(files: list, out_dir: Path, workers: int) -> list:
    """Copy `files` round-robin into `workers` chunk folders under out_dir; the folders."""
    root = out_dir / '_chunks'
    if root.exists():
        shutil.rmtree(root)
    chunks = [root / str(n) for n in range(min(workers, len(files)))]
    for i, f in enumerate(files):
        chunks[i % len(chunks)].mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, chunks[i % len(chunks)] / f.name)
    return chunks


def source_hashes(files: list) -> dict:
    """{lower-case script name: SHA-1 of its source}."""
    return {f.stem.lower(): hashlib.sha1(f.read_bytes()).hexdigest() for f in files}


def needs_compile(files: list, hashes: dict, state: dict) -> set:
    """Lower-case names whose source changed since `state`, plus every script naming one, transitively."""
    todo = {n for n, sha in hashes.items() if state.get(n, {}).get('sha') != sha}
    users = collections.defaultdict(set)
    for f in files:
        for word in set(_WORD.findall(f.read_text(encoding='utf-8', errors='replace').lower())) & hashes.keys():
            users[word].add(f.stem.lower())
    queue = list(todo)
    while queue:
        for user in users[queue.pop()] - todo:
            todo.add(user)
            queue.append(user)
    return todo


def _load_state(out_dir: Path, imports: str) -> dict:
    """The last run's per-script results, {} when absent or made against other headers."""
    path = out_dir / _STATE_FILE
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return state.get('scripts', {}) if state.get('imports') == imports else {}


def _compile_chunks(files: list, out_dir: Path, imports: str, workers: int) -> dict:
    """{script: [error messages]} from compiling `files` in parallel chunk folders."""
    if not files:
        return {}
    chunks = _fo4_chunks(files, out_dir, workers)
    print(f'Compiling {len(files)} files with FO4\'s compiler in {len(chunks)} batches...')
    own = collections.defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(chunks)) as ex:
        for text in ex.map(lambda c: compile_folder(c, out_dir, imports), chunks):
            for m in _FO4_LINE.finditer(text):
                if m.group(2) not in own[m.group(1)]:
                    own[m.group(1)].append(m.group(2))
    shutil.rmtree(out_dir / '_chunks')
    return {name.lower(): messages for name, messages in own.items()}


def compile_fallout4(args) -> tuple:
    """(compiled names, {file: [own error messages]}, source names) with FO4's compiler.

    Only scripts whose source changed since the last run, and the scripts
    naming them, are compiled; the rest keep their saved result. `--full`
    compiles everything. A script's old .pex is deleted first, so a script
    that stops compiling cannot pass on a stale one.
    """
    src_dir, out_dir = Path(args.src).resolve(), Path(args.out).resolve()
    imports = f'{args.headers or header_dirs()};{src_dir}'
    files = sorted(src_dir.glob('*.psc'))
    hashes = source_hashes(files)
    state = {} if args.full else _load_state(out_dir, imports)
    todo = needs_compile(files, hashes, state)
    print(f'{len(todo)} of {len(files)} scripts changed or use one that did')
    for name in todo:
        (out_dir / f'{name}.pex').unlink(missing_ok=True)
    own = _compile_chunks([f for f in files if f.stem.lower() in todo], out_dir, imports, args.workers)
    pex = {p.stem.lower() for p in out_dir.glob('*.pex')}
    scripts = {n: state[n] if n not in todo else {'sha': hashes[n], 'ok': n in pex, 'own': own.get(n, [])}
               for n in hashes}
    (out_dir / _STATE_FILE).write_text(json.dumps({'imports': imports, 'scripts': scripts}), encoding='utf-8')
    compiled = {n for n, s in scripts.items() if s['ok']}
    own = {f.stem: scripts[f.stem.lower()]['own'] for f in files if scripts[f.stem.lower()]['own']}
    return compiled, own, [f.stem for f in files]


def fo4_summary(compiled: set, own: dict, names: list) -> dict:
    """{'files', 'compiled', 'own_errors', 'dependency_only', 'kinds': {kind: files}, 'samples'}."""
    sources = {n.lower() for n in names}
    failing = {n for n in names if n.lower() not in compiled}
    kinds, samples = collections.Counter(), {}
    for name, messages in own.items():
        if name.lower() not in sources:
            continue
        for kind in {fo4_key(m) for m in messages}:
            kinds[kind] += 1
            samples.setdefault(kind, f'{name}: {next(m for m in messages if fo4_key(m) == kind)}')
    with_errors = {n for n in failing if own.get(n)}
    return {'files': len(names), 'compiled': len(names) - len(failing), 'own_errors': len(with_errors),
            'dependency_only': len(failing - with_errors), 'kinds': dict(kinds.most_common()), 'samples': samples}


def gate(summary: dict, baseline_path: Path) -> list:
    """What got worse than the baseline: more failing files, or an error kind that grew or is new."""
    base = json.loads(baseline_path.read_text(encoding='utf-8'))
    worse = []
    if summary['files'] - summary['compiled'] > base['files'] - base['compiled']:
        worse.append(f"failing files {base['files'] - base['compiled']} -> {summary['files'] - summary['compiled']}")
    for kind, n in summary['kinds'].items():
        if n > base['kinds'].get(kind, 0):
            worse.append(f"{base['kinds'].get(kind, 0)} -> {n}  {kind}")
    return worse


def report_fallout4(args) -> int:
    """Compile with FO4's compiler, print the summary, apply the baseline gate; the exit code."""
    summary = fo4_summary(*compile_fallout4(args))
    print(f"\nOK: {summary['compiled']}/{summary['files']} "
          f"({summary['compiled'] * 100 / max(summary['files'], 1):.1f}%)")
    print(f"Failing on their own code: {summary['own_errors']}; only through a script they use: "
          f"{summary['dependency_only']}\n")
    for kind, n in list(summary['kinds'].items())[:args.top]:
        print(f'{n:6d}  {kind}')
        if args.errors_detail:
            print(f"        -> {summary['samples'][kind]}")
    if args.write_baseline:
        Path(args.write_baseline).write_text(
            json.dumps({k: v for k, v in summary.items() if k != 'samples'}, indent=1) + '\n', encoding='utf-8')
        print(f'\nbaseline written: {args.write_baseline}')
    worse = gate(summary, Path(args.baseline)) if args.baseline else []
    for line in worse:
        print(f'WORSE  {line}')
    return 1 if worse else 0


def report_skyrim(args) -> int:
    """Compile with the vendored Skyrim compiler and print the summary; 0."""
    ok, total, errors, samples = compile_skyrim(args)
    print(f'\nOK: {ok}/{total} ({ok * 100 / max(total, 1):.1f}%)')
    print(f'Failed: {total - ok}\n')
    for key, count in errors.most_common(args.top):
        print(f'{count:5d}  {key}')
        if args.errors_detail:
            raw, fname = samples[key]
            print(f'       -> {fname}: {raw}')
    return 0


def main():
    """Parse the command line and run the compile for the chosen game."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--game', choices=('skyrim', 'fallout4'), default='skyrim')
    parser.add_argument('--src', default=str(_PROJECT_ROOT / 'output' / 'oblivion.esm' / 'scripts' / 'source'))
    parser.add_argument('--out', default=str(_PROJECT_ROOT / 'temp' / 'pex'))
    parser.add_argument('--headers', default=None, help='header dirs (Fallout 4: F4SE;Base by default)')
    parser.add_argument('--extra-headers', default=None,
                        help='Skyrim: additional header dir (e.g. output/<plugin>/scripts/source '
                             'when compiling a subset that names other converted types)')
    parser.add_argument('--errors-detail', action='store_true', help='Show sample file per error category')
    parser.add_argument('--top', type=int, default=40, help='error kinds to print')
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 4) - 1))
    parser.add_argument('--baseline', help='Fallout 4: fail when worse than this baseline JSON')
    parser.add_argument('--write-baseline', help='Fallout 4: record this run as the baseline JSON')
    parser.add_argument('--full', action='store_true',
                        help='Fallout 4: compile every script, not only those changed since the last run')
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    sys.exit(report_fallout4(args) if args.game == 'fallout4' else report_skyrim(args))


if __name__ == '__main__':
    main()
