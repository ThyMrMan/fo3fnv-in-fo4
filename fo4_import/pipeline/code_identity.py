"""A repo function's identity as code: a SHA-1 of its syntax tree and of the module-level definitions it names.

Work keyed on the functions that ran (ran_code) then changes only when one of them, or a constant, class or
cached helper one names, changes. Keys are `<repo path>::<qualname>` as code.co_qualname spells them; a class
body's key is the class's.

See: docs/fork/fo4_plugin_layout.md#code-identity
"""

import ast
import copy
import functools
import hashlib
import os
from pathlib import Path

from fo4_import.pipeline.code_tag import ROOT, STARTED, module_file

SEP = '::'
#: How many definitions deep identity follows a name (through imports and assignments' values).
DEPTH = 4
#: Statements that bind or change a module-level name, kept in its identity.
_BINDING = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr)
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
_ROOT = os.path.normcase(str(ROOT)) + os.sep


@functools.cache
def relative(filename: str) -> 'str | None':
    """`filename`'s repo path (forward slashes) when it is a .py file in the repo; else None."""
    full = os.path.abspath(filename)
    norm = os.path.normcase(full)
    if not norm.startswith(_ROOT) or not norm.endswith('.py'):
        return None
    return Path(full).relative_to(ROOT).as_posix()


def module_name(rel: str) -> str:
    """The dotted module name of repo file `rel`."""
    parts = rel[:-3].split('/')
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def _doc(body: list) -> bool:
    """Whether `body` opens with a docstring."""
    return bool(body) and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
        and isinstance(body[0].value.value, str)


def _strip(node: ast.AST) -> ast.AST:
    """A copy of `node` without docstrings, the bodies of the functions defined inside it emptied (they run as
    functions of their own)."""
    node = copy.deepcopy(node)
    for sub in ast.walk(node):
        if isinstance(sub, _DEFS) and sub is not node:
            sub.body = []
        elif isinstance(sub, (*_DEFS, ast.ClassDef, ast.Module)) and _doc(sub.body):
            sub.body = sub.body[1:]
    return node


def _loads(node: ast.AST) -> tuple:
    """({names}, {(name, attribute)}) `node` reads: bare names, and attributes read off a bare name."""
    names, attrs = set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
            attrs.add((sub.value.id, sub.attr))
    return names, attrs


def _bound(node: ast.stmt) -> set:
    """The names a module-level binding binds or changes."""
    targets = getattr(node, 'targets', None) or [getattr(node, 'target', None) or node.value]
    return {n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)}


class Parsed:
    """One repo file's definitions: `defs` {qualname: [def or class nodes]}, `top` {module-level name: [statements
    binding or changing it]} and `imports` {name: (module, attribute or None)}."""

    def __init__(self, rel: str):
        """Parse repo file `rel` and index it."""
        self.rel, self.module = rel, module_name(rel)
        tree = ast.parse((ROOT / rel).read_bytes())
        self.defs, self.top, self.imports = {}, {}, {}
        self._qualnames(tree.body, '')
        self._index(tree.body)

    def _qualnames(self, body: list, prefix: str) -> None:
        """Index every def and class in `body` under its qualname, `prefix` before it."""
        for node in body:
            if isinstance(node, (*_DEFS, ast.ClassDef)):
                name = prefix + node.name
                self.defs.setdefault(name, []).append(node)
                self._qualnames(node.body, name + ('.' if isinstance(node, ast.ClassDef) else '.<locals>.'))
            else:
                self._qualnames([c for c in ast.iter_child_nodes(node)
                                 if isinstance(c, (ast.stmt, ast.excepthandler, ast.match_case))], prefix)

    def _index(self, body: list) -> None:
        """Index `body`'s module-level bindings and imports (inside if, try and with too)."""
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.imports.update(self._imported(node))
            elif isinstance(node, (*_DEFS, ast.ClassDef)):
                self.top.setdefault(node.name, []).append(node)
            elif isinstance(node, _BINDING):
                self._bind(node)
            else:
                self._index([c for c in ast.iter_child_nodes(node)
                             if isinstance(c, (ast.stmt, ast.excepthandler, ast.match_case))])

    def _bind(self, node: ast.stmt) -> None:
        """Index binding `node` under every name it binds."""
        for name in _bound(node):
            self.top.setdefault(name, []).append(node)

    def _imported(self, node: 'ast.Import | ast.ImportFrom') -> dict:
        """{name: (module, attribute or None)} an import statement binds."""
        if isinstance(node, ast.Import):
            return {a.asname or a.name.split('.')[0]: (a.name if a.asname else a.name.split('.')[0], None)
                    for a in node.names}
        base = self._from(node)
        return {a.asname or a.name: (base, a.name) for a in node.names}

    def _from(self, node: ast.ImportFrom) -> str:
        """The absolute module an ImportFrom reads from."""
        if not node.level:
            return node.module or ''
        package = self.module.split('.') if self.rel.endswith('__init__.py') else self.module.split('.')[:-1]
        package = package[:len(package) - node.level + 1]
        return '.'.join(package + ([node.module] if node.module else []))


@functools.lru_cache(maxsize=4096)
def _parsed_at(rel: str, stamp: tuple) -> Parsed:
    """Repo file `rel` parsed, for its (size, mtime) `stamp`."""
    return Parsed(rel)


def parsed(rel: str) -> 'Parsed | None':
    """Repo file `rel` parsed as it is now; None when it is gone or not Python."""
    try:
        stat = (ROOT / rel).stat()
        return _parsed_at(rel, (stat.st_size, stat.st_mtime_ns))
    except (OSError, SyntaxError, ValueError):
        return None


def parsed_module(name: str) -> 'Parsed | None':
    """Module `name` parsed, when it is a repo module."""
    path = module_file(name)
    return parsed(path.relative_to(ROOT).as_posix()) if path else None


class _Walk:
    """The definitions one identity takes in: `parts` {(file, name): [dumps]} and `files` read."""

    def __init__(self):
        """Nothing taken in yet."""
        self.parts, self.files = {}, set()

    def names(self, where: Parsed, node: ast.AST, depth: int, whole: bool) -> None:
        """Take in what `node` names in `where`; `whole`: plain functions too (named where they run at import)."""
        if depth <= 0:
            return
        names, attrs = _loads(node)
        for name in sorted(names):
            self.resolve(where, name, depth, whole)
        for name, attr in sorted(attrs):
            target = self.alias(where, name)
            if target is not None:
                self.resolve(target, attr, depth, whole)

    def alias(self, where: Parsed, name: str) -> 'Parsed | None':
        """The repo module `name` stands for in `where` (`import x as name`, `from pkg import name`), if one."""
        if name not in where.imports or name in where.top:
            return None
        module, attr = where.imports[name]
        return parsed_module(f'{module}.{attr}' if attr else module)

    def resolve(self, where: Parsed, name: str, depth: int, whole: bool) -> None:
        """Take in module-level `name` of `where`: its bindings, or the definition it imports."""
        if (where.rel, name) in self.parts:
            return
        self.files.add(where.rel)
        stmts = where.top.get(name, [])
        kept = [(s, _strip(s)) for s in stmts if whole or not isinstance(s, _DEFS) or s.decorator_list]
        self.parts[where.rel, name] = [ast.dump(bare) for _, bare in kept]
        for stmt, bare in kept:
            self.names(where, bare, depth - 1, whole or isinstance(stmt, _BINDING))
        if not stmts and name in where.imports and where.imports[name][1]:
            target = parsed_module(where.imports[name][0])
            if target is not None:
                self.resolve(target, where.imports[name][1], depth - 1, whole)


@functools.cache
def identity(key: str) -> 'str | None':
    """The identity of `key` (module notes); None when its file or definition is gone, or a file it takes in
    changed after this process started (the code running is not the code on disk)."""
    rel, _, qualname = key.partition(SEP)
    where = parsed(rel)
    if where is None or qualname not in where.defs:
        return None
    walk, digest = _Walk(), hashlib.sha1()
    walk.files.add(rel)
    for node in map(_strip, where.defs[qualname]):
        digest.update(ast.dump(node).encode())
        walk.names(where, node, DEPTH, False)
    for part in sorted(walk.parts):
        digest.update(repr((part, walk.parts[part])).encode())
    if any((ROOT / f).stat().st_mtime > STARTED for f in walk.files):
        return None
    return digest.hexdigest()


def module_keys(rel: str) -> list:
    """The key of every def and class in repo file `rel`."""
    where = parsed(rel)
    return [rel + SEP + name for name in where.defs] if where else []


def hashes(keys) -> dict:
    """{key: identity} of `keys`."""
    return {key: identity(key) for key in sorted(keys)}


def changed(recorded: dict) -> 'str | None':
    """The first key of `recorded` whose identity changed or is unknown; else None."""
    return next((key for key, value in recorded.items() if value is None or identity(key) != value), None)
