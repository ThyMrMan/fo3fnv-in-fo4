"""A cache's code version: a SHA-1 over a module's source and every repo module it imports, transitively.

Editing any file the cached work runs through gives a new tag, so a cache
never needs a hand-bumped version.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import ast
import functools
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module_file(name: str) -> 'Path | None':
    """Module `name`'s repo file; None outside the repo (standard library, pyffi)."""
    base = ROOT.joinpath(*name.split('.'))
    return next((p for p in (base.with_suffix('.py'), base / '__init__.py') if p.is_file()), None)


def imported(path: Path, package: str) -> set:
    """The module names the file at `path` (in `package`) imports, each `from` name also as a submodule."""
    out = set()
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            out |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            parts = package.split('.')[:len(package.split('.')) - node.level + 1] if node.level else []
            base = '.'.join(parts + ([node.module] if node.module else []))
            out |= {base} | {f'{base}.{alias.name}' for alias in node.names}
    return out


@functools.cache
def code_tag(module: str) -> str:
    """The SHA-1 of `module`'s source and its repo imports' (the module notes)."""
    files, todo = {}, [module]
    while todo:
        name = todo.pop()
        path = module_file(name)
        if path is None or name in files:
            continue
        files[name] = path
        todo += imported(path, name if path.name == '__init__.py' else name.rpartition('.')[0])
    digest = hashlib.sha1()
    for name in sorted(files):
        digest.update(name.encode() + b'\0' + files[name].read_bytes())
    return digest.hexdigest()
