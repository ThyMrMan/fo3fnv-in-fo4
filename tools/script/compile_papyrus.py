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
from core.memory_budget import memory_workers
from fo4_import.base import caprica
from fo4_import.base.file_stamps import Stamps
from fo4_import.base.papyrus import compile_folder, header_dirs

#: One FO4 compiler's peak memory: a fixed part, and a part per script in its batch (0.93 GB at 84, 1.02 at 300).
COMPILER_BYTES, COMPILER_SCRIPT_BYTES = 1 << 30, 1 << 19
#: Memory kept free for the build and other programs while the compilers run.
COMPILE_SPARE_BYTES = 2 << 30
#: One FO4 compiler diagnostic: `<path>\<Script>.psc(line,col): message`.
_FO4_LINE = re.compile(r'[\\/](\w+)\.psc\(\d+,\d+\): (.+)')
#: Name prefixes of the scripts converted from a game (lower case): a .pex with one and no source is an orphan.
CONVERTED_PREFIXES = ('falloutnv_', 'fallout3_')
#: Converted script names, folded so one missed construct is one error kind.
_CONVERTED_NAME = re.compile(rf'\b(?:{"|".join(CONVERTED_PREFIXES)}|tes4_)\w+', re.I)
_WORD = re.compile(r'\w+')
#: A Papyrus line continued on the next (`\` at its end).
_CONTINUED = re.compile(r'\\[ \t]*\r?\n')
#: A declaration other scripts compile against: header, import, custom event, struct, function, event, property.
_DECLARATION = re.compile(r'^(?:scriptname|import|customevent|struct|endstruct'
                          r'|(?:[\w:\[\]]+ )?(?:function|event|property)\b|[\w:\[\]]+ property\b)')
#: The member a declaration line declares: a function, event, property or custom event name.
_MEMBER = re.compile(r'\b(?:function|event|property|customevent) (\w+)')
#: Per-script results of the last Fallout 4 run, in --out, so the next run compiles only what changed.
_STATE_FILE = 'compile_state.json'
#: Stamp memos (file_stamps) of the sources' facts and headers' hashes, per --out, in the cache (a build deploys --out).
_SOURCE_STAMPS, _HEADER_STAMPS = 'sources.json', 'headers.json'
_STAMPS_CACHE = _PROJECT_ROOT / 'output' / 'fo4_cache' / 'compile_stamps'


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


def _facts(path: Path) -> list:
    """[SHA-1 of a script's source, its declarations(), its sorted lower-case words]."""
    text = path.read_text(encoding='utf-8', errors='replace')
    return [hashlib.sha1(path.read_bytes()).hexdigest(), declarations(text), sorted(set(_WORD.findall(text.lower())))]


def source_facts(files: list, memo: 'Path | None' = None) -> tuple:
    """(source_hashes, source_declarations, source_words) of `files`, each file read only when its stamp changed
    since the run that wrote `memo` (fo4_import.base.file_stamps; None: read every file)."""
    stamps = Stamps(memo) if memo else None
    facts = {f.stem.lower(): stamps.value(f, _facts) if stamps else _facts(f) for f in files}
    if stamps:
        stamps.save()
    return ({n: f[0] for n, f in facts.items()}, {n: f[1] for n, f in facts.items()},
            {n: set(f[2]) for n, f in facts.items()})


def _stamps_memo(out_dir: Path, name: str) -> Path:
    """Where output folder `out_dir`'s stamp memo `name` lives (_STAMPS_CACHE)."""
    return _STAMPS_CACHE / hashlib.sha1(str(out_dir).lower().encode()).hexdigest()[:12] / name


def source_hashes(files: list) -> dict:
    """{lower-case script name: SHA-1 of its source}."""
    return source_facts(files)[0]


def declarations(text: str) -> list:
    """The sorted declaration lines of a script's source (lower case, comments and extra spaces dropped), struct
    members included: all a script naming it compiles against."""
    out, in_struct = set(), False
    for raw in _CONTINUED.sub(' ', text).splitlines():
        line = ' '.join(raw.split(';', 1)[0].lower().split())
        if line and (in_struct or _DECLARATION.match(line)):
            out.add(line)
        in_struct = (in_struct or line.startswith('struct ')) and line != 'endstruct'
    return sorted(out)


def source_declarations(files: list) -> dict:
    """{lower-case script name: its declarations()}."""
    return source_facts(files)[1]


def source_words(files: list) -> dict:
    """{lower-case script name: the lower-case words of its source}."""
    return source_facts(files)[2]


def users_index(words: dict, names: set) -> dict:
    """{lower-case script name: the scripts naming it}, from source_words()."""
    users = collections.defaultdict(set)
    for script, found in words.items():
        for word in found & names:
            users[word].add(script)
    return users


def member(line: str) -> 'str | None':
    """The member a declaration line declares; None for a header, import or struct."""
    found = _MEMBER.search(line)
    return found.group(1) if found else None


def users_of(users: dict, seeds: set) -> set:
    """Every script naming one of `seeds`, transitively (seeds not included unless named)."""
    out, queue = set(), list(seeds)
    while queue:
        for user in users[queue.pop()] - out:
            out.add(user)
            queue.append(user)
    return out


def needs_compile(hashes: dict, apis: dict, state: dict, users: dict, words: dict) -> set:
    """Changed names; users of one that lost or changed a declaration (those naming the member, for a member);
    failing users of one that added one; and every script that failed with no error of its own (through a
    script it uses, or a compiler that died, e.g. out of memory), so a failure of the run is never kept."""
    changed = {n for n, sha in hashes.items() if state.get(n, {}).get('sha') != sha}
    redeclared = {n for n in changed if state.get(n, {}).get('api') != apis[n]}
    lost = {n: {member(line) for line in set(state[n]['api']) - set(apis[n])}
            for n in redeclared if 'api' in state.get(n, {})}
    whole = {n for n in redeclared if n not in lost or None in lost[n]}
    named = {u for n, members in lost.items() if members and n not in whole
             for u in users_of(users, {n}) if words.get(u, set()) & members}
    failing = {n for n, s in state.items() if not s.get('ok') and n in hashes}
    unexplained = {n for n in failing if not state[n].get('own')}
    return changed | users_of(users, whole) | named | (users_of(users, redeclared) & failing) | unexplained


def header_digest(imports: str, src_dir: Path, memo: 'Path | None' = None) -> str:
    """SHA-1 over the path and SHA-1 of every .psc in the import folders other than `src_dir`, a file read only
    when its stamp changed since the run that wrote `memo` (None: every file)."""
    digest, stamps = hashlib.sha1(), Stamps(memo) if memo else None
    sha = lambda path: hashlib.sha1(path.read_bytes()).hexdigest()
    for folder in (Path(d).resolve() for d in imports.split(';') if d):
        if folder == src_dir:
            continue
        for path in sorted(folder.rglob('*.psc')):
            digest.update(str(path.relative_to(folder)).lower().encode() + b'\0'
                          + (stamps.value(path, sha) if stamps else sha(path)).encode())
    if stamps:
        stamps.save()
    return digest.hexdigest()


def _load_state(out_dir: Path, imports: str, headers: str) -> tuple:
    """(the last run's per-script results, {} when absent or made against other header folders or contents;
    every name it listed)."""
    path = out_dir / _STATE_FILE
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    scripts = state.get('scripts', {})
    same = state.get('imports') == imports and state.get('headers') == headers
    return (scripts if same else {}), set(scripts)


def remove_orphans(out_dir: Path, sources: set, listed: set) -> int:
    """Delete each .pex in out_dir that the last run listed and `sources` no longer has (another plugin's
    scripts in the same folder are never touched); the count."""
    gone = 0
    for pex in out_dir.glob('*.pex'):
        name = pex.stem.lower()
        if name not in sources and name in listed:
            pex.unlink()
            gone += 1
    return gone


def _compile_chunks(files: list, out_dir: Path, imports: str, workers: int, fast: bool = True) -> dict:
    """{script: [error messages]} from compiling `files`: with Caprica first when `fast` and it is bundled
    (fo4_import.base.caprica), the rest in `workers` chunk folders of FO4's compiler, as many at once as free memory
    holds (COMPILER_BYTES and COMPILER_SCRIPT_BYTES each, COMPILE_SPARE_BYTES left).
    See: docs/fork/fo4_pipeline.md#caprica
    """
    done = caprica.compile_files(files, out_dir, imports) if files and fast and caprica.available() else set()
    if done:
        print(f'Caprica compiled {len(done)} of {len(files)} files')
    files = [f for f in files if f.stem.lower() not in done]
    if not files:
        return {}
    chunks = _fo4_chunks(files, out_dir, workers)
    each = COMPILER_BYTES + COMPILER_SCRIPT_BYTES * -(-len(files) // len(chunks))
    running = memory_workers(len(chunks), each, COMPILE_SPARE_BYTES)
    at_once = f', {running} at a time (free memory)' if running < len(chunks) else ''
    print(f'Compiling {len(files)} files with FO4\'s compiler in {len(chunks)} batches{at_once}...')
    own = collections.defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=running) as ex:
        for text in ex.map(lambda c: compile_folder(c, out_dir, imports), chunks):
            for m in _FO4_LINE.finditer(text):
                if m.group(2) not in own[m.group(1)]:
                    own[m.group(1)].append(m.group(2))
    shutil.rmtree(out_dir / '_chunks')
    return {name.lower(): messages for name, messages in own.items()}


def _compile_named(files: list, names: set, out_dir: Path, imports: str, workers: int, fast: bool = True) -> tuple:
    """({script: [own errors]}, names with a .pex after) from compiling `names`, their old .pex deleted first."""
    for name in names:
        (out_dir / f'{name}.pex').unlink(missing_ok=True)
    own = _compile_chunks([f for f in files if f.stem.lower() in names], out_dir, imports, workers, fast)
    return own, {p.stem.lower() for p in out_dir.glob('*.pex')}


def compile_fallout4(args) -> tuple:
    """(compiled names, {file: [own error messages]}, source names), Caprica first (_compile_chunks).

    Compiles what needs_compile names, then users of one that started or
    stopped compiling, then once more any that failed with no error of their
    own; the rest keep the saved result, which other headers void. `--full`
    compiles everything. Old .pex files go first, as does every orphan.
    """
    src_dir, out_dir = Path(args.src).resolve(), Path(args.out).resolve()
    imports = f'{args.headers or header_dirs()};{src_dir}'
    files = sorted(src_dir.glob('*.psc'))
    hashes, apis, words = source_facts(files, _stamps_memo(out_dir, _SOURCE_STAMPS))
    headers = header_digest(imports, src_dir, _stamps_memo(out_dir, _HEADER_STAMPS))
    saved, listed = _load_state(out_dir, imports, headers)
    state = {} if args.full else saved
    removed = remove_orphans(out_dir, set(hashes), listed)
    if removed:
        print(f'{removed} .pex without a source removed')
    users = users_index(words, set(hashes))
    todo = needs_compile(hashes, apis, state, users, words)
    print(f'{len(todo)} of {len(files)} scripts changed or use one whose declarations did')
    own, pex = _compile_named(files, todo, out_dir, imports, args.workers, getattr(args, 'caprica', True))
    flipped = {n for n in todo if n in state and state[n].get('ok') != (n in pex)}
    more = users_of(users, flipped) - todo
    if more:
        print(f'{len(more)} more use one that started or stopped compiling')
        extra, pex = _compile_named(files, more, out_dir, imports, args.workers, getattr(args, 'caprica', True))
        own, todo = {**own, **extra}, todo | more
    retry = {n for n in todo if n not in pex and n not in own}
    if retry:
        print(f'{len(retry)} failed with no error of their own; compiling them again in one batch')
        extra, pex = _compile_named(files, retry, out_dir, imports, 1, getattr(args, 'caprica', True))
        own = {**own, **extra}
    scripts = {n: {**(state[n] if n not in todo else {'ok': n in pex, 'own': own.get(n, [])}),
                   'sha': hashes[n], 'api': apis[n]} for n in hashes}
    (out_dir / _STATE_FILE).write_text(json.dumps({'imports': imports, 'headers': headers, 'scripts': scripts}),
                                       encoding='utf-8')
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
    parser.add_argument('--no-caprica', dest='caprica', action='store_false',
                        help="Fallout 4: FO4's own compiler only (default: Caprica first, FO4's for what it fails)")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    sys.exit(report_fallout4(args) if args.game == 'fallout4' else report_skyrim(args))


if __name__ == '__main__':
    main()
