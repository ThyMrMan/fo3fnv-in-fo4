"""A cache's code version: a SHA-1 over a module's source, every repo module it imports, transitively, and the
native extensions they load.

Editing any file the cached work runs through gives a new tag, so a cache
never needs a hand-bumped version. A native extension in native/dist counts
when a closure file names it in a string (nif_geom_native loads
`_nifgeom_native` by path). An import edge in IGNORED is not followed: its
importer uses that module only in the function named, which no FO4
converter calls (they read exports with parse_export_file and get_hex_bytes).
Sources are hashed with CRLF read as LF, so a CRLF checkout of the same code
(a git worktree) keeps the tag; native extensions are hashed as they are.

See: docs/fork/fo4_tool_audit.md#rebuild
"""

import ast
import functools
import hashlib
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'native' / 'dist'
#: The file name ending of a native extension this interpreter loads.
EXT_SUFFIX = sysconfig.get_config_var('EXT_SUFFIX') or '.pyd'
#: {(importer, imported): the importer's only function using it}: edges code_tag does not follow (module notes).
IGNORED = {('asset_convert.texture.parallax', 'asset_convert.game_paths'): 'strip_diffuse_alpha',
           ('tes5_import.base.text_reader', 'tes5_import.base.equivalents'): 'get_formid',
           ('asset_convert.sources.source_registry', 'version'): 'migrate_known_directories',
           ('asset_convert.texture.image_transcode', 'asset_convert.nif.tex_paths'): 'run'}


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


def natives(path: Path) -> set:
    """The native extension files in NATIVE the source at `path` names in a string."""
    names = {n.value for n in ast.walk(ast.parse(path.read_bytes()))
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier()}
    return {NATIVE / f'{name}{EXT_SUFFIX}' for name in names if (NATIVE / f'{name}{EXT_SUFFIX}').is_file()}


def _followed(importer: str, name: str) -> bool:
    """Whether code_tag follows `importer`'s import of `name` (not an IGNORED edge)."""
    return not any(importer == a and (name == b or name.startswith(b + '.')) for a, b in IGNORED)


def tagged_files(module: str) -> dict:
    """{name: file} of everything code_tag(`module`) hashes: repo modules by name, native extensions by file name."""
    files, todo = {}, [module]
    while todo:
        name = todo.pop()
        path = module_file(name)
        if path is None or name in files:
            continue
        files[name] = path
        package = name if path.name == '__init__.py' else name.rpartition('.')[0]
        todo += [n for n in imported(path, package) if _followed(name, n)]
    return {**files, **{p.name: p for path in list(files.values()) for p in natives(path)}}


@functools.cache
def code_tag(module: str) -> str:
    """The SHA-1 of `module`'s source, its repo imports' and the native extensions they load (the module notes)."""
    files = tagged_files(module)
    digest = hashlib.sha1()
    for name in sorted(files):
        data = files[name].read_bytes()
        digest.update(name.encode() + b'\0' + (data.replace(b'\r\n', b'\n') if files[name].suffix == '.py' else data))
    return digest.hexdigest()
